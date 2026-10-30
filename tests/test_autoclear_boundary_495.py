"""Auto-/clear mechanisch an der Phasengrenze (Issue #495).

Spec: docs/specs/fix-495-autoclear-mechanisch.md (AC-1 bis AC-7; AC-8 = Regressionslauf).

`workflow.py autoclear` vermerkt bei `AUTO_CLEAR=on` und aktivem Workflow die
Grenze `auto_clear_boundary = {phase, command, at}` im Workflow-State; der
Stop-Hook (`footer_gate.py` -> `herdr_bridge.maybe_auto_clear`) loest aus, wenn
dieser Vermerk zu Phase und erwartetem Befehl passt — der Positiv-Satz
„`/clear` ist jetzt gefahrlos“ ist nicht mehr noetig, der Negativ-Satz bleibt Veto.

Hook- und Stub-Helfer aus tests/test_herdr_auto_clear_467.py.
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_herdr_auto_clear_467 import (  # noqa: E402
    AUTO_ON,
    CMD,
    HOOKS_DIR,
    NEGATIVE,
    PHASE,
    WF,
    _assert_no_calls,
    _du,
    _hook_case,
    _message,
    _notifications,
    _run_hook,
    _wait_calls,
)

WORKFLOW = HOOKS_DIR / "workflow.py"
AC_LOG = Path(".claude") / "herdr_auto_clear.log"

# Antwort OHNE Positiv-Satz, aber mit korrekter ❗Du-Zeile
PLAIN = "Phase sauber abgeschlossen, Stand committet."


def _wf_file(proj: Path) -> Path:
    return proj / ".claude" / "workflows" / f"{WF}.json"


def _state(proj: Path) -> dict:
    return json.loads(_wf_file(proj).read_text())


def _boundary(phase: str = PHASE, command: str = CMD, age_s: float = 0) -> dict:
    # `at` relativ zu jetzt: der Vermerk gilt nur 15 min (Sicherheitsnetz, F001)
    at = (datetime.now() - timedelta(seconds=age_s)).isoformat()
    return {"phase": phase, "command": command, "at": at}


def _run_autoclear(proj: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(WORKFLOW), "autoclear"],
                          capture_output=True, text=True, env=env, cwd=str(proj),
                          timeout=30)


def _ac_log(proj: Path) -> str:
    path = proj / AC_LOG
    return path.read_text() if path.exists() else ""


# --- AC-1 -------------------------------------------------------------------

def test_autoclear_on_records_boundary(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path)
    res = _run_autoclear(proj, env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "AUTO_CLEAR=on", res.stdout
    data = _state(proj)
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    expected = workflow.expected_footer_command(data)
    assert expected == CMD, expected
    boundary = data.get("auto_clear_boundary")
    assert isinstance(boundary, dict), f"Kein Vermerk auto_clear_boundary im State: {data}"
    assert boundary.get("phase") == PHASE, boundary
    assert boundary.get("command") == expected, boundary
    assert isinstance(boundary.get("at"), str) and boundary["at"], boundary


# --- AC-2 -------------------------------------------------------------------

def test_autoclear_off_or_no_workflow_records_nothing(tmp_path):
    # (a) Herdr-Pane, aber Auto-/clear aus
    root = tmp_path / "off"
    root.mkdir()
    proj, log, stub, env = _hook_case(root, config="herdr:\n  enabled: true\n")
    res = _run_autoclear(proj, env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "AUTO_CLEAR=off", res.stdout
    assert "auto_clear_boundary" not in _state(proj)

    # (b) Auto-/clear an, aber kein aktiver Workflow: Ausgabe wie bisher, kein Vermerk
    root = tmp_path / "nowf"
    root.mkdir()
    proj, log, stub, env = _hook_case(root, config=AUTO_ON)
    (proj / ".claude" / "active_workflow").unlink()
    env.pop("OPENSPEC_ACTIVE_WORKFLOW")
    res = _run_autoclear(proj, env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "AUTO_CLEAR=on", res.stdout
    assert "Traceback" not in res.stderr, res.stderr
    assert "auto_clear_boundary" not in _state(proj)


# --- AC-3 -------------------------------------------------------------------

def test_spawn_with_boundary_without_positive_marker(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path)
    res = _run_autoclear(proj, env)  # Vermerk ueber den echten CLI-Pfad
    assert res.returncode == 0, res.stderr
    msg = _message(PLAIN, du=_du(CMD))
    assert "gefahrlos" not in msg
    res = _run_hook(proj, env, msg)
    assert res.returncode == 0, res.stderr
    calls = _wait_calls(log, 1)
    assert calls, (f"Kein Runner gespawnt trotz Grenz-Vermerk; Log: {_ac_log(proj)!r}; "
                   f"State-Vermerk: {_state(proj).get('auto_clear_boundary')!r}")
    assert calls[0][:2] == ["notification", "show"], calls[0]
    assert "skip:" not in _ac_log(proj), _ac_log(proj)


# --- AC-4 -------------------------------------------------------------------

def test_no_spawn_without_boundary_logs_reason(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path)
    res = _run_hook(proj, env, _message(PLAIN, du=_du(CMD)))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)
    assert "skip: keine Grenze vermerkt" in _ac_log(proj), _ac_log(proj)


# --- AC-5 -------------------------------------------------------------------

def test_no_spawn_with_stale_phase_or_other_command(tmp_path):
    cases = {
        "stale-phase": _boundary(phase="phase5_tdd_red", command="/40-tdd-red #467"),
        "other-command": _boundary(command="/40-tdd-red #467"),
    }
    for label, boundary in cases.items():
        root = tmp_path / label
        root.mkdir()
        proj, log, stub, env = _hook_case(root, auto_clear_boundary=boundary)
        res = _run_hook(proj, env, _message(PLAIN, du=_du(CMD)))
        assert res.returncode == 0, (label, res.stderr)
        _assert_no_calls(log)


# --- AC-6 -------------------------------------------------------------------

def test_negative_marker_vetoes_boundary(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path, auto_clear_boundary=_boundary())
    res = _run_hook(proj, env, _message(PLAIN, NEGATIVE, du=_du(CMD)))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)


# --- AC-7 -------------------------------------------------------------------

def test_once_lock_single_spawn(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path, auto_clear_boundary=_boundary())
    msg = _message(PLAIN, du=_du(CMD))
    res = _run_hook(proj, env, msg)
    assert res.returncode == 0, res.stderr
    assert _wait_calls(log, 1), f"Erster Stop spawnte keinen Runner; Log: {_ac_log(proj)!r}"
    res = _run_hook(proj, env, msg)
    assert res.returncode == 0, res.stderr
    time.sleep(1.0)
    assert len(_notifications(log)) == 1, _notifications(log)


# --- F001/F002: Vermerk ist Einmal-Signal ------------------------------------

def _age_lock(proj: Path, seconds: float = 601) -> None:
    lock = proj / ".claude" / "herdr_auto_clear_state.json"
    state = json.loads(lock.read_text())
    key = f"{WF}|{PHASE}|{CMD}"
    assert key in state, state
    state[key] = time.time() - seconds
    lock.write_text(json.dumps(state))


def test_boundary_consumed_after_spawn(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path, auto_clear_boundary=_boundary())
    msg = _message(PLAIN, du=_du(CMD))
    res = _run_hook(proj, env, msg)
    assert res.returncode == 0, res.stderr
    assert _wait_calls(log, 1), f"Grenz-Stop spawnte keinen Runner; Log: {_ac_log(proj)!r}"
    assert "auto_clear_boundary" not in _state(proj), _state(proj)
    _age_lock(proj)  # Once-Lock abgelaufen: nur der Verbrauch schuetzt noch
    question = _message("Implementierung halb fertig. Variante A oder B?", du=_du(CMD))
    res = _run_hook(proj, env, question)
    assert res.returncode == 0, res.stderr
    time.sleep(1.0)
    assert len(_notifications(log)) == 1, f"Zweiter Auto-/clear mitten in der Phase: {_notifications(log)}"
    assert _ac_log(proj).splitlines()[-1].endswith("skip: keine Grenze vermerkt"), _ac_log(proj)


def test_boundary_consumed_by_negative_veto(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path, auto_clear_boundary=_boundary())
    res = _run_hook(proj, env, _message(PLAIN, NEGATIVE, du=_du(CMD)))
    assert res.returncode == 0, res.stderr
    assert "auto_clear_boundary" not in _state(proj), _state(proj)
    res = _run_hook(proj, env, _message("Erledigt: Datei X gesichert.", du=_du(CMD)))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)


def test_boundary_kept_when_footer_wrong(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path, auto_clear_boundary=_boundary())
    res = _run_hook(proj, env, _message(PLAIN, du=_du("/40-tdd-red #467")))
    assert res.returncode == 2, f"Exit 2 erwartet: {res.returncode} {res.stderr!r}"
    _assert_no_calls(log)
    assert isinstance(_state(proj).get("auto_clear_boundary"), dict), _state(proj)
    res = _run_hook(proj, env, _message(PLAIN, du=_du(CMD)))
    assert res.returncode == 0, res.stderr
    assert _wait_calls(log, 1), f"Korrigierte Fusszeile spawnte nicht; Log: {_ac_log(proj)!r}"


def test_stale_boundary_ignored(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path, auto_clear_boundary=_boundary(age_s=20 * 60))
    res = _run_hook(proj, env, _message(PLAIN, du=_du(CMD)))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)
    assert "skip: Grenze veraltet" in _ac_log(proj), _ac_log(proj)
    assert "auto_clear_boundary" not in _state(proj), _state(proj)


def test_boundary_consumed_on_stop_hook_active(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path, auto_clear_boundary=_boundary())
    msg = _message(PLAIN, du=_du(CMD))
    res = _run_hook(proj, env, msg, stop_hook_active=True)
    assert res.returncode == 0, res.stderr
    assert "auto_clear_boundary" not in _state(proj), _state(proj)
    res = _run_hook(proj, env, msg)
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)
