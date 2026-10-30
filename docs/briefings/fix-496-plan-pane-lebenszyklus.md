---
spec_file: docs/specs/fix-496-plan-pane-lebenszyklus.md
spec_sha256: 36679b0a3ffd90da969cd5b1acac9766d4f6218297f9b0c799d73690f81ce1ab
spec_frozen_sha256: 0c9cf46b13b433aed54a41ac26a32b063a4cc0a31157eb350ee07b40ce910cf2
---

# PO-Briefing: fix-496-plan-pane-lebenszyklus

- **Spec:** docs/specs/fix-496-plan-pane-lebenszyklus.md
- **Issue:** #496
- **Erstellt:** 2026-10-30

## Was gebaut wird

Jede Claude-Session mit Workflow hat genau ein Workflow-Pane, das mit der Session verschwindet; fremde Panes bleiben immer unangetastet.

## Definition of Done

Im echten Herdr gibt es nach Start, Neustart, Update und /clear genau ein Pane, nach Sessionende keines, fremde Panes bleiben.

## Wie geprüft wird

Automatische Tests mit Attrappe prüfen jede Regel; ein Lauf im echten Herdr mit zwei parallelen Sessions belegt das Zusammenspiel.

## Kritische Anmerkungen

- Nach hartem Abbruch der Session bleibt das Pane bis zu sechs Sekunden stehen.
- Ein von Hand "Workflow" genanntes Pane ohne Besitzer wird immer geschlossen.
- Zombies anderer Arbeitsbereiche räumt nur eine Session dort auf, bewusst nicht von hier aus.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
