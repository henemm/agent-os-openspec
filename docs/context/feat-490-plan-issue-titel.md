# Kontext: feat-490-plan-issue-titel (Issue #490)

Nachgetragen aus der Spec-Recherche (Workflow-State ging beim Container-Wechsel verloren).

## Relevante Dateien
- `core/hooks/workflow.py` — `render_plan`, `_plan_active`, `_plan_watch`, `cmd_plan`, `cmd_start`, `issue_number`, `_workflows_dir` (#476/#478)
- `core/hooks/hook_utils.py` — `find_project_root`, `atomic_write_text`

## Externe Abhaengigkeit
- `gh issue view N --json title -q .title` (GitHub CLI), optional; fehlt sie, entfaellt die Titelzeile.

## Risiken
- Abruf darf Start/Anzeige nie verzoegern → abgekoppelter Prozess, Cache, Fail-open.
