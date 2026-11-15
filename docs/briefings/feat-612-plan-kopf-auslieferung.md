---
spec_file: docs/specs/feat-612-plan-kopf-auslieferung.md
spec_sha256: 40b4e33cf4152b7f68442b267a94ba58eb7c4828649392872d377fe8be338861
spec_frozen_sha256: 62efaadce1dfc2455a021c8915844c3a68322adf0c85ba0143afd052ad7890dd
---

# PO-Briefing: feat-612-plan-kopf-auslieferung

- **Spec:** docs/specs/feat-612-plan-kopf-auslieferung.md
- **Issue:** #612
- **Erstellt:** 2026-11-15

## Was gebaut wird

Plan-Bereich zeigt oben Problem und Ziel des Issues und meldet „fertig“ erst nach abgeschlossener Auslieferung.

## Definition of Done

Oben stehen voller Titel, Problem und Ziel; während Prüfungen laufen zeigt der Plan „Ausliefern läuft“, erst nach Abschluss „Erledigt“; Version 4.13.0 erscheint.

## Wie geprüft wird

Automatische Tests decken alle 15 Kriterien ab; wie lesbar die Zusammenfassung bei echten Issues wirkt, belegen sie nicht.

## Kritische Anmerkungen

- Zusammenfassung ist eine Textheuristik; Issues ohne Überschriften liefern nur ein Problem, kein Ziel.
- Bei manuellem Abschluss ohne Meldung bleibt der Plan auf „läuft“ statt „fertig“ – sichtbar, aber lästig.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
