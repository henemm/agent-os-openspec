---
entity_id: fix-58-worktree-identity-hijack
type: bugfix
created: 2026-07-24
updated: 2026-07-24
status: draft
version: "1.0"
tags: [bugfix, hooks, hook-utils, workflow-resolution, worktree, cross-session, gate-integrity]
test_targets:
  - core/hooks/hook_utils.py
  - tests/test_workflow_resolution_consolidation.py
---

# Fix #58: Worktree-Identitäts-Kaperung — eingefrorene Env-Var als Quelle im Worktree entfernen

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #58 (Worktree-Erstellung kopiert `settings.local.json` samt `env.OPENSPEC_ACTIVE_WORKFLOW` — fremde Workflow-Identität kapert neue Sessions)
- **Frischer Beleg:** Kommentar 2026-07-23 (Plugin 3.9.3), reproduzierter False-Block in `henemm/gregor_zwanzig`

## Purpose

`hook_utils.resolve_active_workflow()` erlaubt in einer **Worktree-Session**, dass die bei Session-Start eingefrorene `OPENSPEC_ACTIVE_WORKFLOW`-Env-Var (Priorität 3) den aktiven Workflow bestimmt, sobald ihr Wert auf *irgendeine* existierende `workflows/<name>.json` zeigt. Da alle Workflow-JSONs im **geteilten** Hauptrepo-Verzeichnis (`{main_repo}/.claude/workflows/`) liegen, besteht der Wert einer *fremden* parallelen Session diese Prüfung und die fremde Workflow-Identität wird übernommen.

Folgen (beide real beobachtet):
- **False-Block:** Ein Gate (`tdd_enforcement.py`) blockiert legitime Schreibzugriffe der eigenen Session mit dem Phase-/Artefakt-Zustand eines fremden Workflows.
- **False-Pass-Risiko (symmetrisch):** Stünde der gekaperte fremde Workflow in einer durchwinkenden Phase, würde die abschließende Session fälschlich als grün behandelt.

Dieser Fix entfernt die eingefrorene Env-Var als Auflösungsquelle **im Worktree-Zweig** vollständig. Im Worktree zählen nur noch worktree-lokale Quellen. Der Kaper-Vektor verschwindet damit für bestehende *und* künftige Workflows, ohne neue Persistenz oder Migration.

## Source

- **File:** `core/hooks/hook_utils.py`
- **Identifier:** `resolve_active_workflow()` — der Worktree-Zweig (aktuell Zeilen ~291–315), speziell die Priorität-3-Env-Var-Auflösung (aktuell ~311–314)

## Root Cause

Im Worktree-Zweig von `resolve_active_workflow()`:

```python
# 3. Env var (frozen at session start) — only trusted if it points to a real workflow
name = os.environ.get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()
if name and _workflow_file_exists(root, name):
    return name, "env"
```

`_workflow_file_exists(root, name)` prüft `{root}/.claude/workflows/<name>.json`, wobei `root = find_project_root()` **den geteilten Hauptrepo** auflöst. Die Existenz-Prüfung unterscheidet also nicht zwischen dem eigenen und einem fremden Workflow — jeder gültige Workflow-Name aus einer beliebigen Session besteht sie.

Die eingefrorene Env-Var ist ein Startzeit-Schnappschuss der launchenden Session. In einem isolierten Worktree ist sie prinzipbedingt kein vertrauenswürdiges Signal für den *eigenen* aktiven Workflow: der dokumentierte Ablauf (`workflow.py start`) schreibt einen aktiven Workflow immer worktree-lokal (Prio 1 `active_workflow`-Datei, Prio 2 worktree-`settings.local.json`).

## Design-Entscheidung

**Gewählt:** Env-Var (Prio 3) im Worktree-Zweig komplett als Quelle entfernen. Sind Prio 1 (worktree `active_workflow`-Datei) und Prio 2 (worktree `settings.local.json` env) beide leer, liefert die Auflösung `("", "none")`.

**Begründung (verworfene Alternativen):**
- *Ownership-Feld (`worktree`-Pfad im Workflow-JSON) + Match-Prüfung:* Präziser, aber braucht neue Persistenz plus Sonderbehandlung aller bestehenden Workflows ohne das Feld — für die wäre „nicht vertrauen" ohnehin das sichere Verhalten, also faktisch identisch zu diesem Fix, bei mehr Code und Migrationsaufwand. Verworfen nach KISS/YAGNI.
- *Env nach `complete` neutralisieren:* Nicht zuverlässig — Hooks laufen als frische Subprozesse und erben die pro-Session eingefrorene Env; sie können sie nicht dauerhaft mutieren.

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/hook_utils.py` | MODIFY | Im Worktree-Zweig von `resolve_active_workflow()` die Priorität-3-Env-Var-Auflösung entfernen: nach leerem Prio 1 + Prio 2 direkt `("", "none")` zurückgeben. Docstring entsprechend anpassen (Prio 3 im Worktree entfällt; Begründung: Kaper-Schutz #58). Der Main-Repo-Zweig bleibt **unverändert** (Env dort weiterhin Prio 3). |
| `tests/test_workflow_resolution_consolidation.py` | MODIFY | Neue Regressionstests (siehe Test Plan). Bestehende Tests 1–4, 9 müssen grün bleiben. |

### Out of Scope

- Der Main-Repo-Zweig (Nicht-Worktree-Session): Env bleibt Prio 3, Rückwärtskompatibilität für Single-Session-Projekte.
- Das Kopieren von `settings.local.json` bei der Worktree-Erstellung (der ursprüngliche Auslöser im Issue-Titel). Diese Härtung ist orthogonal; der hier gewählte Fix macht die kopierte/eingefrorene Identität wirkungslos, unabhängig davon, wie sie in die Session kam.
- Keine Änderung an `_workflow_file_exists()`, `find_project_root()`, `_find_worktree_root()`.

## Expected Behavior

- **EB-1:** In einer Worktree-Session mit gesetzter, auf einen existierenden *fremden* Workflow zeigender `OPENSPEC_ACTIVE_WORKFLOW`-Env-Var, aber **ohne** worktree-lokale `active_workflow`-Datei und **ohne** passenden Eintrag in der worktree-`settings.local.json`, liefert `resolve_active_workflow()` `("", "none")` — der fremde Workflow wird **nicht** übernommen.
- **EB-2:** In einer Worktree-Session gewinnt weiterhin die worktree-lokale `active_workflow`-Datei (Prio 1), auch wenn die Env-Var auf einen anderen existierenden Workflow zeigt.
- **EB-3:** In einer Worktree-Session gewinnt die worktree-`settings.local.json`-Env-Section (Prio 2), wenn Prio 1 leer ist und der Name auf einen existierenden Workflow zeigt.
- **EB-4:** In einer **Main-Repo**-Session (kein Worktree) löst die `OPENSPEC_ACTIVE_WORKFLOW`-Env-Var weiterhin als Prio 3 auf (unverändert).
- **EB-5:** `read_active_workflow_fast()` liefert im EB-1-Szenario `None` (kein `sys.exit`), und `_read_active()` beendet mit `sys.exit(1)` („No active workflow"), da im Worktree nichts Legitimes auflösbar ist.

## Acceptance Criteria

- **AC-1:** Worktree-Session, Env zeigt auf existierenden fremden Workflow, keine Prio-1-Datei, keine Prio-2-Settings → `resolve_active_workflow()` gibt `("", "none")` zurück.
- **AC-2:** Worktree-Session, Prio-1-Datei zeigt auf Workflow A, Env zeigt auf existierenden Workflow B → Auflösung ergibt A (Quelle `file`).
- **AC-3:** Worktree-Session, keine Prio-1-Datei, Prio-2-Settings zeigt auf existierenden Workflow C, Env zeigt auf existierenden Workflow B → Auflösung ergibt C (Quelle `settings`).
- **AC-4:** Main-Repo-Session (kein Worktree), keine Datei/Settings, Env zeigt auf existierenden Workflow → Auflösung ergibt diesen Workflow (Quelle `env`). (Regressionsschutz Bestandsverhalten.)
- **AC-5:** Bestehende Tests in `tests/test_workflow_resolution_consolidation.py` (Test 1, 1b, 2, 2b, 3, 4, 9) bleiben grün. Hinweis: Test 2/2b nutzen `worktree=None` (Main-Repo) und bleiben gültig; kein Test darf für eine Worktree-Session eine Env-basierte Auflösung erwarten.
- **AC-6:** Die Rückgabe-Signatur bleibt `(name: str, source: str)` mit `source ∈ {"file","settings","env","none"}`; `read_active_workflow_fast()` bleibt `(name, data) | None`.

## Test Plan

Alle Tests in `tests/test_workflow_resolution_consolidation.py`, Stil wie bestehend (in-process, `_bind_context`-Mocks für `find_project_root`/`_find_worktree_root`/`_worktree_root_if_any`).

1. **test_5_worktree_ignores_foreign_env (AC-1, EB-1):** `worktree=tmp_path`, `_write_workflow(tmp_path, "foreign-wf")`, `OPENSPEC_ACTIVE_WORKFLOW=foreign-wf`, keine `active_workflow`-Datei, keine settings → `resolve_active_workflow()` == `("", "none")`.
2. **test_5b_worktree_foreign_env_fast_none (AC-1, EB-5):** gleiches Setup → `read_active_workflow_fast()` is None.
3. **test_5c_worktree_foreign_env_read_active_exits (EB-5):** gleiches Setup → `_read_active()` löst `SystemExit(1)` aus.
4. **test_6_worktree_file_beats_env (AC-2, EB-2):** `active_workflow`-Datei = "workflow-a", Env = "workflow-b" (beide JSONs existieren) → `("workflow-a", "file")`.
5. **test_7_worktree_settings_beats_env (AC-3, EB-3):** keine Datei, settings.local.json env = "workflow-c", Env = "workflow-b" (beide JSONs existieren) → `("workflow-c", "settings")`.
6. **test_8_mainrepo_env_still_resolves (AC-4, EB-4):** `worktree=None`, keine Datei/Settings, Env = "workflow-env" (existiert) → `("workflow-env", "env")`.
7. **Regression (AC-5):** Vollständiger Lauf der Datei — Tests 1, 1b, 2, 2b, 3, 4, 9 grün.

## Definition of Done

- [ ] RED: Neue Tests (1–6 oben) geschrieben, laufen zunächst rot bzw. decken die neue Erwartung ab (test_5* rot gegen den alten Code).
- [ ] GREEN: `resolve_active_workflow()`-Worktree-Zweig angepasst, alle neuen Tests grün.
- [ ] Regression: Gesamte `tests/test_workflow_resolution_consolidation.py` grün; keine anderen Testdateien gebrochen.
- [ ] CHANGELOG.md unter passender Version aktualisiert (Fix #58).
- [ ] Docstring von `resolve_active_workflow()` spiegelt das neue Worktree-Verhalten wider.
