---
entity_id: fix-405-424-workflow-ausgaenge
type: bugfix
created: 2026-10-12
updated: 2026-10-12
status: draft
version: "1.0"
workflow: fix-405-424-workflow-ausgaenge
tags: [hooks, workflow, state-machine, footer-gate, abandon]
test_targets:
  - tests/test_rueckspruung_405.py
  - tests/test_no_build_exit_424.py
  - tests/test_skills_sync.py
---

# Workflow-Ausgänge: Rücksprung setzt Freigaben zurück, "nichts bauen" hat einen Ausgang (#405, #424)

## Approval

- [ ] Approved

## GitHub Issue

- **#405:** Nach Rücksprung zur Spec (`workflow.py phase phase3_spec`) bleiben `spec_approved`
  und `green_approved` auf `true`. Ein erneutes `approved` wird vom `phase_listener` ignoriert.
  Umgekehrte Folge: eine alte Freigabe gilt für eine geänderte Spec.
- **#424:** Nach einer Analyse mit der Entscheidung "nichts bauen" bleibt der Workflow in
  `phase2_analyse`. Die Fußzeilenprüfung verlangt `/20-analyse` und lehnt `/99-reset` ab.
- Gemeinsames Ziel beider Punkte: Der Zustandsautomat hat für "Rücksprung" und "nichts bauen"
  keinen sauberen Weg. Beide werden in einer Änderung geschlossen.

## Purpose

Zwei Lücken im Workflow-Zustandsautomaten schließen. (1) Ein Rücksprung auf eine frühere Phase
nimmt die Freigaben mit zurück, die zu den übersprungenen Phasen gehören, sodass erneutes
`approved` wirkt und eine alte Freigabe nicht mehr für eine geänderte Spec gilt. (2) Die
PO-Entscheidung "nichts bauen" wird über einen eigenen, begründungspflichtigen Befehl festgehalten,
woraufhin die Fußzeile `/99-reset` nennt und `/99-reset` den Workflow ehrlich per `abandon`
archiviert.

## Source

- **File:** `core/hooks/workflow.py` — **Identifier:** `cmd_phase` (Rücksprung-Reset),
  neuer `cmd_no_build`, `next_step`, `_SET_FIELD_PROTECTED`, `COMMANDS`
- **File:** `core/commands/99-reset.md` (Quelle); `skills/99-reset/SKILL.md` wird daraus generiert
- Nachgestellt (#405, Wegwerf-Projekt): Workflow in `phase6_implement` mit `spec_approved=true`,
  `green_approved=true`; `phase phase3_spec` lässt beide Flags stehen; Prompt `approved` ergibt
  "Spec ist bereits freigegeben. Zustand unverändert.", Phase bleibt `phase3_spec`.
  Der Listener (`phase_listener.py`, Freigabe-Zweig) wirkt nur bei `phase3_spec` UND nicht
  `spec_approved`.

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow._validate_transition` | function | Erlaubt Rücksprünge ohne Prüfung; nach dem Reset greift bei Vorwärtswechsel `>= phase4_approved` wieder das Freigabe-Gate (`_not_approved_msg`). Keine Änderung. |
| `workflow._is_approved` | function | Liest `spec_approved` oder Phasenindex (#379). Nach dem Reset und Rücksprung unter `phase4_approved` liefert sie `False`. Keine Änderung. |
| `phase_listener.py` | hook | Freigabe wirkt in `phase3_spec` nur ohne `spec_approved`; GREEN wirkt in `phase6_implement`/`phase6b_adversary`. Keine Änderung, profitiert vom Reset. |
| `workflow.next_step` / `expected_footer_command` / `status_note` | functions | Gemeinsame Quelle für Fußzeile und Statusvermerk; eine Änderung in `next_step` wirkt auf beide. |
| `footer_gate.py` | hook | Prüft die Fußzeile gegen `expected_footer_command`. Keine Änderung. |
| `workflow.cmd_abandon` | function | Existiert bereits (Archivierung mit `status: abandoned` und Pflicht-Begründung), ist nur nirgends verlinkt. Keine Änderung. |
| `scripts/sync_skills.py` | script | Generiert `skills/99-reset/SKILL.md` aus `core/commands/99-reset.md`. |

## Scope

- **Affected Files:** `core/hooks/workflow.py`, `core/commands/99-reset.md`,
  `skills/99-reset/SKILL.md` (generiert), `tests/test_rueckspruung_405.py` (neu),
  `tests/test_no_build_exit_424.py` (neu)
- **Estimated Changes:** ca. +140 / -5 LoC (Tests ca. 90, Code ca. 35, Doku ca. 15)

## Implementation Details

### 1. #405 — Reset beim Rücksprung (`cmd_phase`)

In `cmd_phase`, nach erfolgreicher `_validate_transition` und vor dem Speichern, gilt nur bei
Rücksprung (Zielindex in `PHASES` kleiner als Index der aktuellen Phase):

```
if tgt_idx < cur_idx:
    if tgt_idx < index(phase4_approved):  data["spec_approved"]  = False
    if tgt_idx < index(phase6_implement): data["green_approved"] = False
```

Das ergibt: Ziel `phase0`–`phase3_spec` setzt beide Flags zurück; Ziel `phase4_approved` oder
`phase5_tdd_red` setzt nur `green_approved` zurück; Ziel `phase6_implement` oder später (z. B.
`phase7_validate` → `phase6_implement`) ändert nichts. Vorwärtswechsel und gleiche Phase ändern
nichts. Der Adversary-Stand (`adversary_verdict`) und das PO-Briefing bleiben unberührt: das
Briefing ist per `spec_sha256` an die Spec gebunden und wird bei geänderter Spec vom bestehenden
Briefing-Gate ohnehin als veraltet erkannt. Die Hilfsfunktion bleibt ≤ 50 LoC.

### 2. #424 — Befehl `no-build` und Ausgang über `/99-reset`

- **Neuer Befehl** `workflow.py no-build --reason "<Begründung>"` (in `COMMANDS` registriert):
  - Begründung ist Pflicht (leer oder fehlend → Fehler, Exit 1, Usage auf stderr, State unverändert).
  - Nur in `phase1_context` und `phase2_analyse` erlaubt; in jeder anderen Phase Fehler,
    Exit 1, State unverändert (später gibt es Spec und Freigabe, dort gilt der normale Abschluss).
  - Setzt das Feld `no_build_reason` im aktiven Workflow-State.
- **`_SET_FIELD_PROTECTED`** erhält `no_build_reason` mit Hinweis auf `workflow.py no-build --reason`,
  damit der Marker nicht per `set-field` gesetzt werden kann.
- **`next_step()`**: Ist `no_build_reason` gesetzt und die Phase `phase1_context` oder
  `phase2_analyse`, liefert die Funktion `/99-reset`; `expected_footer_command` und `status_note`
  ergänzen daraus wie üblich die Issue-Nummer (`/99-reset #N`). Ohne Marker bleibt der Schritt
  unverändert (`/20-analyse` in `phase2_analyse`). Der Marker wirkt nur in diesen zwei Phasen.
- **`core/commands/99-reset.md`**: Der Abschnitt "Execute Reset" erhält einen Zweig: Hat der
  Workflow `no_build_reason` oder keine `spec_file` (nie eine Spec geschrieben), wird
  `python3 .claude/hooks/workflow.py abandon --reason "<Begründung>"` aufgerufen (Begründung aus
  `no_build_reason`, sonst vom PO erfragen); andernfalls bleibt `finish`.
  `skills/99-reset/SKILL.md` entsteht ausschließlich per `python3 scripts/sync_skills.py`.
- `/99-reset` bleibt `disable-model-invocation`: den Abschluss tippt der PO. Die Fußzeile nennt
  ihn als `❗ Du: /99-reset #N`.

## Expected Behavior

- **Input #405:** `workflow.py phase <früheres Ziel>` aus einer späteren Phase; danach Prompt
  `approved` bzw. `workflow.py phase phase4_approved`.
- **Output #405:** Flags je nach Ziel zurückgesetzt (siehe Abschnitt 1); `approved` in
  `phase3_spec` (mit gültigem Briefing und ADR) führt nach `phase4_approved`; ein direkter
  `phase phase4_approved` ohne neue Freigabe wird mit `_not_approved_msg` geblockt.
- **Input #424:** `workflow.py no-build --reason "..."` in `phase1_context` oder
  `phase2_analyse`; danach `/99-reset`.
- **Output #424:** Fußzeile `/99-reset #N` wird von `footer_gate` akzeptiert (und `/20-analyse`
  stattdessen nicht mehr als erwartet); `abandon --reason` archiviert den Workflow mit
  `status: abandoned`.
- **Side effects:** Nach Rücksprung unter `phase4_approved` gilt `_is_approved` nicht mehr; Edits an
  der `spec_file` sind danach wieder erlaubt (gewollt, siehe AC-5). Neues State-Feld
  `no_build_reason`. Keine neuen Permissions, keine Info.plist-/AppStorage-Änderungen.

## Known Limitations

- **Verworfene Alternative #405: Freigabe an den Spec-Hash binden** (wie `spec_sha256` beim
  Briefing). Robuster gegen Spec-Änderungen ohne Rücksprung, aber neues Feld, neuer Vergleich in
  Listener und Gate, und der Fall "gleiche Spec, bewusst neu freigeben" bliebe offen. Mehr
  Fläche für denselben Nutzen. Die Hash-Bindung würde ADR #379 ("Freigabe bleibt bei Rücksprung
  stehen") nicht kippen, sondern ergänzen; der gewählte Reset kippt dessen Teilaussage bewusst
  für Rücksprünge.
- **Verworfene Alternative #424, Variante 1:** Die Fußzeile akzeptiert in `phase2_analyse` immer
  auch `/99-reset`. Kleiner, nimmt dem Hook aber die Aussagekraft: nach jedem Kontext-Schritt
  wäre Abbruch "korrekt".
- **Verworfene Alternative #424, Variante 2:** eigene Endphase "verworfen". Sauber, aber Eingriff in
  `PHASES`, `PHASE_NUMBERS` und alle Phasenlisten, viel zu groß für den Nutzen.
- Adversary-Verdict und Briefing werden beim Rücksprung bewusst nicht zurückgesetzt; ein
  veraltetes Briefing blockt weiterhin über das bestehende Briefing-Gate.
- `no-build` gilt nur in `phase1_context`/`phase2_analyse`. Wer nach `no-build` doch weiterarbeiten
  will, wechselt die Phase; `next_step` ignoriert den Marker dann nicht automatisch außerhalb
  dieser Phasen, er wird aber dort ohnehin nicht mehr ausgewertet.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Nach einem Rücksprung von `phase6_implement` auf `phase3_spec`, geänderter Spec und neuem
      Briefing führt `approved` über den echten `phase_listener` nach `phase4_approved` (AC-3)
- [ ] Nach `workflow.py no-build --reason "..."` nennt der Hook `/99-reset #N`, und `abandon`
      archiviert den Workflow; ohne Marker bleibt `/20-analyse` (AC-6 bis AC-10)
- [ ] `skills/99-reset/SKILL.md` ist per `sync_skills.py` erzeugt, `--check` zeigt keine Drift (AC-11)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, insbesondere
      `test_gate_coverage`, `test_status_note_325`, `test_skills_sync`)

## Acceptance Criteria

- **AC-1:** Given ein Workflow in `phase6_implement` mit `spec_approved=true` und
  `green_approved=true` / When `workflow.py phase phase3_spec` ausgeführt wird / Then sind
  `spec_approved` und `green_approved` beide `false` und die Phase ist `phase3_spec`.
  - Test: `tests/test_rueckspruung_405.py::test_rueckspruch_auf_spec_setzt_beide_flags_zurueck`

- **AC-2:** Given ein Workflow mit beiden Flags `true` / When Rücksprung auf `phase5_tdd_red` bzw.
  `phase4_approved` erfolgt / Then ist nur `green_approved` `false` und `spec_approved` bleibt
  `true`; bei Rücksprung `phase7_validate` → `phase6_implement` und bei Vorwärtswechsel bleiben
  beide Flags unverändert.
  - Test: `tests/test_rueckspruung_405.py::test_flags_je_nach_ziel_phase`

- **AC-3:** Given Rücksprung `phase6_implement` → `phase3_spec`, Spec geändert und Briefing neu
  gesetzt (`set-briefing`) / When der Prompt `approved` über `phase_listener.py` (Subprozess)
  gesendet wird / Then steht der Workflow in `phase4_approved` und `spec_approved` ist `true`.
  - Test: `tests/test_rueckspruung_405.py::test_approved_nach_rueckspruch_fuehrt_zu_phase4`

- **AC-4:** Given Rücksprung auf `phase3_spec` ohne neue Freigabe / When
  `workflow.py phase phase4_approved` ausgeführt wird / Then endet der Befehl mit Exit 1 und
  der Meldung des Freigabe-Gates (`_not_approved_msg`); die alte Freigabe lässt den Wechsel nicht
  mehr durch, die Phase bleibt `phase3_spec`.
  - Test: `tests/test_rueckspruung_405.py::test_alte_freigabe_gilt_nach_rueckspruch_nicht_mehr`

- **AC-5:** Given Rücksprung auf `phase3_spec` / When `_is_approved` ausgewertet wird (über
  `workflow.py status` bzw. direkten Funktionsaufruf) / Then ist die Freigabe nicht erteilt,
  Edits an der `spec_file` gelten wieder als vor der Freigabe.
  - Test: `tests/test_rueckspruung_405.py::test_is_approved_false_nach_rueckspruch`

- **AC-6:** Given ein Workflow in `phase2_analyse` / When `workflow.py no-build` ohne `--reason`
  oder mit leerer Begründung aufgerufen wird / Then Exit 1, Usage auf stderr und `no_build_reason`
  ist nicht gesetzt.
  - Test: `tests/test_no_build_exit_424.py::test_no_build_ohne_begruendung_schlaegt_fehl`

- **AC-7:** Given ein Workflow außerhalb von `phase1_context`/`phase2_analyse` (z. B.
  `phase3_spec`) / When `workflow.py no-build --reason "x"` aufgerufen wird / Then Exit 1 und
  `no_build_reason` ist nicht gesetzt.
  - Test: `tests/test_no_build_exit_424.py::test_no_build_ausserhalb_phase1_2_schlaegt_fehl`

- **AC-8:** Given ein Workflow `fix-424-…` in `phase2_analyse` nach `no-build --reason "..."` /
  When `expected_footer_command` ausgewertet und `footer_gate.py` (Subprozess) mit der Fußzeile
  `❗ Du: /99-reset #424` gefüttert wird / Then liefert `expected_footer_command` `/99-reset #424`,
  `footer_gate` akzeptiert die Zeile (Exit 0), und `no_build_reason` lässt sich nicht per
  `set-field` setzen.
  - Test: `tests/test_no_build_exit_424.py::test_fusszeile_nennt_99_reset_nach_no_build`

- **AC-9:** Given derselbe Workflow ohne `no-build` in `phase2_analyse` / When
  `expected_footer_command` ausgewertet wird / Then bleibt es `/20-analyse #N`, und eine Fußzeile
  mit `/99-reset` wird weiterhin von `footer_gate` abgelehnt (Exit 2).
  - Test: `tests/test_no_build_exit_424.py::test_ohne_marker_bleibt_20_analyse`

- **AC-10:** Given ein Workflow nach `no-build` / When `workflow.py abandon --reason "..."`
  ausgeführt wird / Then liegt der Workflow archiviert in `_archive/` mit `status: abandoned`,
  `abandon_reason` gesetzt und `no_build_reason` erhalten, und die aktive Workflow-Datei existiert
  nicht mehr.
  - Test: `tests/test_no_build_exit_424.py::test_abandon_archiviert_nach_no_build`

- **AC-11:** Given die geänderte Quelle `core/commands/99-reset.md` / When `sync_skills.py`
  gelaufen ist / Then enthalten `core/commands/99-reset.md` und `skills/99-reset/SKILL.md` beide den
  `abandon --reason`-Zweig (mit Verweis auf `no_build_reason` und fehlende `spec_file`), und
  `python3 scripts/sync_skills.py --check` meldet keine Drift (Exit 0).
  - Test: `tests/test_no_build_exit_424.py::test_reset_command_und_skill_enthalten_abandon_zweig`

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden), hermetisch als Subprozess-Tests nach
Vorlage `tests/test_write_log_phases_111.py` (`CLAUDE_PROJECT_DIR=tmp_path`, `.git` als Verzeichnis):

- `pytest tests/test_rueckspruung_405.py` (AC-1 bis AC-5)
- `pytest tests/test_no_build_exit_424.py` (AC-6 bis AC-11)
- Regression: `pytest tests/ -q`, insbesondere `test_gate_coverage`, `test_status_note_325`,
  `test_skills_sync` (Fixtures mit gesetztem `spec_approved` und Rücksprüngen prüfen)
- Echter Durchlauf als Nachweis: Rücksprung und `approved` sowie `no-build` → `abandon` im
  Wegwerf-Projekt mit den echten Hooks (Reproduktion aus dem Befund)

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Beide Änderungen bleiben im bestehenden Muster: Zustandsänderungen laufen über
  eigene, geprüfte Befehle (`cmd_phase`, neu `no-build`), Gate-Felder sind per `set-field`
  gesperrt, Fußzeile und Statusvermerk hängen an `next_step()`. Neue Architektur entsteht nicht.
  Die geprüften Alternativen (Hash-Bindung der Freigabe; Fußzeile akzeptiert immer `/99-reset`;
  eigene Endphase "verworfen") sind unter Known Limitations begründet verworfen. ADR #379
  ("Freigabe bleibt bei Rücksprung stehen") wird für den Rücksprung-Fall bewusst revidiert, weil
  genau dieses Stehenbleiben der Fehler aus #405 ist.

## Changelog

- 2026-10-12: Initial spec created
