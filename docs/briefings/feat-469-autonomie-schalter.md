---
spec_file: docs/specs/feat-469-autonomie-schalter.md
spec_sha256: 09d50de7ca7672eb8501d15ff21047d42fe3c150f7ed0c96dd9eb134ef38a82f
spec_frozen_sha256: fc3fe7ac565fe41a8ad90baaa5644011e11eeeb97283ed280883bf40b8b26238
---

# PO-Briefing: feat-469-autonomie-schalter

- **Spec:** docs/specs/feat-469-autonomie-schalter.md
- **Issue:** #469
- **Erstellt:** 2026-10-28

## Was gebaut wird

Ein Konfigurationsschalter für Autonomie (Standard: manuell) samt Protokoll, das künftige automatische Freigaben nachvollziehbar festhält.

## Definition of Done

Die Abfrage meldet ohne Einstellung "manual" und mit Einstellung "auto" "auto"; der Status zeigt eingetragene Freigaben, alle bisherigen Tests bleiben grün.

## Wie geprüft wird

Automatische Tests belegen Schalter, Protokoll, Anzeige und Rückfall auf manuell bei Fehlern; echtes Verhalten im Alltag wird nicht erprobt, da nichts ihn nutzt.

## Kritische Anmerkungen

- Der Schalter wirkt noch nirgends; alle Freigaben bleiben bis zu den Teilen B bis D manuell.
- Nur die Konfiguration des Hauptordners zählt; eine in einer Arbeitskopie geänderte Einstellung wird ignoriert.
- Der Test zu "nichts kaputt" prüft nur, dass kein Gate den Schalter nutzt; der Gesamtlauf ist kein Test.

## Freigabe-Frage

Soll der Schalter als reine Vorbereitung ohne Wirkung gebaut werden?
