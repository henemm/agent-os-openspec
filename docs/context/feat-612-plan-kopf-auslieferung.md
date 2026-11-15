# Kontext: feat-612-plan-kopf-auslieferung (Issue #612)

## Aufgabe

Plan-Pane (Herdr, `workflow.py plan --watch`): (1) Kopf zeigt nur sechs Wörter des Issue-Titels, keine Kurzfassung des Issues; (2) ab `phase8_complete` steht „✔ 8 Fertig / ✅ Erledigt“, obwohl Commit, Push, PR, CI und Merge noch laufen.

## Relevante Dateien

- `core/hooks/workflow.py`
  - Plan: `PLAN_STEPS`, `render_plan`, `_plan_lines`, `_plan_deploy_line`, `_wrap_plan_tail`, `_plan_watch`, `cmd_plan`
  - Issue-Titel (#490/#492): `short_title` (6 Wörter), `_issue_titles_file`, `cached_issue_title`, `_store_issue_title` (Sperre `herdr_bridge._pp_flock`), `fetch_issue_title` (`gh api … --jq .title`), `_spawn_issue_title_fetch` (aus `cmd_start`), `_with_issue_title`, `_plan_fetch_missing`, `cmd_issue_title`
  - Endzustand (#550/#555/#551/#589): `END_DONE`, `END_WAITING`, `END_YOU`, `_end_state_final`, `_end_state_open`, `end_state`, `queue_end_args`, `cmd_endstate`, `cmd_waiting`
  - Deploy-Marker (#510): `DEPLOY_STATUS_VALUES`, `_deploy_status_target`, `_status_target`, `_split_note_arg`, `cmd_deploy_status`, `_reset_approvals_on_backstep`
  - Phasenwechsel: `cmd_phase` (`record_transition`, `_save_active`), `cmd_complete` (setzt `phase8_complete` direkt, archiviert, `_herdr("clear")`)
- `core/hooks/herdr_bridge.py`: `STEP_LABELS` (ohne phase8 → Clear), `build_report` (Token `state` aus `end_state(data, **queue_end_args(data))`), `report_workflow`, `clear`
- `scripts/ship.py`: `main()` — Branch, Push, PR, `wait_ci`, Merge; Ausgabe `BRANCH= PR= CI= MERGED=`
- `core/commands/60-validate.md`: Step 4 `phase phase8_complete`, danach Auto-Modus-Liste (Commit, Push, Ausliefern), „Abschluss: Endzustand melden“
- `core/commands/00-intake.md`: Schritte 1, 1b (claim), 1a (queue), 3 (start)
- Tests: `tests/test_plan_issue_titel_490.py`, `test_endzustand_550.py`, `test_plan_deploy_status_510.py`, `test_nacharbeit_555.py`, `test_herdr_plan_pane_476.py`

## Bestehende Muster

- Marker-Muster `deploy_status/deploy_at/deploy_note` + CLI `deploy-status <wert> [<N|name>] [--note]` + Plan-Zeile + `end_state`-Fall (#510/#550/#561).
- Caches unter `.claude/` als JSON, Schreiben unter `_pp_flock`, fail-open, Log `.claude/issue_titles.log`.
- `end_state` ist pure und die einzige Quelle für Chat-Fußzeile, Plan-Schluss und Seitenleisten-Token `state`; Config-Werte (Deploy-Modus, Autonomie) liefern die Aufrufer bzw. `queue_end_args`.
- Tests: Stub-`gh` in `<case>/bin`, `CLAUDE_PROJECT_DIR`, Workflow-JSON direkt in `.claude/workflows/`.

## Dependencies / Dependents

- `render_plan` wird von `cmd_plan`, `_plan_watch` und Tests (#476/#478/#490/#510/#550) aufgerufen; Kopfzeilen 1–3 sind in Tests gepinnt (`["Workflow #490", name, "Kurzer Titel", ""]`).
- `end_state` von `cmd_endstate`, `render_plan`, `herdr_bridge.build_report`, `footer_gate` (über `expected_footer_command`, unverändert).
- `fetch_issue_title`/Cache von `start`, Watcher, `issue-title`; Test #490 pinnt `issue-title` auf die Sechs-Wort-Form (anzupassen).

## Risiken

- Wortlaut-Pins in Bestandstests (Kopfzeilen, Schlusszeilen, „8 Fertig“); Altbestand im Archiv ohne Marker darf nicht ⏳ werden.
- `complete` archiviert vor Push/CI: `ship-status` ohne Nummer braucht einen Archiv-Rückfall.
- `gh api` ohne `--jq` liefert JSON; Stubs liefern Text — beides lesen.

## Analysis

- **Art:** Feature (Anzeige), zwei Teile, kein Gate.
- **Betroffene Dateien / Change-Type:** `workflow.py` (modify, größter Teil), `herdr_bridge.py` (modify, klein), `scripts/ship.py` (modify), `60-validate.md`/`00-intake.md`/Skills (modify), Tests (add/modify), Changelog/Versionen (modify).
- **Scope/Risiko:** mittel; Risiko liegt in Wortlaut-Pins und Rückwärtskompatibilität des Archivs. Mitigation: Schritt „Ausliefern“ ab Phase 8 nur mit Marker; Kopfblock nur mit Kurzfassung.
- **Technischer Ansatz:** Kurzfassung deterministisch aus dem Issue-Text (pure Funktion, Cache, manuelle Übersteuerung per CLI); Auslieferung als Marker nach dem Deploy-Muster, von `ship.py` automatisch gesetzt, `end_state` entscheidet vor dem Deploy; Auto-Modus-Flag über `queue_end_args`.
- **Verworfen:** `waiting_on` automatisch bei `git push`/`gh pr` setzen (PreToolUse) — kein sauberer Zeitpunkt zum Löschen; Phase 8 erst nach dem Merge setzen — bricht Commit-Gates und `complete`-Pfad.
- **Offene Fragen:** keine; PO hat „Override mit Spec“ gewählt.
