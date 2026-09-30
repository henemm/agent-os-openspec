---
entity_id: fix-278-adversary-protokoll-format
type: bugfix
created: 2026-09-30
updated: 2026-09-30
status: draft
version: "1.0"
tags: [adversary, dialog-format, workflow-metrics, cli]
test_targets: ["tests/test_adversary_protokoll_format_278.py"]
---

# Adversary-Protokollformat dokumentieren und Kennzahlen tatsächlich schreiben (#278)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #278 — Sammel-Vorgang, fasst #263 (Rundenformat erratbar, kein CLI-Gerüst) und
  #247 (`adversary_findings_total`/`scope_files_changed` bleiben strukturell immer 0).

## Purpose

Das Prüfprotokoll erzwingt ein Rundenformat (`### Runde N`), das in keiner gelesenen Anweisung
steht — der Agent kann es nur erraten und tut das plausibel falsch (`## Runde N`, wie jede
andere Top-Level-Sektion). Am 2026-09-27 hat das ein inhaltlich vollständiges, VERIFIED-würdiges
Protokoll grundlos blockiert. Gleichzeitig sind zwei Kennzahlen (`adversary_findings_total`,
`scope_files_changed`) strukturell tot: Es gibt keinen Code, der sie jemals schreibt, obwohl die
Daten (Findings im Protokoll, Änderungsmenge über `phase8_code_files()`) längst vorliegen. Diese
Spec gibt dem Format eine maschinenlesbare Quelle (`scaffold`-CLI statt Raten) und koppelt den
Kennzahlen-Rückschrieb an den bereits verpflichtenden `stamp`-Schritt — dasselbe Muster, mit dem
`adversary_verdict` schon zuverlässig funktioniert.

## Source

- **File:** `core/hooks/adversary_dialog.py` — **Identifier:** neu `scaffold_dialog_artifact()`,
  `_count_findings()`, `_persist_adversary_metrics()`; geändert `validate_dialog_artifact_ex()`
  (Rundenregex), `stamp_dialog_artifact()` (ruft `_persist_adversary_metrics()`), `main()`
  (neuer Subcommand `scaffold`)
- **File:** `core/hooks/workflow.py` — **Identifier:** `cmd_write_log()`
- **File:** `core/agents/implementation-validator.md` — verweist auf `scaffold` statt das
  Rundenformat nur in Prosa zu nennen
- **File:** `core/commands/50-implement.md` — Abschnitt 8, verweist auf `scaffold`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `parse_spec_expected_behavior()` / `create_checklist()` | function | Bestehende Spec-Parser, von `scaffold_dialog_artifact()` wiederverwendet für den Checklisten-Teil des Gerüsts |
| `MIN_ROUNDS` | constant | Bestimmt, wie viele `### Runde N`-Platzhalter das Gerüst enthält |
| `phase8_code_files(wf)` | function | Bestehende Phase-8-Änderungsmenge (#259), von `_persist_adversary_metrics()` wiederverwendet für `affected_files` — kein neuer Git-Diff-Code |
| `workflow.py set-field` / `set-affected-files --replace` | CLI | Schreibweg in den Workflow-State, per `subprocess` aufgerufen — exakt das Muster aus `qa_gate.py::_set_verdict()` |
| `_strip_fenced_code_blocks()` | function | Bestehende Fence-Bereinigung, von `_count_findings()` wiederverwendet — ein in einem Codeblock zitiertes `ID: F001` darf nicht mitgezählt werden |

## Scope

- **Affected Files:**
  - Code: `core/hooks/adversary_dialog.py`, `core/hooks/workflow.py`
  - Doku: `core/agents/implementation-validator.md`, `core/commands/50-implement.md` (Quelle —
    `skills/50-implement/SKILL.md` wird per `python3 scripts/sync_skills.py` regeneriert, nicht
    von Hand editiert), `CHANGELOG.md` (Abschnitt `[Unreleased]`)
  - Tests: `tests/test_adversary_protokoll_format_278.py` (neu)
- **Estimated Changes:** Produktivcode ~+120/−15 LoC (Scaffold-Funktion ~30, Findings-Zähler +
  Metriken-Persistierung ~55, Regex-Lockerung ~5, `cmd_write_log`-Unterscheidung ~10, CLI-Wiring
  ~10, Doku ~30 Zeilen)

## Implementation Details

**1. Rundenregex H2-und-H3-tolerant.** `validate_dialog_artifact_ex()` zählt Runden heute strikt
als `^### Runde \d+`. Lockerung auf `^#{2,3} Runde \d+` — akzeptiert zusätzlich `## Runde N`
(der real aufgetretene Fall), ohne bestehende `### Runde N`-Artefakte zu invalidieren.

**2. `scaffold_dialog_artifact(workflow_name, spec_path) -> str`.** Neue Funktion, die ein
formal valides Gerüst rendert: Header (Name, Spec-Pfad, Datum), `## Checkliste` (alle
Expected-Behavior-/AC-N-Punkte aus der Spec als offene `- [ ]`-Zeilen, via
`parse_spec_expected_behavior()` + `create_checklist()`), `## Dialog` mit `MIN_ROUNDS`
Platzhalter-Rundenköpfen (`### Runde 1` … `### Runde N`, je mit leeren `**Adversary:**` /
`**Implementierer:**`-Zeilen) und einer leeren `## Verdict`-Sektion. Das Gerüst ist die einzige
Quelle für das Format — Prosa-Anweisungen beschreiben es nicht mehr, sie verweisen darauf.

**3. CLI-Subcommand `scaffold`.** `python3 adversary_dialog.py scaffold <workflow-name>
<spec-path>` gibt das Gerüst auf stdout aus (Muster wie `parse`). Der Aufrufer leitet es in die
Artefakt-Datei um:
```bash
python3 .claude/hooks/adversary_dialog.py scaffold <workflow-name> <spec-pfad> \
    > docs/artifacts/<workflow-name>/adversary-dialog.md
```

**4. `_count_findings(scan) -> int`.** Zählt eindeutige Finding-IDs (`^\s*ID:\s*(F\d+)\b`,
dedupliziert) im fence-bereinigten Text — dasselbe `ID: F\d+`-Format, das
`implementation-validator.md` für jedes Finding bereits vorschreibt.

**5. `_persist_adversary_metrics(scan) -> str`.** Neue Funktion, aufgerufen am Ende von
`stamp_dialog_artifact()` (NACH dem Schreiben des Hash-Blocks, damit ein Fehler hier den
bereits erfolgreichen, sicherheitskritischen Teil nicht rückgängig macht):
1. Ermittelt den aktiven Workflow (`resolve_active_workflow()`) und lädt seinen State.
2. Zählt Findings via `_count_findings(scan)` → `workflow.py set-field adversary_findings_total
   <n>` (Subprocess, wie `qa_gate.py::_set_verdict()`).
3. Ermittelt die Änderungsmenge via `phase8_code_files(wf)` (bestehend, #259) → `workflow.py
   set-affected-files --replace <dateien...>`.
4. Best-effort: kein aktiver Workflow, nicht lesbarer State oder ein fehlschlagender
   Subprocess-Aufruf geben eine Warnung in der Rückgabe-Message zurück, lassen `stamp_dialog_
   artifact()` aber weiterhin `True` (Erfolg) zurückgeben — der Hash-Block ist bereits
   geschrieben, das ist der sicherheitskritische Teil (Regel aus #77/#253: ein Formproblem an
   dieser Stelle darf kein bereits erbrachtes Ergebnis entwerten).

**6. `cmd_write_log()` unterscheidet „nie gesetzt" von „explizit 0".** Bisher: `data.get
('adversary_findings_total', 0)` — ein Feld, das nie geschrieben wurde, sieht identisch aus wie
ein Adversary-Lauf, der 0 Findings ergab. Neu: Ist der Schlüssel `adversary_findings_total` im
State-Dict nicht vorhanden (Schritt 5 lief nie), schreibt das Execution-Log `unbekannt` für
sowohl `adversary_findings_total` als auch `scope_files_changed` — beide Felder werden
gemeinsam durch `_persist_adversary_metrics()` gesetzt, ihre gemeinsame Abwesenheit ist also ein
verlässliches Signal für „Schritt 5 lief nie", unabhängig vom (immer schon vorhandenen)
Leer-Vorgabewert `[]` von `affected_files`. Ist der Schlüssel vorhanden, zeigt das Log den
tatsächlichen Wert (inklusive `0`).

## Expected Behavior

- **Input:** Ein Dialog-Artefakt (Markdown), das aus `scaffold` hervorgegangen ist oder das
  bisherige `### Runde N`-Format nutzt; der aktive Workflow-State.
- **Output:** `scaffold` → valides Gerüst auf stdout. `validate`/`stamp` → wie bisher, zusätzlich
  schreibt `stamp` die beiden Kennzahlen in den State. `write-log` → `unbekannt` statt `0`, wenn
  die Kennzahlen nie geschrieben wurden.
- **Side effects:** `stamp_dialog_artifact()` schreibt zusätzlich zum Hash-Block
  `adversary_findings_total` und `affected_files` in die aktive Workflow-JSON.

## Error Handling

- Kein aktiver Workflow beim `stamp`-Aufruf → Hash-Block wird trotzdem geschrieben (Erfolg),
  Rückgabemeldung nennt zusätzlich, dass die Kennzahlen nicht persistiert werden konnten.
- `set-field`/`set-affected-files`-Subprocess schlägt fehl (z. B. State-Datei nicht schreibbar)
  → dieselbe Best-effort-Regel, `stamp` bleibt insgesamt erfolgreich.
- Ein Dialog-Artefakt mit 0 dokumentierten Runden (weder H2 noch H3) bleibt ein
  `failure_kind='format'`-Fehler — kein `content`/BROKEN-Verdict landet im State (Invariante aus
  #77 bleibt unverändert).

## Known Limitations

- `_persist_adversary_metrics()` schreibt `affected_files` mit den realpath-absoluten Pfaden aus
  `phase8_code_files()`. `edit_gate.py::_find_workflow_for_file()` vergleicht dabei bereits heute
  per Suffix-Match (`af.endswith("/" + rel)`), nicht per Gleichheit — verträgt sich also mit
  absoluten Pfaden ohne Änderung an `edit_gate.py`. Kein neuer Code hier, nur als Kompatibilitäts-
  Hinweis vermerkt.
- Ruft ein PO/Agent `set-affected-files` manuell VOR dem ersten `stamp`, bevor Schritt 5 je lief,
  bleibt `adversary_findings_total` trotzdem abwesend und das Execution-Log zeigt für BEIDE
  Felder `unbekannt`, obwohl `affected_files` bereits manuell befüllt ist. Seltener Randfall
  (kein dokumentierter Anwendungsfall für manuelles `set-affected-files` vor dem Dialog); wird
  bewusst nicht gesondert behandelt.
- `scaffold` erzeugt ein FORMAL valides, aber inhaltlich leeres Gerüst (Checkliste offen, keine
  Runden-Inhalte, kein Verdict) — es besteht `validate_dialog_artifact_ex()` nicht, bevor der
  Adversary-Agent es ausgefüllt hat. Das ist beabsichtigt: `scaffold` liefert das Format, nicht
  den Beweis.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Der Live-Fall vom 2026-09-27 (`## Runde 1` / `## Runde 2`) wird von der Formprüfung
      akzeptiert — nachgewiesen an einem Regressionstest mit genau diesem Artefakt-Zuschnitt
- [ ] Ein `stamp`-Lauf auf einem Artefakt mit zwei eindeutigen `ID: F00N`-Findings hinterlässt
      `adversary_findings_total == 2` im Workflow-State, ohne manuellen Zusatzbefehl
- [ ] `CHANGELOG.md` hat einen `[Unreleased]`-Eintrag für #278
- [ ] `python3 scripts/sync_skills.py --check` meldet keine Drift (SKILL.md nachgezogen)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, insbesondere
      `tests/test_adversary_coverage_gate_259.py` und `tests/test_adversary_dialog_verdict.py`)

## Acceptance Criteria

- **AC-1:** Given eine Spec mit Expected-Behavior- oder AC-N-Punkten und ein Workflow-Name /
  When `adversary_dialog.py scaffold <workflow> <spec-pfad>` läuft / Then gibt es auf stdout ein
  Markdown-Gerüst mit `## Checkliste` (jeder Spec-Punkt als offene `- [ ]`-Zeile), `## Dialog`
  mit genau `MIN_ROUNDS` `### Runde N`-Überschriften und einer `## Verdict`-Sektion aus,
  Exit-Code 0.
  - Test: `test_adversary_protokoll_format_278.py::test_scaffold_outputs_checklist_and_rounds`

- **AC-2:** Given ein Dialog-Artefakt mit `## Runde 1` und `## Runde 2` (H2 statt H3, sonst
  vollständig: Checkliste abgehakt, `VERDICT: VERIFIED`) / When `adversary_dialog.py validate
  <pfad>` läuft / Then Exit 0 — der Live-Fall vom 2026-09-27 wird nicht mehr grundlos
  abgewiesen.
  - Test: `test_h2_rounds_accepted_reproduces_2026_09_27_case`

- **AC-3:** Given dasselbe Artefakt, aber mit dem bisherigen `### Runde N`-Format (H3) / When
  dieselbe Prüfung läuft / Then bleibt sie unverändert gültig — keine
  Rückwärtskompatibilitäts-Regression für historisch VERIFIED-abgenommene Artefakte.
  - Test: `test_h3_rounds_still_accepted_no_regression`

- **AC-4:** Given ein Dialog-Artefakt mit `Code reference:`-Zeilen und zwei Findings mit den
  IDs `F001` und `F002` (eine davon als Duplikat innerhalb eines Fix-Loop-Zitats in einem
  Fenced-Code-Block) in einem aktiven Workflow / When `adversary_dialog.py stamp <pfad>` läuft /
  Then steht im Workflow-State danach `adversary_findings_total == 2` (das zitierte Duplikat im
  Codeblock zählt nicht mit) — ohne manuellen Zusatzbefehl.
  - Test: `test_stamp_writes_findings_total_excludes_fenced_duplicates`

- **AC-5:** Given denselben Ablauf in einem Git-Arbeitsbaum mit geänderten Dateien / When
  `stamp` läuft / Then ist `affected_files` im Workflow-State mit exakt der Menge aus
  `phase8_code_files()` befüllt (gleicher Inhalt wie `adversary_dialog.py required-files`).
  - Test: `test_stamp_writes_affected_files_matches_required_files`

- **AC-6:** Given einen Workflow, bei dem `stamp` noch nie gelaufen ist (`adversary_findings_
  total` fehlt im State) / When `workflow.py write-log` läuft / Then enthält die geschriebene
  Log-Datei `adversary_findings_total: unbekannt` und `scope_files_changed: unbekannt`.
  - Test: `test_write_log_unbekannt_when_metrics_never_persisted`

- **AC-7:** Given denselben Workflow, nachdem `stamp` einmal gelaufen ist und dabei 0 Findings
  gezählt hat / When `workflow.py write-log` läuft / Then zeigt die Log-Datei
  `adversary_findings_total: 0` (nicht `unbekannt`) — echtes Ergebnis „Adversary lief, fand
  nichts" bleibt von „lief nie" unterscheidbar.
  - Test: `test_write_log_shows_real_zero_after_metrics_persisted`

- **AC-8:** Given ein Dialog-Artefakt mit 0 dokumentierten Runden (weder `##` noch `### Runde
  N`) / When `validate_dialog_artifact_ex()` läuft / Then ist `failure_kind == 'format'` (nicht
  `'content'`) — Regressionsschutz für die Reihenfolge aus #77/#253.
  - Test: `test_zero_rounds_stays_format_failure_not_content`

- **AC-9:** Given `core/agents/implementation-validator.md` und `core/commands/50-implement.md`
  / When man die Dateien liest / Then referenzieren beide den `scaffold`-Befehl; die
  `required-files`-Erwähnungen in den von Issue #259 geprüften Abschnitten (`#### 8c.` in
  50-implement.md, `### Step 3` und `## Step 6` in implementation-validator.md) bleiben
  unverändert vorhanden.
  - Test: `test_docs_reference_scaffold_and_keep_required_files_mentions` (plus Regressionslauf
    von `tests/test_adversary_coverage_gate_259.py::test_ac16_docs_describe_coverage_gate`)

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `python3 -m pytest tests/test_adversary_protokoll_format_278.py -q` (AC-1 bis AC-9)
- Regressionslauf: `python3 -m pytest tests/ -q` (insbesondere
  `tests/test_adversary_coverage_gate_259.py`, `tests/test_adversary_dialog_verdict.py`,
  `tests/test_adversary_dialog_hash_binding_131.py`, `tests/test_adversary_evidence_gate_253.py`)
- Drift-Check: `python3 scripts/sync_skills.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Keine neue Architektur — zwei bestehende Muster werden konsequent
  weiterverwendet:
  1. **Format an einer Quelle statt in Prosa.** `render_dialog_artifact()` existierte bereits
     und erzeugt korrektes Format, hatte aber keinen CLI-Zugang. `scaffold` macht diese Quelle
     erreichbar, statt eine zweite, unabhängige Formatbeschreibung in zwei `.md`-Dateien zu
     pflegen (die schon einmal auseinandergelaufen sind — das war die Root Cause von #263).
     *Verworfene Alternative:* Der Agent nennt die Rundenzahl einmalig explizit (`Runden: 2`)
     statt Kopfzeilen zu zählen — macht das Gerüst formlos, gibt aber die nachlesbare
     Dialog-Struktur auf, die MIN_ROUNDS als Beleg gegen Early-Agreement voraussetzt. Nicht
     empfohlen (siehe Kontext-Dokument, Abschnitt „Technical Approach").
  2. **Kennzahlen an einen bereits verpflichtenden Schritt koppeln, nicht an einen neuen
     optionalen.** `adversary_verdict` funktioniert zuverlässig, weil `qa_gate.py` es an die
     ohnehin verpflichtende Checklisten-Validierung koppelt. Ein separater `count-findings`-Befehl
     hätte exakt das heutige Fehlermuster reproduziert (ein leicht vergessbarer Zusatzschritt).
     *Verworfene Alternative:* eigener CLI-Schritt `count-findings`, den der Agent zusätzlich zu
     `stamp` aufrufen müsste — verworfen aus demselben Grund.

## Changelog

- 2026-09-30: Initial spec created
