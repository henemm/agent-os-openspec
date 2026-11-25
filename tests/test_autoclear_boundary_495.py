"""Auto-/clear mechanisch an der Phasengrenze (Issue #495).

Spec: docs/specs/fix-495-autoclear-mechanisch.md (AC-1 bis AC-7; AC-8 = Regressionslauf).

`workflow.py autoclear` vermerkt bei `AUTO_CLEAR=on` und aktivem Workflow die
Grenze `auto_clear_boundary = {phase, command, at}` im Workflow-State; der
Stop-Hook (`footer_gate.py` -> `herdr_bridge.maybe_auto_clear`) loest aus, wenn
dieser Vermerk zu Phase und erwartetem Befehl passt — der Positiv-Satz
„`/clear` ist jetzt gefahrlos“ ist nicht mehr noetig, der Negativ-Satz bleibt Veto.

Hook- und Stub-Helfer aus tests/test_herdr_auto_clear_467.py.

#597 (docs/specs/fix-597-autoclear-klartext.md): Der Vermerk wird nicht mehr beim
Spawn verbraucht, sondern erst vom Runner unmittelbar vor dem Tippen genommen
(Einmal-Token); der Once-Lock und der Verbrauch bei `stop_hook_active` entfallen.
Die Antworttexte enthalten keine Git-Woerter mehr (sonst greift die
Klartext-Vorpruefung, `skip: Klartext-Prüfung weist die Antwort zurück`).

Abgeloest durch #662 (docs/specs/feat-662-kette-flach.md): `workflow.py autoclear`
sagt immer `AUTO_CLEAR=off` und vermerkt nichts, der Stop-Hook spawnt nie und
schreibt kein Skip-Log. Die Tests, die nur Spawn, Tippen und Verbrauch des
Vermerks beschrieben, sind entfallen (ersetzt durch tests/test_auto_chain_flat_662.py,
AC-2/AC-3); die uebrigen pruefen das neue Verhalten.
"""

import json
import subprocess
import sys
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
    _run_hook,
)

WORKFLOW = HOOKS_DIR / "workflow.py"
AC_LOG = Path(".claude") / "herdr_auto_clear.log"

# Antwort OHNE Positiv-Satz, aber mit korrekter ❗Du-Zeile; ohne Git-Woerter (#597)
PLAIN = "Phase sauber abgeschlossen, Stand gesichert."


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

    # (b) Auto-/clear an, aber kein aktiver Workflow: #662 -> off, kein Vermerk
    root = tmp_path / "nowf"
    root.mkdir()
    proj, log, stub, env = _hook_case(root, config=AUTO_ON)
    (proj / ".claude" / "active_workflow").unlink()
    env.pop("OPENSPEC_ACTIVE_WORKFLOW")
    res = _run_autoclear(proj, env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "AUTO_CLEAR=off", res.stdout
    assert "Traceback" not in res.stderr, res.stderr
    assert "auto_clear_boundary" not in _state(proj)


# --- AC-4 -------------------------------------------------------------------

def test_no_spawn_without_boundary_and_no_skip_log(tmp_path):
    """#662: kein Spawn und kein Skip-Log mehr (maybe_auto_clear kehrt sofort zurueck)."""
    proj, log, stub, env = _hook_case(tmp_path)
    res = _run_hook(proj, env, _message(PLAIN, du=_du(CMD)))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)
    assert _ac_log(proj) == "", _ac_log(proj)


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


def test_footer_wrong_then_corrected_never_spawns(tmp_path):
    """#662: falsche Fusszeile blockt wie bisher (Exit 2); auch die korrigierte
    Fusszeile mit Grenz-Vermerk startet keinen Runner mehr."""
    proj, log, stub, env = _hook_case(tmp_path, auto_clear_boundary=_boundary())
    res = _run_hook(proj, env, _message(PLAIN, du=_du("/40-tdd-red #467")))
    assert res.returncode == 2, f"Exit 2 erwartet: {res.returncode} {res.stderr!r}"
    _assert_no_calls(log)
    res = _run_hook(proj, env, _message(PLAIN, du=_du(CMD)))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)
    assert _ac_log(proj) == "", _ac_log(proj)


def test_stale_boundary_no_spawn_no_skip_log(tmp_path):
    proj, log, stub, env = _hook_case(tmp_path, auto_clear_boundary=_boundary(age_s=20 * 60))
    res = _run_hook(proj, env, _message(PLAIN, du=_du(CMD)))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)
    assert _ac_log(proj) == "", _ac_log(proj)
