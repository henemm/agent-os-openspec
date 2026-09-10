"""Tests fuer #132 — globaler Projekt-Schalter `framework: {enabled: false}`.

Warum es diesen Schalter gibt: das Framework liess sich pro Projekt nur ueber
Claude Codes `enabledPlugins: false` in `.claude/settings.local.json`
abschalten. Diese Datei wird pro VERZEICHNIS gelesen und ist untracked, also
erbt ein git-Worktree sie nicht — in `kotoba_line` feuerten deshalb in jeder
Worktree-Sitzung alle Gates wieder, obwohl das Haupt-Checkout sie aus hat.

Die Projekt-Konfiguration des Frameworks kann das, was jene Datei nicht kann:
`find_project_root()` loest einen Worktree auf das Hauptrepo auf. AC-2 ist
deshalb der eigentliche Punkt dieses Issues und nicht ein Randfall.

Alle Tests hermetisch: Fake-Projekt im tmp_path, Subprozess mit
CLAUDE_PROJECT_DIR (Muster aus test_edit_gate_orchestrator_files.py).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"

SWITCH_OFF = "framework:\n  enabled: false\n"
SWITCH_ON = "framework:\n  enabled: true\n"


# --- Helpers ---------------------------------------------------------------

def _make_project(tmp_path: Path, config: str | None = None, config_name="openspec.yaml") -> Path:
    """Fake-Projekt mit echtem .git-VERZEICHNIS (kein Worktree)."""
    proj = tmp_path / "project"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude").mkdir(parents=True)
    if config is not None:
        (proj / config_name).write_text(config)
    return proj


def _make_worktree(tmp_path: Path, config: str | None = None) -> tuple[Path, Path]:
    """Hauptrepo + verlinkter Worktree, so wie git sie anlegt.

    Der Worktree traegt eine .git-DATEI mit `gitdir:` — genau daran erkennt
    find_main_repo_from_worktree() ihn.
    """
    main = tmp_path / "main"
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    (main / ".claude").mkdir(parents=True)
    if config is not None:
        (main / "openspec.yaml").write_text(config)

    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'wt'}\n")
    # Wie im Fundprojekt: der Worktree hat eine LEERE lokale Konfiguration.
    (wt / ".claude").mkdir()
    (wt / ".claude" / "settings.local.json").write_text("{}")
    return main, wt


def _run(hook: str, payload: dict, cwd: Path, env: dict | None = None):
    full_env = dict(os.environ)
    full_env["CLAUDE_PROJECT_DIR"] = str(cwd)
    # Aus der Umgebung des Testlaeufers darf nichts durchschlagen.
    full_env.pop("OPENSPEC_ACTIVE_WORKFLOW", None)
    full_env.pop("OPENSPEC_FRAMEWORK", None)
    full_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / hook)],
        input=json.dumps(payload), capture_output=True, text=True,
        env=full_env, cwd=str(cwd),
    )


def _edit(proj: Path, env=None, file_name="src/thing.py"):
    return _run("edit_gate.py", {"tool_input": {"file_path": str(proj / file_name)}}, proj, env)


def _bash(proj: Path, command: str, env=None):
    return _run("bash_gate.py", {"tool_input": {"command": command}}, proj, env)


# --- AC-4: der Standard bleibt "an" ---------------------------------------

def test_without_the_key_a_code_file_is_still_blocked(tmp_path):
    """Kontrolle. Ohne den Schalter muss das Gate weiter greifen — sonst
    beweisen die Tests unten nichts."""
    proj = _make_project(tmp_path)
    res = _edit(proj)
    assert res.returncode == 2, res.stdout + res.stderr
    assert "No active workflow" in (res.stdout + res.stderr)


def test_explicit_true_does_not_disable(tmp_path):
    """`enabled: true` ist kein Tippfehler-Ausweg."""
    proj = _make_project(tmp_path, SWITCH_ON)
    res = _edit(proj)
    assert res.returncode == 2, res.stdout + res.stderr


@pytest.mark.parametrize("config", [
    "framework: {}\n",
    "framework:\n  something_else: false\n",
    "other_section:\n  enabled: false\n",
])
def test_unrelated_config_does_not_disable(tmp_path, config):
    """Nur ein ausdrueckliches `framework.enabled: false` schaltet ab. Ein
    Projekt darf seinen Schutz nicht durch eine unbeteiligte Zeile verlieren."""
    proj = _make_project(tmp_path, config)
    res = _edit(proj)
    assert res.returncode == 2, res.stdout + res.stderr


# --- AC-1: der Schalter laesst edit_gate durch ----------------------------

def test_switch_lets_a_code_file_through_without_a_workflow(tmp_path):
    proj = _make_project(tmp_path, SWITCH_OFF)
    res = _edit(proj)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "No active workflow" not in (res.stdout + res.stderr)


@pytest.mark.parametrize("name", ["openspec.yaml", "config.yaml", ".openspec.yaml"])
def test_every_documented_config_name_works(tmp_path, name):
    proj = _make_project(tmp_path, SWITCH_OFF, config_name=name)
    assert _edit(proj).returncode == 0


def test_switch_also_works_under_dot_claude(tmp_path):
    """`.claude/openspec.yaml` ist der Ort, an dem ein Projekt Werkzeug-Konfiguration
    unterbringt, ohne sein Wurzelverzeichnis zu moeblieren."""
    proj = _make_project(tmp_path)
    (proj / ".claude" / "openspec.yaml").write_text(SWITCH_OFF)
    assert _edit(proj).returncode == 0


# --- AC-2: und zwar auch aus einem Worktree -------------------------------

def test_worktree_inherits_the_switch_from_the_main_repo(tmp_path):
    """Der eigentliche Punkt von #132.

    Die Konfiguration liegt im Hauptrepo, gearbeitet wird im Worktree, dessen
    eigene settings.local.json leer ist. Genau hier versagt der bisherige
    Schalter.
    """
    _main, wt = _make_worktree(tmp_path, SWITCH_OFF)
    res = _run("edit_gate.py", {"tool_input": {"file_path": str(wt / "src/thing.py")}}, wt)
    assert res.returncode == 0, res.stdout + res.stderr


def test_worktree_without_the_switch_is_still_blocked(tmp_path):
    """Kontrolle zum Test darueber — der heutige Zustand, schriftlich."""
    _main, wt = _make_worktree(tmp_path, None)
    res = _run("edit_gate.py", {"tool_input": {"file_path": str(wt / "src/thing.py")}}, wt)
    assert res.returncode == 2, res.stdout + res.stderr


# --- AC-5: Umgebungsvariable fuer den Einzelfall --------------------------

@pytest.mark.parametrize("value", ["off", "0", "false", "no", "disabled", "OFF"])
def test_env_var_disables_without_touching_the_repo(tmp_path, value):
    proj = _make_project(tmp_path)
    res = _edit(proj, env={"OPENSPEC_FRAMEWORK": value})
    assert res.returncode == 0, res.stdout + res.stderr


@pytest.mark.parametrize("value", ["on", "1", "true", ""])
def test_env_var_with_any_other_value_changes_nothing(tmp_path, value):
    proj = _make_project(tmp_path)
    res = _edit(proj, env={"OPENSPEC_FRAMEWORK": value})
    assert res.returncode == 2, res.stdout + res.stderr


# --- AC-3: die Schutz-Guards bleiben an -----------------------------------

def test_secrets_are_still_guarded_with_the_switch_off(tmp_path):
    """Der Schalter nimmt die Ceremony raus, nicht den Secret-Schutz. Ein
    Schalter, der beides mitnimmt, entfernt still Schutz, den niemand
    abwaehlen wollte."""
    proj = _make_project(tmp_path, SWITCH_OFF)
    res = _bash(proj, "cat .env")
    assert res.returncode == 2, res.stdout + res.stderr
    assert "Secrets guard" in (res.stdout + res.stderr)


def test_an_ordinary_command_still_passes_with_the_switch_off(tmp_path):
    proj = _make_project(tmp_path, SWITCH_OFF)
    assert _bash(proj, "ls -la").returncode == 0


def test_stop_lock_is_lifted_by_the_switch(tmp_path):
    """Das Stop-Lock ist Workflow-Zwang, kein Schutz: es gehoert zu dem Teil,
    den der Schalter abschaltet. Ohne das bliebe ein Projekt mit gesetztem
    Lock dauerhaft blockiert, ohne Workflow, der es je wieder aufhebt."""
    proj = _make_project(tmp_path, SWITCH_OFF)
    (proj / ".claude" / "stop_lock.json").write_text(json.dumps({"enabled": True}))
    assert _bash(proj, "ls").returncode == 0
    assert _edit(proj).returncode == 0


# --- die uebrigen Ceremony-Gates ------------------------------------------

@pytest.mark.parametrize("hook", [
    "tdd_enforcement.py",
    "post_implementation_gate.py",
])
def test_the_other_edit_ceremony_gates_honour_the_switch(tmp_path, hook):
    proj = _make_project(tmp_path, SWITCH_OFF)
    res = _run(hook, {"tool_input": {"file_path": str(proj / "src/thing.py")}}, proj)
    assert res.returncode == 0, res.stdout + res.stderr


def test_phase_listener_honours_the_switch(tmp_path):
    """Kein Phasen-Zustand heisst auch: kein Zuhoeren auf Freigabe-Woerter.
    Sonst setzt ein beilaeufiges "go" in einem Projekt ohne Workflow Zustand,
    den niemand angelegt hat."""
    proj = _make_project(tmp_path, SWITCH_OFF)
    res = _run("phase_listener.py", {"prompt": "approved"}, proj)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "approv" not in (res.stdout + res.stderr).lower()
