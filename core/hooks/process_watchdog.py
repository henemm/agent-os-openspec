#!/usr/bin/env python3
"""Waechter gegen Dauerlast durch Werkzeuge (#462).

Anlass: Eine `bfs -S dfs /`-Suche lief 31 Stunden im Hintergrund, kein Waechter sah sie.

Aufrufe:
    process_watchdog.py hook      PostToolUse Bash: prueft die Kindprozesse DIESER
                                  Claude-Instanz (Vorfahr des Hooks), Meldung an Claude
    process_watchdog.py end       SessionEnd: wie hook, Meldung nur auf stderr
    process_watchdog.py service   einmal pro Minute (launchd/cron): prueft alle Prozesse,
                                  die unter einer `claude`-Instanz haengen
    Option --dry-run              nichts beenden, nur melden

Regeln (ohne Modell):
    * Suche ab `/`, `~` oder $HOME (find/bfs/fd/grep -r/rg) laenger als SEARCH_KILL_AGE -> beenden
    * sonst: Prozess aelter als LONG_AGE UND mit CPU-Zeit ab LONG_CPU -> nur melden
    * Ausnahmen: xcodebuild, sim.sh (grosse Uebersetzungslaeufe duerfen lange laufen)
    * Keine ulimit-Obergrenze: sie bricht legitime Uebersetzungslaeufe ab.

Fail-open: jeder Fehler endet mit Exit 0, der Waechter darf nie eine Sitzung blockieren.
"""

import json
import os
import re
import shlex
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

SEARCH_KILL_AGE = 60      # Sekunden: eine echte Plattensuche ist laenger fertig
LONG_AGE = 600            # ~10 min
LONG_CPU = 300            # CPU-Sekunden
EXEMPT = ("xcodebuild", "sim.sh")


def _secs(text: str) -> int:
    """`[[dd-]hh:]mm:ss` (ps etime/time) in Sekunden; macOS liefert `mm:ss.cc`."""
    days = 0
    if "-" in text:
        d, text = text.split("-", 1)
        days = int(d)
    parts = [float(p) for p in text.split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return int(total) + days * 86400


def list_processes() -> list:
    """[(pid, ppid, age_s, cpu_s, args)] aller Prozesse; leer bei Fehler."""
    try:
        out = subprocess.run(["ps", "-axo", "pid=,ppid=,etime=,time=,args="],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return []
    procs = []
    for line in out.splitlines():
        f = line.split(None, 4)
        if len(f) < 5:
            continue
        try:
            procs.append((int(f[0]), int(f[1]), _secs(f[2]), _secs(f[3]), f[4]))
        except ValueError:
            continue
    return procs


def descendants(procs: list, roots: set) -> set:
    kids = {}
    for pid, ppid, *_ in procs:
        kids.setdefault(ppid, []).append(pid)
    seen, todo = set(), list(roots)
    while todo:
        for kid in kids.get(todo.pop(), []):
            if kid not in seen:
                seen.add(kid)
                todo.append(kid)
    return seen


def claude_roots(procs: list) -> set:
    """PIDs der Claude-Code-Instanzen (Kommandowort `claude`)."""
    roots = set()
    for pid, _, _, _, args in procs:
        try:
            first = shlex.split(args)[0]
        except (ValueError, IndexError):
            continue
        if os.path.basename(first) == "claude":
            roots.add(pid)
    return roots


def _broad_search(args: str) -> "str | None":
    from bash_gate import _broad_search_hit  # gleiche Regel wie der Hook
    return _broad_search_hit(args)


def scan(procs: list, scope: set) -> list:
    """Befunde fuer die Prozesse in `scope`: [{pid, kind, age, cpu, args, hit}]."""
    findings = []
    for pid, _, age, cpu, args in procs:
        if pid not in scope or pid == os.getpid():
            continue
        if any(e in args for e in EXEMPT):
            continue
        hit = _broad_search(args) if age >= SEARCH_KILL_AGE else None
        if hit:
            kind = "search"
        elif age >= LONG_AGE and cpu >= LONG_CPU:
            kind = "long"
        else:
            continue
        findings.append({"pid": pid, "kind": kind, "age": age, "cpu": cpu,
                         "args": args[:160], "hit": hit})
    return findings


def act(findings: list, dry_run: bool = False) -> list:
    """Beendet Suchen, liefert Meldezeilen fuer alle Befunde."""
    lines = []
    for f in findings:
        what = f"PID {f['pid']} seit {f['age'] // 60} min, CPU {f['cpu']} s: {f['args']}"
        if f["kind"] == "search":
            killed = False
            if not dry_run:
                try:
                    os.kill(f["pid"], signal.SIGTERM)
                    killed = True
                except OSError:
                    pass
            lines.append(f"Suche ueber die Platte ({f['hit']}) "
                         f"{'beendet' if killed else 'erkannt'} — {what}")
        else:
            lines.append(f"Langlaeufer (nicht beendet) — {what}")
    return lines


def _own_claude(procs: list) -> int:
    """Naechster `claude`-Vorfahr dieses Hooks; ersatzweise der Elternprozess."""
    parent = {pid: ppid for pid, ppid, *_ in procs}
    roots = claude_roots(procs)
    pid = os.getppid()
    for _ in range(10):
        if pid in roots:
            return pid
        pid = parent.get(pid, 0)
        if pid <= 1:
            break
    return os.getppid()


def run(mode: str, dry_run: bool = False) -> list:
    procs = list_processes()
    if mode == "service":
        roots = claude_roots(procs)
    else:
        roots = {_own_claude(procs)}
    return act(scan(procs, descendants(procs, roots)), dry_run)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "hook"
    dry = "--dry-run" in sys.argv
    try:
        lines = run("hook" if mode == "end" else mode, dry)
    except Exception:
        sys.exit(0)
    if lines:
        text = "[Waechter #462] " + "; ".join(lines)
        if mode == "hook":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                     "additionalContext": text}}))
        elif mode == "end":
            print(text, file=sys.stderr)
        else:
            print(text)
    sys.exit(0)


if __name__ == "__main__":
    main()
