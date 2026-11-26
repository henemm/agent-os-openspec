---
entity_id: feat-404-qa-run-durchsetzen
type: feature
created: 2026-11-26
updated: 2026-11-26
status: draft
version: "1.0"
tags: [qa-gate, qa-run-stamp, require-run, bash-gate, post-bash, rollout]
workflow: feat-404-qa-run-durchsetzen
test_targets: ["tests/test_qa_run_require_404.py"]
---

# qa_gate --run ausrollen und durchsetzen (Issue #404)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #404 (Folge zu #345): Teil A (Ausrollen), Teil B (Durchsetzen per `qa_gate.require_run`), Befunde F002 (Randfälle `run_and_capture`), F004 (Secrets-Prüfung und `--run`) und #403 (rote Läufe sieht `post_bash` nie). Befund F003 (Stempel per Import fälschen) ist bereits erledigt: `docs/specs/fix-404-qa-stempel-faelschung.md`.

## Purpose

Das QA-Gate kann den Testbefehl seit #345 selbst ausführen (`qa_gate.py --run`) und schreibt dabei einen Stempel `qa_run_stamp`. Heute liest ihn aber nichts, und die Befehle und Agenten schicken Claude weiter zur selbst umgeleiteten Testdatei, die Claude frei formulieren (und damit beschönigen) kann. Diese Änderung stellt alle Befehle und Agenten auf `--run` um und macht den Stempel per Schalter `qa_gate.require_run` (Standard aus) zur Pflicht vor Commit und Phase 8; dazu kommen drei Härtungen (F002, F004, #403).

## Source

- **File:** `core/hooks/workflow.py`, `core/hooks/bash_gate.py`, `core/hooks/qa_gate.py`, `core/hooks/adversary_dialog.py`, `core/hooks/post_bash.py`, `hooks/hooks.json`
- **Identifier:** `workflow.qa_run_stamp_problem`, `adversary_dialog.change_set_hash`, `qa_gate._kill_group`, `qa_gate._pump`, `qa_gate._run_config`, `qa_gate._file_mode`, `bash_gate` Block 5c, `workflow._validate_transition`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `adversary_dialog.phase8_code_files`, `ChangeSetError`, `is_gated_code_path`, `_hash_root` | Funktion | Grundlage für `change_set_hash` (Code-Stand) |
| `config_loader.load_config` | Modul | liest `qa_gate.require_run`, `qa_gate.test_command` (fehlender Schlüssel = false) |
| Secrets-Muster aus `secrets_guard.py` / `bash_gate.py` | Konstanten | F004: Wiederverwendung, nicht kopieren |
| `workflow.write_qa_run_stamp` | Funktion | Stempel-Schreiber (nur `qa_gate.py` als Hauptprogramm, F003) |
| `docs/specs/feat-345-qa-gate-selbst-ausfuehren.md`, `docs/specs/fix-404-qa-stempel-faelschung.md` | Spec | Vorarbeit |
| `scripts/sync_skills.py`, `scripts/sync_cloud_agents.py` | Skript | erzeugen `skills/` und `.claude/agents/` neu |
| Claude-Code-Hook-Event `PostToolUseFailure` | Plattform | liefert Fehlschläge von Bash mit Feld `error` |

## Scope

- **Affected Files:**
  - `core/hooks/adversary_dialog.py` (MODIFY: `change_set_hash(wf)`)
  - `core/hooks/qa_gate.py` (MODIFY: Stempelfeld `code_sha256`, Datei-Modus-Hinweis/-Abbruch, F002, F004)
  - `core/hooks/workflow.py` (MODIFY: `qa_run_stamp_problem`, Prüfung in `_validate_transition` für Phase 8 in beiden Zweigen)
  - `core/hooks/bash_gate.py` (MODIFY: Commit-Gate-Prüfung)
  - `core/hooks/post_bash.py` (MODIFY: Fehlerfall verarbeiten)
  - `hooks/hooks.json` (MODIFY: `PostToolUseFailure`, matcher `Bash`); `setup.py` nur, falls dort Hook-Listen für den Copy-Modus gebaut werden
  - `config.yaml` (MODIFY: `qa_gate.require_run: false`, Doku zu `test_command`)
  - `core/commands/50-implement.md`, `60-validate.md`, `80-workflow.md` (MODIFY)
  - `core/agents/developer-agent.md`, `core/agents/implementation-validator.md` (MODIFY)
  - `CLAUDE.md`, `README.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json` (MODIFY; Version 4.25.4 auf 4.26.0)
  - `skills/*`, `.claude/agents/*` (REGEN per Sync-Skripte)
  - `tests/test_qa_run_require_404.py` (CREATE)
- **Estimated Changes:** Hooks ca. +180 LoC, Doku ca. +120 LoC, Tests ca. +250 LoC; ca. 15 Dateien ohne generierte.
- **Nicht im Scope:** Pflicht für RED-Läufe (Phase 5, `40-tdd-red.md` bleibt dateibasiert, weil rote Läufe nicht gegated sind); kryptografische Signatur; Änderung der Nested-Shell-Regexe.

## Implementation Details

**Reihenfolge:** F002, dann #403, dann Teil B, dann Teil A, dann Sync der generierten Kopien.

**Zentrale Prüfung `workflow.qa_run_stamp_problem(data)`.** Eine einzige Funktion, aufgerufen von `bash_gate.py` (Commit) und `workflow._validate_transition` (Phase 8, `cmd_complete` nutzt diese Funktion mit). Sie gibt `None` zurück, wenn der Stempel passt, sonst einen Klartext-Grund. Geprüft wird: `source == "run"`; `exit_code == 0`; die Datei an `output_path` liegt im Projekt, ist kein Symlink und ihr sha256 gleicht `output_sha256`; `command_sha256` gleicht dem sha256 des aktuell konfigurierten `test_command`; `code_sha256` gleicht dem aktuellen `adversary_dialog.change_set_hash(wf)`. Ein Zeitstempel allein gilt nie als Beleg. Ohne git (`code_sha256` ist None) gilt ersatzweise: Stempelzeit nicht älter als die neueste mtime der Code-Dateien.

**`change_set_hash(wf)`** bildet über `phase8_code_files` die sortierten Paare (realpath, sha256) und hasht sie; `qa_gate.py --run` schreibt das Ergebnis als `code_sha256` in den Stempel.

**Schalter.** `qa_gate.require_run` (Standard `false`, fehlender Schlüssel = false). Bei false bleibt alles wie heute, mit einer Ausnahme: der Datei-Modus druckt einen Hinweis auf `--run` (Deprecation). Bei true:
- Ist kein `test_command` konfiguriert, blockt das Gate mit klarer Meldung (Befehl konfigurieren oder `require_run` ausschalten).
- Wirft `change_set_hash` einen `ChangeSetError` oder ist die Config unlesbar, blockt das Gate (fail-closed).
- Der Datei-Modus von `qa_gate.py` bricht mit Exit 1 ab.

**Platzierung der Prüfung.** Commit-Gate (`bash_gate.py`): Feature-Workflows in `phase6_implement`, `phase6b_adversary`, `phase7_validate` (innerhalb von Block 5c); `feature-fast` ab Phase 6. Phase-8-Übergang in `_validate_transition`: sowohl im feature-fast-Zweig als auch im Normalpfad.

**F002 (`qa_gate.py`).** `_kill_group` signalisiert die Prozessgruppe nur, solange der Leader nicht gereapt ist (kein Treffer auf eine wiederverwendete PID). `_pump` fängt Schreibfehler auf die Ausgabedatei ab (BrokenPipe, Plattenfehler) und leert die Pipe weiter, damit der Testprozess nicht bis zum Timeout blockiert.

**F004 (`qa_gate.py::_run_config`).** Die Nested-Shell-Regexe bleiben unverändert (`--run` dort aufzunehmen brächte nur Fehlalarme: der Befehl steht in der Config, nicht im Bash-Kommando). Stattdessen verweigert `_run_config` einen `test_command`, der Secret-/Credential-Dateien nennt, mit den vorhandenen Secrets-Mustern (importiert, nicht kopiert), Exit 1 mit Klartext.

**#403 (`post_bash.py`, `hooks/hooks.json`).** `post_bash.py` wird zusätzlich unter `PostToolUseFailure` (matcher `Bash`) registriert. Dort fehlt `tool_response`; das Feld `error` hat die Form `Exit code N` plus Ausgabe. Daraus wird `last_test_run` mit Ergebnis `failed` abgeleitet, sofern die Ausgabe wie ein Testlauf aussieht; so überschreibt ein roter Lauf ein veraltetes `passed` (relevant für `awaiting_human_approval`, #628).

**Teil A (Doku/Agenten).** `50-implement.md` (Step 3 Dev-Prompt, Step 4, 8d), `60-validate.md`, `80-workflow.md`, `developer-agent.md` und `implementation-validator.md` rufen `qa_gate.py --run` statt `qa_gate.py <Datei>` auf; der veraltete Schlüssel `pre_commit.test_command` wird durch `qa_gate.test_command` ersetzt. `40-tdd-red.md` bleibt dateibasiert. `config.yaml` dokumentiert `test_command` und `require_run: false`. `CLAUDE.md` und `README.md` beschreiben den Schalter knapp. Danach `scripts/sync_skills.py` und `scripts/sync_cloud_agents.py` ausführen.

## Expected Behavior

- **Input:** Commit-Versuch (Bash), Phasenwechsel nach `phase8_complete` oder `workflow.py complete`, `qa_gate.py`-Aufrufe, Bash-Fehlschläge.
- **Output:** Bei `require_run: false` unverändertes Verhalten. Bei `true` blockt jeder Weg ohne gültigen, zum aktuellen Code und Testbefehl passenden, grünen Lauf-Stempel mit Klartext-Grund.
- **Side effects:** Stempel enthält zusätzlich `code_sha256`; `last_test_run` kann nun auch `failed` aus Fehlschlägen werden; Datei-Modus druckt einen Hinweis.

## Known Limitations

- **Wirksame Config dieses Repos:** Der neue Schlüssel `require_run: false` wird im Template `config.yaml` ergänzt. Falls dieses Template zugleich die wirksame Gate-Config des Repos ist und der Edit dort einen override braucht, wird er nicht umgangen, sondern als Implementierungshinweis vermerkt; der Code funktioniert mit fehlendem Schlüssel (= false).
- Ein Agent mit Schreibzugriff auf die Testdateien kann den Test selbst beschönigen; der Stempel belegt nur, dass der konfigurierte Befehl auf dem aktuellen Code-Stand grün lief, nicht dass die Tests inhaltlich gut sind.
- F004: Der Nested-Shell-Rohscan kennt `--run` weiterhin nicht. Ein `test_command` mit Secret-Bezug wird stattdessen beim Start verweigert; ein Secret-Zugriff über Umwege innerhalb des Testbefehls (zum Beispiel ein Skript, das `.env` liest) bleibt außerhalb der Erkennung.
- `PostToolUseFailure` liefert nur den Text im Feld `error`; ein Fehlschlag ohne erkennbare Testausgabe setzt `last_test_run` nicht.
- Ohne git beruht die Code-Bindung nur auf Zeitstempel gegen mtime (schwächer als der Hash).
- RED-Läufe (Phase 5) bleiben dateibasiert und ungegated.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Mit `qa_gate.require_run: true` lässt sich weder committen noch Phase 8 erreichen, ohne dass das QA-Gate den Testbefehl auf dem aktuellen Code-Stand selbst grün ausgeführt hat
- [ ] Alle Befehle und Agenten zeigen den `--run`-Aufruf; die generierten Kopien sind synchron
- [ ] Ein roter Bash-Testlauf wird als `failed` vermerkt
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün); mit Standardwert `require_run: false` ändert sich nichts außer dem Hinweistext

## Acceptance Criteria

- **AC-1:** Given `qa_gate.require_run` ist false oder fehlt / When ein Commit oder der Wechsel nach Phase 8 ohne Stempel versucht wird / Then verhält sich das Gate wie vor der Änderung (kein Block durch die Stempelprüfung)
  - Test: tests/test_qa_run_require_404.py::test_require_run_false_changes_nothing
- **AC-2:** Given `require_run: true` und kein `qa_run_stamp` im Workflow-State / When `git commit` in phase6_implement, phase6b_adversary oder phase7_validate ausgeführt wird / Then Exit 2 mit Hinweis auf `qa_gate.py --run`
  - Test: tests/test_qa_run_require_404.py::test_commit_blocked_without_stamp
- **AC-3:** Given `require_run: true` und ein Stempel mit `exit_code != 0` / When ein Commit versucht wird / Then Exit 2, Grund nennt den roten Lauf
  - Test: tests/test_qa_run_require_404.py::test_commit_blocked_with_red_stamp
- **AC-4:** Given ein grüner Stempel, danach wurde eine Code-Datei der Änderungsmenge geändert / When ein Commit versucht wird / Then Exit 2, Grund nennt veralteten Code-Stand (`code_sha256`)
  - Test: tests/test_qa_run_require_404.py::test_commit_blocked_with_stale_code
- **AC-5:** Given ein grüner Stempel, danach wurde die Ausgabedatei an `output_path` verändert, ersetzt oder durch einen Symlink ersetzt oder liegt außerhalb des Projekts / When ein Commit versucht wird / Then Exit 2, Grund nennt die Ausgabedatei
  - Test: tests/test_qa_run_require_404.py::test_commit_blocked_with_tampered_output
- **AC-6:** Given ein grüner Stempel, danach wurde `qa_gate.test_command` geändert / When ein Commit versucht wird / Then Exit 2, Grund nennt den geänderten Testbefehl (`command_sha256`)
  - Test: tests/test_qa_run_require_404.py::test_commit_blocked_with_changed_test_command
- **AC-7:** Given `require_run: true` und ein gültiger, grüner, zum Code und Testbefehl passender Stempel / When ein Commit versucht wird / Then lässt das Gate den Commit durch (Stempelprüfung ohne Beanstandung)
  - Test: tests/test_qa_run_require_404.py::test_commit_passes_with_valid_stamp
- **AC-8:** Given `require_run: true` und feature-fast-Workflow ab Phase 6 ohne gültigen Stempel / When ein Commit versucht wird / Then Exit 2 (die Prüfung greift auch ohne Block 5c der Feature-Phasen)
  - Test: tests/test_qa_run_require_404.py::test_feature_fast_commit_blocked_without_stamp
- **AC-9:** Given `require_run: true` und ein Feature-Workflow ohne oder mit ungültigem Stempel / When `workflow.py phase phase8_complete` aufgerufen wird / Then Übergang abgelehnt mit Grund; mit gültigem Stempel erlaubt
  - Test: tests/test_qa_run_require_404.py::test_phase8_transition_requires_stamp_feature
- **AC-10:** Given `require_run: true`, feature-fast-Workflow / When der Wechsel nach `phase8_complete` ohne gültigen Stempel versucht wird / Then Übergang abgelehnt, mit gültigem Stempel erlaubt
  - Test: tests/test_qa_run_require_404.py::test_phase8_transition_requires_stamp_feature_fast
- **AC-11:** Given `require_run: true` und ohne gültigen Stempel / When `workflow.py complete` aufgerufen wird / Then Abbruch mit demselben Grund wie beim Phasenwechsel
  - Test: tests/test_qa_run_require_404.py::test_complete_requires_stamp
- **AC-12:** Given `require_run: true` ohne konfigurierten `test_command` / When ein Commit oder Phase 8 versucht wird / Then Block mit klarer Meldung (Testbefehl konfigurieren oder `require_run` ausschalten)
  - Test: tests/test_qa_run_require_404.py::test_require_run_without_test_command_blocks_clearly
- **AC-13:** Given `require_run: true` und `change_set_hash` wirft `ChangeSetError` / When ein Commit versucht wird / Then Block (fail-closed), nicht durchgelassen
  - Test: tests/test_qa_run_require_404.py::test_change_set_error_fails_closed
- **AC-14:** Given der Datei-Modus `qa_gate.py <Datei>` / When `require_run` false ist / Then läuft er wie bisher und gibt zusätzlich einen Hinweis auf `--run` aus; When `require_run` true ist / Then Exit 1 mit Hinweis, kein Verdict
  - Test: tests/test_qa_run_require_404.py::test_file_mode_deprecation_and_refusal
- **AC-15:** Given ein Testprozess, dessen Prozessgruppen-Leader bereits gereapt ist / When `_kill_group` aufgerufen wird / Then wird kein Signal an eine fremde, wiederverwendete Gruppe gesendet
  - Test: tests/test_qa_run_require_404.py::test_kill_group_skips_reaped_leader
- **AC-16:** Given ein Schreibfehler auf die Ausgabedatei (zum Beispiel BrokenPipe) / When `_pump` läuft / Then wird die Pipe weiter geleert und der Lauf endet ohne Hängen bis zum Timeout
  - Test: tests/test_qa_run_require_404.py::test_pump_drains_pipe_on_write_error
- **AC-17:** Given ein `qa_gate.test_command`, der eine Secret-/Credential-Datei nennt (zum Beispiel `cat .env`) / When `qa_gate.py --run` startet / Then Exit 1 mit Klartext, der Befehl wird nicht ausgeführt; ein harmloser Befehl läuft weiter
  - Test: tests/test_qa_run_require_404.py::test_run_refuses_test_command_with_secret_file
- **AC-18:** Given ein fehlgeschlagener Bash-Testlauf, gemeldet als `PostToolUseFailure` mit Feld `error` ("Exit code 1" plus Ausgabe) / When `post_bash.py` das Ereignis verarbeitet / Then steht `last_test_run` mit Ergebnis `failed`; und `hooks/hooks.json` registriert `post_bash.py` unter `PostToolUseFailure` mit matcher `Bash`
  - Test: tests/test_qa_run_require_404.py::test_post_tool_use_failure_records_failed
- **AC-19:** Given `50-implement.md`, `60-validate.md`, `80-workflow.md`, `developer-agent.md`, `implementation-validator.md` / When sie nach Aufrufen durchsucht werden / Then enthält keine davon einen Datei-Modus-Aufruf `qa_gate.py docs/artifacts`, sie nennen `qa_gate.py --run`, und der Schlüssel `pre_commit.test_command` kommt nicht mehr vor
  - Test: tests/test_qa_run_require_404.py::test_docs_and_agents_use_run_mode
- **AC-20:** Given die geänderten Quellen in `core/commands` und `core/agents` / When `sync_skills.py --check` und `sync_cloud_agents.py --check` laufen / Then melden beide keine Abweichung; `config.yaml` enthält `require_run: false`
  - Test: tests/test_qa_run_require_404.py::test_generated_copies_in_sync

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden, alle in `tests/test_qa_run_require_404.py`):

- GIVEN `require_run` fehlt WHEN Commit ohne Stempel THEN kein Stempel-Block (AC-1)
- GIVEN `require_run: true` WHEN Stempel fehlt, rot, veraltet, Ausgabedatei manipuliert, Testbefehl geändert THEN Exit 2 mit jeweils eigenem Grund; mit gültigem Stempel Durchlass (AC-2 bis AC-7)
- GIVEN feature-fast bzw. Feature-Workflow WHEN Phase-8-Übergang und `complete` THEN gleiche Prüfung (AC-8 bis AC-11)
- GIVEN `require_run: true` ohne `test_command` bzw. mit `ChangeSetError` THEN klare Blockmeldung, fail-closed (AC-12, AC-13)
- GIVEN Datei-Modus WHEN `require_run` false bzw. true THEN Hinweis bzw. Exit 1 (AC-14)
- F002, F004 und #403 als Einzeltests (AC-15 bis AC-18)
- Doku-/Agenten-Grep und Sync-Prüfung (AC-19, AC-20)

Aufruf: `pytest tests/test_qa_run_require_404.py`. Regression: `pytest tests/test_qa_gate_run_345.py tests/test_qa_stamp_forgery_404.py tests/test_bash_gate_*.py tests/test_post_bash*.py`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Durchsetzung folgt dem bestehenden Muster der Beleg-Prüfungen (Dialog-Beleg, Evidence-Gate) an denselben zwei Stellen und ist per Schalter abschaltbar; die Grundsatzentscheidung zum Selbst-Ausführen steht in ADR-0345 (Abschnitt „Architektur-Entscheidung“ in `docs/specs/feat-345-qa-gate-selbst-ausfuehren.md`). Keine neue Architektur.

## Changelog

- 2026-11-26: Initial spec created
