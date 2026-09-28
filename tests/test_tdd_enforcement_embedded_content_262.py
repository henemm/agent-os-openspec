"""Regressionstest für Issue #262 (Epic #199).

`tdd_enforcement._PLACEHOLDER_RE` lief über den KOMPLETTEN Artefakt-Inhalt. Prüft
ein RED-Test den Inhalt eines Framework-Dokuments (`skills/*/SKILL.md`,
`core/commands/*.md`), schreibt pytest bei fehlgeschlagener Assertion den ganzen
Dateiinhalt in die Ausgabe. `skills/40-tdd-red/SKILL.md` enthält die Zeile
"❌ **Placeholder artifacts** → Hook will block implementation" — das Gate
erklärte damit seine eigene Warnung vor gefälschten Artefakten zum Beweis für
ein gefälschtes Artefakt und blockte jeden Edit in phase6.

Abgrenzung: #89 löste "Wort als Teilstring in einem Bezeichner" per \\b-Grenzen.
Hier steht das Wort als eigenes Wort in ZITIERTEM Fremdinhalt — Wortgrenzen
helfen nicht. Die Lösung folgt dem Vorbild von #73 (`_TAP_SUMMARY_RE`): die von
pytest als Zitat markierten Bereiche werden vor der Platzhalter-Suche entfernt.

Stilvorlage: tests/test_tdd_enforcement_placeholder_wordboundary_89.py
(direkter Aufruf von tdd_enforcement._validate_artifact, echte Dateien in tmp_path).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import tdd_enforcement  # noqa: E402


def _artifact(tmp_path, content: str, name: str = "red-output.log") -> dict:
    p = tmp_path / name
    p.write_text(content)
    return {
        "type": "test_output",
        "path": str(p),
        "description": "1 Test fehlgeschlagen: AssertionError in SKILL.md-Pruefung",
    }


# Wörtlicher Auszug aus dem am 2026-09-28 nachgestellten Lauf: ein RED-Test
# prüft den Inhalt von skills/40-tdd-red/SKILL.md, die Assertion scheitert,
# pytest gibt das Dokument als E-Zeilen aus. Die Treffer des Platzhalter-Musters
# stehen ALLE auf E-Zeilen, also in pytest-eigener Zitat-Markierung.
REAL_PYTEST_RED_WITH_EMBEDDED_SKILL_DOC = (
    "============================= test session starts ==============================\n"
    "platform darwin -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0\n"
    "collected 1 item\n\n"
    "test_skill_content_repro.py F                                            [100%]\n\n"
    "=================================== FAILURES ===================================\n"
    "______________________ test_skill_documents_new_gate_rule ______________________\n\n"
    "    def test_skill_documents_new_gate_rule():\n"
    "        content = SKILL.read_text()\n"
    '>       assert "NOCH-NICHT-IMPLEMENTIERTE-REGEL" in content, content\n'
    "E       AssertionError: ---\n"
    "E         ## Artifact Requirements\n"
    "E         - Be a **real file** (not placeholder)\n"
    "E         \n"
    "E         ## Common Mistakes\n"
    "E         \n"
    "E         ❌ **Tests that pass** → Test is worthless, proves nothing\n"
    "E         ❌ **Placeholder artifacts** → Hook will block implementation\n"
    "E         ❌ **Skip to implement** → TDD enforcement hook will block you\n"
    "E         \n"
    "E       assert 'NOCH-NICHT-IMPLEMENTIERTE-REGEL' in '---\\ndescription: ...'\n\n"
    "test_skill_content_repro.py:12: AssertionError\n"
    "=========================== short test summary info ============================\n"
    "FAILED test_skill_content_repro.py::test_skill_documents_new_gate_rule - Asse...\n"
    "============================== 1 failed in 0.02s ===============================\n"
)


class TestEmbeddedDocumentContentNotTreatedAsPlaceholder:
    def test_real_red_artifact_quoting_skill_doc_is_valid(self, tmp_path):
        """Der nachgestellte Livefall aus #262 muss durchgehen."""
        art = _artifact(tmp_path, REAL_PYTEST_RED_WITH_EMBEDDED_SKILL_DOC)
        assert tdd_enforcement._validate_artifact(art, tmp_path) is None

    def test_placeholder_word_on_assertion_line_is_ignored(self, tmp_path):
        content = (
            "=================================== FAILURES ===================================\n"
            "    def test_doc_mentions_rule():\n"
            ">       assert marker in text, text\n"
            "E       AssertionError: assert 'x' in 'Placeholder artifacts are blocked'\n"
            "FAILED tests/test_doc.py::test_doc_mentions_rule - AssertionError\n"
            "============================== 1 failed in 0.02s ===============================\n"
        )
        art = _artifact(tmp_path, content)
        assert tdd_enforcement._validate_artifact(art, tmp_path) is None

    def test_todo_in_quoted_source_line_is_ignored(self, tmp_path):
        """Die '>'-Zeile ist pytest-zitierter Quellcode, kein Artefakt-Platzhalter."""
        content = (
            "=================================== FAILURES ===================================\n"
            "    def test_scanner_finds_markers():\n"
            '>       assert scan("# TODO: FIXME") == 2\n'
            "E       AssertionError: assert 1 == 2\n"
            "FAILED tests/test_scanner.py::test_scanner_finds_markers - AssertionError\n"
            "============================== 1 failed in 0.03s ===============================\n"
        )
        art = _artifact(tmp_path, content)
        assert tdd_enforcement._validate_artifact(art, tmp_path) is None

    def test_captured_stdout_section_is_ignored(self, tmp_path):
        """Ein Test, der den Dokumentinhalt per print() ausgibt, landet im
        Captured-stdout-Abschnitt — ebenfalls zitierter Fremdinhalt."""
        content = (
            "=================================== FAILURES ===================================\n"
            "    def test_doc_rule():\n"
            ">       assert False\n"
            "E       assert False\n"
            "----------------------------- Captured stdout call -----------------------------\n"
            "## Common Mistakes\n"
            "❌ **Placeholder artifacts** → Hook will block implementation\n"
            "TODO: dieser Satz steht im Dokument, nicht im Artefakt\n"
            "=========================== short test summary info ============================\n"
            "FAILED tests/test_doc.py::test_doc_rule - assert False\n"
            "============================== 1 failed in 0.02s ===============================\n"
        )
        art = _artifact(tmp_path, content)
        assert tdd_enforcement._validate_artifact(art, tmp_path) is None


class TestFabricatedArtifactsStillBlocked:
    """Das Gate darf durch den Fix keine Zähne verlieren: Platzhalter im
    Artefakt-Rahmen (also nicht in pytest-zitiertem Inhalt) blocken weiter."""

    def test_standalone_placeholder_still_blocked(self, tmp_path):
        art = _artifact(
            tmp_path,
            "PLACEHOLDER - replace with actual test output\n"
            "AssertionError: dummy\n" * 5,
        )
        err = tdd_enforcement._validate_artifact(art, tmp_path)
        assert err is not None and "Platzhalter" in err

    def test_todo_line_next_to_real_summary_still_blocked(self, tmp_path):
        """Eine echte Summenzeile macht ein Artefakt nicht automatisch echt."""
        content = (
            "TODO: hier die echte Testausgabe einfügen\n"
            "AssertionError: dummy\n"
            "============================== 1 failed in 0.02s ===============================\n"
        )
        art = _artifact(tmp_path, content)
        err = tdd_enforcement._validate_artifact(art, tmp_path)
        assert err is not None and "Platzhalter" in err

    def test_bracket_pattern_still_blocked(self, tmp_path):
        art = _artifact(tmp_path, "<test_output>\nAssertionError: dummy\n" * 5)
        err = tdd_enforcement._validate_artifact(art, tmp_path)
        assert err is not None and "Platzhalter" in err


class TestBlockMessageNamesOffendingLine:
    """Im Livefall nannte die Meldung nur die Datei. Ohne die auslösende Zeile
    ist ein Fehlalarm nicht in Minuten, sondern in Stunden zu finden."""

    def test_message_quotes_the_matching_line(self, tmp_path):
        art = _artifact(
            tmp_path,
            "Zeile eins ohne Befund\n"
            "TODO: hier die echte Ausgabe einfügen\n"
            "AssertionError: dummy\n" * 3,
        )
        err = tdd_enforcement._validate_artifact(art, tmp_path)
        assert err is not None
        assert "TODO: hier die echte Ausgabe einfügen" in err
        assert "Zeile 2" in err
