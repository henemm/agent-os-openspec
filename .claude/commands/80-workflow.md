<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->
---
description: "Manage workflows"
disable-model-invocation: true
---

# Workflow Management

Manage multiple parallel workflows with isolated state (v3).

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
```

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/80-workflow #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf — der komplette State überlebt jeden `/clear` und jeden Worktree. Alle anderen Argumente (`list`, `status`, `switch <name>` …) bleiben unverändert und laufen wie unten beschrieben:

```bash
ISSUE=42   # die übergebene Nummer (ohne #)
python3 - "$ISSUE" <<'PY'
import sys, json, glob, re, os
issue = sys.argv[1].lstrip('#')
pat = re.compile(rf'(^|[-_]){re.escape(issue)}([-_]|$)')
hits = []
for f in glob.glob('.claude/workflows/*.json'):
    name = os.path.basename(f)[:-5]
    if pat.search(name):
        d = json.load(open(f))
        hits.append((name, d.get('current_phase'), d.get('spec_file') or 'Not created', d.get('adversary_verdict'), d.get('affected_files', [])))
if not hits:
    print(f'KEIN laufender Workflow fuer #{issue} (evtl. abgeschlossen -> .claude/workflows/_archive/).')
else:
    for name, ph, spec, verd, aff in hits:
        print(f'GEFUNDEN: {name} | Phase={ph} | Spec={spec} | Verdict={verd}')
        if aff: print(f'  affected_files: {", ".join(aff)}')
    print('\nNAME=' + hits[0][0])
PY
```

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen). Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58):

```bash
$WF switch <NAME-aus-obigem-Output>
$WF status
```

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec/Verdict. **Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht**, inklusive des nächsten Pflicht-Schritts.

**Ohne Argument** gilt der Rest dieser Datei unverändert.

## Commands

### List All Workflows
```bash
$WF list
```

### List Active Sessions
```bash
$WF sessions
$WF sessions --json
```
Liest das Session-Register (`.claude/session-locks/*.json`), das `session_singleton_guard.py`
fuehrt: Agent-Name, Worktree, Branch, Workflow, Issue und Phase pro aktiver Session dieses
Projekts. Fehlende optionale Felder erscheinen in der Tabelle als `–`.

### Retro: Abgeschlossene Workflows analysieren
```bash
# Alle archivierten Workflows auflisten
$WF retro-list

# Zuletzt abgeschlossenen Workflow analysieren
$WF retro

# Bestimmten Workflow analysieren
$WF retro <name>
```
Zeigt: Phasen-Timeline mit Zeiten, Qualitätssignale (TDD, Adversary-Verdict, Fix-Loops), Optimierungshinweise.
Slash-Command: `/90-retro`

### Check Current Status
```bash
$WF status
```

### Start New Workflow
```bash
$WF start "feature-name"
```

### Switch Active Workflow
```bash
$WF switch "other-feature"
```

### Set Specific Phase
```bash
$WF phase phase4_approved
```

### Set Workflow Fields
```bash
$WF set-field spec_file "docs/specs/auth/login.md"
$WF set-field context_file "docs/context/login.md"
$WF set-affected-files src/auth.py src/login.py
```

### Register Test Artifacts
```bash
$WF add-artifact test_output \
    "docs/artifacts/feature/test-red.txt" \
    "Test FAILED: assertion error" \
    phase5_tdd_red
```

### Mark TDD RED Done
```bash
$WF mark-red "3 tests failed"
$WF mark-ui-red "UI test assertion"
```

### Write Execution Log (Required before complete)
```bash
$WF write-log success
$WF write-log partial
$WF write-log reverted
```
Writes `.claude/workflows/_log/YYYY-MM-DD_<name>.yaml` with phases completed,
adversary verdict, fix-loop count, LoC delta, and outcome.

### Override AMBIGUOUS Adversary Verdict
```bash
$WF override-ambiguous "reason for proceeding"
```
Required when adversary verdict is AMBIGUOUS and all findings are resolved.
Without this, `git commit` is blocked.

### Link to GitHub Issue
```bash
$WF set-field github_issue 42
```

### Override LoC Limit
```bash
$WF set-field loc_limit_override 500          # Produktivcode
$WF set-field test_loc_limit_override 800     # Testcode (eigenes Limit)
```

### Complete Workflow
```bash
# Requires execution log — will fail without write-log first
$WF finish
```

### Abandon Workflow (ehrlicher Abbruch ohne Abschluss-Gates)
```bash
# Fuer Workflows OHNE Pruefgegenstand (reine Analyse-/Kontext-Arbeit,
# nie in phase6_implement): complete verlangt ein Adversary-Verdict,
# das es hier nie geben kann. NICHT den workflow_type umklassifizieren,
# um das Gate loszuwerden — stattdessen:
$WF abandon --reason "Analyse-Vorlauf, Umsetzung in FEAT_002 abgeschlossen"
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
# Validate test output and set adversary verdict
python3 ${_H}/qa_gate.py docs/artifacts/feature/test-output.txt
python3 ${_H}/qa_gate.py docs/artifacts/feature/test-output.txt --screenshot screenshot.png
python3 ${_H}/qa_gate.py docs/artifacts/feature/test-output.txt --infra --no-visual "pure infrastructure"
```

## Migration from v2

```bash
python3 ${_H}/migrate_state.py          # Dry run
python3 ${_H}/migrate_state.py --apply   # Actually migrate
```

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /80-workflow · agent-os-openspec 3.30.0

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von zwei Formen: `❗ Du: …`, wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist niemals „nichts zu tun“. Oder `ℹ️ Nichts zu tun: <du arbeitest gerade selbst / wartest auf ein Ergebnis, z. B. einen Hintergrund-Agenten> — danach: /<befehl> #<N>`, ausschließlich wenn du auf etwas ANDERES als den PO wartest. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase übernimmst du aus dem Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — Phase und Schritt wörtlich von dort. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfallen die erste Zeile und die Statuszeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.
