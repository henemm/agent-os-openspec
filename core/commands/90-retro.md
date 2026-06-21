# /90-retro — Workflow-Retro

Analysiere einen abgeschlossenen Workflow aus dem Archiv: Zeiten pro Phase, Qualitätssignale, Optimierungshinweise.

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
python3 .claude/hooks/workflow.py retro-list
```

Zeige die Ausgabe und frage: "Welchen Workflow möchtest du analysieren?"
Dann `retro <name>` mit der Auswahl aufrufen.

---

Wenn der User `/90-retro <name>` aufruft, direkt zu Schritt 2.

Wenn der User `/90-retro` ohne Argumente aufruft:

```bash
python3 .claude/hooks/workflow.py retro-list
```

Zeige die Liste kurz an, dann ohne Nachfrage den zuletzt abgeschlossenen analysieren:

```bash
python3 .claude/hooks/workflow.py retro
```

### Schritt 2 — Retro ausgeben

```bash
python3 .claude/hooks/workflow.py retro <name>
```

### Schritt 3 — PO-Zusammenfassung

Nach der technischen Ausgabe: kurze Zusammenfassung in einfacher Sprache (2–4 Sätze):

- Wie lange hat der Workflow insgesamt gedauert?
- Gab es Qualitätsprobleme (Fix-Loops, Override, fehlendes TDD)?
- Was war die langsamste Phase und warum könnte das so sein?
- Was lief besonders gut?

Kein Fachjargon, keine Dateinamen.
