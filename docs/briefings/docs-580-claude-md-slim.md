---
spec_file: docs/specs/docs-580-claude-md-slim.md
spec_sha256: 5870a9d285797ba9425a28db22f1420c0feef5cb68f4a4170737a2e31094e983
spec_frozen_sha256: 91b21cc7a9800d8d43c4a901641047dedbff431175887ae84f37fab877e3c451
---

# PO-Briefing: docs-580-claude-md-slim

- **Spec:** docs/specs/docs-580-claude-md-slim.md
- **Issue:** #580
- **Erstellt:** 2026-11-25

## Was gebaut wird

Die Projektanleitung wird auf die täglich nötigen Regeln gekürzt; Nachschlagewissen wandert unverändert in eine eigene Architektur-Datei.

## Definition of Done

Die Anleitung ist höchstens 12 KB groß, alle verschobenen Abschnitte stehen in der Architektur-Datei, und die Messung vorher/nachher steht im Epic.

## Wie geprüft wird

Automatische Tests prüfen Größe, Verweis, verschobene Abschnitte und behaltene Kernregeln; ob die Sitzung tatsächlich weniger Token verbraucht, messen sie nicht.

## Kritische Anmerkungen

- Erwarteter Effekt: Spec nennt rund 7 000 von 100 000 Token, das Ticket schätzte 4–5 Prozent; nur im Framework-Repo wirksam.
- Größenwächter liegt als Test, nicht im Release-Check; Zusatzaufträge (Messung im Epic, Ticket #579) sind nur Abnahmepunkte ohne Test.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
