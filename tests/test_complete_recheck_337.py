"""Issue #337: `workflow.py finish/complete` prueft auch dann voll, wenn der
Workflow schon auf phase8_complete steht. Vorher kehrte `_validate_transition`
bei gleicher Phase sofort zurueck und archivierte ohne Adversary-Nachweis."""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"


def _project(tmp_path, phase="phase8_complete", **extra):
    wf_dir = tmp_path / ".claude" / "workflows"
    (wf_dir / "_log").mkdir(parents=True)
    data = {"name": "wf-337", "workflow_type": "feature", "current_phase": phase,
            "context_file": "docs/context/x.md", "adversary_verdict": None}
    data.update(extra)
    (wf_dir / "wf-337.json").write_text(json.dumps(data))
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    (wf_dir / "_log" / f"{ts}_wf-337.yaml").write_text("outcome: success\n")
    return wf_dir


def _run(tmp_path, *args):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_TOOL_INPUT"}
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = "wf-337"
    return subprocess.run([sys.executable, str(HOOKS_DIR / "workflow.py"), *args],
                          capture_output=True, text=True, env=env, cwd=str(tmp_path))


@pytest.mark.parametrize("cmd", ["complete", "finish"])
def test_complete_in_phase8_without_evidence_is_blocked(tmp_path, cmd):
    wf_dir = _project(tmp_path)
    r = _run(tmp_path, cmd)
    assert r.returncode == 1 and "BLOCKED" in r.stderr, r.stdout + r.stderr
    assert (wf_dir / "wf-337.json").exists(), "nicht archiviert"
    assert not (wf_dir / "_archive" / "wf-337.json").exists()


def test_same_phase_transition_below_phase8_still_free(tmp_path):
    _project(tmp_path, phase="phase6_implement")
    r = _run(tmp_path, "phase", "phase6_implement")
    assert r.returncode == 0, r.stderr
