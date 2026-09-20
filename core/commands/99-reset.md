# Reset Workflow

Reset the workflow state to start fresh.

## When to Use

| Situation | Action |
|-----------|--------|
| Workflow completed successfully | `/99-reset` |
| Need to abort current workflow | `/99-reset` |
| Starting a completely new task | `/99-reset` |

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/99-reset #<N>` aufgerufen?** Dann löse den Workflow ZUERST von der Platte auf. Dieser Befehl archiviert den **aktiven** Workflow — steht der falsche aktiv, trifft es fremde Arbeit:

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
python3 .claude/hooks/workflow.py switch <NAME-aus-obigem-Output>
python3 .claude/hooks/workflow.py status
```

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec/Verdict. **Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** — steht er vor `phase8_complete`, nenne den offenen Pflicht-Schritt und frage nach, bevor du abschließt.

**Ohne Argument** wird der aktive Workflow abgeschlossen.

## What Happens

Completes and archives the current workflow, or removes it if in early phases.

## Execute Reset

```bash
# Complete and archive the current workflow
python3 .claude/hooks/workflow.py finish

# Or start fresh with a new workflow
python3 .claude/hooks/workflow.py start "new-feature"
```

## Next Steps

After reset, start a new workflow:

```
/10-context               → Gather context first
/20-analyse [feature/bug] → Start analysis
```

---

*Use reset for clean starts. Don't carry state from abandoned work.*
