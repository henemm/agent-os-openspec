---
description: "Gather context for a new feature or bug fix"
disable-model-invocation: false
---

# Phase 1: Context Generation

You are starting **Phase 1 - Context Generation** for a new workflow.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
```

## Purpose

Before analysing, gather ALL relevant context. This prevents:
- Missing important related code
- Overlooking existing patterns
- Reinventing existing solutions

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/10-context #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf — der komplette State überlebt jeden `/clear` und jeden Worktree:

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

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec. **Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** — und überspringe dann Schritt 1: ein gefundener Workflow wird NICHT neu gestartet.

Meldet der Block `KEIN laufender Workflow`, sag das und frage, ob ein neuer Workflow zu dieser Nummer starten soll. **Ohne Argument** geht es direkt bei Schritt 1 weiter.

## Your Tasks

### 1. Start or Resume Workflow

```bash
$WF start "[feature-name]"
```

Or switch to existing:
```bash
$WF switch "[feature-name]"
```

### 2. Gather Context

Search and collect:

1. **Related Files** - Find all files that might be relevant
   ```
   Grep for: keywords, function names, class names
   Glob for: related file patterns
   ```

2. **Existing Specs** - Check `docs/specs/` for related entities

3. **Similar Implementations** - How does the codebase handle similar things?

4. **Dependencies** - What does the affected code depend on?

5. **Dependents** - What depends on the code we'll change?

### 3. Create Context Document

Create `docs/context/[workflow-name].md`:

```markdown
# Context: [Workflow Name]

## Request Summary
[1-2 sentences: what the user wants]

## Related Files
| File | Relevance |
|------|-----------|
| path/to/file.py | Contains X which we need to modify |

## Existing Patterns
- Pattern 1: How similar things are done
- Pattern 2: ...

## Dependencies
- Upstream: [what our code uses]
- Downstream: [what uses our code]

## Existing Specs
- `docs/specs/category/entity.md` - Related spec

## Risks & Considerations
- Risk 1
- Risk 2
```

### 4. Update Workflow State

```bash
$WF phase phase2_analyse
```

## Next Step

### Checkpoint prüfen (Anweisung an dich — nicht ausgeben)

Prüfe der Reihe nach, bevor du unten etwas ausgibst:

- Phase im Workflow-State geschrieben — `$WF status` bestätigt sie
- Alle Ergebnisdateien dieser Phase liegen auf der Platte
- Keine Erkenntnis, die für `/20-analyse` nötig und nirgends niedergeschrieben ist

Sind alle Punkte erfüllt: Gib den Positiv-Block aus. Ist mindestens einer verletzt: Gib stattdessen den Negativ-Block aus und ersetze dessen Platzhalter durch den konkreten Sicherungsschritt.

Weder diese Anweisung noch die `###`-Überschriften gehören in die Ausgabe — an den User geht ausschließlich der Text zwischen den `---`-Trennern, und zwar genau einmal, als letzter inhaltlicher Teil der Nachricht: keine Vorab- oder Kurzfassung davor, keine Wiederholung danach.

### Ausgabe: Zusammenfassung (immer)

---
**Kontext gesammelt.**

Was ich gefunden habe: [Kurz beschreiben was relevant ist — z.B. welche bestehenden Bereiche betroffen sind, ob ähnliche Lösungen schon existieren, was zu beachten ist — keine Dateinamen oder Technik]

---

### Ausgabe A: Positiv-Block (alle Vorbedingungen erfüllt)

---
**Gesichert auf der Platte:**
- `.claude/workflows/<name>.json` — Phase `phase2_analyse`, Verdict, Artefakt-Register
- `docs/context/<workflow-name>.md` — gesammelter Kontext: relevante Dateien, bestehende Muster, Dependencies/Dependents, bekannte Risiken

✅ **`/clear` ist jetzt gefahrlos** — alles oben Gelistete stellt der Folge-Befehl allein aus diesen Dateien wieder her. Im Gesprächsverlauf steht nichts, was verloren ginge.

1. `/clear`
2. `/20-analyse #<N>`

---

### Ausgabe B: Negativ-Block (mindestens eine Vorbedingung verletzt)

---
⚠️ **`/clear` jetzt NICHT** — Folgendes steht nur im Gesprächsverlauf:
- <was fehlt> → sichern mit: <konkreter Befehl oder Schritt>

Erst sichern, dann ist `/clear` gefahrlos.

---

**IMPORTANT:** Do NOT skip to implementation. Context → Analyse → Spec → Implement.

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /10-context · agent-os-openspec 3.28.3

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von zwei Formen: `❗ Du: …`, wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist niemals „nichts zu tun“. Oder `ℹ️ Nichts zu tun: <du arbeitest gerade selbst / wartest auf ein Ergebnis, z. B. einen Hintergrund-Agenten> — danach: /<befehl> #<N>`, ausschließlich wenn du auf etwas ANDERES als den PO wartest. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase übernimmst du aus dem Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — Phase und Schritt wörtlich von dort. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfallen die erste Zeile und die Statuszeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.
