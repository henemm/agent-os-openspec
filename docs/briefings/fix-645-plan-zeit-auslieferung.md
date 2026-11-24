---
spec_file: docs/specs/fix-645-plan-zeit-auslieferung.md
spec_sha256: 3c8e15b09b5e9823e2e2fcf5b6e9d464eda4826849723e430bf31f734eb76c60
spec_frozen_sha256: 823e4907b504ec56af54a7befc8350570194e184791d26b4e6f9276c36e89a60
---

# PO-Briefing: fix-645-plan-zeit-auslieferung

- **Spec:** docs/specs/fix-645-plan-zeit-auslieferung.md
- **Issue:** #645
- **Erstellt:** 2026-11-24

## Was gebaut wird

Die Planansicht zeigt während der Auslieferung „Ausliefern seit Uhrzeit“ mit laufender Dauer und „Ende offen“ statt einer falschen Fertig-Uhrzeit.

## Definition of Done

Läuft eine Auslieferung, steht im Plan „Ausliefern seit …“ und „Ende offen“; nach Abschluss erscheinen Ende und Dauer bis zum Abschluss der Auslieferung.

## Wie geprüft wird

Automatische Tests belegen laufende, abgeschlossene, alte und fehlerhafte Fälle sowie Zeitzone und Zeilenumbruch; echte Anzeige im Terminal-Pane wird nicht geprüft.

## Kritische Anmerkungen

- Zusatz zur Anfrage: Auch bei fehlgeschlagener Auslieferung bleibt das Ende offen. Die Dauer ist Wanduhrzeit, keine Arbeitszeit.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
