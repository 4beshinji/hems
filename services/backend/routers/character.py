"""Character identity endpoint — exposes basic character info to the frontend."""

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/character", tags=["character"])

# Minimal YAML loading — reimplements the resolution order from brain's character_loader
# without importing the brain package.
try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


def _find_config_dir() -> Path:
    env_dir = os.environ.get("CONFIG_DIR")
    if env_dir:
        return Path(env_dir)
    if Path("/config/characters").is_dir():
        return Path("/config")
    this_dir = Path(__file__).resolve().parent
    for parent in this_dir.parents:
        candidate = parent / "config" / "characters"
        if candidate.is_dir():
            return parent / "config"
    return this_dir / "config"


def _load_character_identity() -> dict[str, Any]:
    """Load just the identity section from the active character config."""
    defaults = {
        "name": "HEMS",
        "archetype": "friendly-assistant",
        "first_person": "私",
        "second_person": "あなた",
    }

    if yaml is None:
        return defaults

    config_dir = _find_config_dir()
    characters_dir = config_dir / "characters"

    try:
        data = _resolve_character_source(config_dir, characters_dir)
        # Resolve single-level extends
        extends = data.get("extends")
        if extends:
            tmpl_path = characters_dir / f"{extends}.yaml"
            if tmpl_path.is_file():
                with open(tmpl_path, "r", encoding="utf-8") as f:
                    base = yaml.safe_load(f) or {}
                # Merge: data overrides base
                for key in ("identity", "personality"):
                    if key in data:
                        base_section = base.get(key, {})
                        base_section.update(data[key])
                        base[key] = base_section
                data = base

        identity = data.get("identity", {})
        personality = data.get("personality", {})
        return {
            "name": identity.get("name", defaults["name"]),
            "archetype": personality.get("archetype", defaults["archetype"]),
            "first_person": identity.get("first_person", defaults["first_person"]),
            "second_person": identity.get("second_person", defaults["second_person"]),
        }
    except Exception as e:
        logger.warning("Failed to load character identity: %s", e)
        return defaults


def _resolve_character_source(
    config_dir: Path, characters_dir: Path
) -> dict[str, Any]:
    char_file = os.environ.get("CHARACTER_FILE")
    if char_file:
        path = Path(char_file)
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}

    char_name = os.environ.get("CHARACTER")
    if char_name:
        for name in [char_name, char_name.replace("_", "-")]:
            tmpl_path = characters_dir / f"{name}.yaml"
            if tmpl_path.is_file():
                with open(tmpl_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}

    custom_path = config_dir / "character.yaml"
    if custom_path.is_file():
        with open(custom_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    default_path = characters_dir / "default.yaml"
    if default_path.is_file():
        with open(default_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    return {}


@router.get("/")
async def get_character():
    """Return the active character's identity information."""
    return _load_character_identity()
