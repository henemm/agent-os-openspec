"""Regressionstest fuer Issue #349.

`tdd_enforcement._TAP_SUMMARY_RE` entfernte die Summary-Zeilen von `node --test`
nur in der TAP-Form (`# todo 0`). Der spec-Reporter schreibt dieselben Zeilen als
`ℹ todo 0` — die Platzhaltersuche traf `todo` und blockte ein echtes RED-Artefakt.

Spec: docs/specs/fix-352-349-gates.md (AC-5 bis AC-7).

Die Fixtures entstehen zur Laufzeit aus einem echten `node --test`-Lauf mit einem
gruenen und einem roten Test. Fehlt `node`, wird mit Begruendung uebersprungen.

Stilvorlage: tests/test_tdd_enforcement_embedded_content_262.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import tdd_enforcement  # noqa: E402

TEST_JS = (
    "const test = require('node:test');\n"
    "const assert = require('node:assert');\n"
    "test('gruen', () => { assert.strictEqual(1, 1); });\n"
    "test('rot', () => { assert.strictEqual(1, 2); });\n"
)


def _node_lauf(tmp_path: Path, reporter: str) -> str:
    """Echter `node --test`-Lauf mit einem roten Test; liefert stdout+stderr."""
    if shutil.which("node") is None:
        pytest.skip("node nicht installiert — echte Reporter-Ausgabe nicht erzeugbar")
    (tmp_path / "beispiel.test.js").write_text(TEST_JS)
    proc = subprocess.run(
        ["node", "--test", f"--test-reporter={reporter}", "beispiel.test.js"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode != 0, f"Vorbedingung: der rote Test muss scheitern: {proc.stdout!r}"
    return proc.stdout + proc.stderr


def test_spec_reporter_summary_ist_kein_platzhalter(tmp_path):
    """AC-5: echte spec-Reporter-Ausgabe loest keinen Platzhalter-Block aus."""
    ausgabe = _node_lauf(tmp_path, "spec")
    assert "ℹ todo 0" in ausgabe.splitlines(), (
        f"Vorbedingung: keine echte spec-Form (Zeile `ℹ todo 0` fehlt): {ausgabe!r}"
    )
    treffer = tdd_enforcement._find_placeholder(ausgabe)
    assert treffer is None, (
        f"AC-5 #349: spec-Reporter-Summary wird als Platzhalter gewertet: {treffer!r}"
    )


def test_echter_platzhalter_blockt_weiterhin(tmp_path):
    """AC-6: ein echter Platzhalter im Runner-Rahmen wird weiterhin gefunden."""
    ausgabe = _node_lauf(tmp_path, "spec")
    assert "ℹ todo 0" in ausgabe.splitlines()
    gefaelscht = "TODO: fill in\n" + ausgabe
    treffer = tdd_enforcement._find_placeholder(gefaelscht)
    assert treffer is not None, "AC-6: echter Platzhalter neben spec-Summary wird nicht gefunden"
    assert "TODO: fill in" in treffer[1], f"AC-6: falsche Fundstelle: {treffer!r}"


def test_tap_summary_bleibt_unbeanstandet(tmp_path):
    """AC-7: TAP-Form (`# todo 0`) bleibt wie seit #73 unbeanstandet."""
    ausgabe = _node_lauf(tmp_path, "tap")
    assert "# todo 0" in ausgabe.splitlines(), (
        f"Vorbedingung: keine echte TAP-Form (Zeile `# todo 0` fehlt): {ausgabe!r}"
    )
    treffer = tdd_enforcement._find_placeholder(ausgabe)
    assert treffer is None, f"AC-7: TAP-Summary wird als Platzhalter gewertet: {treffer!r}"
