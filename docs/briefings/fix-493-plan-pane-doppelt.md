---
spec_file: docs/specs/fix-493-plan-pane-doppelt.md
spec_sha256: d61741aa18769e24a65e35ec4b524348a3df7d06671e6fc7ce79681813d95518
spec_frozen_sha256: 652ecad905f85b3e65f7ba3f3a3cc8fc528328fe1648c89a48ccb6aae65b1db0
---

# PO-Briefing: fix-493-plan-pane-doppelt

- **Spec:** docs/specs/fix-493-plan-pane-doppelt.md
- **Issue:** #493
- **Erstellt:** 2026-10-30

## Was gebaut wird

Nach Neustart von Claude im selben Herdr-Fenster wird der vorhandene Workflow-Seitenbereich wiederverwendet statt ein zweiter geöffnet.

## Definition of Done

Nach Beenden und Neustart von Claude im selben Fenster existiert genau ein Seitenbereich, der den Workflow der neuen Sitzung zeigt.

## Wie geprüft wird

Automatische Tests mit Attrappe prüfen Wiederverwendung und Umschalten; das echte Herdr-Verhalten bleibt deine manuelle Abnahme.

## Kritische Anmerkungen

- Der Seitenbereich schließt sich weiterhin nicht beim Beenden von Claude, sondern bleibt bewusst offen zur Wiederverwendung.
- Einmalig nach dem Update kann noch ein zusätzlicher Seitenbereich entstehen; der alte muss von Hand geschlossen werden.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
