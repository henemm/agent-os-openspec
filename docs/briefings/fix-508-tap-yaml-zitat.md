---
spec_file: docs/specs/fix-508-tap-yaml-zitat.md
spec_sha256: 739464410468b0c1eca38f63b9e55d22a66aba3fc874381ea296b214898ccbc9
spec_frozen_sha256: e0b085368dd64928985ac60bcb9be876d9b442e986b2f1f27d3b4eb7d9befbe8
---

# PO-Briefing: fix-508-tap-yaml-zitat

- **Spec:** docs/specs/fix-508-tap-yaml-zitat.md
- **Issue:** #508
- **Erstellt:** 2026-11-04

## Was gebaut wird

Echte Testausgaben von node mit dem Wort „placeholder:" werden nicht mehr fälschlich als Platzhalter-Text abgelehnt.

## Definition of Done

Die Beispielausgabe aus dem Ticket wird als gültiger fehlgeschlagener Test akzeptiert, und alle bisherigen Prüfungen bleiben unverändert grün.

## Wie geprüft wird

Automatische Tests belegen jede Anforderung samt Gegenfällen; nicht abgedeckt ist die Ausgabe im node-Format „spec".

## Kritische Anmerkungen

- Bekannte Lücke: Bei der node-Ausgabe im Format „spec" wird „placeholder:" weiterhin abgelehnt; Folge-Ticket nötig.
- Gefälschte Ausgaben können Platzhalter in solchen Blöcken verstecken; die Prüfung auf echte Fehlerhinweise bleibt als Schutz bestehen.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
