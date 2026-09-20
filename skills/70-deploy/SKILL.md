---
description: "Deploy to production"
disable-model-invocation: true
---

# Deploy to Production

Deploy the current main branch to production.

**CUSTOMIZE THIS FILE for your project's deployment setup!**

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
```

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/70-deploy #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf — der komplette State überlebt jeden `/clear` und jeden Worktree:

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

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Verdict. **Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** — steht er vor `phase8_complete`, nenne den offenen Pflicht-Schritt, bevor du deployst.

**Ohne Argument** geht es direkt mit den Pre-Flight-Checks weiter.

## Pre-Flight Checks

Before deploying, verify:

```bash
# Current branch
git branch --show-current

# Uncommitted changes?
git status --porcelain

# Main is up to date with remote?
git fetch origin main
git log HEAD..origin/main --oneline
```

**STOP if:**
- Uncommitted changes exist -> Commit or stash first
- Main is behind origin -> Run `git pull` first
- Tests are failing -> Fix tests first

## Deployment Steps

### Option A: Git-based Deployment

```bash
# Ensure on main
git checkout main

# Push to main (if not already)
git push origin main

# Merge to production branch
git checkout production
git merge main --no-edit
git push origin production

# Return to main
git checkout main
```

### Option B: Direct Deployment (customize for your platform)

**For Vercel:**
```bash
vercel --prod
```

**For Google Cloud Run:**
```bash
gcloud builds submit --config=cloudbuild.yaml
```

**For AWS:**
```bash
aws ecs update-service --cluster <cluster> --service <service> --force-new-deployment
```

**For Heroku:**
```bash
git push heroku main
```

## Post-Deployment Verification

1. **Check deployment status** (platform-specific)
2. **Verify application is running:**
   - Open production URL
   - Check health endpoint
   - Verify key functionality

3. **Monitor logs for errors:**
   ```bash
   # Example for various platforms
   # vercel logs
   # gcloud run services logs read <service>
   # heroku logs --tail
   ```

## Rollback (if needed)

```bash
# Git-based rollback
git checkout production
git revert HEAD
git push origin production
```

## Configuration

Customize this template by updating:
- Deployment commands for your platform
- Production URL
- Health check endpoints
- Log viewing commands
- Rollback procedures

---

**Note:** This is a template. Copy to your project and customize for your specific deployment setup.

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen zwei Zeilen, in dieser Reihenfolge:

Workflow `<name>` · Phase `<x>` von 8 · Nächster Pflicht-Schritt: `/<befehl> #<N>`
⚙ /70-deploy · agent-os-openspec 3.25.0

Die Statuszeile übernimmst du aus dem Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert — Phase und Schritt wörtlich von dort. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfällt die Statuszeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In der Statuszeile ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Beide Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die Statuszeile entfällt.
