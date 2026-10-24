# Fast Track: Release 3.42.2

## Problem

Auf main liegt seit 3.42.1 der Fix #445: Der Sitzungs-Wächter sperrt Ordner ohne Git nicht mehr aus
(dort scheitert `EnterWorktree`, Ausweg war nur „override“). Ohne Release erreicht der Fix die
Plugin-Nutzer nicht; die lokale Sofortmaßnahme in der Plugin-Kopie wird beim nächsten Update überschrieben.
Patch-Version: reine Fehlerbehebung, keine neue Funktion, keine Config-Änderung. Folgeticket: #459.

## Scope

- `.claude-plugin/plugin.json`, `CLAUDE.md`, `README.md`: Version 3.42.2
- `CHANGELOG.md`: `[Unreleased]` wird zu `[3.42.2]`, neuer leerer `[Unreleased]`-Abschnitt
- `skills/*/SKILL.md`, `.claude/commands/*.md`: neu erzeugt (`sync_skills.py`) bzw. Versionszeile

## Definition of Done

Das Release-Gate (`release_check.py --pr-gate`) ist grün, und nach dem Merge entsteht der Tag `agent-os-openspec--v3.42.2` automatisch.

## Acceptance Criteria

- **AC-1:** Given der Versions-Bump, When `release_check.py --pr-gate --base origin/main` läuft, Then sind Version, README, CLAUDE.md, Tag und Skills grün.
- **AC-2:** Given der Merge nach main, When der Release-Workflow läuft, Then existiert der Tag agent-os-openspec--v3.42.2 mit den Notizen aus dem CHANGELOG-Abschnitt.

## Test Plan

- `python3 scripts/release_check.py --pr-gate --base origin/main` (AC-1)
- Volle Suite in der CI; Tag nach dem Merge per `git ls-remote --tags` prüfen (AC-2)
