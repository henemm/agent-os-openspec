---
spec_file: docs/specs/docs/docs-679-marker-slim.md
spec_sha256: ecc557daa42d1f96fc9acc41cff489f4a868b11dfcadc739134a64e5401e9378
spec_frozen_sha256: ff222c57469cff3b39a934a748ef67fe9f7620167e64763a86b8742591867c6f
---

# PO-Briefing: docs-679-marker-slim

- **Spec:** docs/specs/docs/docs-679-marker-slim.md
- **Issue:** #679
- **Erstellt:** 2026-11-26

## Was gebaut wird

Die wiederkehrenden Pflicht-Texte an jedem Befehl und in jeder Nachricht werden kürzer, ohne dass sich Regeln ändern.

## Definition of Done

Fußzeilen-Text höchstens 1,2 KB, Zug-Hinweis höchstens 900 Bytes, Vorher-nachher-Messung an Ticket 649 gepostet, alle Tests grün, Version 4.26.3 veröffentlicht.

## Wie geprüft wird

Tests belegen die Größengrenzen, die erhaltenen Pflicht-Stichworte und die ausgelagerte Begründung; die Token-Messung in frischen Sitzungen erfolgt nur manuell.

## Kritische Anmerkungen

- Die Token-Messung (AC-8) hat keinen automatischen Test; nur der Byte-Anteil ist testbar.
- Grundlast der ersten Anfrage sinkt kaum; Ersparnis zeigt sich erst je Befehlsaufruf und Zug.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
