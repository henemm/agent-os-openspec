---
spec_file: docs/specs/fix-352-349-gates.md
spec_sha256: 37afba0fe1011aa03083a9993cdbac897d0907acf7711e06a402170e74d58485
---

# PO-Briefing: fix-352-349-gates

- **Spec:** docs/specs/fix-352-349-gates.md
- **Issue:** #352, #349
- **Erstellt:** 2026-10-05

## Was gebaut wird

Zwei Prüfungen blocken künftig nicht mehr fälschlich den Merge-Abschluss und Node-Testprotokolle; echte Verstöße werden weiterhin gestoppt.

## Definition of Done

Ein Merge von origin/main lässt sich mit Commit abschließen, und ein Testprotokoll im spec-Format wird nicht mehr als Fälschung geblockt.

## Wie geprüft wird

Automatische Tests mit Wegwerf-Repos und echtem Node-Lauf belegen alle sieben Kriterien; der Weg über "merge --continue" wird nicht geprüft.

## Kritische Anmerkungen

- Merge-Abschluss per "merge --continue" bleibt ungeprüft; das Gate bleibt inkonsistent, Folge-Issue kommt erst später.
- Der Test für das Node-Format wird ohne installiertes Node übersprungen; dort bleibt der Fix unbewiesen.

## Freigabe-Frage

Gibst du beide Fehlalarm-Korrekturen frei, obwohl "merge --continue" vorerst ungeprüft bleibt?
