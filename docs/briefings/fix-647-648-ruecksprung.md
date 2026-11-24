---
spec_file: docs/specs/fix-647-648-ruecksprung.md
spec_sha256: 50234b4a08456b0b897c2e9ede5ea833fa08f63838bc85c58faaeee9f0dc6403
spec_frozen_sha256: aed41a445a0b28ee8476ee9d6536e63a7d085aae937a7c742c28b5a04eb62216
---

# PO-Briefing: fix-647-648-ruecksprung

- **Spec:** docs/specs/fix-647-648-ruecksprung.md
- **Issue:** #647
- **Erstellt:** 2026-11-24

## Was gebaut wird

Nach einem Rücksprung verlangt der Workflow wieder eine neue Spec, statt eine überholte freizugeben.

## Definition of Done

Nach einem Rücksprung zeigt die Fußzeile die Spec-Erstellung statt der Freigabe, und die Endstand-Abfrage nennt den aktiven Workflow.

## Wie geprüft wird

Automatische Tests belegen jede Anforderung samt Regressionslauf bestehender Tests; ein echter Ablauf im Live-Betrieb wird nicht geprüft.

## Kritische Anmerkungen

- Zusatz ohne Anfrage: Historie verworfener Briefings und Sperre der neuen Felder per set-field; unkritisch, begrenzt.
- Fälle, die vor dieser Änderung zurückgesprungen sind, behalten das alte Verhalten (dokumentiert, akzeptiert).

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
