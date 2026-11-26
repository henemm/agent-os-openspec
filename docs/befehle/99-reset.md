# Hintergrund zu /99-reset

Begründungen, Tabellen und Sonderfälle zu core/commands/99-reset.md; der Befehlstext enthält Wiedereinstieg und Abschlussbefehle.

## When to Use

| Situation | Action |
|-----------|--------|
| Workflow completed successfully | `/99-reset` |
| Need to abort current workflow | `/99-reset` |
| Starting a completely new task | `/99-reset` |

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

Dieser Befehl archiviert den **aktiven** Workflow — steht der falsche aktiv, trifft es fremde Arbeit.

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen). Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58).

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec/Verdict.

## What Happens

Completes and archives the current workflow, or removes it if in early phases. Workflows ohne Bau (PO-Entscheidung „nichts bauen" oder keine Spec) werden per `abandon` archiviert.

## Next Steps

After reset, start a new workflow:

```
/10-context               → Gather context first
/20-analyse [feature/bug] → Start analysis
```

Or start fresh with a new workflow directly: `python3 .claude/hooks/workflow.py start "new-feature"`.

---

*Use reset for clean starts. Don't carry state from abandoned work.*
