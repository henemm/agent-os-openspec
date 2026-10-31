---
spec_file: docs/specs/fix-506-autoclear-ohne-herdr-status.md
spec_sha256: 2db67d7ff084a8e180dca5bd4ef634be898ca8675e070ba7e0e85e20d96b2d1f
spec_frozen_sha256: ec42af3997f9c0f5b140b84afecc7dfbef9720503240f90ebc28167b94ff837d
---

# PO-Briefing: fix-506-autoclear-ohne-herdr-status

- **Spec:** docs/specs/fix-506-autoclear-ohne-herdr-status.md
- **Issue:** #506
- **Erstellt:** 2026-10-31

## Was gebaut wird

Das automatische /clear an Phasengrenzen läuft wieder zuverlässig, unabhängig davon, wie Herdr die Sitzung einstuft.

## Definition of Done

Im echten Herdr mit nachgebautem PO-Regelwerk laufen /clear und danach der Folgebefehl durch; mit dem alten Stand bricht derselbe Lauf ab.

## Wie geprüft wird

Automatische Tests und ein echter Lauf mit Herdr belegen es; echte Bedienung in deiner eigenen Umgebung bleibt ungeprüft.

## Kritische Anmerkungen

- Getippter, nicht abgeschickter Text wird mit /clear vermischt; Eingaben zwischen /clear und Folgebefehl bleiben unbemerkt (bekannte Grenze).
- Bleibt das Signal nach /clear aus, bricht der Ablauf ab und der Folgebefehl muss von Hand getippt werden.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
