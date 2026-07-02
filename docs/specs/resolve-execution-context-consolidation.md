---
entity_id: resolve-execution-context-consolidation
type: bugfix
created: 2026-07-02
updated: 2026-07-02
status: draft
workflow: feat-resolve-execution-context
---

# Resolve Execution Context Consolidation

## Approval

- [ ] Approved

## Purpose

`core/hooks/workflow.py` löst den Namen des aktiven Workflows zweimal separat und
unvollständig auf (`_read_active()`-FATAL-Pfad und `read_active_workflow_fast()`),
statt die bereits korrekte, worktree-aware Priorität aus
`hook_utils.resolve_active_workflow()` zu verwenden. Dadurch ignoriert der
FATAL-Pfad die worktree-lokale `.claude/active_workflow`-Datei und stürzt live mit
`FATAL: OPENSPEC_ACTIVE_WORKFLOW=... ist gesetzt aber keine passende Workflow-Datei
existiert` ab, obwohl Datei und `settings.local.json` korrekt auf einen anderen,
gültigen Workflow zeigen (Issue #13). Zusätzlich sind 6 Tests, die diese
Auflösungsfunktionen direkt aufrufen, nicht hermetisch, weil sie nur
`hook_utils.find_project_root()` mocken, nicht `hook_utils._find_worktree_root()`
— sie lesen dadurch den echten Worktree-Zustand der laufenden Test-Session
(Issue #35). Diese Spec konsolidiert beide `workflow.py`-Funktionen auf
`hook_utils.resolve_active_workflow()` als einzige Quelle der Wahrheit und macht
die betroffenen Tests hermetisch.

## Source

- **File:** `core/hooks/workflow.py`
- **Identifier:** `def _read_active`, `def read_active_workflow_fast`
- **File:** `core/hooks/hook_utils.py`
- **Identifier:** `def resolve_active_workflow`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils.resolve_active_workflow()` | function | Einzige Quelle der Wahrheit für Workflow-Namens-Auflösung (Priorität: worktree-lokale Datei > worktree-lokale settings.local.json > Env-Var, jeweils mit Existenz-Validierung wo zutreffend) |
| `hook_utils._find_worktree_root()` | function | Bestimmt, ob CWD in einem Git-Worktree liegt — Grundlage der worktree-aware Priorität |
| `workflow._workflow_file(name)` | function | Prüft/liest die konkrete `workflows/<name>.json` nach erfolgter Namens-Auflösung |
| `tdd_enforcement.py`, `post_implementation_gate.py` | consumer | Rufen `read_active_workflow_fast()` auf — Verhalten muss nach Refactor unverändert bleiben |
| `bash_gate.py`, `edit_gate.py`, `qa_gate.py` | consumer | Rufen `_read_active()`-Kette indirekt via `workflow.py`-CLI-Subprozesse auf |

## Scope

### Affected Files
| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/workflow.py` | MODIFY | `_read_active()` FATAL-Pfad und `read_active_workflow_fast()` delegieren die Namensauflösung an `hook_utils.resolve_active_workflow()` statt eigener dupliziter Logik; Außenverhalten (FATAL-Meldung + `sys.exit(1)` bei nicht auflösbarem Workflow, `None`-Rückgabe bei `read_active_workflow_fast()`) bleibt identisch |
| `core/hooks/hook_utils.py` | MODIFY | Kleiner Doku-Kommentar an `resolve_active_workflow()`, der die Funktion explizit als einzige Quelle der Wahrheit für `workflow.py` kennzeichnet. Keine Logik-Änderung. |
| `tests/test_selfexplaining_gates.py` | MODIFY | 5 Tests (`test_ac4_resolve_from_env`, `test_ac4_resolve_none`, `test_ac7_get_active_workflow_name_returns_plain_string`, `test_ac1_diagnostics_no_active_workflow`, `test_ac2_diagnostics_with_phase`) ergänzen `monkeypatch.setattr(hook_utils, "_find_worktree_root", lambda: None)`, damit sie eine Main-Repo-Session simulieren statt den echten Worktree-Zustand zu lesen |
| `tests/test_workflow_name_validation.py` | MODIFY | `_run_bash_gate()`-Helper übergibt `cwd=str(tmp_path)` an `subprocess.run`, damit `_find_worktree_root()` im Subprozess innerhalb von `tmp_path` startet statt im echten Worktree-CWD der Testsession (behebt `test_ambiguous_without_override_blocks`) |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]` → `Fixed`: Konsolidierung der Workflow-Namens-Auflösung in `workflow.py` auf `hook_utils.resolve_active_workflow()`; Referenz auf Issue #13 und #35 |

### Estimated Changes
- Files: 5
- LoC: +45/-95 (netto Reduktion durch Wegfall der duplizierten Logik in `read_active_workflow_fast()` und im FATAL-Pfad von `_read_active()`; Testdateien: +6/-1 je Testfunktion)

## Implementation Details

### `_read_active()` — FATAL-Pfad delegiert an `resolve_active_workflow()`

Statt eigenständig Env-Var und `settings.local.json` zu lesen (bisherige Zeilen
164-200), ruft `_read_active()` `hook_utils.resolve_active_workflow()` auf. Der
zurückgegebene `name` wird wie bisher gegen die tatsächliche `workflows/<name>.json`
validiert — bleibt der Name unauflösbar (leerer String, `source == "none"`), greift
unverändert der bestehende `.active`-Symlink-Hinweis-Pfad und danach die generische
`"No active workflow"`-Meldung mit `sys.exit(1)`. Die Meldung für den Fall
"Name aufgelöst, aber `workflows/<name>.json` existiert nicht" wird generisch auf
alle drei möglichen Quellen (`file`/`settings`/`env`) formuliert, statt wie bisher
ausschließlich `OPENSPEC_ACTIVE_WORKFLOW` zu erwähnen — da der Name jetzt auch aus
der Datei oder aus `settings.local.json` stammen kann.

```python
def _read_active() -> tuple[dict, str]:
    from hook_utils import resolve_active_workflow
    name, source = resolve_active_workflow()
    if name:
        wf_file = _workflow_file(name)
        if wf_file.exists():
            data = _read_workflow(wf_file)
            return data, data.get("name", wf_file.stem)
        print(f"FATAL: Resolved active workflow '{name}' (source={source}) but no "
              f"matching workflow file exists.\n"
              f"  Run: python3 .claude/hooks/workflow.py list", file=sys.stderr)
        sys.exit(1)
    # ... unveränderter .active-Symlink-Hinweis + generische "No active workflow"-Meldung
```

### `read_active_workflow_fast()` — dünner Wrapper

Die komplette worktree-aware Prioritätslogik (bisherige Zeilen 230-284, ~55 Zeilen)
entfällt und wird durch einen Aufruf von `resolve_active_workflow()` ersetzt, gefolgt
von der bestehenden `workflows/<name>.json`-Existenzprüfung. Rückgabewert
(`(name, data)` oder `None`) bleibt unverändert.

### Keine Änderung an `hook_utils.py`-Logik

`resolve_active_workflow()` ist bereits korrekt (siehe `test_ac4_resolve_file_beats_env`,
der die Priorität Datei > Env korrekt verifiziert). Es wird lediglich ein
Doku-Kommentar ergänzt, der die Funktion als von `workflow.py` genutzte Quelle der
Wahrheit kennzeichnet.

### Kein neues CLI-Flag

Es wird bewusst **kein** `--workflow`-Flag zu `workflow.py` hinzugefügt. Die
Priorität "Datei schlägt Env" gilt ausnahmslos; es gibt in dieser Iteration keinen
Escape-Hatch.

## Test Plan

### Automated Tests (TDD RED)

- [ ] Test 1 (Live-Bug-Regression): GIVEN eine worktree-lokale `.claude/active_workflow`-Datei zeigt auf Workflow A und `OPENSPEC_ACTIVE_WORKFLOW` (Env) zeigt (veraltet) auf Workflow B, WHEN `workflow.py status` ohne inline gesetzte Env-Var im aktuellen Shell-Kontext läuft, THEN liefert der Befehl den Status von Workflow A und es tritt kein `FATAL`-Fehler auf.
- [ ] Test 2 (Env als dritte Priorität, kein Worktree): GIVEN kein Worktree, keine `.claude/active_workflow`-Datei, keine `settings.local.json`, aber eine gültige, existierende `OPENSPEC_ACTIVE_WORKFLOW`-Env-Var, WHEN `_read_active()` bzw. `read_active_workflow_fast()` aufgerufen wird, THEN wird der Workflow aus der Env-Var aufgelöst wie bisher (source == "env").
- [ ] Test 3 (Kein Workflow auflösbar): GIVEN weder Datei noch Env noch Settings verweisen auf einen existierenden Workflow, WHEN `_read_active()` aufgerufen wird, THEN wird weiterhin die generische `"No active workflow"`-Meldung ausgegeben und der Prozess beendet sich mit `sys.exit(1)`.
- [ ] Test 4 (`read_active_workflow_fast()` non-fatal): GIVEN kein Workflow auflösbar, WHEN `read_active_workflow_fast()` aufgerufen wird, THEN wird `None` zurückgegeben, ohne `sys.exit()` aufzurufen.
- [ ] Test 5 (Hermetik `test_ac4_resolve_from_env`): GIVEN `hook_utils._find_worktree_root` ist auf `lambda: None` gemockt und `OPENSPEC_ACTIVE_WORKFLOW=feature-x` gesetzt, WHEN `resolve_active_workflow()` aufgerufen wird, THEN liefert es `("feature-x", "env")` unabhängig vom Zustand des echten Worktrees der Testsession.
- [ ] Test 6 (Hermetik `test_ac4_resolve_none`): GIVEN `_find_worktree_root` gemockt auf `lambda: None` und keine Env-Var gesetzt, WHEN `resolve_active_workflow()` aufgerufen wird, THEN liefert es `("", "none")` unabhängig vom echten Worktree-Zustand.
- [ ] Test 7 (Hermetik `test_ac7_get_active_workflow_name_returns_plain_string`, `test_ac1_diagnostics_no_active_workflow`, `test_ac2_diagnostics_with_phase`): GIVEN `_find_worktree_root` jeweils passend gemockt, WHEN die jeweilige Funktion (`get_active_workflow_name()` / `gate_diagnostics()`) aufgerufen wird, THEN liefert sie das erwartete Ergebnis unabhängig vom echten Worktree-Zustand der Testsession.
- [ ] Test 8 (Hermetik `test_ambiguous_without_override_blocks`): GIVEN `_run_bash_gate()` startet `bash_gate.py` als Subprozess mit `cwd=str(tmp_path)` (statt dem echten Worktree-CWD) und einer synthetischen `test-wf.json` mit `adversary_verdict: "AMBIGUOUS"`, WHEN `git commit -m test` via Bash-Gate geprüft wird, THEN blockiert das Gate mit `"AMBIGUOUS"` in `stderr`, unabhängig davon, ob in der echten Session parallel ein anderer Workflow aktiv ist.
- [ ] Test 9 (Regressionsfreiheit): GIVEN volle Testsuite (`pytest tests/`), WHEN diese mit `env -u OPENSPEC_ACTIVE_WORKFLOW` UND temporär beiseite verschobener `.claude/active_workflow`-Datei (verschieben, nicht `git stash -u` — das nimmt die Datei versehentlich mit) als Baseline ausgeführt wird, THEN gibt es keine neuen Fehlschläge gegenüber dem Stand vor diesem Fix.

## Acceptance Criteria

- **AC-1**: GIVEN eine worktree-lokale `.claude/active_workflow`-Datei zeigt auf Workflow A und die (veraltete) `OPENSPEC_ACTIVE_WORKFLOW`-Env-Var zeigt auf Workflow B, WHEN ein beliebiger `workflow.py`-Befehl (`status`, `phase`, `set-field`, etc.) ausgeführt wird, THEN wird Workflow A verwendet und es tritt **kein** `FATAL`-Fehler auf.
- **AC-2**: GIVEN kein Worktree, keine Datei, keine `settings.local.json`, nur eine gültige, existierende `OPENSPEC_ACTIVE_WORKFLOW`-Env-Var, WHEN `workflow.py`-Befehle ausgeführt werden, THEN funktioniert die Auflösung unverändert wie vor diesem Fix (Env als dritte Priorität).
- **AC-3**: GIVEN weder Datei noch Env noch Settings verweisen auf einen existierenden Workflow, WHEN `workflow.py status` (oder ein anderer Befehl, der `_read_active()` nutzt) ausgeführt wird, THEN erscheint weiterhin eine `FATAL`/`"No active workflow"`-Fehlermeldung mit `sys.exit(1)` — das Verhalten für den "gar kein Workflow aktiv"-Fall ist unverändert.
- **AC-4**: GIVEN die 6 in dieser Spec benannten Tests (5 in `test_selfexplaining_gates.py`, 1 in `test_workflow_name_validation.py`), WHEN die Testsuite unabhängig vom Zustand der echten Session/des echten Worktrees ausgeführt wird (z. B. mit einem anderen aktiven Workflow im selben Worktree), THEN laufen alle 6 Tests deterministisch grün.
- **AC-5**: GIVEN die volle Testsuite vor diesem Fix als Baseline (`env -u OPENSPEC_ACTIVE_WORKFLOW`, `.claude/active_workflow` temporär verschoben), WHEN die Suite nach diesem Fix erneut ausgeführt wird, THEN gibt es keine neuen Fehlschläge (nur die vorher genannten Tests wechseln von rot zu grün, keine Regression bei zuvor grünen Tests).
- **AC-6**: GIVEN `read_active_workflow_fast()` wird von `tdd_enforcement.py` und `post_implementation_gate.py` aufgerufen, WHEN diese Hooks nach dem Refactor laufen, THEN bleibt die Rückgabe-Signatur (`(name, data)` oder `None`, kein `sys.exit()`) unverändert.

## Known Limitations

- Das settings.local.json-Overwrite-Verhalten der Claude-Code-Harness selbst
  (vermutete Mitursache von Issue #13 in manchen Fällen) wird durch diese Spec
  nicht behoben — das liegt außerhalb unserer Kontrolle und wird als gegeben
  behandelt.
- Issue #26 (bash_gate.py Rebase-Check nutzt `find_project_root()` statt
  Worktree-Branch) ist ein anderes Problem (Git-Branch-Vergleich, nicht
  Namens-Resolution) und wird hier explizit NICHT behoben.
- Issue #38 (edit_gate.py Datei-Ownership-Staleness über `affected_files`) ist ein
  anderes Problem (Lifecycle-/Match-Reihenfolge, nicht Resolution-Priorität) und
  wird hier explizit NICHT behoben.
- Issue #33 (`CLAUDE_PLUGIN_ROOT` / `installed_plugins.json` als robustere
  Plugin-Root-Quelle) wird hier NICHT umgesetzt — es gibt aktuell keinen
  Konsumenten von `find_plugin_root()`, der davon profitieren würde.
- Issue #28 ist vermutlich bereits durch den 3.4.15-Fix erledigt (Return-Code-Check
  in `qa_gate.py` existiert bereits) — nicht Teil dieser Arbeit. Der User kann das
  Issue nach eigener Verifikation schließen.
- Ein Versionsbump wird in dieser Spec bewusst nicht festgelegt — diese
  Entscheidung erfolgt erst nach dem Adversary-Verdikt.

## Changelog

- 2026-07-02: Initial spec created
- 2026-07-02: Scope-Korrektur während TDD-RED (per eigener Verifikation, nicht nur
  Agent-Aussage): Die ursprüngliche Recherche zu Issue #35 hatte nur 6 von
  tatsächlich 11 betroffenen Tests benannt. 5 weitere Tests mit identischem Root
  Cause (fehlender `_find_worktree_root`-Mock bzw. fehlendes `cwd=tmp_path` bei
  Subprozess-Tests) ergänzt: `test_ac4_resolve_broken_settings`,
  `test_ac4_resolve_null_env_settings`, `test_ac7_get_active_workflow_name_empty`,
  `test_ac1_e2e_no_workflow_block_has_diagnostics` (alle in
  `tests/test_selfexplaining_gates.py`, gleicher In-Process-Mock-Fix), sowie
  `tests/test_gate_coverage.py::test_phase6_edit_on_spec_without_ac_blocked`
  (neue betroffene Datei, gleicher Subprozess-`cwd`-Fix wie
  `test_ambiguous_without_override_blocks`). AC-4/AC-5 gelten jetzt für alle 11
  ursprünglich in Issue #35 genannten Tests, nicht nur 6.
