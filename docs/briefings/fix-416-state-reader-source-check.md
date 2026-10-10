---
spec_file: docs/specs/fix-416-state-reader-source-check.md
spec_sha256: 804d2a1a47af5690c1c897fd81f127b837af741463b277a6571bdf806bdc837d
---

# PO-Briefing: fix-416-state-reader-source-check

- **Spec:** docs/specs/fix-416-state-reader-source-check.md
- **Issue:** #416
- **Erstellt:** 2026-10-10

## Was gebaut wird

Workflow-Zustand wird nur gelesen, wenn er eine echte eigene Datei ist, nicht ein Verweis.

## Definition of Done

Jeder Zustandsleser verweigert bei harten und weichen Verweisen mit Meldung; normale Dateien unverändert, Testsuite grün.

## Wie geprüft wird

Automatische Tests prüfen jeden Leser und jede Verweisart; Fälschung per Link anlegen, schreiben, löschen bleibt unerkannt.

## Kritische Anmerkungen

- Link anlegen, beschreiben, löschen bleibt unerkannt; Schutz ist nicht lückenlos.
- Ticket nennt Marker-Dateien; Spec lässt sie aus, Folgeticket geplant.
- Mehrere Leser warnen nur, statt zu verweigern; Ticket verlangte Verweigerung durch jeden Leser.

## Freigabe-Frage

Genügt dir ein Schutz, der Link-löschen-Fälschung nicht erkennt und Marker-Dateien vorerst auslässt?
