---
spec_file: docs/specs/fix-409-worktree-always-allowed.md
spec_sha256: cc7a0ff864e16d2da3cd1ca6383bf6426c7c4a9ef504da33b18e309b67d1f917
---

# PO-Briefing: fix-409-worktree-always-allowed

- **Spec:** docs/specs/fix-409-worktree-always-allowed.md
- **Issue:** #409
- **Erstellt:** 2026-10-09

## Was gebaut wird

Code-Schutzprüfungen greifen künftig auch in Arbeitsordner-Sitzungen, statt dort alles durchzuwinken.

## Definition of Done

Code-Edits im Arbeitsordner werden geprüft, Dokumentation und Konfiguration bleiben frei; alle zehn Kriterien sind automatisch getestet.

## Wie geprüft wird

Automatische Tests prüfen Pfadfälle und echte Prozessläufe; absichtlich eingebaute Fehler werden nur teilweise automatisch nachgewiesen.

## Kritische Anmerkungen

- Die Prüfungen greifen erstmals real: laufende Projekte können nach dem Update plötzlich blockiert werden.
- Zusatz: Pfade ausserhalb des Projekts, etwa /tmp, werden künftig nicht mehr geprüft — nicht verlangt.
- Zwei der drei Fehlerproben sind nicht automatisiert, sondern nur im Adversary-Dialog vorgesehen.

## Freigabe-Frage

Darf die Prüfung in allen Projekten scharf geschaltet werden, trotz möglicher Blockaden und der Lockerung ausserhalb?
