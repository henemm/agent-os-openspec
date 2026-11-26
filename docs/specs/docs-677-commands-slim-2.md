---
entity_id: docs-677-commands-slim-2
type: refactor
created: 2026-11-26
updated: 2026-11-26
status: draft
version: "1.0"
workflow: docs-677-commands-slim-2
tags: [token, befehle, docs, epic-649]
---

# Befehlstexte verschlanken, Schnitt 2 (Issue #677)

## Approval

- [ ] Approved

## Purpose

Der Befehlstext einer Phase wird bei jedem Aufruf vollständig geladen. Schnitt 2 kürzt `30-write-spec.md` (14 544 Bytes), `00-intake.md` (12 568 Bytes) und `80-workflow.md` (10 931 Bytes), zusammen 38 043 Bytes, auf höchstens 22 825 Bytes (−40 %). Begründungen, Referenzteile und Sonderfall-Erläuterungen wandern wörtlich nach `docs/befehle/<befehl>.md`. Das Gesamtziel über alle Befehlstexte schließt #678 ab; #679 übernimmt den Marker-Block und die Hook-Hinweise.

## Source

- **File:** `core/commands/30-write-spec.md`, `core/commands/00-intake.md`, `core/commands/80-workflow.md`, neu `docs/befehle/30-write-spec.md`, `docs/befehle/00-intake.md`, `docs/befehle/80-workflow.md`
- **Identifier:** Abschnitte der drei Befehlstexte

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `scripts/sync_skills.py` | script | erzeugt `skills/*/SKILL.md` aus `core/commands`; `--check` weist Drift nach |
| `scripts/release_check.py` | script | prüft Skill-Drift und Versionsstände |
| Pin-Tests 30-write-spec (u. a. `test_ampel_kalibrierung_485`, `test_clear_checkpoint_blocks`, `test_cloud_agents_577`, `test_config_additiv_622`, `test_context_stop_658`, `test_kontext_haushalt`, `test_auto_chain_flat_662`, `test_kette_auto_clear_489`, `test_foreground_checkers_83`, `test_spec_ampel_470`, `test_setup_alias_sync_150`, `test_skills_sync`, `test_wakeup_blocks`) | test | pinnen Wortlaute in 30-write-spec; müssen unverändert grün bleiben |
| Pin-Tests 00-intake (u. a. `test_intake_bugs_250a1`, `test_intake_two_tracks_254`, `test_adversary_risk_342`, `test_autonomy_kette_472`, `test_auftrag_551`, `test_spur_591`, `test_session_register_docs_120_121`, `test_issue_claim_461`, `test_plan_kopf_612`, `test_zeitschaetzung_620`) | test | pinnen Wortlaute in 00-intake |
| Pin-Tests 80-workflow (`test_handoff_667`, `test_handoff_668`, `test_issue_claim_461`, `test_skills_sync`) | test | pinnen Wortlaute in 80-workflow |
| Globale Pin-Tests (`test_endzustand_550`, `test_guard_quote_vs_write_276`, `test_no_tmp_paths`, `test_vorlagen_klartext_597`, `test_agent_dispatch_drift_279`) | test | gelten für alle Befehle |
| `core/hooks/workflow.py` (Zeile 2787), `scripts/ci_spec_gate.py` (Zeile 275) | hook/script | verweisen auf „/30-write-spec Step 3b“; die Überschrift bleibt |
| `tests/test_commands_slim_674.py` | test | Größenwächter aus Schnitt 1; wird angepasst |
| Epic #649, Vorgänger #674, Folge-Issues #678, #679 | issue | Gesamtziel und Marker-Block |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/commands/30-write-spec.md | MODIFY | auf höchstens 8 704 Bytes kürzen, Verweis-Satz auf `docs/befehle/30-write-spec.md`; Überschrift „Step 3b“ bleibt |
| core/commands/00-intake.md | MODIFY | auf höchstens 8 192 Bytes kürzen, Verweis-Satz auf `docs/befehle/00-intake.md`; Überschriften „### 1a.“ und Bug-Abschnitt vor „### 2. Score präsentieren“ bleiben |
| core/commands/80-workflow.md | MODIFY | auf höchstens 5 632 Bytes kürzen, Verweis-Satz auf `docs/befehle/80-workflow.md` |
| docs/befehle/30-write-spec.md | CREATE | verschobene Begründungen und Erläuterungen, wörtlich, mindestens 3 `##`-Abschnitte |
| docs/befehle/00-intake.md | CREATE | verschobene Erläuterungen, wörtlich, mindestens 3 `##`-Abschnitte |
| docs/befehle/80-workflow.md | CREATE | verschobener Referenzteil, wörtlich, mindestens 3 `##`-Abschnitte |
| tests/test_commands_slim_674.py | MODIFY | Budgets der drei Dateien senken, `LINKED` um 00-intake, 30-write-spec, 80-workflow erweitern |
| tests/test_commands_slim_677.py | CREATE | je ein Budget-Test pro Datei und ein Test für die Summe |
| skills/00-intake/SKILL.md, skills/30-write-spec/SKILL.md, skills/80-workflow/SKILL.md | MODIFY | per `sync_skills.py` regeneriert |
| CHANGELOG.md, .claude-plugin/plugin.json, CLAUDE.md, README.md, Versionsmarker | MODIFY | Version 4.25.6 (Marker per sync) |

### Estimated Changes

- Files: 3 Befehle, 3 neue Doku, 1 neuer und 1 angepasster Test, 3 Generate, Versionsdateien
- LoC: Befehle ca. -230/+50, Doku ca. +230, Tests ca. +60 (unter 250 Produktivzeilen)
- Risk Level: LOW (nur Anweisungstext, Doku, Tests; kein Hook-Code)

## Implementation Details

Abschnittsweise Vorgehen in den drei Befehlen. Es bleiben der Ablauf, alle Agent-Aufrufe, `workflow.py`-Befehle, Ausgabe-Blöcke und jeder von bestehenden Tests gepinnte Wortlaut. Reine Begründungen, Erläuterungen und Referenzteile wandern wörtlich in gleichnamige Abschnitte von `docs/befehle/<befehl>.md`. Im Befehl steht dafür ein Satz: „Hintergrund: `docs/befehle/<befehl>.md` (Plugin-Ordner)“.

- **30-write-spec (≤ 8 704 Bytes):** Step 0 auf Kernbefehle, „Hängende Subagenten“, Erläuterung zu „Agent-Typen und Fallback“, Begründung zu Step 3b, Erläuterung zu Step 4b, Erläuterung der Freigabe-Ausgabe und Details zu „After Approval“ ziehen um. Es bleiben: Überschrift „Step 3b“, Agent-Aufrufe samt Fallback-Zeile (ohne `model=`), Checkpoint-Gerüst, Kontext-Haushalt-Absatz, Planungsabsatz, AskUserQuestion-Verbot, Briefing-Marker.
- **00-intake (≤ 8 192 Bytes):** Erläuterungen zu Scoring und Tiefe, Details zu 1a (Auftrag-Besitz, ALTAUFTRAG), Details der Issue-Kurzfassung in 1c, Registrierung am Issue, Zeitschätzungs-Beispiele, Modell-Empfehlung, Stufen-Tabelle und Mini-Spec-Vorlage ziehen um. Alle gepinnten Sätze und die Reihenfolge der Überschriften bleiben; die erste Überschrift mit „Bug“ steht weiterhin vor „### 2. Score präsentieren“ (es gibt zwei „### 1c.“-Überschriften).
- **80-workflow (≤ 5 632 Bytes):** Der Referenzteil (Workflow Phases, State Architecture, Code Modification Rules, Audit Trail, Execution Log, Automatic Phase Detection, QA Gate, Migration, Retro-Beispiele) zieht um. Befehlsübersicht, handoff, queue und Wiedereinstieg bleiben.

Größenwächter: In `tests/test_commands_slim_674.py` erhalten die drei Dateien die neuen Budgets, `LINKED` wird um die drei Befehle erweitert. `tests/test_commands_slim_677.py` prüft je Datei das Budget und die Summe von höchstens 22 825 Bytes.

Messung: Bytes und geschätzte Token (Bytes/3,5) der geladenen Skill-Texte vorher/nachher je Befehl; `CONTEXT_TOKENS` dieser Sitzung wird in Epic #649 festgehalten.

Invarianten: kein Hook- und kein Gate-Code geändert, keine Änderung an der Gate-Konfiguration, kein Schritt braucht einen Override (autarker Auftrag), alle Pin-Tests unverändert grün ohne `skip`/`xfail`.

## Expected Behavior

- **Input:** Aufruf von `/00-intake`, `/30-write-spec` oder `/80-workflow`
- **Output:** gleicher Ablauf und gleiche Pflichtschritte wie bisher, aus einem kürzeren Text (30-write-spec ≤ 8 704, 00-intake ≤ 8 192, 80-workflow ≤ 5 632 Bytes; zusammen ≤ 22 825 Bytes)
- **Side effects:** geringere Last beim Laden der drei Befehle; Hintergrundwissen vollständig in `docs/befehle/`

## Known Limitations

- Der 00-intake-Text enthält viel gepinnten Wortlaut; die Kürzung gelingt nur, weil Erläuterungen, Tabellen und Vorlagen umziehen.
- Die Wirkung tritt erst beim Laden des jeweiligen Befehls ein.
- `docs/befehle/` liegt im Plugin-Ordner, nicht im Konsumentenprojekt; der Hintergrund ist zur Ausführung nicht nötig.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] 30-write-spec.md ≤ 8 704, 00-intake.md ≤ 8 192, 80-workflow.md ≤ 5 632 Bytes, Summe ≤ 22 825 Bytes, verschobener Text vollständig in `docs/befehle/`
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, `skills/` ohne Drift)
- [ ] CHANGELOG `[4.25.6]`, Version 4.25.6 überall, veröffentlicht
- [ ] Messung vorher/nachher (Bytes, geschätzte Token je Befehl) und `CONTEXT_TOKENS` in Epic #649 festgehalten

## Acceptance Criteria

- **AC-1:** Given das Repo nach der Änderung / When die Größe von `core/commands/30-write-spec.md` gemessen wird / Then beträgt sie höchstens 8 704 Bytes
  - Test: tests/test_commands_slim_677.py::test_write_spec_within_budget

- **AC-2:** Given das Repo nach der Änderung / When die Größe von `core/commands/00-intake.md` gemessen wird / Then beträgt sie höchstens 8 192 Bytes
  - Test: tests/test_commands_slim_677.py::test_intake_within_budget

- **AC-3:** Given das Repo nach der Änderung / When die Größe von `core/commands/80-workflow.md` gemessen wird / Then beträgt sie höchstens 5 632 Bytes
  - Test: tests/test_commands_slim_677.py::test_workflow_within_budget

- **AC-4:** Given die drei Befehlstexte / When ihre Summe gemessen wird / Then beträgt sie höchstens 22 825 Bytes (−40 % gegenüber 38 043 Bytes)
  - Test: tests/test_commands_slim_677.py::test_total_within_budget

- **AC-5:** Given alle Dateien in `core/commands/` / When die Budget-Tabelle des Größenwächters geprüft wird / Then hat jeder Befehlstext ein Budget und hält es ein
  - Test: tests/test_commands_slim_674.py::test_every_command_has_budget

- **AC-6:** Given `00-intake.md`, `30-write-spec.md` und `80-workflow.md` / When nach dem Verweis gesucht wird / Then nennen sie ihre Datei `docs/befehle/<befehl>.md`, und diese existiert mit mindestens 3 `##`-Abschnitten
  - Test: tests/test_commands_slim_674.py::test_commands_link_background_docs

- **AC-7:** Given die drei zugehörigen `skills/*/SKILL.md` / When `sync_skills.py --check` läuft und der Text geprüft wird / Then gibt es keine Drift, und alle Skills tragen den Verweis ebenfalls
  - Test: tests/test_commands_slim_674.py::test_skills_carry_link

- **AC-8:** Given die Überschrift „Step 3b“ in `30-write-spec.md` sowie „### 1a.“ und der Bug-Abschnitt vor „### 2. Score präsentieren“ in `00-intake.md` / When die Befehlstexte geprüft werden / Then sind sie unverändert vorhanden
  - Test: tests/test_commands_slim_677.py::test_anchor_headings_kept

- **AC-9:** Given die bestehenden Pin-Tests auf Wortlaute in 00/30/80 / When die Gesamtsuite läuft / Then bleibt sie grün, ohne `skip`/`xfail`
  - Test: tests/ (Gesamtsuite)

## Test Plan

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN die gekürzten Befehle fehlen noch WHEN `pytest tests/test_commands_slim_677.py` läuft THEN scheitern die drei Budget-Tests und der Summentest (RED), nach dem Kürzen sind sie grün
- [ ] Test 2: GIVEN die erweiterte `LINKED`-Liste WHEN `tests/test_commands_slim_674.py` läuft THEN scheitert der Verweis-Test, bis Verweis-Satz und `docs/befehle/<befehl>.md` (mind. 3 `##`) vorhanden sind
- [ ] Test 3: GIVEN die gekürzten Befehle WHEN die Pin-Tests aus der Dependencies-Tabelle einzeln und danach `pytest tests/` laufen THEN sind alle grün ohne `skip`/`xfail`
- [ ] Test 4: GIVEN die regenerierten Skills WHEN `python3 scripts/sync_skills.py --check` läuft THEN gibt es keine Drift

Tests laufen im venv mit `pytest` und `pyyaml`. Messung: Bytes und geschätzte Token (Bytes/3,5) je Befehl vorher/nachher; Ergebnis und `CONTEXT_TOKENS` dieser Sitzung als Kommentar an Epic #649.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Reine Umverteilung von Anweisungstext und Dokumentation; keine neue Entscheidungsfläche, Vorgehen wie bei #580 und #674.
- **Alternative A, Kürzen ohne Verschieben:** verworfen, das Wissen ginge verloren.
- **Alternative B, alles in einem PR mit #674 und #678:** verworfen, die Umfangsgrenze (250 Zeilen je Workflow) lässt das nicht zu.
- **Alternative C, gepinnte Wortlaute umschreiben und Tests anpassen:** verworfen, Risiko für das Gate- und Auslieferungsverhalten.

## Changelog

- 2026-11-26: Erstfassung
