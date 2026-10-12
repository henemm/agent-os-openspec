---
spec_file: docs/specs/infra/fix-405-424-workflow-ausgaenge.md
spec_sha256: 8f2a218654b7287fd80ff8cdaf0eb5c15454d5c5fbe5686bbf61b46479fe4678
---

# PO-Briefing: fix-405-424-workflow-ausgaenge

- **Spec:** docs/specs/infra/fix-405-424-workflow-ausgaenge.md
- **Issue:** #405, #424
- **Erstellt:** 2026-10-12

## Was gebaut wird

Nach Rücksprung zur Spec gilt eine erneute Freigabe wieder, und bei "nichts bauen" führt die Fußzeile zum sauberen Abschluss.

## Definition of Done

Nach Rücksprung und geänderter Spec bringt "approved" den Workflow in die Freigabe-Phase; nach "nichts bauen" nennt die Fußzeile den Abschluss-Befehl, der archiviert.

## Wie geprüft wird

Automatische Tests mit echten Hooks belegen alle elf Kriterien; ob der Abschluss-Befehl den neuen Zweig wählt, prüft nur ein Textvergleich.

## Kritische Anmerkungen

- PO-Vorgabe: #405 braucht nicht den vollen Workflow; die Spec bündelt es trotzdem mit #424.
- Ungefragter Zusatz: Der Abschluss archiviert künftig auch Workflows ohne Spec automatisch als verworfen.

## Freigabe-Frage

Soll die Änderung mit Freigabe-Rücksetzung beim Rücksprung und dem neuen "nichts bauen"-Ausgang freigegeben werden?
