---
spec_file: docs/specs/feat-633-release-ohne-doppeltest.md
spec_sha256: f5bbdbe4f8c36686c505ae12fe08175a57f01a5aa014ade644120d461d92ff12
spec_frozen_sha256: 40cf57211fee241f5daf57e880788ca63cf87e1bcea336660181397bf258e52c
---

# PO-Briefing: feat-633-release-ohne-doppeltest

- **Spec:** docs/specs/feat-633-release-ohne-doppeltest.md
- **Issue:** #633
- **Erstellt:** 2026-11-21

## Was gebaut wird

Eine Veröffentlichung wiederholt die elfminütigen Tests nicht mehr, wenn derselbe Stand vorher schon grün getestet wurde.

## Definition of Done

Ein Release mit unverändert getestetem Stand erscheint nach ein bis zwei Minuten; in jedem anderen Fall laufen die vollen Tests wie bisher.

## Wie geprüft wird

Automatische Tests belegen Entscheidung, echten Stand-Vergleich, Fehlerfall und Ablauf; ob die Zeitersparnis live eintritt, zeigt erst das nächste Release.

## Kritische Anmerkungen

- Bei Direkt-Veröffentlichung ohne PR oder abweichendem Stand laufen die vollen Tests weiter (gewollt, sicher, nur langsamer).
- Wird der Testlauf in der CI umbenannt, läuft unbemerkt immer die volle Suite.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
