# Kontext: feat-694-handoff-tab (Issue #694)

## Request Summary
`workflow.py handoff --start` (#667) startet die Folgesitzung per `pane split --direction right`
im eigenen Tab; mit jedem Issue stapeln sich Panes (Beleg 2026-11-26: Tab `w21:t1` mit 3 Claude-Panes
p1/p6/p8 + 3 Plan-Panes). Ziel: Folgesitzung in eigenem herdr-Tab „#N Kurztitel", Plan-Pane dort;
Rückfall auf Split, wenn `tab create` scheitert. Ergänzung (Henning): Die Nachfolgerin räumt die
Vorgängerin auf, sobald diese ihren Turn beendet hat (idle) und sauber mit ⏳ übergeben hat; bei ❗ bleibt
der Tab stehen; fail-open; Nachfolgerin nennt in der ersten Meldung das Ergebnis der Vorgängerin.

## Related Files
- `core/hooks/herdr_bridge.py:846` `start_session(prompt, cwd)` — heute `pane split` + `pane run exec claude`.
- `core/hooks/herdr_bridge.py` Plan-Pane-Runner (`_pp_*`), `run_plan_pane_close` (SessionEnd), Muster für
  detachten Runner (`open_plan_pane` → `herdr_bridge.py plan-pane …`), Log `.claude/herdr_plan_pane.log`.
- `core/hooks/workflow.py:5904` `handoff_prompt`, `:5977` `cmd_handoff` (ruft `start_session`).
- `core/hooks/session_banner.py:591-597` SessionStart: `report_active`, `open_plan_pane_for_active`.
- `core/commands/60-validate.md:277ff`, `core/commands/80-workflow.md:79ff` — Anweisungstexte zum Handoff.
- Tests: `tests/test_handoff_667.py` (Fake-herdr, AC-5 prüft heute `pane split`), `tests/test_handoff_668.py`.

## Herdr-API (real geprüft, 2026-11-26)
- `herdr tab create --workspace W --cwd P --label T --env K=V --no-focus` → JSON
  `result.tab.tab_id`, `result.root_pane.pane_id`. `--env` kommt im Prozess an (Probe `PROBE_694=1`).
- `herdr tab close <tab_id>` → `{"result":{"type":"ok"}}`; `pane split` kennt ebenfalls `--env`.
- `herdr pane get <id>` → `result.pane.{tab_id, agent, agent_status (working|idle|blocked|done|unknown)}`.
- `herdr pane list --workspace W` → Panes mit `tab_id`, Plan-Panes tragen Token `owner=<claude-pane>`.
- `herdr agent wait <pane> --until idle --until done --timeout <ms>`.
- `herdr pane read <id> --source recent-unwrapped --lines N` → Bildschirmtext; die Vorgängerin endet mit
  „⏳ Läuft noch: Claude startet #694 aus deinem Auftrag…" (real gelesen aus w21:p6).

## Existing Patterns
- Detachter Runner mit Lock + Log (Plan-Pane #476/#496), fail-open, nie stdout/stderr.
- Plan-Pane öffnet sich bei `workflow.py start` rechts vom Claude-Pane → im neuen Tab automatisch dort.
- Plan-Pane-Besitz: Token `owner` am Pane.

## Dependencies / Dependents
- #696 baut darauf auf (Übergabe am Phasenwechsel nutzt denselben Start + Aufräumen).
- Konsumenten-Projekte erhalten die Änderung über das Plugin.

## Risks
- Tab-Close beendet die Vorgänger-Sitzung hart: nur bei idle/done + ⏳ als letzte Endzustandsmarke.
- Der Starttab des Auftrags kann fremde Panes enthalten (Shell etc.): dann nicht den Tab, nur die Panes
  der Vorgängerin (Claude-Pane + eigene Plan-Panes) schließen.
- Nach Idle kurze Nachprüfung (Footer-Gate kann den Turn wieder aufnehmen).
- Fail-open überall; kein Herdr → nichts.

## Analysis

**Type:** Feature (Änderung an bestehendem Handoff #667). Kombinierter Durchgang Context+Analyse (Score 3).

### Affected Files
| Datei | Change | Grund |
|---|---|---|
| `core/hooks/herdr_bridge.py` | MODIFY | `start_session`: `tab create` (+`--env OPENSPEC_HANDOFF_PREV_PANE`), Rückfall `pane split` (+`--env`); neuer Runner `handoff-cleanup` + Starter `start_predecessor_cleanup()` |
| `core/hooks/workflow.py` | MODIFY | `cmd_handoff` reicht Tab-Label „#N Kurztitel" durch; `handoff_prompt` nennt Vorgänger-Issue für den Ein-Satz-Bericht |
| `core/hooks/session_banner.py` | MODIFY | SessionStart ruft `start_predecessor_cleanup()` (fail-open) |
| `core/commands/80-workflow.md`, `core/commands/60-validate.md` | MODIFY | Text „neuer Pane" → „neuer Tab" |
| `skills/*` | REGEN | `scripts/sync_skills.py` |
| `tests/test_handoff_667.py` | MODIFY | AC-5 erwartet jetzt `tab create` |
| `tests/test_handoff_tab_694.py` | CREATE | neue ACs |
| `CHANGELOG.md`, Versionsdateien | MODIFY | Release |

### Scope / Risk
~6 Dateien, ~200 LoC Code + Tests. Risiko hoch (Hook-Code, beendet Sitzungen) → Adversary 2 Runden.

### Technical Approach
1. `start_session(prompt, cwd, label)`: `tab create --workspace $HERDR_WORKSPACE_ID --cwd <cwd> --label <label>
   --env OPENSPEC_HANDOFF_PREV_PANE=<eigenes Pane> --no-focus` → `root_pane.pane_id` → `pane run <neu> "exec claude …"`.
   Scheitert `tab create` (Exit≠0, Zeitlimit, kein JSON/pane_id, eigenes Pane, kein Workspace) → bisheriger
   `pane split … --env …`. Scheitert `pane run` im neuen Tab → neuen Tab schließen, STARTED=no.
2. Label: `#M <Titel>` aus `.claude/issue_briefs.json` (Cache), sonst `#M`; auf 40 Zeichen gekappt, Steuerzeichen raus.
3. Aufräumen (Nachfolgerin): SessionStart startet detachten Runner nur bei gesetztem `OPENSPEC_HANDOFF_PREV_PANE`
   ≠ eigenes Pane. Runner: `agent wait <prev> --until idle --until done` (Frist 30 min) → 5 s Nachprüfung per
   `pane get` (weiter idle/done) → `pane read --source recent-unwrapped` → letzte Endzustandsmarke (⏳/✅/❗/‼️)
   muss ⏳ sein → Tab der Vorgängerin per `pane list`: enthält er nur die Vorgängerin + ihre Plan-Panes
   (Token `owner`) und nicht die Nachfolgerin → `tab close`, sonst nur diese Panes einzeln schließen.
   Sperre je Vorgänger-Pane, Log `.claude/herdr_plan_pane.log`, alles fail-open, Exit 0.
4. Startauftrag: zusätzlicher Satz „Nenne in deiner ersten Meldung in einem Satz das Ergebnis von #<alt>
   (Abschlusskommentar am Issue)".

### Dependencies
#696 nutzt `start_session` + Aufräumen wieder. Plan-Pane-Runner unverändert (öffnet sich im neuen Tab).

### Open Questions
Keine Produktfragen offen (Henning hat Aufräum-Regel entschieden). Technische Default-Entscheidung: Starttab mit
fremden Panes wird nicht geschlossen, nur die Panes der Vorgängerin.
