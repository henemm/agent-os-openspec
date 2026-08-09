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

    def test_counts_only_added_not_deleted(self, tmp_path):
        # Nur `added` zaehlt: 300 added blockt, 300 deleted (bei 10 added) nicht
        assert self._run_loc_check(tmp_path, "10\t5\tsrc/foo.py\n") is None
        assert self._run_loc_check(tmp_path, "10\t300\tsrc/foo.py\n") is None
        assert self._run_loc_check(tmp_path, "300\t0\tsrc/foo.py\n") is not None

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
        result = self._run_loc_check(tmp_path, "250\t0\tsrc/foo.py\n", max_loc=250)
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


# --- LoC-Delta: Produktiv/Test-Split (Issue #94) ---

def _run_split_loc_check(tmp_path, monkeypatch, numstat_output: str,
                         scope_cfg: dict, workflow_extra: "dict | None" = None):
    """Ruft edit_gate._check_loc_delta() mit gemocktem git-numstat + Config auf.

    Die Config wird sowohl als `config`-Argument uebergeben als auch ueber
    config_loader.load_config() bereitgestellt, damit der Test unabhaengig
    davon ist, ueber welchen der beiden Wege die Implementierung die
    scope_guard-Werte bezieht (Spec: via get_scope_loc_config() /
    get_scope_test_loc_config()).
    """
    import edit_gate
    import config_loader

    monkeypatch.setattr(config_loader, "load_config",
                        lambda: {"scope_guard": dict(scope_cfg)})

    orig_root = edit_gate._root
    edit_gate._root = tmp_path
    try:
        config = {"scope_guard": dict(scope_cfg)}
        workflow = {"name": "test-wf", "current_phase": "phase6_implement"}
        workflow.update(workflow_extra or {})
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = numstat_output
            mock_run.return_value = mock_result
            return edit_gate._check_loc_delta(config, workflow)
    finally:
        edit_gate._root = orig_root


class TestLocDeltaProdTestSplit:
    """AC-1 bis AC-5 aus openspec/changes/feat-94-loc-limit-risk (Issue #94)."""

    def test_ac1_only_added_lines_count_not_deleted(self, tmp_path, monkeypatch):
        """AC-1: 1:1-Umbenennung (1 added / 1 deleted) zaehlt 1, nicht 2."""
        cfg = {"max_loc_delta": 1, "loc_exclude_patterns": [],
               "max_test_loc_delta": 500}
        result = _run_split_loc_check(
            tmp_path, monkeypatch, "1\t1\tsrc/foo.py\n", cfg)
        # Alte Logik: 1 + 1 = 2 > 1 → Block. Neue Logik: added=1, nicht > 1.
        assert result is None, f"1:1-Rename darf nicht blocken, war: {result}"

        # Gegenprobe: bei Blockade wird nur `added` als Produktiv-Total gemeldet.
        cfg_block = {"max_loc_delta": 5, "loc_exclude_patterns": [],
                     "max_test_loc_delta": 500}
        blocked = _run_split_loc_check(
            tmp_path, monkeypatch, "10\t90\tsrc/foo.py\n", cfg_block)
        assert blocked is not None
        assert "Produktiv 10/5" in blocked, blocked
        assert "100" not in blocked, f"deleted darf nicht mitzaehlen: {blocked}"

    def test_ac2_test_files_go_into_test_bucket(self, tmp_path, monkeypatch):
        """AC-2: Testpfade zaehlen gegen max_test_loc_delta, nicht max_loc_delta."""
        cfg = {"max_loc_delta": 250, "loc_exclude_patterns": [],
               "max_test_loc_delta": 500}

        # tests/test_foo.py: 300 added → Test-Bucket (300 <= 500), Prod bleibt 0
        result = _run_split_loc_check(
            tmp_path, monkeypatch, "300\t0\ttests/test_foo.py\n", cfg)
        assert result is None, f"tests/test_foo.py gehoert in den Test-Bucket: {result}"

        # src/bar.test.ts ebenfalls Test-Bucket
        result_ts = _run_split_loc_check(
            tmp_path, monkeypatch, "300\t0\tsrc/bar.test.ts\n", cfg)
        assert result_ts is None, f"src/bar.test.ts gehoert in den Test-Bucket: {result_ts}"

        # Gegenprobe: gegen das Test-Limit wird sehr wohl geprueft
        cfg_small_test = {"max_loc_delta": 250, "loc_exclude_patterns": [],
                          "max_test_loc_delta": 100}
        blocked = _run_split_loc_check(
            tmp_path, monkeypatch, "300\t0\ttests/test_foo.py\n", cfg_small_test)
        assert blocked is not None
        assert "Produktiv 0/250" in blocked, blocked
        assert "Tests 300/100" in blocked, blocked

    def test_ac3_regression_issue94_session_not_blocked(self, tmp_path, monkeypatch):
        """AC-3: prod=98/250 + test=286/500 (Default) darf NICHT blocken.

        Regressionstest fuer die Beleg-Session aus Issue #94: die alte
        Summenlogik haette mit 98+286=384 > 250 geblockt.
        """
        # max_test_loc_delta und test_path_patterns bewusst NICHT gesetzt
        # → eingebaute Defaults (500 bzw. Standard-Testpfade) muessen greifen.
        cfg = {"max_loc_delta": 250, "loc_exclude_patterns": []}
        numstat = (
            "60\t20\tcore/hooks/edit_gate.py\n"
            "38\t10\tcore/hooks/config_loader.py\n"
            "286\t14\ttests/test_gate_coverage.py\n"
        )
        result = _run_split_loc_check(tmp_path, monkeypatch, numstat, cfg)
        assert result is None, (
            "prod=98/250, test=286/500 darf nicht blockieren (Issue #94), "
            f"war: {result}"
        )

    def test_ac4_block_message_lists_both_buckets(self, tmp_path, monkeypatch):
        """AC-4: Meldung enthaelt immer 'Produktiv {p}/{max}, Tests {t}/{max}'."""
        cfg = {"max_loc_delta": 50, "loc_exclude_patterns": [],
               "max_test_loc_delta": 100}

        # a) beide Buckets ueber Limit
        both = _run_split_loc_check(
            tmp_path, monkeypatch,
            "80\t0\tsrc/foo.py\n120\t0\ttests/test_foo.py\n", cfg)
        assert both is not None
        assert "Produktiv 80/50, Tests 120/100" in both, both

        # b) nur Produktiv ueber Limit → Test-Werte trotzdem in der Meldung
        prod_only = _run_split_loc_check(
            tmp_path, monkeypatch,
            "80\t0\tsrc/foo.py\n10\t0\ttests/test_foo.py\n", cfg)
        assert prod_only is not None
        assert "Produktiv 80/50, Tests 10/100" in prod_only, prod_only

        # c) nur Tests ueber Limit → Produktiv-Werte trotzdem in der Meldung
        test_only = _run_split_loc_check(
            tmp_path, monkeypatch,
            "10\t0\tsrc/foo.py\n120\t0\ttests/test_foo.py\n", cfg)
        assert test_only is not None
        assert "Produktiv 10/50, Tests 120/100" in test_only, test_only

    def test_ac5_test_loc_limit_override_raises_only_test_bucket(self, tmp_path, monkeypatch):
        """AC-5: test_loc_limit_override hebt nur den Test-Schwellwert an."""
        cfg = {"max_loc_delta": 250, "loc_exclude_patterns": [],
               "max_test_loc_delta": 500}

        # a) Test-Override 900 → 700 Test-Zeilen kommen durch, Prod bleibt unter Limit
        allowed = _run_split_loc_check(
            tmp_path, monkeypatch,
            "700\t0\ttests/test_a.py\n200\t0\tsrc/foo.py\n",
            cfg, workflow_extra={"test_loc_limit_override": "900"})
        assert allowed is None, f"Test-Override 900 muss 700 Test-Zeilen erlauben: {allowed}"

        # b) Produktiv-Limit bleibt vom Test-Override unberuehrt
        blocked = _run_split_loc_check(
            tmp_path, monkeypatch,
            "700\t0\ttests/test_a.py\n300\t0\tsrc/foo.py\n",
            cfg, workflow_extra={"test_loc_limit_override": "900"})
        assert blocked is not None, "Prod 300 > 250 muss trotz Test-Override blocken"
        assert "Produktiv 300/250, Tests 700/900" in blocked, blocked


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

    def test_ac6_test_loc_defaults_without_config(self, tmp_path, monkeypatch):
        """AC-6: get_scope_test_loc_config() liefert Defaults ohne Projekt-Config."""
        import re as _re
        import config_loader

        def _matches(patterns, path):
            return any(_re.search(p, path) for p in patterns)

        # a) Gar keine Config
        monkeypatch.setattr(config_loader, "load_config", lambda: {})
        max_test_loc, test_patterns = config_loader.get_scope_test_loc_config()
        assert max_test_loc == 500
        assert test_patterns, "Default-Testpfad-Patterns duerfen nicht leer sein"

        # b) Bestehende Config mit scope_guard, aber ohne die neuen Keys
        #    (z.B. gregor_zwanzig-Stand) → ebenfalls Defaults
        monkeypatch.setattr(config_loader, "load_config", lambda: {
            "scope_guard": {"max_loc_delta": 250, "loc_exclude_patterns": [r"\.po$"]}
        })
        max_test_loc2, test_patterns2 = config_loader.get_scope_test_loc_config()
        assert max_test_loc2 == 500
        assert test_patterns2 == test_patterns

        # Default-Patterns erkennen uebliche Testpfade ...
        for path in ("tests/test_foo.py", "pkg/foo_test.py",
                     "app/__tests__/foo.js", "src/bar.test.ts", "src/bar.spec.ts"):
            assert _matches(test_patterns, path), f"{path} sollte als Testpfad gelten"

        # ... und lassen Produktivcode in Ruhe
        for path in ("src/foo.py", "core/hooks/edit_gate.py", "src/latest.ts"):
            assert not _matches(test_patterns, path), f"{path} ist kein Testpfad"


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
