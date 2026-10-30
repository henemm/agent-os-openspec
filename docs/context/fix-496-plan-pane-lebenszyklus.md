# Kontext + Analyse: fix-496-plan-pane-lebenszyklus (Issue #496)

## Request Summary
PO (echtes Herdr): Workflow-Plan-Panes bleiben nach Sessionende stehen (Zombie, cwd "<pfad> (deleted)"), nach Update entstehen zwei, ohne aktiven Workflow stehen Panes mit abgeschlossenem Workflow, nach Update zeigt ein wiederverwendetes Pane alten Code. Zusatz-Vorfall: ein manueller Aufraeumbefehl ueber `pane list` OHNE `--workspace` hat Panes ALLER Sessions geschlossen → harte Anforderung: nie fremde Panes schliessen.

## Recherche am echten Herdr 0.9.5 headless + Claude Code 2.1.314 TUI + Plugin (BELEGT)
- Hook-Ereignisse: `/clear` → SessionEnd reason=`clear` + SessionStart source=`clear` (Pane-`agent` bleibt `claude`); `/exit`, Ctrl-C → SessionEnd reason=`prompt_input_exit`; kill TERM/HUP → `other`; `pane close <claude>` → `other`; `kill -9` → KEIN SessionEnd.
- SessionEnd-Hooks werden nach ~1,25 s abgebrochen ("Hook cancelled"); `herdr pane close <plan>` dauert 0,025–0,77 s → synchron als erster Schritt rechtzeitig. Popen mit start_new_session ueberlebt den Abbruch nicht; Doppel-Fork schon.
- Im Plan-Pane gesetzt: `HERDR_PANE_ID` (eigene ID), `HERDR_WORKSPACE_ID`, `HERDR_BIN_PATH`, `HERDR_SOCKET_PATH`.
- Endet der Prozess im Pane (`exec`-Watcher), schliesst Herdr das Pane selbst.
- `pane get <owner>`: fehlend → rc 1 `pane_not_found`; nach Claude-Ende `agent: None`; laufend `agent: "claude"`. Prototyp owner_watch: Watcher endet nach 3 Runden ohne Claude-Owner → Pane nach ~3 s weg (auch nach kill -9).
- `pane report-metadata <pane> --source user:openspec --token owner=… --token workflow=… --token version=…` (Pane-ID VOR den Optionen!) → in `pane list`/`pane get` als `tokens`; Tokens ueberleben Watcher-Neustart und /clear, werden aber nicht automatisch aktualisiert.
- `pane list --workspace W` → `.result.panes[]` mit `pane_id, workspace_id, cwd, label, agent_status, agent?, tokens?`. OHNE `--workspace` alle Workspaces (Vorfall!).
- Watcher-Neustart im laufenden exec-Pane nicht moeglich (`pane run` tippt nur in stdin) → bei Versionswechsel Pane schliessen und neu oeffnen (SessionStart laeuft schon mit neuem Code).
- Prototyp sweep.py am echten Herdr: Altlasten geschlossen, genau 1 Pane bei Workflow, 0 ohne, Versionswechsel → neu.

## Ursachen im Code (BELEGT)
- `core/hooks/herdr_bridge.py` `_pp_open`: findet bekanntes Pane per ID-Datei, aktualisiert nur cwd, alter Watcher laeuft weiter; nichts schliesst Panes; Altlasten anderer Formate/Orte werden nicht gefunden → zweites `split`.
- `open_plan_pane_for_active` (SessionStart via `core/hooks/session_banner.py`) oeffnet ohne Workflow nichts, schliesst aber auch nichts.
- Kein SessionEnd-Gegenstueck in `hooks/hooks.json`.
- `workflow.py` `_plan_watch`: keine Owner-Pruefung.

## Design (festgelegt)
1. SessionStart (jede source, auch clear) — Sweep NUR `pane list --workspace $HERDR_WORKSPACE_ID`, nur Panes mit `label=="Workflow"`:
   - schliessen: cwd endet auf " (deleted)"; kein `tokens.owner` (Altlast); Owner nicht in der Liste oder Owner ohne `agent=="claude"`; Owner == eigenes Pane UND (kein aktiver Workflow ODER `tokens.version` != eigene Plugin-Version ODER Duplikat).
   - NIE schliessen: Pane, dessen Owner ein ANDERES lebendes Claude-Pane ist.
   - danach: aktiver Workflow und kein eigenes Pane behalten → oeffnen (split/rename/report-metadata owner+workflow+version/run `exec … plan --watch --target <me>`); behaltenes Pane: `workflow`-Token nachziehen.
2. SessionEnd (neu in hooks.json): bei reason != "clear" eigenes Pane (label Workflow, tokens.owner == $HERDR_PANE_ID, im eigenen Workspace) synchron als erstes per `pane close` schliessen; fail-open, ohne schwere Imports.
3. Watcher `--target`: pro Runde (oder alle N) `pane get <target>`; 3 Runden in Folge rc≠0 oder agent≠claude → beenden (Pane schliesst sich selbst). Beenden, wenn eigene `workflow.py` fehlt.
4. ID-Datei aus #493 nicht mehr Quelle der Wahrheit (hoechstens Cache/entfernen).
5. Plugin-Version aus `.claude-plugin/plugin.json` (Plugin-Root relativ zu herdr_bridge.py).

## Abnahme
Echter E2E `scripts/e2e_plan_pane.sh` gegen Herdr 0.9.5 headless (Vorlage `scripts/e2e_auto_clear.sh`): a Start mit Workflow → 1 Pane mit Tokens; b `/exit` → 0 (b2 kill -9 → 0 nach ≤6 s); c Neustart im selben Pane → 1; d Altlasten (deleted cwd, fremder toter Owner, ohne Tokens) → nur eigenes bleibt; e ohne Workflow → 0; f `/clear` → dasselbe Pane, derselbe Watcher; g Versions-Token alt → neues Pane; h ZWEI Claude-Sessions (gleicher und anderer Workspace) mit je Workflow → Start/Exit der einen laesst das Pane der anderen unberuehrt.
