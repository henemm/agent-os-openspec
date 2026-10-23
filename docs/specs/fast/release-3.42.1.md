# Fast Track: Release 3.42.1

## Problem

Auf main liegen seit 3.42.0: #448 (Beleg-Schreibsperre gegen Umgehungen abgedichtet) und #453
(Restlücken der Beleg-Schreibsperre 1d geschlossen, Fehlalarm beim reinen Lesen behoben).
Patch-Version: beide sind Fehlerbehebungen an der bestehenden Sperre aus #447, ohne neue Funktion
und ohne Config-Änderung. Die Nebenwirkung aus #448 (`mv`/`rsync` in bzw. aus `docs/artifacts/<wf>/`
blockt) steht im CHANGELOG. Restbefunde: #455.

## Scope

- `.claude-plugin/plugin.json`, `CLAUDE.md`, `README.md`: Version 3.42.1
- `CHANGELOG.md`: `[Unreleased]` wird zu `[3.42.1]`, neuer leerer `[Unreleased]`-Abschnitt; #453-Eintrag auf den gemergten Stand gebracht
- `skills/*/SKILL.md`, `.claude/commands/*.md`: neu erzeugt (`sync_skills.py`) bzw. Versionszeile

## Definition of Done

Das Release-Gate (`release_check.py --pr-gate`) ist grün, und nach dem Merge entsteht der Tag `agent-os-openspec--v3.42.1` automatisch.

## Acceptance Criteria

- **AC-1:** Given der Versions-Bump, When `release_check.py --pr-gate --base origin/main` läuft, Then sind Version, README, CLAUDE.md, Tag und Skills grün.
- **AC-2:** Given der Merge nach main, When der Release-Workflow läuft, Then existiert der Tag agent-os-openspec--v3.42.1 mit den Notizen aus dem CHANGELOG-Abschnitt.

## Test Plan

- `python3 scripts/release_check.py --pr-gate --base origin/main` (AC-1)
- Volle Suite in der CI; Tag nach dem Merge per `git ls-remote --tags` prüfen (AC-2)
