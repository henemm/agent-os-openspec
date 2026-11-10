---
spec_file: docs/specs/fix-566-plugin-update-sync.md
spec_sha256: 5a892dcb58b0baadb302a48708bb63f9feca461f22cd75d3bba07b3f611d913c
spec_frozen_sha256: 83d36b0f904d0d4084048efc28ae492f36d00d110decabca6b76d3dfc296bfb7
---

# PO-Briefing: fix-566-plugin-update-sync

- **Spec:** docs/specs/fix-566-plugin-update-sync.md
- **Issue:** #566
- **Erstellt:** 2026-11-10

## Was gebaut wird

Beim Aktualisieren im Plugin-Modus werden keine Hooks und Befehle mehr kopiert; nur veraltete Weiterleitungen und Kurzbefehle werden erneuert.

## Definition of Done

Ein Update im Plugin-Projekt lässt eigene Dateien und echte Kopien unverändert, erneuert nur veraltete Weiterleitungen und Kurzbefehle, und ein zweites Update ändert nichts.

## Wie geprüft wird

Automatische Tests mit echten Dateien belegen Plugin-Modus mit und ohne Pin sowie unveränderten Kopier-Modus; Agenten und Werkzeug-Ordner sind nicht Teil der Prüfung.

## Kritische Anmerkungen

- Vorhandene Alt-Kopien in Plugin-Projekten werden nicht gelöscht und veralten still; das Ticket verlangt nur, sie nicht mehr zu aktualisieren.
- Agenten, Werkzeuge und Modul-Dateien werden im Plugin-Modus weiterhin kopiert; das Ticket nannte nur Hooks und Befehle.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
