---
spec_file: docs/specs/feat-345-qa-gate-selbst-ausfuehren.md
spec_sha256: 12cdff2037b0dc0594a9062625d7d5a158a764523294d0abcca4fcda4ca1ecb9
---

# PO-Briefing: feat-345-qa-gate-selbst-ausfuehren

- **Spec:** docs/specs/feat-345-qa-gate-selbst-ausfuehren.md
- **Issue:** #345
- **Erstellt:** 2026-10-08

## Was gebaut wird

Das Prüftor startet Tests selbst und urteilt nach dem echten Ergebnis statt nach einer Textdatei.

## Definition of Done

Jeder Lauf hinterlässt Ausgabedatei, gesperrten Stempel und Urteil; rote Läufe sind immer BROKEN; die alte Datei-Variante funktioniert weiter.

## Wie geprüft wird

Elf automatische Tests mit echten Prozessen belegen Urteil, Zeitlimit, Stempel, Sperre; nicht geprüft wird, ob der neue Weg genutzt wird.

## Kritische Anmerkungen

- Neuer Weg ist freiwillig: Pflicht, Migration und Datei-Modus-Entscheidung fehlen; Fälschbarkeit bleibt bis zum Folge-Ticket.
- Exit 0 mit unbekanntem Ausgabeformat ergibt nur AMBIGUOUS, also Rückfrage, nicht grün.
- Zusatz: Änderung am Befehls-Filter; das Folge-Ticket ist noch nicht angelegt.

## Freigabe-Frage

Reicht dir Scheibe 1 als freiwilliger Weg, mit Pflicht und Migration später in einem Folge-Ticket?
