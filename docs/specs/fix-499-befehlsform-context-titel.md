---
entity_id: fix-499-befehlsform-context-titel
type: bugfix
created: 2026-10-30
updated: 2026-10-30
status: draft
version: "1.0"
workflow: fix-499-befehlsform-context-titel
tags: [herdr, auto-clear, command-form, context-file, issue-title, e2e]
---

# Auto-/clear: richtige Befehlsform, /10-context mit context_file, robuster Issue-Titel (Issues #499, #500, #492)

## Approval

- [ ] Approved

## Purpose

Drei zusammenhaengende Fehler im Auto-/clear-Pfad werden gemeinsam behoben. (#499) Herdr tippt nach `/clear` den Kurzbefehl `/20-analyse #N`, der ohne installierte Aliase im TUI "Unknown command" ergibt; kuenftig waehlt der Runner beim Senden die Form, die im Projekt bzw. beim Benutzer wirklich existiert, und `/99-reset` wird nie automatisch getippt. (#500) `/10-context` nennt `set-field context_file` nicht, daher scheitert der Phasenwechsel nach `phase2_analyse` mit "context_file not set". (#492) Der Issue-Kurztitel laesst Steuerzeichen durch, vertraut dem Cache ungeprueft, schreibt den Cache ohne Sperre und scheitert im GraphQL-gesperrten Umfeld lautlos.

## Source

- **File:** `core/hooks/herdr_bridge.py` (Befehlsform), `core/hooks/workflow.py` (Titel-Cache), `core/commands/10-context.md` (Befehlstext)
- **Identifier:** `maybe_auto_clear`, `_Runner._prompt`, `_Runner.run`, `run_auto_clear`; `short_title`, `_read_issue_titles`, `cached_issue_title`, `fetch_issue_title`, `_with_issue_title`, `_validate_transition` (context_file), `expected_footer_command`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/herdr_bridge.py` (#467/#495/#497) | module | `maybe_auto_clear` und `_Runner` senden `/clear` und Folgebefehl; `_ac_log`, `_pp_flock`, `_CONTROL_RE` werden wiederverwendet |
| `core/hooks/workflow.py` (#490/#495) | module | `expected_footer_command` bleibt Quelle des Folgebefehls (Kurzform im Vermerk und in der Fusszeile); `short_title`/Cache fuer #492 |
| `core/hooks/footer_gate.py` | module | akzeptiert die Kurzform; unveraendert |
| `core/hooks/hook_utils.py` | module | `atomic_write_json`, `atomic_write_text`, `find_project_root` |
| `core/commands/10-context.md`, `scripts/sync_skills.py` | command/script | Quelle bzw. Generator fuer `skills/10-context/SKILL.md` |
| `scripts/e2e_auto_clear.sh` (#495/#497) | script | echter E2E mit Herdr, Claude-TUI und Plugin |
| `gh` (CLI) | extern | Titelabruf per REST (`gh api`), vom Remote aufgeloest |
| `tests/test_plan_issue_titel_490.py`, `tests/test_autoclear_boundary_495.py` | tests | Regression; Helfer und Stub-Muster als Vorbild |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | MODIFY | Form-Wahl `resolve_command_form` (Alias vs. Plugin-Form) beim Senden in `_Runner`; `/99-reset` wird nie gesendet |
| core/hooks/workflow.py | MODIFY | `short_title` entfernt Steuerzeichen/ANSI; `_with_issue_title` normalisiert Cache-Wert erneut; Cache-Schreiben unter Sperre; `fetch_issue_title` per `gh api`; Fehlerprotokoll `.claude/issue_titles.log` |
| core/commands/10-context.md | MODIFY | Step 3/4: `set-field context_file docs/context/[workflow-name].md` vor `phase phase2_analyse` |
| skills/10-context/SKILL.md | MODIFY (generiert) | per `python3 scripts/sync_skills.py` |
| tests/test_befehlsform_context_titel_499.py | CREATE | Tests zu AC-1 bis AC-13 |
| tests/test_plan_issue_titel_490.py | MODIFY | Stub-`gh` und `_gh_calls`-Pruefungen an `gh api repos/{owner}/{repo}/issues/N` anpassen (wo `issue view` fest verdrahtet ist) |
| scripts/e2e_auto_clear.sh | MODIFY | Szenario A'/E ohne `--command-aliases`-Aufruf und ohne `context_file`-Hilfsregel; neues Szenario F: Plugin-Form ohne Aliase |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] / Fixed (#499, #500, #492) |

### Estimated Changes

- Files: 1 neu, 7 geaendert (+ 1 generiert)
- LoC: +95 Produktion / +300 Test / +50 E2E-Skript
- Risk Level: MEDIUM (Auto-/clear laeuft nur mit Herdr und Opt-in; Titel-Pfad ist fail-open; Befehlstext-Aenderung ist additiv)

## Implementation Details

**#499 Form-Wahl.** Vermerk (`auto_clear_boundary.command`), Fusszeile, `footer_gate` und `_recheck` im Runner bleiben bei der Kurzform (`/20-analyse #N`, eine Quelle: `expected_footer_command`). Erst unmittelbar vor dem Senden in `_Runner.run` bestimmt eine reine Funktion in `herdr_bridge.py` die tatsaechliche Form. Der Name ist der erste Token ohne fuehrenden `/`; Argumente (z. B. `#999`) werden unveraendert angehaengt.
- Kurzform, wenn mindestens einer der vier Orte den Befehl kennt: `<projekt>/.claude/commands/<name>.md`, `<projekt>/.claude/skills/<name>/SKILL.md`, `~/.claude/commands/<name>.md`, `~/.claude/skills/<name>/SKILL.md` (so loest Claude Code Aliase auf).
- Sonst Plugin-Form `/agent-os-openspec:<name> <Argumente>`.
- Bereits qualifizierte Befehle (Name enthaelt `:`) bleiben unveraendert. Das Projekt ist `find_project_root()` des Runners (worktree-lokal), das Home-Verzeichnis `Path.home()` (`HOME`).
- Jede Ausnahme bei der Pruefung ergibt die Plugin-Form (fail-open: die Plugin-Form existiert immer, wenn das Framework als Plugin laeuft).
- Log-Tag und Once-Lock-Schluessel behalten die Kurzform; nur der getippte Text aendert sich.

**`/99-reset` nie.** Ist der Name des Folgebefehls `99-reset` (Fall `no_build_reason`: Folgebefehl `/99-reset #N`), sendet der Runner weder `/clear` noch den Befehl. Die Pruefung steht in `maybe_auto_clear` (Skip-Grund `Workflow-Abschluss bleibt manuell`, vor dem Spawn, damit kein Runner und keine Ankuendigung entsteht) und zusaetzlich defensiv im Runner vor dem ersten Prompt (`_Abort`).

**#500 Befehlstext.** In `core/commands/10-context.md` ergaenzt Step 3 (nach dem Anlegen von `docs/context/[workflow-name].md`) bzw. Step 4 die Zeile `python3 .claude/hooks/workflow.py set-field context_file docs/context/[workflow-name].md` VOR `workflow.py phase phase2_analyse`, mit einem Satz Begruendung (der Phasenwechsel verlangt das Feld). Der Pfad-Praefix `python3 .claude/hooks/workflow.py` entspricht den uebrigen Aufrufen in dieser Datei. Danach `python3 scripts/sync_skills.py`; `skills/10-context/SKILL.md` enthaelt dieselbe Reihenfolge.

**#492 Issue-Titel.**
- `short_title`: nicht druckbare Zeichen und ANSI-Escape-Sequenzen (`ESC[...m` u. a.) werden vor dem Kuerzen entfernt, Zeilenumbrueche/Tabs zaehlen als Leerraum.
- `_with_issue_title`: der Cache-Wert wird erneut durch `short_title` normalisiert; leeres Ergebnis setzt kein `issue_title`.
- Cache-Schreiben (`fetch_issue_title`): Lesen-Aendern-Schreiben unter kurzer exklusiver Sperre `<cache>.lock` (Muster `_pp_flock` aus `herdr_bridge.py`, max. ca. 2 s, danach fail-open ohne Sperre), Cache innerhalb der Sperre frisch lesen und atomar schreiben, damit parallele Abrufe keine Eintraege verlieren.
- Abruf: `gh api repos/{owner}/{repo}/issues/N --jq .title` statt `gh issue view` (GraphQL, im Container mit HTTP 403 gesperrt); `{owner}/{repo}` loest `gh` aus dem Remote des Projektordners (`cwd=find_project_root()`).
- Diagnose: Fehlschlaege (gh fehlt, Exit != 0, Timeout, leerer Titel) schreiben eine Zeile mit Zeitstempel, Issue-Nummer und Grund in `.claude/issue_titles.log` (rotierend, begrenzte Zeilenzahl, Steuerzeichen entfernt). Das Protokollieren und jede andere Ausnahme bleiben fail-open: Rueckgabe None, nie ein Fehler fuer den Aufrufer.

**E2E.** `scripts/e2e_auto_clear.sh`: Szenario A' (Testdouble) und E bekommen kein `setup.py --command-aliases` mehr; fuer A' liegt das Testdouble `20-analyse` unter `.claude/commands` (Kurzform wird gewaehlt, weil es existiert), fuer E fehlt jede Alias-Datei, der Runner tippt `/agent-os-openspec:20-analyse #999`. Die `set-field context_file`-Hilfsregel fuer Szenario E entfaellt, weil `/10-context` das Feld selbst setzt (#500). Neues Szenario F: wie A', aber ohne Testdouble-Alias und ohne installierte Aliase, nur `--plugin-dir`; erwartet, dass `/clear` und danach `/agent-os-openspec:20-analyse #999` im TUI als `❯`-Zeile erscheinen und der Befehl nicht mit "Unknown command" endet.

## Expected Behavior

- **Input:** Auto-/clear ist aktiv, ein Grenz-Phasenwechsel hat einen Vermerk gesetzt, die Fusszeile nennt den Folgebefehl
- **Output:** Nach `/clear` tippt Herdr die Form, die existiert (Kurz-Alias oder Plugin-Form); bei `/99-reset` passiert nichts Automatisches; `/10-context` fuehrt bis `phase2_analyse` ohne Fehlermeldung durch; die Plan-Titelzeile erscheint auch bei gesperrtem GraphQL
- **Side effects:** `.claude/issue_titles.log` bei Titel-Fehlschlaegen; `.claude/issue_titles.json.lock`; Runner-Log wie bisher

## Known Limitations

- Die Alias-Erkennung prueft nur Dateien an den vier genannten Orten; Aliase aus anderen Quellen (z. B. andere Plugins) werden nicht erkannt und fuehren zur Plugin-Form, die dann ebenfalls existiert.
- Die Fusszeile zeigt weiter die Kurzform; ohne Aliase kann der PO sie dort nicht direkt kopieren (Anzeige-Entscheidung, `footer_gate` bleibt unveraendert).
- `gh api` braucht einen aufloesbaren GitHub-Remote und Anmeldung; ohne beides bleibt die Titelzeile weg, der Grund steht im Log.
- Die Sperre ist best effort (fail-open nach ca. 2 s); bei Windows ohne `fcntl` entfaellt sie.
- Echtes TUI-Verhalten ist nur im realen Herdr pruefbar; Szenario E (grosses Modell) kostet Zeit und Geld und laeuft nur per `ONLY=E`.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt (AC-12 durch das E2E-Skript)
- [ ] Szenario F und Szenario E des E2E laufen in einem echten Herdr gruen und der Beleg (Log, Pane-Auszug) liegt vor
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen, insbesondere #467-/#490-/#495-/#497-Tests)

## Acceptance Criteria

- **AC-1:** Given der Folgebefehl `/20-analyse #999` und eine Alias-Datei an mindestens einem der vier Orte (Projekt-commands, Projekt-skills, `~/.claude/commands`, `~/.claude/skills`) / When der Runner den Folgebefehl sendet / Then lautet der getippte Text `/20-analyse #999` (je Ort ein Testfall)
  - Test: tests/test_befehlsform_context_titel_499.py::test_alias_present_in_each_location_sends_short_form

- **AC-2:** Given keine Alias-Datei an den vier Orten / When der Runner den Folgebefehl sendet / Then lautet der getippte Text `/agent-os-openspec:20-analyse #999`; das Argument `#999` bleibt erhalten, ein bereits qualifizierter Befehl bleibt unveraendert
  - Test: tests/test_befehlsform_context_titel_499.py::test_no_alias_sends_plugin_form_keeps_arguments

- **AC-3:** Given ein Fehler bei der Alias-Pruefung (z. B. Home nicht ermittelbar) / When der Runner sendet / Then wird die Plugin-Form gesendet, kein Abbruch
  - Test: tests/test_befehlsform_context_titel_499.py::test_form_check_error_falls_back_to_plugin_form

- **AC-4:** Given Vermerk, Fusszeile und `_recheck` / When die Form gewaehlt wird / Then bleiben `auto_clear_boundary.command`, Log-Tag und Once-Lock-Schluessel in Kurzform (`/20-analyse #N`), nur der Prompt-Text aendert sich
  - Test: tests/test_befehlsform_context_titel_499.py::test_state_log_and_lock_keep_short_form

- **AC-5:** Given der Folgebefehl `/99-reset #N` (Fall `no_build_reason`) und sonst erfuellte Bedingungen / When `maybe_auto_clear` bzw. der Runner laeuft / Then wird weder `/clear` noch `/99-reset` getippt und kein Runner gespawnt; der Skip-Grund steht im Log
  - Test: tests/test_befehlsform_context_titel_499.py::test_99_reset_is_never_typed_automatically

- **AC-6:** Given `core/commands/10-context.md` und `skills/10-context/SKILL.md` / When der Text gelesen wird / Then steht `workflow.py set-field context_file docs/context/[workflow-name].md` vor `workflow.py phase phase2_analyse`, und der Skill stimmt mit der Quelle ueberein (`sync_skills.py` ohne Drift)
  - Test: tests/test_befehlsform_context_titel_499.py::test_context_command_and_skill_set_context_file_before_phase

- **AC-7:** Given ein Titel mit Steuerzeichen und ANSI-Sequenzen (z. B. `\x1b[31mRot\x07 Titel\nzeile`) / When `short_title` laeuft / Then enthaelt das Ergebnis keine Zeichen < 0x20 oder 0x7f und keine ESC-Sequenz; normale Titel (inkl. Umlaute, Kuerzung auf 6 Woerter) bleiben unveraendert
  - Test: tests/test_befehlsform_context_titel_499.py::test_short_title_strips_control_and_ansi

- **AC-8:** Given ein Cache-Eintrag mit Zeilenumbruch oder Steuerzeichen / When `_with_issue_title` den Titel uebernimmt / Then ist `issue_title` erneut normalisiert (einzeilig, ohne Steuerzeichen); ein nach der Normalisierung leerer Wert setzt keinen Titel
  - Test: tests/test_befehlsform_context_titel_499.py::test_cache_value_is_renormalized

- **AC-9:** Given mehrere parallele `fetch_issue_title`-Aufrufe fuer verschiedene Issues / When alle fertig sind / Then enthaelt `issue_titles.json` alle Eintraege (kein Verlust durch Lesen-Aendern-Schreiben); ein nicht erhaeltliches Lock fuehrt nach kurzer Frist zu fail-open ohne Exception
  - Test: tests/test_befehlsform_context_titel_499.py::test_parallel_cache_writes_lose_no_entry

- **AC-10:** Given ein Stub-`gh` / When `fetch_issue_title` laeuft / Then ruft es `gh api repos/{owner}/{repo}/issues/N --jq .title` auf (kein `issue view`) und cached den gekuerzten Titel
  - Test: tests/test_befehlsform_context_titel_499.py::test_fetch_uses_rest_api_call

- **AC-11:** Given ein fehlschlagender Abruf (Exit != 0, leerer Titel, Timeout, `gh` fehlt) / When `fetch_issue_title` laeuft / Then liefert es None ohne Exception und `.claude/issue_titles.log` enthaelt eine Zeile mit Issue-Nummer und Grund; ein nicht schreibbares Log aendert nichts am Ergebnis
  - Test: tests/test_befehlsform_context_titel_499.py::test_fetch_failure_is_logged_fail_open

- **AC-12:** Given echtes Herdr mit Claude-TUI und nur `--plugin-dir` (keine Aliase) / When Szenario F laeuft / Then steht im Log `OK`, im TUI erscheinen `❯ /clear` und `❯ /agent-os-openspec:20-analyse #999`, und es erscheint kein "Unknown command"; Szenario E (echter `10-context`, Opus) erreicht `phase2_analyse` ohne Hilfsregel zum `context_file`
  - Test: scripts/e2e_auto_clear.sh (ONLY="F E")

- **AC-13:** Given die bestehenden Tests / When `pytest tests/test_plan_issue_titel_490.py tests/test_autoclear_boundary_495.py tests/test_autoclear_transition_497.py tests/test_herdr_auto_clear_467.py` laufen (490er-Stub antwortet auf `api`) / Then sind sie gruen
  - Test: Regressionslauf `pytest tests/`

## Test Plan

Muster `tests/test_autoclear_boundary_495.py` (isoliertes Projekt, Stub-Herdr mit protokolliertem `agent prompt`, `HOME` auf ein Wegwerf-Verzeichnis) und `tests/test_plan_issue_titel_490.py` (Stub-`gh` in `PATH`, `GH_LOG`).

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN je eine Alias-Datei an einem der vier Orte WHEN der Runner `/20-analyse #999` sendet THEN ist der Prompt-Text `/20-analyse #999`
- [ ] Test 2: GIVEN keine Alias-Datei WHEN der Runner sendet THEN ist der Prompt-Text `/agent-os-openspec:20-analyse #999`; qualifizierter Befehl unveraendert
- [ ] Test 3: GIVEN Fehler bei der Alias-Pruefung WHEN der Runner sendet THEN Plugin-Form
- [ ] Test 4: GIVEN gewaehlte Plugin-Form WHEN Vermerk, Log-Tag und Lock geprueft werden THEN Kurzform
- [ ] Test 5: GIVEN Folgebefehl `/99-reset #N` WHEN `maybe_auto_clear` laeuft THEN kein Spawn, kein `/clear`, Skip-Grund im Log
- [ ] Test 6: GIVEN `10-context.md` und `SKILL.md` WHEN gelesen THEN `set-field context_file` vor `phase phase2_analyse`
- [ ] Test 7: GIVEN Titel mit ESC-/Steuerzeichen WHEN `short_title` THEN bereinigt; Normalfall unveraendert
- [ ] Test 8: GIVEN Cache-Wert mit Zeilenumbruch WHEN `_with_issue_title` THEN einzeilig
- [ ] Test 9: GIVEN parallele Abrufe (Prozesse) WHEN fertig THEN alle Eintraege im Cache
- [ ] Test 10: GIVEN Stub-`gh` WHEN `fetch_issue_title` THEN Aufruf `api repos/{owner}/{repo}/issues/N --jq .title`
- [ ] Test 11: GIVEN Fehlschlag-Varianten WHEN `fetch_issue_title` THEN None und Log-Zeile

Weitere Laeufe:

- `pytest tests/test_befehlsform_context_titel_499.py`
- Regressionslauf: `pytest tests/` (insbesondere #467, #490, #495, #497)
- Syntaxpruefung: `python3 -m py_compile core/hooks/workflow.py core/hooks/herdr_bridge.py`
- Skills: `python3 scripts/sync_skills.py` und Drift-Pruefung
- E2E: `ONLY="F E" E2E_MODEL=opus bash scripts/e2e_auto_clear.sh`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Fehlerkorrekturen innerhalb bestehender Module ohne neues Gate, neue Hook-Registrierung oder State-Format-Aenderung. Die Form-Wahl liegt bewusst erst beim Senden, damit Vermerk, Fusszeile und `footer_gate` eine einzige Quelle (Kurzform) behalten; alle neuen Pfade sind fail-open und reversibel.

## Changelog

- 2026-10-30: Initial spec created
