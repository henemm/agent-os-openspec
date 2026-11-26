"""Issue #679: Versions-Marker-Block und Hook-Hinweis je Zug verschlanken.

`sync_skills.marker_block` haengt an jeden Befehl den Fusszeilen-Pflichttext;
`workflow.status_note` kommt bei jeder Nutzer-Nachricht mit aktivem Workflow
in den Kontext. Beide werden auf die Regeln gekuerzt, die Begruendungen
stehen in docs/befehle/fusszeile.md. Die Pflicht-Stichworte pruefen die
bestehenden Tests (test_skills_sync, test_endzustand_550, test_status_note_325,
test_spec_ampel_470); hier nur die Groessenwaechter.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))

import sync_skills  # noqa: E402
import workflow  # noqa: E402

MARKER_BUDGET = 1200   # vorher 3 259 Bytes
NOTE_BUDGET = 900      # vorher 1 886 Bytes
FUSSZEILE_DOC = REPO_ROOT / "docs" / "befehle" / "fusszeile.md"

NOTE_DATA = {"name": "fix-1761-statusvermerk", "current_phase": "phase7_validate",
             "issue": 1761}


def _bytes(text: str) -> int:
    return len(text.encode("utf-8"))


def test_marker_block_within_budget():
    block = sync_skills.marker_block("60-validate", "4.26.3")
    assert _bytes(block) <= MARKER_BUDGET, _bytes(block)


def test_marker_block_keeps_version_line_verbatim_at_line_start():
    block = sync_skills.marker_block("60-validate", "4.26.3")
    assert "\n⚙ /60-validate · agent-os-openspec 4.26.3\n" in block


def test_marker_block_points_to_background_doc():
    block = sync_skills.marker_block("60-validate", "4.26.3")
    assert "docs/befehle/fusszeile.md" in block


def test_status_note_within_budget():
    note = workflow._status_note_base(NOTE_DATA)
    assert note, "Vermerk fuer phase7_validate erwartet"
    assert _bytes(note) <= NOTE_BUDGET, _bytes(note)


def test_auto_approval_note_within_budget():
    data = dict(NOTE_DATA, current_phase="phase3_spec")
    orig = workflow.next_step
    workflow.next_step = lambda _d: workflow.AUTO_APPROVAL_STEP
    try:
        note = workflow._status_note_base(data)
    finally:
        workflow.next_step = orig
    assert note and "❗" not in note
    assert _bytes(note) <= NOTE_BUDGET, _bytes(note)


def test_background_doc_holds_the_reasons():
    assert FUSSZEILE_DOC.is_file()
    text = FUSSZEILE_DOC.read_text(encoding="utf-8")
    for anchor in ("Turn-Beginn", "Übergabe-Blöcke", "Platzhalter",
                   "Emoji", "es gibt keine vierte"):
        assert anchor in text, anchor


def test_generated_skills_carry_the_slim_block():
    for name in sync_skills.synced_names():
        if name in sync_skills.MARKER_EXEMPT:
            continue
        text = (REPO_ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        tail = text.split("## Versions-Marker", 1)[1]
        assert _bytes("## Versions-Marker" + tail) <= MARKER_BUDGET + 64, name
