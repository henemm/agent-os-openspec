# Context: chore-663-rueckbau-autoclear

## Request Summary
Issue #663 (Epic #649, Schnitt 4): Rückbau des Auto-/clear per Herdr. #662 (v4.23.0) hat es stillgelegt
(`auto_clear_active()` fest False, `maybe_auto_clear` kehrt sofort zurück, `workflow.py autoclear` druckt `AUTO_CLEAR=off`,
`_note_transition_boundary` schreibt nichts). Jetzt wird der tote Code samt Tests gelöscht: Runner, Signale, Sperren,
Grenz-Vermerk `auto_clear_boundary`, Klartext-Vorprüfung, `scripts/e2e_auto_clear.sh`, Spawn, Skip-Log. Herdr-Seitenleiste
(#466) und Plan-Pane (#476) bleiben voll funktionsfähig. Konfig-Schlüssel `herdr.auto_clear` und Env
`OPENSPEC_HERDR_AUTO_CLEAR` bleiben still wirkungslos; `config.yaml` wird in diesem Auftrag NICHT angefasst (Gate-Config).
Danach sind #505, #601, #503 als durch #649 überholt zu schließen (nur benennen).

## Related Files

### core/hooks/herdr_bridge.py (1840 Zeilen, Stand v4.23.0)
| Zeilen | Inhalt | Schicksal |
|--------|--------|-----------|
| 1-93 | Modul-Docstring | umschreiben: Abschnitte Auto-/clear (#467/#597/#598/#506) streichen; Plan-Pane-Absatz (#476/#478/#496) bleibt, Satz zu `maybe_auto_clear` (#478) und „Basis fuer #467" raus (~ -48 Zeilen) |
| 94-364 | Sidebar: `SOURCE`, `AGENT`, `TOKEN_NAMES`, `STATE_TOKENS`, `STEP_LABELS`, `_clean`, `_binary`, `_enabled`, `_pane`, `_next_seq`, `_launch`, `run_herdr`, `_spur_token`, Scope (`parse_session_scope`, `session_scope`), `build_report`, `_base_args`, `clear`, `report_workflow`, `report_active` | BLEIBT |
| 365-383 | Konstanten `AC_LOG_FILE`, `AC_TOKEN_LOCK_FILE`, `AC_BOUNDARY_MAX_AGE_S`, `AC_DEFAULTS`, `AC_SETTLE_S`, `AC_PROMPT_TIMEOUT`, `AC_LOG_MAX_LINES`, `POSITIVE_MARKER`, `NEGATIVE_MARKER`, `AC_SIGNAL_*`, `AC_CLEAR_*`, `AC_SINCE_FUTURE_S`, `AC_CONTINUE_KINDS`, `AC_CLEAR_KEY`, `_PANE_FILE_RE` | löschen; ausser `AC_LOG_MAX_LINES` (von `_ac_log`, das der Plan-Pane braucht, siehe unten) |
| 386-389 | `_hooks_on_path` | BLEIBT (Plan-Pane :1289, :1408, :1724) |
| 391-437 | `_auto_clear_config`, `auto_clear_enabled`, `auto_clear_active` | löschen (Aufrufer siehe unten) |
| 440-472 | `_footer_parts`, `has_clear_marker` | löschen (nur Auto-/clear und `test_herdr_auto_clear_467`) |
| 475-511 | `_ac_base`, `_ac_base_for` | BLEIBT, aber umbenennen (z. B. `_base_dir`): Plan-Pane ruft `_ac_base()` in :1318 |
| 514-544 | `spawn_auto_clear` | löschen |
| 547-581 | `PLUGIN_NAMESPACE`, `MANUAL_COMMANDS`, `_command_name`, `resolve_command_form` | löschen (nur Runner/Test 499); vor dem Löschen per grep gegen `skills/`/Befehle prüfen, dass nichts es benutzt (ist der Fall: nur herdr_bridge + `test_befehlsform_context_titel_499`) |
| 584-660 | `maybe_auto_clear` | löschen |
| 662-670 | `_klartext_hits` (die Klartext-Vorprüfung; `klartext_gate.py` selbst bleibt unangetastet) | löschen |
| 673-719 | `_context_cut_active`, `_record_context_cut_boundary` | löschen |
| 721-764 | `_boundary_matches`, `_boundary_fresh`, `_consume_boundary` | löschen |
| 766-797 | `_ac_skip` (Skip-Log) | löschen |
| 799-813 | `_ac_log` | BLEIBT (Plan-Pane-Log :1345 `_ac_log(line, PP_LOG_FILE)`), umbenennen (`_log`), Default-Logdatei-Argument ohne `AC_LOG_FILE` |
| 816-853 | `_signal_path`, `record_signal` | löschen |
| 854-882 | `SIGNAL_ACTIVITY_KINDS`, `run_signal` | löschen |
| 883-1268 | `read_signal`, `_signal_at`, `_parse_since`, Runner-Klasse `_Runner`, `run_auto_clear` | löschen (ca. 385 Zeilen) |
| 1270-1840 | Plan-Pane (`PP_*`, `open_plan_pane`, `_pp_*`, `run_plan_pane`, `run_plan_pane_close`) | BLEIBT |
| 1819-1840 | `__main__`-Zweig | `auto-clear`- und `signal`-Zweige streichen, `plan-pane`/`plan-pane-close` bleiben |

Bilanz `herdr_bridge.py`: ca. 905 Zeilen Auto-/clear-Block (365-1268) plus ca. 45 Docstring, ca. 8 `__main__`; wegen der beiden Hilfen ca. 40 Zeilen bleibend → netto ca. **-920 Zeilen** (Datei danach ca. 920 Zeilen). Der Auftrag nannte ~1800 Zeilen; real sind es rund 920 Zeilen in der Bridge, der große Rest liegt in den Tests.

### Aufrufer und Rest-Stellen außerhalb der Bridge
| Stelle | Inhalt | Änderung |
|--------|--------|----------|
| core/hooks/footer_gate.py:191-219 `_maybe_auto_clear`, :210-219 `_discard_boundary`, :222-234 `_record_stop`, Aufrufe :244 (`_record_stop()` in `main`), :265 (`_maybe_auto_clear`), dazu der `_discard_boundary`-Aufruf im Pfad „zweimal falsche Fusszeile" (#497a) | einziger Aufrufer von `maybe_auto_clear`/`_consume_boundary`/`record_signal("stop")` | alle drei Helfer und Aufrufe löschen (ca. -45); Fusszeilen-Prüfung selbst unverändert |
| core/hooks/phase_listener.py:468-475 | `record_signal("input")` | Block löschen (-8); `report_workflow` (:362) bleibt |
| core/hooks/session_banner.py:~585-592 | `record_signal("session", …)` | Block löschen (-8); `report_active` (:599) und `open_plan_pane_for_active` (:604) bleiben |
| core/hooks/session_singleton_guard.py:~970-988 | `_record_activity` mit `record_signal("activity","pretooluse")` und sein Aufruf im PreToolUse-Pfad | Funktion und Aufruf löschen (-20) |
| core/hooks/workflow.py:2367-2405 | `AUTO_CLEAR_BOUNDARIES`, `_boundary_timestamp`, `_note_transition_boundary` (+ alle Aufrufe in den Phasenwechsel-/Approval-Pfaden) | löschen (-40 plus Aufrufstellen; Aufrufer per `grep _note_transition_boundary` suchen) |
| core/hooks/workflow.py:5310-5320 `cmd_autoclear` + :6012 Tabelle `"autoclear": cmd_autoclear` | stille Auskunft `AUTO_CLEAR=off` | siehe Bewertung unten: BLEIBT als Einzeiler |
| core/hooks/workflow.py:5323-5360 `_record_auto_clear_boundary` | | löschen (-40) |
| hooks/hooks.json:156, 168, 184 | `herdr_bridge.py signal activity` (Notification `permission_prompt`, PermissionRequest, SessionEnd) | die drei Hook-Einträge löschen (ggf. leere Event-Blöcke Notification/PermissionRequest ganz entfernen); `:179 plan-pane-close` bleibt |
| core/hooks/hook_utils.py, klartext_gate.py, post_bash.py | nur `context_stop_applies`/`context_cut_note` (seit #662 ohne Herdr); keine Rest-Stelle | keine Änderung (zur Sicherheit `grep auto_clear_active` nach dem Löschen) |
| core/hooks/alias_sync.py, setup.py (außer Zeile 1390), templates/, sync_cloud_hooks | kein Auto-/clear-Bezug (nur `BEFEHLSTEXT FEHLT`-Treffer) | keine Änderung; `setup.py:1390` ist Text zum Kontext-Haushalt ohne Auto-/clear-Pflichtteil, per Lesen prüfen |
| scripts/e2e_auto_clear.sh | 945 Zeilen E2E gegen echtes Herdr | DELETE; keine Referenz in `.github/workflows` oder `scripts/*.py` gefunden |
| scripts/e2e_plan_pane.sh:63, :142 | setzt `OPENSPEC_HERDR_AUTO_CLEAR` zurück bzw. schreibt Config `auto_clear:` | belassen (harmlos, hält die E2E-Umgebung sauber); optional später |
| core/commands/*.md, skills/*, .claude/agents | seit #662 frei von Auto-/clear (grep ohne Treffer) | keine Änderung, kein Sync nötig |

### Config / Env
`config.yaml:395-409` (Kommentar + `auto_clear:`-Block) ist Gate-Config und wird laut Auftrag NICHT geändert. Folge: der Schlüssel bleibt als Wirkungsloses stehen (Kommentar behauptet noch Funktion; irreführend, aber Folge-Aufräumen mit eigenem Auftrag). `OPENSPEC_HERDR_AUTO_CLEAR` wird nirgends mehr gelesen, sobald `_auto_clear_config` weg ist. Kein Config-Schema-Test hängt an `herdr.auto_clear` (grep in Tests nur die zu löschenden Dateien und `test_context_stop_658`).

## Bewertung `workflow.py autoclear`
Empfehlung: **bleibt als Einzeiler** (`cmd_autoclear` druckt `AUTO_CLEAR=off`, 4 Zeilen plus Tabelleneintrag; Docstring ohne „Wegfall mit #663").
- Konsumenten pinnen Plugin-Versionen; alte gecachte Befehlstexte (≤ 4.22) rufen `workflow.py autoclear` und lesen `AUTO_CLEAR=` (#489). Entfiele der Subcommand, bekäme ein solcher Befehlstext „Unbekannter Befehl" mit Exit ≠ 0 und die Kette bräche an Phase 1/2/3/5 ab.
- Kosten der Behaltens: 5 Zeilen und ein Test, der `off` pinnt (`test_auto_chain_flat_662`, `test_kette_auto_clear_489::test_autoclear_cli`, `test_auftrag_551`).
- Löschen kann ein späteres Issue, sobald die Pin-Spanne der Konsumenten ≥ 4.23.0 ist (nicht prüfbar aus diesem Repo → Entscheidung Claude: behalten).

## Tests

### Komplett löschbar (nur Auto-/clear)
| Datei | Zeilen | Tests |
|-------|--------|-------|
| tests/test_herdr_auto_clear_467.py | 534 | 17 (Helfer `AUTO_ON`, `_hook_case`, `WF` werden von 499/551/478 importiert, siehe unten) |
| tests/test_autoclear_boundary_495.py | 158 | 6 |
| tests/test_autoclear_transition_497.py | 319 | 5 |
| tests/test_autoclear_kontextschnitt_598.py | 140 | 8 |
| tests/test_autoclear_retry_597.py | 770 | 6 |
| tests/test_autoclear_eigene_signale_506.py | 1388 | 22 |
| tests/test_auto_clear_global_480.py | 222 | 6 |
| scripts/e2e_auto_clear.sh | 945 | (E2E-Skript) |
Summe: 7 Testdateien, 3531 Zeilen, 70 Tests, plus 945 Zeilen Skript.

### Gemischt / umschreiben
| Datei | Zeilen / Tests | Was |
|-------|----------------|-----|
| tests/test_befehlsform_context_titel_499.py | 518 / 11 | importiert Helfer aus `test_herdr_auto_clear_467`; prüft `resolve_command_form` (Runner-Befehlsform, löschen) und Kontext-/Titel-Anteile (#499: Titel/Context der Phasenbefehle). Auto-/clear-Tests löschen, Rest prüfen; Helfer-Import ersetzen. Netto ca. -300 |
| tests/test_herdr_plan_deploy_sessionstart_478.py | 427 / 9 | Plan-Pane/SessionStart (bleibt) plus `test_auto_clear_never_logs_skip_reason`, Runner-Stub `RUNNER_BOUNDARY_AT`, `AUTO_ON`, `.session.json`-Signal-Stub; Auto-/clear-Teile (ca. 3 Tests, ca. 100 Zeilen) löschen |
| tests/test_auftrag_551.py | 771 / 9 | Auto-/clear-Block :220-240, :596-602, :628-635, :755-760: Tests der `autoclear`-Auskunft `off` BLEIBEN, nur Fall-Helfer (`_autoclear_case` importiert `AUTO_ON, _hook_case, WF` aus 467) auf eigenen kleinen Helfer umstellen; kein `auto_clear_boundary`-Assert mehr nötig (Feld existiert nicht mehr, ein „nicht vorhanden"-Assert ist trivial erfüllt, löschbar) |
| tests/test_context_stop_658.py | 376 / 7 | Fälle `HERDR_AUTO_CLEAR_*` und `auto_clear_env` bleiben gültig als Beleg „Config/Env wirkungslos" und `herdr_bridge.auto_clear_active = boom` (:260) bricht, weil die Funktion fehlt → diesen Test umstellen (z. B. `herdr_bridge` wirft beim Import) |
| tests/test_kette_auto_clear_489.py | 85 / 3 | `test_autoclear_cli` (`off`), `test_chain_commands_*`, `test_skills_in_sync`: bleiben, `autoclear`-CLI-Zeile bleibt |
| tests/test_auto_chain_flat_662.py | 553 / 7 | pinnt „stillgelegt" über `auto_clear_active`, `maybe_auto_clear`, Spawn-Stubs; umschreiben auf neue Wahrheit: (a) `autoclear` → `off` überall, (b) `herdr_bridge` hat die Symbole nicht mehr (`not hasattr`, einmalig), (c) Env `OPENSPEC_HERDR_AUTO_CLEAR=1` + Pane: kein Prozess, kein `herdr_auto_clear.log`, kein `herdr_signals`-Ordner, kein `auto_clear_boundary` im State, (d) Phasen-/Stop-/Prompt-Hooks laufen mit Pane ohne Fehler (Exit 0). Erwartet ca. 553 → 200 |
| tests/test_vorlagen_klartext_597.py | 139 / 2 | prüft Vorlagen auf Klartext (ein Treffer „Spec: …autoclear-klartext"); unabhängig, prüfen mit `pytest`, vermutlich unverändert |
| tests/test_clear_checkpoint_blocks.py | – | hat eigene Konstanten `POSITIVE_MARKER`/`NEGATIVE_MARKER`, importiert nichts aus der Bridge; unverändert (Checkpoint-Blöcke für manual bleiben) |

Seitenleiste/Plan-Pane-Tests ohne Auto-/clear-Bezug und unverändert: `test_herdr_sidebar_466.py` (17), `test_herdr_plan_pane_476.py` (14), `test_herdr_plan_pane_reuse_493.py` (10). Sie müssen nach dem Rückbau grün sein und sind das Regressionsnetz für „Sidebar/Plan-Pane bleiben funktionsfähig"; ihre Stub-Binaries brauchen `herdr_bridge` nur über `report_*`, `open_plan_pane`, `run_plan_pane*`.

Geschätzte Testbilanz: ca. -3900 Zeilen Tests (7 Dateien komplett ca. -3531, Teilkürzungen ca. -650, Neufassung ca. +150), ca. -85 Tests.

## Doku-Stellen
| Datei | Stelle | Änderung |
|-------|--------|----------|
| CLAUDE.md | :75 Architektur-Zeile herdr_bridge, :335 Stop-Absatz („Das Herdr-Auto-/clear … stillgelegt"), :478 Tabellenzeile | auf „Sidebar (#466), Plan-Pane (#476)" kürzen, „stillgelegt/Rueckbau #663" streichen bzw. „entfernt (#663)"; Hinweis `autoclear` bleibt als Kompatibilitätszeile (eine Halbzeile). `claude_md_protection.py` schützt vor Aufblähung → Zeilen netto kürzen |
| README.md | :311 (Kontext-Absatz) | pro Stand v4.23.0 schon ohne Auto-/clear; per grep kein Treffer mehr (Treffer nur BEFEHLSTEXT) → keine Änderung |
| setup.py:1390 | Konsumenten-Hinweis | schon aktuell; keine Änderung |
| CHANGELOG.md | `[Unreleased]` leer | Eintrag „Rückbau Auto-/clear (#663)"; Einzel-Auslieferung: Eintrag direkt als `[4.24.0]` (Entfernung öffentlicher Subcommands `signal`/`auto-clear` und Config-Wirkung = Minor), `.claude-plugin/plugin.json` 4.23.0 → 4.24.0 im selben PR |
| docs/specs/* (feat-467, fix-489/495/497/506/597/598, feat-480 usw.) | historisch | nicht ändern; die Spec für #663 vermerkt sie als „abgelöst durch Epic #649 / #662 / #663" |
| docs/reference/ | existiert in diesem Repo nicht | – |

## Existing Patterns
- Rückbau-Muster wie #662: ein zentraler Helfer-Schalter, danach Löschung; hier die zweite Hälfte.
- `herdr_bridge.py` ist fail-open und still: nach dem Löschen bleiben nur noch drei CLI-Modi im `__main__` (`plan-pane`, `plan-pane-close`).
- `hooks.json`-Einträge dürfen nicht auf nicht mehr vorhandene CLI-Modi zeigen: `signal activity` ruft sonst `herdr_bridge.py` auf, das (dank `except BaseException` und Exit 0) still nichts täte, aber ein sinnloser Prozessstart je Event bliebe → Einträge entfernen.
- Migration alter Zustände: bestehende Workflow-JSONs können noch `auto_clear_boundary` enthalten, `.claude/herdr_signals/`, `herdr_auto_clear.log`/`.lock` können in Projekten liegen. Nichts liest sie mehr; State-Schlüssel stören nicht (Workflow-State ist ein offenes Dict). Kein Migrationscode nötig; der Plan-Pane-Pfad benutzt weiterhin `.claude/herdr_plan_pane.*`.

## Dependencies
- Upstream: #662 (gemergt, 4.23.0), Epic #649.
- Downstream: Konsumenten-Projekte mit gepinnten älteren Plugin-Versionen (alte Befehlstexte rufen `autoclear` → bleibt); Hook-Registrierungen in Konsumenten-`settings.json` (Copy-Modus, `setup.py --update`) enthalten ggf. noch `herdr_bridge.py signal activity` — nach dem Update zeigt das auf ein Bridge-Skript ohne `signal`-Modus; weil `__main__` jede Ausnahme schluckt und mit 0 endet, bleibt es harmlos. `setup.py --update` räumt veraltete Einträge über das Manifest auf bzw. schreibt die neue Fassung; per Test/Lesen von `setup.py` bestätigen (offen, siehe unten).
- Zu schließen nach dem Merge (nur benennen): #505, #601, #503 (durch #649 überholt), dann #663, danach Epic #649.

## Risks & Considerations
- Gemeinsame Helfer nicht mitlöschen: `_ac_base`/`_ac_base_for` und `_ac_log` (Plan-Pane :1318, :1345), `_hooks_on_path`, `_CONTROL_RE`, `AC_LOG_MAX_LINES`. Vorab `grep` gegen Zeilen > 1269 (hier gemacht: nur diese vier Treffer) und danach die Plan-Pane-Tests laufen lassen.
- `_record_stop`/`record_signal("stop")` fiele aus `footer_gate` (Stop-Hook läuft in jedem Konsumentenprojekt): Änderung klein, aber `fail-open` bleibt tragend; `test_footer_gate*` und `test_herdr_*` müssen grün bleiben.
- Das gate-geschützte `core/hooks/`: Schreiben dort braucht ab Phase 6 den laufenden Workflow (Override nicht nötig, #322). `hooks/hooks.json` und `config.yaml` sind Gate-Config (bash_gate schützt „wirksame Gate-Config"): `hooks.json`-Änderung ist Teil dieses Schnitts, `config.yaml` bewusst nicht.
- Sehr großer Löschanteil: Tests löschen sich leicht, aber `tests/test_herdr_auto_clear_467.py` exportiert Helfer (`AUTO_ON`, `_hook_case`, `WF`, Stub-Herdr), die `499`, `551`, `478` importieren; vor dem Löschen Abhängigkeiten umstellen, sonst bricht die Sammlung (ImportError) und rote CI.
- LoC-Limit (±250 je Schnitt) ist für einen Rückbau nicht sinnvoll anwendbar; reine Löschungen zählen als Rückbau, geringes Risiko je Zeile. Für die Spec: ADR-/Scope-Hinweis „Löschung ohne neue Logik" begründen (oder Teilung, siehe unten).
- Kein Produktkonflikt: PO hat Rückbau im Epic entschieden; Verhalten für Nutzer ändert sich nicht (seit #662 inaktiv).

## Analysis

### Type
Chore / Refactoring (Rückbau toten Codes, kein Verhalten; Epic #649 Schnitt 4).

### Affected Files (with changes)
| File | Change Type | Description | LoC netto |
|------|-------------|-------------|-----------|
| core/hooks/herdr_bridge.py | MODIFY | Auto-/clear-Block 365-1268 (außer `_ac_base*`, `_ac_log`, `_hooks_on_path`) und Docstring-Teile löschen; `__main__` auf `plan-pane*` kürzen; Helfer umbenennen | ca. -920 |
| core/hooks/footer_gate.py | MODIFY | `_maybe_auto_clear`, `_discard_boundary`, `_record_stop` + Aufrufe entfernen | ca. -45 |
| core/hooks/workflow.py | MODIFY | `AUTO_CLEAR_BOUNDARIES`, `_boundary_timestamp`, `_note_transition_boundary` + Aufrufstellen, `_record_auto_clear_boundary`; `cmd_autoclear` bleibt als Einzeiler (Docstring) | ca. -90 |
| core/hooks/phase_listener.py | MODIFY | `record_signal("input")`-Block entfernen | ca. -8 |
| core/hooks/session_banner.py | MODIFY | `record_signal("session")`-Block entfernen | ca. -8 |
| core/hooks/session_singleton_guard.py | MODIFY | `record_signal("activity")`-Helfer und Aufruf entfernen | ca. -20 |
| hooks/hooks.json | MODIFY | drei `signal activity`-Einträge löschen | ca. -25 |
| scripts/e2e_auto_clear.sh | DELETE | | -945 |
| tests/test_herdr_auto_clear_467.py, test_autoclear_boundary_495.py, test_autoclear_transition_497.py, test_autoclear_kontextschnitt_598.py, test_autoclear_retry_597.py, test_autoclear_eigene_signale_506.py, test_auto_clear_global_480.py | DELETE | 7 Dateien, 70 Tests | -3531 |
| tests/test_befehlsform_context_titel_499.py, test_herdr_plan_deploy_sessionstart_478.py, test_auftrag_551.py, test_context_stop_658.py, test_auto_chain_flat_662.py | MODIFY | Auto-/clear-Teile löschen, Helfer-Importe lösen, Pinn-Test neu fassen | ca. -750 / +150 |
| CLAUDE.md | MODIFY | herdr_bridge-Beschreibungen (3 Stellen) kürzen | ca. -3 |
| CHANGELOG.md, .claude-plugin/plugin.json | MODIFY | Eintrag, Version 4.24.0 | ca. +12 |
| config.yaml | KEIN CHANGE | Gate-Config, Auftrag verbietet; wirkungsloser Schlüssel bleibt | 0 |

### Scope Assessment
- Dateien: 7 Code/Config + 1 Skript + 7 Testdateien gelöscht + 5 Testdateien geändert + 3 Doku = ca. 23 Dateien.
- LoC: Code ca. -1115, Skript -945, Tests ca. -4100 netto; insgesamt ca. **-6100 Zeilen**, Neuanteil nur ca. +160 (Pinn-Test, Changelog). Gelöschte Produktionszeilen ca. 1115 (unter der 1500-Marke), mit Skript ca. 2060, mit Tests ca. 6000.
- Risiko: niedrig bis mittel. Produktcode: nur Löschung toter Pfade plus Umbenennung zweier Helfer des Plan-Panes; Hauptrisiken sind (1) versehentlich mitgelöschte Plan-Pane-Helfer, (2) ImportError in Tests, die Helfer aus `test_herdr_auto_clear_467` importieren, (3) `hooks.json`-/Konsumenten-Altregistrierungen (harmlos dank fail-open).
- Teilung: Empfehlung **ein Schnitt**. Begründung: Die Löschung ist atomar (Runner, Signale, Vermerk, Aufrufer hängen aneinander; ein Zwischenstand mit gelöschtem `record_signal` aber stehendem Aufrufer oder umgekehrt ist fehleranfälliger als eine Gesamtlöschung, vor allem für die Stop-/Prompt-Hooks, die in jedem Konsumentenprojekt laufen). Die CI prüft alles in einem Lauf. Falls Review-Größe stört (PR ca. 6000 gelöschte Zeilen, dennoch lesbar, weil nur Löschung): Notteilung a) `herdr_bridge.py` Runner/Signale + deren Aufrufer (footer_gate, phase_listener, session_banner, session_singleton_guard, hooks.json) + Tests 467/506/597/598/480, b) workflow.py-Vermerk (`AUTO_CLEAR_BOUNDARIES`, `_note_transition_boundary`, `_record_auto_clear_boundary`) + Test 495/497 + Skript + Doku; a) ist ohne b) lauffähig, weil `_note_transition_boundary` seit #662 über `auto_clear_active()` schon nichts schreibt (dazu müsste `auto_clear_active` in a) bleiben, was die Löschung unsauber macht). Daher nur als Rückfall.

### Technical Approach
Reihenfolge im Schnitt: (1) Tests zuerst umbauen: Helfer-Importe aus `test_herdr_auto_clear_467` in 499/551/478 durch kleine lokale Helfer ersetzen, `test_auto_chain_flat_662` auf „Symbole gibt es nicht mehr, Env/Config bewirken nichts" neu fassen, `test_context_stop_658` (`auto_clear_active = boom`) anpassen; danach die sieben reinen Auto-/clear-Dateien und das E2E-Skript löschen. (2) Aufrufer entfernen (`footer_gate`, `phase_listener`, `session_banner`, `session_singleton_guard`, `hooks.json`). (3) In `herdr_bridge.py` den Block löschen, `_ac_base`/`_ac_log` zu `_base_dir`/`_log` umbenennen, `__main__` kürzen. (4) `workflow.py`: Vermerk-Funktionen samt Aufrufstellen weg, `cmd_autoclear` bleibt als stiller Einzeiler `AUTO_CLEAR=off` (Kompatibilität gecachter Befehlstexte). (5) CLAUDE.md/CHANGELOG/Version. Prüfung: `pytest` über Sidebar-, Plan-Pane-, 478-, Footer-Gate-, Workflow-, Kontext-Tests sowie `scripts/sync_skills.py --check`; `python3 -m py_compile` auf Hooks; `grep -rn "record_signal\|maybe_auto_clear\|auto_clear_boundary\|AUTO_CLEAR_BOUNDARIES\|herdr_signals" core hooks scripts tests` muss leer sein (bis auf Pinn-Test und die Kompatibilitätszeile).

Alternativen:
- **A) `autoclear`-Subcommand ebenfalls löschen:** sauberer, aber bricht alte gecachte Befehlstexte (Exit ≠ 0 mitten in der Kette). Verworfen, solange Pin-Spanne unbekannt; Folge-Issue möglich.
- **B) Nur Runner löschen, Signale/Vermerk stehen lassen:** weniger Diff, aber `record_signal` und `signal activity`-Hooks schreiben weiter Dateien ohne Leser; verfehlt den Auftrag („Signale"). Verworfen.
- **C) Config-Schlüssel mitentfernen (`config.yaml` aufräumen):** wäre konsequent, Auftrag untersagt ausdrücklich (Gate-Config, autarker Auftrag). Zurückgestellt, als Folge-Issue mit PO-/Gate-Freigabe.
- **D) Zweistufig a/b:** siehe Scope; nur Rückfall.
ADR: keine neue; Spec vermerkt, dass die Entscheidungen aus feat-467/fix-489/495/497/506/597/598/480 durch Epic #649 abgelöst sind und mit #663 vollständig entfallen.

### Dependencies
- #662 gemergt; Epic #649; Folgeschritte: Schließen von #505, #601, #503 (überholt), #663, Epic #649.
- Konsumenten: alte Befehlstexte (`autoclear`), Copy-Modus-`settings.json` mit `signal activity`-Hook (wirkungslos, fail-open).

### Open Questions
Keine Produktfrage. Technisch für die Spec zu bestätigen (Claude entscheidet):
1. `setup.py --update` und `hooks.json` im Copy-Modus: räumt das Update alte `herdr_bridge.py signal activity`-Registrierungen in Konsumenten-`settings.json` auf, oder bleiben sie liegen? (Folge: harmlos, aber evtl. Hinweis im CHANGELOG.) Zu prüfen in `setup.py`-Hook-Merge-Logik.
2. `config.yaml`-Kommentar `herdr.auto_clear` bleibt aufgrund der Auftragsgrenze irreführend; Folge-Issue für das Gate-Config-Aufräumen anlegen (oder in Spec als „Known Limitation" vermerken).
3. Versionssprung: 4.24.0 (Minor, öffentliche CLI-Modi entfallen) statt 4.23.1 — Empfehlung 4.24.0.
