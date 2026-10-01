---
spec_file: docs/specs/feat-286-herkunft-vorbedingungen.md
spec_sha256: 0d9257015dbb6ddf5b885221ed6ea188cb28312e2d593449cb76a1417ebe57f6
---

# PO-Briefing: feat-286-herkunft-vorbedingungen

- **Spec:** docs/specs/feat-286-herkunft-vorbedingungen.md
- **Issue:** #286
- **Erstellt:** 2026-09-30

## Was gebaut wird

Prüfberichte müssen künftig belegen, woher unklare Programm-Vorbedingungen stammen — sonst warnt oder blockiert das System automatisch.

## Definition of Done

Fertig ist es, wenn fehlende oder unvollständige Herkunfts-Angaben zuverlässig gemeldet werden — anfangs nur als Warnung, Blockieren muss extra eingeschaltet werden.

## Wie geprüft wird

Automatisierte Tests prüfen jeden Fall mit vorbereiteten Beispieldaten; im eigenen Projekt greift die Prüfung praktisch nie, da es keine passenden Dateien hat.

## Kritische Anmerkungen

- Ein Test prüft zwei Anleitungen, nicht die tatsächlich verwendete Kopie einer davon — nur ein Abgleich sichert das ab.

## Freigabe-Frage

Passt die Lösung so — meldet zunächst nur, kein automatisches Blockieren — trotz der Lücke bei den geprüften Anleitungstexten?
