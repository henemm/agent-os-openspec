---
entity_id: fix-520-cloud-hooks
type: bugfix
created: 2026-11-04
updated: 2026-11-04
status: draft
version: "1.0"
workflow: fix-520-cloud-hooks
tags: [hooks, cloud, settings, worktree, enforcement]
---

# Gates in Cloud-Sitzungen (Issue #520)

## Approval

- [ ] Approved

## Purpose

In Cloud-Sitzungen (Claude Code on the web) läuft für dieses Repo kein einziger Framework-Hook: Die Cloud lädt keine Plugins, auch nicht über `enabledPlugins` in der Projekt-`settings.json`. Dokumentiert ausgeführt werden nur Hooks, die direkt in der Projekt-`.claude/settings.json` stehen. Künftig registriert dieses Repo dort alle Hooks aus `hooks/hooks.json`, jeweils so, dass sie nur in der Cloud (`CLAUDE_CODE_REMOTE=true`) starten; lokal mit installiertem Plugin läuft dadurch nichts doppelt. Ein Generator hält die Liste synchron mit `hooks/hooks.json`, `release_check.py` blockt Drift. Damit die Gates die Cloud-Sitzung nicht komplett sperren, nimmt `session_singleton_guard` Cloud-Sitzungen von der Worktree-Pflicht aus: Der Container ist die Isolation.

## Source

- **File:** `scripts/sync_cloud_hooks.py` (neu), `core/hooks/session_singleton_guard.py`, `scripts/release_check.py`, `.claude/settings.json`
- **Identifier:** `sync_cloud_hooks.cloud_hooks`, `sync_cloud_hooks.main` (neu); `session_singleton_guard` Modus `guard` (geändert); `release_check` Prüfliste (erweitert); genutzt, unverändert: `setup._PLUGIN_HOOK_CMD_RE`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hooks/hooks.json` | config | einzige Quelle der Hook-Liste (Event, Matcher, Reihenfolge, Timeout, Argumente) |
| `setup._PLUGIN_HOOK_CMD_RE` (#279) | regex | zerlegt `${CLAUDE_PLUGIN_ROOT}/core/hooks/<datei>.py [args]`; wird importiert, nicht kopiert |
| `hook_utils.find_plugin_root` | function | liest `CLAUDE_PLUGIN_ROOT`; der Cloud-Befehl setzt es auf die Repo-Wurzel |
| `scripts/sync_skills.py` | script | Vorbild für Generator mit `--check` und Release-Prüfung |
| `CLAUDE_CODE_REMOTE` | env | von Claude Code gesetzt, `true` nur in Cloud-Sitzungen |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| scripts/sync_cloud_hooks.py | CREATE | erzeugt den `hooks`-Block der Projekt-`settings.json` aus `hooks/hooks.json`; `--check` meldet Drift (Exit 1) |
| .claude/settings.json | MODIFY | `hooks`-Block (generiert); `permissions` bleibt unverändert |
| core/hooks/session_singleton_guard.py | MODIFY | `guard`: bei `CLAUDE_CODE_REMOTE == "true"` keine Worktree-Pflicht |
| scripts/release_check.py | MODIFY | neue Prüfung „Cloud-Hooks synchron“ |
| tests/test_cloud_hooks_520.py | CREATE | Generator, Drift, Befehlsverhalten lokal/Cloud, Guard-Ausnahme, Release-Prüfung, Doku |
| README.md | MODIFY | Abschnitt „Cloud sessions (Claude Code on the web)“ |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 2 neu, 5 geändert
- LoC: +90/−0 Produktion (+~180 generiertes JSON) / +250 Test
- Risk Level: HIGH (schaltet alle Gates für jede künftige Cloud-Sitzung dieses Repos scharf; ändert die Worktree-Pflicht für alle Konsumenten in der Cloud)

## Implementation Details

**Befehlsform** je Eintrag aus `hooks/hooks.json` (`${CLAUDE_PLUGIN_ROOT}/core/hooks/<datei>.py<args>`):

```
[ "$CLAUDE_CODE_REMOTE" != "true" ] || CLAUDE_PLUGIN_ROOT="${CLAUDE_PROJECT_DIR}" python3 "${CLAUDE_PROJECT_DIR}/core/hooks/<datei>.py"<args>
```

- Lokal (Variable fehlt oder ist nicht genau `true`): `[` ist wahr, Exit 0, das Skript startet nicht, stdin bleibt ungelesen.
- Cloud: das Skript läuft mit unverändertem stdin; sein Exit-Code (0/2/sonst) ist der Exit-Code des Befehls.
- Event, Matcher, Reihenfolge, `type`, `timeout` und Argumente werden 1:1 übernommen. Kein Eintrag wird ausgelassen (Parität; die herdr-/Watchdog-Hooks sind fail-open).
- Ein Kommando, das nicht zu `setup._PLUGIN_HOOK_CMD_RE` passt, bricht die Erzeugung mit Exit 1 ab (kein halber Schutz).

**`scripts/sync_cloud_hooks.py`**
- `cloud_hooks(hooks_json: dict) -> dict`: reine Funktion, liefert den `hooks`-Block.
- `main()`: ohne Argument liest `.claude/settings.json` (fehlt → `{}`), ersetzt nur den Schlüssel `hooks`, schreibt mit `indent=2`, `ensure_ascii=False`, abschließendem Zeilenumbruch. Alle anderen Schlüssel bleiben unverändert und in ihrer Reihenfolge. `--check`: schreibt nichts; Exit 0, wenn der `hooks`-Block gleich `cloud_hooks(...)` ist, sonst Exit 1 mit Meldung „Cloud-Hooks nicht synchron … `python3 scripts/sync_cloud_hooks.py`“.
- `--root <pfad>` (Default: Repo-Wurzel des Skripts) für Tests.

**`session_singleton_guard.py`, Modus `guard`:** direkt nach dem Heartbeat und vor der Tool-Prüfung: `if os.environ.get("CLAUDE_CODE_REMOTE") == "true": sys.exit(0)`. Kommentar: Cloud-Container = eine Sitzung, eigene Isolation (#520). `register`, `cleanup`, `claim`, `sync-main` bleiben unverändert.

**`release_check.py`:** neue Zeile „Cloud-Hooks“ in derselben Form wie „Skills“; ruft `sync_cloud_hooks` im Check-Modus auf (Funktion oder Subprozess), FAIL bei Drift.

**README:** Abschnitt „Cloud sessions (Claude Code on the web)“: Cloud lädt keine Plugins; Copy-Modus-Projekte haben ihre Hooks; dieses Repo registriert die Hooks per `sync_cloud_hooks.py` nur für die Cloud; nach jeder Änderung an `hooks/hooks.json` `python3 scripts/sync_cloud_hooks.py` ausführen; Plugin-Modus-Konsumenten sind in der Cloud ohne Gates (Folge-Issue).

## Expected Behavior

- **Input:** Tool-Aufruf in einer Sitzung dieses Repos
- **Output:** Cloud-Sitzung: dieselben Gates wie lokal mit Plugin, ohne Worktree-Pflicht. Lokale Sitzung: unverändert (Plugin-Hooks laufen einmal, die Projekt-Einträge enden sofort mit Exit 0).
- **Side effects:** `.claude/settings.json` bekommt einen `hooks`-Block; Release scheitert bei Drift zu `hooks/hooks.json`.

## Known Limitations

- Konsumenten im Plugin-Modus bleiben in der Cloud ohne Gates: die Hook-Skripte liegen dort nicht im Repo. PO-Entscheidung 2026-11-04: Folge-Issue #522.
- In Cloud-Threads eines Claude-Projekts und in Sitzungen mit mehreren Repos führt Claude Code laut Doku keine Projekt-Hooks aus.
- In der Cloud laufen die Hooks aus dem ausgecheckten Arbeitsstand dieses Repos, nicht aus dem gepinnten `@main`. Ein kaputter Hook endet mit Exit ≠ 2 und blockt nicht (nicht-blockierender Hook-Fehler); ein falsch blockender Hook ist per Override bzw. Rückbau der Zeile lösbar.
- Ob eine schon laufende Sitzung die neuen Hooks sofort übernimmt, hängt von Claude Code ab; sicher greifen sie ab der nächsten Sitzung.
- Lokal setzt der Nutzer `CLAUDE_CODE_REMOTE` nicht; wer es von Hand auf `true` setzt, bekommt lokal doppelte Hooks und keine Worktree-Pflicht. Das Modell kann die Umgebung des Hook-Prozesses nicht ändern.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] `python3 scripts/sync_cloud_hooks.py --check` und `scripts/release_check.py` (Zeile Cloud-Hooks) sind grün
- [ ] Beleg aus einer Cloud-Sitzung nach dem Merge: ein Gate greift (z. B. `footer_gate` oder `edit_gate`-Meldung), festgehalten im PR bzw. Issue
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/` grün)

## Acceptance Criteria

Testaufbau: echte Dateien in `tmp_path`, Befehle über `subprocess.run(["bash", "-c", cmd], input=payload, env=...)`. Kein Mock der Shell.

- **AC-1:** Given `hooks/hooks.json` dieses Repos / When `sync_cloud_hooks.cloud_hooks` läuft / Then enthält das Ergebnis dieselben Events, je Event dieselben Gruppen mit demselben Matcher in derselben Reihenfolge und je Gruppe dieselben Einträge in derselben Reihenfolge mit gleichem `type`, `timeout` und gleichen Argumenten; jedes `command` hat die Form aus „Implementation Details“ mit `core/hooks/<datei>.py` des Originals
  - Test: tests/test_cloud_hooks_520.py::test_cloud_hooks_mirror_plugin_hooks

- **AC-2:** Given das Repo im committeten Stand / When `python3 scripts/sync_cloud_hooks.py --check` läuft / Then Exit 0, und der `hooks`-Block in `.claude/settings.json` ist gleich `cloud_hooks(hooks.json)`
  - Test: tests/test_cloud_hooks_520.py::test_committed_settings_are_in_sync

- **AC-3:** Given eine Kopie (`--root`) mit `settings.json`, in der ein Eintrag fehlt bzw. ein Timeout abweicht / When `--check` läuft / Then Exit 1 mit „Cloud-Hooks nicht synchron“ und die Datei ist byte-identisch
  - Test: tests/test_cloud_hooks_520.py::test_check_detects_drift

- **AC-4:** Given eine Kopie mit `settings.json`, die `permissions` und einen weiteren Schlüssel enthält / When das Skript ohne `--check` zweimal läuft / Then sind `permissions` und der weitere Schlüssel unverändert, `hooks` ist gleich `cloud_hooks(...)` und der zweite Lauf ändert kein Byte
  - Test: tests/test_cloud_hooks_520.py::test_sync_keeps_other_keys_and_is_idempotent

- **AC-5:** Given ein Projektordner mit `core/hooks/probe.py`, das stdin, `CLAUDE_PLUGIN_ROOT` und einen Marker in eine Datei schreibt und mit Exit 2 endet, und der daraus erzeugte Befehl / When der Befehl (a) ohne `CLAUDE_CODE_REMOTE`, (b) mit `CLAUDE_CODE_REMOTE=false`, (c) mit `CLAUDE_CODE_REMOTE=true` läuft (jeweils `CLAUDE_PROJECT_DIR` = Projektordner, Pfad mit Leerzeichen) / Then (a) und (b) Exit 0 ohne Marker; (c) Exit 2, Marker vorhanden, stdin vollständig angekommen, `CLAUDE_PLUGIN_ROOT` = Projektordner
  - Test: tests/test_cloud_hooks_520.py::test_command_runs_only_in_cloud_and_propagates_exit

- **AC-6:** Given `session_singleton_guard.py guard` mit Bash-Payload und `cwd` in einem Git-Ordner außerhalb von `.claude/worktrees/` / When es (a) mit `CLAUDE_CODE_REMOTE=true`, (b) ohne die Variable, (c) mit `CLAUDE_CODE_REMOTE=1` läuft / Then (a) Exit 0 ohne Blockade-Meldung, (b) und (c) Exit 2 mit „Worktree-Pflicht“ wie bisher
  - Test: tests/test_cloud_hooks_520.py::test_guard_skips_worktree_rule_only_in_cloud

- **AC-7:** Given eine Kopie mit abweichendem `hooks`-Block / When die Cloud-Hooks-Prüfung aus `scripts/release_check.py` läuft / Then meldet sie FAIL mit Verweis auf `sync_cloud_hooks.py`; im committeten Stand OK
  - Test: tests/test_cloud_hooks_520.py::test_release_check_reports_cloud_hook_drift

- **AC-8:** Given `README.md` / When gelesen / Then gibt es einen Abschnitt zu Cloud-Sitzungen, der `CLAUDE_CODE_REMOTE` und `sync_cloud_hooks.py` nennt
  - Test: tests/test_cloud_hooks_520.py::test_readme_documents_cloud_sessions

- **AC-9:** Given `CHANGELOG.md` / When gelesen / Then steht ab `## [Unreleased]` (Unreleased oder ein Versionsabschnitt, release-fest) ein Eintrag, der `#520` nennt
  - Test: tests/test_cloud_hooks_520.py::test_changelog_mentions_520

## Test Plan

- `pytest tests/test_cloud_hooks_520.py`
- `pytest tests/test_copy_mode_hooks_279.py tests/test_hook_paths_project_dir_165.py tests/test_release_check_93.py` und alle `tests/test_session_singleton*`
- `python3 scripts/sync_cloud_hooks.py --check`, `python3 scripts/release_check.py --no-tests`
- Regressionslauf: `pytest tests/`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Kein neues Gate und keine neue Regel; dieselben Hooks bekommen einen zweiten, dokumentierten Ladeweg für die Cloud, abgeleitet aus der einen Quelle `hooks/hooks.json` (wie der Copy-Modus aus #279). Reversibel durch Entfernen des `hooks`-Blocks. Verworfen: (a) `enabledPlugins`/`extraKnownMarketplaces` — laut Doku in der Cloud wirkungslos; (b) Hooks ohne Cloud-Bedingung — lokal doppelte Ausführung neben dem Plugin (Doku: Plugin-Kopie wird nicht dedupliziert); (c) Setup-Skript der Umgebung installiert das Plugin — nicht versioniert, undokumentiert, liegt außerhalb des Repos.

## Changelog

- 2026-11-04: Initial spec created
- 2026-11-04: PO-Entscheidung Umfang: erst dieses Repo, Plugin-Konsumenten in #522
