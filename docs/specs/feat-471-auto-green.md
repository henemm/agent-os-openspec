---
entity_id: feat-471-auto-green
type: feature
created: 2026-10-28
updated: 2026-10-28
status: draft
version: "1.0"
workflow: feat-471-auto-green
tags: [autonomie, green, approvals, post-implementation-gate]
---

# Automatische GREEN-Freigabe im Auto-Modus (Issue #471)

## Approval

- [ ] Approved

## Purpose

Teil C von #468: Im Auto-Modus (`autonomy.mode: auto`) entfaellt die manuelle GREEN-Freigabe (`go`) nach der Implementierung. Ein neuer Befehl `workflow.py auto-green` setzt `green_approved` selbst, wenn ein maschinell belegter GREEN-Lauf vorliegt, und das Post-Implementation-Gate sperrt im Auto-Modus nicht mehr. Im Modus `manual` bleibt alles wie bisher.

## Source

- **File:** `core/hooks/workflow.py`
- **Identifier:** `_auto_green_decision`, `cmd_auto_green`, `COMMANDS`; zusaetzlich `core/hooks/post_implementation_gate.py::main`, `core/commands/50-implement.md` (Step 6), `skills/50-implement/SKILL.md`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/workflow.py` | module | `autonomy_mode()` und `trusted_config()` (#469/#470), `record_approval()`, `is_stop_locked()`, `_read_active`, `_save_active`, `_one_line`; `cmd_auto_approve` / `_auto_approve_decision` (#470) als Vorbild fuer Ausgabeformat und Fail-closed-Muster |
| `core/hooks/post_implementation_gate.py` | module | Lock/Batch-Fenster/Marker `user_approved_validation_<wf>`; wird im Auto-Modus uebersprungen |
| `core/hooks/phase_listener.py` | module | GREEN-Phrase `go` setzt weiterhin `green_approved` und Marker; bleibt unveraendert |
| `core/commands/50-implement.md` | command | Quelle fuer `skills/50-implement/SKILL.md`; Step 6 verzweigt nach Modus |
| `scripts/sync_skills.py` | script | Erzeugt den Skill aus dem Command; `--check` meldet Drift |
| `docs/context/feat-468-autonomie-modus.md` | doc | Gesamtanalyse und PO-Entscheidungen zu #468 |
| `docs/context/feat-471-auto-green.md` | doc | Kontext und Analyse zu #471 |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `_auto_green_decision()`, `cmd_auto_green`, Eintrag `auto-green` in `COMMANDS` |
| core/hooks/post_implementation_gate.py | MODIFY | Im Auto-Modus nach den Bypass-Pruefungen direkt `allow()`: kein Lock, kein Block |
| core/commands/50-implement.md | MODIFY | Step 6 verzweigt: `AUTONOMY=auto` -> `auto-green`; sonst bisherige `go`-Freigabe |
| skills/50-implement/SKILL.md | MODIFY (generiert) | Per `python3 scripts/sync_skills.py` neu erzeugt |
| tests/test_auto_green_471.py | CREATE | Tests zu allen Acceptance Criteria |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 5 geaendert
- LoC: +70 Produktion / +300 Test

## Implementation Details

**Befehl.** `workflow.py auto-green` (`cmd_auto_green`) gibt zwei Zeilen auf stdout aus: `AUTO_GREEN=done|human` und `REASON=<kurz, einzeilig>`. Exit immer 0, fail-closed: jede Ausnahme einschliesslich `SystemExit` ergibt `human`. Der Zustand wird nur bei `done` gespeichert.

**Pruefkette** (`_auto_green_decision() -> (verdict, reason)`), erste Verfehlung ergibt `human` ohne State-Aenderung:

1. `autonomy_mode() == "auto"`. Das ist nur ueber `trusted_config()` erreichbar (YAML der wirksamen Projekt-Config); `settings.local.json` und Unterordner-Configs wirken nicht.
2. Aktiver Workflow lesbar (`_read_active()`), sonst `human`.
3. `current_phase == "phase6_implement"`.
4. `red_test_done` ist gesetzt (RED wurde belegt).
5. Mindestens ein Eintrag in `test_artifacts` mit `type == "test_output"` und `phase == "phase6_implement"` (das GREEN-Artefakt aus Step 4). Massgeblich ist das **juengste** solche Artefakt (letzter passender Eintrag in `test_artifacts`); aeltere werden nicht beruecksichtigt. PO-Entscheidung: `auto-green` gibt nur frei, wenn dieses Artefakt **inhaltlich bestandene Tests** zeigt (keine failed/errors, mindestens ein passed). Die Auswertung ist `core/hooks/qa_gate.py::validate_test_output(filepath, trusted=True)` (Rueckgabe `(valid, message)`; sie nutzt intern `_find_pytest_summary_line` / `_evaluate_pytest_summary` und die Runner-Auswertungen fuer unittest, node, go, cargo, Swift) und wird wiederverwendet, nicht nachgebaut. `trusted=True`, weil die Altersgrenze (30 min) und der Groessen-Vorfilter fuer ein beim Registrieren gepruefte Artefakt nicht passen; die inhaltliche Auswertung bleibt voll aktiv. `valid == False` ergibt `human` mit dem `message` als `REASON`. Die Datei wird nur gelesen, wenn sie eine **regulaere Datei** ist (kein Symlink, kein Verzeichnis, kein Geraet) und ihr aufgeloester Pfad **innerhalb des Projekts** liegt (Projekt-Root per `find_project_root`, Pfadaufloesung per `resolve()`); relative Artefaktpfade werden gegen den Projekt-Root aufgeloest. Fehlt die Datei, ist sie leer, nicht lesbar, ausserhalb des Projekts oder ein Symlink, ergibt das `human`, ohne dass `validate_test_output` ueberhaupt aufgerufen wird.
6. Kein aktiver Stop-Lock (`is_stop_locked()`).
7. `green_approved` ist noch nicht gesetzt.

**Wirkung bei `done`.** `green_approved = True`; `record_approval(data, "green", "auto", "GREEN-Artefakt vorhanden", evidence={"artifact": <path des juengsten passenden test_output-Artefakts>})`; `_save_active(data)`. Kein Phasenwechsel: der Uebergang bleibt `workflow.py phase phase6b_adversary` in Step 7 von `50-implement.md`. Es wird keine Marker-Datei `user_approved_validation_<wf>` geschrieben und kein Lock angefasst.

**Post-Implementation-Gate.** In `main()` direkt nach den beiden Phasen-Pruefungen (Bypass-Phasen, nicht gegatete Phasen) und vor dem Lesen von Lock und Marker: `autonomy_mode()` per lazy Import aus `workflow`; bei `"auto"` sofort `allow()`. Damit entsteht im Auto-Modus kein Lock, es gibt kein Batch-Fenster und keinen Block, auch nicht nach 15 Minuten und auch nicht, wenn vor einem Moduswechsel schon ein Lock existiert (er wird ignoriert, nicht geloescht). Jede Ausnahme beim Import oder Lesen ergibt `manual`, also das bisherige Verhalten (fail-closed). Es wird kein Marker gefaelscht.

**Command.** `50-implement.md` Step 6 beginnt mit `python3 .claude/hooks/workflow.py autonomy`. Bei `AUTONOMY=auto`: `workflow.py auto-green` ausfuehren; bei `AUTO_GREEN=done` die Zusammenfassung (Was umgesetzt, Was funktioniert, Qualitaetspruefungen, Auffaelligkeiten) als reine Information ohne Rueckfrage ausgeben und direkt zu Step 7; bei `AUTO_GREEN=human` (oder bei `AUTONOMY=manual`) gilt die bisherige Ausgabe mit `go` und das Warten auf den User. Auffaelligkeiten werden im Auto-Modus nicht zurueckgehalten, sondern in der Zusammenfassung genannt und gehen an den Adversary. `skills/50-implement/SKILL.md` wird mit `python3 scripts/sync_skills.py` neu erzeugt.

**Unveraendert.** `phase_listener.py` (die Phrase `go` wirkt weiter, auch im Auto-Modus), `next_step`/`status_note`, `_validate_transition`, `edit_gate.py`, `bash_gate.py`. Immer menschlich bleiben AMBIGUOUS, zweites BROKEN/Circuit Breaker, Override, Deploy und Stop-Lock.

## Expected Behavior

- **Input:** Aufruf `workflow.py auto-green` am Ende von phase6; Edit/Write in `phase6_implement` durch `post_implementation_gate.py`
- **Output:** `AUTO_GREEN=done` bzw. `AUTO_GREEN=human` plus `REASON=...`, Exit 0; im Auto-Modus kein Block durch das Post-Implementation-Gate
- **Side effects:** Nur bei `done`: `green_approved=True` und ein `approvals`-Eintrag mit `gate=green`, `by=auto`, `evidence`. Bei `human` bleibt die State-Datei byte-identisch. Es wird nie eine Marker-Datei geschrieben.

## Known Limitations

- GREEN wird im Auto-Modus immer automatisch erteilt, auch bei gemeldeten Auffaelligkeiten (PO-Entscheidung). Diese Auffaelligkeiten werden nicht menschlich geprueft; der Ausgleich sind der Adversary-Lauf (Step 8) und die Abschlussmeldung.
- Der Befehl wertet den Inhalt des juengsten `test_output`-Artefakts der Phase mit `qa_gate.py::validate_test_output` aus (PO-Entscheidung). Das belegt, dass die registrierte Datei bestandene Tests zeigt, nicht dass sie echt aus einem Lauf stammt; die Echtheit und die fachliche Pruefung leistet der Adversary.
- Bei einem Moduswechsel mitten in phase6 wird ein bereits vorhandener Lock im Auto-Modus ignoriert und bleibt liegen, bis der Workflow endet oder zurueck nach `manual` gewechselt wird.
- Gelesen wird die wirksame Config des Projekts (`trusted_config()`); eine Worktree-lokale oder `settings.local.json`-Abweichung wirkt nicht.
- Ein Agent kann ein frisches, plausibles Testprotokoll fabrizieren; Alters-, Groessen- und FAILED/ERROR-Pruefung erschweren das nur. Die Echtheit prueft der Adversary.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Mit `autonomy.mode: auto` setzt `workflow.py auto-green` nach vorhandenem GREEN-Artefakt `green_approved` und protokolliert die Freigabe in `approvals`, ohne dass der User `go` tippt
- [ ] Mit `autonomy.mode: auto` blockiert das Post-Implementation-Gate in phase6 keinen Edit mehr; mit `manual` verhaelt es sich unveraendert
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen, `python3 scripts/sync_skills.py --check` ohne Drift)

## Acceptance Criteria

- **AC-1:** Given `autonomy.mode: auto` in der wirksamen Config, ein Workflow in `phase6_implement` mit `red_test_done`, einem `test_output`-Artefakt der Phase `phase6_implement`, ohne Stop-Lock und ohne `green_approved` / When `workflow.py auto-green` laeuft / Then steht auf stdout `AUTO_GREEN=done` (plus `REASON=`-Zeile), der Exit-Code ist 0, `green_approved` ist `true` und die Phase ist weiterhin `phase6_implement`
  - Test: tests/test_auto_green_471.py::test_auto_green_happy_path_sets_green_approved

- **AC-2:** Given derselbe Happy-Path-Zustand / When `auto-green` laeuft / Then enthaelt `approvals` genau einen neuen Eintrag mit `gate="green"`, `by="auto"`, `mode="auto"`, ISO-Zeitstempel in `at` und `evidence` mit dem Pfad des `test_output`-Artefakts
  - Test: tests/test_auto_green_471.py::test_auto_green_records_approval_with_evidence

- **AC-3:** Given `autonomy.mode: manual` bzw. kein `autonomy`-Abschnitt, sonst Happy-Path-Zustand / When `auto-green` laeuft / Then lautet die Ausgabe `AUTO_GREEN=human`, der Exit-Code ist 0 und die State-Datei ist byte-identisch
  - Test: tests/test_auto_green_471.py::test_human_in_manual_mode_state_unchanged

- **AC-4:** Given Auto-Modus, aber Phase ungleich `phase6_implement` (z. B. `phase5_tdd_red`, `phase6b_adversary`) / When `auto-green` laeuft / Then `AUTO_GREEN=human`, Exit 0 und State byte-identisch
  - Test: tests/test_auto_green_471.py::test_human_in_wrong_phase

- **AC-5:** Given Auto-Modus in `phase6_implement` ohne `red_test_done` / When `auto-green` laeuft / Then `AUTO_GREEN=human`, Exit 0 und State byte-identisch
  - Test: tests/test_auto_green_471.py::test_human_without_red_test_done

- **AC-6:** Given Auto-Modus in `phase6_implement` mit `red_test_done`, aber ohne `test_output`-Artefakt der Phase `phase6_implement` (nur ein RED-Artefakt der Phase `phase5_tdd_red` oder ein Artefakt anderen Typs) / When `auto-green` laeuft / Then `AUTO_GREEN=human`, Exit 0 und State byte-identisch
  - Test: tests/test_auto_green_471.py::test_human_without_green_artifact

- **AC-7:** Given Happy-Path-Zustand bei aktivem Stop-Lock / When `auto-green` laeuft / Then `AUTO_GREEN=human`, Exit 0 und State byte-identisch
  - Test: tests/test_auto_green_471.py::test_human_when_stop_locked

- **AC-8:** Given Happy-Path-Zustand mit bereits gesetztem `green_approved` / When `auto-green` laeuft / Then `AUTO_GREEN=human`, Exit 0, State byte-identisch und kein zweiter `approvals`-Eintrag
  - Test: tests/test_auto_green_471.py::test_human_when_already_green_approved

- **AC-9:** Given `settings.local.json` mit `autonomy.mode: auto`, aber die wirksame `config.yaml` ohne Auto-Modus / When `auto-green` laeuft / Then `AUTO_GREEN=human` und State byte-identisch, weil der Modus nur aus `trusted_config()` kommt
  - Test: tests/test_auto_green_471.py::test_settings_local_auto_has_no_effect

- **AC-10:** Given ein kaputter State, eine nicht lesbare Config oder ein fehlender aktiver Workflow / When `auto-green` laeuft / Then `AUTO_GREEN=human`, Exit 0 und es wird nichts veraendert
  - Test: tests/test_auto_green_471.py::test_broken_inputs_fail_closed

- **AC-11:** Given Auto-Modus und ein Workflow in `phase6_implement` ohne Lock / When `post_implementation_gate.py` einen Code-Edit prueft, auch wenn `auto-green` nie lief / Then wird der Edit erlaubt (Exit 0) und es wird keine Datei `pending_validation_<wf>.json` angelegt
  - Test: tests/test_auto_green_471.py::test_gate_auto_mode_creates_no_lock

- **AC-12:** Given Auto-Modus und ein Lock, der aelter als das Batch-Fenster ist (mehr als 15 Minuten), ohne Freigabe-Marker / When `post_implementation_gate.py` einen Code-Edit prueft / Then wird der Edit erlaubt (kein Block), und der vorhandene Lock bleibt unveraendert liegen
  - Test: tests/test_auto_green_471.py::test_gate_auto_mode_no_block_after_window_with_existing_lock

- **AC-13:** Given `autonomy.mode: manual`, ein Lock aelter als das Batch-Fenster und kein Marker / When `post_implementation_gate.py` einen Code-Edit prueft / Then blockt es wie bisher (Exit 2); ebenso legt der erste Edit ohne Lock weiterhin den Lock an
  - Test: tests/test_auto_green_471.py::test_gate_manual_mode_unchanged

- **AC-14:** Given Auto-Modus, aber `autonomy_mode()` scheitert (Import- oder Lesefehler) / When `post_implementation_gate.py` einen Edit prueft / Then gilt das Verhalten von `manual` (fail-closed)
  - Test: tests/test_auto_green_471.py::test_gate_falls_back_to_manual_on_error

- **AC-15:** Given ein Workflow in `phase6_implement` und die Nachricht `go` im Listener / When `phase_listener.py` laeuft, im Modus `manual` wie im Modus `auto` / Then setzt er weiterhin `green_approved=True` und schreibt den Marker, sofern ein Lock existiert
  - Test: tests/test_auto_green_471.py::test_listener_go_still_works

- **AC-16:** Given `core/commands/50-implement.md` und `skills/50-implement/SKILL.md` / When ihr Text geprueft wird / Then enthalten beide in Step 6 die Verzweigung (`workflow.py autonomy`, `AUTONOMY=auto`, `workflow.py auto-green`, `AUTO_GREEN=done`, `AUTO_GREEN=human`) und weiterhin die manuelle Freigabe mit `go`; `python3 scripts/sync_skills.py --check` meldet keinen Drift
  - Test: tests/test_auto_green_471.py::test_command_and_skill_branch_on_autonomy

- **AC-17:** Given ein `auto-green`-Lauf mit `done` / When anschliessend das Projektverzeichnis geprueft wird / Then existiert keine Datei `.claude/user_approved_validation_<wf>` und kein neuer Lock; `post_implementation_gate.py` und `workflow.py` schreiben diesen Marker im Auto-Pfad nie (kein gefaelschter Marker)
  - Test: tests/test_auto_green_471.py::test_no_marker_file_written

- **AC-18:** Given Happy-Path-Zustand, aber das juengste `test_output`-Artefakt der Phase `phase6_implement` ist eine regulaere Datei im Projekt mit realistischer pytest-Ausgabe und Summary `3 passed` / When `auto-green` laeuft / Then `AUTO_GREEN=done`, Exit 0 und `green_approved` ist `true`
  - Test: tests/test_auto_green_471.py::test_artifact_with_3_passed_gives_done

- **AC-19:** Given Happy-Path-Zustand, aber das juengste `test_output`-Artefakt der Phase zeigt `1 failed, 2 passed` (auch wenn ein aelteres Artefakt gruen war) / When `auto-green` laeuft / Then `AUTO_GREEN=human`, Exit 0 und State byte-identisch
  - Test: tests/test_auto_green_471.py::test_artifact_with_failures_gives_human

- **AC-20:** Given Happy-Path-Zustand, aber das juengste `test_output`-Artefakt enthaelt kein Testergebnis (leere Datei, beliebiger Text ohne Testausgabe) oder die Datei fehlt auf der Platte / When `auto-green` laeuft / Then `AUTO_GREEN=human`, Exit 0 und State byte-identisch
  - Test: tests/test_auto_green_471.py::test_artifact_without_result_empty_or_missing_gives_human

- **AC-21:** Given Happy-Path-Zustand, aber der Pfad des juengsten `test_output`-Artefakts liegt ausserhalb des Projekts (absoluter Pfad oder `..`) oder ist ein Symlink (auch auf eine gruene Datei im Projekt) / When `auto-green` laeuft / Then `AUTO_GREEN=human`, Exit 0, State byte-identisch und die Datei wird nicht gelesen
  - Test: tests/test_auto_green_471.py::test_artifact_outside_project_or_symlink_gives_human

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden); Config-Varianten per temporaerer `config.yaml` im Testprojekt, CLI-Tests als Subprozess mit `OPENSPEC_ACTIVE_WORKFLOW`, Gate-Tests als Subprozess mit Hook-Input auf stdin, State-Vergleich per Bytes vor/nach dem Aufruf:

- `pytest tests/test_auto_green_471.py`
- Regressionslauf: `pytest tests/` (insbesondere die Tests zu #469, #470 und zum Post-Implementation-Gate)
- Skill-Drift: `python3 scripts/sync_skills.py --check`
- Syntaxpruefung: `python3 -m py_compile core/hooks/workflow.py core/hooks/post_implementation_gate.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Weichenstellung (Freigaben im Auto-Modus automatisieren, Config-Schalter, `approvals`-Protokoll, Modus nur aus `trusted_config()`) ist bereits in #469 und #470 gefallen. Diese Aenderung wendet das Muster auf ein weiteres Gate an: additiv, fail-closed, ohne neue Hook-Registrierung und ohne Migrationspfad, durch `autonomy.mode: manual` voll reversibel. Eine neue grundsaetzliche Architekturentscheidung entsteht dabei nicht.

## Changelog

- 2026-10-28: Initial spec created
- 2026-10-28: PO-Entscheidung ergaenzt: `auto-green` gibt nur frei, wenn das juengste `test_output`-Artefakt der Phase `phase6_implement` inhaltlich bestandene Tests zeigt (Auswertung per `qa_gate.py::validate_test_output`, Datei nur regulaer und innerhalb des Projekts); neue AC-18 bis AC-21
- Kritische Anmerkung: Die Inhaltspruefung belegt nur, dass die registrierte Datei gruene Testausgabe enthaelt, nicht dass sie aus einem echten Lauf stammt (ein Agent kann Text in eine Datei schreiben und registrieren). Dagegen helfen die Pfadregeln (regulaer, im Projekt) nur teilweise; die Echtheit bleibt Aufgabe des Adversary-Laufs. Zudem erkennt `validate_test_output` mit `trusted=True` keine zu kleinen oder alten Dateien mehr; Test-Fixtures muessen deshalb realistische Runner-Ausgabe sein (mindestens zwei erkannte Testmuster), sonst meldet die Auswertung "Doesn't look like test output".
