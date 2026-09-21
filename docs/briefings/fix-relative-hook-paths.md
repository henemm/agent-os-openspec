---
spec_file: docs/specs/hook-paths-project-dir.md
spec_sha256: d15aef98dcc946151809435abb357f462eeef562b08c350c5e9c1d968f0e922b
---

# PO-Briefing: fix-relative-hook-paths

- **Spec:** docs/specs/hook-paths-project-dir.md
- **Issue:** #165
- **Erstellt:** 2026-09-21

## Was gebaut wird

Hook-Befehle werden projektfest statt ordnerabhängig, damit Nachrichten in Unterordnern nicht mehr abbrechen.

## Definition of Done

Neu erzeugte und reparierte Hook-Befehle enthalten keinen ordnerabhängigen Pfad mehr; der gemeldete Absturz bleibt nachweislich aus.

## Wie geprüft wird

Automatisierte Tests prüfen alle vier Anforderungen plus Nachstellung des ursprünglichen Fehlers; die drei betroffenen Bestandsprojekte werden nicht automatisiert getestet.

## Kritische Anmerkungen

- PO hat Umsetzung per "override" ohne formale Spec-Freigabe angeordnet — dieses Briefing dokumentiert nachträglich, nicht vorab.
- Die drei betroffenen Bestandsprojekte werden laut Spec explizit NICHT hier repariert, sondern erst danach — PO hat das bestätigt.

## Freigabe-Frage

Genügt dir automatisierter Testnachweis plus Nachstellung, und bleibt die Reparatur der drei Bestandsprojekte wie vereinbart ein späterer Schritt?
