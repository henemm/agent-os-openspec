---
spec_file: docs/specs/feat-471-auto-green.md
spec_sha256: 8bd6dd3792c1b8ab0f907c18414089c726f703ea74a413006c1e9cd41a5f0076
spec_frozen_sha256: d6eceaba92ff5c64fe66b25f166631a858fae99625d1674129ff9ebb2c7ec800
---

# PO-Briefing: feat-471-auto-green

- **Spec:** docs/specs/feat-471-auto-green.md
- **Issue:** #471
- **Erstellt:** 2026-10-29

## Was gebaut wird

Im Auto-Modus gibt das System die Implementierung selbst frei, wenn das Testprotokoll bestandene Tests zeigt, ohne dass „go“ getippt wird.

## Definition of Done

Bei bestandenen Tests läuft der Auto-Modus ohne Nachfrage weiter und protokolliert die Freigabe, sonst entscheidet der Mensch; manueller Modus bleibt unverändert.

## Wie geprüft wird

Automatische Tests belegen Freigabe, Sperrfälle und Ablehnung roter Protokolle; dass das Protokoll aus einem echten Lauf stammt, belegen sie nicht.

## Kritische Anmerkungen

- Ein Agent könnte grünen Text als Testprotokoll ablegen; die Echtheit prüft nur der spätere Prüflauf.
- Auffälligkeiten stoppen die Freigabe nicht, wie entschieden; sie gehen nur an den Prüfer und die Abschlussmeldung.

## Freigabe-Frage

Soll die Freigabe im Auto-Modus automatisch erfolgen, wenn das Testprotokoll bestandene Tests zeigt?

## Ampel

Ampel: gruen
