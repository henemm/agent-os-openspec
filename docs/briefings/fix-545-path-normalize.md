---
spec_file: docs/specs/fix-545-path-normalize.md
spec_sha256: facee5e020b83f76c49393e02fc0b01a51b4ef96284e3bb6573757d6dc06b5d5
spec_frozen_sha256: 26c96b82a882c97ae7f600410f53e89f0ae98d4803eb7338904e726b2946bb03
---

# PO-Briefing: fix-545-path-normalize

- **Spec:** docs/specs/fix-545-path-normalize.md
- **Issue:** #545
- **Erstellt:** 2026-11-09

## Was gebaut wird

Geschützte Dateien lassen sich nicht mehr durch ungewöhnliche Pfadschreibweisen wie doppelte Schrägstriche umgehen.

## Definition of Done

Alle ungewöhnlichen Schreibweisen für Einstellungen, Workflow-Stand und Hooks sind blockiert, saubere Pfade funktionieren unverändert, alle automatischen Tests laufen grün.

## Wie geprüft wird

Automatische Tests schreiben über die Schreibweisen und erwarten die Sperre; nicht abgedeckt bleibt die Umgehung über verschachtelte Shell-Aufrufe.

## Kritische Anmerkungen

- Abweichung: Eine reine Plugin-Änderung über unsaubere Schreibweise wird blockiert, das Ticket verlangte Gleichbehandlung mit der erlaubten Ausnahme.
- Zusatz: Die Spec sichert auch Workflow-Stand, Infrastruktur und Shell-Sperre ab; das Ticket verlangte dort nur Prüfung.

## Freigabe-Frage

Soll eine reine Plugin-Änderung über unsaubere Pfadschreibweise blockiert werden (Spec) oder wie die saubere Schreibweise erlaubt sein (Ticket)?

## Ampel

Ampel: rot
