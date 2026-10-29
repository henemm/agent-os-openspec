"""Autonomie-Modus benutzerweit einschaltbar (Issue #481) — Tests zu AC-1 bis AC-5.

Spec: docs/specs/feat-481-autonomy-global.md

Vertraege, die diese Tests festlegen (zusaetzlich zur Spec):
- Die Umgebungsvariable heisst `OPENSPEC_AUTONOMY`; alle OPENSPEC_*-Variablen
  werden vor jedem Subprozess gestrippt und je Fall explizit gesetzt.
- `HOME` zeigt fuer jeden Gate-Aufruf auf ein Testverzeichnis; die persoenlichen
  Einstellungen liegen dort unter `.claude/settings.json` bzw. `settings.local.json`.
- bash_gate liest den Befehl aus `CLAUDE_TOOL_INPUT` (Muster #410), edit_gate das
  PreToolUse-JSON von stdin (Muster #473). Override-Token: `__infra__` (Muster #473).
- AC-5 prueft zusaetzlich die Gegenprobe: mit `OPENSPEC_AUTONOMY=auto` und der
  Repo-config.yaml ergibt `autonomy_mode()` "auto" (das Template ueberstimmt den
  Benutzer-Schalter nicht).

Fehlende Funktionen erscheinen als Test-FAIL (Importe erst im Testkoerper).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
EDIT_GATE = HOOKS_DIR / "edit_gate.py"
BASH_GATE = HOOKS_DIR / "bash_gate.py"

ENV_VAR = "OPENSPEC_AUTONOMY"
OVERRIDE_HINT = "override"
NO_SECTION = "project:\n  name: x\n"

_SCRUBBED = {"CLAUDE_TOOL_INPUT", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT",
             "PYTHONPATH"}


# --- Helpers ---------------------------------------------------------------

def _env(proj: Path, home: Path, switch: "str | None" = None) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in _SCRUBBED and not k.startswith(("OPENSPEC_", "HERDR_", "GIT_"))}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(home)
    if switch is not None:
        env[ENV_VAR] = switch
    return env


def _sandbox(root: Path, config: "str | None" = None):
    """Projekt ohne Workflow (root/proj) + Home (root/home/.claude)."""
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "docs").mkdir()
    proj = proj.resolve()
    home = (root / "home").resolve()
    (home / ".claude").mkdir(parents=True)
    if config is not None:
        (proj / "openspec.yaml").write_text(config)
    return proj, home


def _autonomy_cli(proj: Path, home: Path, switch: "str | None"):
    return subprocess.run([sys.executable, str(WORKFLOW_PY), "autonomy"],
                          capture_output=True, text=True,
                          env=_env(proj, home, switch), cwd=str(proj), timeout=60)


def _token(proj: Path) -> None:
    from test_config_edit_schutz_473 import _token as token473  # noqa: PLC0415
    token473(proj)


def _edit_gate(proj: Path, home: Path, tool: str, tool_input: dict):
    payload = json.dumps({"tool_name": tool, "tool_input": tool_input})
    return subprocess.run([sys.executable, str(EDIT_GATE)], input=payload,
                          capture_output=True, text=True, env=_env(proj, home),
                          cwd=str(proj), timeout=60)


def _bash_gate(proj: Path, home: Path, command: str):
    env = _env(proj, home)
    env["CLAUDE_TOOL_INPUT"] = json.dumps({"command": command})
    return subprocess.run([sys.executable, str(BASH_GATE)], capture_output=True,
                          text=True, env=env, cwd=str(proj), timeout=60)


def _fail(ac: str, wrong: list) -> None:
    assert not wrong, f"{ac}: {len(wrong)} Abweichungen:\n" + "\n".join(wrong)


def _expect_autonomy(label, proj, home, switch, want) -> list:
    r = _autonomy_cli(proj, home, switch)
    got = r.stdout.strip().splitlines()
    if r.returncode != 0 or got != [f"AUTONOMY={want}"]:
        return [f"  {label} ({ENV_VAR}={switch!r}): rc={r.returncode}, "
                f"stdout={r.stdout.strip()!r} (soll AUTONOMY={want}), "
                f"stderr={r.stderr.strip()[:160]!r}"]
    return []


# --- AC-1 -------------------------------------------------------------------

def test_env_switch_without_project_entry(tmp_path):
    """AC-1: ohne `autonomy`-Abschnitt entscheidet OPENSPEC_AUTONOMY (getrimmt, case-insensitiv)."""
    proj, home = _sandbox(tmp_path, NO_SECTION)
    wrong = []
    for value in ("auto", " AUTO ", "Auto"):
        wrong += _expect_autonomy("kein Abschnitt", proj, home, value, "auto")
    for value in (None, "manual", "1", "true", ""):
        wrong += _expect_autonomy("kein Abschnitt", proj, home, value, "manual")
    _fail("AC-1", wrong)


# --- AC-2 -------------------------------------------------------------------

def test_project_entry_wins_over_env(tmp_path):
    """AC-2: ein Projekteintrag `autonomy.mode` hat Vorrang vor der Variable."""
    wrong = []
    p1, h1 = _sandbox(tmp_path / "manual", "autonomy:\n  mode: manual\n")
    wrong += _expect_autonomy("Projekt manual", p1, h1, "auto", "manual")
    p2, h2 = _sandbox(tmp_path / "auto", "autonomy:\n  mode: auto\n")
    wrong += _expect_autonomy("Projekt auto", p2, h2, None, "auto")
    p3, h3 = _sandbox(tmp_path / "leer", "autonomy: {}\n")
    wrong += _expect_autonomy("Projekt autonomy: {}", p3, h3, "auto", "auto")
    _fail("AC-2", wrong)


# --- AC-3 -------------------------------------------------------------------

def test_edit_gate_protects_user_settings(tmp_path):
    """AC-3: Edit/Write auf ~/.claude/settings(.local).json -> Exit 2 + override; mit Token Exit 0."""
    proj, home = _sandbox(tmp_path, NO_SECTION)
    settings = home / ".claude" / "settings.json"
    settings.write_text('{"env": {}}\n')
    local = home / ".claude" / "settings.local.json"  # existiert nicht: Anlegen zaehlt
    switch = '{"env": {"OPENSPEC_AUTONOMY": "auto"}}\n'
    calls = [
        ("settings.json Edit", "Edit",
         {"file_path": str(settings), "old_string": '"env": {}',
          "new_string": '"env": {"OPENSPEC_AUTONOMY": "auto"}'}),
        ("settings.json Write", "Write",
         {"file_path": str(settings), "content": switch}),
        ("settings.local.json Write (neu)", "Write",
         {"file_path": str(local), "content": switch}),
    ]
    wrong = []
    for label, tool, tin in calls:
        r = _edit_gate(proj, home, tool, tin)
        if r.returncode != 2 or OVERRIDE_HINT not in r.stderr:
            wrong.append(f"  ohne Token {label}: rc={r.returncode} (soll 2), "
                         f"stderr={r.stderr.strip()[:160]!r}")
    _token(proj)
    for label, tool, tin in calls:
        r = _edit_gate(proj, home, tool, tin)
        if r.returncode != 0:
            wrong.append(f"  mit Token {label}: rc={r.returncode} (soll 0), "
                         f"stderr={r.stderr.strip()[:160]!r}")
    _fail("AC-3", wrong)


# --- AC-4 -------------------------------------------------------------------

def test_bash_gate_blocks_settings_and_env_assignment(tmp_path):
    """AC-4: Schreiben auf ~/.claude/settings.json und OPENSPEC_AUTONOMY-Zuweisungen blocken; Lesen frei."""
    proj, home = _sandbox(tmp_path, NO_SECTION)
    (home / ".claude" / "settings.json").write_text("{}\n")
    blocked = [
        "echo '{}' > ~/.claude/settings.json",
        "export OPENSPEC_AUTONOMY=auto",
        "OPENSPEC_AUTONOMY=auto python3 x.py",
        "env OPENSPEC_AUTONOMY=auto python3 x.py",
    ]
    free = [
        "echo $OPENSPEC_AUTONOMY",
        "env | grep OPENSPEC_AUTONOMY",
    ]
    wrong = []
    for cmd in blocked:
        r = _bash_gate(proj, home, cmd)
        if r.returncode != 2 or OVERRIDE_HINT not in r.stderr:
            wrong.append(f"  {cmd!r}: rc={r.returncode} (soll 2), "
                         f"stderr={r.stderr.strip()[:160]!r}")
    for cmd in free:
        r = _bash_gate(proj, home, cmd)
        if r.returncode != 0:
            wrong.append(f"  {cmd!r}: rc={r.returncode} (soll 0), "
                         f"stderr={r.stderr.strip()[:160]!r}")
    _fail("AC-4", wrong)


# --- AC-5 -------------------------------------------------------------------

def test_template_does_not_override_user_switch(tmp_path, monkeypatch):
    """AC-5: Repo-config.yaml hat keinen aktiven autonomy.mode; ohne Variable manual, mit auto auto."""
    import yaml  # noqa: PLC0415
    cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())
    assert isinstance(cfg, dict)
    section = cfg.get("autonomy")
    assert not (isinstance(section, dict) and "mode" in section), \
        f"config.yaml hat aktiven autonomy.mode: {section!r}"

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
    monkeypatch.delenv(ENV_VAR, raising=False)
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    monkeypatch.setattr(workflow, "trusted_config", lambda: cfg)
    assert workflow.autonomy_mode() == "manual"
    monkeypatch.setenv(ENV_VAR, "auto")
    assert workflow.autonomy_mode() == "auto", \
        "Template ueberstimmt den Benutzer-Schalter OPENSPEC_AUTONOMY=auto"
