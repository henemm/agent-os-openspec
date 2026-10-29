---
spec_file: docs/specs/feat-480-auto-clear-global.md
spec_sha256: 112c6f5a4c46b08769a8a4be6bbe07482b70366a291df967894e1097f909efb7
spec_frozen_sha256: dcf9d8a6cd68069befa0bcc55ae80ab6aa49d46dd04c45761fa4743abacfc798
---

# PO-Briefing: feat-480-auto-clear-global

- **Spec:** docs/specs/feat-480-auto-clear-global.md
- **Issue:** #480
- **Erstellt:** 2026-10-29

## Was gebaut wird

Auto-/clear lässt sich einmal für alle Projekte einschalten; die Fehlermeldung nach Befehlen verschwindet.

## Definition of Done

Mit gesetztem Schalter räumt Herdr in einem Projekt ohne eigene Einstellung auf, und nach Befehlen erscheint kein „Permission denied“ mehr.

## Wie geprüft wird

Automatische Tests belegen Vorrangregeln und Ausführungsrecht; ob es in echtem Herdr wirkt, prüfst du manuell.

## Kritische Anmerkungen

- Der Schutz gegen Dauerlast lief bisher nie und beendet künftig lange Suchen ab Home-Verzeichnis automatisch — erstmals aktiv, Nebenwirkung ungetestet.
- Der Schalter ist kein Klick: Du bearbeitest selbst eine Einstellungsdatei, Wirkung erst nach Neustart von Claude Code.
- Fehlerfix ist nur per Dateirecht-Test belegt; ob die Meldung verschwindet, zeigt allein deine Abnahme.

## Freigabe-Frage

Darf der bisher nie gelaufene Dauerlast-Schutz mit diesem Ticket erstmals scharf werden?

## Ampel

Ampel: rot
