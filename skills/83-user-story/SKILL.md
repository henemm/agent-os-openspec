---
description: "User Story Discovery (JTBD)"
disable-model-invocation: false
---

# User Story Discovery (JTBD-basiert)

Du führst einen **strukturierten Dialog** mit dem Product Owner, um eine User Story zu ermitteln und zu dokumentieren.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
```

## Framework: Jobs to be Done (JTBD)

Kernidee: Menschen "kaufen" Produkte nicht - sie "heuern" sie an, um einen Job zu erledigen.

## Argument prüfen (ZUERST)

Das Argument dieses Befehls ist normalerweise ein **Thema** (`/83-user-story Kalender-Integration`) — dann überspringe diesen Abschnitt und arbeite mit dem Thema weiter.

**Besteht das Argument nur aus einer Nummer** (`/83-user-story #1761`)? Dann ist ein laufender Workflow gemeint — löse ihn von der Platte auf, statt zu raten:

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

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec. **Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht**, und frage dann, für welches Feature die User Story gesucht ist. Findet der Block nichts, behandle das Argument doch als Thema.

## Dein Vorgehen

### Phase 1: Kontext klären

Frage zuerst, worum es geht:

```
Für welches Produkt/Feature soll ich die User Story ermitteln?
- Gesamtes Produkt
- Neues Epic/Feature (z.B. "Kalender-Integration")
- Bestehendes Feature verbessern
```

### Phase 2: JTBD Interview (Dialog)

Stelle diese Fragen **nacheinander** (nicht alle auf einmal). Nutze `AskUserQuestion` für strukturierte Fragen, oder frage frei im Chat.

**1. Die Situation (When...)**
> "In welcher Situation befindet sich der Nutzer, wenn das Problem auftritt?"
> "Was macht er gerade? Wo ist er? Was ist der Kontext?"

**2. Der Job (I want to...)**
> "Was will der Nutzer in diesem Moment erreichen?"
> "Was ist die konkrete Aufgabe, die er erledigen will?"

**3. Das gewünschte Ergebnis (So that...)**
> "Was erhofft sich der Nutzer davon?"
> "Wie sieht Erfolg aus? Was ist anders, wenn der Job erledigt ist?"

**4. Die Dimensionen**
- **Funktional:** Was muss technisch passieren?
- **Emotional:** Wie will sich der Nutzer fühlen? (sicher, entspannt, in Kontrolle?)
- **Sozial:** Wie will der Nutzer von anderen wahrgenommen werden?

**5. Die Timeline (optional, bei komplexeren Stories)**
> "Was war der erste Gedanke - wann wurde dir klar, dass du so etwas brauchst?"
> "Welche anderen Lösungen hast du vorher probiert?"
> "Was hat dich motiviert, aktiv nach einer Lösung zu suchen?"

**6. Die Alternativen**
> "Was macht der Nutzer heute, um dieses Problem zu lösen?"
> "Was sind die Nachteile der aktuellen Lösung?"

### Phase 3: Zusammenfassung validieren

Fasse die Story zusammen und lass sie bestätigen:

```markdown
## User Story: [Name]

**Situation:** [When...]
**Job:** [I want to...]
**Ergebnis:** [So that...]

### Das Problem heute
[Was der Nutzer aktuell macht und warum das nicht gut funktioniert]

### Die gewünschte Lösung
[Was das Produkt/Feature anders macht]

### Erfolgskriterien
- [ ] Kriterium 1
- [ ] Kriterium 2
```

### Phase 4: Dokumentieren

Speichere das Ergebnis im Projekt:

```
docs/stories/[name].md
```

Verwende das Template unten.

## Output Template

```markdown
# User Story: [Name]

> Erstellt: [Datum]
> Status: Draft | Approved
> Produkt: [Produktname]

## JTBD Statement

**When** [Situation/Kontext],
**I want to** [Job/Aufgabe],
**So that** [gewünschtes Ergebnis].

## Kontext

### Die Situation
[Detaillierte Beschreibung der Situation, in der das Problem auftritt]

### Das Problem heute
[Wie löst der Nutzer das Problem aktuell? Was sind die Nachteile?]

### Alternativen
- Alternative 1: [Was der Nutzer sonst tun könnte]
- Alternative 2: ...

## Dimensionen

### Funktional
[Was muss technisch passieren?]

### Emotional
[Wie will sich der Nutzer fühlen?]

### Sozial
[Wie will der Nutzer wahrgenommen werden?]

## Erfolgskriterien

- [ ] Kriterium 1
- [ ] Kriterium 2
- [ ] Kriterium 3

## Abgeleitete Features

| Feature | Priorität | Status |
|---------|-----------|--------|
| Feature 1 | Must | Backlog |
| Feature 2 | Should | Backlog |

---
*Ermittelt im JTBD-Dialog am [Datum]*
```

## Wichtig

- **Frag nach, bis du es wirklich verstehst** - keine Annahmen
- **Nutze die Sprache des Users** - keine technischen Begriffe erzwingen
- **Emotional > Funktional** - Das "Warum" ist wichtiger als das "Was"
- **Validiere am Ende** - Lass die Zusammenfassung bestätigen bevor du speicherst

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen zwei Zeilen, in dieser Reihenfolge:

Workflow `<name>` · Phase `<x>` von 8 · Nächster Pflicht-Schritt: `/<befehl> #<N>`
⚙ /83-user-story · agent-os-openspec 3.25.0

Die Statuszeile übernimmst du aus dem Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert — Phase und Schritt wörtlich von dort. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfällt die Statuszeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In der Statuszeile ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Beide Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die Statuszeile entfällt.
