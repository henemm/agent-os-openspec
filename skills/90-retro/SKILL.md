---
description: "/90-retro — Workflow-Retro"
disable-model-invocation: false
---

# Workflow-Retro

Analysiere einen abgeschlossenen Workflow aus dem Archiv: Zeiten pro Phase, Qualitätssignale, Optimierungshinweise.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
```

## Verwendung

```
/90-retro            → zuletzt abgeschlossenen Workflow analysieren
/90-retro <name>     → bestimmten archivierten Workflow analysieren
/90-retro list       → alle archivierten Workflows auflisten
```

## Ablauf

### Schritt 1 — Argument prüfen

Wenn der User `/90-retro list` aufruft:

```bash
$WF retro-list
```

Zeige die Ausgabe und frage: "Welchen Workflow möchtest du analysieren?"
Dann `retro <name>` mit der Auswahl aufrufen.

---

Wenn der User `/90-retro <name>` aufruft, direkt zu Schritt 2.

Wenn der User `/90-retro` ohne Argumente aufruft:

```bash
$WF retro-list
```

Zeige die Liste kurz an, dann ohne Nachfrage den zuletzt abgeschlossenen analysieren:

```bash
$WF retro
```

### Schritt 2 — Retro ausgeben

```bash
$WF retro <name>
```

### Schritt 3 — PO-Zusammenfassung

Nach der technischen Ausgabe: kurze Zusammenfassung in einfacher Sprache (2–4 Sätze):

- Wie lange hat der Workflow insgesamt gedauert?
- Gab es Qualitätsprobleme (Fix-Loops, Override, fehlendes TDD)?
- Was war die langsamste Phase und warum könnte das so sein?
- Was lief besonders gut?

Kein Fachjargon, keine Dateinamen.
