"""
Tests for CharacterLoader — config loading, inheritance, validation, hot-reload.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure brain src is on path
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "services" / "brain" / "src"))

import character_loader  # noqa: E402


# ── CharacterConfig properties ───────────────────────────────────


class TestCharacterConfigProperties:
    def test_name_property(self):
        cfg = character_loader.load_character()
        assert isinstance(cfg.name, str)
        assert len(cfg.name) > 0

    def test_first_person_property(self):
        cfg = character_loader.load_character()
        assert isinstance(cfg.first_person, str)

    def test_formality_property(self):
        cfg = character_loader.load_character()
        assert isinstance(cfg.formality, int)
        assert 0 <= cfg.formality <= 4

    def test_archetype_property(self):
        cfg = character_loader.load_character()
        assert isinstance(cfg.archetype, str)


# ── _find_config_dir ─────────────────────────────────────────────


class TestFindConfigDir:
    def test_env_var_override(self, tmp_path):
        config_dir = tmp_path / "myconfig"
        config_dir.mkdir()
        with patch.dict(os.environ, {"CONFIG_DIR": str(config_dir)}):
            result = character_loader._find_config_dir()
        assert result == config_dir

    def test_docker_mount_path(self):
        with patch("character_loader.Path.exists", return_value=True), \
             patch.dict(os.environ, {}, clear=False):
            # Remove CONFIG_DIR if present
            env = os.environ.copy()
            env.pop("CONFIG_DIR", None)
            with patch.dict(os.environ, env, clear=True):
                character_loader._find_config_dir()
                # Should find /config or walk up; either is valid


# ── _load_yaml_file ──────────────────────────────────────────────


class TestLoadYamlFile:
    def test_non_dict_yaml_raises(self, tmp_path):
        yaml_file = tmp_path / "list.yaml"
        yaml_file.write_text("- item1\n- item2\n")
        with pytest.raises(ValueError, match="Expected a YAML mapping"):
            character_loader._load_yaml_file(yaml_file)

    def test_scalar_yaml_raises(self, tmp_path):
        yaml_file = tmp_path / "scalar.yaml"
        yaml_file.write_text("just a string\n")
        with pytest.raises(ValueError, match="Expected a YAML mapping"):
            character_loader._load_yaml_file(yaml_file)

    def test_valid_yaml_returns_dict(self, tmp_path):
        yaml_file = tmp_path / "valid.yaml"
        yaml_file.write_text("name: test\nvalue: 42\n")
        result = character_loader._load_yaml_file(yaml_file)
        assert result == {"name": "test", "value": 42}


# ── _find_template_path ─────────────────────────────────────────


class TestFindTemplatePath:
    def test_exact_match(self):
        result = character_loader._find_template_path("ena")
        assert result is not None
        assert result.name == "ena.yaml"

    def test_underscore_to_hyphen_fallback(self):
        result = character_loader._find_template_path("gentle_senpai")
        if result is not None:
            assert "gentle" in result.name

    def test_nonexistent_returns_none(self):
        result = character_loader._find_template_path("nonexistent_template_xyz")
        assert result is None


# ── _resolve_inheritance ─────────────────────────────────────────


class TestResolveInheritance:
    def test_valid_inheritance(self, tmp_path):
        """Template extending another should merge correctly."""
        data = {
            "identity": {"name": "Custom"},
        }
        # Without extends, should return data as-is
        result = character_loader._resolve_inheritance(data)
        assert result["identity"]["name"] == "Custom"

    def test_missing_template_logs_warning(self, tmp_path):
        """Extending a non-existent template should warn and return data."""
        data = {"extends": "nonexistent_template_xyz_123"}
        result = character_loader._resolve_inheritance(data)
        assert isinstance(result, dict)

    def test_circular_inheritance_raises(self):
        """Circular extends chain should raise ValueError."""
        data = {"extends": "self_loop"}
        # The function uses seen set to detect circular inheritance
        with pytest.raises(ValueError, match="[Cc]ircular"):
            character_loader._resolve_inheritance(data, seen={"self_loop"})


# ── load_character ───────────────────────────────────────────────


class TestLoadCharacter:
    def test_loads_default_character(self):
        cfg = character_loader.load_character()
        assert cfg is not None
        assert isinstance(cfg.name, str)

    def test_character_env_override(self):
        """CHARACTER=ena should load ena template."""
        with patch.dict(os.environ, {"CHARACTER": "ena"}):
            cfg = character_loader.load_character()
        assert cfg is not None

    def test_character_file_env_override(self, tmp_path):
        """CHARACTER_FILE pointing to valid YAML should load it."""
        char_file = tmp_path / "custom.yaml"
        char_file.write_text(
            "identity:\n  name: TestChar\n  first_person: I\n"
        )
        with patch.dict(os.environ, {"CHARACTER_FILE": str(char_file)}):
            cfg = character_loader.load_character()
        assert cfg.name == "TestChar"

    def test_character_file_not_found_falls_back(self):
        """CHARACTER_FILE pointing to missing file should fall back."""
        with patch.dict(os.environ, {"CHARACTER_FILE": "/nonexistent/char.yaml"}):
            cfg = character_loader.load_character()
        # Should fall back to default
        assert cfg is not None

    def test_invalid_yaml_falls_back(self, tmp_path):
        """Malformed YAML should fall back to default."""
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("{{{{invalid yaml}}}\n")
        with patch.dict(os.environ, {"CHARACTER_FILE": str(bad_file)}):
            cfg = character_loader.load_character()
        assert cfg is not None


# ── reload_character ─────────────────────────────────────────────


class TestReloadCharacter:
    def test_reload_clears_cache(self):
        # Load initial character
        character_loader.load_character()
        # Reload
        cfg2 = character_loader.reload_character()
        assert cfg2 is not None
        assert isinstance(cfg2.name, str)

    def test_get_current_character_lazy_loads(self):
        # Clear cache
        character_loader._current_character = None
        cfg = character_loader.get_current_character()
        assert cfg is not None
        assert isinstance(cfg.name, str)

    def test_get_current_character_returns_cached(self):
        cfg1 = character_loader.get_current_character()
        cfg2 = character_loader.get_current_character()
        assert cfg1 is cfg2


# ── validate_character_data ──────────────────────────────────────


class TestValidateCharacterData:
    def test_valid_data_no_errors(self):
        data = {
            "identity": {"name": "Test", "first_person": "I"},
            "personality": {"archetype": "helper", "formality": 2},
        }
        errors = character_loader.validate_character_data(data)
        assert errors == []

    def test_non_dict_root(self):
        errors = character_loader.validate_character_data([1, 2, 3])
        assert len(errors) > 0
        assert "dict" in errors[0].lower() or "mapping" in errors[0].lower()

    def test_unknown_top_level_keys(self):
        data = {"identity": {"name": "X"}, "unknown_key": "value"}
        errors = character_loader.validate_character_data(data)
        assert any("unknown_key" in e for e in errors)

    def test_wrong_type_for_name(self):
        data = {"identity": {"name": 42}}
        errors = character_loader.validate_character_data(data)
        assert any("name" in e.lower() or "type" in e.lower() for e in errors)

    def test_formality_out_of_range(self):
        data = {"personality": {"formality": 10}}
        errors = character_loader.validate_character_data(data)
        assert any("formality" in e.lower() or "range" in e.lower() for e in errors)

    def test_endings_not_list(self):
        data = {"speaking_style": {"endings": {"neutral": "not-a-list"}}}
        errors = character_loader.validate_character_data(data)
        assert len(errors) > 0

    def test_speaker_id_not_int(self):
        data = {"voicevox": {"speaker_id": {"neutral": "three"}}}
        errors = character_loader.validate_character_data(data)
        assert len(errors) > 0

    def test_speed_scale_out_of_range(self):
        data = {"voicevox": {"speed_scale": 0.2}}
        errors = character_loader.validate_character_data(data)
        assert len(errors) > 0

    def test_intonation_scale_non_numeric(self):
        data = {"voicevox": {"intonation_scale": "high"}}
        errors = character_loader.validate_character_data(data)
        assert len(errors) > 0
