---
spec_file: docs/specs/fix-530-default-branch-fallback.md
spec_sha256: 17a639707ec837b4e2aed5619ed4c52088e60dfee8ce4fe493194d5a71351fba
spec_frozen_sha256: 7b5fb0a18969c755ff2ee896f6c5aaf73ef73d701dcbb42164dda93e72d540e7
---

# PO-Briefing: fix-530-default-branch-fallback

- **Spec:** docs/specs/fix-530-default-branch-fallback.md
- **Issue:** #530
- **Erstellt:** 2026-11-06

## Was gebaut wird

Im Auto-Modus liefert Claude auch aus, wenn der Standard-Branch lokal unbekannt ist; sonst meldet er das in Alltagssprache.

## Definition of Done

Die Anleitung nennt den Ersatzweg und die Meldung ohne Git-Auftrag, der Namenskonflikt nennt lokal und Remote, alle Tests laufen grün.

## Wie geprüft wird

Textprüfungen belegen alle drei Punkte samt Verweis-Kontrolle; ob Claude im echten Lauf danach handelt, prüft kein Test.

## Kritische Anmerkungen

- Keine — Spec deckt die Anfrage ab, jede Anforderung hat einen Test.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
