---
description: "Intake: Aufgaben-Klassifikation"
disable-model-invocation: false
---

# Intake: Aufgaben-Klassifikation

**Immer der erste Schritt** — vor jedem Feature-Workflow. Auch Bugs starten hier.
Bestimmt den Track und verhindert, dass ein 10-Minuten-Fix 8 Phasen durchläuft.

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/00-intake.md` im Plugin-Ordner — nur bei Bedarf lesen.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
_S="${_H%/core/hooks}/scripts"; [ "$_H" = ".claude/hooks" ] && _S=".claude/scripts"
```

## Scoring

Bewerte die Aufgabe anhand von 3 Kriterien:

| Kriterium | Low (0) | Medium (1) | High (2) |
|-----------|---------|------------|---------|
| **Scope** | 1–3 Dateien, ≤30 LoC | 4–8 Dateien, ≤100 LoC | Neue Architektur, neue Dateien |
| **Blast Radius** | Internes Utility, isoliert | Service-Schnittstelle | Infra, Auth, kritischer Pfad, Breaking Change |
| **Unsicherheit** | Bekanntes Pattern, vertrauter Code | Teilweise bekannt | Neue Technologie, unbekannter Bereich |

**Summe 0**: Fast Track (`feature-fast`) — Phasen 3→4→6→8
**Summe ≥ 1**: Voller Prozess (`feature`) — alle Phasen 1→8, Adversary: mindestens 2 Dialog-Runden bei hohem Risiko, eine Runde bei niedrigem Risiko
(`MIN_ROUNDS` in `adversary_dialog.py`). Das Risiko folgt mechanisch aus der Dateiliste der Änderung
(Hook-/Gate-Code, Guards, Konfiguration = hoch; nur Anweisungstext, Doku, Tests = niedrig; im Zweifel hoch) —
`python3 ${_H}/adversary_dialog.py risk` zeigt Stufe, Grund und geforderte Runden (#342)

## Deine Aufgaben

### 1. Aufgabe verstehen + schnell recherchieren

Lies den Aufgaben-Kontext aus dem Gespräch (ARGUMENTS oder letzte User-Nachricht).
Bei Unklarheit über Scope: `grep -rn "keyword" --include="*.py" -l | head -10`.

### 1b. Issue-Nummer(n) ins Session-Register eintragen

Sobald die Issue-Nummer(n) bekannt sind — noch vor der Track-Bewertung:

```bash
python3 ${_H}/session_singleton_guard.py claim --issue <N>[,<M>...]
```

Ohne Issue-Nummer entfällt der Schritt.

### 1c. Issue-Kurzfassung für den Plan prüfen

```bash
$WF issue-brief <N>
```

Ist `PROBLEM=` oder `ZIEL=` leer, nichtssagend oder falsch, schreibe nach dem Lesen des Issues
selbst je ein bis zwei Sätze in Alltagssprache:

```bash
$WF issue-brief <N> --problem "<was heute stört>" --ziel "<was danach gilt>"
```

### 1a. Mehr-Issue-Auftrag sichern (#551)

Erteilt der PO mehrere Issues in einem Auftrag, sichere ihn vor dem ersten Workflow per `workflow.py queue add`:

```bash
$WF queue add <N...> [--autark] [--note "<Wortlaut>"] [--spur <name>]
```

`--autark` nur, wenn der PO „autark“ bzw. „melde dich nur, wenn …“ gesagt hat.
`--spur <name>` (auch einzeln: `workflow.py spur <name>`), wenn der PO eine Spur genannt hat
oder die Aufgabe zu einer erkennbaren Reihe gehört (#591): nach „fertig“ schlägt `endstate`
dann offene Issues mit dem GitHub-Label `spur:<name>` vor. Epic und Meilenstein haben Vorrang.
Meldet `workflow.py queue` `ALTAUFTRAG=`, nur per `workflow.py queue claim` übernehmen, wenn er
nachweislich dieser Sitzung gilt. Bei nur einem Issue entfällt der Schritt.

**Planung autarker Aufträge (#622):** Bei einem autarken Auftrag keine Schritte
einplanen, die eine menschliche Sperre (override) brauchen, wenn eingebaute
Standardwerte oder ein anderer Weg genügen. Änderungen an der wirksamen Gate-Config
vermeiden; nur die reinen Anzeige-Abschnitte `next_suggestion` und `time_estimate`
sind per Edit ohne override änderbar (Bash-Schreibzugriffe auf die Config bleiben gesperrt).

### 1c. Bugs: Vorprüfung vor dem Scoring

Bei einem Fehlerbericht, noch bevor bewertet wird:

1. **Duplikatsuche:** `gh issue list --label "bug" --state open` und
   `gh issue list --search "<Stichwort>" --state open`. Duplikat → bestehendes Issue verwenden.
2. **Fehler nachstellen** und die Ursache mit `file:line` belegen (Vorgehen: `/20-analyse` Step 2b).
3. **Scoring speisen:** Ursache bekannt und ≤3 Dateien → Unsicherheit **Low**.
   Ursache unklar → Unsicherheit mindestens Medium.
4. **STOP** und nachfragen, wenn: Ursache unklar, nicht reproduzierbar, mehrere mögliche Ursachen,
   Fix > 5 Dateien.

Kein eigener Bug-Typ: Nachweis ist ein Test, der den Fehler vorher rot zeigt.

### 2. Score präsentieren und Track vorschlagen

Gib dem User exakt dieses Format aus:

```
## Intake-Bewertung: [Aufgaben-Titel]

| Kriterium     | Score  | Begründung            |
|---------------|--------|-----------------------|
| Scope         | Low    | 2 Dateien, ~20 LoC    |
| Blast Radius  | Low    | Internes Utility      |
| Unsicherheit  | Low    | Bekanntes Pattern     |

Summe: 0 → **Fast Track** · Modell: **Sonnet**

Was das bedeutet:
- Kein Context-Doc, keine Analyse-Phase
- Mini-Spec (Bullets statt vollständige Spec) + User-Freigabe
- Inline-Test während Implementierung (kein separates TDD-RED)
- Kein Adversary Agent
```

Modell: Sonnet bei Fast Track und Summe 1–3, Opus bei Summe 4–6.
**Workflow-Name:** Leite ihn selbst aus dem Aufgaben-Titel ab (Issue-Nummer + Stichwort, z.B. `fix-862-col-labels`). Nie beim User erfragen.

### 2b. Autonomie prüfen (#472)

```bash
$WF autonomy
```

- **`AUTONOMY=auto`** — übernimm den Track-Vorschlag ohne Rückfrage: Bewertung
  ausgeben (als Info, ohne Frage nach dem Track) und den Workflow aus Step 3
  sofort mit `workflow.py start` starten, dann direkt mit dem nächsten Befehl
  weiter. Fast Track nur bei Summe 0 — im Zweifel höher bewerten, nie
  herunterrunden. Die Rückfrage-STOPs aus Step 1c bleiben: Ursache unklar, nicht
  reproduzierbar, mehrere mögliche Ursachen oder Fix > 5 Dateien → STOP und
  nachfragen, auch bei `AUTONOMY=auto`.
- **`AUTONOMY=manual`** (oder jede andere Ausgabe) — wie bisher: Track vorschlagen
  und auf die Bestätigung des Users warten.

Immer menschlich bleiben — auch bei `AUTONOMY=auto`: AMBIGUOUS-Verdict, zweites BROKEN bzw. Circuit Breaker, Override, Deploy, Stop-Lock.

### 3. Workflow starten (nach User-Bestätigung des Tracks, bei `AUTONOMY=auto` sofort)

`--issue <N>` nur, wenn die Issue-Nummer bekannt ist. `--score <S>` immer mit der Summe aus Step 2 (0–6) (#620).

**Registrierung am Issue (#461):** Bricht `start` mit `ABGEBROCHEN: An Issue #N arbeitet bereits eine andere
Sitzung` ab, entsteht kein Workflow: nicht weiterarbeiten, dem PO in einfachen Worten sagen, wer
wo seit wann daran arbeitet. `start <name> --uebernehmen` nur, wenn die andere Sitzung nachweislich nicht mehr
arbeitet oder der PO zustimmt.

**Fast Track:**
```bash
$WF start [name] --type feature-fast --issue <N> --score <S>
export OPENSPEC_ACTIVE_WORKFLOW=[name]
```
→ Weiter mit `/30-write-spec` (Mini-Spec-Vorlage: `docs/befehle/00-intake.md`, Abschnitt „Mini-Spec (Fast Track)“); nach "approved" direkt zu `/50-implement`.

**Auto-Modus (`autonomy.mode: auto`, #470):** Auch der Fast Track braucht dann ein
unabhängiges PO-Briefing mit `## Ampel`. Also nach der Mini-Spec den `po-briefer` laufen lassen
(`/30-write-spec` Step 3b), `workflow.py set-briefing <pfad>` und danach
`workflow.py auto-approve`: `AUTO_APPROVE=done` → direkt weiter zu `/50-implement`,
`AUTO_APPROVE=human` → der PO gibt wie bisher mit "approved" frei.

**Voller Prozess:**
```bash
$WF start [name] --type feature --issue <N> --score <S>
export OPENSPEC_ACTIVE_WORKFLOW=[name]
```
→ Summe 1–3: weiter mit `/10-context` (Context + Analyse in einem Durchgang kombinieren)
→ Summe 4–6: weiter mit `/10-context`, dann `/20-analyse` (getrennt, 3x parallele Agenten), dann `/30-write-spec`

**Zeitschätzung (#620, #642), direkt nach dem Start:**
```bash
$WF estimate
```
Meldet `workflow.py estimate` `ESTIMATE=on`, den Satz aus `LINE=` als letzte Zeile der Intake-Bewertung nennen; bei `ESTIMATE=off` weglassen.

Beim Fast Track bleiben IMMER aktiv: Spec + User-Freigabe, Rebase-Gate, Secrets Guard, Stop-Lock.

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /00-intake · agent-os-openspec 4.26.2

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von drei Formen (es gibt keine vierte):

- `✅ Erledigt: <was>. Du kannst /clear ausführen und das nächste Issue starten.` — nur wenn der Workflow wirklich abgeschlossen ist.
- `⏳ Läuft noch: <worauf gewartet wird>. Du musst nichts tun, ich melde mich.` — du wartest auf CI, einen Hintergrund-Agenten oder einen Server.
- `❗ Du: …` (`❗ Du: <Schritt> — <warum>`), wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist immer ❗, nie ⏳.

Beendest du einen Turn, während du auf CI, Agent oder Server wartest, setze vorher `workflow.py waiting "<worauf>"` und gib die ⏳-Zeile aus; ist das Ergebnis da, `workflow.py waiting --clear`. Die passende Zeile liefert `workflow.py endstate [#<N>]` als `FOOTER=…` — gib sie wörtlich aus. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase geben den Stand AM ENDE dieser Nachricht wieder. Quelle ist der Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — aber nur, solange du die Phase in dieser Nachricht nicht selbst gewechselt hast. Hast du per `workflow.py phase <x>` (oder `complete`) gewechselt, beschreibt der Hinweis den Stand von Turn-Beginn; maßgeblich ist dann der neue Stand, den `workflow.py status` zeigt. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfällt die Statuszeile; die erste Zeile kommt dann aus `workflow.py endstate #<N>` und entfällt nur ohne Workflow. Die Marker-Zeilen entfallen NIE wegen eines Phasenwechsels; die ⚙-Zeile bleibt immer die letzte Zeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.
