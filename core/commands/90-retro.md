# /90-retro — Workflow-Retro

Analysiere einen abgeschlossenen Workflow aus dem Archiv: Zeiten pro Phase, Qualitätssignale, Optimierungshinweise.

## Verwendung

```
/90-retro            → zuletzt abgeschlossenen Workflow analysieren
/90-retro <name>     → bestimmten archivierten Workflow analysieren
/90-retro list       → alle archivierten Workflows auflisten
```

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/90-retro #<N>` aufgerufen?** Dann ist der Workflow zu dieser Nummer gemeint. Er ist per Definition **abgeschlossen und archiviert** — deshalb hier kein `workflow.py switch` (das gilt nur für laufende Workflows), sondern die Suche im Archiv und danach `retro <name>`:

```bash
ISSUE=42   # die übergebene Nummer (ohne #)
python3 - "$ISSUE" <<'PY'
import sys, json, glob, re, os
issue = sys.argv[1].lstrip('#')
pat = re.compile(rf'(^|[-_]){re.escape(issue)}([-_]|$)')
hits = []
for f in glob.glob('.claude/workflows/_archive/*.json') + glob.glob('.claude/workflows/*.json'):
    name = os.path.basename(f)[:-5]
    if pat.search(name):
        d = json.load(open(f))
        hits.append((name, d.get('current_phase'), '_archive' in f))
if not hits:
    print(f'KEIN Workflow fuer #{issue} — weder im Archiv noch laufend.')
else:
    for name, ph, arch in hits:
        print(f'GEFUNDEN: {name} | Phase={ph} | {"archiviert" if arch else "LAEUFT NOCH"}')
    print('\nNAME=' + hits[0][0])
PY
```

Mit dem gefundenen Namen weiter bei Schritt 2 (`retro <name>`). **Fasse dem User in 2 Sätzen zusammen**, welchen Workflow du analysierst und ob er wirklich abgeschlossen ist. Steht dort `LAEUFT NOCH`, sag das zuerst und nenne den offenen Pflicht-Schritt — eine Retro über laufende Arbeit ist verfrüht.

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
