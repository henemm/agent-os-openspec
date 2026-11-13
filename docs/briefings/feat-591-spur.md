---
spec_file: docs/specs/feat-591-spur.md
spec_sha256: 41c9364ac78e9d47b135a3ea1d092e7a4ca2b58aaa44b775f632fd14c76ea37c
spec_frozen_sha256: 4eae8474741e48d9e0a9e0b560c15ce7657fab295310fd2598fc6284eced72f9
---

# PO-Briefing: feat-591-spur

- **Spec:** docs/specs/feat-591-spur.md
- **Issue:** #591
- **Erstellt:** 2026-11-13

## Was gebaut wird

Ein Auftrag kann eine Spur tragen; nach "fertig" schlägt das System die nächste Aufgabe derselben Spur vor, herdr zeigt sie an.

## Definition of Done

Nach einer fertigen Aufgabe ohne Epic oder Meilenstein nennt die Schlusszeile die nächste Aufgabe der Spur; autarke Aufträge machen selbst weiter.

## Wie geprüft wird

Automatische Tests ohne Netz belegen Setzen, Vorschlag, Weitermachen und Anzeige; ob GitHub-Labels im echten Betrieb gepflegt sind, prüfen sie nicht.

## Kritische Anmerkungen

- Spur gilt je Projekt: parallele Sitzungen teilen sich eine Spur.
- Labels `spur:<name>` müssen von Hand an den Aufgaben stehen; fehlen sie, greift still die nächste Stufe.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
