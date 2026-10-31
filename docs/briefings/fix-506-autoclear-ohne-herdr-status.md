---
spec_file: docs/specs/fix-506-autoclear-ohne-herdr-status.md
spec_sha256: 4e33b9a416c5e932dcc8981ad5d28fb1ea10ea655aa88ae6bd65adb1d9b32729
spec_frozen_sha256: 6896f42bbcaf260df36c2caee982c0bd5425723a95276b9952b811b79c75ffc0
---

# PO-Briefing: fix-506-autoclear-ohne-herdr-status

- **Spec:** docs/specs/fix-506-autoclear-ohne-herdr-status.md
- **Issue:** #506
- **Erstellt:** 2026-10-31

## Was gebaut wird

Automatisches /clear mit anschließendem Folgebefehl klappt an Phasengrenzen auch dann, wenn Herdr die fertige Sitzung als wartend meldet.

## Definition of Done

Im echten Herdr mit Ihren Erkennungsregeln laufen /clear und der nächste Befehl durch; bei offenem Berechtigungsdialog wird nichts getippt.

## Wie geprüft wird

Automatische Tests und Läufe im echten Herdr belegen Erfolg sowie Abbruch bei neuer Eingabe oder offenem Dialog.

## Kritische Anmerkungen

- Restrisiko: Fortsetzung nur mit Text, länger als die Wartezeit, wird nicht erkannt; /clear könnte in den laufenden Turn gelangen.
- Eingetippt wird per simulierten Tasten statt Herdrs Befehlsfunktion, weil Herdr diese bei Ihrem Status ablehnt.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
