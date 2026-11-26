---
description: "Write failing tests (RED phase)"
disable-model-invocation: false
---

# Phase 5: TDD RED - Write Failing Tests

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/40-tdd-red.md` im Plugin-Ordner — nur bei Bedarf lesen.

Tests vor der Implementierung; sie MÜSSEN scheitern.

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

**Aufruf mit Issue-Nummer** (z. B. `/40-tdd-red #42`, typisch nach `/clear`)? Workflow explizit aktivieren (`export` reicht NICHT):

```bash
$WF find 42   # die übergebene Nummer
$WF switch <NAME-aus-obigem-Output>
$WF status
```

Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht. **Ohne Issue-Argument:** `workflow.py status` reicht.

## Your Tasks

### 1. Enter TDD RED Phase

```bash
$WF phase phase5_tdd_red
```

### 2. Write Tests Based on Spec

Je Anforderung aus dem Test Plan ein Test (GIVEN/WHEN/THEN), der am fehlenden Feature scheitert.

### 3. Run Tests - MUST BE RED, Capture REAL Artifacts

```bash
mkdir -p docs/artifacts/[workflow-name]
pytest tests/ -v > docs/artifacts/[workflow]/test-red-output.txt 2>&1
```

**Expected:** FAIL mit klarer Fehlermeldung; UI/API: echte Screenshots/Antworten.

### 4. Register Artifacts

```bash
$WF add-artifact test_output \
    "docs/artifacts/[workflow]/test-red-output.txt" \
    "Test FAILED: [function] raises NotImplementedError - assertion error line 42" \
    phase5_tdd_red
```

### 5. Mark RED

Gleich nach dem Registrieren (Fußzeile nennt dann schon `/50-implement`):

```bash
$WF mark-red "<kurzes Ergebnis, z. B. 3 tests failed>"
```

**Checkliste:** Tests für alle Anforderungen, alle ausgeführt und RED, mind. 1 echtes, nicht leeres Artefakt mit
Beschreibung und Fehlerbeleg registriert, `mark-red` ausgeführt.

## Next Step

Sind alle Artefakte registriert und Spec + RED-Testdateien committed:

```bash
$WF phase phase6_implement
```

### Checkpoint prüfen (Anweisung an dich — nicht ausgeben)

Prüfe der Reihe nach, bevor du unten etwas ausgibst:

- Phase im Workflow-State geschrieben — `$WF status` bestätigt sie
- Alle Ergebnisdateien dieser Phase liegen auf der Platte
- Alle RED-Artefakte per `add-artifact` registriert
- RED per `workflow.py mark-red "<Ergebnis>"` gemeldet
- Keine ungesicherten Änderungen an Dateien, die `/50-implement` braucht
- Keine Erkenntnis, die für `/50-implement` nötig und nirgends niedergeschrieben ist

Sind alle Punkte erfüllt: Gib den Positiv-Block aus. Ist mindestens einer verletzt: Gib stattdessen den Negativ-Block aus und ersetze dessen Platzhalter durch den konkreten Sicherungsschritt.

Weder diese Anweisung noch die `###`-Überschriften gehören in die Ausgabe — an den User geht ausschließlich der Text zwischen den `---`-Trennern, und zwar genau einmal, als letzter inhaltlicher Teil der Nachricht: keine Vorab- oder Kurzfassung davor, keine Wiederholung danach.

### Ausgabe: Zusammenfassung (immer)

---
✅ Phase 5 (TDD RED) abgeschlossen.

Workflow: `<name>` · Issue: **#<N>** · Phase 5 (`phase5_tdd_red`) ✓ · jetzt: `phase6_implement`

**Was wurde gemacht:** Die Qualitätsprüfungen (Tests) sind aufgesetzt und bestätigt als fehlschlagend — genau wie geplant, denn die eigentliche Funktion ist noch nicht gebaut. Das ist ein gutes Zeichen: Wir messen zuerst, dann bauen wir.

---

### Ausgabe A: Positiv-Block (alle Vorbedingungen erfüllt)

---
**Gesichert auf der Platte:**
- `.claude/workflows/<name>.json` — Phase `phase6_implement`, Feld `spec_file`, Verdict, Artefakt-Register
- `tests/<test-datei>.py` — die geschriebenen, fehlschlagenden Testdateien (gesichert)
- `docs/artifacts/<workflow-name>/test-red-output.txt` — RED-Beleg, per `add-artifact` registriert

✅ **`/clear` ist jetzt gefahrlos** — alles oben Gelistete stellt der Folge-Befehl allein aus diesen Dateien wieder her. Im Gesprächsverlauf steht nichts, was verloren ginge.

1. `/clear`
2. `/50-implement #<N>`

---

### Ausgabe B: Negativ-Block (mindestens eine Vorbedingung verletzt)

---
⚠️ **`/clear` jetzt NICHT** — Folgendes steht nur im Gesprächsverlauf:
- <was fehlt> → sichern mit: <konkreter Befehl oder Schritt>

Erst sichern, dann ist `/clear` gefahrlos.

---

Vor dem Selbstaufruf zusätzlich `$WF context` ausführen (Kontext-Haushalt): Bei `CONTEXT_STOP=on` (Kontext über der wirksamen Schwelle `CONTEXT_THRESHOLD` aus `context_budget`: Grundkontext der Sitzung + `growth_tokens`, mindestens `clear_threshold_tokens`, Default 100.000 Token, nur im Modus manual) den Skill `50-implement` NICHT selbst aufrufen, sondern die Antwort mit dem Checkpoint und der ❗Du-Zeile `/50-implement #<N>` beenden — der Stand liegt auf der Platte, der PO tippt `/clear`. Bei `CONTEXT_STOP=off` oder `CONTEXT_TOKENS=unknown`: Kette unverändert selbst fortsetzen (#658).

Ohne `/clear`: Rufe den Skill `50-implement` jetzt sofort selbst auf, ohne auf den User zu warten (gilt in jedem Autonomie-Modus, #472).
Mit `/clear`: Wiedereinstieg über `/50-implement #<N>`.
Immer menschlich bleiben — auch bei `AUTONOMY=auto`: AMBIGUOUS-Verdict, zweites BROKEN bzw. Circuit Breaker, Override, Deploy, Stop-Lock.

## Common Mistakes

❌ Grüne Tests (wertlos) · alles gemockt · Platzhalter-Artefakte oder Sprung zur Implementierung (Hook blockt)

## Versions-Marker (Pflicht)

Letzte Nachricht endet so (Gründe: `docs/befehle/fusszeile.md`):

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /40-tdd-red · agent-os-openspec 4.26.5

Erste Zeile genau einmal, in einer Form: `✅ Erledigt: <was>. …` (abgeschlossen), `⏳ Läuft noch: <worauf gewartet wird>. …` (vorher `workflow.py waiting "…"`, danach `--clear`) oder `❗ Du: …` (PO ist dran, auch wenn du nur auf ihn wartest; dringend `‼️`). Genaue Zeile: `workflow.py endstate`.

Schritt/Phase = Stand AM ENDE dieser Nachricht: Hook-Hinweis („Nächster Pflicht-Schritt“), nach eigenem Phasenwechsel `workflow.py status`; ohne Hinweis keine Statuszeile. Vor `phase8_complete` ist der Schritt Pflicht (nie bei Bedarf/optional), Workflow nie fertig/abgeschlossen/erledigt. In frei formulierten Arbeitsstandsmeldungen steht er vor `/clear`- oder Kosten-Empfehlung (Übergabe-Blöcke oben bleiben unverändert). Platzhalter ersetzen; nach dem Übergabe-Block, ⚙-Zeile wörtlich zuletzt, auch wenn die übrigen Zeilen entfallen.
