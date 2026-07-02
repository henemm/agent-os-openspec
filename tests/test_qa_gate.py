import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
COPY_FILES = ["qa_gate.py", "workflow.py", "hook_utils.py",
              "config_loader.py", "override_token.py"]


def _setup_fake_project(tmp_path: Path, wf_name: str, skip_workflow_py: bool = False) -> Path:
    fake_hooks = tmp_path / "fake_hooks"
    fake_hooks.mkdir()
    for fname in COPY_FILES:
        if skip_workflow_py and fname == "workflow.py":
            continue
        shutil.copy(HOOKS_DIR / fname, fake_hooks / fname)
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / f"{wf_name}.json").write_text(json.dumps({
        "name": wf_name, "current_phase": "phase6_implement",
        "adversary_verdict": None,
    }))
    return fake_hooks


def _run_qa_gate(fake_hooks: Path, tmp_path: Path, wf_name: str, output_file: Path):
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "OPENSPEC_ACTIVE_WORKFLOW": wf_name,
           "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, str(fake_hooks / "qa_gate.py"), str(output_file)],
        capture_output=True, text=True, cwd=str(fake_hooks), env=env,
    )


def test_verdict_persisted_in_flat_consumer_layout(tmp_path):
    fake_hooks = _setup_fake_project(tmp_path, "wf1")
    output = tmp_path / "test-output.txt"
    output.write_text("test session starts\n5 passed in 1.2s\n" * 3)
    result = _run_qa_gate(fake_hooks, tmp_path, "wf1", output)
    assert result.returncode == 0
    state = json.loads((tmp_path / ".claude" / "workflows" / "wf1.json").read_text())
    assert state["adversary_verdict"] is not None
    assert state["adversary_verdict"].startswith("VERIFIED:")


def test_missing_workflow_py_fails_loudly(tmp_path):
    fake_hooks = _setup_fake_project(tmp_path, "wf2", skip_workflow_py=True)
    output = tmp_path / "test-output.txt"
    output.write_text("test session starts\n5 passed in 1.2s\n" * 3)
    result = _run_qa_gate(fake_hooks, tmp_path, "wf2", output)
    assert result.returncode != 0
    assert "Commit is now allowed." not in result.stdout
