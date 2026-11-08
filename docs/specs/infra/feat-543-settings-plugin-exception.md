---
entity_id: feat-543-settings-plugin-exception
type: feature
created: 2026-11-08
updated: 2026-11-08
status: draft
version: "1.0"
workflow: feat-543-settings-plugin-exception
tags: [hooks, edit-gate, settings, plugins]
test_targets:
  - tests/test_edit_gate_settings_plugins_543.py
  - tests/test_edit_gate_orchestrator_files.py
---

# Edit-Gate: enge Ausnahme für Plugin-Einrichtung in der projektlokalen `.claude/settings.json` (#543)

## Approval

- [ ] Approved

## GitHub Issue

- **#543:** `edit_gate.py` Schritt 1b (`ORCHESTRATOR_FILES`) sperrt jede Bearbeitung der
  projektlokalen `.claude/settings.json`. Die PO-Vorgabe vom 2026-11-08 (Plugins und Marketplaces,
  die ein Repo braucht, stehen in dessen `.claude/settings.json`, damit Cloud-Sitzungen sie
  bekommen) lässt sich deshalb in keinem Repo umsetzen. Der Hinweis „update-config Skill
  verwenden" hilft nicht, der Skill läuft in dieselbe Sperre.

## Purpose

Eine Bearbeitung der projektlokalen `.claude/settings.json` wird erlaubt, wenn sie nachweislich
nur die Schlüssel `enabledPlugins` und `extraKnownMarketplaces` ändert. Alles andere in der Datei
(insbesondere `hooks`, `permissions`, `env`, `disableAllHooks`) bleibt so geschützt wie bisher.
Damit kann jede Sitzung die von einem Repo benötigten Plugins selbst eintragen, ohne dass das Gate
seinen Schutz für Hooks und Rechte verliert.

## Source

- **File:** `core/hooks/edit_gate.py` — **Identifier:** Schritt 1b in `main()`, neue Hilfsfunktion
  `_settings_plugin_change_reason(file_path, tool_input)`, Konstante `SETTINGS_PLUGIN_KEYS`
- Nachgestellt: In einem Wegwerf-Projekt mit `.claude/settings.json` = `{}` liefert ein `Write`
  mit `{"enabledPlugins": {"x@y": true}}` heute Exit 2 und „settings.json ist
  Orchestrator-Domäne".

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `edit_gate._simulate_spec_write` | function | Liefert für Write/Edit/MultiEdit alle plausiblen neuen Fassungen (inkl. Variante beim leeren `new_string`, Zeitbudget, Variantenlimit); wirft bei jedem Zweifel. Wird wiederverwendet, keine Änderung. |
| `edit_gate._spec_tool_name` | function | Werkzeug aus dem Payload bzw. den Feldern. Keine Änderung. |
| `edit_gate._has_override_token` | function | Override-Weg (#48). Keine Änderung. |
| Always-Allowed (Schritt 2, `.json`) | rule | Fällt Schritt 1b nicht, wird `.claude/settings.json` dort erlaubt. Die Ausnahme lässt deshalb nur den Block aus, statt selbst `allow()` zu rufen. |

## Scope

- **Affected Files:** `core/hooks/edit_gate.py`, `tests/test_edit_gate_settings_plugins_543.py`
  (neu), `CHANGELOG.md`
- **Estimated Changes:** ca. +190 / -3 LoC (Code ca. 60, Tests ca. 130)
- **Nicht im Scope:** `.claude/settings.local.json` und `.claude/active_workflow` (bleiben voll
  gesperrt); Schreibwege über Bash (`bash_gate.py`); die Restock-Einrichtung selbst (eigener
  Schritt nach Auslieferung, anderes Repo).

## Implementation Details

1. Neue Konstante `SETTINGS_PLUGIN_KEYS = ("enabledPlugins", "extraKnownMarketplaces")`.
2. Neue Funktion `_settings_plugin_change_reason(file_path, tool_input) -> str | None`:
   gibt `None` zurück, wenn die Ausnahme greift, sonst einen kurzen Grund (für die Meldung).
   Jeder Fehler oder Zweifel ergibt einen Grund, nie `None` (fail-closed):
   - Pfad: Dateiname `settings.json`, Elternordner `.claude` — für den angegebenen UND den
     aufgelösten Pfad; ein Symlink wird nicht ausgenommen.
   - Bisheriger Inhalt: existiert die Datei, wird sie gelesen und streng geparst (doppelte
     Schlüssel auf jeder Ebene = Grund), muss ein JSON-Objekt sein. Existiert sie nicht, ist nur
     `Write` zulässig, bisheriger Inhalt gilt als `{}`.
   - Neue Fassungen: über `_simulate_spec_write` (bzw. bei neuer Datei direkt `content`). JEDE
     Fassung muss streng geparst ein JSON-Objekt sein; `enabledPlugins` (falls vorhanden) ein
     Objekt mit Text-Schlüsseln und Wahrheitswerten (`true`/`false`); `extraKnownMarketplaces`
     (falls vorhanden) ein Objekt, dessen Werte Objekte sind.
   - Vergleich: alle Schlüssel außer den zwei erlaubten müssen in alter und neuer Fassung gleich
     vorhanden/fehlend und gleich sein. Verglichen wird kanonisch serialisiert
     (`json.dumps(..., sort_keys=True)`), damit `1`, `1.0` und `true` nicht als gleich gelten.
3. Schritt 1b in `main()`: Für `settings.json` wird zuerst `_settings_plugin_change_reason`
   geprüft. Ergibt sie `None`, wird der Block übersprungen (weiter zu Schritt 2 → Always-Allowed).
   Sonst unverändert: gültiger Override-Token gibt frei (#48), ansonsten Block. Die Prüfung steht
   vor dem Token, damit eine erlaubte Plugin-Änderung keinen Override-Token verbraucht.
4. Meldung bei `settings.json`: nennt die Ausnahme („nur `enabledPlugins` und
   `extraKnownMarketplaces`") und den Grund, warum sie hier nicht greift. Der wirkungslose Hinweis
   auf den update-config-Skill entfällt und wird durch den gangbaren Ausweg ersetzt (User tippt
   „override"). Für `settings.local.json` und `active_workflow` bleibt die Meldung bis auf diesen
   Hinweis gleich.

## Expected Behavior

- **Input:** Edit/Write/MultiEdit auf `<projekt>/.claude/settings.json`
- **Output:** Exit 0, wenn nur `enabledPlugins`/`extraKnownMarketplaces` sich ändern und die
  Werte die erwartete Form haben; sonst Exit 2 mit Meldung, die die Ausnahme und den Grund nennt.
- **Side effects:** keine; ein vorhandener Override-Token wird bei erlaubter Plugin-Änderung nicht
  verbraucht.

## Known Limitations

- Die Ausnahme prüft die Form der zwei Schlüssel, nicht, ob Plugin oder Marketplace existieren
  oder vertrauenswürdig sind. Ein Plugin bringt eigene Hooks mit; das Eintragen eines fremden
  Plugins ist also eine inhaltliche Entscheidung, die das Gate nicht trifft. Verworfene
  Alternative: Allowlist der Marketplaces in `config.yaml` — mehr Konfiguration ohne
  Sicherheitsgewinn, da die Allowlist ihrerseits von derselben Sitzung pflegbar wäre.
- Schreibwege über Bash sind nicht Teil dieser Änderung.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Eine Sitzung kann in einem Projekt ohne `.claude/settings.json` die Datei mit
      `enabledPlugins` und `extraKnownMarketplaces` anlegen (AC-1) und in einer bestehenden Datei
      diese Schlüssel ergänzen (AC-2)
- [ ] Jede Änderung an anderen Schlüsseln bleibt ohne Override gesperrt (AC-3 bis AC-5)
- [ ] Der Override-Weg (#48) und die Sperre von `settings.local.json` sind unverändert (AC-7, AC-8)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given ein Projekt ohne `.claude/settings.json` / When `Write` mit nur
  `enabledPlugins` und `extraKnownMarketplaces` / Then Exit 0.
  - Test: `tests/test_edit_gate_settings_plugins_543.py::test_create_with_plugin_keys_only_allowed`
- **AC-2:** Given eine bestehende `settings.json` mit `hooks` und `permissions` / When `Edit` bzw.
  `MultiEdit` bzw. `Write` nur `enabledPlugins`/`extraKnownMarketplaces` ergänzt oder ändert und
  alles andere gleich lässt / Then Exit 0.
  - Test: `tests/test_edit_gate_settings_plugins_543.py::test_existing_file_plugin_change_allowed`
- **AC-3:** Given eine bestehende `settings.json` / When die neue Fassung einen Hook, eine
  Permission, eine Env-Variable oder `disableAllHooks` ergänzt oder ändert / Then Exit 2.
  - Test: `tests/test_edit_gate_settings_plugins_543.py::test_other_key_change_blocked`
- **AC-4:** Given eine bestehende `settings.json` mit `hooks` / When die neue Fassung einen
  Schlüssel außerhalb der zwei erlaubten entfernt, oder eine neue Datei andere Schlüssel enthält /
  Then Exit 2.
  - Test: `tests/test_edit_gate_settings_plugins_543.py::test_other_key_removed_or_new_file_extra_key_blocked`
- **AC-5:** Given eine `settings.json` / When die neue Fassung kaputtes JSON ist, kein Objekt ist,
  `enabledPlugins` bzw. `extraKnownMarketplaces` keine Objekte (bzw. keine Wahrheitswerte /
  Objekt-Werte) enthalten, doppelte Schlüssel hat, oder die bisherige Datei kaputt ist / Then Exit 2.
  - Test: `tests/test_edit_gate_settings_plugins_543.py::test_malformed_or_non_object_blocked`
- **AC-6:** Given eine gesperrte Bearbeitung der `settings.json` / When der Block greift / Then
  nennt die Meldung die Ausnahme (`enabledPlugins`, `extraKnownMarketplaces`).
  - Test: `tests/test_edit_gate_settings_plugins_543.py::test_block_message_names_exception`
- **AC-7:** Given ein gültiger Override-Token / When eine Änderung an `hooks` / Then Exit 0
  (unverändert, #48); bei einer erlaubten Plugin-Änderung bleibt der Token erhalten.
  - Test: `tests/test_edit_gate_settings_plugins_543.py::test_override_path_unchanged`
- **AC-8:** Given `.claude/settings.local.json` / When `Write` mit nur `enabledPlugins` / Then
  Exit 2 (Ausnahme gilt nur für `settings.json`); ein Symlink `.claude/settings.json` auf eine
  andere Datei wird nicht ausgenommen.
  - Test: `tests/test_edit_gate_settings_plugins_543.py::test_exception_limited_to_settings_json`

## Test Plan

Hermetische Subprozess-Tests nach Vorlage `tests/test_edit_gate_orchestrator_files.py`
(Fake-HOME, Fake-Projekt mit `.git`, `CLAUDE_PROJECT_DIR`, Payload mit `tool_name`):

- `pytest tests/test_edit_gate_settings_plugins_543.py` (AC-1 bis AC-8)
- Regression: `pytest tests/ -q`, insbesondere `tests/test_edit_gate_orchestrator_files.py`
- Echter Durchlauf: nach dem Merge die Restock-Einrichtung (`enabledPlugins`
  `agent-os-openspec@henemm-private`, Marketplace `henemm/agent-os-openspec`) mit dem echten Gate

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Ausnahme bleibt im bestehenden Muster des Edit-Gates: Der neue Inhalt wird
  wie beim Spec-Freeze (#439) simuliert und gegen den alten verglichen, jeder Zweifel sperrt. Kein
  neuer Hook, keine neue Konfiguration. Verworfen: eigene Allowlist für Marketplaces (siehe Known
  Limitations) und eine Freigabe über den update-config-Skill (der Skill schreibt über dieselben
  Werkzeuge und kann nicht vom Gate unterschieden werden).

## Changelog

- 2026-11-08: Initial spec created
