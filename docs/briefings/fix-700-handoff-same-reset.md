---
spec_file: docs/specs/fix-700-handoff-same-reset.md
spec_sha256: 1367368d3cab3b9e3895f7e5ae783e790f130614aa34c71396abc6dadbf67914
spec_frozen_sha256: 870f2a182af8e3fd111126c89f018a739562a653664769b2a7a377b0e04f6aba
---

# PO-Briefing: fix-700-handoff-same-reset

- **Spec:** docs/specs/fix-700-handoff-same-reset.md
- **Issue:** #700
- **Erstellt:** 2026-11-27

## Was gebaut wird

Nach einem Rücksprung in dieselbe Phase kann der Workflow wieder eine frische Sitzung übergeben, statt stehenzubleiben.

## Definition of Done

Ein Workflow, der nach BROKEN in dieselbe Phase zurückkehrt, startet dort erneut eine Nachfolgesitzung; der Doppelstart-Schutz innerhalb einer Phase bleibt bestehen.

## Wie geprüft wird

Automatische Tests mit Attrappen belegen Rücksprung, Doppelstart-Schutz und Abschluss; ein Echtlauf mit dem echten Terminal-Werkzeug fehlt.

## Kritische Anmerkungen

- Zusätzlich wird der Vermerk auch beim Workflow-Abschluss verworfen; vom Ticket nicht verlangt, aber harmlos.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
