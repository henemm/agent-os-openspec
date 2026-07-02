# Context: feat-resolve-execution-context

## Request Summary
`bash_gate.py`, `edit_gate.py`, `qa_gate.py`, `workflow.py` und `hook_utils.py` lösen
jeweils separat auf, (a) welcher Workflow aktiv ist und (b) wo der Plugin-Root liegt.
Uneinheitliche Prioritäts-/Fallback-Regeln verursachen 6 offene Issues. Ziel: eine
zentrale, getestete Resolution-Schicht, die von allen Konsumenten einheitlich genutzt
wird.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/hook_utils.py` | Enthält `find_project_root()`, `find_plugin_root()`, `resolve_active_workflow()` — die eigentlichen Auflösungsfunktionen |
| `core/hooks/bash_gate.py` | Nutzt `find_project_root()` für den Rebase-Check (Issue #26: falscher Root) |
| `core/hooks/edit_gate.py` | Datei-Ownership-Matching über `affected_files` aller Workflows (Issue #38) |
| `core/hooks/qa_gate.py` | Nutzt `find_plugin_root()` für `_set_verdict()`-Subprozess-Pfad (Issue #28) |
| `core/hooks/workflow.py` | `start`/`switch` schreiben `OPENSPEC_ACTIVE_WORKFLOW` nach `settings.local.json` (Issue #13) |
| `tests/test_selfexplaining_gates.py`, `tests/test_workflow_name_validation.py`, `tests/test_gate_coverage.py` | Nicht hermetisch, weil sie nur `find_project_root()` mocken, nicht `_find_worktree_root()` (Issue #35) |
| `~/.claude/plugins/installed_plugins.json` | Enthält den echten `installPath` der aktiven Plugin-Version — bisher ungenutzte, robustere Quelle für Plugin-Root |

## Issue-Quellen (Volltext bereits recherchiert)
- #13: resolve_active_workflow — veraltete Session-Env verschattet frisch gestarteten Workflow (2x wiedereröffnet)
- #26: bash_gate.py Rebase-Check prüft Hauptrepo-Branch statt Worktree-Branch
- #28: qa_gate.py Verdict-Set schlägt im Worktree still fehl (find_plugin_root Fallback falsch)
- #33: CLAUDE_PLUGIN_ROOT bei manuell aufgerufenen CLI-Tools nicht aufgelöst → strukturelle Doppelentwicklung
- #35: Tests für resolve_active_workflow() nicht hermetisch → 11 rote Tests bei aktivem Worktree-Workflow
- #38: edit_gate — stale Workflow-State kapert Datei-Ownership über affected_files

## Existing Patterns
- `find_project_root()` löst Worktrees absichtlich auf den Hauptrepo-Root auf (für gemeinsamen `.claude/workflows/`-State) — richtig für State, falsch für git-Branch-Vergleiche (#26).
- `resolve_active_workflow()`: Env zuerst, Fallback nur bei leerer Env — keine Staleness-Erkennung.
- `find_plugin_root()`: `CLAUDE_PLUGIN_ROOT` → Fallback `Path(__file__).parent.parent.parent`, ohne zu prüfen ob dort wirklich `.claude-plugin/plugin.json` existiert.

## Dependencies
- Downstream: ALLE Consumer-Projekte, die das Plugin nutzen (gregor_zwanzig, henemm-website, etc.) — jede Änderung an der Resolution-Logik wirkt sich auf deren Gate-Verhalten aus.
- Upstream: Claude-Code-Harness-Verhalten bzgl. `CLAUDE_PLUGIN_ROOT`-Injection (nur für Harness-Hook-Subprozesse, nicht für manuelle Bash-Aufrufe) — außerhalb unserer Kontrolle, muss als gegeben behandelt werden.

## Existing Specs
- Keine vorhandene Spec zu zentraler Context-Resolution.

## Risks & Considerations
- Höchster Blast Radius im gesamten Framework — Fehler hier blockieren Commits/Edits in JEDEM Consumer-Projekt.
- Rückwärtskompatibilität: bestehendes Verhalten für den Normalfall (kein Worktree, kein Workflow-Wechsel mitten in der Sitzung) darf sich nicht ändern.
- `.claude/settings.local.json` wird von der Harness selbst bei Permission-Grants überschrieben (in #13 als Ursache vermutet) — evtl. braucht es eine robustere Speicherform als diese Datei für den "zuletzt gestarteten Workflow"-Zeiger.
- Scope-Grenze: Diese Iteration konsolidiert die Resolution-Logik und macht Plugin-Root robust (via `installed_plugins.json`). Sie behebt NICHT zwangsläufig das settings.local.json-Overwrite-Verhalten der Harness selbst (außerhalb unserer Kontrolle) — dafür ggf. eine robustere Speicherform als Workaround.
