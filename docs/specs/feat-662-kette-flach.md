---
entity_id: feat-662-kette-flach
type: feature
created: 2026-11-25
updated: 2026-11-25
status: draft
version: "1.0"
workflow: feat-662-kette-flach
tags: [kontext, hooks, workflow, herdr, auto-modus, epic-649]
---

# Phasenkette im Auto-Modus flach fortsetzen, kein Turn-Ende für Herdr (Issue #662, Epic #649 Schnitt 3)

## Approval

- [ ] Approved

## Purpose

Im Auto-Modus (`OPENSPEC_AUTONOMY=auto`) beendeten die Phasenbefehle 10 bis 50 bei `AUTO_CLEAR=on` den Turn an jeder Phasengrenze, damit Herdr `/clear` und den Folgebefehl tippt. Dieser Weg aus #467 ist fehleranfällig (#505, #598, #601). Neu: Das Auto-`/clear` ist global stillgelegt, die Hauptsitzung setzt die Kette im Auto-Modus überall selbst fort (Helfer-Agenten flach), und `CONTEXT_STOP=on` gibt es nur noch im Modus `manual`. Herdr tippt nichts mehr, zeigt nur noch an (PO-Entscheidung Epic #649, 2026-11-24; flach statt verschachtelt, 2026-11-25). Diese Spec löst die Entscheidung aus feat-467 und fix-489 („Herdr tippt /clear und Folgebefehl") ab: abgelöst durch Epic #649 / #662.

## Source

- **File:** `core/hooks/herdr_bridge.py`, `core/hooks/workflow.py`, `core/hooks/hook_utils.py`, `core/commands/10-context.md` bis `50-implement.md`
- **Identifier:** `herdr_bridge.auto_clear_active`, `herdr_bridge.maybe_auto_clear`, `workflow._note_transition_boundary`, `workflow.cmd_autoclear`, `workflow.cmd_context`, `hook_utils.context_stop_applies`, `hook_utils.context_cut_note`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils.context_stop_applies` (#658) | function | zentrale Entscheidung „Kette anhalten"; wird zu `autonomy_mode() != "auto"` |
| `workflow.autonomy_mode` | function | Quelle für `auto`/`manual`; Fehler ergibt weiter „Stopp gilt" |
| `herdr_bridge.auto_clear_active` (#658) | function | einzige Wahrheit für Auto-/clear; liefert fest `False` |
| `herdr_bridge._auto_clear_config`, `auto_clear_enabled` | function | bleiben unangetastet (Config-Tests), Löschung in #663 |
| `footer_gate.py` | hook | einziger Aufrufer von `maybe_auto_clear`; bleibt unverändert |
| `workflow.auftrag_autark_open` (#551) | function | Autark setzt CUT schon auf off; bleibt vorrangig |
| `scripts/sync_skills.py`, `scripts/sync_cloud_agents.py` | tool | Generat nach Befehlstext-Änderung neu erzeugen |
| `docs/specs/fix-658-context-stop-auto.md` | spec | Vorarbeit (`CONTEXT_STOP`) |
| `docs/specs/feat-467-herdr-auto-clear.md`, `fix-489-kette-auto-clear.md`, `fix-598-autoclear-kontextschnitt.md` | spec | abgelöste Entscheidungen |
| Issue #663 | issue | Schnitt 4: Code-Rückbau von Runner, Signalen, Grenz-Vermerk, Config |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | MODIFY | `auto_clear_active()` liefert immer `False`; `maybe_auto_clear` kehrt als erste Anweisung ohne Spawn und ohne Skip-Log zurück |
| core/hooks/workflow.py | MODIFY | `_note_transition_boundary` nutzt `herdr_bridge.auto_clear_active()` statt `_pane() and auto_clear_enabled()`; `cmd_autoclear` druckt immer `AUTO_CLEAR=off`, schreibt keinen Vermerk; Docstring `cmd_context` |
| core/hooks/hook_utils.py | MODIFY | `context_stop_applies` = `autonomy_mode() != "auto"` (Fehler wie bisher True); Wortlaut `context_cut_note` ohne „Herdr" |
| core/commands/10-context.md, 20-analyse.md, 30-write-spec.md, 40-tdd-red.md, 50-implement.md | MODIFY | Absatz „Herdr-Auto-/clear: Turn an der Grenze beenden (#489)" und `autoclear`-Prüfung entfallen (bei 30 beide Stellen inkl. Step 4b); Kontext-Absatz sagt „Modus manual"; Checkpoint-Blöcke bleiben |
| skills/*/SKILL.md, .claude/agents | REGENERATE | `python3 scripts/sync_skills.py`, `python3 scripts/sync_cloud_agents.py` |
| tests/test_auto_chain_flat_662.py | CREATE | Pinn-Test zu allen ACs |
| tests/test_context_stop_658.py, test_kette_auto_clear_489.py, test_kontext_haushalt.py | MODIFY | Erwartungen auf „Auto + Herdr: off", `AUTO_CLEAR=off`, neuen Absatz-Wortlaut umstellen |
| tests/test_herdr_auto_clear_467.py, test_autoclear_boundary_495.py, test_autoclear_transition_497.py, test_autoclear_kontextschnitt_598.py, test_autoclear_retry_597.py, test_autoclear_eigene_signale_506.py, test_auto_clear_global_480.py, test_herdr_plan_deploy_sessionstart_478.py | MODIFY | nur die Hook-Einstiegs-Tests (Spawn, Vermerk): auf „nie spawnen" / „kein Vermerk" umstellen oder, wo sie nur den toten Weg beschreiben, entfernen; Runner-Interna-Tests bleiben bis #663 |
| CLAUDE.md, README.md, setup.py | MODIFY | Hook-Architektur/Stop-Hook, `herdr_bridge`-Zeile, Kontext-Haushalt Regel 1, Konsumenten-Hinweistext, knapp |
| CHANGELOG.md, .claude-plugin/plugin.json | MODIFY | Eintrag und Version 4.23.0 (auch in CLAUDE.md, README und Versionsmarkern) |

Nicht geändert: `config.yaml` (autarker Auftrag, wirksame Gate-Config), Seitenleiste und Plan-Pane (`herdr report`), `footer_gate.py`, `hooks/hooks.json`, Runner, Signale und Grenz-Vermerk-Code.

### Estimated Changes

- Files: 3 Hooks, 5 Befehle, 1 neuer und ca. 11 geänderte Testdateien, 5 Doku-/Versionsdateien, Generat
- LoC: Code ca. +15/-10, Befehlstexte ca. -60/+10, Tests ca. +150/-300, Doku ca. +20/-10
- Umfang: überschreitet das Schnittlimit (4 bis 5 Dateien, 250 LoC). Der Tech Lead nimmt das bewusst an: ein Ziel in einem Schnitt, weil ein Teilschnitt (nur Verhalten oder nur Texte) die Kette zwischenzeitlich widersprüchlich lässt; der große Teil ist Löschung toter Spawn-Tests und Textstreichung, kein neuer Code.
- Risk Level: MEDIUM (Hook-Code in allen Konsumenten; Verhaltensänderung im Modus manual mit Herdr, Testpflege)

## Implementation Details

1. **`auto_clear_active()`** liefert fest `False` (Docstring: stillgelegt seit #662, Löschung mit #663). Damit sind `cmd_autoclear`, `context_stop_applies` und die Vermerk-Bedingung stillgelegt, auch wenn der PO `OPENSPEC_HERDR_AUTO_CLEAR=1` global gesetzt hat (Env-Schalter #480 bewirkt nichts mehr).
2. **`maybe_auto_clear`** (Stop-Hook-Einstieg) gibt als erste Anweisung `False` zurück. Nötig, weil der Stop-Pfad `_auto_clear_config()` direkt liest und sonst trotz `auto_clear_active() == False` spawnen würde.
3. **`_note_transition_boundary`** (Phasenwechsel 1 nach 2, 2 nach 3, 3 nach 4, 5 nach 6, 6b nach 7) prüft `herdr_bridge.auto_clear_active()` und schreibt deshalb nie mehr `auto_clear_boundary`.
4. **`cmd_autoclear`** bleibt als Kompatibilitätszeile für alte, aus dem Plugin-Cache gelieferte Befehlstexte: genau `AUTO_CLEAR=off`, Exit 0, kein Vermerk. Alte Texte setzen die Kette dadurch selbst fort. Die Zeile fällt mit #663.
5. **`context_stop_applies`** ist `workflow.autonomy_mode() != "auto"`, der Herdr-Import entfällt, Fehler liefern True. Im Auto-Modus bei `CONTEXT_CUT=on` gilt `CONTEXT_STOP=off` mit `CONTEXT_REASON=AUTO_NO_CLEAR` (Wortlaut der Zeile unverändert). `context_cut_note(stop=False)` sagt: Auto-Modus, niemand führt `/clear` aus, weiterarbeiten, Nachschlagen an Teilagenten abgeben, Claude Code komprimiert automatisch.
6. **Befehlstexte 10 bis 50:** Herdr-Absatz und `autoclear`-Prüfung entfallen, ebenso der hängende Satz „Bei `AUTO_CLEAR=off:`". Im Auto-Modus ruft die Hauptsitzung den Folge-Skill selbst auf; nur `CONTEXT_STOP=on` (Modus manual) beendet den Turn mit Checkpoint und ❗Du-Zeile. Halt sonst nur an PO-Punkten (`approved` ohne Auto-Freigabe, AMBIGUOUS, Override, Produktfragen). Kette 40 nach 50 nach 60 bleibt unabhängig vom Modus (#472).
7. **Doku und Version:** CLAUDE.md, README.md, `setup.py`-Hinweistext, CHANGELOG, Version 4.23.0; danach Skills und Cloud-Agents neu erzeugen.

## Expected Behavior

- **Input:** `OPENSPEC_AUTONOMY`, Herdr-Umgebung (`HERDR_ENV`, `HERDR_PANE_ID`), Config `herdr.auto_clear`, Env `OPENSPEC_HERDR_AUTO_CLEAR`, Messdatei, Phasenwechsel, Stop-Hook-Aufruf
- **Output:** `workflow.py autoclear` ergibt immer `AUTO_CLEAR=off`; `workflow.py context` endet mit `CONTEXT_STOP=on` nur bei CUT=on und Modus `manual`; im Auto-Modus bei CUT=on mit `CONTEXT_REASON=AUTO_NO_CLEAR` und `CONTEXT_STOP=off`
- **Side effects:** kein Phasenwechsel schreibt `auto_clear_boundary`; der Stop-Hook startet nie einen Runner; Herdr tippt nichts mehr; Seitenleiste und Plan-Pane laufen unverändert

## Known Limitations

- Toter Code bis #663: Runner, Signale (`record_signal`, `run_signal`, `signal activity`-Hooks), Grenz-Vermerk-Code, `_record_context_cut_boundary`, `_auto_clear_config`/`auto_clear_enabled`, `autoclear`-Subcommand, Config-Schlüssel `herdr.auto_clear`, E2E-Skript `scripts/e2e_auto_clear.sh` und deren Runner-Interna-Tests bleiben stehen und werden dort gelöscht.
- Der Kommentar zu `herdr.auto_clear` in `config.yaml` bleibt veraltet (er beschreibt noch ein wirksames Auto-/clear), weil `config.yaml` hier nicht angefasst wird (autarker Auftrag, Gate-Config); #663 entfernt den Abschnitt.
- Der Hauptkontext wächst im Auto-Modus ohne `/clear`; Ausgleich sind flache Helfer-Agenten und die automatische Komprimierung von Claude Code. Die Messung für die Epic-DoD (Kontextwachstum über eine ganze Kette) steht noch aus.
- Im Modus `manual` tippt Herdr nicht mehr `/clear` und Folgebefehl; der PO tippt beides wie ohne Herdr. Das deckt der Epic-Text ohne Moduseinschränkung.
- Ein Hinweis zur Fortsetzung bleibt Auskunft: ob Claude anhält, erzwingt kein Hook.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Im Auto-Modus hält weder `workflow.py context` noch `workflow.py autoclear` noch ein Befehlstext die Kette für Herdr an, auch in einem Herdr-Pane mit gesetztem Env-Schalter
- [ ] Im Modus `manual` hält die Kette an der Kontext-Schwelle weiterhin mit Checkpoint an
- [ ] Der Stop-Hook startet keinen Auto-/clear-Lauf mehr und kein Phasenwechsel hinterlässt einen Grenz-Vermerk
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, `skills/` ohne Drift, kein `pytest.skip` zur Entschärfung, Version 4.23.0 veröffentlicht)

## Acceptance Criteria

- **AC-1:** Given ein aktives Herdr-Pane, Config `herdr.auto_clear.enabled: true` und Env `OPENSPEC_HERDR_AUTO_CLEAR=1` / When `herdr_bridge.auto_clear_active()` aufgerufen wird / Then liefert es `False`
  - Test: tests/test_auto_chain_flat_662.py::test_auto_clear_active_always_false

- **AC-2:** Given Herdr-Pane, Config und Env schalten Auto-/clear ein, beliebiger Autonomie-Modus / When `workflow.py autoclear` läuft / Then lautet die Ausgabe genau `AUTO_CLEAR=off`, Exit 0, und es entsteht kein Grenz-Vermerk
  - Test: tests/test_auto_chain_flat_662.py::test_autoclear_cli_always_off

- **AC-3:** Given Herdr-Pane und eingeschalteter Auto-/clear-Schalter, ein Stop-Hook-Aufruf mit Grenz-Vermerk oder Kontext-Schnitt / When `maybe_auto_clear` (über `footer_gate`) läuft / Then wird kein Runner gestartet und kein Prozess gespawnt
  - Test: tests/test_auto_chain_flat_662.py::test_stop_hook_never_spawns_runner

- **AC-4:** Given Herdr-Pane mit eingeschaltetem Auto-/clear-Schalter / When ein Phasenwechsel (1 nach 2, 2 nach 3, 3 nach 4, 5 nach 6, 6b nach 7) ausgeführt wird / Then steht im Workflow-State kein `auto_clear_boundary`
  - Test: tests/test_auto_chain_flat_662.py::test_phase_change_writes_no_boundary

- **AC-5:** Given Auto-Modus mit Herdr-Pane und Auto-/clear-Schalter, Kontext über der Schwelle / When `workflow.py context` läuft / Then lauten die Zeilen `CONTEXT_CUT=on`, `CONTEXT_REASON=AUTO_NO_CLEAR` und zuletzt `CONTEXT_STOP=off`
  - Test: tests/test_auto_chain_flat_662.py::test_context_auto_with_herdr_stop_off

- **AC-6:** Given Modus `manual` (mit und ohne Herdr), Kontext über der Schwelle / When `workflow.py context` läuft / Then lautet die letzte Zeile `CONTEXT_STOP=on` und `CONTEXT_REASON=AUTO_NO_CLEAR` fehlt
  - Test: tests/test_auto_chain_flat_662.py::test_context_manual_stop_on

- **AC-7:** Given der Entscheidungs-Helfer wirft einen Fehler und CUT ist on / When `workflow.py context` läuft / Then folgt `CONTEXT_STOP` dem Wert von `CONTEXT_CUT` (`on`), Exit 0
  - Test: tests/test_context_stop_658.py::test_helper_error_stop_follows_cut

- **AC-8:** Given die Befehlstexte 10-context bis 50-implement samt erzeugten Skills / When ihr Text gelesen wird / Then enthalten sie weder den Absatz „Herdr-Auto-/clear" noch einen Aufruf `workflow.py autoclear` oder die Zeile `AUTO_CLEAR`, verweisen aber weiter auf `CONTEXT_STOP=on` für den Halt, und `sync_skills.py --check` meldet keine Drift
  - Test: tests/test_auto_chain_flat_662.py::test_phase_commands_without_herdr_paragraph

- **AC-9:** Given der Hinweis von `post_bash.py` über der Schwelle im Auto-Modus / When er erzeugt wird / Then sagt er „weiterarbeiten" mit Teilagenten und automatischer Komprimierung, ohne „Herdr" und ohne Halt-Aufforderung
  - Test: tests/test_context_stop_658.py::test_post_bash_note_wording_per_variant

- **AC-10:** Given die Checkpoint-Blöcke der Phasenbefehle für den Modus manual / When ihr Text gelesen wird / Then bleibt der Positiv-Block „`/clear` ist jetzt gefahrlos" mit ❗Du-Zeile unverändert erhalten
  - Test: tests/test_clear_checkpoint_blocks.py (Bestandstest, bleibt unverändert grün)

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden, ohne Netzwerk, Messdatei, Config und Workflow-State per `tmp_path`; Test-Env setzt `OPENSPEC_AUTONOMY`, `HERDR_ENV`, `HERDR_PANE_ID` und `OPENSPEC_HERDR_AUTO_CLEAR` explizit, weil die Cloud-Umgebung `OPENSPEC_AUTONOMY=auto` vorgibt):

- `pytest tests/test_auto_chain_flat_662.py` (RED zuerst, dann GREEN)
- Umgestellte Bestandstests: `pytest tests/test_context_stop_658.py tests/test_kette_auto_clear_489.py tests/test_kontext_haushalt.py tests/test_clear_checkpoint_blocks.py tests/test_auftrag_551.py`
- Umgestellte Hook-Einstiegs-Tests: `pytest tests/test_herdr_auto_clear_467.py tests/test_autoclear_boundary_495.py tests/test_autoclear_transition_497.py tests/test_autoclear_kontextschnitt_598.py tests/test_autoclear_retry_597.py tests/test_autoclear_eigene_signale_506.py tests/test_auto_clear_global_480.py tests/test_herdr_plan_deploy_sessionstart_478.py tests/test_befehlsform_context_titel_499.py tests/test_vorlagen_klartext_597.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/herdr_bridge.py core/hooks/workflow.py core/hooks/hook_utils.py`
- `python3 scripts/sync_skills.py --check` und `python3 scripts/sync_cloud_agents.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Auto-/clear wird zentral stillgelegt, der Code bleibt bis #663 stehen. `auto_clear_active()` ist die einzige Wahrheit für `cmd_autoclear`, `context_stop_applies` und die Vermerk-Bedingung; `maybe_auto_clear` bekommt zusätzlich einen Frühausstieg, weil der Stop-Pfad die Config direkt liest. Alle drei Pfade werden gleichzeitig stillgelegt, sonst entstünden Vermerke ohne Abnehmer oder ein Spawn trotz Abschaltung. Die Zeile `AUTO_CLEAR=off` bleibt als Rückwärtskompatibilität für gecachte Befehlstexte. Reversibel durch Wiederherstellung der Helfer-Rückgabe und der Texte. Die Entscheidung aus feat-467/fix-489 gilt als abgelöst durch Epic #649 / #662.
- **Alternative A, nur Befehlstexte ändern:** verworfen. Der Stop-Hook spawnt weiter, sobald ein Phasenwechsel einen Vermerk schreibt oder der Kontext-Schnitt (#598) ohne Vermerk als Grenze zählt; Herdr tippte dann `/clear` mitten in die flache Kette und verletzt „Stop-Hook startet keinen Auto-/clear-Lauf mehr".
- **Alternative C, Auto-/clear nur im Modus auto ausschalten, in manual erlauben:** verworfen. Kleinster Eingriff (eine Zeile), hält aber den fehleranfälligen Runner (#505, #598, #601) produktiv, ergibt zwei Betriebsweisen und verhindert in #663 das Löschen des Runners. Rückfall nur, falls der PO den Herdr-Komfort in manual ausdrücklich behalten will; dafür gibt es keinen Anhaltspunkt.
- **Alternative D, Config-Default `herdr.auto_clear.enabled: false`:** verworfen. Der Env-Schalter des PO (`OPENSPEC_HERDR_AUTO_CLEAR`, #480, Vorrang vor dem Default) überstimmt das, und `config.yaml` bleibt hier unangetastet.
- **Direktes Löschen (Schnitt 4 vorgezogen):** verworfen, #662 schließt den Rückbau ausdrücklich aus; Preis von B ist toter, getesteter Code bis #663.

## Changelog

- 2026-11-25: Initial spec created
