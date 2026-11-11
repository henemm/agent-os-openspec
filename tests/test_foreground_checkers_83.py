"""Issue #83: kurzlebige Pruef-/Kontextagenten laufen im Vordergrund.

Hintergrund-Starts ohne Worktree-Isolation meldeten sich wiederholt idle ohne
Bericht. Der Orchestrator braucht das Ergebnis ohnehin vor dem naechsten Schritt.
Langlaufende Agenten (developer, implementation-validator) bleiben im Hintergrund.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Werkzeug-Syntax seit #577 (benannte Typen ohne model, anonyme Starts mit model).
FOREGROUND = [
    ("30-write-spec", r'Agent\(subagent_type="spec-validator", description="[^"]*", '
                      r'run_in_background=(\w+), prompt="\s*Validiere die Spec'),
    ("50-implement", r'Agent\(subagent_type="Explore", model="haiku", description="[^"]*", '
                     r'run_in_background=(\w+), prompt="\s*Lies folgende Dateien'),
    ("60-validate", r'Agent\(subagent_type="general-purpose", model="haiku", '
                    r'description="TEST CHECK", run_in_background=(\w+)'),
    ("60-validate", r'Agent\(subagent_type="general-purpose", model="haiku", '
                    r'description="SPEC COMPLIANCE", run_in_background=(\w+)'),
    ("60-validate", r'Agent\(subagent_type="general-purpose", model="haiku", '
                    r'description="REGRESSION CHECK", run_in_background=(\w+)'),
    ("60-validate", r'Agent\(subagent_type="general-purpose", model="haiku", '
                    r'description="SCOPE CHECK", run_in_background=(\w+)'),
]

BACKGROUND = [
    ("50-implement", r'Agent\(subagent_type="developer-agent", description="[^"]*", '
                     r'run_in_background=(\w+)'),
    ("50-implement", r'Agent\(subagent_type="implementation-validator", description="[^"]*", '
                     r'run_in_background=(\w+)'),
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
