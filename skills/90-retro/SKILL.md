---
description: "/90-retro — Workflow-Retro"
disable-model-invocation: false
---

# Workflow-Retro

Analysiere einen abgeschlossenen Workflow aus dem Archiv: Zeiten pro Phase, Qualitätssignale, Optimierungshinweise.

## Setup

```bash
# Plugin: CLAUDE_PLUGIN_ROOT; Legacy-Fallback: .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"; _H="${_H:-.claude/hooks}"
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
