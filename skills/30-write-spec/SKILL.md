---
description: "Write a specification for the current feature or bug fix"
disable-model-invocation: false
---

# Phase 3: Write Specification

You are in **Phase 3 - Specification Writing**.

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/30-write-spec.md` im Plugin-Ordner — nur bei Bedarf lesen.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
_S="${_H%/core/hooks}/scripts"; [ "$_H" = ".claude/hooks" ] && _S=".claude/scripts"
```

## Step 0: Workflow-State auflösen (ZUERST — vor allem anderen)

**Aufruf mit Issue-Nummer** (z. B. `/30-write-spec #42`, typisch nach `/clear`)? Workflow explizit aktivieren (`export` reicht NICHT):

```bash
$WF find 42   # die übergebene Nummer
$WF switch <NAME-aus-obigem-Output>
$WF status
```

Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht. **Ohne Issue-Argument:** `workflow.py status` reicht.

## Fast Track (workflow_type == feature-fast)

Bei `workflow_type: feature-fast` **kein Sonnet-Agent, kein Haiku-Validator**: Mini-Spec im Hauptkontext nach
`docs/specs/fast/[name].md` (Vorlage: `docs/befehle/00-intake.md`, Abschnitt „Mini-Spec (Fast Track)“),
`workflow.py set-field spec_file "docs/specs/fast/[name].md"`, Freigabe ("approved") abwarten, dann `/50-implement`.
**Kein PO-Briefing**, außer bei `po_briefing_gate.skip_fast_track: false` oder Auto-Modus (dann Step 3b).

## Your Tasks

### Step 1: Vorbereitung

Lies `docs/context/[workflow-name].md` und das Template `docs/specs/_template.md`.

**Autarker Auftrag (#622):** Bei `AUTARK=on` (`workflow.py queue`) keine Spec-Schritte einplanen, die eine
menschliche Sperre (override) brauchen, wenn Standardwerte oder ein anderer Weg genügen; keine Änderungen an der
wirksamen Gate-Config (nur `next_suggestion` und `time_estimate` per Edit ohne override). Hinweis an den spec-writer weiterreichen.

### Hängende Subagenten

Die Sitzung wird automatisch erneut aufgerufen, sobald der Hintergrund-Agent fertig ist. Sonst beim nächsten Zug
`TaskList` prüfen, noch aktiv → `TaskStop` und neu starten. Nur im `/loop`-Lauf zusätzlich:

```
ScheduleWakeup(1200, "[30-write-spec] /loop-Rückfall: TaskList → Agent aktiv? JA → TaskStop, User: 'Agent hängt — /30-write-spec neu starten.' NEIN → fertig.")
```

### Agent-Typen und Fallback (#577)

Start **ohne `model`**. **Fallback, wenn ein Typ fehlt:**
- spec-writer → `agent-os-openspec:spec-writer`, sonst `Agent(subagent_type="general-purpose", model="sonnet", prompt="Lies zuerst .claude/agents/spec-writer.md und folge ihr. …")`
- spec-validator → `agent-os-openspec:spec-validator`, sonst `Agent(subagent_type="general-purpose", model="haiku", prompt="Lies zuerst .claude/agents/spec-validator.md und folge ihr. …")`
- po-briefer → `agent-os-openspec:po-briefer`, sonst `Agent(subagent_type="general-purpose", model="sonnet", prompt="Lies zuerst .claude/agents/po-briefer.md und folge ihr. …")`

### Step 2: Spec erstellen (spec-writer/Sonnet)

```
Agent(subagent_type="spec-writer", description="Spec schreiben", run_in_background=true, prompt="
  feature_name, analysis_summary, affected_files, dependencies, workflow_name: [aus Phase 2]
  Erstelle eine vollstaendige Spec in docs/specs/[category]/[entity].md nach dem spec-writer Workflow.")
```

### Step 3: Spec validieren (spec-validator/Haiku)

Im Vordergrund (`run_in_background: false`, #83); bei INVALID Fehler beheben und erneut validieren bis VALID:

```
Agent(subagent_type="spec-validator", description="Spec validieren", run_in_background=false, prompt="
  Validiere die Spec: docs/specs/[category]/[entity].md — Output: VALID oder INVALID mit Details.")
```

### Step 3b: PO-Briefing erstellen (po-briefer/Sonnet) — PFLICHT vor der Freigabe

Ein **unabhängiger** Briefer prüft die Spec gegen die Ursprungsanfrage:

```
Agent(subagent_type="po-briefer", description="PO-Briefing schreiben", run_in_background=true, prompt="
  Spec: docs/specs/[category]/[entity].md
  Ursprungsanfrage: Issue #[N]: [Titel + Text] (ersatzweise docs/context/[workflow].md)
  Workflow: [workflow-name]. Folge dem po-briefer Protokoll. Schreibe docs/briefings/[workflow-name].md.")
```

Danach registrieren (sonst blockiert das Gate die Freigabe):

```bash
$WF set-briefing docs/briefings/[workflow-name].md
```

**Änderst du die Spec danach noch, wird das Briefing ungültig** — Step 3b wiederholen; nach einem Rücksprung ebenso (#647).

### Step 4: Workflow State aktualisieren

```bash
$WF set-field spec_file "docs/specs/[category]/[entity].md"
$WF phase phase3_spec
```

### Step 4b: Auto-Freigabe versuchen (#470)

```bash
$WF auto-approve
```

- **`AUTO_APPROVE=done`** — Briefing wörtlich als Info, „automatisch freigegeben (Ampel grün)", **ohne** ❗Du-Zeile;
  dann `40-tdd-red` selbst aufrufen (Kontext-Prüfung unten).
- **`AUTO_APPROVE=human`** — Freigabe-Ausgabe unten; `REASON` nur im Auto-Modus nennen.

## Next Step

### Freigabe-Ausgabe an den User (bei `AUTO_APPROVE=human`)

**Keine eigene Zusammenfassung** der Spec. Genau diese Teile, in dieser Reihenfolge:

1. **Das Briefing wörtlich** ab `## Was gebaut wird` bis zum Ende.
2. **Optional:** je widersprochener *Kritischer Anmerkung* eine Zeile `Meine Einschätzung: …`, max. 3.
3. **❗Du-Zeile + Marker-Zeile** als letzte beiden Zeilen (keine `⏳`-/`✅`-Variante):

---
[Briefing ab '## Was gebaut wird' WÖRTLICH]

Meine Einschätzung: [nur bei Widerspruch zu einer Anmerkung — sonst weglassen]

❗ Du: `approved` — Freigabe der Spec, danach beginnt die Umsetzung
⚙ PO-Briefing unabhängig erstellt · agent-os-openspec 4.26.2

---

## After Approval

Nach "approved": State advances to `phase4_approved`.
Ohne `/clear`: Rufe den Skill `40-tdd-red` jetzt sofort selbst auf — "approved" ist bereits die Entscheidung.
Mit `/clear`: Wiedereinstieg über `/40-tdd-red #<N>` (Checkpoint unten).

Vor dem Selbstaufruf zusätzlich `$WF context` ausführen (Kontext-Haushalt): Bei `CONTEXT_STOP=on` (Kontext über der wirksamen Schwelle `CONTEXT_THRESHOLD` aus `context_budget`: Grundkontext der Sitzung + `growth_tokens`, mindestens `clear_threshold_tokens`, Default 100.000 Token, nur im Modus manual) den Skill `40-tdd-red` NICHT selbst aufrufen, sondern die Antwort mit dem Checkpoint und der ❗Du-Zeile `/40-tdd-red #<N>` beenden — der Stand liegt auf der Platte, der PO tippt `/clear`. Bei `CONTEXT_STOP=off` oder `CONTEXT_TOKENS=unknown`: Kette unverändert selbst fortsetzen (#658).

### Checkpoint prüfen (Anweisung an dich — nicht ausgeben)

Prüfe der Reihe nach, bevor du unten etwas ausgibst:

- Phase im Workflow-State geschrieben — `$WF status` bestätigt sie
- Alle Ergebnisdateien dieser Phase liegen auf der Platte
- Keine Erkenntnis, die für `/40-tdd-red` nötig und nirgends niedergeschrieben ist

Sind alle Punkte erfüllt: Gib den Positiv-Block aus. Ist mindestens einer verletzt: Gib stattdessen den Negativ-Block aus und ersetze dessen Platzhalter durch den konkreten Sicherungsschritt.

Weder diese Anweisung noch die `###`-Überschriften gehören in die Ausgabe — an den User geht ausschließlich der Text zwischen den `---`-Trennern, und zwar genau einmal, als letzter inhaltlicher Teil der Nachricht: keine Vorab- oder Kurzfassung davor, keine Wiederholung danach.

### Ausgabe A: Positiv-Block (alle Vorbedingungen erfüllt)

---
**Gesichert auf der Platte:**
- `.claude/workflows/<name>.json` — Phase `phase4_approved`, Feld `spec_file`, Verdict, Artefakt-Register
- `docs/specs/<category>/<entity>.md` — die freigegebene Spec: Acceptance Criteria, Scope, geplante Tests
- `docs/briefings/<workflow-name>.md` — das unabhängige PO-Briefing zur freigegebenen Spec-Fassung

✅ **`/clear` ist jetzt gefahrlos** — alles oben Gelistete stellt der Folge-Befehl allein aus diesen Dateien wieder her. Im Gesprächsverlauf steht nichts, was verloren ginge.

1. `/clear`
2. `/40-tdd-red #<N>`

---

### Ausgabe B: Negativ-Block (mindestens eine Vorbedingung verletzt)

---
⚠️ **`/clear` jetzt NICHT** — Folgendes steht nur im Gesprächsverlauf:
- <was fehlt> → sichern mit: <konkreter Befehl oder Schritt>

Erst sichern, dann ist `/clear` gefahrlos.

---

**IMPORTANT:**
- Do NOT implement until approved
- Die Spec-Freigabe nie per Auswahldialog (`AskUserQuestion`) erfragen, sondern immer mit der ❗Du-Zeile `approved`: der `phase_listener` sieht ausschließlich getippte Nachrichten, eine im Dialog geklickte Freigabe wirkt nicht. Hat der PO im Dialog bereits freigegeben, bitte in genau einer Zeile um das Stichwort (#183, #485)
