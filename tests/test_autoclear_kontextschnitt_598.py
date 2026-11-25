"""Auto-/clear greift auch beim Kontext-Schnitt mitten in der Phase (Issue #598).

Befund (henemm-infra #515, phase6_implement, Herdr-Pane mit Auto-/clear): Die
Sitzung endete wegen der Kontext-Schwelle (151128 Token bei Grundlast ~69k,
wirksame Schwelle ~144k) mit `❗ Du: /clear, dann /50-implement #515`, aber der
Stop-Hook meldete `skip: keine Grenze vermerkt`. Den Grenz-Vermerk
`auto_clear_boundary` setzen nur Phasenwechsel (`AUTO_CLEAR_BOUNDARIES`) oder
`workflow.py autoclear`, und Letzteres ruft das Modell beim Kontext-Schnitt
mitten in der Phase nicht auf.

Regel (mechanisch im Stop-Hook): Fehlt der Vermerk, gilt der Stop trotzdem als
Grenze, wenn für die stoppende Sitzung der Kontext-Schnitt aktiv ist, also
dieselbe Bedingung wie `workflow.py context` -> `CONTEXT_CUT=on`:
`context_budget` an, Messung der Sitzung (`session_id` aus dem Stop-Payload,
ohne Rückgriff auf die jüngste fremde Messung) >= wirksame Schwelle, kein
autarker Auftrag offen. Dann schreibt der Hook den Vermerk für Phase und
erwarteten Befehl und läuft den normalen Pfad weiter. Ein von der
Klartext-Prüfung zurückgewiesener Stop, ein Negativ-Marker oder eine Fußzeile
ohne den erwarteten Befehl schreiben keinen Vermerk.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_autoclear_retry_597 import (  # noqa: E402
    CLEAN, CLEAR, CMD, FOLLOW, GIT, NEGATIVE, PHASE, SKIP_KLARTEXT, Case,
    _assert_no_calls, _ends, _message, _wait_for,
)

SESSION = "sess-597"  # session_id, die Case.run_footer im Stop-Payload sendet
SKIP_NO_BOUNDARY = "skip: keine Grenze vermerkt"

BASELINE = 69_000
OVER = 151_128   # Befund #515
UNDER = 120_000  # unter der wirksamen Schwelle 144000


def _kontext_case(tmp_path, label, *, tokens=OVER, session=SESSION, enabled=True,
                  autark=False, grace=0) -> Case:
    """Case ohne Grenz-Vermerk, mit Kontext-Messung und `context_budget`-Config."""
    case = Case(tmp_path, label, grace=grace, boundary=None)
    config = case.proj / "config.yaml"
    config.write_text(config.read_text() + (
        "context_budget:\n"
        f"  enabled: {'true' if enabled else 'false'}\n"
        "  clear_threshold_tokens: 100000\n"
        "  growth_tokens: 75000\n"))
    if tokens is not None:
        usage = case.proj / ".claude" / "context_usage" / f"{session}.json"
        usage.parent.mkdir(parents=True, exist_ok=True)
        usage.write_text(json.dumps({"tokens": tokens, "baseline_tokens": BASELINE,
                                     "announced_bucket": 1}))
    if autark:
        path = case.proj / ".claude" / "auftrag.json"
        path.write_text(json.dumps({
            "issues": [{"n": 598, "status": "open"}], "autark": True, "note": "",
            "created": "2026-11-25T10:00:00Z", "updated": "2026-11-25T10:00:00Z"}))
    return case


def _footer(text: str) -> str:
    return "\n\n".join([CLEAN, f"❗ Du: {text}",
                        "⚙ /50-implement · agent-os-openspec 4.21.0"])


def _assert_skipped_without_boundary(case: Case, res, reason: str = SKIP_NO_BOUNDARY):
    assert res.returncode == 0, res.stderr
    _assert_no_calls(case)
    assert case.current_boundary() is None, \
        f"Vermerk geschrieben, obwohl kein Auto-/clear: {case.state()}"
    if reason:
        assert reason in case.runner_log(), case.runner_log()


# --- (1) Kontext über der Schwelle: Grenze wird mechanisch vermerkt ----------

def test_context_cut_without_boundary_spawns_runner(tmp_path):
    """Kein Vermerk, Messung der Sitzung über der wirksamen Schwelle, Fußzeile nennt
    den erwarteten Befehl (Wortlaut aus #515): Runner startet, der Vermerk steht für
    Phase und Befehl im State und ist nach dem Tippen verbraucht."""
    case = _kontext_case(tmp_path, "ueber", grace=1)
    res = case.run_footer(_footer(f"/clear, dann {CMD}"))
    assert res.returncode == 0, res.stderr
    assert SKIP_NO_BOUNDARY not in case.runner_log(), case.runner_log()
    assert _wait_for(lambda: case.notifications(), 3), \
        f"Kein Runner beim Kontext-Schnitt; Log: {case.runner_log()!r}"
    boundary = case.current_boundary()
    if boundary is not None:  # Runner hat ihn evtl. schon genommen
        assert boundary["phase"] == PHASE and boundary["command"] == CMD, boundary
        assert boundary.get("at"), boundary
    assert _wait_for(lambda: _ends(case) >= 1, 30), case.runner_log()
    assert ": OK" in case.runner_log(), case.runner_log()
    assert case.typing() == CLEAR + FOLLOW, case.calls()
    assert case.current_boundary() is None, case.state()


def test_context_cut_records_boundary_before_spawn(tmp_path):
    """Der Vermerk liegt schon beim Spawn im State (der Runner nimmt ihn erst nach
    der Grace-Zeit); `at` ist ein frischer Zeitstempel."""
    case = _kontext_case(tmp_path, "vermerk", grace=5)
    res = case.run_footer(_message())
    assert res.returncode == 0, res.stderr
    assert _wait_for(lambda: case.notifications(), 3), case.runner_log()
    boundary = case.current_boundary()
    assert isinstance(boundary, dict), f"Kein Vermerk im State: {case.state()}"
    assert boundary["phase"] == PHASE and boundary["command"] == CMD, boundary


# --- (2) Kontext unter der Schwelle / fremde Messung: wie bisher ------------

def test_below_threshold_keeps_old_behaviour(tmp_path):
    case = _kontext_case(tmp_path, "unter", tokens=UNDER)
    _assert_skipped_without_boundary(case, case.run_footer(_message()))


def test_other_sessions_measurement_does_not_count(tmp_path):
    """Nur die Messung der stoppenden Sitzung zählt, nie die jüngste fremde."""
    case = _kontext_case(tmp_path, "fremd", session="andere-sitzung")
    _assert_skipped_without_boundary(case, case.run_footer(_message()))
    case = _kontext_case(tmp_path, "ohne-messung", tokens=None)
    _assert_skipped_without_boundary(case, case.run_footer(_message()))


# --- (3) Fußzeile ohne den erwarteten Befehl: nie ---------------------------

def test_footer_without_command_never_triggers(tmp_path):
    for i, text in enumerate(("Client secret kopieren und hier einfügen",
                              "⏳ Läuft noch, Ergebnis folgt")):
        case = _kontext_case(tmp_path, f"fuss-{i}")
        _assert_skipped_without_boundary(case, case.run_footer(_footer(text)), reason="")


# --- (4) autarker Auftrag offen: kein Auto-/clear ---------------------------

def test_autark_auftrag_blocks(tmp_path):
    case = _kontext_case(tmp_path, "autark", autark=True)
    _assert_skipped_without_boundary(case, case.run_footer(_message()))


# --- (5) context_budget abgeschaltet: kein Auto-/clear ----------------------

def test_context_budget_disabled_blocks(tmp_path):
    case = _kontext_case(tmp_path, "budget-aus", enabled=False)
    _assert_skipped_without_boundary(case, case.run_footer(_message()))


# --- (6) Klartext-Treffer / Negativ-Marker: kein Vermerk ---------------------

def test_klartext_hit_writes_no_boundary(tmp_path):
    case = _kontext_case(tmp_path, "klartext")
    _assert_skipped_without_boundary(case, case.run_footer(_message(GIT)),
                                     reason=SKIP_KLARTEXT)


def test_negative_marker_writes_no_boundary(tmp_path):
    case = _kontext_case(tmp_path, "negativ")
    _assert_skipped_without_boundary(case, case.run_footer(_message(CLEAN, NEGATIVE)),
                                     reason="skip: Negativmarker")
