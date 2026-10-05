"""Anleitungen duerfen keine Schreibziele unter /tmp vorgeben.

secret_egress_guard blockt Schreibziele ausserhalb des Projekts (Ausnahme: das
eigene Sitzungs-Scratchpad). Eine Anleitung, die `/tmp/...` vorschreibt, erzeugt
deshalb bei jedem Durchlauf eine Blockade und eine Extra-Runde. Belegt in den
Gate-Logs (gate-audit-data, 2026-09-29..10-02): `/tmp/adversary_test_output.txt`
aus /50-implement Step 8d.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES = sorted(
    list((REPO_ROOT / "core" / "commands").glob("*.md"))
    + list((REPO_ROOT / "core" / "agents").glob("*.md"))
    + list((REPO_ROOT / "templates").glob("*.md"))
    + list((REPO_ROOT / "skills").glob("*/SKILL.md"))
)


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_tmp_write_targets(path):
    hits = [ln for ln in path.read_text().splitlines() if re.search(r"(?<![\w.])/tmp/", ln)]
    assert not hits, f"{path}: /tmp-Pfade in Anleitung: {hits}"


def test_qa_gate_output_lives_in_artifacts():
    text = (REPO_ROOT / "core" / "commands" / "50-implement.md").read_text()
    assert "docs/artifacts/<workflow-name>/adversary-test-output.txt" in text
