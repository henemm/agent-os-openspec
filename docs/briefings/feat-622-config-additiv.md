---
spec_file: docs/specs/feat-622-config-additiv.md
spec_sha256: 3a599aaaa036ba35556622e81766a067f785e55c148547cf5b852881e243d369
spec_frozen_sha256: d6df9ae532c0009e5f5031264bce02e5ca115304af5b92e7c512621a464d52c5
---

# PO-Briefing: feat-622-config-additiv

- **Spec:** docs/specs/feat-622-config-additiv.md
- **Issue:** #622
- **Erstellt:** 2026-11-21

## Was gebaut wird

Autarke Aufträge dürfen reine Anzeige-Einstellungen der Konfiguration ändern, ohne dass du „override“ tippen musst.

## Definition of Done

Ein autarker Auftrag ändert die Anzeige-Abschnitte ohne override, jede Änderung an Gate-Schaltern verlangt weiterhin override, und beide Planungsbefehle tragen den Hinweis.

## Wie geprüft wird

Automatische Tests prüfen Erlauben und Blockieren je Fall samt Fehlerfällen; ob künftige neue Anzeige-Abschnitte korrekt eingeordnet werden, prüfen sie nicht.

## Kritische Anmerkungen

- Keine — Spec deckt die Anfrage ab, jede Anforderung hat einen Test.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
