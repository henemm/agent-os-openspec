<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->
---
description: "Register a test artifact in the workflow"
disable-model-invocation: true
---

# Add Test Artifact

Register a **REAL** test artifact for TDD workflow validation.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
```

## Purpose

TDD requires proof that tests were executed with REAL data:
- Screenshots showing actual test output
- Log files from actual test runs
- API responses from actual calls
- Email content from actual sends

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/81-add-artifact #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf — ein Artefakt landet im State des AKTIVEN Workflows; steht der falsche aktiv, geht der Beweis an die falsche Stelle:

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

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec. **Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** — die Phase entscheidet, als welche Phase das Artefakt registriert wird.

**Ohne Argument** wird der aktive Workflow verwendet.

## Usage

When you have captured a test artifact:

1. **Save the artifact** to `docs/artifacts/[workflow-name]/`

2. **Register it**:
```bash
$WF add-artifact screenshot \
    "docs/artifacts/[workflow]/screenshot.png" \
    "Screenshot showing test failure: expected X but got Y" \
    phase5_tdd_red
```

## Artifact Types

| Type | Extensions | Min Size | Use For |
|------|------------|----------|---------|
| `screenshot` | .png, .jpg, .gif | 1KB | UI tests, error screens |
| `email` | .eml, .txt | 100B | Email notifications |
| `api_response` | .json, .xml | 10B | API integration tests |
| `log` | .log, .txt | 10B | Test execution logs |
| `test_output` | .txt, .json | 10B | Test runner output |
| `ui_test_output` | .txt, .log | 10B | UI test runner output |
| `video` | .mp4, .mov | 10KB | UI flow recordings |

## Requirements

Artifacts MUST be:
- **Real files** - Not placeholders
- **Non-empty** - Minimum size enforced
- **Recent** - Less than 24 hours old
- **Described** - What does this prove?

## RED Phase Artifacts

For TDD RED phase (`phase5_tdd_red`), artifacts must show **test failure**:
- Description should mention: fail, error, assertion, expected/actual

## Validate Phase Artifacts

For validation (`phase7_validate`), artifacts show **test success**:
- Description should mention: pass, success, verified, works

## Example

```bash
# After running failing test, capture the output
./run-tests.sh > docs/artifacts/feature-login/test-output-red.txt 2>&1

# Register it
$WF add-artifact test_output \
    "docs/artifacts/feature-login/test-output-red.txt" \
    "Test failed: LoginService.authenticate() not implemented - assertion error on line 42" \
    phase5_tdd_red
```

## Shorthand: Mark RED Done

```bash
$WF mark-red "3 tests failed as expected"
$WF mark-ui-red "UI test assertion error"
```

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /81-add-artifact · agent-os-openspec 3.30.0

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von zwei Formen: `❗ Du: …`, wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist niemals „nichts zu tun“. Oder `ℹ️ Nichts zu tun: <du arbeitest gerade selbst / wartest auf ein Ergebnis, z. B. einen Hintergrund-Agenten> — danach: /<befehl> #<N>`, ausschließlich wenn du auf etwas ANDERES als den PO wartest. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase übernimmst du aus dem Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — Phase und Schritt wörtlich von dort. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfallen die erste Zeile und die Statuszeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.
