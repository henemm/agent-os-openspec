---
entity_id: fix-506-autoclear-ohne-herdr-status
type: bugfix
created: 2026-10-31
updated: 2026-10-31
status: draft
version: "1.0"
workflow: fix-506-autoclear-ohne-herdr-status
tags: [herdr, auto-clear, hooks, signals, e2e]
---

# Auto-/clear mit eigenen Plugin-Signalen statt Herdr-Status (Issue #506)

## Approval

- [ ] Approved

## Purpose

Auto-/clear bricht beim PO an Phasengrenzen fast immer ab (24 Abbrueche, 3 Erfolge, Log: `ABBRUCH: wait 1/2: agent wait Exit 1 timed out waiting for agent status`). Der Runner wartet per `herdr agent wait --until idle --until done` auf einen Zustand, den Herdr per lokalem Erkennungs-Manifest (`~/.config/herdr/agent-detection/claude.toml`, Prio 960) klassifiziert: Eine Antwort, die mit `❗ Du: …` endet, gilt als `blocked`. Genau diese Zeile verlangt das Plugin an jeder Phasengrenze, also wird Herdr dort nie `idle`. Statt Herdrs Heuristik zu umgehen, nutzt das Plugin kuenftig eigene, vom Plugin selbst erzeugte Signale (Hook-Marker je Pane); Herdr wird nur noch zum Tippen (`agent prompt`) gebraucht, `agent wait` entfaellt.

## Source

- **File:** `core/hooks/herdr_bridge.py` (Runner, Marker-API), `core/hooks/phase_listener.py` (UserPromptSubmit-Marker), `core/hooks/session_banner.py` (SessionStart-Marker)
- **Identifier:** `_Runner` (`_wait_ready` entfaellt, `run`, `__init__`), `_ac_base`, `AC_DEFAULTS`, `READY_STATES`, neu `record_signal`; `phase_listener.main`; `session_banner.main`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/herdr_bridge.py` (#467/#495/#497/#499) | module | `_Runner`, `_recheck`, Once-Lock, `/99-reset`-Sperre (`MANUAL_COMMANDS`), `resolve_command_form`, `_ac_log`, `_ac_base` bleiben; nur das Warten wird ersetzt |
| `core/hooks/hook_utils.py` | module | `atomic_write_json`, `read_state_json`, `framework_disabled` |
| `hooks/hooks.json` | config | Reihenfolge SessionStart (`session_singleton_guard register` vor `session_banner`) und UserPromptSubmit (`phase_listener`) bleibt; keine neue Registrierung |
| `tests/test_herdr_auto_clear_467.py`, `test_auto_clear_global_480.py`, `test_herdr_plan_deploy_sessionstart_478.py` | tests | Stub-Herdr beantwortet `agent wait`; Stub und Erwartungen anpassen |
| `scripts/e2e_auto_clear.sh` (#495/#497/#499) | script | echter E2E mit Herdr 0.9.5, Claude-TUI und Plugin |
| Herdr 0.9.5 (`agent prompt`, Erkennungs-Manifest-Format) | extern | nur noch Tippen; Manifestformat fuer Szenario G am echten Binary belegen |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | MODIFY | `record_signal(kind, source)` (Marker schreiben, fail-open); `_Runner`: `_wait_ready` entfernt, neu Eingabe-Pruefung vor `/clear` und Warten auf SessionStart-`clear` danach; Budget/Docstring angepasst; `READY_STATES` entfernt, falls ungenutzt |
| core/hooks/phase_listener.py | MODIFY | Am Anfang von `main` (nach `framework_disabled`) `record_signal("input")`, eine Zeile, `try/except`, ohne Ausgabe |
| core/hooks/session_banner.py | MODIFY | Am Anfang von `main` (nach `framework_disabled`, vor Wartung/Git-Sync) `record_signal("session", source)` |
| tests/test_autoclear_eigene_signale_506.py | CREATE | Tests zu AC-1 bis AC-13 |
| tests/test_herdr_auto_clear_467.py, tests/test_auto_clear_global_480.py, tests/test_herdr_plan_deploy_sessionstart_478.py | MODIFY | Stub: kein `agent wait` mehr; `agent prompt /clear` im Stub schreibt den SessionStart-Marker; Erwartungssequenz `agent prompt`, `agent prompt`; `test_runner_reads_real_agent_status_field` entfaellt bzw. wird durch AC-1 ersetzt |
| scripts/e2e_auto_clear.sh | MODIFY | Szenario G (PO-Manifest nachgebaut) samt Gegenprobe G0 (alter Code), Szenario H (Eingabe in der Grace-Zeit); `H agent wait` der bestehenden Szenarien durch Pane-Text-Polling ersetzen |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] / Fixed (#506) |

### Estimated Changes

- Files: 1 neu, 8 geaendert
- LoC: +85/-45 Produktion, +260 Test, +90 E2E-Skript
- Risk Level: MEDIUM (Auto-/clear laeuft nur mit Herdr und Opt-in; Hooks bekommen einen Schreibzugriff, der strikt fail-open und ohne Ausgabe bleibt)

## Implementation Details

**Marker.** `herdr_bridge.record_signal(kind, source=None)`: tut nichts, wenn `HERDR_ENV != "1"` oder `HERDR_PANE_ID` leer ist; der Import von `herdr_bridge` in den Hooks erfolgt erst nach dieser Env-Pruefung. Datei je Pane und Art unter `_ac_base()/.claude/herdr_signals/`: `<pane>.input.json` (`{"at": <time.time()>}`) und `<pane>.session.json` (`{"source": "<clear|startup|resume|compact>", "at": <time.time()>}`). Zwei Dateien statt einer, damit die zwei Hooks nie Lesen-Aendern-Schreiben auf derselben Datei brauchen. Die Pane-Id wird fuer den Dateinamen auf `[A-Za-z0-9_.-]` reduziert. Schreiben per `hook_utils.atomic_write_json`; jede Ausnahme wird verschluckt, nichts geht auf stdout/stderr, kein `sleep`, kein Subprozess. Die Wanduhr (`time.time()`) ist gewollt: Hook und Runner sind verschiedene Prozesse auf demselben Rechner.

**Hook-Stellen.** `phase_listener.main`: unmittelbar nach `framework_disabled()`, noch vor Nachrichtenauswertung (auch injizierte Notification-Turns zaehlen als Eingabe, ein neuer Turn laeuft dann; Abbruch ist hier die sichere Seite). `session_banner.main`: vor `build_output`, weil Wartung und Haupt-Ordner-Sync Sekunden dauern koennen und der Runner auf dieses Signal wartet; `source` aus dem Hook-Payload.

**Runner (`_Runner.run`).** `spawn_at = time.time()` zu Beginn. Ablauf:
1. `/99-reset`-Sperre (unveraendert), Ankuendigung, Grace-Pause.
2. Eingabe-Pruefung: `<pane>.input.json` mit `at > spawn_at` -> `_Abort("vor /clear: Nutzer hat weitergeschrieben")`. Fehlende oder unlesbare Datei heisst "keine neue Eingabe".
3. settle, `_recheck("vor /clear")`, Eingabe-Pruefung ein zweites Mal (unmittelbar vor dem Tippen), dann `t_clear = time.time()` und `agent prompt /clear`.
4. Warten (Poll alle 0,2 s, hoechstens `idle_timeout_s`) auf `<pane>.session.json` mit `source == "clear"` und `at >= t_clear`. Ein aelterer Marker (SessionStart vor dem eigenen `/clear`) zaehlt nicht. Zeitablauf -> `_Abort("nach /clear: kein SessionStart(clear)")`, es wird kein Folgebefehl getippt.
5. settle, `_recheck("vor Folgebefehl")`, `agent prompt <resolve_command_form(command)>` (unveraendert).

Der Config-Schluessel `idle_timeout_s` und das CLI-Argument `--idle-timeout` bleiben (Bedeutung: Frist fuer das Eintreffen des `/clear`-Signals); keine neue Option. Das Gesamt-Budget enthaelt nur noch eine Wartephase. Once-Lock, `_recheck`, Vermerk, Log-Tag und `/99-reset`-Sperre bleiben unveraendert. Warum kein Berechtigungsdialog-Risiko: Der Runner startet erst im Stop-Hook, also nach dem Turn-Ende; Dialoge entstehen nur waehrend eines Turns.

**E2E.** Szenario G: wie A (Testdouble `20-analyse`), aber der Test-Herdr bekommt `$XDG_CONFIG_HOME/herdr/agent-detection/claude.toml` mit den PO-Regeln (Antwort endet mit `❗ Du:` -> `blocked`, `ℹ️ Nichts zu tun` -> `working`, Prio 960). Das Format wird am echten 0.9.5 belegt (Herdr-Doku bzw. `agent explain`), nicht geraten; ein Vorab-Check im Skript bestaetigt per `agent explain`/Status, dass die Regel greift (`blocked`). Erwartung: Log `OK`, im TUI `❯ /clear` und `❯ /20-analyse #999`. Gegenprobe G0: dasselbe Szenario mit dem Code von `origin/main` (Worktree, `--plugin-dir`) muss mit `ABBRUCH: wait 1` enden. Szenario H: wie A mit `grace_s` 25; waehrend der Grace-Zeit sendet das Skript einen neuen Prompt an die Claude-Session; erwartet: Log `ABBRUCH` mit "Nutzer hat weitergeschrieben", kein `❯ /clear` danach im TUI. Bestehende `herdr agent wait`-Aufrufe des Skripts dienen nur als Testhilfe und werden, wo sie im Manifest-Szenario haengen wuerden, durch Polling auf den Pane-Text ersetzt. A'-D und F laufen unveraendert.

## Expected Behavior

- **Input:** Auto-/clear ist aktiv, ein Grenz-Phasenwechsel hat einen Vermerk gesetzt, die Antwort endet mit `❗ Du: /<naechster> #N`, Herdr klassifiziert den Pane als `blocked`
- **Output:** Nach der Grace-Zeit tippt der Runner `/clear`, wartet auf das SessionStart(clear)-Signal des Plugins und tippt dann den Folgebefehl; Herdrs Agent-Status spielt keine Rolle
- **Side effects:** Dateien unter `.claude/herdr_signals/`; Runner-Log wie bisher; Abbruchgruende "Nutzer hat weitergeschrieben" und "kein SessionStart(clear)" im Log

## Known Limitations

- Hat der Nutzer in der Grace-Zeit Text getippt, aber nicht abgeschickt, erkennt das Plugin das nicht (es sieht nur abgeschickte Prompts); der Text wuerde mit `/clear` vermischt. Wie bisher.
- Eingaben nach dem getippten `/clear`, aber vor dem Folgebefehl, werden nicht erkannt (unklar, ob `/clear` einen UserPromptSubmit ausloest; eine Pruefung koennte das Verfahren faelschlich immer abbrechen).
- Die Marker-Dateien je Pane werden nicht aufgeraeumt (wenige Bytes je Pane); bei Herdr-Pane-Wiederverwendung gilt der letzte Stand, die Zeitvergleiche gegen `spawn_at`/`t_clear` machen aeltere Staende wirkungslos.
- Die Hooks schreiben in jedem Herdr-Pane einen Marker, auch bei ausgeschaltetem Auto-/clear (billig, ohne Konfigurationszugriff).
- Echtes TUI-/Manifest-Verhalten ist nur im realen Herdr pruefbar.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt (AC-12 durch das E2E-Skript)
- [ ] E2E G gruen mit neuem Code und G0 scheitert mit altem Code; H, A'-D, F gruen; Belege (Log, Pane-Auszug) liegen vor
- [ ] Regressionslauf gruen, insbesondere #467-/#478-/#480-/#495-/#497-/#499-Tests

## Acceptance Criteria

- **AC-1:** Given ein Stub-Herdr, der jeden Aufruf protokolliert / When der Runner einen vollstaendigen Lauf macht / Then enthaelt das Protokoll keinen Aufruf `agent wait`, nur `agent prompt` (`/clear`, dann Folgebefehl)
  - Test: tests/test_autoclear_eigene_signale_506.py::test_runner_never_calls_agent_wait

- **AC-2:** Given eine Eingabe-Marke mit `at` nach dem Runner-Start (Nutzer schreibt in der Grace-Zeit weiter) / When der Runner vor `/clear` prueft / Then Abbruch "Nutzer hat weitergeschrieben", weder `/clear` noch Folgebefehl getippt
  - Test: tests/test_autoclear_eigene_signale_506.py::test_new_input_since_spawn_aborts_without_typing

- **AC-3:** Given keine oder nur aeltere Eingabe-Marke / When der Runner prueft / Then wird `/clear` getippt
  - Test: tests/test_autoclear_eigene_signale_506.py::test_no_new_input_types_clear

- **AC-4:** Given ein SessionStart-Marker `source=clear` nach dem eigenen `/clear` / When der Runner wartet / Then tippt er nach settle und `_recheck` den Folgebefehl
  - Test: tests/test_autoclear_eigene_signale_506.py::test_session_clear_after_own_clear_types_followup

- **AC-5:** Given der SessionStart-Marker bleibt bis `idle_timeout_s` aus / When die Frist ablaeuft / Then Abbruch im Log, Folgebefehl nicht getippt
  - Test: tests/test_autoclear_eigene_signale_506.py::test_missing_session_signal_aborts_without_followup

- **AC-6:** Given ein SessionStart(clear)-Marker, dessen `at` vor dem eigenen `/clear` liegt, oder `source` ist nicht `clear` / When der Runner wartet / Then zaehlt er nicht (Abbruch nach Frist, kein Folgebefehl)
  - Test: tests/test_autoclear_eigene_signale_506.py::test_session_start_before_own_clear_does_not_count

- **AC-7:** Given Marker fuer ein fremdes Pane (andere `HERDR_PANE_ID`) / When der Runner prueft und wartet / Then beeinflussen sie weder die Eingabe-Pruefung noch das Warten
  - Test: tests/test_autoclear_eigene_signale_506.py::test_markers_are_per_pane

- **AC-8:** Given `HERDR_PANE_ID` fehlt oder `HERDR_ENV != "1"` / When `phase_listener.py` und `session_banner.py` als Hook laufen / Then entsteht keine Datei unter `.claude/herdr_signals/`; mit gesetztem Pane schreiben sie `<pane>.input.json` bzw. `<pane>.session.json` (`source` aus dem Payload)
  - Test: tests/test_autoclear_eigene_signale_506.py::test_hooks_write_marker_only_with_pane_id

- **AC-9:** Given ein nicht schreibbares Markerverzeichnis oder ungueltige Daten / When die Hooks laufen / Then kein Fehler, kein Exit-Code ungleich 0, keine Ausgabe auf stdout/stderr durch das Marker-Schreiben, und der uebrige Hook-Ablauf bleibt unveraendert
  - Test: tests/test_autoclear_eigene_signale_506.py::test_marker_write_is_fail_open_and_silent

- **AC-10:** Given Folgebefehl `/99-reset #N`, bereits gesetzter Once-Lock bzw. geaenderte Phase/erwarteter Befehl / When `maybe_auto_clear` bzw. der Runner laeuft / Then verhalten sie sich wie vor der Aenderung (kein Spawn bzw. Abbruch, `_recheck` vor `/clear` und vor dem Folgebefehl)
  - Test: tests/test_autoclear_eigene_signale_506.py::test_manual_lock_and_recheck_unchanged

- **AC-11:** Given die angepassten Bestandstests / When `pytest tests/test_herdr_auto_clear_467.py tests/test_auto_clear_global_480.py tests/test_herdr_plan_deploy_sessionstart_478.py tests/test_autoclear_boundary_495.py tests/test_autoclear_transition_497.py tests/test_befehlsform_context_titel_499.py` laufen / Then sind sie gruen
  - Test: Regressionslauf `pytest tests/`

- **AC-12:** Given echtes Herdr 0.9.5 mit nachgebautem PO-Manifest (`❗ Du:` -> `blocked`) und Claude-TUI / When Szenario G laeuft / Then Log `OK` und im TUI `❯ /clear` und `❯ /20-analyse #999`; die Gegenprobe G0 mit dem Code von `origin/main` endet mit `ABBRUCH: wait 1`
  - Test: scripts/e2e_auto_clear.sh (ONLY="G G0")

- **AC-13:** Given echtes Herdr und Szenario H (Nutzer schickt in der Grace-Zeit einen neuen Prompt) / When der Runner prueft / Then Log `ABBRUCH` mit "Nutzer hat weitergeschrieben" und kein `❯ /clear`; Szenarien A'-D und F bleiben gruen
  - Test: scripts/e2e_auto_clear.sh (ONLY="H A B C D F")

## Test Plan

Muster `tests/test_herdr_auto_clear_467.py` (isoliertes Projekt, Stub-Herdr mit Protokoll, `HOME` auf Wegwerf-Verzeichnis). Der Stub kennt nur `agent prompt` (und `notification show`); bei `agent prompt <pane> /clear` schreibt er optional den SessionStart-Marker im selben Format wie `record_signal`. Marker fuer Eingaben und fremde Panes legen die Tests direkt als Dateien an.

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN vollstaendiger Lauf WHEN Stub-Protokoll gelesen THEN kein `agent wait`
- [ ] Test 2: GIVEN Eingabe-Marke juenger als Runner-Start WHEN Runner THEN Abbruch, nichts getippt
- [ ] Test 3: GIVEN keine neue Eingabe WHEN Runner THEN `/clear` getippt
- [ ] Test 4: GIVEN Marker `clear` nach eigenem `/clear` WHEN Runner THEN Folgebefehl getippt
- [ ] Test 5: GIVEN kein Marker bis Timeout WHEN Runner THEN Abbruch, kein Folgebefehl
- [ ] Test 6: GIVEN Marker vor `/clear` oder `source=startup` WHEN Runner THEN zaehlt nicht
- [ ] Test 7: GIVEN Marker fremdes Pane WHEN Runner THEN ohne Einfluss
- [ ] Test 8: GIVEN Hooks mit/ohne Pane-Id WHEN ausgefuehrt THEN Marker nur mit Pane-Id
- [ ] Test 9: GIVEN Markerverzeichnis nicht schreibbar WHEN Hook THEN Exit 0 ohne Ausgabe
- [ ] Test 10: GIVEN `/99-reset`, Once-Lock, Phasenwechsel WHEN Auto-/clear THEN wie bisher

Weitere Laeufe:

- `pytest tests/test_autoclear_eigene_signale_506.py`, danach `pytest tests/`
- Syntaxpruefung: `python3 -m py_compile core/hooks/herdr_bridge.py core/hooks/phase_listener.py core/hooks/session_banner.py`
- E2E: `ONLY="G G0 H A B C D F" bash scripts/e2e_auto_clear.sh`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** ADR-0506 (Konvention: ADR-Nummer = Issue-Nummer)
- **Rationale:** Der Runner entscheidet kuenftig auf Basis eigener, deterministischer Plugin-Signale (letzte Eingabe, SessionStart-`clear` je Pane) statt auf Herdrs Statusklassifikation. Alternativen: (1) Konfig-Option/Herdr-Manifest anpassen, verworfen, weil es die Abhaengigkeit von einer lokalen Heuristik bestehen laesst, die jede Regel oder Herdr-Version verschieben kann, und der PO ausdruecklich das Plugin aendern statt sich arrangieren will; (2) ueber `agent read` den Bildschirmtext auswerten, verworfen, weil ebenfalls eine Bildschirmheuristik. Gewaehlt: Hooks laufen ohnehin bei jedem Prompt und jedem Sessionstart, kennen also genau die zwei Ereignisse, die der Runner braucht; der Runner startet erst nach Turn-Ende, womit Berechtigungsdialoge ausgeschlossen sind. Folge: zwei kleine Schreibzugriffe in bestehenden Hooks (fail-open, ohne neue Registrierung) und Wegfall der Herdr-Statusabhaengigkeit.

## Changelog

- 2026-10-31: Initial spec created
