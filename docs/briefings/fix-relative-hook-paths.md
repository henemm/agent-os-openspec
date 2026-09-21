---
spec_file: docs/specs/hook-paths-project-dir.md
spec_sha256: a7b3f85e19777773e3ba63b55b7e79e15a832df4f6d8b13d08a672f35e6684c0
---

# PO-Briefing: fix-relative-hook-paths

- **Spec:** docs/specs/hook-paths-project-dir.md
- **Issue:** #165
- **Erstellt:** 2026-09-21

## Was gebaut wird

Hook-Startpfade werden fest an den Projektordner gebunden, damit Nachrichten nicht mehr abbrechen.

## Definition of Done

Neu eingerichtete und reparierte Projekte starten Nachrichten und Aktionen zuverlässig, unabhängig davon, wo der Projektordner liegt oder wie er heißt.

## Wie geprüft wird

Automatisierte Tests prüfen die Pfad-Erzeugung und -Reparatur in verschiedenen Fällen; ob dein blockiertes Projekt tatsächlich wieder läuft, prüfen sie nicht.

## Kritische Anmerkungen

- Dein aktuell blockiertes Projekt wird durch diese Änderung nicht automatisch repariert, dafür ist ein separater Schritt nötig.
- Die Spezifikation listet keinen Test pro Prüfpunkt auf; ob jede Regel wirklich geprüft wird, zeigt erst der Test-Code.
- Zusätzlich wird eine bislang nicht erwähnte zweite Einstellungsdatei mitrepariert, sinnvoll, aber über die Anfrage hinausgehend.

## Freigabe-Frage

Soll das Framework so gehärtet werden, auch wenn dein aktuell blockiertes Projekt danach noch einen zusätzlichen Reparatur-Schritt braucht?
