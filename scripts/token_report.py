#!/usr/bin/env python3
"""Tokenverbrauch je Workflow-Phase und Akteur (eigenstaendiges Werkzeug, KEIN Hook/Gate).

Quelle sind die Claude-Code-Transcripts unter ~/.claude/projects/<projekt>/:
Hauptsitzungen als <sessionId>.jsonl, Subagenten als
<sessionId>/subagents/agent-*.jsonl mit Nachbardatei agent-*.meta.json (agentType).

Gezaehlt werden assistant-Zeilen; je message.id nur einmal (Streaming-Duplikate,
es gilt die Zeile mit dem hoechsten output_tokens). Phasen stammen aus den
Bash-Aufrufen `workflow.py phase phaseN_...` der Hauptsitzung; jede Nachricht
(auch von Subagenten) faellt per Zeitstempel in die Phase ihrer (Eltern-)Sitzung.

Aufruf:
    python3 token_report.py [PFAD ...] [--branch NAME] [--since ISO] [--until ISO] [--md]

PFAD = Projektordner (Default: alle unter ~/.claude/projects mit 'agent-os-openspec'
im Namen). "Neu-Tokens" = input + cache_create + output; cache_read steht separat,
weil er billig ist. Nur Standardbibliothek.
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PRE = "vor-workflow"
_PHASE = re.compile(r"workflow\.py\s+phase\s+(phase\d\w*)")
COLS = ("msgs", "input", "cache_create", "cache_read", "output")
_USAGE = {"input": "input_tokens", "cache_create": "cache_creation_input_tokens",
          "cache_read": "cache_read_input_tokens", "output": "output_tokens"}


def parse_ts(value) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _num(value) -> int:
    return value if isinstance(value, int) else 0


def _read_file(path: Path) -> list[dict]:
    """Assistant-Zeilen einer Datei, je message.id die mit dem hoechsten output."""
    best: dict[str, dict] = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or row.get("type") != "assistant":
                continue
            msg = row.get("message") if isinstance(row.get("message"), dict) else {}
            ts = parse_ts(row.get("timestamp"))
            if ts is None:
                continue
            usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else {}
            rec = {k: _num(usage.get(v)) for k, v in _USAGE.items()}
            content = msg.get("content") if isinstance(msg.get("content"), list) else []
            rec.update(ts=ts, branch=row.get("gitBranch") or "", commands=[
                str((b.get("input") or {}).get("command", "")) for b in content
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Bash"])
            key = msg.get("id") or f"_line{n}"
            if key not in best or rec["output"] > best[key]["output"]:
                best[key] = rec
    return list(best.values())


def _actor(path: Path) -> str:
    try:
        meta = json.loads(path.with_name(path.stem + ".meta.json").read_text(encoding="utf-8"))
        return str(meta.get("agentType") or "subagent")
    except (OSError, ValueError, AttributeError):
        return "subagent"


def load(dirs: list[Path]) -> list[dict]:
    """Alle Nachrichten mit session (Hauptsitzung bzw. Elternsitzung) und actor."""
    records: list[dict] = []
    for d in dirs:
        for path in sorted(Path(d).rglob("*.jsonl")):
            sub = path.parent.name == "subagents"
            session = path.parent.parent.name if sub else path.stem
            actor = _actor(path) if sub else "main"
            for rec in _read_file(path):
                rec.update(session=(str(d), session), actor=actor)
                records.append(rec)
    return records


def phase_index(records: list[dict]) -> dict:
    """Je Hauptsitzung sortierte Phasenwechsel [(ts, phase), ...]."""
    marks = defaultdict(list)
    for rec in records:
        if rec["actor"] != "main":
            continue
        for cmd in rec["commands"]:
            for phase in _PHASE.findall(cmd):
                marks[rec["session"]].append((rec["ts"], phase))
    return {s: sorted(m) for s, m in marks.items()}


def phase_of(index: dict, session, ts: datetime) -> str:
    marks = index.get(session, [])
    pos = bisect.bisect_right([m[0] for m in marks], ts)
    return marks[pos - 1][1] if pos else PRE


def collect(dirs, branch=None, since=None, until=None) -> dict:
    """Aggregat {(phase, actor): Counter(msgs, input, cache_create, cache_read, output)}."""
    records = load([Path(d) for d in dirs])
    index = phase_index(records)
    parent_branch = {}
    for rec in records:
        if rec["actor"] == "main" and rec["branch"]:
            parent_branch.setdefault(rec["session"], rec["branch"])
    agg: dict = defaultdict(Counter)
    for rec in records:
        eff = rec["branch"] or parent_branch.get(rec["session"], "")
        if (branch and eff != branch) or (since and rec["ts"] < since) or (until and rec["ts"] > until):
            continue
        c = agg[(phase_of(index, rec["session"], rec["ts"]), rec["actor"])]
        c["msgs"] += 1
        for k in _USAGE:
            c[k] += rec[k]
    return dict(agg)


def _new(c: Counter) -> int:
    return c["input"] + c["cache_create"] + c["output"]


def _table(title: str, groups: dict, md: bool) -> list[str]:
    head = ["Gruppe", "Nachrichten", "input", "cache_create", "cache_read", "output", "Neu-Tokens"]
    rows = [[name] + [str(c[k]) for k in COLS] + [str(_new(c))]
            for name, c in sorted(groups.items(), key=lambda kv: -_new(kv[1]))]
    total = sum(groups.values(), Counter())
    rows.append(["Summe"] + [str(total[k]) for k in COLS] + [str(_new(total))])
    if md:
        out = [f"\n## {title}\n", "| " + " | ".join(head) + " |", "|---" + "|---:" * 6 + "|"]
        return out + ["| " + " | ".join(r) + " |" for r in rows]
    widths = [max(len(r[i]) for r in rows + [head]) for i in range(len(head))]
    fmt = lambda r: "  ".join(v.ljust(widths[0]) if i == 0 else v.rjust(widths[i]) for i, v in enumerate(r))
    return [f"\n{title}", fmt(head)] + [fmt(r) for r in rows]


def report(agg: dict, md: bool) -> str:
    if not agg:
        return "Keine Nachrichten im gewaehlten Filter gefunden.\n"
    by_phase, by_actor = defaultdict(Counter), defaultdict(Counter)
    for (phase, actor), c in agg.items():
        by_phase[phase] += c
        by_actor[actor] += c
    out = ["# Token-Report" if md else "Token-Report"]
    out += _table("Je Phase", by_phase, md) + _table("Je Akteur", by_actor, md)
    out.append("\n## Die drei teuersten Kombinationen (Akteur / Phase)\n" if md
               else "\nDie drei teuersten Kombinationen (Akteur / Phase)")
    top = sorted(agg.items(), key=lambda kv: -_new(kv[1]))[:3]
    for i, ((phase, actor), c) in enumerate(top, 1):
        out.append(f"{i}. {actor} / {phase}: {_new(c)} Neu-Tokens ({c['msgs']} Nachrichten)")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--branch", help="nur Nachrichten dieses gitBranch")
    ap.add_argument("--since", help="ab ISO-Zeitpunkt (UTC, falls ohne Zone)")
    ap.add_argument("--until", help="bis ISO-Zeitpunkt (UTC, falls ohne Zone)")
    ap.add_argument("--md", action="store_true", help="Markdown-Tabellen")
    args = ap.parse_args(argv)
    since, until = parse_ts(args.since) if args.since else None, parse_ts(args.until) if args.until else None
    if (args.since and since is None) or (args.until and until is None):
        print("--since/--until erwarten ISO-Zeitpunkte", file=sys.stderr)
        return 2
    dirs = [Path(p) for p in args.paths] or sorted(
        p for p in (Path.home() / ".claude" / "projects").glob("*agent-os-openspec*") if p.is_dir())
    sys.stdout.write(report(collect(dirs, args.branch, since, until), args.md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
