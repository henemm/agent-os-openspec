---
entity_id: feat-kontext-haushalt
type: feature
created: 2026-11-06
updated: 2026-11-06
status: draft
version: "1.0"
tags: [token, context, hooks, workflow, ship]
workflow: feat-kontext-haushalt
---

# Kontext-Haushalt: früher schneiden, Nachschlagen abgeben, Befehle bündeln

## Approval

- [ ] Approved

## Purpose

Eine Token-Analyse nach Kategorien zeigt: 70–75 % des Wiederlesens entstehen in Schritten mit
über 100.000 Token Kontext, ein Schritt mit 200k kostet rund das Fünffache eines Schritts mit 40k.
Das Framework soll Sitzungen deshalb früher schneiden lassen, Nachschlagefragen an Teilagenten
abgeben, mehrere Befehle in einem Aufruf bündeln und die Lese- und Steuerungsdisziplin
dokumentieren. Alles ist Auskunft und Konvention, kein neues Gate.

## Source

- **File:** `core/hooks/post_bash.py` — Kontextmessung und Hinweis
- **File:** `core/hooks/hook_utils.py` — `context_tokens_from_transcript`
- **File:** `core/hooks/workflow.py` — Unterbefehle `context` und `batch`
- **File:** `scripts/ship.py` — pushen, PR anlegen, CI abwarten, optional mergen

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `config.yaml` → `context_budget` | Konfiguration | `enabled` und `clear_threshold_tokens` (Default 100000) |
| `core/hooks/config_loader.py::PLUGIN_CONFIG_KEYS` | bestehende Liste | `context_budget` muss als Plugin-Schlüssel klassifiziert sein |
| `scripts/sync_skills.py` | Generator | Skills werden aus `core/commands/` regeneriert; `.claude/scripts/` löst im Plugin nach `<root>/scripts` auf |
| `setup.py` | Installer | Kopiert `ship.py` nach `.claude/scripts/`, ergänzt die Konsumenten-`CLAUDE.md`-Vorlage |
| `AUTO_CLEAR=on` (Auto-/clear, #467) | bestehender Mechanismus | Vorbild für das Verhalten der Phasen-Befehle bei `CONTEXT_CUT=on` |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/hook_utils.py` | MODIFY | Messung der Kontextgröße aus dem Transcript, Stufenlogik, Zustandsdatei je Sitzung |
| `core/hooks/post_bash.py` | MODIFY | Misst nach Bash-Aufrufen, gibt `additionalContext` ab der Schwelle aus |
| `core/hooks/workflow.py` | MODIFY | Neue Unterbefehle `context` und `batch` |
| `core/hooks/config_loader.py` | MODIFY | `context_budget` in `PLUGIN_CONFIG_KEYS` |
| `scripts/ci_spec_gate.py` | MODIFY | Schlüssel-Liste der CI-Gate-Kopie angeglichen |
| `scripts/ship.py` | CREATE | Eigenständiges Werkzeug, kein Hook |
| `scripts/sync_skills.py` | MODIFY | Pfadauflösung `.claude/scripts/` im Plugin |
| `config.yaml` | MODIFY | Abschnitt `context_budget` |
| `core/commands/10-context.md` bis `60-validate.md` | MODIFY | Kettenabbruch bei `CONTEXT_CUT=on`, Nachschlage-Regel, Verweis auf `ship.py` |
| `skills/*/SKILL.md`, `.claude/commands/*.md` | REGENERATE | Aus den Befehlstexten erzeugt bzw. aufgefrischt |
| `templates/agent_orchestration.md` | MODIFY | Muster „Nachschlage-Agent" |
| `CLAUDE.md`, `README.md`, `setup.py` | MODIFY | Abschnitt „Kontext-Haushalt" (Framework-Doku und Konsumenten-Vorlage) |
| `CHANGELOG.md`, `.gitignore` | MODIFY | Eintrag unter `[Unreleased]`, `.claude/context_usage/` ignoriert |
| `tests/test_kontext_haushalt.py` | CREATE | Tests für alle Punkte |

### Estimated Changes

- Files: 39
- LoC: +1051/-2 (ca.)

## Implementation Details

### 1. Früher schneiden

- `hook_utils.context_tokens_from_transcript` summiert Eingabe, Cache-Aufbau und Cache-Lesen der
  letzten Hauptsitzungs-Antwort aus dem Transcript und liest nur das Dateiende.
- `post_bash.py` merkt die Größe je Sitzung in `.claude/context_usage/<session_id>.json` und gibt
  ab `context_budget.clear_threshold_tokens` einen Hinweis aus, danach je weitere 50.000 Token
  erneut, jede Stufe nur einmal. Der Hinweis fordert auf, den Block abzuschließen, den Stand zu
  sichern und den Turn mit Checkpoint und ❗Du-Zeile zu beenden.
- `workflow.py context` gibt `CONTEXT_TOKENS=` und `CONTEXT_CUT=on|off` aus, immer Exit 0, ohne
  aktiven Workflow.
- Die Befehle `/10-context` bis `/50-implement` rufen bei `on` den Folge-Skill nicht selbst auf.
- Kill-Switch: nur ein ausdrückliches `context_budget.enabled: false` schaltet ab.

### 2. Nachschlagen abgeben

Regel in `/10-context` und `/50-implement`: Fragen der Art „Wo wird X benutzt?" gehen an einen
Explore-Teilagenten, der nur die Antwort zurückgibt. Muster „Nachschlage-Agent" in
`templates/agent_orchestration.md`.

### 3. Befehle bündeln

- `workflow.py batch <cmd> [args] -- <cmd> …` führt mehrere Workflow-Aufrufe nacheinander aus,
  schreibt je Schritt die Kopfzeile `# batch i/n` und stoppt beim ersten Fehler mit dessen Exit-Code.
  Unbekannte, verschachtelte und leere Aufrufe werden abgelehnt.
- `scripts/ship.py` pusht, legt den PR an oder nutzt den offenen, wartet die CI ab und mergt auf
  Wunsch (`--merge squash|merge|rebase`). Ausgabe: `BRANCH= PR= CI= FAILED_CHECKS= MERGED=`.
  Auf dem Default-Branch bricht es ohne `--branch` ab, `--dry-run` zeigt nur den Plan.

### 4. und 5. Gezielt lesen, Steuerungs-Overhead klein halten

Dokumentation im Abschnitt „Kontext-Haushalt" in `CLAUDE.md`, der Konsumenten-Vorlage und im README.

## Definition of Done

- Die Kontextmessung liefert aus einem Transcript die Summe der drei Token-Felder der letzten
  Hauptsitzungs-Antwort, ohne die ganze Datei zu lesen.
- Ab der Schwelle erscheint genau ein Hinweis je Stufe; unterhalb der Schwelle und bei
  abgeschaltetem Schalter erscheint keiner.
- `workflow.py context` und `workflow.py batch` verhalten sich wie beschrieben und verändern
  keinen Workflow-State.
- `scripts/ship.py` schützt den Default-Branch und lässt sich ohne Netz per `--dry-run` prüfen.
- Die Phasen-Befehle brechen die Kette bei `CONTEXT_CUT=on` ab.
- Skills sind regeneriert, `sync_skills.py --check` und `sync_cloud_hooks.py --check` melden
  Synchronität, die volle Testsuite ist grün.
- Der CI-Check `spec-gate` ist ohne Ausstiegs-Trailer grün.

## Expected Behavior

Siehe Acceptance Criteria.

## Acceptance Criteria

- **AC-1:** Given ein Transcript mit mehreren Antworten und Nutzungsangaben / When die Kontextgröße
  gemessen wird / Then ist sie die Summe aus Eingabe, Cache-Aufbau und Cache-Lesen der letzten
  Hauptsitzungs-Antwort, und ein Transcript ohne Nutzungsangaben ergibt keinen Wert.
- **AC-2:** Given eine Sitzung, deren Kontext die Schwelle überschreitet / When nach einem
  Bash-Aufruf gemessen wird / Then gibt `post_bash.py` genau einen Hinweis je Stufe aus (Schwelle,
  dann je 50.000 Token mehr), und unterhalb der Schwelle wird die Größe still festgehalten.
- **AC-3:** Given `context_budget.enabled: false` in der Konfiguration / When nach einem
  Bash-Aufruf gemessen wird / Then erscheint kein Hinweis, ein bloßes Fehlen des Schlüssels
  schaltet dagegen nicht ab.
- **AC-4:** Given gemessene Kontextgrößen mehrerer Sitzungen / When `workflow.py context` läuft /
  Then meldet es für die eigene Sitzung `CONTEXT_TOKENS=` und `CONTEXT_CUT=on` ab der Schwelle,
  `off` darunter, bei fehlender Messung einen unbekannten Wert, immer mit Exit 0 und ohne Workflow.
- **AC-5:** Given mehrere Workflow-Aufrufe getrennt durch `--` / When `workflow.py batch` läuft /
  Then werden sie in Reihenfolge mit Kopfzeile `# batch i/n` ausgeführt, beim ersten Fehler
  stoppt der Lauf mit dessen Exit-Code, und unbekannte, verschachtelte oder leere Aufrufe
  werden abgelehnt.
- **AC-6:** Given der Default-Branch ist ausgecheckt / When `scripts/ship.py` ohne `--branch`
  startet / Then bricht es ab, ohne etwas zu pushen; auf einem Feature-Branch zeigt `--dry-run`
  den Plan ohne Netzzugriff, und die CI-Ergebnisse werden zu einem Gesamtstatus verdichtet.
- **AC-7:** Given die Befehlstexte `/10-context` bis `/50-implement` / When `CONTEXT_CUT=on`
  gemeldet wird / Then rufen sie den Folge-Skill nicht selbst auf, und `/10-context` sowie
  `/50-implement` enthalten die Nachschlage-Regel; `/60-validate` nennt `ship.py` als Ein-Aufruf-Weg.
- **AC-8:** Given `config.yaml`, `templates/agent_orchestration.md` und `.gitignore` / When sie
  gelesen werden / Then enthält die Config den Abschnitt `context_budget`, die Vorlage das Muster
  „Nachschlage-Agent", und `.claude/context_usage/` ist ignoriert.

## Test Plan

Automatisiert in `tests/test_kontext_haushalt.py`, ausführbar mit `python3 -m pytest tests/test_kontext_haushalt.py`.

- AC-1: `test_transcript_tokens_sum_last_main_assistant`, `test_transcript_tokens_read_from_tail`, `test_transcript_tokens_none_without_usage`
- AC-2: `test_context_bucket`, `test_cut_note_keeps_sentence_commas_and_formats_numbers`, `test_post_bash_announces_once_per_bucket`, `test_post_bash_below_threshold_records_silently`, `test_post_bash_other_session_not_confused_by_newest_file`
- AC-3: `test_post_bash_disabled_by_literal_false`, `test_settings_default_literal_false_and_bad_threshold`
- AC-4: `test_workflow_context_unknown_without_measurement`, `test_workflow_context_on_for_session_and_newest_fallback`, `test_workflow_context_off_below_threshold_from_config`
- AC-5: `test_batch_runs_steps_in_order`, `test_batch_stops_at_first_failure_with_its_exit_code`, `test_batch_rejects_unknown_nested_and_empty`
- AC-6: `test_ship_classify_rollup`, `test_ship_refuses_default_branch_without_branch_flag`, `test_ship_dry_run_on_feature_branch_prints_plan`, `test_ship_dry_run_with_branch_flag_from_default`
- AC-7: `test_phase_commands_stop_chain_at_context_cut`, `test_lookup_rule_in_context_and_implement`, `test_validate_offers_ship_script`
- AC-8: `test_config_yaml_has_context_budget_section`, `test_orchestration_template_has_lookup_agent`, `test_gitignore_covers_context_usage`

Zusätzlich die volle Suite sowie `sync_skills.py --check` und `sync_cloud_hooks.py --check`.

## Known Limitations

- Die Kontextgröße stammt aus der letzten Antwort im Transcript und wird nur nach Bash-Aufrufen
  gemessen; sie ist eine Näherung, kein exakter Zählerstand.
- Der Hinweis ist Auskunft. Nichts erzwingt den Schnitt, die Entscheidung bleibt beim Orchestrator.
- Die Änderungen an `core/hooks/` entstanden in einer Cloud-Sitzung per Bash, weil das Edit-Gate
  ohne getipptes „override" blockte. Der Product Owner hat auf Rückfrage entschieden, sie zu behalten.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Erweitert bestehende Bausteine (`post_bash.py`, `workflow.py`, Auto-/clear-Muster) um eine reine Auskunft ohne neue Gate-Art und ohne neues Workflow-State-Feld. `ship.py` liegt unter `scripts/` nach der Konvention für eigenständige Werkzeuge. Reversibel über `context_budget.enabled: false`.

## Changelog

- 2026-11-06: Spec nachgereicht für PR 537, abgeleitet aus Umsetzung und PR-Beschreibung
