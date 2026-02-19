#!/usr/bin/env python3
"""
HEMS Character YAML Validator

CLI tool to validate a character YAML file against the HEMS character schema.

Usage:
    python validate_character.py <path-to-character.yaml>
    python validate_character.py config/characters/tsundere.yaml
    python validate_character.py --all          # validate all built-in templates
    python validate_character.py --list         # list available templates

Exit codes:
    0 = valid
    1 = validation errors found
    2 = file not found or YAML parse error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _characters_dir() -> Path:
    return _project_root() / "config" / "characters"


# ---------------------------------------------------------------------------
# Import the validation function from character_loader
# ---------------------------------------------------------------------------
# We add the brain src directory to the path so we can import directly.
_brain_src = _project_root() / "services" / "brain" / "src"
sys.path.insert(0, str(_brain_src))

from character_loader import (  # noqa: E402
    CharacterConfig,
    _deep_merge,
    _dict_to_config,
    _load_yaml_file,
    _resolve_inheritance,
    validate_character_data,
)


def _print_header(text: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def _print_field(label: str, value: object, indent: int = 2) -> None:
    prefix = " " * indent
    print(f"{prefix}{label}: {value}")


def validate_file(filepath: Path, verbose: bool = False) -> list[str]:
    """
    Validate a single character YAML file.

    Returns a list of error strings (empty if valid).
    """
    errors: list[str] = []

    # --- Check file exists ---
    if not filepath.is_file():
        return [f"File not found: {filepath}"]

    # --- Parse YAML ---
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]

    if not isinstance(data, dict):
        return [f"Expected a YAML mapping at root, got {type(data).__name__}"]

    # --- Schema validation ---
    schema_errors = validate_character_data(data)
    errors.extend(schema_errors)

    # --- Inheritance resolution ---
    try:
        resolved = _resolve_inheritance(data)
    except ValueError as e:
        errors.append(f"Inheritance error: {e}")
        resolved = data

    # --- Try building the dataclass ---
    try:
        config = _dict_to_config(resolved)
    except Exception as e:
        errors.append(f"Config construction error: {e}")
        config = None

    # --- Print summary if verbose ---
    if verbose and config is not None:
        _print_header(f"Character: {filepath.name}")
        _print_field("Name", config.identity.name)
        _print_field("Name Reading", config.identity.name_reading)
        _print_field("First Person", config.identity.first_person)
        _print_field("Second Person", config.identity.second_person)
        _print_field("Honorific", config.identity.honorific_suffix)
        print()
        _print_field("Archetype", config.personality.archetype)
        _print_field("Traits", ", ".join(config.personality.traits))
        _print_field("Formality", f"{config.personality.formality}/4")
        _print_field("Expressiveness", f"{config.personality.expressiveness}/4")
        print()
        _print_field("Voice Backend", config.voice.backend)
        _print_field("Default Speaker", config.voice.voicevox.speakers.get("default"))
        _print_field("Speed", config.voice.voicevox.speed_scale)
        _print_field("Pitch", config.voice.voicevox.pitch_scale)
        _print_field("Intonation", config.voice.voicevox.intonation_scale)

        if config.speaking_style.vocabulary.catchphrase:
            print()
            _print_field("Catchphrase", config.speaking_style.vocabulary.catchphrase)

        if config.extends:
            print()
            _print_field("Extends", config.extends)

    return errors


def list_templates() -> None:
    """List all available built-in character templates."""
    chars_dir = _characters_dir()
    if not chars_dir.is_dir():
        print(f"Characters directory not found: {chars_dir}")
        sys.exit(2)

    templates = sorted(chars_dir.glob("*.yaml"))
    if not templates:
        print("No character templates found.")
        return

    print(f"\nAvailable character templates ({chars_dir}):\n")
    for t in templates:
        try:
            data = _load_yaml_file(t)
            archetype = data.get("personality", {}).get("archetype", "?")
            first_person = data.get("identity", {}).get("first_person", "?")
            formality = data.get("personality", {}).get("formality", "?")
            extends = data.get("extends") or "-"
            print(
                f"  {t.stem:<20s}  "
                f"archetype={archetype:<20s}  "
                f"一人称={first_person}  "
                f"formality={formality}  "
                f"extends={extends}"
            )
        except Exception as e:
            print(f"  {t.stem:<20s}  (error: {e})")


def validate_all(verbose: bool = False) -> int:
    """Validate all built-in templates. Returns exit code."""
    chars_dir = _characters_dir()
    if not chars_dir.is_dir():
        print(f"Characters directory not found: {chars_dir}")
        return 2

    templates = sorted(chars_dir.glob("*.yaml"))
    if not templates:
        print("No character templates found.")
        return 0

    total_errors = 0
    for t in templates:
        errors = validate_file(t, verbose=verbose)
        status = "PASS" if not errors else "FAIL"
        print(f"  [{status}] {t.name}")
        for err in errors:
            print(f"         - {err}")
        total_errors += len(errors)

    print()
    if total_errors == 0:
        print(f"All {len(templates)} templates passed validation.")
        return 0
    else:
        print(f"{total_errors} error(s) found across {len(templates)} templates.")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate HEMS character YAML files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Path to a character YAML file to validate.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="validate_all",
        help="Validate all built-in character templates.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available character templates.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed character summary after validation.",
    )

    args = parser.parse_args()

    if args.list:
        list_templates()
        sys.exit(0)

    if args.validate_all:
        _print_header("Validating all built-in templates")
        exit_code = validate_all(verbose=args.verbose)
        sys.exit(exit_code)

    if not args.file:
        parser.print_help()
        sys.exit(2)

    filepath = Path(args.file).resolve()
    _print_header(f"Validating: {filepath.name}")

    errors = validate_file(filepath, verbose=args.verbose)

    if errors:
        print(f"\n  FAIL - {len(errors)} error(s):\n")
        for err in errors:
            print(f"    - {err}")
        print()
        sys.exit(1)
    else:
        print("\n  PASS - Character file is valid.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
