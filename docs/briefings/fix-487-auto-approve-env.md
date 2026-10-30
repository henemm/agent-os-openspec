---
spec_file: docs/specs/fix-487-auto-approve-env.md
spec_sha256: 06f87df6e55fc5f02ef0b921a7179f33652f76109272e45b8273d42f5e3c3f16
spec_frozen_sha256: 10ff9e87e84d0b94fa76ca92b3937e5e50ffb1da4ac9ab7130d131e4591d3138
---

# PO-Briefing: fix-487-auto-approve-env

- **Spec:** docs/specs/fix-487-auto-approve-env.md
- **Issue:** #487
- **Erstellt:** 2026-10-30

## Was gebaut wird

Die automatische Freigabe beachtet den benutzerweiten Autonomie-Schalter, sodass eine grüne Ampel die Spec ohne „approved“ freigibt.

## Definition of Done

In einem Projekt mit eingeschaltetem Schalter läuft eine Spec mit grüner Ampel ohne dein „approved“ bis zur Freigabe durch.

## Wie geprüft wird

Automatische Tests belegen Freigabe mit Schalter und Vorrang von „manual“; ob es in deiner echten Sitzung klappt, zeigt nur deine Abnahme.

## Kritische Anmerkungen

- Behoben wird nur die Freigabe; die „go“-Abfrage vor der Prüfphase ist nicht Teil dieser Spec.
- Nur eine Ursache wird behoben; wirkt es in deiner Sitzung trotzdem nicht, bleibt eine weitere Ursache.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
