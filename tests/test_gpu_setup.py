"""
Tests for HEMS GPU auto-detection and setup script.
"""
import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

# Import gpu_setup from infra/scripts
_scripts_dir = str(Path(__file__).resolve().parent.parent / "infra" / "scripts")
sys.path.insert(0, _scripts_dir)
import gpu_setup

sys.path.remove(_scripts_dir)


# -- GPU Detection Tests --


class TestDetectNvidia:
    def test_nvidia_detected(self):
        csv = "NVIDIA GeForce RTX 4090, 24564, 550.54, 00000000:01:00.0\n"
        with patch("gpu_setup.subprocess.check_output", return_value=csv):
            gpu = gpu_setup.detect_nvidia()
        assert gpu is not None
        assert gpu.vendor == "nvidia"
        assert gpu.name == "NVIDIA GeForce RTX 4090"
        assert gpu.vram_mb == 24564
        assert gpu.driver_version == "550.54"

    def test_nvidia_not_available(self):
        with patch("gpu_setup.subprocess.check_output",
                   side_effect=FileNotFoundError):
            gpu = gpu_setup.detect_nvidia()
        assert gpu is None

    def test_nvidia_smi_fails(self):
        from subprocess import CalledProcessError
        with patch("gpu_setup.subprocess.check_output",
                   side_effect=CalledProcessError(1, "nvidia-smi")):
            gpu = gpu_setup.detect_nvidia()
        assert gpu is None

    def test_nvidia_empty_output(self):
        with patch("gpu_setup.subprocess.check_output", return_value=""):
            gpu = gpu_setup.detect_nvidia()
        assert gpu is None

    def test_nvidia_multi_gpu_picks_first(self):
        csv = (
            "NVIDIA GeForce RTX 4090, 24564, 550.54, 00000000:01:00.0\n"
            "NVIDIA GeForce RTX 3060, 12288, 550.54, 00000000:02:00.0\n"
        )
        with patch("gpu_setup.subprocess.check_output", return_value=csv):
            gpu = gpu_setup.detect_nvidia()
        assert gpu.name == "NVIDIA GeForce RTX 4090"
        assert gpu.vram_mb == 24564


class TestDetectAmd:
    def test_amd_detected(self):
        rocm_vram = "GPU[0], vram Total Memory (B), 17163091968\n"
        rocm_name = "Card Series:\t\tRadeon RX 7900 XT\n"

        def mock_check_output(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "--showmeminfo" in cmd_str:
                return rocm_vram
            if "--showproductname" in cmd_str:
                return rocm_name
            if "--showuniqueid" in cmd_str:
                return ""
            raise FileNotFoundError

        with patch("gpu_setup.subprocess.check_output", side_effect=mock_check_output), \
             patch("gpu_setup.os.path.exists", return_value=True), \
             patch("gpu_setup.os.path.isdir", return_value=False):
            gpu = gpu_setup.detect_amd(card_override="/dev/dri/card1")

        assert gpu is not None
        assert gpu.vendor == "amd"
        assert gpu.name == "Radeon RX 7900 XT"
        assert gpu.vram_mb == 17163091968 // (1024 * 1024)  # ~16GB
        assert gpu.card_device == "/dev/dri/card1"
        assert gpu.render_device == "/dev/dri/renderD129"

    def test_amd_no_kfd(self):
        with patch("gpu_setup.os.path.exists", return_value=False):
            gpu = gpu_setup.detect_amd()
        assert gpu is None

    def test_amd_card_override_card0(self):
        with patch("gpu_setup.subprocess.check_output",
                   side_effect=FileNotFoundError), \
             patch("gpu_setup.os.path.exists", return_value=True), \
             patch("gpu_setup.os.path.isdir", return_value=False):
            gpu = gpu_setup.detect_amd(card_override="/dev/dri/card0")
        assert gpu is not None
        assert gpu.card_device == "/dev/dri/card0"
        assert gpu.render_device == "/dev/dri/renderD128"


class TestDetectGpuLspci:
    def test_nvidia_via_lspci(self):
        lspci_out = (
            "00:02.0 VGA compatible controller: Intel UHD Graphics\n"
            "01:00.0 3D controller: NVIDIA Corporation GA102 [GeForce RTX 3090]\n"
        )
        with patch("gpu_setup.subprocess.check_output", return_value=lspci_out):
            gpu = gpu_setup.detect_gpu_lspci()
        assert gpu is not None
        assert gpu.vendor == "nvidia"

    def test_amd_via_lspci(self):
        lspci_out = "06:00.0 VGA compatible controller: AMD/ATI Navi 31 [Radeon RX 7900 XT]\n"
        with patch("gpu_setup.subprocess.check_output", return_value=lspci_out):
            gpu = gpu_setup.detect_gpu_lspci()
        assert gpu is not None
        assert gpu.vendor == "amd"

    def test_no_gpu_lspci(self):
        lspci_out = "00:02.0 VGA compatible controller: Intel UHD Graphics 630\n"
        with patch("gpu_setup.subprocess.check_output", return_value=lspci_out):
            gpu = gpu_setup.detect_gpu_lspci()
        assert gpu is None

    def test_lspci_not_available(self):
        with patch("gpu_setup.subprocess.check_output",
                   side_effect=FileNotFoundError):
            gpu = gpu_setup.detect_gpu_lspci()
        assert gpu is None


class TestDetectGpu:
    def test_force_nvidia(self):
        csv = "NVIDIA RTX 4070, 12288, 550.54, 00000000:01:00.0\n"
        with patch("gpu_setup.subprocess.check_output", return_value=csv):
            gpu = gpu_setup.detect_gpu(force_vendor="nvidia")
        assert gpu.vendor == "nvidia"
        assert gpu.vram_mb == 12288

    def test_force_nvidia_no_smi(self):
        with patch("gpu_setup.subprocess.check_output",
                   side_effect=FileNotFoundError):
            gpu = gpu_setup.detect_gpu(force_vendor="nvidia")
        assert gpu.vendor == "nvidia"
        assert gpu.name == "NVIDIA GPU (forced)"

    def test_force_amd(self):
        with patch("gpu_setup.subprocess.check_output",
                   side_effect=FileNotFoundError), \
             patch("gpu_setup.os.path.exists", return_value=False), \
             patch("gpu_setup.os.path.isdir", return_value=False):
            gpu = gpu_setup.detect_gpu(force_vendor="amd",
                                       amd_card="/dev/dri/card1")
        assert gpu.vendor == "amd"
        assert gpu.card_device == "/dev/dri/card1"
        assert gpu.render_device == "/dev/dri/renderD129"

    def test_force_none(self):
        gpu = gpu_setup.detect_gpu(force_vendor="none")
        assert gpu.vendor == "none"

    def test_auto_detect_order(self):
        """NVIDIA checked first, then AMD, then lspci."""
        with patch("gpu_setup.detect_nvidia", return_value=None) as nvidia_mock, \
             patch("gpu_setup.detect_amd", return_value=None) as amd_mock, \
             patch("gpu_setup.detect_gpu_lspci", return_value=None) as lspci_mock:
            gpu = gpu_setup.detect_gpu()
            nvidia_mock.assert_called_once()
            amd_mock.assert_called_once()
            lspci_mock.assert_called_once()
            assert gpu.vendor == "none"


# -- Compose Override Tests --


class TestGenerateComposeOverride:
    def test_nvidia_override(self):
        gpu = gpu_setup.GPUInfo(vendor="nvidia", name="RTX 4090", vram_mb=24564)
        override = gpu_setup.generate_compose_override(gpu)

        assert "services:" in override
        assert "ollama/ollama" in override
        assert "driver: nvidia" in override
        assert "count: 1" in override
        assert "capabilities: [gpu]" in override

    def test_amd_override(self):
        gpu = gpu_setup.GPUInfo(
            vendor="amd", name="RX 7900 XT", vram_mb=16384,
            card_device="/dev/dri/card1",
            render_device="/dev/dri/renderD129",
            hsa_version="12.0.1",
        )
        override = gpu_setup.generate_compose_override(gpu)

        assert "ollama/ollama:rocm" in override
        assert "/dev/kfd:/dev/kfd" in override
        assert "/dev/dri/card1:/dev/dri/card1" in override
        assert "/dev/dri/renderD129:/dev/dri/renderD129" in override
        assert "HSA_OVERRIDE_GFX_VERSION" in override

    def test_cpu_override_empty(self):
        gpu = gpu_setup.GPUInfo(vendor="none")
        override = gpu_setup.generate_compose_override(gpu)
        assert override == ""


class TestWriteComposeOverride:
    def test_write_nvidia(self, tmp_path):
        gpu = gpu_setup.GPUInfo(vendor="nvidia", name="RTX 4090", vram_mb=24564)
        override = gpu_setup.generate_compose_override(gpu)
        out_path = tmp_path / "docker-compose.gpu.yml"
        gpu_setup.write_compose_override(override, out_path)

        content = out_path.read_text()
        assert "ollama/ollama" in content
        assert "nvidia" in content

    def test_write_cpu_comment(self, tmp_path):
        out_path = tmp_path / "docker-compose.gpu.yml"
        gpu_setup.write_compose_override("", out_path)

        content = out_path.read_text()
        assert "CPU-only" in content


# -- Model Recommendation Tests --


class TestRecommendModels:
    def test_4gb_vram(self):
        models = gpu_setup.recommend_models(4000)
        assert len(models) == 1
        assert models[0]["tier"] == "~4GB"
        assert "gemma2:2b" in models[0]["models"]

    def test_8gb_vram(self):
        models = gpu_setup.recommend_models(8192)
        tiers = [m["tier"] for m in models]
        assert "~4GB" in tiers
        assert "~8GB" in tiers
        assert "~12-16GB" not in tiers

    def test_8gb_includes_swallow(self):
        models = gpu_setup.recommend_models(8192)
        tier_8gb = [m for m in models if m["tier"] == "~8GB"][0]
        assert "okamototk/llama-swallow:8b" in tier_8gb["models"]

    def test_12gb_includes_gpt_oss(self):
        models = gpu_setup.recommend_models(12288)
        tier_12 = [m for m in models if m["tier"] == "~12-16GB"][0]
        assert "gpt-oss:20b" in tier_12["models"]

    def test_16gb_vram(self):
        models = gpu_setup.recommend_models(16384)
        tiers = [m["tier"] for m in models]
        assert "~12-16GB" in tiers
        assert "~24GB+" not in tiers

    def test_24gb_vram(self):
        models = gpu_setup.recommend_models(24576)
        tiers = [m["tier"] for m in models]
        assert "~24GB+" in tiers
        assert len(tiers) == 4  # All tiers available

    def test_unknown_vram_returns_all(self):
        models = gpu_setup.recommend_models(0)
        assert len(models) == len(gpu_setup.MODEL_RECOMMENDATIONS)


class TestMatchingHfModels:
    def test_hf_models_with_enough_vram(self):
        hf = gpu_setup._matching_hf_models(16384)
        assert "gpt-oss-swallow:20b" in hf
        assert hf["gpt-oss-swallow:20b"]["hf_repo"] == \
            "tokyotech-llm/GPT-OSS-Swallow-20B-RL-v0.1"

    def test_hf_models_insufficient_vram(self):
        hf = gpu_setup._matching_hf_models(4000)
        assert "gpt-oss-swallow:20b" not in hf

    def test_hf_models_unknown_vram_returns_all(self):
        hf = gpu_setup._matching_hf_models(0)
        assert "gpt-oss-swallow:20b" in hf


# -- .env Update Tests --


class TestUpdateEnv:
    def test_update_existing_env(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("GPU_TYPE=none\nLOG_LEVEL=INFO\n")

        gpu = gpu_setup.GPUInfo(vendor="nvidia", name="RTX 4090", vram_mb=24564)
        gpu_setup.update_env(gpu, env_path=env_file)

        content = env_file.read_text()
        assert "GPU_TYPE=nvidia" in content
        assert "GPU_NAME=RTX 4090" in content
        assert "GPU_VRAM_MB=24564" in content
        assert "LOG_LEVEL=INFO" in content  # Preserved

    def test_update_with_model(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("GPU_TYPE=none\nLLM_MODEL=mock\n")

        gpu = gpu_setup.GPUInfo(vendor="nvidia", name="RTX 4090", vram_mb=24564)
        gpu_setup.update_env(gpu, model="qwen2.5:14b", env_path=env_file)

        content = env_file.read_text()
        assert "LLM_MODEL=qwen2.5:14b" in content
        assert "LLM_PROVIDER=ollama" in content

    def test_amd_sets_hsa(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("GPU_TYPE=none\n")

        gpu = gpu_setup.GPUInfo(
            vendor="amd", name="RX 7900", vram_mb=16384,
            hsa_version="11.0.0",
        )
        gpu_setup.update_env(gpu, env_path=env_file)

        content = env_file.read_text()
        assert "GPU_TYPE=amd" in content
        assert "HSA_OVERRIDE_GFX_VERSION=11.0.0" in content

    def test_preserves_comments(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# System config\nGPU_TYPE=none\n# End\n")

        gpu = gpu_setup.GPUInfo(vendor="nvidia", name="RTX", vram_mb=8192)
        gpu_setup.update_env(gpu, env_path=env_file)

        content = env_file.read_text()
        assert "# System config" in content
        assert "# End" in content


# -- nvidia-container-toolkit Check --


class TestCheckNvidiaContainerToolkit:
    def test_ctk_installed(self):
        with patch("gpu_setup.subprocess.check_output", return_value="1.14.0\n"):
            assert gpu_setup.check_nvidia_container_toolkit() is True

    def test_docker_info_has_nvidia(self):
        def mock_check(cmd, **kwargs):
            if "nvidia-ctk" in cmd:
                raise FileNotFoundError
            return "Runtimes: io.containerd.runc.v2 nvidia runc\n"

        with patch("gpu_setup.subprocess.check_output", side_effect=mock_check):
            assert gpu_setup.check_nvidia_container_toolkit() is True

    def test_nothing_installed(self):
        with patch("gpu_setup.subprocess.check_output",
                   side_effect=FileNotFoundError):
            assert gpu_setup.check_nvidia_container_toolkit() is False


# -- Resolve AMD Devices --


class TestResolveAmdDevices:
    def test_card_override(self):
        card, render = gpu_setup._resolve_amd_devices("/dev/dri/card2")
        assert card == "/dev/dri/card2"
        assert render == "/dev/dri/renderD130"

    def test_card0_override(self):
        card, render = gpu_setup._resolve_amd_devices("/dev/dri/card0")
        assert card == "/dev/dri/card0"
        assert render == "/dev/dri/renderD128"

    def test_no_devices_found(self):
        with patch("gpu_setup.os.path.isdir", return_value=False), \
             patch("gpu_setup.os.path.exists", return_value=False):
            card, render = gpu_setup._resolve_amd_devices()
        assert card == ""
        assert render == ""
