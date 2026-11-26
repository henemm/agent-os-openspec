---
spec_file: docs/specs/fast/fix-671-wackelige-tests.md
spec_sha256: d0eef2fed99bb338e62de83109a6c9092eac8f45b97cbe5e9cce5b4ce62e2fe5
spec_frozen_sha256: 1700392917e00d0633d7bcd02ff41be4285ee2299ad0515e07c8ab37af9e544e
---

# PO-Briefing: fix-671-wackelige-tests

- **Spec:** docs/specs/fast/fix-671-wackelige-tests.md
- **Issue:** #671
- **Erstellt:** 2026-11-26

## Was gebaut wird

Zwei Tests, die in der automatischen Prüfung gelegentlich grundlos scheitern, werden stabil gemacht; das Produkt bleibt unverändert.

## Definition of Done

Beide Testdateien laufen mehrfach hintereinander grün, ein Änderungsprotokoll-Eintrag und eine neue Patch-Version liegen vor, am Produktivcode ist nichts geändert.

## Wie geprüft wird

Ein neuer Test belegt den Umgang mit halb geschriebenen Zeilen; die Laufzeitgrenze wird nur gegen simulierte Rechnerlast nicht eigens getestet.

## Kritische Anmerkungen

- Zwei Kriterien (halb geschriebene Zeile beim Schreiben, Scheitern bei echter Verlangsamung) haben keinen eigenen Test, nur indirekte Abdeckung.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
