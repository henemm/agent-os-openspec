---
spec_file: docs/specs/hook-paths-project-dir.md
spec_sha256: 560b46233b149f994ec2b76957220277098558b283d2d880fdc18fb068d2b251
---

# PO-Briefing: fix-relative-hook-paths

- **Spec:** docs/specs/hook-paths-project-dir.md
- **Issue:** #165
- **Erstellt:** 2026-09-21

## Was gebaut wird

Neue und migrierte Projekte erhalten Hook-Befehle, die unabhängig vom Arbeitsordner zuverlässig starten.

## Definition of Done

Kein neu erzeugter oder migrierter Hook-Befehl bricht ab, wenn die Sitzung in einem Unterordner startet.

## Wie geprüft wird

Automatisierte Tests decken zwölf benannte Sonderfälle ab; nicht geprüft: Verhalten bei echter Shell-Ausführung mit Kommentaren oder Windows-Pfaden.

## Kritische Anmerkungen

- Umfang wuchs über vier Gegenprüfungs-Runden von ~30 auf ~300 Zeilen; PO hob die Grenze auf 320 an, um fertigzustellen.
- Der gemeldete Fehler war schon vor dieser Härtung behoben; sie repariert nur künftige Projekte, nicht die drei bestehenden.
- Die Spec räumt ein: wo ein Pfad in einer Befehlszeile endet, ist ohne echte Shell-Grammatik nicht immer entscheidbar.

## Freigabe-Frage

Reicht dieser Schutz für künftige Projekte, obwohl seltene Pfadformen mit Leerzeichen und Sonderzeichen weiterhin ungelöst bleiben?
