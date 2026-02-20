#!/usr/bin/env python3
"""
GPU auto-detection and Docker Compose override generator for HEMS Ollama.

Detects NVIDIA/AMD GPUs, generates docker-compose.gpu.yml override,
updates .env with GPU info, and recommends models based on VRAM.

Usage:
    python infra/scripts/gpu_setup.py
    python infra/scripts/gpu_setup.py --non-interactive
    python infra/scripts/gpu_setup.py --force-vendor=nvidia
    python infra/scripts/gpu_setup.py --force-vendor=amd --amd-card=/dev/dri/card1
"""
import argparse
import os
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
INFRA_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = INFRA_DIR.parent
OVERRIDE_PATH = INFRA_DIR / "docker-compose.gpu.yml"
ENV_PATH = PROJECT_ROOT / ".env"

MODEL_RECOMMENDATIONS = [
    {"vram_min": 0, "models": [
        "gemma2:2b", "qwen2.5:3b", "phi3:mini",
    ], "tier": "~4GB", "desc": "Lightweight (2-4B params)"},
    {"vram_min": 6144, "models": [
        "qwen2.5:7b", "llama3.1:8b", "mistral:7b",
    ], "tier": "~8GB", "desc": "General purpose (7-8B params)"},
    {"vram_min": 10240, "models": [
        "qwen2.5:14b", "deepseek-r1:14b",
    ], "tier": "~12-16GB", "desc": "Strong Japanese support (14B params)"},
    {"vram_min": 20480, "models": [
        "qwen2.5:32b", "deepseek-r1:32b",
    ], "tier": "~24GB+", "desc": "High performance (32B params)"},
]


@dataclass
class GPUInfo:
    vendor: str  # "nvidia", "amd", "none"
    name: str = "Unknown"
    vram_mb: int = 0
    driver_version: str = ""
    # AMD-specific
    card_device: str = ""
    render_device: str = ""
    hsa_version: str = ""


def detect_nvidia() -> Optional[GPUInfo]:
    """Detect NVIDIA GPU using nvidia-smi."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version,pci.bus_id",
             "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    if not out:
        return None

    # Take first GPU line
    line = out.splitlines()[0]
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 3:
        return None

    return GPUInfo(
        vendor="nvidia",
        name=parts[0],
        vram_mb=int(float(parts[1])),
        driver_version=parts[2],
    )


def detect_amd(card_override: Optional[str] = None) -> Optional[GPUInfo]:
    """Detect AMD GPU using rocm-smi and /dev/dri."""
    # Check for /dev/kfd (ROCm kernel driver)
    if not os.path.exists("/dev/kfd"):
        return None

    name = "AMD GPU"
    vram_mb = 0

    # Try rocm-smi for VRAM info
    try:
        out = subprocess.check_output(
            ["rocm-smi", "--showmeminfo", "vram", "--csv"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            for p in parts:
                # Extract any large number as VRAM candidate
                try:
                    val = int(p)
                    if val > 1_000_000:  # Bytes → MB
                        vram_mb = max(vram_mb, val // (1024 * 1024))
                    elif val > 1000:  # Already MB
                        vram_mb = max(vram_mb, val)
                except ValueError:
                    continue
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # Try rocm-smi for GPU name
    try:
        out = subprocess.check_output(
            ["rocm-smi", "--showproductname"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
        for line in out.splitlines():
            if "Card Series" in line or "Card Model" in line:
                match = re.search(r":\s*(.+)", line)
                if match:
                    name = match.group(1).strip()
                    break
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # Resolve device nodes
    card_device, render_device = _resolve_amd_devices(card_override)
    if not card_device:
        return None

    # Detect HSA version from amdgpu driver
    hsa_version = _detect_hsa_version()

    return GPUInfo(
        vendor="amd",
        name=name,
        vram_mb=vram_mb,
        card_device=card_device,
        render_device=render_device,
        hsa_version=hsa_version,
    )


def _resolve_amd_devices(card_override: Optional[str] = None) -> tuple[str, str]:
    """Resolve AMD GPU card and render device nodes."""
    if card_override:
        card = card_override
        # Derive renderD node: card0 → renderD128, card1 → renderD129, etc.
        match = re.search(r"card(\d+)", card)
        if match:
            render_num = 128 + int(match.group(1))
            render = f"/dev/dri/renderD{render_num}"
        else:
            render = "/dev/dri/renderD128"
        return card, render

    # Auto-detect: look for discrete GPU via by-path symlinks
    by_path = "/dev/dri/by-path/"
    if os.path.isdir(by_path):
        for link in sorted(os.listdir(by_path)):
            if "card" in link:
                target = os.path.realpath(os.path.join(by_path, link))
                match = re.search(r"card(\d+)", target)
                if match:
                    render_num = 128 + int(match.group(1))
                    render = f"/dev/dri/renderD{render_num}"
                    return target, render

    # Fallback: use card0/card1 if they exist
    for card_num in [1, 0]:
        card = f"/dev/dri/card{card_num}"
        if os.path.exists(card):
            render = f"/dev/dri/renderD{128 + card_num}"
            return card, render

    return "", ""


def _detect_hsa_version() -> str:
    """Try to detect appropriate HSA_OVERRIDE_GFX_VERSION."""
    try:
        out = subprocess.check_output(
            ["rocm-smi", "--showuniqueid"],
            stderr=subprocess.DEVNULL, text=True,
        )
        # This is a best-effort heuristic; users should verify
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    return "12.0.1"  # Safe default for modern AMD GPUs


def detect_gpu_lspci() -> Optional[GPUInfo]:
    """Fallback GPU detection via lspci."""
    try:
        out = subprocess.check_output(
            ["lspci"], stderr=subprocess.DEVNULL, text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    for line in out.splitlines():
        if "VGA" in line or "3D" in line:
            lower = line.lower()
            if "nvidia" in lower:
                return GPUInfo(vendor="nvidia", name=line.split(":")[-1].strip())
            if "amd" in lower or "radeon" in lower:
                return GPUInfo(vendor="amd", name=line.split(":")[-1].strip())

    return None


def check_nvidia_container_toolkit() -> bool:
    """Check if nvidia-container-toolkit is installed."""
    # Check nvidia-ctk
    try:
        subprocess.check_output(
            ["nvidia-ctk", "--version"],
            stderr=subprocess.DEVNULL, text=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # Check docker info for nvidia runtime
    try:
        out = subprocess.check_output(
            ["docker", "info"],
            stderr=subprocess.DEVNULL, text=True,
        )
        if "nvidia" in out.lower():
            return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    return False


def detect_gpu(force_vendor: Optional[str] = None,
               amd_card: Optional[str] = None) -> GPUInfo:
    """Main GPU detection logic."""
    if force_vendor:
        if force_vendor == "nvidia":
            gpu = detect_nvidia()
            if gpu:
                return gpu
            # Forced but no nvidia-smi — return minimal info
            return GPUInfo(vendor="nvidia", name="NVIDIA GPU (forced)")
        elif force_vendor == "amd":
            gpu = detect_amd(amd_card)
            if gpu:
                return gpu
            # Forced but no rocm — return with provided/default devices
            card = amd_card or "/dev/dri/card1"
            match = re.search(r"card(\d+)", card)
            render_num = 128 + int(match.group(1)) if match else 128
            return GPUInfo(
                vendor="amd", name="AMD GPU (forced)",
                card_device=card,
                render_device=f"/dev/dri/renderD{render_num}",
                hsa_version="12.0.1",
            )
        else:
            return GPUInfo(vendor="none")

    # Auto-detect: NVIDIA first, then AMD, then lspci fallback
    gpu = detect_nvidia()
    if gpu:
        return gpu

    gpu = detect_amd(amd_card)
    if gpu:
        return gpu

    gpu = detect_gpu_lspci()
    if gpu:
        return gpu

    return GPUInfo(vendor="none")


def generate_compose_override(gpu: GPUInfo) -> str:
    """Generate docker-compose.gpu.yml content as a YAML string."""
    if gpu.vendor == "nvidia":
        return textwrap.dedent("""\
            services:
              ollama:
                image: ollama/ollama
                deploy:
                  resources:
                    reservations:
                      devices:
                        - driver: nvidia
                          count: 1
                          capabilities: [gpu]
        """)
    elif gpu.vendor == "amd":
        hsa_val = gpu.hsa_version or "12.0.1"
        return textwrap.dedent(f"""\
            services:
              ollama:
                image: ollama/ollama:rocm
                devices:
                  - /dev/kfd:/dev/kfd
                  - {gpu.card_device}:{gpu.card_device}
                  - {gpu.render_device}:{gpu.render_device}
                environment:
                  - HSA_OVERRIDE_GFX_VERSION=${{HSA_OVERRIDE_GFX_VERSION:-{hsa_val}}}
        """)
    else:
        return ""


def write_compose_override(content: str, path: Path = OVERRIDE_PATH) -> None:
    """Write docker-compose.gpu.yml."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        if content:
            f.write(content)
        else:
            f.write("# CPU-only mode: no GPU override needed\n")


def recommend_models(vram_mb: int) -> list[dict]:
    """Return model recommendation tiers matching the available VRAM."""
    if vram_mb <= 0:
        # Unknown VRAM — return all tiers
        return MODEL_RECOMMENDATIONS[:]

    results = []
    for tier in MODEL_RECOMMENDATIONS:
        if vram_mb >= tier["vram_min"]:
            results.append(tier)
    return results


def update_env(gpu: GPUInfo, model: Optional[str] = None,
               env_path: Path = ENV_PATH) -> None:
    """Update .env file with GPU configuration."""
    updates = {
        "GPU_TYPE": gpu.vendor if gpu.vendor != "none" else "none",
        "GPU_NAME": gpu.name,
        "GPU_VRAM_MB": str(gpu.vram_mb) if gpu.vram_mb > 0 else "",
    }

    if gpu.vendor == "amd" and gpu.hsa_version:
        updates["HSA_OVERRIDE_GFX_VERSION"] = gpu.hsa_version

    if model:
        updates["LLM_MODEL"] = model
        updates["LLM_PROVIDER"] = "ollama"
        updates["LLM_API_URL"] = "http://ollama:11434/v1"

    _merge_env_file(updates, env_path)


def _merge_env_file(updates: dict, env_path: Path) -> None:
    """Merge key=value updates into .env file, preserving other content."""
    lines = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                val = updates[key]
                new_lines.append(f"{key}={val}" if val else f"# {key}=")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # Append new keys not found in existing file
    for key, val in updates.items():
        if key not in updated_keys:
            if val:
                new_lines.append(f"{key}={val}")
            else:
                new_lines.append(f"# {key}=")

    env_path.write_text("\n".join(new_lines) + "\n")


def print_summary(gpu: GPUInfo, models: list[dict]) -> None:
    """Print detection summary."""
    print("\n=== HEMS GPU Setup ===\n")

    if gpu.vendor == "none":
        print("GPU: Not detected (CPU-only mode)")
        print("Ollama will run on CPU. Performance will be limited.")
    else:
        print(f"GPU:    {gpu.name}")
        print(f"Vendor: {gpu.vendor.upper()}")
        if gpu.vram_mb > 0:
            print(f"VRAM:   {gpu.vram_mb} MB ({gpu.vram_mb / 1024:.1f} GB)")
        if gpu.driver_version:
            print(f"Driver: {gpu.driver_version}")

    if gpu.vendor == "nvidia":
        has_toolkit = check_nvidia_container_toolkit()
        if has_toolkit:
            print("\nnvidia-container-toolkit: installed")
        else:
            print("\n[WARNING] nvidia-container-toolkit not found!")
            print("Install it to use NVIDIA GPU with Docker:")
            print("  Ubuntu/Debian:")
            print("    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \\")
            print("      | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg")
            print("    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \\")
            print("      | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \\")
            print("      | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list")
            print("    sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit")
            print("    sudo nvidia-ctk runtime configure --runtime=docker")
            print("    sudo systemctl restart docker")

    print(f"\nOverride: {OVERRIDE_PATH}")

    if models:
        print("\nRecommended models:")
        for tier in models:
            print(f"  [{tier['tier']}] {tier['desc']}")
            for m in tier["models"]:
                print(f"    - {m}")


def interactive_model_select(models: list[dict]) -> Optional[str]:
    """Interactive model selection prompt."""
    all_models = []
    for tier in models:
        for m in tier["models"]:
            all_models.append((m, tier["tier"], tier["desc"]))

    if not all_models:
        return None

    print("\nSelect a model to configure (or press Enter to skip):\n")
    for i, (model, tier, desc) in enumerate(all_models, 1):
        print(f"  {i}) {model}  [{tier}]")

    print()
    try:
        choice = input("Choice [skip]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not choice:
        return None

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(all_models):
            selected = all_models[idx][0]
            print(f"\nSelected: {selected}")
            print(f"\nAfter starting Ollama, pull the model with:")
            print(f"  docker exec hems-ollama ollama pull {selected}")
            return selected
    except ValueError:
        pass

    print("Skipping model selection.")
    return None


def main():
    parser = argparse.ArgumentParser(description="HEMS GPU auto-detection and setup")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Skip interactive model selection")
    parser.add_argument("--force-vendor", choices=["nvidia", "amd", "none"],
                        help="Force GPU vendor instead of auto-detecting")
    parser.add_argument("--amd-card",
                        help="AMD card device path (e.g. /dev/dri/card1)")
    args = parser.parse_args()

    # Detect GPU
    gpu = detect_gpu(force_vendor=args.force_vendor, amd_card=args.amd_card)

    # Generate and write compose override
    override = generate_compose_override(gpu)
    write_compose_override(override)

    # Get model recommendations
    models = recommend_models(gpu.vram_mb)

    # Print summary
    print_summary(gpu, models)

    # Interactive model selection
    selected_model = None
    if not args.non_interactive and gpu.vendor != "none":
        selected_model = interactive_model_select(models)

    # Update .env
    if ENV_PATH.exists():
        update_env(gpu, selected_model)
        print(f"\nUpdated: {ENV_PATH}")

    # Print launch command
    print("\nTo start Ollama with GPU support:")
    if override:
        print("  cd infra && docker compose -f docker-compose.yml -f docker-compose.gpu.yml \\")
        print("    --profile ollama up -d --build")
    else:
        print("  cd infra && docker compose --profile ollama up -d --build")

    print()


if __name__ == "__main__":
    main()
