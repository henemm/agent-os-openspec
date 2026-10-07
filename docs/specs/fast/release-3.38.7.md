# Fast Track: Release 3.38.7

## Problem

Auf main liegt seit 3.38.6 der Fix zu #388 (qa_gate wertet Swift-Testing-Läufe aus). Ohne
Versions-Bump erreicht er keinen Plugin-Nutzer.
Patch-Version: Fehlerbehebung, keine neue Funktion.

## Scope

- `.claude-plugin/plugin.json`, `CLAUDE.md`, `README.md`: Version 3.38.7
- `CHANGELOG.md`: Abschnitt `[3.38.7]`
- `skills/*/SKILL.md`, `.claude/commands/*.md`: neu erzeugt (`sync_skills.py`, `--refresh-aliases`)

## Definition of Done

Das Release-Gate (`release_check.py --pr-gate`) ist grün, und nach dem Merge entsteht der Tag `agent-os-openspec--v3.38.7` automatisch.

## Acceptance Criteria

- **AC-1:** Given der Versions-Bump, When `release_check.py --pr-gate --base origin/main` läuft, Then sind Version, README, CLAUDE.md, Tag und Skills grün.
- **AC-2:** Given der Merge nach main, When der Release-Workflow läuft, Then existiert der Tag agent-os-openspec--v3.38.7 mit den Notizen aus dem CHANGELOG-Abschnitt.

## Test Plan

- `python3 scripts/release_check.py --pr-gate --base origin/main` (AC-1)
- Volle Suite in der CI; Tag nach dem Merge per `git ls-remote --tags` prüfen (AC-2)
