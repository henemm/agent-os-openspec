---
entity_id: docs-678-commands-slim-3
type: refactor
created: 2026-11-26
updated: 2026-11-26
status: draft
version: "1.0"
workflow: docs-678-commands-slim-3
tags: [token, befehle, docs, epic-649]
---

# Befehlstexte verschlanken, Schnitt 3 (Issue #678)

## Approval

- [ ] Approved

## Purpose

Der Befehlstext einer Phase wird bei jedem Aufruf vollständig geladen. Schnitt 3 kürzt `10-context`, `20-analyse`, `40-tdd-red`, `70-deploy` und die kleinen Befehle `01-feature`, `81-add-artifact`, `82-test`, `83-user-story`, `90-retro`, `99-reset`. Weil deren gepinnte Pflichtblöcke (Checkpoint, Kontext-Absatz, Kettensätze, Wiedereinstieg) allein nicht genug Spielraum lassen, bekommt `60-validate.md` (größter Befehl) einen zweiten Durchgang. Danach gilt das Gesamtziel aus #674: `core/commands/*.md` zusammen höchstens 83 000 Bytes (Stand nach #677: 108 646 Bytes; −40 % gegenüber 138 946 Bytes wären 83 368). Begründungen, Vorlagen, Tabellen und Sonderfall-Erläuterungen wandern wörtlich nach `docs/befehle/<befehl>.md`.

## Source

- **File:** die elf Befehlstexte in `core/commands/`, neue bzw. erweiterte `docs/befehle/<befehl>.md`
- **Identifier:** Abschnitte der Befehlstexte

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `scripts/sync_skills.py`, `setup.py . --refresh-aliases` | script | erzeugen `skills/*/SKILL.md` und die Vollkopien `.claude/commands/{70,81,99}` |
| Pin-Tests (Liste in `docs/context/docs-678-commands-slim-3.md`, u. a. `test_clear_checkpoint_blocks`, `test_context_stop_658`, `test_kontext_haushalt`, `test_auto_chain_flat_662`, `test_kette_auto_clear_489`, `test_autonomy_kette_472`, `test_skills_sync`, `test_guard_quote_vs_write_276`, `test_cloud_agents_577`, `test_wakeup_blocks`, `test_skill_stop_instruction`, `test_issue_number_513`, `test_befehlsform_context_titel_499`, `test_issue_claim_461`, `test_deploy_config_81`, `test_app_config_yaml_372`, `test_plan_deploy_status_510`, `test_nachpruefung_broken_561`, `test_endzustand_550`, `test_nacharbeit_555`, `test_auftrag_551`, `test_handoff_667`, `test_handoff_668`, `test_testausgabe_erkennung_275`, `test_no_build_exit_424`, `test_skill_path_resolution`, `test_vorlagen_klartext_597`, `test_agent_dispatch_drift_279`, Alias-Tests; für 60-validate alle bisherigen Pins) | test | pinnen Wortlaute; bleiben unverändert grün |
| `core/commands/00-intake.md`, `docs/befehle/00-intake.md` | doc | verweisen auf „/20-analyse Step 2b“ — Überschrift bleibt |
| `docs/befehle/60-validate.md` | doc | verweist auf „/70-deploy Step 4, Teil b“ — `## Step 4` und „b) Fachlicher Befund“ bleiben |
| `core/hooks/session_singleton_guard.py` | hook | erlaubt `session_singleton_guard.py sync-main` aus 70-deploy — Befehl bleibt |
| `tests/test_commands_slim_674.py` | test | Größenwächter; Budgets sinken, `LINKED` wächst |
| Epic #649, #674, #677, Folge #679 | issue | Gesamtziel; #679 übernimmt Marker-Block und Hook-Hinweise |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/commands/10-context.md | MODIFY | ≤ 5 120 B |
| core/commands/20-analyse.md | MODIFY | ≤ 6 656 B, `### Step 2b` bleibt |
| core/commands/40-tdd-red.md | MODIFY | ≤ 5 632 B, `## Common Mistakes` bleibt |
| core/commands/70-deploy.md | MODIFY | ≤ 6 144 B, `## Step 4` + „b) Fachlicher Befund“ bleiben |
| core/commands/60-validate.md | MODIFY | ≤ 16 384 B (zweiter Durchgang) |
| core/commands/01-feature.md, 81-add-artifact.md, 82-test.md, 83-user-story.md, 90-retro.md, 99-reset.md | MODIFY | je ≤ 2 048 B |
| docs/befehle/10-context.md, 20-analyse.md, 40-tdd-red.md, 70-deploy.md, 81-add-artifact.md, 83-user-story.md | CREATE | verschobener Text wörtlich, je ≥ 3 `##`-Abschnitte |
| docs/befehle/60-validate.md | MODIFY | weiterer verschobener Text |
| tests/test_commands_slim_674.py | MODIFY | neue Budgets, `LINKED` um 10, 20, 40, 70, 81, 83 erweitert |
| tests/test_commands_slim_678.py | CREATE | Budget je Befehl dieses Schnitts, Gesamtsumme ≤ 83 000 B, Ankerüberschriften |
| skills/*/SKILL.md, .claude/commands/70-deploy.md, 81-add-artifact.md, 99-reset.md | MODIFY | regeneriert |
| CHANGELOG.md, .claude-plugin/plugin.json, CLAUDE.md, README.md, Versionsmarker | MODIFY | Version 4.26.2 |

### Estimated Changes

- Files: 11 Befehle, 6 neue + 1 erweiterte Doku, 1 neuer + 1 angepasster Test, Generate, Versionsdateien
- LoC: Befehle ca. −600/+150, Doku ca. +450 (verschobener Text), Tests ca. +70
- Risk Level: LOW (nur Anweisungstext, Doku, Tests; kein Hook-Code)

## Implementation Details

Wie #674/#677: Es bleiben der Ablauf, alle Agent-Aufrufe, `workflow.py`-Befehle, Ausgabe-Blöcke und jeder gepinnte Wortlaut. Begründungen, Vorlagen, Tabellen und Erläuterungen wandern wörtlich in Abschnitte von `docs/befehle/<befehl>.md`; im Befehl steht dafür „Hintergrund (Begründungen, Sonderfälle): `docs/befehle/<befehl>.md` im Plugin-Ordner — nur bei Bedarf lesen.“

- **Wiedereinstieg** (alle betroffenen Befehle außer 01, 90): auf die drei Kernbefehle (`python3 .claude/hooks/workflow.py find 42`, `switch`, `status`) plus „in 2 Sätzen“ zusammengefasst; die #58-Begründung steht im Hintergrund.
- **10/20/40:** Checkpoint-Gerüst bytegleich; Kontext-Absatz in der Kurzform von 30-write-spec (ohne „200k ≈ Fünffache“ und ohne AUTO_NO_CLEAR-Klammer); Kontext-Dokument-Vorlage (10), Synthese-Vorlage und „Hängende Subagenten“-Rückfall (20), Codebeispiele und Artefakt-Anforderungen (40) ziehen um.
- **70:** Haupt-Ordner-Abschnitt auf Befehl + einen Satz, Erläuterungen zu Step 2/4 und zur Kette in den Hintergrund; alle gepinnten Wörter bleiben.
- **Kleine Befehle:** Vorlagen und Tabellen (83: Interview-Fragen und Output-Template; 81: Artefakt-Typen-Tabelle, Beispiel; 01: Modus-Tabelle, Standards; 82: Zero-Tolerance-Erläuterung; 99: Situationstabelle; 90: Verwendungsblock) ziehen um oder werden zusammengefasst.
- **60-validate:** zweiter Durchgang über Erläuterungen (Hängende Subagenten, Kontext laden, Validation-Report-Vorlage, On Failure, Beobachtbare-Oberfläche-Details); „Auto-Modus prüfen“ und alle gepinnten Wortlaute bleiben.

Invarianten: kein Hook- und kein Gate-Code geändert, keine Gate-Konfiguration, kein Override nötig, alle Pin-Tests unverändert grün ohne `skip`/`xfail`, Vollkopien und Skills ohne Drift.

## Expected Behavior

- **Input:** Aufruf eines der elf Befehle
- **Output:** gleicher Ablauf und gleiche Pflichtschritte aus kürzerem Text; `core/commands/*.md` zusammen ≤ 83 000 Bytes
- **Side effects:** geringere Last beim Laden; Hintergrundwissen vollständig in `docs/befehle/`

## Known Limitations

- Die Wirkung tritt erst beim Laden des jeweiligen Befehls ein.
- `docs/befehle/` liegt im Plugin-Ordner; zur Ausführung nicht nötig.
- Der Marker-Block und die Hook-Hinweise je Zug sind Thema von #679.

## Definition of Done

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Budgets je Befehl eingehalten, Gesamtsumme ≤ 83 000 Bytes, verschobener Text vollständig in `docs/befehle/`
- [ ] Gesamtsuite grün, `skills/` und Vollkopien ohne Drift
- [ ] CHANGELOG `[4.26.2]`, Version 4.26.2 überall, veröffentlicht
- [ ] Messung (Bytes je Befehl vorher/nachher) und `CONTEXT_TOKENS` an Epic #649

## Acceptance Criteria

- **AC-1:** Given das Repo nach der Änderung / When die Größe von `10-context.md`, `20-analyse.md`, `40-tdd-red.md`, `70-deploy.md` gemessen wird / Then halten sie 5 120, 6 656, 5 632 und 6 144 Bytes ein
  - Test: tests/test_commands_slim_678.py::test_main_commands_within_budget

- **AC-2:** Given die sechs kleinen Befehle / When ihre Größe gemessen wird / Then ist jeder höchstens 2 048 Bytes groß
  - Test: tests/test_commands_slim_678.py::test_small_commands_within_budget

- **AC-3:** Given `60-validate.md` / When seine Größe gemessen wird / Then beträgt sie höchstens 16 384 Bytes
  - Test: tests/test_commands_slim_678.py::test_validate_second_cut

- **AC-4:** Given alle `core/commands/*.md` / When ihre Summe gemessen wird / Then beträgt sie höchstens 83 000 Bytes
  - Test: tests/test_commands_slim_678.py::test_total_within_83kb

- **AC-5:** Given alle Dateien in `core/commands/` / When die Budget-Tabelle geprüft wird / Then hat jeder Befehl ein Budget und hält es ein
  - Test: tests/test_commands_slim_674.py::test_every_command_has_budget

- **AC-6:** Given 10, 20, 40, 70, 81, 83 / When nach dem Verweis gesucht wird / Then nennen sie `docs/befehle/<befehl>.md`, und diese existiert mit mindestens 3 `##`-Abschnitten
  - Test: tests/test_commands_slim_674.py::test_commands_link_background_docs

- **AC-7:** Given `### Step 2b` in 20-analyse, `## Common Mistakes` in 40-tdd-red, `## Step 4` und „b) Fachlicher Befund“ in 70-deploy / When die Texte geprüft werden / Then sind die Anker vorhanden
  - Test: tests/test_commands_slim_678.py::test_anchor_headings_kept

- **AC-8:** Given die bestehenden Pin-Tests / When die Gesamtsuite läuft / Then bleibt sie grün, ohne `skip`/`xfail`, und `sync_skills.py --check` meldet keine Drift
  - Test: tests/ (Gesamtsuite)

## Test Plan

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN die ungekürzten Befehle WHEN `pytest tests/test_commands_slim_678.py` läuft THEN scheitern Budget- und Summentests (RED)
- [ ] Test 2: GIVEN die erweiterte `LINKED`-Liste WHEN `tests/test_commands_slim_674.py` läuft THEN scheitert der Verweis-Test, bis Verweis und Doku vorhanden sind
- [ ] Test 3: GIVEN die gekürzten Befehle WHEN `pytest tests/` läuft THEN alles grün ohne `skip`/`xfail`

Tests im venv mit `pytest` und `pyyaml`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Umverteilung von Anweisungstext wie #580/#674/#677.
- **Alternative A, nur die zehn genannten Befehle:** verworfen, Summe ≈ 88 KB, DoD verfehlt.
- **Alternative B, gepinnte Wortlaute umschreiben und Tests anpassen:** verworfen, Risiko für Gate-Verhalten.

## Changelog

- 2026-11-26: Erstfassung
