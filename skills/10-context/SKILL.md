---
description: "Gather context for a new feature or bug fix"
disable-model-invocation: false
---

# Phase 1: Context Generation

You are starting **Phase 1 - Context Generation** for a new workflow.

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/10-context.md` im Plugin-Ordner — nur bei Bedarf lesen.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
_S="${_H%/core/hooks}/scripts"; [ "$_H" = ".claude/hooks" ] && _S=".claude/scripts"
```

## Wiedereinstieg (`/10-context #<N>`, nach `/clear`)

Workflow explizit aktivieren (`export` reicht NICHT):

```bash
$WF find 42   # die übergebene Nummer
$WF switch <NAME-aus-obigem-Output>
$WF status
```

Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht; Schritt 1 entfällt. `KEIN laufender Workflow`: fragen, ob neu starten.

## Your Tasks

### 1. Start or Resume Workflow

```bash
$WF start "[feature-name]" --issue <N>
```

`--issue <N>` nur mit bekannter Nummer. `start` registriert die Sitzung am Issue (#461); bricht er ab (andere Sitzung
registriert), dem PO sagen, wer wo seit wann arbeitet; `--uebernehmen` nur, wenn die andere ruht (`workflow.py claim status`) oder der PO zustimmt.
Bestehenden Workflow: `$WF switch "[feature-name]"`.

### 2. Gather Context

Betroffene Dateien, Specs in `docs/specs/`, ähnliche Lösungen, Dependencies, Dependents.

**Kontext-Haushalt:** Nachschlagen an einen Explore-Teilagenten (Haiku); selbst nur mit Zeilenbereich (`sed -n 120,160p`) oder gezielter Suche lesen; Workflow-Aufrufe mit `workflow.py batch a -- b -- c` bündeln.

### 3. Create Context Document

`docs/context/[workflow-name].md`: Request Summary, Related Files, Existing Patterns, Dependencies, Existing Specs, Risks (Vorlage im Hintergrund).

### 4. Update Workflow State

Erst `context_file` eintragen, dann die Phase:

```bash
$WF set-field context_file docs/context/[workflow-name].md
$WF phase phase2_analyse
```

## Next Step

### Checkpoint prüfen (Anweisung an dich — nicht ausgeben)

Prüfe der Reihe nach, bevor du unten etwas ausgibst:

- Phase im Workflow-State geschrieben — `$WF status` bestätigt sie
- Alle Ergebnisdateien dieser Phase liegen auf der Platte
- Keine Erkenntnis, die für `/20-analyse` nötig und nirgends niedergeschrieben ist

Sind alle Punkte erfüllt: Gib den Positiv-Block aus. Ist mindestens einer verletzt: Gib stattdessen den Negativ-Block aus und ersetze dessen Platzhalter durch den konkreten Sicherungsschritt.

Weder diese Anweisung noch die `###`-Überschriften gehören in die Ausgabe — an den User geht ausschließlich der Text zwischen den `---`-Trennern, und zwar genau einmal, als letzter inhaltlicher Teil der Nachricht: keine Vorab- oder Kurzfassung davor, keine Wiederholung danach.

### Ausgabe: Zusammenfassung (immer)

---
**Kontext gesammelt.**

Was ich gefunden habe: [Kurz beschreiben was relevant ist — z.B. welche bestehenden Bereiche betroffen sind, ob ähnliche Lösungen schon existieren, was zu beachten ist — keine Dateinamen oder Technik]

---

### Ausgabe A: Positiv-Block (alle Vorbedingungen erfüllt)

---
**Gesichert auf der Platte:**
- `.claude/workflows/<name>.json` — Phase `phase2_analyse`, Verdict, Artefakt-Register
- `docs/context/<workflow-name>.md` — gesammelter Kontext: relevante Dateien, bestehende Muster, Dependencies/Dependents, bekannte Risiken

✅ **`/clear` ist jetzt gefahrlos** — alles oben Gelistete stellt der Folge-Befehl allein aus diesen Dateien wieder her. Im Gesprächsverlauf steht nichts, was verloren ginge.

1. `/clear`
2. `/20-analyse #<N>`

---

### Ausgabe B: Negativ-Block (mindestens eine Vorbedingung verletzt)

---
⚠️ **`/clear` jetzt NICHT** — Folgendes steht nur im Gesprächsverlauf:
- <was fehlt> → sichern mit: <konkreter Befehl oder Schritt>

Erst sichern, dann ist `/clear` gefahrlos.

---

### Auto-Modus: Kette selbst fortsetzen (#472)

```bash
$WF autonomy
```

Bei `AUTONOMY=auto` ohne `/clear`: Rufe den Skill `20-analyse` jetzt sofort selbst auf, ohne auf den User zu warten; der Checkpoint-Block bleibt in der Ausgabe. Sonst auf den User warten.

Vor dem Selbstaufruf zusätzlich `$WF context` ausführen (Kontext-Haushalt): Bei `CONTEXT_STOP=on` (Kontext über der wirksamen Schwelle `CONTEXT_THRESHOLD` aus `context_budget`: Grundkontext der Sitzung + `growth_tokens`, mindestens `clear_threshold_tokens`, Default 100.000 Token, nur im Modus manual) den Skill `20-analyse` NICHT selbst aufrufen, sondern die Antwort mit dem Checkpoint und der ❗Du-Zeile `/20-analyse #<N>` beenden — der Stand liegt auf der Platte, der PO tippt `/clear`. Bei `CONTEXT_STOP=off` oder `CONTEXT_TOKENS=unknown`: Kette unverändert selbst fortsetzen (#658).

Immer menschlich bleiben — auch bei `AUTONOMY=auto`: AMBIGUOUS-Verdict, zweites BROKEN bzw. Circuit Breaker, Override, Deploy, Stop-Lock.

**IMPORTANT:** Do NOT skip to implementation. Context → Analyse → Spec → Implement.

## Versions-Marker (Pflicht)

Letzte Nachricht endet so (Gründe: `docs/befehle/fusszeile.md`):

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /10-context · agent-os-openspec 4.26.3

Erste Zeile genau einmal, in einer Form: `✅ Erledigt: <was>. …` (abgeschlossen), `⏳ Läuft noch: <worauf gewartet wird>. …` (vorher `workflow.py waiting "…"`, danach `--clear`) oder `❗ Du: …` (PO ist dran, auch wenn du nur auf ihn wartest; dringend `‼️`). Genaue Zeile: `workflow.py endstate`.

Schritt/Phase = Stand AM ENDE dieser Nachricht: Hook-Hinweis („Nächster Pflicht-Schritt“), nach eigenem Phasenwechsel `workflow.py status`; ohne Hinweis keine Statuszeile. Vor `phase8_complete` ist der Schritt Pflicht (nie bei Bedarf/optional), Workflow nie fertig/abgeschlossen/erledigt. In frei formulierten Arbeitsstandsmeldungen steht er vor `/clear`- oder Kosten-Empfehlung (Übergabe-Blöcke oben bleiben unverändert). Platzhalter ersetzen; nach dem Übergabe-Block, ⚙-Zeile wörtlich zuletzt, auch wenn die übrigen Zeilen entfallen.
