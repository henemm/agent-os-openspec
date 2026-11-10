---
spec_file: docs/specs/fix-561-nachpruefung-broken.md
spec_sha256: 21b2be7a6215a5d6d1c3e5a67dd0ced067054895340321f5282c89ab58878300
spec_frozen_sha256: 04607312d3f1b3d3dda194457be6e2692c2e2c0f1996a14ec0efd198e87de765
---

# PO-Briefing: fix-561-nachpruefung-broken

- **Spec:** docs/specs/fix-561-nachpruefung-broken.md
- **Issue:** #561
- **Erstellt:** 2026-11-10

## Was gebaut wird

Findet die Prüfung nach der Auslieferung einen fachlichen Fehler, springt der Workflow zurück, und der Plan zeigt den echten Stand.

## Definition of Done

Nach dem Rücksprung zeigt der Plan keinen alten Auslieferungs-Stand mehr, nach erneuter Auslieferung steht dort „offen“, und die Anleitungen beschreiben den Rückweg.

## Wie geprüft wird

Automatische Tests belegen jede Anforderung; ob Claude die Anleitung tatsächlich befolgt, prüft kein Test.

## Kritische Anmerkungen

- Keine — Spec deckt die Anfrage ab, jede Anforderung hat einen Test.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
