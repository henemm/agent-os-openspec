#!/usr/bin/env python3
"""Auswertung von .claude/gate-events.jsonl (eigenstaendiges Werkzeug, KEIN Hook/Gate).

Das Log (hook_utils.log_gate_event) haelt nur Blockaden fest: ts, hook, tool,
reason, command_excerpt, session_id. Es kennt weder erlaubte Aufrufe noch ob eine
Blockade ein Fehlalarm war. Dieses Skript liefert deshalb Haeufigkeiten, Cluster
und Schleifen-Verdacht - die Einstufung "echt oder Fehlalarm" bleibt Handarbeit.

Aufruf:
    python3 gate_audit.py <log-oder-ordner> [weitere ...] [--since YYYY-MM-DD]
                          [--top N] [--loop-min M] [--loop-count K] [--md]

Ein Ordner wird rekursiv nach gate-events.jsonl durchsucht. Mehrere Projekte
lassen sich gemeinsam auswerten; die Quelle steht dann als Praefix im Report.
Nur Standardbibliothek.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

_NUM = re.compile(r"\d+")
_HEX = re.compile(r"\b[0-9a-f]{7,40}\b")
_PATH = re.compile(r"(?:[\w.\-]+/)+[\w.\-]+")
_WF = re.compile(r"(?i)\b(?:feat|fix|bug|feature)[-_][\w\-]+")


def normalize(reason: str) -> str:
    """Grund auf ein Muster kuerzen: Zahlen, Hashes, Pfade, Workflow-Namen -> Platzhalter."""
    text = (reason or "").strip()
    text = _WF.sub("<wf>", text)
    text = _HEX.sub("<hash>", text)
    text = _PATH.sub("<pfad>", text)
    text = _NUM.sub("N", text)
    return re.sub(r"\s+", " ", text)[:140]


def find_logs(inputs: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            found.extend(sorted(p.rglob("gate-events.jsonl")))
        elif p.is_file():
            found.append(p)
        else:
            print(f"WARNUNG: {raw} nicht gefunden", file=sys.stderr)
    return found


def parse_ts(value: str) -> datetime | None:
    try:
        ts = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def load(paths: list[Path], since: datetime | None):
    events, broken = [], 0
    for path in paths:
        label = path.parent.parent.name or str(path)
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    broken += 1
                    continue
                ts = parse_ts(ev.get("ts", ""))
                if ts is None or (since and ts < since):
                    continue
                ev["_ts"], ev["_src"] = ts, label
                ev["_pattern"] = normalize(ev.get("reason", ""))
                events.append(ev)
    events.sort(key=lambda e: e["_ts"])
    return events, broken


def find_loops(events, minutes: int, count: int):
    """Gleiche Sitzung + gleicher Hook + gleiches Muster >= count mal binnen minutes.

    Das ist das Muster 'Gate blockt wiederholt, Claude versucht es weiter'
    (selfexplaining-gates: ~1,9 Mio Token in einem Fall)."""
    groups = defaultdict(list)
    for e in events:
        sid = e.get("session_id") or f"?{e['_src']}"
        groups[(e["_src"], sid, e.get("hook", ""), e["_pattern"])].append(e["_ts"])
    window, loops = timedelta(minutes=minutes), []
    for key, stamps in groups.items():
        best, lo = 0, 0
        for hi in range(len(stamps)):
            while stamps[hi] - stamps[lo] > window:
                lo += 1
            best = max(best, hi - lo + 1)
        if best >= count:
            loops.append((best, key, stamps[0]))
    return sorted(loops, key=lambda x: -x[0])


def report(events, broken, top, loop_min, loop_count) -> str:
    out: list[str] = []
    if not events:
        return "Keine Ereignisse im gewaehlten Zeitraum.\n"
    first, last = events[0]["_ts"], events[-1]["_ts"]
    sessions = {e.get("session_id") or "" for e in events} - {""}
    out.append("# Gate-Event-Auswertung\n")
    out.append(f"- Zeitraum: {first:%Y-%m-%d} bis {last:%Y-%m-%d}")
    out.append(f"- Blockaden gesamt: {len(events)}  |  Sitzungen mit ID: {len(sessions)}"
               f"  |  Quellen: {', '.join(sorted({e['_src'] for e in events}))}")
    if broken:
        out.append(f"- Nicht lesbare Zeilen uebersprungen: {broken}")
    out.append("- Grenze: nur Blockaden, kein Nenner (erlaubte Aufrufe) und kein Fehlalarm-Urteil.\n")

    by_hook = Counter(e.get("hook", "?") for e in events)
    out.append("## Blockaden je Hook\n\n| Hook | Anzahl | Anteil |\n|---|---:|---:|")
    for hook, n in by_hook.most_common():
        out.append(f"| {hook} | {n} | {n / len(events):.0%} |")

    out.append(f"\n## Haeufigste Muster (Top {top})\n\n| # | Hook | Muster | Sitzungen | Quellen |\n|---:|---|---|---:|---|")
    pat = Counter((e.get("hook", "?"), e["_pattern"]) for e in events)
    for (hook, p), n in pat.most_common(top):
        sess = {e.get("session_id") for e in events
                if e.get("hook", "?") == hook and e["_pattern"] == p}
        srcs = sorted({e["_src"] for e in events
                       if e.get("hook", "?") == hook and e["_pattern"] == p})
        out.append(f"| {n} | {hook} | {p.replace('|', '/')} | {len(sess)} | {', '.join(srcs)} |")

    out.append("\n## Verlauf je Kalenderwoche\n\n| Woche | Blockaden |\n|---|---:|")
    weeks = Counter(f"{e['_ts'].isocalendar().year}-KW{e['_ts'].isocalendar().week:02d}" for e in events)
    for wk in sorted(weeks):
        out.append(f"| {wk} | {weeks[wk]} |")

    loops = find_loops(events, loop_min, loop_count)
    out.append(f"\n## Schleifen-Verdacht (>= {loop_count}x gleiches Muster in {loop_min} min, gleiche Sitzung)\n")
    if not loops:
        out.append("Keine.")
    else:
        out.append("| Wiederholungen | Quelle | Hook | Muster | Beginn |\n|---:|---|---|---|---|")
        for n, (src, _sid, hook, p), start in loops[:top]:
            out.append(f"| {n} | {src} | {hook} | {p.replace('|', '/')} | {start:%Y-%m-%d %H:%M} |")

    out.append("\n## Stichprobe zur Handeinstufung\n")
    out.append("Je Top-Muster ein Beispiel (maskierter Ausschnitt). Frage pro Zeile: war die Blockade berechtigt?\n")
    seen = set()
    for (hook, p), _n in pat.most_common(top):
        ex = next(e for e in reversed(events) if e.get("hook", "?") == hook and e["_pattern"] == p)
        if (hook, p) in seen:
            continue
        seen.add((hook, p))
        excerpt = (ex.get("command_excerpt") or "").replace("\n", " ")[:120]
        out.append(f"- `{hook}` {ex['_ts']:%Y-%m-%d}: {excerpt or '(kein Ausschnitt)'}")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--since", help="nur Ereignisse ab YYYY-MM-DD (UTC)")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--loop-min", type=int, default=10)
    ap.add_argument("--loop-count", type=int, default=3)
    ap.add_argument("--md", action="store_true", help="(Standard) Markdown-Ausgabe; Flag nur fuer Klarheit")
    args = ap.parse_args()

    since = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        except ValueError:
            print("--since erwartet YYYY-MM-DD", file=sys.stderr)
            return 2
    paths = find_logs(args.inputs)
    if not paths:
        print("Kein gate-events.jsonl gefunden.", file=sys.stderr)
        return 1
    events, broken = load(paths, since)
    sys.stdout.write(report(events, broken, args.top, args.loop_min, args.loop_count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
