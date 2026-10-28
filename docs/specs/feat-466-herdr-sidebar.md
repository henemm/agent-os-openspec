---
entity_id: feat-466-herdr-sidebar
type: feature
created: 2026-10-28
updated: 2026-10-28
status: draft
version: "1.0"
workflow: feat-466-herdr-sidebar
tags: [herdr, sidebar, workflow, utility]
---

# Herdr-Sidebar-Fortschritt (Issue #466)

## Approval

- [ ] Approved

## Purpose

Laeuft Claude Code in einem Herdr-Pane, zeigt die Herdr-Sidebar den Workflow-Stand (Issue, Phase x/8, aktueller Schritt, naechster Befehl) an, ohne dass der User in den Pane wechseln muss. Das neue Utility `herdr_bridge.py` meldet den Stand display-only an Herdr und liefert mit `run_herdr` den generischen Aufruf-Helper, auf dem #467 (Auto-`/clear` via Herdr) aufbaut.

## Source

- **File:** `core/hooks/herdr_bridge.py`
- **Identifier:** `build_report`, `report_workflow`, `clear`, `run_herdr`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/workflow.py` | module | Phasentabellen (`PHASE_NUMBERS`, `TOTAL_PHASES`), `expected_footer_command()`, `issue_number()`; Schreibstellen `_save_active`, `cmd_start`, `cmd_switch`, `complete`, `abandon` |
| `core/hooks/phase_listener.py` | module | Freigabe schreibt `phase4_approved` ueber eigenes `_save_workflow` |
| `core/hooks/session_banner.py` | module | SessionStart-Republish in `main()` |
| `core/hooks/config_loader.py` | module | `load_config()`, `PLUGIN_CONFIG_KEYS` um `herdr` erweitern |
| Herdr-CLI (`$HERDR_BIN_PATH`) | extern, optional | `pane report-metadata` (Herdr >= 0.7.4, Tokens); fehlt es, ist die Bridge ein No-op |
| `tests/conftest.py` | test infra | autouse-Fixture isoliert `HERDR_*` |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | CREATE | Env-/Config-Gate, `build_report(data)`, `report_workflow(data)`, `clear()`, generisches `run_herdr(args, wait=False, timeout=2.0)`; kein Hook, nicht in `hooks.json` |
| core/hooks/workflow.py | MODIFY | Report in `_save_active`, `cmd_start`, `cmd_switch`; Clear in `complete` und `abandon` |
| core/hooks/phase_listener.py | MODIFY | Report am Ende von `_save_workflow` (deckt die Freigabe ab) |
| core/hooks/session_banner.py | MODIFY | Republish in `main()` fuer alle Quellen (startup/resume/clear/compact) |
| core/hooks/config_loader.py | MODIFY | `herdr` in `PLUGIN_CONFIG_KEYS` |
| config.yaml | MODIFY | Abschnitt `herdr:` (`enabled: true`) plus Kommentar mit Sidebar-Beispiel |
| tests/conftest.py | MODIFY | autouse-Fixture entfernt `HERDR_*` aus `os.environ` |
| tests/test_herdr_sidebar_466.py | CREATE | Tests mit Stub-Binary |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |
| CLAUDE.md | MODIFY | Zeile `herdr_bridge.py` in der Tabelle "Wichtige Dateien" |

### Estimated Changes

- Files: 2 neu, 8 geaendert
- LoC: +150 Produktion / +250 Test

## Implementation Details

**Gate.** Die Bridge wird nur aktiv, wenn `HERDR_ENV == "1"`, `HERDR_PANE_ID` nicht leer ist, `HERDR_BIN_PATH` ein absoluter Pfad auf eine ausfuehrbare regulaere Datei ist und `config.yaml` -> `herdr.enabled` nicht `false` ist (Default `true`, Opt-out). Sonst kehrt jede oeffentliche Funktion sofort und ohne Seiteneffekt zurueck.

**Aufruf.** `run_herdr(args, wait=False, timeout=2.0)` startet `[HERDR_BIN_PATH, *args]` per `subprocess.Popen`: kein Shell, `stdin/stdout/stderr=DEVNULL`, `start_new_session=True`, `close_fds=True`. Bei `wait=False` wird nicht auf den Prozess gewartet; bei `wait=True` hoechstens `timeout` Sekunden, danach Kill. Jeder Pfad liegt in `try/except Exception`; es wird nie eine Ausnahme propagiert und nie auf stdout/stderr der aufrufenden Hooks geschrieben. `run_herdr` ist bewusst generisch gehalten, damit #467 es wiederverwenden kann.

**Report.** `report_workflow(data)` ruft `run_herdr` mit `pane report-metadata <HERDR_PANE_ID> --source user:openspec --agent claude --seq <ms-Zeitstempel> --title "<Titel>"` und fuenf `--token name=wert` auf. Der Millisekunden-Zeitstempel als `--seq` macht Reihenfolge-Rennen der detachten Prozesse unschaedlich (Herdr verwirft aeltere Reports).

**Tokens** (Werte auf 80 Zeichen gekuerzt, Control-Chars entfernt):

| Token | Inhalt |
|-------|--------|
| `workflow` | Workflow-Name |
| `issue` | Issue-Nummer (`workflow.issue_number()`), leer wenn keine |
| `phase` | `<Nr>/8`, z. B. `5/8` |
| `step` | Kurzlabel der Phase (Tabelle unten) |
| `next` | `workflow.expected_footer_command()`; ist das Ergebnis Freitext (Freigabe-Phrase), wird `approved` gesetzt |

**Titel:** `#<issue> <phase> <step>` (z. B. `#466 5/8 TDD-RED`); ohne Issue-Nummer `<workflow> <phase> <step>`. Gekuerzt auf 80 Zeichen.

**Mapping-Tabelle:**

| Phase | phase | step |
|-------|-------|------|
| phase1_context | 1/8 | CONTEXT |
| phase2_analyse | 2/8 | ANALYSE |
| phase3_spec | 3/8 | SPEC |
| phase4_approved | 4/8 | APPROVED |
| phase5_tdd_red | 5/8 | TDD-RED |
| phase6_implement | 6/8 | IMPLEMENT |
| phase6b_adversary | 6/8 | ADVERSARY |
| phase7_validate | 7/8 | VALIDATE |
| phase8_complete | (Clear, siehe unten) | (Clear) |

`phase0_idle` und unbekannte Phasen fuehren zu Clear (kein aktiver Workflow-Stand anzuzeigen). Das Kurzlabel DONE gehoert nicht zu den gemeldeten Werten, weil phase8 bewusst ein Clear ausloest.

**Clear.** `clear()` ruft `pane report-metadata <pane> --source user:openspec --agent claude --seq <ms> --clear-title` plus `--clear-token` fuer alle fuenf Tokens auf. Ausgeloest bei `complete`, `abandon`, `phase8_complete`, `phase0_idle` und wenn kein aktiver Workflow aufloesbar ist.

**Einhaengepunkte.** Nicht alle Phasen-Schreibstellen laufen ueber `_save_active`: `cmd_start` schreibt per `_atomic_write` direkt, `complete`/`abandon` archivieren ohne Save, `cmd_switch` setzt nur den Zeiger, `phase_listener` nutzt ein eigenes `_save_workflow`. Deshalb wird je Schreibstelle explizit gemeldet: `_save_active`, `cmd_start`, `cmd_switch` (Report des neuen aktiven Workflows), Clear in `complete`/`abandon`, Report am Ende von `phase_listener._save_workflow`. Die Anzeige-Logik wird nicht dupliziert, sondern aus `workflow.py` gelesen.

**SessionStart.** `session_banner.main()` ruft (nicht `build_output`) nach dem Banner den Republish fuer den aktiven Workflow auf, fuer alle `source`-Werte. Das stellt die Sidebar nach `/clear`, `compact`, Resume und Herdr-Neustart des Panes wieder her.

**Konfiguration.** `config.yaml` erhaelt `herdr: enabled: true` und einen Kommentar mit dem Sidebar-Beispiel (`[ui.sidebar.agents.rows_by_agent]` mit `$phase`, `$step`, `$next`).

**Tests.** `tests/conftest.py` bekommt eine autouse-Fixture, die `HERDR_ENV`, `HERDR_PANE_ID`, `HERDR_BIN_PATH` und `HERDR_SOCKET_PATH` aus `os.environ` entfernt, damit Entwickler in einem Herdr-Pane mit der Testsuite nicht die eigene Sidebar bespielen. Die Tests in `tests/test_herdr_sidebar_466.py` nutzen ein Stub-Binary (Shell-/Python-Skript), das seine argv in eine Datei schreibt, und setzen die Env-Variablen per `monkeypatch`.

## Expected Behavior

- **Input:** Phasenwechsel, Workflow-Start/-Wechsel, Freigabe, Abschluss, Abbruch oder SessionStart in einem Herdr-Pane
- **Output:** Herdr-Sidebar zeigt Titel und Tokens `workflow`, `issue`, `phase`, `step`, `next` des aktiven Workflows; nach Abschluss/Abbruch sind sie geraeumt
- **Side effects:** Pro Zustandswechsel ein detachter, kurzlebiger Prozess `herdr pane report-metadata`. Kein Einfluss auf stdout, Exit-Code oder Laufzeit der Hooks und CLI.

## Known Limitations

- Nach einem Herdr-Server-Restart sind die Token-Metadaten verloren, bis zum naechsten Statewechsel oder SessionStart (Herdr stellt sie nicht wieder her).
- Kein TTL in v1: Stirbt die Session ohne `complete`/`abandon`, bleibt der letzte Stand sichtbar, bis der Pane geschlossen oder ein neuer Report gesendet wird.
- Kein Stop-Hook in v1: Aenderungen am State ausserhalb der genannten Schreibstellen (z. B. manuelles Editieren der JSON-Datei) erscheinen erst beim naechsten Report.
- Rein anzeigend: Die Bridge uebernimmt nicht die State-Autoritaet der offiziellen Herdr-Claude-Integration.
- Herdr ist in der Cloud-Umgebung nicht installiert; Verifikation gegen die echte Sidebar entfaellt, getestet wird gegen ein Stub-Binary.
- Pro Pane sind maximal 32 sequenzierte Quellen erlaubt; die Bridge nutzt genau eine (`user:openspec`).

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] In einem Herdr-Pane zeigt die Sidebar nach Workflow-Start, jedem Phasenwechsel und der Freigabe Titel (`#<issue> <phase> <step>`) und die Tokens `phase`, `step`, `next`; nach `complete`/`abandon` ist die Anzeige leer
- [ ] Ausserhalb von Herdr, mit ungueltigem Binary oder mit `herdr.enabled: false` verhalten sich Hooks und CLI exakt wie vorher (gleiche stdout, gleicher Exit-Code)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen)

## Acceptance Criteria

- **AC-1:** Given ein Herdr-Pane (`HERDR_ENV=1`, gueltige `HERDR_PANE_ID`/`HERDR_BIN_PATH` auf ein Stub-Binary) / When `workflow.py start feat-466-demo` laeuft / Then ruft das Stub genau einen `pane report-metadata <pane>` mit `--source user:openspec`, `--agent claude`, numerischem `--seq`, Titel mit Workflow-Namen und den fuenf Tokens `workflow`, `issue`, `phase`, `step`, `next` auf
  - Test: tests/test_herdr_sidebar_466.py::test_start_reports_workflow_state

- **AC-2:** Given ein aktiver Workflow im Herdr-Pane / When `workflow.py phase phase5_tdd_red` laeuft / Then meldet das Stub den Titel `#466 5/8 TDD-RED` und die Tokens `phase=5/8`, `step=TDD-RED`
  - Test: tests/test_herdr_sidebar_466.py::test_phase_change_reports_title_and_tokens

- **AC-3:** Given ein Workflow in `phase3_spec` im Herdr-Pane / When `phase_listener` die Freigabe verarbeitet und `phase4_approved` schreibt / Then meldet das Stub `phase=4/8`, `step=APPROVED`
  - Test: tests/test_herdr_sidebar_466.py::test_approval_via_phase_listener_reports

- **AC-4:** Given zwei Workflows, von denen A aktiv ist / When `workflow.py switch B` laeuft / Then meldet das Stub Workflow, Phase und Titel von B
  - Test: tests/test_herdr_sidebar_466.py::test_switch_reports_new_active_workflow

- **AC-5:** Given ein aktiver Workflow mit gesetzten Sidebar-Tokens / When `workflow.py complete` bzw. `workflow.py abandon` laeuft / Then ruft das Stub `pane report-metadata` mit `--clear-title` und `--clear-token` fuer alle fuenf Tokens (`workflow`, `issue`, `phase`, `step`, `next`) auf
  - Test: tests/test_herdr_sidebar_466.py::test_complete_and_abandon_clear_all_tokens

- **AC-6:** Given `HERDR_ENV` ist nicht gesetzt (oder `HERDR_PANE_ID` fehlt) / When ein Phasenwechsel, `start` oder `complete` laeuft / Then wird kein Prozess gestartet (Stub-Aufrufdatei bleibt leer) und Exit-Code sowie stdout entsprechen dem Verhalten ohne Bridge
  - Test: tests/test_herdr_sidebar_466.py::test_noop_without_herdr_env

- **AC-7:** Given `HERDR_BIN_PATH` zeigt auf einen nicht existierenden, relativen, nicht ausfuehrbaren oder nicht-regulaeren Pfad (z. B. Verzeichnis) / When ein Phasenwechsel laeuft / Then wird nichts gestartet, es wird keine Ausnahme geworfen und der Exit-Code ist 0
  - Test: tests/test_herdr_sidebar_466.py::test_noop_with_invalid_binary_path

- **AC-8:** Given Herdr-Env ist gueltig, aber `config.yaml` setzt `herdr.enabled: false` / When ein Phasenwechsel laeuft / Then wird das Stub nicht aufgerufen
  - Test: tests/test_herdr_sidebar_466.py::test_kill_switch_disables_reporting

- **AC-9:** Given ein Stub-Binary, das 30 Sekunden schlaeft / When `workflow.py phase ...` laeuft / Then endet der Aufruf in unter 2 Sekunden mit unveraendertem Exit-Code (0) und die Statusdatei enthaelt die neue Phase
  - Test: tests/test_herdr_sidebar_466.py::test_hanging_binary_does_not_block

- **AC-10:** Given ein Stub-Binary, das selbst auf stdout und stderr schreibt und mit Exit-Code 1 endet / When Hooks (`phase_listener`, `session_banner`) und `workflow.py`-Befehle laufen / Then ist deren stdout byte-identisch zum Lauf ohne Herdr-Env (JSON der Hooks bleibt gueltig) und der Exit-Code unveraendert
  - Test: tests/test_herdr_sidebar_466.py::test_stdout_and_exit_code_unchanged

- **AC-11:** Given ein aktiver Workflow und gueltiges Herdr-Env / When `session_banner.main()` fuer `source` startup, resume, clear und compact laeuft / Then erfolgt je Quelle ein Report des aktiven Workflows; ohne aktiven Workflow erfolgt stattdessen ein Clear
  - Test: tests/test_herdr_sidebar_466.py::test_session_start_republishes_for_all_sources

- **AC-12:** Given je ein Workflow in jeder Phase / When `build_report` die Daten abbildet / Then ergibt phase1..phase7 die Paare 1/8 CONTEXT, 2/8 ANALYSE, 3/8 SPEC, 4/8 APPROVED, 5/8 TDD-RED, 6/8 IMPLEMENT, 7/8 VALIDATE, `phase6b_adversary` ergibt 6/8 ADVERSARY, und `phase8_complete` sowie `phase0_idle` fuehren zu Clear statt Report
  - Test: tests/test_herdr_sidebar_466.py::test_phase_mapping_table

- **AC-13:** Given `expected_footer_command()` liefert Freitext (Freigabe-Phrase in phase3_spec) bzw. einen Slash-Befehl / When der Report gebaut wird / Then ist `next=approved` im Freitext-Fall und sonst der Slash-Befehl unveraendert; alle Token-Werte und der Titel sind auf 80 Zeichen gekuerzt
  - Test: tests/test_herdr_sidebar_466.py::test_next_token_freetext_and_length_limit

- **AC-14:** Given ein Workflow ohne Issue-Nummer im Namen / When der Report gebaut wird / Then lautet der Titel `<workflow> <phase> <step>` und der Token `issue` ist leer
  - Test: tests/test_herdr_sidebar_466.py::test_title_without_issue_uses_workflow_name

- **AC-15:** Given die Testsuite laeuft in einem Entwickler-Pane mit gesetzten `HERDR_ENV`, `HERDR_PANE_ID`, `HERDR_BIN_PATH`, `HERDR_SOCKET_PATH` / When ein beliebiger Test startet / Then sind diese Variablen durch die autouse-Fixture in `tests/conftest.py` aus `os.environ` entfernt
  - Test: tests/test_herdr_sidebar_466.py::test_conftest_strips_herdr_env

- **AC-16:** Given Herdr-Env ist gueltig / When `run_herdr(["notification", "show", "x"], wait=False)` aufgerufen wird / Then startet es das Stub ohne Shell mit exakt diesen Argumenten, detached (eigene Session, alle Streams DEVNULL) und gibt sofort zurueck (Basis fuer #467)
  - Test: tests/test_herdr_sidebar_466.py::test_run_herdr_generic_detached_no_shell

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden), alle gegen ein Stub-Binary, das seine argv in eine Datei protokolliert:

- `pytest tests/test_herdr_sidebar_466.py`
- Regressionslauf: `pytest tests/` (insbesondere die bestehenden Tests zu `workflow.py`, `phase_listener.py`, `session_banner.py`)
- Syntaxpruefung: `python3 -m py_compile core/hooks/herdr_bridge.py core/hooks/workflow.py core/hooks/phase_listener.py core/hooks/session_banner.py core/hooks/config_loader.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Rein additives, optionales Utility mit Kill-Switch, das ausschliesslich anzeigt und weder Gate-Logik, State-Format noch Hook-Registrierung veraendert; die Entscheidung ist ohne Migrationspfad voll reversibel (Datei entfernen bzw. `herdr.enabled: false`). Keine strukturelle, schwer umkehrbare Weichenstellung, die eine ADR rechtfertigt.

## Changelog

- 2026-10-28: Initial spec created
