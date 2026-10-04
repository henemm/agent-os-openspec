---
spec_file: docs/specs/fix-350-remove-aliases-robust.md
spec_sha256: 67d7b879bf7dfd8ac2abbf9f77e689b5627fd33ceb5adee46c60d17bfe39214b
---

# PO-Briefing: fix-350-remove-aliases-robust

- **Spec:** docs/specs/fix-350-remove-aliases-robust.md
- **Issue:** #350
- **Erstellt:** 2026-10-04

## Was gebaut wird

Entfernen und Auffrischen der Kurzbefehle läuft auch dann durch, wenn unlesbare oder ungewöhnliche Dateien im Ordner liegen.

## Definition of Done

Mit einer kaputten Datei im Ordner entfernt der Befehl die echten Kurzbefehle, lässt die kaputte stehen, listet nur echte Dateien und warnt bei --global.

## Wie geprüft wird

Automatische Tests prüfen jeden Teil mit echten Testdateien und dem echten Befehl; die Warnung beim Sitzungsstart wird nicht direkt getestet.

## Kritische Anmerkungen

- Zusatz: Spec repariert auch Auffrischen und Sitzungs-Warnung, nicht im Ticket verlangt; die Sitzungs-Warnung hat keinen eigenen Test.
- Ein unlesbarer, echter Kurzbefehl wird nie entfernt, sondern bleibt stehen; Nutzer löscht ihn von Hand.

## Freigabe-Frage

Gibst du die robuste Entfernung samt erweitertem Umfang (Auffrischen, Sitzungs-Warnung) frei?
