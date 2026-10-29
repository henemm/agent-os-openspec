# Context: feat-476-herdr-plan-pane

## Request Summary
Läuft Claude Code in einem Herdr-Pane, soll rechts daneben ein schmaler Bereich den gesamten Workflow-Plan live zeigen: erledigte Schritte ✔, laufender ▶, kommende ○, darunter der nächste Befehl. #466 lieferte nur Titel/Tokens für die linke Sidebar — das war nicht das Gewünschte.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py` | `PHASES`, `PHASE_NUMBERS`, `TOTAL_PHASES`, `expected_footer_command()`, `issue_number()`, `read_active_workflow_fast()`, `_archive_file()`; `cmd_start` (Fast Track startet in `phase3_spec`) — Ort für Renderer + CLI `plan` und Auto-Öffnen beim Start |
| `core/hooks/herdr_bridge.py` | Gate `_pane()`/`_binary()`/`_enabled()`, `_launch` (detached), Muster für detachten Runner + CLI (`auto-clear`) — Ort für das Öffnen des Panes |
| `config.yaml` | Abschnitt `herdr:` (#466/#467) — neuer Unterabschnitt `plan_pane` |
| `core/hooks/config_loader.py` | `herdr` bereits in `PLUGIN_CONFIG_KEYS` |
| `tests/test_herdr_sidebar_466.py`, `tests/test_herdr_auto_clear_467.py` | Stub-Binary-Muster über `HERDR_BIN_PATH`, conftest entfernt `HERDR_*` |

## Herdr-Schnittstelle (0.9.5, aus Doku + Quellcode verifiziert)
- Keine eingebaute rechte Leiste; nur linke Sidebar + einzeiliger Statusbereich rechts in der Tab-Zeile
- `herdr pane split [<pane>] --direction right [--ratio F] [--cwd PATH] [--env K=V] [--no-focus]` → JSON, neue ID unter `.result.pane.pane_id`
- `--ratio` = Breitenanteil des **ursprünglichen** (ersten) Panes, geklemmt auf 0.1–0.9 (`src/layout.rs` `split_node`/`split_rect`) → 0.75 ⇒ neuer Pane ein Viertel
- `herdr pane run <pane> <command>` tippt Text + Enter in die Shell des Panes
- `herdr pane get <pane>` → Exit ≠ 0, wenn der Pane nicht mehr existiert
- `herdr pane rename <pane> <label>`
- Alternative Plugin-Pane (`herdr-plugin.toml`, `placement = "split"`) verworfen: braucht Plugin-Installation beim User

## Existing Patterns
- Fail-open, nie stdout in Hooks/`workflow.py`-Kernpfaden
- Detachter Runner-Prozess für mehrstufige Herdr-Abläufe (#467), Log unter `.claude/`
- Kill-Switch-Muster `herdr.<feature>.enabled`

## Dependencies
- Upstream: Herdr-CLI ≥ 0.9.5, `workflow.py`-Phasentabellen
- Downstream: keine

## Risks & Considerations
- Doppelte Panes bei jedem Start → Pane-ID merken, vor dem Öffnen per `pane get` prüfen
- `pane run` tippt in eine Shell — Pfade mit Leerzeichen quoten; Shell des Users unbekannt
- `cwd` des neuen Panes bestimmt, welchen Workflow die Anzeige auflöst (Worktree!)
- Nach `complete` ist der Workflow archiviert → Anzeige soll „abgeschlossen“ zeigen statt zu verschwinden
- Herdr hier nicht installiert → Stub-Binary-Tests; echtes Layout nur manuell prüfbar

## Analysis

### Type
Feature

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `PLAN_STEPS`, pure `render_plan(data, archived, width)`, CLI `plan` / `plan --watch` / `plan --open`, fail-open Auto-Öffnen in `cmd_start` |
| core/hooks/herdr_bridge.py | MODIFY | `plan_pane_enabled()`, `open_plan_pane()` (spawnt nur), Runner + CLI `plan-pane` (Lock, `pane get`, `pane split`, `pane rename`, `pane run`), eigenes Log |
| config.yaml | MODIFY | `herdr.plan_pane: {enabled: true, ratio: 0.75}` |
| tests/test_herdr_plan_pane_476.py | CREATE | Renderer pur, Watch einmalig, Runner mit Stub-Binary, Lock-Race, Kill-Switch, kein stdout |
| CHANGELOG.md | MODIFY | [Unreleased] |

### Scope Assessment
- Files: 1 neu, 4 geändert
- Estimated LoC: +230 Prod / +260 Test
- Risk Level: MEDIUM (Layout-Änderung + Tippen in eine frische Shell; ausserhalb Herdr No-op)

### Technical Approach (Plan/Sonnet-Bewertung übernommen)
- Eigene Schrittliste statt `PHASES.index()`; Fast Track 3,4,6,7,8; Phase ausserhalb der Liste → nächstkleinerer Schritt läuft
- Pane-ID-Datei, Lock und `--cwd` über `_ac_base()` (worktree-lokal); Watcher löst jede Sekunde neu auf (Issue #58: Env im neuen Pane nicht gesetzt)
- Once-Lock per `O_EXCL` (30 s Stale-Grenze) gegen parallele Starts
- `pane run` mit `exec <sys.executable> <workflow.py> plan --watch`, Pfade per `shlex.quote`, kurze Wartezeit nach dem Split
- Auslösung nur aus `cmd_start` (nicht `switch`), Ablauf ausschliesslich im detachten Runner

### PO-Entscheidung
- Auto-Öffnen beim Workflow-Start: **an** (Default `enabled: true`, Opt-out); Begründung des Agents für Opt-in (Layout-Eingriff) als Kritische Anmerkung ins Briefing
