---
spec_file: docs/specs/fix-506-autoclear-ohne-herdr-status.md
spec_sha256: 8c10d3d276f0236aab7c0ccf5e30be8d131fc3c861cbcdbaeb99dc87bd44078b
spec_frozen_sha256: 7dc5d1949b0bb2b23fc836069f330dc7342fb64f170f472c425a2b67d6e2eee5
---

# PO-Briefing: fix-506-autoclear-ohne-herdr-status

- **Spec:** docs/specs/fix-506-autoclear-ohne-herdr-status.md
- **Issue:** #506
- **Erstellt:** 2026-10-31

## Was gebaut wird

Das automatische /clear an Phasengrenzen funktioniert wieder zuverlässig, weil das Plugin eigene Signale nutzt statt Herdrs Statusmeldung.

## Definition of Done

Im echten Herdr mit nachgebautem Regelwerk laufen /clear und Folgebefehl durch, während der alte Stand im selben Test abbricht.

## Wie geprüft wird

Automatische Tests und ein echter Herdr-Lauf belegen es; dein eigener Alltagsbetrieb bleibt ungeprüft.

## Kritische Anmerkungen

- Herdr wird nicht benachrichtigt, sondern nur als Tastatur benutzt; das erfüllt deinen Wunsch dem Sinn nach, nicht wörtlich.
- Getippter, nicht abgeschickter Text vermischt sich mit /clear; Eingaben zwischen /clear und Folgebefehl bleiben unbemerkt (bekannte Grenze).

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
