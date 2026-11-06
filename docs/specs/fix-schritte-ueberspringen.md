---
entity_id: fix-schritte-ueberspringen
type: bugfix
created: 2026-11-06
updated: 2026-11-06
status: draft
version: "1.0"
workflow: fix-schritte-ueberspringen
tags: [aliases, gates, footer, workflow]
---

# Schritte-Überspringen verhindern: Alias-Fallback ohne Plugin, Adversary-Nachweis beim Wechsel nach Phase 7, Begründung in der Fußzeilen-Meldung

## Approval

- [ ] Approved

## Purpose

Claude überspringt in Sessions wiederholt Workflow-Schritte, weil drei Lücken zusammenwirken: Die Kurz-Aliase unter `.claude/commands/` verweisen nur auf einen Plugin-Skill, den Cloud-Sitzungen nicht laden, sodass der Befehlstext nie ankommt; `workflow.py phase phase7_validate` lässt sich ohne Adversary-Nachweis setzen, weil Verdict und Dialog erst ab Phase 8 geprüft werden; und der Fußzeilen-Hook korrigiert die ❗Du-Zeile ohne Phase und ohne Grund. Diese Änderung schließt alle drei Lücken: Der Alias liefert ohne Plugin den Befehlstext selbst (oder stoppt hörbar), das Gate greift schon beim Wechsel nach Phase 7, und die Fußzeilen-Meldung nennt Workflow, Phase und Grund.

## Source

- **File:** `core/hooks/alias_sync.py`, `core/hooks/workflow.py`, `core/hooks/footer_gate.py`
- **Identifier:** `alias_content`, `_validate_transition`, `_expected_command` und `main` in `footer_gate.py`

Kein Issue (keine Nummer bekannt). Ursprungsanfrage des PO und Reproduktion: `docs/context/fix-schritte-ueberspringen.md`.

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/alias_sync.py` | module | einzige Quelle für den Soll-Inhalt der Kurz-Aliase (genutzt von `setup.py` und `session_banner.py`) |
| `core/hooks/adversary_dialog.py` | module | `check_dialog_evidence`, `phase8_code_files`, `coverage_gate_enabled` (Nachweisprüfung, geteilt mit dem Commit-Gate in `bash_gate.py`) |
| `core/hooks/workflow.py` | module | `PHASES`, `PHASE_NAMES`, `next_step`, `expected_footer_command`, `_evidence_reason` (#447) |
| `core/hooks/hook_utils.py` | module | `resolve_active_workflow`, `read_state_json`, `block` |
| `core/hooks/evidence_gate.py` (#447) | module | Evidence-Gate bleibt bei `phase8_complete` |
| `scripts/sync_skills.py` | script | regeneriert `skills/50-implement/SKILL.md` und `skills/60-validate/SKILL.md` aus `core/commands` |
| `tests/test_repo_own_aliases_147.py` | test | bindet die committeten Aliase byte-gleich an `alias_content` |
| `tests/test_spec_freeze_partial_hash_439.py` | test | Vorbild für ein gültiges Dialog-Nachweis-Fixture (`stamp`, `add-artifact`, Verdict) |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/alias_sync.py | MODIFY | `alias_content()`: Redirect mit `allowed-tools`, Erklärungssatz und einzeiligem Inline-Bash-Block (Fallback auf lokale SKILL.md oder Stopp-Text) |
| .claude/commands/ (11 Redirects) | MODIFY | regeneriert aus `alias_content` |
| core/hooks/workflow.py | MODIFY | `_validate_transition`: Verdict und Dialog-Nachweis ab `phase7_validate` statt erst `phase8_complete`; Evidence-Gate bleibt bei Phase 8 |
| core/hooks/footer_gate.py | MODIFY | `_expected_command` liefert Befehl und Phase; Blockmeldung nennt Workflow, Phase, Phasenbezeichnung und Grund |
| core/commands/50-implement.md | MODIFY | Gate-Wirkung: Nachweis schon beim Wechsel nach Phase 7 |
| core/commands/60-validate.md | MODIFY | Gate-Wirkung und Hinweis auf BROKEN-Rücksprung |
| skills/50-implement/SKILL.md, skills/60-validate/SKILL.md | MODIFY | regeneriert per `scripts/sync_skills.py` |
| CLAUDE.md, README.md | MODIFY | Hook-Beschreibung (Phase 7 statt 8) und Alias-Fallback ohne Plugin |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] mit Migrationshinweis |
| tests/test_fix_schritte_ueberspringen.py | CREATE | Tests für alle AC |
| tests/test_effort_budget_250b.py | MODIFY | Fixture mit Dialog-Nachweis oder Ziel `phase6b_adversary` |
| tests/test_spec_content_gate_521.py | MODIFY | Fixture mit Dialog-Nachweis oder Ziel `phase6b_adversary` |
| tests/test_red_marker_phase_gate_f004.py | MODIFY | Fixture mit Dialog-Nachweis oder Ziel `phase6b_adversary` |
| tests/test_autoclear_transition_497.py | MODIFY | Fixture mit Dialog-Nachweis oder Ziel `phase6b_adversary` |

### Estimated Changes

- Files: 1 neu, 4 Quelldateien/Befehlstexte und 4 Tests geändert, 13 generierte Dateien, 3 Doku-Dateien
- LoC: +about 60 Produktion (alias_sync +35, workflow about 12 verschoben, footer_gate about 10), +about 250 Test
- Risk Level: HIGH (Gate-Code und Alias-Erzeugung treffen alle Konsumenten-Projekte)

## Implementation Details

Reihenfolge der Umsetzung: Teil B (Gate), dann Teil C (Fußzeile), dann Teil A (Alias), weil A der riskanteste Teil ist.

**Teil A: Alias-Fallback.** `alias_content()` ändert nur Skills mit `disable-model-invocation: false`; die vier Vollkopien (70-deploy, 80-workflow, 81-add-artifact, 99-reset) bleiben unverändert. Der Redirect bekommt im Frontmatter zusätzlich `allowed-tools: Bash(python3 -c *)`; `description: Kurz-Alias für /agent-os-openspec:<name>` bleibt. Der Alias-Marker steht weiterhin direkt nach dem Frontmatter (#251), damit `is_alias_file` die Datei erkennt und `alias_version` None liefert. Danach folgen die Zeile `/agent-os-openspec:<name> $ARGUMENTS`, ein Erklärungssatz und ein Inline-Bash-Block (```!) mit genau einer Zeile `python3 -c '...'`, ohne `&&`, `;` oder `|`, weil Bash-Permission-Regeln Präfix-Treffer sind, die an Shell-Operatoren enden (gleiches Muster wie SETUP_BLOCK in `scripts/sync_skills.py`).

Der Einzeiler arbeitet in dieser Reihenfolge:

1. Existiert `~/.claude/plugins/installed_plugins.json` und enthält unter `plugins` einen Schlüssel mit Präfix `agent-os-openspec@`, gibt er nichts aus (Plugin geladen, der Redirect gilt).
2. Sonst bestimmt er den Projekt-Root aus der Umgebungsvariable `CLAUDE_PROJECT_DIR`, ersatzweise dem Arbeitsverzeichnis, ersatzweise dem substituierten Argument.
3. Existiert `<root>/skills/<name>/SKILL.md`, gibt er einen Hinweis aus (Plugin nicht geladen, der folgende Text gilt), bei vorhandenem `<root>/core/hooks` die Zeile `export CLAUDE_PLUGIN_ROOT=<root>`, dann den vollständigen SKILL.md-Text. Keine Ausgabezeile beginnt mit `⚙ `.
4. Sonst gibt er einen Stopp-Text mit `BEFEHLSTEXT FEHLT` aus: Phase nicht beginnen, PO informieren.

Der Exit-Code ist immer 0.

**Teil B: Phase-7-Gate.** In `_validate_transition` wandern die Prüfungen Verdict (`adversary_verdict == VERIFIED`) und `adversary_dialog.check_dialog_evidence` (inklusive Abdeckung aus `phase8_code_files`, Kill-Switch `adversary_coverage_gate.enabled`) von der Bedingung `tgt_idx >= phase8_complete` auf `tgt_idx >= phase7_validate`. `_evidence_reason` (#447) bleibt an `phase8_complete`. Rückwärts-Übergänge (BROKEN-Rücksprung `phase6b_adversary` nach `phase6_implement`) bleiben frei und erhöhen `fix_loop_iterations`. Fast Track (`feature-fast`) prüft weiterhin nur Freigabe und Evidence. Nur `cmd_phase` und `complete` rufen `_validate_transition`; kein Hook schreibt Phase 7 programmatisch. Der Wechsel nach Phase 7 vor dem Commit besteht, wenn der Dialog nach der letzten Änderung gestempelt wurde (so bereits getestet in `test_adversary_coverage_gate_259.py` und `test_adversary_evidence_gate_253.py`).

**Teil C: Fußzeilen-Begründung.** `_expected_command(name)` in `footer_gate.py` liefert zusätzlich die aktuelle Phase. Die Blockmeldung `FUSSZEILE FALSCH` nennt Workflow-Name, Phase, die Bezeichnung aus `PHASE_NAMES` und den Satz, dass diese Phase nur den erwarteten Befehl verlässt (Beispiel: `phase6b_adversary` verlässt nur `/50-implement`). Der Ausnahmepfad bleibt unverändert: Fehlt der State oder ist er unlesbar, ist der Schritt Freitext (None) oder fehlt die ❗Du-Zeile, endet der Hook mit Exit 0 ohne Meldung.

## Expected Behavior

- **Input:** Aufruf eines Kurz-Alias (`/50-implement` u. a.) in einer Sitzung mit oder ohne Plugin; `workflow.py phase phase7_validate`; Ende einer Antwort mit ❗Du-Zeile (Stop-Hook)
- **Output:** Ohne Plugin der volle Befehlstext oder ein Stopp-Text `BEFEHLSTEXT FEHLT`; Ablehnung des Wechsels nach Phase 7 mit `BLOCKED` und konkreter Ursache, solange Verdict oder Dialog-Nachweis fehlen; Fußzeilen-Blockmeldung mit Workflow, Phase und Grund
- **Side effects:** Die 11 Redirect-Aliase in `.claude/commands/` und in Konsumenten-Projekten werden beim nächsten `--refresh-aliases` bzw. Banner-Refresh neu geschrieben; keine Änderung am Workflow-State-Format

## Known Limitations

- `allowed-tools: Bash(python3 -c *)` genehmigt während des Alias-Aufrufs jedes `python3 -c` vor. Entscheidung: hinnehmen, denn eine exakte Präfix-Regel mit eingebettetem Code ist YAML-fragil.
- Ob `${CLAUDE_PROJECT_DIR}` im Inline-Bash-Block substituiert wird, ist dokumentiert, im Repo aber ohne Präzedenz. Deshalb wird der Root zuerst aus Umgebungsvariable und Arbeitsverzeichnis bestimmt, die Substitution dient nur als Rückfall.
- Plugin-Konsumenten in Cloud-Sitzungen haben weder Plugin noch lokale SKILL.md und bekommen deshalb nur den Stopp-Text; die Ursache (#522) bleibt offen.
- Bestehende Workflows in `phase6b_adversary` brauchen ab jetzt Verdict und Dialog-Nachweis vor dem Wechsel nach Phase 7 (Migration: Dialog stempeln und registrieren, Verdict setzen, dann wechseln).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Der PO sieht in einer Cloud-Sitzung dieses Repos beim Aufruf von `/50-implement` den Befehlstext statt einer leeren Weiterleitung
- [ ] `workflow.py phase phase7_validate` ohne Nachweis wird mit der Meldung `Adversary verdict missing or not VERIFIED` bzw. `Adversary verdict ohne gültigen Dialog-Nachweis` abgelehnt
- [ ] Die Fußzeilen-Meldung nennt Workflow, Phase und Grund
- [ ] CHANGELOG [Unreleased] enthält den Eintrag samt Migrationshinweis
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `python3 -m pytest tests -q` grün)

## Acceptance Criteria

Teil A: Alias-Fallback

- **AC-1:** Given ein Skill mit `disable-model-invocation: false` / When `alias_content` den Redirect erzeugt / Then enthält das Frontmatter `description: Kurz-Alias für /agent-os-openspec:<name>` und `allowed-tools: Bash(python3 -c *)`, der Alias-Marker steht direkt nach dem Frontmatter, `is_alias_file` erkennt die Datei und `alias_version` liefert None
  - Test: tests/test_fix_schritte_ueberspringen.py::test_redirect_frontmatter_has_allowed_tools_and_marker

- **AC-2:** Given derselbe Redirect / When sein Text gelesen wird / Then enthält er die Zeile `/agent-os-openspec:<name> $ARGUMENTS` und einen Inline-Bash-Block (```!), dessen Befehl eine einzige Zeile ist, mit `python3 -c ` beginnt und weder `&&` noch `;` noch `|` enthält
  - Test: tests/test_fix_schritte_ueberspringen.py::test_redirect_inline_block_is_single_python_line

- **AC-3:** Given eine `~/.claude/plugins/installed_plugins.json` mit einem Schlüssel `agent-os-openspec@…` unter `plugins` / When der Inline-Befehl ausgeführt wird / Then ist seine Ausgabe leer
  - Test: tests/test_fix_schritte_ueberspringen.py::test_inline_command_silent_when_plugin_installed

- **AC-4:** Given kein installiertes Plugin und eine Datei `<root>/skills/<name>/SKILL.md` (Root aus der Umgebungsvariable `CLAUDE_PROJECT_DIR`) / When der Inline-Befehl ausgeführt wird / Then steht in der Ausgabe zuerst ein Hinweis, dass das Plugin nicht geladen ist und der folgende Text gilt, danach der vollständige SKILL.md-Text; existiert `<root>/core/hooks`, zusätzlich die Zeile `export CLAUDE_PLUGIN_ROOT=<root>`, und keine Ausgabezeile beginnt mit `⚙ `
  - Test: tests/test_fix_schritte_ueberspringen.py::test_inline_command_prints_skill_text_without_plugin

- **AC-5:** Given kein installiertes Plugin und keine lokale SKILL.md / When der Inline-Befehl ausgeführt wird / Then enthält die Ausgabe `BEFEHLSTEXT FEHLT` und die Anweisung, die Phase nicht zu beginnen und den PO zu informieren, und der Exit-Code ist 0
  - Test: tests/test_fix_schritte_ueberspringen.py::test_inline_command_stop_message_without_any_text

- **AC-6:** Given der Redirect-Text / When er gelesen wird / Then enthält er einen Erklärungssatz für drei Fälle (Plugin geladen: der Redirect gilt; Befehlstext unten: danach arbeiten; `BEFEHLSTEXT FEHLT`: nicht beginnen) und den Hinweis, den Block per Bash auszuführen, falls er wörtlich statt seiner Ausgabe erscheint
  - Test: tests/test_fix_schritte_ueberspringen.py::test_redirect_explains_fallback_cases

- **AC-7:** Given die 11 committeten Redirects unter `.claude/commands/` dieses Repos / When sie mit `alias_content` verglichen werden / Then sind sie byte-gleich (zusätzlich zum bestehenden `tests/test_repo_own_aliases_147.py`)
  - Test: tests/test_fix_schritte_ueberspringen.py::test_repo_aliases_match_alias_content

Teil B: Phase-7-Gate

- **AC-8:** Given ein Workflow `feature` in `phase6b_adversary` mit RED-Artefakt, aber ohne `adversary_verdict` / When `workflow.py phase phase7_validate` läuft / Then endet der Aufruf mit Exit 1, stderr enthält `BLOCKED` und `Adversary verdict missing or not VERIFIED`, und die Phase bleibt `phase6b_adversary`
  - Test: tests/test_fix_schritte_ueberspringen.py::test_phase7_blocked_without_verdict

- **AC-9:** Given derselbe Workflow mit `adversary_verdict: VERIFIED`, aber ohne registriertes und gestempeltes Dialog-Artefakt / When `workflow.py phase phase7_validate` läuft / Then endet der Aufruf mit Exit 1 und stderr enthält `Adversary verdict ohne gültigen Dialog-Nachweis`
  - Test: tests/test_fix_schritte_ueberspringen.py::test_phase7_blocked_without_dialog_evidence

- **AC-10:** Given derselbe Workflow mit VERIFIED und einem gültigen, gestempelten (`adversary_dialog.py stamp`) und registrierten (`add-artifact adversary_dialog`) Dialog-Artefakt / When `workflow.py phase phase7_validate` läuft / Then endet der Aufruf mit Exit 0 und die Phase ist `phase7_validate`
  - Test: tests/test_fix_schritte_ueberspringen.py::test_phase7_allowed_with_valid_evidence

- **AC-11:** Given ein Workflow in `phase6b_adversary` ohne Verdict (BROKEN-Pfad) / When `workflow.py phase phase6_implement` läuft / Then endet der Aufruf mit Exit 0 und `fix_loop_iterations` steigt um 1
  - Test: tests/test_fix_schritte_ueberspringen.py::test_backstep_to_phase6_stays_free

- **AC-12:** Given ein Workflow `feature-fast` in `phase6_implement` mit freigegebener Spec / When `workflow.py phase phase7_validate` läuft ohne Verdict / Then endet der Aufruf mit Exit 0
  - Test: tests/test_fix_schritte_ueberspringen.py::test_fast_track_phase7_unchanged

- **AC-13:** Given ein konfigurierter Evidence-Check (`evidence_checks` in config.yaml), ein gültiger Dialog-Nachweis und kein Beleg / When erst `phase phase7_validate` und danach `phase phase8_complete` läuft / Then endet der Wechsel nach Phase 7 mit Exit 0 und der Wechsel nach Phase 8 mit Exit 1
  - Test: tests/test_fix_schritte_ueberspringen.py::test_evidence_gate_stays_at_phase8

Teil C: Footer-Begründung

- **AC-14:** Given ein Workflow in `phase6b_adversary` und eine Antwort, die mit `❗ Du: /60-validate` endet / When der Stop-Hook `footer_gate.py` läuft / Then endet er mit Exit 2 und stderr enthält `FUSSZEILE FALSCH`, den Workflow-Namen, `phase6b_adversary`, die Bezeichnung `Adversary Verification` und den Satz, dass diese Phase nur `/50-implement` verlässt
  - Test: tests/test_fix_schritte_ueberspringen.py::test_footer_block_names_phase_and_reason

- **AC-15:** Given ein fehlender oder unlesbarer Workflow-State, ein Freitext-Schritt (etwa `phase3_spec` mit gesetztem `spec_file`) oder eine Antwort ohne ❗Du-Zeile / When der Stop-Hook läuft / Then endet er mit Exit 0 und gibt keine Meldung aus
  - Test: tests/test_fix_schritte_ueberspringen.py::test_footer_fail_open_unchanged

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `python3 -m pytest tests/test_fix_schritte_ueberspringen.py -q` (neue Datei, deckt AC-1 bis AC-15)
- Angepasste Fixtures in `tests/test_effort_budget_250b.py`, `tests/test_spec_content_gate_521.py`, `tests/test_red_marker_phase_gate_f004.py` und `tests/test_autoclear_transition_497.py`: Sie setzen heute `phase phase7_validate` ohne Verdict und bekommen ein gestempeltes Dialog-Fixture oder zielen auf `phase6b_adversary`
- Bestehende Alias-Tests: `tests/test_repo_own_aliases_147.py`, `tests/test_alias_marker_position_251.py`, `tests/test_alias_robust_350.py`, `tests/test_alias_sync_robust_400.py`, `tests/test_session_banner.py`
- `python3 scripts/sync_skills.py --check` (Skills-Drift)
- Voller Regressionslauf: `python3 -m pytest tests -q`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Bugfix im Rahmen bestehender Architektur: Ein vorhandenes Gate wird um eine Phase nach vorn gezogen (gleiche Prüffunktionen wie Phase 8 und Commit-Gate), die Alias-Erzeugung bekommt einen Fallback ohne neue Abhängigkeit, und die Fußzeilen-Meldung wird nur ausführlicher. Keine neue Komponente und kein neues State-Format; reversibel durch Zurücksetzen der drei Dateien.

## Changelog

- 2026-11-06: Initial spec created
