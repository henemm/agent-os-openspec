# Context: fix-700-handoff-same-reset (#700)

## Request Summary

Befund F001 aus der Gegenprüfung zu #696: `workflow.py handoff --same --start` schreibt nach
erfolgreichem Start den Vermerk `handoff_same = {phase, next, at}` und meldet bei gleichem
Phase+NEXT `STARTED=already`. Der Vermerk wird nie zurückgesetzt. Kehrt ein Workflow nach
BROKEN in dieselbe Phase mit demselben Folgebefehl zurück (phase6 → phase6b → phase6,
NEXT `/60-validate`), meldet ein erneuter Übergabeversuch `already`, der Befehlstext verlangt
Turn-Ende mit ⏳, aber keine Nachfolgerin läuft: der Workflow steht.

## Related Files

- `core/hooks/workflow.py`
  - `_handoff_same_start()` (~6100): prüft `note.phase == phase and note.next == nxt` → already;
    schreibt `handoff_same` + `waiting_on` nur bei Erfolg.
  - `record_transition()` (~2470): EINZIGE Stelle, die jeden Phasenwechsel protokolliert
    (#111). Leert bereits `waiting_on` (#550) und `spec_rework` (#647). Aufrufer: `cmd_phase`
    (~4026), Freigabe-Pfad (~5502), `phase_listener.py:588`.
  - `cmd_complete()` (~4460): setzt `phase8_complete` direkt, ohne `record_transition`, poppt
    `waiting_on` selbst.
  - `cmd_start()` (~3562): Startphase, kein Wechsel, neuer State ohne Vermerk — unkritisch.
- `tests/test_feat_696_handoff_same.py`: AC-12 (`test_second_start_same_phase_is_already`)
  testet already/neuer Start über vorgefertigte Vermerke.
- `docs/specs/feat-696-handoff-phasenwechsel.md`: Spec zu #696 (AC-12 definiert already).

## Existing Patterns

`waiting_on` wird exakt aus dem gleichen Grund (veralteter Zustand nach Wechsel) in
`record_transition` und `cmd_complete` verworfen (#550). Gleiches Muster für `handoff_same`
ist die naheliegende Lösung (Option 1 im Issue). Option 2 (`at` gegen Phaseneintritt prüfen)
wäre mehr Logik bei gleichem Effekt.

## Dependencies / Dependents

- Leser von `handoff_same`: nur `_handoff_same_start`.
- Folge: Nach einem echten Phasenwechsel ist ein erneuter Start in derselben Phase wieder
  möglich; innerhalb derselben Phase (ohne Wechsel) bleibt der Doppelstart-Schutz.

## Risks

- Hook-Code (Workflow-State) → Risiko hoch für Adversary-Runden.
- Doppelstart-Schutz darf innerhalb einer Phase nicht verloren gehen (AC-12 bleibt grün).

## Analysis

- **Type:** Bugfix (Score 1, Kontext + Analyse kombiniert; Ursache per Code-Lektüre belegt,
  keine Explore-Agenten nötig).
- **Ursache:** `core/hooks/workflow.py` `_handoff_same_start` vergleicht nur Phase+NEXT;
  `record_transition` und `cmd_complete` verwerfen `waiting_on`, aber nicht `handoff_same`.
- **Affected Files:**
  - `core/hooks/workflow.py` (MODIFY): `data.pop("handoff_same", None)` in `record_transition`
    neben `waiting_on`; ebenso in `cmd_complete`.
  - `tests/test_fix_700_handoff_same_reset.py` (CREATE): Rücksprung phase6→phase6b→phase6
    per `workflow.py phase` leert den Vermerk; danach `handoff --same --start` → `STARTED=yes`;
    ohne Phasenwechsel bleibt `already` (AC-12 unverändert).
  - `CHANGELOG.md`, `.claude-plugin/plugin.json`, `CLAUDE.md` (Version 4.28.1).
- **Scope/Risk:** ~4 LoC Produktivcode; Hook-Code → Adversary-Risiko hoch (2 Runden).
- **Technical Approach:** Option 1 aus dem Issue (Muster #550), weil `record_transition` der
  einzige Wechselpfad ist (#111) und damit alle Aufrufer (cmd_phase, Freigabe,
  phase_listener) automatisch abgedeckt sind. Option 2 (Zeitvergleich) verworfen: mehr
  Logik, Uhren-/Formatabhängigkeit, kein Mehrwert.
- **Open Questions:** keine.
