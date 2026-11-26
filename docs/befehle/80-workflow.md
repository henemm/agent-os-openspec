# Hintergrund zu /80-workflow

Begründungen, Sonderfälle und Referenzteil zu core/commands/80-workflow.md; der Befehlstext enthält die Befehlsübersicht und Pflichtschritte.

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

Der komplette State überlebt jeden `/clear` und jeden Worktree.

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen). Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58):

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec/Verdict. **Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht**, inklusive des nächsten Pflicht-Schritts.

## Commands: Erläuterungen

### List Active Sessions
Liest das Session-Register (`.claude/session-locks/*.json`), das `session_singleton_guard.py`
fuehrt: Agent-Name, Worktree, Branch, Workflow, Issue und Phase pro aktiver Session dieses
Projekts. Fehlende optionale Felder erscheinen in der Tabelle als `–`.

### Endzustand der Fußzeile (#550)
`endstate` gibt die Schlusszeile des Workflows aus — immer eine von drei Formen:
`✅ Erledigt` (nichts offen), `⏳ Läuft noch` (z. B. Deploy/CI läuft, was wartet), `❗ Du`
(der PO muss handeln). `waiting` setzt bzw. löscht (`--clear`) den Vermerk „läuft noch";
ein Phasenwechsel leert ihn automatisch.

### Auftragsliste (#551)
Sichert einen Mehr-Issue-Auftrag der laufenden Sitzung im Haupt-Repo (überlebt `/clear`):
`.claude/auftrag/<sitzung>.json` (herdr-Workspace, sonst Sitzungs-Id), ohne beides
`.claude/auftrag.json`; andere Sitzungen sehen ihn nicht (#613).
Ausgabe `QUEUE=`, `AUTARK=`, `NEXT=` und bei offenem Auftrag `PROMPT=/00-intake #<NEXT>`,
mit Sitzungskennung `OWNER=` und ggf. `ALTAUFTRAG=` (Auftrag ohne laufende Sitzung);
`complete` hakt das Issue ab, `endstate` nennt danach das nächste Issue. Kill-Switch
`auftrag.enabled: false` → `QUEUE=disabled`.

### Übergabe an eine frische Sitzung (#667)
Wählt für das nächste Issue eines autarken Auftrags (Autonomie `auto`) den Weg:
`HANDOFF=cloud` (`CLAUDE_CODE_REMOTE=true`, dazu `REPO_URL=`), `herdr` (Herdr-Pane und `claude`
im PATH), `inline` (bisheriger Selbstaufruf) oder `none`; dazu `NEXT=` und der Startauftrag
zwischen `PROMPT_BEGIN`/`PROMPT_END` (Auftrag neu anlegen, 00-intake, Haltregel, Messung).
`--start` meldet `STARTED=yes|no|already` (bei `no` mit `REASON=`), `--mark cloud|herdr`
vermerkt den Start im Auftrag (Feld `handoff`); derselbe Vermerk ergibt `STARTED=already`.
Ist für `NEXT` schon ein Start vermerkt, folgt `HANDOFF_DONE=<weg>` (#668: keine zweite
Sitzung starten). `--mark` meldet `MARKED=yes|no`; scheitert der Vermerk, folgt
`WARN=Vermerk fehlgeschlagen (<Typ>)` (bei `--start` bleibt dann `STARTED=yes`).
Exit 0; nur ungültige Argumente (etwa `--mark` mit anderem Weg) enden mit Usage und Exit 1.

### Retro: Abgeschlossene Workflows analysieren
```bash
# Alle archivierten Workflows auflisten
python3 .claude/hooks/workflow.py retro-list

# Zuletzt abgeschlossenen Workflow analysieren
python3 .claude/hooks/workflow.py retro

# Bestimmten Workflow analysieren
python3 .claude/hooks/workflow.py retro <name>
```
Zeigt: Phasen-Timeline mit Zeiten, Qualitätssignale (TDD, Adversary-Verdict, Fix-Loops), Optimierungshinweise.
Slash-Command: `/90-retro`

### Write Execution Log (Required before complete)
Writes `.claude/workflows/_log/YYYY-MM-DD_<name>.yaml` with phases completed,
adversary verdict, fix-loop count, LoC delta, and outcome.

### Override AMBIGUOUS Adversary Verdict
Required when adversary verdict is AMBIGUOUS and all findings are resolved.
Without this, `git commit` is blocked.

### Complete Workflow
```bash
# Requires execution log — will fail without write-log first
python3 .claude/hooks/workflow.py finish
```

### Abandon Workflow (ehrlicher Abbruch ohne Abschluss-Gates)
```bash
# Fuer Workflows OHNE Pruefgegenstand (reine Analyse-/Kontext-Arbeit,
# nie in phase6_implement): complete verlangt ein Adversary-Verdict,
# das es hier nie geben kann. NICHT den workflow_type umklassifizieren,
# um das Gate loszuwerden — stattdessen:
python3 .claude/hooks/workflow.py abandon --reason "Analyse-Vorlauf, Umsetzung in FEAT_002 abgeschlossen"
```
Archiviert mit Status `abandoned` (nicht `complete`) — in `retro-list`
als "abgebrochen" sichtbar. Die Begruendung ist Pflicht.

## Workflow Phases

| Phase | Name | Description |
|-------|------|-------------|
| `phase0_idle` | Idle | No workflow started |
| `phase1_context` | Context | Gathering relevant context |
| `phase2_analyse` | Analysis | Analysing requirements |
| `phase3_spec` | Specification | Writing spec |
| `phase4_approved` | Approved | User approved spec |
| `phase5_tdd_red` | TDD RED | Writing failing tests |
| `phase6_implement` | Implementation | Writing code (TDD GREEN) |
| `phase6b_adversary` | Adversary | Adversary verification |
| `phase7_validate` | Validation | Final validation |
| `phase8_complete` | Complete | Ready for commit |

## State Architecture (v3)

Each workflow gets its own JSON file in `.claude/workflows/`:

```
.claude/workflows/
├── .active              ← Symlink to active workflow
├── feature-login.json   ← Isolated state
├── bugfix-crash.json    ← Isolated state
└── _archive/            ← Completed workflows
```

## Code Modification Rules

Code files can only be modified in:
- `phase6_implement`
- `phase6b_adversary`
- `phase7_validate`
- `phase8_complete`

And only if:
- TDD RED phase artifacts exist
- Spec has `## Acceptance Criteria` with at least one `AC-N` entry
- LoC delta does not exceed project limit — separately for Produktivcode
  (`max_loc_delta`, default 250) and Testcode (`max_test_loc_delta`, default 500);
  only added lines count, not `added + deleted` (Issue #94)

## Phase Transition Audit Trail

Every `workflow.py phase <target>` call is logged:
```json
{"from": "phase3_spec", "to": "phase4_approved", "at": "...", "trigger": "user_keyword"}
```
`trigger` values: `user_keyword` | `command` | `manual`

Manual skips (e.g. phase2 → phase6) emit a warning but are not blocked.
Fix-loop counter increments each time phase6_implement is re-entered from phase6b_adversary.

## Execution Log

Written to `.claude/workflows/_log/YYYY-MM-DD_<name>.yaml`:
```yaml
workflow_id: feature-login
project: my-app
phases_completed: [phase1_context, phase2_analyse, ...]
phases_skipped: []
tdd_red_confirmed: true
adversary_verdict: VERIFIED
adversary_fix_loop_iterations: 1
scope_loc_delta: +142
outcome: success
```

## Automatic Phase Detection

Some phase transitions happen automatically:
- User says "approved" → `phase4_approved`
- `/10-context` completed → `phase1_context`
- `/20-analyse` completed → `phase2_analyse`
- `/30-write-spec` completed → `phase3_spec`

## QA Gate (Adversary Validation)

```bash
# Run qa_gate.test_command (config.yaml), validate it and set adversary verdict —
# needs --checklist for commit/phase 8 (#253); output: docs/artifacts/<wf>/test-run-output.txt
python3 .claude/hooks/qa_gate.py --run
python3 .claude/hooks/qa_gate.py --run --screenshot screenshot.png
python3 .claude/hooks/qa_gate.py --run --infra --no-visual "pure infrastructure"
```

`qa_gate.require_run: true` (#404): commit and phase 8 need a green run stamp (`qa_run_stamp`)
matching the current code and `qa_gate.test_command`; the legacy file mode `qa_gate.py <file>`
is then refused.

## Migration from v2

```bash
python3 .claude/hooks/migrate_state.py          # Dry run
python3 .claude/hooks/migrate_state.py --apply   # Actually migrate
```
