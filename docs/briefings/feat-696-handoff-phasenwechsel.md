---
spec_file: docs/specs/feat-696-handoff-phasenwechsel.md
spec_sha256: 4ba032e02e644521f5f5f472336779d030b9befecd2a80961d1ae3b7eb1d81bc
spec_frozen_sha256: 89a9f7f0465367642ecbf985b2919a9a5372cbff62c509cd8f5886383827b21d
---

# PO-Briefing: feat-696-handoff-phasenwechsel

- **Spec:** docs/specs/feat-696-handoff-phasenwechsel.md
- **Issue:** #696
- **Erstellt:** 2026-11-26

## Was gebaut wird

Wird der Arbeitsspeicher innerhalb eines Issues zu voll, setzt Claude die Arbeit am Phasenwechsel in einem neuen Tab fort.

## Definition of Done

Ein Workflow, der unter Herdr die Schwelle überschreitet, läuft im neuen Tab am selben Arbeitsstand weiter, der alte Tab schliesst sich.

## Wie geprüft wird

Automatische Tests mit einem Herdr-Ersatz belegen jede Regel; der Echtlauf mit echtem Herdr ist nur manuell möglich und folgt im Issue.

## Kritische Anmerkungen

- Die alte Sitzung muss nach dem Start sofort aufhören; das steht nur im Befehlstext, nichts erzwingt es.
- Keine Übergabe bei Phase 3 mit Freigabe und nach Auslieferung; dort gilt das bisherige Verhalten.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
