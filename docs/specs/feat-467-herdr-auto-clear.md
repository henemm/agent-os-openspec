---
entity_id: feat-467-herdr-auto-clear
type: feature
created: 2026-10-28
updated: 2026-10-28
status: draft
version: "1.0"
workflow: feat-467-herdr-auto-clear
tags: [herdr, auto-clear, workflow, footer-gate]
---

# Herdr Auto-/clear an Phasengrenzen (Issue #467)

## Approval

- [ ] Approved

## Purpose

Laeuft Claude Code in einem Herdr-Pane und hat die letzte Antwort den Checkpoint "`/clear` ist jetzt gefahrlos" gemeldet, tippt ein detachter Runner automatisch `/clear` und danach den naechsten Workflow-Befehl (`/<cmd> #N`) in den Pane. Der Kontext bleibt damit klein; der State liegt vollstaendig auf Platte/GitHub, die `#N`-Wiedereinstiege der Commands stellen ihn wieder her. Das Feature ist Opt-in (`herdr.auto_clear.enabled: false` als Default) und loest nie eine Freigabe aus (#468).

## Source

- **File:** `core/hooks/herdr_bridge.py` (Marker-Detektor, Once-Lock, Spawn, Runner, CLI), `core/hooks/footer_gate.py` (Aufrufstelle)
- **Identifier:** `auto_clear_enabled`, `has_clear_marker`, `maybe_auto_clear`, `spawn_auto_clear`, `run_auto_clear`, CLI `herdr_bridge.py auto-clear`; in `footer_gate.main()` der Pfad "Fusszeile korrekt"

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/herdr_bridge.py` (#466) | module | `_pane()`, `_binary()`, `_enabled()` (Eltern-Kill-Switch `herdr.enabled`), `run_herdr`, `_launch` (Popen detached) |
| `core/hooks/footer_gate.py` | module | Stop-Hook bei jedem Turn-Ende; `_footer_commands`, `_expected_command`, `DU_LINE_RE`; Pfad "Fusszeile korrekt" endet heute in `sys.exit(0)` |
| `core/hooks/workflow.py` | module | `expected_footer_command(data)` (vollstaendiger Befehl inkl. `#N`), `issue_number()`; `data["current_phase"]` |
| `core/hooks/config_loader.py` | module | `load_config()`; `herdr` steht seit #466 in `PLUGIN_CONFIG_KEYS` |
| `core/commands/10-context.md` ... `50-implement.md` | commands | Checkpoint-Positivblock "`/clear` ist jetzt gefahrlos" bzw. Negativblock "`/clear` jetzt NICHT" |
| `hooks/hooks.json` | config | footer_gate ist bereits Stop-Hook, keine Aenderung |
| Herdr-CLI (`$HERDR_BIN_PATH`) | extern | `agent wait <target> [--until STATUS]... [--timeout MS]`, `agent prompt <target> <text>`, `notification show <title> --body ...` |
| `tests/conftest.py` | test infra | autouse-Fixture isoliert `HERDR_*` (aus #466) |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | MODIFY | Strikter Opt-in-Reader, Marker-Detektor (pure function), Once-Lock, `maybe_auto_clear`, `spawn_auto_clear`, Runner `run_auto_clear` + CLI `auto-clear` |
| core/hooks/footer_gate.py | MODIFY | Auf dem Pfad "Fusszeile korrekt" fail-open an `herdr_bridge.maybe_auto_clear` delegieren (~12 LoC) |
| config.yaml | MODIFY | `herdr.auto_clear` (enabled false, grace_s 3, idle_timeout_s 120, announce true) |
| tests/test_herdr_auto_clear_467.py | CREATE | Verzweigendes Stub-Binary, Runner synchron ueber CLI (Delays 0), Hook-Seite per Subprozess |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

Keine Aenderung an `hooks/hooks.json`, `session_singleton_guard.py`, `session_banner.py` (ruft `report_active` bereits bei jeder SessionStart-Quelle).

### Estimated Changes

- Files: 1 neu, 4 geaendert
- LoC: +140 Produktion / +300 Test
- Risk Level: HIGH (tippt ins Terminal, loescht Kontext) — durch Opt-in begrenzt

## Implementation Details

**Trigger-Bedingungen** (`maybe_auto_clear(payload, message, data)`, in dieser Reihenfolge; jede nicht erfuellte Bedingung oder Ausnahme = kein Spawn, fail-open):

1. `herdr_bridge._pane()` liefert eine Pane-ID (`HERDR_ENV=1`, `HERDR_PANE_ID`, gueltiges `HERDR_BIN_PATH`, `herdr.enabled` nicht `false`).
2. `herdr.auto_clear.enabled is True` (nur das Literal `True`; fehlt der Abschnitt oder ist der Wert etwas anderes, gilt aus).
3. `payload["stop_hook_active"]` ist nicht `True`.
4. Fusszeile korrekt: der volle erwartete Befehl aus `workflow.expected_footer_command(data)` beginnt mit `/`, ist nicht `/clear`, und sein erstes Wort steht unter den Slash-Befehlen der letzten ❗Du-Zeile (`_footer_commands`). footer_gate vergleicht nur das erste Wort; an den Runner geht der vollstaendige Befehl inklusive `#N`. Ein Freitext-Schritt (Freigabe-Phrase) ist kein Slash-Befehl und loest nie aus.
5. Marker (`has_clear_marker(message)`): der Positivmarker `` `/clear` ist jetzt gefahrlos `` (Bold-tolerant, also auch `**`...`**`) kommt ausserhalb von Code-Fences (``` ```) und vor der letzten ❗Du-Zeile vor; der Negativmarker `` `/clear` jetzt NICHT `` steht nirgends in der Nachricht (auch nicht in einem Fence).
6. Once-Lock: Schluessel `workflow|phase|befehl`, worktree-lokal in `.claude/herdr_auto_clear_state.json`, Ablauf nach 10 Minuten. Der Lock wird vor dem Spawn gesetzt und bei Spawn-Fehler wieder geloescht. Ein identischer Schluessel innerhalb der 10 Minuten loest nicht erneut aus (footer_gate laeuft bei Exit-2-Korrektur mehrfach pro Turn).

**Hook-Seite.** `footer_gate.main()` behaelt Exit-Code und stdout bei: auf dem Pfad "Fusszeile korrekt" (`not expected or expected in actuals`) wird vor `sys.exit(0)` in `try/except Exception` `herdr_bridge.maybe_auto_clear(...)` aufgerufen. Bei falscher Fusszeile (Exit 2 / Block) wird nie gespawnt. `spawn_auto_clear` startet `[sys.executable, herdr_bridge.py, "auto-clear", ...]` per `subprocess.Popen` (kein Shell, `start_new_session=True`, Streams DEVNULL, `close_fds=True`) und kehrt sofort zurueck. Der Stop-Hook wartet nie.

**Runner** (`run_auto_clear`, eigener Prozess, Gesamt-Deadline, immer Exit 0, Log-Eintraege in `.claude/herdr_auto_clear.log`). Aufruf: `python3 herdr_bridge.py auto-clear --pane P --workflow W --phase PH --command "<befehl #N>"` plus ueberschreibbare Delays `--grace`, `--settle`, `--idle-timeout`, `--announce` (Tests: 0). Ablauf:

1. Optional (`announce`) `notification show` als Vorankuendigung, danach `grace_s` warten.
2. `agent wait P --until idle --until done --timeout <idle_timeout_s*1000>`; nur Exit 0 und Status `idle` oder `done` im JSON (`.result.agent`) fuehren weiter; `blocked`, `unknown`, `working`, Timeout (Exit 1) oder nicht parsbare Ausgabe brechen ab.
3. Settle-Delay, dann State-Recheck: der Workflow steht noch in derselben Phase und `expected_footer_command` liefert noch denselben Befehl; sonst Abbruch.
4. `agent prompt P /clear` ohne `--wait` (sonst `agent_prompt_stalled`, weil `/clear` kein sichtbares Arbeiten ausloest); kein Retry. Exit != 0 bricht ab.
5. Delay, zweites `agent wait P --until idle --until done --timeout ...` mit denselben Abbruchregeln, State-Recheck wie in Schritt 3.
6. `agent prompt P "<befehl #N>"` ohne `--wait`. Exit != 0 bricht ab.

Jeder Abbruch schreibt eine Zeile mit Zeitstempel und Grund ins Log und beendet den Runner mit Exit 0. Nach Abbruch wird kein Folgeprompt gesendet.

**Konfiguration.** `config.yaml` -> `herdr.auto_clear: {enabled: false, grace_s: 3, idle_timeout_s: 120, announce: true}`. `herdr.enabled: false` schaltet auch Auto-Clear ab (Eltern-Kill-Switch).

## Expected Behavior

- **Input:** Turn-Ende (Stop-Hook) in einem Herdr-Pane mit aktivem Opt-in, korrekter ❗Du-Zeile mit Slash-Befehl und Positivmarker
- **Output:** Der Pane erhaelt nacheinander `/clear` und `/<cmd> #N`; footer_gate-Exit-Code und stdout bleiben unveraendert
- **Side effects:** Ein detachter Runner-Prozess pro Ausloesung, `.claude/herdr_auto_clear_state.json` (Once-Lock), `.claude/herdr_auto_clear.log` (Abbrueche); bei jeder nicht erfuellten Bedingung keine Wirkung

## Known Limitations

- Gleichzeitiges Tippen des Users im Pane kann sich mit dem gesendeten Text vermischen; Mitigation sind nur Vorankuendigung, Wartezeit und State-Recheck vor jedem Senden.
- Der Positivmarker ist eine Modellkonvention der Commands, nicht mechanisch auf Vollstaendigkeit der Sicherung geprueft.
- Die Idle-Race direkt nach dem Stop (Herdr meldet evtl. noch `working`) wird durch Settle-Delay und `agent wait` abgefangen; das ist nur manuell in einem echten Herdr pruefbar, die Tests nutzen ein Stub-Binary.
- Nur `/clear`, kein `/compact`.
- Freigaben (`approved`, `go`) bleiben manuell; Autonomie ist #468. Die Kette Phase 1 -> 2 -> 3 laeuft beabsichtigt automatisch, bricht aber an der Freigabe ab, weil der erwartete Schritt dort kein Slash-Befehl ist.
- `agent wait`/`agent prompt` mit Timeout beweisen nicht, dass nichts gesendet wurde; deshalb gibt es kein Retry.
- `/clear` erzeugt eine neue Session-ID; Session-Register und Herdr-Resume muessen damit umgehen (bestehendes SessionStart-Verhalten, hier nicht veraendert).

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Mit `herdr.auto_clear.enabled: true` in einem Herdr-Pane folgen nach einem Checkpoint-Turn `/clear` und der naechste Workflow-Befehl ohne Zutun des Users (manuelle Abnahme in echtem Herdr)
- [ ] Ohne Opt-in, ausserhalb von Herdr oder bei Kill-Switch verhaelt sich footer_gate exakt wie vorher (gleicher Exit-Code, gleiche stdout)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen, insbesondere Footer-Gate- und #466-Tests)

## Acceptance Criteria

- **AC-1:** Given Herdr-Env gueltig (Stub-Binary, das haengt), `herdr.auto_clear.enabled: true`, Workflow mit erwartetem Befehl `/50-implement #467`, letzte Antwort mit Positivmarker vor einer korrekten ❗Du-Zeile / When `footer_gate.py` den Stop-Payload verarbeitet / Then wird ein Runner-Prozess gespawnt, footer_gate endet mit Exit 0 und unveraendertem stdout und kehrt sofort zurueck (deutlich unter der Haengezeit des Stubs)
  - Test: tests/test_herdr_auto_clear_467.py::test_hook_spawns_runner_and_returns_immediately

- **AC-2:** Given ein verzweigendes Stub-Binary und der Runner per CLI (`auto-clear`, Delays 0), das beide `agent wait` mit Status `idle` beantwortet / When der Runner laeuft / Then ist die protokollierte argv-Folge exakt `agent wait P`, `agent prompt P /clear`, `agent wait P`, `agent prompt P "/50-implement #467"`; die `wait`-Aufrufe tragen `--until idle --until done --timeout`, die `prompt`-Aufrufe tragen kein `--wait`
  - Test: tests/test_herdr_auto_clear_467.py::test_runner_exact_sequence_and_flags

- **AC-3:** Given Herdr-Env gueltig, aber `herdr.auto_clear` fehlt bzw. `enabled: false` / When footer_gate bei sonst erfuellten Bedingungen laeuft / Then wird kein Runner gestartet und Exit-Code sowie stdout entsprechen dem Verhalten ohne Feature
  - Test: tests/test_herdr_auto_clear_467.py::test_no_spawn_when_auto_clear_not_enabled

- **AC-4:** Given `herdr.enabled: false` (Eltern-Kill-Switch) bei `auto_clear.enabled: true` / When footer_gate laeuft / Then wird kein Runner gestartet
  - Test: tests/test_herdr_auto_clear_467.py::test_no_spawn_when_herdr_disabled

- **AC-5:** Given kein `HERDR_ENV` (bzw. fehlende `HERDR_PANE_ID`) / When footer_gate laeuft / Then wird kein Runner gestartet
  - Test: tests/test_herdr_auto_clear_467.py::test_no_spawn_without_herdr_env

- **AC-6:** Given `stop_hook_active: true` im Payload / When footer_gate laeuft / Then wird kein Runner gestartet
  - Test: tests/test_herdr_auto_clear_467.py::test_no_spawn_when_stop_hook_active

- **AC-7:** Given eine falsche ❗Du-Zeile (nennt einen anderen Befehl als erwartet) / When footer_gate laeuft / Then endet er mit Exit 2 (Block wie bisher) und es wird kein Runner gestartet
  - Test: tests/test_herdr_auto_clear_467.py::test_no_spawn_on_wrong_footer_exit_2

- **AC-8:** Given eine korrekte Fusszeile, aber ohne Positivmarker in der Antwort / When footer_gate laeuft / Then wird kein Runner gestartet
  - Test: tests/test_herdr_auto_clear_467.py::test_no_spawn_without_positive_marker

- **AC-9:** Given Positivmarker und zusaetzlich der Negativmarker "`/clear` jetzt NICHT" in derselben Antwort / When footer_gate laeuft / Then wird kein Runner gestartet
  - Test: tests/test_herdr_auto_clear_467.py::test_no_spawn_with_negative_marker

- **AC-10:** Given der Positivmarker steht nur innerhalb einer Code-Fence / When footer_gate laeuft / Then wird kein Runner gestartet
  - Test: tests/test_herdr_auto_clear_467.py::test_no_spawn_when_marker_only_in_code_fence

- **AC-11:** Given Workflow in `phase3_spec`, dessen erwarteter Schritt Freitext (Freigabe-Phrase) statt Slash-Befehl ist, mit Positivmarker / When footer_gate laeuft / Then wird kein Runner gestartet (Freigaben bleiben manuell)
  - Test: tests/test_herdr_auto_clear_467.py::test_no_spawn_when_expected_step_is_freetext

- **AC-12:** Given ein erster Payload hat den Runner gespawnt / When derselbe Payload (gleicher Workflow, gleiche Phase, gleicher Befehl) erneut verarbeitet wird / Then wird nicht erneut gespawnt; liegt der Lock-Zeitstempel mehr als 10 Minuten zurueck, wird wieder gespawnt
  - Test: tests/test_herdr_auto_clear_467.py::test_once_lock_blocks_duplicate_and_expires_after_10_min

- **AC-13:** Given `agent wait` endet mit Timeout (Exit 1, JSON auf stderr) / When der Runner laeuft / Then wird kein `agent prompt` gesendet, das Log in `.claude/herdr_auto_clear.log` enthaelt einen Abbruch-Eintrag, Exit-Code 0
  - Test: tests/test_herdr_auto_clear_467.py::test_runner_aborts_on_wait_timeout

- **AC-14:** Given `agent wait` meldet Status `blocked` bzw. `unknown` (Exit 0) / When der Runner laeuft / Then wird kein `agent prompt` gesendet, Log-Eintrag, Exit-Code 0
  - Test: tests/test_herdr_auto_clear_467.py::test_runner_aborts_on_blocked_or_unknown

- **AC-15:** Given der Workflow-State aendert sich zwischen den Schritten (Phase gewechselt oder anderer erwarteter Befehl) / When der Runner den State-Recheck ausfuehrt / Then wird kein weiterer Prompt gesendet (vor dem ersten Prompt kein `/clear`, nach `/clear` kein Folgebefehl), Log-Eintrag, Exit-Code 0
  - Test: tests/test_herdr_auto_clear_467.py::test_runner_aborts_when_state_changed_between_steps

- **AC-16:** Given `agent prompt P /clear` endet mit Exit != 0 / When der Runner laeuft / Then wird der Folgebefehl nicht gesendet, es gibt keinen Retry, Log-Eintrag, Exit-Code 0
  - Test: tests/test_herdr_auto_clear_467.py::test_runner_aborts_when_clear_prompt_fails

- **AC-17:** Given der Default in `config.yaml` / When die Konfiguration geladen wird / Then ist `herdr.auto_clear.enabled` `false` (zusaetzlich `grace_s: 3`, `idle_timeout_s: 120`, `announce: true`)
  - Test: tests/test_herdr_auto_clear_467.py::test_config_default_auto_clear_disabled

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden). Hook-Seite per Subprozess gegen `footer_gate.py` mit Stub-Binary und isoliertem Projektverzeichnis; Runner synchron ueber die CLI `herdr_bridge.py auto-clear` mit Delays 0 und einem verzweigenden Stub, das je Unterbefehl (`agent wait`, `agent prompt`, `notification`) Exit-Code und JSON steuert und seine argv protokolliert:

- `pytest tests/test_herdr_auto_clear_467.py`
- Regressionslauf: `pytest tests/` (insbesondere Footer-Gate-Tests und `tests/test_herdr_sidebar_466.py`)
- Syntaxpruefung: `python3 -m py_compile core/hooks/herdr_bridge.py core/hooks/footer_gate.py`
- Manuell (nicht automatisierbar): Idle-Race und echtes Tippverhalten in einem realen Herdr-Pane

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Opt-in-Erweiterung des bestehenden #466-Utilities mit Default aus und eigenem Kill-Switch; sie aendert weder State-Format, Gate-Logik noch Hook-Registrierung (footer_gate ist bereits Stop-Hook, die Delegation ist fail-open). Voll reversibel durch Config-Wert oder Entfernen der Aufrufstelle, daher keine schwer umkehrbare strukturelle Weichenstellung, die eine ADR rechtfertigt.

## Changelog

- 2026-10-28: Initial spec created
