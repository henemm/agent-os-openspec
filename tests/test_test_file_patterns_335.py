"""Issue #335: Testdateien neben dem Code (Go `*_test.go` u. a.) sind kein
Produktivcode — TDD-RED darf sie anlegen.

Go legt Tests per Konvention ins selbe Package wie den Code; `edit_gate` kannte
nur Test-ORDNER und blockte `notified_test.go` in phase5_tdd_red. Die Muster
sind bewusst eng: `test_helpers.go` ohne `_test`-Suffix bleibt Produktivcode.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

from hook_utils import is_gated_code_path, is_colocated_test_file  # noqa: E402
from config_loader import DEFAULT_TEST_PATH_PATTERNS  # noqa: E402

TESTS = ["notified_test.go", "cmd/app/main_test.go",
         "src/app.test.ts", "src/app.spec.tsx", "web/a.test.mjs", "web/b.spec.js"]
# Pruefrunde 1: Python-Namen tragen die Konvention nicht verlaesslich —
# test_lock_guard.py ist ein echter Hook, ab_test.py ein Feature.
CODE = ["notified.go", "test_helpers.go", "testing.go", "contest.py", "latest.py",
        "src/test.ts", "src/app.ts", "src/testing/app.go", "Latest.java", "MyTest.swift",
        "test_parser.py", "pkg/x_test.py", "src/ab_test.py",
        "modules/ios-swiftui/hooks/test_lock_guard.py", "x_test.go/main.go"]


@pytest.mark.parametrize("path", TESTS)
def test_test_files_are_not_gated_code(path):
    assert is_colocated_test_file(path)
    assert is_gated_code_path(path, config={}) is False


@pytest.mark.parametrize("path", CODE)
def test_production_files_stay_gated(path):
    assert not is_colocated_test_file(path), path
    assert is_gated_code_path(path, config={}) is True, path


def test_project_pattern_list_does_not_drop_test_files():
    """Eine eigene always_allowed_patterns-Liste ersetzt die Defaults —
    Testdateien bleiben trotzdem frei (Workaround aus dem Issue ueberfluessig)."""
    cfg = {"strict_code_gate": {"always_allowed_patterns": [r"\.md$"]}}
    assert is_gated_code_path("notified_test.go", config=cfg) is False


def test_loc_gate_counts_go_tests_as_tests():
    import re
    assert any(re.search(p, "pkg/notified_test.go") for p in DEFAULT_TEST_PATH_PATTERNS)


# --- Ende-zu-Ende: edit_gate in phase5_tdd_red ---

@pytest.fixture
def red_project(tmp_path):
    proj = tmp_path / "project"
    (proj / ".git").mkdir(parents=True)
    wf = proj / ".claude" / "workflows"
    wf.mkdir(parents=True)
    (wf / "feat-335.json").write_text(json.dumps(
        {"name": "feat-335", "current_phase": "phase5_tdd_red", "workflow_type": "feature"}))
    return proj


def _edit(proj: Path, rel: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_TOOL_INPUT", "OPENSPEC_FRAMEWORK")}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = "feat-335"
    payload = json.dumps({"tool_input": {"file_path": str(proj / rel)}})
    return subprocess.run([sys.executable, str(HOOKS_DIR / "edit_gate.py")], input=payload,
                          capture_output=True, text=True, env=env, cwd=str(proj))


def test_red_phase_allows_go_test_file(red_project):
    r = _edit(red_project, "notified_test.go")
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("rel", ["notified.go", "test_helpers.go"])
def test_red_phase_still_blocks_go_code(red_project, rel):
    r = _edit(red_project, rel)
    assert r.returncode == 2 and "phase5_tdd_red" in r.stderr, r.stderr


# --- Pruefrunde 1: Infrastruktur und Stop-Lock gehen vor ---

@pytest.mark.parametrize("rel", [".claude/hooks/test_lock_guard.py", ".claude/hooks/x_test.go"])
def test_infrastructure_stays_blocked_despite_test_name(red_project, rel):
    r = _edit(red_project, rel)
    assert r.returncode == 2 and "Infrastruktur" in r.stderr, r.stderr


def test_stop_lock_blocks_colocated_test_file(red_project):
    (red_project / ".claude" / "stop_lock.json").write_text('{"enabled": true}')
    r = _edit(red_project, "notified_test.go")
    assert r.returncode == 2 and "Stop-lock" in r.stderr, r.stderr
