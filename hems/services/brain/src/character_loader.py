"""
HEMS AI Character Loading System

Loads and resolves character configurations from YAML files with
template inheritance support.

Resolution order (first match wins):
  1. CHARACTER_FILE env var  -> path to a specific YAML file
  2. CHARACTER env var       -> template name (e.g. "tsundere")
  3. config/character.yaml   -> project-level override
  4. Built-in default        -> config/characters/default.yaml
"""

from __future__ import annotations

import copy
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# The config root is resolved relative to the project root.
# In Docker, this is typically /app/config or bind-mounted.
# Locally, we walk up from this file to find the project root.
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parents[3]  # services/brain/src -> project root
_CONFIG_DIR = _PROJECT_ROOT / "config"
_CHARACTERS_DIR = _CONFIG_DIR / "characters"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class IdentityConfig:
    name: str = "HEMS"
    name_reading: str = "ヘムス"
    first_person: str = "私"
    second_person: str = "あなた"
    honorific_suffix: Optional[str] = "さん"


@dataclass
class PersonalityConfig:
    archetype: str = "friendly-assistant"
    traits: list[str] = field(default_factory=lambda: ["思いやりがある", "効率的"])
    behavioral_notes: str = ""
    formality: int = 2  # 0-4
    expressiveness: int = 2  # 0-4


@dataclass
class EndingsConfig:
    neutral: list[str] = field(default_factory=lambda: ["です", "ですね"])
    caring: list[str] = field(default_factory=lambda: ["ね", "てくださいね"])
    humorous: list[str] = field(default_factory=lambda: ["かも？", "なんちゃって"])
    alert: list[str] = field(default_factory=lambda: ["！", "ください！"])


@dataclass
class VocabularyConfig:
    prefer: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    catchphrase: Optional[str] = None


@dataclass
class RejectionConfig:
    directions: list[str] = field(default_factory=lambda: ["嘆き系", "皮肉系"])
    persona_description: str = "丁寧だが少し残念そうに断るアシスタント"


@dataclass
class SpeakingStyleConfig:
    endings: EndingsConfig = field(default_factory=EndingsConfig)
    vocabulary: VocabularyConfig = field(default_factory=VocabularyConfig)
    rejection: RejectionConfig = field(default_factory=RejectionConfig)


@dataclass
class VoicevoxConfig:
    speakers: dict[str, int] = field(
        default_factory=lambda: {
            "default": 47,
            "caring": 47,
            "humorous": 48,
            "alert": 46,
        }
    )
    speed_scale: float = 1.0
    pitch_scale: float = 0.0
    intonation_scale: float = 1.0


@dataclass
class VoiceConfig:
    backend: str = "voicevox"
    voicevox: VoicevoxConfig = field(default_factory=VoicevoxConfig)


@dataclass
class PromptTemplatesConfig:
    system_prompt_override: Optional[str] = None


@dataclass
class CharacterConfig:
    """Top-level character configuration."""

    extends: Optional[str] = None
    identity: IdentityConfig = field(default_factory=IdentityConfig)
    personality: PersonalityConfig = field(default_factory=PersonalityConfig)
    speaking_style: SpeakingStyleConfig = field(default_factory=SpeakingStyleConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    prompt_templates: PromptTemplatesConfig = field(
        default_factory=PromptTemplatesConfig
    )

    @property
    def name(self) -> str:
        return self.identity.name

    @property
    def first_person(self) -> str:
        return self.identity.first_person

    @property
    def formality(self) -> int:
        return self.personality.formality

    @property
    def archetype(self) -> str:
        return self.personality.archetype


# ---------------------------------------------------------------------------
# Deep merge utility
# ---------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merge `override` into `base`, returning a new dict.

    - dict values are recursively merged.
    - list values in override fully replace the base list.
    - scalar values in override replace base values.
    - Keys present only in base are preserved.
    - Keys present only in override are added.
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


# ---------------------------------------------------------------------------
# YAML loading helpers
# ---------------------------------------------------------------------------


def _find_template_path(template_name: str) -> Optional[Path]:
    """Resolve a template name to a YAML file path."""
    path = _CHARACTERS_DIR / f"{template_name}.yaml"
    if path.is_file():
        return path
    # Try without hyphens (e.g. "gentle_senpai" -> "gentle-senpai.yaml")
    alt = _CHARACTERS_DIR / f"{template_name.replace('_', '-')}.yaml"
    if alt.is_file():
        return alt
    return None


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}, got {type(data).__name__}")
    return data


def _resolve_inheritance(data: dict[str, Any], seen: set[str] | None = None) -> dict[str, Any]:
    """
    Resolve the `extends` chain, returning a fully merged dict.

    Detects circular inheritance and raises ValueError.
    """
    if seen is None:
        seen = set()

    extends = data.get("extends")
    if not extends:
        return data

    if extends in seen:
        raise ValueError(f"Circular character inheritance detected: {extends}")
    seen.add(extends)

    base_path = _find_template_path(extends)
    if base_path is None:
        logger.warning(
            "Character template '%s' not found, ignoring extends directive", extends
        )
        return data

    base_data = _load_yaml_file(base_path)
    base_data = _resolve_inheritance(base_data, seen)

    # Merge: override's explicit fields win over base
    merged = _deep_merge(base_data, data)
    # Clear extends since inheritance is now resolved
    merged["extends"] = None
    return merged


# ---------------------------------------------------------------------------
# Dict -> Dataclass conversion
# ---------------------------------------------------------------------------


def _dict_to_config(data: dict[str, Any]) -> CharacterConfig:
    """Convert a raw dict to a CharacterConfig dataclass tree."""
    identity_data = data.get("identity", {})
    personality_data = data.get("personality", {})
    speaking_data = data.get("speaking_style", {})
    voice_data = data.get("voice", {})
    prompt_data = data.get("prompt_templates", {})

    identity = IdentityConfig(
        name=identity_data.get("name", "HEMS"),
        name_reading=identity_data.get("name_reading", "ヘムス"),
        first_person=identity_data.get("first_person", "私"),
        second_person=identity_data.get("second_person", "あなた"),
        honorific_suffix=identity_data.get("honorific_suffix", "さん"),
    )

    personality = PersonalityConfig(
        archetype=personality_data.get("archetype", "friendly-assistant"),
        traits=personality_data.get("traits", ["思いやりがある", "効率的"]),
        behavioral_notes=personality_data.get("behavioral_notes", ""),
        formality=personality_data.get("formality", 2),
        expressiveness=personality_data.get("expressiveness", 2),
    )

    endings_data = speaking_data.get("endings", {})
    endings = EndingsConfig(
        neutral=endings_data.get("neutral", ["です", "ですね"]),
        caring=endings_data.get("caring", ["ね", "てくださいね"]),
        humorous=endings_data.get("humorous", ["かも？", "なんちゃって"]),
        alert=endings_data.get("alert", ["！", "ください！"]),
    )

    vocab_data = speaking_data.get("vocabulary", {})
    vocabulary = VocabularyConfig(
        prefer=vocab_data.get("prefer", []),
        avoid=vocab_data.get("avoid", []),
        catchphrase=vocab_data.get("catchphrase"),
    )

    rejection_data = speaking_data.get("rejection", {})
    rejection = RejectionConfig(
        directions=rejection_data.get("directions", ["嘆き系", "皮肉系"]),
        persona_description=rejection_data.get(
            "persona_description", "丁寧だが少し残念そうに断るアシスタント"
        ),
    )

    speaking_style = SpeakingStyleConfig(
        endings=endings,
        vocabulary=vocabulary,
        rejection=rejection,
    )

    voicevox_data = voice_data.get("voicevox", {})
    voicevox = VoicevoxConfig(
        speakers=voicevox_data.get(
            "speakers", {"default": 47, "caring": 47, "humorous": 48, "alert": 46}
        ),
        speed_scale=voicevox_data.get("speed_scale", 1.0),
        pitch_scale=voicevox_data.get("pitch_scale", 0.0),
        intonation_scale=voicevox_data.get("intonation_scale", 1.0),
    )

    voice = VoiceConfig(
        backend=voice_data.get("backend", "voicevox"),
        voicevox=voicevox,
    )

    prompt_templates = PromptTemplatesConfig(
        system_prompt_override=prompt_data.get("system_prompt_override"),
    )

    return CharacterConfig(
        extends=data.get("extends"),
        identity=identity,
        personality=personality,
        speaking_style=speaking_style,
        voice=voice,
        prompt_templates=prompt_templates,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Module-level cache for the loaded character
_current_character: Optional[CharacterConfig] = None


def load_character(
    config_dir: Path | str | None = None,
) -> CharacterConfig:
    """
    Load the active character configuration.

    Resolution order:
      1. CHARACTER_FILE env var  -> absolute path to a YAML file
      2. CHARACTER env var       -> template name (looked up in characters/)
      3. config/character.yaml   -> project-level custom character
      4. Built-in default        -> config/characters/default.yaml

    On any error (missing file, invalid YAML, schema issues), falls back
    to the built-in default character with a warning log.

    Args:
        config_dir: Override the config directory (for testing).

    Returns:
        A fully resolved CharacterConfig instance.
    """
    global _current_character

    characters_dir = _CHARACTERS_DIR
    cfg_dir = _CONFIG_DIR
    if config_dir is not None:
        cfg_dir = Path(config_dir)
        characters_dir = cfg_dir / "characters"

    try:
        data = _resolve_character_source(cfg_dir, characters_dir)
        data = _resolve_inheritance(data)
        config = _dict_to_config(data)
        _current_character = config
        logger.info(
            "Character loaded: %s (archetype=%s, formality=%d)",
            config.identity.name,
            config.personality.archetype,
            config.personality.formality,
        )
        return config

    except Exception as e:
        logger.warning("Failed to load character config: %s. Falling back to default.", e)
        return _load_default_fallback(characters_dir)


def _resolve_character_source(
    cfg_dir: Path, characters_dir: Path
) -> dict[str, Any]:
    """Determine which YAML file to load based on env vars and file presence."""

    # 1. CHARACTER_FILE env var -> explicit path
    char_file = os.environ.get("CHARACTER_FILE")
    if char_file:
        path = Path(char_file)
        if path.is_file():
            logger.info("Loading character from CHARACTER_FILE: %s", path)
            return _load_yaml_file(path)
        else:
            raise FileNotFoundError(f"CHARACTER_FILE not found: {char_file}")

    # 2. CHARACTER env var -> template name
    char_name = os.environ.get("CHARACTER")
    if char_name:
        tmpl_path = characters_dir / f"{char_name}.yaml"
        if not tmpl_path.is_file():
            # Try hyphenated variant
            tmpl_path = characters_dir / f"{char_name.replace('_', '-')}.yaml"
        if tmpl_path.is_file():
            logger.info("Loading character template: %s", char_name)
            return _load_yaml_file(tmpl_path)
        else:
            raise FileNotFoundError(f"Character template not found: {char_name}")

    # 3. config/character.yaml
    custom_path = cfg_dir / "character.yaml"
    if custom_path.is_file():
        logger.info("Loading custom character from %s", custom_path)
        return _load_yaml_file(custom_path)

    # 4. Default
    default_path = characters_dir / "default.yaml"
    if default_path.is_file():
        logger.info("Loading default character")
        return _load_yaml_file(default_path)

    # Nothing found — return empty dict (will use dataclass defaults)
    logger.info("No character config found, using built-in defaults")
    return {}


def _load_default_fallback(characters_dir: Path) -> CharacterConfig:
    """Load the default character, or return bare dataclass defaults."""
    try:
        default_path = characters_dir / "default.yaml"
        if default_path.is_file():
            data = _load_yaml_file(default_path)
            return _dict_to_config(data)
    except Exception as e:
        logger.error("Failed to load even the default character: %s", e)
    return CharacterConfig()


def reload_character(
    config_dir: Path | str | None = None,
) -> CharacterConfig:
    """
    Force-reload the character configuration.

    Useful for hot-reloading after editing the YAML file without restarting
    the service.

    Returns:
        The newly loaded CharacterConfig.
    """
    global _current_character
    _current_character = None
    logger.info("Reloading character configuration...")
    return load_character(config_dir=config_dir)


def get_current_character() -> CharacterConfig:
    """
    Get the currently loaded character, loading it if necessary.

    This is the main entry point for other modules that need the character.

    Returns:
        The active CharacterConfig instance.
    """
    global _current_character
    if _current_character is None:
        return load_character()
    return _current_character


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

# Expected top-level keys and their types for validation
_SCHEMA: dict[str, dict[str, Any]] = {
    "extends": {"type": (str, type(None)), "required": False},
    "identity": {
        "type": dict,
        "required": False,
        "fields": {
            "name": {"type": str},
            "name_reading": {"type": str},
            "first_person": {"type": str},
            "second_person": {"type": str},
            "honorific_suffix": {"type": (str, type(None))},
        },
    },
    "personality": {
        "type": dict,
        "required": False,
        "fields": {
            "archetype": {"type": str},
            "traits": {"type": list},
            "behavioral_notes": {"type": str},
            "formality": {"type": int, "min": 0, "max": 4},
            "expressiveness": {"type": int, "min": 0, "max": 4},
        },
    },
    "speaking_style": {
        "type": dict,
        "required": False,
        "fields": {
            "endings": {"type": dict},
            "vocabulary": {"type": dict},
            "rejection": {"type": dict},
        },
    },
    "voice": {
        "type": dict,
        "required": False,
        "fields": {
            "backend": {"type": str},
            "voicevox": {"type": dict},
        },
    },
    "prompt_templates": {
        "type": dict,
        "required": False,
        "fields": {
            "system_prompt_override": {"type": (str, type(None))},
        },
    },
}


def validate_character_data(data: dict[str, Any]) -> list[str]:
    """
    Validate a character data dict against the schema.

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"Root must be a mapping, got {type(data).__name__}"]

    # Check for unknown top-level keys
    known_keys = set(_SCHEMA.keys())
    for key in data:
        if key not in known_keys:
            errors.append(f"Unknown top-level key: '{key}'")

    for key, spec in _SCHEMA.items():
        if key not in data:
            continue

        value = data[key]

        # Type check
        expected_type = spec["type"]
        if value is not None and not isinstance(value, expected_type):
            errors.append(
                f"'{key}' should be {expected_type}, got {type(value).__name__}"
            )
            continue

        # Nested field validation
        if isinstance(value, dict) and "fields" in spec:
            for field_name, field_spec in spec["fields"].items():
                if field_name not in value:
                    continue
                field_val = value[field_name]
                field_type = field_spec["type"]

                if field_val is not None and not isinstance(field_val, field_type):
                    errors.append(
                        f"'{key}.{field_name}' should be {field_type}, "
                        f"got {type(field_val).__name__}"
                    )
                    continue

                # Range checks for int fields
                if isinstance(field_val, int):
                    if "min" in field_spec and field_val < field_spec["min"]:
                        errors.append(
                            f"'{key}.{field_name}' must be >= {field_spec['min']}, "
                            f"got {field_val}"
                        )
                    if "max" in field_spec and field_val > field_spec["max"]:
                        errors.append(
                            f"'{key}.{field_name}' must be <= {field_spec['max']}, "
                            f"got {field_val}"
                        )

    # Validate speaking_style.endings has the required tones
    endings = data.get("speaking_style", {}).get("endings", {})
    if isinstance(endings, dict):
        required_tones = {"neutral", "caring", "humorous", "alert"}
        for tone in required_tones:
            if tone in endings and not isinstance(endings[tone], list):
                errors.append(
                    f"'speaking_style.endings.{tone}' must be a list"
                )

    # Validate voice.voicevox.speakers
    speakers = data.get("voice", {}).get("voicevox", {}).get("speakers", {})
    if isinstance(speakers, dict):
        for tone_key, speaker_id in speakers.items():
            if not isinstance(speaker_id, int):
                errors.append(
                    f"'voice.voicevox.speakers.{tone_key}' must be an int, "
                    f"got {type(speaker_id).__name__}"
                )

    # Validate voice.voicevox float ranges
    voicevox = data.get("voice", {}).get("voicevox", {})
    if isinstance(voicevox, dict):
        float_fields = {
            "speed_scale": (0.5, 2.0),
            "pitch_scale": (-0.15, 0.15),
            "intonation_scale": (0.0, 2.0),
        }
        for fname, (lo, hi) in float_fields.items():
            if fname in voicevox:
                val = voicevox[fname]
                if isinstance(val, (int, float)):
                    if val < lo or val > hi:
                        errors.append(
                            f"'voice.voicevox.{fname}' must be between "
                            f"{lo} and {hi}, got {val}"
                        )
                else:
                    errors.append(
                        f"'voice.voicevox.{fname}' must be a number, "
                        f"got {type(val).__name__}"
                    )

    return errors
