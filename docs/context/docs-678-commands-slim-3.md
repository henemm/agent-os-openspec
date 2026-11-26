# Context: docs-678-commands-slim-3

## Request Summary
Schnitt 3 von #674 (Epic #649): `20-analyse`, `70-deploy`, `40-tdd-red`, `10-context` und die kleinen Befehle (`01-feature`, `81-add-artifact`, `82-test`, `83-user-story`, `90-retro`, `99-reset`) kürzen. Danach gilt das Gesamtziel: `core/commands/*.md` zusammen ≤ 83 KB (−40 % gegenüber 138 946 B). Stand nach #677: 108 646 B.

## Related Files
| File | Relevance |
|------|-----------|
| core/commands/{10,20,40,70,01,81,82,83,90,99}*.md | zu kürzende Befehlstexte |
| core/commands/60-validate.md | 20 286 B, zweiter Durchgang nötig (s. Analyse) |
| docs/befehle/*.md | Hintergrund, wörtlich verschoben, je ≥ 3 `## `-Abschnitte |
| tests/test_commands_slim_674.py | BUDGETS je Befehl, LINKED |
| skills/*/SKILL.md, .claude/commands/{70,81,99}.md | Generat: `scripts/sync_skills.py`, `setup.py . --refresh-aliases` |

## Pin-Tests (Wortlaute, die bleiben müssen; Explore-Sammlung)
- Global: `python3 .claude/hooks/workflow.py find 42` in mind. 12 Befehlen (10,20,30,40,50,60,70,80,81,82,83,99 — keiner darf ihn verlieren); Wiedereinstieg (10,20,40,70,81,82,83,99): `/<name> #`, `workflow.py find|switch|status`, `in 2 Sätzen`; keine `/tmp/`; max. 1 `ScheduleWakeup(` ≥1200; Agent-Aufrufe Explore/Plan/general-purpose mit `model=`; je Befehl außer 01 mind. ein `.claude/hooks/`-Verweis, 01 keiner; Vorlagen-Blöcke ohne Git-Wörter; feature-planner nur in 01, test-runner nur in 82; user-story-planner nirgends.
- 10/20/40: Checkpoint-Gerüst bytegleich (Überschriften, Bullets, A/B-Blöcke, Phase im Positiv-Block), Kontext-Absatz (`workflow.py context\``, Kontext-Haushalt, CONTEXT_STOP=on/off, `` `<next>` NICHT selbst aufrufen ``, `` ❗Du-Zeile `/<next> #<N>` ``, Default 100.000 Token, manual), Immer-menschlich-Zeile, `AUTONOMY=auto`, `workflow.py autonomy`, `` Rufe den Skill `<next>` jetzt sofort selbst auf ``.
- 10: `set-field context_file docs/context/[workflow-name].md` vor `phase phase2_analyse`; `--uebernehmen`, „registrier“; `Explore-Teilagenten`, `Zeilenbereich`, `workflow.py batch`.
- 20: `### Step 2b` (00-intake verweist), bug-intake ohne model + Fallback general-purpose haiku; `automatisch erneut aufgerufen`, `TaskList`, `TaskStop`; `offene Frage(n)` nahe Kettensatz.
- 40: `Register Artifacts` → `workflow.py mark-red` → `phase phase6_implement`; `` jetzt: `phase6_implement` ``; Kettensatz zwischen Ausgabe-B-`---` und `## Common Mistakes`.
- 70: `## Step 4` + `**b) Fachlicher Befund**` (docs/befehle/60-validate.md verweist); deploy-config, DEPLOY_CONFIGURED=no, `in \`openspec.yaml\` unter \`deploy:\``, deploy-status running/done/failed, BROKEN-Pfad-Wörter (Kontingent, Korrektur-PR, archiviert, derselben Issue-Nummer, am Workflow vorbei), endstate/`endstate <name>`, Kette-Absatz (FOOTER, aus deinem Auftrag, /00-intake #M, ENDSTATE=waiting, queue), handoff-Abschnitt (create_session, --mark cloud, --start, inline, HANDOFF_DONE= + „keine weitere Sitzung“ in 400 Z.).
- 82: Ausgabezeilen `Tests: … passed …` mit `übersprungen`; „0 bestanden … übersprungen … nicht grün“; test-runner-Aufruf + Fallback haiku.
- 90: `/90-retro #<N>`, `.claude/workflows/_archive/*.json`, `` kein `workflow.py switch` ``.
- 99: `workflow.py abandon --reason`, `no_build_reason`, `spec_file`; kein `{{OPENSPEC_VERSION}}`.
- 01: feature-planner ohne model, Fallback general-purpose sonnet in 600 Z.; kein `.claude/hooks/`.

## Existing Patterns
- #674/#677: Befehl behält Ablauf + gepinnte Wortlaute, Satz „Hintergrund (Begründungen, Sonderfälle): `docs/befehle/<befehl>.md` im Plugin-Ordner — nur bei Bedarf lesen.“; Doku mit `##`-Abschnitten, Text wörtlich verschoben.

## Dependencies
- Upstream: sync_skills.py, setup.py-Aliase. Downstream: jede Sitzung lädt die Skills.

## Risks & Considerations
- Fest gepinnte Blöcke (Checkpoint ≈ 2,0–2,3 KB, Kontext-Absatz ≈ 0,6–0,9 KB, Kettensätze) begrenzen 10/20/40 auf ≈ 5–6,5 KB.
- Kleine Befehle tragen je ≈ 0,5 KB Wiedereinstieg.

## Analysis

### Type
Feature (Doku-/Anweisungstext, kein Gate-Code)

### Rechnung
Nicht angefasst: 50 (15 019) + 60 (20 286) + 00 (7 907) + 30 (8 575) + 80 (4 761) = 56 548 B. Für ≤ 83 000 B gesamt blieben den zehn Befehlen 26 452 B (−49 %). Schätzung nach Pins: 10 ≈ 4,9 KB, 20 ≈ 6,4 KB, 40 ≈ 5,2 KB, 70 ≈ 5,5 KB, sechs kleine ≈ 9,6 KB → ≈ 31,6 KB. Das Ziel ist ohne zweiten Durchgang an `60-validate.md` (größter Befehl, 20 KB) nicht erreichbar.

| Variante | Summe core/commands | Ziel erreicht |
|---|---|---|
| nur die zehn Befehle | ≈ 88 KB | nein |
| zehn Befehle + 60-validate ≤ 16 KB | ≈ 83 KB | knapp ja |

Entscheidung (Tech Lead): 60-validate.md bekommt einen zweiten Durchgang (≤ 16 384 B); das erfüllt die DoD von #678/#674 ohne Gate-Änderung.

### Affected Files
| File | Change | Description |
|---|---|---|
| core/commands/10,20,40,70,01,81,82,83,90,99, 60 | MODIFY | gekürzt |
| docs/befehle/10-context.md, 20-analyse.md, 40-tdd-red.md, 70-deploy.md, 83-user-story.md, 81-add-artifact.md | CREATE | Hintergrund wörtlich |
| docs/befehle/60-validate.md | MODIFY | weiterer Hintergrund |
| tests/test_commands_slim_674.py | MODIFY | Budgets senken, LINKED erweitern |
| tests/test_commands_slim_678.py | CREATE | Gesamt ≤ 83 000 B |
| skills/*, .claude/commands/{70,81,99}.md | MODIFY | regeneriert |

### Scope / Risiko
11 Befehlstexte, nur Anweisungstext → Risiko niedrig (adversary_dialog risk: Doku).

### Open Questions
- keine
