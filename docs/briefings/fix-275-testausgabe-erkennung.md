---
spec_file: docs/specs/fix-275-testausgabe-erkennung.md
spec_sha256: e121fb8db1ecd08bea4db7baff48ce1fcd8c469906af0289ba7cbd71e1301721
---

# PO-Briefing: fix-275-testausgabe-erkennung

- **Spec:** docs/specs/fix-275-testausgabe-erkennung.md
- **Issue:** #275
- **Erstellt:** 2026-10-01

## Was gebaut wird

Testergebnisse werden zuverlässig gelesen, und ein Lauf ohne bestandene, aber mit übersprungenen Tests gilt nicht mehr als Erfolg.

## Definition of Done

Alle 15 Prüfpunkte laufen automatisch grün, die drei Fehlerfälle waren vorher nachweislich rot, grüne Läufe bleiben abgewiesen.

## Wie geprüft wird

Automatische Tests mit echten Testausgaben beweisen Erkennung und Gegenprobe; nicht bewiesen wird das Verhalten in Fremdprojekten.

## Kritische Anmerkungen

- Projekte, deren Tests nur übersprungen werden, gelten künftig als nicht bestanden — gewollte Folge Ihrer Entscheidung.
- „Nichts gelaufen" wird nur bei xcodebuild klar gemeldet; pytest und Swift Testing bleiben unerkannt, aber nie grün.
- Echte Testausgaben für übersprungene Tests müssen erst erzeugt werden; gelingt das nicht, fehlen die Belege.

## Freigabe-Frage

Geben Sie die Änderung frei, inklusive der Folge, dass reine Übersprungen-Läufe künftig als nicht bestanden gelten?
