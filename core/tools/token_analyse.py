#!/usr/bin/env python3
"""Token-Verbrauch je Tätigkeit aus den Claude-Code-Sitzungsprotokollen (#535).

Liest ~/.claude/projects/<Projekt>*/**/*.jsonl (Hauptsitzungen, Worktrees und
Teilagenten-Protokolle) und zeigt, welche Tätigkeit wie viel verbraucht.

Aufruf:
    token_analyse.py --liste                      vorhandene Projekte
    token_analyse.py -home-hem-mein-projekt       Auswertung (Präfix des Ordnernamens)
    token_analyse.py PRÄFIX --json                maschinenlesbar
    token_analyse.py PRÄFIX --verzeichnis DIR     anderer Protokollordner

Wie gerechnet wird (Näherung, keine Abrechnung):
  * Eine API-Antwort wird einmal gezählt (Eintrags-ID), auch wenn sie im
    Protokoll auf mehrere Zeilen verteilt ist.
  * Jede Antwort gehört zur Tätigkeit, die sie auslöst (Werkzeug, bei Bash der
    Befehl, bei Edit/Write der Pfad). Das Wiederlesen des Kontexts wird dem
    nächsten Schritt zugerechnet, nicht dem Schritt, der den Kontext gefüllt hat.
  * Kostenanteil: gewichtete Summe nach ungefähren Preisverhältnissen
    (frischer Input 1, Cache lesen 0,1, Cache schreiben 2, Output 5). Die
    Gewichte stehen in GEWICHTE und lassen sich anpassen.
  * Die Zuordnung der Tätigkeiten ist grob (Muster auf Befehle und Pfade).
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

GEWICHTE = {"inp": 1.0, "cw": 2.0, "cr": 0.1, "out": 5.0}
STANDARD_VERZEICHNIS = os.path.expanduser("~/.claude/projects")

K_OHNE_WERKZEUG = "Antworten und Denken (ohne Werkzeug)"
K_TESTS_SCHREIBEN = "Tests schreiben"
K_SPEC = "Spec, ADR, Doku schreiben"
K_CODE = "Code schreiben"
K_KONNEKTOR = "Abnahme über MCP-Werkzeuge"
K_WEB = "Web-Recherche"
K_AGENT = "Teilagenten starten"
K_TESTEN = "Tests ausführen"
K_STEUERUNG = "Steuerung (Workflow, Skills, Nachrichten)"
K_GIT = "Git und GitHub (Branch, PR, CI, Issues)"
K_PROBIEREN = "Probieren und Messen (Wegwerf-Skripte)"
K_LESEN_CODE = "Lesen: Code und Sonstiges"
K_LESEN_DOKU = "Lesen: Specs, ADRs, Doku, Nachweise"
K_LESEN_TESTS = "Lesen: Tests"
K_BASH = "Bash sonstiges (Server, Skripte)"
K_WARTEN = "Warten auf CI und Hintergrundläufe"
K_SONST = "Sonstiges"
_DOKU = re.compile(r"docs/(specs|adr|artifacts|context)|(^|[\s/'\"])openspec/|\.md\b")
_TEST = re.compile(r"/tests/|test_")


def _zahl(x):
    """Token-Zahl aus dem Protokoll: nur int/float (kein bool), sonst 0."""
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else 0


def _text(x):
    return x if isinstance(x, str) else ""


def _feld(u, k):
    """Textfeld aus der Werkzeug-Eingabe; falscher Typ zählt als leer."""
    eingabe = u.get("input")
    return _text(eingabe.get(k)) if isinstance(eingabe, dict) else ""


def _lesen(uses):
    """Lesende Zugriffe nach Ziel trennen: Doku/Specs, Tests, sonst Code."""
    text = " ".join(
        _feld(u, k)
        for u in uses for k in ("file_path", "path", "pattern", "command", "glob")
    )
    if _DOKU.search(text):
        return K_LESEN_DOKU
    if _TEST.search(text):
        return K_LESEN_TESTS
    return K_LESEN_CODE


def _schreibziel(pfade):
    if any("/tests/" in p or os.path.basename(p).startswith("test_") for p in pfade):
        return K_TESTS_SCHREIBEN
    if any("/docs/" in p or p.endswith(".md") for p in pfade):
        return K_SPEC
    return K_CODE


def taetigkeit(bloecke):
    """Ordnet eine Antwort (Liste ihrer Inhaltsblöcke) einer Tätigkeit zu."""
    uses = [b for b in bloecke if b.get("type") == "tool_use"]
    if not uses:
        return K_OHNE_WERKZEUG
    namen = [_text(u.get("name")) for u in uses]
    pfade = [
        _feld(u, "file_path")
        for u in uses
        if u.get("name") in ("Edit", "Write", "NotebookEdit")
    ]
    if pfade:
        return _schreibziel(pfade)
    if any(n.startswith("mcp__") and "claude-artifacts" not in n for n in namen):
        return K_KONNEKTOR
    if any(n in ("WebSearch", "WebFetch") for n in namen):
        return K_WEB
    if any(n in ("Agent", "Task", "SubagentHandback") for n in namen):
        return K_AGENT
    bash = [_feld(u, "command") for u in uses if u.get("name") == "Bash"]
    if bash:
        c = " ".join(bash)
        if re.search(r"pytest|playwright|npm (run )?test|unittest|\.mjs\b", c):
            return K_TESTEN
        if "workflow.py" in c:
            return K_STEUERUNG
        if re.search(r"\bgit\b|\bgh\b", c):
            return K_GIT
        if re.search(r"cat\s*>|\.write\(|write_text|sed\s+-i|\btee\b", c):
            if "/tmp/claude" in c or "scratchpad" in c:
                return K_PROBIEREN
            if re.search(r"docs/|\.md\b", c):
                return K_SPEC
            if re.search(r"tests/|test_", c):
                return K_TESTS_SCHREIBEN
            return K_CODE
        if re.search(r"\b(grep|rg|find|ls|cat|head|tail|sed|wc|diff|date)\b", c):
            return _lesen(uses)
        return K_BASH
    if "Monitor" in namen:
        return K_WARTEN
    if "AskUserQuestion" in namen:
        return K_OHNE_WERKZEUG
    if any(n in ("Read", "Grep", "Glob") for n in namen):
        return _lesen(uses)
    if any(n in ("Skill", "ToolSearch", "ScheduleWakeup", "SendMessage", "ListAgents") for n in namen):
        return K_STEUERUNG
    return K_SONST


def antworten(dateien):
    """Liefert je API-Antwort (einmalig) ihre Nutzung und ihre Inhaltsblöcke."""
    gesehen = set()
    for datei in dateien:
        je_id = {}
        try:
            zeilen = open(datei, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with zeilen:
            for zeile in zeilen:
                try:
                    d = json.loads(zeile)
                except ValueError:
                    continue
                if not isinstance(d, dict) or d.get("type") != "assistant":
                    continue
                m = d.get("message") or {}
                if (not isinstance(m, dict) or not isinstance(m.get("id"), str) or not m["id"]
                        or not isinstance(m.get("usage"), dict)):
                    continue
                e = je_id.setdefault(m["id"], {"usage": m["usage"], "bloecke": []})
                inhalt = m.get("content")
                if isinstance(inhalt, list):
                    e["bloecke"] += [b for b in inhalt if isinstance(b, dict)]
                # Streaming: die Zeile mit dem höchsten output_tokens trägt die Endnutzung
                if _zahl(m["usage"].get("output_tokens")) > _zahl(e["usage"].get("output_tokens")):
                    e["usage"] = m["usage"]
        for mid, e in je_id.items():
            if mid in gesehen:
                continue
            gesehen.add(mid)
            yield e["usage"], e["bloecke"]


def auswerten(dateien):
    summen = collections.defaultdict(collections.Counter)
    schritte = collections.Counter()
    denken = collections.Counter()
    kontext = collections.Counter()
    kontext_schritte = collections.Counter()
    for u, bloecke in antworten(dateien):
        t = taetigkeit(bloecke)
        s = summen[t]
        inp = _zahl(u.get("input_tokens"))
        cw = _zahl(u.get("cache_creation_input_tokens"))
        cr = _zahl(u.get("cache_read_input_tokens"))
        s["inp"] += inp
        s["cw"] += cw
        s["cr"] += cr
        s["out"] += _zahl(u.get("output_tokens"))
        details = u.get("output_tokens_details")
        denken[t] += _zahl(details.get("thinking_tokens")) if isinstance(details, dict) else 0
        schritte[t] += 1
        ctx = inp + cw + cr
        stufe = "< 100k" if ctx < 100_000 else ("100-200k" if ctx < 200_000 else "> 200k")
        kontext[stufe] += cr
        kontext_schritte[stufe] += 1
    return summen, schritte, denken, kontext, kontext_schritte


def _kosten(v):
    return sum(GEWICHTE[k] * v[k] for k in GEWICHTE)


def bericht(dateien):
    summen, schritte, denken, kontext, kontext_schritte = auswerten(dateien)
    gesamt = sum(_kosten(v) for v in summen.values()) or 1
    out_alle = sum(v["out"] for v in summen.values()) or 1
    cr_alle = sum(kontext.values()) or 1
    n = sum(schritte.values()) or 1
    zeilen = []
    for t, v in sorted(summen.items(), key=lambda kv: -_kosten(kv[1])):
        zeilen.append({
            "taetigkeit": t,
            "schritte": schritte[t],
            "output": v["out"],
            "davon_denken": denken[t],
            "kostenanteil_prozent": round(100 * _kosten(v) / gesamt, 1),
            "outputanteil_prozent": round(100 * v["out"] / out_alle, 1),
        })
    stufen = [
        {
            "kontext": s,
            "schritte": kontext_schritte[s],
            "schrittanteil_prozent": round(100 * kontext_schritte[s] / n, 1),
            "wiederlesen_anteil_prozent": round(100 * kontext[s] / cr_alle, 1),
        }
        for s in ("< 100k", "100-200k", "> 200k")
    ]
    roh = {k: sum(v[k] for v in summen.values()) for k in GEWICHTE}
    return {"dateien": len(dateien), "antworten": sum(schritte.values()), "roh": roh,
            "taetigkeiten": zeilen, "kontext": stufen}


def ausgeben(b):
    r = b["roh"]
    print(f"Dateien: {b['dateien']}, Antworten: {b['antworten']}")
    print(f"Summen roh: frischer Input {r['inp']/1e6:.1f} Mio, Cache schreiben {r['cw']/1e6:.1f} Mio, "
          f"Cache lesen {r['cr']/1e6:.1f} Mio, Output {r['out']/1e6:.2f} Mio\n")
    print(f"{'Tätigkeit':46} {'Schritte':>8} {'Output':>9} {'davon Denken':>12} {'Kosten':>8} {'Output':>8}")
    for z in b["taetigkeiten"]:
        print(f"{z['taetigkeit']:46} {z['schritte']:8d} {z['output']/1e3:8.0f}k {z['davon_denken']/1e3:11.0f}k "
              f"{z['kostenanteil_prozent']:7.1f}% {z['outputanteil_prozent']:7.1f}%")
    print("\nVerbrauch nach Kontextgröße (Wiederlesen des Gesprächs):")
    for s in b["kontext"]:
        print(f"  Kontext {s['kontext']:9} Schritte {s['schritte']:6d} ({s['schrittanteil_prozent']:4.1f} %)  "
              f"Anteil Wiederlesen {s['wiederlesen_anteil_prozent']:4.1f} %")


def projekte(verzeichnis):
    """Projektordner ohne die Worktree-Zusätze, mit Zahl der Protokolle."""
    zaehler = collections.Counter()
    for ordner in sorted(os.listdir(verzeichnis)):
        stamm = ordner.split("--claude-worktrees")[0]
        zaehler[stamm] += len(glob.glob(os.path.join(verzeichnis, ordner, "**", "*.jsonl"), recursive=True))
    return zaehler


def main(argv=None):
    # Projektordner heißen wie der Pfad (-home-hem-…) und beginnen mit "-":
    # ein einzelner Bindestrich mit längerem Text gilt hier als Präfix, nicht als Option.
    argv = list(sys.argv[1:] if argv is None else argv)
    argv = ["--praefix=" + x if re.match(r"^-[^-]{2,}", x) else x for x in argv]
    p = argparse.ArgumentParser(description="Token-Verbrauch je Tätigkeit aus Sitzungsprotokollen")
    p.add_argument("--praefix", dest="praefix_opt", help=argparse.SUPPRESS)
    p.add_argument("praefix", nargs="?", help="Präfix des Projektordners, z. B. -home-hem-mein-projekt")
    p.add_argument("--liste", action="store_true", help="vorhandene Projekte anzeigen")
    p.add_argument("--json", action="store_true", help="als JSON ausgeben")
    p.add_argument("--verzeichnis", default=STANDARD_VERZEICHNIS, help="Ordner mit den Projektprotokollen")
    a = p.parse_args(argv)
    a.praefix = a.praefix_opt or a.praefix
    if a.liste or not a.praefix:
        try:
            liste = projekte(a.verzeichnis)
        except OSError as fehler:
            print(f"Protokollordner nicht lesbar: {a.verzeichnis} ({fehler.strerror})", file=sys.stderr)
            return 1
        for name, n in sorted(liste.items(), key=lambda kv: -kv[1]):
            print(f"{n:6d}  {name}")
        return 0
    dateien = glob.glob(os.path.join(a.verzeichnis, a.praefix + "*", "**", "*.jsonl"), recursive=True)
    if not dateien:
        print(f"Keine Protokolle für Präfix {a.praefix!r} in {a.verzeichnis}", file=sys.stderr)
        return 1
    b = bericht(dateien)
    if a.json:
        print(json.dumps(b, ensure_ascii=False, indent=2))
    else:
        ausgeben(b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
