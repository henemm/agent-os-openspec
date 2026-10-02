"""Zwei Stufen statt drei: Stufen-Tabelle in /00-intake auf den Code zurueckgeschnitten (#254).

Der Workflow-State kennt nur `feature-fast` und `feature`; adversary_dialog.MIN_ROUNDS = 2 ist ein
harter Boden. Die Texte duerfen weder drei Stufen noch eine einzelne Adversary-Runde zusagen.
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INTAKE = (REPO / "core" / "commands" / "00-intake.md").read_text(encoding="utf-8")


def test_no_single_adversary_round_promise():  # AC-1
    assert "1 Runde" not in INTAKE


def test_intake_names_the_real_minimum_rounds():  # AC-2
    code = (REPO / "core" / "hooks" / "adversary_dialog.py").read_text(encoding="utf-8")
    n = int(re.search(r"^MIN_ROUNDS\s*=\s*(\d+)", code, re.M).group(1))
    assert f"mindestens {n}" in INTAKE


def test_exactly_two_start_blocks_with_distinct_types():  # AC-3
    types = re.findall(r"workflow\.py start \[name\] --type (\S+)", INTAKE)
    assert sorted(types) == ["feature", "feature-fast"]


def test_full_process_is_no_longer_a_stage_name():  # AC-4
    for rel in ("core/commands/00-intake.md", "core/commands/30-write-spec.md", "README.md", "CLAUDE.md"):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "Full Process" not in text and "Full-Process" not in text, rel


def test_generated_skills_are_in_sync():  # AC-5
    res = subprocess.run([sys.executable, str(REPO / "scripts" / "sync_skills.py"), "--check"],
                         capture_output=True, text=True, cwd=str(REPO))
    assert res.returncode == 0, res.stdout + res.stderr
