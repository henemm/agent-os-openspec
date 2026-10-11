---
spec_file: docs/specs/fix-422-state-files-source-check.md
spec_sha256: ea65af0dc36abf1fc0f71fff6d5e6e51a0a0fc700dfbf6d01ff0570f459afed0
---

# PO-Briefing: fix-422-state-files-source-check

- **Spec:** docs/specs/fix-422-state-files-source-check.md
- **Issue:** #422
- **Erstellt:** 2026-10-11

## Was gebaut wird

Freigaben, Sperren und Sitzungslisten werden nur noch gelesen und beschrieben, wenn sie echte eigene Dateien sind, nicht Verweise.

## Definition of Done

Für jede Datei und jede Verweisart beweist ein Test: keine Freigabe entsteht, keine Sperre fällt, Normalfall unverändert, Vollsuite grün.

## Wie geprüft wird

Automatische Tests mit echten Hook-Läufen belegen das Verhalten bei Verweisen; nicht erfasst bleiben gefälschte echte Dateien und die Einstellungsdatei.

## Kritische Anmerkungen

- Umfang 12 Dateien, ca. 500 Zeilen, doppelt über Limit; hohes Risiko, da Kerngates jeden Turn laufen.
- Restlücke: Wer den Verweis löscht und eine gefälschte echte Datei anlegt, wird nicht erkannt.
- Einstellungsdatei und Migrationswerkzeug bewusst ungeprüft, obwohl das Ticket sie nannte; dort kein Test.

## Freigabe-Frage

Gibst du die Absicherung aller Zustandsdateien trotz doppelter Größe und bekannter Restlücke frei?
