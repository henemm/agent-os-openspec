# Fast Track: Release 3.42.0

## Problem

Auf main liegen seit 3.41.0: #447 (Evidence-Gate vor Phase 8, opt-in, plus globale Schreibsperre für
`docs/artifacts/<wf>/simulator-run.txt` und `docs/artifacts/<wf>/simulator-run/`) und #440
(Fortsetzungszeilen unter `- Test:` bleiben im Spec-Freeze eingefroren).
Minor-Version: #447 ist eine neue Funktion. Ohne `evidence_checks` ändert sich am Abschluss nichts.
Die Schreibsperre ist eine bewusste Nebenwirkung und steht im CHANGELOG.

## Scope

- `.claude-plugin/plugin.json`, `CLAUDE.md`, `README.md`: Version 3.42.0
- `CHANGELOG.md`: `[Unreleased]` wird zu `[3.42.0]`, neuer leerer `[Unreleased]`-Abschnitt
- `skills/*/SKILL.md`, `.claude/commands/*.md`: neu erzeugt (`sync_skills.py`, Versionszeile)

## Definition of Done

Das Release-Gate (`release_check.py --pr-gate`) ist grün, und nach dem Merge entsteht der Tag `agent-os-openspec--v3.42.0` automatisch.

## Acceptance Criteria

- **AC-1:** Given der Versions-Bump, When `release_check.py --pr-gate --base origin/main` läuft, Then sind Version, README, CLAUDE.md, Tag und Skills grün.
- **AC-2:** Given der Merge nach main, When der Release-Workflow läuft, Then existiert der Tag agent-os-openspec--v3.42.0 mit den Notizen aus dem CHANGELOG-Abschnitt.

## Test Plan

- `python3 scripts/release_check.py --pr-gate --base origin/main` (AC-1)
- Volle Suite in der CI; Tag nach dem Merge per `git ls-remote --tags` prüfen (AC-2)
