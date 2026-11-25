# Context: docs-674-commands-slim

## Request Summary
Issue #674 (Epic #649): Befehlstexte verschlanken nach dem Muster von #580. Ablauf und Pflichtschritte bleiben im Befehlstext, Begründungen, Sonderfälle und Nachschlagewissen wandern nach `docs/`. Kein Gate-Verhalten ändert sich.

## Schnitt
`core/commands/*.md` = 138 946 Bytes; −40 % heißt ≈ 56 KB verschieben. Die Umfangsgrenze (`scope_guard.max_loc_delta` 250 hinzugefügte Produktivzeilen; nur `docs/specs|context|briefings` ausgenommen) erlaubt das nicht in einem Workflow. Aufteilung:
- **#674 (dieser Workflow):** `60-validate.md` (27 481 B) und `50-implement.md` (21 324 B), Größenwächter-Test für alle Befehlstexte (Startbudget je Datei = heutige Größe, für 50/60 das neue Budget).
- **#677:** 30-write-spec, 00-intake, 80-workflow.
- **#678:** 20-analyse, 70-deploy, 40-tdd-red, 10-context, kleine Befehle; Gesamtziel ≤ 83 KB.
- **#679:** Versions-Marker-Block aus `scripts/sync_skills.py` (≈ 3,5 KB je Skill) und Hook-Hinweise je Zug.

## Related Files
| File | Relevance |
|------|-----------|
| core/commands/50-implement.md, 60-validate.md | Quelle, wird gekürzt |
| skills/50-implement/SKILL.md, skills/60-validate/SKILL.md | Generat (`scripts/sync_skills.py`) |
| docs/befehle/50-implement.md, 60-validate.md | NEU: Hintergrund (Begründungen, Sonderfälle) |
| docs/architektur.md, docs/arbeitsweise.md | enthalten schon Adversary-/Gate-/Kontext-Haushalt-Wissen → Dubletten können entfallen bzw. verweisen |
| tests/test_commands_slim_674.py | NEU: Größenwächter |

## Existing Patterns
- #580: CLAUDE.md → docs/architektur.md wörtlich, Größenwächter-Test `tests/test_claude_md_slim_580.py`.
- Kein Hook parst Befehlstexte zur Laufzeit; nur `sync_skills.py` (Setup-Block, Pfad-Rewrite, Marker) und `release_check.py` (Drift).
- `hook_utils.py` stuft `core/commands/*.md` als niedriges Adversary-Risiko ein (1 Runde).

## Dependencies / Dependents
- Viele Tests pinnen Wortlaute in 50/60 (Analyse-Bericht): u. a. test_foreground_checkers_83, test_cloud_agents_577, test_auto_green_471, test_skill_stop_instruction, test_clear_checkpoint_blocks, test_context_stop_658, test_kontext_haushalt, test_adversary_protokoll_format_278, test_precondition_section_gate, test_adversary_risk_342, test_no_tmp_paths_in_instructions, test_nachpruefung_broken_561, test_plan_kopf_und_auslieferung_612, test_testausgabe_erkennung_275, test_observable_surface_260, test_auto_ship_525/528/530, test_autonomy_kette_472, test_endzustand_550, 551, 555, 667, 668, 589, test_vorlagen_klartext_597, test_guard_276, test_skills_sync.
- „Auto-Modus prüfen“ in 60-validate (7 KB) ist weitgehend wörtlich gepinnt → bleibt.

## Risks & Considerations
- Realistisch ≈ 30 % je Datei ohne gepinnten Text anzutasten (Analyse: 50 ≈ 6–7 KB, 60 ≈ 7–8 KB verschiebbar).
- Konsumenten: Plugin liefert das ganze Repo aus, `docs/befehle/` liegt im Plugin-Ordner; verschobener Text ist Hintergrund, nicht zur Ausführung nötig.
- Gate-Verhalten: nur Anweisungstext, keine Hook-Änderung.

## Analysis

### Type
Feature (Doku-/Anweisungstext-Umbau), Quelle: Explore-Bericht dieser Sitzung (Abschnitte je Datei mit KEEP/CONDENSE/MOVE, alle Test-Pins).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/commands/50-implement.md | MODIFY | ≤ 15 360 B: Begründungen zu #58, #83, #183, #253, #259, #289, #577, Rollentabelle, Circuit-Breaker-Erläuterung, „200k ≈ 5×“ raus |
| core/commands/60-validate.md | MODIFY | ≤ 20 480 B: #253/#259/Phase-7-Absätze, #83-Begründung, „Warum spec_file_path“, Epic-Details #589/#610, Erläuterungen Step 2/4 raus; „Auto-Modus prüfen“ bleibt |
| docs/befehle/50-implement.md, docs/befehle/60-validate.md | CREATE | verschobener Hintergrund, wörtlich |
| tests/test_commands_slim_674.py | CREATE | Größenwächter je Befehlstext (Budget-Tabelle), Verweis auf docs/befehle vorhanden, Datei existiert |
| skills/50-implement, skills/60-validate | MODIFY | regeneriert |
| CHANGELOG.md, plugin.json, CLAUDE.md, README.md, Marker | MODIFY | 4.25.5 |

### Scope Assessment
- Files: 2 Befehle, 2 neue Doku, 1 Test, Generate, Version
- Estimated LoC: Befehle ca. −150 / +40, Doku ca. +170, Test ca. +60 → unter 250 Produktivzeilen
- Risk Level: LOW (Anweisungstext, Doku, Tests; kein Hook-Code)

### Technical Approach
Abschnittsweise: Befehlsablauf, Aufrufe und alle von Tests gepinnten Wortlaute bleiben; reine Begründungen/Historie/Sonderfall-Erklärungen wörtlich nach `docs/befehle/<befehl>.md` mit gleichnamigen Überschriften; im Befehl ein Satz „Hintergrund: `docs/befehle/<befehl>.md` (Plugin-Ordner)“. Ziel −30 % je Datei (mehr ist ohne gepinnten Text nicht möglich); Gesamtziel −40 % über #677/#678.

### Dependencies
Siehe Kontext; zentrale Absicherung ist die bestehende Suite (≈ 30 Pin-Tests) + `sync_skills --check`.

### Open Questions
- keine (Schnitt-Aufteilung ist Technik, Folge-Issues #677/#678/#679 angelegt)
