# Context: feat-short-command-aliases

## Request Summary
Vor der Plugin-Migration (v3.2) hießen Slash-Commands kurz (`/50-implement`). Seitdem
Skills als Plugin ausgeliefert werden, zeigt Claude Code sie mit Namespace-Präfix
(`/agent-os-openspec:50-implement`). Der User möchte die kurzen Namen zurück, ohne
dass sie erneut von der Migrations-Cleanup-Logik entfernt werden.

## Related Files
| File | Relevance |
|------|-----------|
| `migrate_to_plugin.py` | `_find_removable_command_files()` löscht jede `.claude/commands/<name>.md`, deren Dateiname zu einem `skills/<name>/SKILL.md` passt — unabhängig vom Inhalt. Das killt sowohl alte Volltext-Kopien als auch bewusste Alias-Weiterleitungen. |
| `setup.py` | Enthält `install_plugin_mode()` (Frisch-Install) und `update_project()` (Legacy-Modus-Update). Kein bestehender Mechanismus erzeugt Alias-Dateien. |
| `skills/*/SKILL.md` | 16 Skills, deren Verzeichnisname (`00-bug`, `50-implement`, ...) der kanonische Kurzname ist. |
| `.claude-plugin/plugin.json` | Enthält die Versionsnummer (aktuell 3.4.15). |
| `CHANGELOG.md` | Muss um den neuen Eintrag ergänzt werden. |

## Existing Patterns
- Claude Code unterstützt lokale `.claude/commands/*.md`-Dateien, die als eigenständige,
  nicht-namespaced Slash-Commands erscheinen — auch parallel zu einem gleichnamigen
  Plugin-Skill (bestätigt via claude-code-guide-Agent gegen die offizielle Doku:
  `https://code.claude.com/docs/en/plugins.md`, `https://code.claude.com/docs/en/skills.md`).
  Eine solche Datei kann per `$ARGUMENTS`-Weiterleitung den Plugin-Skill aufrufen:
  ```
  /agent-os-openspec:50-implement $ARGUMENTS
  ```
- Es gibt kein offizielles Alias-Feature auf Plugin-Ebene — Namespacing ist bei
  Plugin-Skills/-Commands immer aktiv (verhindert Kollisionen zwischen Plugins).

## Dependencies
- Upstream: Claude Code lädt `.claude/commands/*.md` sowohl aus dem Projekt als auch
  aus `~/.claude/commands/` (User-Scope, projektübergreifend).
- Downstream: `migrate_to_plugin.py` wird von Consumer-Projekten beim Umstieg auf
  Plugin-Mode ausgeführt und räumt `.claude/commands/` auf.

## Existing Specs
- Keine vorhandene Spec zu Command-Aliasing.

## Analysis

### Type
Feature (mit Bugfix-Charakter: eine frühere Cleanup-Logik löscht Aliase versehentlich)

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `setup.py` | MODIFY | Neue Funktion `generate_command_aliases(project_path)` + CLI-Flag `--command-aliases`. Schreibt für jeden `skills/<name>/` einen Alias in `<project_path>/.claude/commands/<name>.md` mit Marker-Kommentar + `/agent-os-openspec:<name> $ARGUMENTS`-Weiterleitung. |
| `migrate_to_plugin.py` | MODIFY | `_find_removable_command_files()` überspringt Dateien, die den Alias-Marker enthalten (Content-Check statt reiner Dateiname-Match). |
| `tests/test_migrate_command_cleanup.py` | MODIFY | Neuer Testfall: Alias-Datei mit Marker wird NICHT entfernt; Legacy-Volltext-Kopie ohne Marker weiterhin entfernt. |
| `tests/test_setup_command_aliases.py` | CREATE | Neue Tests für `generate_command_aliases()`: erzeugt eine Datei pro Skill, enthält Marker + Redirect, überschreibt keine bestehenden Custom-Commands ohne Marker. |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]` / neue Version. |
| `.claude-plugin/plugin.json` | MODIFY | Versionsbump 3.4.15 → 3.5.0 (neues Feature, keine Breaking Change → MINOR). |

### Scope Assessment
- Files: 6
- Estimated LoC: +90/-5
- Risk Level: LOW (rein additiv, betrifft nur `.claude/commands/`-Verwaltung, keine Hook-Gate-Logik)

### Technical Approach
1. **Marker-Konvention:** Jede generierte Alias-Datei beginnt mit
   `<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->` als erste Zeile,
   gefolgt von YAML-Frontmatter (`description:`) und dem Redirect-Body
   `/agent-os-openspec:<name> $ARGUMENTS`.
2. **`generate_command_aliases(project_path)`** iteriert `FRAMEWORK_ROOT/skills/*/`,
   überspringt Skills ohne `SKILL.md`, schreibt/überschreibt nur Dateien, die entweder
   nicht existieren ODER bereits den Marker tragen (schützt versehentlich
   gleichnamige, echte Custom-Commands eines Users vor Overwrite).
3. **`_find_removable_command_files()`** liest jede Kandidaten-Datei und prüft auf
   den Marker via `MARKER not in content` → nur dann als "removable legacy" werten.
   Dateien MIT Marker sind das neue Feature selbst und werden nie entfernt.
4. **Zielort:** `setup.py <path> --command-aliases` bleibt generisch (beliebiger
   `project_path`). Empfehlung an den User: einmalig `python3 setup.py ~
   --command-aliases` für globale Verfügbarkeit über alle Projekte hinweg, sowie
   optional pro Projekt falls dort abweichend gewünscht.

### Dependencies
- Keine Downstream-Breaks: bestehende `.claude/commands/*.md` ohne Marker (echte
  projektspezifische Custom-Commands) bleiben von `_find_removable_command_files()`
  unangetastet — Verhalten für diesen Fall ändert sich nicht.

### Open Questions
- Keine offenen Fragen — Ansatz mit User im Zuge der Diskussion abgestimmt.

## Risks & Considerations
- Die Cleanup-Logik in `migrate_to_plugin.py` muss zwischen "alte Volltext-Kopie"
  (löschen) und "bewusster Kurz-Alias" (behalten) unterscheiden — sonst killt der
  nächste Migrationslauf die neu angelegten Aliase wieder. Lösung: Marker-Kommentar
  in der generierten Alias-Datei, den die Cleanup-Funktion erkennt.
  → **das war die Ursache des ursprünglichen Bugs** (Issue #24 / Commit `71608aa`
  löschte pauschal nach Dateiname, nicht nach Inhalt).
- Skill-Set kann wachsen (neue Skills) — Alias-Generierung muss automatisch aus dem
  `skills/`-Verzeichnis ableiten, nicht hartkodierte Liste.
- Ziel-Ort der generierten Aliase: `~/.claude/commands/` (User-Scope) ist am
  praktischsten, weil er projektübergreifend gilt und nicht in jedem Consumer-Repo
  einzeln gepflegt werden muss. `setup.py` nimmt bereits einen beliebigen
  `project_path` entgegen — `~` als Pfad funktioniert ohne Sonderfall.
- Scope-Grenze: Diese Änderung erzeugt/verwaltet nur die Alias-Dateien und schützt
  sie vor der Cleanup-Logik. Sie ändert NICHT, wie Skills selbst definiert sind.
