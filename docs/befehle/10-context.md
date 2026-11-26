# Hintergrund zu /10-context

Begründungen und Sonderfälle zu core/commands/10-context.md; der Befehlstext enthält Ablauf und Pflichtschritte.

## Purpose

Before analysing, gather ALL relevant context. This prevents:
- Missing important related code
- Overlooking existing patterns
- Reinventing existing solutions

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/10-context #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf — der komplette State überlebt jeden `/clear` und jeden Worktree.

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen). Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58).

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec. **Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** — und überspringe dann Schritt 1: ein gefundener Workflow wird NICHT neu gestartet.

Meldet der Block `KEIN laufender Workflow`, sag das und frage, ob ein neuer Workflow zu dieser Nummer starten soll. **Ohne Argument** geht es direkt bei Schritt 1 weiter.

## Start or Resume Workflow

`--issue <N>` nur, wenn die Issue-Nummer bekannt ist — sonst weglassen (die Nummer kommt dann
aus dem Namen).

`start` registriert die Sitzung am Issue (#461). Bricht er ab, weil dort schon eine andere
Sitzung registriert ist, entsteht kein Workflow: dem PO sagen, wer wo seit wann daran arbeitet;
`--uebernehmen` nur, wenn die andere Sitzung nachweislich ruht (`workflow.py claim status`)
oder der PO zustimmt.

## Gather Context (Erläuterungen)

1. **Related Files** - Find all files that might be relevant
   ```
   Grep for: keywords, function names, class names
   Glob for: related file patterns
   ```

2. **Existing Specs** - Check `docs/specs/` for related entities

3. **Similar Implementations** - How does the codebase handle similar things?

4. **Dependencies** - What does the affected code depend on?

5. **Dependents** - What depends on the code we'll change?

**Kontext-Haushalt (Nachschlagen abgeben, gezielt lesen):** Nachschlagefragen („Wo wird X benutzt?“, „Welche Dateien importieren Y?“, „Wie heißt die Funktion für Z?“) gehen an einen Explore-Teilagenten (Haiku), der mit eigenem, kleinem Kontext liest und nur die Antwort zurückgibt — Recherche ist der größte Token-Posten, und im Hauptkontext zahlt jeder Schritt das Wiederlesen aller vorher gelesenen Dateien erneut. Selbst liest du nur, was du gleich brauchst, mit Zeilenbereich (`sed -n 120,160p`, Read mit offset/limit) oder gezielter Suche statt ganzer Dateien. Mehrere `grep`/`sed -n` zur selben Frage in einen Aufruf bündeln; Workflow-Aufrufe mit `workflow.py batch a -- b -- c` zusammenfassen.

## Vorlage Kontext-Dokument

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

## Update Workflow State

Erst das Kontext-Dokument im State eintragen — der Phasenwechsel nach `phase2_analyse` verlangt das Feld `context_file`.

## Auto-Modus: Kette selbst fortsetzen (#472)

Bei `AUTONOMY=auto` und ohne `/clear` in derselben Session: Rufe den Skill `20-analyse` jetzt sofort selbst auf — warte nicht auf eine User-Eingabe. Der Checkpoint-Block oben bleibt trotzdem in der Ausgabe (Wiedereinstieg über `/20-analyse #<N>`). Bei `AUTONOMY=manual` (oder jeder anderen Ausgabe): wie bisher auf den User warten.

## Kontext-Haushalt beim Selbstaufruf

Ein Schritt mit 200k Token Kontext kostet etwa das Fünffache eines Schritts mit 40k. Bei `CONTEXT_STOP=off` (auch mit `CONTEXT_REASON=AUTO_NO_CLEAR`: Auto-Modus, niemand tippt `/clear`, Nachschlagen an Teilagenten abgeben, Claude Code komprimiert automatisch) oder `CONTEXT_TOKENS=unknown`: Kette unverändert selbst fortsetzen (#658).
