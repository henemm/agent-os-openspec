---
description: "/90-retro — Workflow-Retro"
disable-model-invocation: false
---

# /90-retro — Workflow-Retro

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

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /90-retro · agent-os-openspec 3.28.4

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von zwei Formen: `❗ Du: …`, wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist niemals „nichts zu tun“. Oder `ℹ️ Nichts zu tun: <du arbeitest gerade selbst / wartest auf ein Ergebnis, z. B. einen Hintergrund-Agenten> — danach: /<befehl> #<N>`, ausschließlich wenn du auf etwas ANDERES als den PO wartest. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase übernimmst du aus dem Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — Phase und Schritt wörtlich von dort. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfallen die erste Zeile und die Statuszeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.
