"""Auto-/clear mit eigenen Plugin-Signalen statt Herdr-Status (Issue #506).

Spec: docs/specs/fix-506-autoclear-ohne-herdr-status.md v1.2 (AC-1 bis AC-10,
AC-14 bis AC-22; AC-11 ist der Regressionslauf, AC-12/AC-13/AC-23 das E2E-Skript).

Stub-Herdr (bash), protokolliert jeden Aufruf NUL-getrennt in STUB_LOG. Herdr ist
nur noch Tastatur: getippt wird per `pane send-text <pane> <text>`, abgeschickt per
`pane send-keys <pane> enter`.
- `pane send-text <pane> <text>`: merkt sich den Text (`$STUB_LOG.pending`), Exit 0.
- `pane send-keys <pane> enter`: war der gemerkte Text `/clear`, fuehrt der Stub
  optional STUB_CLEAR_HOOK aus (State-Umbau) und schreibt optional den
  SessionStart-Marker nach STUB_SESSION_MARKER — simuliert den echten
  SessionStart(clear)-Hook. Steuerung: STUB_SESSION_DELAY (Sekunden, im
  Hintergrund), STUB_SESSION_SOURCE (Default `clear`), STUB_SESSION_AT_OFFSET
  (Sekunden auf `time.time()`, negativ = Zeitstempel vor dem /clear).
- `agent prompt`: bei STUB_BLOCKED=1 (Default der Runner-Tests, Pane `blocked` wie
  beim PO) wie echtes Herdr 0.9.5 abgelehnt: `agent_blocked`, Exit 1. Sonst Exit 0
  ohne Wirkung (kein Marker) — `agent prompt` tippt in diesem Stub nie.
- `agent wait`: wie beim PO (Pane `blocked`): Exit 1 "timed out waiting for agent status".
- alles andere: Exit 0.

Marker-Vertrag (Spec, Implementation Details): `<base>/.claude/herdr_signals/`
mit `<pane>.input.json` = `{"at": <time.time()>}` und
`<pane>.session.json` = `{"source": "<clear|startup|resume|compact>", "at": ...}`.
"""

import json
import os
import stat
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
BRIDGE = HOOKS_DIR / "herdr_bridge.py"
FOOTER_GATE = HOOKS_DIR / "footer_gate.py"
PHASE_LISTENER = HOOKS_DIR / "phase_listener.py"
SESSION_BANNER = HOOKS_DIR / "session_banner.py"

PANE = "pane-506"
OTHER_PANE = "pane-fremd"
WF = "fix-506-autoclear-ohne-herdr-status"
PHASE = "phase6_implement"
CMD = "/50-implement #506"
IDLE_TIMEOUT = 2

STUB_SCRIPT = r"""#!/bin/bash
{ for a in "$@"; do printf '%s\0' "$a"; done; printf '\n'; } >> "$STUB_LOG"
PENDING="$STUB_LOG.pending"
if [ "$1 $2" = "agent wait" ]; then
  printf '%s\n' 'timed out waiting for agent status' >&2
  exit 1
fi
if [ "$1 $2" = "agent prompt" ]; then
  if [ "$STUB_BLOCKED" = "1" ]; then
    printf '%s\n' '{"error":{"code":"agent_blocked","message":"agent is blocked"}}' >&2
    exit 1
  fi
  exit 0
fi
if [ "$1 $2" = "pane send-text" ]; then
  printf '%s' "$4" > "$PENDING"
  exit 0
fi
if [ "$1 $2" = "pane send-keys" ]; then
  typed=""
  if [ -f "$PENDING" ]; then typed="$(cat "$PENDING")"; rm -f "$PENDING"; fi
  if [ "$4" = "enter" ] && [ "$typed" = "/clear" ]; then
    if [ -n "$STUB_CLEAR_HOOK" ]; then bash "$STUB_CLEAR_HOOK"; fi
    if [ -n "$STUB_SESSION_MARKER" ]; then
      ( sleep "${STUB_SESSION_DELAY:-0}"
        python3 - "$STUB_SESSION_MARKER" "${STUB_SESSION_SOURCE:-clear}" \
          "${STUB_SESSION_AT_OFFSET:-0}" <<'EOF'
import json, os, sys, time
path, source, offset = sys.argv[1], sys.argv[2], float(sys.argv[3])
os.makedirs(os.path.dirname(path), exist_ok=True)
tmp = path + ".tmp"
with open(tmp, "w") as fh:
    json.dump({"source": source, "at": time.time() + offset}, fh)
os.replace(tmp, path)
EOF
      ) </dev/null >/dev/null 2>&1 &
    fi
  fi
  exit 0
fi
exit 0
"""

AUTO_ON = ("herdr:\n  auto_clear:\n    enabled: true\n    grace_s: 0\n"
           "    idle_timeout_s: 2\n    announce: true\n"
           "session_banner:\n  behind_check: false\n")


# --- Helpers ---------------------------------------------------------------

def _make_stub(root: Path) -> Path:
    stub = root / "herdr-stub"
    stub.write_text(STUB_SCRIPT)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def _project(root: Path, phase: str = PHASE, config: "str | None" = AUTO_ON,
             **fields) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    data = {"name": WF, "workflow_type": "feature", "current_phase": phase,
            "phase_transitions": [], "phase_log": []}
    data.update(fields)
    (proj / ".claude" / "workflows" / f"{WF}.json").write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(WF)
    if config is not None:
        (proj / "config.yaml").write_text(config)
    return proj


def _signals(proj: Path) -> Path:
    return proj / ".claude" / "herdr_signals"


def _marker(proj: Path, pane: str, kind: str) -> Path:
    return _signals(proj) / f"{pane}.{kind}.json"


def _write_marker(path: Path, **data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _env(proj: Path, log: Path, stub: Path, *, herdr: bool = True,
         pane: str = PANE, **extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_", "CLAUDE_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    if herdr:
        env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": pane,
                    "HERDR_BIN_PATH": str(stub), "STUB_LOG": str(log)})
    env.update({k: str(v) for k, v in extra.items()})
    return env


def _case(tmp_path: Path, label: str, *, session_to: "str | None" = PANE,
          phase: str = PHASE, **extra):
    """Isoliertes Projekt + Stub; der Stub schreibt den session-Marker fuer `session_to`."""
    root = tmp_path / label
    root.mkdir()
    proj = _project(root, phase=phase)
    log = root / "stub.log"
    stub = _make_stub(root)
    if session_to is not None:
        extra.setdefault("STUB_SESSION_MARKER", str(_marker(proj, session_to, "session")))
    extra.setdefault("STUB_BLOCKED", "1")  # Pane `blocked` wie beim PO
    return proj, log, _env(proj, log, stub, **extra), root


def _calls(log: Path) -> list:
    if not log.exists():
        return []
    out = []
    for line in log.read_bytes().decode("utf-8", "replace").split("\n"):
        if line:
            out.append(line.split("\0")[:-1] if line.endswith("\0") else line.split("\0"))
    return out


def _kind(args: list) -> str:
    return " ".join(args[:2])


TYPING_KINDS = ("pane send-text", "pane send-keys")


def _typing(calls: list) -> list:
    """Alle Tastatur-Aufrufe (`pane send-text`/`pane send-keys`) in Reihenfolge."""
    return [c for c in calls if _kind(c) in TYPING_KINDS]


def _typed_or_prompted(calls: list) -> list:
    """Alles, womit der Runner Text an die Session schicken koennte."""
    return [c for c in calls if _kind(c) in TYPING_KINDS + ("agent prompt",)]


_NOW = object()  # Sentinel: --since = Zeitpunkt des Aufrufs (wie der Stop-Hook)


def _runner_argv(*, command: str = CMD, phase: str = PHASE, grace: float = 0,
                 idle_timeout: float = IDLE_TIMEOUT, since=_NOW) -> list:
    argv = [sys.executable, str(BRIDGE), "auto-clear",
            "--pane", PANE, "--workflow", WF, "--phase", phase, "--command", command,
            "--grace", str(grace), "--settle", "0", "--idle-timeout", str(idle_timeout),
            "--announce", "0"]
    if since is _NOW:
        since = time.time()
    if since is not None:
        argv += ["--since", repr(float(since))]
    return argv


def _run_runner(proj: Path, env: dict, timeout: float = 40, **kw):
    return subprocess.run(_runner_argv(**kw), capture_output=True, text=True, env=env,
                          cwd=str(proj), timeout=timeout)


def _start_runner(proj: Path, env: dict, **kw) -> subprocess.Popen:
    return subprocess.Popen(_runner_argv(**kw), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env, cwd=str(proj))


def _runner_log(proj: Path) -> str:
    path = proj / ".claude" / "herdr_auto_clear.log"
    return path.read_text() if path.exists() else ""


def _assert_clean(res, proj):
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in (res.stderr or ""), res.stderr
    assert _runner_log(proj).strip(), "kein Eintrag in herdr_auto_clear.log"


ENTER = ["pane", "send-keys", PANE, "enter"]
CLEAR = [["pane", "send-text", PANE, "/clear"], ENTER]
FOLLOW = [["pane", "send-text", PANE, "/agent-os-openspec:50-implement #506"], ENTER]


def _state_changer(root: Path) -> Path:
    """Skript: setzt den Workflow auf phase7_validate (anderer erwarteter Befehl)."""
    wf = root / "proj" / ".claude" / "workflows" / f"{WF}.json"
    script = root / "change.sh"
    script.write_text(
        "python3 - <<'EOF'\n"
        "import json\n"
        f"p = {str(wf)!r}\n"
        "d = json.load(open(p))\n"
        "d['current_phase'] = 'phase7_validate'\n"
        "json.dump(d, open(p, 'w'))\n"
        "EOF\n")
    return script


# --- AC-1 -------------------------------------------------------------------

def test_runner_never_calls_agent_wait(tmp_path):
    proj, log, env, _ = _case(tmp_path, "nowait", STUB_SESSION_DELAY="0.3")
    res = _run_runner(proj, env)
    _assert_clean(res, proj)
    calls = _calls(log)
    assert [c for c in calls if _kind(c) == "agent wait"] == [], \
        f"Runner ruft weiterhin `agent wait` auf: {calls}"
    assert [c for c in calls if _kind(c) == "agent prompt"] == [], \
        f"Runner tippt per `agent prompt` (bei `blocked` abgelehnt): {calls}"
    assert [c for c in calls if c and c[0] == "agent"] == [], \
        f"Runner nutzt weiterhin `agent`-Befehle: {calls}"
    assert [_kind(c) for c in calls] == ["pane send-text", "pane send-keys"] * 2, calls
    assert calls == CLEAR + FOLLOW, f"Log: {_runner_log(proj)!r} Aufrufe: {calls}"
    assert "OK" in _runner_log(proj), _runner_log(proj)


# --- AC-2 -------------------------------------------------------------------

def test_new_input_since_spawn_aborts_without_typing(tmp_path):
    proj, log, env, _ = _case(tmp_path, "input")
    since = time.time()  # Stop-Hook-Zeitpunkt
    proc = _start_runner(proj, env, grace=2.5, since=since)
    time.sleep(0.8)  # Nutzer schickt in der Grace-Zeit einen neuen Prompt ab
    _write_marker(_marker(proj, PANE, "input"), at=time.time())
    out, err = proc.communicate(timeout=40)
    assert proc.returncode == 0, err
    assert _typed_or_prompted(_calls(log)) == [], _calls(log)
    assert "Nutzer hat weitergeschrieben" in _runner_log(proj), _runner_log(proj)


# --- AC-3 -------------------------------------------------------------------

@pytest.mark.parametrize("variant", ["none", "older"])
def test_no_new_input_types_clear(tmp_path, variant):
    proj, log, env, _ = _case(tmp_path, variant, STUB_SESSION_DELAY="0.3")
    since = time.time()
    if variant == "older":
        _write_marker(_marker(proj, PANE, "input"), at=since - 60)
    res = _run_runner(proj, env, since=since)
    _assert_clean(res, proj)
    typing = _typing(_calls(log))
    assert typing[:2] == CLEAR, \
        f"/clear nicht getippt; Log: {_runner_log(proj)!r} Aufrufe: {_calls(log)}"


# --- AC-14 ------------------------------------------------------------------

def test_input_between_stop_and_runner_start_aborts(tmp_path):
    # (a) Eingabe zwischen Stop-Hook (--since) und Runner-Start: zaehlt als neu
    proj, log, env, _ = _case(tmp_path, "gap", STUB_SESSION_DELAY="0.3")
    since = time.time()
    _write_marker(_marker(proj, PANE, "input"), at=since + 0.1)
    time.sleep(0.4)  # Runner startet erst nach der Eingabe
    res = _run_runner(proj, env, since=since)
    _assert_clean(res, proj)
    assert _typed_or_prompted(_calls(log)) == [], \
        f"(a) trotz Eingabe nach --since getippt: {_calls(log)}"
    assert "Nutzer hat weitergeschrieben" in _runner_log(proj), _runner_log(proj)

    # (b) ohne --since gilt der Runner-Start: dieselbe (dann aeltere) Eingabe zaehlt nicht
    proj, log, env, _ = _case(tmp_path, "nosince", STUB_SESSION_DELAY="0.3")
    _write_marker(_marker(proj, PANE, "input"), at=time.time() - 0.3)
    time.sleep(0.1)
    res = _run_runner(proj, env, since=None)
    _assert_clean(res, proj)
    assert _typing(_calls(log)) == CLEAR + FOLLOW, \
        f"(b) Log: {_runner_log(proj)!r} Aufrufe: {_calls(log)}"

    # (c) ohne --since: Eingabe nach Runner-Start (Grace-Zeit) bricht weiterhin ab
    proj, log, env, _ = _case(tmp_path, "nosince-grace")
    proc = _start_runner(proj, env, grace=2.0, since=None)
    time.sleep(0.8)
    _write_marker(_marker(proj, PANE, "input"), at=time.time())
    _, err = proc.communicate(timeout=40)
    assert proc.returncode == 0, err
    assert _typed_or_prompted(_calls(log)) == [], f"(c) {_calls(log)}"
    assert "Nutzer hat weitergeschrieben" in _runner_log(proj), _runner_log(proj)


# --- AC-4 -------------------------------------------------------------------

def test_session_clear_after_own_clear_types_followup(tmp_path):
    proj, log, env, _ = _case(tmp_path, "followup", STUB_SESSION_DELAY="0.8")
    res = _run_runner(proj, env)
    _assert_clean(res, proj)
    assert _typing(_calls(log)) == CLEAR + FOLLOW, \
        f"Log: {_runner_log(proj)!r} Aufrufe: {_calls(log)}"
    assert "OK" in _runner_log(proj), _runner_log(proj)
    marker = json.loads(_marker(proj, PANE, "session").read_text())
    assert marker["source"] == "clear"


# --- AC-5 -------------------------------------------------------------------

def test_missing_session_signal_aborts_without_followup(tmp_path):
    proj, log, env, _ = _case(tmp_path, "nosession", session_to=None)
    start = time.monotonic()
    res = _run_runner(proj, env)
    elapsed = time.monotonic() - start
    _assert_clean(res, proj)
    assert _typing(_calls(log)) == CLEAR, \
        f"Log: {_runner_log(proj)!r} Aufrufe: {_calls(log)}"
    assert "ABBRUCH" in _runner_log(proj)
    assert "SessionStart" in _runner_log(proj), _runner_log(proj)
    assert elapsed >= IDLE_TIMEOUT * 0.8, f"Frist nicht abgewartet: {elapsed:.2f}s"


# --- AC-6 -------------------------------------------------------------------

@pytest.mark.parametrize("variant", ["stale-preexisting", "stale-at", "startup"])
def test_session_start_before_own_clear_does_not_count(tmp_path, variant):
    if variant == "stale-preexisting":
        # Marker aus einem frueheren SessionStart(clear), Stub schreibt keinen neuen
        proj, log, env, _ = _case(tmp_path, variant, session_to=None)
        _write_marker(_marker(proj, PANE, "session"), source="clear", at=time.time() - 5)
    elif variant == "stale-at":
        proj, log, env, _ = _case(tmp_path, variant, STUB_SESSION_AT_OFFSET="-100")
    else:
        proj, log, env, _ = _case(tmp_path, variant, STUB_SESSION_SOURCE="startup")
    res = _run_runner(proj, env)
    _assert_clean(res, proj)
    assert _typing(_calls(log)) == CLEAR, \
        f"Log: {_runner_log(proj)!r} Aufrufe: {_calls(log)}"
    assert "ABBRUCH" in _runner_log(proj)
    assert "SessionStart" in _runner_log(proj), _runner_log(proj)


# --- AC-7 -------------------------------------------------------------------

def test_markers_are_per_pane(tmp_path):
    # (a) Eingabe in einem fremden Pane waehrend der Grace-Zeit stoppt nicht
    proj, log, env, _ = _case(tmp_path, "foreign-input", STUB_SESSION_DELAY="0.3")
    proc = _start_runner(proj, env, grace=1.5)
    time.sleep(0.5)
    _write_marker(_marker(proj, OTHER_PANE, "input"), at=time.time())
    _, err = proc.communicate(timeout=40)
    assert proc.returncode == 0, err
    assert _typing(_calls(log)) == CLEAR + FOLLOW, \
        f"(a) Log: {_runner_log(proj)!r} Aufrufe: {_calls(log)}"

    # (b) SessionStart(clear) eines fremden Panes zaehlt nicht fuer das eigene
    proj, log, env, _ = _case(tmp_path, "foreign-session", session_to=OTHER_PANE)
    res = _run_runner(proj, env)
    _assert_clean(res, proj)
    assert _marker(proj, OTHER_PANE, "session").exists(), "Stub schrieb keinen Fremd-Marker"
    assert _typing(_calls(log)) == CLEAR, \
        f"(b) Log: {_runner_log(proj)!r} Aufrufe: {_calls(log)}"


# --- AC-8 / AC-9: Hooks als Subprozess --------------------------------------

def _plugin_root(root: Path) -> Path:
    plugin = root / "plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": "9.9.9"}))
    return plugin


def _hook_env(proj: Path, root: Path, *, herdr_env: "str | None", pane: "str | None") -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_", "CLAUDE_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["CLAUDE_PLUGIN_ROOT"] = str(_plugin_root(root) if not (root / "plugin").exists()
                                    else root / "plugin")
    env["HOME"] = str(proj / "_home")
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    stub = root / "herdr-stub"
    if not stub.exists():
        _make_stub(root)
    env["HERDR_BIN_PATH"] = str(stub)
    env["STUB_LOG"] = str(root / "stub.log")
    if herdr_env is not None:
        env["HERDR_ENV"] = herdr_env
    if pane is not None:
        env["HERDR_PANE_ID"] = pane
    return env


def _run_listener(proj: Path, env: dict, prompt: str = "wie ist der Stand?",
                  raw: "str | None" = None):
    payload = raw if raw is not None else json.dumps(
        {"prompt": prompt, "session_id": "sess-506", "cwd": str(proj),
         "hook_event_name": "UserPromptSubmit"})
    return subprocess.run([sys.executable, str(PHASE_LISTENER)], input=payload,
                          capture_output=True, text=True, env=env, cwd=str(proj), timeout=30)


def _run_banner(proj: Path, env: dict, source: str = "resume", raw: "str | None" = None):
    payload = raw if raw is not None else json.dumps(
        {"session_id": "sess-506", "cwd": str(proj), "hook_event_name": "SessionStart",
         "source": source})
    return subprocess.run([sys.executable, str(SESSION_BANNER)], input=payload,
                          capture_output=True, text=True, env=env, cwd=str(proj), timeout=30)


def _signal_files(proj: Path) -> list:
    sig = _signals(proj)
    if not sig.is_dir():
        return []
    return sorted(p.name for p in sig.iterdir())


@pytest.mark.parametrize("label,herdr_env,pane", [
    ("no-herdr", None, None),
    ("env-0", "0", PANE),
    ("no-pane", "1", None),
    ("empty-pane", "1", ""),
])
def test_hooks_write_marker_only_with_pane_id(tmp_path, label, herdr_env, pane):
    # Negativ: ohne Herdr-Pane entsteht nichts
    root = tmp_path / label
    root.mkdir()
    proj = _project(root)
    env = _hook_env(proj, root, herdr_env=herdr_env, pane=pane)
    assert _run_listener(proj, env).returncode == 0
    assert _run_banner(proj, env).returncode == 0
    assert _signal_files(proj) == [], _signal_files(proj)

    # Positiv: mit Pane schreiben beide Hooks ihren Marker
    root = tmp_path / f"{label}-with-pane"
    root.mkdir()
    proj = _project(root)
    env = _hook_env(proj, root, herdr_env="1", pane=PANE)
    before = time.time()
    res = _run_listener(proj, env)
    assert res.returncode == 0, res.stderr
    inp = _marker(proj, PANE, "input")
    assert inp.is_file(), f"phase_listener schrieb kein {inp.name}: {_signal_files(proj)}"
    at = json.loads(inp.read_text())["at"]
    assert isinstance(at, (int, float)) and before - 1 <= at <= time.time() + 1, at

    before = time.time()
    res = _run_banner(proj, env, source="resume")
    assert res.returncode == 0, res.stderr
    ses = _marker(proj, PANE, "session")
    assert ses.is_file(), f"session_banner schrieb kein {ses.name}: {_signal_files(proj)}"
    data = json.loads(ses.read_text())
    assert data["source"] == "resume", data
    assert isinstance(data["at"], (int, float)) and before - 1 <= data["at"] <= time.time() + 1


def test_marker_write_is_fail_open_and_silent(tmp_path):
    # Vorbedingung: das Marker-Schreiben existiert (sonst ist "fail-open" bedeutungslos)
    root = tmp_path / "control"
    root.mkdir()
    proj = _project(root)
    env = _hook_env(proj, root, herdr_env="1", pane=PANE)
    assert _run_listener(proj, env).returncode == 0
    assert _run_banner(proj, env, source="clear").returncode == 0
    assert _marker(proj, PANE, "input").is_file() and _marker(proj, PANE, "session").is_file(), \
        f"Marker-Schreiben fehlt: {_signal_files(proj)}"

    # Baseline: dieselben Hooks ausserhalb von Herdr
    root = tmp_path / "baseline"
    root.mkdir()
    proj = _project(root)
    env = _hook_env(proj, root, herdr_env=None, pane=None)
    base_l = _run_listener(proj, env)
    base_b = _run_banner(proj, env, source="clear")

    # (a) Markerverzeichnis nicht anlegbar: `.claude/herdr_signals` ist eine Datei
    root = tmp_path / "unwritable"
    root.mkdir()
    proj = _project(root)
    _signals(proj).write_text("keine Verzeichnis")
    env = _hook_env(proj, root, herdr_env="1", pane=PANE)
    for res, base in ((_run_listener(proj, env), base_l),
                      (_run_banner(proj, env, source="clear"), base_b)):
        assert res.returncode == base.returncode == 0, res.stderr
        assert res.stdout == base.stdout, (res.stdout, base.stdout)
        assert res.stderr == base.stderr, (res.stderr, base.stderr)
    assert _signals(proj).read_text() == "keine Verzeichnis"

    # (b) Ungueltige Pane-Id darf nichts ausserhalb des Markerverzeichnisses schreiben
    root = tmp_path / "badpane"
    root.mkdir()
    proj = _project(root)
    env = _hook_env(proj, root, herdr_env="1", pane="../../ausbruch")
    res_l = _run_listener(proj, env)
    res_b = _run_banner(proj, env, source="clear")
    for res, base in ((res_l, base_l), (res_b, base_b)):
        assert res.returncode == 0, res.stderr
        assert res.stdout == base.stdout, (res.stdout, base.stdout)
        assert res.stderr == base.stderr, (res.stderr, base.stderr)
    escaped = [p for p in root.rglob("*ausbruch*")
               if _signals(proj) not in p.parents]
    assert escaped == [], escaped

    # (c) Ungueltiger Payload: Hooks laufen wie ohne Marker
    root = tmp_path / "badpayload"
    root.mkdir()
    proj = _project(root)
    env_b = _hook_env(proj, root, herdr_env=None, pane=None)
    base_raw_l = _run_listener(proj, env_b, raw="kein json")
    base_raw_b = _run_banner(proj, env_b, raw="kein json")
    env = _hook_env(proj, root, herdr_env="1", pane=PANE)
    for res, base in ((_run_listener(proj, env, raw="kein json"), base_raw_l),
                      (_run_banner(proj, env, raw="kein json"), base_raw_b)):
        assert res.returncode == base.returncode == 0, res.stderr
        assert res.stdout == base.stdout
        assert res.stderr == base.stderr


# --- AC-10 ------------------------------------------------------------------

POSITIVE = "✅ **`/clear` ist jetzt gefahrlos** — alles auf Platte gesichert."


def _footer_message(command: str = CMD) -> str:
    return "\n\n".join(["Phase abgeschlossen.", POSITIVE,
                        f"❗ Du: `{command}` — der naechste Pflicht-Schritt",
                        "⚙ /50-implement · agent-os-openspec 4.4.8"])


def test_manual_lock_and_recheck_unchanged(tmp_path):
    # (a) /99-reset: Runner tippt nichts
    proj, log, env, _ = _case(tmp_path, "reset")
    res = _run_runner(proj, env, command="/99-reset #506")
    _assert_clean(res, proj)
    assert _typed_or_prompted(_calls(log)) == [], _calls(log)
    assert "manuell" in _runner_log(proj), _runner_log(proj)

    # (b) Once-Lock gesetzt: footer_gate spawnt keinen Runner
    root = tmp_path / "lock"
    root.mkdir()
    boundary = {"phase": PHASE, "command": CMD, "at": datetime.now().isoformat()}
    proj = _project(root, auto_clear_boundary=boundary)
    lock = proj / ".claude" / "herdr_auto_clear_state.json"
    lock.write_text(json.dumps({f"{WF}|{PHASE}|{CMD}": time.time()}))
    log = root / "stub.log"
    env = _env(proj, log, _make_stub(root))
    payload = {"session_id": "sess-506", "hook_event_name": "Stop", "cwd": str(proj),
               "last_assistant_message": _footer_message(),
               "prompt_id": "11111111-2222-3333-4444-555555555555"}
    res = subprocess.run([sys.executable, str(FOOTER_GATE)], input=json.dumps(payload),
                         capture_output=True, text=True, env=env, cwd=str(proj), timeout=30)
    assert res.returncode == 0, res.stderr
    time.sleep(0.8)
    assert _calls(log) == [], f"Runner trotz Once-Lock gespawnt: {_calls(log)}"

    # (c) Phase wechselt in der Grace-Zeit: _recheck vor /clear, nichts getippt
    proj, log, env, root = _case(tmp_path, "recheck-before")
    proc = _start_runner(proj, env, grace=1.5)
    time.sleep(0.5)
    subprocess.run(["bash", str(_state_changer(root))], check=True, timeout=30)
    _, err = proc.communicate(timeout=40)
    assert proc.returncode == 0, err
    assert _typed_or_prompted(_calls(log)) == [], _calls(log)
    assert "vor /clear" in _runner_log(proj), _runner_log(proj)

    # (d) Phase wechselt beim /clear: SessionStart(clear) kommt, aber _recheck
    #     vor dem Folgebefehl bricht ab
    proj, log, env, root = _case(tmp_path, "recheck-after", STUB_SESSION_DELAY="0.3")
    env["STUB_CLEAR_HOOK"] = str(_state_changer(root))
    res = _run_runner(proj, env)
    _assert_clean(res, proj)
    assert _typing(_calls(log)) == CLEAR, \
        f"Log: {_runner_log(proj)!r} Aufrufe: {_calls(log)}"
    assert "vor Folgebefehl" in _runner_log(proj), _runner_log(proj)


# ===========================================================================
# Spec v1.2 (Adversary R1): eigene Aktivitaets- und Stop-Marker, `--since`-
# Validierung, Marker-Basis aus dem Payload-`cwd` (AC-15 bis AC-22).
#
# Marker-Vertrag v1.2: `<pane>.activity.json` = {"kind": "<pretooluse|notification|
# permission>", "at": ...}, `<pane>.stop.json` = {"at": ...}. Abbruchgrund fuer
# activity/stop: "Claude arbeitet weiter". Toleranz nach dem eigenen /clear:
# AC_CLEAR_TOLERANCE_S = 2,0 s.
# ===========================================================================

GUARD = HOOKS_DIR / "session_singleton_guard.py"
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
TOLERANCE_S = 2.0
WORKING = "Claude arbeitet weiter"
TYPED_ON = "Nutzer hat weitergeschrieben"

_WRITER = r"""import json, os, sys, time
path, delay, fields = sys.argv[1], float(sys.argv[2]), json.loads(sys.argv[3])
time.sleep(delay)
os.makedirs(os.path.dirname(path), exist_ok=True)
fields["at"] = time.time()
tmp = path + ".tmp"
with open(tmp, "w") as fh:
    json.dump(fields, fh)
os.replace(tmp, path)
"""


def _clear_hook_writing(root: Path, marker: Path, delay: float, **fields) -> Path:
    """STUB_CLEAR_HOOK: schreibt `marker` `delay` s nach dem getippten /clear (Hintergrund)."""
    writer = root / "marker_writer.py"
    writer.write_text(_WRITER)
    script = root / f"clear_hook_{marker.stem}.sh"
    script.write_text(
        f"python3 {str(writer)!r} {str(marker)!r} {delay!r} {json.dumps(fields)!r} "
        "</dev/null >/dev/null 2>&1 &\n")
    return script


def _argv_v12(*, since_raw: "str | None", grace: float = 0, settle: float = 0,
              idle_timeout: float = IDLE_TIMEOUT) -> list:
    """Runner-argv mit frei waehlbarem settle und rohem `--since=<wert>`."""
    argv = _runner_argv(grace=grace, idle_timeout=idle_timeout, since=None)
    argv[argv.index("--settle") + 1] = str(settle)
    if since_raw is not None:
        argv.append(f"--since={since_raw}")
    return argv


def _start_v12(proj: Path, env: dict, cwd: "Path | None" = None, **kw) -> subprocess.Popen:
    return subprocess.Popen(_argv_v12(**kw), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env, cwd=str(cwd or proj))


def _finish(proc: subprocess.Popen, timeout: float = 60) -> None:
    _, err = proc.communicate(timeout=timeout)
    assert proc.returncode == 0, err
    assert "Traceback" not in (err or ""), err


def _wait_for(predicate, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.1)
    return predicate()


# --- AC-15 ------------------------------------------------------------------

def test_activity_after_since_aborts_without_typing(tmp_path):
    # (a) Aktivitaet (Tool-Aufruf) in der Grace-Zeit: nichts tippen
    proj, log, env, _ = _case(tmp_path, "act-grace", STUB_SESSION_DELAY="0.3")
    since = time.time()
    proc = _start_v12(proj, env, since_raw=repr(since), grace=2.0)
    time.sleep(0.8)
    _write_marker(_marker(proj, PANE, "activity"), kind="pretooluse", at=time.time())
    _finish(proc)
    assert _typed_or_prompted(_calls(log)) == [], \
        f"(a) trotz Aktivitaet nach --since getippt: {_calls(log)}"
    assert WORKING in _runner_log(proj), f"(a) {_runner_log(proj)!r}"

    # (b) Aktivitaet erst waehrend settle/_recheck: zweite Pruefung vor /clear greift
    proj, log, env, _ = _case(tmp_path, "act-settle", STUB_SESSION_DELAY="0.3")
    since = time.time()
    proc = _start_v12(proj, env, since_raw=repr(since), grace=0.5, settle=3.0)
    time.sleep(1.9)  # nach der Pruefung nach grace, vor der unmittelbar vor /clear
    _write_marker(_marker(proj, PANE, "activity"), kind="permission", at=time.time())
    _finish(proc)
    assert _typed_or_prompted(_calls(log)) == [], \
        f"(b) Aktivitaet waehrend settle nicht erkannt: {_calls(log)}"
    assert WORKING in _runner_log(proj), f"(b) {_runner_log(proj)!r}"

    # (c) Aktivitaet nach t_clear + Toleranz: /clear getippt, Folgebefehl nicht
    proj, log, env, root = _case(tmp_path, "act-after-clear", STUB_SESSION_DELAY="3.4")
    env["STUB_CLEAR_HOOK"] = str(_clear_hook_writing(
        root, _marker(proj, PANE, "activity"), TOLERANCE_S + 0.6, kind="pretooluse"))
    proc = _start_v12(proj, env, since_raw=repr(time.time()), idle_timeout=7)
    _finish(proc)
    assert _typing(_calls(log)) == CLEAR, \
        f"(c) Log: {_runner_log(proj)!r} Aufrufe: {_calls(log)}"
    assert WORKING in _runner_log(proj), f"(c) {_runner_log(proj)!r}"

    # (d) Aktivitaet innerhalb der Toleranz nach /clear zaehlt nicht
    proj, log, env, root = _case(tmp_path, "act-in-tolerance", STUB_SESSION_DELAY="0.6")
    env["STUB_CLEAR_HOOK"] = str(_clear_hook_writing(
        root, _marker(proj, PANE, "activity"), 0.2, kind="pretooluse"))
    proc = _start_v12(proj, env, since_raw=repr(time.time()), idle_timeout=5)
    _finish(proc)
    assert _typing(_calls(log)) == CLEAR + FOLLOW, \
        f"(d) Log: {_runner_log(proj)!r} Aufrufe: {_calls(log)}"
    assert WORKING not in _runner_log(proj), _runner_log(proj)

    # (e) Aktivitaet mit at <= since (vor dem Stop) zaehlt nicht
    proj, log, env, _ = _case(tmp_path, "act-old", STUB_SESSION_DELAY="0.3")
    since = time.time()
    _write_marker(_marker(proj, PANE, "activity"), kind="pretooluse", at=since - 0.5)
    proc = _start_v12(proj, env, since_raw=repr(since), grace=0.5)
    _finish(proc)
    assert _typing(_calls(log)) == CLEAR + FOLLOW, \
        f"(e) Log: {_runner_log(proj)!r} Aufrufe: {_calls(log)}"


# --- AC-16 ------------------------------------------------------------------

def test_second_stop_after_since_aborts(tmp_path):
    # (a) eigener Stop (at <= since) loest keinen Abbruch aus
    proj, log, env, _ = _case(tmp_path, "own-stop", STUB_SESSION_DELAY="0.3")
    since = time.time()
    _write_marker(_marker(proj, PANE, "stop"), at=since - 0.01)
    proc = _start_v12(proj, env, since_raw=repr(since), grace=0.5)
    _finish(proc)
    assert _typing(_calls(log)) == CLEAR + FOLLOW, \
        f"(a) Log: {_runner_log(proj)!r} Aufrufe: {_calls(log)}"

    # (b) weiterer Stop nach since (fremder Stop-Hook setzte den Turn fort): nichts tippen
    proj, log, env, _ = _case(tmp_path, "second-stop", STUB_SESSION_DELAY="0.3")
    since = time.time()
    _write_marker(_marker(proj, PANE, "stop"), at=since - 0.01)
    proc = _start_v12(proj, env, since_raw=repr(since), grace=2.0)
    time.sleep(0.8)
    _write_marker(_marker(proj, PANE, "stop"), at=time.time())
    _finish(proc)
    assert _typed_or_prompted(_calls(log)) == [], \
        f"(b) trotz zweitem Stop getippt: {_calls(log)}"
    assert WORKING in _runner_log(proj), f"(b) {_runner_log(proj)!r}"

    # (c) Stop nach t_clear + Toleranz: kein Folgebefehl
    proj, log, env, root = _case(tmp_path, "stop-after-clear", STUB_SESSION_DELAY="3.4")
    env["STUB_CLEAR_HOOK"] = str(_clear_hook_writing(
        root, _marker(proj, PANE, "stop"), TOLERANCE_S + 0.6))
    proc = _start_v12(proj, env, since_raw=repr(time.time()), idle_timeout=7)
    _finish(proc)
    assert _typing(_calls(log)) == CLEAR, \
        f"(c) Log: {_runner_log(proj)!r} Aufrufe: {_calls(log)}"
    assert WORKING in _runner_log(proj), f"(c) {_runner_log(proj)!r}"


# --- AC-17 ------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["input", "activity", "stop"])
def test_activity_during_wait_for_clear_prevents_followup(tmp_path, kind):
    proj, log, env, root = _case(tmp_path, f"wait-{kind}", STUB_SESSION_DELAY="4.5")
    fields = {"kind": "pretooluse"} if kind == "activity" else {}
    env["STUB_CLEAR_HOOK"] = str(_clear_hook_writing(
        root, _marker(proj, PANE, kind), TOLERANCE_S + 0.6, **fields))
    session = _marker(proj, PANE, "session")
    proc = _start_v12(proj, env, since_raw=repr(time.time()), idle_timeout=8)
    _finish(proc)
    # Abbruch waehrend des Wartens: der SessionStart(clear)-Marker kam noch gar nicht
    assert not session.exists(), \
        f"Runner wartete bis SessionStart(clear) statt beim Signal abzubrechen: {_runner_log(proj)!r}"
    assert _wait_for(session.exists, 6), "Stub schrieb den SessionStart-Marker nicht"
    time.sleep(0.5)
    assert _typing(_calls(log)) == CLEAR, \
        f"Log: {_runner_log(proj)!r} Aufrufe: {_calls(log)}"
    assert "ABBRUCH" in _runner_log(proj)
    reason = TYPED_ON if kind == "input" else WORKING
    assert reason in _runner_log(proj), _runner_log(proj)


# --- AC-18 ------------------------------------------------------------------

def _run_guard(env: dict, proc_cwd: Path, *, payload_cwd: "Path | None", tool: str = "Read",
               tool_input: "dict | None" = None, raw: "str | None" = None):
    if raw is None:
        payload = {"session_id": "sess-506", "hook_event_name": "PreToolUse",
                   "tool_name": tool, "tool_input": tool_input or {"file_path": "x.txt"}}
        if payload_cwd is not None:
            payload["cwd"] = str(payload_cwd)
        raw = json.dumps(payload)
    return subprocess.run([sys.executable, str(GUARD), "guard"], input=raw,
                          capture_output=True, text=True, env=env, cwd=str(proc_cwd),
                          timeout=30)


BLOCK_CALL = {"tool": "Bash", "tool_input": {"command": "echo hallo"}}


def _guard_case(tmp_path: Path, label: str, *, herdr_env, pane):
    root = tmp_path / label
    root.mkdir()
    proj = _project(root)
    env = _hook_env(proj, root, herdr_env=herdr_env, pane=pane)
    return root, proj, env


def test_pretooluse_guard_writes_activity_marker_silently(tmp_path, monkeypatch):
    # Baseline ohne Herdr: Exit-Code/Ausgabe des Guards (erlaubt bzw. blockiert)
    root, proj, env = _guard_case(tmp_path, "baseline", herdr_env=None, pane=None)
    base_ok = _run_guard(env, root, payload_cwd=proj)
    base_block = _run_guard(env, root, payload_cwd=proj, **BLOCK_CALL)
    assert base_ok.returncode == 0, base_ok.stderr
    assert base_block.returncode == 2, "Vorbedingung: Guard blockt Bash im Haupt-Repo"
    assert _signal_files(proj) == []

    # Mit Pane: erlaubter Aufruf schreibt activity(pretooluse), still, Exit unveraendert
    root, proj, env = _guard_case(tmp_path, "with-pane", herdr_env="1", pane=PANE)
    before = time.time()
    res = _run_guard(env, root, payload_cwd=proj)
    after = time.time()
    assert (res.returncode, res.stdout, res.stderr) == \
        (base_ok.returncode, base_ok.stdout, base_ok.stderr)
    act = _marker(proj, PANE, "activity")
    assert act.is_file(), f"guard schrieb kein {act.name}: {_signal_files(proj)}"
    data = json.loads(act.read_text())
    assert data.get("kind") == "pretooluse", data
    assert isinstance(data.get("at"), (int, float)) and before - 1 <= data["at"] <= after + 1

    # Auch wenn der Guard blockt: Marker liegt vor, Block-Verhalten unveraendert
    act.unlink()
    before = time.time()
    res = _run_guard(env, root, payload_cwd=proj, **BLOCK_CALL)
    assert (res.returncode, res.stdout, res.stderr) == \
        (base_block.returncode, base_block.stdout, base_block.stderr)
    assert act.is_file(), f"kein activity-Marker beim blockierten Aufruf: {_signal_files(proj)}"
    data = json.loads(act.read_text())
    assert data.get("kind") == "pretooluse" and data["at"] >= before - 1, data

    # Ohne Pane-Id bzw. ohne HERDR_ENV=1: keine Datei
    for label, herdr_env, pane in (("g-no-pane", "1", None), ("g-env-0", "0", PANE)):
        root, proj, env = _guard_case(tmp_path, label, herdr_env=herdr_env, pane=pane)
        assert _run_guard(env, root, payload_cwd=proj).returncode == 0
        assert _signal_files(proj) == [], (label, _signal_files(proj))

    # Nicht schreibbares Markerverzeichnis: fail-open, Ausgabe/Exit wie Baseline
    root, proj, env = _guard_case(tmp_path, "g-unwritable", herdr_env="1", pane=PANE)
    _signals(proj).write_text("keine Verzeichnis")
    for kw, base in (({}, base_ok), (BLOCK_CALL, base_block)):
        res = _run_guard(env, root, payload_cwd=proj, **kw)
        assert (res.returncode, res.stdout, res.stderr) == \
            (base.returncode, base.stdout, base.stderr)
    assert _signals(proj).read_text() == "keine Verzeichnis"

    # Marker-Write: unter 50 ms je Aufruf, kein Subprozess, kein sleep
    root, proj, _ = _guard_case(tmp_path, "g-timing", herdr_env="1", pane=PANE)
    monkeypatch.syspath_prepend(str(HOOKS_DIR))
    for key in [k for k in os.environ if k.startswith(("HERDR_", "CLAUDE_"))]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", PANE)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    import herdr_bridge

    def _forbidden(*_a, **_k):
        raise AssertionError("record_signal startet Subprozess bzw. schlaeft")

    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(time, "sleep", _forbidden)
    durations = []
    for _ in range(20):
        t0 = time.perf_counter()
        herdr_bridge.record_signal("activity", "pretooluse", cwd=str(proj))
        durations.append(time.perf_counter() - t0)
    data = json.loads(_marker(proj, PANE, "activity").read_text())
    assert data.get("kind") == "pretooluse", data
    assert max(durations) < 0.05, f"Marker-Write zu langsam: {max(durations) * 1000:.1f} ms"


# --- AC-19 ------------------------------------------------------------------

_OMIT_RE = r"(weggelassen|entf(ae|ä)llt|nicht registriert|existiert nicht|gibt es nicht)"


def _unreleased_changelog() -> str:
    text = CHANGELOG.read_text()
    start = text.index("## [Unreleased]")
    end = text.find("\n## [", start + 1)
    return text[start:end if end != -1 else len(text)]


def _run_signal_cli(env: dict, proc_cwd: Path, raw: str):
    return subprocess.run([sys.executable, str(BRIDGE), "signal", "activity"], input=raw,
                          capture_output=True, text=True, env=env, cwd=str(proc_cwd),
                          timeout=30)


def test_signal_activity_cli_and_hooks_json_registration(tmp_path):
    import re as _re

    # hooks.json: Eintrag je Event oder (spec-konform) begruendete Auslassung im CHANGELOG
    hooks = json.loads(HOOKS_JSON.read_text())["hooks"]
    unreleased = _unreleased_changelog()
    registered = 0
    for event in ("Notification", "PermissionRequest"):
        groups = hooks.get(event)
        if groups is None:
            assert _re.search(rf"{event}.{{0,300}}{_OMIT_RE}|{_OMIT_RE}.{{0,300}}{event}",
                              unreleased, _re.S), \
                f"{event} weder in hooks/hooks.json registriert noch im CHANGELOG begruendet"
            continue
        signal = [(g.get("matcher"), h) for g in groups for h in g.get("hooks", [])
                  if "herdr_bridge.py signal activity" in h.get("command", "")]
        assert signal, f"{event}: kein Eintrag mit `herdr_bridge.py signal activity`: {groups}"
        for matcher, hook in signal:
            assert hook["command"] == \
                "${CLAUDE_PLUGIN_ROOT}/core/hooks/herdr_bridge.py signal activity", hook
            assert hook.get("timeout") == 5, hook
            if event == "Notification":
                assert matcher == "permission_prompt", \
                    f"Notification-Matcher muss `permission_prompt` sein (nicht idle_prompt): {matcher!r}"
        registered += 1
    for g in hooks.get("Notification", []):
        assert "idle_prompt" not in str(g.get("matcher") or ""), g

    # CLI `signal activity`: Marker im Payload-cwd, kind je Event, still, Exit 0
    for event, kind, extra in (
            ("Notification", "notification", {"notification_type": "permission_prompt",
                                              "message": "Claude needs your permission"}),
            ("PermissionRequest", "permission", {"tool_name": "Bash",
                                                 "tool_input": {"command": "ls"}})):
        root = tmp_path / f"cli-{kind}"
        root.mkdir()
        proj = _project(root)
        env = _hook_env(proj, root, herdr_env="1", pane=PANE)
        payload = {"session_id": "sess-506", "cwd": str(proj), "hook_event_name": event, **extra}
        before = time.time()
        res = _run_signal_cli(env, root, json.dumps(payload))
        after = time.time()
        assert (res.returncode, res.stdout, res.stderr) == (0, "", ""), res
        act = _marker(proj, PANE, "activity")
        assert act.is_file(), f"{event}: `signal activity` schrieb kein {act.name}: " \
                              f"{_signal_files(proj)}"
        data = json.loads(act.read_text())
        assert data.get("kind") == kind, data
        assert isinstance(data.get("at"), (int, float)) and before - 1 <= data["at"] <= after + 1

        # ohne Pane-Id: nichts
        env_np = _hook_env(proj, root, herdr_env="1", pane=None)
        act.unlink()
        res = _run_signal_cli(env_np, root, json.dumps(payload))
        assert (res.returncode, res.stdout, res.stderr) == (0, "", ""), res
        assert _signal_files(proj) == [], _signal_files(proj)

        # ungueltiger Payload: nichts, still, Exit 0
        for raw in ("kein json", "[]", ""):
            res = _run_signal_cli(env, root, raw)
            assert (res.returncode, res.stdout, res.stderr) == (0, "", ""), (raw, res)
            assert _signal_files(proj) == [], (raw, _signal_files(proj))


# --- AC-20 ------------------------------------------------------------------

def _run_footer(env: dict, proc_cwd: Path, proj: Path, message: str, **fields):
    payload = {"session_id": "sess-506", "hook_event_name": "Stop", "cwd": str(proj),
               "last_assistant_message": message,
               "prompt_id": "11111111-2222-3333-4444-555555555555", **fields}
    return subprocess.run([sys.executable, str(FOOTER_GATE)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, cwd=str(proc_cwd),
                          timeout=30)


WRONG_FOOTER = _footer_message("/70-deploy #506")


def _footer_case(tmp_path: Path, label: str, *, herdr: bool = True, boundary: bool = False,
                 **extra):
    root = tmp_path / label
    root.mkdir()
    fields = {}
    if boundary:
        fields["auto_clear_boundary"] = {"phase": PHASE, "command": CMD,
                                         "at": datetime.now().isoformat()}
    proj = _project(root, **fields)
    log = root / "stub.log"
    stub = _make_stub(root)
    if herdr:
        extra.setdefault("STUB_SESSION_MARKER", str(_marker(proj, PANE, "session")))
        extra.setdefault("STUB_SESSION_DELAY", "0.3")
        extra.setdefault("STUB_BLOCKED", "1")
    return root, proj, log, _env(proj, log, stub, herdr=herdr, **extra)


def _assert_stop_marker(proj: Path, before: float, after: float, label: str) -> float:
    stop = _marker(proj, PANE, "stop")
    assert stop.is_file(), f"{label}: footer_gate schrieb kein {stop.name}: {_signal_files(proj)}"
    at = json.loads(stop.read_text()).get("at")
    assert isinstance(at, (int, float)) and before - 1 <= at <= after + 1, (label, at)
    return at


def test_footer_gate_writes_stop_marker_on_all_paths(tmp_path):
    # Baseline ohne Herdr: Exit-Codes/Ausgaben der Pfade
    root, proj, _, env = _footer_case(tmp_path, "f-base-ok", herdr=False)
    base_ok = _run_footer(env, root, proj, _footer_message())
    root, proj, _, env = _footer_case(tmp_path, "f-base-block", herdr=False)
    base_block = _run_footer(env, root, proj, WRONG_FOOTER)
    assert base_ok.returncode == 0, base_ok.stderr
    assert base_block.returncode == 2, "Vorbedingung: falsche Fusszeile blockt"

    # Jeder Pfad schreibt den Stop-Marker, Gate-Verhalten unveraendert
    paths = (
        ("f-ok", {}, _footer_message(), {}, base_ok),
        ("f-block", {}, WRONG_FOOTER, {}, base_block),
        ("f-stop-active", {}, WRONG_FOOTER, {"stop_hook_active": True}, None),
        ("f-disabled", {"OPENSPEC_FRAMEWORK": "off"}, WRONG_FOOTER, {}, None),
        ("f-no-footer", {}, "Nur Text, keine Fusszeile.", {}, None),
    )
    for label, extra_env, message, fields, base in paths:
        root, proj, _, env = _footer_case(tmp_path, label, **extra_env)
        before = time.time()
        res = _run_footer(env, root, proj, message, **fields)
        after = time.time()
        if base is not None:
            assert (res.returncode, res.stdout, res.stderr) == \
                (base.returncode, base.stdout, base.stderr), label
        else:
            assert res.returncode == 0, (label, res.stderr)
        _assert_stop_marker(proj, before, after, label)

    # Marker nicht schreibbar: Exit-Code und Ausgabe des Gates unveraendert
    for label, message, base in (("f-unw-ok", _footer_message(), base_ok),
                                 ("f-unw-block", WRONG_FOOTER, base_block)):
        root, proj, _, env = _footer_case(tmp_path, label)
        _signals(proj).write_text("keine Verzeichnis")
        res = _run_footer(env, root, proj, message)
        assert (res.returncode, res.stdout, res.stderr) == \
            (base.returncode, base.stdout, base.stderr), label
        assert _signals(proj).read_text() == "keine Verzeichnis"

    # since nach dem Stop-Marker: der eigene Stop bricht den gespawnten Runner nicht ab
    root, proj, log, env = _footer_case(tmp_path, "f-spawn", boundary=True)
    before = time.time()
    res = _run_footer(env, root, proj, _footer_message())
    after = time.time()
    assert res.returncode == 0, res.stderr
    _assert_stop_marker(proj, before, after, "f-spawn")
    assert _wait_for(lambda: ("OK" in _runner_log(proj) or "ABBRUCH" in _runner_log(proj)), 30), \
        f"Runner nicht gelaufen: {_runner_log(proj)!r}"
    assert "OK" in _runner_log(proj), \
        f"eigener Stop brach den Runner ab (since vor dem Stop-Marker?): {_runner_log(proj)!r}"
    assert _typing(_calls(log)) == CLEAR + FOLLOW, _calls(log)


# --- AC-21 ------------------------------------------------------------------

INVALID_SINCE = ("nan", "inf", "-inf", "keine-zahl", "0", "-5", "zukunft")


def test_since_validation_falls_back_to_runner_start(tmp_path):
    def _raw(value: str) -> str:
        return repr(time.time() + 60) if value == "zukunft" else value

    runs = []
    for i, value in enumerate(INVALID_SINCE):
        # (i) Marker nach dem verworfenen Wert, aber vor Runner-Start: zaehlt nicht
        proj, log, env, _ = _case(tmp_path, f"stale-{i}", STUB_SESSION_DELAY="0.3")
        _write_marker(_marker(proj, PANE, "input"), at=time.time() - 10)
        runs.append(("stale", value, proj, log, _start_v12(proj, env, since_raw=_raw(value))))
        # (ii) Marker nach Runner-Start (Grace-Zeit): wird weiterhin erkannt
        proj, log, env, _ = _case(tmp_path, f"fresh-{i}", STUB_SESSION_DELAY="0.3")
        runs.append(("fresh", value, proj, log,
                     _start_v12(proj, env, since_raw=_raw(value), grace=4.0)))
    # gueltig, knapp in der Zukunft (<= jetzt + 5 s): unveraendert uebernommen,
    # eine Eingabe davor zaehlt also nicht
    proj, log, env, _ = _case(tmp_path, "valid-near-future", STUB_SESSION_DELAY="0.3")
    runs.append(("near-future", "jetzt+4", proj, log,
                 _start_v12(proj, env, since_raw=repr(time.time() + 4.0), grace=2.0)))
    # gueltig, in der Vergangenheit: Eingabe zwischen since und Runner-Start zaehlt
    proj, log, env, _ = _case(tmp_path, "valid-past", STUB_SESSION_DELAY="0.3")
    since = time.time() - 3
    _write_marker(_marker(proj, PANE, "input"), at=since + 1)
    runs.append(("past", "jetzt-3", proj, log,
                 _start_v12(proj, env, since_raw=repr(since), grace=0.5)))

    time.sleep(2.0)  # alle Runner gestartet, die fresh-/near-future-Runner noch in grace
    for kind, _, proj, _, _ in runs:
        if kind in ("fresh", "near-future"):
            _write_marker(_marker(proj, PANE, "input"), at=time.time())

    failures = []
    for kind, value, proj, log, proc in runs:
        _finish(proc)
        text = _runner_log(proj)
        typing = _typing(_calls(log))
        if kind == "stale":
            if typing != CLEAR + FOLLOW:
                failures.append(f"--since={value} (Marker vor Runner-Start): erwartet voller "
                                f"Lauf, Log {text.strip()!r}")
        elif kind == "fresh":
            if typing or TYPED_ON not in text:
                failures.append(f"--since={value} (Marker nach Runner-Start): erwartet Abbruch "
                                f"'{TYPED_ON}', getippt {typing}, Log {text.strip()!r}")
        elif kind == "near-future":
            if typing[:2] != CLEAR:
                failures.append(f"--since={value}: gueltiger Wert nicht uebernommen, "
                                f"Log {text.strip()!r}")
        elif typing or TYPED_ON not in text:
            failures.append(f"--since={value}: gueltiger Wert nicht uebernommen, "
                            f"Log {text.strip()!r}")
        if kind in ("stale", "fresh") and "since" not in text.lower():
            failures.append(f"--since={value}: kein Vermerk zum verworfenen --since im Log "
                            f"({text.strip()!r})")
    assert failures == [], "\n".join(failures)


# --- AC-22 ------------------------------------------------------------------

def _worktree(root: Path, proj: Path) -> "tuple[Path, Path]":
    gitdir = proj / ".git" / "worktrees" / "wt-506"
    gitdir.mkdir(parents=True)
    wt = root / "wt-506"
    (wt / "sub").mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {gitdir}\n")
    return wt, wt / "sub"


def _base_for(cwd: Path, env: dict) -> Path:
    """Basisordner, den Spawner/Runner (`_ac_base`) fuer dieses cwd verwenden."""
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import herdr_bridge; "
            "print(herdr_bridge._ac_base())")
    res = subprocess.run([sys.executable, "-c", code, str(HOOKS_DIR)], capture_output=True,
                         text=True, env=env, cwd=str(cwd), timeout=30)
    assert res.returncode == 0, res.stderr
    return Path(res.stdout.strip())


def test_markers_use_payload_cwd_base(tmp_path):
    root = tmp_path / "wtcase"
    root.mkdir()
    proj = _project(root)
    wt, sub = _worktree(root, proj)
    env = _hook_env(proj, root, herdr_env="1", pane=PANE)
    base = _base_for(sub, env)
    assert base == wt, f"Vorbedingung: _ac_base fuer den Worktree ist {base}"
    assert _base_for(proj, env) == proj

    def _wt_marker(kind):
        return base / ".claude" / AC_SIGNAL_DIR_NAME / f"{PANE}.{kind}.json"

    # Prozess-cwd = Haupt-Repo, Payload-cwd = Worktree-Unterordner
    res = _run_listener(proj, env, raw=json.dumps(
        {"prompt": "weiter", "session_id": "sess-506", "cwd": str(sub),
         "hook_event_name": "UserPromptSubmit"}))
    assert res.returncode == 0, res.stderr
    res = _run_banner(proj, env, raw=json.dumps(
        {"session_id": "sess-506", "cwd": str(sub), "hook_event_name": "SessionStart",
         "source": "clear"}))
    assert res.returncode == 0, res.stderr
    res = _run_guard(env, proj, payload_cwd=sub)
    assert res.returncode == 0, res.stderr
    guard_kind = (json.loads(_wt_marker("activity").read_text()).get("kind")
                  if _wt_marker("activity").is_file() else None)
    res = _run_footer(env, proj, sub, _footer_message())
    assert res.returncode == 0, res.stderr
    res = _run_signal_cli(env, proj, json.dumps(
        {"session_id": "sess-506", "cwd": str(sub), "hook_event_name": "Notification",
         "notification_type": "permission_prompt"}))
    assert res.returncode == 0, res.stderr

    missing = [k for k in ("input", "session", "activity", "stop") if not _wt_marker(k).is_file()]
    assert missing == [], \
        f"Marker fehlen im Worktree-Basisordner {base}: {missing}; " \
        f"Worktree: {_signal_files(wt)}, Haupt-Repo: {_signal_files(proj)}"
    assert guard_kind == "pretooluse", guard_kind
    assert json.loads(_wt_marker("activity").read_text()).get("kind") == "notification"
    assert json.loads(_wt_marker("session").read_text()).get("source") == "clear"
    assert _signal_files(proj) == [], f"Marker im Haupt-Repo statt im Worktree: {_signal_files(proj)}"

    # Der Runner (gestartet wie vom Spawner im Basisordner) findet die Eingabe-Marke
    for p in (base / ".claude" / AC_SIGNAL_DIR_NAME).iterdir():
        p.unlink()
    log = root / "stub.log"
    renv = _env(proj, log, root / "herdr-stub", STUB_BLOCKED="1",
                STUB_SESSION_MARKER=str(_wt_marker("session")), STUB_SESSION_DELAY="0.3")
    proc = _start_v12(proj, renv, cwd=base, since_raw=repr(time.time()), grace=2.5)
    time.sleep(0.8)
    res = _run_listener(proj, env, raw=json.dumps(
        {"prompt": "noch eine Frage", "session_id": "sess-506", "cwd": str(sub),
         "hook_event_name": "UserPromptSubmit"}))
    assert res.returncode == 0, res.stderr
    _finish(proc)
    wt_log = base / ".claude" / "herdr_auto_clear.log"
    text = wt_log.read_text() if wt_log.exists() else ""
    assert _typed_or_prompted(_calls(log)) == [], \
        f"Runner fand die Eingabe-Marke des Worktrees nicht: {_calls(log)} Log {text!r}"
    assert TYPED_ON in text, text

    # Ohne cwd im Payload gilt der Prozess-cwd
    for p in (base / ".claude" / AC_SIGNAL_DIR_NAME).iterdir():
        p.unlink()
    res = _run_listener(sub, env, raw=json.dumps(
        {"prompt": "weiter", "session_id": "sess-506", "hook_event_name": "UserPromptSubmit"}))
    assert res.returncode == 0, res.stderr
    assert _wt_marker("input").is_file(), \
        f"ohne Payload-cwd: kein Marker im Basisordner des Prozess-cwd: {_signal_files(wt)}"


AC_SIGNAL_DIR_NAME = "herdr_signals"
