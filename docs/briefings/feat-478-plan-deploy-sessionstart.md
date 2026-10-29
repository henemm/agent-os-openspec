---
spec_file: docs/specs/feat-478-plan-deploy-sessionstart.md
spec_sha256: 7fdf7a58e2c0ecc21014f66ca62272700b796eb72502bd9073b8ccf49fea4746
spec_frozen_sha256: f0081f1733751f1480ceaa6f7613bccbabe7306b06b2ddefcc47c0d71e6d3248
---

# PO-Briefing: feat-478-plan-deploy-sessionstart

- **Spec:** docs/specs/feat-478-plan-deploy-sessionstart.md
- **Issue:** #478
- **Erstellt:** 2026-10-29

## Was gebaut wird

Plan zeigt Deploy als offenen Schritt, öffnet sich beim Start, und Auto-/clear funktioniert wieder mit Fehlerprotokoll.

## Definition of Done

Bei konfiguriertem Deploy zeigt der Plan nach Phase 8 „Deploy offen“, öffnet beim Start, und Auto-/clear greift in Herdr.

## Wie geprüft wird

Tests mit Herdr-Attrappe prüfen Anzeige, Start und Auto-/clear; ob echtes Herdr so antwortet, zeigt nur Ihre Abnahme.

## Kritische Anmerkungen

- Auto-/clear-Fix beruht auf Herdr-Quellcode, nicht auf echtem Lauf; erst Ihre Abnahme beweist, dass er greift.
- Deploy wird erst bei Archivierung abgehakt; Projekte ohne vollständige Deploy-Einstellung sehen den Schritt nie.
- Fehlerprotokoll: nur zwei von acht Abbruchgründen getestet.

## Freigabe-Frage

Freigeben, obwohl der Auto-/clear-Fix erst in Ihrer Abnahme im echten Herdr bewiesen wird?

## Ampel

Ampel: rot
