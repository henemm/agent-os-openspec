# Fast Track: Release 3.37.0

## Problem

Auf main liegen seit 3.36.1 #81 (`/70-deploy` aus der Projekt-Config), #365 (Heredoc in
Befehlsersetzung) und das Sicherheits-Paket #279/#355/#252/#300/#295. Ohne Versions-Bump
erreichen sie keinen Plugin-Nutzer. Minor-Version, weil Copy-Modus-Projekte nach dem Update
spürbar mehr Wächter erhalten (Worktree-Pflicht) und `/70-deploy` neu arbeitet.

## Scope

- `.claude-plugin/plugin.json`, `CLAUDE.md`, `README.md`: Version 3.37.0
- `CHANGELOG.md`: Abschnitt `[3.37.0]`
- `skills/*/SKILL.md`, `.claude/commands/*.md`: neu erzeugt (`sync_skills.py`, `--refresh-aliases`)
- Keine Verhaltensänderung über die bereits gemergten, geprüften Änderungen hinaus

## Definition of Done

Das Release-Gate (`release_check.py --pr-gate`) ist grün, und nach dem Merge entsteht der Tag
`agent-os-openspec--v3.37.0` automatisch.

## Acceptance Criteria

- **AC-1:** Given der Versions-Bump, When `release_check.py --pr-gate --base origin/main` läuft, Then sind Version, README, CLAUDE.md, Tag und Skills grün.
- **AC-2:** Given der Merge nach main, When der Release-Workflow läuft, Then existiert der Tag agent-os-openspec--v3.37.0 mit den Notizen aus dem CHANGELOG-Abschnitt.

## Test Plan

- `python3 scripts/release_check.py --pr-gate --base origin/main` (AC-1)
- Volle Suite in der CI; Tag nach dem Merge per `git ls-remote --tags` prüfen (AC-2)
