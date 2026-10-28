# PO-Briefing: feat-471-auto-green

- **Spec:** docs/specs/feat-471-auto-green.md
- **Issue:** #471
- **Erstellt:** 2026-10-28

## Was gebaut wird

Im Auto-Modus gibt das System die Implementierung selbst frei, sobald das Testprotokoll bestandene Tests zeigt, ohne dass „go“ getippt wird.

## Definition of Done

Bei bestandenen Tests läuft der Auto-Modus ohne Nachfrage weiter und protokolliert die Freigabe, sonst fragt er den Menschen; manueller Modus unverändert.

## Wie geprüft wird

Automatische Tests belegen Freigabe, Sperrfälle und Ablehnung roter Testprotokolle; ob das Protokoll aus einem echten Lauf stammt, belegen sie nicht.

## Kritische Anmerkungen

- Ein Agent könnte grünen Text als Testprotokoll ablegen; die Echtheit prüft nur der spätere Prüflauf.
- Auffälligkeiten stoppen die Freigabe nicht, wie entschieden; sie gehen nur an den Prüfer und die Abschlussmeldung.

## Freigabe-Frage

Soll die Freigabe im Auto-Modus automatisch erfolgen, wenn das Testprotokoll bestandene Tests zeigt?

## Ampel

Ampel: gruen
