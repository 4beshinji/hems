"""
Tests for infra/scripts/init_env.py — .env secret generation helper.
"""

import sys
from pathlib import Path

import pytest

_script = Path(__file__).resolve().parent.parent / "infra" / "scripts"
if str(_script) not in sys.path:
    sys.path.insert(0, str(_script))

import init_env as ie


class TestIsPlaceholder:
    def test_none_is_placeholder(self):
        assert ie._is_placeholder(None) is True

    def test_empty_string_is_placeholder(self):
        assert ie._is_placeholder("") is True

    def test_change_me_before_use_is_placeholder(self):
        assert ie._is_placeholder("CHANGE_ME_BEFORE_USE") is True

    def test_change_me_is_placeholder(self):
        assert ie._is_placeholder("CHANGE_ME") is True

    def test_whitespace_only_is_placeholder(self):
        assert ie._is_placeholder("   ") is True

    def test_real_value_is_not_placeholder(self):
        assert ie._is_placeholder("secret123") is False


class TestGetCurrentValue:
    def test_extracts_value(self):
        content = "POSTGRES_PASSWORD=secret\nMQTT_PASS=CHANGE_ME\n"
        assert ie._get_current_value(content, "POSTGRES_PASSWORD") == "secret"
        assert ie._get_current_value(content, "MQTT_PASS") == "CHANGE_ME"

    def test_missing_key_returns_none(self):
        assert ie._get_current_value("A=1\n", "B") is None


class TestSetValue:
    def test_replaces_existing_key(self):
        content = "POSTGRES_PASSWORD=old\n"
        assert ie._set_value(content, "POSTGRES_PASSWORD", "new") == "POSTGRES_PASSWORD=new\n"

    def test_appends_missing_key(self):
        content = "A=1\n"
        result = ie._set_value(content, "B", "2")
        assert result.startswith("A=1\n\n# Added by init_env.py on")
        assert result.endswith("B=2\n")


class TestInitEnv:
    @pytest.fixture
    def env_files(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_example = tmp_path / "env.example"
        monkeypatch.setattr(ie, "ENV_FILE", env_file)
        monkeypatch.setattr(ie, "ENV_EXAMPLE", env_example)
        return env_file, env_example

    def _base_env(self, overrides: dict | None = None) -> str:
        values = {
            "POSTGRES_PASSWORD": "secret",
            "MQTT_PASS": "secret",
            "BACKEND_API_KEY": "secret",
            "HEMS_INTERNAL_TOKEN": "secret",
        }
        if overrides:
            values.update(overrides)
        return "".join(f"{k}={v}\n" for k, v in values.items())

    def test_creates_env_from_example_when_missing(self, env_files):
        env_file, env_example = env_files
        env_example.write_text("POSTGRES_PASSWORD=CHANGE_ME\nMQTT_PASS=CHANGE_ME\n")
        changes = ie.init_env()
        assert env_file.exists()
        assert "POSTGRES_PASSWORD=" in env_file.read_text()
        assert len(changes) == len(ie.SECRETS)

    def test_only_missing_replaces_placeholders(self, env_files):
        env_file, _env_example = env_files
        env_file.write_text(self._base_env({"MQTT_PASS": "CHANGE_ME"}))
        changes = ie.init_env()
        assert len(changes) == 1
        assert changes[0][0] == "MQTT_PASS"
        assert env_file.read_text().startswith("POSTGRES_PASSWORD=secret\n")

    def test_only_missing_keeps_existing_values(self, env_files):
        env_file, _env_example = env_files
        env_file.write_text(self._base_env())
        changes = ie.init_env()
        assert len(changes) == 0
        content = env_file.read_text()
        assert "POSTGRES_PASSWORD=secret" in content
        assert "MQTT_PASS=secret" in content

    def test_force_overwrites_existing_values(self, env_files):
        env_file, _env_example = env_files
        env_file.write_text(self._base_env())
        changes = ie.init_env(only_missing=False)
        assert len(changes) == len(ie.SECRETS)
        assert any(c[0] == "POSTGRES_PASSWORD" and c[1] != "secret" for c in changes)

    def test_dry_run_does_not_modify_file(self, env_files):
        env_file, _env_example = env_files
        env_file.write_text(self._base_env({"POSTGRES_PASSWORD": "CHANGE_ME"}))
        original = env_file.read_text()
        changes = ie.init_env(dry_run=True)
        assert len(changes) == 1
        assert env_file.read_text() == original

    def test_appends_missing_key(self, env_files):
        env_file, _env_example = env_files
        env_file.write_text("MQTT_PASS=secret\n")
        changes = ie.init_env()
        assert any(c[0] == "POSTGRES_PASSWORD" for c in changes)
        content = env_file.read_text()
        assert "POSTGRES_PASSWORD=" in content
