---
spec_file: docs/specs/fix-299-bash-gate-erkennung-teil-c.md
spec_sha256: 7ca17d49807066ae7e841cc325e37cee7c09501b67478c38aead167c175cfcf8
---

# PO-Briefing: fix-299-teil-c

- **Spec:** docs/specs/fix-299-bash-gate-erkennung-teil-c.md
- **Issue:** #299
- **Erstellt:** 2026-10-02

## Was gebaut wird

Das Gate erkennt drei bisher übersehene Wege, Workflow-Zustandsdateien per Shell zu überschreiben, und blockiert sie.

## Definition of Done

Die drei Umgehungen werden abgewiesen, harmlose Befehle laufen weiter, und alle bisherigen Tests bleiben grün.

## Wie geprüft wird

Automatische Tests schicken Umgehungs- und Kontrollbefehle durch das echte Gate; vorsätzliche Verschleierung (eval, Skripte) wird nicht geprüft.

## Kritische Anmerkungen

- Abweichung: Alias-Prüfung (#324) und CI-Nachweis (#325) sind ausgelagert; beide Lücken bleiben vorerst offen.
- Die Änderung am gemeinsamen Befehls-Zerleger wirkt auf alle Prüfungen; Fehlalarme würden Arbeit blockieren.
- Verhindert wird nur versehentliches Umgehen; absichtliches bleibt möglich.

## Freigabe-Frage

Freigeben, obwohl Alias-Lücke und CI-Nachweis in eigene Vorgänge ausgelagert sind?
