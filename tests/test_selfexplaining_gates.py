"""Tests for spec: Selbst-erklärende Gate-Block-Meldungen (selfexplaining-gates).

Covers AC-1 .. AC-7 from docs/specs/selfexplaining-gates.md.

The hook modules live under core/hooks/ (not .claude/hooks/) in this meta-repo.
"""

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import hook_utils  # noqa: E402


# --------------------------------------------------------------------------
# AC-4 + AC-7: quellen-bewusste Auflösung
# --------------------------------------------------------------------------

def test_ac4_resolve_from_env(monkeypatch):
    """Env-Var gesetzt → (name, 'env')."""
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "feature-x")
    name, source = hook_utils.resolve_active_workflow()
    assert name == "feature-x"
    assert source == "env"


def test_ac4_resolve_from_settings(monkeypatch, tmp_path):
    """Keine Env-Var, Workflow nur in settings.local.json → (name, 'settings')."""
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "settings.local.json").write_text(
        json.dumps({"env": {"OPENSPEC_ACTIVE_WORKFLOW": "settings-wf"}})
    )
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: tmp_path)
    name, source = hook_utils.resolve_active_workflow()
    assert name == "settings-wf"
    assert source == "settings"


def test_ac4_resolve_none(monkeypatch, tmp_path):
    """Weder Env-Var noch settings → ('', 'none')."""
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: tmp_path)
    name, source = hook_utils.resolve_active_workflow()
    assert name == ""
    assert source == "none"


def test_ac4_resolve_broken_settings(monkeypatch, tmp_path):
    """Defekte settings.local.json → ('', 'none'), kein Crash."""
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "settings.local.json").write_text("{ this is not json")
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: tmp_path)
    name, source = hook_utils.resolve_active_workflow()
    assert name == ""
    assert source == "none"


def test_ac4_resolve_null_env_settings(monkeypatch, tmp_path):
    """settings.local.json mit {"env": null} → ('', 'none'), kein Crash (F001)."""
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "settings.local.json").write_text(json.dumps({"env": None}))
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: tmp_path)
    name, source = hook_utils.resolve_active_workflow()
    assert name == ""
    assert source == "none"


def test_ac7_get_active_workflow_name_returns_plain_string(monkeypatch):
    """get_active_workflow_name() liefert weiterhin reinen Name-String (env)."""
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "plain-name")
    result = hook_utils.get_active_workflow_name()
    assert result == "plain-name"
    assert isinstance(result, str)


def test_ac7_get_active_workflow_name_empty(monkeypatch, tmp_path):
    """Kein Workflow → leerer String (unverändertes Verhalten)."""
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: tmp_path)
    result = hook_utils.get_active_workflow_name()
    assert result == ""
    assert isinstance(result, str)


def test_ac7_get_active_workflow_name_matches_resolve(monkeypatch):
    """get_active_workflow_name() delegiert an resolve_active_workflow()[0]."""
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "delegate-check")
    assert hook_utils.get_active_workflow_name() == hook_utils.resolve_active_workflow()[0]


# --------------------------------------------------------------------------
# AC-1 / AC-2 / AC-3: gate_diagnostics suffix builder
# --------------------------------------------------------------------------

def test_ac1_diagnostics_no_active_workflow(monkeypatch, tmp_path):
    """Kein aktiver Workflow → '[wf=— (none) | token=keins]'."""
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: tmp_path)
    suffix = hook_utils.gate_diagnostics()
    assert "wf=— (none)" in suffix
    assert "token=keins" in suffix
    assert suffix.startswith("[") and suffix.endswith("]")


def test_ac2_diagnostics_with_phase(monkeypatch, tmp_path):
    """Aktiver Workflow in phase3_spec → enthält name, source, token, phase."""
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "feature-x")
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: tmp_path)
    suffix = hook_utils.gate_diagnostics({"current_phase": "phase3_spec"})
    assert "wf=feature-x (env)" in suffix
    assert "phase=phase3_spec" in suffix
    assert "token=" in suffix


def test_ac3_diagnostics_loc_delta_and_limit(monkeypatch, tmp_path):
    """LoC-Block → delta=+N und limit=M im Suffix."""
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "feature-x")
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: tmp_path)
    suffix = hook_utils.gate_diagnostics(
        {"current_phase": "phase6_implement"}, delta="+312", limit=250
    )
    assert "delta=+312" in suffix
    assert "limit=250" in suffix


def test_diagnostics_token_valid(monkeypatch, tmp_path):
    """Gültiger Override-Token → token=gültig."""
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "feature-x")
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: tmp_path)
    import override_token
    monkeypatch.setattr(override_token, "has_valid_token", lambda name=None: True)
    suffix = hook_utils.gate_diagnostics({"current_phase": "phase6_implement"})
    assert "token=gültig" in suffix


# --------------------------------------------------------------------------
# AC-5: Token-Import-Fehler → token=? und kein Crash
# --------------------------------------------------------------------------

def test_ac5_token_import_failure(monkeypatch, tmp_path):
    """override_token nicht importierbar → token=?, wirft nicht."""
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "feature-x")
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: tmp_path)
    # Make `from override_token import has_valid_token` raise
    monkeypatch.setitem(sys.modules, "override_token", None)
    suffix = hook_utils.gate_diagnostics({"current_phase": "phase6_implement"})
    assert "token=?" in suffix


def test_ac5_token_function_raises(monkeypatch, tmp_path):
    """has_valid_token wirft Exception → token=?, gate_diagnostics wirft nicht."""
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "feature-x")
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: tmp_path)
    import override_token

    def _boom(name=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(override_token, "has_valid_token", _boom)
    suffix = hook_utils.gate_diagnostics({"current_phase": "phase6_implement"})
    assert "token=?" in suffix


def test_ac5_gate_diagnostics_never_raises(monkeypatch):
    """gate_diagnostics wirft auch bei kaputtem resolve nie."""
    def _boom():
        raise RuntimeError("resolve exploded")

    monkeypatch.setattr(hook_utils, "resolve_active_workflow", _boom)
    # Must not raise
    suffix = hook_utils.gate_diagnostics()
    assert isinstance(suffix, str)
    assert suffix.startswith("[") and suffix.endswith("]")


# --------------------------------------------------------------------------
# AC-6: Kein .active-Lesepfad mehr in den vier Hooks
# --------------------------------------------------------------------------

@pytest.mark.parametrize("hook_name", [
    "edit_gate.py", "bash_gate.py", "post_bash.py", "phase_listener.py",
])
def test_ac6_no_active_symlink_read_paths(hook_name):
    """Keiner der vier Hooks liest den .active-Symlink mehr."""
    source = (HOOKS_DIR / hook_name).read_text()
    # The literal symlink name used as a path component must be gone.
    assert '".active"' not in source, f"{hook_name} still references .active path literal"
    # os.readlink on a .active link must be gone.
    assert "readlink" not in source, f"{hook_name} still calls readlink (symlink read path)"


def test_ac6_phase_listener_docstring_no_symlink_claim():
    """phase_listener-Docstring behauptet nicht mehr '.active symlink (default)'."""
    source = (HOOKS_DIR / "phase_listener.py").read_text()
    assert ".active symlink" not in source


# --------------------------------------------------------------------------
# End-to-End: echter edit_gate-Block enthält den Diagnose-Suffix
# --------------------------------------------------------------------------

def _run_edit_gate(env, file_path):
    import subprocess
    payload = json.dumps({"tool_input": {"file_path": file_path}})
    full_env = dict(os.environ)
    full_env.update(env)
    full_env["CLAUDE_PROJECT_DIR"] = str(env.get("CLAUDE_PROJECT_DIR", REPO_ROOT))
    proc = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "edit_gate.py")],
        input=payload, capture_output=True, text=True, env=full_env,
    )
    return proc


def test_ac1_e2e_no_workflow_block_has_diagnostics(tmp_path):
    """edit_gate blockt 'No active workflow' und Meldung trägt Diagnose-Suffix."""
    # Fresh empty project so no workflow is found
    (tmp_path / ".git").mkdir()
    code_file = tmp_path / "src" / "module.py"
    code_file.parent.mkdir(parents=True)
    env = {
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "OPENSPEC_ACTIVE_WORKFLOW": "",
    }
    proc = _run_edit_gate(env, str(code_file))
    assert proc.returncode == 2, proc.stderr
    assert "No active workflow" in proc.stderr
    assert "wf=— (none)" in proc.stderr
    assert "token=keins" in proc.stderr
