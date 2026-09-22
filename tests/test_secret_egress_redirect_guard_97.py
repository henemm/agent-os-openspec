"""Tests fuer den Redirect-Guard in secret_egress_guard.py (Issue #97).

Zweiter, unabhaengiger Check im selben Hook: `find_leaks()` (bestehend) prueft
literale Secret-WERTE im Tool-Input. Dieser Check prueft SCHREIBZIELE von
Bash-Redirects (`>`, `>>`, `tee`) gegen eine Sicherheitszone (Projekt +
konfigurierte Ausnahmen) -- unabhaengig davon, ob ein bekannter Secret-Wert
im Kommando steht. Der gemessene Vorfall aus #97: ein fehlschlagender Test
druckt einen Konfigurationswert in seine Ausgabe, die Ausgabe wird per
Shell-Redirect in eine Datei ausserhalb jedes geschuetzten Ordners geschrieben
-- der Wert selbst steht nie im Tool-Input, das Ziel der Umleitung aber schon.

Spec: docs/specs/feat-97-secret-egress-redirect-guard.md
Stilvorlage: tests/test_egress_guard.py (Subprozess, kein Mock).
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
HOOK = HOOKS_DIR / "secret_egress_guard.py"
CONFIG_YAML = REPO_ROOT / "config.yaml"

FAKE_PASS = "Kq7-fiktiv-passwort-9xZ"
ENV_CONTENT = f"GZ_SMTP_PASS={FAKE_PASS}\n"


def _make_project(tmp_path: Path, config_yaml: "str | None" = None) -> None:
    (tmp_path / ".git").mkdir(exist_ok=True)
    if config_yaml is not None:
        (tmp_path / "config.yaml").write_text(config_yaml)


def _write_override_token(tmp_path: Path) -> None:
    token_dir = tmp_path / ".claude"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "user_override_token.json").write_text(json.dumps({
        "version": 2,
        "tokens": {"__test__": {"created": datetime.now().isoformat(), "granted_by": "test"}},
    }))


def _run(tmp_path: Path, tool_name: str, tool_input: dict) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env.pop("CLAUDE_TOOL_INPUT", None)
    env.pop("CLAUDE_TOOL_NAME", None)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload, capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )


# AC-1: der im Issue gemessene Vorfall
def test_measured_incident_pytest_redirect_to_tmp_is_blocked(tmp_path):
    _make_project(tmp_path)
    r = _run(tmp_path, "Bash", {"command": "uv run pytest > /tmp/pytest_full.log"})
    assert r.returncode == 2, r.stdout + r.stderr
    assert "/tmp/pytest_full.log" in r.stderr


# AC-2: Ziel INNERHALB des Projekts ist erlaubt
def test_redirect_inside_project_is_allowed(tmp_path):
    _make_project(tmp_path)
    r = _run(tmp_path, "Bash", {"command": "echo hello > output.log"})
    assert r.returncode == 0, r.stdout + r.stderr


# AC-3: konfigurierte Ausnahme erlaubt das Ziel
def test_redirect_matching_extra_allowed_dir_is_allowed(tmp_path):
    _make_project(tmp_path, config_yaml=(
        "secret_egress_guard:\n"
        "  extra_allowed_write_dirs:\n"
        '    - "^/tmp/"\n'
    ))
    r = _run(tmp_path, "Bash", {"command": "uv run pytest > /tmp/pytest_full.log"})
    assert r.returncode == 0, r.stdout + r.stderr


# AC-4: tee auf ein Ziel ausserhalb der Zone
def test_tee_redirect_outside_project_is_blocked(tmp_path):
    _make_project(tmp_path)
    r = _run(tmp_path, "Bash", {"command": "uv run pytest | tee /tmp/x.log"})
    assert r.returncode == 2, r.stdout + r.stderr
    assert "/tmp/x.log" in r.stderr


def test_tee_append_flag_is_skipped_to_find_target(tmp_path):
    """tee -a /tmp/x.log -- das Flag ist kein Ziel-Token."""
    _make_project(tmp_path)
    r = _run(tmp_path, "Bash", {"command": "uv run pytest | tee -a /tmp/x.log"})
    assert r.returncode == 2, r.stdout + r.stderr
    assert "/tmp/x.log" in r.stderr


# AC-5: gueltiger Override-Token hebt NUR den neuen Check auf
def test_valid_override_token_allows_redirect_outside_zone(tmp_path):
    _make_project(tmp_path)
    _write_override_token(tmp_path)
    r = _run(tmp_path, "Bash", {"command": "uv run pytest > /tmp/pytest_full.log"})
    assert r.returncode == 0, r.stdout + r.stderr


# AC-6: Literal-Wert-Treffer hat Vorrang vor dem Redirect-Check
def test_literal_secret_hit_takes_precedence_over_redirect_check(tmp_path):
    _make_project(tmp_path)
    (tmp_path / ".env").write_text(ENV_CONTENT)
    r = _run(tmp_path, "Bash", {"command": f'echo "{FAKE_PASS}" > /tmp/leak.txt'})
    assert r.returncode == 2, r.stdout + r.stderr
    assert "GZ_SMTP_PASS" in r.stderr, "Literal-Wert-Meldung muss feuern, nicht die Redirect-Meldung"
    assert FAKE_PASS not in r.stderr


# AC-7: Nicht-Bash-Tools sind vom Redirect-Check ausgenommen
def test_non_bash_tool_is_not_checked_by_redirect_guard(tmp_path):
    _make_project(tmp_path)
    r = _run(tmp_path, "Write", {"file_path": "/tmp/notes.md", "content": "# harmlos\n"})
    assert r.returncode == 0, r.stdout + r.stderr


def test_write_content_that_looks_like_a_redirect_is_not_flagged(tmp_path):
    """AC-7, scharf gestellt: der Check liest NUR das command-Feld eines
    Bash-Aufrufs, kein rekursiver String-Scan wie bei find_leaks(). Eine
    Doku-Datei, die zufaellig '> /tmp/x.log' als Text enthaelt, ist kein
    Shell-Kommando und darf nicht als Redirect gewertet werden."""
    _make_project(tmp_path)
    r = _run(tmp_path, "Write", {
        "file_path": "/tmp/notes.md",
        "content": "Beispiel: `uv run pytest > /tmp/x.log`\n",
    })
    assert r.returncode == 0, r.stdout + r.stderr


# AC-8: eigener Kill-Switch, unabhaengig vom Gesamt-Guard
def test_redirect_guard_disabled_still_checks_literal_leaks(tmp_path):
    _make_project(tmp_path, config_yaml=(
        "secret_egress_guard:\n"
        "  redirect_guard_enabled: false\n"
    ))
    (tmp_path / ".env").write_text(ENV_CONTENT)

    # Redirect ausserhalb der Zone: mit abgeschaltetem Check erlaubt.
    r1 = _run(tmp_path, "Bash", {"command": "uv run pytest > /tmp/pytest_full.log"})
    assert r1.returncode == 0, r1.stdout + r1.stderr

    # Literal-Wert-Pruefung bleibt unabhaengig davon aktiv.
    r2 = _run(tmp_path, "Bash", {"command": f'echo "{FAKE_PASS}"'})
    assert r2.returncode == 2, r2.stdout + r2.stderr


# AC-9: FD-Duplizierung und /dev/null sind keine Ziele
@pytest.mark.parametrize("cmd", [
    "make build 2>&1",
    "make build > /dev/null",
    "make build 2>/dev/null",
])
def test_fd_duplication_and_devnull_are_not_flagged_as_targets(tmp_path, cmd):
    _make_project(tmp_path)
    r = _run(tmp_path, "Bash", {"command": cmd})
    assert r.returncode == 0, r.stdout + r.stderr


# AC-10: ein '>' innerhalb von quoted Freitext ist kein echter Redirect
def test_arrow_inside_quoted_text_is_not_flagged(tmp_path):
    _make_project(tmp_path)
    r = _run(tmp_path, "Bash", {
        "command": 'gh pr create --title "x" --body "... a > b arrow in text ..."',
    })
    assert r.returncode == 0, r.stdout + r.stderr


# --------------------------------------------------------------------------
# Unit-Tests gegen die neuen Funktionen direkt (Randfaelle)
# --------------------------------------------------------------------------

sys.path.insert(0, str(HOOKS_DIR))
import secret_egress_guard as seg  # noqa: E402


class TestConfigYamlMatchesCodeDefaults:
    """Dieselbe Drift-Klasse wie #145/#146: config.yaml gewinnt zur Laufzeit
    gegen den Code-Default -- beide muessen identisch sein."""

    def _section(self) -> dict:
        return yaml.safe_load(CONFIG_YAML.read_text())["secret_egress_guard"]

    def test_redirect_guard_enabled_matches_code_default(self):
        assert self._section()["redirect_guard_enabled"] is True

    def test_extra_allowed_write_dirs_matches_code_default(self):
        assert self._section()["extra_allowed_write_dirs"] == []


class TestShellWriteTargetsUnit:
    def test_simple_redirect(self):
        assert seg._shell_write_targets("echo hi > /tmp/x.log") == ["/tmp/x.log"]

    def test_append_redirect(self):
        assert seg._shell_write_targets("echo hi >> /tmp/x.log") == ["/tmp/x.log"]

    def test_no_redirect_returns_empty(self):
        assert seg._shell_write_targets("echo hello world") == []

    def test_devnull_is_excluded(self):
        assert seg._shell_write_targets("echo hi > /dev/null") == []

    def test_fd_duplication_is_excluded(self):
        assert seg._shell_write_targets("echo hi 2>&1") == []

    def test_tee_target_extracted(self):
        assert seg._shell_write_targets("echo hi | tee /tmp/out.log") == ["/tmp/out.log"]

    def test_tee_append_flag_skipped(self):
        assert seg._shell_write_targets("echo hi | tee -a /tmp/out.log") == ["/tmp/out.log"]

    def test_quoted_arrow_is_not_a_redirect(self):
        assert seg._shell_write_targets('echo "a > b"') == []

    def test_nested_shell_falls_back_to_raw_scan(self):
        """sh -c: konservativer Roh-Scan greift weiterhin (Sicherheitsnetz).

        Der Roh-Scan versteht keine Quotes (identisch zu bash_gate.py's
        _raw_redirect()) -- das Ziel kann ein angehaengtes Anfuehrungszeichen
        tragen. Das ist unschaedlich: der Pfad liegt trotzdem erkennbar unter
        /tmp und wird als ausserhalb der Zone erkannt (siehe Integrationstest
        test_measured_incident_pytest_redirect_to_tmp_is_blocked fuer den
        sauberen, nicht verschachtelten Fall)."""
        targets = seg._shell_write_targets('bash -c "echo hi > /tmp/nested.log"')
        assert len(targets) == 1
        assert targets[0].startswith("/tmp/nested.log")


class TestIsOutsideSafeZoneUnit:
    def test_path_inside_root_is_safe(self, tmp_path):
        cfg = {"extra_allowed_write_dirs": []}
        assert seg._is_outside_safe_zone(str(tmp_path / "a.log"), tmp_path, cfg) is False

    def test_path_outside_root_is_unsafe(self, tmp_path):
        cfg = {"extra_allowed_write_dirs": []}
        assert seg._is_outside_safe_zone("/tmp/definitely-outside.log", tmp_path, cfg) is True

    def test_extra_allowed_pattern_makes_it_safe(self, tmp_path):
        cfg = {"extra_allowed_write_dirs": [r"^/tmp/"]}
        assert seg._is_outside_safe_zone("/tmp/definitely-outside.log", tmp_path, cfg) is False

    def test_relative_path_resolves_against_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = {"extra_allowed_write_dirs": []}
        assert seg._is_outside_safe_zone("relative.log", tmp_path, cfg) is False
