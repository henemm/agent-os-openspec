---
spec_file: docs/specs/fix-489-kette-auto-clear.md
spec_sha256: 35d6373eba4558efefe2029662dad66b39af0e11cc4547200c3b01d490a80ebf
spec_frozen_sha256: 950ccbbc74b0f4cec58ecb6106519a0e3f502d4e06975604f8674af6c0a3302c
---

# PO-Briefing: fix-489-kette-auto-clear

- **Spec:** docs/specs/fix-489-kette-auto-clear.md
- **Issue:** #489
- **Erstellt:** 2026-10-30

## Was gebaut wird

Ist automatisches Leeren aktiv, hält die Arbeit an jeder Phasengrenze an, damit Herdr leert und den nächsten Schritt startet.

## Definition of Done

In Herdr mit aktivem automatischem Leeren wird an jeder Phasengrenze geleert und der nächste Befehl startet, ohne dass der PO eingreift.

## Wie geprüft wird

Automatische Tests prüfen die Auskunft und den Anweisungstext der Befehle; ob Claude der Anweisung folgt, zeigt nur die manuelle Abnahme in Herdr.

## Kritische Anmerkungen

- Nur fünf Übergänge (Kontext bis Implementieren) sind erfasst; Grenzen danach und andere erwähnte Abläufe bleiben ungeprüft.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
