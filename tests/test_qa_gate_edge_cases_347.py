"""Issue #347: Randfaelle der unittest/node-Erkennung im qa_gate.

Fixtures unter tests/fixtures/qa_gate_347/ stammen aus echten Laeufen (node 22,
Python 3.11); die zwei node-Randfaelle sind daraus abgeleitet (zwei echte
TAP-Summaries ohne Trennzeile; ein echter gruener Lauf mit verfaelschter
tests-Zahl), weil echtes node sie selbst nicht erzeugt.
"""

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))

from qa_gate import validate_test_output  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "qa_gate_347"


def _validate(tmp_path, name):
    target = tmp_path / name
    shutil.copy(FIXTURES / name, target)
    return validate_test_output(str(target))


def test_f101_node_green_with_test_failed_in_name(tmp_path):
    valid, msg = _validate(tmp_path, "node_spec_green_name_mentions_test_failed.txt")
    assert valid, msg


def test_f101_unittest_green_with_test_failed_in_docstring(tmp_path):
    valid, msg = _validate(tmp_path, "unittest_green_docstring_mentions_test_failed.txt")
    assert valid, msg


def test_f101_real_marker_still_red(tmp_path):
    src = (FIXTURES / "unittest_green_docstring_mentions_test_failed.txt").read_text()
    (tmp_path / "x.txt").write_text(src + "\n** TEST FAILED **\n")
    valid, msg = validate_test_output(str(tmp_path / "x.txt"))
    assert not valid, msg


def test_f102_two_blocks_without_separator_red_wins(tmp_path):
    valid, msg = _validate(tmp_path, "node_tap_two_blocks_no_separator.txt")
    assert not valid and "1 failed" in msg, msg


def test_f104_inconsistent_counts_are_not_green(tmp_path):
    valid, msg = _validate(tmp_path, "node_tap_green_inconsistent_counts.txt")
    assert not valid and "tests != " in msg, msg


def test_f104_fractional_counter_is_not_green(tmp_path):
    src = (FIXTURES / "node_tap_two_blocks_no_separator.txt").read_text().splitlines()[8:]
    text = "\n".join(src).replace("# pass 2", "# pass 2.5") + "\n"
    (tmp_path / "f.txt").write_text(text)
    valid, msg = validate_test_output(str(tmp_path / "f.txt"))
    assert not valid and "ganzzahlig" in msg, msg
