---
entity_id: fix-561-nachpruefung-broken
type: bugfix
created: 2026-11-10
updated: 2026-11-10
status: draft
version: "1.0"
workflow: fix-561-nachpruefung-broken
tags: [workflow, deploy, plan, broken-pfad]
---

# Fachlicher Befund bei der Nachprüfung nach Phase 8 nimmt den BROKEN-Pfad (Issue #561)

## Approval

- [ ] Approved

## Purpose

Fand die Prüfung nach der Auslieferung (Staging/live) einen fachlichen Fehler, entstand bisher ein Korrektur-PR am Workflow vorbei; Plan und Seitenleiste blieben bei „8 Code fertig / Deploy“ stehen. Diese Änderung beschreibt den fachlichen Befund in `/70-deploy` und `/60-validate` als BROKEN-Pfad (Rücksprung nach `phase6_implement`, Fix, Adversary-Runde, Validierung, erneut ausliefern) und sorgt dafür, dass ein Rücksprung vor Phase 8 den alten Deploy-Zustand verwirft.

## Source

- **File:** `core/hooks/workflow.py`, `core/commands/70-deploy.md`, `core/commands/60-validate.md`
- **Identifier:** `_reset_approvals_on_backstep`, `cmd_deploy_status`, `_end_state_final`, `_plan_deploy_line`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow._reset_approvals_on_backstep` (~2547) | function | Rücksprung-Nebenwirkungen (#405); bekommt das Verwerfen des Deploy-Zustands |
| `workflow.cmd_deploy_status` (~3241) | function | schreibt `deploy_status`/`deploy_at`; bekommt `--note` |
| `workflow._end_state_final` (~409), `_plan_deploy_line` (~601) | function | lesen `deploy_status`/`deploy_note` für Endzeile und Plan; unverändert |
| `workflow.cmd_phase`, `_validate_transition` | function | erlauben den Rückwärtswechsel aus `phase8_complete`, solange nicht archiviert |
| `docs/specs/feat-510-plan-deploy-status.md`, `fix-550-endzustand.md`, `fix-555-nacharbeit-endzustand.md` | spec | Grundlage für `deploy_status`, Endzustand und `deploy_note` |
| `scripts/sync_skills.py` | tool | erzeugt `skills/*/SKILL.md` aus den Befehlstexten (`--check` prüft Drift) |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | Rücksprung mit Ziel vor `phase8_complete` entfernt `deploy_status`, `deploy_at`, `deploy_note`; `deploy-status <wert> --note <Grund>` schreibt `deploy_note` |
| core/commands/70-deploy.md | MODIFY | Step 4: technischer Fehlschlag vs. fachlicher Befund; fachlich = BROKEN-Pfad; archivierter Workflow → neuer Workflow mit derselben Issue-Nummer |
| core/commands/60-validate.md | MODIFY | Nachprüfung nach Phase 8 (Staging/live) als BROKEN-Pfad, Verweis auf `/70-deploy` |
| skills/60-validate/SKILL.md, skills/70-deploy/SKILL.md | REGENERATE | `python3 scripts/sync_skills.py` |
| tests/test_nachpruefung_broken_561.py | CREATE | Regressionstests zu allen AC |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased], keine Versionsnummer |

### Estimated Changes

- Files: 1 neu (+ 2 regenerierte Skills), 4 geändert
- LoC: ca. +25 Code, +115 Anweisung/Test
- Risk Level: MEDIUM (Kern-State-CLI `workflow.py`, aber nur Anzeige-Felder ohne Gate-Wirkung)

## Implementation Details

1. **Rücksprung (`_reset_approvals_on_backstep`).** Bei Rückwärtswechsel (Ziel-Index kleiner als Ist-Index) mit Ziel vor `phase8_complete` werden `deploy_status`, `deploy_at` und `deploy_note` per `pop` entfernt. Vorwärtswechsel und gleiche Phase bleiben unverändert; ein Rücksprung auf `phase8_complete` selbst (z. B. aus einer späteren Phase, falls vorhanden) behält den Deploy-Zustand.
2. **`cmd_deploy_status` mit `--note`.** Optionales `--note <Grund>` an beliebiger Stelle nach dem Wert; der Text ist das nächste Argument. Gesetzt wird `deploy_note` als Einzeiler (Zeilenumbrüche zu Leerzeichen, getrimmt); ein leerer Text ergibt kein Feld. Ohne `--note` wird ein vorhandenes `deploy_note` entfernt, denn ein neuer Status ersetzt die alte Notiz. `--note` ohne Text endet mit Exit 1 und Usage. Die Usage-Zeile nennt `[--note <Grund>]`.
3. **`/70-deploy` Step 4.** Zwei Fälle: (a) technischer Fehlschlag (Infrastruktur, Deploy bricht ab) wie bisher: `deploy-status failed --note "<Grund>"`, Rollback vorschlagen. (b) Fachlicher Befund (eine AC ist auf Staging/live verletzt, nicht die Infrastruktur) ist der BROKEN-Pfad: `workflow.py deploy-status failed --note "<AC und Befund>"`, `workflow.py phase phase6_implement`, Fix per `/50-implement`, eine Adversary-Runde aus demselben Kontingent (Adversary-Limit), `/60-validate`, danach erneut ausliefern. Kein Korrektur-PR am Workflow vorbei. Ist der Workflow schon archiviert (`complete`/`finish`/`/99-reset`), geht der Rücksprung nicht mehr: neuer Workflow mit derselben Issue-Nummer (`/00-intake #<N>`) bzw. ein Folge-Issue.
4. **`/60-validate`.** Die Auslieferungs- und Staging-Schritte verweisen auf denselben Pfad: ein fachlicher Befund nach Phase 8 zählt wie BROKEN (#259), zurück zu `phase6_implement`, Adversary-Runde aus demselben Kontingent, danach erneut `/60-validate` und `/70-deploy`.
5. **Skills und Changelog.** `python3 scripts/sync_skills.py` erzeugt `skills/60-validate/SKILL.md` und `skills/70-deploy/SKILL.md` neu; `CHANGELOG.md` bekommt unter `[Unreleased]` einen Eintrag.

## Expected Behavior

- **Input:** Workflow-State in `phase8_complete` mit `deploy_status=failed` (ggf. `deploy_note`), Aufruf `workflow.py phase phase6_implement`; Aufruf `workflow.py deploy-status <wert> [--note <Grund>]`
- **Output:** Nach dem Rücksprung zeigt der Plan `▶ 6 Implement  (läuft)` ohne Deploy-Altstand; nach erneutem Erreichen von Phase 8 steht `▶ Deploy  (offen)` statt `✘ Deploy  (fehlgeschlagen)`; die Endzeile nennt den Grund aus `deploy_note`, solange `failed` gilt
- **Side effects:** `deploy_status`, `deploy_at`, `deploy_note` werden beim Rücksprung vor Phase 8 entfernt; keine neue Gate-Wirkung

## Known Limitations

- Nach einem bereits gemergten Erst-PR verlangt die Abdeckungsprüfung (#259) alle Dateien seit `base_commit`. Das ist strenger und gewollt; diese Änderung ändert kein Gate.
- Ob Claude den BROKEN-Pfad einhält, erzwingt kein Hook; die Anweisung ist verbindlich formuliert, wie bei den übrigen Befehlstexten.
- Bei archiviertem Workflow gibt es keinen Rücksprung; der Weg ist ein neuer Workflow bzw. ein Folge-Issue (nur Anweisung).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Nach Rücksprung `phase8_complete → phase6_implement` mit `deploy_status=failed` zeigt der Plan `▶ 6 Implement  (läuft)` ohne Deploy-Altstand, und nach erneutem Phase 8 erscheint `▶ Deploy  (offen)`
- [ ] `/70-deploy` und `/60-validate` beschreiben den fachlichen Befund als BROKEN-Pfad, `skills/` ist neu generiert und ohne Drift
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given ein Workflow in `phase8_complete` mit `deploy_status=failed`, `deploy_at` und `deploy_note` / When `_reset_approvals_on_backstep` mit Ziel `phase6_implement` (oder einer anderen Phase vor `phase8_complete`) läuft / Then sind `deploy_status`, `deploy_at` und `deploy_note` aus dem State entfernt
  - Test: tests/test_nachpruefung_broken_561.py::test_backstep_before_phase8_clears_deploy_fields

- **AC-2:** Given ein Workflow mit gesetztem Deploy-Zustand / When der Phasenwechsel vorwärts oder auf dieselbe Phase geht, oder ein Rückwärtswechsel nicht vor `phase8_complete` endet / Then bleiben `deploy_status`, `deploy_at` und `deploy_note` unverändert
  - Test: tests/test_nachpruefung_broken_561.py::test_forward_and_same_phase_keep_deploy_fields

- **AC-3:** Given `deploy_status=failed` in `phase8_complete` / When der Rücksprung nach `phase6_implement` läuft und danach wieder `phase8_complete` erreicht wird / Then zeigt der Plan in Phase 6 `▶ 6 Implement  (läuft)` ohne Deploy-Altstand und nach erneutem Phase 8 `▶ Deploy  (offen)` ohne `fehlgeschlagen` und ohne den alten Grund
  - Test: tests/test_nachpruefung_broken_561.py::test_plan_after_backstep_and_second_phase8_shows_open_deploy

- **AC-4:** Given ein aktiver Workflow / When `workflow.py deploy-status failed --note "AC-3 verletzt"` läuft (auch mit `--note` vor dem Wert) / Then ist `deploy_status=failed` und `deploy_note="AC-3 verletzt"` gesetzt, die Endzeile nennt den Grund, und der Text ist ein Einzeiler (Zeilenumbrüche werden zu Leerzeichen, ein leerer Text setzt kein Feld)
  - Test: tests/test_nachpruefung_broken_561.py::test_deploy_status_note_sets_single_line_note

- **AC-5:** Given ein vorhandenes `deploy_note` / When `deploy-status running` oder `deploy-status done` ohne `--note` läuft / Then ist `deploy_note` entfernt und der neue Status gilt
  - Test: tests/test_nachpruefung_broken_561.py::test_deploy_status_without_note_removes_old_note

- **AC-6:** Given der Aufruf `deploy-status failed --note` ohne Text / When der Befehl läuft / Then endet er mit Exit 1 und Usage-Hinweis, und der State bleibt unverändert
  - Test: tests/test_nachpruefung_broken_561.py::test_deploy_status_note_without_text_exits_1

- **AC-7:** Given `core/commands/70-deploy.md` / When gelesen / Then beschreibt Step 4 den fachlichen Befund (AC verletzt, nicht Infrastruktur) als BROKEN-Pfad mit `deploy-status failed` und `--note`, `workflow.py phase phase6_implement`, `/50-implement`, Adversary-Runde aus demselben Kontingent und erneuter Auslieferung, verbietet den Korrektur-PR am Workflow vorbei und nennt für archivierte Workflows den neuen Workflow mit derselben Issue-Nummer
  - Test: tests/test_nachpruefung_broken_561.py::test_deploy_command_describes_broken_path

- **AC-8:** Given `core/commands/60-validate.md` / When gelesen / Then behandelt sie den fachlichen Befund bei der Nachprüfung nach Phase 8 wie BROKEN (Rücksprung `phase6_implement`, Adversary-Runde aus demselben Kontingent) und verweist auf `/70-deploy`
  - Test: tests/test_nachpruefung_broken_561.py::test_validate_command_describes_broken_path

- **AC-9:** Given die geänderten Befehlstexte / When `python3 scripts/sync_skills.py --check` läuft / Then meldet es keine Drift, und `skills/60-validate/SKILL.md` sowie `skills/70-deploy/SKILL.md` enthalten die neuen Anweisungen
  - Test: tests/test_nachpruefung_broken_561.py::test_skills_in_sync_with_commands

## Test Plan

Automatische Tests (jeweils an eine AC gebunden, ohne Netzwerk, State per `tmp_path`/Monkeypatch wie in `tests/test_plan_deploy_status_510.py` und `tests/test_rueckspruung_405.py`):
- `pytest tests/test_nachpruefung_broken_561.py` (RED zuerst, dann GREEN)
- Bestandstests: `pytest tests/test_rueckspruung_405.py tests/test_plan_deploy_status_510.py tests/test_endzustand_550.py tests/test_nacharbeit_555.py tests/test_skills_sync.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/workflow.py`
- `python3 scripts/sync_skills.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung folgt dem bestehenden Muster „Phasenwechsel verwirft Anzeige-Zustand“ (`_reset_approvals_on_backstep` aus #405, `waiting_on` aus #550) und ergänzt den vorhandenen Befehl `deploy-status` um ein optionales Argument. Deploy-Felder sind reine Anzeige ohne Gate-Wirkung; additiv und reversibel. Der fachliche Befund nutzt den vorhandenen BROKEN-Pfad statt eines neuen Mechanismus.

## Changelog

- 2026-11-10: Initial spec created
