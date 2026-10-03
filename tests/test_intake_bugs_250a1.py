"""/00-intake wird der einzige Eingang, auch fuer Bugs (#250, Teil A, Stufe A1).

Reiner Anweisungstext: die Tests pruefen String-Praesenz in den Befehls- und Skill-Dateien.
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INTAKE = (REPO / "core" / "commands" / "00-intake.md").read_text(encoding="utf-8")


def _bug_section(text: str) -> str:
    m = re.search(r"^#{2,3} .*Bugs?\b.*$", text, re.M)
    assert m, "Abschnitt 'Bugs' fehlt in 00-intake.md"
    return text[m.start():]


def test_intake_has_bug_section_before_scoring():  # AC-1
    section = _bug_section(INTAKE)
    for needle in ("gh issue list", "nachstellen", "file:line", "STOP", "Step 2b"):
        assert needle in section, needle
    assert re.search(r"^#{2,3} .*Bugs?\b.*$", INTAKE, re.M).start() < INTAKE.index("### 2. Score präsentieren")


def test_known_cause_means_low_uncertainty():  # AC-2
    section = _bug_section(INTAKE)
    assert re.search(r"Ursache bekannt.*≤\s?3 Dateien.*Low", section, re.S)
    # Gegenfall (Anmerkung des Briefings): unklare Ursache hebt die Unsicherheit an.
    assert re.search(r"Ursache unklar.*mindestens Medium", section, re.S)


def test_no_bug_type_and_two_start_blocks():  # AC-3
    assert "--type bug" not in INTAKE
    types = re.findall(r"workflow\.py start \[name\] --type (\S+)", INTAKE)
    assert sorted(types) == ["feature", "feature-fast"]


def test_no_bug_fast_track_left_in_commands_or_skills():  # AC-5
    files = list((REPO / "core" / "commands").glob("*.md")) + list((REPO / "skills").glob("*/SKILL.md"))
    assert files
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"Manuell testen", text, re.I), f
        assert "--type bug" not in text, f


def test_generated_skills_are_in_sync():  # AC-6
    res = subprocess.run([sys.executable, str(REPO / "scripts" / "sync_skills.py"), "--check"],
                         capture_output=True, text=True, cwd=str(REPO))
    assert res.returncode == 0, res.stdout + res.stderr


def test_00_bug_is_removed():  # #333: /00-bug existiert nicht mehr
    for rel in ("core/commands/00-bug.md", "skills/00-bug", ".claude/commands/00-bug.md"):
        assert not (REPO / rel).exists(), rel
