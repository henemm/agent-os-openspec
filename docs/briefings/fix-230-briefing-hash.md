---
spec_file: docs/specs/fix-230-spec-freeze-after-approval.md
spec_sha256: bf40a0e5e5bbbe4f2298a3046aa9c683645bbe93adc11ce60e80ba2163107ecf
---

# PO-Briefing: fix-230-briefing-hash

- **Spec:** docs/specs/fix-230-spec-freeze-after-approval.md
- **Issue:** #230
- **Erstellt:** 2026-09-28

## Was gebaut wird

Freigegebene Spezifikationen werden vor nachträglichen Änderungen geschützt, damit automatische Dokumentationspflege den Arbeitsabschluss nicht mehr blockiert.

## Definition of Done

Ein Durchlauf mit automatischer Dokumentationspflege erreicht den Abschluss, ohne dass die Prüfung „Briefing veraltet" noch auftritt.

## Wie geprüft wird

Automatische Tests belegen Blockade und Freigabe-Ausnahme; sie prüfen nicht, ob der Verlust der Status-Nachführung in der Spezifikation hingenommen werden soll.

## Kritische Anmerkungen

- Weg 3 weicht von beiden Issue-Vorschlägen ab; Specs zeigen künftig nie mehr den Umsetzungsstand — PO nicht ausdrücklich gefragt.
- Der Schutz wirkt nur bei einem bestimmten Änderungsweg; über einen anderen ließe sich die Datei trotzdem noch ändern.
- Die Änderung wirkt in jedem Projekt mit aktiver Freigabeprüfung — ungetestet bleibt, wie bestehende, schon blockierte Fälle davon profitieren.

## Freigabe-Frage

Soll eine freigegebene Spezifikation künftig dauerhaft unveränderbar bleiben und ihren Umsetzungsstand nicht mehr selbst zeigen?
