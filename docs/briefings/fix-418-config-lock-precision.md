---
spec_file: docs/specs/fix-418-config-lock-precision.md
spec_sha256: cf643a6548691e53a2af8285f231ade0c84dcb0e7e1f9b5b811c9e659aa03df8
---

# PO-Briefing: fix-418-config-lock-precision

- **Spec:** docs/specs/fix-418-config-lock-precision.md
- **Issue:** #418
- **Erstellt:** 2026-10-10

## Was gebaut wird

Die Schutzsperre für die Gate-Konfiguration blockt nur noch echtes Überschreiben, nicht mehr Lesen, und erkennt mehr Schreibvarianten.

## Definition of Done

Lesende Befehle laufen durch, versehentliche Schreibformen und Verzeichniswechsel im Befehl werden blockiert, "override" gibt weiter frei, bestehende Tests bleiben grün.

## Wie geprüft wird

Automatische Tests starten das echte Gate mit je einem Befehl und prüfen Blockieren bzw. Durchlassen; vorsätzliche Umgehungen werden nicht geprüft.

## Kritische Anmerkungen

- Ein Befehl nach Verzeichniswechsel auf gleichnamige Datei im Unterordner wird künftig frei, vorher blockiert; nicht im Ticket.
- Ticket nennt ex, patch und git apply; diese bleiben bewusst ungeblockt (dokumentierte Lücke).

## Freigabe-Frage

Geben Sie die Änderung frei, obwohl ex, patch und git apply ungeblockt bleiben und das Spiegelbild frei wird?
