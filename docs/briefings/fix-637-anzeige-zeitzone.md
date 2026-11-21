---
spec_file: docs/specs/fast/fix-637-anzeige-zeitzone.md
spec_sha256: 31077e9af117ff0c0a3091ce7c90c46fa7f26e8c825e35196cb8b23426ba9827
spec_frozen_sha256: 640df9dbb9db95599f6071176a4e598f1a9f50a72e99c946cc282b02bc69fa75
---

# PO-Briefing: fix-637-anzeige-zeitzone

- **Spec:** docs/specs/fast/fix-637-anzeige-zeitzone.md
- **Issue:** #637
- **Erstellt:** 2026-11-21

## Was gebaut wird

Das Plugin zeigt alle Uhrzeiten der Zeitschätzung in deutscher Zeit statt in der UTC-Zeit des Servers.

## Definition of Done

Auf einem UTC-Server zeigt der Plan-Block für einen Start um 16:46 UTC die Zeit 17:46, und die Schätzung nennt ebenfalls deutsche Zeit.

## Wie geprüft wird

Automatische Tests mit simulierter UTC-Systemzone prüfen Standard, Einstellung „local“ und ungültigen Zonennamen; echte Anzeige auf deinem Server wird nicht geprüft.

## Kritische Anmerkungen

- Du wolltest „lokale Zeit“; die Spec setzt stattdessen fest Europe/Berlin als Standard, „local“ bleibt wählbar.
- Der zweite Befund aus Issue 637 (Ende bei laufender Auslieferung) bleibt offen und ist nicht Teil dieser Korrektur.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
