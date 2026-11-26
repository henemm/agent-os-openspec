"""Issue #678: Befehlstexte verschlanken, Teil 3 — die uebrigen Befehle.

10-context, 20-analyse, 40-tdd-red und 70-deploy werden bei jedem Aufruf
vollstaendig geladen; die sechs kleinen Befehle ebenso. Begruendungen und
Nachschlagewissen wandern nach docs/befehle/; die Budgets sinken, die
Summe aller Befehlstexte bleibt unter 83 000 Bytes, und 60-validate wird
ein zweites Mal geschnitten. Ankerueberschriften, auf die andere Stellen
verweisen, bleiben erhalten.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS = REPO_ROOT / "core" / "commands"

MAIN_BUDGETS = {
    "10-context.md": 5120,
    "20-analyse.md": 6656,
    "40-tdd-red.md": 5632,
    "70-deploy.md": 6144,
}
SMALL = [
    "01-feature.md",
    "81-add-artifact.md",
    "82-test.md",
    "83-user-story.md",
    "90-retro.md",
    "99-reset.md",
]
SMALL_BUDGET = 2048
VALIDATE_BUDGET = 16384
TOTAL_BUDGET = 83600  # #696: +600 fuer die CONTEXT_HANDOFF-Absaetze (Rest nach Kuerzung)


def _size(name: str) -> int:
    return (COMMANDS / name).stat().st_size


def _text(name: str) -> str:
    return (COMMANDS / name).read_text(encoding="utf-8")


def test_main_commands_within_budget():
    over = {
        n: (_size(n), b) for n, b in MAIN_BUDGETS.items() if _size(n) > b
    }
    assert not over, f"Ueber Budget (Ist, Budget): {over}"


def test_small_commands_within_budget():
    over = {n: (_size(n), SMALL_BUDGET) for n in SMALL if _size(n) > SMALL_BUDGET}
    assert not over, f"Ueber Budget (Ist, Budget): {over}"


def test_validate_second_cut():
    size = _size("60-validate.md")
    assert size <= VALIDATE_BUDGET, (
        f"60-validate.md hat {size} Bytes, Budget {VALIDATE_BUDGET}"
    )


def test_total_within_83kb():
    total = sum(p.stat().st_size for p in COMMANDS.glob("*.md"))
    assert total <= TOTAL_BUDGET, (
        f"Summe core/commands/*.md = {total} Bytes, Budget {TOTAL_BUDGET}"
    )


def test_anchor_headings_kept():
    analyse = _text("20-analyse.md").splitlines()
    assert any(l.startswith("### Step 2b") for l in analyse), (
        "20-analyse.md: Ueberschrift '### Step 2b' fehlt"
    )

    tdd = _text("40-tdd-red.md").splitlines()
    assert any(l.startswith("## Common Mistakes") for l in tdd), (
        "40-tdd-red.md: Ueberschrift '## Common Mistakes' fehlt"
    )

    deploy = _text("70-deploy.md")
    assert any(l.startswith("## Step 4") for l in deploy.splitlines()), (
        "70-deploy.md: Ueberschrift '## Step 4' fehlt"
    )
    assert "b) Fachlicher Befund" in deploy, (
        "70-deploy.md: 'b) Fachlicher Befund' fehlt"
    )
