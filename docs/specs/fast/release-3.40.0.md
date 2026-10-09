# Fast Track: Release 3.40.0

## Problem

Auf main liegen seit 3.39.0: #345 (`qa_gate.py --run` führt den konfigurierten Testbefehl selbst aus),
#409 (TDD- und Review-Gate greifen in Worktree-Sitzungen erstmals tatsächlich), #407 (bash_gate erkennt
Verweise auf Zustandspfade), #399/#400 (Kurzbefehl-Wartung), #235 (Fußzeilen-Regel), #72 (Doku).
Minor-Version, weil #345 eine neue Option bringt und #409 bisher tote Prüfungen in allen Projekten scharf schaltet.

## Scope

- `.claude-plugin/plugin.json`, `CLAUDE.md`, `README.md`: Version 3.40.0
- `CHANGELOG.md`: Abschnitt `[3.40.0]`
- `skills/*/SKILL.md`, `.claude/commands/*.md`: neu erzeugt (`sync_skills.py`, Versionszeile)

## Definition of Done

Das Release-Gate (`release_check.py --pr-gate`) ist grün, und nach dem Merge entsteht der Tag `agent-os-openspec--v3.40.0` automatisch.

## Acceptance Criteria

- **AC-1:** Given der Versions-Bump, When `release_check.py --pr-gate --base origin/main` läuft, Then sind Version, README, CLAUDE.md, Tag und Skills grün.
- **AC-2:** Given der Merge nach main, When der Release-Workflow läuft, Then existiert der Tag agent-os-openspec--v3.40.0 mit den Notizen aus dem CHANGELOG-Abschnitt.

## Test Plan

- `python3 scripts/release_check.py --pr-gate --base origin/main` (AC-1)
- Volle Suite in der CI; Tag nach dem Merge per `git ls-remote --tags` prüfen (AC-2)
