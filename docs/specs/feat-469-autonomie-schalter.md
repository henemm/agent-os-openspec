---
entity_id: feat-469-autonomie-schalter
type: feature
created: 2026-10-28
updated: 2026-10-28
status: draft
version: "1.0"
workflow: feat-469-autonomie-schalter
tags: [autonomie, config, workflow, approvals]
---

# Autonomie-Schalter und Freigabe-Protokoll (Issue #469)

## Approval

- [ ] Approved

## Purpose

Teil A von #468: Ein Konfigurationsschalter `autonomy.mode` (`manual` | `auto`) und ein Freigabe-Protokoll `approvals` im Workflow-State bilden die Grundlage, auf der B (#470), C (#471) und D (#472) spaeter Freigaben automatisieren koennen. Diese Aenderung fuehrt nur Schalter und Protokoll ein und aendert kein bestehendes Gate-Verhalten.

## Source

- **File:** `core/hooks/workflow.py`
- **Identifier:** `autonomy_mode`, `record_approval`, `cmd_autonomy`, `_new_workflow`, `cmd_status`, `_SET_FIELD_PROTECTED`, `COMMANDS`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/config_loader.py` | module | `load_config()` liefert die Config (Haupt-Repo-`config.yaml` plus `settings.local.json`); `PLUGIN_CONFIG_KEYS` um `autonomy` erweitern |
| `scripts/ci_spec_gate.py` | module | `_FALLBACK_PLUGIN_KEYS` ist eine Kopie von `PLUGIN_CONFIG_KEYS` und muss `autonomy` ebenfalls enthalten |
| `tests/test_app_config_yaml_372.py` | test | Drift-Test zwischen `PLUGIN_CONFIG_KEYS` und `_FALLBACK_PLUGIN_KEYS` muss gruen bleiben |
| `core/hooks/workflow.py` | module | `_new_workflow`, `cmd_status`, `_SET_FIELD_PROTECTED`, `COMMANDS`; `cmd_observable_surface` als Vorbild fuer Statuszeilen-Ausgabe `KEY=wert` mit Exit 0 |
| `docs/context/feat-468-autonomie-modus.md` | doc | Gesamtanalyse, Gate-Inventar und PO-Entscheidungen zu #468 |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| config.yaml | MODIFY | Neuer Abschnitt `autonomy:` mit `mode: manual` und erklaerendem Kommentar |
| core/hooks/config_loader.py | MODIFY | `autonomy` in `PLUGIN_CONFIG_KEYS` |
| scripts/ci_spec_gate.py | MODIFY | `autonomy` in `_FALLBACK_PLUGIN_KEYS` |
| core/hooks/workflow.py | MODIFY | `autonomy_mode()`, `record_approval(...)`, `cmd_autonomy`, `"approvals": []` in `_new_workflow`, `approvals` in `_SET_FIELD_PROTECTED`, Anzeige in `cmd_status`, Eintrag `autonomy` in `COMMANDS` |
| tests/test_autonomy_schalter_469.py | CREATE | Tests zu allen Acceptance Criteria |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 5 geaendert
- LoC: +70 Produktion / +200 Test

## Implementation Details

**Schalter.** `autonomy_mode() -> str` in `workflow.py` liest ausschliesslich ueber `config_loader.load_config()` den Wert `autonomy.mode`. Nur der exakte Literal-String `"auto"` ergibt `"auto"`; jeder andere Wert (`"AUTO"`, `" auto"`, `True`, `1`, `"yes"`, `None`, fehlender Abschnitt, falscher Typ des Abschnitts) und jede Ausnahme beim Laden ergibt `"manual"`. Es gibt keinen Trimmen- oder Lowercase-Pfad: Fail-closed, damit eine Tippfehler-Config nie versehentlich automatisiert. Die Funktion wirft nie. B, C, D und `post_implementation_gate` importieren sie spaeter von dort.

**CLI.** `workflow.py autonomy` (`cmd_autonomy`) druckt genau eine Zeile `AUTONOMY=<mode>` auf stdout und endet immer mit Exit 0, auch wenn `autonomy_mode()` oder der Druck intern scheitert (dann `AUTONOMY=manual`). Der Befehl braucht keinen aktiven Workflow (kein `_read_active()`), Vorbild ist `cmd_observable_surface`.

**Protokoll.** `_new_workflow` legt `"approvals": []` an. `record_approval(data, gate, by, reason, evidence=None)` haengt an `data["approvals"]` einen Eintrag mit den Schluesseln `gate`, `by`, `mode` (aktueller `autonomy_mode()`), `at` (ISO-Zeit), `reason`, `evidence` an (legt die Liste per `setdefault` an, falls ein aelterer State sie nicht hat) und gibt den Eintrag zurueck. Sie speichert nicht selbst; der Aufrufer ruft wie bisher `_save_active`. Genutzt wird sie erst von B und C, hier ist sie nur mit Tests abgesichert.

**Schutz.** `approvals` kommt in `_SET_FIELD_PROTECTED` (Hinweis: wird nur von `record_approval` gefuehrt), sodass `set-field approvals ...` blockt. `_reset_approvals_on_backstep` bleibt unveraendert und beruehrt `approvals` nicht: das Protokoll ueberlebt Ruecksprung-Phasen.

**Anzeige.** `cmd_status` zeigt bei nicht leerem `approvals` eine Zeile `Freigaben: <Anzahl>` und je Eintrag eine Zeile mit Gate, Urheber, Modus und Zeit; ohne Eintraege bleibt die Ausgabe unveraendert.

**Config.** `config.yaml` erhaelt `autonomy: mode: manual`. `autonomy` steht in `PLUGIN_CONFIG_KEYS` und `_FALLBACK_PLUGIN_KEYS`, damit der Abschnitt im Plugin-Modus als Config erkannt und im CI-Gate nicht als fremder Schluessel behandelt wird.

**Kein Verhaltenswechsel.** Weder `edit_gate.py`, `bash_gate.py`, `phase_listener.py` noch `post_implementation_gate.py` werden geaendert; `autonomy_mode()` hat in diesem Schritt keinen Aufrufer ausser der CLI.

## Expected Behavior

- **Input:** `config.yaml` -> `autonomy.mode`, Aufruf `workflow.py autonomy`, Aufruf `record_approval(...)` aus Code
- **Output:** `AUTONOMY=manual` bzw. `AUTONOMY=auto`; Eintrag in `approvals` des Workflow-States
- **Side effects:** Neue Workflows enthalten `approvals: []`; `status` zeigt vorhandene Eintraege. Sonst keine.

## Known Limitations

- Der Schalter hat in diesem Schritt keine Wirkung auf Gates; die Wirkung entsteht erst in #470, #471, #472.
- `record_approval` hat in diesem Schritt keinen produktiven Aufrufer.
- Bestehende Workflow-States ohne `approvals` werden nicht migriert; `record_approval` legt die Liste bei Bedarf an, `status` behandelt fehlenden Schluessel als leer.
- Gelesen wird die Config des Haupt-Repos (plus `settings.local.json`); eine Worktree-lokale Abweichung von `config.yaml` wirkt nicht.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] `python3 .claude/hooks/workflow.py autonomy` gibt in einem Projekt ohne `autonomy`-Abschnitt `AUTONOMY=manual` aus, mit `autonomy.mode: auto` gibt es `AUTONOMY=auto` aus
- [ ] Ein neuer Workflow enthaelt `approvals: []`, `set-field approvals` wird abgelehnt, und `status` zeigt eingetragene Freigaben
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen)

## Acceptance Criteria

- **AC-1:** Given eine Config ohne Abschnitt `autonomy` / When `autonomy_mode()` aufgerufen wird / Then liefert sie `"manual"`
  - Test: tests/test_autonomy_schalter_469.py::test_default_manual_without_section

- **AC-2:** Given eine Config mit `autonomy.mode: auto` / When `autonomy_mode()` aufgerufen wird / Then liefert sie `"auto"`
  - Test: tests/test_autonomy_schalter_469.py::test_mode_auto_returns_auto

- **AC-3:** Given eine Config mit `autonomy.mode` gleich `"AUTO"`, `" auto"`, `true`, `1`, `"yes"`, `null` oder `"manual"` bzw. `autonomy` als Nicht-Mapping / When `autonomy_mode()` aufgerufen wird / Then liefert sie jeweils `"manual"`
  - Test: tests/test_autonomy_schalter_469.py::test_other_values_fall_back_to_manual

- **AC-4:** Given `load_config()` wirft eine Ausnahme oder die Config ist syntaktisch kaputt / When `autonomy_mode()` aufgerufen wird / Then liefert sie `"manual"` und wirft nicht
  - Test: tests/test_autonomy_schalter_469.py::test_broken_config_falls_back_to_manual

- **AC-5:** Given ein Projekt mit `autonomy.mode: auto` bzw. ohne Abschnitt / When `workflow.py autonomy` als Subprozess laeuft / Then steht auf stdout genau `AUTONOMY=auto` bzw. `AUTONOMY=manual` und der Exit-Code ist 0
  - Test: tests/test_autonomy_schalter_469.py::test_cli_prints_autonomy_line

- **AC-6:** Given eine kaputte Config oder ein fehlender aktiver Workflow / When `workflow.py autonomy` laeuft / Then ist der Exit-Code 0 und stdout lautet `AUTONOMY=manual`
  - Test: tests/test_autonomy_schalter_469.py::test_cli_exit_zero_on_error

- **AC-7:** Given ein neuer Workflow / When `workflow.py start <name>` laeuft / Then enthaelt die State-Datei `"approvals": []`
  - Test: tests/test_autonomy_schalter_469.py::test_new_workflow_has_empty_approvals

- **AC-8:** Given ein aktiver Workflow / When `workflow.py set-field approvals '[]'` laeuft / Then wird der Aufruf abgelehnt (Exit-Code ungleich 0, Hinweis auf `record_approval`) und der State bleibt unveraendert
  - Test: tests/test_autonomy_schalter_469.py::test_set_field_approvals_blocked

- **AC-9:** Given ein Workflow-State und `autonomy.mode: auto` / When `record_approval(data, "spec", "claude", "Grund", evidence="docs/briefings/x.md")` aufgerufen wird / Then enthaelt `data["approvals"]` genau einen Eintrag mit `gate="spec"`, `by="claude"`, `mode="auto"`, `reason="Grund"`, `evidence="docs/briefings/x.md"` und einem ISO-Zeitstempel in `at`; ohne `evidence` ist der Wert `None`; weitere Aufrufe haengen an, ohne bisherige Eintraege zu aendern
  - Test: tests/test_autonomy_schalter_469.py::test_record_approval_appends_entry

- **AC-10:** Given ein State ohne Schluessel `approvals` (aelterer Workflow) / When `record_approval(...)` aufgerufen wird / Then wird die Liste angelegt und der Eintrag angehaengt
  - Test: tests/test_autonomy_schalter_469.py::test_record_approval_creates_missing_list

- **AC-11:** Given ein Workflow mit mindestens einem Eintrag in `approvals` in `phase6_implement` / When ein Ruecksprung nach `phase3_spec` ausgefuehrt wird / Then sind die Eintraege in `approvals` unveraendert vorhanden, waehrend die uebrigen Freigabe-Marker zurueckgesetzt werden wie bisher
  - Test: tests/test_autonomy_schalter_469.py::test_backstep_keeps_approvals

- **AC-12:** Given ein Workflow mit zwei Eintraegen in `approvals` / When `workflow.py status` laeuft / Then zeigt die Ausgabe die Anzahl und je Eintrag Gate, Urheber, Modus und Zeit; ohne Eintraege entspricht die Ausgabe dem bisherigen Status
  - Test: tests/test_autonomy_schalter_469.py::test_status_shows_approvals

- **AC-13:** Given `config_loader.PLUGIN_CONFIG_KEYS` und `ci_spec_gate._FALLBACK_PLUGIN_KEYS` / When beide verglichen werden / Then enthalten beide `autonomy` und sind identisch (Drift-Test `tests/test_app_config_yaml_372.py` bleibt gruen)
  - Test: tests/test_autonomy_schalter_469.py::test_autonomy_in_both_plugin_key_sets

- **AC-14:** Given die mitgelieferte `config.yaml` / When sie geladen wird / Then enthaelt sie `autonomy.mode` mit dem Wert `manual`
  - Test: tests/test_autonomy_schalter_469.py::test_config_yaml_default_is_manual

- **AC-15:** Given die bestehende Testsuite / When `pytest tests/` laeuft / Then bleiben alle vor dieser Aenderung gruenen Tests gruen, weil `autonomy_mode()` ausser der CLI keinen Aufrufer hat und kein Gate sein Verhalten aendert
  - Test: tests/test_autonomy_schalter_469.py::test_no_gate_imports_autonomy_mode

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden); Config-Varianten per temporaerer `config.yaml` bzw. Monkeypatch von `load_config`, CLI-Tests als Subprozess:

- `pytest tests/test_autonomy_schalter_469.py`
- Drift-Test: `pytest tests/test_app_config_yaml_372.py`
- Regressionslauf: `pytest tests/`
- Syntaxpruefung: `python3 -m py_compile core/hooks/workflow.py core/hooks/config_loader.py scripts/ci_spec_gate.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Rein additiv und fail-closed: ein Config-Schalter mit Default `manual`, ein Protokollfeld und ein Auskunfts-Befehl, ohne Aenderung an Gate-Logik oder Hook-Registrierung und ohne Migrationspfad. Die Entscheidung ist durch Entfernen des Abschnitts voll reversibel; die eigentliche Weichenstellung (Automatisierung von Freigaben) faellt erst in B bis D und wird dort bewertet.

## Changelog

- 2026-10-28: Initial spec created
