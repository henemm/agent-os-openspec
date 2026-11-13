---
spec_file: docs/specs/feat-589-naechster-vorschlag.md
spec_sha256: 15548f8e01c1cfcb7a83d809578d62d8df18f8b36d9ae43d9882e74e9db50f5f
spec_frozen_sha256: d26679499b88fc0311a01eaa53b4db569033911f2f7e592e564d9a64b516c79c
---

# PO-Briefing: feat-589-naechster-vorschlag

- **Spec:** docs/specs/feat-589-naechster-vorschlag.md
- **Issue:** #589
- **Erstellt:** 2026-11-12

## Was gebaut wird

Nach "fertig" nennt der Workflow die passende nächste Aufgabe: gleiches Epic, gleicher Meilenstein, verwandt, sonst wichtigste offene.

## Definition of Done

Die Schlusszeile nennt Aufgabe und Grund; autarke Aufträge starten Epic- und Meilenstein-Nachfolger selbst; ohne GitHub-Zugang bleibt alles wie bisher.

## Wie geprüft wird

Automatische Tests mit simuliertem GitHub belegen jede Anforderung; echtes GitHub und die tatsächliche Vorschlagsqualität werden nicht geprüft.

## Kritische Anmerkungen

- Freie Spur und herdr-Anzeige fehlen (auf #591 verschoben); du wolltest sie, die Aufteilung entschied nur der Tech Lead.
- Autark macht nur bei Epic und Meilenstein selbst weiter; bei verwandt und wichtigster Aufgabe bleibt es beim Vorschlag, anders als deine Entscheidung.

## Freigabe-Frage

Akzeptierst du, dass Spur und herdr-Anzeige später kommen und das automatische Weitermachen nur bei Epic und Meilenstein gilt?

## Ampel

Ampel: rot
