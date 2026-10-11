---
spec_file: docs/specs/fix-421-compiler-echo.md
spec_sha256: 3d523575608d65f83dbb9bfffc40121df657629c852c35246c8eb11457525bbc
---

# PO-Briefing: fix-421-compiler-echo

- **Spec:** docs/specs/fix-421-compiler-echo.md
- **Issue:** #421
- **Erstellt:** 2026-10-11

## Was gebaut wird

Echte Swift-Testausgaben werden nicht mehr als Platzhalter abgelehnt, nur weil zitierter Testcode das Wort „placeholder“ enthält.

## Definition of Done

Das Artefakt aus dem Ticket wird akzeptiert, erfundene Platzhalter-Artefakte bleiben abgelehnt, alle bisherigen Tests bleiben grün.

## Wie geprüft wird

Automatische Tests belegen Akzeptanz von Echo-Zeilen, plain und farbig, und weiter blockierte Fälschungen; nicht geprüft wird das echte Original-Artefakt, nur ein Nachbau.

## Kritische Anmerkungen

- Abweichung: Das Ticket verlangt Suche nur nach typischen Erfindungsmustern; die Spec nimmt stattdessen nummerierte Compiler-Zeilen aus, Wortliste bleibt unverändert.
- Wer „TODO“ in eine nummerierte Zeile schreibt, umgeht die Wortsuche; Schutz bleibt nur die Fehler-Evidenz.

## Freigabe-Frage

Soll das Gate Compiler-Zeilen mit Zeilennummer ausnehmen, statt wie im Ticket gewünscht die Wortliste einzuengen?
