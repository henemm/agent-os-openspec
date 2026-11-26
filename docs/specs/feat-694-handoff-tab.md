---
entity_id: feat-694-handoff-tab
type: feature
created: 2026-11-26
updated: 2026-11-26
status: draft
version: "1.0"
workflow: feat-694-handoff-tab
tags: [auftrag, workflow, herdr, handoff, tab, aufraeumen, epic-649]
---

# Übergabe an neue Sitzung: eigener Tab statt Pane, Nachfolgerin räumt auf (Issue #694)

## Approval

- [ ] Approved

## Purpose

Die lokale Übergabe (`workflow.py handoff --start`, #667) startet die Folgesitzung per `pane split` rechts neben der alten; mit jedem Issue eines Auftrags stapeln sich Claude- und Plan-Panes im selben Tab (Beleg 2026-11-26: Tab `w21:t1` mit drei Claude- und drei Plan-Panes). Neu: Jede Folgesitzung läuft in einem eigenen Herdr-Tab „#N Kurztitel", und sobald die Vorgängerin sauber übergeben hat (Turn beendet, Endzustand ⏳), schließt die Nachfolgerin deren Tab. Ziel: immer nur ein Arbeits-Tab je Auftrag, ohne dass laufende oder gescheiterte Arbeit angetastet wird.

## Source

- **File:** `core/hooks/herdr_bridge.py`, `core/hooks/workflow.py`, `core/hooks/session_banner.py`, `core/commands/80-workflow.md`, `core/commands/60-validate.md`
- **Identifier:** `herdr_bridge.start_session`, `herdr_bridge.start_predecessor_cleanup` (neu), Runner `herdr_bridge.py handoff-cleanup` (neu), `workflow.cmd_handoff`, `workflow.handoff_prompt`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `herdr_bridge.start_session` (#667) | function | wird von Split auf Tab umgestellt, Rückfall bleibt der Split |
| `herdr_bridge._pane`, `_binary`, `_pp_call` | function | Pane-Erkennung, Binary, fail-open-Aufruf mit Timeout |
| `herdr_bridge.open_plan_pane` / Plan-Pane-Runner (#476, #496) | function | Muster für detachten Runner mit Sperre und Log; Plan-Pane öffnet sich im neuen Tab von selbst, Runner bleibt unverändert |
| `session_banner.py` SessionStart (`report_active`, `open_plan_pane_for_active`) | hook | ruft zusätzlich `start_predecessor_cleanup()` auf |
| `.claude/issue_briefs.json` | cache | Issue-Titel für das Tab-Label; fehlt er, nur „#M" |
| `workflow.handoff_prompt`, `workflow.cmd_handoff` | function | Startauftrag und Aufruf von `start_session` |
| Herdr-CLI `tab create`, `tab close`, `pane run`, `pane split`, `pane get`, `pane list`, `pane read`, `agent wait` | tool | real geprüft am 2026-11-26 (siehe docs/context/feat-694-handoff-tab.md) |
| Env `HERDR_WORKSPACE_ID`, `HERDR_PANE_ID`, `HERDR_BIN_PATH` | env | Ziel-Workspace, eigenes Pane, Binary |
| `scripts/sync_skills.py`, `scripts/sync_cloud_agents.py` | tool | Generat nach Befehlstext-Änderung neu erzeugen |
| docs/specs/feat-667-fresh-session.md, tests/test_handoff_668.py | spec/test | Vorarbeit; AC-5 aus #667 ändert sich |
| Issue #694, #696, Epic #649 | issue | Auftrag; #696 (Übergabe am Phasenwechsel) baut auf Start und Aufräumen auf |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | MODIFY | `start_session(prompt, cwd, label)`: `tab create` mit Rückfall `pane split`; neuer Runner `handoff-cleanup`, Starter `start_predecessor_cleanup()` |
| core/hooks/workflow.py | MODIFY | `cmd_handoff` baut das Label „#M Titel" und reicht es durch; `handoff_prompt` bekommt den Satz mit der Vorgänger-Issue-Nummer |
| core/hooks/session_banner.py | MODIFY | SessionStart ruft `start_predecessor_cleanup()` (fail-open) |
| core/commands/80-workflow.md, core/commands/60-validate.md | MODIFY | Text „neuer Pane" wird „neuer Tab" |
| skills/*/SKILL.md, .claude/agents | REGENERATE | `python3 scripts/sync_skills.py`, `python3 scripts/sync_cloud_agents.py` |
| tests/test_handoff_tab_694.py | CREATE | Tests zu den ACs (Fake-herdr-Binary wie in test_handoff_667.py) |
| tests/test_handoff_667.py | MODIFY | AC-5-Test erwartet `tab create` statt `pane split` als Primärweg |
| CHANGELOG.md, .claude-plugin/plugin.json, CLAUDE.md (Versionszeile), README.md | MODIFY | Eintrag und Version |

Nicht geändert: `config.yaml` und jede wirksame Gate-Config (autarker Auftrag, Konstanten im Code), Plan-Pane-Runner, Cloud-Weg, `hooks/hooks.json`, `end_state`/`footer_gate.py`.

### Estimated Changes

- Files: 3 Hooks, 2 Befehle, 2 Testdateien, 4 Doku-/Versionsdateien, Generat
- LoC: ca. +330/-25 (Code ca. 200, Tests ca. 130)
- Risk Level: HIGH (Hook-Code in allen Konsumenten; das Aufräumen beendet Sitzungen) — Adversary mit zwei Runden

### Out of Scope

- #696 (Übergabe am Phasenwechsel): nutzt später denselben Start und dasselbe Aufräumen
- Cloud-Weg (`create_session`): unverändert
- Plan-Pane-Runner: unverändert; er öffnet sich beim `workflow.py start` der Folgesitzung rechts von deren Claude-Pane und damit im neuen Tab
- Config-Schlüssel für Tab/Aufräumen: bewusst keiner

## Implementation Details

Konstanten (im Code, nicht in der Config): Warte-Frist 30 Minuten, Nachprüfung 5 Sekunden, Label-Länge 40 Zeichen, Endzustandsmarken ⏳ ✅ ❗ ‼️.

1. **Start im eigenen Tab.** `start_session(prompt, cwd, label) -> (bool, reason)` ruft zuerst `tab create --workspace $HERDR_WORKSPACE_ID --cwd <cwd> --label <label> --env OPENSPEC_HANDOFF_PREV_PANE=<eigenes Pane> --no-focus`. Aus der JSON-Antwort kommen `result.tab.tab_id` und `result.root_pane.pane_id`; danach `pane run <neues Pane> "exec claude <shlex-quoted prompt>"`. Tab-Fehlschlag (Exit ungleich 0, Zeitlimit, kein JSON oder keine `pane_id`, `pane_id` gleich dem eigenen Pane, fehlendes `HERDR_WORKSPACE_ID`) führt zum bisherigen `pane split <eigenes Pane> --direction right --cwd <cwd> --no-focus`, jetzt ebenfalls mit `--env OPENSPEC_HANDOFF_PREV_PANE=<eigenes Pane>`. Scheitert `pane run` im neuen Tab, wird dieser Tab per `tab close <tab_id>` wieder geschlossen und das Ergebnis ist `STARTED=no` mit `REASON`. Nie ist das eigene Pane Ziel von `pane run` oder `tab close`.
2. **Label.** `#M <Titel>` aus dem Cache `.claude/issue_briefs.json`; ohne Cache-Eintrag nur `#M`. Steuerzeichen werden entfernt, Leerraum zusammengezogen, Gesamtlänge höchstens 40 Zeichen.
3. **Aufräum-Runner der Nachfolgerin.** SessionStart (`session_banner.py`) ruft `start_predecessor_cleanup()`. Der Starter tut nur dann etwas, wenn `OPENSPEC_HANDOFF_PREV_PANE` gesetzt und ungleich dem eigenen Pane ist; er startet dann detacht `herdr_bridge.py handoff-cleanup <prev-pane>` (Muster `open_plan_pane`), ohne zu warten und ohne stdout/stderr. Der Runner:
   1. Sperre je Vorgänger-Pane (zweiter Lauf beendet sich still).
   2. `agent wait <prev> --until idle --until done --timeout <30 min>`; Zeitablauf, `blocked` oder Fehler beenden den Runner ohne Aktion.
   3. Nach 5 Sekunden Nachprüfung per `pane get <prev>`: `agent_status` weiterhin `idle` oder `done`, sonst Abbruch (das Footer-Gate kann den Turn wieder aufnehmen).
   4. `pane read <prev> --source recent-unwrapped` und letzte Endzustandsmarke bestimmen (⏳ ✅ ❗ ‼️, die letzte im Text gewinnt). Nur ⏳ erlaubt das Schließen; ❗, ✅, ‼️, keine Marke oder nicht lesbar lassen alles stehen.
   5. `pane list --workspace <W>`: Tab der Vorgängerin ermitteln. Enthält er ausschließlich die Vorgängerin und Plan-Panes mit Token `owner=<prev>` und nicht das eigene Pane, dann `tab close <tab_id>`; sonst werden nur die Vorgängerin und ihre Plan-Panes einzeln per `pane close` geschlossen.
   6. Jede Stufe fail-open, Log-Zeile in `.claude/herdr_plan_pane.log`, Exit 0.
4. **Startauftrag.** `handoff_prompt` ergänzt einen Satz: „Nenne in deiner ersten Meldung in einem Satz das Ergebnis von #<alt> (Abschlusskommentar am Issue)." `<alt>` ist die Issue-Nummer des Workflows der Vorgängerin. Das Ergebnis jedes Issues steht im Abschlusskommentar am Issue; die Nachfolgerin liest es dort.
5. **Befehlstexte.** `80-workflow.md` und `60-validate.md` sprechen von „neuem Tab" statt „neuem Pane" und erwähnen, dass die Nachfolgerin den Tab der Vorgängerin nach sauberer Übergabe schließt. Skills und Cloud-Agents sind Generat.
6. **Version.** MINOR-Erhöhung in `.claude-plugin/plugin.json`, CLAUDE.md-Versionszeile und README (Wert bestimmt der Implementierer aus dem aktuellen Stand, 4.26.5 plus eins), CHANGELOG-Eintrag unter dem neuen Release.

## Expected Behavior

- **Input:** Herdr-Umgebung (`HERDR_ENV`, `HERDR_PANE_ID`, `HERDR_WORKSPACE_ID`, `HERDR_BIN_PATH`), Auftrag mit nächstem Issue M, optional Titel-Cache; bei der Nachfolgerin Env `OPENSPEC_HANDOFF_PREV_PANE`
- **Output:** `handoff --start` meldet wie bisher `STARTED=yes|no|already`; die Nachfolgerin läuft in einem eigenen Tab „#M Titel"; ihr Startauftrag enthält den Ein-Satz-Bericht-Satz
- **Side effects:** Neuer Herdr-Tab (ohne Fokuswechsel); später Schließen des Vorgänger-Tabs bzw. ihrer Panes; Log-Zeilen in `.claude/herdr_plan_pane.log`; Sperrdatei je Vorgänger-Pane

## Known Limitations

- Die Marke wird aus dem Bildschirmtext des Panes gelesen (`pane read`); ein langer Nachlauf nach der Marke, ein Umbruch oder ein geänderter Footer-Text kann die Erkennung verfehlen. Dann bleibt der Tab stehen (sicherer Ausgang), nie umgekehrt.
- Die Warte-Frist beträgt 30 Minuten; endet die Vorgängerin später, räumt niemand auf, und der Tab bleibt stehen.
- Die 5-Sekunden-Nachprüfung fängt Wiederaufnahme durch das Footer-Gate ab, nicht aber eine spätere, nutzerausgelöste Weiterarbeit in der Vorgängerin.
- Enthält der Start-Tab fremde Panes (zum Beispiel eine Shell), wird nur die Vorgängerin samt Plan-Panes geschlossen, nicht der Tab; ein übrig gebliebener Tab ist hinnehmbar.
- Der Rückfall auf den Split stapelt wieder Panes (wie vor #694), räumt aber über dasselbe Env-Verfahren auf.
- Der lokale Echtdurchlauf mit Herdr ist aus der Cloud nicht ausführbar; belegt ist er gegen das Fake-Binary, der Echtlauf wird am Epic #649 festgehalten.
- Ob die Nachfolgerin den Ein-Satz-Bericht tatsächlich bringt, erzwingt kein Hook; es ist Teil des Startauftrags.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Auftrag mit mindestens zwei Issues startet das zweite Issue in einem eigenen, beschrifteten Herdr-Tab, ohne dass sich Panes im Tab der Vorgängerin stapeln
- [ ] Nach sauberer Übergabe (⏳) verschwindet der Tab der Vorgängerin samt Plan-Pane von selbst; nach ❗, bei laufender oder unklarer Vorgängerin und bei fehlendem Herdr bleibt alles unberührt
- [ ] Die erste Meldung der Nachfolgerin nennt in einem Satz das Ergebnis des Vorgänger-Issues
- [ ] Scheitert `tab create`, läuft die Übergabe wie bisher per Split (kein Rückschritt gegenüber #667)
- [ ] `skills/` und `.claude/agents` ohne Drift, Regressionslauf `pytest tests/` grün, kein `pytest.skip` zur Entschärfung, Doku, CHANGELOG und Version veröffentlicht

## Acceptance Criteria

- **AC-1:** Given Weg `herdr`, ein Fake-Herdr-Binary (`HERDR_ENV=1`, `HERDR_PANE_ID`, `HERDR_WORKSPACE_ID`, `HERDR_BIN_PATH`), das `tab create`-JSON mit `tab_id` und `root_pane.pane_id` liefert und alle Aufrufe protokolliert / When `workflow.py handoff --start` läuft / Then ruft es `tab create --workspace <W> --cwd <Projekt-Root> --label <Label> --env OPENSPEC_HANDOFF_PREV_PANE=<eigenes Pane> --no-focus` und danach `pane run <neues Root-Pane>` mit `exec claude` und dem shlex-gequoteten Startauftrag auf, ruft `pane split` nicht auf, meldet `STARTED=yes` und schreibt das Auftragsfeld `handoff` wie in #667
  - Test: tests/test_handoff_tab_694.py::test_tab_create_with_env_label_no_focus

- **AC-2:** Given ein Titel-Cache `.claude/issue_briefs.json` mit Titel zu Issue M, kein Eintrag, ein Titel länger als 40 Zeichen und ein Titel mit Steuerzeichen (Zeilenumbruch, Tabulator, ESC) / When das Tab-Label gebaut wird / Then lautet es `#M <Titel>` bzw. nur `#M` ohne Eintrag, ist höchstens 40 Zeichen lang und enthält keine Steuerzeichen
  - Test: tests/test_handoff_tab_694.py::test_tab_label_cache_fallback_truncate_sanitize

- **AC-3:** Given ein Fake-Binary, dessen `tab create` fehlschlägt (Exit ungleich 0), ohne gültiges JSON oder ohne `pane_id` antwortet, die `pane_id` des eigenen Panes liefert oder hängt (Zeitlimit), sowie ein Lauf ohne `HERDR_WORKSPACE_ID` / When `workflow.py handoff --start` läuft / Then fällt `start_session` auf `pane split <eigenes Pane> --direction right --cwd <Projekt-Root> --no-focus` mit `--env OPENSPEC_HANDOFF_PREV_PANE=<eigenes Pane>` zurück, ruft danach `pane run <neues Pane>` auf und meldet `STARTED=yes`; ohne Workspace-Kennung wird `tab create` gar nicht erst aufgerufen
  - Test: tests/test_handoff_tab_694.py::test_tab_failure_falls_back_to_split_with_env

- **AC-4:** Given ein Fake-Binary, bei dem `tab create` gelingt und `pane run` im neuen Tab fehlschlägt / When `workflow.py handoff --start` läuft / Then wird `tab close <neue tab_id>` aufgerufen, die Ausgabe lautet `STARTED=no` mit `REASON=<kurz>`, Exit 0, und es wird kein `handoff`-Vermerk geschrieben
  - Test: tests/test_handoff_tab_694.py::test_pane_run_failure_closes_new_tab

- **AC-5:** Given ein Fake-Binary, das als neues Pane die ID des eigenen Panes zurückgibt / When `workflow.py handoff --start` läuft / Then wird weder `pane run` noch `tab close` mit dem eigenen Pane als Ziel aufgerufen
  - Test: tests/test_handoff_tab_694.py::test_never_targets_own_pane

- **AC-6:** Given `OPENSPEC_HANDOFF_PREV_PANE` nicht gesetzt, leer oder gleich dem eigenen Pane / When `start_predecessor_cleanup()` bei SessionStart läuft / Then startet kein Runner-Prozess, und es gibt keine Ausgabe auf stdout oder stderr; bei gesetztem Env ungleich eigenem Pane startet genau ein detachter Runner `handoff-cleanup <prev>`
  - Test: tests/test_handoff_tab_694.py::test_cleanup_starter_only_with_foreign_prev_env

- **AC-7:** Given Vorgängerin mit `agent_status` idle (bzw. done), bestätigt durch die Nachprüfung, deren Bildschirmtext zuletzt die Marke ⏳ trägt, und ein Tab, der nur sie und Plan-Panes mit Token `owner=<prev>` enthält, nicht aber die eigene Sitzung / When der Runner `handoff-cleanup` läuft / Then ruft er `tab close <Tab der Vorgängerin>` genau einmal auf und endet mit Exit 0
  - Test: tests/test_handoff_tab_694.py::test_cleanup_closes_whole_tab_after_waiting_marker

- **AC-8:** Given Vorgängerin idle mit ⏳, aber ein Tab mit fremdem Pane (zum Beispiel einer Shell) oder mit dem Pane der Nachfolgerin / When der Runner läuft / Then wird kein `tab close` aufgerufen, sondern nur die Vorgängerin und ihre Plan-Panes (Token `owner=<prev>`) werden einzeln per `pane close` geschlossen, fremde Panes und das eigene Pane bleiben
  - Test: tests/test_handoff_tab_694.py::test_cleanup_closes_only_own_panes_in_shared_tab

- **AC-9:** Given Bildschirmtext der Vorgängerin mit letzter Endzustandsmarke ❗, ✅ oder ‼️, ohne Marke oder nicht lesbar, sowie eine Folge mit mehreren Marken / When der Runner läuft / Then wird nichts geschlossen, außer die zuletzt vorkommende Marke ist ⏳ (bei „❗ ... ⏳" wird geschlossen, bei „⏳ ... ❗" nicht)
  - Test: tests/test_handoff_tab_694.py::test_cleanup_marker_matrix_last_wins

- **AC-10:** Given Vorgängerin `blocked`, `working` über die Frist hinaus (Zeitlimit des `agent wait` verkürzt per Test), oder nach der Nachprüfung wieder `working` / When der Runner läuft / Then wird nichts geschlossen und der Runner endet mit Exit 0
  - Test: tests/test_handoff_tab_694.py::test_cleanup_no_close_when_not_idle_or_timeout_or_resumed

- **AC-11:** Given eine bereits laufende Sperre für dasselbe Vorgänger-Pane / When ein zweiter Runner startet / Then beendet er sich ohne Herdr-Aufruf; mit einer Sperre für ein anderes Vorgänger-Pane läuft er normal
  - Test: tests/test_handoff_tab_694.py::test_cleanup_lock_per_predecessor_pane

- **AC-12:** Given ein kaputtes Herdr (Binary fehlt, Exit ungleich 0, Müll-JSON, Zeitlimit) / When `start_predecessor_cleanup()` und der Runner laufen / Then enden beide mit Exit 0, schreiben nichts auf stdout oder stderr, und es wird nichts geschlossen
  - Test: tests/test_handoff_tab_694.py::test_cleanup_fail_open_silent

- **AC-13:** Given ein autarker Auftrag mit Vorgänger-Issue N und nächstem Issue M / When der Startauftrag ausgegeben wird / Then enthält er zusätzlich den Satz, in der ersten Meldung in einem Satz das Ergebnis von #N (Abschlusskommentar am Issue) zu nennen, und alle Bausteine aus #667 bleiben erhalten
  - Test: tests/test_handoff_tab_694.py::test_prompt_has_predecessor_result_sentence

- **AC-14:** Given die Befehlstexte `core/commands/80-workflow.md` und `60-validate.md` samt erzeugten Skills / When der Absatz zur Herdr-Übergabe gelesen wird / Then sprechen sie von „neuem Tab" und nicht mehr von „neuem Pane", und `sync_skills.py --check` sowie `sync_cloud_agents.py --check` melden keine Drift
  - Test: tests/test_handoff_tab_694.py::test_command_texts_say_tab_and_skills_in_sync

- **AC-15:** Given der Bestandstest zu #667 (Herdr-Start gegen Fake-Binary) / When er nach der Änderung läuft / Then erwartet er `tab create` als Primärweg (statt `pane split`) und bleibt grün; alle übrigen Tests aus test_handoff_667.py und test_handoff_668.py laufen unverändert grün
  - Test: tests/test_handoff_667.py::test_herdr_start_with_fake_binary

## Test Plan

Automatische Tests, jeweils an eine AC gebunden, ohne Netzwerk, mit tmp-Projekt, Subprozess-Aufruf von `workflow.py` bzw. `herdr_bridge.py` und einem Fake-Herdr-Binary (Muster aus tests/test_handoff_667.py), das Aufrufe protokolliert und je Testfall Antworten (JSON, Exit-Code, Hängen, `pane read`-Text, `pane list`-Inhalt) steuert. Das Test-Env setzt `OPENSPEC_AUTONOMY`, `CLAUDE_CODE_REMOTE`, `HERDR_ENV`, `HERDR_PANE_ID`, `HERDR_WORKSPACE_ID`, `HERDR_BIN_PATH` und `PATH` explizit; Wartezeiten des Runners sind für Tests per Umgebungsvariable verkürzbar, die Produktionswerte stehen als Konstanten im Code.

- GIVEN Fake-Binary mit tab-create-JSON WHEN `handoff --start` THEN `tab create` mit Label, Env, `--no-focus`, danach `pane run`, kein `pane split` (AC-1)
- GIVEN Cache mit Titel, ohne Eintrag, lang, mit Steuerzeichen WHEN Label gebaut THEN `#M Titel` bzw. `#M`, höchstens 40 Zeichen, bereinigt (AC-2)
- GIVEN `tab create` scheitert in allen Varianten oder Workspace fehlt WHEN `handoff --start` THEN `pane split` mit `--env`, `STARTED=yes` (AC-3)
- GIVEN `pane run` scheitert im neuen Tab WHEN `handoff --start` THEN `tab close`, `STARTED=no`, kein Vermerk (AC-4)
- GIVEN Fake liefert das eigene Pane zurück WHEN `handoff --start` THEN kein Zugriff auf das eigene Pane (AC-5)
- GIVEN Env fehlt, leer, gleich eigenem Pane bzw. fremd WHEN SessionStart-Starter THEN kein bzw. genau ein Runner (AC-6)
- GIVEN idle, ⏳, reiner Vorgänger-Tab WHEN Runner THEN ein `tab close` (AC-7)
- GIVEN idle, ⏳, Tab mit fremdem oder eigenem Pane WHEN Runner THEN nur einzelne `pane close` (AC-8)
- GIVEN Marken ❗, ✅, ‼️, keine, gemischte Reihenfolgen WHEN Runner THEN Schließen nur bei letzter Marke ⏳ (AC-9)
- GIVEN blocked, Zeitlimit, Wiederaufnahme WHEN Runner THEN nichts geschlossen (AC-10)
- GIVEN laufende Sperre für dasselbe bzw. anderes Pane WHEN zweiter Runner THEN Abbruch bzw. Lauf (AC-11)
- GIVEN kaputtes Herdr WHEN Starter und Runner THEN Exit 0, keine Ausgabe, nichts geschlossen (AC-12)
- GIVEN Auftrag mit Vorgänger N WHEN Startauftrag THEN Satz zu #N plus alle #667-Bausteine (AC-13)
- GIVEN Befehlstexte und Skills WHEN gelesen und `--check` THEN „Tab", keine Drift (AC-14)
- GIVEN angepasster Bestandstest WHEN `pytest tests/test_handoff_667.py` THEN grün (AC-15)

Läufe:

- `pytest tests/test_handoff_tab_694.py tests/test_handoff_667.py tests/test_handoff_668.py` (RED zuerst, dann GREEN)
- Regressionslauf: `pytest tests/` (insbesondere Plan-Pane-Tests und `footer_gate`-Tests)
- `python3 -m py_compile core/hooks/herdr_bridge.py core/hooks/workflow.py core/hooks/session_banner.py`
- `python3 scripts/sync_skills.py --check` und `python3 scripts/sync_cloud_agents.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung bleibt im Rahmen des bestehenden Herdr-Starts aus #667 und des Plan-Pane-Musters (detachter, fail-open Runner mit Sperre und Log); es entsteht keine neue Architekturebene, keine Gate-Config und kein neuer Hook (SessionStart ruft nur eine weitere fail-open-Funktion). Entscheidung: Tab statt Split, weil ein Tab je Auftrag die Übersicht hält und Panes sich nicht mehr stapeln. Aufräumen macht die Nachfolgerin über die Bildschirm-Marke ⏳ der Vorgängerin: Nur die Marke trennt „sauber übergeben" von „gescheitert" (❗), ohne dass die Vorgängerin selbst etwas tun muss; im Zweifel bleibt der Tab stehen (lieber ein überzähliger Tab als geschlossene Arbeit). Reversibel: Rückfall auf den Split ist der bisherige Weg.
- **Alternative A, bei Splits bleiben:** verworfen, Panes stapeln sich mit jedem Issue (Beleg 2026-11-26).
- **Alternative B, Vorgängerin schließt sich selbst per SessionEnd-Hook:** verworfen. Beim Sitzungsende ist nicht sicher, ob die Übergabe geglückt ist, und ein selbst geschlossenes Pane nimmt Fehlerbild und letzte Meldung mit; die Nachfolgerin sieht beides vorher.
- **Alternative C, Marke über Zustandsdatei statt Bildschirmtext:** verworfen. Der Endzustand ⏳ entsteht erst im Fußzeilen-Text des Turns; ein zusätzlicher Dateivermerk bräuchte einen neuen Schreibpunkt in `end_state`/`footer_gate.py` (bewusst unverändert, #667 AC-10). Bildschirmtext ist die eine Quelle, die Henning selbst sieht.
- **Alternative D, Config-Schalter für Tab und Aufräumen:** verworfen, autarker Auftrag ohne Gate-Config-Änderung; Konstanten im Code, Kill-Switch ist das Fehlen von Herdr bzw. der bestehende `auftrag.enabled`.
- **Alternative E, immer den ganzen Tab schließen:** verworfen, der Tab kann fremde Panes (Shell) oder die Nachfolgerin selbst enthalten; dann nur die eigenen Panes der Vorgängerin.

## Changelog

- 2026-11-26: Initial spec created
