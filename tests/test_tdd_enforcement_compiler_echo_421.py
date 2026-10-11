"""Regressionstest für Issue #421.

Der Swift-Compiler zitiert zu jeder Fehlerzeile die betroffene Quellzeile im
Format `NN |     code` (Swift-6-Diagnosestil, auch durch xcbeautify). Steht in
dieser Quellzeile das Wort "placeholder" (z. B. ein Testname), hielt
`tdd_enforcement._find_placeholder` ein echtes RED-Artefakt für gefälscht und
sperrte jede Code-Bearbeitung. #262 nahm nur pytest-Zitate (`E `, `> `,
`Captured ...`) aus; das Compiler-Echo war nie ausgenommen.

Lösung (wie #262): nummerierte Echo-Zeilen gehören nicht zum Runner-Rahmen.
Das Gate wird nicht gelockert — Platzhalter in Rahmenzeilen ohne `NN |`-Form
bleiben Funde.

Stilvorlage: tests/test_tdd_enforcement_embedded_content_262.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import tdd_enforcement  # noqa: E402

ESC = "\x1b"


def _artifact(tmp_path, content: str, name: str = "test-red-hinweis.txt") -> dict:
    p = tmp_path / name
    p.write_text(content)
    return {
        "type": "test_output",
        "path": str(p),
        "description": "Swift-Testlauf: Kompilierfehler, Tests nicht ausfuehrbar",
    }


ECHO_PLAIN = '79 |     @Test("Not listening with an empty field shows the usual placeholder")'
ECHO_ANSI = (
    f'{ESC}[36m79 |     @Test("Not listening with an empty field shows the usual placeholder"){ESC}[0m'
)

# Nachbau des Originalartefakts aus loose-ends (279-pegel-mikrofon): Compiler-
# Fehlerzeile, Quellzeilen-Echo mit dem Wort, Gutter-Zeile, echte Fehler-Evidenz.
REAL_SWIFT_COMPILER_RED = (
    "Compiling LooseEndsTests\n"
    "❌ /Users/x/LooseEndsTests/ListeningTests.swift:79:6: error: cannot find 'MicLevel' in scope\n"
    "\n"
    "70 |     func startListening() {\n"
    f"{ESC}[36m71 |         let level = MicLevel.current{ESC}[0m\n"
    + ECHO_PLAIN + "\n"
    "   |      `- error: cannot find 'MicLevel' in scope\n"
    "80 |     func check() {}\n"
    "\n"
    "** TEST FAILED **\n"
    "error: Testing failed\n"
)


class TestCompilerEchoNotTreatedAsPlaceholder:
    def test_plain_echo_line_is_ignored(self):
        assert tdd_enforcement._find_placeholder(ECHO_PLAIN + "\n") is None

    def test_ansi_colored_echo_line_is_ignored(self):
        assert tdd_enforcement._find_placeholder(ECHO_ANSI + "\n") is None


class TestForgeryStillBlocked:
    def test_todo_in_unnumbered_frame_line_is_found(self):
        content = "error: build failed\nTODO: hier kommt die Testausgabe\n"
        found = tdd_enforcement._find_placeholder(content)
        assert found is not None and found[0] == 2

    def test_markdown_table_row_with_todo_is_found(self):
        content = "error: build failed\n| TODO | Spalte |\n"
        found = tdd_enforcement._find_placeholder(content)
        assert found is not None and found[0] == 2


class TestMessageNamesOriginalLine:
    def test_later_real_hit_reports_original_line_number(self, tmp_path):
        content = (
            "❌ Foo.swift:1:1: error: boom\n"
            + ECHO_PLAIN + "\n"
            "[test output here]\n"
            "error: Testing failed\n"
        )
        msg = tdd_enforcement._validate_artifact(_artifact(tmp_path, content), tmp_path)
        assert msg is not None
        assert "Zeile 3" in msg or ":3" in msg or "3:" in msg


class TestRealArtifactAccepted:
    def test_rebuilt_original_artifact_is_valid(self, tmp_path):
        art = _artifact(tmp_path, REAL_SWIFT_COMPILER_RED)
        assert tdd_enforcement._validate_artifact(art, tmp_path) is None
