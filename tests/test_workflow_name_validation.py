"""Tests für Workflow-Namen-Validierung und AMBIGUOUS-Block (Issue #14)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import workflow as wf_module


# --- _validate_name ---

class TestValidateName:
    def test_traversal_rejected(self):
        with pytest.raises(SystemExit):
            wf_module._validate_name("../../etc/x")

    def test_glob_star_rejected(self):
        with pytest.raises(SystemExit):
            wf_module._validate_name("feat*")

    def test_glob_question_rejected(self):
        with pytest.raises(SystemExit):
            wf_module._validate_name("feat?")

    def test_empty_name_rejected(self):
        with pytest.raises(SystemExit):
            wf_module._validate_name("")

    def test_too_long_rejected(self):
        with pytest.raises(SystemExit):
            wf_module._validate_name("a" * 65)

    def test_valid_names_accepted(self):
        # Darf NICHT werfen
        wf_module._validate_name("my-feature-01")
        wf_module._validate_name("FEAT_001")
        wf_module._validate_name("a")
        wf_module._validate_name("a" * 64)

    def test_slash_rejected(self):
        with pytest.raises(SystemExit):
            wf_module._validate_name("foo/bar")

    def test_dot_dot_rejected(self):
        with pytest.raises(SystemExit):
            wf_module._validate_name("..foo")


class TestCmdStartCallsValidate(object):
    """Subprocess-Test: cmd_start ruft _validate_name auf."""

    def test_start_traversal_exits(self, tmp_path):
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
        (tmp_path / ".git").mkdir()
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "workflow.py"), "start", "../../etc/x"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode != 0
        assert "INVALID" in result.stderr


# --- AMBIGUOUS-Block in bash_gate ---

def _run_bash_gate(env: dict, command: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"command": command}})
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "bash_gate.py")],
        input=payload, capture_output=True, text=True, env=full_env,
    )


class TestAmbiguousBlock:
    def _make_workflow(self, tmp_path: Path, verdict: str, with_override: bool = False) -> str:
        wf_dir = tmp_path / ".claude" / "workflows"
        wf_dir.mkdir(parents=True)
        data = {
            "name": "test-wf",
            "workflow_type": "feature",
            "current_phase": "phase7_validate",
            "spec_approved": True,
            "adversary_verdict": verdict,
        }
        if with_override:
            data["adversary_ambiguous_override"] = {"reason": "test", "at": "2026-01-01T00:00:00"}
        (wf_dir / "test-wf.json").write_text(json.dumps(data))
        return "test-wf"

    def test_ambiguous_without_override_blocks(self, tmp_path):
        self._make_workflow(tmp_path, "AMBIGUOUS")
        env = {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "OPENSPEC_ACTIVE_WORKFLOW": "test-wf",
        }
        result = _run_bash_gate(env, "git commit -m test")
        assert result.returncode == 2
        assert "AMBIGUOUS" in result.stderr

    def test_ambiguous_with_override_allows(self, tmp_path):
        self._make_workflow(tmp_path, "AMBIGUOUS", with_override=True)
        env = {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "OPENSPEC_ACTIVE_WORKFLOW": "test-wf",
        }
        result = _run_bash_gate(env, "git commit -m test")
        # Mit Override darf der AMBIGUOUS-Check nicht blocken
        assert "AMBIGUOUS" not in result.stderr or result.returncode == 0

    def test_verified_not_blocked(self, tmp_path):
        self._make_workflow(tmp_path, "VERIFIED")
        env = {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "OPENSPEC_ACTIVE_WORKFLOW": "test-wf",
        }
        result = _run_bash_gate(env, "git commit -m test")
        # VERIFIED darf nie durch AMBIGUOUS-Check geblockt werden
        assert "AMBIGUOUS" not in result.stderr

    def test_no_verdict_not_ambiguous_blocked(self, tmp_path):
        self._make_workflow(tmp_path, "")
        env = {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "OPENSPEC_ACTIVE_WORKFLOW": "test-wf",
        }
        result = _run_bash_gate(env, "git commit -m test")
        # Fehlender Verdict → anderer Block-Pfad, nicht AMBIGUOUS
        assert "AMBIGUOUS" not in result.stderr
