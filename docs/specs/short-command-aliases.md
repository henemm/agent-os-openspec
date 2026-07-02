---
entity_id: short-command-aliases
type: feature
created: 2026-07-02
updated: 2026-07-02
status: draft
version: "1.0"
tags: [setup, commands, aliases, migrate-to-plugin, cli]
workflow: feat-short-command-aliases
---

# Short Command Aliases

## Approval

- [ ] Approved

## Purpose

Seit der Plugin-Migration (v3.2) zeigt Claude Code alle Skills mit Namespace-Präfix
(`/agent-os-openspec:50-implement` statt `/50-implement`). Diese Spec fügt einen
opt-in-Mechanismus hinzu, der pro Skill eine kurze, lokale `.claude/commands/<name>.md`-
Redirect-Datei erzeugt (`/agent-os-openspec:<name> $ARGUMENTS`), markiert diese
eindeutig als vom Framework verwaltet, und stellt sicher, dass die
Migrations-Cleanup-Logik (`migrate_to_plugin.py`) diese Aliase nicht mehr fälschlich
als Legacy-Duplikate löscht (Issue #24 / Commit `71608aa`).

## Source

- **File:** `setup.py`
- **Identifier:** `def generate_command_aliases(project_path: Path) -> None`, CLI-Flag `--command-aliases` in `main()`
- **File:** `migrate_to_plugin.py`
- **Identifier:** `def _find_removable_command_files(project_path: Path) -> list[Path]`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `FRAMEWORK_ROOT / skills / <name> / SKILL.md` | Datenquelle | Kanonische Liste der Skill-Namen, aus der die Aliase generiert werden (aktuell 16 Skills, z.B. `00-bug`, `50-implement`) |
| `setup.py::main()` / `argparse` | bestehende CLI | Neues Flag `--command-aliases` reiht sich neben `--plugin-mode`, `--update`, `--force` ein |
| `migrate_to_plugin.py::_find_removable_command_files()` | bestehende Funktion | Muss den neuen Marker erkennen, um generierte Aliase von Legacy-Duplikaten zu unterscheiden |
| `tests/test_migrate_command_cleanup.py` | bestehende Tests | Stilvorlage (Direktimport `import migrate_to_plugin as mig`, `tmp_path`-Fixtures) für neue und erweiterte Tests |
| `.claude-plugin/plugin.json` | Versionsquelle | Wird von `setup.py::_read_plugin_version()` gelesen; Bump auf 3.5.0 erforderlich, kein Code-Änderung in `setup.py` nötig |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|--------------|
| `setup.py` | MODIFY | Neue Funktion `generate_command_aliases(project_path)` + CLI-Flag `--command-aliases` |
| `migrate_to_plugin.py` | MODIFY | `_find_removable_command_files()` prüft Datei-Inhalt auf Marker statt nur Dateiname |
| `tests/test_setup_command_aliases.py` | CREATE | Tests für `generate_command_aliases()` |
| `tests/test_migrate_command_cleanup.py` | MODIFY | Neuer Testfall: Marker-Datei bleibt erhalten, Legacy-Datei ohne Marker wird weiterhin entfernt |
| `CHANGELOG.md` | MODIFY | Neuer Eintrag unter `[Unreleased]` / `### Added` |
| `.claude-plugin/plugin.json` | MODIFY | Versionsbump `3.4.15` → `3.5.0` (MINOR, additiv) |

### Estimated Changes

- Files: 6
- LoC: +90/-5 (ca.)

## Implementation Details

### 1. `generate_command_aliases(project_path: Path) -> None` in `setup.py`

- Iteriert über `FRAMEWORK_ROOT / "skills"`, für jedes Unterverzeichnis mit
  vorhandener `SKILL.md` wird `<name>` = Verzeichnisname als Skill-Alias verwendet.
  Verzeichnisse ohne `SKILL.md` werden übersprungen.
- Zielpfad: `<project_path>/.claude/commands/<name>.md`. Verzeichnis wird mit
  `mkdir(parents=True, exist_ok=True)` angelegt, falls es nicht existiert.
- Erzeugter Datei-Inhalt (exakt, erste Zeile ist der Marker):
  ```
  <!-- openspec-alias: do-not-treat-as-legacy-duplicate -->
  ---
  description: Kurz-Alias für /agent-os-openspec:<name>
  ---

  /agent-os-openspec:<name> $ARGUMENTS
  ```
- Overwrite-Regel pro Zieldatei:
  - Existiert die Datei nicht → schreiben, zählt als "created".
  - Existiert die Datei und ihre erste Zeile beginnt mit `<!-- openspec-alias:`
    → überschreiben, zählt als "updated".
  - Existiert die Datei und die erste Zeile enthält den Marker NICHT (= vermuteter
    projektspezifischer Custom-Command) → NICHT anfassen, zählt als "skipped",
    Name wird in einer Sammel-Liste für die Abschluss-Warnung vermerkt.
- Am Ende: Zusammenfassung ausgeben, z.B.
  `"Command aliases: 14 created, 2 updated, 1 skipped."`, gefolgt von je einer
  Zeile `"  SKIPPED (custom command exists): <name>.md"` pro übersprungener Datei.
- Funktion hat keinen Rückgabewert (reine Seiteneffekt-Funktion, `-> None`), macht
  sie über Print-Ausgaben und den Dateisystem-Zustand testbar.

### 2. CLI-Flag `--command-aliases` in `setup.py::main()`

- Neues `argparse`-Flag, konsistent zu den bestehenden Flags (`action="store_true"`,
  eigener Hilfetext, Beispielzeile im `epilog`).
- In `main()`: Wird das Flag gesetzt, ruft der Code
  `generate_command_aliases(project_path)` auf und `return`et danach — analog zum
  bestehenden Muster für `--update` und `--plugin-mode` (früher Return vor der
  regulären Fresh-Install-Logik). Kombinierbar mit anderen Flags ist nicht
  gefordert; das Flag deckt einen eigenständigen Nutzungspfad ab
  (`python3 setup.py <path> --command-aliases`), unabhängig von Install/Update.
- Kein automatischer Aufruf von `generate_command_aliases()` an anderer Stelle in
  `install_plugin_mode()` oder `update_project()` — die Alias-Generierung bleibt
  ausschließlich explizit über das Flag erreichbar.

### 3. `migrate_to_plugin.py::_find_removable_command_files()`

- Bisheriges Verhalten: `[f for f in commands_dir.glob("*.md") if f.stem in provided]`
  — reiner Dateiname-Match, ignoriert den Inhalt.
- Neues Verhalten: Zusätzlich zum Namens-Match wird der Dateiinhalt gelesen; nur
  wenn der String `openspec-alias:` NICHT im Inhalt vorkommt, gilt die Datei als
  entfernbares Legacy-Duplikat. Enthält die Datei den Marker, wird sie aus der
  removable-Liste ausgeschlossen (das ist der neue, bewusst angelegte Alias selbst).
- Der bisherige Zweck der Funktion (Docstring: Entfernen von Volltext-Kopien aus
  Legacy-Pre-Plugin-Installs, die einen `skills/<name>/SKILL.md`-Namen duplizieren)
  bleibt für Dateien ohne Marker vollständig unverändert erhalten.
- Lesefehler (z.B. Binärdatei, kaputte Encoding) dürfen die Funktion nicht zum
  Absturz bringen — Datei in diesem Fall konservativ NICHT als removable werten
  (Fail-safe: im Zweifel nicht löschen).

### 4. CHANGELOG.md

- Neuer Eintrag unter `[Unreleased]` / Abschnitt `### Added`, der beschreibt:
  Problem (Issue #24 hatte Aliase mangels Content-Unterscheidung mitgelöscht),
  Fix (Marker-Kommentar + Content-Check), neue Nutzung
  (`python3 setup.py <path> --command-aliases`, Empfehlung `~` für global über
  alle Projekte).

### 5. Versionsbump

- `.claude-plugin/plugin.json`: `"version": "3.4.15"` → `"version": "3.5.0"`.
- `setup.py::_read_plugin_version()` liest die Version bereits dynamisch aus
  dieser Datei — keine Code-Änderung in `setup.py` für den Versionsbump nötig.

## Expected Behavior

- **AC-1:** Given ein leeres `.claude/commands/`-Verzeichnis (oder gar keins) in
  `project_path` / When `generate_command_aliases(project_path)` aufgerufen wird /
  Then existiert für jeden Skill mit `SKILL.md` unter `FRAMEWORK_ROOT/skills/` eine
  Datei `.claude/commands/<name>.md`, deren erste Zeile exakt
  `<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->` lautet und deren
  Inhalt die Zeile `/agent-os-openspec:<name> $ARGUMENTS` sowie das YAML-Frontmatter
  `description: Kurz-Alias für /agent-os-openspec:<name>` enthält.
- **AC-2:** Given `.claude/commands/` existiert vorher nicht in `project_path` /
  When `generate_command_aliases(project_path)` aufgerufen wird / Then wird das
  Verzeichnis automatisch angelegt, ohne Fehler.
- **AC-3:** Given `.claude/commands/50-implement.md` existiert bereits mit dem
  Marker in der ersten Zeile (alter Alias-Stand) / When
  `generate_command_aliases(project_path)` erneut aufgerufen wird / Then wird die
  Datei überschrieben (Update-Fall), der Inhalt entspricht danach exakt dem
  aktuellen Template.
- **AC-4:** Given `.claude/commands/50-implement.md` existiert bereits OHNE den
  Marker in der ersten Zeile (z.B. mit Inhalt `"custom user command"`) / When
  `generate_command_aliases(project_path)` aufgerufen wird / Then bleibt der
  Datei-Inhalt unverändert (kein Overwrite), und die Funktion gibt am Ende eine
  Warnung der Form `SKIPPED (custom command exists): 50-implement.md` aus.
- **AC-5:** Given ein vollständiger Lauf über alle Skills mit gemischtem
  Ausgangszustand (einige Dateien fehlen, eine hat den Marker, eine hat keinen
  Marker) / When `generate_command_aliases(project_path)` aufgerufen wird / Then
  gibt die Funktion am Ende eine Zusammenfassung mit korrekten Zählern für
  "created", "updated" und "skipped" aus, deren Summe der Gesamtzahl der Skills
  entspricht.
- **AC-6:** Given `setup.py <project_path> --command-aliases` wird als CLI-Aufruf
  ausgeführt / When `main()` das Flag parst / Then wird `generate_command_aliases`
  mit dem aufgelösten `project_path` aufgerufen und das Programm beendet sich
  danach, ohne die reguläre Fresh-Install- oder Update-Logik auszuführen.
- **AC-7:** Given ein normaler Aufruf von `setup.py <project_path>` (ohne
  `--command-aliases`) oder `setup.py <project_path> --update` / When das Setup
  durchläuft / Then wird `generate_command_aliases()` NICHT automatisch aufgerufen
  und `.claude/commands/` bleibt von diesem Feature unangetastet.
- **AC-8:** Given eine Datei `.claude/commands/00-intake.md` mit Marker-Inhalt
  (`<!-- openspec-alias: ... -->` in der ersten Zeile) und passendem Skill-Namen /
  When `migrate_to_plugin._find_removable_command_files(project_path)` aufgerufen
  wird / Then ist diese Datei NICHT in der zurückgegebenen Liste enthalten.
- **AC-9:** Given eine Datei `.claude/commands/00-intake.md` mit reinem
  Legacy-Volltext-Inhalt (kein Marker, entspricht dem alten Kopier-Verhalten) und
  passendem Skill-Namen / When
  `migrate_to_plugin._find_removable_command_files(project_path)` aufgerufen wird /
  Then ist diese Datei weiterhin in der zurückgegebenen Liste enthalten
  (Alt-Verhalten für echte Duplikate bleibt erhalten).
- **AC-10:** Given eine Datei `.claude/commands/e2e-verify.md`, deren Name keinem
  `skills/<name>/`-Verzeichnis entspricht (echter Custom-Command) / When
  `_find_removable_command_files(project_path)` aufgerufen wird / Then ist diese
  Datei nicht in der Liste enthalten (unverändertes Verhalten gegenüber vor
  diesem Fix).
- **AC-11:** Given `CHANGELOG.md` / When die Datei nach Umsetzung gelesen wird /
  Then enthält der `[Unreleased]`-Abschnitt unter `### Added` einen Eintrag, der
  Issue #24, den Marker-basierten Fix und den CLI-Aufruf
  `python3 setup.py <path> --command-aliases` erwähnt.
- **AC-12:** Given `.claude-plugin/plugin.json` / When die Datei nach Umsetzung
  gelesen wird / Then ist der Wert des Felds `"version"` exakt `"3.5.0"`.

## Known Limitations

- Die Alias-Generierung ist rein additiv und nicht Teil des Standard-Install-/
  Update-Flows — Consumer-Projekte müssen `--command-aliases` bewusst und manuell
  ausführen (kein Auto-Migrate für bestehende Installationen).
- Der Custom-Command-Schutz (AC-4) basiert ausschließlich auf der ersten Zeile der
  Datei. Ein User, der zufällig exakt die Marker-Zeile `<!-- openspec-alias:
  do-not-treat-as-legacy-duplicate -->` als erste Zeile eines eigenen,
  unabhängigen Custom-Commands verwendet, würde bei einem Re-Lauf überschrieben
  werden. Dieses Risiko ist bewusst akzeptiert (Kollisions-Wahrscheinlichkeit
  vernachlässigbar bei diesem spezifischen, framework-eigenen Marker-Text).
- Wächst das `skills/`-Verzeichnis um neue Skills, werden diese erst nach einem
  erneuten `--command-aliases`-Lauf als Alias verfügbar — kein automatischer
  Watch-Mechanismus.
- Diese Änderung betrifft ausschließlich `.claude/commands/`-Verwaltung; sie
  ändert nichts an der Definition der Skills selbst oder an Hook-Gate-Logik.

## Test Plan

Direktimport-Pattern wie in `tests/test_migrate_command_cleanup.py`
(`sys.path.insert` auf `REPO_ROOT`, `import setup` bzw. `import migrate_to_plugin as mig`),
`tmp_path`-Fixtures für isolierte `project_path`-Verzeichnisse.

### `tests/test_setup_command_aliases.py` (neu)

- GIVEN ein leeres `tmp_path` / WHEN `setup.generate_command_aliases(tmp_path)`
  aufgerufen wird / THEN existiert für jeden Skill unter `FRAMEWORK_ROOT/skills/`
  eine Datei `.claude/commands/<name>.md` mit korrektem Marker und Redirect-Inhalt.
- GIVEN eine vorhandene Marker-Datei mit veraltetem Inhalt / WHEN
  `generate_command_aliases(tmp_path)` erneut aufgerufen wird / THEN wird die
  Datei mit dem aktuellen Template überschrieben.
- GIVEN eine vorhandene Datei ohne Marker (simulierter Custom-Command) / WHEN
  `generate_command_aliases(tmp_path)` aufgerufen wird / THEN bleibt der Inhalt
  dieser Datei unverändert.
- GIVEN `tmp_path` ohne `.claude/commands/`-Verzeichnis / WHEN
  `generate_command_aliases(tmp_path)` aufgerufen wird / THEN wird das
  Verzeichnis angelegt und die Aliase werden erfolgreich geschrieben.

### `tests/test_migrate_command_cleanup.py` (erweitert)

- GIVEN eine Datei `.claude/commands/00-intake.md` mit Marker-Erster-Zeile / WHEN
  `mig._find_removable_command_files(tmp_path)` aufgerufen wird / THEN ist diese
  Datei NICHT im Ergebnis enthalten.
- GIVEN parallel eine gleichnamige Legacy-Datei ohne Marker in einem anderen
  Testfall (z.B. `.claude/commands/90-retro.md` mit Volltext-Inhalt) / WHEN
  `mig._find_removable_command_files(tmp_path)` aufgerufen wird / THEN ist diese
  Datei weiterhin im Ergebnis enthalten.

## Changelog

- 2026-07-02: Initial spec erstellt (Marker-basierte Kurz-Alias-Generierung für Skills, Content-Check-Fix in `migrate_to_plugin.py` gegen Issue #24)
