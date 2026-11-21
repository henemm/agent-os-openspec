---
spec_file: docs/specs/feat-640-auslieferung-schneller.md
spec_sha256: 9ada35507d0e38d10c18925cb0ad654bfbea83643342f0083eafd44ca0537e75
spec_frozen_sha256: eed90343d2f39f0b9a248ff4f05fe09305e187562f980ac92a40847b08e4cb76
---

# PO-Briefing: feat-640-auslieferung-schneller

- **Spec:** docs/specs/feat-640-auslieferung-schneller.md
- **Issue:** #640
- **Erstellt:** 2026-11-21

## Was gebaut wird

Tests laufen parallel, und eine einzeln ausgelieferte Korrektur enthält die Versionsnummer gleich selbst, sodass nur noch ein Testlauf nötig ist.

## Definition of Done

Der Testlauf im Pull Request ist messbar kürzer, drei Läufe in Folge bleiben grün, und eine Einzel-Auslieferung braucht bis zur Veröffentlichung nur einen Testlauf.

## Wie geprüft wird

Automatische Tests prüfen Einstellungen, Rückfall auf seriell und Doku-Konsistenz; die tatsächliche Zeitersparnis wird nur in der CI gemessen, nicht per Test.

## Kritische Anmerkungen

- Die Regel „Release als eigener PR" aus deiner Vorgabe entfällt bei Einzel-Auslieferung; getrennter Release bleibt nur beim Bündeln.
- Der Zeitgewinn hängt von der Runner-Größe ab; gemessen wurden 192 statt 708 Sekunden lokal, ohne CI-Zahl.
- Umfang überschreitet die 5-Dateien-Grenze, begründet mit zusammengehörender Doku.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
