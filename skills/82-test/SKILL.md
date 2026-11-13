---
description: "Run tests"
disable-model-invocation: false
---

# Tests ausfuehren

Starte den `test-runner` Agenten — eigener Agent-Typ (Projekt-Agent in `.claude/agents/`, lokal auch als Plugin-Agent), Start **ohne `model`**, das Modell steht im Frontmatter (#577):

```
Agent(subagent_type="test-runner", description="Tests ausfuehren", prompt="
  Fuehre die Tests des Projekts aus und fasse das Ergebnis zusammen
  (passed/failed/uebersprungen, bei Failures Fehlermeldungen und betroffene Dateien).
  Kontext (falls Wiedereinstieg): affected_files und test_files aus dem Workflow-State.")
```

**Fallback, wenn der Typ in der Agent-Liste fehlt:** test-runner → `agent-os-openspec:test-runner`, sonst `Agent(subagent_type="general-purpose", model="haiku", prompt="Lies zuerst .claude/agents/test-runner.md (im Framework-Repo core/agents/test-runner.md) und folge ihr. …")`.

---

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
_S="${_H%/core/hooks}/scripts"; [ "$_H" = ".claude/hooks" ] && _S=".claude/scripts"
```

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/82-test #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf — der komplette State überlebt jeden `/clear` und jeden Worktree:

```bash
$WF find 42   # die übergebene Nummer
```

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen). Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58):

```bash
$WF switch <NAME-aus-obigem-Output>
$WF status
```

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec. **Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** — `affected_files` und `test_files` aus dem State gehören in den Auftrag an den Test-Runner.

**Ohne Argument** laufen die Tests des aktuellen Projekts.

---

## Anweisung

1. Ermittle das passende Test-Kommando fuer das Projekt
2. Fuehre alle Tests aus
3. Fasse Ergebnisse kurz und verstaendlich zusammen
4. Bei Failures: Zeige betroffene Dateien und Fehlermeldungen

---

## Output Format

Ein Lauf mit 0 bestanden und ≥ 1 übersprungen ist nicht grün.

**Bei Erfolg:**
```
Tests: X passed, Y failed, Z übersprungen
Status: Alles gruen
```

**Bei Failures:**
```
Tests: X passed, Y failed, Z übersprungen
Fehlgeschlagen:
- TestClass.testMethod: [Fehlermeldung]

Betroffene Dateien:
- [Pfad]
```

---

## Zero Tolerance Policy

- ALLE Tests muessen gruen sein vor Commit
- Bei Failures: Nicht committen, erst fixen
- Keine Ausnahmen

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /82-test · agent-os-openspec 4.12.0

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von drei Formen (es gibt keine vierte):

- `✅ Erledigt: <was>. Du kannst /clear ausführen und das nächste Issue starten.` — nur wenn der Workflow wirklich abgeschlossen ist.
- `⏳ Läuft noch: <worauf gewartet wird>. Du musst nichts tun, ich melde mich.` — du wartest auf CI, einen Hintergrund-Agenten oder einen Server.
- `❗ Du: …` (`❗ Du: <Schritt> — <warum>`), wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist immer ❗, nie ⏳.

Beendest du einen Turn, während du auf CI, Agent oder Server wartest, setze vorher `workflow.py waiting "<worauf>"` und gib die ⏳-Zeile aus; ist das Ergebnis da, `workflow.py waiting --clear`. Die passende Zeile liefert `workflow.py endstate [#<N>]` als `FOOTER=…` — gib sie wörtlich aus. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase geben den Stand AM ENDE dieser Nachricht wieder. Quelle ist der Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — aber nur, solange du die Phase in dieser Nachricht nicht selbst gewechselt hast. Hast du per `workflow.py phase <x>` (oder `complete`) gewechselt, beschreibt der Hinweis den Stand von Turn-Beginn; maßgeblich ist dann der neue Stand, den `workflow.py status` zeigt. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfällt die Statuszeile; die erste Zeile kommt dann aus `workflow.py endstate #<N>` und entfällt nur ohne Workflow. Die Marker-Zeilen entfallen NIE wegen eines Phasenwechsels; die ⚙-Zeile bleibt immer die letzte Zeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.
