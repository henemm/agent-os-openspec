"""Issue #677: Befehlstexte verschlanken, Teil 2 — 00-intake, 30-write-spec, 80-workflow.

Die drei Befehlstexte werden bei jedem Aufruf vollstaendig geladen.
Begruendungen und Nachschlagewissen wandern nach docs/befehle/; die
Budgets sinken, zusammen um mindestens 40 % gegenueber 38 043 Bytes.
Ankerueberschriften, auf die andere Stellen verweisen, bleiben erhalten.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS = REPO_ROOT / "core" / "commands"

BUDGETS = {
    "00-intake.md": 8192,
    "30-write-spec.md": 8704,
    "80-workflow.md": 5632,
}
TOTAL_BUDGET = 22825  # -40 % gegenueber 38 043 Bytes


def _size(name: str) -> int:
    return (COMMANDS / name).stat().st_size


def _text(name: str) -> str:
    return (COMMANDS / name).read_text(encoding="utf-8")


def test_write_spec_within_budget():
    size = _size("30-write-spec.md")
    assert size <= 8704, f"30-write-spec.md hat {size} Bytes, Budget 8704"


def test_intake_within_budget():
    size = _size("00-intake.md")
    assert size <= 8192, f"00-intake.md hat {size} Bytes, Budget 8192"


def test_workflow_within_budget():
    size = _size("80-workflow.md")
    assert size <= 5632, f"80-workflow.md hat {size} Bytes, Budget 5632"


def test_total_within_budget():
    total = sum(_size(n) for n in BUDGETS)
    assert total <= TOTAL_BUDGET, (
        f"Summe 00/30/80 = {total} Bytes, Budget {TOTAL_BUDGET}"
    )


def test_anchor_headings_kept():
    spec = _text("30-write-spec.md")
    assert any(
        line.startswith("### Step 3b") for line in spec.splitlines()
    ), "30-write-spec.md: Ueberschrift '### Step 3b' fehlt"

    intake = _text("00-intake.md")
    assert "### 1a." in intake, "00-intake.md: '### 1a.' fehlt"
    score = "### 2. Score präsentieren"
    assert score in intake, f"00-intake.md: '{score}' fehlt"
    bug = re.search(r"^#{2,3} .*Bugs?\b.*$", intake, re.M)
    assert bug, "00-intake.md: Bug-Abschnitt fehlt"
    assert bug.start() < intake.index(score), (
        f"00-intake.md: Bug-Abschnitt '{bug.group(0)}' steht nicht vor '{score}'"
    )
