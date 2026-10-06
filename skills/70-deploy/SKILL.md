---
description: "Deploy to production"
disable-model-invocation: true
---

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

**`DEPLOY_CONFIGURED=no`:** Nichts deployen und nichts raten — auch nicht aus Beispielen
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

Führe die `command`-Zeilen aus der Ausgabe von Step 2 **wörtlich und in dieser Reihenfolge**
aus. Bricht ein Befehl ab: STOPP, Fehlermeldung an den PO, nicht improvisieren.

## Step 4: Nachprüfung

Führe die `verify`-Zeilen aus. Erst wenn sie erfolgreich sind, ist der Deploy erledigt.
Schlägt die Nachprüfung fehl: Ergebnis an den PO und die `rollback`-Zeilen **vorschlagen**
(nicht ungefragt ausführen — außer der PO hat das für dieses Projekt ausdrücklich festgelegt).

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

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /70-deploy · agent-os-openspec 3.38.5

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von zwei Formen: `❗ Du: …`, wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist niemals „nichts zu tun“. Oder `ℹ️ Nichts zu tun: <du arbeitest gerade selbst / wartest auf ein Ergebnis, z. B. einen Hintergrund-Agenten> — danach: /<befehl> #<N>`, ausschließlich wenn du auf etwas ANDERES als den PO wartest. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase übernimmst du aus dem Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — Phase und Schritt wörtlich von dort. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfallen die erste Zeile und die Statuszeile.

Hast DU SELBST in dieser Nachricht per `workflow.py phase <x>` (oder `complete`) die Phase gewechselt, ist der Hinweis noch der ALTE Stand von Turn-Beginn — nutze trotzdem den NEUEN, von dir selbst herbeigeführten Stand für Schritt und Phase. Die Marker-Zeilen entfallen NIE aus diesem Grund; die ⚙-Zeile bleibt immer die letzte Zeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.
