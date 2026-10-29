---
entity_id: feat-478-plan-deploy-sessionstart
type: feature
created: 2026-10-29
updated: 2026-10-29
status: draft
version: "1.0"
workflow: feat-478-plan-deploy-sessionstart
tags: [herdr, workflow, plan, deploy, session-start]
---

# Herdr-Plan-Pane: Deploy-Schritt und Öffnen beim Sitzungsstart (Issue #478)

## Approval

- [ ] Approved

## Purpose

Folge zu #476/#467. Viertens behebt es den Fehler, an dem Auto-`/clear` in echtem Herdr immer scheiterte: `agent wait` liefert den Status im Feld `.result.agent.agent_status` (Herdr 0.9.5, `AgentInfo` in `src/api/schema/agents.rs`), der Runner las `.result.agent.status` und brach mit „agent wait Ausgabe nicht parsbar“ ab (PO-Log 2026-10-29T11:24:09). Drittens schreibt Auto-`/clear` (#467) bei aktivem Opt-in jeden Grund, aus dem es an einem Turn-Ende NICHT ausloest, als Zeile in `.claude/herdr_auto_clear.log`, damit der PO sieht, warum nichts passiert. Erstens zeigt der Workflow-Plan bei Projekten mit beschriebenem Deploy nach Phase 8 einen eigenen Schritt „Deploy“ als offen und nennt `/70-deploy #N` als naechsten Befehl, statt „abgeschlossen“ zu melden, waehrend die Sitzung noch das Deploy verlangt. Zweitens oeffnet sich der Plan-Bereich auch beim Start von Claude Code (SessionStart, auch nach `/clear`), wenn ein Workflow aktiv ist.

## Source

- **File:** `core/hooks/workflow.py`, `core/hooks/herdr_bridge.py`, `core/hooks/session_banner.py`
- **Identifier:** `deploy_configured`, `render_plan` (neuer Parameter `deploy`), `_plan_active`/`_plan_watch`/`cmd_plan`; `open_plan_pane_for_active`; `session_banner.main`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/workflow.py` (#476, #81) | module | `render_plan`, `_deploy_steps`, `cmd_deploy_config`, `read_active_workflow_fast`, `expected_footer_command`, `issue_number` |
| `core/hooks/herdr_bridge.py` (#476) | module | `open_plan_pane(force=False)`, Runner `plan-pane` (prueft per `pane get`, ob der Pane schon offen ist) |
| `core/hooks/session_banner.py` | hook | SessionStart; ruft bereits fail-open `herdr_bridge.report_active()` |
| `core/hooks/config_loader.py` | module | `load_config()` fuer `deploy:` und `herdr.plan_pane` |
| Herdr-CLI (`$HERDR_BIN_PATH`) | extern | unveraendert gegenueber #476 |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `deploy_configured()`, `render_plan(data, archived=False, width=None, deploy=False)`, `plan`/`plan --watch` reichen `deploy_configured()` durch |
| core/hooks/herdr_bridge.py | MODIFY | `open_plan_pane_for_active() -> bool` |
| core/hooks/session_banner.py | MODIFY | Aufruf von `open_plan_pane_for_active()` nach `report_active()`, fail-open |
| core/hooks/herdr_bridge.py (#467-Teil) | MODIFY | `maybe_auto_clear` loggt Skip-Gruende, wenn Opt-in aktiv; `_wait_ready` liest `agent_status` |
| tests/test_herdr_auto_clear_467.py | MODIFY | Stub liefert das echte Herdr-Format (`agent_status`) statt des erfundenen `status` |
| tests/test_herdr_plan_deploy_sessionstart_478.py | CREATE | Renderer, CLI mit Deploy-Config, SessionStart mit Stub-Binary |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 4 geaendert
- LoC: +50 Produktion / +200 Test
- Risk Level: MEDIUM (SessionStart laeuft in jedem Projekt; nur fail-open Spawn, keine Ausgabe)

## Implementation Details

**Deploy-Signal.** `deploy_configured() -> bool` in `workflow.py`: wahr genau dann, wenn `load_config()["deploy"]` ein dict ist und `_deploy_steps(command)` sowie `_deploy_steps(verify)` beide nicht leer sind (dieselbe Regel wie `DEPLOY_CONFIGURED=yes` in `cmd_deploy_config`; die Bedingung wird in eine gemeinsame Hilfsfunktion gezogen, die beide nutzen). Jede Ausnahme → `False`.

**Renderer.** `render_plan(data, archived=False, width=None, deploy=False)` bleibt pure. Nur wenn `deploy` wahr ist, folgt nach dem letzten Schritt („8 Fertig“) eine Zeile fuer Deploy:

- Workflow in `phase8_complete`, nicht archiviert: `▶ Deploy  (offen)`; letzte Zeile `Nächster: /70-deploy #<N>` (ohne Issue-Nummer `/70-deploy`); kein `abgeschlossen`.
- archiviert (`archived=True`): `✔ Deploy`, letzte Zeile `abgeschlossen`.
- jede fruehere Phase: `○ Deploy`, sonst unveraendert.

Ohne `deploy` ist die Ausgabe byte-identisch zu #476. `next_step`/`expected_footer_command`/`status_note` bleiben unveraendert (footer_gate verlangt in Phase 8 nichts Neues).

**CLI.** `plan` und `plan --watch` rufen `render_plan(..., deploy=deploy_configured())`; in `--watch` je Runde neu ermittelt.

**Skip-Gruende Auto-`/clear`.** In `maybe_auto_clear` gilt: Ist Herdr-Env gueltig und `herdr.auto_clear.enabled is True`, schreibt jede danach greifende Abbruchbedingung eine Zeile `<zeitstempel> skip: <grund>` per `_ac_log` in `.claude/herdr_auto_clear.log` (Gruende: `stop_hook_active`, `kein Slash-Befehl als naechster Schritt (<wert>)`, `/clear als Befehl`, `Fusszeile nennt <erwartet> nicht`, `Marker fehlt oder Negativmarker`, `Workflow ohne Name/Phase`, `Once-Lock aktiv`, `Spawn fehlgeschlagen`). Ohne Opt-in oder ausserhalb Herdr wird nichts geschrieben. Gleiche Gruende in Folge werden nicht doppelt geloggt, wenn der letzte Logeintrag identisch ist (sonst laeuft das Log bei jedem Turn voll; Rotation wie bisher).

**Bugfix `agent wait`.** `_wait_ready` liest den Status aus `.result.agent.agent_status`; fehlt das Feld, wird ersatzweise `.result.agent.status` gelesen (aeltere/abweichende Ausgabe). Ist keines ein String, gilt wie bisher „Ausgabe nicht parsbar“. Der #467-Test-Stub wird auf das echte Format umgestellt (`{"result":{"agent":{"agent_status":"idle", ...}}}`), damit die Tests das reale Verhalten pruefen.

**Sitzungsstart.** `herdr_bridge.open_plan_pane_for_active() -> bool` (fail-open, nie stdout/stderr): ermittelt per `workflow.read_active_workflow_fast()` den aktiven Workflow; nur wenn einer existiert, `open_plan_pane()` (ohne `force`, also mit Kill-Switch `herdr.plan_pane.enabled` und Gate `_pane()`). `session_banner.main()` ruft sie nach `report_active()` in `try/except Exception` fuer jede SessionStart-Quelle. Ein schon offener Pane bleibt dank `pane get` im Runner der einzige.

## Expected Behavior

- **Input:** (a) `workflow.py plan [--watch]` in einem Projekt mit `deploy:`-Config (command + verify), Workflow in Phase 8; (b) Start von Claude Code in einem Herdr-Pane mit aktivem Workflow
- **Output:** (a) Plan mit `▶ Deploy  (offen)` und `Nächster: /70-deploy #N`; nach Archivierung `✔ Deploy` und `abgeschlossen`; (b) der Plan-Bereich geht rechts auf, falls er nicht schon offen ist
- **Side effects:** (b) ein detachter Runner pro Sitzungsstart; SessionStart-Ausgabe (stdout) unveraendert

## Known Limitations

- Projekte ohne `deploy:`-Config (command + verify) sehen keinen Deploy-Schritt, auch wenn sie per eigener `70-deploy.md` oder `CLAUDE.md` deployen.
- Der Deploy-Schritt wird erst mit der Archivierung (`finish`/`complete`) abgehakt; ein erledigtes Deploy ohne anschliessendes `finish` bleibt als offen stehen.
- Beim Sitzungsstart in einem zweiten Claude-Pane desselben Projekts wird kein zweiter Plan-Bereich geoeffnet, solange der erste existiert.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] In einem Projekt mit `deploy:`-Config zeigt der Plan nach Phase 8 Deploy als offen mit `/70-deploy #N`; beim Neustart von Claude Code in Herdr geht der Plan-Bereich wieder auf (manuelle Abnahme durch den PO)
- [ ] Ohne Deploy-Config, ohne Herdr oder ohne aktiven Workflow verhaelt sich alles wie in 4.1.0
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen, insbesondere #466/#467/#476-Tests)

## Acceptance Criteria

- **AC-1:** Given ein Workflow mit Issue-Nummer 478 in `phase8_complete` und `deploy=True` / When `render_plan` laeuft / Then folgt nach `✔ 8 Fertig` die Zeile `▶ Deploy  (offen)`, die letzte Zeile ist `Nächster: /70-deploy #478`, und `abgeschlossen` kommt nicht vor
  - Test: tests/test_herdr_plan_deploy_sessionstart_478.py::test_render_phase8_with_deploy_shows_open_deploy

- **AC-2:** Given derselbe Workflow mit `archived=True` und `deploy=True` / When `render_plan` laeuft / Then steht `✔ Deploy` nach `✔ 8 Fertig` und die letzte Zeile ist `abgeschlossen`; Given `phase5_tdd_red` und `deploy=True` / Then steht `○ Deploy` als letzter Schritt
  - Test: tests/test_herdr_plan_deploy_sessionstart_478.py::test_render_deploy_archived_and_early_phase

- **AC-3:** Given beliebige Daten und `deploy=False` (bzw. ohne den Parameter) / When `render_plan` laeuft / Then ist die Ausgabe identisch zu #476 (keine Deploy-Zeile; Phase 8 endet mit `abgeschlossen`)
  - Test: tests/test_herdr_plan_deploy_sessionstart_478.py::test_render_without_deploy_unchanged

- **AC-4:** Given ein Projekt mit `deploy: {command: "x", verify: "y"}` und aktivem Workflow in `phase8_complete` / When `workflow.py plan` laeuft / Then enthaelt die Ausgabe `▶ Deploy  (offen)` und `Nächster: /70-deploy #<N>`; Given nur `command` ohne `verify` bzw. keine `deploy:`-Config / Then keine Deploy-Zeile
  - Test: tests/test_herdr_plan_deploy_sessionstart_478.py::test_cli_plan_uses_deploy_config

- **AC-5:** Given ein Workflow in `phase8_complete` / When `next_step` und `expected_footer_command` aufgerufen werden / Then liefern sie weiterhin `None` (unveraendert gegenueber 4.1.0), auch mit `deploy:`-Config
  - Test: tests/test_herdr_plan_deploy_sessionstart_478.py::test_next_step_phase8_unchanged

- **AC-6:** Given gueltiges Herdr-Env (Stub-Binary), Default-Config und ein aktiver Workflow / When `session_banner.py` mit einem SessionStart-Payload (`source` startup bzw. clear) laeuft / Then protokolliert der Stub `pane split ... --direction right`, und die stdout von `session_banner.py` ist identisch mit der ohne Herdr-Env
  - Test: tests/test_herdr_plan_deploy_sessionstart_478.py::test_session_start_opens_pane_for_active_workflow

- **AC-8:** Given gueltiges Herdr-Env, `herdr.auto_clear.enabled: true` und ein Workflow in `phase8_complete` (kein Slash-Befehl als naechster Schritt) bzw. eine Antwort ohne Positivmarker / When `footer_gate.py` den Stop-Payload verarbeitet / Then steht in `.claude/herdr_auto_clear.log` eine `skip:`-Zeile mit dem jeweiligen Grund, es wird kein Runner gestartet, Exit-Code und stdout von footer_gate bleiben unveraendert; ohne Opt-in entsteht keine Log-Datei
  - Test: tests/test_herdr_plan_deploy_sessionstart_478.py::test_auto_clear_logs_skip_reason_only_when_enabled

- **AC-9:** Given ein Stub, dessen `agent wait` wie Herdr 0.9.5 `{"id":"cli:agent:wait","result":{"agent":{"terminal_id":"t1","agent_status":"idle","pane_id":"P","workspace_id":"w1","tab_id":"t","focused":true}}}` liefert / When der Auto-`/clear`-Runner laeuft / Then sendet er `agent prompt P /clear` und danach den Folgebefehl; liefert der Stub `agent_status: "blocked"`, bricht er ohne Prompt ab
  - Test: tests/test_herdr_plan_deploy_sessionstart_478.py::test_runner_reads_real_agent_status_field

- **AC-7:** Given gueltiges Herdr-Env, aber kein aktiver Workflow bzw. `herdr.plan_pane.enabled: false` / When `session_banner.py` laeuft / Then wird kein `pane split` protokolliert
  - Test: tests/test_herdr_plan_deploy_sessionstart_478.py::test_session_start_no_pane_without_workflow_or_disabled

## Test Plan

Renderer direkt importiert; CLI per Subprozess gegen `core/hooks/workflow.py` in einem isolierten Projekt mit `config.yaml`; SessionStart per Subprozess gegen `core/hooks/session_banner.py` mit Stub-Binary (Muster aus `tests/test_herdr_plan_pane_476.py`), Warten auf den detachten Runner mit kurzer Frist.

- `pytest tests/test_herdr_plan_deploy_sessionstart_478.py`
- Regressionslauf: `pytest tests/`
- Syntaxpruefung: `python3 -m py_compile core/hooks/workflow.py core/hooks/herdr_bridge.py core/hooks/session_banner.py`
- Manuell: PO-Abnahme in echtem Herdr

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Rein anzeigende Erweiterung von #476 plus ein weiterer fail-open Aufrufpunkt im bestehenden SessionStart-Hook; kein neues State-Feld, keine Gate-Logik, `next_step` bleibt unveraendert. Voll reversibel per `herdr.plan_pane.enabled: false` bzw. Entfernen der Aufrufstelle.

## Changelog

- 2026-10-29: Initial spec created
