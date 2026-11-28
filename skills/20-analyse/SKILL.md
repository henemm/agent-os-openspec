---
description: "Analyse requirements and determine technical approach"
disable-model-invocation: false
---

# Phase 2: Analyse

You are in **Phase 2 - Analysis** of the workflow.

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/20-analyse.md` im Plugin-Ordner — nur bei Bedarf lesen.

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

**Aufruf mit Issue-Nummer** (z. B. `/20-analyse #42`, typisch nach `/clear`)? Workflow explizit aktivieren (`export` reicht NICHT):

```bash
$WF find 42   # die übergebene Nummer
$WF switch <NAME-aus-obigem-Output>
$WF status
```

Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht. **Ohne Issue-Argument:** `workflow.py status` reicht.

## Your Tasks

### Step 1: Bug vs. Feature Routing

Bug (etwas funktioniert nicht) → Step 2b, Feature (neu oder geändert) → Step 2a.

### Hängende Subagenten

Die Sitzung wird automatisch erneut aufgerufen, sobald der Hintergrund-Agent fertig ist. Sonst
`TaskList` prüfen, noch aktiv → `TaskStop`, neu starten.

### Step 2a: Feature-Analyse (3x Explore/Haiku parallel)

```
Agent(subagent_type="Explore", model="haiku", description="Betroffene Dateien", run_in_background=true, prompt="
  Finde alle von [Feature-Bereich] betroffenen Dateien: Pfad, MODIFY/CREATE/DELETE, Begruendung.")
Agent(subagent_type="Explore", model="haiku", description="Bestehende Specs", run_in_background=true, prompt="
  Bestehende Specs in docs/specs/ zu [Feature-Bereich], mit Status.")
Agent(subagent_type="Explore", model="haiku", description="Dependencies", run_in_background=true, prompt="
  Dependencies und Imports fuer [Feature-Bereich]: wer haengt davon ab, was wird importiert?")
```

### Step 2b: Bug-Analyse (bug-intake/Haiku)

Bei Bugs den **bug-intake Agent**, Start **ohne `model`** (#577):

```
Agent(subagent_type="bug-intake", description="Bug-Intake", run_in_background=true, prompt="
  Input: symptom=[Fehlerbeschreibung], context=[Wo/Wann]
  Fuehre parallele Investigation durch und erstelle Bug Report.")
```

**Fallback, wenn der Typ in der Agent-Liste fehlt:** bug-intake → `agent-os-openspec:bug-intake`, sonst `Agent(subagent_type="general-purpose", model="haiku", prompt="Lies zuerst .claude/agents/bug-intake.md (im Framework-Repo core/agents/bug-intake.md) und folge ihr. …")`.

### Step 3: Strategische Bewertung (Plan/Sonnet)

```
Agent(subagent_type="Plan", model="sonnet", description="Strategische Bewertung", run_in_background=true, prompt="
  [Ergebnisse aus Step 2]. Bewerte: 1. Ansatz 2. Risiko 3. Scope (Dateien, LoC) 4. Reihenfolge 5. Befunde gegen den
  Plan (oder „keine“ mit Begruendung); Varianten mit Zahlen als Tabelle VOR der Empfehlung 6. Eine klare Empfehlung")
```

### Step 4: Synthese praesentieren

`docs/context/[workflow-name].md` um `## Analysis` ergänzen: Type, Affected Files (Change Type), Scope/Risk, Technical Approach, Dependencies, Open Questions (Vorlage im Hintergrund).

### Step 5: Update Workflow State

```bash
$WF phase phase3_spec
```

## Next Step

### Checkpoint prüfen (Anweisung an dich — nicht ausgeben)

Prüfe der Reihe nach, bevor du unten etwas ausgibst:

- Phase im Workflow-State geschrieben — `$WF status` bestätigt sie
- Alle Ergebnisdateien dieser Phase liegen auf der Platte
- Keine Erkenntnis, die für `/30-write-spec` nötig und nirgends niedergeschrieben ist

Sind alle Punkte erfüllt: Gib den Positiv-Block aus. Ist mindestens einer verletzt: Gib stattdessen den Negativ-Block aus und ersetze dessen Platzhalter durch den konkreten Sicherungsschritt.

Weder diese Anweisung noch die `###`-Überschriften gehören in die Ausgabe — an den User geht ausschließlich der Text zwischen den `---`-Trennern, und zwar genau einmal, als letzter inhaltlicher Teil der Nachricht: keine Vorab- oder Kurzfassung davor, keine Wiederholung danach.

### Ausgabe: Zusammenfassung (immer)

---
**Analyse abgeschlossen.**

**Art der Aufgabe:** [Feature / Bugfix]

**Was steht an?** [1–2 Sätze was konkret geändert oder gebaut wird — aus Nutzerperspektive, ohne Dateinamen oder Code]

**Risiko:** [Niedrig / Mittel / Hoch] — [kurze Begründung ohne Technik, z.B. "betrifft nur einen isolierten Bereich" oder "ändert eine zentrale Funktion"]

---

### Ausgabe A: Positiv-Block (alle Vorbedingungen erfüllt)

---
**Gesichert auf der Platte:**
- `.claude/workflows/<name>.json` — Phase `phase3_spec`, Verdict, Artefakt-Register
- `docs/context/<workflow-name>.md`, Abschnitt `## Analysis` — Art der Aufgabe, betroffene Dateien mit Change-Type, Scope/Risiko, technischer Ansatz, offene Fragen

✅ **`/clear` ist jetzt gefahrlos** — alles oben Gelistete stellt der Folge-Befehl allein aus diesen Dateien wieder her. Im Gesprächsverlauf steht nichts, was verloren ginge.

1. `/clear`
2. `/30-write-spec #<N>`

---

### Ausgabe B: Negativ-Block (mindestens eine Vorbedingung verletzt)

---
⚠️ **`/clear` jetzt NICHT** — Folgendes steht nur im Gesprächsverlauf:
- <was fehlt> → sichern mit: <konkreter Befehl oder Schritt>

Erst sichern, dann ist `/clear` gefahrlos.

---

Wenn noch offene Fragen bestehen: Zuerst den User fragen, bevor es weitergeht.

### Auto-Modus: Kette selbst fortsetzen (#472)

```bash
$WF autonomy
```

Bei `AUTONOMY=auto`, ohne offene Frage an den User und ohne `/clear`: Rufe den Skill `30-write-spec` jetzt sofort selbst auf, ohne auf den User zu warten; der Checkpoint-Block bleibt in der Ausgabe. Sonst auf den User warten.

Vor dem Selbstaufruf zusätzlich `$WF context` ausführen (Kontext-Haushalt): Bei `CONTEXT_STOP=on` (über `CONTEXT_THRESHOLD`, Default 100.000 Token, nur Modus manual; Herleitung: docs/befehle/10-context.md) den Skill `30-write-spec` NICHT selbst aufrufen, sondern die Antwort mit dem Checkpoint und der ❗Du-Zeile `/30-write-spec #<N>` beenden — der Stand liegt auf der Platte, der PO tippt `/clear`. Bei `CONTEXT_STOP=off` oder `CONTEXT_TOKENS=unknown`: Kette unverändert selbst fortsetzen (#658).

`CONTEXT_HANDOFF=on` (#696): `workflow.py handoff --same --start`; `STARTED=yes`/`already`: `30-write-spec` nicht aufrufen, Turn mit Checkpoint und ⏳-Zeile sofort beenden; `STARTED=no`: weiter.

Immer menschlich bleiben — auch bei `AUTONOMY=auto`: AMBIGUOUS-Verdict, zweites BROKEN bzw. Circuit Breaker, Override, Deploy, Stop-Lock.

**IMPORTANT:** Do NOT start implementation. Analysis -> Spec -> Approve -> TDD RED -> Implement.

## Versions-Marker (Pflicht)

Letzte Nachricht endet so (Gründe: `docs/befehle/fusszeile.md`):

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /20-analyse · agent-os-openspec 4.29.0

Erste Zeile genau einmal, in einer Form: `✅ Erledigt: <was>. …` (abgeschlossen), `⏳ Läuft noch: <worauf gewartet wird>. …` (vorher `workflow.py waiting "…"`, danach `--clear`) oder `❗ Du: …` (PO ist dran, auch wenn du nur auf ihn wartest; dringend `‼️`). Genaue Zeile: `workflow.py endstate`.

Schritt/Phase = Stand AM ENDE dieser Nachricht: Hook-Hinweis („Nächster Pflicht-Schritt“), nach eigenem Phasenwechsel `workflow.py status`; ohne Hinweis keine Statuszeile. Vor `phase8_complete` ist der Schritt Pflicht (nie bei Bedarf/optional), Workflow nie fertig/abgeschlossen/erledigt. In frei formulierten Arbeitsstandsmeldungen steht er vor `/clear`- oder Kosten-Empfehlung (Übergabe-Blöcke oben bleiben unverändert). Platzhalter ersetzen; nach dem Übergabe-Block, ⚙-Zeile wörtlich zuletzt, auch wenn die übrigen Zeilen entfallen.
