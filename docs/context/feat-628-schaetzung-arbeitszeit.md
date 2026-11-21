# Context: feat-628-schaetzung-arbeitszeit

## Request Summary
Die Zeitschätzung aus #620 (Plan-Pane, `workflow.py estimate`) zeigt Spannen wie „1 h 43 min–8 h 37 min“. Sie soll künftig nur Arbeitszeit schätzen. Wartezeit auf eine PO-Freigabe und Leerlauf zählen nicht mit. Steht eine menschliche Freigabe tatsächlich aus, erscheint „+ Wartezeit auf dich“ (PO-Entscheidung 2026-11-21, #628).

## Befund (Archiv `.claude/workflows/_archive/`, 11 Workflows)
- Reine Arbeit meist 36–97 min.
- feat-562: Segment `phase3_spec` 21:47 → 05:49 (482 min), danach Übergang `phase4_approved` mit `trigger: "approval"` (menschliche Freigabe, Ampel nicht grün). feat-589: dasselbe Muster, 465 min.
- fix-566: Spec um 09:44 automatisch freigegeben (`trigger: "auto"`), weiter erst 12:18 → 154 min Leerlauf in `phase4_approved`, ohne Wartegrund.
- `go` (GREEN) ist im Auto-Modus seit #471 automatisch (alle 11: `approvals[gate=green].by == "auto"`). #629 (go abschaffen) deshalb geschlossen.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py` Z. 790–1065 | Zeitschätzung: `_archive_phase_entry`, `load_archive_phase_durations`, `_estimate_rests`, `estimate_remaining`, `current_estimate`, `_plan_time_lines`, `_estimate_basis`; `_finished_span` (Ist-Block) |
| `core/hooks/workflow.py` `cmd_estimate`, `_estimate_kv_lines` (~Z. 4834) | CLI-Ausgabe `ESTIMATE_*`, `LINE=` |
| `core/hooks/workflow.py` `_retro_estimate_line` (~Z. 4460) | Retro-Lernnachweis |
| `core/hooks/session_singleton_guard.py` `_heartbeat` (Z. 596) | PreToolUse auf allen Tools, Throttle 60 s (`_HEARTBEAT_THROTTLE_SECONDS`), kennt Workflow/Phase über `_apply_context_fields`. Einzige bestehende Stelle mit regelmäßigem Aktivitätssignal |
| `tests/test_time_estimate*.py` (aus #620) | Bestehende Tests der Schätzung |
| `config.yaml` Abschnitt `time_estimate` | Anzeige-Abschnitt, ohne Override änderbar (#622) |

## Vorhandene Zeitstempel im Workflow-State
- `phase_log[]`: `entered_at`, `exited_at`, `duration_min` (Wall-Clock, Wiedereintritte als eigene Segmente).
- `phase_transitions[]`: `to`, `at`, `trigger` (`command` | `auto` | `approval`). `approval` = menschliche Spec-Freigabe.
- `po_briefing.created`: Zeitpunkt des Briefings = ab hier wartet die Spec auf Freigabe.
- `approvals[].at`, `last_test_run.at`, `spec_post_approval_edits[].ts`.
- Kein Aktivitätsprotokoll: Leerlauf innerhalb eines Segments ist rückwirkend nicht erkennbar.

## Existing Patterns
- Zeitschätzung ist reine Anzeige, fail-open, wirft nie (#620).
- Heartbeat schreibt höchstens einmal je 60 s, wirft nie (EB-1).
- Workflow-State wird per Read-Modify-Write von `workflow.py` geschrieben. Ein zweiter Schreiber (Hook) auf dieselbe Datei kann Phasenwechsel überschreiben. Daher eine eigene Datei je Workflow, nie das Workflow-JSON aus dem Hook.

## Analyse (Kontext und Analyse in einem Durchgang, Score 2)

**Zwei Arten Nicht-Arbeitszeit:**
1. *Wartezeit auf den PO:* rückwirkend exakt bestimmbar. Spanne `[po_briefing.created, at]` des Übergangs nach `phase4_approved` mit `trigger == "approval"`. Wird von den Phasensegmenten abgezogen (Überschneidung).
2. *Leerlauf:* nur vorausschauend messbar. Der Heartbeat (alle Tools, also auch Teilagenten) zählt Aktivminuten je Phase in eine eigene Datei `.claude/workflows/_activity/<workflow>.json`: Liegt der letzte Schlag höchstens `idle_gap_min` (Standard 15 min = `_STALE_SECONDS`) zurück, zählt die Differenz als Arbeit der aktuellen Phase, sonst nichts.

**Empfehlung (Variante A):** Archiv-Eintrag nutzt die Aktivminuten, wenn eine Aktivitätsdatei existiert. Sonst `phase_log` abzüglich PO-Wartezeit. Laufender Workflow analog: verstrichene Zeit = Arbeitszeit, nicht Wanduhr.

**Alternative B: Lückenkappung ohne neues Signal.** Jede Phase über X min wird auf X gekappt. Verworfen: Legitime lange Phasen (iOS-Builds in Loose Ends, 30–60 min) würden verfälscht. Der Grenzwert wäre willkürlich. Würde B gewählt, fiele die ADR „Schätzung nur aus `phase_log`, kein Aktivitätssignal“.

**Alternative C: Aktivität aus dem Claude-Transcript.** Verworfen: Transcripts sind sitzungsgebunden, `/clear` erzeugt neue. Beim Archivieren nicht verlässlich zuzuordnen.

**ADR (bei Variante A):** Aktivität wird vom Session-Heartbeat in eine eigene Datei je Workflow geschrieben, nie ins Workflow-JSON (kein zweiter Schreiber auf den State).

## Dependencies
- Upstream: `phase_log`, `phase_transitions`, `po_briefing`, Heartbeat in `session_singleton_guard.py`, `config_loader`.
- Downstream: Plan-Pane (`_plan_time_lines`), `workflow.py estimate` (Intake-Zeile, Herdr), Retro (`_retro_estimate_line`), `_stamp_intake_estimate`.

## Existing Specs
- `docs/specs/feat-620-zeitschaetzung.md`: Grundspec der Schätzung, wird ergänzt, nicht abgelöst.

## Risks & Considerations
- `session_singleton_guard.py` ist ein Guard auf allen Tools. Der neue Aufruf muss vollständig fail-open sein und darf nur im fälligen Throttle-Zweig laufen (keine Mehrlast je Tool-Aufruf).
- Mehrere Sitzungen am selben Workflow: Aktivitätsdatei per atomarem Schreiben, letzter Schreiber gewinnt; Doppelzählung höchstens 1 min je Schlag.
- „+ Wartezeit auf dich“ nur, wenn eine menschliche Freigabe aussteht: Phase `phase3_spec`, Briefing gesetzt und Auto-Freigabe nicht möglich (Ampel rot oder Modus manual).
- Ist-Block: Arbeitszeit und Gesamtzeit getrennt, sonst wirkt die Prognose falsch.
- Bestehende Tests aus #620 müssen grün bleiben. Archivdateien werden nicht migriert.
