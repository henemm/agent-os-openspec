---
spec_file: docs/specs/fix-299-bash-gate-erkennung.md
spec_sha256: 54bfb33e177a8f5f77abf92c2536ab28a529aaeb5235c721fc25b59f90eefbc8
---

# PO-Briefing: fix-299-bash-gate-erkennung

- **Spec:** docs/specs/fix-299-bash-gate-erkennung.md
- **Issue:** #299
- **Erstellt:** 2026-10-01

## Was gebaut wird

Der Commit-Schutz erkennt fünf bisher übersehene Schreibweisen, und die Rebase-Meldung nennt einen Befehl, der bei vorgemerkten Dateien funktioniert.

## Definition of Done

Alle genannten Umgehungen werden blockiert, harmlose Befehle bleiben erlaubt, und der empfohlene Rebase-Befehl gelingt bei vorgemerkten Dateien.

## Wie geprüft wird

Automatische Tests spielen jede Schreibweise gegen die echte Sperre durch, in beide Richtungen; Alias-Tricks und absichtliche Verschleierung prüfen sie nicht.

## Kritische Anmerkungen

- Nur Teil A: Alias- und merge-Umgehungen (#281, #297) bleiben offen, #299 ist nicht erledigt.
- Gefordert war eine strukturelle Zustandsprüfung; geliefert wird weitere Textmustererkennung, vorsätzliche Umgehung bleibt möglich.
- #284: Nur der Meldungstext ändert sich, keine Reihenfolge-Korrektur.

## Freigabe-Frage

Genügt es dir, dass #299 nur teilweise gelöst wird und Alias-Umgehungen vorerst offen bleiben?
