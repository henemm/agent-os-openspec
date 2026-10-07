# Fast Track: Release 3.39.0

## Problem

Auf main liegt seit 3.38.8 der Fix zu #72: `setup.py --update` erhält lokale Anpassungen über ein
Manifest (`.claude/framework_manifest.json`) und legt neue Framework-Fassungen als `<name>.new` daneben.
Minor-Version, weil sich das sichtbare Update-Verhalten ändert (neue Datei im Projekt, neue Meldungen).

## Scope

- `.claude-plugin/plugin.json`, `CLAUDE.md`, `README.md`: Version 3.39.0
- `CHANGELOG.md`: Abschnitt `[3.39.0]`
- `skills/*/SKILL.md`, `.claude/commands/*.md`: neu erzeugt (`sync_skills.py`, `--refresh-aliases`)

## Definition of Done

Das Release-Gate (`release_check.py --pr-gate`) ist grün, und nach dem Merge entsteht der Tag `agent-os-openspec--v3.39.0` automatisch.

## Acceptance Criteria

- **AC-1:** Given der Versions-Bump, When `release_check.py --pr-gate --base origin/main` läuft, Then sind Version, README, CLAUDE.md, Tag und Skills grün.
- **AC-2:** Given der Merge nach main, When der Release-Workflow läuft, Then existiert der Tag agent-os-openspec--v3.39.0 mit den Notizen aus dem CHANGELOG-Abschnitt.

## Test Plan

- `python3 scripts/release_check.py --pr-gate --base origin/main` (AC-1)
- Volle Suite in der CI; Tag nach dem Merge per `git ls-remote --tags` prüfen (AC-2)
