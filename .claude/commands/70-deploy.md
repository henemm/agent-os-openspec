---
description: "Deploy to production"
disable-model-invocation: true
---
<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->

# Deploy

Bringt `main` live — mit **genau dem Ablauf des Projekts** (`deploy:`: `command`, `verify`, `rollback`).

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/70-deploy.md` im Plugin-Ordner — nur bei Bedarf lesen.

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

**Aufruf als `/70-deploy #<N>`?** Zuerst Workflow auflösen und aktivieren:

```bash
$WF find 42   # die übergebene Nummer
$WF switch <NAME-aus-obigem-Output>
$WF status
```

**Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht**; vor `phase8_complete` erst den offenen Pflicht-Schritt nennen.

## Step 1: Vorabprüfungen

```bash
git status --porcelain
git fetch origin main
git log HEAD..origin/main --oneline
```

**STOPP** bei nicht committeten Änderungen, Stand hinter `origin/main` oder roten Tests.

## Step 2: Deploy-Ablauf lesen

```bash
$WF deploy-config
```

**`DEPLOY_CONFIGURED=no`:** nichts deployen, nichts raten. Vorschlag aus `CLAUDE.md`/`docs/`/`deploy*.sh` suchen, dann den PO fragen: Wie kommt der Stand live (`command`)? Woran sieht man es (`verify`)? Wie geht es zurück (`rollback`)? Bestätigtes in `openspec.yaml` unter `deploy:` eintragen, committen, neu bei Step 1. Ohne Antwort Ende.

## Step 3: Deploy ausführen

Ohne Workflow/Issue-Nummer alle `deploy-status`-Aufrufe überspringen.

```bash
$WF deploy-status running <N>
```

`command`-Zeilen **wörtlich, in Reihenfolge** ausführen. Bricht einer ab: `$WF deploy-status failed <N> --note "<Grund>"`, STOPP, Meldung an den PO.

## Step 4: Nachprüfung

`verify`-Zeilen ausführen; erst bei Erfolg:

```bash
$WF deploy-status done <N>
```

Scheitert sie (#561):

**a) Technischer Fehlschlag:** `deploy-status failed <N> --note "<Grund>"`, `rollback`-Zeilen dem PO **vorschlagen**.

**b) Fachlicher Befund** (AC live nicht erfüllt) = **BROKEN-Pfad**:

```bash
$WF deploy-status failed <N> --note "<AC-N verletzt: Befund>"
$WF phase phase6_implement
```

Dann `/50-implement`, eine Adversary-Runde aus demselben Kontingent, `/60-validate`, ausliefern, `/70-deploy`. **Kein Korrektur-PR, kein Developer-Agent am Workflow vorbei.** Schon archiviert: neuer Workflow mit derselben Issue-Nummer (`/00-intake #<N>`).

## Haupt-Ordner nachziehen

Neue Claude-Session im Haupt-Ordner: `python3 ${_H}/session_singleton_guard.py sync-main`

## Abschluss: Endzustand melden (Pflicht, #550)

Jeden Lauf beenden mit `$WF endstate <N>` (ohne Nummer `workflow.py endstate <name>`) und den Wert hinter `FOOTER=` **wörtlich** als letzte Zeile ausgeben.

Kette bei offenem Auftrag (#551): nur wenn `FOOTER=` „aus deinem Auftrag“ enthält; `M` = Nummer darin (`NEXT=M` aus `workflow.py queue`).
Bei `ENDSTATE=waiting`: #M an frische Sitzung übergeben, `$WF handoff`, dann je nach `HANDOFF=`:
Steht `HANDOFF_DONE=` da (#668): ⏳-Zeile, Turn beenden, keine weitere Sitzung starten.
- `cloud`: `create_session` (`prompt` = Text zwischen `PROMPT_BEGIN`/`PROMPT_END`, `source_url` = `REPO_URL` außer `none`), dann `workflow.py handoff --mark cloud`, Turn beenden; misslingt es, wie `inline`.
- `herdr`: `workflow.py handoff --start`; `STARTED=yes`/`already` → Turn beenden, `no` → wie `inline`.
- `inline`/`none`: `/00-intake #M` selbst aufrufen.

Bei `ENDSTATE=you` Zeile ausgeben und auf den PO warten.

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /70-deploy · agent-os-openspec 4.26.2

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von drei Formen (es gibt keine vierte):

- `✅ Erledigt: <was>. Du kannst /clear ausführen und das nächste Issue starten.` — nur wenn der Workflow wirklich abgeschlossen ist.
- `⏳ Läuft noch: <worauf gewartet wird>. Du musst nichts tun, ich melde mich.` — du wartest auf CI, einen Hintergrund-Agenten oder einen Server.
- `❗ Du: …` (`❗ Du: <Schritt> — <warum>`), wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist immer ❗, nie ⏳.

Beendest du einen Turn, während du auf CI, Agent oder Server wartest, setze vorher `workflow.py waiting "<worauf>"` und gib die ⏳-Zeile aus; ist das Ergebnis da, `workflow.py waiting --clear`. Die passende Zeile liefert `workflow.py endstate [#<N>]` als `FOOTER=…` — gib sie wörtlich aus. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase geben den Stand AM ENDE dieser Nachricht wieder. Quelle ist der Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — aber nur, solange du die Phase in dieser Nachricht nicht selbst gewechselt hast. Hast du per `workflow.py phase <x>` (oder `complete`) gewechselt, beschreibt der Hinweis den Stand von Turn-Beginn; maßgeblich ist dann der neue Stand, den `workflow.py status` zeigt. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfällt die Statuszeile; die erste Zeile kommt dann aus `workflow.py endstate #<N>` und entfällt nur ohne Workflow. Die Marker-Zeilen entfallen NIE wegen eines Phasenwechsels; die ⚙-Zeile bleibt immer die letzte Zeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.
