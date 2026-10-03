---
spec_file: docs/specs/feat-250-teil-b-aufwandsbremse.md
spec_sha256: 9a6a8097e25510508af448d0af0387236822d5abefd8222bce91f7371c9d2b16
---

# PO-Briefing: feat-250-teil-b-aufwandsbremse

- **Spec:** docs/specs/feat-250-teil-b-aufwandsbremse.md
- **Issue:** #250
- **Erstellt:** 2026-10-03

## Was gebaut wird

Überschreitet eine Aufgabe ihr Aufwandsbudget, fragt Claude den PO, statt still weiterzuarbeiten; Prüfungen bleiben unangetastet.

## Definition of Done

Bei Überschreitung erscheint eine Rückfrage an den PO samt Protokolleintrag, kein Schritt wird verweigert, und die Änderungsgröße steht nach Abschluss im Archiv.

## Wie geprüft wird

Automatische Tests belegen Meldung, Protokoll, Schnellweg-Frist und Größenmessung; nicht belegt ist, ob Claude die Rückfrage befolgt.

## Kritische Anmerkungen

- Rückfrage ist nur eine Anweisung an Claude, keine Sperre; ob sie befolgt wird, zeigt sich erst in späteren Auswertungen.
- Zusatz ohne Entscheidung: Größenmessung beim Abschluss; zudem wird die Bremse im Schnellweg von 15 auf 30 Minuten gelockert.
- Grenzwerte (1–2 Fix-Loops, Wiedereintritte) sind ungeprüfte Startwerte; zu eng gesetzt, fragt Claude zu oft.

## Freigabe-Frage

Soll bei Überschreitung gefragt statt gesperrt werden, mit Schnellweg-Frist 30 Minuten und Größenmessung?
