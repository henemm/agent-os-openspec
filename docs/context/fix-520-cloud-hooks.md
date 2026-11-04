# Kontext: fix-520-cloud-hooks (Issue #520)

## Anfrage (PO, 2026-11-04)

Tech-Lead-Empfehlung „Gates greifen in Cloud-Sitzungen nicht“ als oberste Priorität; PO: „Ja“ (Issue anlegen und damit anfangen). Arbeitsweise weiter autonom wie #508/#509.

## Befund

- Cloud-Sitzung (Claude Code on the web) für dieses Repo: `CLAUDE_CODE_REMOTE=true`, `~/.claude/plugins/` ohne installiertes Plugin, `.claude/settings.json` nur mit `permissions`. Kein Hook aus `hooks/hooks.json` läuft.
- #508 und #509 liefen deshalb ohne `edit_gate`, `bash_gate`, `tdd_enforcement`, `post_implementation_gate`, `footer_gate`, `session_singleton_guard`. Erzwungen hat nur die CI.

## Doku-Lage (code.claude.com, abgefragt 2026-11-04)

- `cloud-environments`: „Plugins and marketplaces declared in your repo's `.claude/settings.json`: No.“ `enabledPlugins`/`extraKnownMarketplaces` wirken in der Cloud nicht (braucht Workspace-Trust-Dialog, den die Cloud nie zeigt).
- `cloud-environments`: „Your repo's `.claude/settings.json` hooks and permission rules: Yes, in a session with one repository.“ Nicht in Cloud-Threads eines Claude-Projekts und nicht bei mehreren Repos.
- `hooks`: Gleicher Handler in mehreren Settings-Dateien läuft einmal; die Kopie eines Plugins bleibt getrennt → Copy-Hooks plus Plugin laufen lokal doppelt.
- `env-vars`: `CLAUDE_CODE_REMOTE` ist `true` in Cloud-Sitzungen, lokal nicht gesetzt. `CLAUDE_PROJECT_DIR` ist in Hooks gesetzt (Repo-Wurzel).

## Folgerung

Einziger dokumentierter Weg: Hooks in der Projekt-`.claude/settings.json` registrieren. Damit lokal (Plugin installiert) nichts doppelt läuft, startet jeder Eintrag sein Skript nur bei `CLAUDE_CODE_REMOTE=true`.

## Code-Stand (4.5.2)

- `hooks/hooks.json`: 23 Einträge, Format `${CLAUDE_PLUGIN_ROOT}/core/hooks/<datei>.py [args]`.
- `setup.py:543` `_PLUGIN_HOOK_CMD_RE`, `setup.py:554` `copy_mode_hooks()`: leitet Copy-Modus-Hooks für Konsumenten aus `hooks.json` ab (#279), Ziel `.claude/hooks/`.
- `core/hooks/hook_utils.py:2062` `find_plugin_root()`: nutzt `CLAUDE_PLUGIN_ROOT`, sonst Elternordner von `core/hooks`.
- `core/hooks/session_singleton_guard.py:700–740` `guard`: blockt schreibende Tools außerhalb von `.claude/worktrees/<n>/`, sofern `.git` vorhanden. In der Cloud (ein Container pro Sitzung, Arbeitsordner = normaler Klon) würde das jede Sitzung sperren — betrifft heute schon Copy-Modus-Konsumenten in der Cloud.
- `scripts/release_check.py`: prüft u. a. Skill-Drift (`sync_skills.py`); Vorbild für eine Drift-Prüfung.

## Abgrenzung

- Konsumenten im Plugin-Modus haben in der Cloud keine Hook-Skripte im Repo; das bleibt offen (Folge-Issue). Copy-Modus-Konsumenten profitieren von der Guard-Ausnahme.
