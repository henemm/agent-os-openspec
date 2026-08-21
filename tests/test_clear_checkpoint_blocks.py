"""Tests für die /clear-Checkpoint-Blöcke in core/commands (Issue #107).

Die fünf Phasen-Commands müssen statt der pauschalen Behauptung
"der Workflow-State liegt sicher auf der Platte" einen Checkpoint mit
Sicherungsliste und zwei Verdikt-Varianten (✅ / ⚠️) enthalten.
`60-validate.md` bekommt bewusst keinen Checkpoint (Commit folgt in
derselben Sitzung).
"""

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS_DIR = REPO_ROOT / "core" / "commands"

CHECKPOINT_FILES = [
    "10-context.md",
    "20-analyse.md",
    "30-write-spec.md",
    "40-tdd-red.md",
    "50-implement.md",
]

NO_CHECKPOINT_FILE = "60-validate.md"

SAVED_MARKER = "**Gesichert auf der Platte:**"
POSITIVE_MARKER = "✅ **`/clear` ist jetzt gefahrlos**"
NEGATIVE_MARKER = "⚠️ **`/clear` jetzt NICHT**"
LEGACY_MARKERS = [
    "liegt sicher auf der Platte",
    "Bei kleinem Kontext optional",
]


def _read(name: str) -> str:
    path = COMMANDS_DIR / name
    assert path.exists(), f"Command-Datei fehlt: {path}"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", CHECKPOINT_FILES)
def test_exactly_one_saved_block(name):
    """AC-1: Jede Zieldatei enthält genau einen 'Gesichert auf der Platte'-Block."""
    content = _read(name)
    assert content.count(SAVED_MARKER) == 1, (
        f"{name}: erwartet genau 1x '{SAVED_MARKER}', "
        f"gefunden {content.count(SAVED_MARKER)}x"
    )


@pytest.mark.parametrize("name", CHECKPOINT_FILES)
def test_both_verdict_variants_present(name):
    """AC-1/AC-2: Positiv- und Negativ-Verdikt stehen in jeder Zieldatei."""
    content = _read(name)
    assert POSITIVE_MARKER in content, f"{name}: Positiv-Verdikt fehlt"
    assert NEGATIVE_MARKER in content, f"{name}: Negativ-Verdikt fehlt"


@pytest.mark.parametrize("name", CHECKPOINT_FILES)
def test_no_legacy_formulations(name):
    """AC-3: Die Alt-Formulierungen sind restlos entfernt."""
    content = _read(name)
    for marker in LEGACY_MARKERS:
        assert marker not in content, f"{name}: Alt-Formulierung '{marker}' noch vorhanden"


def test_validate_command_has_no_checkpoint():
    """60-validate.md bekommt keinen Checkpoint — Commit folgt in derselben Sitzung."""
    content = _read(NO_CHECKPOINT_FILE)
    for marker in (SAVED_MARKER, POSITIVE_MARKER, NEGATIVE_MARKER):
        assert marker not in content, (
            f"{NO_CHECKPOINT_FILE}: Checkpoint-Marker '{marker}' darf hier nicht stehen"
        )
