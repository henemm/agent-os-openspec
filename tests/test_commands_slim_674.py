"""Issue #674: Befehlstexte verschlanken — Groessenwaechter fuer core/commands.

50-implement.md und 60-validate.md werden bei jedem Aufruf vollstaendig
geladen. Begruendungen und Nachschlagewissen wandern nach docs/befehle/;
jeder Befehlstext bekommt ein Byte-Budget, damit er nicht wieder waechst.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS = REPO_ROOT / "core" / "commands"
SKILLS = REPO_ROOT / "skills"
BEFEHLE = REPO_ROOT / "docs" / "befehle"

BUDGETS = {
    "00-intake.md": 8192,
    "01-feature.md": 2560,
    "10-context.md": 7680,
    "20-analyse.md": 9728,
    "30-write-spec.md": 8704,
    "40-tdd-red.md": 8192,
    "50-implement.md": 15360,
    "60-validate.md": 20480,
    "70-deploy.md": 8704,
    "80-workflow.md": 5632,
    "81-add-artifact.md": 3584,
    "82-test.md": 3072,
    "83-user-story.md": 5120,
    "90-retro.md": 3072,
    "99-reset.md": 3072,
}

LINKED = ["50-implement", "60-validate", "00-intake", "30-write-spec", "80-workflow"]


def _size(name: str) -> int:
    return (COMMANDS / name).stat().st_size


def test_implement_within_budget():
    size = _size("50-implement.md")
    assert size <= 15360, f"50-implement.md hat {size} Bytes, Budget 15360"


def test_validate_within_budget():
    size = _size("60-validate.md")
    assert size <= 20480, f"60-validate.md hat {size} Bytes, Budget 20480"


def test_every_command_has_budget():
    existing = sorted(p.name for p in COMMANDS.glob("*.md"))
    missing = [n for n in existing if n not in BUDGETS]
    assert not missing, f"Befehle ohne Budget: {missing}"
    stale = [n for n in BUDGETS if n not in existing]
    assert not stale, f"Budget fuer nicht existierende Befehle: {stale}"
    over = {
        n: (_size(n), BUDGETS[n]) for n in existing if _size(n) > BUDGETS[n]
    }
    assert not over, f"Ueber Budget (Bytes, Budget): {over}"


def test_commands_link_background_docs():
    for cmd in LINKED:
        link = f"docs/befehle/{cmd}.md"
        text = (COMMANDS / f"{cmd}.md").read_text(encoding="utf-8")
        assert link in text, f"{cmd}.md verweist nicht auf {link}"
        doc = BEFEHLE / f"{cmd}.md"
        assert doc.is_file(), f"{link} fehlt"
        sections = [
            line
            for line in doc.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ")
        ]
        assert len(sections) >= 3, (
            f"{link} hat nur {len(sections)} '## '-Abschnitte, erwartet >= 3"
        )


def test_skills_carry_link():
    result = subprocess.run(
        [sys.executable, "scripts/sync_skills.py", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"sync_skills.py --check meldet Drift:\n{result.stdout}\n{result.stderr}"
    )
    for cmd in LINKED:
        link = f"docs/befehle/{cmd}.md"
        text = (SKILLS / cmd / "SKILL.md").read_text(encoding="utf-8")
        assert link in text, f"skills/{cmd}/SKILL.md verweist nicht auf {link}"
