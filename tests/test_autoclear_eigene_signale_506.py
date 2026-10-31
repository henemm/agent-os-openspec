"""Auto-/clear mit eigenen Plugin-Signalen statt Herdr-Status (Issue #506).

Spec: docs/specs/fix-506-autoclear-ohne-herdr-status.md v1.1 (AC-1 bis AC-10 und
AC-14; AC-11 ist der Regressionslauf, AC-12/AC-13 das E2E-Skript).

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
