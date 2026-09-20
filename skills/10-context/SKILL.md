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

Beende deine letzte Nachricht in diesem Befehl mit genau dieser Zeile:

⚙ /10-context · agent-os-openspec 3.24.0

Wörtlich, unverändert, genau einmal. Sie steht **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` — als allerletzte Zeile der Nachricht.
