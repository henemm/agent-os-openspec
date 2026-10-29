"""Ampel-Kalibrierung und keine Freigabe per Auswahldialog (Issue #485) — AC-1 bis AC-4.

Spec: docs/specs/fix-485-ampel-kalibrierung.md
Textvertraege per Dateilesen; AC-3 per Import von workflow.check_briefing_content/parse_ampel.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
PO_BRIEFER = REPO_ROOT / "core" / "agents" / "po-briefer.md"
WRITE_SPEC = REPO_ROOT / "core" / "commands" / "30-write-spec.md"
WRITE_SPEC_SKILL = REPO_ROOT / "skills" / "30-write-spec" / "SKILL.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _ampel_section(text: str) -> str:
    """Text ab dem Ampel-Pflichtabschnitt bis zu den Laengengrenzen."""
    start = text.index("Pflichtabschnitt `## Ampel`")
    end = text.index("**Längengrenzen", start)
    return text[start:end]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def test_po_briefer_red_reasons_closed_list():
    text = _read(PO_BRIEFER)
    sec = _norm(_ampel_section(text))
    assert "abschliessend" in sec or "abschließend" in sec
    assert "abweichung vom ticket" in sec
    assert "po-entscheidung" in sec  # Abweichung nur rot ohne bereits getroffene PO-Entscheidung
    assert "acceptance criterion" in sec and "ohne test" in sec
    assert "vag" in sec
    assert "offene entscheidung" in sec and "nur der po" in sec
    low = _norm(text)
    assert "im zweifel rot" not in low
    assert "sonstigem zweifel" not in low
    assert "sonstiger zweifel" not in low


def test_po_briefer_not_red_list():
    sec = _norm(_ampel_section(_read(PO_BRIEFER)))
    assert "nicht rot" in sec
    assert "known limitations" in sec
    assert "manuelle abnahme" in sec
    assert "bereits getroffene" in sec and "entscheidung" in sec


def test_green_briefing_without_question_passes_gate():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow

    briefing = (
        "# PO-Briefing: demo\n\n"
        "- **Spec:** docs/specs/demo.md\n\n"
        "## Was gebaut wird\n\n"
        "Nutzer koennen kuenftig mit einem Klick etwas ausloesen, das heute fehlt.\n\n"
        "## Definition of Done\n\n"
        "Fertig ist es, wenn der Klick sichtbar etwas ausloest und das automatisch geprueft wird.\n\n"
        "## Wie geprueft wird\n\n"
        "Ein automatischer Test klickt stellvertretend und prueft das sichtbare Ergebnis.\n\n"
        "## Kritische Anmerkungen\n\n"
        "- Keine offene Entscheidung fuer den PO.\n\n"
        "## Freigabe-Frage\n\n"
        "Keine – Ampel gruen.\n\n"
        "## Ampel\n\n"
        "Ampel: gruen\n"
    )
    assert workflow.check_briefing_content(briefing) is None
    assert workflow.parse_ampel(briefing) == "green"


def test_write_spec_forbids_dialog_approval():
    for path in (WRITE_SPEC, WRITE_SPEC_SKILL):
        text = _read(path)
        assert "AskUserQuestion" in text, path
        low = _norm(text)
        assert "nie per auswahldialog" in low or "nicht per auswahldialog" in low, path
