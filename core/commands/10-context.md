# Phase 1: Context Generation

You are starting **Phase 1 - Context Generation** for a new workflow.

## Purpose

Before analysing, gather ALL relevant context. This prevents:
- Missing important related code
- Overlooking existing patterns
- Reinventing existing solutions

## Your Tasks

### 1. Start or Resume Workflow

```bash
python3 .claude/hooks/workflow.py start "[feature-name]"
```

Or switch to existing:
```bash
python3 .claude/hooks/workflow.py switch "[feature-name]"
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
python3 .claude/hooks/workflow.py phase phase2_analyse
```

## Next Step

Informiere den User mit folgender Zusammenfassung:

---
**Kontext gesammelt.**

Was ich gefunden habe: [Kurz beschreiben was relevant ist — z.B. welche bestehenden Bereiche betroffen sind, ob ähnliche Lösungen schon existieren, was zu beachten ist — keine Dateinamen oder Technik]

---

**Checkpoint — Vorbedingungen prüfen, bevor du unten etwas ausgibst:**

Gib das `✅`-Verdikt nur aus, wenn ALLE zutreffenden Punkte erfüllt sind:
- Phase im Workflow-State geschrieben — `python3 .claude/hooks/workflow.py status` bestätigt sie
- Alle Ergebnisdateien dieser Phase existieren auf der Platte
- Keine uncommitteten Änderungen an Dateien, die `/20-analyse` braucht
- Ab Phase 5: alle RED-Artefakte per `add-artifact` registriert
- Keine Erkenntnis, die für `/20-analyse` nötig und nirgends niedergeschrieben ist

Alle zutreffenden Punkte erfüllt → gib den Positiv-Block aus. Mindestens einer verletzt → gib stattdessen den Negativ-Block aus, mit dem konkreten Sicherungsschritt.

**Positiv-Block (alle Vorbedingungen erfüllt):**

---
**Gesichert auf der Platte:**
- `.claude/workflows/<name>.json` — Phase `phase2_analyse`, Verdict, Artefakt-Register
- `docs/context/<workflow-name>.md` — gesammelter Kontext: relevante Dateien, bestehende Muster, Dependencies/Dependents, bekannte Risiken

✅ **`/clear` ist jetzt gefahrlos** — alles oben Gelistete stellt der Folge-Befehl allein aus diesen Dateien wieder her. Im Gesprächsverlauf steht nichts, was verloren ginge.

1. `/clear`
2. `/20-analyse #<N>`

---

**Negativ-Block (mindestens eine Vorbedingung verletzt):**

---
⚠️ **`/clear` jetzt NICHT** — Folgendes steht nur im Gesprächsverlauf:
- <was fehlt> → sichern mit: <konkreter Befehl oder Schritt>

Erst sichern, dann ist `/clear` gefahrlos.

---

**IMPORTANT:** Do NOT skip to implementation. Context → Analyse → Spec → Implement.
