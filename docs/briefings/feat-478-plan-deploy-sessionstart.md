---
spec_file: docs/specs/feat-478-plan-deploy-sessionstart.md
spec_sha256: e64ab1903d1e3bbfd00220d2d74dcd8b851bafdf6f9e5b8a4039f0377f237841
spec_frozen_sha256: d9e997c1ebf4bd86a649dbe02469fcbd32037002cfa09c584d21c3154095da98
---

# PO-Briefing: feat-478-plan-deploy-sessionstart

- **Spec:** docs/specs/feat-478-plan-deploy-sessionstart.md
- **Issue:** #478
- **Erstellt:** 2026-10-29

## Was gebaut wird

Plan zeigt Deploy als offenen Schritt, öffnet sich beim Claude-Start, und das Log erklärt, warum Auto-/clear nicht auslöst.

## Definition of Done

Mit Deploy-Konfiguration steht nach Phase 8 „Deploy (offen)“ samt Befehl im Plan; nach Neustart öffnet sich der Plan-Bereich wieder.

## Wie geprüft wird

Automatische Tests belegen jede Anforderung; ob es im echten Herdr gut aussieht und funktioniert, prüft nur deine manuelle Abnahme.

## Kritische Anmerkungen

- Auto-/clear löst in Phase 8 weiterhin nicht aus; nur das Log nennt den Grund.
- Ohne Deploy-Konfiguration kein Deploy-Schritt; erledigt gilt Deploy erst mit Archivierung.
- Zusatz ohne Anfrage: doppelte Log-Zeilen werden unterdrückt; Tests decken nur zwei der acht Abbruchgründe ab.

## Freigabe-Frage

Passt dir, dass Auto-/clear in Phase 8 nicht auslöst und Deploy nur mit Deploy-Konfiguration erscheint?

## Ampel

Ampel: rot
