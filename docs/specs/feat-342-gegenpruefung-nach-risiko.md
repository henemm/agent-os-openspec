---
entity_id: feat-342-gegenpruefung-nach-risiko
type: module
created: 2026-10-03
updated: 2026-10-03
status: draft
version: "1.0"
tags: [adversary, risiko, gegenpruefung, token, "#342", "#250"]
---

# Gegenprüfung nach Risiko staffeln (#342, Teil des Meilensteins „Token-Verbrauch senken")

## Approval

- [ ] Approved

## Purpose

Heute verlangt jede Gegenprüfung im vollen Prozess mindestens zwei Dialog-Runden
(`adversary_dialog.MIN_ROUNDS = 2`), unabhängig davon, was sich geändert hat. Eine reine Textänderung an
einem Befehl und eine Änderung an einem Sicherheits-Guard kosten dieselbe Prüfung. Die Auswertung (1.958
Workflows) zeigt, dass die Prüfung selten etwas zurückschickt (Fix-Loops im Schnitt 0,1); der eine belegte
Fall, in dem eine dritte Runde eine kritische Lücke fand (#237), betraf Gate-Code.

Entscheidung des PO (2026-10-03, #342): **Die Gegenprüfung wird nach Risiko gestaffelt, nicht pauschal
gedeckelt.** Das vereint die Entscheidung vom 26.09. („die Gegenprüfung wird nie abgeschnitten") mit dem
Meilenstein vom 03.10. („nur bei Risiko"):

- **Hohes Risiko** (Hook- und Gate-Code, Sicherheits-Guards, Freigabe-Logik, Konfiguration der Gates):
  unverändert mindestens **2 Runden**.
- **Niedriges Risiko** (ausschließlich Anweisungstext, Dokumentation und Tests): mindestens **1 Runde**.

Das Risiko ergibt sich **mechanisch aus der Dateiliste** der Änderung, nicht aus einer Selbsteinstufung und
nicht aus der Zeilenzahl; im Zweifel gilt hohes Risiko.

## Source

- **File:** `core/hooks/hook_utils.py`, `core/hooks/adversary_dialog.py`, `config.yaml`
- **Identifier:** `observable_surface_report` (Vorbild), `adversary_dialog.MIN_ROUNDS`,
  `adversary_dialog.check_dialog_evidence`, `adversary_dialog.validate_dialog_artifact_ex`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils.observable_surface_report` | Funktion | Vorbild: mechanische, fail-closed Einstufung aus der git-Dateiliste gegen Musterlisten in `config.yaml` (#260) |
| `hook_utils._observable_base`, `_observable_files` | Funktionen | liefern Basis-Stand (merge-base gegen `origin/HEAD`) und Dateiliste der Änderung; werden wiederverwendet, nicht kopiert |
| `adversary_dialog.check_dialog_evidence` | Funktion | einziger Weg, über den Commit-Gate und Phase-8-Übergang das Dialog-Artefakt prüfen — dort wird die Risikostufe angewandt |
| `adversary_dialog.validate_dialog_artifact_ex` | Funktion | prüft das Artefakt inkl. Rundenzahl; bekommt die Mindestzahl als Parameter, Standard bleibt `MIN_ROUNDS` |
| `core/agents/implementation-validator.md` | Agent | beschreibt die Early-Agreement-Skepsis und die Rundenzahl; wird angepasst |
| `tests/test_intake_two_tracks_254.py` | Test | verlangt „mindestens 2" im Intake-Text; bleibt gültig (hohes Risiko) |

## Scope

- **Affected Files:** `core/hooks/hook_utils.py`, `core/hooks/adversary_dialog.py`, `config.yaml`,
  `core/commands/00-intake.md`, `core/commands/50-implement.md`, `core/agents/implementation-validator.md`,
  `CLAUDE.md`, `skills/00-intake/SKILL.md` und `skills/50-implement/SKILL.md` (generiert),
  `tests/test_adversary_risk_342.py` (neu), `CHANGELOG.md`
- **Estimated Changes:** ca. +130 LoC Logik, ca. +220 LoC Tests, ca. 15 Zeilen Text. 3 Logik-Dateien
  (Hausregel eingehalten).
- **Nicht enthalten:** Fix-Loop-Limit und Circuit Breaker (`MAX_ITERATIONS`), Verdict-Regeln, die
  Abdeckungsprüfung (#259), der Fast Track (hat keine Gegenprüfung), #289 (Nachweis nach Rebase),
  die Aufwandsbremse (#340). Keine Prüfung entfällt vollständig; auch bei niedrigem Risiko bleibt eine Runde
  mit Beweisführung je Acceptance Criterion Pflicht.

## Implementation Details

1. **`config.yaml` — neuer Block `adversary_risk`:** `enabled` (nur ein ausdrückliches `false` schaltet ab,
   dann gilt immer hohes Risiko), `high_risk_patterns`, `low_risk_patterns`, `low_risk_min_rounds: 1`,
   `base_branch` (leer = aus `origin/HEAD` ableiten, wie bei `observable_surface`). Startwerte:
   - `high_risk_patterns` (ein Treffer genügt): `^core/hooks/`, `^hooks/`, `^core/agents/`, `^scripts/`,
     `^modules/`, `^setup\.py$`, `^config\.yaml$`, `^\.github/`, `^\.claude-plugin/`, `(^|/)\.env`,
     `secret`.
   - `low_risk_patterns` (nur wenn **jede** Datei trifft): `^docs/`, `^tests?/`, `(^|/)test_[^/]+\.py$`,
     `^core/commands/[^/]+\.md$`, `^skills/[^/]+/SKILL\.md$`, `(^|/)(CHANGELOG|README|CONTRIBUTING)\.md$`,
     `(^|/)CLAUDE\.md$`, `(^|/)\.gitignore$`.
2. **`hook_utils.adversary_risk_report()`** — Schwester von `observable_surface_report` mit derselben
   fail-closed-Reihenfolge: ungültiger Config-Block → hoch; abgeschaltet → hoch; kein Basis-Stand oder
   git-Fehler → hoch; leere Dateiliste → hoch; ein Treffer in `high_risk_patterns` → hoch; jede Datei in
   `low_risk_patterns` → niedrig; irgendeine unbekannte Datei → hoch. Rückgabe
   `{risk, reason, files, root, min_rounds}`; liest nur, schreibt nichts.
3. **`adversary_dialog.required_rounds()`** liefert `MIN_ROUNDS` (2) bei hohem Risiko und
   `low_risk_min_rounds` bei niedrigem, begrenzt auf 1 bis `MIN_ROUNDS`; jeder ungültige Wert fällt auf
   `MIN_ROUNDS`. **Nur** `check_dialog_evidence` (der Weg von Commit-Gate und Phase 8) ruft sie auf und gibt
   die Zahl an `validate_dialog_artifact_ex(path, min_rounds=…)` weiter. Ohne Parameter gilt weiter
   `MIN_ROUNDS` — dadurch bleibt jeder bestehende Aufruf und Test unabhängig vom Zustand des Checkouts.
4. **CLI `adversary_dialog.py risk`:** gibt Stufe, Begründung, Dateianzahl und geforderte Rundenzahl aus
   (Vorbild: `workflow.py observable-surface`), damit PO und Prüfer-Agent die Stufe nachvollziehen können.
5. **Texte:** `00-intake.md` (Scoring und Tabelle), `50-implement.md` (Zeile „Mindestens 2 Runden Dialog"),
   `implementation-validator.md` und `CLAUDE.md` (Abschnitt Adversary Dialog) nennen „mindestens 2 Runden
   bei hohem Risiko, 1 Runde bei niedrigem Risiko" und verweisen auf `adversary_dialog.py risk`. Die
   Early-Agreement-Skepsis bleibt: auch eine einzige Runde muss jeden Punkt belegen.

## Expected Behavior

- **Input:** Ein Workflow im vollen Prozess erreicht Commit oder Phase 8.
- **Output:** Betrifft die Änderung ausschließlich Anweisungstext, Dokumentation und Tests, genügt ein
  Dialog-Artefakt mit einer Runde; berührt sie auch nur eine Datei aus der Hochrisiko-Liste oder eine
  unbekannte Datei, sind wie bisher mindestens zwei Runden nötig.
- **Side effects:** Keine neuen Blockaden. Die Staffelung erlaubt nur eine kürzere Prüfung, sie verlangt nie
  mehr als bisher.

## Known Limitations

- Anweisungstext ändert das Verhalten von Claude, die Tests belegen aber nur, dass der Text da ist. Die
  Einstufung als niedriges Risiko folgt der Entscheidung des PO und ist ein bewusstes Restrisiko.
- Die Musterlisten sind Startwerte. Eine Datei, die keine der beiden Listen trifft, gilt als unbekannt und
  damit als hohes Risiko; neue Verzeichnisse müssen bei Bedarf in `low_risk_patterns` ergänzt werden.
- Der Einspareffekt ist nicht vorab belegt. Er zeigt sich erst in `token_report` und `workflow_stats`
  nach einigen Wochen (Tokenverbrauch und Dauer je Workflow).
- Die Dateiliste kommt aus dem Vergleich mit dem Basis-Stand; ohne `origin/HEAD` oder bei einem git-Fehler
  gilt hohes Risiko (kürzere Prüfung entfällt, es wird nichts übersehen).

## Alternativen (und was sie kippen würden)

1. **Pauschal auf eine Runde deckeln:** verworfen. Die dritte Runde bei #237 fand eine kritische Lücke in
   Gate-Code; ein pauschaler Deckel hätte sie abgeschnitten.
2. **Bei niedrigem Risiko gar keine Gegenprüfung:** verworfen. Anweisungstext wirkt auf das Verhalten von
   Claude, und die Tests prüfen nur Text; eine Runde mit Beweisführung bleibt das Mindeste.
3. **Staffeln nach Zeilenzahl:** verworfen (Beobachtung in #250, 2026-09-27): die Schicht, nicht die Größe,
   bestimmt das Risiko; zwei geänderte Zeilen in einem Guard sind riskanter als 200 Zeilen Doku.
4. **Selbsteinstufung durch Claude (Feld im State oder Flag am Befehl):** verworfen. Wer die Prüfung
   spart, würde sie sich selbst genehmigen; die Einstufung darf nur aus der Dateiliste kommen.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Eine Änderung ausschließlich an Anweisungstext, Dokumentation und Tests kommt mit einer Dialog-Runde
      durch Commit-Gate und Phase 8, jede andere Änderung weiterhin nur mit mindestens zwei
- [ ] Im Zweifel (Fehler, abgeschaltet, unbekannte Datei, leere Liste) gilt hohes Risiko
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given `config.yaml` / When geladen / Then enthält sie `adversary_risk` mit `enabled`,
  `high_risk_patterns`, `low_risk_patterns` und `low_risk_min_rounds: 1`; fehlt der Block, gelten dieselben
  Werte als Modul-Konstanten
  - Test: `tests/test_adversary_risk_342.py::test_config_block_and_defaults`
- **AC-2:** Given eine Änderungsmenge mit mindestens einer Datei unter `core/hooks/` (auch zusammen mit
  Dokumentation) / When das Risiko ermittelt wird / Then lautet es „hoch" und `min_rounds` ist 2
  - Test: `tests/test_adversary_risk_342.py::test_one_high_risk_file_makes_it_high`
- **AC-3:** Given eine Änderungsmenge, in der jede Datei unter `docs/`, `tests/`, `core/commands/*.md`,
  `skills/*/SKILL.md`, `CHANGELOG.md`, `README.md` oder `CLAUDE.md` liegt / When das Risiko ermittelt wird /
  Then lautet es „niedrig" und `min_rounds` ist 1
  - Test: `tests/test_adversary_risk_342.py::test_only_text_docs_and_tests_is_low`
- **AC-4:** Given ungültiger Config-Block, abgeschalteter Block, fehlender Basis-Stand, git-Fehler, leere
  Dateiliste oder eine Datei, die keine Liste trifft / When das Risiko ermittelt wird / Then lautet es in
  jedem dieser Fälle „hoch" mit dem jeweiligen Grund
  - Test: `tests/test_adversary_risk_342.py::test_every_doubt_means_high`
- **AC-5:** Given dasselbe Dialog-Artefakt mit genau einer Runde / When `check_dialog_evidence` bei
  niedrigem bzw. hohem Risiko läuft / Then akzeptiert es das Artefakt bei niedrigem Risiko und lehnt es bei
  hohem Risiko wegen der Rundenzahl ab
  - Test: `tests/test_adversary_risk_342.py::test_one_round_passes_only_when_risk_is_low`
- **AC-6:** Given `validate_dialog_artifact`/`validate_dialog_artifact_ex` ohne Parameter / When das
  Artefakt nur eine Runde hat / Then wird es unabhängig vom Zustand des Checkouts abgelehnt (Standard bleibt
  `MIN_ROUNDS`)
  - Test: `tests/test_adversary_risk_342.py::test_validate_without_parameter_keeps_two_rounds`
- **AC-7:** Given `low_risk_min_rounds` mit ungültigem Wert (Text, 0, negativ, größer als 2) oder
  `adversary_risk.enabled: false` / When die Rundenzahl ermittelt wird / Then fällt sie auf 2 zurück
  - Test: `tests/test_adversary_risk_342.py::test_invalid_values_and_kill_switch_fall_back_to_two`
- **AC-8:** Given `python3 adversary_dialog.py risk` / When er läuft / Then nennt die Ausgabe Stufe,
  Begründung, Dateianzahl und geforderte Rundenzahl, Exit-Code 0
  - Test: `tests/test_adversary_risk_342.py::test_risk_cli_reports_level_and_rounds`
- **AC-9:** Given `00-intake.md`, `50-implement.md`, `implementation-validator.md` und `CLAUDE.md` / When
  der Text gelesen wird / Then nennen alle „mindestens 2" Runden bei hohem und „1 Runde" bei niedrigem
  Risiko und verweisen auf `adversary_dialog.py risk`; kein Text behauptet mehr eine feste Rundenzahl für
  alle; `sync_skills.py --check` meldet keinen Drift
  - Test: `tests/test_adversary_risk_342.py::test_texts_describe_risk_staging_and_skills_in_sync`

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich: Nach der
> Freigabe ist diese Datei eingefroren (#230). Stimmt ein Testname später nicht mehr, gehört die
> Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`), nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_adversary_risk_342.py` (AC-1 bis AC-9)
- Regression: `pytest tests/test_adversary_dialog_*.py tests/test_adversary_evidence_gate_253.py
  tests/test_adversary_coverage_gate_259.py tests/test_intake_two_tracks_254.py` und die gesamte Suite

Nicht automatisch prüfbar: ob die Einstufung die richtigen Änderungen als niedrig erkennt und ob der
Prüf-Agent bei niedrigem Risiko mit einer Runde auskommt. Das belegt die Auswertung nach einigen Wochen
(`token_report`, `workflow_stats`): Tokenverbrauch und Dauer je Workflow, Anteil niedrig eingestufter
Workflows, Fix-Loops danach.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine eigene Nummer — die Entscheidung steht in diesem Dokument
- **Rationale:** Das Risiko wird **mechanisch aus der Dateiliste** abgeleitet, **fail-closed** und nach dem
  Muster von `observable_surface_report` (#260), und es verändert nur die **Mindestzahl der Runden**, nie das
  Verdict oder die Beweispflicht. Gewählt ist die kleinste Mechanik, die Ihre beiden Entscheidungen
  zusammenführt: die Gegenprüfung bleibt dort unverkürzt, wo ein Fehler teuer ist, und spart dort, wo sie
  selten etwas findet. Eine Selbsteinstufung ist ausgeschlossen, weil sie das Sparen selbst genehmigen würde.

## Changelog

- 2026-10-03: Initial spec created
