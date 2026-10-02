"""scripts/gate_audit.py — Auswertung von .claude/gate-events.jsonl (Folge von #181).

Das Skript ist ein eigenstaendiges Werkzeug (kein Hook, kein Gate). Getestet wird
das, worauf die Auswertung sich verlaesst: Muster-Normalisierung, Schleifenerkennung,
Robustheit gegen kaputte Zeilen und der Zeitfilter.
"""
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "gate_audit.py"
_spec = importlib.util.spec_from_file_location("gate_audit", SCRIPT)
gate_audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate_audit)

BASE = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def _event(minutes=0, days=0, hook="edit_gate", reason="blocked", session="s1", excerpt=""):
    ts = BASE + timedelta(minutes=minutes, days=days)
    return {
        "ts": ts.isoformat(timespec="seconds"),
        "hook": hook,
        "tool": "Edit",
        "reason": reason,
        "command_excerpt": excerpt,
        "session_id": session,
    }


def _write_log(tmp_path, rows, project="projA", extra_lines=()):
    log = tmp_path / project / ".claude" / "gate-events.jsonl"
    log.parent.mkdir(parents=True)
    lines = [json.dumps(r) for r in rows] + list(extra_lines)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log


def _load(tmp_path, since=None):
    return gate_audit.load(gate_audit.find_logs([str(tmp_path)]), since)


def test_normalize_collapses_numbers_paths_hashes_and_workflow_names():
    a = gate_audit.normalize("LoC delta +312 exceeds limit 250 in core/hooks/x.py (wf=fix-134-foo)")
    b = gate_audit.normalize("LoC delta +405 exceeds limit 250 in core/hooks/y.py (wf=fix-200-bar)")
    assert a == b
    assert "312" not in a and "core/hooks" not in a and "fix-134" not in a


def test_normalize_keeps_different_reasons_apart():
    assert gate_audit.normalize("Zugriff auf .env blockiert") != gate_audit.normalize(
        "Phase phase3_spec does not allow code edits"
    )


def test_find_logs_searches_directories_recursively_and_accepts_files(tmp_path):
    first = _write_log(tmp_path, [_event()], project="projA")
    _write_log(tmp_path, [_event()], project="projB")
    assert len(gate_audit.find_logs([str(tmp_path)])) == 2
    assert gate_audit.find_logs([str(first)]) == [first]


def test_load_skips_broken_lines_and_counts_them(tmp_path):
    _write_log(tmp_path, [_event()], extra_lines=["kein json", '{"ts": "kaputt"}'])
    events, broken = _load(tmp_path)
    assert len(events) == 1  # Zeile mit unlesbarem Zeitstempel zaehlt nicht als Ereignis
    assert broken == 1  # nur die nicht parsbare Zeile wird als defekt gezaehlt


def test_load_applies_since_filter(tmp_path):
    _write_log(tmp_path, [_event(days=0), _event(days=10)])
    events, _ = _load(tmp_path, since=BASE + timedelta(days=5))
    assert len(events) == 1


def test_find_loops_detects_repeats_in_one_session_within_window(tmp_path):
    _write_log(tmp_path, [_event(minutes=i, reason=f"Phase {i} blocked") for i in range(4)])
    events, _ = _load(tmp_path)
    loops = gate_audit.find_loops(events, minutes=10, count=3)
    assert len(loops) == 1 and loops[0][0] == 4


def test_find_loops_ignores_slow_repeats_and_other_sessions(tmp_path):
    rows = [_event(minutes=60 * i) for i in range(4)]  # eine Stunde Abstand
    rows += [_event(minutes=i, session=f"s{i}") for i in range(4)]  # jede Sitzung nur einmal
    _write_log(tmp_path, rows)
    events, _ = _load(tmp_path)
    assert gate_audit.find_loops(events, minutes=10, count=3) == []


def test_report_contains_sections_and_totals(tmp_path):
    _write_log(tmp_path, [_event(hook="edit_gate"), _event(minutes=1, hook="bash_gate")])
    events, broken = _load(tmp_path)
    text = gate_audit.report(events, broken, top=5, loop_min=10, loop_count=3)
    for heading in ("Blockaden je Hook", "Haeufigste Muster", "Verlauf je Kalenderwoche",
                    "Schleifen-Verdacht", "Stichprobe zur Handeinstufung"):
        assert heading in text
    assert "Blockaden gesamt: 2" in text


def test_report_on_empty_input_does_not_crash():
    assert "Keine Ereignisse" in gate_audit.report([], 0, 5, 10, 3)


def test_main_returns_nonzero_when_no_log_found(tmp_path, capsys):
    import sys
    old = sys.argv
    sys.argv = ["gate_audit.py", str(tmp_path / "gibt-es-nicht")]
    try:
        assert gate_audit.main() == 1
    finally:
        sys.argv = old
