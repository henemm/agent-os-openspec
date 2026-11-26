# Kontext: feat-696-handoff-phasenwechsel (Issue #696)

## Request Summary

Im Auto-Modus wächst der Kontext innerhalb eines Issues ungebremst (Beleg #691: ~200k bei
Schwelle ~150k). Seit #663 tippt niemand mehr `/clear`; frischen Kontext gibt es nur je Issue
(`workflow.py handoff`, #667/#694). Ziel: Liegt die Messung an einem Phasenwechsel über der
Schwelle, startet Claude per `handoff --start` eine neue Sitzung für **denselben Workflow**
(Startauftrag `/<nächster Befehl> #N`) und beendet die Antwort. Eigener Tab + Aufräumen der
Vorgängerin wie #694. Nur an Phasenwechseln mit positivem Checkpoint. Cloud ohne Herdr:
bisheriges Verhalten.

## Related Files

- `core/hooks/workflow.py`
  - `cmd_context` (~5596): Ausgabe `CONTEXT_TOKENS/CUT/THRESHOLD/REASON/STOP`; bei autarkem
    Auftrag wird CUT hart auf `off` gezwungen (`CONTEXT_REASON=AUTARK`). Letzte Zeile ist
    `CONTEXT_STOP=` (vertraglich).
  - `_context_measurement`, `hook_utils.context_budget_settings`,
    `hook_utils.effective_context_threshold`, `hook_utils.context_stop_applies`.
  - `cmd_handoff` (~5988), `handoff_route`, `handoff_prompt`, `_handoff_label`,
    `_handoff_mark` (Vermerk im Auftrag, Feld `handoff`, Schlüssel = Issue).
  - `next_step` / `expected_footer_command` (~288/330): Folgebefehl aus dem State, z. B.
    `/50-implement #696`; Freitext-Schritte (Freigabe) beginnen nicht mit `/`.
  - `cmd_waiting` (~4908): `waiting_on` → Endzustand ⏳; Phasenwechsel leert es.
- `core/hooks/herdr_bridge.py`
  - `start_session(prompt, cwd, label)` (~855): neuer Tab mit
    `OPENSPEC_HANDOFF_PREV_PANE`, Rückfall Split.
  - `start_predecessor_cleanup` / `handoff-cleanup` (~950ff): Nachfolgerin schließt Tab der
    Vorgängerin, sobald diese ruht und ihre letzte Endzustandsmarke ⏳ ist.
- `core/hooks/hook_utils.py::find_project_root` löst Worktrees zum Haupt-Repo auf —
  `cmd_handoff` übergibt diesen Pfad heute als `cwd`. Für denselben Workflow wäre das falsch:
  die neue Sitzung landete im Haupt-Ordner, legte per Worktree-Pflicht einen frischen Worktree
  von origin/main an und sähe die laufenden, noch nicht ausgelieferten Änderungen nicht.
- `core/commands/{10-context,20-analyse,30-write-spec,40-tdd-red,50-implement}.md`:
  Abschnitt „Auto-Modus: Kette selbst fortsetzen“ ruft `workflow.py context` vor dem
  Selbstaufruf des Folge-Skills.
- `core/commands/80-workflow.md`, `docs/befehle/*.md`: Doku des `handoff`-Befehls.
- Tests: `tests/test_handoff*.py`, `tests/test_context*.py` (bestehende Muster).

## Existing Patterns

- KEY=value-Ausgaben, fail-open, Exit 0 (außer Usage).
- Vermerk gegen Doppelstart (`HANDOFF_DONE`/`STARTED=already`, #668).
- Startauftrag ohne Gesprächswissen lesbar (`handoff_prompt`).
- Workflow-Registrierung am Issue (`issue_claim`) hängt am Workflow, nicht an der Sitzung:
  `switch` auf denselben Workflow löst keinen Konflikt aus.
- Worktree-Sitzung: aktive Workflow-Auflösung über worktree-lokale `.claude/active_workflow`
  → eine neue Sitzung im selben Worktree findet denselben Workflow.

## Analyse / Ansatz

1. `cmd_context` meldet zusätzlich `CONTEXT_HANDOFF=on|off`: `on` genau dann, wenn
   Messung ≥ wirksame Schwelle, `context_budget` an, Autonomie `auto`, nicht Cloud
   (`CLAUDE_CODE_REMOTE`), Herdr-Pane und `claude` vorhanden. Gilt auch bei autarkem
   Auftrag (dort bleibt `CONTEXT_CUT=off`). `CONTEXT_STOP` bleibt letzte Zeile.
2. `workflow.py handoff --same [--start]`: Übergabe desselben Workflows. Folgebefehl aus
   `expected_footer_command` (nur Slash-Befehle; sonst `HANDOFF=none`). Arbeitsordner =
   Wurzel des aktuellen Worktrees (`git rev-parse --show-toplevel`). Vermerk im
   Workflow-State (`handoff_same: {phase, at}`) gegen Doppelstart je Phase. Bei Erfolg setzt
   der Befehl `waiting_on`, damit der Endzustand ⏳ ist (Bedingung für das Aufräumen).
   Startauftrag: Auftrag erneut anlegen (falls vorhanden), `waiting --clear`,
   `/<befehl> #N` ausführen.
3. Phasen-Befehle 10–50: bei `CONTEXT_HANDOFF=on` → `handoff --same --start`;
   `STARTED=yes|already` → Antwort mit Checkpoint und ⏳-Zeile beenden; `no` → wie bisher.

## Dependencies / Dependents

- Baut auf #694 (Tab, Aufräumen), #667 (handoff), #662 (Auto-Kette), #557 (Schwelle).
- Konsumenten: alle Projekte im Auto-Modus mit Herdr.

## Risks

- Doppelte Sitzung im selben Worktree, falls die Vorgängerin nach dem Start weiterarbeitet
  → Anweisung: Turn sofort beenden; Aufräumen schließt erst bei ⏳.
- Schleife: neue Sitzung startet groß (Grundkontext) und übergibt sofort wieder → Vermerk je
  Phase + wirksame Schwelle berücksichtigt Baseline (`baseline + growth`).
- Falscher Arbeitsordner (Haupt-Repo) → Verlust des Arbeitsstands; Test deckt cwd ab.
