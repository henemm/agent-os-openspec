# Context: feat-404-qa-run-durchsetzen

## Request Summary
Issue #404 (Folge zu #345): `qa_gate.py --run` in allen Befehlen/Agenten ausrollen (Teil A) und per `qa_gate.require_run` (Default false) durchsetzen (Teil B). Dazu offene Befunde aus der #345-Gegenprüfung: F004 (Secrets-Prüfung kennt `--run` nicht als verschachtelte Shell), F002 (Randfälle `run_and_capture`), #403 (rote Läufe sieht `post_bash` nie). F003 (Stempel per Import fälschen) ist bereits erledigt (`docs/specs/fix-404-qa-stempel-faelschung.md`).

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/qa_gate.py | `_run_mode` :637 (Stempel: source=run, exit_code, output_sha256, output_path, command_sha256, timestamp), `_file_mode` :656 (source=file), `main` :672, `_pump` :500 (kein Schutz um out_file.write → BrokenPipe/Fehler blockiert bis Timeout), `_kill_group` :519 (kein Check auf gereapten Leader), `run_and_capture` :532, `_run_config` :619 |
| core/hooks/workflow.py | `write_qa_run_stamp` :1996 (nur qa_gate.py als __main__), `_validate_transition` :2981 (feature-fast-Zweig :2984-3006, Verdict :3051, Dialog-Beleg :3062, Evidence :3078), `cmd_complete` :4301; `last_test_run` nur in `awaiting_human_approval` :1433 |
| core/hooks/bash_gate.py | Block 3c :2121 (`_forges_qa_stamp`), Block 4 Secrets :2126 (`_matches_file_token` :1520 mit Nested-Shell-Regex-Fallback), `_has_real_redirect` :1466 (gleicher Fallback, kennt `--run` auch nicht), Block 5 Commit-Gate :2181, 5c :2250 (nur phase6/6b/7, ohne feature-fast) |
| core/hooks/secrets_guard.py | `_NESTED_SHELL_RE` :70 — muss mit bash_gate synchron bleiben |
| core/hooks/post_bash.py | `_record_test_run` → `last_test_run`; registriert nur PostToolUse (hooks/hooks.json:96) |
| config.yaml :457 | `qa_gate: test_command: "", run_timeout: 540` — `qa_gate` steht bereits in `PLUGIN_CONFIG_KEYS` |
| core/commands/50-implement.md | Step 3 Dev-Prompt :116 Umleitung, Step 4 :136 add-artifact, 8d :313-326 `qa_gate.py <datei>` |
| core/commands/60-validate.md | :47/:52/:106 TEST CHECK ohne qa_gate |
| core/commands/80-workflow.md | :268-270 `qa_gate.py <datei>`-Beispiele |
| core/agents/developer-agent.md :57, implementation-validator.md :55-66,:233 | Datei-Umleitung; veralteter Key `pre_commit.test_command` |
| skills/*, .claude/agents/* | Generate: `scripts/sync_skills.py`, `scripts/sync_cloud_agents.py` |
| setup.py `generate_config_yaml` :1154 | kopiert config.yaml → openspec.yaml beim Neuinstallieren |

## Existing Patterns
- Kill-Switch/Opt-in-Flags in config.yaml mit Default, gelesen über `config_loader.load_config()`.
- Beleg-Prüfungen an genau zwei Stellen: `bash_gate` Block 5c (Commit) und `workflow._validate_transition` (Phase 7/8) — Muster `check_dialog_evidence`, `_evidence_reason`.
- Nested-Shell-Behandlung per Regex-Fallback auf Rohscan (`sh -c`, `eval`).
- Tests: tmp-Projekt mit `.claude/workflows/<wf>.json`, `.claude/config.yaml`, Hooks per subprocess (`tests/test_qa_gate_run_345.py:49-89`).

## Dependencies
- Upstream: config_loader, hook_utils, adversary_dialog, evidence_gate.
- Downstream: alle Konsumenten-Projekte (Befehle, Agenten, openspec.yaml); CI-Tests.

## Existing Specs
- `docs/specs/feat-345-qa-gate-selbst-ausfuehren.md` (+ ADR-0345)
- `docs/specs/fix-404-qa-stempel-faelschung.md` (F003, erledigt)

## Risks & Considerations
- Durchsetzung darf bei `require_run: false` nichts ändern (Migrationspfad, keine Breaking Change).
- Stempel muss beim Lesen gegengeprüft werden (SHA der Datei an `output_path`, Zeitstempel ≥ letzter Code-Änderung?) — sonst wertlos.
- Stempel gilt für einen Code-Stand: nach weiteren Edits veraltet. Bindung an Code-Stand (z. B. Baum-Hash) klären.
- feature-fast überspringt 5c — Pflicht muss dort ebenfalls greifen (Phase-8-Übergang).
- Projekte ohne `test_command` dürfen mit `require_run: false` nicht brechen; bei `true` ohne Befehl klare Meldung.
- `post_bash` unter PostToolUseFailure: Input-Format unterscheidet sich (kein tool_response-Exit?) — Doku prüfen; Alternative: Hinweis streichen.
- Generierte Kopien müssen synchron bleiben (Release-Check).

## Analysis

### Type
Feature (Durchsetzung + Ausrollen) mit drei Härtungs-Befunden (F002, F004, #403).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/adversary_dialog.py | MODIFY | `change_set_hash(wf)` über `phase8_code_files` (sortierte realpath+sha256-Paare) |
| core/hooks/qa_gate.py | MODIFY | Stempel + `code_sha256`; Datei-Modus: Deprecation-Hinweis, bei `require_run` Abbruch; F002 `_kill_group` nur solange Leader lebt, `_pump` leert die Pipe weiter bei Schreibfehler |
| core/hooks/workflow.py | MODIFY | `qa_run_stamp_problem(data)` (eine Prüfstelle); in `_validate_transition` für phase8_complete (feature-fast- und Normalzweig) |
| core/hooks/bash_gate.py | MODIFY | Commit-Gate: bei `require_run` Stempelprüfung für feature (6/6b/7) und feature-fast (ab 6) |
| core/hooks/post_bash.py | MODIFY | PostToolUseFailure verarbeiten (`error`-Text → result failed) |
| hooks/hooks.json (+ setup.py Copy-Modus-Registrierung prüfen) | MODIFY | post_bash unter PostToolUseFailure, matcher Bash |
| config.yaml | MODIFY | `qa_gate.require_run: false` + Doku `test_command` |
| core/commands/50-implement.md, 60-validate.md, 80-workflow.md | MODIFY | auf `qa_gate.py --run` umstellen |
| core/agents/developer-agent.md, implementation-validator.md | MODIFY | `--run` statt Datei-Umleitung, veralteten Key `pre_commit.test_command` ersetzen |
| CLAUDE.md, README.md, CHANGELOG.md, plugin.json | MODIFY | Doku, Version |
| skills/*, .claude/agents/* | REGEN | sync-Skripte |
| tests/test_qa_run_require_404.py | CREATE | Tests |

### Scope Assessment
- Files: ~15 (ohne generierte)
- Estimated LoC: Hooks ~+180, Doku ~+120, Tests ~+250
- Risk Level: HIGH (Gate-Code; mit `require_run: false` verhaltensneutral)

### Technical Approach
- **„Passender SHA"** = alle Prüfungen in `workflow.qa_run_stamp_problem`: `source=="run"`, `exit_code==0`, Datei an `output_path` (im Projekt, kein Symlink) hat `output_sha256`, `command_sha256` = sha256 des aktuell konfigurierten `test_command`, `code_sha256` = aktueller `change_set_hash`. Zeitstempel allein gilt nicht. Ohne git (`code_sha256` None): Vergleich Stempelzeit gegen mtime der Code-Dateien.
- **require_run true, kein test_command:** blocken mit klarer Meldung. Fehlerhafte Config/ChangeSetError bei `require_run: true` → fail-closed.
- **Durchsetzung nur bei `require_run: true`**; Default false = heutiges Verhalten (plus Deprecation-Hinweis im Datei-Modus).
- **F004 (Entscheidung):** kein echter Angriff über die Kommandozeile — der Befehl steht in der Config, nicht im Bash-Kommando; `--run` in `_NESTED_SHELL_RE` brächte nur Fehlalarme. Stattdessen: `_run_config` prüft den `test_command`-String mit den vorhandenen Secrets-Mustern (Credential-Dateien im Befehl → Abbruch) und Known Limitation dokumentieren.
- **#403 (Entscheidung):** post_bash zusätzlich unter `PostToolUseFailure` (matcher Bash) registrieren; das Feld `error` enthält „Exit code N" + Ausgabe (Doku code.claude.com/docs/en/hooks). Damit überschreibt ein roter Lauf ein veraltetes „passed" (wichtig für `awaiting_human_approval`, #628). Streichen verworfen: #628 hängt daran.
- **Schnitt:** ein Workflow/PR (Issue erlaubt flaches Aufräumen in einem Workflow); Reihenfolge F002 → #403 → B → A → Sync.

### Dependencies
- `adversary_dialog.phase8_code_files`, `ChangeSetError`, `is_gated_code_path`, `_hash_root`; `config_loader.load_config`; Secrets-Muster aus `bash_gate`/`secrets_guard` (Wiederverwendung, nicht kopieren).

### Open Questions
- keine an den PO (rein technische Entscheidungen, oben getroffen)
