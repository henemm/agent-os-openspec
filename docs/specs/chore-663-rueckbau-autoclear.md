---
entity_id: chore-663-rueckbau-autoclear
type: refactor
created: 2026-11-25
updated: 2026-11-25
status: draft
version: "1.0"
workflow: chore-663-rueckbau-autoclear
tags: [herdr, rueckbau, hooks, epic-649]
---

# Rückbau Auto-/clear per Herdr (Issue #663, Epic #649 Schnitt 4)

## Approval

- [ ] Approved

## Purpose

Das Auto-/clear per Herdr (#467) ist seit #662 (v4.23.0) außer Betrieb, sein Code (Runner, Signale, Grenz-Vermerk `auto_clear_boundary`, Klartext-Vorprüfung, Spawn, Skip-Log, E2E-Skript, Tests) steht aber als toter Code da. Dieser Schnitt löscht ihn vollständig. Herdr-Seitenleiste (#466) und Plan-Pane (#476/#493) bleiben unverändert. Die Entscheidungen aus feat-467, fix-489, fix-495, fix-497, fix-506, fix-597, fix-598 und feat-480 sind durch Epic #649 / #662 abgelöst und entfallen mit #663 vollständig.

## Source

- **File:** `core/hooks/herdr_bridge.py`, `core/hooks/footer_gate.py`, `core/hooks/workflow.py`, `core/hooks/phase_listener.py`, `core/hooks/session_banner.py`, `core/hooks/session_singleton_guard.py`, `hooks/hooks.json`
- **Identifier:** `herdr_bridge.run_auto_clear`, `herdr_bridge.maybe_auto_clear`, `herdr_bridge.record_signal`, `herdr_bridge.run_signal`, `herdr_bridge.spawn_auto_clear`, `workflow._note_transition_boundary`, `workflow._record_auto_clear_boundary`, `workflow.cmd_autoclear`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `herdr_bridge.report_workflow`, `report_active`, `clear` (#466) | function | Seitenleiste; bleibt unverändert |
| `herdr_bridge.open_plan_pane`, `run_plan_pane`, `run_plan_pane_close` (#476/#493) | function | Plan-Pane; bleibt unverändert |
| `herdr_bridge._ac_base`, `_ac_base_for`, `_ac_log`, `AC_LOG_MAX_LINES`, `_hooks_on_path`, `_CONTROL_RE` | helper | vom Plan-Pane mitbenutzt; bleiben, die ersten drei werden zu `_base_dir`, `_base_dir_for`, `_log` umbenannt |
| `workflow.cmd_autoclear` | function | bleibt als Einzeiler `AUTO_CLEAR=off` für gecachte Befehlstexte (Plugin-Pins bis 4.22) |
| `hooks/hooks.json`, `scripts/sync_cloud_hooks` | config / tool | `signal activity`-Einträge entfallen, `plan-pane-close` bleibt |
| `setup.py::_merge_hook_entries` | function | geprüft: ergänzt fehlende Einträge, entfernt nie welche; `herdr_bridge` wird im Copy-Modus gar nicht registriert |
| `klartext_gate.py`, `hook_utils.context_stop_applies` | hook / function | unverändert (seit #662 ohne Herdr) |
| `docs/context/chore-663-rueckbau-autoclear.md` | doc | vollständige Analyse mit Zeilenbereichen |
| Epic #649, #662 | issue | Vorarbeit; Folge: #505, #601, #503 als überholt schließen |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | MODIFY | Auto-/clear-Block (Config, Marker-Prüfung, Spawn, `maybe_auto_clear`, Klartext-Vorprüfung, Kontext-Schnitt-Vermerk, Grenz-Prüfung, Skip-Log, Signale, Runner) und Docstring-Teile löschen; Helfer des Plan-Panes umbenennen; `__main__` kennt nur `plan-pane`/`plan-pane-close`, jeder andere Modus (auch `signal`, `auto-clear`) endet still mit Exit 0 |
| core/hooks/footer_gate.py | MODIFY | `_maybe_auto_clear`, `_discard_boundary`, `_record_stop` samt Aufrufen entfernen; Fußzeilen-Prüfung unverändert |
| core/hooks/workflow.py | MODIFY | `AUTO_CLEAR_BOUNDARIES`, `_boundary_timestamp`, `_note_transition_boundary` (mit allen Aufrufen), `_record_auto_clear_boundary` löschen; `cmd_autoclear` bleibt als Einzeiler `AUTO_CLEAR=off`, Exit 0 |
| core/hooks/phase_listener.py | MODIFY | Signal-Block `input` entfernen |
| core/hooks/session_banner.py | MODIFY | Signal-Block `session` entfernen |
| core/hooks/session_singleton_guard.py | MODIFY | `_record_activity` und Aufruf entfernen |
| hooks/hooks.json | MODIFY | die drei `signal activity`-Einträge löschen (leere Event-Blöcke entfallen), `plan-pane-close` bleibt |
| scripts/e2e_auto_clear.sh | DELETE | 945 Zeilen E2E-Skript, ohne Referenz |
| tests/test_herdr_auto_clear_467.py, test_autoclear_boundary_495.py, test_autoclear_transition_497.py, test_autoclear_kontextschnitt_598.py, test_autoclear_retry_597.py, test_autoclear_eigene_signale_506.py, test_auto_clear_global_480.py | DELETE | 7 reine Auto-/clear-Testdateien, ca. 70 Tests |
| tests/test_befehlsform_context_titel_499.py, test_herdr_plan_deploy_sessionstart_478.py, test_auftrag_551.py, test_context_stop_658.py, test_auto_chain_flat_662.py | MODIFY | zuerst Helfer-Importe aus `test_herdr_auto_clear_467` durch lokale Helfer ersetzen, dann Auto-/clear-Tests entfernen bzw. auf „Symbol existiert nicht" umstellen; `autoclear` → `AUTO_CLEAR=off` bleibt gepinnt |
| tests/test_rueckbau_autoclear_663.py | CREATE | Pinn-Tests zu den ACs |
| CLAUDE.md | MODIFY | Zeilen zu `herdr_bridge` (Architektur, Wichtige Dateien), Stop-Hook-Absatz: ohne Auto-/clear-Beschreibung, nur Halbzeile zur Kompatibilitätsauskunft `autoclear`; netto kürzer |
| README.md, setup.py | MODIFY (nur Versionsmarker/Texte) | Version 4.24.0; Texte ohne Auto-/clear (grep zeigt aktuell keinen Treffer) |
| CHANGELOG.md, .claude-plugin/plugin.json | MODIFY | Eintrag `[4.24.0]` mit Migrationshinweis; Version 4.23.0 → 4.24.0 |
| config.yaml | KEIN CHANGE | Gate-Config, autarker Auftrag; siehe Known Limitations |

### Estimated Changes

- Files: 7 Hooks/Config, 1 Skript und 7 Testdateien gelöscht, 5 Testdateien geändert, 1 neu, ca. 4 Doku-/Versionsdateien (ca. 25 Dateien)
- LoC: Produktcode ca. -1115 (davon `herdr_bridge.py` ca. -920), Skript -945, Tests ca. -3900 netto, neu nur ca. +200 (Pinn-Tests, CHANGELOG); gesamt ca. -6000
- Bewusste Annahme: Das Schnittlimit (4 bis 5 Dateien, ±250 LoC) gilt für Rückbau durch reine Löschung nicht sinnvoll. Der Tech Lead nimmt den Umfang an, weil die Löschung atomar ist: Runner, Signale, Vermerk und Aufrufer hängen aneinander, ein Zwischenstand mit gelöschtem `record_signal` und stehendem Aufrufer wäre in Stop-/Prompt-Hooks (laufen in jedem Konsumentenprojekt) fehleranfälliger als eine Gesamtlöschung. Neue Logik entsteht nicht.
- Risk Level: MEDIUM (Hook-Code in allen Konsumenten; Risiko: versehentlich mitgelöschte Plan-Pane-Helfer, ImportError in Tests, Altregistrierungen)

## Implementation Details

Reihenfolge:

1. **Tests zuerst:** In 499/551/478 die Importe von `AUTO_ON`, `_hook_case`, `WF` aus `test_herdr_auto_clear_467` durch kleine lokale Helfer ersetzen; `test_auto_chain_flat_662` und `test_context_stop_658` (dort `auto_clear_active = boom`) auf die neue Wahrheit umstellen; danach die sieben reinen Auto-/clear-Testdateien und `scripts/e2e_auto_clear.sh` löschen. Kein `pytest.skip`/`xfail`.
2. **Aufrufer entfernen:** `footer_gate`, `phase_listener`, `session_banner`, `session_singleton_guard`, `hooks/hooks.json`.
3. **`herdr_bridge.py`:** Block löschen, Plan-Pane-Helfer umbenennen (`_ac_base` → `_base_dir`, `_ac_base_for` → `_base_dir_for`, `_ac_log` → `_log`), Docstring kürzen, `__main__` auf `plan-pane`/`plan-pane-close` kürzen; unbekannte oder entfernte Modi (`signal`, `auto-clear`) enden still mit Exit 0, weil die Bridge fail-open bleibt.
4. **`workflow.py`:** Vermerk-Funktionen samt Aufrufstellen löschen; `cmd_autoclear` und Tabelleneintrag bleiben (Einzeiler `AUTO_CLEAR=off`), weil alte gecachte Befehlstexte (4.22 und älter) den Befehl rufen und bei „Unbekannter Befehl" mit Exit ≠ 0 die Kette abbräche.
5. **Doku und Version:** CLAUDE.md, CHANGELOG `[4.24.0]`, `plugin.json`, Versionsmarker.
6. **Prüfung:** `python3 -m py_compile` auf alle geänderten Hooks; `grep -rn "record_signal\|maybe_auto_clear\|auto_clear_boundary\|AUTO_CLEAR_BOUNDARIES\|herdr_signals\|auto_clear_active" core hooks scripts tests` bleibt leer, außer in den Pinn-Tests und der Kompatibilitätszeile; `scripts/sync_skills.py --check`, `scripts/sync_cloud_agents.py --check`.

**`setup.py` geprüft:** `_merge_hook_entries` fügt nur fehlende Hook-Einträge hinzu und entfernt nie welche; ein Aufräumen veralteter Registrierungen gibt es nicht. `herdr_bridge.py` wird im Copy-Modus von `setup.py` ohnehin nicht registriert (kein Treffer in `setup.py`), betroffen sind nur Plugin-Modus (`hooks/hooks.json`, wird mit dem Plugin ersetzt) und handgepflegte Registrierungen. Daher: `setup.py` bleibt funktional unverändert (nur Versionsmarker); eine verbliebene Registrierung `herdr_bridge.py signal …` ist harmlos (Known Limitation).

## Expected Behavior

- **Input:** Phasenwechsel, Stop-/Prompt-/SessionStart-Hooks, `workflow.py autoclear`, Aufruf von `herdr_bridge.py` mit `signal …`, Config `herdr.auto_clear`, Env `OPENSPEC_HERDR_AUTO_CLEAR`, Herdr-Pane
- **Output:** `workflow.py autoclear` ergibt genau `AUTO_CLEAR=off`, Exit 0; `herdr_bridge.py signal …` und `auto-clear` enden still mit Exit 0; Seitenleiste und Plan-Pane arbeiten wie bisher
- **Side effects:** kein Code-Pfad startet einen Prozess, der in einen Herdr-Pane tippt; kein Phasenwechsel schreibt `auto_clear_boundary`; es entstehen weder `.claude/herdr_signals/` noch `herdr_auto_clear.log`/`.lock`; vorhandene Altdateien und State-Schlüssel stören nicht, werden nicht mehr gelesen

## Known Limitations

- `config.yaml` bleibt unverändert (Gate-Config, autarker Auftrag): der Schlüssel `herdr.auto_clear` und sein Kommentar bleiben stehen und beschreiben noch ein wirksames Auto-/clear; der Schlüssel und `OPENSPEC_HERDR_AUTO_CLEAR` sind still wirkungslos. Aufräumen ist ein Folge-Issue (siehe Definition of Done).
- `workflow.py autoclear` bleibt als Kompatibilitätszeile; Löschung erst, wenn alle Konsumenten Plugin-Version ≥ 4.23.0 pinnen (aus diesem Repo nicht prüfbar).
- `setup.py --update` entfernt keine veralteten Hook-Registrierungen aus Konsumenten-`settings.json`; ein verbliebenes `herdr_bridge.py signal …` startet nur einen wirkungslosen Prozess mit Exit 0.
- `scripts/e2e_plan_pane.sh` setzt weiter `OPENSPEC_HERDR_AUTO_CLEAR` zurück bzw. schreibt `auto_clear:` in die Config; harmlos, bleibt.
- Historische Specs (feat-467, fix-489/495/497/506/597/598, feat-480) bleiben unverändert und gelten als abgelöst.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Kein Code-Pfad tippt mehr in einen Herdr-Pane; Seitenleiste und Plan-Pane arbeiten unverändert (Seitenleisten- und Plan-Pane-Tests grün)
- [ ] `grep` nach `record_signal`, `maybe_auto_clear`, `auto_clear_boundary`, `herdr_signals` in `core/`, `hooks/`, `scripts/` ist leer (außer Kompatibilitätszeile)
- [ ] CLAUDE.md und README enthalten keine Auto-/clear-Beschreibung mehr (außer der Kompatibilitätshalbzeile); CHANGELOG `[4.24.0]` enthält den Migrationshinweis (entfallene CLI-Modi `signal`/`auto-clear`, `herdr.auto_clear` und `OPENSPEC_HERDR_AUTO_CLEAR` wirkungslos, Altregistrierungen harmlos); Version 4.24.0 überall, veröffentlicht
- [ ] Gesamtsuite grün, `skills/` und Cloud-Agents ohne Drift, kein `pytest.skip`/`xfail` zur Entschärfung
- [ ] Folge-Issue für das Aufräumen von `herdr.auto_clear` samt Kommentar in `config.yaml` angelegt
- [ ] #505, #601 und #503 als durch Epic #649 überholt geschlossen

## Acceptance Criteria

- **AC-1:** Given das Modul `herdr_bridge` nach dem Rückbau / When seine Symbole geprüft werden / Then gibt es keine Funktionen `maybe_auto_clear`, `spawn_auto_clear`, `run_auto_clear`, `record_signal`, `run_signal`, `auto_clear_active`, `auto_clear_enabled` mehr, und das Modul enthält keine Spawn-Funktion für einen Herdr-Pane-Tipp
  - Test: tests/test_rueckbau_autoclear_663.py::test_bridge_has_no_auto_clear_symbols

- **AC-2:** Given Herdr-Pane, Env `OPENSPEC_HERDR_AUTO_CLEAR=1` und Config `herdr.auto_clear.enabled: true` / When `workflow.py autoclear` läuft / Then lautet die Ausgabe genau `AUTO_CLEAR=off`, Exit 0, und im Workflow-State steht kein `auto_clear_boundary`
  - Test: tests/test_rueckbau_autoclear_663.py::test_autoclear_cli_prints_off

- **AC-3:** Given Herdr-Pane mit eingeschaltetem Auto-/clear-Schalter / When ein Phasenwechsel (1 nach 2, 2 nach 3, 3 nach 4, 5 nach 6, 6b nach 7) ausgeführt wird / Then steht im Workflow-State kein `auto_clear_boundary`
  - Test: tests/test_rueckbau_autoclear_663.py::test_phase_change_writes_no_boundary

- **AC-4:** Given Herdr-Pane mit Stub-Binary und eingeschaltetem Auto-/clear-Schalter / When Stop-Hook, Prompt-Hook, SessionStart-Hook und PreToolUse-Guard je einmal laufen / Then enden alle mit Exit 0, es startet kein Prozess, und weder `.claude/herdr_signals/` noch `herdr_auto_clear.log` entstehen
  - Test: tests/test_rueckbau_autoclear_663.py::test_hooks_spawn_nothing_and_write_no_signal_files

- **AC-5:** Given `hooks/hooks.json` nach dem Rückbau / When die Registrierungen gelesen werden / Then verweist keine Hook-Registrierung auf `herdr_bridge.py signal`, und `herdr_bridge.py plan-pane-close` ist unter SessionEnd weiter eingetragen
  - Test: tests/test_rueckbau_autoclear_663.py::test_hooks_json_has_no_signal_entries_but_plan_pane_close

- **AC-6:** Given eine veraltete Hook-Registrierung in einem Konsumentenprojekt / When `herdr_bridge.py signal activity` oder `herdr_bridge.py auto-clear` aufgerufen wird / Then endet der Aufruf still mit Exit 0 ohne Ausgabe auf stderr und ohne Prozess-Start
  - Test: tests/test_rueckbau_autoclear_663.py::test_removed_cli_modes_exit_zero_silently

- **AC-7:** Given ein Herdr-Stub-Binary / When ein Workflow-Wechsel gemeldet wird (`report_workflow`, `report_active`) / Then erhält die Seitenleiste dieselben Aufrufe wie vor dem Rückbau
  - Test: tests/test_herdr_sidebar_466.py (Bestandstests, unverändert grün)

- **AC-8:** Given ein Herdr-Stub-Binary, ein offener Plan / When `workflow.py plan` bzw. das Plan-Pane-Schließen läuft und ein vorhandener Pane wiederverwendet wird / Then öffnet, benutzt und schließt der Plan-Pane den Pane wie vor dem Rückbau, einschließlich Log-Datei
  - Test: tests/test_herdr_plan_pane_476.py und tests/test_herdr_plan_pane_reuse_493.py (Bestandstests, unverändert grün)

- **AC-9:** Given der Stand nach dem Rückbau / When die Testsammlung läuft / Then gibt es keinen ImportError und keine Datei der sieben gelöschten Auto-/clear-Testsuiten, und die Kontext-Stop-Tests belegen, dass Config und Env `OPENSPEC_HERDR_AUTO_CLEAR` weder `CONTEXT_STOP` noch `AUTO_CLEAR` beeinflussen
  - Test: tests/test_context_stop_658.py und tests/test_rueckbau_autoclear_663.py::test_config_and_env_have_no_effect

- **AC-10:** Given CLAUDE.md, README.md, CHANGELOG und `plugin.json` / When ihre Texte gelesen werden / Then beschreibt keine der Dokumentationen ein Auto-/clear mehr als Funktion, der CHANGELOG enthält unter `[4.24.0]` den Migrationshinweis, und die Version ist überall 4.24.0
  - Test: tests/test_rueckbau_autoclear_663.py::test_docs_and_version_consistent

## Test Plan

Automatische Tests (je an eine AC gebunden, Netzwerk-frei, Config, State und Herdr-Stub per `tmp_path`; Test-Env setzt `OPENSPEC_AUTONOMY`, `HERDR_ENV`, `HERDR_PANE_ID`, `OPENSPEC_HERDR_AUTO_CLEAR` explizit):

- `pytest tests/test_rueckbau_autoclear_663.py` (RED zuerst, dann GREEN)
- Regressionsnetz Herdr (unverändert): `pytest tests/test_herdr_sidebar_466.py tests/test_herdr_plan_pane_476.py tests/test_herdr_plan_pane_reuse_493.py`; dazu `tests/test_herdr_plan_deploy_sessionstart_478.py` nach Bereinigung (Plan-/Deploy-/SessionStart-Teile bleiben)
- Umgestellte Bestandstests: `pytest tests/test_befehlsform_context_titel_499.py tests/test_auftrag_551.py tests/test_context_stop_658.py tests/test_auto_chain_flat_662.py tests/test_kette_auto_clear_489.py tests/test_clear_checkpoint_blocks.py tests/test_vorlagen_klartext_597.py`
- Footer-Gate und Workflow: `pytest` über die Footer-Gate-Tests und die Workflow-Phasentests
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile` auf alle geänderten Hooks; `python3 scripts/sync_skills.py --check`; `python3 scripts/sync_cloud_agents.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Reiner Rückbau einer durch Epic #649 / #662 bereits entschiedenen und stillgelegten Funktion; die Entscheidung aus feat-467/fix-489 gilt als abgelöst, es entsteht keine neue Entscheidungsfläche. `autoclear` bleibt aus Kompatibilität zu gecachten Befehlstexten, die Bridge bleibt fail-open.
- **Alternative A, zweistufige Teilung (a: Bridge-Runner/Signale mit Aufrufern und Tests, b: Vermerk in `workflow.py`, Skript, Doku):** verworfen. Die Teile hängen an `auto_clear_active()`; ein Zwischenstand lässt Aufrufer ohne Ziel oder Vermerke ohne Abnehmer in Hooks, die in jedem Konsumentenprojekt laufen. Nur Rückfall, falls das Review untragbar wird.
- **Alternative B, `workflow.py autoclear` ganz entfernen:** verworfen. Alte, aus dem Plugin-Cache gelieferte Befehlstexte (4.22 und älter) rufen den Befehl; „Unbekannter Befehl" mit Exit ≠ 0 bräche die Kette in Phase 1, 2, 3 und 5. Kosten des Behaltens: wenige Zeilen und ein Pinn-Test; Löschung in einem späteren Issue, sobald die Pin-Spanne ≥ 4.23.0 ist.
- **Alternative C, toten Code stehen lassen:** verworfen. Verfehlt das Ziel des Issues; `record_signal` und `signal activity`-Hooks starten bei jedem Event Prozesse ohne Leser, und getesteter toter Code bindet Pflegeaufwand und täuscht Funktion vor.
- **Alternative D, nur den Runner löschen, Signale und Vermerk behalten:** verworfen. Schreibt weiter Dateien ohne Leser und widerspricht dem Auftrag.
- **Alternative E, `config.yaml` mit aufräumen:** zurückgestellt, Gate-Config und autarker Auftrag; Folge-Issue.

## Changelog

- 2026-11-25: Initial spec created
