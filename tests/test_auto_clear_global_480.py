"""Auto-/clear benutzerweit einschaltbar; alle registrierten Hooks ausfuehrbar (Issue #480).

Spec: docs/specs/feat-480-auto-clear-global.md (AC-1 bis AC-5).

Vertraege, die diese Tests festlegen (zusaetzlich zur Spec):
- Opt-in-Leser laufen als Subprozess (`python3 -c`) mit `CLAUDE_PROJECT_DIR` = isoliertes
  Projekt; `herdr_bridge.auto_clear_enabled()` -> bool, `_auto_clear_config()` -> dict|None
  mit den Schluesseln `grace_s`, `idle_timeout_s`, `announce` (Defaults: `AC_DEFAULTS`).
- Eine Root-config.yaml nur mit `deploy:` gilt als App-Config (#372); die Test-Configs
  enthalten deshalb immer einen Plugin-Schluessel (`herdr:`).
- Die Env-Variable heisst `OPENSPEC_HERDR_AUTO_CLEAR` und wird fuer jeden Lauf
  explizit gesetzt oder entfernt (alle OPENSPEC_*-Variablen werden vorher gestrippt).
- AC-5: Pfade aus hooks/hooks.json per Regex `core/hooks/[^ "]+\\.py`.

Importfehler/fehlende Funktionen erscheinen als Test-FAIL: Module werden erst im
Testkoerper bzw. im Subprozess importiert.
"""

import json
import os
import re
import stat
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
FOOTER_GATE = HOOKS_DIR / "footer_gate.py"
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"

ENV_VAR = "OPENSPEC_HERDR_AUTO_CLEAR"
PANE = "pane-480"
WF = "feat-480-auto-clear-global"
PHASE = "phase6_implement"
CMD = "/50-implement #480"

NO_ENTRY = "herdr:\n  enabled: true\n"
PROJECT_FALSE = "herdr:\n  auto_clear:\n    enabled: false\n"
PROJECT_TRUE = "herdr:\n  auto_clear:\n    enabled: true\n"
GRACE_ONLY = "herdr:\n  auto_clear:\n    grace_s: 7\n"

POSITIVE = "✅ **`/clear` ist jetzt gefahrlos** — alles auf Platte gesichert."

# #506: `/clear` loest im Stub den SessionStart(clear)-Marker aus wie der echte Hook
STUB_SCRIPT = r"""#!/bin/bash
{ for a in "$@"; do printf '%s\0' "$a"; done; printf '\n'; } >> "$STUB_LOG"
if [ "$1 $2" = "agent prompt" ]; then exit 1; fi  # Pane `blocked`: abgelehnt (#506)
if [ "$1 $2" = "pane send-text" ]; then printf '%s' "$4" > "$STUB_LOG.pending"; exit 0; fi
typed=""
if [ "$1 $2" = "pane send-keys" ] && [ -f "$STUB_LOG.pending" ]; then
  typed="$(cat "$STUB_LOG.pending")"; rm -f "$STUB_LOG.pending"
fi
if [ "$1 $2 $4" = "pane send-keys enter" ] && [ "$typed" = "/clear" ]; then
  python3 - "$CLAUDE_PROJECT_DIR/.claude/herdr_signals/$3.session.json" <<'EOF'
import json, os, sys, time
os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True)
with open(sys.argv[1] + ".tmp", "w") as fh:
    json.dump({"source": "clear", "at": time.time()}, fh)
os.replace(sys.argv[1] + ".tmp", sys.argv[1])
EOF
fi
exit 0
"""


# --- Helpers ---------------------------------------------------------------

def _project(root: Path, config: "str | None") -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    data = {"name": WF, "workflow_type": "feature", "current_phase": PHASE,
            "phase_transitions": [], "phase_log": []}
    (proj / ".claude" / "workflows" / f"{WF}.json").write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(WF)
    if config is not None:
        (proj / "config.yaml").write_text(config)
    return proj


def _env(proj: Path, switch: "str | None") -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    if switch is not None:
        env[ENV_VAR] = switch
    return env


_PROBE = (
    "import json, sys\n"
    f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
    "import herdr_bridge\n"
    "print(json.dumps({'enabled': herdr_bridge.auto_clear_enabled(),\n"
    "                  'config': herdr_bridge._auto_clear_config(),\n"
    "                  'defaults': dict(herdr_bridge.AC_DEFAULTS)}))\n"
)


def _probe(tmp_path: Path, label: str, config: "str | None", switch: "str | None") -> dict:
    root = tmp_path / label
    root.mkdir()
    proj = _project(root, config)
    res = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True,
                         env=_env(proj, switch), cwd=str(proj), timeout=30)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


def _calls(log: Path) -> list:
    if not log.exists():
        return []
    out = []
    for line in log.read_bytes().decode("utf-8", "replace").split("\n"):
        if line:
            out.append(line.split("\0")[:-1] if line.endswith("\0") else line.split("\0"))
    return out


def _wait_for(log: Path, n: int = 1, timeout: float = 4.0) -> list:
    deadline = time.monotonic() + timeout
    calls = _calls(log)
    while len(calls) < n and time.monotonic() < deadline:
        time.sleep(0.05)
        calls = _calls(log)
    return calls


# --- AC-1 -------------------------------------------------------------------

@pytest.mark.parametrize("switch", ["1", "true", "YES", " on "])
def test_env_switch_without_project_entry(tmp_path, switch):
    res = _probe(tmp_path, "on", NO_ENTRY, switch)
    assert res["enabled"] is True, res
    assert res["config"] is not None, res


@pytest.mark.parametrize("switch", [None, "0", "false", ""])
def test_env_switch_off_values_without_project_entry(tmp_path, switch):
    res = _probe(tmp_path, "off", NO_ENTRY, switch)
    assert res["enabled"] is False, res
    assert res["config"] is None, res


# --- AC-2 -------------------------------------------------------------------

def test_project_value_wins_over_env(tmp_path):
    res = _probe(tmp_path, "false-vs-env1", PROJECT_FALSE, "1")
    assert res["enabled"] is False, res
    for i, switch in enumerate([None, "0"]):
        res = _probe(tmp_path, f"true-{i}", PROJECT_TRUE, switch)
        assert res["enabled"] is True, (switch, res)


# --- AC-3 -------------------------------------------------------------------

def test_env_switch_uses_project_values(tmp_path):
    res = _probe(tmp_path, "grace", GRACE_ONLY, "1")
    cfg = res["config"]
    assert cfg is not None, res
    assert cfg["grace_s"] == 7, cfg
    for key in ("idle_timeout_s", "announce"):
        assert cfg[key] == res["defaults"][key], (key, cfg, res["defaults"])


# --- AC-4 -------------------------------------------------------------------

def test_footer_gate_spawns_with_env_switch(tmp_path):
    proj = _project(tmp_path, NO_ENTRY)
    wf = proj / ".claude" / "workflows" / f"{WF}.json"
    data = json.loads(wf.read_text())
    data["auto_clear_boundary"] = {"phase": PHASE, "command": CMD, "at": datetime.now().isoformat()}
    wf.write_text(json.dumps(data))  # Grenz-Vermerk wie `workflow.py autoclear` (#495)
    stub = tmp_path / "herdr-stub"
    stub.write_text(STUB_SCRIPT)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    log = tmp_path / "stub.log"
    env = _env(proj, "1")
    env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": PANE,
                "HERDR_BIN_PATH": str(stub), "STUB_LOG": str(log)})
    message = "\n\n".join(["Phase abgeschlossen.", POSITIVE,
                           f"❗ Du: `{CMD}` — der naechste Pflicht-Schritt",
                           "⚙ /40-tdd-red · agent-os-openspec 3.43.1"])
    payload = {"session_id": "sess-480", "hook_event_name": "Stop", "cwd": str(proj),
               "last_assistant_message": message,
               "prompt_id": "11111111-2222-3333-4444-555555555555"}
    res = subprocess.run([sys.executable, str(FOOTER_GATE)], input=json.dumps(payload),
                         capture_output=True, text=True, env=env, cwd=str(proj), timeout=30)
    assert res.returncode == 0, res.stderr
    calls = _wait_for(log, 2, timeout=20.0)  # Default grace 10 s + settle 2 s vor /clear (#506)
    kinds = [" ".join(c[:2]) for c in calls]
    assert "pane send-text" in kinds, f"Runner nicht gestartet (kein `pane send-text`): {calls}"


# --- AC-5 -------------------------------------------------------------------

def test_all_registered_hooks_are_executable():
    text = HOOKS_JSON.read_text()
    paths = sorted(set(re.findall(r'core/hooks/[^ "]+\.py', text)))
    assert paths, "Keine Hook-Pfade in hooks/hooks.json gefunden"
    bad = []
    for rel in paths:
        out = subprocess.run(["git", "ls-files", "-s", rel], capture_output=True,
                             text=True, cwd=str(REPO_ROOT), timeout=30).stdout.strip()
        mode = out.split()[0] if out else "untracked"
        if mode != "100755":
            bad.append(f"{rel}: git-Modus {mode}")
        if not os.access(REPO_ROOT / rel, os.X_OK):
            bad.append(f"{rel}: im Arbeitsbaum nicht ausfuehrbar")
    assert not bad, "Registrierte Hooks ohne Ausfuehrungsrecht:\n" + "\n".join(bad)
