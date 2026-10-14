# Fast Track: Release 3.41.0

## Problem

Auf main liegen seit 3.40.0: #439 (Spec-Freeze nur über den freigegebenen Teil; **Breaking:** „override“
öffnet den Spec-Freeze nicht mehr), #424 (Ausgang „nichts bauen“), #405 (Rücksprung setzt Freigaben
zurück), #417 (Worktree-Sitzung schreibt per Bash nicht in den Haupt-Ordner), #416/#422/#425
(Zustandsdateien prüfen an der Quelle), #418/#410 (bash_gate-Präzisierungen), #411 (Pfad-Randfälle der
Immer-erlaubt-Liste), #421 (Compiler-Echo im RED-Artefakt).
Minor-Version: neue Funktionen (#439, #424) und ein bewusst verschärftes Verhalten mit Migrationspfad
(Legacy-Briefings bleiben gültig, bis `set-briefing` sie migriert).

## Scope

- `.claude-plugin/plugin.json`, `CLAUDE.md`, `README.md`: Version 3.41.0
- `CHANGELOG.md`: `[Unreleased]` wird zu `[3.41.0]`, neuer leerer `[Unreleased]`-Abschnitt
- `skills/*/SKILL.md`, `.claude/commands/*.md`: neu erzeugt (`sync_skills.py`, Versionszeile)

## Definition of Done

Das Release-Gate (`release_check.py --pr-gate`) ist grün, und nach dem Merge entsteht der Tag `agent-os-openspec--v3.41.0` automatisch.

## Acceptance Criteria

- **AC-1:** Given der Versions-Bump, When `release_check.py --pr-gate --base origin/main` läuft, Then sind Version, README, CLAUDE.md, Tag und Skills grün.
- **AC-2:** Given der Merge nach main, When der Release-Workflow läuft, Then existiert der Tag agent-os-openspec--v3.41.0 mit den Notizen aus dem CHANGELOG-Abschnitt.

## Test Plan

- `python3 scripts/release_check.py --pr-gate --base origin/main` (AC-1)
- Volle Suite in der CI; Tag nach dem Merge per `git ls-remote --tags` prüfen (AC-2)
