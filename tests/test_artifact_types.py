"""Tests für Artefakt-Typen von workflow.py (Issue #41).

`adversary_dialog` ist ein dokumentierter Artefakt-Typ (Skill 50-implement,
Step 8c), wurde aber von `VALID_ARTIFACT_TYPES` nicht akzeptiert.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import workflow as wf_module


def test_adversary_dialog_in_valid_types():
    """(a) 'adversary_dialog' ist ein gültiger Artefakt-Typ."""
    assert "adversary_dialog" in wf_module.VALID_ARTIFACT_TYPES


def _make_tmp_workflow(tmp_path: Path, name: str = "test-wf") -> None:
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    data = {
        "name": name,
        "workflow_type": "feature",
        "current_phase": "phase6b_adversary",
        "spec_approved": True,
    }
    (wf_dir / f"{name}.json").write_text(json.dumps(data))


def _run_add_artifact(tmp_path: Path, name: str, *artifact_args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = name
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py"), "add-artifact", *artifact_args],
        capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )


def test_add_artifact_adversary_dialog_accepted(tmp_path):
    """(b) add-artifact adversary_dialog läuft gegen einen tmp-Workflow durch."""
    _make_tmp_workflow(tmp_path)
    result = _run_add_artifact(
        tmp_path, "test-wf",
        "adversary_dialog", "docs/artifacts/adversary.md", "Adversary protocol", "phase6b_adversary",
    )
    assert result.returncode == 0, result.stderr
    assert "Invalid artifact type" not in result.stderr

    # Persistiert mit korrektem Typ
    saved = json.loads((tmp_path / ".claude" / "workflows" / "test-wf.json").read_text())
    types = [a["type"] for a in saved.get("test_artifacts", [])]
    assert "adversary_dialog" in types


def test_add_artifact_invalid_type_rejected(tmp_path):
    """(c) Ein ungültiger Typ wird weiterhin abgelehnt."""
    _make_tmp_workflow(tmp_path)
    result = _run_add_artifact(
        tmp_path, "test-wf",
        "quatsch", "docs/artifacts/x.md", "Nonsense", "phase6b_adversary",
    )
    assert result.returncode != 0
    assert "Invalid artifact type" in result.stderr
