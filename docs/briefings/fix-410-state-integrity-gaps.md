---
spec_file: docs/specs/fix-410-state-integrity-gaps.md
spec_sha256: 2ae1522764f5c341837d2e68f6a7c58d2c18b59464f78c9b1f8415920323fa09
---

# PO-Briefing: fix-410-state-integrity-gaps

- **Spec:** docs/specs/fix-410-state-integrity-gaps.md
- **Issue:** #410
- **Erstellt:** 2026-10-09

## Was gebaut wird

Das Gate erkennt weitere versehentliche Wege, Workflow-Zustand zu überschreiben, und schützt die wirksame Gate-Konfiguration.

## Definition of Done

Aufgelistete Schreibbefehle werden blockiert, harmlose Lesebefehle laufen weiter, Konfigurationsänderung geht nur nach „override“.

## Wie geprüft wird

Automatische Tests prüfen jeden Befehl am echten Gate in beide Richtungen; vorsätzliche Umgehung, etwa per Python, fangen sie nicht.

## Kritische Anmerkungen

- Neu für dich: Änderungen an der Live-Konfiguration brauchen künftig immer dein „override“, auch ohne laufenden Workflow.
- Prüfung an der Quelle und Pipe-Umgehungen bleiben offen (Tickets 416/417).
- Bewusster Fehlalarm: Lesen mit Platzhalter plus Umleitung wird blockiert.

## Freigabe-Frage

Akzeptierst du, dass Konfigurationsänderungen künftig dein „override“ brauchen und vorsätzliche Umgehungen vorerst offen bleiben?
