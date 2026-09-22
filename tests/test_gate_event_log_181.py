"""Gate-Event-Log (Issue #181) — Epic #199, erster und blockierender Posten.

## Problem

Blockaden waren nur im Transcript sichtbar. Keine Kennzahl, kein Weg von
einem Fehlalarm zum Regressionstest. Laut /insights-Report vom 21.09.2026
(241 Sessions, 15.482 Bash-Aufrufe): "Eigene Guardrails sind die groesste
Reibungsquelle."

## Umfang dieser Datei

`log_gate_event()` in `hook_utils.py` ist der Kern: eine JSON-Zeile pro
Blockade, nie eine Ausnahme, keine Rotation, keine Auswertung — das Log
beobachtet, es entscheidet nichts (siehe Kommentar in hook_utils.py).

`hook_utils.block()` ruft sie automatisch auf und deckt damit `bash_gate.py`,
`edit_gate.py`, `post_implementation_gate.py` und `tdd_enforcement.py` ohne
jede Aenderung an diesen vier Dateien ab. Fuenf weitere Hooks blockieren mit
rohem `sys.exit(2)` statt ueber `block()` und wurden einzeln um einen
Log-Aufruf ergaenzt: `claude_md_protection.py`, `secret_egress_guard.py`
(bewusst OHNE Inhalt — siehe unten), `secrets_guard.py` (4 Stellen),
`session_singleton_guard.py`, `worktree_write_guard.py`. Das sind alle
Stellen in `core/hooks/*.py`, die `sys.exit(2)` aufrufen (nachgezaehlt) —
AC-1 aus dem Issue ("jeder blockierende Hook") ist damit vollstaendig
gedeckt, nicht nur die vier "Kern-Gates" im architektonischen Sinn.

## Was NICHT in dieser Datei ist

`/91-gate-audit` (Auswertung/Clustering) — bewusst zurueckgestellt, bis
Daten vorliegen. Kein Weg vom Log zurueck in ein Gate.
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

import hook_utils  # noqa: E402


def _events(project_root: Path) -> list:
    path = project_root / ".claude" / "gate-events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _run(hook: str, tmp_path: Path, payload: dict, extra_env: "dict | None" = None
         ) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
    env.pop("OPENSPEC_ENV", None)
    env.pop("CLAUDE_TOOL_INPUT", None)
    env.pop("CLAUDE_TOOL_NAME", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / hook)],
        input=json.dumps(payload), capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )


class TestMaskAndTruncateExcerpt:
    """Reine Funktionstests, keine Subprozesse noetig."""

    def test_plain_text_passes_through(self):
        assert hook_utils.mask_and_truncate_excerpt("cat .env") == "cat .env"

    def test_empty_and_none_become_empty_string(self):
        assert hook_utils.mask_and_truncate_excerpt("") == ""
        assert hook_utils.mask_and_truncate_excerpt(None) == ""

    def test_truncates_long_text(self):
        long_text = "x" * 500
        result = hook_utils.mask_and_truncate_excerpt(long_text)
        assert len(result) <= hook_utils._EXCERPT_LIMIT + 1  # +1 fuer das Ellipsis-Zeichen
        assert result.endswith("…")

    @pytest.mark.parametrize("keyword", ["API_KEY", "api_key", "TOKEN", "password", "PASSWD"])
    def test_masks_known_secret_keyword_assignments(self, keyword):
        text = f"export {keyword}=sk-dummy-super-secret-1234567890"
        result = hook_utils.mask_and_truncate_excerpt(text)
        assert "sk-dummy-super-secret-1234567890" not in result
        assert "***" in result

    def test_masks_authorization_bearer_including_the_token_itself(self):
        """Der Fall, der eine reine 'naechstes Wort maskieren'-Strategie
        durchlassen wuerde: 'Bearer' UND das Token dahinter muessen weg."""
        text = 'curl -H "Authorization: Bearer sk-dummy-abcdefghijklmnop"'
        result = hook_utils.mask_and_truncate_excerpt(text)
        assert "sk-dummy-abcdefghijklmnop" not in result
        assert "Bearer" not in result or "***" in result

    def test_filename_with_key_substring_not_over_masked(self):
        """Gegenprobe zur eigenen Vorsicht: ein Dateiname wie 'keyword_guard'
        darf nicht als Geheimnis behandelt werden — sonst zerstoert die
        Maskierung genau die Diagnoseinformation, die #89/#145 brauchten."""
        text = "tests/test_phase_listener_keyword_guard.py"
        result = hook_utils.mask_and_truncate_excerpt(text)
        assert result == text


class TestLogGateEvent:
    def test_writes_one_jsonl_line_with_expected_fields(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        hook_utils.log_gate_event("bash_gate", "Bash", "Testgrund\nzweite Zeile", "echo hi")

        events = _events(tmp_path)
        assert len(events) == 1
        e = events[0]
        assert e["hook"] == "bash_gate"
        assert e["tool"] == "Bash"
        assert e["reason"] == "Testgrund"  # nur die erste Zeile
        assert e["command_excerpt"] == "echo hi"
        assert "ts" in e and e["ts"]
        assert "session_id" in e

    def test_appends_rather_than_overwrites(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        hook_utils.log_gate_event("hook_a", "Bash", "erster", "")
        hook_utils.log_gate_event("hook_b", "Read", "zweiter", "")
        events = _events(tmp_path)
        assert [e["hook"] for e in events] == ["hook_a", "hook_b"]

    def test_never_raises_when_claude_dir_path_is_blocked_by_a_file(self, tmp_path, monkeypatch):
        """Sicherheitsinvariante: ein Logging-Fehler darf ein Gate nie zum
        Absturz bringen. `chmod` allein beweist das nicht — diese Sitzung
        laeuft als root, das umgeht Dateirechte. Stattdessen: `.claude` ist
        hier bereits eine gewoehnliche DATEI, nicht ein Verzeichnis — `mkdir`
        schlaegt daran unabhaengig von Rechten fehl, auch fuer root."""
        blocked = tmp_path / "blocked"
        blocked.mkdir()
        (blocked / ".claude").write_text("ich bin eine Datei, kein Verzeichnis")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(blocked))
        hook_utils.log_gate_event("hook_a", "Bash", "grund", "cmd")  # darf nicht werfen

    def test_session_id_included_when_env_set(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-abc123")
        hook_utils.log_gate_event("hook_a", "Bash", "grund", "")
        assert _events(tmp_path)[0]["session_id"] == "sess-abc123"

    def test_secret_in_command_excerpt_is_masked_end_to_end(self, tmp_path, monkeypatch):
        """AC-2 aus dem Issue: 'Die Events enthalten keine Secrets (Test mit
        Dummy-Secret)' — end-to-end durch log_gate_event, nicht nur die
        Maskierungsfunktion isoliert."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        dummy_secret = "sk-dummy-do-not-leak-9876543210"
        hook_utils.log_gate_event("bash_gate", "Bash", "grund",
                                  f"curl -H API_KEY={dummy_secret}")
        raw_file_content = (tmp_path / ".claude" / "gate-events.jsonl").read_text()
        assert dummy_secret not in raw_file_content


class TestBlockAutoLogs:
    """block() muss automatisch loggen, ohne dass bestehende Aufrufer sich
    aendern — Kompatibilitaet mit den vier Kern-Gates, die block(message)
    bereits mit genau einem Argument aufrufen."""

    def test_block_with_only_message_still_logs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_TOOL_NAME", "Edit")
        monkeypatch.setenv("CLAUDE_TOOL_INPUT", json.dumps({"file_path": "core/hooks/x.py"}))
        with pytest.raises(SystemExit) as exc_info:
            hook_utils.block("BLOCKED: irgendein Grund")
        assert exc_info.value.code == 2

        events = _events(tmp_path)
        assert len(events) == 1
        assert events[0]["tool"] == "Edit"
        assert events[0]["command_excerpt"] == "core/hooks/x.py"

    def test_block_still_exits_2_even_if_logging_is_broken(self, tmp_path, monkeypatch):
        """Die Sicherheitsinvariante direkt an block() geprueft: ein
        kaputter Logger darf den Exit-Code nicht veraendern."""
        monkeypatch.setattr(hook_utils, "log_gate_event",
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        with pytest.raises(SystemExit) as exc_info:
            hook_utils.block("BLOCKED: x")
        assert exc_info.value.code == 2

    def test_explicit_hook_tool_excerpt_override_env_derivation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        with pytest.raises(SystemExit):
            hook_utils.block("BLOCKED: x", hook="custom_hook", tool="Write",
                            command_excerpt="explicit.txt")
        e = _events(tmp_path)[0]
        assert e["hook"] == "custom_hook"
        assert e["tool"] == "Write"
        assert e["command_excerpt"] == "explicit.txt"


class TestAllBlockingHooksLogAnEvent:
    """AC-1: jeder blockierende Hook aus hooks.json schreibt ein Event.

    Ein Fall pro Datei mit rohem sys.exit(2) (5 Dateien) plus ein Fall pro
    Kern-Gate, das ueber block() laeuft (stellvertretend bash_gate + edit_gate
    — post_implementation_gate/tdd_enforcement teilen sich denselben
    Mechanismus und sind in ihren eigenen Testdateien ausfuehrlich getestet).
    """

    def test_claude_md_protection_logs(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "claude_md:\n"
            "  forbidden_patterns:\n"
            "    - pattern: 'VERBOTEN'\n"
            "      message: 'Testverbot'\n"
        )
        payload = {"tool_input": {"file_path": "CLAUDE.md", "content": "Hier steht VERBOTEN drin"}}
        res = self._run(tmp_path, "claude_md_protection.py", payload)
        assert res.returncode == 2
        events = _events(tmp_path)
        assert any(e["hook"] == "claude_md_protection" for e in events)

    def test_worktree_write_guard_logs(self, tmp_path):
        main_repo = tmp_path / "main"
        wt = main_repo / ".claude" / "worktrees" / "feature-x"
        wt.mkdir(parents=True)
        (main_repo / ".claude").mkdir(exist_ok=True)
        payload = {
            "cwd": str(wt),
            "tool_input": {"file_path": str(main_repo / "README.md")},
        }
        res = self._run(main_repo, "worktree_write_guard.py", payload)
        assert res.returncode == 2
        events = _events(main_repo)
        assert any(e["hook"] == "worktree_write_guard" for e in events)

    def test_secrets_guard_read_always_blocked_logs(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        payload = {"tool_name": "Read", "tool_input": {"file_path": ".env"}}
        res = self._run(tmp_path, "secrets_guard.py", payload)
        assert res.returncode == 2
        events = _events(tmp_path)
        assert any(e["hook"] == "secrets_guard" for e in events)

    def test_secret_egress_guard_logs_without_leaking_value(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".env").write_text("MY_DUMMY_SECRET=leak-me-not-123456\n")
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo leak-me-not-123456"},
        }
        res = self._run(tmp_path, "secret_egress_guard.py", payload)
        assert res.returncode == 2, res.stdout + res.stderr
        events = _events(tmp_path)
        assert any(e["hook"] == "secret_egress_guard" for e in events)
        raw = (tmp_path / ".claude" / "gate-events.jsonl").read_text()
        assert "leak-me-not-123456" not in raw

    def _run(self, project_root: Path, hook: str, payload: dict) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(project_root)
        env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
        env.pop("OPENSPEC_ENV", None)
        env.pop("CLAUDE_TOOL_INPUT", None)
        env.pop("CLAUDE_TOOL_NAME", None)
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / hook)],
            input=json.dumps(payload), capture_output=True, text=True,
            env=env, cwd=str(project_root),
        )


class TestGitignoreCoversTheLogFile:
    def test_repo_gitignore_has_the_entry(self):
        text = (REPO_ROOT / ".gitignore").read_text()
        assert ".claude/gate-events.jsonl" in text

    def test_setup_py_installs_the_entry(self):
        sys.path.insert(0, str(REPO_ROOT))
        import setup as setup_py
        assert ".claude/gate-events.jsonl" in setup_py.GITIGNORE_RUNTIME_ENTRIES
