---
spec_file: docs/specs/fix-557-kontext-grundlast.md
spec_sha256: 42896765c4fcb977cb53152b8a244ce36981aeb46bc4daf7ad01db516f7812b0
spec_frozen_sha256: 7d6d3ec5236ccb7cf3b38d179fed25d5a7842897a03dd367de59dc67e0f10fde
---

# PO-Briefing: fix-557-kontext-grundlast

- **Spec:** docs/specs/fix-557-kontext-grundlast.md
- **Issue:** #557
- **Erstellt:** 2026-11-09

## Was gebaut wird

Cloud-Sitzungen melden den Kontext-Schnitt erst nach echtem Wachstum, nicht schon wegen ihres großen Grundkontexts.

## Definition of Done

Eine Sitzung mit 100.000 Grundkontext meldet erst nach 75.000 zusätzlichen Token Schnittbedarf; lokale Sitzungen behalten die Schwelle 100.000.

## Wie geprüft wird

Automatische Tests prüfen Cloud- und Lokal-Szenario, Zurücksetzen nach /clear und alte Messdateien; ob Claude beim Hinweis wirklich anhält, wird nicht geprüft.

## Kritische Anmerkungen

- Cloud-Schwelle liegt damit bei 175.000 statt 100.000; das Wachstumsbudget von 75.000 ist eine Annahme der Spec.
- Ein /compact, das unter 30 Prozent einspart, setzt den Grundkontext nicht zurück; die Schwelle bleibt dann höher.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
