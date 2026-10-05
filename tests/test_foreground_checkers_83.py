"""Issue #83: kurzlebige Pruef-/Kontextagenten laufen im Vordergrund.

Hintergrund-Starts ohne Worktree-Isolation meldeten sich wiederholt idle ohne
Bericht. Der Orchestrator braucht das Ergebnis ohnehin vor dem naechsten Schritt.
Langlaufende Agenten (developer, implementation-validator) bleiben im Hintergrund.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

FOREGROUND = [
    ("30-write-spec", r"Task \(general-purpose/haiku, run_in_background: (\w+)\): \"Du bist der spec-validator"),
    ("50-implement", r"Task \(Explore/haiku, run_in_background: (\w+)\): \"Lies folgende Dateien"),
    ("60-validate", r"Task 1 \(general-purpose/haiku, run_in_background: (\w+)\) - TEST CHECK"),
    ("60-validate", r"Task 2 \(general-purpose/haiku, run_in_background: (\w+)\) - SPEC COMPLIANCE"),
    ("60-validate", r"Task 3 \(general-purpose/haiku, run_in_background: (\w+)\) - REGRESSION CHECK"),
    ("60-validate", r"Task 4 \(general-purpose/haiku, run_in_background: (\w+)\) - SCOPE CHECK"),
]

BACKGROUND = [
    ("50-implement", r"Task \(developer-agent/opus, run_in_background: (\w+)\)"),
    ("50-implement", r"Task \(implementation-validator, run_in_background: (\w+)\)"),
]


def _sources(cmd):
    return [REPO_ROOT / "core" / "commands" / f"{cmd}.md",
            REPO_ROOT / "skills" / cmd / "SKILL.md"]


@pytest.mark.parametrize("cmd,pattern", FOREGROUND)
def test_short_lived_checkers_run_in_foreground(cmd, pattern):
    for path in _sources(cmd):
        m = re.search(pattern, path.read_text())
        assert m, f"{path}: Task-Zeile nicht gefunden"
        assert m.group(1) == "false", f"{path}: {m.group(0)}"


@pytest.mark.parametrize("cmd,pattern", BACKGROUND)
def test_long_running_agents_stay_in_background(cmd, pattern):
    for path in _sources(cmd):
        m = re.search(pattern, path.read_text())
        assert m and m.group(1) == "true", f"{path}"
