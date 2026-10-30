# Kontext + Analyse: fix-493-plan-pane-doppelt (Issue #493)

## Request Summary
PO: Nach Exit der Claude-Session bleibt der Herdr-Plan-Pane (#476) offen. Startet Claude im **selben Herdr-Pane** neu, wird der offene Plan-Pane nicht gefunden und ein zweiter geoeffnet.

## Related Files
- `core/hooks/herdr_bridge.py` — `_ac_base()` (Z. ~343, worktree-lokal), `open_plan_pane()`, `open_plan_pane_for_active()`, `_pp_open()` (gemerkte ID `.claude/herdr_plan_pane.json`, `pane get`, `pane split`, `pane run ... plan --watch`), `run_plan_pane()` (Lock `.claude/herdr_plan_pane.lock`)
- `core/hooks/workflow.py` — `_plan_watch()` (Z. ~1790), `_plan_active()` → `read_active_workflow_fast()` → `hook_utils.resolve_active_workflow()` (cwd-/worktree-abhaengig)
- `core/hooks/hook_utils.py` — `find_project_root()` (loest aus Worktree zum Haupt-Repo auf), `_find_worktree_root()`, `read_state_json`, `atomic_write_json`
- `core/hooks/session_banner.py:534` — SessionStart ruft `open_plan_pane_for_active()`
- Tests: `tests/test_herdr_plan_pane_476.py` (Stub-Herdr mit `pane get/split/rename/run`), `tests/test_herdr_plan_deploy_sessionstart_478.py`

## Ursache (Code-Beleg)
1. `_pp_open` liest/schreibt die Pane-ID unter `_ac_base()/.claude/herdr_plan_pane.json`; `_ac_base()` ist der **Worktree** der Session. Jede neue Claude-Session arbeitet in einem neuen Worktree (Worktree-Pflicht) → andere Datei → keine bekannte ID → zweiter `pane split`.
2. Folgeproblem bei Wiederverwendung: Der Watcher im Plan-Pane laeuft mit `cwd` = alter Worktree und loest den aktiven Workflow relativ zu diesem cwd auf. Ein wiederverwendeter Pane wuerde den Workflow der **alten** Session zeigen.

## Existing Patterns
- Geteilter Zustand liegt im Haupt-Repo (`find_project_root()`), z. B. `.claude/workflows/`, `.claude/issue_titles.json` (#490).
- Herdr-Aufrufe fail-open mit Timeout (`_pp_call`), Logs `.claude/herdr_plan_pane.log`.

## Dependencies
- Herdr-CLI 0.9.5: `pane get`, `pane split`, `pane rename`, `pane run` (kein bekannter `pane close` → nicht verwenden).
- `HERDR_PANE_ID` der Claude-Session (bleibt beim Neustart im selben Pane gleich).

## Loesungsrichtung
- ID-Datei ins Haupt-Repo (`find_project_root()/.claude/`), Eintrag je Claude-Pane: `{"<claude_pane>": {"pane_id": ..., "cwd": ...}}`; alte Single-Form `{"pane_id": ...}` weiter lesbar.
- Wiederverwendung: `pane get` ok → `cwd` im Eintrag auf neue Basis setzen statt neu splitten.
- Watcher liest pro Runde seinen Eintrag (per `--target <claude_pane>`) und wechselt per `os.chdir` in die eingetragene Basis, wenn sie existiert und abweicht.

## Risks & Considerations
- Nicht in diesem Container nachstellbar (kein Herdr); Nachweis per Stub-Binary wie in #476.
- Bestehende Watcher (ohne `--target`) laufen unveraendert weiter.
- Lock ebenfalls ins Haupt-Repo, damit zwei Worktrees nicht parallel splitten.
