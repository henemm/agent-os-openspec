---
spec_file: docs/specs/feat-562-cloud-cache-finder.md
spec_sha256: 3f8b4d58409df282cbec7296c36845fe47cab6dd0ca3336237d8e7a1e293631e
spec_frozen_sha256: b54209e345ff592a5d11bd806c38c03b392ce8861fe52d5a9c3f79fcba631ed0
---

# PO-Briefing: feat-562-cloud-cache-finder

- **Spec:** docs/specs/feat-562-cloud-cache-finder.md
- **Issue:** #562
- **Erstellt:** 2026-11-09

## Was gebaut wird

Projekteigene Hooks und Kurzbefehle funktionieren in Cloud-Sitzungen, und lokal erscheint ein Hinweis, wenn der Cloud-Stand veraltet ist.

## Definition of Done

In frischer Cloud-Sitzung liefert /10-context den Befehlstext und projekteigene Hooks laufen; lokal bleibt alles wie bisher.

## Wie geprüft wird

Automatische Tests mit echten Dateien; die echte Cloud-Sitzung wird nicht automatisch getestet.

## Kritische Anmerkungen

- Abweichung vom Ticket: Der Shim nutzt statt Plugin-Ordner und Zeiger den geprüften Pin-Cache und lädt ihn selbst nach.
- Alte Projekte bleiben kaputt, bis sie einmal aktualisiert und committet werden; die Spec rollt das zusätzlich per Setup aus.

## Freigabe-Frage

Darf der Shim vom Ticket abweichen und den geprüften Pin-Cache statt Plugin-Ordner und Zeiger nutzen?

## Ampel

Ampel: rot
