# Deploy

Bringt den aktuellen Stand von `main` live — mit **genau dem Ablauf, den dieses Projekt
festgelegt hat**. Das Framework kennt deine Plattform nicht und rät sie nicht.

> Der Ablauf steht in der Projekt-Config unter `deploy:` (`command`, `verify`, `rollback`).
> Fehlt er, führt dieser Befehl **nichts** aus, sondern fragt ihn einmal ab (Step 2).

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/70-deploy #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf — der komplette State überlebt jeden `/clear` und jeden Worktree:

```bash
python3 .claude/hooks/workflow.py find 42   # die übergebene Nummer
```

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen). Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58):

```bash
python3 .claude/hooks/workflow.py switch <NAME-aus-obigem-Output>
python3 .claude/hooks/workflow.py status
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
python3 .claude/hooks/workflow.py deploy-config
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
python3 .claude/hooks/workflow.py deploy-status running <N>
```

Führe die `command`-Zeilen aus der Ausgabe von Step 2 **wörtlich und in dieser Reihenfolge**
aus. Bricht ein Befehl ab: `python3 .claude/hooks/workflow.py deploy-status failed <N> --note "<Grund>"`,
dann STOPP, Fehlermeldung an den PO, nicht improvisieren.

## Step 4: Nachprüfung

Führe die `verify`-Zeilen aus. Erst wenn sie erfolgreich sind, ist der Deploy erledigt —
erst dann den Marker setzen, der den Plan auf „✔ Deploy“ springen lässt:

```bash
python3 .claude/hooks/workflow.py deploy-status done <N>
```

Schlägt die Nachprüfung fehl, unterscheide zwei Fälle (#561):

**a) Technischer Fehlschlag** (Infrastruktur: Server nicht erreichbar, Deploy bricht ab,
`verify` scheitert an der Umgebung):
`python3 .claude/hooks/workflow.py deploy-status failed <N> --note "<Grund>"`, Ergebnis an den
PO und die `rollback`-Zeilen **vorschlagen** (nicht ungefragt ausführen — außer der PO hat das
für dieses Projekt ausdrücklich festgelegt).

**b) Fachlicher Befund** (eine AC ist auf Staging/live nicht erfüllt, die Infrastruktur läuft):
Das ist der **BROKEN-Pfad**, kein neuer Auftrag:

```bash
python3 .claude/hooks/workflow.py deploy-status failed <N> --note "<AC-N verletzt: Befund>"
python3 .claude/hooks/workflow.py phase phase6_implement
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
python3 .claude/hooks/session_singleton_guard.py sync-main
```

Der Guard lässt in dieser Session genau diesen Befehl durch. Er zieht per `git fetch` +
`git merge --ff-only` nach und bricht mit klarer Meldung ab (nichts geändert), wenn der Ordner
Änderungen an versionierten Dateien hat, die Historie abweicht oder kein Upstream existiert.


## Abschluss: Endzustand melden (Pflicht, #550)

Beende jeden Lauf dieses Befehls — erfolgreich, fehlgeschlagen oder abgebrochen — mit:

```bash
python3 .claude/hooks/workflow.py endstate <N>
```

Gib den Wert hinter `FOOTER=` **wörtlich** als Endzustand-Zeile der Nachricht aus (genau eine
der drei Formen `✅ Erledigt: …`, `⏳ Läuft noch: …`, `❗ Du: … — …`). Keine eigene Formulierung,
kein „Nächster: /70-deploy“ daneben. Ohne Issue-Nummer rufe denselben Befehl mit dem
Workflow-Namen auf (`workflow.py endstate <name>`); nur ganz ohne Workflow entfällt der Aufruf.

Kette bei offenem Auftrag (#551, #555): Sie greift nur, wenn der Wert hinter `FOOTER=`
„aus deinem Auftrag“ enthält; `M` ist die Nummer darin (dieselbe wie `NEXT=M` aus
`python3 .claude/hooks/workflow.py queue`). Bei `ENDSTATE=waiting` (`⏳ Läuft noch: Claude
startet #M aus deinem Auftrag. …`) gib die Zeile aus und rufe danach `/00-intake #M` selbst
auf (autarker Auftrag) — kein Halt für `/clear`. Bei `ENDSTATE=you` (`❗ Du: /00-intake #M — …`,
Auftrag nicht autark) gib die Zeile wörtlich aus und warte auf den PO. Ein `ENDSTATE=waiting`
ohne „aus deinem Auftrag“ (Deploy, CI, Agent) startet keine Kette.
