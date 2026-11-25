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

Abgeloest durch #662 (docs/specs/feat-662-kette-flach.md): Auch beim
Kontext-Schnitt startet der Stop-Hook keinen Runner und schreibt weder Vermerk
noch Skip-Log. `test_context_cut_without_boundary_spawns_runner` und
`test_context_cut_records_boundary_before_spawn` sind entfallen, ersetzt durch
tests/test_auto_chain_flat_662.py::test_stop_hook_never_spawns_runner (Fall
`context-cut`); die uebrigen Faelle pruefen "kein Spawn, kein Vermerk, kein Log".
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_autoclear_retry_597 import (  # noqa: E402
    CLEAN, CMD, GIT, NEGATIVE, Case, _assert_no_calls, _message,
)

SESSION = "sess-597"  # session_id, die Case.run_footer im Stop-Payload sendet

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


def _assert_skipped_without_boundary(case: Case, res):
    """#662: kein Spawn, kein Vermerk und kein Skip-Log (frueher mit Skip-Grund)."""
    assert res.returncode == 0, res.stderr
    _assert_no_calls(case)
    assert case.current_boundary() is None, \
        f"Vermerk geschrieben, obwohl kein Auto-/clear: {case.state()}"
    assert case.runner_log() == "", case.runner_log()


# --- (1) Kontext über der Schwelle: #662 kein Spawn, kein Vermerk -----------

def test_context_cut_never_spawns_nor_records(tmp_path):
    """Kein Vermerk, Messung der Sitzung über der wirksamen Schwelle, Fußzeile nennt
    den erwarteten Befehl (Wortlaut aus #515): #662 startet keinen Runner mehr."""
    case = _kontext_case(tmp_path, "ueber", grace=1)
    _assert_skipped_without_boundary(case, case.run_footer(_footer(f"/clear, dann {CMD}")))
    case = _kontext_case(tmp_path, "ueber-positiv")
    _assert_skipped_without_boundary(case, case.run_footer(_message()))


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
        _assert_skipped_without_boundary(case, case.run_footer(_footer(text)))


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
    _assert_skipped_without_boundary(case, case.run_footer(_message(GIT)))


def test_negative_marker_writes_no_boundary(tmp_path):
    case = _kontext_case(tmp_path, "negativ")
    _assert_skipped_without_boundary(case, case.run_footer(_message(CLEAN, NEGATIVE)))
