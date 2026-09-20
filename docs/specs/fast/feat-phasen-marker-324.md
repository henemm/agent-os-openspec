# Fast Track: Versions-Marker am Ende jeder Phase (3.24.0)

## Problem

Nur die Freigabe-Ausgabe von `/30-write-spec` trug eine Marker-Zeile. An allen anderen Phasen
konnte der PO nicht erkennen, ob ein Plugin-Update überhaupt wirkt — dieselbe Blindheit, die den
Skills-Drift (#151) monatelang unentdeckt ließ.

## Scope

- `scripts/sync_skills.py`: Marker-Abschnitt wird an jede generierte `skills/<name>/SKILL.md` angehängt
- `core/commands/{10-context,20-analyse,30-write-spec,40-tdd-red,50-implement}.md`: Checkpoint-Satz erweitert
- `skills/*/SKILL.md` neu generiert, Version 3.24.0, CHANGELOG
- Nicht enthalten: Kopiermodus (#150)

## Definition of Done

Jede Phase endet mit einer Zeile, die Befehl und geladene Version nennt, und der Checkpoint-Block
„Gesichert auf der Platte“ erscheint genau einmal.

## Acceptance Criteria

- **AC-1:** Given ein generierter Skill außer `30-write-spec`, When er ausgeführt wird, Then endet die letzte Nachricht mit `⚙ /<befehl> · agent-os-openspec <version>` mit echtem Befehlsnamen und echter Version.
- **AC-2:** Given `30-write-spec`, When generiert wird, Then enthält der Skill keinen zusätzlichen Marker-Abschnitt, weil die Freigabe-Ausgabe wörtlich vorgegeben ist und bereits einen Marker trägt.
- **AC-3:** Given eine Versionsänderung in `plugin.json`, When der Generator läuft, Then tragen alle Marker die neue Version, und `--check` blockt bis zur Neugenerierung.
- **AC-4:** Given der Generator läuft zweimal hintereinander, When der zweite Lauf startet, Then schreibt er keine Datei (Idempotenz) und der Marker landet nie innerhalb eines Codeblocks.
- **AC-5:** Given eine Phase mit Checkpoint-Block, When die Ausgabe erstellt wird, Then erscheint „Gesichert auf der Platte“ genau einmal, ohne Vorab- oder Kurzfassung davor.

## Test Plan

- `tests/test_skills_sync.py`: 7 neue Tests (AC-1 bis AC-4), darunter Fence-Parität und Idempotenz
- Volle Suite: 803 passed; `sync_skills.py --check` meldet 16 Skills synchron
- AC-5 ist eine Anweisung an das Modell und wird bei der nächsten Phase in gregor_zwanzig beobachtet
