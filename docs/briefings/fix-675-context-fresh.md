---
spec_file: docs/specs/fix-675-context-fresh.md
spec_sha256: 0c497f606f52b600e56d5f8ef0c012e5a2ea99a06e01028777a2c4905bad233a
spec_frozen_sha256: c66ea2081420d825ef970ee3b24a3233dd32aa4bca8c633af70610f8840752d2
---

# PO-Briefing: fix-675-context-fresh

- **Spec:** docs/specs/fix-675-context-fresh.md
- **Issue:** #675
- **Erstellt:** 2026-11-25

## Was gebaut wird

Die Kontext-Abfrage nennt gleich nach Sitzungsstart eine Zahl statt „unknown", indem sie den Gesprächsverlauf selbst ausliest.

## Definition of Done

In einer frischen Sitzung zeigt die Abfrage eine Zahl, alle bestehenden Tests laufen weiter grün, Änderungsprotokoll und Version sind erhöht.

## Wie geprüft wird

Automatische Tests belegen jede Anforderung, darunter frische Sitzung, Vorrang eigener Messung und ungültige Sitzungskennung; echte Sitzungen werden nicht getestet.

## Kritische Anmerkungen

- Aus dem Gesprächsverlauf gibt es keinen Grundkontext; die Schwelle fällt dann auf den Standardwert zurück (dokumentierte Einschränkung).

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
