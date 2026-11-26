---
description: "Validate the implementation"
disable-model-invocation: false
---

# Phase 7: Validation

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/60-validate.md` im Plugin-Ordner — nur bei Bedarf lesen.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
_S="${_H%/core/hooks}/scripts"; [ "$_H" = ".claude/hooks" ] && _S=".claude/scripts"
```

## Wiedereinstieg (`/60-validate #<N>`, nach `/clear`)

Workflow explizit aktivieren (`export` reicht NICHT):

```bash
$WF find 42   # die übergebene Nummer
$WF switch <NAME-aus-obigem-Output>
$WF status
```

Fasse dem User in 2 Sätzen den Stand zusammen (Phase, Verdict).

### Hängende Subagenten

Die Sitzung wird automatisch erneut aufgerufen, sobald der Hintergrund-Agent fertig ist. Fehlt dann der
Bericht: `TaskList` prüfen, noch aktiv → `TaskStop`, neu starten.

### Kontext laden (nur bei Wiedereinstieg nach `/clear`)

```
Agent(subagent_type="Explore", model="haiku", description="Validierungs-Kontext laden", run_in_background=true, prompt="
  Lies [spec_file], docs/artifacts/<workflow-name>/adversary-dialog.md, config.yaml. Gib zurück: spec_file_path,
  affected_files, test_command, alle AC-N, adversary_verdict.")
```

Nie mit `[...]`-Platzhaltern starten.

## Prerequisites

Implementierung fertig, GREEN-Artefakte registriert, `adversary_verdict` gesetzt (`workflow.py status`). **Pflicht vor allem Weiteren:**

```bash
python3 ${_H}/adversary_dialog.py validate docs/artifacts/<workflow-name>/adversary-dialog.md
```

Scheitert sie: zurück zu `/50-implement` Step 8. Akzeptiert: **VERIFIED** oder **AMBIGUOUS** (mit User-OK).

## Your Tasks

### Step 1: Parallele Validierung (4x Haiku)

4 Haiku-Agenten im Vordergrund, alle in EINER Nachricht (laufen parallel):

```
Agent(subagent_type="general-purpose", model="haiku", description="TEST CHECK", run_in_background=false, prompt="
  Fuehre ALLE Tests aus: python3 ${_H}/qa_gate.py --run (ohne test_command: [test_command]). Report: passed/failed, Laufzeit, Fehler.")
Agent(subagent_type="general-purpose", model="haiku", description="SPEC COMPLIANCE", run_in_background=false, prompt="
  Pruefe jedes Acceptance Criterion aus [spec_file_path] gegen die Implementation. Report: erfuellt / nicht erfuellt.")
Agent(subagent_type="general-purpose", model="haiku", description="REGRESSION CHECK", run_in_background=false, prompt="
  Volle Test-Suite ausfuehren. Report: welche vorher gruenen Tests sind jetzt rot?")
Agent(subagent_type="general-purpose", model="haiku", description="SCOPE CHECK", run_in_background=false, prompt="
  Geaenderte Dateien vs. Spec: Dateien ausserhalb der Spec? Mehr als 5 Dateien / 250 LoC?")
```

Bei `qa_gate.require_run: true` nach jedem Auto-Fix `--run` wiederholen (#404).

### Step 2: Ergebnis-Auswertung

**Step 2a:** Alle Checks bestanden → Step 3.

**Step 2b: Fehler → Auto-Fix nur für Nicht-Code** (Doku, Tests, Config). **Braucht ein Fund eine
Code-Änderung, ist das der BROKEN-Pfad:** zurück zu `phase6_implement`, Fix per `/50-implement`, eine Adversary-Runde
aus demselben Kontingent wie jedes BROKEN-Verdict.

**Nachprüfung nach Phase 8 (Staging/live):** Ein fachlicher Befund zählt wie BROKEN: `deploy-status failed --note`,
zurück zu `phase6_implement`, Fix per `/50-implement`, eine Adversary-Runde aus demselben Kontingent, danach erneut
`/60-validate` und `/70-deploy`.

```
Agent(subagent_type="general-purpose", model="sonnet", description="Auto-Fix Nicht-Code", run_in_background=true, prompt="
  Behebe nur: [Fehler-Liste aus den 4 Haiku-Reports]. Keine Code-Dateien (Code-Fix = BROKEN-Pfad); Scoping Limits; Tests erneut.")
```

Danach die relevanten Haiku-Checks erneut.

### Step 3: Dokumentation aktualisieren (docs-updater/Sonnet)

**docs-updater**, Start **ohne `model`**:

```
Agent(subagent_type="docs-updater", description="Doku aktualisieren", run_in_background=true, prompt="
  changed_files: [Liste], feature_summary: [Kurzbeschreibung],
  spec_file_path: [Pfad — NUR LESEN]. Aktualisiere die betroffene Doku; die Spec selbst NICHT
  bearbeiten, der freigegebene Teil ist eingefroren (#230, #439).")
```

**Fallback, wenn der Typ fehlt:** docs-updater → `agent-os-openspec:docs-updater`, sonst `Agent(subagent_type="general-purpose", model="sonnet", prompt="Lies zuerst .claude/agents/docs-updater.md und folge ihr. …")`.

Änderungen am freigegebenen Teil der Spec nur über `workflow.py phase phase3_spec`.

### Step 4: Workflow State aktualisieren

```bash
$WF phase phase8_complete
```

Phase 8 heißt nur **„Code fertig“** (`ship_status: open`); erst `ship-status done` (oder `ship-status skipped`, nur ohne Auslieferung) schließt den
Workflow ab (archiviert, im Auftrag abgehakt; kein `finish`). `scripts/ship.py` meldet das selbst; von Hand
`$WF ship-status running|done|failed <N> --note "<Stand in Alltagssprache>"`.

## Validation Report

Test Results, Spec Compliance / Regression / Scope, Result PASS / FAIL (Vorlage im Hintergrund), je Testlauf:
- Full Suite: [N] total, [N] passed, [N] übersprungen — 0 bestanden und ≥ 1 übersprungen ist nicht grün.

## Next Step

### Autonomen Weiterlauf prüfen (PFLICHT, vor der Ausgabe)

Gibt es `/70-deploy` UND `deploy.autonomous: true` (`$WF deploy-config`) oder
dokumentiert das Projekt (`CLAUDE.md`, `70-deploy.md`) Deploy **ohne Freigabe-Halt autonom**? Dann bindend: committen
und `/70-deploy` **im selben Turn selbst aufrufen**, Ergebnis der Kette melden. Sonst fragen (Standard unten).

### Beobachtbare Oberfläche prüfen (PFLICHT, vor der Ausgabe)

**Keine eigene Einschätzung ersetzt den Aufruf:**

```bash
$WF observable-surface
```

Fehlt die Zeile `OBSERVABLE_SURFACE=no` (auch bei `yes`, Absturz, abweichendem Format, ohne Aufruf), wird
„Soll ich den Stand sichern?" gefragt; nur die gelesene Zeile `OBSERVABLE_SURFACE=no` erspart das. Autonomie sticht:

| Oberfläche | Autonomie dokumentiert | Schlusszeile |
|---|---|---|
| `yes` | nein | Frage „Soll ich den Stand sichern?" |
| `yes` | ja | Ankündigung: schreibe fest und deploye, Kette im selben Turn |
| `no` | nein | Ankündigung: schreibe jetzt fest, keine Rückfrage |
| `no` | ja | Ankündigung: schreibe fest und deploye, Kette im selben Turn |

### Auto-Modus prüfen (PFLICHT, vor der Ausgabe, #472)

```bash
$WF autonomy
```

Nur die gelesene Zeile `AUTONOMY=auto` schaltet um; alles andere (auch Fehler) gilt als `manual` (Tabelle oben).

Bei `AUTONOMY=auto` (nach Step 4, also mit `phase8_complete`):

1. **`auto-ship` prüfen (#525)** — vor dem Commit, denn davon hängt Punkt 2 ab:

   ```bash
   $WF auto-ship
   ```

   Nur die gelesene Zeile `AUTO_SHIP=on` schaltet um; alles andere gilt als `AUTO_SHIP=off`. Default an;
   aus per `autonomy.ship: false` in der Projekt-`config.yaml` (`settings.local.json` zählt nicht).
2. **Committen ohne Rückfrage** — unabhängig von `OBSERVABLE_SURFACE`; die Frage „Soll ich den
   Stand sichern?" entfällt. Die Commit-Gates (`bash_gate.py`) gelten wie immer.
   Bei `AUTO_SHIP=on`: Steht der Checkout auf `main`, `master`, dem Default-Branch des Remotes
   (ermittelt wie in Punkt 3) oder einem detached `HEAD`, legst du VOR dem Commit einen
   Feature-Branch mit dem Workflow-Namen an (`git switch -c <workflow-name>`). Existiert der Name
   schon lokal oder auf dem Remote, wird `-2`, `-3` und so weiter angehängt. Der lokale Default-Branch
   wird nie zurückgesetzt (kein `reset`, kein `--force`). Bei `AUTO_SHIP=off` gilt der Text oben
   unverändert.
3. **Den Feature-Branch pushen** — Branch prüfen mit `git rev-parse --abbrev-ref HEAD` und den
   Default-Branch des Remotes ermitteln: zuerst `git symbolic-ref --short refs/remotes/origin/HEAD`;
   schlägt das fehl, `git ls-remote --symref origin HEAD` und die
   Zeile `ref: refs/heads/<name>` auswerten. Gepusht wird nur, wenn der aktuelle Branch weder
   `main` noch `master` noch der Default-Branch des Remotes ist: dann
   `git push -u origin <feature-branch>`. Schlagen beide Wege fehl, gilt: bei `AUTO_SHIP=off` wird
   wie bisher nicht gepusht und das in der Abschlussmeldung gemeldet; bei `AUTO_SHIP=on` wird
   ebenfalls nicht gepusht und das Problem in Alltagssprache gemeldet (etwa „Der Server war nicht
   erreichbar, ausgeliefert wird später“), nie als Git-Auftrag an den PO.
   Nie `main`, `master` oder den Default-Branch pushen (auch kein detached `HEAD`), nie
   `--force`. Nur bei `AUTO_SHIP=off` gilt: steht der Checkout darauf, wird nur committet und der
   PO in der Abschlussmeldung darauf hingewiesen. Schlägt der Push fehl, melden statt umgehen.
   **Ein Aufruf statt vieler (Kontext-Haushalt):** `python3 ${_S}/ship.py [--branch <workflow-name>]
   [--merge squash]` erledigt Punkt 3 und 5 (Branch, Push, PR, CI, bei `AUTO_SHIP=on` Merge) mit denselben Regeln;
   Ausgabe `BRANCH=… PR=… CI=green|red|none MERGED=yes|no|skipped`, bei `CI=red` `FAILED_CHECKS=` (dann Punkt 5).
   Bei `AUTO_SHIP=off` ohne `--merge`.
4. **Deploy bleibt beim PO.** Der Auto-Modus löst nie ein Deploy aus; `deploy.autonomous` (oben) ist eine
   getrennte Projekt-Entscheidung, von `AUTONOMY=auto` weder gesetzt noch ersetzt. Kein `/70-deploy` aus dem Auto-Modus.
5. **Ausliefern (Merge und PR, #525)** —
   **Bei `AUTO_SHIP=on` liefert Claude selbst aus:** Nach Punkt 2 und 3 im selben Turn den PR vom
   Feature-Branch auf den Default-Branch anlegen (PR-Vorlage des Repos beachten), die CI abwarten
   (PR-Aktivität abonnieren statt Polling, wo verfügbar) und bei grüner CI und konfliktfreiem PR
   mergen, mit der im Repo üblichen Methode (an der Historie des Default-Branchs ablesbar, im
   Zweifel Squash); danach den Feature-Branch auf den neuen Stand bringen. Merge-Konflikt:
   Default-Branch in den Feature-Branch mergen, Konflikt lösen, Tests erneut laufen lassen, wieder
   warten. Bei roter CI die Ursache suchen und beheben (ein Code-Fix zählt wie BROKEN: zurück zu
   `phase6_implement`) oder, wenn nicht aus diesem Änderungssatz behebbar, das Problem in
   Alltagssprache melden. Hat das Repo keine CI-Checks, wird auf Basis der grünen lokalen
   Testsuite aus Phase 7 gemergt. Schutzregeln (Pflicht-Reviews, Branch-Protection) werden nie
   umgangen, nie `--force`, rote CI nie überbrücken; verhindert eine Schutzregel den Merge, lautet
   die Meldung „wartet auf Prüfung durch einen Techniker“. Auch ohne Zugang zu Remote oder GitHub:
   in Alltagssprache melden, nie ein Git-Auftrag an den PO. Die Abschlussmeldung nennt dem PO
   keinen Git-Schritt, auch nicht für den neu angelegten Branch.
   **Bei `AUTO_SHIP=off`** gilt unverändert:
   **Merge und PR — Git-Policy des Projekts sticht:** Steht in der `CLAUDE.md` des Projekts
   (oder in der Memory), dass Claude Git und Auslieferung selbst erledigt (Formulierungen wie
   „Git entscheidet Claude selbst“, „bis `main` ausliefern“, „PO will mit Git nichts zu tun haben“),
   dann ist das bindend: Du legst den PR an, wartest die CI ab und lieferst nach den dort
   beschriebenen Regeln (z. B. Vorspulen) selbst auf den Default-Branch aus, im selben Turn, und
   meldest nur das Ergebnis. Das Verbot aus Punkt 3 (nie `main` pushen) gilt dann nur so weit,
   wie die Projektregel den Weg nicht ausdrücklich vorgibt; nie `--force`, nie Schutzregeln
   umgehen, rote CI nie überbrücken. Auch ohne ausdrückliche Policy liegen PR und Merge beim Tech Lead
   (Claude), nie beim PO (PO-Vorgabe 2026-11-08): PR anlegen, CI abwarten, bei grün mergen und
   dem PO nur das Ergebnis melden.
   **Versions-Bump bei Einzel-Auslieferung (#640):** gilt die Projektregel (Framework-Repo: `docs/arbeitsweise.md`):
   ein Issue allein und sofort veröffentlicht → Bump im Fix-/Feature-PR; Release-PR nur beim Bündeln mehrerer Issues.
6. **Automatische Freigaben auflisten** — für die Abschlussmeldung:

   ```bash
   $WF approvals --auto
   ```

   Ausgabe `APPROVALS=<n>`, dann je Eintrag `- <gate> | <by> | <at> | <reason>` → als Gate, Zeit und Grund
   in die Abschlussmeldung; bei `APPROVALS=0` „keine automatischen Freigaben".

Immer menschlich bleiben — auch bei `AUTONOMY=auto`: AMBIGUOUS-Verdict, zweites BROKEN bzw. Circuit Breaker, Override, Deploy, Stop-Lock.

### Zusammenfassung an den User

---
✅ **Alles fertig und geprüft.**

**Was wurde umgesetzt:** [Feature/Bugfix in 1–2 Sätzen aus Nutzerperspektive]

**Ergebnis:**
- Alle Qualitätsprüfungen bestanden
- Alle Anforderungen aus dem Plan erfüllt
- Keine bestehenden Funktionen beeinträchtigt

**Bereit für:** Sichern[, dann Deploy — falls im Projekt vorgesehen]

Soll ich den Stand sichern?

---

**Ausnahmen:** Autonomie dokumentiert oder keine beobachtbare Oberfläche → Ankündigung aus der Tabelle statt
der Frage. `AUTONOMY=auto`: letzte Zeile durch Ergebnis plus Block ersetzen, keine Commit-Frage.

Bei `AUTO_SHIP=on` (Claude hat ausgeliefert, siehe Punkt 5):

```
**Ergebnis:** <PR-Link> · gemergt ja/nein · <Merge-Commit>   (sonst in Alltagssprache, warum nicht)
**Automatisch freigegeben:**
- <Gate> · <Zeit> · <Grund>     (je Zeile aus `workflow.py approvals --auto`)
```

Die ❗Du-Zeile nennt nie einen Git-Schritt (PR, Merge, Push, Branch, Commit); die Endzustand-Zeile kommt nur
aus `workflow.py endstate`.

Bei `AUTO_SHIP=off` (Ergebnis: Commit-Hash, gepushter Branch):

```
**Automatisch freigegeben:**
- <Gate> · <Zeit> · <Grund>     (je Zeile aus `workflow.py approvals --auto`)
```

Auch hier nennt die Endzustand-Zeile nie einen Git-Schritt, siehe Punkt 5.

### Abschluss: Endzustand melden (Pflicht, #550)

Auch nach `complete`:

```bash
$WF endstate <N>
```

Den Wert hinter `FOOTER=` **wörtlich** als Endzustand-Zeile ausgeben — genau eine Form: `✅ Erledigt: …`,
`⏳ Läuft noch: …` oder `❗ Du: … — …`; nichts erfinden, keine zweite Abschlusszeile. `SHIP_STATUS=open`/`running`
trotz Auslieferung: erst `ship-status done` (Step 4). Warten auf CI, Agent, Server: `ship-status running --note
"<worauf>"` bzw. `workflow.py waiting "<worauf>" <N>`, dann `endstate` erneut.

Kette bei offenem Auftrag (#551, #555): Sie greift nur, wenn der Wert hinter `FOOTER=`
„aus deinem Auftrag“ enthält; `M` ist die Nummer darin (dieselbe wie `NEXT=M` aus
`$WF queue`). Bei `ENDSTATE=waiting` (`⏳ Läuft noch: Claude
startet #M aus deinem Auftrag. …`, autarker Auftrag) gib die Zeile aus und übergib #M an eine
frische Sitzung (`workflow.py handoff`, #667), kein Halt für `/clear`: erst `$WF handoff`, dann je nach `HANDOFF=`:
Steht `HANDOFF_DONE=` in der Ausgabe, ist #M schon übergeben (#668): ⏳-Zeile ausgeben und
Turn beenden, keine weitere Sitzung starten (weder `create_session` noch `--start` noch
Selbstaufruf).
- `cloud`: Werkzeug `create_session` (claude-code-remote) mit `prompt` = Text zwischen
  `PROMPT_BEGIN` und `PROMPT_END`, `source_url` = `REPO_URL` (nur wenn ≠ `none`), Titel „#M …“.
  Bei Erfolg `$WF handoff --mark cloud`, ⏳-Zeile ausgeben, Turn
  beenden, kein Selbstaufruf; misslingt `create_session`, weiter wie `inline`.
- `herdr`: `$WF handoff --start`; bei `STARTED=yes` (auch mit
  `WARN=`) oder `STARTED=already` Turn beenden, bei `STARTED=no` weiter wie `inline`.
- `inline` (auch `none`): wie bisher `/00-intake #M` selbst aufrufen.

Bei `ENDSTATE=you` (`❗ Du: /00-intake #M — …`,
Auftrag nicht autark) gib die Zeile wörtlich aus und warte auf den PO. Ein `ENDSTATE=waiting`
ohne „aus deinem Auftrag“ (CI, Deploy, Agent) startet keine Kette.

Vorschlag (#589): Ohne nächstes Issue aus dem Auftrag nennt die ✅-Zeile hinter `FOOTER=` oft schon die nächste
Aufgabe („… mit /00-intake #M weitermachen (<Grund>).“), dazu `SUGGEST_ISSUE=M`,
`SUGGEST_SOURCE=epic|milestone|spur|related|priority`, `SUGGEST_REASON=`; bei `SUGGEST_SOURCE=epic-leer` das
Abschlusskriterium des Epics prüfen, nie ein Issue außerhalb vorschlagen. Zeile wörtlich ausgeben, wegen eines
Vorschlags nichts selbst starten — die Kette greift nur bei „aus deinem Auftrag“.

## On Failure

Scheitert die Validierung nach dem Auto-Fix: Status nicht auf complete setzen, Restfehler melden, der User entscheidet
(selbst beheben oder neu implementieren).

## Versions-Marker (Pflicht)

Letzte Nachricht endet so (Gründe: `docs/befehle/fusszeile.md`):

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /60-validate · agent-os-openspec 4.26.7

Erste Zeile genau einmal, in einer Form: `✅ Erledigt: <was>. …` (abgeschlossen), `⏳ Läuft noch: <worauf gewartet wird>. …` (vorher `workflow.py waiting "…"`, danach `--clear`) oder `❗ Du: …` (PO ist dran, auch wenn du nur auf ihn wartest; dringend `‼️`). Genaue Zeile: `workflow.py endstate`.

Schritt/Phase = Stand AM ENDE dieser Nachricht: Hook-Hinweis („Nächster Pflicht-Schritt“), nach eigenem Phasenwechsel `workflow.py status`; ohne Hinweis keine Statuszeile. Vor `phase8_complete` ist der Schritt Pflicht (nie bei Bedarf/optional), Workflow nie fertig/abgeschlossen/erledigt. In frei formulierten Arbeitsstandsmeldungen steht er vor `/clear`- oder Kosten-Empfehlung (Übergabe-Blöcke oben bleiben unverändert). Platzhalter ersetzen; nach dem Übergabe-Block, ⚙-Zeile wörtlich zuletzt, auch wenn die übrigen Zeilen entfallen.
