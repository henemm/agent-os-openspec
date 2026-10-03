"""/00-intake wird der einzige Eingang, auch fuer Bugs (#250, Teil A, Stufe A1).

Reiner Anweisungstext: die Tests pruefen String-Praesenz in den Befehls- und Skill-Dateien.
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INTAKE = (REPO / "core" / "commands" / "00-intake.md").read_text(encoding="utf-8")
BUG = (REPO / "core" / "commands" / "00-bug.md").read_text(encoding="utf-8")


def _bug_section(text: str) -> str:
    m = re.search(r"^#{2,3} .*Bugs?\b.*$", text, re.M)
    assert m, "Abschnitt 'Bugs' fehlt in 00-intake.md"
    return text[m.start():]


def test_intake_has_bug_section_before_scoring():  # AC-1
    section = _bug_section(INTAKE)
    for needle in ("gh issue list", "nachstellen", "file:line", "STOP", "Step 2b"):
        assert needle in section, needle
    assert INTAKE.index("Bugs") < INTAKE.index("### 2. Score präsentieren")
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


def test_00_bug_is_only_a_pointer():  # AC-4
    assert "/00-intake" in BUG
    assert len(BUG.strip().splitlines()) <= 15
    for forbidden in ("--type bug", "workflow.py", "Manuell testen"):
        assert forbidden not in BUG, forbidden


def test_no_bug_fast_track_left_in_commands_or_skills():  # AC-5
    files = list((REPO / "core" / "commands").glob("*.md")) + list((REPO / "skills").glob("*/SKILL.md"))
    assert files
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert "Manuell testen" not in text, f
        assert "--type bug" not in text, f


def test_generated_skills_are_in_sync():  # AC-6
    res = subprocess.run([sys.executable, str(REPO / "scripts" / "sync_skills.py"), "--check"],
                         capture_output=True, text=True, cwd=str(REPO))
    assert res.returncode == 0, res.stdout + res.stderr


def test_docs_describe_00_bug_as_pointer():  # AC-8
    for rel in ("README.md", "CLAUDE.md", "setup.py", "docs/WORKFLOW_GUIDE.md"):
        lines = [l for l in (REPO / rel).read_text(encoding="utf-8").splitlines()
                 if "/00-bug" in l and ("Analysis-First" in l or "analyze the root cause" in l
                                         or "Analyse a bug" in l or "Bug analysieren" in l)]
        assert not lines, f"{rel}: {lines}"
    for rel in ("README.md", "CLAUDE.md", "docs/WORKFLOW_GUIDE.md"):
        rows = [l for l in (REPO / rel).read_text(encoding="utf-8").splitlines()
                if l.startswith("| `/00-bug`")]
        assert rows and all("/00-intake" in r for r in rows), rel
