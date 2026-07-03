---
description: "Reset or complete the current workflow"
disable-model-invocation: true
---

# Reset Workflow

Reset the workflow state to start fresh.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
```

## When to Use

| Situation | Action |
|-----------|--------|
| Workflow completed successfully | `/99-reset` |
| Need to abort current workflow | `/99-reset` |
| Starting a completely new task | `/99-reset` |

## What Happens

Completes and archives the current workflow, or removes it if in early phases.

## Execute Reset

```bash
# Complete and archive the current workflow
$WF complete

# Or start fresh with a new workflow
$WF start "new-feature"
```

## Next Steps

After reset, start a new workflow:

```
/10-context               → Gather context first
/20-analyse [feature/bug] → Start analysis
```

---

*Use reset for clean starts. Don't carry state from abandoned work.*
