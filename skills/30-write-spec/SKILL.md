---
description: "Write a specification for the current feature or bug fix"
disable-model-invocation: false
---

# Phase 3: Write Specification

You are in **Phase 3 - Specification Writing**.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
```

## Step 0: Workflow-State auflösen (ZUERST — vor allem anderen)

**Wurde dieser Befehl mit einer Issue-Nummer aufgerufen** (z. B. `/30-write-spec #42` — typisch nach einem `/clear`)? Dann aktiviere den Workflow explizit. Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58).

```bash
ISSUE=42   # die übergebene Nummer (ohne #)
python3 - "$ISSUE" <<'PY'
import sys, json, glob, re, os
issue = sys.argv[1].lstrip('#')
pat = re.compile(rf'(^|[-_]){re.escape(issue)}([-_]|$)')
hits = []
for f in glob.glob('.claude/workflows/*.json'):
    name = os.path.basename(f)[:-5]
    if pat.search(name):
        d = json.load(open(f))
        hits.append((name, d.get('current_phase'), d.get('spec_file') or 'Not created'))
if not hits:
    print(f'KEIN laufender Workflow fuer #{issue} (evtl. abgeschlossen -> .claude/workflows/_archive/).')
else:
    for name, ph, spec in hits:
        print(f'GEFUNDEN: {name} | Phase={ph} | Spec={spec}')
    print('\nNAME=' + hits[0][0])
PY
```

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen) und den Stand verifizieren:

```bash
$WF switch <NAME-aus-obigem-Output>
$WF status
```

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Analyse-Stand. Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht — damit sichtbar ist, dass der `/clear` nichts verloren hat.

**Ohne Issue-Argument** (laufende Session, kein `/clear` dazwischen): `workflow.py status` reicht direkt.

## Fast Track (workflow_type == feature-fast)

Prüfe zuerst den Workflow-Typ:
```bash
$WF status
```

Wenn `workflow_type: feature-fast` → **kein Sonnet-Agent, kein Haiku-Validator**.
Schreibe direkt eine Mini-Spec im Hauptkontext:

- Datei: `docs/specs/fast/[name].md`
- Format: laut `/00-intake` → Mini-Spec-Template
- Dann: `workflow.py set-field spec_file "docs/specs/fast/[name].md"`
- Dann: Freigabe vom User abwarten ("approved")
- **Kein PO-Briefing** (Gate überspringt Fast Track). Wer es auch hier will:
  `config.yaml` → `po_briefing_gate.skip_fast_track: false`, dann gilt Step 3b auch im Fast Track.
- Nach Freigabe: direkt zu `/50-implement`

**Standard- und Full-Process-Workflows** folgen dem normalen Ablauf unten.

---

## Prerequisites (Standard / Full Process)

- Analysis completed (`phase2_analyse`)
- Context document exists with affected files list

Check current workflow:
```bash
$WF status
```

## Your Tasks

### Step 1: Vorbereitung

Lies die Analyse-Ergebnisse aus `docs/context/[workflow-name].md` und das Template aus `docs/specs/_template.md`.

### Step 2: Spec erstellen (general-purpose/Sonnet)

Dispatche einen **general-purpose/Sonnet Subagenten** mit den spec-writer Instruktionen:

```
Task (general-purpose/sonnet, run_in_background: true): "Du bist der spec-writer Agent.

  Input:
  - feature_name: [Name]
  - analysis_summary: [Zusammenfassung aus Phase 2]
  - affected_files: [Liste aus Analyse]
  - dependencies: [Liste aus Analyse]
  - workflow_name: [Workflow-Name]

  Erstelle eine vollstaendige Spec in docs/specs/[category]/[entity].md
  nach dem spec-writer Workflow. Beachte alle Qualitaetsregeln."
```

**TIMEOUT-PFLICHT — sofort nach dem Spawn:**
```
ScheduleWakeup(300, "Spec-Writer Timeout [30-write-spec Step 2]: TaskList → noch aktiv? JA → TaskStop, dann User: 'Spec-Writer nach 5 Min gestoppt — bitte /30-write-spec neu starten.' NEIN → ignorieren, fertig.")
```

### Step 3: Spec validieren (spec-validator/Haiku)

Dispatche den **spec-validator/Haiku** zur Validierung:

```
Task (general-purpose/haiku, run_in_background: true): "Du bist der spec-validator Agent.

  Validiere die Spec: docs/specs/[category]/[entity].md
  Pruefe alle Required Fields, Sections, Placeholders.
  Output: VALID oder INVALID mit Details."
```

**TIMEOUT-PFLICHT — sofort nach dem Spawn:**
```
ScheduleWakeup(180, "Spec-Validator Timeout [30-write-spec Step 3]: TaskList → noch aktiv? JA → TaskStop, dann User: 'Spec-Validator nach 3 Min gestoppt — bitte Step 3 neu starten.' NEIN → ignorieren, fertig.")
```

**Bei INVALID:**
1. Behebe die gemeldeten Fehler in der Spec
2. Dispatche spec-validator erneut
3. Wiederhole bis VALID

### Step 3b: PO-Briefing erstellen (po-briefer/Sonnet) — PFLICHT vor der Freigabe

Die Freigabe ist die einzige Stelle, an der ein Mensch entscheidet. Sie darf nicht
auf deiner eigenen Zusammenfassung beruhen — du hast die Spec beauftragt, du bist
befangen. Dispatche deshalb einen **unabhängigen** Briefer, der die Spec gegen die
Ursprungsanfrage prüft, ohne deinen Gesprächsverlauf zu kennen:

```
Task (general-purpose/sonnet, run_in_background: true): "Du bist der po-briefer Agent.

  ## Spec
  docs/specs/[category]/[entity].md

  ## Ursprungsanfrage
  Issue #[N]: [Titel + Text]   (ersatzweise: docs/context/[workflow].md)

  ## Workflow
  [workflow-name]

  Folge dem po-briefer Protokoll. Schreibe docs/briefings/[workflow-name].md."
```

**TIMEOUT-PFLICHT — sofort nach dem Spawn:**
```
ScheduleWakeup(240, "PO-Briefer Timeout [30-write-spec Step 3b]: TaskList → noch aktiv? JA → TaskStop, dann User: 'PO-Briefer nach 4 Min gestoppt — bitte Step 3b neu starten.' NEIN → ignorieren, fertig.")
```

Danach registrieren — ohne diesen Schritt blockiert das Gate die Freigabe:

```bash
$WF set-briefing docs/briefings/[workflow-name].md
```

Der Befehl bindet das Briefing per SHA-256 an die gelesene Spec-Fassung. **Änderst
du die Spec danach noch, wird das Briefing ungültig** — dann Step 3b wiederholen,
nicht die Registrierung von Hand nachziehen.

Das Briefing wird dem User **wörtlich** ausgegeben (siehe unten). Du fasst es nicht
zusammen, kürzt es nicht und glättest seine kritischen Anmerkungen nicht — sonst ist
die Unabhängigkeit wieder weg.

### Step 4: Workflow State aktualisieren

```bash
# Update spec file path in workflow
$WF set-field spec_file "docs/specs/[category]/[entity].md"

# Advance to spec_written phase
$WF phase phase3_spec
```

## Next Step

### Freigabe-Ausgabe an den User

Du schreibst **keine eigene Zusammenfassung** der Spec. Was gebaut wird, wo vom
Ticket abgewichen wurde und was fragwürdig ist, steht im unabhängigen Briefing —
eine zweite Fassung von dir wäre wieder Selbstauskunft und verdoppelt nur den Text.

Die Ausgabe besteht aus genau diesen Teilen, in dieser Reihenfolge:

1. **Das Briefing wörtlich** — Inhalt von `docs/briefings/<workflow-name>.md` ab
   `## Was gebaut wird` bis zum Ende. Nichts weglassen, nichts umformulieren.
2. **Optional: deine Gegenstimme** — nur zu einer *Kritischen Anmerkung*, der du
   widersprichst, je genau eine Zeile `Meine Einschätzung: …`, höchstens 3 Zeilen
   insgesamt. Stimmst du allen Anmerkungen zu: nichts schreiben.
3. **❗Du-Zeile + Marker-Zeile** — wörtlich, als letzte beiden Zeilen, `⚙` ganz zuletzt:
   `❗ Du: \`approved\` — Freigabe der Spec, danach beginnt die Umsetzung`
   `⚙ PO-Briefing unabhängig erstellt · agent-os-openspec 3.30.3`
   Diese Freigabe verlangt *immer* eine PO-Entscheidung — anders als bei den generischen
   Pflicht-Markern in anderen Befehlen gibt es hier keine `ℹ️ Nichts-zu-tun`-Variante.

Vorlage:

---
[Briefing ab '## Was gebaut wird' WÖRTLICH]

Meine Einschätzung: [nur bei Widerspruch zu einer Anmerkung — sonst weglassen]

❗ Du: `approved` — Freigabe der Spec, danach beginnt die Umsetzung
⚙ PO-Briefing unabhängig erstellt · agent-os-openspec 3.30.3

---

## After Approval

When user approves:
1. `workflow_state_updater` hook detects approval phrase
2. State advances to `phase4_approved`
3. Next: `/40-tdd-red` to write failing tests

Ohne `/clear` in derselben Session: Rufe den Skill `40-tdd-red` jetzt sofort selbst
auf — warte nicht auf eine weitere User-Eingabe, die Freigabe ("approved") ist
bereits die Entscheidung.

Mit `/clear` dazwischen: Der Checkpoint-Block unten zeigt den regulären
Wiedereinstieg über den expliziten Befehl `/40-tdd-red #<N>`.

Nach der Freigabe kannst du dem User zusätzlich den Kontext-Reset anbieten:

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
- Do NOT skip TDD RED phase after approval
- Die Freigabe-Ausgabe ist das Briefing wörtlich plus Marker-Zeile — keine eigene
  Zusammenfassung davor oder danach. Abweichungen vom Ticket benennt der po-briefer
  unter *Kritische Anmerkungen*. Widersprichst du einer Anmerkung: eine
  "Meine Einschätzung"-Zeile je Anmerkung, max. 3 — kein eigener Block.
