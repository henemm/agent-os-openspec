"""#387: falsch registriertes RED-Artefakt muss per CLI entfernbar sein."""

import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "core" / "hooks"
NAME = "wf387"


def _run(tmp_path, *args):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = NAME
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py"), *args],
        capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )


def _setup(tmp_path):
    d = tmp_path / ".claude" / "workflows"
    d.mkdir(parents=True)
    (d / f"{NAME}.json").write_text(json.dumps({
        "name": NAME, "workflow_type": "feature", "current_phase": "phase6_implement",
        "test_artifacts": [
            {"type": "test_output", "path": "a.log", "phase": "phase5_tdd_red"},
            {"type": "test_output", "path": "b.log", "phase": "phase5_tdd_red"},
        ],
    }))
    return d / f"{NAME}.json"


def test_remove_artifact_by_path(tmp_path):
    f = _setup(tmp_path)
    r = _run(tmp_path, "remove-artifact", "a.log", "phase5_tdd_red")
    assert r.returncode == 0, r.stderr
    paths = [a["path"] for a in json.loads(f.read_text())["test_artifacts"]]
    assert paths == ["b.log"]


def test_remove_artifact_unknown_path_fails(tmp_path):
    f = _setup(tmp_path)
    r = _run(tmp_path, "remove-artifact", "zzz.log")
    assert r.returncode == 1
    assert len(json.loads(f.read_text())["test_artifacts"]) == 2
