---
spec_file: docs/specs/feat-476-herdr-plan-pane.md
spec_sha256: b616499d60127c763ce108d0688c0dffeb3e43c765561c8d937027254b70245a
spec_frozen_sha256: e86cc5c2b0e58f5a8d098b2e715bb4c20a7e4e2450e26284e2dad0b41df28112
---

# PO-Briefing: feat-476-herdr-plan-pane

- **Spec:** docs/specs/feat-476-herdr-plan-pane.md
- **Issue:** #476
- **Erstellt:** 2026-10-29

## Was gebaut wird

Beim Workflow-Start öffnet sich rechts neben Claude ein Bereich, der alle Schritte mit erledigt, laufend und offen live zeigt.

## Definition of Done

In echtem Herdr erscheint nach dem Start rechts der Bereich „Workflow“ und folgt Phasenwechseln.

## Wie geprüft wird

Tests prüfen Anzeige und Öffnen mit Ersatzprogramm; echtes Aussehen und Nachziehen prüft nur Ihre Abnahme.

## Kritische Anmerkungen

- Bereich öffnet automatisch und verkleinert Claude auf etwa drei Viertel der Breite; abschaltbar.
- Öffnet nur beim Start, nicht nach Sitzungsneustart oder Workflow-Wechsel.
- Das Nachziehen binnen einer Sekunde hat keinen automatischen Test.

## Freigabe-Frage

Soll der Plan-Bereich wie beschrieben automatisch beim Workflow-Start aufgehen, mit Ihrer Abnahme in echtem Herdr?

## Ampel

Ampel: rot
