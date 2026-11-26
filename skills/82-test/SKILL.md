---
description: "Run tests"
disable-model-invocation: false
---

# Tests ausfuehren

Starte den `test-runner` Agenten — eigener Agent-Typ, Start **ohne `model`** (#577):

```
Agent(subagent_type="test-runner", description="Tests ausfuehren", prompt="
  Fuehre die Tests des Projekts aus und fasse das Ergebnis zusammen
  (passed/failed/uebersprungen, bei Failures Fehlermeldungen und betroffene Dateien).
  Kontext (falls Wiedereinstieg): affected_files und test_files aus dem Workflow-State.")
```

**Fallback, wenn der Typ in der Agent-Liste fehlt:** test-runner → `agent-os-openspec:test-runner`, sonst `Agent(subagent_type="general-purpose", model="haiku", prompt="Lies zuerst .claude/agents/test-runner.md (im Framework-Repo core/agents/test-runner.md) und folge ihr. …")`.

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

**Aufruf als `/82-test #<N>`?** Zuerst Workflow auflösen und aktivieren:

```bash
$WF find 42   # die übergebene Nummer
$WF switch <NAME-aus-obigem-Output>
$WF status
```

**Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht**; `affected_files` und `test_files` gehören in den Auftrag. Ohne Argument laufen die Tests des aktuellen Projekts.

## Output Format

Ein Lauf mit 0 bestanden und ≥ 1 übersprungen ist nicht grün.

Erfolg: `Tests: X passed, Y failed, Z übersprungen` + `Status: Alles gruen`.
Failures:
```
Tests: X passed, Y failed, Z übersprungen
Fehlgeschlagen:
- TestClass.testMethod: [Fehlermeldung]
Betroffene Dateien:
- [Pfad]
```

Vor Commit muessen ALLE Tests gruen sein.

## Versions-Marker (Pflicht)

Letzte Nachricht endet so (Gründe: `docs/befehle/fusszeile.md`):

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /82-test · agent-os-openspec 4.26.6

Erste Zeile genau einmal, in einer Form: `✅ Erledigt: <was>. …` (abgeschlossen), `⏳ Läuft noch: <worauf gewartet wird>. …` (vorher `workflow.py waiting "…"`, danach `--clear`) oder `❗ Du: …` (PO ist dran, auch wenn du nur auf ihn wartest; dringend `‼️`). Genaue Zeile: `workflow.py endstate`.

Schritt/Phase = Stand AM ENDE dieser Nachricht: Hook-Hinweis („Nächster Pflicht-Schritt“), nach eigenem Phasenwechsel `workflow.py status`; ohne Hinweis keine Statuszeile. Vor `phase8_complete` ist der Schritt Pflicht (nie bei Bedarf/optional), Workflow nie fertig/abgeschlossen/erledigt. In frei formulierten Arbeitsstandsmeldungen steht er vor `/clear`- oder Kosten-Empfehlung (Übergabe-Blöcke oben bleiben unverändert). Platzhalter ersetzen; nach dem Übergabe-Block, ⚙-Zeile wörtlich zuletzt, auch wenn die übrigen Zeilen entfallen.
