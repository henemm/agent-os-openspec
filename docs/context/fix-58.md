# Kontext: Fix #58 — Worktree-Identitäts-Kaperung

## Fundstellen

- **Auflösungskette:** `core/hooks/hook_utils.py::resolve_active_workflow()` (Zeilen ~260–338).
  - Worktree-Zweig: Prio 1 `active_workflow`-Datei → Prio 2 worktree-`settings.local.json` → Prio 3 eingefrorene `OPENSPEC_ACTIVE_WORKFLOW`-Env-Var.
  - Prio-3-Validierung nur via `_workflow_file_exists(root, name)` mit `root = find_project_root()` → **geteiltes Hauptrepo** → fremde Workflows bestehen die Prüfung.
- **Workflow-JSON-Speicherort:** `_workflow_dir()` = `find_project_root()/.claude/workflows` → geteilt über alle Worktrees/Sessions. Workflow-State trägt **kein** Ownership-Feld (`_new_workflow()` in `core/hooks/workflow.py`).
- **Konsumenten der Auflösung:** `tdd_enforcement.py`, `post_implementation_gate.py`, `bash_gate.py` (via `read_active_workflow_fast()` / `_read_active()`).

## Bestehende Tests

- `tests/test_workflow_resolution_consolidation.py` — deckt Prio-Kette ab, `_bind_context()` mockt `find_project_root`/`_find_worktree_root`/`_worktree_root_if_any`. Direkte Vorlage für die neuen Tests.

## Belege

- Issue #58, Kommentar 2026-07-23 (Plugin 3.9.3): reproduzierter False-Block in `henemm/gregor_zwanzig`; frozen Env zeigte auf fremden `feat-1337-egress-guard-core`, dessen JSON im Hauptrepo existierte → Prio-3-Prüfung bestanden → Kaperung.
