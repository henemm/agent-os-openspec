# Adversary Dialog — fix-416-state-reader-source-check
Spec: docs/specs/fix-416-state-reader-source-check.md
Datum: 2026-10-11 00:33

## Checkliste
- [x] **Input:** Jeder Lesezugriff auf `.claude/workflows/<name>.json` (und `_archive/`) durch einen der genannten Leser.
- [x] **Output:** Normale eigene Datei: Verhalten wie heute. Verweis hart oder weich (Datei, Ordner `.claude/workflows`, `.claude`): der Leser verweigert gemäß Tabelle in Implementation Details Punkt 4, mit Meldung zu Pfad, Grund und Bereinigungsweg.
- [x] **Side effects:** Keine neuen Subprozesse, keine neuen Abhängigkeiten, keine geänderten Config-Keys, kein neues State-Format. Beim Fund wird nichts zurückgeschrieben und nichts kopiert.
- [x] **AC-1:** Given eine Projektwurzel, in der `.claude/workflows/<wf>.json` mit einem zweiten Namen hart verlinkt ist (`st_nlink == 2`) / When `read_state_json` die Datei liest / Then wirft sie `UnsafeStateError`, die Meldung nennt Pfad, Grund (harter Verweis, Linkzahl) und Bereinigungsweg, und es wird nichts geschrieben
- [x] **AC-2:** Given eine Projektwurzel, in der `.claude/workflows/<wf>.json` ein Symlink auf eine andere Datei ist / When `read_state_json` die Datei liest / Then wirft sie `UnsafeStateError` mit Grund „symbolischer Verweis“
- [x] **AC-3:** Given eine Projektwurzel, in der der Ordner `.claude/workflows` ein Symlink auf einen anderen Ordner ist / When `read_state_json` eine State-Datei darin liest / Then wirft sie `UnsafeStateError` (Elternkette wird geprüft, nicht nur das letzte Glied)
- [x] **AC-4:** Given eine Projektwurzel, in der `.claude` selbst ein Symlink ist / When `read_state_json` eine State-Datei darunter liest / Then wirft sie `UnsafeStateError`
- [x] **AC-5:** Given eine normale eigene State-Datei (`S_ISREG`, `st_nlink == 1`, keine Verweise in der Kette), eine fehlende Datei und eine Datei mit kaputtem JSON / When `read_state_json` bzw. jeder Leser sie liest / Then liefert die normale Datei den Inhalt wie heute, die fehlende Datei `FileNotFoundError` bzw. das heutige „kein Workflow“, das kaputte JSON `json.JSONDecodeError` wie heute; es gibt keinen `UnsafeStateError`
- [x] **AC-6:** Given eine Projektwurzel, die selbst hinter einem Symlink liegt (z. B. `/tmp` → `/private/tmp` auf macOS, im Test ein Symlink-Elternordner der Wurzel) / When `read_state_json` eine normale State-Datei liest / Then liefert sie den Inhalt ohne Fehlalarm
- [x] **AC-7:** Given die Klasse `UnsafeStateError` / When ihre Vererbung geprüft wird / Then erbt sie von `Exception`, aber weder von `OSError` noch von `ValueError`, sodass `except (OSError, ValueError)` in Leser-Code sie nicht verschluckt
- [x] **AC-8:** Given ein unsicherer State in einer der vier Richtungen / When ein Leser ihn meldet / Then nennt die Meldung Pfad, Grund und den Bereinigungsweg (Verweis bzw. State entfernen, Workflow frisch starten), und es erfolgt keine Reparatur durch Kopieren (die Datei hinter dem Verweis bleibt unverändert, es entsteht keine neue State-Datei)
- [x] **AC-9:** Given ein unsicherer State (harter und weicher Verweis) und ein Code-Edit außerhalb der Always-Allowed-Dateien / When `edit_gate` bzw. `tdd_enforcement` als Subprozess läuft / Then enden sie mit Exit 2 und der Meldung aus AC-8; eine Always-Allowed-Datei bleibt frei
- [x] **AC-10:** Given ein unsicherer State / When `bash_gate` einen state-abhängigen Befehl (`git commit`) und einen gewöhnlichen Befehl (`ls`) prüft / Then verweigert er nur den Commit (Exit 2 mit Meldung), der gewöhnliche Befehl endet mit Exit 0, damit der Zustand bereinigt werden kann
- [x] **AC-11:** Given ein unsicherer State / When `phase_listener` (mit Freigabe-Phrase), `footer_gate` und `post_implementation_gate` laufen / Then enden alle mit Exit 0 und einer Warnung (nie Exit 2), und `phase_listener` schreibt weder einen Phasenwechsel noch eine Freigabe in den State
- [x] **AC-12:** Given ein unsicherer State / When die `workflow.py`-CLI (`status`, `list`) läuft / Then endet sie mit Exit 1 und der Meldung aus AC-8, und `read_active_workflow_fast()` liefert kein Adversary-Verdict
- [x] **AC-13:** Given ein unsicherer State / When `adversary_dialog` den Fast-Track-Check, die Metriken und `required-files` ausführt / Then gewährt der Fast-Track keine Freigabe, die Metriken warnen, `required-files` endet mit Exit 1
- [x] **AC-14:** Given ein unsicherer State / When `session_singleton_guard._read_workflow_phase` ihn liest / Then liefert die Funktion `None`
- [x] **AC-15:** Given ein unsicherer State und die Lesen-Ändern-Schreiben-Stellen (`edit_gate` LoC-Delta, `bash_gate._write_e2e_scope`, `post_bash._record_test_run`) / When sie laufen / Then schreiben sie nicht zurück: die Datei hinter dem Verweis ist byte-gleich zum Zustand davor und wird nicht atomar als normale Datei ersetzt
- [x] **AC-16:** Given ein State, der durch einen harten Verweis erreichbar ist / When `phase_listener._save_workflow` schreibt / Then geschieht das atomar (neuer Inode, kein Schreiben durch den Verweis hindurch): die über den zweiten Namen sichtbare Datei behält den alten Inhalt
- [x] **AC-17:** Given die Spec `docs/specs/fix-410-state-integrity-gaps.md` / When Known Limitation F004 gelesen wird / Then verweist sie auf `docs/specs/fix-416-state-reader-source-check.md` bzw. #416 und gilt als aufgelöst
- [x] **AC-18:** Given der bestehende Testbestand / When die Vollsuite und das Regressionsnetz `tests/test_bash_gate*` laufen / Then bleiben sie grün (Normalfall unverändert)

## Dialog

Vorlauf: Lauf 1 (BROKEN, F001 HIGH, F002/F003 LOW) siehe `docs/artifacts/fix-416-state-reader-source-check/adversary-runde1-broken.md`. Dies ist der zweite und letzte Lauf nach gezieltem Fix.

### Runde 1
**Adversary:** Lauf 1 ergab BROKEN wegen F001 (`cmd_cleanup_stale_locks` verschluckte `UnsafeStateError` im breiten `except Exception: pass` und löschte danach die Sperren). Prüfung des Fixes, danach Sweep über alle breiten Fangstellen um einen State-Leser.
(a) F001-Fix gelesen (core/hooks/workflow.py:2077-2096): `except UnsafeStateError as exc:` vor `except Exception:`, meldet `SKIPPED <wf> (unsicherer State: <reason>)` und `continue`, ohne Marker zu löschen.
(b) `venv/bin/python -m pytest tests/test_state_reader_source_416.py -q -k cleanup_stale` → `5 passed, 41 deselected` (4 Richtungen mit Sperrdatei plus Gegenprobe normaler State in phase8_complete: `Removed:` und beide Marker weg).
(c) Dangling Symlink per Code-Lesung: `active_file.exists()` (workflow.py:2077) ist False, kein State gelesen, Sperren fallen wie bei fehlendem State — Altverhalten, kein gefälschter Inhalt beteiligt, kein Befund.
(d) Sweep `grep -n "except Exception" core/hooks/*.py` gegen alle Aufrufer:
- workflow.py:2089 (cleanup): jetzt davor abgefangen, restriktiv. workflow.py:1090 (`_validate_transition`): fail-closed. workflow.py:1687, 1386, 1478, 1513, 2126, 2155/2161: lesen keinen Workflow-State. `_read_active` (351) und `read_active_workflow_fast` (401) lassen durch; `main()` (workflow.py:2261) → `BLOCKED:`, Exit 1. `cmd_switch` (1243) fängt nur `SystemExit` (restriktiv). `cmd_list`, `cmd_find_issue`, `cmd_retro_*`: Exit 1.
- qa_gate.py:496 (`_write_stamp`): nur Warnung, Stempel entfällt, Urteil unverändert — restriktiv.
- tdd_enforcement.py:253/256: `UnsafeStateError` blockt (Exit 2); das folgende `except Exception: allow()` greift nur bei Importfehlern.
- post_implementation_gate.py:126/130: Warnung + `allow()` gemäß AC-11; Code-Edits blockt edit_gate.
- edit_gate.py:162/168/189, 263-281: Fund wird durchgereicht, Aufrufer (334, 667) blocken. `_find_workflow_by_spec_file` ignoriert unsichere Dateien nur für Docs (Known Limitation F002). `_check_loc_delta` (519/526): Fund verschluckt, aber nichts zurückgeschrieben — restriktiv.
- bash_gate.py:741 und 851: Commit-Pfad (1315) blockt, `_write_e2e_scope` (857) schreibt nicht. 1241/1256/1262 betreffen Secrets-Config.
- post_bash.py:144: fängt Fund, schreibt nicht; 125 gehört zum atomaren Schreiben.
- phase_listener.py:470: `_finish_unsafe` ohne Schreiben/Freigabe; `_emit_status_note` (428) lesend; 525/535/563 hinter der Prüfung.
- adversary_dialog.py:949, 1021, 1354 gemäß AC-13; 1166 fail-closed.
- footer_gate.py:161 Warnung; session_singleton_guard.py:329 → `None`.
- Direkte `read_text`/`json.load` auf State-Dateien außerhalb von `read_state_json`: keine.
Ergebnis: keine weitere Stelle, an der der Fund über ein breites `except` zu Freigabe, Löschung oder Schreibung führt.
**Implementierer:** F001 behoben. Code reference: core/hooks/workflow.py:2084. F003 als Docstring festgehalten. Code reference: core/hooks/hook_utils.py:1419. F002 als Known Limitation im CHANGELOG-Eintrag zu #416.

### Runde 2
**Adversary:** Alle 21 Checklistenpunkte erneut, ohne Lauf-1-Ergebnisse zu übernehmen. `venv/bin/python -m pytest tests/ -q > docs/artifacts/fix-416-state-reader-source-check/adversary-test-output.txt 2>&1` → `2477 passed, 23 skipped in 174.45s`, 0 failed (Lauf 1: 2472; +5 = die neuen `test_cleanup_stale_locks_*`; dieselben 23 Skips).
Zuordnung: AC-1..4/8 `read_state_json` (hook_utils.py:1471) mit `dir_fd`-Walk, `O_NOFOLLOW`, `fstat`; AC-5/6 Normalfall, Wurzel hinter Symlink; AC-7 hook_utils.py:1399; AC-9 edit_gate.py:667, tdd_enforcement.py:253; AC-10 bash_gate.py:1315; AC-11 phase_listener.py:470/363, footer_gate.py:161, post_implementation_gate.py:126; AC-12 workflow.py:2261; AC-13 adversary_dialog.py:949/1021/1354; AC-14 session_singleton_guard.py:329; AC-15 edit_gate.py:519/526, bash_gate.py:857, post_bash.py:144; AC-16 phase_listener.py:357 → hook_utils.py:1499; AC-17 docs/specs/fix-410-state-integrity-gaps.md:89; AC-18 Vollsuite grün.
Early-Agreement-Skepsis: Lauf-1-Findings gegen aktuellen Stand geprüft, Fangstellen-Sweep in Runde 1. Offene Grenzen im CHANGELOG benannt (Link anlegen/durchschreiben/löschen; Textprüfung; Symlink von außen).
**Implementierer:** Bestätigt; keine weitere Änderung erforderlich.

## Findings
Keine neuen Findings. F001 (HIGH), F002 (LOW) und F003 (LOW) aus Lauf 1 sind bearbeitet und unten als Bestätigungen geführt.

## Confirmations

Confirmation:
  AC: F001 (Lauf 1)
  Code reference: core/hooks/workflow.py:2084
  Evidence: `except UnsafeStateError` vor `except Exception`; SKIPPED mit Grund, `continue`, Marker bleiben; 4 Richtungen plus Gegenprobe grün
  Status: CONFIRMED

Confirmation:
  AC: Input / AC-5 / AC-7
  Code reference: core/hooks/hook_utils.py:1399
  Evidence: `UnsafeStateError(Exception)` ohne OSError/ValueError; F003-Docstring bei 1419-1432
  Status: CONFIRMED

Confirmation:
  AC: AC-1 / AC-2 / AC-3 / AC-4 / AC-6 / AC-8 / Output
  Code reference: core/hooks/hook_utils.py:1471
  Evidence: `dir_fd`-Walk mit O_NOFOLLOW, fstat auf S_ISREG und st_nlink == 1; Wurzel per realpath; Meldung mit Pfad, Grund, Bereinigungsweg
  Status: CONFIRMED

Confirmation:
  AC: AC-16
  Code reference: core/hooks/hook_utils.py:1499
  Evidence: `atomic_write_json` (tempfile + os.replace) liefert neuen Inode; Test grün
  Status: CONFIRMED

Confirmation:
  AC: AC-12
  Code reference: core/hooks/workflow.py:2261
  Evidence: `main()` fängt `UnsafeStateError`, `BLOCKED:` auf stderr, Exit 1
  Status: CONFIRMED

Confirmation:
  AC: AC-9
  Code reference: core/hooks/edit_gate.py:667
  Evidence: Block vor Override-, Phase- und TDD-Prüfung; LoC-Delta schreibt bei Fund nicht zurück
  Status: CONFIRMED

Confirmation:
  AC: AC-9
  Code reference: core/hooks/tdd_enforcement.py:253
  Evidence: `except hook_utils.UnsafeStateError` → `block`; Always-Allowed vorher
  Status: CONFIRMED

Confirmation:
  AC: AC-10 / AC-15
  Code reference: core/hooks/bash_gate.py:1315
  Evidence: nur der Commit-Pfad blockt; `_write_e2e_scope` schreibt bei Fund nicht
  Status: CONFIRMED

Confirmation:
  AC: AC-11 / AC-16
  Code reference: core/hooks/phase_listener.py:363
  Evidence: `_finish_unsafe` ohne Phasenwechsel/Freigabe, Exit 0 mit Warnung; `_save_workflow` atomar
  Status: CONFIRMED

Confirmation:
  AC: AC-11
  Code reference: core/hooks/footer_gate.py:161
  Evidence: `except UnsafeStateError` mit Warnung, nie Exit 2
  Status: CONFIRMED

Confirmation:
  AC: AC-11
  Code reference: core/hooks/post_implementation_gate.py:126
  Evidence: `except UnsafeStateError` → Warnung, `allow()`
  Status: CONFIRMED

Confirmation:
  AC: AC-15
  Code reference: core/hooks/post_bash.py:144
  Evidence: `except (OSError, json.JSONDecodeError, UnsafeStateError)` → kein Zurückschreiben
  Status: CONFIRMED

Confirmation:
  AC: AC-13
  Code reference: core/hooks/adversary_dialog.py:949
  Evidence: Fast-Track False; Metriken warnen (1021); `required-files` Exit 1 (1354)
  Status: CONFIRMED

Confirmation:
  AC: AC-14
  Code reference: core/hooks/session_singleton_guard.py:329
  Evidence: `except UnsafeStateError` → `None`
  Status: CONFIRMED

Confirmation:
  AC: AC-17
  Code reference: docs/specs/fix-410-state-integrity-gaps.md:89
  Evidence: F004 verweist auf die Spec zu #416 und gilt als aufgelöst
  Status: CONFIRMED

Confirmation:
  AC: AC-18 / Side effects
  Code reference: tests/test_state_reader_source_416.py:590
  Evidence: Vollsuite `2477 passed, 23 skipped, 0 failed`; keine neuen Subprozesse, Abhängigkeiten oder Config-Keys
  Status: CONFIRMED

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict: VERIFIED

## Geprüfte Dateien

- sha256:fa5bf9eb79b6a52ff0e960ea89e8d48df5448d385c1ddc3b3b45d6656fededf7  core/hooks/adversary_dialog.py
- sha256:6ea1dc3f7ac6e1d5db4afc760945195d3ee2d4851bd648eec504f15e6729a469  core/hooks/bash_gate.py
- sha256:3326d74297c9257686c6598ba946f1b73eed8d425aca520a4cd73d3514e40548  core/hooks/edit_gate.py
- sha256:b8e12b5d661ccac4688b0e68ab44e71371f8ba3d942d3ab6beafee073f5fac8a  core/hooks/footer_gate.py
- sha256:808fe0243a93379dcb927b92aba8b50d04302abfb9737eea9b36af300f82c788  core/hooks/hook_utils.py
- sha256:d8b213f4cf0e55e234d5be70a5c7e22e174140992a18c25eb80281ef0d8caf92  core/hooks/phase_listener.py
- sha256:35561504fe51ea1317e45a7239862faaca40c0603620e257530444bed2ce39a6  core/hooks/post_bash.py
- sha256:350a32be90d9c7cf63fa343ee65df3c1ee803e9ee4702674b9dfa8c71ae35efb  core/hooks/post_implementation_gate.py
- sha256:81d21c3179232dcb39b3170d965a892abe744d09b8116ad523c9de37a4096b22  core/hooks/session_singleton_guard.py
- sha256:788216a1242faf1f33af02980ae4d1da52fde5275870c60ac8182d82ba96390c  core/hooks/tdd_enforcement.py
- sha256:aa94e307f41fcf404b12bbd8daced39b5e22ac649bdcf73aac9ccf81061657bf  core/hooks/workflow.py
- sha256:4c6e06ffb32cb15e16d94d7f29a4b5e84497920f11fb4bfb688110d9ac1135c3  docs/specs/fix-410-state-integrity-gaps.md
- sha256:9d872ff2a4b76c7b5c7ad6f21cc1e9a943e1c8b43e95e7d69c58ec946875df67  tests/test_state_reader_source_416.py

## Prüfbasis

- base: 592d2bede76eb7b535d2275714b7d58fc59a1959
- blob:e577276066abaf0e7857738e881a82059f2ca788  core/hooks/adversary_dialog.py
- blob:11a38013d52184e92128a52ca132164c45f94e4c  core/hooks/bash_gate.py
- blob:700f4e7a6585617ea4e7cb2fad7b4ee6c4f35b56  core/hooks/edit_gate.py
- blob:5ddaeacadd581adcfb58235d79d6fe969db303bd  core/hooks/footer_gate.py
- blob:2d5239478eadfa10fc6a3b81aebcb09216419ed7  core/hooks/hook_utils.py
- blob:afa4de4f7a568d43215d12306970858ee69ec54e  core/hooks/phase_listener.py
- blob:4ba2c1c9a16a10ec179825d14d69eeb264d38ebb  core/hooks/post_bash.py
- blob:abb64b60211aba4a9f7820b7f313b2b68b5f7c66  core/hooks/post_implementation_gate.py
- blob:64f066752f38769ae508f7a9d19a711f052f7e62  core/hooks/session_singleton_guard.py
- blob:738d8fa581329b7efe9ef37ced88addb9daa2b8b  core/hooks/tdd_enforcement.py
- blob:fbff8b180d70f7351084db74b7a12f7df3e008e3  core/hooks/workflow.py
- blob:15cef63947101dc5ce6383107d6cb04aa0a3a73b  docs/specs/fix-410-state-integrity-gaps.md
- blob:8acb3627753469c914b011da5f59b4bc154363bd  tests/test_state_reader_source_416.py
