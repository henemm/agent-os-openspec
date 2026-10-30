---
entity_id: fix-493-plan-pane-doppelt
type: bugfix
created: 2026-10-30
updated: 2026-10-30
status: draft
version: "1.0"
workflow: fix-493-plan-pane-doppelt
tags: [herdr, workflow, plan, pane, worktree]
---

# Plan-Pane nach Claude-Neustart im selben Herdr-Pane wiederverwenden (Issue #493)

## Approval

- [ ] Approved

## Purpose

Beendet der PO Claude Code und startet es im selben Herdr-Pane neu, bleibt der Plan-Pane (#476) offen, und beim naechsten Workflow-Start oeffnet sich ein zweiter. Ursache: Die gemerkte Pane-ID liegt im `.claude/` des Worktrees der Session, jede neue Session hat einen neuen Worktree, also keine bekannte ID. Kuenftig liegt die ID im Haupt-Repo und ist je Claude-Pane abgelegt; der vorhandene Plan-Pane wird wiederverwendet und zeigt den Workflow der neuen Session.

## Source

- **File:** `core/hooks/herdr_bridge.py` (Runner), `core/hooks/workflow.py` (Watcher)
- **Identifier:** `_pp_open`, `_pp_known_pane`, `run_plan_pane`, `PP_ID_FILE`, `PP_LOCK_FILE`; `_plan_watch`, `cmd_plan`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/herdr_bridge.py` (#476/#478) | module | `_pp_open`, `run_plan_pane`, `open_plan_pane`, `_ac_base()`, `_ac_log` |
| `core/hooks/workflow.py` (#476/#490) | module | `_plan_watch`, `cmd_plan`, `_plan_active`, `read_active_workflow_fast` |
| `core/hooks/hook_utils.py` | module | `find_project_root()` (loest aus dem Worktree zum Haupt-Repo auf), `read_state_json`, `atomic_write_json`, `resolve_active_workflow` (cwd-abhaengig) |
| Herdr-CLI (0.9.5) | extern | `pane get`, `pane split`, `pane rename`, `pane run`; kein belegter `pane close` (wird nicht verwendet) |
| `HERDR_PANE_ID` | Umgebung | bleibt beim Neustart von Claude im selben Pane gleich; Schluessel des Eintrags |
| `tests/test_herdr_plan_pane_476.py` | test infra | Stub-Herdr-Binary, Hilfsfunktionen als Vorbild |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | MODIFY | ID-Datei und Lock ins Haupt-Repo; Eintraege je Claude-Pane mit `pane_id` und `cwd`; Wiederverwendung setzt `cwd` neu; `pane run` mit `--target` |
| core/hooks/workflow.py | MODIFY | Nur Watcher/`cmd_plan`: `--target <pane>` lesen, je Runde in die eingetragene Basis wechseln |
| tests/test_herdr_plan_pane_reuse_493.py | CREATE | Zwei Worktrees, ein Split; Ablageort; mehrere Claude-Panes; `pane get` schlaegt fehl; Watcher wechselt cwd; Fail-open |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 3 geaendert
- LoC: +60 Produktion / +200 Test
- Risk Level: LOW bis MEDIUM (Herdr-Layout; ausserhalb von Herdr No-op; jeder Fehler fuehrt zum bisherigen Verhalten)

## Implementation Details

**Ablageort.** `.claude/herdr_plan_pane.json` und `.claude/herdr_plan_pane.lock` liegen unter `find_project_root()` (Haupt-Repo), nicht mehr unter `_ac_base()`. So sehen alle Worktrees dieselbe Datei, und zwei Worktrees splitten nicht parallel. Das Log `herdr_plan_pane.log` bleibt unveraendert unter `_ac_base()`.

**Inhalt der ID-Datei.** `{"panes": {"<HERDR_PANE_ID der Claude-Session>": {"pane_id": "<plan-pane>", "cwd": "<basis>"}}}`. Schreiben atomar (`atomic_write_json`); beim Schreiben werden die Eintraege anderer Claude-Panes erhalten. Das alte Format `{"pane_id": ...}` wird nicht als Treffer gelesen (siehe Known Limitations).

**Runner (`_pp_open`).**

1. Eintrag fuer `args.pane` lesen. Ist er vorhanden und `pane get <pane_id>` endet mit Exit 0: kein Split; `cwd` im Eintrag auf `args.cwd` setzen (atomar, andere Eintraege erhalten), Log `vorhanden`, Ende.
2. Sonst `pane split` wie bisher, `pane rename`, Wartezeit, dann `pane run <neu> "exec <python> <workflow.py> plan --watch --target <claude_pane>"` (alles `shlex.quote`). Danach den Eintrag fuer `args.pane` mit `{"pane_id": <neu>, "cwd": args.cwd}` setzen bzw. ersetzen, auch wenn `pane run` scheitert.
3. Lock-Pfad wie oben im Haupt-Repo; Alter-Regel (30 s) unveraendert.

**Watcher (`plan --watch --target <P>`).** `cmd_plan`/`_plan_watch` lesen `--target`. Je Runde, vor dem Aufloesen des aktiven Workflows: Eintrag `<P>` aus `find_project_root()/.claude/herdr_plan_pane.json` lesen; ist `cwd` ein existierender Ordner und weicht er vom aktuellen Arbeitsverzeichnis ab, `os.chdir(cwd)`. Jeder Fehler (Datei fehlt oder kaputt, Eintrag fehlt, Ordner existiert nicht, `chdir` scheitert) wird geschluckt, der Watcher arbeitet mit dem aktuellen Arbeitsverzeichnis weiter. Ohne `--target` ist das Verhalten unveraendert; bereits laufende alte Watcher kennen `--target` nicht und bleiben unberuehrt.

**Fail-open.** Alles Exit 0, keine Ausgabe auf stdout/stderr ausserhalb des Plans, keine Verzoegerung des Sitzungsstarts (Runner laeuft weiterhin detached).

## Expected Behavior

- **Input:** Claude startet im selben Herdr-Pane erneut (anderer Worktree), `workflow.py start` oder SessionStart mit aktivem Workflow
- **Output:** Kein zweiter Pane; der vorhandene Plan-Pane zeigt innerhalb einer Sekunde den Workflow der neuen Session
- **Side effects:** `.claude/herdr_plan_pane.json` und `.claude/herdr_plan_pane.lock` im Haupt-Repo; Eintrag-`cwd` folgt der jeweils letzten Session dieses Claude-Panes

## Known Limitations

- Das alte Format `{"pane_id": ...}` wird nicht mehr als Treffer genutzt; beim ersten Start nach dem Update kann einmalig ein neuer Plan-Pane gesplittet werden (der alte bleibt offen und zeigt weiter den Plan seines Worktrees, bis er von Hand geschlossen wird).
- Es gibt kein `pane close` (in Herdr 0.9.5 nicht belegt). Dass der Plan-Pane beim Beenden von Claude offen bleibt, ist gewollt: er wird beim Neustart wiederverwendet.
- Laufen zwei Claude-Sessions parallel im selben Pane-Eintrag (nicht moeglich, ausser nach Neustart), gewinnt die zuletzt gestartete.
- Alte Watcher ohne `--target` (vor diesem Fix gestartet) wechseln nie die Basis.
- Echtes Herdr-Verhalten ist nur im realen Herdr pruefbar; die Tests nutzen ein Stub-Binary.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] In einem echten Herdr: Claude beenden und im selben Pane neu starten oeffnet keinen zweiten Plan-Pane, und der vorhandene zeigt den neuen Workflow (manuelle Abnahme durch den PO)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen, insbesondere #476-/#478-/#490-Tests)

## Acceptance Criteria

- **AC-1:** Given zwei Worktrees desselben Projekts und derselbe `--pane` / When der Runner nacheinander mit `--cwd` des ersten und des zweiten Worktrees laeuft / Then protokolliert der Stub genau ein `pane split`, und der Eintrag fuer den Pane enthaelt danach `cwd` des zweiten Worktrees
  - Test: tests/test_herdr_plan_pane_reuse_493.py::test_second_run_reuses_pane_and_updates_cwd

- **AC-2:** Given ein Runner-Lauf aus einem Worktree / When er fertig ist / Then liegen `herdr_plan_pane.json` (und waehrend des Laufs der Lock) im `.claude/` des Haupt-Repos und nicht im `.claude/` des Worktrees
  - Test: tests/test_herdr_plan_pane_reuse_493.py::test_id_file_lives_in_main_repo

- **AC-3:** Given zwei verschiedene Claude-Panes (`--pane A`, `--pane B`) / When der Runner fuer beide laeuft / Then gibt es zwei `pane split`, und die Datei enthaelt beide Eintraege mit je eigener `pane_id`; ein erneuter Lauf fuer A veraendert den Eintrag von B nicht
  - Test: tests/test_herdr_plan_pane_reuse_493.py::test_distinct_claude_panes_keep_own_entries

- **AC-4:** Given ein Eintrag fuer `--pane`, bei dem `pane get` mit Exit ≠ 0 endet / When der Runner laeuft / Then folgt ein neues `pane split`, und der Eintrag enthaelt die neue `pane_id`
  - Test: tests/test_herdr_plan_pane_reuse_493.py::test_dead_pane_is_replaced

- **AC-5:** Given ein frischer Split / When `pane run` abgesetzt wird / Then enthaelt der Befehl `plan --watch --target <claude_pane>` mit der `--pane`-ID
  - Test: tests/test_herdr_plan_pane_reuse_493.py::test_pane_run_passes_target

- **AC-6:** Given Datei-Eintrag `<P>` mit `cwd` = Projektbasis X (aktiver Workflow `wf-x`) und ein Watcher, der aus Basis Y (aktiver Workflow `wf-y`) startet / When `plan --watch --target <P>` mit `OPENSPEC_PLAN_WATCH_ROUNDS` laeuft / Then zeigt die Ausgabe den Workflow `wf-x`, nicht `wf-y`
  - Test: tests/test_herdr_plan_pane_reuse_493.py::test_watcher_switches_to_registered_base

- **AC-7:** Given eine fehlende oder kaputte ID-Datei, ein fehlender Eintrag fuer `<P>` oder ein nicht existierendes `cwd` / When `plan --watch --target <P>` laeuft / Then endet der Watcher mit Exit 0 und zeigt wie bisher den Workflow des aktuellen Arbeitsverzeichnisses
  - Test: tests/test_herdr_plan_pane_reuse_493.py::test_watcher_fail_open

- **AC-8:** Given ein Stub-Herdr und die bestehenden Tests / When `pytest tests/test_herdr_plan_pane_476.py tests/test_herdr_plan_deploy_sessionstart_478.py` laeuft / Then sind sie weiterhin gruen (ggf. mit angepasstem Ablageort der ID-Datei, ohne Verhaltensaenderung)
  - Test: tests/test_herdr_plan_pane_476.py, tests/test_herdr_plan_deploy_sessionstart_478.py (Regressionslauf)

## Test Plan

Runner synchron per `herdr_bridge.py plan-pane --delay 0` mit verzweigendem Stub-Binary (`HERDR_BIN_PATH`, Muster `tests/test_herdr_plan_pane_476.py`), das argv protokolliert und je Unterbefehl Exit-Code und JSON steuert. Zwei Worktrees entstehen per `git worktree add` in einem isolierten Projekt (`CLAUDE_PROJECT_DIR`); der Watcher laeuft per Subprozess mit `OPENSPEC_PLAN_WATCH_ROUNDS` und Intervall 0.

- `pytest tests/test_herdr_plan_pane_reuse_493.py`
- Regressionslauf: `pytest tests/` (insbesondere #476, #478, #490)
- Syntaxpruefung: `python3 -m py_compile core/hooks/workflow.py core/hooks/herdr_bridge.py`
- Manuell (nicht automatisierbar): Claude im echten Herdr-Pane beenden und neu starten

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Fehlerkorrektur im Herdr-Utility: verlegt eine Hilfsdatei ins Haupt-Repo und erweitert sie um einen Eintrag je Pane. Kein State-Format des Workflows, kein Gate, keine Hook-Registrierung betroffen; reversibel durch Loeschen der Datei.

## Changelog

- 2026-10-30: Initial spec created
