---
spec_file: docs/specs/fix-665-config-kommentare.md
spec_sha256: 7d215c982a74807682b7e3d3631cca80f86fd09bb1d9a65147b3648103a97a74
spec_frozen_sha256: bcd2da38c6c0df212b6199ef14ce7acd45e6c8ce5f7c897aef9450e4df0ee3d5
---

# PO-Briefing: fix-665-config-kommentare

- **Spec:** docs/specs/fix-665-config-kommentare.md
- **Issue:** #665
- **Erstellt:** 2026-11-25

## Was gebaut wird

Die Erklärtexte in der Konfiguration beschreiben das automatische Leeren des Kontexts und das Haltesignal nicht mehr falsch.

## Definition of Done

Die Konfigurationswerte sind unverändert, die Kommentare nennen das richtige Haltesignal und markieren die tote Einstellung als wirkungslos, alle Tests sind grün.

## Wie geprüft wird

Automatische Tests prüfen unveränderte Werte und die neuen Kommentartexte; ob die Formulierungen für Menschen verständlich sind, prüft kein Test.

## Kritische Anmerkungen

- Keine — Spec deckt die Anfrage ab, jede Anforderung hat einen Test.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
