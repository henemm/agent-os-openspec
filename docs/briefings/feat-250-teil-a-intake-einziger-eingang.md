---
spec_file: docs/specs/feat-250-teil-a1-intake-einziger-eingang.md
spec_sha256: 6a2260731b32017ef73693d0a191b67539f3107b70c5db54a9e86abe88424c27
---

# PO-Briefing: feat-250-teil-a-intake-einziger-eingang

- **Spec:** docs/specs/feat-250-teil-a1-intake-einziger-eingang.md
- **Issue:** #250
- **Erstellt:** 2026-10-03

## Was gebaut wird

Fehlerberichte laufen künftig über denselben Einstieg wie alle Aufgaben; der separate Bug-Schnellweg ohne Gegenprüfung entfällt.

## Definition of Done

Ein Fehlerbericht führt zu Duplikatsuche, Nachstellen und Ursachenbeleg vor der Bewertung; der alte Bug-Befehl verweist nur noch dorthin.

## Wie geprüft wird

Automatische Texttests belegen, dass die Anweisungen vorhanden sind; ob Claude sie im echten Ablauf befolgt, weist nichts nach.

## Kritische Anmerkungen

- Nur Anweisungstext: nichts erzwingt Nachstellen oder Ursachenbeleg; Prüfmechanismen akzeptieren den alten Bug-Typ bis zum Folgeauftrag weiter.
- Regel „Ursache unklar heißt mindestens mittlere Unsicherheit" hat keinen eigenen Test; nur der Low-Fall ist abgedeckt.
- Elf Dateien betroffen, über der Hausgrenze von fünf; sechs sind Einzeiler oder generiert.

## Freigabe-Frage

Soll der Bug-Schnellweg wie beschrieben entfallen und Bugs denselben Weg samt Gegenprüfung nehmen wie alles andere?
