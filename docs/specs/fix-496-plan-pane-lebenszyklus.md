---
entity_id: fix-496-plan-pane-lebenszyklus
type: bugfix
created: 2026-10-30
updated: 2026-10-30
status: draft
version: "1.0"
workflow: fix-496-plan-pane-lebenszyklus
tags: [herdr, plan-pane, lifecycle, session-end, sweep, watcher, e2e]
---

# Plan-Pane-Lebenszyklus: Zombies verhindern, Altlasten aufraeumen, nie fremde Panes schliessen (Issue #496)

## Approval

- [ ] Approved

## Purpose

Der Workflow-Plan-Pane (#476/#493) hat heute nur ein „Oeffnen“, aber keinen Lebenszyklus: nach Sessionende bleibt er als Zombie stehen (cwd „<pfad> (deleted)“), nach einem Update entstehen zwei, ohne aktiven Workflow stehen Panes mit abgeschlossenem Workflow, und ein wiederverwendetes Pane zeigt alten Code. Kuenftig besitzt jedes Plan-Pane ein Owner-Token (das Claude-Pane, dem es gehoert); der SessionStart raeumt im eigenen Workspace Altlasten ab, das SessionEnd schliesst das eigene Pane, und der Watcher beendet sich selbst, wenn sein Owner nicht mehr lebt. Harte Randbedingung nach einem realen Vorfall (ein Aufraeumbefehl ohne `--workspace` schloss Panes aller Sessions): es wird nie ein Pane geschlossen, dessen Owner ein anderes lebendes Claude-Pane ist, und nie ausserhalb des eigenen Workspace gesucht.

## Source

- **File:** `core/hooks/herdr_bridge.py` (Plan-Pane-Teil), `core/hooks/workflow.py` (Watcher), `core/hooks/session_banner.py` (Aufruf), `hooks/hooks.json` (SessionEnd)
- **Identifier:** `_pp_open`, `open_plan_pane`, `open_plan_pane_for_active`, `run_plan_pane`, `_pp_*`; `workflow._plan_watch`, `workflow._plan_follow_target`, `workflow.cmd_plan`; neu `_pp_sweep`, `run_plan_pane_close`, `plugin_version`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/herdr_bridge.py` (#466/#476/#478/#493) | module | Bestand: `_pane()`, `_binary()`, `_pp_call`, Pane-Lock je Claude-Pane, `PP_LABEL = "Workflow"`; wird um Sweep, Tokens und SessionEnd-Modus erweitert |
| `core/hooks/workflow.py` (#476/#490/#493) | module | `_plan_watch` bekommt Owner-Pruefung und Selbstbeendigung; `read_active_workflow_fast` entscheidet „aktiver Workflow“ |
| `core/hooks/session_banner.py` (#478) | module | Ruft beim SessionStart `open_plan_pane_for_active()`; der Aufruf bleibt, der Pfad dahinter wird zum Sweep + Oeffnen |
| `hooks/hooks.json` | config | Neuer SessionEnd-Eintrag (Pflicht: Hooks IMMER dort registrieren) |
| `.claude-plugin/plugin.json` | config | Quelle der Plugin-Version fuer das `version`-Token (relativ zu `herdr_bridge.py`) |
| Herdr 0.9.5 CLI | extern | `pane list --workspace`, `pane get`, `pane close`, `pane split/rename/run`, `pane report-metadata … --token`; Env `HERDR_PANE_ID`, `HERDR_WORKSPACE_ID`, `HERDR_BIN_PATH` |
| `tests/test_herdr_plan_pane_476.py`, `tests/test_herdr_plan_pane_reuse_493.py`, `tests/test_herdr_plan_deploy_sessionstart_478.py` | tests | Regression; Stub-Herdr-Helfer als Vorbild; ID-Datei-Annahmen werden angepasst |
| `scripts/e2e_auto_clear.sh` (#495/#497) | script | Vorlage fuer den echten E2E mit Herdr 0.9.5 headless und Claude-TUI |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | MODIFY | `plugin_version()`; `_pp_sweep` (nur `--workspace $HERDR_WORKSPACE_ID`, Regeln siehe Implementation Details); `_pp_open` oeffnet mit Tokens `owner/workflow/version`, zieht `workflow`-Token bei behaltenem Pane nach, nutzt die ID-Datei nicht mehr als Quelle der Wahrheit; `open_plan_pane_for_active` startet den Runner auch ohne Workflow (Sweep); neuer Modus `plan-pane-close` (SessionEnd, schlank, synchron) |
| core/hooks/workflow.py | MODIFY | `_plan_watch`: Owner-Pruefung (3 Runden in Folge → Ende), Ende bei fehlender eigener `workflow.py`; `_plan_follow_target` liest nur noch das cwd aus der ID-Datei (Cache) |
| core/hooks/session_banner.py | MODIFY (ggf.) | Nur falls der Aufruf angepasst werden muss; Verhalten bleibt „fire and forget“ |
| hooks/hooks.json | MODIFY | SessionEnd: `herdr_bridge.py plan-pane-close` als ERSTER Eintrag, `timeout` 2 |
| tests/test_plan_pane_lifecycle_496.py | CREATE | Tests zu AC-1 bis AC-12 mit Stub-Herdr |
| tests/test_herdr_plan_pane_476.py, tests/test_herdr_plan_pane_reuse_493.py | MODIFY | Nur dort, wo das Eintragsformat der ID-Datei oder die Wiederverwendung ueber die ID fest verdrahtet ist |
| scripts/e2e_plan_pane.sh | CREATE | Echter E2E gegen Herdr 0.9.5 headless, Szenarien a bis h (AC-13) |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] / Fixed (#496) |

### Estimated Changes

- Files: 2 neu, 6 geaendert (+ Anpassung 2 Bestandstests)
- LoC: +150 Produktion / +380 Test / +260 E2E-Skript
- Risk Level: HIGH (die Aenderung schliesst Panes; Fehlschliessen fremder Panes ist der Worst Case; dagegen: Workspace-Beschraenkung, Owner-Pruefung, fail-open, Tests mit zwei Sessions)

## Implementation Details

**Festgelegt durch die Recherche an echtem Herdr 0.9.5 und Claude Code 2.1.314 (Kontext-Dokument `docs/context/fix-496-plan-pane-lebenszyklus.md`):** SessionEnd feuert bei `/exit`, Ctrl-C (`prompt_input_exit`), TERM/HUP und `pane close` (`other`), bei `/clear` mit `reason=clear` (gefolgt von SessionStart `source=clear`), bei `kill -9` gar nicht. SessionEnd-Hooks werden nach ca. 1,25 s abgebrochen; `pane close` dauert 0,025–0,77 s. Endet der `exec`-Prozess im Plan-Pane, schliesst Herdr das Pane selbst.

**Pane-Identitaet per Tokens (statt ID-Datei).** Beim Oeffnen setzt der Runner nach `split` und `rename Workflow` per `pane report-metadata <pane> --source user:openspec --token owner=<claude-pane> --token workflow=<name> --token version=<plugin-version>` (Pane-ID vor den Optionen). Die Version kommt aus `.claude-plugin/plugin.json`, Plugin-Root relativ zu `herdr_bridge.py`; fehlt sie, gilt ein fester Ersatzwert, der nie mit einer echten Version uebereinstimmt (also im Zweifel „neu oeffnen“, nie „fremdes schliessen“). Die ID-Datei `herdr_plan_pane.json` (#493) ist nicht mehr Quelle der Wahrheit fuer „welches Pane gehoert wem“; sie bleibt nur als Cache fuer das cwd, dem der Watcher per `--target` folgt (`_plan_follow_target`), und ihr `pane_id`-Feld wird nicht mehr gelesen.

**Sweep beim SessionStart (jede source, auch `clear`).** `open_plan_pane_for_active` startet den detached Runner `plan-pane` kuenftig auch ohne aktiven Workflow (der Sitzungsstart wartet nicht darauf). Der Runner nimmt den Pane-Lock des eigenen Claude-Panes und fuehrt aus:

1. `pane list --workspace $HERDR_WORKSPACE_ID` — IMMER mit `--workspace`. Fehlt `HERDR_WORKSPACE_ID` oder scheitert der Aufruf, wird nichts geschlossen und kein Sweep durchgefuehrt. Betrachtet werden nur Panes mit `label == "Workflow"`.
2. Schliessen (`pane close`), wenn eine der Regeln zutrifft:
   - cwd endet auf „ (deleted)“;
   - kein `tokens.owner` (Altlast aus Formaten vor #496);
   - Owner steht nicht in der Liste (toter Owner);
   - Owner steht in der Liste, hat aber nicht `agent == "claude"`;
   - Owner ist das EIGENE Claude-Pane und (kein aktiver Workflow ODER `tokens.version` weicht von der eigenen Plugin-Version ab ODER es ist ein zweites Pane desselben Owners, Duplikat).
3. NIE schliessen: ein Pane, dessen Owner ein ANDERES lebendes Claude-Pane im selben Workspace ist. Panes anderer Workspaces tauchen in der Liste nicht auf und werden gar nicht betrachtet.
4. Danach: gibt es einen aktiven Workflow und kein eigenes Pane wurde behalten, wird geoeffnet (`split --direction right`, `rename`, `report-metadata` mit allen drei Tokens, `pane run "exec … workflow.py plan --watch --target <eigenes Pane>"`). Ein behaltenes eigenes Pane bekommt nur das `workflow`-Token nachgezogen (andere Tokens bleiben). Ein Watcher laesst sich im laufenden `exec`-Pane nicht neu starten; deshalb wird bei altem `version`-Token geschlossen und neu geoeffnet (der SessionStart laeuft schon mit dem neuen Code).

**SessionEnd (neu).** Ein schlanker Modus `herdr_bridge.py plan-pane-close` als erster SessionEnd-Hook. Er liest `reason` aus dem stdin-Payload. Bei `reason == "clear"` tut er nichts (das Pane bleibt, der SessionStart `source=clear` uebernimmt). Sonst: `pane list --workspace $HERDR_WORKSPACE_ID` und `pane close` fuer genau die Panes mit `label == "Workflow"` und `tokens.owner == $HERDR_PANE_ID`, synchron und als erster Schritt, damit es vor der Kappung bei ca. 1,25 s fertig ist. Keine schweren Imports (`config_loader`, `workflow` werden nicht geladen; Pruefung nur ueber Env und Binary). Jeder Fehler endet mit Exit 0 ohne Ausgabe.

**Watcher (`plan --watch --target`).** Pro Runde `pane get <target>`; liefert er dreimal in Folge einen Fehler (z. B. `pane_not_found`) oder `agent != "claude"`, beendet sich der Watcher (Herdr schliesst das Pane, weil der `exec`-Prozess endet). Der Zaehler setzt sich bei einer gesunden Runde zurueck. Ein Herdr-Aufruf, der gar nicht antwortet (Binary fehlt, Zeitlimit), zaehlt nicht als „Owner tot“ — im Zweifel weiterlaufen. Fehlt die eigene `workflow.py` (Plugin geloescht oder aktualisiert), beendet sich der Watcher ebenfalls.

**Klarstellung (Orchestrator-Entscheidung, Phase 6):** Die Regel „nie fremd lebend“ hat Vorrang vor allen Schliess-Regeln. Ein Pane, dessen `tokens.owner` ein ANDERES Pane mit `agent == "claude"` im eigenen Workspace ist, wird NIE geschlossen — auch dann nicht, wenn sein cwd auf „ (deleted)“ endet. Fuer Panes des eigenen Owners gilt die cwd-Regel weiter (schliessen und, bei aktivem Workflow, neu oeffnen). Schlaegt `pane list` fehl, wird nichts geschlossen; bei aktivem Workflow wird dann wie ohne behaltenes Pane geoeffnet (ein dabei entstehendes Duplikat raeumt der naechste Sweep ab).

**Nachtrag Adversary-Runde 1 (PO-Grundsatz: lieber ein ueberzaehliges Pane stehen lassen als je ein Pane einer lebenden Session schliessen).**
- *Agent-Panes nie (F001):* Ein Pane mit gesetztem `agent` (jeder Agent, nicht nur `claude`) ist nie Kandidat — weder im Sweep noch im SessionEnd —, egal welches Label es traegt.
- *Erst Owner, dann Label (F002):* `_pp_spawn_watcher` setzt nach `split` ZUERST `report-metadata` (owner/workflow/version) und erst DANN `rename Workflow`, danach `run`. Ein Pane mit Label „Workflow“ hat damit immer schon seinen Owner; ohne Label betrachtet es kein Sweep. Scheitert `report-metadata`, schliesst der Runner sein eben gesplittetes Pane wieder und bricht ab (kein ownerloses Pane mit Label).
- *Guertel fuer ownerlose Panes (F002):* Herdr 0.9.5 liefert in `pane list`/`pane get` weder Alter noch Startzeit (geprueft: Felder `agent_status, cwd, focused, foreground_cwd, pane_id, revision, scroll, tab_id, terminal_id, workspace_id`). Deshalb ohne Zustandsdatei: ein Pane, das nur nach der Regel „kein `tokens.owner`“ zu schliessen waere, wird nicht sofort geschlossen; der Runner liest nach 2 s (`PP_ORPHAN_GRACE_S`) `pane list --workspace` erneut und schliesst nur, was dann immer noch Label „Workflow“, kein Agent und kein `owner`-Token hat. Ein gerade entstehendes Pane einer anderen Session bekommt in dieser Zeit seinen Owner (oder ist wieder weg). Scheitert der zweite Blick, bleibt das Pane stehen. Kosten: 2 s im detached Runner, nur wenn ownerlose Panes existieren.
- *Eigenes Pane muss gelistet sein (F003):* Steht `$HERDR_PANE_ID` nicht in `pane list --workspace $HERDR_WORKSPACE_ID` (Env veraltet, z. B. nach `pane move`), wird nichts geschlossen und nichts geoeffnet.
- *Altbestand laufender Sessions (F004):* Ein ownerloses Plan-Pane, das in der #493-ID-Datei (`<haupt-repo>/.claude/herdr_plan_pane.json`, `{"panes": {"<claude>": {"pane_id": …}}}`) einem ANDEREN Claude-Pane zugeordnet ist, das lebt (`agent == "claude"` in der Liste), bleibt stehen. Ist dieser Owner tot, gilt die Altlast-Regel.

**Nachtrag Adversary-Runde 2 (gleicher PO-Grundsatz).**
- *Verschachtelte Claude-Session (F001):* Ein Kind-Claude (`claude -p` aus dem Bash-Werkzeug oder einem Skript einer lebenden Session) erbt `HERDR_PANE_ID` und sah deshalb das Plan-Pane der Eltern als eigenes. Erkennung, belegt am echten Herdr 0.9.5 mit echter TUI und echtem `claude -p` (`docs/artifacts/fix-496-plan-pane-lebenszyklus/nested-detection.txt`): `CLAUDE_PID` (setzt Claude Code fuer Hooks und Werkzeuge auf den eigenen Prozess) muss unter den `foreground_processes` von `pane process-info --pane $HERDR_PANE_ID` stehen; das ist nur bei der Session der Fall, die das Pane im Vordergrund haelt. Gilt im Runner (vor Sweep, Oeffnen, Token- und cwd-Cache-Nachziehen) und in `plan-pane-close` (nur wenn es ueberhaupt ein eigenes Pane zu schliessen gibt, Zeitlimit 0,3 s). Fehlt `CLAUDE_PID`, scheitert `process-info` oder ist die Antwort unlesbar: nichts tun. Verworfen, weil am Beleg unzuverlaessig: `CLAUDE_CODE_ENTRYPOINT` (geerbter Wert bleibt teils stehen), TTY von stdin (bei beiden kein TTY), Hook-Felder, `session_id` (in einer Umgebung erbte das Kind die der Eltern), claude-Vorfahr im Prozessbaum (Herdr selbst kann unter einem claude-Prozess laufen).
- *Rename scheitert (F002):* Scheitert `rename Workflow` nach erfolgreichem `report-metadata`, schliesst der Runner das eben gesplittete Pane und bricht ab (kein Watcher). Zusaetzlich zaehlt ein Nicht-Agent-Pane ohne Label als Kandidat, wenn es die Tokens `owner == $HERDR_PANE_ID`, `workflow` und `version` traegt (nur `_pp_spawn_watcher` setzt diese Kombination; Herdr fuehrt die Token-Quelle in `pane list` nicht mit): Sweep und `plan-pane-close` behandeln es wie ein eigenes Plan-Pane; ein behaltenes bekommt das Label nachgezogen.
- *Split liefert das eigene Pane (F003):* Ist die `pane_id` aus der `split`-Antwort gleich `$HERDR_PANE_ID`, bricht der Runner ab, ohne dieses Pane anzufassen.

**Fail-open ueberall.** Herdr fehlt, `HERDR_*` nicht gesetzt, `pane list`/`close` schlaegt fehl, JSON unlesbar, Zeitlimit: es wird nichts geschlossen, Exit 0, keine Ausgabe auf stdout/stderr, der Sitzungsstart ist nicht verzoegert (der Sweep laeuft im detached Runner, nicht im Hook-Prozess).

## Expected Behavior

- **Input:** SessionStart (alle sources) und SessionEnd einer Claude-Session in einem Herdr-Pane; Plan-Pane-Opt-out `herdr.plan_pane.enabled: false` schaltet Sweep und Oeffnen weiterhin ab
- **Output:** Pro Claude-Session mit aktivem Workflow genau ein Plan-Pane mit Tokens; ohne Workflow keines; nach Sessionende keines
- **Side effects:** `pane close` auf eigene bzw. verwaiste Plan-Panes im eigenen Workspace; `report-metadata` auf dem Plan-Pane; Log in `herdr_plan_pane.log`

## Known Limitations

- Nach `kill -9` der Claude-Session feuert kein SessionEnd; das Plan-Pane lebt, bis der Watcher den toten Owner nach drei Runden bemerkt (ca. 3 s bei 1-s-Intervall, im E2E bis 6 s toleriert).
- Der SessionEnd-Hook wird nach ca. 1,25 s abgebrochen. Gelingt `pane close` in dieser Zeit nicht (Herdr haengt), bleibt das Aufraeumen dem Watcher bzw. dem naechsten Sweep ueberlassen.
- Mehrere Claude-Panes mit demselben Owner-Token gibt es nicht; ein Nicht-Agent-Pane ohne `owner`-Token wird nach dem zweiten Blick (2 s) als Altlast geschlossen, auch wenn es von Hand mit dem Label „Workflow“ benannt wurde — ausser die #493-ID-Datei ordnet es einem lebenden anderen Claude-Pane zu. Agent-Panes (auch ein Claude-Pane namens „Workflow“) werden nie geschlossen.
- Ein Plan-Pane einer aelteren Plugin-Fassung ohne Tokens, das in KEINER ID-Datei steht, wird geschlossen; die betroffene Session oeffnet erst beim naechsten eigenen SessionStart neu.
- Wer eine laufende Session per `pane move` in einen anderen Workspace verschiebt, bekommt bis zum Neustart der Session weder Sweep noch neues Plan-Pane (die Env zeigt noch auf das alte Pane).
- Ohne `CLAUDE_PID` in der Hook-Umgebung (aeltere Claude-Code-Fassungen) oder ohne `pane process-info` (aeltere Herdr-Fassungen) oeffnet und schliesst der Plan-Pane-Lebenszyklus nichts mehr; der Watcher endet weiter mit seinem Owner.
- Eine verschachtelte Kind-Session bekommt kein eigenes Plan-Pane und raeumt nichts auf; ein Claude, das nicht Vordergrundprozess seines Panes ist (z. B. hinter einem eigenen Terminal-Multiplexer im Pane), ebenso.
- Der Sweep sieht nur den eigenen Workspace. Zombies in anderen Workspaces raeumt erst eine Session dieses Workspace auf; das ist gewollt (kein Eingriff in fremde Workspaces).
- Das `version`-Token wird nicht automatisch aktualisiert; nach einem Plugin-Update wird deshalb bewusst geschlossen und neu geoeffnet.
- Echtes TUI- und Hook-Verhalten ist nur im realen Herdr pruefbar; die Unit-Tests nutzen ein Stub-Binary.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt (AC-13 durch das E2E-Skript)
- [ ] Der E2E `scripts/e2e_plan_pane.sh` laeuft mit allen Szenarien a bis h gegen ein echtes Herdr 0.9.5 gruen und der Beleg (Log, `pane list`-Auszuege) liegt vor
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen, insbesondere #476-/#478-/#490-/#493-Tests)

## Acceptance Criteria

- **AC-1:** Given ein Workspace mit Panes (Label „Workflow“) in den Zustaenden: cwd endet auf „ (deleted)“; ohne `tokens.owner`; Owner nicht in der Liste; Owner ohne `agent == "claude"`; eigener Owner ohne aktiven Workflow; eigener Owner mit abweichendem `version`-Token; zweites Pane desselben eigenen Owners / When der Sweep beim SessionStart laeuft / Then wird jedes dieser Panes per `pane close` geschlossen
  - Test: tests/test_plan_pane_lifecycle_496.py::test_sweep_closes_each_stale_rule

- **AC-2:** Given ein Plan-Pane im selben Workspace, dessen Owner ein ANDERES lebendes Claude-Pane (`agent == "claude"`) ist, auch mit anderem Workflow und anderer Version / When der Sweep laeuft / Then wird dieses Pane NICHT geschlossen und nicht veraendert
  - Test: tests/test_plan_pane_lifecycle_496.py::test_sweep_never_closes_foreign_living_owner

- **AC-3:** Given Panes in einem anderen Workspace / When der Sweep laeuft / Then lautet jeder `pane list`-Aufruf `pane list --workspace $HERDR_WORKSPACE_ID`, kein `pane close` trifft ein Pane des anderen Workspace; fehlt `HERDR_WORKSPACE_ID`, wird gar nichts geschlossen
  - Test: tests/test_plan_pane_lifecycle_496.py::test_sweep_is_workspace_scoped

- **AC-4:** Given ein aktiver Workflow und kein eigenes Pane / When der Runner oeffnet / Then entsteht genau ein Pane mit Label „Workflow“ und den Tokens `owner=<eigenes Pane>`, `workflow=<Name>`, `version=<Version aus plugin.json>`, und der Watcher wird mit `--target <eigenes Pane>` gestartet; bei einem behaltenen eigenen Pane mit anderem `workflow`-Token wird nur dieses Token nachgezogen und nicht neu geoeffnet
  - Test: tests/test_plan_pane_lifecycle_496.py::test_open_sets_tokens_and_reuses_with_token_refresh

- **AC-5:** Given ein Plan-Pane mit `owner == $HERDR_PANE_ID` / When SessionEnd mit `reason` ungleich `clear` (z. B. `prompt_input_exit`, `other`) feuert / Then wird genau dieses Pane synchron geschlossen und kein Pane eines anderen Owners
  - Test: tests/test_plan_pane_lifecycle_496.py::test_session_end_closes_only_own_pane

- **AC-6:** Given dasselbe Plan-Pane / When SessionEnd mit `reason == "clear"` feuert / Then bleibt das Pane stehen, und der folgende SessionStart (`source=clear`) behaelt es (selbes Pane, kein zweites)
  - Test: tests/test_plan_pane_lifecycle_496.py::test_session_end_clear_keeps_pane

- **AC-7:** Given ein Watcher mit `--target`, dessen Owner dreimal in Folge `pane get` mit Fehler beantwortet oder `agent != "claude"` hat / When der Watcher laeuft / Then beendet er sich nach der dritten Runde; bei einer gesunden Zwischenrunde setzt sich der Zaehler zurueck; fehlt das Herdr-Binary ganz, laeuft er weiter
  - Test: tests/test_plan_pane_lifecycle_496.py::test_watcher_exits_after_three_dead_owner_rounds

- **AC-8:** Given ein laufender Watcher / When die eigene `workflow.py` nicht mehr existiert / Then beendet sich der Watcher
  - Test: tests/test_plan_pane_lifecycle_496.py::test_watcher_exits_when_workflow_py_missing

- **AC-9:** Given Herdr fehlt, `HERDR_*` ist nicht gesetzt, `pane list` liefert Fehler oder kaputtes JSON, oder `pane close` schlaegt fehl / When Sweep bzw. SessionEnd laufen / Then wird nichts geschlossen, der Exit-Code ist 0 und es gibt keine Ausgabe auf stdout/stderr
  - Test: tests/test_plan_pane_lifecycle_496.py::test_fail_open_everywhere

- **AC-10:** Given der SessionStart-Hook / When er Sweep und Oeffnen anstoesst (auch bei haengendem Herdr) / Then kehrt `session_banner.py` ohne Wartezeit auf Herdr zurueck (Sweep im detached Runner); `plan-pane-close` importiert weder `config_loader` noch `workflow` und beendet sich bei haengendem `pane close` per Zeitlimit unter der Hook-Kappung
  - Test: tests/test_plan_pane_lifecycle_496.py::test_session_start_not_delayed_and_close_is_lightweight

- **AC-11:** Given `hooks/hooks.json` / When sie geladen wird / Then steht unter `SessionEnd` als erster Eintrag ein Kommando auf `herdr_bridge.py plan-pane-close` mit `${CLAUDE_PLUGIN_ROOT}`-Pfad und `timeout` von hoechstens 2 Sekunden
  - Test: tests/test_plan_pane_lifecycle_496.py::test_hooks_json_registers_session_end_close_first

- **AC-12:** Given die bestehenden Tests / When `pytest tests/test_herdr_plan_pane_476.py tests/test_herdr_plan_pane_reuse_493.py tests/test_herdr_plan_deploy_sessionstart_478.py` laufen / Then sind sie gruen (angepasst nur dort, wo das ID-Datei-Format oder die Wiederverwendung ueber die ID fest verdrahtet ist; das cwd-Folgen des Watchers per `--target` (#493) bleibt erhalten)
  - Test: Regressionslauf `pytest tests/`

- **AC-13:** Given echtes Herdr 0.9.5 headless, Claude-TUI und dieses Repo als Plugin / When `scripts/e2e_plan_pane.sh` laeuft / Then sind alle Szenarien gruen: (a) Start mit Workflow → genau 1 Plan-Pane mit Tokens owner/workflow/version; (b) `/exit` → 0 Panes, (b2) `kill -9` → 0 Panes nach hoechstens 6 s; (c) Neustart im selben Pane → genau 1; (d) Altlasten (cwd „(deleted)“, fremder toter Owner, ohne Tokens) → nur das eigene bleibt; (e) ohne Workflow → 0; (f) `/clear` → dasselbe Pane, derselbe Watcher; (g) altes `version`-Token → neues Pane; (h) ZWEI Claude-Sessions (gleicher und anderer Workspace) mit je Workflow → Start und Exit der einen laesst das Pane der anderen unberuehrt
  - Test: scripts/e2e_plan_pane.sh

## Test Plan

Muster `tests/test_herdr_plan_pane_reuse_493.py`: isoliertes Projekt, Stub-Herdr (`HERDR_BIN_PATH`, `HERDR_ENV=1`, `HERDR_PANE_ID`, `HERDR_WORKSPACE_ID`), das `pane list/get/close/split/rename/run/report-metadata` aus einer JSON-Welt beantwortet und alle Aufrufe protokolliert; Runner, `plan-pane-close` und Watcher per Subprozess bzw. mit `OPENSPEC_PLAN_WATCH_ROUNDS`/`_INTERVAL`.

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN eine Stub-Welt mit je einem Pane pro Regel (deleted cwd, ohne Owner, toter Owner, Owner ohne claude, eigener ohne Workflow, eigener mit alter Version, Duplikat) WHEN der Runner laeuft THEN wird jedes per `pane close` geschlossen und das Protokoll nennt nur diese Pane-IDs
- [ ] Test 2: GIVEN ein Plan-Pane mit lebendem fremdem Claude-Owner im selben Workspace WHEN der Runner laeuft THEN fehlt jedes `pane close` und `report-metadata` fuer dieses Pane
- [ ] Test 3: GIVEN Panes in zwei Workspaces WHEN der Runner laeuft THEN enthaelt jeder `pane list`-Aufruf `--workspace <eigener>`, und ohne `HERDR_WORKSPACE_ID` gibt es kein `pane close`
- [ ] Test 4: GIVEN aktiver Workflow, kein eigenes Pane WHEN der Runner laeuft THEN je ein `split`, `rename Workflow`, `report-metadata` mit owner/workflow/version und `pane run … plan --watch --target <eigenes Pane>`; GIVEN eigenes Pane mit altem `workflow`-Token THEN nur `report-metadata … --token workflow=` und kein `split`
- [ ] Test 5: GIVEN `plan-pane-close` mit Payload `reason: prompt_input_exit` und eigenem plus fremdem Plan-Pane WHEN er laeuft THEN nur das eigene wird geschlossen; mit `reason: clear` keines
- [ ] Test 6: GIVEN Watcher mit `--target` und Stub, der dreimal `pane_not_found` bzw. `agent: null` liefert WHEN er laeuft THEN endet er nach Runde 3; mit gesunder Runde dazwischen laeuft er weiter; ohne Binary laeuft er weiter
- [ ] Test 7: GIVEN ein Watcher mit entfernter `workflow.py` (Kopie in temporaerem Ordner) WHEN er laeuft THEN endet er
- [ ] Test 8: GIVEN Herdr fehlt, kaputtes JSON, `pane list` bzw. `pane close` mit Exit 1 WHEN Sweep und `plan-pane-close` laufen THEN Exit 0, keine Ausgabe, kein Close
- [ ] Test 9: GIVEN haengendes Stub-Herdr (Sleep) WHEN `session_banner.py` bzw. `plan-pane-close` laufen THEN kehrt der Banner sofort zurueck, und `plan-pane-close` endet innerhalb des Zeitlimits ohne `config_loader`/`workflow` zu importieren
- [ ] Test 10: GIVEN `hooks/hooks.json` WHEN gelesen THEN ist `plan-pane-close` erster SessionEnd-Eintrag mit `timeout <= 2`
- [ ] Test 11 (R2 F001, `test_nested_child_session_leaves_panes_alone`): GIVEN ein Plan-Pane der Eltern und `CLAUDE_PID` ungleich dem Vordergrund von `$HERDR_PANE_ID` WHEN Runner (ohne, mit anderem, mit gleichem Workflow) bzw. `plan-pane-close` laufen THEN kein `close`/`split`/`rename`/`report-metadata`/`run`, cwd-Cache unveraendert; ohne `CLAUDE_PID` bzw. bei Fehler/kaputtem `process-info` ebenso; Kontrolle mit Eltern-PID schliesst
- [ ] Test 12 (R2 F002, `test_rename_failure_closes_fresh_pane`): GIVEN `rename` scheitert WHEN der Runner oeffnet THEN wird das neue Pane geschlossen, kein `run`; GIVEN drei eigene Panes ohne Label mit owner/workflow/version THEN bleibt genau eines, kein `split`, SessionEnd schliesst es; ohne `version`-Token oder mit fremdem Owner unberuehrt
- [ ] Test 13 (R2 F003, `test_abort_never_closes_owner_pane`): GIVEN `split` liefert `$HERDR_PANE_ID` WHEN der Runner laeuft (mit/ohne Fehler bei `report-metadata`/`rename`) THEN kein Aufruf veraendert das eigene Claude-Pane

Weitere Laeufe:

- `pytest tests/test_plan_pane_lifecycle_496.py`
- Regressionslauf: `pytest tests/` (insbesondere #476, #478, #490, #493)
- Syntaxpruefung: `python3 -m py_compile core/hooks/herdr_bridge.py core/hooks/workflow.py core/hooks/session_banner.py`
- E2E: `bash scripts/e2e_plan_pane.sh` (Vorlage `scripts/e2e_auto_clear.sh`; `HERDR_E2E_BIN`, `KEEP=1`, `ONLY="a b …"`)

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Fehlerkorrektur am bestehenden Plan-Pane (#476/#493): Besitz wird nicht mehr in einer lokalen ID-Datei, sondern als Token am Pane selbst gefuehrt, das Herdr beim Auflisten zurueckgibt (zustandslos, ueberlebt Watcher-Neustart und `/clear`). Der Sweep sitzt im bestehenden Runner, das SessionEnd-Gegenstueck ist ein Modus der bestehenden Datei `herdr_bridge.py` und nur deshalb ein eigener Hook-Eintrag, weil SessionEnd ein eigenes Event ist (in `hooks/hooks.json` registriert). Kein neues Gate, kein Breaking Change am Workflow-State; Sicherheit vor Vollstaendigkeit: im Zweifel wird nichts geschlossen (fail-open, Workspace-Beschraenkung, Owner-Regel).

## Changelog

- 2026-10-30: Initial spec created
- 2026-10-30: Nachtrag Adversary-Runde 2 (F001 verschachtelte Session, F002 Rename-Fehler, F003 split == eigenes Pane) in Implementation Details, Known Limitations, Test Plan; E2E-Szenario l
