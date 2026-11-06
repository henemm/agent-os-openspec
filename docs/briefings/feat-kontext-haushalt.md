---
spec_file: docs/specs/feat-kontext-haushalt.md
spec_sha256: 6aeefe3d0481a96747e97f97a496f16ebbfd40f00120a08cafb8630d39c0a46e
spec_frozen_sha256: 59da7f4d41d032e7406d6f52e1ba1a95046f1daff57850f45b8eb6dd07e5fe6e
---

# PO-Briefing: feat-kontext-haushalt

- **Spec:** docs/specs/feat-kontext-haushalt.md
- **Issue:** keine (Anlass: Pull Request 537)
- **Erstellt:** 2026-11-06

## Was gebaut wird

Claude erinnert ab 100.000 Token Kontext an einen Schnitt; Befehlsfolgen und Pull-Request-Abläufe laufen gebündelt in einem Aufruf.

## Definition of Done

Ab 100.000 Token erscheint je Stufe genau ein Hinweis, Befehlsbündel und Pull-Request-Werkzeug funktionieren, und die gesamte Testsuite sowie der Spec-Check der CI sind grün.

## Wie geprüft wird

Automatische Tests decken alle acht Kriterien ab, das Pull-Request-Werkzeug aber nur im Trockenlauf; echtes Pushen, CI-Warten und Mergen steht nicht im Test Plan.

## Kritische Anmerkungen

- Spec wurde erst nach der Umsetzung geschrieben (Pull Request offen); sie beschreibt den Code, steuerte ihn nicht.
- Wünsche 4 und 5 (gezielt lesen, Overhead klein halten) sind nur Dokumentation, nichts erzwingt sie.
- Der 100k-Hinweis ist nur Auskunft, aus der letzten Antwort geschätzt und nur nach Befehlsaufrufen gemessen.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
