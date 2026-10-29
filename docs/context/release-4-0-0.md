# Context: release-4-0-0

## Request Summary
Release 4.0.0: Versions-Bump für die mit PR #474 gemergten Features (#466, #467, #469–#473). Ziel: neue Funktionen als Plugin-Version ausliefern (`release.yml` taggt `agent-os-openspec--v4.0.0` nach Merge).

## Related Files
| File | Relevance |
|------|-----------|
| `.claude-plugin/plugin.json` | Version 3.43.1 → 4.0.0 (Auslöser für `release.yml`) |
| `README.md`, `CLAUDE.md` | Versionszeile (`release_check.py` prüft Gleichstand) |
| `CHANGELOG.md` | `[Unreleased]` → `[4.0.0] - 2026-10-29` + Zusammenfassung |
| `skills/*/SKILL.md` | generierte Versionszeile (`scripts/sync_skills.py`) |
| `scripts/release_check.py` | Release-Vorbedingungen |

## Analysis
- SemVer MINOR: neue, standardmäßig deaktivierte Funktionen, kein Breaking Change
- Keine Verhaltensänderung am Code; nur Versionsangaben und CHANGELOG
- Prüfung: `release_check.py --no-tests` inhaltlich OK; Versions-/Skill-Tests grün
