# Context: fix-691-auto-abhaken (Issue #691)

## Request Summary
Im Auto-Modus liefert `/60-validate` selbst bis `main` aus (`scripts/ship.py --merge`), ruft aber nie
`workflow.py finish`/`complete` auf. Folge (Echtbeleg #686, Workflow `fix-653-target-dir-flag`):
Workflow bleibt in `phase8_complete` aktiv in `.claude/workflows/`, das Issue steht im Auftrag
(`.claude/auftrag/<owner>.json`) weiter als `open`, `queue` würde es erneut als `NEXT` vorschlagen.

## Related Files
- `core/hooks/workflow.py`
  - `cmd_complete` (~4397): Log-Pflicht, `_validate_transition(phase8_complete)`, `_mark_ship_open`,
    Archivierung (`_archive_dir`, `_workflow_file(name).unlink()`, `_persist_env(None)`, `_herdr("clear")`),
    danach `auftrag_mark_done` (#551, fail-open). Einziger Ort, der im Auftrag abhakt.
  - `cmd_write_log` (4335): schreibt `.claude/workflows/_log/<datum>_<name>.yaml` aus dem **aktiven** Workflow.
  - `cmd_ship_status` (~4660): setzt `ship_status`/`ship_at`/`ship_note`; bei `done`/`skipped`
    `_claim_release` (#461). Ziel: aktiver Workflow, sonst `_ship_fallback_target` (Archiv), oder `<nr|name>`.
  - `_mark_ship_open` (#612), `_ship_fallback_target`, `_status_target`.
- `core/hooks/hook_utils.py::auftrag_mark_done` (3281) — wirft nie, False ohne Auftrag/Nummer.
- `scripts/ship.py` — ruft nach erfolgreichem Merge `ship-status done "PR N gemergt"` (Zeile ~337).
- `core/commands/60-validate.md` / `skills/60-validate/SKILL.md` — Step 4 setzt nur
  `phase phase8_complete`; Auto-Weg (Punkt 5) endet mit `ship.py --merge`, kein `finish`.

## Existing Patterns
- Fail-open-Nebenwirkungen in try/except (`cmd_complete` #551, `_herdr` #555).
- `ship-status` wird von `ship.py` als Subprozess der Sitzung gerufen → gleiche Env, gleicher Auftrags-Owner.
- Tests: `tests/test_auftrag_551.py`, `tests/test_auto_ship_525.py` (Subprozess mit `cwd=tmp_path`).

## Dependencies / Dependents
- Plan-Pane/Seitenleiste/`endstate` lesen `ship_status` und Auftrag; `endstate` nutzt `queue_next`.
- `_ship_fallback_target` findet archivierte Workflows mit offenem Stand — Archivierung nach `done` stört das nicht.
- `/90-retro` braucht das Execution-Log im `_log`-Ordner.

## Existing Specs
- `docs/specs/` zu #551 (Auftrag), #612 (ship-status), #525 (auto-ship).

## Risks
- Archivieren aus `ship-status` heraus darf keinen Workflow treffen, der nicht `phase8_complete` ist
  (z. B. `ship-status done` von Hand in Phase 6).
- Archivieren eines nicht aktiven Workflows darf den Aktiv-Zeiger einer anderen Sitzung nicht löschen.
- Doppelte Ausführung (`complete` nach `ship-status done`) muss idempotent bleiben.

## Analysis

**Type:** Bugfix (Auto-Weg schließt Workflow und Auftrag nicht ab)

### Affected Files
| Datei | Change | Grund |
|---|---|---|
| `core/hooks/workflow.py` | MODIFY | Abschluss-Teil von `cmd_complete` als Helfer `_finalize_archive(data, name)` herauslösen; `cmd_ship_status` ruft bei `done`/`skipped` fail-open (a) `auftrag_mark_done` für die Issue-Nummer des Ziel-Workflows, (b) bei nicht archiviertem Ziel in `phase8_complete` die Archivierung inkl. Execution-Log, falls noch keins existiert |
| `tests/test_ship_status_finalize_691.py` | CREATE | Auto-Weg: `phase8_complete` → `ship-status done` → Workflow im Archiv, Log vorhanden, Auftrag `done`; Negativfälle |
| `core/commands/60-validate.md`, `skills/60-validate/SKILL.md` | MODIFY | Ein Satz in Step 4: `ship-status done` schließt den Workflow ab (archiviert, hakt im Auftrag ab); `finish` danach nicht mehr nötig |
| `CHANGELOG.md` | MODIFY | Eintrag |

### Scope / Risk
~60–90 LoC Produktivcode, 1 Hook-Datei (hohes Adversary-Risiko, da `workflow.py`). Blast Radius: nur der
`done`/`skipped`-Zweig von `ship-status`; `running`/`failed` unverändert.

### Technical Approach
Kopplung an „Phase 8 + ausgeliefert“ statt an einen zusätzlichen Befehl im Anweisungstext: `ship.py` setzt
`ship-status done` mechanisch nach dem Merge, also greift der Abschluss ohne dass Claude an `finish` denken muss.
- Ziel ist **aktiv** (Datei in `.claude/workflows/`) und `current_phase == phase8_complete`: Log schreiben, falls
  keins (`_log/*_<name>.yaml`), dann archivieren wie `complete` (Datei ins Archiv, Arbeitsdatei löschen,
  `_persist_env(None)` + `_herdr("clear")` nur, wenn es der aktive Workflow der Sitzung ist).
- Ziel nicht in Phase 8 (z. B. Hand-Aufruf früher): nur Status setzen wie bisher, kein Archiv, kein Abhaken.
- Ziel schon im Archiv (`complete` lief vorher): nur abhaken (idempotent).
- Abhaken im Auftrag bei `done`/`skipped`, wenn das Ziel `phase8_complete` ist oder bereits archiviert.
- Alles fail-open: Fehler beim Archivieren/Abhaken ändern weder Ausgabe `SHIP_STATUS=…` noch Exit-Code;
  zusätzliche Ausgabezeile `ARCHIVED=<name>` nur bei erfolgter Archivierung.
- `cmd_complete` nutzt denselben Helfer (keine Verhaltensänderung).

### Alternativen (verworfen)
| Variante | Nachteil |
|---|---|
| Nur Anweisungstext: `/60-validate` ruft nach Merge `write-log` + `finish` | Genau das Vergessen ist der Befund; nicht mechanisch |
| Abhaken bereits bei `phase phase8_complete` | Issue gälte als erledigt, bevor ausgeliefert ist (CI rot) |

### Open Questions
Keine.
