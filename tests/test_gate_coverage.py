"""Tests für AC-Format, LoC-Delta, Docs-Durchlass, Config-API, Status-Anzeige (Issue #14)."""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


# --- AC-Format-Check ---

class TestSpecAcFormat:
    """Tests für _check_acceptance_criteria() in edit_gate."""

    def _make_workflow(self, tmp_path: Path, spec_content: str, spec_mtime=None) -> tuple:
        spec_path = tmp_path / "docs" / "specs" / "test.md"
        spec_path.parent.mkdir(parents=True)
        spec_path.write_text(spec_content)
        if spec_mtime is not None:
            import os as _os
            _os.utime(str(spec_path), (spec_mtime, spec_mtime))
        wf = {
            "name": "test-wf",
            "spec_file": "docs/specs/test.md",
            "current_phase": "phase6_implement",
        }
        return wf, spec_path

    def _run_check(self, tmp_path, spec_content, spec_mtime=None, cutoff=None):
        import importlib, types
        # Frische edit_gate-Instanz mit tmp_path als Root
        import edit_gate
        orig_root = edit_gate._root
        edit_gate._root = tmp_path
        try:
            wf, _ = self._make_workflow(tmp_path, spec_content, spec_mtime)
            if cutoff is not None:
                with patch("config_loader.load_config", return_value={"spec_validation": {"ac_format_required_since": cutoff}}):
                    return edit_gate._check_acceptance_criteria(wf)
            return edit_gate._check_acceptance_criteria(wf)
        finally:
            edit_gate._root = orig_root

    def test_no_ac_section_blocked(self, tmp_path):
        result = self._run_check(tmp_path, "# Spec\n\nKein AC-Abschnitt hier.")
        assert result is not None
        assert "Acceptance Criteria" in result

    def test_ac_section_but_no_entries_blocked(self, tmp_path):
        result = self._run_check(tmp_path, "# Spec\n\n## Acceptance Criteria\n\nKeine Einträge.")
        assert result is not None
        assert "AC-N" in result

    def test_ac_entry_too_short_blocked(self, tmp_path):
        result = self._run_check(tmp_path, "# Spec\n\n## Acceptance Criteria\n\n- **AC-1:** Zu kurz")
        assert result is not None
        assert "too short" in result or "kurz" in result.lower() or "30" in result

    def test_ac_entry_sufficient_length_allowed(self, tmp_path):
        long_ac = "- **AC-1:** Given a valid workflow name / When start is called / Then the workflow is created"
        result = self._run_check(tmp_path, f"# Spec\n\n## Acceptance Criteria\n\n{long_ac}")
        assert result is None

    def test_multiple_acs_one_short_blocked(self, tmp_path):
        content = (
            "# Spec\n\n## Acceptance Criteria\n\n"
            "- **AC-1:** Given a valid workflow name / When start is called / Then the workflow is created\n"
            "- **AC-2:** Kurz"
        )
        result = self._run_check(tmp_path, content)
        assert result is not None

    def test_legacy_spec_before_cutoff_allowed(self, tmp_path):
        # Spec-Datei mit altem mtime (2020)
        old_ts = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
        long_ac = "- **AC-1:** Given a valid workflow name / When start is called / Then the workflow is created"
        result = self._run_check(
            tmp_path,
            f"# Spec\n\n## Acceptance Criteria\n\n{long_ac}",
            spec_mtime=old_ts,
            cutoff="2025-01-01T00:00:00",
        )
        # Legacy-Spec → kein Block
        assert result is None

    def test_no_cutoff_configured_normal_check_applies(self, tmp_path):
        # Ohne Cutoff: normaler Check greift
        result = self._run_check(tmp_path, "# Spec\n\n## Acceptance Criteria\n\n- **AC-1:** Kurz", cutoff=None)
        assert result is not None


# --- Edit-Gate Live (Subprocess) ---

def _run_edit_gate(env: dict, file_path: str, cwd: "str | None" = None) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"file_path": file_path}})
    full_env = dict(os.environ)
    full_env.update(env)
    # cwd auf das jeweilige tmp_path setzen, damit _find_worktree_root() im
    # Subprozess innerhalb des Test-Verzeichnisses startet statt im echten
    # Worktree-CWD der Testsession (verhindert Cross-Session-Kontamination).
    if cwd is None:
        cwd = env.get("CLAUDE_PROJECT_DIR")
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "edit_gate.py")],
        input=payload, capture_output=True, text=True, env=full_env, cwd=cwd,
    )


class TestEditGateLive:
    def test_docs_spec_not_blocked_by_loc_gate(self, tmp_path):
        """docs/specs/*.md ist ALWAYS_ALLOWED → kein Block."""
        (tmp_path / ".git").mkdir()
        doc_file = tmp_path / "docs" / "specs" / "foo.md"
        doc_file.parent.mkdir(parents=True)
        env = {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "OPENSPEC_ACTIVE_WORKFLOW": "",
        }
        result = _run_edit_gate(env, str(doc_file))
        # Docs sind always-allowed → darf nicht durch LoC oder Phase geblockt werden
        # (wird geblockt durch "No active workflow" für .md NICHT — weil .md ALWAYS_ALLOWED_PATTERNS)
        assert result.returncode == 0

    def test_phase6_edit_on_spec_without_ac_blocked(self, tmp_path):
        """Phase-6-Edit auf Spec ohne AC → Edit-Gate blockt."""
        (tmp_path / ".git").mkdir()
        # Workflow mit Spec anlegen
        wf_dir = tmp_path / ".claude" / "workflows"
        wf_dir.mkdir(parents=True)
        spec_path = tmp_path / "docs" / "specs" / "myspec.md"
        spec_path.parent.mkdir(parents=True)
        spec_path.write_text("# Spec\n\nKein Acceptance Criteria Abschnitt.\n")
        wf_data = {
            "name": "test-wf",
            "workflow_type": "feature",
            "current_phase": "phase6_implement",
            "spec_file": "docs/specs/myspec.md",
            "spec_approved": True,
            "red_test_done": True,
        }
        (wf_dir / "test-wf.json").write_text(json.dumps(wf_data))
        code_file = tmp_path / "src" / "module.py"
        code_file.parent.mkdir(parents=True)
        env = {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "OPENSPEC_ACTIVE_WORKFLOW": "test-wf",
        }
        result = _run_edit_gate(env, str(code_file), cwd=str(tmp_path))
        assert result.returncode == 2
        assert "Acceptance Criteria" in result.stderr


# --- LoC-Delta ---

class TestGetLocDelta:
    """Tests für _check_loc_delta() in edit_gate."""

    def _run_loc_check(self, tmp_path, numstat_output: str, max_loc: int = 250, excludes=None):
        import edit_gate
        orig_root = edit_gate._root
        edit_gate._root = tmp_path
        try:
            config = {"scope_guard": {"max_loc_delta": max_loc, "loc_exclude_patterns": excludes or []}}
            workflow = {"name": "test-wf", "current_phase": "phase6_implement"}
            with patch("subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.stdout = numstat_output
                mock_run.return_value = mock_result
                # Zweiter Aufruf (für loc_delta_current schreiben) soll auch OK sein
                return edit_gate._check_loc_delta(config, workflow)
        finally:
            edit_gate._root = orig_root

    def test_counts_added_and_deleted(self, tmp_path):
        # 10 added + 5 deleted = 15 total → unter Limit 250
        result = self._run_loc_check(tmp_path, "10\t5\tsrc/foo.py\n")
        assert result is None

    def test_excludes_po_files(self, tmp_path):
        # .po-Datei soll ausgeschlossen werden
        result = self._run_loc_check(
            tmp_path,
            "300\t0\tlocales/de.po\n",
            excludes=[r"\.po$"],
        )
        assert result is None  # Ausgeschlossen → kein Block

    def test_excludes_binary_files(self, tmp_path):
        # Binärdateien haben "-" statt Zahlen
        result = self._run_loc_check(tmp_path, "-\t-\timage.png\n")
        assert result is None

    def test_empty_output_no_block(self, tmp_path):
        result = self._run_loc_check(tmp_path, "")
        assert result is None

    def test_exceeds_limit_blocked(self, tmp_path):
        result = self._run_loc_check(tmp_path, "300\t0\tsrc/foo.py\n", max_loc=250)
        assert result is not None
        assert "300" in result or "BLOCKED" in result

    def test_exactly_at_limit_not_blocked(self, tmp_path):
        result = self._run_loc_check(tmp_path, "125\t125\tsrc/foo.py\n", max_loc=250)
        assert result is None


class TestCheckLocDelta:
    def test_loc_override_raises_limit(self, tmp_path):
        import edit_gate
        orig_root = edit_gate._root
        edit_gate._root = tmp_path
        try:
            config = {"scope_guard": {"max_loc_delta": 250, "loc_exclude_patterns": []}}
            # Override auf 500 → 300 LoC sollen durchkommen
            workflow = {"name": "test-wf", "current_phase": "phase6_implement", "loc_limit_override": "500"}
            with patch("subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.stdout = "300\t0\tsrc/foo.py\n"
                mock_run.return_value = mock_result
                result = edit_gate._check_loc_delta(config, workflow)
            assert result is None  # Override 500 > 300
        finally:
            edit_gate._root = orig_root

    def test_delta_under_limit_allowed(self, tmp_path):
        import edit_gate
        orig_root = edit_gate._root
        edit_gate._root = tmp_path
        try:
            config = {"scope_guard": {"max_loc_delta": 250, "loc_exclude_patterns": []}}
            workflow = {"name": "test-wf", "current_phase": "phase6_implement"}
            with patch("subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.stdout = "100\t50\tsrc/foo.py\n"
                mock_run.return_value = mock_result
                result = edit_gate._check_loc_delta(config, workflow)
            assert result is None
        finally:
            edit_gate._root = orig_root

    def test_delta_exceeds_limit_blocked(self, tmp_path):
        import edit_gate
        orig_root = edit_gate._root
        edit_gate._root = tmp_path
        try:
            config = {"scope_guard": {"max_loc_delta": 100, "loc_exclude_patterns": []}}
            workflow = {"name": "test-wf", "current_phase": "phase6_implement"}
            with patch("subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.stdout = "200\t0\tsrc/foo.py\n"
                mock_run.return_value = mock_result
                result = edit_gate._check_loc_delta(config, workflow)
            assert result is not None
            assert "BLOCKED" in result
        finally:
            edit_gate._root = orig_root

    def test_git_error_fail_soft(self, tmp_path):
        import edit_gate, subprocess as _sp
        orig_root = edit_gate._root
        edit_gate._root = tmp_path
        try:
            config = {"scope_guard": {"max_loc_delta": 100, "loc_exclude_patterns": []}}
            workflow = {"name": "test-wf", "current_phase": "phase6_implement"}
            with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
                result = edit_gate._check_loc_delta(config, workflow)
            assert result is None  # fail-soft
        finally:
            edit_gate._root = orig_root


# --- Scope Config ---

class TestScopeConfig:
    def test_defaults_without_config(self, tmp_path, monkeypatch):
        import config_loader
        monkeypatch.setattr(config_loader, "load_config", lambda: {})
        max_loc, excludes = config_loader.get_scope_loc_config()
        assert max_loc == 250
        assert excludes == []

    def test_reads_from_yaml_config(self, tmp_path, monkeypatch):
        import config_loader
        monkeypatch.setattr(config_loader, "load_config", lambda: {
            "scope_guard": {
                "max_loc_delta": 400,
                "loc_exclude_patterns": [r"\.po$", r"\.strings$"],
            }
        })
        max_loc, excludes = config_loader.get_scope_loc_config()
        assert max_loc == 400
        assert r"\.po$" in excludes


# --- Status mit loc_limit_override ---

class TestStatusLocOverride:
    def test_status_shows_override(self, tmp_path):
        wf_dir = tmp_path / ".claude" / "workflows"
        wf_dir.mkdir(parents=True)
        log_dir = tmp_path / ".claude" / "workflows" / "_log"
        log_dir.mkdir(parents=True)
        wf_data = {
            "name": "test-wf",
            "workflow_type": "feature",
            "current_phase": "phase6_implement",
            "spec_file": None,
            "spec_approved": False,
            "context_file": None,
            "affected_files": [],
            "test_artifacts": [],
            "is_new_ui": False,
            "red_test_done": False,
            "ui_test_red_done": False,
            "green_approved": False,
            "adversary_verdict": None,
            "phase_transitions": [],
            "fix_loop_iterations": 0,
            "phase_log": [],
            "loc_delta_current": "+312",
            "loc_limit_override": "500",
        }
        (wf_dir / "test-wf.json").write_text(json.dumps(wf_data))
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
        env["OPENSPEC_ACTIVE_WORKFLOW"] = "test-wf"
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "workflow.py"), "status"],
            capture_output=True, text=True, env=env, cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert "/500" in result.stdout
        assert "override" in result.stdout
