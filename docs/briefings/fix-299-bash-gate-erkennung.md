---
spec_file: docs/specs/fix-299-bash-gate-erkennung.md
spec_sha256: 4e56325e25cdea41b06ea24008960af8293ce91c19fef1b5fe71501864539545
---

# PO-Briefing: fix-299-bash-gate-erkennung

- **Spec:** docs/specs/fix-299-bash-gate-erkennung.md
- **Issue:** #299
- **Erstellt:** 2026-10-01

## Was gebaut wird

Die Commit-Sperre erkennt bisher durchgerutschte Schreibweisen von Commits und blockiert sie wie normale Commits.

## Definition of Done

Fünf bisher durchgelassene Commit-Schreibweisen werden blockiert, harmlose Befehle laufen weiter, und die Rebase-Meldung nennt einen Befehl, der tatsächlich funktioniert.

## Wie geprüft wird

Automatische Tests spielen jede Schreibweise gegen die echte Sperre durch, auch gegen Über-Blockieren; vorsätzliche Verschleierung wird nicht getestet.

## Kritische Anmerkungen

- Nur Teil A: Alias-Umgehung (#281) und merge/cherry-pick (#297) bleiben offen; #299 wird dadurch nicht geschlossen.
- Vorsätzliche Umgehung (Umgebungsvariablen, eval) bleibt möglich; geschützt wird nur gegen versehentliches Überspringen.
- Rebase-Pflicht wird nur im Hinweistext korrigiert; Messort bleibt, weil Angleichung einen bestehenden Test bricht.

## Freigabe-Frage

Soll Teil A freigegeben werden, mit Teil B als eigenem Folgeauftrag?
