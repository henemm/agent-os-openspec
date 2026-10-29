---
entity_id: feat-476-herdr-plan-pane
type: feature
created: 2026-10-29
updated: 2026-10-29
status: draft
version: "1.0"
workflow: feat-476-herdr-plan-pane
tags: [herdr, workflow, plan, pane]
---

# Herdr: Workflow-Plan als Live-Bereich rechts neben Claude (Issue #476)

## Approval

- [ ] Approved

## Purpose

Laeuft Claude Code in einem Herdr-Pane, oeffnet sich beim Workflow-Start rechts daneben ein schmaler Pane, der den gesamten Workflow-Plan live zeigt: erledigte Schritte mit ✔, den laufenden mit ▶, kommende mit ○, darunter den naechsten Befehl. Herdr hat keine eingebaute rechte Leiste; der Bereich ist ein normaler Herdr-Pane (`pane split --direction right`), in dem ein Anzeigeprogramm des Frameworks laeuft. Die Anzeige ist auch ohne Herdr per `workflow.py plan` abrufbar.

## Source

- **File:** `core/hooks/workflow.py` (Schrittliste, Renderer, CLI `plan`, Ausloesung in `cmd_start`), `core/hooks/herdr_bridge.py` (Oeffnen des Panes: Spawn, Runner, CLI)
- **Identifier:** `PLAN_STEPS`, `PLAN_STEPS_FAST`, `render_plan`, `cmd_plan` (`plan`, `plan --watch`, `plan --open`); `plan_pane_enabled`, `open_plan_pane`, `run_plan_pane`, CLI `herdr_bridge.py plan-pane`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/workflow.py` | module | `PHASE_NUMBERS`, `expected_footer_command(data)`, `issue_number(name)`, `read_active_workflow_fast()`, `_archive_file(name)`, `_read_workflow` |
| `core/hooks/herdr_bridge.py` (#466/#467) | module | `_pane()`, `_binary()`, `_enabled()` (Eltern-Kill-Switch `herdr.enabled`), `_ac_base()` (worktree-lokales `.claude/`), Log-Rotation wie `_ac_log` |
| `core/hooks/hook_utils.py` | module | `resolve_active_workflow()` (cwd-basiert, Issue #58) |
| `core/hooks/config_loader.py` | module | `load_config()`; `herdr` steht bereits in `PLUGIN_CONFIG_KEYS` |
| Herdr-CLI (`$HERDR_BIN_PATH`, 0.9.5) | extern | `pane get <id>`, `pane split <id> --direction right --ratio F --cwd PATH --no-focus` (JSON `.result.pane.pane_id`; `ratio` = Breitenanteil des urspruenglichen Panes, geklemmt 0.1–0.9), `pane rename <id> <label>`, `pane run <id> <command>` |
| `tests/conftest.py` | test infra | autouse-Fixture isoliert `HERDR_*` (aus #466) |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | Schrittlisten, pure `render_plan`, CLI `plan` mit `--watch`/`--open`, fail-open Aufruf von `herdr_bridge.open_plan_pane()` am Ende von `cmd_start` |
| core/hooks/herdr_bridge.py | MODIFY | `plan_pane_enabled()`, `open_plan_pane()` (spawnt nur), Runner `run_plan_pane` + CLI `plan-pane`, Lock, Pane-ID-Datei, Log |
| config.yaml | MODIFY | `herdr.plan_pane: {enabled: true, ratio: 0.75}` mit Kommentar |
| tests/test_herdr_plan_pane_476.py | CREATE | Renderer pur, `plan`-CLI, Runner mit verzweigendem Stub-Binary, Lock, Kill-Switches, kein stdout aus `start` |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

Keine Aenderung an `hooks/hooks.json`, `phase_listener.py`, `session_banner.py`, Sidebar-Tokens aus #466.

### Estimated Changes

- Files: 1 neu, 4 geaendert
- LoC: +230 Produktion / +260 Test
- Risk Level: MEDIUM (veraendert das Herdr-Layout und tippt einen Befehl in eine frische Shell; ausserhalb von Herdr No-op)

## Implementation Details

**Schrittlisten.** Eigene Tabellen, nicht `PHASES.index()`:

| Schritt | Phase | Voll | Fast Track |
|---------|-------|------|------------|
| 1 Kontext | phase1_context | ✓ | – |
| 2 Analyse | phase2_analyse | ✓ | – |
| 3 Spec | phase3_spec | ✓ | ✓ |
| 4 Freigabe | phase4_approved | ✓ | ✓ |
| 5 TDD-RED | phase5_tdd_red | ✓ | – |
| 6 Implement | phase6_implement | ✓ | ✓ |
| 6b Adversary | phase6b_adversary | ✓ | – |
| 7 Validierung | phase7_validate | ✓ | ✓ |
| 8 Fertig | phase8_complete | ✓ | ✓ |

Fast Track = `workflow_type == "feature-fast"`.

**Status je Schritt** (`render_plan(data, archived=False, width=None) -> str`, pure, keine I/O): Index `i` des laufenden Schritts = Position von `current_phase` in der Liste; steht die Phase nicht in der Liste, gilt der letzte Listenschritt mit kleinerer Phasenposition (nach `PHASES`-Reihenfolge) als laufend, bei `phase0_idle` keiner. Schritte vor `i` = ✔, Schritt `i` = ▶ mit Zusatz `(läuft)`, danach ○. Bei `current_phase == "phase8_complete"` oder `archived=True` sind alle Schritte ✔.

**Aufbau der Ausgabe:**

```
Workflow #476
feat-476-herdr-plan-pane

✔ 1 Kontext
✔ 2 Analyse
▶ 3 Spec  (läuft)
○ 4 Freigabe
...
○ 8 Fertig

Nächster: Freigabe ...
```

- Kopfzeile `Workflow #<N>`, ohne Issue-Nummer `Workflow`; zweite Zeile der Name.
- Letzte Zeile `Nächster: <expected_footer_command(data)>` unveraendert (auch Freitext); fehlt der Wert, entfaellt die Zeile. Bei Phase 8 bzw. Archiv stattdessen `abgeschlossen`.
- Ohne Daten (`data is None`): `Kein aktiver Workflow`.
- `width` gesetzt: jede Zeile auf `width` Zeichen gekuerzt.

**CLI** `workflow.py plan [--watch | --open]` (wie die uebrigen Unterbefehle im Dispatch registriert):

- `plan`: loest den aktiven Workflow per `read_active_workflow_fast()` auf und druckt `render_plan` einmal, Exit 0 (auch ohne Workflow).
- `plan --watch`: Endlosschleife, je Sekunde neu aufloesen (Name nie einfrieren, damit `switch` und ein neuer `start` mitgehen); nur bei geaenderter Ausgabe neu zeichnen mit `\x1b[H\x1b[2J`, Breite aus `shutil.get_terminal_size()`. Liefert die Aufloesung nichts, wird der zuletzt gezeigte Name in `_archive/` gesucht und mit `archived=True` gezeigt; nie gezeigt → `Kein aktiver Workflow`. Jede Ausnahme in einer Runde → letzte Ausgabe bleibt stehen, Schleife laeuft weiter. Ctrl-C → Exit 0. Testhaken: Umgebungsvariable `OPENSPEC_PLAN_WATCH_ROUNDS=<n>` begrenzt die Runden, `OPENSPEC_PLAN_WATCH_INTERVAL=<s>` das Intervall.
- `plan --open`: ruft `herdr_bridge.open_plan_pane(force=True)` (ignoriert `plan_pane.enabled`, respektiert `herdr.enabled` und das Herdr-Env); gibt eine Zeile aus, ob ein Oeffnen angestossen wurde oder warum nicht (`kein Herdr-Pane`).

**Ausloesung.** Am Ende von `cmd_start`, nach `_herdr("report", data)`, in `try/except Exception`: `herdr_bridge.open_plan_pane()`. Kein Aufruf aus `switch`, `phase`, Hooks. `cmd_start` behaelt Exit-Code und stdout unveraendert.

**`open_plan_pane(force=False) -> bool`** (fail-open, nie stdout/stderr): `_pane()` muss eine Pane-ID liefern; ohne `force` muss `plan_pane_enabled()` wahr sein. Dann `[sys.executable, herdr_bridge.py, "plan-pane", "--pane", P, "--cwd", <_ac_base()>, "--ratio", R]` per `subprocess.Popen` (kein Shell, `start_new_session=True`, Streams DEVNULL, `close_fds=True`); kehrt sofort zurueck. Rueckgabe: ob gespawnt wurde.

**`plan_pane_enabled()`**: Opt-out — nur das Literal `herdr.plan_pane.enabled: false` schaltet ab; fehlt der Abschnitt, gilt an. `herdr.enabled: false` schaltet immer ab (ueber `_pane()`). `ratio`: Zahl im Bereich 0.1–0.9, sonst Default 0.75.

**Runner** (`run_plan_pane`, CLI `plan-pane --pane P --cwd C --ratio R [--delay S]`, immer Exit 0, Log `.claude/herdr_plan_pane.log` unter `_ac_base()`, gleiche Rotation wie `_ac_log`):

1. Lock `.claude/herdr_plan_pane.lock` per `os.open(O_CREAT|O_EXCL)`; existiert er und ist juenger als 30 s → Abbruch mit Log `läuft bereits`; aelter → ersetzen. Freigabe im `finally`.
2. Gemerkte ID aus `.claude/herdr_plan_pane.json` (`{"pane_id": ...}`): falls vorhanden, `pane get <id>` (Timeout 3 s); Exit 0 → Log `vorhanden`, Ende.
3. `pane split P --direction right --ratio R --cwd C --no-focus` (Timeout 5 s); neue ID aus JSON `.result.pane.pane_id`; Exit ≠ 0 oder keine ID → Log, Ende.
4. `pane rename <neu> Workflow` (Fehler ignoriert).
5. `--delay` warten (Default 0.5 s), dann `pane run <neu> "exec <quote(sys.executable)> <quote(workflow.py)> plan --watch"` mit `shlex.quote`; `workflow.py` = Datei neben `herdr_bridge.py`.
6. ID in `.claude/herdr_plan_pane.json` schreiben (atomar), auch wenn `pane run` scheitert (Pane existiert), Log-Zeile mit Ergebnis.

**Konfiguration.** `config.yaml` → `herdr.plan_pane: {enabled: true, ratio: 0.75}` mit Kommentar (Opt-out, Wirkung, Ratio-Bedeutung).

**Umsetzungsnachtrag (Validierung).** Zusaetzlich `plan_pane_settings() -> {"enabled", "ratio"}` (vom Test verlangt), `_ac_log` um den Parameter `log_file` erweitert (Default unveraendert, #467-Verhalten gleich). `tests/test_herdr_sidebar_466.py::test_start_reports_workflow_state` setzt `herdr.plan_pane.enabled: false`, weil `start` mit Default jetzt zwei Herdr-Aufrufe macht und der Test nur den Sidebar-Report zaehlt. Umfang: +342 LoC Produktion statt geschaetzt +230.

## Expected Behavior

- **Input:** `workflow.py start <name>` in einem Herdr-Pane (gueltiges Herdr-Env, `herdr.enabled` und `herdr.plan_pane.enabled` nicht `false`)
- **Output:** Rechts neben dem Claude-Pane erscheint ein Pane „Workflow“, der den Plan live zeigt und bei jedem Phasenwechsel innerhalb von etwa einer Sekunde nachzieht; `start` gibt dasselbe aus wie bisher
- **Side effects:** Ein detachter Runner pro Start; `.claude/herdr_plan_pane.json`, `.claude/herdr_plan_pane.lock` (kurzlebig), `.claude/herdr_plan_pane.log`; ist der Pane schon offen, passiert nichts

## Known Limitations

- Echtes Layout, Breite und Tippverhalten sind nur in einem realen Herdr pruefbar; die Tests nutzen ein Stub-Binary.
- `pane run` tippt in die Shell des neuen Panes. Das Quoting ist POSIX (`shlex.quote`); exotische Shells (z. B. fish mit Sonderzeichen im Pfad) koennen scheitern — dann bleibt ein leerer Shell-Pane, `workflow.py plan --watch` laesst sich darin von Hand starten.
- Ist die Shell nach 0.5 s noch nicht bereit, kann der getippte Befehl verloren gehen.
- Ctrl-C im Plan-Pane beendet das Programm und schliesst durch `exec` den Pane; der naechste `start` oeffnet ihn neu.
- Die Ratio ist relativ; bei sehr schmalem Terminal wird der Pane knapp. Eine Mindestbreite erzwingt Herdr nicht.
- Geoeffnet wird nur bei `start` (und `plan --open`), nicht beim Wiedereinstieg nach `/clear` oder `switch`.
- Nach einem Herdr-Server-Neustart ist die gemerkte Pane-ID ungueltig; `pane get` erkennt das, der naechste `start` oeffnet neu.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] In einem echten Herdr-Pane erscheint nach `workflow.py start` rechts ein Pane „Workflow“ mit dem Plan, der Phasenwechseln folgt (manuelle Abnahme durch den PO)
- [ ] Ausserhalb von Herdr oder mit Kill-Switch verhaelt sich `workflow.py start` exakt wie vorher
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen, insbesondere #466-/#467-Tests)

## Acceptance Criteria

- **AC-1:** Given ein voller Workflow in `phase5_tdd_red` mit Issue-Nummer 476 / When `render_plan` laeuft / Then zeigt die Ausgabe `Workflow #476`, Schritte 1–4 mit ✔, `▶ 5 TDD-RED  (läuft)`, Schritte 6, 6b, 7, 8 mit ○ in dieser Reihenfolge und `Nächster: ` mit dem Wert von `expected_footer_command`
  - Test: tests/test_herdr_plan_pane_476.py::test_render_full_workflow_marks_done_running_open

- **AC-2:** Given ein Fast-Track-Workflow (`feature-fast`) in `phase6_implement` / When `render_plan` laeuft / Then enthaelt die Ausgabe genau die Schritte 3, 4, 6, 7, 8 (kein Kontext, Analyse, TDD-RED, Adversary), 3 und 4 mit ✔, 6 laufend, 7 und 8 offen
  - Test: tests/test_herdr_plan_pane_476.py::test_render_fast_track_steps

- **AC-3:** Given ein Fast-Track-Workflow, dessen Phase nicht in der Fast-Track-Liste steht (`phase5_tdd_red`) / When `render_plan` laeuft / Then gilt Schritt 4 als laufend und es gibt keine Ausnahme
  - Test: tests/test_herdr_plan_pane_476.py::test_render_fast_track_off_list_phase

- **AC-4:** Given ein Workflow in `phase8_complete` bzw. ein archivierter Workflow (`archived=True`) / When `render_plan` laeuft / Then sind alle Schritte ✔, kein ▶, letzte Zeile `abgeschlossen`
  - Test: tests/test_herdr_plan_pane_476.py::test_render_complete_and_archived

- **AC-5:** Given `data is None` / When `render_plan` laeuft / Then ist die Ausgabe `Kein aktiver Workflow`; Given `width=12` / Then ist keine Zeile laenger als 12 Zeichen
  - Test: tests/test_herdr_plan_pane_476.py::test_render_no_workflow_and_width

- **AC-6:** Given ein aktiver Workflow / When `workflow.py plan` laeuft / Then gibt es die Plan-Ausgabe mit Exit 0 aus; ohne aktiven Workflow `Kein aktiver Workflow` mit Exit 0
  - Test: tests/test_herdr_plan_pane_476.py::test_cli_plan_prints_once

- **AC-7:** Given `plan --watch` mit `OPENSPEC_PLAN_WATCH_ROUNDS=2` und Intervall 0, der zuletzt gezeigte Workflow wird zwischen den Runden archiviert / When die zweite Runde laeuft / Then zeigt sie den archivierten Workflow als `abgeschlossen`, Exit 0
  - Test: tests/test_herdr_plan_pane_476.py::test_watch_follows_archive

- **AC-8:** Given gueltiges Herdr-Env (Stub-Binary) und Default-Config / When `workflow.py start x` laeuft / Then wird der Runner gestartet (Stub protokolliert `pane split ... --direction right --ratio 0.75 --cwd <projekt> --no-focus`, danach `pane rename <neu> Workflow` und `pane run <neu> "exec ... workflow.py ... plan --watch"`), die ID steht in `.claude/herdr_plan_pane.json`, und die stdout von `start` ist identisch mit der ohne Herdr-Env
  - Test: tests/test_herdr_plan_pane_476.py::test_start_opens_pane_with_split_rename_run

- **AC-9:** Given `.claude/herdr_plan_pane.json` mit einer ID, fuer die `pane get` Exit 0 liefert / When der Runner laeuft / Then wird kein `pane split` ausgefuehrt; liefert `pane get` Exit ≠ 0, wird gesplittet und die neue ID gespeichert
  - Test: tests/test_herdr_plan_pane_476.py::test_runner_reuses_existing_pane_or_reopens

- **AC-10:** Given eine Lock-Datei juenger als 30 s / When der Runner laeuft / Then fuehrt er kein `pane split` aus und loggt `läuft bereits`; ist der Lock aelter als 30 s, laeuft er normal
  - Test: tests/test_herdr_plan_pane_476.py::test_runner_lock_blocks_parallel_and_expires

- **AC-11:** Given `pane split` endet mit Exit ≠ 0 bzw. liefert JSON ohne `.result.pane.pane_id` / When der Runner laeuft / Then folgen kein `pane rename`/`pane run`, keine ID-Datei, ein Log-Eintrag, Exit 0
  - Test: tests/test_herdr_plan_pane_476.py::test_runner_aborts_on_failed_split

- **AC-12:** Given `herdr.plan_pane.enabled: false` bzw. `herdr.enabled: false` bzw. kein Herdr-Env / When `workflow.py start x` laeuft / Then wird kein Herdr-Aufruf mit `pane split` protokolliert
  - Test: tests/test_herdr_plan_pane_476.py::test_no_pane_when_disabled_or_outside_herdr

- **AC-13:** Given `herdr.plan_pane.enabled: false`, aber gueltiges Herdr-Env / When `workflow.py plan --open` laeuft / Then wird der Pane trotzdem geoeffnet (Stub protokolliert `pane split`); ohne Herdr-Env meldet der Befehl `kein Herdr-Pane`, Exit 0
  - Test: tests/test_herdr_plan_pane_476.py::test_plan_open_forces_pane

- **AC-14:** Given die Default-`config.yaml` / When die Konfiguration geladen wird / Then ist `herdr.plan_pane.enabled` `true` und `herdr.plan_pane.ratio` `0.75`; ein ungueltiger Ratio-Wert (z. B. `2` oder `"x"`) fuehrt zu `0.75`
  - Test: tests/test_herdr_plan_pane_476.py::test_config_default_and_ratio_validation

## Test Plan

Automatische Tests, je an eine AC gebunden. Renderer direkt importiert; CLI per Subprozess gegen `core/hooks/workflow.py` in einem isolierten Projektverzeichnis; Runner synchron ueber `herdr_bridge.py plan-pane --delay 0` mit einem verzweigenden Stub-Binary (`HERDR_BIN_PATH`), das argv protokolliert und je Unterbefehl (`pane get`, `pane split`, `pane rename`, `pane run`) Exit-Code und JSON steuert; fuer AC-8/12/13 wird auf das Protokoll des detachten Runners mit kurzer Frist gewartet.

- `pytest tests/test_herdr_plan_pane_476.py`
- Regressionslauf: `pytest tests/` (insbesondere `tests/test_herdr_sidebar_466.py`, `tests/test_herdr_auto_clear_467.py`)
- Syntaxpruefung: `python3 -m py_compile core/hooks/workflow.py core/hooks/herdr_bridge.py`
- Manuell (nicht automatisierbar): echtes Layout und Live-Aktualisierung in einem realen Herdr-Pane

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Rein anzeigende Erweiterung des bestehenden Herdr-Utilities (#466/#467); sie aendert weder State-Format noch Gate-Logik noch Hook-Registrierung. Der Plugin-Pane-Weg (`herdr-plugin.toml`) wurde verworfen, weil er eine Plugin-Installation beim User verlangt. Voll reversibel per Config-Wert (`herdr.plan_pane.enabled: false`) oder Entfernen der Aufrufstelle in `cmd_start`, daher keine schwer umkehrbare Weichenstellung, die eine ADR rechtfertigt.

## Changelog

- 2026-10-29: Initial spec created
