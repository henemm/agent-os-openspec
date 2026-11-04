"""Regressionstest fuer Issue #508.

`node --test` (TAP 13) zitiert den Inhalt einer fehlgeschlagenen Assertion in
einem YAML-Diagnoseblock (`---` ... `...`) unter der `not ok`-Zeile. Enthielt
der geprueft Inhalt `placeholder:text-muted-foreground` (Tailwind) oder `TODO`,
hielt `tdd_enforcement._find_placeholder` den Block fuer Runner-Rahmen und
lehnte das echte RED-Artefakt ab; in Phase 6 war jeder Edit gesperrt.
Loesung: ein formgerechter TAP-YAML-Block gilt als Zitat (wie die pytest-Zitate
aus #262). Unvollstaendige / falsch platzierte Bloecke bleiben Rahmen.

Stilvorlage: tests/test_tdd_enforcement_embedded_content_262.py
(direkter Aufruf von tdd_enforcement, echte Dateien in tmp_path, kein Mock).
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
sys.path.insert(0, str(HOOKS_DIR))

import tdd_enforcement  # noqa: E402


def _artifact(tmp_path, content: str, name: str = "red-output.log") -> dict:
    p = tmp_path / name
    p.write_text(content)
    return {
        "type": "test_output",
        "path": str(p),
        "description": "3 Tests fehlgeschlagen: AssertionError in login.test.mjs",
    }


# Woertliche Ausgabe von `node --test --test-reporter=tap` (node v22.23.4,
# 2026-11-04) fuer eine Testdatei mit verschachteltem Subtest und zwei
# fehlschlagenden strictEqual-Assertions auf HTML mit Tailwind-Klasse und TODO.
# Einzige Aenderung: absoluter Scratchpad-Pfad durch /work/app ersetzt.
REAL_NODE_TAP_OUTPUT = (
    'TAP version 13\n'
    '# Subtest: outer\n'
    '    # Subtest: inner\n'
    '    not ok 1 - inner\n'
    '      ---\n'
    '      duration_ms: 2.123063\n'
    "      type: 'test'\n"
    "      location: '/work/app/login.test.mjs:4:11'\n"
    "      failureType: 'testCodeFailure'\n"
    '      error: |-\n'
    '        Expected values to be strictly equal:\n'
    '        + actual - expected\n'
    '        \n'
    '        + \'<input class="placeholder:text-muted-foreground border">\\n<p>TODO later</p>\'\n'
    '        - \'<input class="border">\'\n'
    '        \n'
    "      code: 'ERR_ASSERTION'\n"
    "      name: 'AssertionError'\n"
    '      expected: \'<input class="border">\'\n'
    '      actual: |-\n'
    '        <input class="placeholder:text-muted-foreground border">\n'
    '        <p>TODO later</p>\n'
    "      operator: 'strictEqual'\n"
    '      stack: |-\n'
    '        TestContext.<anonymous> (file:///work/app/login.test.mjs:5:12)\n'
    '        Test.runInAsyncScope (node:async_hooks:214:14)\n'
    '        Test.run (node:internal/test_runner/test:1047:25)\n'
    '        Test.start (node:internal/test_runner/test:944:17)\n'
    '        TestContext.test (node:internal/test_runner/test:373:20)\n'
    '        TestContext.<anonymous> (file:///work/app/login.test.mjs:4:11)\n'
    '        Test.runInAsyncScope (node:async_hooks:214:14)\n'
    '        Test.run (node:internal/test_runner/test:1047:25)\n'
    '        Test.start (node:internal/test_runner/test:944:17)\n'
    '        startSubtestAfterBootstrap (node:internal/test_runner/harness:296:17)\n'
    '      ...\n'
    '    1..1\n'
    'not ok 1 - outer\n'
    '  ---\n'
    '  duration_ms: 3.461646\n'
    "  type: 'test'\n"
    "  location: '/work/app/login.test.mjs:3:1'\n"
    "  failureType: 'subtestsFailed'\n"
    "  error: '1 subtest failed'\n"
    "  code: 'ERR_TEST_FAILURE'\n"
    '  ...\n'
    '# Subtest: top\n'
    'not ok 2 - top\n'
    '  ---\n'
    '  duration_ms: 0.454493\n'
    "  type: 'test'\n"
    "  location: '/work/app/login.test.mjs:8:1'\n"
    "  failureType: 'testCodeFailure'\n"
    '  error: |-\n'
    '    Expected values to be strictly equal:\n'
    '    + actual - expected\n'
    '    \n'
    '    + \'<input class="placeholder:text-muted-foreground border">\\n<p>TODO later</p>\'\n'
    '    - \'<input class="border">\'\n'
    '    \n'
    "  code: 'ERR_ASSERTION'\n"
    "  name: 'AssertionError'\n"
    '  expected: \'<input class="border">\'\n'
    '  actual: |-\n'
    '    <input class="placeholder:text-muted-foreground border">\n'
    '    <p>TODO later</p>\n'
    "  operator: 'strictEqual'\n"
    '  stack: |-\n'
    '    TestContext.<anonymous> (file:///work/app/login.test.mjs:9:10)\n'
    '    Test.runInAsyncScope (node:async_hooks:214:14)\n'
    '    Test.run (node:internal/test_runner/test:1047:25)\n'
    '    Test.processPendingSubtests (node:internal/test_runner/test:744:18)\n'
    '    Test.postRun (node:internal/test_runner/test:1173:19)\n'
    '    Test.run (node:internal/test_runner/test:1101:12)\n'
    '    async startSubtestAfterBootstrap (node:internal/test_runner/harness:296:3)\n'
    '  ...\n'
    '1..2\n'
    '# tests 3\n'
    '# suites 0\n'
    '# pass 0\n'
    '# fail 3\n'
    '# cancelled 0\n'
    '# skipped 0\n'
    '# todo 0\n'
    '# duration_ms 77.994089\n'
)


class TestRealNodeTap:
    def test_real_node_tap_output_with_placeholder_in_yaml_is_valid(self, tmp_path):
        """AC-1: der nachgestellte Livefall aus #508 muss durchgehen."""
        assert "# fail 3" in REAL_NODE_TAP_OUTPUT
        assert "placeholder:text-muted-foreground" in REAL_NODE_TAP_OUTPUT
        assert "TODO later" in REAL_NODE_TAP_OUTPUT
        art = _artifact(tmp_path, REAL_NODE_TAP_OUTPUT)
        assert tdd_enforcement._validate_artifact(art, tmp_path) is None

    def test_nested_subtest_yaml_block_is_quote(self):
        """AC-2: Testzeile 4 Leerzeichen, YAML-Block 6 Leerzeichen."""
        content = (
            "TAP version 13\n"
            "# Subtest: outer\n"
            "    # Subtest: inner\n"
            "    not ok 1 - inner\n"
            "      ---\n"
            "      error: |-\n"
            "        + '<input class=\"placeholder:text-muted-foreground\">'\n"
            "      ...\n"
            "    1..1\n"
            "not ok 1 - outer\n"
            "# fail 2\n"
        )
        assert tdd_enforcement._find_placeholder(content) is None


class TestNegativeCasesStayFrame:
    def test_unclosed_yaml_block_stays_frame(self):
        """AC-3: ohne `...` auf gleicher Einrueckung bleibt alles Rahmen."""
        content = (
            "TAP version 13\n"
            "not ok 1 - x\n"
            "  ---\n"
            "  error: |-\n"
            "    <input class=\"placeholder:text-muted-foreground\">\n"
            "  stack: |-\n"
            "    foo (x.mjs:1:1)\n"
            "# fail 1\n"
        )
        hit = tdd_enforcement._find_placeholder(content)
        assert hit is not None
        assert hit[0] == 5
        assert "placeholder:" in hit[1]

    def test_yaml_block_without_preceding_test_line_stays_frame(self):
        """AC-4: `---` am Dateianfang / nach Kommentarzeile / nach Leerzeile."""
        at_start = "  ---\n  TODO: fake\n  ...\nnot ok 1 - x\n"
        after_comment = "# Subtest: x\n  ---\n  TODO: fake\n  ...\n"
        after_blank = "not ok 1 - x\n\n  ---\n  TODO: fake\n  ...\n"
        hit = tdd_enforcement._find_placeholder(at_start)
        assert hit is not None and hit[0] == 2
        hit = tdd_enforcement._find_placeholder(after_comment)
        assert hit is not None and hit[0] == 3
        hit = tdd_enforcement._find_placeholder(after_blank)
        assert hit is not None and hit[0] == 4

    def test_yaml_block_not_indented_deeper_stays_frame(self):
        """AC-5: `---` auf Hoehe der Testzeile ist kein Diagnoseblock."""
        content = (
            "not ok 1 - x\n"
            "---\n"
            "TODO: fake\n"
            "...\n"
        )
        hit = tdd_enforcement._find_placeholder(content)
        assert hit is not None and hit[0] == 3

    def test_frame_after_yaml_block_is_still_checked(self, tmp_path):
        """AC-6: nach dem Block wird der Rahmen weiter geprueft."""
        content = (
            "TAP version 13\n"
            "not ok 1 - x\n"
            "  ---\n"
            "  error: |-\n"
            "    <input class=\"placeholder:text-muted-foreground\">\n"
            "  ...\n"
            "# TODO: echte Ausgabe einfuegen\n"
            "# fail 1\n"
        )
        art = _artifact(tmp_path, content)
        err = tdd_enforcement._validate_artifact(art, tmp_path)
        assert err is not None
        assert "Artefakt enthält Platzhalter-Text" in err
        assert "Zeile 7" in err
        assert "# TODO: echte Ausgabe einfuegen" in err

    def test_deeper_indented_dots_do_not_end_block(self):
        """AC-7: nur `...` auf Marker-Hoehe beendet den Block."""
        content = (
            "TAP version 13\n"
            "not ok 1 - x\n"
            "  ---\n"
            "  error: |-\n"
            "    erste Zeile\n"
            "    ...\n"
            "    <input class=\"placeholder:text-muted-foreground\">\n"
            "  ...\n"
            "# fail 1\n"
        )
        assert tdd_enforcement._find_placeholder(content) is None


class TestUnchangedBehaviour:
    def test_failure_evidence_check_unchanged(self, tmp_path):
        """AC-8: ok-Zeilen mit YAML-Bloecken ohne Fehlerwoerter bleiben kein RED."""
        content = (
            "TAP version 13\n"
            "ok 1 - x\n"
            "  ---\n"
            "  duration_ms: 1.2\n"
            "  type: 'test'\n"
            "  ...\n"
            "1..1\n"
            "# tests 1\n"
            "# pass 1\n"
        )
        art = _artifact(tmp_path, content)
        err = tdd_enforcement._validate_artifact(art, tmp_path)
        assert err is not None and "RED-Artefakt zeigt keine Fehler-Evidenz" in err

    def test_block_message_mentions_tap_yaml(self, tmp_path):
        """AC-9: die Ablehnungsmeldung nennt TAP-YAML unter den Ausnahmen."""
        art = _artifact(
            tmp_path,
            "TODO: hier die echte Ausgabe einfuegen\nAssertionError: dummy\n" * 3,
        )
        err = tdd_enforcement._validate_artifact(art, tmp_path)
        assert err is not None and "Platzhalter" in err
        assert "TAP-YAML" in err


def test_changelog_mentions_508():
    """AC-10 (release-fest): CHANGELOG.md nennt #508 ab der Zeile `## [Unreleased]`,
    also unter [Unreleased] oder in irgendeinem Versionsabschnitt danach."""
    text = CHANGELOG.read_text()
    start = text.index("## [Unreleased]")
    assert "#508" in text[start:], "Kein #508-Eintrag ab [Unreleased] im CHANGELOG"
