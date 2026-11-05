---
spec_file: docs/specs/fix-521-spec-platzhalter-lokal.md
spec_sha256: 4daf1b61d4027c8039112a49a47c74d2ba2edf8e0aa98c974f1a3ff422c3c0a7
spec_frozen_sha256: 25a6828d41803931fe84fc554a74100881e168915062c178784b6f296e43f876
---

# PO-Briefing: fix-521-spec-platzhalter-lokal

- **Spec:** docs/specs/fix-521-spec-platzhalter-lokal.md
- **Issue:** #521
- **Erstellt:** 2026-11-05

## Was gebaut wird

Die Spec-Prüfung der CI läuft schon bei der lokalen Freigabe, damit abgelehnte Specs nicht erst später auffallen.

## Definition of Done

Eine Spec, die die CI ablehnt, lässt sich lokal nicht freigeben, und es gibt nur noch eine Platzhalter-Liste.

## Wie geprüft wird

Automatische Tests belegen Freigabe-Sperre, Gleichstand mit der CI und die einzelne Liste; echte Konsumenten-Projekte werden nicht getestet.

## Kritische Anmerkungen

- Die CI wird bei einem Platzhalter-Marker strenger; bestehende Specs sind laut Spec geprüft und unauffällig.
- Das Briefing-Werkzeug prüft die Spec nicht; Fehler zeigen sich erst bei der Freigabe.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
