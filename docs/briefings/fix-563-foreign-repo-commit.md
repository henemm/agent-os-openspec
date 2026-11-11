---
spec_file: docs/specs/fix-563-foreign-repo-commit.md
spec_sha256: fdfdfa240574c86a8ef3eea52fd91c9e2fc996ded51fc6474d7ccde65668839d
spec_frozen_sha256: 3d07b6d562d84776ebc03e1568774e942179d758488c233b41a1c54a8e05c8ed
---

# PO-Briefing: fix-563-foreign-repo-commit

- **Spec:** docs/specs/fix-563-foreign-repo-commit.md
- **Issue:** #563
- **Erstellt:** 2026-11-10

## Was gebaut wird

Ein Commit in einem anderen Projekt wird nicht mehr durch die Abnahme-Sperre des laufenden Auftrags blockiert.

## Definition of Done

Commit in ein fremdes Projekt klappt trotz fehlender Abnahme; Commit im eigenen Projekt und dessen Arbeitskopien bleibt gesperrt.

## Wie geprüft wird

Automatische Tests mit echten Testprojekten prüfen fremd, eigen, gemischt, unsichere Schreibweisen, Stopp-Sperre und Geheimnisschutz; keine manuelle Abnahme.

## Kritische Anmerkungen

- Commits in fremde Projekte über Umwege (Wrapper, Umgebungsvariablen, verschachtelte Shell) bleiben bewusst gesperrt; direkte Schreibweise nötig.
- Commits in Unterprojekten (Submodulen) des eigenen Projekts gelten als fremd und werden nicht geprüft.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
