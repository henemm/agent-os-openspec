---
entity_id: release-3-44-0
type: module
created: 2026-10-29
updated: 2026-10-29
status: draft
version: "1.0"
tags: [release, version-bump]
---

# Release 3.44.0

## Approval

- [ ] Approved

## Purpose

Das Framework wird von 3.43.1 auf 3.44.0 gehoben, damit die mit PR #474 gemergten Funktionen (#466, #467, #469–#473) als Plugin-Version ausgeliefert werden. `release.yml` taggt nach dem Merge `agent-os-openspec--v3.44.0`. Es ändert sich kein Code-Verhalten, nur Versionsangaben und der CHANGELOG-Abschnitt.

## Source

- **File:** `.claude-plugin/plugin.json`
- **Identifier:** Feld `version` (führende Versionsquelle; README, CLAUDE.md, CHANGELOG und generierte Skills folgen ihr)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `scripts/release_check.py` | script | Prüft Gleichstand der Versionen (plugin.json, CHANGELOG, README, CLAUDE.md) und Skill-Sync |
| `scripts/sync_skills.py` | script | Erzeugt `skills/*/SKILL.md` mit der Versionszeile neu |

## Scope

- **Affected Files:** `.claude-plugin/plugin.json`, `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `skills/*/SKILL.md` (generiert)
- **Estimated Changes:** ~30 LoC (Versionszeilen und eine CHANGELOG-Überschrift; Skills nur per `sync_skills.py`)

## Implementation Details

```
1. .claude-plugin/plugin.json: version "3.43.1" -> "3.44.0"
2. README.md: Versionszeile -> 3.44.0
3. CLAUDE.md: Zeile "**Version**: 3.43.1" -> "**Version**: 3.44.0"
4. CHANGELOG.md: Abschnitt [Unreleased] wird zu "## [3.44.0] - 2026-10-29",
   mit kurzer Zusammenfassung; die Einträge #466, #467, #469, #470, #471,
   #472, #473 bleiben darin unverändert erhalten; darüber ein leerer [Unreleased]
5. python3 scripts/sync_skills.py: generierte Versionszeile in skills/*/SKILL.md
```

SemVer MINOR (3.43.1 auf 3.44.0): Neue Funktionen (Herdr-Sidebar, Auto-/clear, Autonomie-Modus mit Spec-Ampel, Auto-GREEN, Workflow-Kette, Config-Edit-Schutz) sind abwärtskompatibel und standardmäßig deaktiviert (`autonomy.mode: manual`, `herdr.auto_clear.enabled: false`). Es gibt keinen Breaking Change und keine Migration, daher weder PATCH (zu klein für neue Funktionen) noch MAJOR.

## Expected Behavior

- **Input:** Repository-Stand 3.43.1 mit gefülltem `[Unreleased]`-Block
- **Output:** Alle Versionsangaben stehen auf 3.44.0, CHANGELOG hat den Abschnitt 3.44.0, Skills sind synchron
- **Side effects:** `release.yml` taggt nach dem Merge `agent-os-openspec--v3.44.0`

## Known Limitations

- Die Versionsprüfung deckt plugin.json, CHANGELOG, README und CLAUDE.md ab. Die Skill-Versionszeile deckt `test_skills_sync.py` ab.
- Kein bestehender Test prüft die Ticket-Nummern im CHANGELOG-Abschnitt einzeln; AC-4 belegt über den Abschnitts-Test die Abschnittsgrenzen, die Nummern prüft der PO im Review.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] `python3 scripts/release_check.py --no-tests` meldet für Version, README, CLAUDE.md und Skills Gleichstand mit 3.44.0
- [ ] Der CHANGELOG-Abschnitt 3.44.0 nennt #466, #467 und #469 bis #473
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given `.claude-plugin/plugin.json` hat Version 3.44.0 / When die Versionen von README und CLAUDE.md gegen plugin.json geprüft werden / Then stimmen beide mit 3.44.0 überein
  - Test: tests/test_readme_version_195.py::TestRepositoryState::test_readme_matches_plugin_manifest und tests/test_readme_version_195.py::TestClaudeMdVersion279::test_repo_claude_md_matches_plugin_json
- **AC-2:** Given CHANGELOG.md hat den obersten Versionsabschnitt `[3.44.0]` / When `latest_changelog_version` und `check_version_match` gegen plugin.json laufen / Then ist die CHANGELOG-Version identisch mit 3.44.0 und der leere `[Unreleased]`-Block wird übersprungen
  - Test: tests/test_release_check_93.py::TestVersionMatch::test_match_passes
- **AC-3:** Given die Versionszeile ist gehoben / When `scripts/sync_skills.py --check` läuft / Then sind `skills/*/SKILL.md` synchron zu `core/commands` und tragen die Version aus plugin.json
  - Test: tests/test_skills_sync.py::test_repo_skills_are_in_sync_with_commands und tests/test_skills_sync.py::test_marker_uses_real_version_not_placeholder
- **AC-4:** Given der Abschnitt `[3.44.0]` in CHANGELOG.md / When `changelog_section("3.44.0")` ausgelesen wird / Then enthält er die Einträge #466, #467, #469, #470, #471, #472 und #473 und nur diesen Abschnitt
  - Test: tests/test_release_check_93.py::TestChangelogSection::test_extracts_only_the_requested_section
- **AC-5:** Given Version in plugin.json auf 3.44.0 gehoben und CHANGELOG, README, CLAUDE.md konsistent / When das PR-Gate `run_pr_gate` mit Bump läuft / Then besteht es
  - Test: tests/test_release_check_93.py::TestPrGate::test_bump_with_valid_release_state_passes

> Die Test-Zuordnung wird bei der Spec-Erstellung eingetragen. Die genannten Tests existieren bereits und prüfen den Repository-Stand; sie schlagen vor dem Bump fehl bzw. belegen ihn danach.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_readme_version_195.py` (AC-1)
- `pytest tests/test_release_check_93.py` (AC-2, AC-4, AC-5)
- `pytest tests/test_skills_sync.py` (AC-3)
- `python3 scripts/release_check.py --no-tests` als Gesamtprüfung

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Reiner Versions-Bump ohne Verhaltensänderung und ohne neue Architekturentscheidung; die Architekturentscheidungen zu den enthaltenen Funktionen (#466–#473) sind in ihren eigenen Specs und ADRs festgehalten. SemVer MINOR folgt aus neuen, abwärtskompatiblen und standardmäßig deaktivierten Funktionen.

## Changelog

- 2026-10-29: Initial spec created
