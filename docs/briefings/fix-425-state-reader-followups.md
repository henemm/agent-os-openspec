---
spec_file: docs/specs/fix-425-state-reader-followups.md
spec_sha256: 6655ab04bc103f9fe406c343ca351762cfa41828529854b883b13c136f37aaa3
---

# PO-Briefing: fix-425-state-reader-followups

- **Spec:** docs/specs/fix-425-state-reader-followups.md
- **Issue:** #425
- **Erstellt:** 2026-10-11

## Was gebaut wird

Der Zustandsleser meldet keine Fehlalarme mehr, lange Dateinamen funktionieren, und ein fehlgeschlagenes Override wird dem Nutzer gemeldet.

## Definition of Done

Parallele Lese- und Schreibzugriffe erzeugen keine Fehlalarme, Dateinamen mit 255 Zeichen funktionieren, bei unsicherem Override erscheint eine Warnung statt Erfolgsmeldung, Vollsuite grün.

## Wie geprüft wird

Je Befund ein vorher roter automatischer Test samt Gegenprobe, dass echte Verweise weiter blockiert werden.

## Kritische Anmerkungen

- Nach gleichzeitigem Ersetzen liefert der Leser den Stand von kurz davor; Ticket erlaubte auch Neuöffnen. Gate kann kurz hinterherhinken.
- Eine gleichartige Verweisprüfung in der QA-Schranke bleibt bewusst unverändert; im Ticket nicht erwähnt.

## Freigabe-Frage

Soll #425 so umgesetzt werden, inklusive des möglichen Lesens vom Stand kurz vor dem Ersetzen?
