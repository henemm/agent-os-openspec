"""Herdr Auto-/clear an Phasengrenzen (Issue #467) — Tests gegen ein Stub-Binary.

Spec: docs/specs/feat-467-herdr-auto-clear.md (AC-1 bis AC-17).

Das verzweigende Stub-Binary (bash) protokolliert jeden Aufruf NUL-getrennt in
STUB_LOG und verzweigt nach Unterbefehl:
- `agent wait`: konsumiert pro Aufruf eine Zeile aus der Sequenzdatei STUB_SEQ
  (`exit|stdout-json|stderr-json|hook-skript`); leere/fehlende Sequenz = Status
  idle, Exit 0. Das optionale Hook-Skript laeuft vor der Ausgabe (State-Umbau).
- `agent prompt`: Exit 0; fuer den Text `/clear` Exit ${STUB_CLEAR_EXIT:-0}.
- alles andere (z.B. `notification show`): Exit 0.
- STUB_SLEEP: Schlaf vor jeder Verzweigung (Haengen des Binarys).

Vertraege, die diese Tests festlegen (die Spec nennt sie nicht exakt):
- `agent wait` liefert auf stdout `{"result": {"agent": {"status": "<s>", ...}}}`.
- Runner-CLI: `herdr_bridge.py auto-clear --pane P --workflow W --phase PH
  --command C --grace 0 --settle 0 --idle-timeout 5 --announce 0`; `--idle-timeout`
  in Sekunden (-> `--timeout 5000`), `--announce 0` = keine Vorankuendigung.
- Once-Lock `.claude/herdr_auto_clear_state.json`: flaches JSON-Objekt
  `{"<workflow>|<phase>|<befehl>": <epoch-sekunden als Zahl>}`.
- `has_clear_marker(message) -> bool` (reine Funktion in herdr_bridge).

Importfehler/fehlende Funktionen erscheinen als Test-FAIL: Module werden erst im
Testkoerper importiert, Runner und Hook laufen als Subprozess.
"""

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
BRIDGE = HOOKS_DIR / "herdr_bridge.py"
FOOTER_GATE = HOOKS_DIR / "footer_gate.py"

PANE = "pane-467"
WF = "feat-467-herdr-auto-clear"
PHASE = "phase6_implement"
CMD = "/50-implement #467"
IDLE_TIMEOUT = 5

# `wait`-Fehler fuer den Timeout-Fall; die Felder sind bewusst frei gewaehlt.
TIMEOUT_ERR = '{"error": {"code": "timeout", "message": "agent wait timed out"}}'

STUB_SCRIPT = r"""#!/bin/bash
{ for a in "$@"; do printf '%s\0' "$a"; done; printf '\n'; } >> "$STUB_LOG"
if [ -n "$STUB_SLEEP" ]; then sleep "$STUB_SLEEP"; fi
if [ "$1 $2" = "agent wait" ]; then
  code=0; out='{"result":{"agent":{"status":"idle"}}}'; err=""; hook=""
  if [ -n "$STUB_SEQ" ] && [ -s "$STUB_SEQ" ]; then
    IFS='|' read -r code out err hook < "$STUB_SEQ"
    tail -n +2 "$STUB_SEQ" > "$STUB_SEQ.tmp"; mv "$STUB_SEQ.tmp" "$STUB_SEQ"
  fi
  if [ -n "$hook" ]; then bash "$hook"; fi
  if [ -n "$out" ]; then printf '%s\n' "$out"; fi
  if [ -n "$err" ]; then printf '%s\n' "$err" >&2; fi
  exit "${code:-0}"
fi
if [ "$1 $2" = "agent prompt" ]; then
  if [ "$4" = "/clear" ]; then exit "${STUB_CLEAR_EXIT:-0}"; fi
  exit 0
fi
exit 0
"""

AUTO_ON = ("herdr:\n  auto_clear:\n    enabled: true\n    grace_s: 0\n"
           "    idle_timeout_s: 5\n    announce: true\n")


# --- Helpers ---------------------------------------------------------------

def _make_stub(tmp_path: Path, name: str = "herdr-stub") -> Path:
    stub = tmp_path / name
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


def _env(proj: Path, log: Path, stub, *, herdr: bool = True, **extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    if herdr:
        env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": PANE,
                    "HERDR_BIN_PATH": str(stub), "STUB_LOG": str(log)})
    env.update(extra)
    return env


def _calls(log: Path) -> list:
    if not log.exists():
        return []
    out = []
    for line in log.read_bytes().decode("utf-8", "replace").split("\n"):
        if line:
            out.append(line.split("\0")[:-1] if line.endswith("\0") else line.split("\0"))
    return out


def _wait_calls(log: Path, n: int = 1, timeout: float = 3.0) -> list:
    deadline = time.monotonic() + timeout
    calls = _calls(log)
    while len(calls) < n and time.monotonic() < deadline:
        time.sleep(0.05)
        calls = _calls(log)
    return calls


def _assert_no_calls(log: Path):
    time.sleep(0.8)
    assert _calls(log) == [], f"Stub wurde unerwartet aufgerufen: {_calls(log)}"


def _flag_values(args: list, flag: str) -> list:
    return [args[i + 1] for i, a in enumerate(args) if a == flag and i + 1 < len(args)]


def _kind(args: list) -> str:
    return " ".join(args[:2])


def _prompts(calls: list) -> list:
    return [c for c in calls if _kind(c) == "agent prompt"]


def _waits(calls: list) -> list:
    return [c for c in calls if _kind(c) == "agent wait"]


def _wait_line(status: str = "idle", code: int = 0, err: str = "", hook: str = "") -> str:
    out = json.dumps({"result": {"agent": {"status": status}}}) if code == 0 else ""
    return f"{code}|{out}|{err}|{hook}"


def _seq(tmp: Path, *lines: str) -> Path:
    path = tmp / "seq.txt"
    path.write_text("\n".join(lines) + "\n")
    return path


def _run_runner(proj: Path, env: dict, *, command: str = CMD, phase: str = PHASE,
                timeout: float = 30) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(BRIDGE), "auto-clear",
            "--pane", PANE, "--workflow", WF, "--phase", phase, "--command", command,
            "--grace", "0", "--settle", "0", "--idle-timeout", str(IDLE_TIMEOUT),
            "--announce", "0"]
    return subprocess.run(argv, capture_output=True, text=True, env=env,
                          cwd=str(proj), timeout=timeout)


def _runner_case(tmp_path: Path, label: str, *seq_lines: str, phase: str = PHASE,
                 **env_extra):
    root = tmp_path / label
    root.mkdir()
    proj = _project(root, phase=phase)
    log = root / "stub.log"
    stub = _make_stub(root)
    extra = dict(env_extra)
    if seq_lines:
        extra["STUB_SEQ"] = str(_seq(root, *seq_lines))
    return proj, log, _env(proj, log, stub, **extra), root


def _runner_log(proj: Path) -> str:
    path = proj / ".claude" / "herdr_auto_clear.log"
    return path.read_text() if path.exists() else ""


def _assert_clean_abort(res, proj):
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr
    assert _runner_log(proj).strip(), "Abbruch ohne Log-Eintrag in herdr_auto_clear.log"


def _state_changer(root: Path, name: str = "change.sh") -> Path:
    """Hook-Skript: setzt den Workflow auf phase7_validate (anderer erwarteter Befehl)."""
    wf = root / "proj" / ".claude" / "workflows" / f"{WF}.json"
    script = root / name
    script.write_text(
        "python3 - <<'EOF'\n"
        "import json\n"
        f"p = {str(wf)!r}\n"
        "d = json.load(open(p))\n"
        "d['current_phase'] = 'phase7_validate'\n"
        "json.dump(d, open(p, 'w'))\n"
        "EOF\n")
    return script


# --- Hook-Helpers ----------------------------------------------------------

POSITIVE = "✅ **`/clear` ist jetzt gefahrlos** — alles auf Platte gesichert."
NEGATIVE = "⚠️ **`/clear` jetzt NICHT** — Hintergrund-Agent laeuft noch."


def _du(command: str = CMD) -> str:
    return f"❗ Du: `{command}` — der naechste Pflicht-Schritt"


def _message(*blocks: str, du: str = "") -> str:
    return "\n\n".join(["Phase abgeschlossen.", *blocks, du or _du(),
                        "⚙ /40-tdd-red · agent-os-openspec 3.43.1"])


def _run_hook(proj: Path, env: dict, message: str, **payload_extra):
    payload = {"session_id": "sess-467", "hook_event_name": "Stop", "cwd": str(proj),
               "last_assistant_message": message,
               "prompt_id": "11111111-2222-3333-4444-555555555555"}
    payload.update(payload_extra)
    return subprocess.run([sys.executable, str(FOOTER_GATE)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, cwd=str(proj),
                          timeout=30)


def _hook_case(tmp_path: Path, *, config: "str | None" = AUTO_ON, herdr: bool = True,
               phase: str = PHASE, **fields):
    proj = _project(tmp_path, phase=phase, config=config, **fields)
    log = tmp_path / "stub.log"
    stub = _make_stub(tmp_path)
    return proj, log, stub, _env(proj, log, stub, herdr=herdr)


def _baseline(tmp_path: Path, message: str, phase: str = PHASE, **fields):
    """Gleiches Szenario ausserhalb von Herdr = Verhalten ohne Feature."""
    root = tmp_path / "baseline"
    root.mkdir()
    proj, log, stub, env = _hook_case(root, herdr=False, phase=phase, **fields)
    return _run_hook(proj, env, message)


def _notifications(log: Path) -> list:
    return [c for c in _calls(log) if _kind(c) == "notification show"]


# --- AC-1 -------------------------------------------------------------------

def test_hook_spawns_runner_and_returns_immediately(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path)
    env["STUB_SLEEP"] = "6"  # haengendes Binary
    msg = _message(POSITIVE)
    start = time.monotonic()
    res = _run_hook(proj, env, msg)
    elapsed = time.monotonic() - start
    assert elapsed < 3.0, f"footer_gate wartete auf den Runner/das Stub: {elapsed:.2f}s"
    base = _baseline(tmp_path, msg)
    assert res.returncode == 0 == base.returncode, res.stderr
    assert res.stdout == base.stdout
    calls = _wait_calls(log, 1)
    assert calls, "Kein Runner gespawnt (Stub nie aufgerufen)"
    assert calls[0][:2] == ["notification", "show"], calls[0]


# --- AC-2 -------------------------------------------------------------------

def test_runner_exact_sequence_and_flags(tmp_path):
    proj, log, env, _ = _runner_case(tmp_path, "seq", _wait_line("idle"), _wait_line("done"))
    res = _run_runner(proj, env)
    assert res.returncode == 0, res.stderr
    calls = _calls(log)
    assert [_kind(c) for c in calls] == ["agent wait", "agent prompt",
                                         "agent wait", "agent prompt"], calls
    w1, p1, w2, p2 = calls
    for w in (w1, w2):
        assert w[:3] == ["agent", "wait", PANE], w
        assert _flag_values(w, "--until") == ["idle", "done"], w
        assert _flag_values(w, "--timeout") == [str(IDLE_TIMEOUT * 1000)], w
    assert p1 == ["agent", "prompt", PANE, "/clear"], p1
    assert p2 == ["agent", "prompt", PANE, CMD], p2
    for p in (p1, p2):
        assert "--wait" not in p, p


# --- AC-3 -------------------------------------------------------------------

@pytest.mark.parametrize("label,config", [
    ("missing", None),
    ("no-section", "herdr:\n  enabled: true\n"),
    ("false", "herdr:\n  auto_clear:\n    enabled: false\n"),
    ("string-true", 'herdr:\n  auto_clear:\n    enabled: "true"\n'),
])
def test_no_spawn_when_auto_clear_not_enabled(tmp_path, label, config):
    root = tmp_path / label
    root.mkdir()
    proj, log, stub, env = _hook_case(root, config=config)
    msg = _message(POSITIVE)
    res = _run_hook(proj, env, msg)
    base = _baseline(tmp_path / label, msg)
    assert res.returncode == base.returncode == 0, res.stderr
    assert res.stdout == base.stdout
    _assert_no_calls(log)


# --- AC-4 -------------------------------------------------------------------

def test_no_spawn_when_herdr_disabled(tmp_path):
    cfg = "herdr:\n  enabled: false\n  auto_clear:\n    enabled: true\n    grace_s: 0\n"
    proj, log, stub, env = _hook_case(tmp_path, config=cfg)
    res = _run_hook(proj, env, _message(POSITIVE))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)


# --- AC-5 -------------------------------------------------------------------

@pytest.mark.parametrize("missing", ["HERDR_ENV", "HERDR_PANE_ID"])
def test_no_spawn_without_herdr_env(tmp_path, missing):
    proj, log, stub, env = _hook_case(tmp_path)
    env.pop(missing)
    res = _run_hook(proj, env, _message(POSITIVE))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)


# --- AC-6 -------------------------------------------------------------------

def test_no_spawn_when_stop_hook_active(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path)
    res = _run_hook(proj, env, _message(POSITIVE), stop_hook_active=True)
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)


# --- AC-7 -------------------------------------------------------------------

def test_no_spawn_on_wrong_footer_exit_2(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path)
    res = _run_hook(proj, env, _message(POSITIVE, du=_du("/40-tdd-red #467")))
    assert res.returncode == 2, f"Exit 2 erwartet: {res.returncode} {res.stderr!r}"
    _assert_no_calls(log)


# --- AC-8 -------------------------------------------------------------------

def test_no_spawn_without_positive_marker(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path)
    res = _run_hook(proj, env, _message("Alles erledigt, weiter geht es gleich."))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)


# --- AC-9 -------------------------------------------------------------------

def test_no_spawn_with_negative_marker(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path)
    res = _run_hook(proj, env, _message(POSITIVE, NEGATIVE))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)


# --- AC-10 ------------------------------------------------------------------

def test_no_spawn_when_marker_only_in_code_fence(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path)
    fenced = "Beispiel:\n```\n" + POSITIVE + "\n```"
    res = _run_hook(proj, env, _message(fenced))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)


# --- AC-11 ------------------------------------------------------------------

def test_no_spawn_when_expected_step_is_freetext(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path, phase="phase3_spec",
                                      spec_file="docs/specs/x.md")
    res = _run_hook(proj, env, _message(POSITIVE, du="❗ Du: tippe `approved` (danach `/40-tdd-red`)"))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)


# --- AC-12 ------------------------------------------------------------------

def test_once_lock_blocks_duplicate_and_expires_after_10_min(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path)
    msg = _message(POSITIVE)
    res = _run_hook(proj, env, msg)
    assert res.returncode == 0, res.stderr
    assert _wait_calls(log, 1), "Erster Payload spawnte keinen Runner"
    assert len(_notifications(log)) == 1

    res = _run_hook(proj, env, msg)  # identisch -> Lock
    assert res.returncode == 0, res.stderr
    time.sleep(1.0)
    assert len(_notifications(log)) == 1, "Zweiter identischer Payload spawnte erneut"

    lock = proj / ".claude" / "herdr_auto_clear_state.json"
    state = json.loads(lock.read_text())
    key = f"{WF}|{PHASE}|{CMD}"
    assert key in state, state
    state[key] = time.time() - 11 * 60
    lock.write_text(json.dumps(state))

    res = _run_hook(proj, env, msg)  # Lock abgelaufen -> erneut
    assert res.returncode == 0, res.stderr
    deadline = time.monotonic() + 3
    while len(_notifications(log)) < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert len(_notifications(log)) == 2, "Abgelaufener Lock loeste nicht erneut aus"


# --- AC-13 ------------------------------------------------------------------

def test_runner_aborts_on_wait_timeout(tmp_path):
    proj, log, env, _ = _runner_case(tmp_path, "timeout", _wait_line(code=1, err=TIMEOUT_ERR))
    res = _run_runner(proj, env)
    _assert_clean_abort(res, proj)
    assert _prompts(_calls(log)) == [], _calls(log)


# --- AC-14 ------------------------------------------------------------------

@pytest.mark.parametrize("status", ["blocked", "unknown", "working"])
def test_runner_aborts_on_blocked_or_unknown(tmp_path, status):
    proj, log, env, _ = _runner_case(tmp_path, f"first-{status}", _wait_line(status))
    res = _run_runner(proj, env)
    _assert_clean_abort(res, proj)
    assert _prompts(_calls(log)) == [], _calls(log)

    # blockiert erst nach /clear: kein Folgebefehl
    proj2, log2, env2, _ = _runner_case(tmp_path, f"second-{status}",
                                        _wait_line("idle"), _wait_line(status))
    res = _run_runner(proj2, env2)
    _assert_clean_abort(res, proj2)
    assert _prompts(_calls(log2)) == [["agent", "prompt", PANE, "/clear"]], _calls(log2)


# --- AC-15 ------------------------------------------------------------------

def test_runner_aborts_when_state_changed_between_steps(tmp_path):
    # (a) Aenderung waehrend des ersten wait: gar kein Prompt
    root = tmp_path / "a"
    root.mkdir()
    proj = _project(root)
    hook = _state_changer(root)
    log = root / "stub.log"
    env = _env(proj, log, _make_stub(root),
               STUB_SEQ=str(_seq(root, _wait_line("idle", hook=str(hook)), _wait_line("idle"))))
    res = _run_runner(proj, env)
    _assert_clean_abort(res, proj)
    assert _prompts(_calls(log)) == [], _calls(log)

    # (b) Aenderung waehrend des zweiten wait: nur /clear, kein Folgebefehl
    root = tmp_path / "b"
    root.mkdir()
    proj = _project(root)
    hook = _state_changer(root)
    log = root / "stub.log"
    env = _env(proj, log, _make_stub(root),
               STUB_SEQ=str(_seq(root, _wait_line("idle"), _wait_line("idle", hook=str(hook)))))
    res = _run_runner(proj, env)
    _assert_clean_abort(res, proj)
    assert _prompts(_calls(log)) == [["agent", "prompt", PANE, "/clear"]], _calls(log)


# --- AC-16 ------------------------------------------------------------------

def test_runner_aborts_when_clear_prompt_fails(tmp_path):
    proj, log, env, _ = _runner_case(tmp_path, "clearfail", STUB_CLEAR_EXIT="1")
    res = _run_runner(proj, env)
    _assert_clean_abort(res, proj)
    assert _prompts(_calls(log)) == [["agent", "prompt", PANE, "/clear"]], _calls(log)


# --- AC-17 ------------------------------------------------------------------

def test_config_default_auto_clear_disabled():
    import yaml  # noqa: PLC0415
    cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())
    section = cfg["herdr"]["auto_clear"]
    assert section["enabled"] is False
    assert section["grace_s"] == 3
    assert section["idle_timeout_s"] == 120
    assert section["announce"] is True


# --- Zusatz (ohne eigene AC): reine Marker-Funktion --------------------------

def test_has_clear_marker_pure_function():
    sys.path.insert(0, str(HOOKS_DIR))
    import herdr_bridge  # noqa: PLC0415
    f = herdr_bridge.has_clear_marker
    assert f(_message(POSITIVE)) is True
    assert f(_message("✅ `/clear` ist jetzt gefahrlos")) is True        # ohne Bold
    assert f(_message(POSITIVE, NEGATIVE)) is False
    assert f(_message("```\n" + POSITIVE + "\n```")) is False
    assert f("Nichts Besonderes\n" + _du()) is False
    assert f(_du() + "\n" + POSITIVE) is False                            # nach der Du-Zeile
