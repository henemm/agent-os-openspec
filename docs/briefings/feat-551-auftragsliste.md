---
spec_file: docs/specs/feat-551-auftragsliste.md
spec_sha256: a54c407e26a8136c3bfb9d08cf2816ad1576278b6670133cc75fb3d5228011e5
spec_frozen_sha256: 5e5453f5214c796908ad679dcdc10e574a4fe65d483f4fba9680f5119f6d4fa2
---

# PO-Briefing: feat-551-auftragsliste

- **Spec:** docs/specs/feat-551-auftragsliste.md
- **Issue:** #551
- **Erstellt:** 2026-11-09

## Was gebaut wird

Ein Mehrfach-Auftrag wird in einer Datei gespeichert, übersteht /clear und wird Issue für Issue automatisch weiterverfolgt.

## Definition of Done

Nach /clear zeigt Claude den offenen Auftrag, schließt #547 ab und startet #548 selbst, ohne Halt für /clear.

## Wie geprüft wird

Automatische Tests belegen Speichern, Abhaken, Endmeldung und Sitzungsstart; ob Claude die Anweisungen tatsächlich befolgt, prüft kein Test.

## Kritische Anmerkungen

- Abweichung: /compact kann Claude nicht selbst auslösen; stattdessen komprimiert Claude Code automatisch — dein Wunsch nur indirekt erfüllt.
- Ohne Wort "autark" nennt die Übergabe nur das nächste Issue, nicht die ganze Restliste.
- Die Kettenfortsetzung beruht auf Befehlstexten; kein Hook erzwingt sie.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
