---
spec_file: docs/specs/fix-508-tap-yaml-zitat.md
spec_sha256: 7017b13c819d652d2ce8018e42bbbd89d5346edc093560e9f49a4fa3333fa568
spec_frozen_sha256: 92d0fea7c96fda55ffaf2d10f3f15acd8181890f88e51687061c2b402b5c4e97
---

# PO-Briefing: fix-508-tap-yaml-zitat

- **Spec:** docs/specs/fix-508-tap-yaml-zitat.md
- **Issue:** #508
- **Erstellt:** 2026-11-04

## Was gebaut wird

Echte Testausgabe von Node mit dem Wort placeholder in zitiertem HTML wird nicht mehr fälschlich als Platzhalter-Text abgelehnt.

## Definition of Done

Die ursprünglich blockierte Testausgabe wird als gültiger Fehlschlag-Nachweis akzeptiert, echte Platzhalter außerhalb des Zitatblocks werden weiterhin abgelehnt.

## Wie geprüft wird

Automatische Tests mit der echten Ausgabe, Grenzfällen und unveränderten Altfällen; nicht geprüft wird der alternative Spec-Reporter-Modus.

## Kritische Anmerkungen

- Ausgabe im Spec-Reporter-Modus von Node bleibt blockiert (dokumentierte Einschränkung, Folge-Issue); Betroffene müssen dort weiter nachmessen.
- Das Gate prüft künftig weniger Zeilen: Platzhalter in formgerechtem Zitatblock fallen durch, der Fehler-Nachweis bleibt Pflicht.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
