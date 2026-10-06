"""Issue #379: `set-field` setzte jeden Schluessel ohne Pruefung.

`set-field workflow_type feature-fast` entzog einen freigegebenen `feature`-
Workflow dem Adversary-Gate beim Abschluss: `complete` archivierte ohne
Verdict. Zweiter Punkt: der Banner-Fetch haengte `-oBatchMode=yes` auch an
nicht-OpenSSH-Clients (plink) und brach dort still ab.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import session_banner  # noqa: E402

NAME = "wf-379"


def _project(tmp_path, phase="phase7_validate", wf_type="feature", **extra):
    wf_dir = tmp_path / ".claude" / "workflows"
    (wf_dir / "_log").mkdir(parents=True)
    data = {"name": NAME, "workflow_type": wf_type, "current_phase": phase,
            "context_file": "docs/context/x.md", "spec_file": "docs/specs/x.md",
            "spec_approved": True, "red_test_done": True, "adversary_verdict": None}
    data.update(extra)
    (wf_dir / f"{NAME}.json").write_text(json.dumps(data))
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    (wf_dir / "_log" / f"{ts}_{NAME}.yaml").write_text("outcome: success\n")
    return wf_dir


def _token(tmp_path):
    (tmp_path / ".claude" / "user_override_token.json").write_text(json.dumps(
        {"version": 2, "tokens": {NAME: {"created": datetime.now().isoformat(),
                                         "granted_by": "user_prompt"}}}))


def _run(tmp_path, *args):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_TOOL_INPUT"}
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = NAME
    return subprocess.run([sys.executable, str(HOOKS_DIR / "workflow.py"), *args],
                          capture_output=True, text=True, env=env, cwd=str(tmp_path))


def _state(wf_dir):
    return json.loads((wf_dir / f"{NAME}.json").read_text())


@pytest.mark.parametrize("phase", ["phase4_approved", "phase7_validate", "phase8_complete"])
def test_downgrade_after_approval_blocked(tmp_path, phase):
    wf_dir = _project(tmp_path, phase=phase)
    r = _run(tmp_path, "set-field", "workflow_type", "feature-fast")
    assert r.returncode == 1 and "BLOCKED" in r.stderr, r.stdout + r.stderr
    assert _state(wf_dir)["workflow_type"] == "feature"


def test_reproduction_from_issue_no_longer_archives(tmp_path):
    wf_dir = _project(tmp_path)
    _run(tmp_path, "set-field", "workflow_type", "feature-fast")
    r = _run(tmp_path, "finish")
    assert r.returncode == 1, r.stdout + r.stderr
    assert not (wf_dir / "_archive" / f"{NAME}.json").exists()


def test_downgrade_with_override_allowed(tmp_path):
    wf_dir = _project(tmp_path)
    _token(tmp_path)
    r = _run(tmp_path, "set-field", "workflow_type", "feature-fast")
    assert r.returncode == 0, r.stderr
    assert _state(wf_dir)["workflow_type"] == "feature-fast"


def test_legacy_bug_workflow_needs_override_too(tmp_path):
    wf_dir = _project(tmp_path, wf_type="bug")
    r = _run(tmp_path, "set-field", "workflow_type", "feature-fast")
    assert r.returncode == 1, r.stdout
    _token(tmp_path)
    r = _run(tmp_path, "set-field", "workflow_type", "feature-fast")
    assert r.returncode == 0, r.stderr
    assert _state(wf_dir)["workflow_type"] == "feature-fast"


@pytest.mark.parametrize("phase", ["phase1_context", "phase3_spec"])
def test_downgrade_before_approval_free(tmp_path, phase):
    wf_dir = _project(tmp_path, phase=phase)
    r = _run(tmp_path, "set-field", "workflow_type", "feature-fast")
    assert r.returncode == 0, r.stderr
    assert _state(wf_dir)["workflow_type"] == "feature-fast"


def test_upgrade_to_feature_always_free(tmp_path):
    wf_dir = _project(tmp_path, wf_type="feature-fast")
    r = _run(tmp_path, "set-field", "workflow_type", "feature")
    assert r.returncode == 0, r.stderr
    assert _state(wf_dir)["workflow_type"] == "feature"


def test_unknown_type_rejected(tmp_path):
    wf_dir = _project(tmp_path, phase="phase1_context")
    r = _run(tmp_path, "set-field", "workflow_type", "bug")
    assert r.returncode == 1, r.stdout
    assert _state(wf_dir)["workflow_type"] == "feature"


@pytest.mark.parametrize("key,value", [
    ("current_phase", "phase8_complete"),
    ("spec_approved", "true"),
    ("red_test_done", "true"),
    ("ui_test_red_done", "true"),
    ("status", "complete"),
])
def test_gate_keys_blocked(tmp_path, key, value):
    wf_dir = _project(tmp_path, phase="phase3_spec", spec_approved=False,
                      red_test_done=False)
    before = _state(wf_dir)
    r = _run(tmp_path, "set-field", key, value)
    assert r.returncode == 1 and "BLOCKED" in r.stderr and key in r.stderr, r.stdout
    assert _state(wf_dir) == before


@pytest.mark.parametrize("key,value", [
    ("github_issue", "379"),
    ("loc_limit_override", "400"),
    ("spec_file", "docs/specs/y.md"),
    ("adversary_findings_total", "3"),
])
def test_regular_keys_still_settable(tmp_path, key, value):
    wf_dir = _project(tmp_path)
    r = _run(tmp_path, "set-field", key, value)
    assert r.returncode == 0, r.stderr
    assert str(_state(wf_dir)[key]) == value


# --- Zweiter Punkt: BatchMode nur fuer OpenSSH ---

def _env(**kw):
    env = {k: v for k, v in kw.items() if v is not None}
    session_banner._batch_ssh(env)
    return env.get("GIT_SSH_COMMAND")


def test_default_ssh_gets_batchmode():
    assert _env() == "ssh -oBatchMode=yes"


def test_openssh_path_gets_batchmode():
    assert _env(GIT_SSH_COMMAND="/usr/bin/ssh -i k") == "/usr/bin/ssh -i k -oBatchMode=yes"


def test_plink_command_untouched():
    assert _env(GIT_SSH_COMMAND="plink -batch") == "plink -batch"


def test_windows_plink_path_untouched():
    cmd = r'"C:\Program Files\PuTTY\plink.exe" -batch'
    assert _env(GIT_SSH_COMMAND=cmd) == cmd


def test_plink_variant_untouched():
    assert _env(GIT_SSH_COMMAND="ssh-wrapper", GIT_SSH_VARIANT="plink") == "ssh-wrapper"


def test_git_ssh_alone_not_overridden():
    # GIT_SSH_COMMAND hat Vorrang vor GIT_SSH — setzen hiesse den Client ersetzen
    assert _env(GIT_SSH="/opt/plink") is None
