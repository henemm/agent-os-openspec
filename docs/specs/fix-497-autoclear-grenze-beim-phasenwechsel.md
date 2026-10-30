---
entity_id: fix-497-autoclear-grenze-beim-phasenwechsel
type: bugfix
created: 2026-10-30
updated: 2026-10-30
status: draft
version: "1.0"
workflow: fix-497-autoclear-grenze-beim-phasenwechsel
tags: [herdr, auto-clear, workflow, phase-transition, footer-gate, e2e]
---

# Auto-/clear-Grenze beim Phasenwechsel selbst vermerken, Restfaelle schliessen, echter E2E (Issue #497)

## Approval

- [ ] Approved

## Purpose

Seit #495 haengt der Auto-/clear davon ab, dass Claude am Phasenende zusaetzlich `workflow.py autoclear` aufruft; tut das Modell es nicht, entsteht kein Vermerk und kein `/clear`. Kuenftig schreibt der erzwungene Phasenwechsel (`record_transition`) den Grenz-Vermerk `auto_clear_boundary` selbst, wenn der Uebergang eine Phasengrenze ist und Auto-/clear aktiv ist. Zusaetzlich werden zwei Restfaelle aus #495 geschlossen (zweimal falsche Fusszeile hinterlaesst den Vermerk; `at` ohne Zeitzone) und die Kette wird mit einem echten Plugin-Befehl und einem grossen Modell in Herdr getestet.

## Source

- **File:** `core/hooks/workflow.py` (Vermerk beim Phasenwechsel), `core/hooks/footer_gate.py` (Vermerk verwerfen), `core/hooks/herdr_bridge.py` (Leser)
- **Identifier:** `record_transition`, `_record_auto_clear_boundary`, `cmd_phase`, `_apply_spec_approval`, `expected_footer_command`; `footer_gate.main`; `_boundary_fresh`, `_consume_boundary`, `maybe_auto_clear`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/workflow.py` (#495) | module | `record_transition` ist der gemeinsame Pfad aller Phasenwechsel (`cmd_phase`, `_apply_spec_approval` fuer `auto-approve`, `phase_listener`-Freigabe); `next_step`/`expected_footer_command` liefern den Folgebefehl |
| `core/hooks/herdr_bridge.py` (#467/#480/#495) | module | `_pane()`, `auto_clear_enabled()` entscheiden, ob Auto-/clear aktiv ist; `_consume_boundary`, `_boundary_fresh`, `maybe_auto_clear` bleiben der Leser |
| `core/hooks/phase_listener.py` | module | Freigabe-Pfad „approved“ ruft `record_transition`; unveraendert, erbt den Vermerk |
| `core/hooks/footer_gate.py` | module | `stop_hook_active`-Ausgang verwirft vorhandenen Vermerk |
| `scripts/e2e_auto_clear.sh` (#495) | script | echter E2E mit Herdr 0.9.5 headless, Claude-TUI und Plugin |
| `tests/test_autoclear_boundary_495.py`, `tests/test_herdr_auto_clear_467.py`, `tests/test_auto_clear_global_480.py`, `tests/test_kette_auto_clear_489.py`, | tests | Regression; Helfer als Vorbild |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | Grenz-Tabelle `AUTO_CLEAR_BOUNDARIES`; in `record_transition` Vermerk setzen, wenn (alt, neu) Grenze und Auto-/clear aktiv (fail-open); `at` mit Zeitzone, auch in `_record_auto_clear_boundary` |
| core/hooks/footer_gate.py | MODIFY | `stop_hook_active`-Ausgang (vor `sys.exit(0)`) verwirft vorhandenen Vermerk, fail-open |
| core/hooks/herdr_bridge.py | MODIFY (ggf.) | Nur Zeitzonen-Lesen in `_boundary_fresh`, falls der Bestandscode naive und tz-aware `at` nicht schon beide korrekt liest |
| tests/test_autoclear_transition_497.py | CREATE | Tests zu AC-1 bis AC-9 |
| scripts/e2e_auto_clear.sh | MODIFY | Szenario A ohne `autoclear`-Aufruf (nur `workflow.py phase phase2_analyse`); neues Szenario E mit echtem Plugin-Befehl und grossem Modell |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] / Fixed (#497) |

### Estimated Changes

- Files: 1 neu, 5 geaendert
- LoC: +45 Produktion / +260 Test / +80 E2E-Skript
- Risk Level: MEDIUM (laeuft bei jedem Phasenwechsel; Wirkung nur mit Herdr und Opt-in; jeder Fehler fuehrt zu „kein vermerkt“)

## Implementation Details

**Grenz-Tabelle.** Eine Konstante in `workflow.py` mit den fuenf Grenzen (alt → neu), jeweils Ende eines Phasenbefehls, nach dem der Folgebefehl im neuen Kontext startet:

| Uebergang | Ort | Folgebefehl |
|---|---|---|
| phase1_context → phase2_analyse | 10-context Ende | `/20-analyse #N` |
| phase2_analyse → phase3_spec | 20-analyse Ende | `/30-write-spec #N` |
| phase3_spec → phase4_approved | Freigabe (`approved` im `phase_listener`, `auto-approve` via `_apply_spec_approval`) | `/40-tdd-red #N` |
| phase5_tdd_red → phase6_implement | 40-tdd-red Ende | `/50-implement #N` |
| phase6b_adversary → phase7_validate | 50-implement nach VERIFIED | `/60-validate #N` |

Keine Grenzen (kein Vermerk): phase4 → phase5 (Anfang von 40), phase6 → phase6b (mitten in 50), phase6b → phase6 (BROKEN-Fix-Schleife), jeder Ruecksprung, phase7 → phase8.

**Vermerk beim Phasenwechsel.** Am Ende von `record_transition` (nach Protokoll und Budget, vor `return`; `current_phase` ist dort noch die alte Phase): ist `(alt, target)` in der Tabelle und `herdr_bridge._pane()` sowie `herdr_bridge.auto_clear_enabled()` wahr, wird der Folgebefehl aus einer Kopie mit `current_phase = target` per `expected_footer_command` bestimmt (dieselbe Quelle wie `status_note()` und der Leser). Ist das Ergebnis ein String, der mit `/` beginnt, wird `data["auto_clear_boundary"] = {"phase": target, "command": <Befehl #N>, "at": <tz-aware ISO>}` gesetzt. Der Aufrufer speichert den State ohnehin (`cmd_phase` per `_save_active`, `_apply_spec_approval`-Aufrufer, `phase_listener`); es gibt keinen zusaetzlichen Schreibvorgang. Die Pruefung steckt komplett in einem `try/except Exception: pass`: ein Fehler beim Vermerken (Import, Herdr-Status, Befehlsbestimmung) aendert weder Rueckgabewert noch Ausgabe noch Exit-Code des Phasenwechsels. Bei Auto-/clear aus wird nichts geschrieben und nichts ausgegeben; die Ausgabe von `cmd_phase` (`Set phase to: ...`, Budget-Rueckfrage) bleibt byteweise gleich.

**`workflow.py autoclear` bleibt** als zweite, gleichwertige Quelle; `_record_auto_clear_boundary` und der neue Pfad nutzen denselben Zeitstempel-Helfer.

**Zeitzone (#497b).** `at` wird als `datetime.now().astimezone().isoformat()` geschrieben (z. B. `2026-10-30T14:03:11+01:00`). `_boundary_fresh` liest tz-aware (nach lokaler Zeit umgerechnet) und naive Werte (als lokale Zeit) aus aelteren States; Aenderung in `herdr_bridge.py` nur, falls ein Test eine Luecke zeigt.

**footer_gate (#497a).** Im Zweig `payload.get("stop_hook_active") is True` (Fusszeile weiterhin falsch, Exit 0 statt Block) wird vor dem Beenden ein vorhandener `auto_clear_boundary` verworfen: State lesen, `herdr_bridge._consume_boundary(data, boundary)`, jede Ausnahme geschluckt, Exit-Code und stdout unveraendert. So bleibt nach zweimal falscher Fusszeile kein Rest-Vermerk, der einen spaeteren Turn derselben Phase ausloest.

**E2E (`scripts/e2e_auto_clear.sh`).**
- Szenario A' ersetzt A: Claude fuehrt nur `python3 <repo>/core/hooks/workflow.py phase phase2_analyse` aus (Workflow steht auf phase1_context), kein `autoclear`-Aufruf, gibt danach die ❗Du-Zeile mit `/20-analyse #N` aus. Erwartung: Vermerk entsteht durch den Phasenwechsel, Log `OK`, Herdr tippt `/clear` und den Folgebefehl. B/C/D bleiben, werden aber an A' angepasst (Vermerk ueber Phasenwechsel statt `autoclear`).
- Szenario E (optional, `ONLY=E`): echter Plugin-Befehl `/agent-os-openspec:10-context` (bzw. Alias) in einem kleinen Wegwerf-Projekt mit Issue-Nummer, grosses Modell ueber `E2E_MODEL` (z. B. `opus`), Rechte fuer das Wegwerf-Projekt per `--dangerously-skip-permissions` (isolierter Container, Wegwerf-Ordner). Erwartung: Phase wechselt auf `phase2_analyse`, Herdr tippt `/clear` und `/20-analyse #N`, der echte Folgebefehl startet. Standardlauf `ONLY` bleibt ohne E (Kosten/Dauer).

## Expected Behavior

- **Input:** Ein Befehl beendet seine Phase mit einem erzwungenen Phasenwechsel an einer Grenze (oder der PO gibt frei), Herdr-Pane, Opt-in an
- **Output:** `auto_clear_boundary` steht im State, der Stop-Hook spawnt den Auto-/clear-Runner, im neuen Kontext startet der Folgebefehl
- **Side effects:** Feld `auto_clear_boundary` mit tz-aware `at`; bei zweimal falscher Fusszeile wird ein Vermerk entfernt; Log-Grund `skip: ...` wie bisher

## Known Limitations

- Ein Grenz-Phasenwechsel ausserhalb eines Befehlsendes (z. B. manuell per `workflow.py phase`) setzt ebenfalls den Vermerk. Begrenzt wird das durch Einmal-Signal, 15-min-Fenster und die Pflicht, dass die Fusszeile den Folgebefehl nennt; das Risiko ist Fehl-Ausloesung bei Opt-in.
- Der Vermerk garantiert nicht, dass der Befehl alle Arbeit gesichert hat; das bleibt Aufgabe der Befehlstexte. Das Negativ-Veto schuetzt nur, wenn das Modell es ausgibt.
- Die uebrigen Schleifenschutz-Ausgaenge von `footer_gate` (gleiche Turn-ID, Sperrfenster) verwerfen den Vermerk nicht; dort begrenzt das 15-min-Fenster.
- Der echte E2E (Szenario E) mit grossem Modell kostet einige Minuten und Cent bis wenige Dollar und ist nur per `ONLY=E` bzw. manuell laufbar.
- Echtes TUI-Verhalten ist nur im realen Herdr pruefbar; die Unit-Tests nutzen ein Stub-Binary.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt (AC-9 durch das E2E-Skript)
- [ ] Szenario A' und Szenario E des E2E laufen in einem echten Herdr gruen und der Beleg (Log, Pane-Auszug) liegt vor
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen, insbesondere #467-/#478-/#480-/#489-/#495-Tests)

## Acceptance Criteria

- **AC-1:** Given aktives Auto-/clear (Herdr-Pane, Opt-in) und ein Workflow / When `workflow.py phase` jede der fuenf Grenzen (1→2, 2→3, 5→6, 6b→7; 3→4 siehe AC-2) ausfuehrt / Then enthaelt der State `auto_clear_boundary` = `{phase: neue Phase, command: Folgebefehl #N, at}` mit den Folgebefehlen `/20-analyse`, `/30-write-spec`, `/50-implement`, `/60-validate`
  - Test: tests/test_autoclear_transition_497.py::test_phase_command_records_boundary_per_table

- **AC-2:** Given aktives Auto-/clear / When die Spec freigegeben wird, per `auto-approve` und per `phase_listener` („approved“) / Then steht `auto_clear_boundary` = `{phase: phase4_approved, command: "/40-tdd-red #N"}` im State
  - Test: tests/test_autoclear_transition_497.py::test_approval_paths_record_boundary

- **AC-3:** Given aktives Auto-/clear / When phase4→phase5, phase6→phase6b, phase6b→phase6, ein Ruecksprung oder phase7→phase8 ausgefuehrt wird / Then wird KEIN `auto_clear_boundary` gesetzt
  - Test: tests/test_autoclear_transition_497.py::test_non_boundaries_record_nothing

- **AC-4:** Given Auto-/clear aus (kein Herdr-Pane oder Opt-in aus) / When ein Grenz-Phasenwechsel laeuft / Then wird kein Vermerk gesetzt, und Ausgabe und Exit-Code von `workflow.py phase` sind identisch zum Lauf ohne diese Aenderung
  - Test: tests/test_autoclear_transition_497.py::test_auto_clear_off_records_nothing_output_unchanged

- **AC-5:** Given ein Fehler beim Vermerken (z. B. `herdr_bridge` nicht importierbar oder `expected_footer_command` wirft) / When ein Grenz-Phasenwechsel laeuft / Then wird der Phasenwechsel trotzdem protokolliert und gespeichert, Exit 0
  - Test: tests/test_autoclear_transition_497.py::test_boundary_error_never_aborts_transition

- **AC-6:** Given ein vorhandener Vermerk und ein Stop mit `stop_hook_active` bei weiterhin falscher Fusszeile / When `footer_gate.py` laeuft / Then ist der Vermerk danach aus dem State entfernt, Exit 0, stdout unveraendert (#497a)
  - Test: tests/test_autoclear_transition_497.py::test_footer_gate_stop_hook_active_discards_boundary

- **AC-7:** Given ein neu geschriebener Vermerk / When `at` gelesen wird / Then enthaelt `at` eine Zeitzone; und `_boundary_fresh` akzeptiert sowohl diesen Wert als auch einen alten naiven `at` aus bestehenden States (frisch = true, aelter als 15 min = false) (#497b)
  - Test: tests/test_autoclear_transition_497.py::test_at_has_timezone_and_reader_accepts_both

- **AC-8:** Given Szenario A' (Claude fuehrt nur `workflow.py phase phase2_analyse` aus, kein `autoclear`) in echtem Herdr mit Claude-TUI / When das Skript laeuft / Then steht im Log `OK`, Herdr tippt `/clear` und `/20-analyse #N`, und der Folgebefehl startet; Szenario E: Given echter Plugin-Befehl `10-context` in einem Wegwerf-Projekt mit grossem Modell (`E2E_MODEL`) / Then wird `phase2_analyse` erreicht, Herdr tippt `/clear` und `/20-analyse #N`, der echte Folgebefehl startet
  - Test: scripts/e2e_auto_clear.sh (ONLY="A E")

- **AC-9:** Given die bestehenden Tests / When `pytest tests/test_autoclear_boundary_495.py tests/test_herdr_auto_clear_467.py tests/test_auto_clear_global_480.py tests/test_kette_auto_clear_489.py` laufen / Then sind sie gruen
  - Test: Regressionslauf `pytest tests/`

## Test Plan

Muster `tests/test_autoclear_boundary_495.py`: isoliertes Projekt, Stub-Herdr (`HERDR_BIN_PATH`, `HERDR_ENV=1`, `HERDR_PANE_ID`), `workflow.py phase` und `footer_gate.py` per Subprozess mit `OPENSPEC_ACTIVE_WORKFLOW`; Auto-/clear aus ueber fehlende Env bzw. Opt-in-Config.

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN Auto-/clear aktiv und ein Workflow in phase1_context WHEN `workflow.py phase phase2_analyse` THEN steht `auto_clear_boundary` {phase2_analyse, `/20-analyse #N`} im State; analog 2→3, 5→6 (mit `red_test_done`), 6b→7
- [ ] Test 2: GIVEN Auto-/clear aktiv und Workflow in phase3_spec mit Spec WHEN `auto-approve` bzw. der `phase_listener` „approved“ verarbeitet THEN steht {phase4_approved, `/40-tdd-red #N`} im State
- [ ] Test 3: GIVEN Auto-/clear aktiv WHEN phase4→5, 6→6b, 6b→6, Ruecksprung, 7→8 THEN fehlt `auto_clear_boundary`
- [ ] Test 4: GIVEN Auto-/clear aus WHEN Grenz-Phasenwechsel THEN kein Vermerk, Ausgabe `Set phase to: ...` und Exit 0 wie bisher
- [ ] Test 5: GIVEN ein Fehler im Vermerk-Pfad (Stub wirft) WHEN Grenz-Phasenwechsel THEN Phase gespeichert, `phase_transitions` ergaenzt, Exit 0
- [ ] Test 6: GIVEN State mit Vermerk und falscher Fusszeile bei `stop_hook_active: true` WHEN `footer_gate.py` THEN Vermerk entfernt, Exit 0
- [ ] Test 7: GIVEN Vermerk mit tz-aware und mit naivem `at` (frisch/alt) WHEN `_boundary_fresh` THEN frisch true, alt false; neuer Vermerk traegt Zeitzone
- [ ] Test 8: GIVEN Vermerk aus Phasenwechsel plus korrekte Fusszeile WHEN `footer_gate.py` THEN spawnt der Runner (Stub-Herdr), ohne dass `autoclear` aufgerufen wurde

Weitere Laeufe:

- `pytest tests/test_autoclear_transition_497.py`
- Regressionslauf: `pytest tests/` (insbesondere #467, #478, #480, #489, #495)
- Syntaxpruefung: `python3 -m py_compile core/hooks/workflow.py core/hooks/footer_gate.py core/hooks/herdr_bridge.py`
- E2E: `ONLY="A E" E2E_MODEL=opus bash scripts/e2e_auto_clear.sh`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Fehlerkorrektur im bestehenden Auto-/clear: der bereits vorhandene Vermerk (#495) wird an der Stelle gesetzt, die jeder Phasenwechsel ohnehin durchlaeuft (`record_transition`), statt von einem zusaetzlichen Modell-Aufruf abzuhaengen. Kein neues Gate, keine Hook-Registrierung, kein Breaking Change am State-Format (zusaetzlicher Zeitzonen-Offset in `at` wird von alten Lesern per `fromisoformat` verstanden, alte naive Werte bleiben lesbar); jeder Fehler ist fail-open und reversibel.

## Changelog

- 2026-10-30: Initial spec created
