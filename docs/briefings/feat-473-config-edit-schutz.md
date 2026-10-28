---
spec_file: docs/specs/feat-473-config-edit-schutz.md
spec_sha256: 1c27513d0bec51db9c81ee78f6ba54beb115a887af5b6ecbd8010d5a88d672cc
spec_frozen_sha256: 43356d209bdc3dd542898df09bc87889ae928d7d4153394c6ad790467130b47d
---

# PO-Briefing: feat-473-config-edit-schutz

- **Spec:** docs/specs/feat-473-config-edit-schutz.md
- **Issue:** #473
- **Erstellt:** 2026-10-28

## Was gebaut wird

Die Einstellungsdatei der Schutzregeln lässt sich nicht mehr ohne Nutzerfreigabe ändern oder durch eine vorrangige Datei überlagern.

## Definition of Done

Ein Agent kann die Schutz-Einstellungen nur noch mit dem Wort "override" ändern oder neu anlegen; alle Tests laufen grün.

## Wie geprüft wird

Automatische Tests belegen Blockade und Freigabe per Override für Bearbeiten und Anlegen; nicht belegt sind Umgehungen über Skripte.

## Kritische Anmerkungen

- Abweichung: Nicht alle Config-Namen sind gesperrt; wirkungslose nachrangige Dateien und App-Konfiguration bleiben frei, das Ticket verlangte alle.
- Schreiben per Python-Einzeiler oder Skript umgeht den Schutz weiterhin; Lücke nur teilweise geschlossen.
- Zusatz: Schutz gilt auch bei abgeschaltetem Framework; dort braucht jede Config-Änderung künftig "override".

## Freigabe-Frage

Reicht dir diese Teilschließung (ohne Skript-Umgehungen, ohne wirkungslose Dateien), bevor der Auto-Modus genutzt wird?

## Ampel

Ampel: rot
