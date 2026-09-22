---
description: "Analyze a bug following the Analysis-First principle"
disable-model-invocation: false
---

# Bug Analysis (Analysis-First)

Analyze a bug following the **Analysis-First** principle.

**NEVER fix directly!** First understand completely, then document, then (after approval) fix.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
```

## Step 0: GitHub Issues durchsuchen (IMMER ZUERST)

```bash
# Offene Bug-Issues anzeigen
gh issue list --label "bug" --state open

# Keyword-Suche nach aehnlichen Bugs
gh issue list --search "$ARGUMENTS" --state open
```

Falls Duplikat gefunden → vorhandenes Issue referenzieren, kein neues erstellen.
Falls kein Duplikat → `bug-investigator` erstellt am Ende ein neues Issue.

---

## Phase 1: Understand the Bug

1. **Capture symptoms:**
   - What exactly happens? (User description)
   - Where does it happen? (View, feature, context)
   - When does it happen? (Always? Sometimes? After specific action?)

2. **Define reproduction steps:**
   - Step-by-step instructions to reproduce
   - Expected behavior vs. actual behavior

## Phase 2: Find Root Cause

3. **Analyze code:**
   - Identify affected files
   - Trace data flow completely (NOT just fragments!)
   - Question: "Where does the problem ORIGINATE?"

4. **Identify root cause with certainty:**
   - Name concrete code location(s) (file:line)
   - WHY does this location cause the problem?
   - No speculation - only proven causes!

## Phase 3: Document

5. **Create entry in bug tracking:**

```markdown
## Bug: [Short Description]

- **Location:** [File(s)]
- **Problem:** [What goes wrong]
- **Expected:** [What should happen]
- **Root Cause:** [Why it happens - code location]
- **Test:** [How to verify fix]
- **Effort:** [Small/Medium/Large]
```

## Phase 4: Fix (only after approval!)

After documentation and user approval:
1. `/20-analyse` - Start workflow
2. `/30-write-spec` - Specify fix
3. User: "approved"
4. `/50-implement` - Implement fix
5. `/60-validate` - Test

## STOP Conditions

Stop and ask when:
- Root cause unclear (need more info)
- Bug not reproducible (need steps)
- Multiple possible causes (prioritize)
- Fix would change >5 files (split?)

## Output to User

Summarize (NO code, understandable language):

1. **What is the problem?** (1-2 sentences)
2. **Where is the cause?** (File + short explanation)
3. **How do we test the fix?** (Concrete steps)
4. **Estimated effort** (Small/Medium/Large)

---

## Fast Track (triviale Bugs — ≤3 Dateien, bekannte Ursache)

Wenn Ursache klar und Fix klein → direkt implementieren ohne vollständigen 8-Phasen-Workflow.

**Voraussetzungen:**
- Ursache mit Sicherheit bekannt (konkrete Datei + Zeile)
- Fix berührt ≤3 Dateien
- Kein neues API-Design oder Breaking Changes

**Ablauf:**
```bash
# 1. Bug-Workflow starten (startet direkt bei phase6_implement)
$WF start BUG-<N> --type bug
export OPENSPEC_ACTIVE_WORKFLOW=BUG-<N>

# 2. Fix implementieren (kein Spec, kein TDD-Red erforderlich)
# ...edit files...

# 3. Manuell testen
# Reproduktionsschritte durchgehen, Fix verifizieren

# 4. Abschließen
$WF write-log success
$WF finish
```

**Was wegfällt beim Fast Track:**
- Phasen 1–5 (Kontext, Analyse, Spec, Approval, TDD-Red)
- Adversary-Validierung vor `git commit`
- TDD-Artefakt-Pflicht

**Was bleibt aktiv:**
- Rebase-Gate (Branch muss auf `origin/main` stehen)
- Stop-Lock / Override-Token
- Secrets Guard

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /00-bug · agent-os-openspec 3.30.0

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von zwei Formen: `❗ Du: …`, wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist niemals „nichts zu tun“. Oder `ℹ️ Nichts zu tun: <du arbeitest gerade selbst / wartest auf ein Ergebnis, z. B. einen Hintergrund-Agenten> — danach: /<befehl> #<N>`, ausschließlich wenn du auf etwas ANDERES als den PO wartest. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase übernimmst du aus dem Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — Phase und Schritt wörtlich von dort. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfallen die erste Zeile und die Statuszeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.
