---
description: "Deploy to production"
disable-model-invocation: true
---
<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->

# Deploy

Bringt den aktuellen Stand von `main` live — mit **genau dem Ablauf, den dieses Projekt
festgelegt hat**. Das Framework kennt deine Plattform nicht und rät sie nicht.

> Der Ablauf steht in der Projekt-Config unter `deploy:` (`command`, `verify`, `rollback`).
> Fehlt er, führt dieser Befehl **nichts** aus, sondern fragt ihn einmal ab (Step 2).

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

**Wurde dieser Befehl als `/70-deploy #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf — der komplette State überlebt jeden `/clear` und jeden Worktree:

```bash
$WF find 42   # die übergebene Nummer
```

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen). Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58):

```bash
$WF switch <NAME-aus-obigem-Output>
$WF status
```

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Verdict. **Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** — steht er vor `phase8_complete`, nenne den offenen Pflicht-Schritt, bevor du deployst.

**Ohne Argument** geht es direkt mit den Pre-Flight-Checks weiter.

## Step 1: Vorabprüfungen (plattformunabhängig)

```bash
git branch --show-current
git status --porcelain
git fetch origin main
git log HEAD..origin/main --oneline
```

**STOPP, wenn:**
- es nicht committete Änderungen gibt → erst committen
- der Stand hinter `origin/main` liegt → erst nachziehen
- Tests rot sind → erst reparieren (Testbefehl des Projekts ausführen)

## Step 2: Deploy-Ablauf des Projekts lesen

```bash
$WF deploy-config
```

**`DEPLOY_CONFIGURED=no`:** Diesen Fall erreicht nur noch, wer `/70-deploy` von Hand aufruft
(#550): Ein Projekt ohne `deploy:`-Block gilt als ohne Deploy, sein Workflow endet schon mit
`✅ Erledigt`, und kein Plan und keine Fußzeile schlägt `/70-deploy` vor.
Nichts deployen und nichts raten — auch nicht aus Beispielen
oder aus dem, was „üblich“ ist. Stattdessen:

1. Prüfe, ob das Projekt seinen Ablauf schon beschreibt (`CLAUDE.md`, `docs/`, Skripte wie
   `deploy*.sh`). Gefundenes ist ein **Vorschlag**, keine Freigabe.
2. Stelle dem PO genau diese drei Fragen (Vorschlag aus 1 mitgeben, falls vorhanden):
   - Wie kommt der Stand live? → `command`
   - Woran sieht man, dass er live ist? → `verify`
   - Wie geht es zurück, falls nicht? → `rollback`
3. Trage die bestätigten Antworten in `openspec.yaml` unter `deploy:` ein, committe sie und
   beginne `/70-deploy` erneut bei Step 1. Eine Root-`config.yaml` zählt nur, wenn sie einen
   Plugin-Block enthält (#372) — `deploy:` allein reicht dort nicht; eine `HINWEIS:`-Zeile
   der Ausgabe nennt eine so übergangene Datei.
   Ohne Antwort endet der Befehl hier.

**`DEPLOY_CONFIGURED=yes`:** weiter mit Step 3.

## Step 3: Deploy ausführen

**Plan-Marker (#510)** — vorher den Deploy als laufend vermerken (`<N>` = Issue-Nummer des
Workflows; ohne Workflow/Issue-Nummer alle `deploy-status`-Aufrufe überspringen, bei
`DEPLOY_CONFIGURED=no` gibt es keinen Marker):

```bash
$WF deploy-status running <N>
```

Führe die `command`-Zeilen aus der Ausgabe von Step 2 **wörtlich und in dieser Reihenfolge**
aus. Bricht ein Befehl ab: `$WF deploy-status failed <N> --note "<Grund>"`,
dann STOPP, Fehlermeldung an den PO, nicht improvisieren.

## Step 4: Nachprüfung

Führe die `verify`-Zeilen aus. Erst wenn sie erfolgreich sind, ist der Deploy erledigt —
erst dann den Marker setzen, der den Plan auf „✔ Deploy“ springen lässt:

```bash
$WF deploy-status done <N>
```

Schlägt die Nachprüfung fehl, unterscheide zwei Fälle (#561):

**a) Technischer Fehlschlag** (Infrastruktur: Server nicht erreichbar, Deploy bricht ab,
`verify` scheitert an der Umgebung):
`$WF deploy-status failed <N> --note "<Grund>"`, Ergebnis an den
PO und die `rollback`-Zeilen **vorschlagen** (nicht ungefragt ausführen — außer der PO hat das
für dieses Projekt ausdrücklich festgelegt).

**b) Fachlicher Befund** (eine AC ist auf Staging/live nicht erfüllt, die Infrastruktur läuft):
Das ist der **BROKEN-Pfad**, kein neuer Auftrag:

```bash
$WF deploy-status failed <N> --note "<AC-N verletzt: Befund>"
$WF phase phase6_implement
```

Danach gezielter Fix per `/50-implement`, eine Adversary-Runde aus demselben Kontingent
(Adversary-Limit in `CLAUDE.md`), `/60-validate`, dann erneut ausliefern und `/70-deploy`.
**Kein Korrektur-PR und kein Developer-Agent am Workflow vorbei** — sonst bleiben Plan und
Seitenleiste auf dem alten Stand stehen. Der Rücksprung verwirft den alten Deploy-Stand: Der
Plan zeigt danach „○ Deploy“, nach erneutem Phase 8 „▶ Deploy (offen)“.
Ist der Workflow schon archiviert (`workflow.py find <N>` meldet KEIN laufender Workflow), geht
kein Rücksprung mehr: neuer Workflow mit derselben Issue-Nummer (`/00-intake #<N>`) bzw. ein
Folge-Issue.

## Haupt-Ordner nachziehen (nach gemergtem PR)

Ein Workflow endet im Worktree; der Haupt-Ordner des Projekts auf der Platte bleibt auf altem
Stand — relevant z. B. für Xcode, das den Haupt-Ordner öffnet. Aus einer Worktree-Session heraus
lässt er sich nicht aktualisieren (Claude Code verweigert dort Git-Aufrufe auf den Haupt-Ordner).

**Weg:** eine neue Claude-Session **im Haupt-Ordner** öffnen und ausführen:

```bash
python3 ${_H}/session_singleton_guard.py sync-main
```

Der Guard lässt in dieser Session genau diesen Befehl durch. Er zieht per `git fetch` +
`git merge --ff-only` nach und bricht mit klarer Meldung ab (nichts geändert), wenn der Ordner
Änderungen an versionierten Dateien hat, die Historie abweicht oder kein Upstream existiert.


## Abschluss: Endzustand melden (Pflicht, #550)

Beende jeden Lauf dieses Befehls — erfolgreich, fehlgeschlagen oder abgebrochen — mit:

```bash
$WF endstate <N>
```

Gib den Wert hinter `FOOTER=` **wörtlich** als Endzustand-Zeile der Nachricht aus (genau eine
der drei Formen `✅ Erledigt: …`, `⏳ Läuft noch: …`, `❗ Du: … — …`). Keine eigene Formulierung,
kein „Nächster: /70-deploy“ daneben. Ohne Issue-Nummer rufe denselben Befehl mit dem
Workflow-Namen auf (`workflow.py endstate <name>`); nur ganz ohne Workflow entfällt der Aufruf.

Kette bei offenem Auftrag (#551, #555): Sie greift nur, wenn der Wert hinter `FOOTER=`
„aus deinem Auftrag“ enthält; `M` ist die Nummer darin (dieselbe wie `NEXT=M` aus
`$WF queue`). Bei `ENDSTATE=waiting` (`⏳ Läuft noch: Claude
startet #M aus deinem Auftrag. …`) gib die Zeile aus und rufe danach `/00-intake #M` selbst
auf (autarker Auftrag) — kein Halt für `/clear`. Bei `ENDSTATE=you` (`❗ Du: /00-intake #M — …`,
Auftrag nicht autark) gib die Zeile wörtlich aus und warte auf den PO. Ein `ENDSTATE=waiting`
ohne „aus deinem Auftrag“ (Deploy, CI, Agent) startet keine Kette.

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /70-deploy · agent-os-openspec 4.12.0

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von drei Formen (es gibt keine vierte):

- `✅ Erledigt: <was>. Du kannst /clear ausführen und das nächste Issue starten.` — nur wenn der Workflow wirklich abgeschlossen ist.
- `⏳ Läuft noch: <worauf gewartet wird>. Du musst nichts tun, ich melde mich.` — du wartest auf CI, einen Hintergrund-Agenten oder einen Server.
- `❗ Du: …` (`❗ Du: <Schritt> — <warum>`), wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist immer ❗, nie ⏳.

Beendest du einen Turn, während du auf CI, Agent oder Server wartest, setze vorher `workflow.py waiting "<worauf>"` und gib die ⏳-Zeile aus; ist das Ergebnis da, `workflow.py waiting --clear`. Die passende Zeile liefert `workflow.py endstate [#<N>]` als `FOOTER=…` — gib sie wörtlich aus. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase geben den Stand AM ENDE dieser Nachricht wieder. Quelle ist der Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — aber nur, solange du die Phase in dieser Nachricht nicht selbst gewechselt hast. Hast du per `workflow.py phase <x>` (oder `complete`) gewechselt, beschreibt der Hinweis den Stand von Turn-Beginn; maßgeblich ist dann der neue Stand, den `workflow.py status` zeigt. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfällt die Statuszeile; die erste Zeile kommt dann aus `workflow.py endstate #<N>` und entfällt nur ohne Workflow. Die Marker-Zeilen entfallen NIE wegen eines Phasenwechsels; die ⚙-Zeile bleibt immer die letzte Zeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.
