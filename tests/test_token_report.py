"""scripts/token_report.py — Tokenverbrauch je Phase und Akteur (Issue #250, Teil 0).

Eigenstaendiges Messwerkzeug (kein Hook, kein Gate). Getestet wird, worauf die
Auswertung sich verlaesst: Streaming-Duplikate nur einmal zaehlen, Phasenzuordnung
per Zeitstempel je Sitzung, Akteur aus der meta.json, Zweig-Filter (inkl. Erbe
der Elternsitzung) und Robustheit gegen kaputte Zeilen.
"""
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "token_report.py"
_spec = importlib.util.spec_from_file_location("token_report", SCRIPT)
token_report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(token_report)

BASE = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def _msg(mid, minute, inp=0, cc=0, cr=0, out=0, branch="feat-x", session="S1", command=None):
    content = [{"type": "text", "text": "hi"}]
    if command:
        content.append({"type": "tool_use", "name": "Bash", "input": {"command": command}})
    line = {
        "type": "assistant",
        "sessionId": session,
        "timestamp": (BASE + timedelta(minutes=minute)).isoformat().replace("+00:00", "Z"),
        "message": {
            "id": mid,
            "model": "claude-test",
            "usage": {"input_tokens": inp, "cache_creation_input_tokens": cc,
                      "cache_read_input_tokens": cr, "output_tokens": out},
            "content": content,
        },
    }
    if branch is not None:
        line["gitBranch"] = branch
    return line


def _write(path: Path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for ln in lines:
            fh.write(ln if isinstance(ln, str) else json.dumps(ln))
            fh.write("\n")


def _subagent(project: Path, parent: str, name: str, agent_type, lines):
    sub = project / parent / "subagents"
    _write(sub / f"agent-{name}.jsonl", lines)
    if agent_type is not None:
        (sub / f"agent-{name}.meta.json").write_text(json.dumps({"agentType": agent_type}))


def test_duplicate_message_id_counted_once_with_max_output(tmp_path):
    _write(tmp_path / "S1.jsonl", [
        _msg("m1", 0, inp=10, out=1),
        _msg("m1", 0, inp=10, out=50),
        _msg("m1", 0, inp=10, out=7),
        _msg("m2", 1, inp=5, out=5),
    ])
    agg = token_report.collect([tmp_path])
    total = sum((c for c in agg.values()), token_report.Counter())
    assert total["msgs"] == 2
    assert total["output"] == 55
    assert total["input"] == 15


def test_phase_assignment_by_timestamp(tmp_path):
    _write(tmp_path / "S1.jsonl", [
        _msg("a", 0, out=1),
        _msg("b", 10, out=2, command="python3 .claude/hooks/workflow.py phase phase5_tdd_red"),
        _msg("c", 20, out=4),
        _msg("d", 30, out=8, command="OPENSPEC_ACTIVE_WORKFLOW=x python3 workflow.py phase phase6_implement"),
        _msg("e", 40, out=16),
    ])
    agg = token_report.collect([tmp_path])
    assert agg[("vor-workflow", "main")]["output"] == 1
    assert agg[("phase5_tdd_red", "main")]["output"] == 2 + 4
    assert agg[("phase6_implement", "main")]["output"] == 8 + 16


def test_phase_boundaries_not_mixed_between_sessions(tmp_path):
    _write(tmp_path / "S1.jsonl", [
        _msg("a", 0, out=1, session="S1", command="workflow.py phase phase6_implement"),
        _msg("b", 30, out=2, session="S1"),
    ])
    _write(tmp_path / "S2.jsonl", [
        _msg("c", 10, out=4, session="S2"),
        _msg("d", 40, out=8, session="S2"),
    ])
    agg = token_report.collect([tmp_path])
    assert agg[("phase6_implement", "main")]["output"] == 3
    assert agg[("vor-workflow", "main")]["output"] == 12


def test_subagent_actor_from_meta_and_parent_phase(tmp_path):
    _write(tmp_path / "S1.jsonl", [
        _msg("a", 0, out=1, command="workflow.py phase phase3_spec"),
    ])
    _subagent(tmp_path, "S1", "x1", "agent-os-openspec:po-briefer", [
        _msg("s1", 5, inp=100, cc=20, cr=999, out=30, branch=None),
    ])
    _subagent(tmp_path, "S1", "x2", None, [_msg("s2", 6, out=3)])
    agg = token_report.collect([tmp_path])
    po = agg[("phase3_spec", "agent-os-openspec:po-briefer")]
    assert (po["msgs"], po["input"], po["cache_create"], po["cache_read"], po["output"]) == (1, 100, 20, 999, 30)
    assert agg[("phase3_spec", "subagent")]["output"] == 3


def test_branch_filter_with_inherited_parent_branch(tmp_path):
    _write(tmp_path / "S1.jsonl", [_msg("a", 0, out=1, branch="feat-x", session="S1")])
    _write(tmp_path / "S2.jsonl", [_msg("b", 0, out=2, branch="other", session="S2")])
    _subagent(tmp_path, "S1", "x1", "general-purpose", [_msg("s1", 1, out=4, branch=None)])
    agg = token_report.collect([tmp_path], branch="feat-x")
    total = sum((c for c in agg.values()), token_report.Counter())
    assert total["output"] == 5
    assert agg[("vor-workflow", "general-purpose")]["output"] == 4


def test_since_until_filter(tmp_path):
    _write(tmp_path / "S1.jsonl", [_msg("a", 0, out=1), _msg("b", 10, out=2), _msg("c", 20, out=4)])
    since = BASE + timedelta(minutes=5)
    until = BASE + timedelta(minutes=15)
    agg = token_report.collect([tmp_path], since=since, until=until)
    total = sum((c for c in agg.values()), token_report.Counter())
    assert total["output"] == 2


def test_broken_lines_and_missing_fields(tmp_path):
    no_usage = _msg("z", 2)
    del no_usage["message"]["usage"]
    _write(tmp_path / "S1.jsonl", [
        "{kaputt",
        json.dumps({"type": "user", "message": {"content": "x"}}),
        _msg("a", 0, inp=3, out=1),
        no_usage,
        "",
    ])
    agg = token_report.collect([tmp_path])
    total = sum((c for c in agg.values()), token_report.Counter())
    assert total["msgs"] == 2
    assert total["input"] == 3


def test_cli_table_has_new_tokens_sum_and_top(tmp_path, capsys):
    _write(tmp_path / "S1.jsonl", [_msg("a", 0, inp=10, cc=20, cr=500, out=5)])
    rc = token_report.main([str(tmp_path), "--md"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Neu-Tokens" in out
    assert "| Summe |" in out
    assert "35" in out  # 10 + 20 + 5, cache_read nicht enthalten
    assert "teuerst" in out.lower()


def test_cli_empty_input_exit_zero(tmp_path, capsys):
    rc = token_report.main([str(tmp_path)])
    assert rc == 0
    assert "Keine" in capsys.readouterr().out
