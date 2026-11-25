# Context: feat-662-kette-flach

## Request Summary
Issue #662 (Epic #649, Schnitt 3): Im Auto-Modus (`AUTONOMY=auto`) setzt die Hauptsitzung die Phasenkette
überall selbst fort, auch im Herdr-Pane. Heute beendet jeder Phasenbefehl bei `AUTO_CLEAR=on` den Turn, damit
Herdr `/clear` + Folgebefehl tippt (#467, fehleranfällig: #505, #598, #601). Neu: kein Turn-Ende mehr für Herdr;
`CONTEXT_STOP=on` nur noch im Modus `manual`; der Stop-Hook startet keinen Auto-/clear-Lauf mehr. Checkpoint-Blöcke
bleiben für `manual`. Halt nur an PO-Punkten (approved ohne Auto-Freigabe, AMBIGUOUS, Override, Produktfragen).
Code-Rückbau (Runner, Signale, Grenz-Vermerk, ~1800 Zeilen `herdr_bridge.py`) ist Schnitt 4 (#663), nicht hier.
Entscheidung im Epic: flach statt verschachtelt (Cloud: `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`).

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/workflow.py:5308 `cmd_autoclear` | gibt `AUTO_CLEAR=on|off` aus; `on` = `herdr_bridge.auto_clear_active()` und kein autarker Auftrag; bei `on` schreibt es per `_record_auto_clear_boundary` (:5334) den Grenz-Vermerk |
| core/hooks/workflow.py:2367-2405 `AUTO_CLEAR_BOUNDARIES`, `_note_transition_boundary` | Phasenwechsel (1→2, 2→3, 3→4, 5→6, 6b→7) schreibt Vermerk `auto_clear_boundary`, Bedingung hier **direkt** `herdr_bridge._pane() and auto_clear_enabled()` (nicht über `auto_clear_active`) |
| core/hooks/workflow.py:5463-5520 `cmd_context` | `CONTEXT_STOP` über `hook_utils.context_stop_applies()` (:5505) |
| core/hooks/hook_utils.py:2796 `context_stop_applies` | True bei Modus != auto ODER `herdr_bridge.auto_clear_active()` — hier fällt der Herdr-Zweig weg |
| core/hooks/hook_utils.py:2818 `context_cut_note` | Hinweiswortlaut `stop=True/False`; Text „Auto-Modus ohne automatisches /clear (kein Herdr-Auto-/clear)" (:2842) umformulieren |
| core/hooks/herdr_bridge.py:391 `_auto_clear_config`, :425 `auto_clear_enabled`, :430 `auto_clear_active` | Opt-in-Schalter (Config `herdr.auto_clear.enabled`, Env `OPENSPEC_HERDR_AUTO_CLEAR`); `auto_clear_active` = Pane und enabled |
| core/hooks/herdr_bridge.py:586 `maybe_auto_clear` | Stop-Hook-Einstieg: prüft `_pane()`, `_auto_clear_config()`, Vermerk, Klartext; ruft `spawn_auto_clear` (:516) |
| core/hooks/herdr_bridge.py:671 `_context_cut_active`, :701 `_record_context_cut_boundary` | #598: Stop beim Kontext-Schnitt zählt ohne Vermerk als Grenze (Schnitt-4-Rückbau) |
| core/hooks/herdr_bridge.py:1225 `run_auto_clear` + Runner-Klasse (~:960-1225), `record_signal` :823, `run_signal` :856 | Runner und Signale (#506); werden nach Schnitt 3 nie mehr gestartet, aber noch nicht gelöscht |
| core/hooks/footer_gate.py:191 `_maybe_auto_clear`, :210 `_discard_boundary`, :222 `_record_stop`, :265 Aufruf | einziger Aufrufer von `maybe_auto_clear` (Stop-Hook); `_record_stop` schreibt Stop-Signal für den Runner |
| hooks/hooks.json:156,168,184 (`herdr_bridge.py signal activity`), :179 `plan-pane-close` | Aktivitäts-Signale für den Runner; ohne Runner wirkungslos, Entfernen = Schnitt 4 |
| core/hooks/session_banner.py:587 `record_signal("session", …)` | Session-Signal für den Runner (Schnitt 4) |
| core/commands/10-context.md:167-176, 20-analyse.md:202-211 | Absatz „Herdr-Auto-/clear: Turn an der Grenze beenden (#489)" mit `workflow.py autoclear` / `AUTO_CLEAR=on`; dazu Verweis „Herdr-Auto-Clear #467" im Auto-Absatz davor |
| core/commands/30-write-spec.md:188-192 (Step 4b `AUTO_APPROVE=done`), :245-253 (After Approval) | zwei Stellen mit `autoclear`-Prüfung vor dem Selbstaufruf von `40-tdd-red` |
| core/commands/40-tdd-red.md:183-189, 50-implement.md:405-411 | Kontext-Absatz + `autoclear`-Absatz („Bei `AUTO_CLEAR=off:` …" mit hängendem Doppelpunkt); Kette gilt hier **unabhängig vom Autonomie-Modus** (#472) |
| core/commands/60-validate.md, 70-deploy.md | kein Herdr-Auto-/clear-Bezug (nur Namens-Treffer „herdr-Workspace") |
| config.yaml:393-411 (`herdr.auto_clear`, Kommentar), :336 | Config-Schlüssel und Kommentar zu `/clear` |
| skills/{10,20,30,40,50}-*/SKILL.md, .claude/agents | Generat (`scripts/sync_skills.py`, `sync_cloud_agents.py`) |
| scripts/e2e_auto_clear.sh (~850 Zeilen), scripts/e2e_plan_pane.sh | E2E gegen echtes Herdr-Binary; E2E-Auto-/clear wird gegenstandslos (Schnitt 4) |

Seitenleiste/Endzustand: `herdr_bridge.report` und `next_step`/`expected_footer_command` kennen Auto-/clear nicht
(grep ohne Treffer außerhalb der oben genannten Stellen); `POSITIVE_MARKER` ("`/clear` ist jetzt gefahrlos",
herdr_bridge.py:375) wird nur von `has_clear_marker` und den Klartext-/Checkpoint-Tests benutzt. Es gibt also
keine ⏳/❗-Sonderlogik für Auto-/clear, die mitzuziehen wäre. `footer_gate` selbst bleibt unverändert (prüft nur
die Du-Zeile).

## Existing Patterns
- Auskunfts-CLI mit Ein-Zeilen-Signal (`autoclear`, `context`, `autonomy`): Exit 0, fail-open auf `off`. Alte, vom
  Plugin-Cache gelieferte Befehlstexte lesen `AUTO_CLEAR=`/`CONTEXT_STOP=`; bleibt `autoclear` bestehen und liefert
  immer `off`, verhalten sie sich auch ohne Textänderung richtig (Rückwärtskompatibilität, Schnitt 4 löscht dann die Zeile).
- Zentrale Entscheidungs-Helfer statt Verteilung (#658 `context_stop_applies`, `auto_clear_active`).
- Schalter-Vorrang: Projekt `false` > Projekt `true` > Env `OPENSPEC_HERDR_AUTO_CLEAR` (#480). Der PO kann die Env global
  gesetzt haben, ein bloßes Default-off in `config.yaml` reicht deshalb NICHT.

## Dependencies
- Upstream: #658 (`CONTEXT_STOP`, `context_stop_applies`, `auto_clear_active`), `autonomy_mode()`.
- Downstream: Phasenbefehle 10–50, `post_bash.py`-Hinweis (`context_cut_note`), Stop-Hook `footer_gate`,
  Tests (siehe unten), Schnitt 4 (#663) räumt Runner, Signale, Vermerk, `maybe_auto_clear`, `config.yaml` herdr.auto_clear, E2E-Skript auf.

## Existing Specs
- docs/specs/fix-658-context-stop-auto.md (Vorarbeit)
- docs/specs/feat-467-herdr-auto-clear.md, fix-489-kette-auto-clear.md, fix-495-autoclear-mechanisch.md,
  fix-497-autoclear-grenze-beim-phasenwechsel.md, fix-506-autoclear-ohne-herdr-status.md,
  fix-597-autoclear-klartext.md, fix-598-autoclear-kontextschnitt.md, feat-480-auto-clear-global.md (alle Gegenstand des Rückbaus)
- docs/specs/feat-551-auftragsliste.md (AUTARK: Kette läuft schon ohne Halt)

## Tests, die das heutige Verhalten pinnen (brechen bei „nie halten / nie spawnen")
| Testdatei | Betroffene Tests (brechen oder werden umgeschrieben) |
|-----------|------|
| tests/test_kette_auto_clear_489.py | `test_autoclear_cli` (erwartet `AUTO_CLEAR=on` im Pane); `test_chain_commands_check_autoclear[*]` (verlangt `autoclear`-Aufruf, `AUTO_CLEAR=on`, „NICHT selbst" in 10–50) — nur bei Textänderung |
| tests/test_context_stop_658.py | `test_auto_with_herdr_auto_clear_stop_on` (Auto + Herdr → on; künftig off), `test_autoclear_output_unchanged` (pane-clear-on → `AUTO_CLEAR=on`), `test_post_bash_note_wording_per_variant` ("auto mit Herdr-Auto-Clear"-Variante), `test_phase_commands_read_context_stop` (Wortlaut-Asserts an Text), `test_auto_without_herdr_stop_off_with_reason` (Wortlaut Reason bleibt) |
| tests/test_kontext_haushalt.py | `test_phase_commands_stop_chain_at_context_cut[*]` (Absatz-Wortlaut), `test_workflow_context_on_for_session_and_newest_fallback` (Env-Autonomie prüfen) |
| tests/test_herdr_auto_clear_467.py (561 Z.) | alle Hook-Pfad-Tests: `test_hook_spawns_runner_and_returns_immediately`, `test_spawn_when_stop_hook_active`, `test_second_identical_stop_does_not_double_type`, `test_no_spawn_*`-Familie (bleibt grün, Ursache aber anders); Runner-Tests (`test_runner_*`) rufen `run_auto_clear` direkt und bleiben grün |
| tests/test_autoclear_boundary_495.py | `test_autoclear_on_records_boundary`, `test_spawn_with_boundary_without_positive_marker`, `test_single_boundary_types_once`, `test_boundary_consumed_after_typing`, `test_boundary_consumed_by_negative_veto`, `test_boundary_kept_*` (spawnen/Vermerk) |
| tests/test_autoclear_transition_497.py | `test_phase_command_records_boundary_per_table`, `test_approval_paths_record_boundary`, `test_footer_gate_stop_hook_active_discards_boundary`, `test_at_has_timezone_and_reader_accepts_both` (Vermerk beim Phasenwechsel) |
| tests/test_autoclear_kontextschnitt_598.py | `test_context_cut_without_boundary_spawns_runner`, `test_context_cut_records_boundary_before_spawn` |
| tests/test_autoclear_retry_597.py | `test_stop_hook_active_stop_spawns_runner`, `test_spawn_keeps_boundary_and_has_no_once_lock`, `test_klartext_pre_check_skips_and_keeps_boundary` (Hook-Pfad); Runner-interne Tests bleiben |
| tests/test_autoclear_eigene_signale_506.py | nur die vier Hook-Pfad-Tests (footer_gate schreibt Stop-Marker u. ä.) — Runner/Signal-Tests bleiben unberührt, solange Schnitt 4 den Code nicht löscht |
| tests/test_auto_clear_global_480.py | `test_footer_gate_spawns_with_env_switch`; Konfig-Tests (`test_env_switch_*`, `test_project_value_wins_over_env`) bleiben grün, sofern `auto_clear_enabled()`/`_auto_clear_config()` unangetastet bleiben |
| tests/test_herdr_plan_deploy_sessionstart_478.py | `test_auto_clear_logs_skip_reason_only_when_enabled` (Skip-Log bei Opt-in) |
| tests/test_befehlsform_context_titel_499.py, test_vorlagen_klartext_597.py | Runner-/Vorlagenprüfung, nur Hook-Pfade; vor dem Bauen mit `pytest` prüfen |
| tests/test_auftrag_551.py | `AUTO_CLEAR`/`AUTARK`-Treffer, prüfen (Autark-Pfad bleibt `off`) |
| tests/test_clear_checkpoint_blocks.py | Checkpoint-Blöcke („`/clear` ist jetzt gefahrlos") — bleiben unverändert (manual) |
| `scripts/sync_skills.py --check` (in `test_kette_auto_clear_489::test_skills_in_sync`) | Drift der generierten Skills nach Textänderung |

## Doku-Stellen
- CLAUDE.md:75 und :478 (herdr_bridge: „Auto-/clear (#467)"), :305 (Kontext-Haushalt Regel 1: „on nur bei CUT=on und Modus manual oder Herdr-Auto-/clear")
- README.md:311 (Abschnitt Kontext, „mode manual or Herdr auto-/clear"), README.md:144 (Kette läuft selbst durch)
- setup.py:1390 (Konsumenten-Hinweis, „mode manual or Herdr auto-/clear")
- config.yaml:393-411 (Kommentar `herdr.auto_clear`), :336
- CHANGELOG.md, .claude-plugin/plugin.json (Version)
- docs/specs/* (historisch, nicht ändern)

## Risks & Considerations
- **Manual-Modus mit Herdr:** `AUTO_CLEAR=on` ist heute NICHT an den Autonomie-Modus gebunden (40→50 und 50→60 laufen laut #472 immer selbst durch). In `manual` tippt Herdr heute also schon an 10/20/30 (nach Freigabe)/40/50 `/clear` + Folgebefehl, das PO-Wort ersetzt das nicht (Freigaben bleiben manuell). Ohne Auto-/clear geht `manual` an 10/20 zurück auf „warten, PO tippt Folgebefehl" (= Definition von manual) und läuft ab 40 selbst durch, mit `CONTEXT_STOP` als einzigem Schnitt. Kein Produktkonflikt: Epic #649 hat Auto-/clear ausdrücklich als Sorgenkind benannt; im Epic-Text ist „Stop-Hook startet keinen Auto-/clear-Lauf mehr" ohne Moduseinschränkung.
- **Env-Schalter des PO:** `OPENSPEC_HERDR_AUTO_CLEAR=1` kann benutzerweit in `~/.claude/settings.json` stehen (#480); jede Lösung muss ihn überstimmen, nicht nur das Config-Default ändern.
- Zwei Pfade lesen den Schalter: `auto_clear_active()` (cmd_autoclear, context_stop_applies) und direkt `_pane() and auto_clear_enabled()` (`_note_transition_boundary`) bzw. `_auto_clear_config()` (`maybe_auto_clear`). Alle drei müssen gleichzeitig stillgelegt werden, sonst schreibt ein Phasenwechsel Vermerke ohne Abnehmer oder der Stop-Hook spawnt trotzdem.
- Alte, gecachte Befehlstexte (Plugin-Pin bei Konsumenten) rufen weiter `autoclear` auf und müssen `AUTO_CLEAR=off` bekommen → die Zeile bleibt bis Schnitt 4.
- `footer_gate._record_stop`, `signal activity`-Hooks und `record_signal("session")` laufen weiter (schreiben nur Dateien, fail-open, harmlos); Entfernen ist Schnitt 4, nicht hier.
- Kontextwachstum: Ohne Auto-/clear läuft die Auto-Kette mit großem Kontext durch; Ausgleich laut Epic = Helfer-Agenten flach (Developer, Adversary, Explore) und Claude Codes automatische Komprimierung; der Hinweistext `context_cut_note(stop=False)` sagt das schon.
- `/60-validate` und `/70-deploy` brauchen keine Änderung (kein Herdr-Halt).

## Analysis

### Type
Feature (Verhaltensänderung, Teil von Epic #649; erste Stufe des Rückbaus von Auto-/clear).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | MODIFY | `auto_clear_active()` liefert immer False (Docstring: stillgelegt seit #662, Löschung #663); `maybe_auto_clear` kehrt als erste Zeile mit False zurück (kein Spawn, kein Skip-Log). `_auto_clear_config()`/`auto_clear_enabled()` bleiben unberührt (Config-Tests, Schnitt 4 löscht sie). ca. +8 / −0 |
| core/hooks/workflow.py | MODIFY | `_note_transition_boundary`: Bedingung `herdr_bridge._pane() and auto_clear_enabled()` → `herdr_bridge.auto_clear_active()`; `cmd_autoclear` bleibt (druckt dank Helfer immer `AUTO_CLEAR=off`, schreibt nie mehr Vermerk); Docstring `cmd_context` anpassen. ca. +4 / −3 |
| core/hooks/hook_utils.py | MODIFY | `context_stop_applies` = `workflow.autonomy_mode() != "auto"` (Herdr-Import weg, Fehler weiter True); `context_cut_note`-Text für `stop=False`: „Auto-Modus: niemand führt /clear aus, weiterarbeiten…" ohne „Herdr". ca. +4 / −8 |
| core/commands/10-context.md, 20-analyse.md | MODIFY | Abschnitt „Herdr-Auto-/clear (#489)" löschen; Verweis „Herdr-Auto-Clear #467" im Auto-Absatz streichen; Kontext-Absatz „und `/clear` kommt: Modus manual oder Herdr-Auto-/clear" → „Modus manual". je ca. −9 / +1 |
| core/commands/30-write-spec.md | MODIFY | Step 4b: `autoclear`-Prüfung entfernen, nach `AUTO_APPROVE=done` direkt `40-tdd-red` selbst aufrufen; After-Approval-Absatz „Vorher … autoclear" entfernen; Kontext-Absatz wie oben. ca. −10 / +2 |
| core/commands/40-tdd-red.md, 50-implement.md | MODIFY | `autoclear`-Absatz und hängendes „Bei `AUTO_CLEAR=off:`" entfernen; Kontext-Absatz wie oben. je ca. −6 / +1 |
| skills/{10,20,30,40,50}-*/SKILL.md, .claude/agents | REGENERATE | `scripts/sync_skills.py`, `scripts/sync_cloud_agents.py` (generiert, zählt nicht als Handarbeit) |
| tests/test_context_stop_658.py | MODIFY | Fall „auto + Herdr-Auto-Clear" erwartet jetzt `CONTEXT_STOP=off`; `test_autoclear_output_unchanged` → neue Erwartung `AUTO_CLEAR=off` in allen Fällen; Hinweis-Variante „auto mit Herdr-Auto-Clear" entfällt. ca. ±30 |
| tests/test_kette_auto_clear_489.py | MODIFY | `test_autoclear_cli` erwartet immer `off`; `test_chain_commands_check_autoclear` → neuer Test „Befehle 10–50 enthalten weder `workflow.py autoclear` noch `AUTO_CLEAR`"; Skills-Sync bleibt. ca. ±25 |
| tests/test_kontext_haushalt.py | MODIFY | Absatz-Test ggf. Wortlaut |
| tests/test_autoclear_*_49x/59x/506/467/480/478 (Hook-Pfad-Tests, siehe Tabelle) | MODIFY/DELETE | Spawn-/Vermerk-Tests löschen oder durch EINEN neuen Test „Phasenwechsel schreibt keinen Vermerk, Stop-Hook spawnt nie, auch mit Env-Schalter" ersetzen; Runner-/Signal-Interna-Tests nicht anfassen (Schnitt 4) |
| tests/test_auto_chain_flat_662.py | CREATE | Neuer Pinn-Test: (a) `autoclear` → `off` in allen Kombinationen Pane/Env/Config/Modus; (b) `footer_gate` startet nie einen Runner (Stub zeichnet keinen Aufruf), auch bei Env `OPENSPEC_HERDR_AUTO_CLEAR=1`; (c) `context` → `CONTEXT_STOP=on` nur bei manual; (d) Befehle 10–50 ohne `AUTO_CLEAR`; (e) Phasenwechsel schreibt keinen `auto_clear_boundary` |
| CLAUDE.md, README.md, setup.py, config.yaml (Kommentar), CHANGELOG.md, .claude-plugin/plugin.json | MODIFY | Doku „on nur bei manual"; config-Kommentar „Auto-/clear stillgelegt (#662), entfällt mit #663"; Version 4.22.2 / 4.23.0 |

### Scope Assessment
- Dateien (Handarbeit): 3 Hooks + 5 Befehle + ~6 Test-Dateien + 5 Doku-Dateien = ca. 19; mit Generat ca. 29. Überschreitet das Projektlimit (4–5 Dateien, ±250 LoC je Schnitt).
- LoC: Code ca. 30 netto (klein), Befehlstexte ca. −60/+10, Tests ca. −400/+150 (viel Löschung der Spawn-Tests; Löschen zählt als Rückbau, Risiko gering), Doku ca. 20.
- Risiko: mittel. Code-Risiko klein (drei Bedingungen, fail-open), Hauptrisiko ist die Testpflege (viele Hook-Pfad-Tests, eine Datei mit 1388 Zeilen, in der nur vier Tests betroffen sind) und der Manual-Modus (PO-sichtbar: Herdr tippt nicht mehr automatisch).
- **Empfohlene Teilung (ein Ziel, zwei Schnitte, beide unter #662):**
  - **3a Verhalten:** `herdr_bridge.py` (auto_clear_active → False, maybe_auto_clear früh raus), `workflow.py` (Vermerk über Helfer), `hook_utils.py` (context_stop_applies nur manual + Hinweistext), Tests: `test_auto_chain_flat_662.py` neu, `test_context_stop_658.py`, `test_kette_auto_clear_489.py::test_autoclear_cli`, plus Hook-Pfad-Tests 495/497/467/598 (löschen/umstellen). Ca. 4 Code-Dateien + Tests (Tests werden ersetzt, nicht addiert). Alte Befehlstexte bleiben gültig (`AUTO_CLEAR=off` → Selbstaufruf).
  - **3b Texte und Doku:** Befehle 10–50 (+ Skills, Cloud-Agents generiert), `test_kette_auto_clear_489`/`test_kontext_haushalt`-Textasserts, CLAUDE.md/README/setup.py/config-Kommentar, CHANGELOG, Version. Reines Text-Paket, kein Verhalten.
  Reihenfolge a → b ist sicher: nach 3a läuft die Kette im Auto-Modus bereits flach, 3b räumt Wortlaut auf. Einzel-Auslieferung gemäß Arbeitsweise: je Schnitt PR mit Versions-Bump im selben PR; alternativ beide bündeln und `Closes #662` erst im Text-Schnitt.

### Technical Approach
Empfohlen (**B: Auto-/clear zentral stilllegen, Code stehen lassen**): `herdr_bridge.auto_clear_active()` wird die einzige Wahrheit und liefert fest `False`. Damit sind `cmd_autoclear` (immer `AUTO_CLEAR=off`, kein Vermerk), `context_stop_applies` und `_note_transition_boundary` stillgelegt, ohne dass Konfig oder Env-Schalter des PO (`OPENSPEC_HERDR_AUTO_CLEAR`, #480) noch etwas bewirken. `maybe_auto_clear` (Stop-Hook-Einstieg) kehrt zusätzlich sofort zurück, weil der Stop-Pfad `_auto_clear_config()` direkt liest und sonst trotz `auto_clear_active()==False` spawnen würde; die Runner-Klasse, Signale, Grenz-Vermerk-Helfer und `config.yaml`-Abschnitt bleiben bis Schnitt 4 (#663) toter, getesteter Code und werden dort samt Tests gelöscht. `context_stop_applies` wird zu `autonomy_mode() != "auto"`, also `CONTEXT_STOP=on` nur im Modus manual. Auch im Modus manual greift Auto-/clear nie mehr: es gibt keinen Fall, in dem es heute sinnvoll nötig wäre, weil `manual` ohnehin an jedem PO-Punkt auf Eingabe wartet und `CONTEXT_STOP` den Kontext-Schnitt per Checkpoint abdeckt; „Herdr tippt `/clear`" war die Brücke zwischen den Modi und ist der Fehlerherd. Die Zeile `AUTO_CLEAR=` bleibt als Rückwärtskompatibilität für gecachte Befehlstexte erhalten und kommt in Schnitt 4 raus. Befehlstexte 10–50 verlieren den Herdr-Absatz und die `autoclear`-Prüfung (30: Step 4b und After Approval); der Auto-Absatz heißt dann einfach: bei `AUTONOMY=auto` Folgeskill sofort selbst aufrufen, außer an den PO-Punkten, und `CONTEXT_STOP=on` (nur manual) beendet den Turn. Checkpoint-Blöcke bleiben unverändert (Test `test_clear_checkpoint_blocks`).

Alternativen:
- **A) Nur Befehlstexte ändern** (kein `autoclear`-Aufruf mehr): einfachste Änderung, aber der Stop-Hook spawnt weiter, sobald ein Vermerk entsteht (Phasenwechsel schreibt ihn, #598-Schnitt zählt ohne Vermerk) → Herdr tippt `/clear` mitten in die flache Kette. Verworfen, verletzt „Stop-Hook startet keinen Auto-/clear-Lauf mehr".
- **C) Auto-/clear nur im Modus auto abschalten, in manual weiter erlauben** (`auto_clear_active` = Pane und enabled und Modus manual): kleinster Eingriff (eine Zeile), hält aber den fehleranfälligen Runner (#505, #598, #601) produktiv und zwei Verhaltensweisen im Betrieb; Schnitt 4 könnte ihn dann nicht löschen. Verworfen, weil der Epic den Rückbau will; nur als Rückfall sinnvoll, falls der PO den Herdr-Komfort in manual ausdrücklich behalten will (PO-Entscheidung, bisher keine Anhaltspunkte).
- **D) Schalter per Config `herdr.auto_clear.enabled: false` als Default:** reicht nicht (Env des PO überstimmt, Opt-in-Logik #480); verworfen.
- Gegenüber dem direkten Löschen (Schnitt 4 vorgezogen) spart B den großen Rückbau, den #662 ausdrücklich ausschließt; Preis: wenige Tage toter Code.

ADR: keine neue nötig, aber ADR-/Spec-Hinweis: dieser Schnitt löst die Entscheidung aus feat-467/fix-489 („Herdr tippt /clear und Folgebefehl") ab; die Spec soll sie als „abgelöst durch Epic #649 / #662" vermerken (Spec-Abschnitt Architektur-Entscheidung: Alternativen A–D oben).

### Dependencies
- #658 (gemergt) liefert `CONTEXT_STOP`, `context_stop_applies`, `auto_clear_active`.
- #663 (Schnitt 4) folgt: Löschung von Runner, `record_signal`/`run_signal`, Hook-Einträge `signal activity`, `AUTO_CLEAR_BOUNDARIES`, `_record_auto_clear_boundary`, `_record_context_cut_boundary`, `autoclear`-Subcommand, `config.yaml` herdr.auto_clear, `scripts/e2e_auto_clear.sh`, der zugehörigen Tests.
- Plugin-Cache bei Konsumenten: alte Befehlstexte bleiben durch die `AUTO_CLEAR=off`-Zeile funktionsfähig.
- Generierte Dateien nach Befehlsänderung: `python3 scripts/sync_skills.py` und `python3 scripts/sync_cloud_agents.py`.

### Open Questions
- Keine echte Produktfrage. Eine implizite Annahme zur Bestätigung in der Spec: Auto-/clear entfällt auch im Modus manual (Herdr tippt dort nicht mehr; der PO tippt `/clear` + Folgebefehl wie ohne Herdr). Der Epic-Text deckt das („Stop-Hook startet keinen Auto-/clear-Lauf mehr", ohne Moduseinschränkung); nur wenn der PO den Herdr-Komfort in manual behalten will, wäre Alternative C die Rückfalloption.
- Technisch offen für die Spec: Hook-Pfad-Tests der Familien 467/495/497/597/598/506 in 3a löschen (Rückbau vorgezogen, spart Pflege) oder auf „nie spawnen" umstellen. Empfehlung: durch einen gemeinsamen Pinn-Test ersetzen, Runner-Interna-Tests stehen lassen bis #663.
