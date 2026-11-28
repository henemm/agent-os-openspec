# Deploy

Bringt `main` live — mit **genau dem Ablauf des Projekts** (`deploy:`: `command`, `verify`, `rollback`).

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/70-deploy.md` im Plugin-Ordner — nur bei Bedarf lesen.

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Aufruf als `/70-deploy #<N>`?** Zuerst Workflow auflösen und aktivieren:

```bash
python3 .claude/hooks/workflow.py find 42   # die übergebene Nummer
python3 .claude/hooks/workflow.py switch <NAME-aus-obigem-Output>
python3 .claude/hooks/workflow.py status
```

**Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht**; vor `phase8_complete` erst den offenen Pflicht-Schritt nennen.

## Step 0: Selbstaufruf nur bei deploy.autonomous (#707)

Selbst aufgerufen (nicht vom PO getippt)? `python3 .claude/hooks/workflow.py deploy-config`: nur bei
`autonomous: true` weiter, sonst STOP mit ❗ Du: `/70-deploy #N` (sperrt auch `skill_gate`).

## Step 1: Vorabprüfungen

```bash
git status --porcelain
git fetch origin main
git log HEAD..origin/main --oneline
```

**STOPP** bei nicht committeten Änderungen, Stand hinter `origin/main` oder roten Tests.

## Step 2: Deploy-Ablauf lesen

```bash
python3 .claude/hooks/workflow.py deploy-config
```

**`DEPLOY_CONFIGURED=no`:** nichts deployen, nichts raten. Vorschlag aus `CLAUDE.md`/`docs/`/`deploy*.sh` suchen, dann den PO fragen: Wie kommt der Stand live (`command`)? Woran sieht man es (`verify`)? Wie geht es zurück (`rollback`)? Bestätigtes in `openspec.yaml` unter `deploy:` eintragen, committen, neu bei Step 1. Ohne Antwort Ende.

## Step 3: Deploy ausführen

Ohne Workflow/Issue-Nummer alle `deploy-status`-Aufrufe überspringen.

```bash
python3 .claude/hooks/workflow.py deploy-status running <N>
```

`command`-Zeilen **wörtlich, in Reihenfolge** ausführen. Bricht einer ab: `python3 .claude/hooks/workflow.py deploy-status failed <N> --note "<Grund>"`, STOPP, Meldung an den PO.

## Step 4: Nachprüfung

`verify`-Zeilen ausführen; erst bei Erfolg:

```bash
python3 .claude/hooks/workflow.py deploy-status done <N>
```

Scheitert sie (#561):

**a) Technischer Fehlschlag:** `deploy-status failed <N> --note "<Grund>"`, `rollback`-Zeilen dem PO **vorschlagen**.

**b) Fachlicher Befund** (AC live nicht erfüllt) = **BROKEN-Pfad**:

```bash
python3 .claude/hooks/workflow.py deploy-status failed <N> --note "<AC-N verletzt: Befund>"
python3 .claude/hooks/workflow.py phase phase6_implement
```

Dann `/50-implement`, eine Adversary-Runde aus demselben Kontingent, `/60-validate`, ausliefern, `/70-deploy`. **Kein Korrektur-PR, kein Developer-Agent am Workflow vorbei.** Schon archiviert: neuer Workflow mit derselben Issue-Nummer (`/00-intake #<N>`).

## Haupt-Ordner nachziehen

Neue Claude-Session im Haupt-Ordner: `python3 .claude/hooks/session_singleton_guard.py sync-main`

## Abschluss: Endzustand melden (Pflicht, #550)

Jeden Lauf beenden mit `python3 .claude/hooks/workflow.py endstate <N>` (ohne Nummer `workflow.py endstate <name>`) und den Wert hinter `FOOTER=` **wörtlich** als letzte Zeile ausgeben.

Kette bei offenem Auftrag (#551): nur wenn `FOOTER=` „aus deinem Auftrag“ enthält; `M` = Nummer darin (`NEXT=M` aus `workflow.py queue`).
Bei `ENDSTATE=waiting`: #M an frische Sitzung übergeben, `python3 .claude/hooks/workflow.py handoff`, dann je nach `HANDOFF=`:
Steht `HANDOFF_DONE=` da (#668): ⏳-Zeile, Turn beenden, keine weitere Sitzung starten.
- `cloud`: `create_session` (`prompt` = Text zwischen `PROMPT_BEGIN`/`PROMPT_END`, `source_url` = `REPO_URL` außer `none`), dann `workflow.py handoff --mark cloud`, Turn beenden; misslingt es, wie `inline`.
- `herdr`: `workflow.py handoff --start`; `STARTED=yes`/`already` → Turn beenden, `no` → wie `inline`.
- `inline`/`none`: `/00-intake #M` selbst aufrufen.

Bei `ENDSTATE=you` Zeile ausgeben und auf den PO warten.
