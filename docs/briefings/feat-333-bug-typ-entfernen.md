---
spec_file: docs/specs/feat-333-bug-typ-entfernen.md
spec_sha256: 5832f50ea7e5c1e36355d1cebcb7eb32071cf4d4a7bf5db1bfaa239ee38091fa
---

# PO-Briefing: feat-333-bug-typ-entfernen

- **Spec:** docs/specs/feat-333-bug-typ-entfernen.md
- **Issue:** #333
- **Erstellt:** 2026-10-03

## Was gebaut wird

Der Workflow-Typ „Bug" mit Schnellweg und der Befehl /00-bug verschwinden; Fehler laufen nur noch über den normalen Eingang.

## Definition of Done

Kein Bug-Schnellweg mehr in Hooks, Befehlen oder Doku; Bug-Start wird verständlich abgelehnt; alte Workflows lesbar; Vollsuite grün.

## Wie geprüft wird

Automatische Tests prüfen Ablehnung, Altbestand, Alias-Aufräumen und Doku-Suche; nicht geprüft wird das Verhalten in fremden Konsumenten-Projekten.

## Kritische Anmerkungen

- Laufende Alt-Workflows vom Typ Bug bekommen volle Gates und können blockieren; das Rezept steht nur im Änderungsprotokoll.
- Umfang etwa 27 Dateien statt 4–5; von Ihnen entschieden, aber Prüfaufwand hoch.

## Freigabe-Frage

Soll der Bug-Schnellweg samt /00-bug endgültig entfernt werden, obwohl laufende Alt-Workflows dann volle Prüfungen durchlaufen?
