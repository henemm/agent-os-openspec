---
spec_file: docs/specs/fix-528-ship-default-branch.md
spec_sha256: e72d66e4c152fa0c890f384efd49b433c872e3d27ae062d86cabfd9758f2763b
spec_frozen_sha256: 55f77f54322b60e127b3399e71cd65ae469cdaa7a77b6bc325aa5b55554bfa87
---

# PO-Briefing: fix-528-ship-default-branch

- **Spec:** docs/specs/fix-528-ship-default-branch.md
- **Issue:** #528
- **Erstellt:** 2026-11-06

## Was gebaut wird

Claude liefert im Auto-Modus auch dann selbständig aus, wenn die Arbeit direkt auf dem Hauptzweig liegt.

## Definition of Done

Bei Selbst-Ausliefern auf dem Hauptzweig legt Claude einen eigenen Arbeitszweig an und liefert aus, ohne dem PO einen Git-Schritt zu nennen.

## Wie geprüft wird

Automatische Textprüfungen belegen jede Anforderung in der Anleitung; das tatsächliche Verhalten im Lauf wird nicht getestet.

## Kritische Anmerkungen

- Zusatz: Auch "master" und losgelöster Stand lösen den neuen Arbeitszweig aus; das ist sinngemäss von der Anfrage gedeckt.
- Früher lokal auf dem Hauptzweig gespeicherte Änderungen landen im neuen Pull Request; der lokale Hauptzweig weicht danach ab.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
