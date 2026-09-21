---
description: "Run tests"
disable-model-invocation: false
---

# Tests ausfuehren

Starte den `test-runner` Agenten aus `core/agents/test-runner.md`.

---

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
```

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/82-test #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf — der komplette State überlebt jeden `/clear` und jeden Worktree:

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

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec. **Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** — `affected_files` und `test_files` aus dem State gehören in den Auftrag an den Test-Runner.

**Ohne Argument** laufen die Tests des aktuellen Projekts.

---

## Anweisung

1. Ermittle das passende Test-Kommando fuer das Projekt
2. Fuehre alle Tests aus
3. Fasse Ergebnisse kurz und verstaendlich zusammen
4. Bei Failures: Zeige betroffene Dateien und Fehlermeldungen

---

## Output Format

**Bei Erfolg:**
```
Tests: X passed
Status: Alles gruen
```

**Bei Failures:**
```
Tests: X passed, Y failed
Fehlgeschlagen:
- TestClass.testMethod: [Fehlermeldung]

Betroffene Dateien:
- [Pfad]
```

---

## Zero Tolerance Policy

- ALLE Tests muessen gruen sein vor Commit
- Bei Failures: Nicht committen, erst fixen
- Keine Ausnahmen

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen zwei Zeilen, in dieser Reihenfolge:

Workflow `<name>` · Phase `<x>` von 8 · Nächster Pflicht-Schritt: `/<befehl> #<N>`
⚙ /82-test · agent-os-openspec 3.27.1

Die Statuszeile übernimmst du aus dem Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert — Phase und Schritt wörtlich von dort. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfällt die Statuszeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In der Statuszeile ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Beide Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die Statuszeile entfällt.
