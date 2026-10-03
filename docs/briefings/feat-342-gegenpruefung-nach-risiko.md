---
spec_file: docs/specs/feat-342-gegenpruefung-nach-risiko.md
spec_sha256: b1d95c36648243027c8b165c4e5e8482ff318551c83f26307f0826d8d77b36a7
---

# PO-Briefing: feat-342-gegenpruefung-nach-risiko

- **Spec:** docs/specs/feat-342-gegenpruefung-nach-risiko.md
- **Issue:** #342
- **Erstellt:** 2026-10-03

## Was gebaut wird

Die Gegenprüfung verlangt bei reinen Text-, Doku- und Teständerungen nur eine Runde, sonst weiterhin mindestens zwei.

## Definition of Done

Reine Text-, Doku- und Teständerungen kommen mit einer Runde durch; alle anderen, auch unklare, weiterhin nur mit zwei.

## Wie geprüft wird

Tests belegen Einstufung und Rundenzahl; nicht belegt: ob die Einstufung richtig trifft und Tokens spart.

## Kritische Anmerkungen

- Befehlstexte steuern Claude, Tests prüfen nur ihr Vorhandensein; niedrige Einstufung ist bewusstes Restrisiko.
- Ersparnis zeigt sich erst nach Wochen in der Auswertung, nicht vorab.
- Zusatz ungefragt: Tests und Befehlstexte gelten als niedrig; Abschalter und Anzeigebefehl kommen dazu.

## Freigabe-Frage

Soll die Gegenprüfung bei reinen Text-, Doku- und Teständerungen auf eine Runde sinken, sonst bei zwei bleiben?
