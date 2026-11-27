---
description: "Register a test artifact in the workflow"
disable-model-invocation: true
---
<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->

# Add Test Artifact

Register a **REAL** test artifact (screenshot, log, API response, test output) for TDD workflow validation.

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/81-add-artifact.md` im Plugin-Ordner — nur bei Bedarf lesen.

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

**Aufruf als `/81-add-artifact #<N>`?** Zuerst Workflow auflösen und aktivieren — das Artefakt landet im State des AKTIVEN Workflows:

```bash
$WF find 42   # die übergebene Nummer
$WF switch <NAME-aus-obigem-Output>
$WF status
```

**Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** — die Phase bestimmt die Artefakt-Phase. Ohne Argument gilt der aktive Workflow.

## Usage

1. **Save the artifact** to `docs/artifacts/[workflow-name]/`
2. **Register it** (Typen: `screenshot`, `email`, `api_response`, `log`, `test_output`, `ui_test_output`, `video`):
```bash
$WF add-artifact screenshot \
    "docs/artifacts/[workflow]/screenshot.png" \
    "Screenshot showing test failure: expected X but got Y" \
    phase5_tdd_red
```

Artifacts MUST be real, non-empty (Mindestgröße), less than 24 h old and described. `phase5_tdd_red`: description shows failure (fail, error, assertion, expected/actual); `phase7_validate`: success (pass, success, verified, works).

## Shorthand: Mark RED Done

```bash
$WF mark-red "3 tests failed as expected"
$WF mark-ui-red "UI test assertion error"
```

## Versions-Marker (Pflicht)

Letzte Nachricht endet so (Gründe: `docs/befehle/fusszeile.md`):

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /81-add-artifact · agent-os-openspec 4.28.1

Erste Zeile genau einmal, in einer Form: `✅ Erledigt: <was>. …` (abgeschlossen), `⏳ Läuft noch: <worauf gewartet wird>. …` (vorher `workflow.py waiting "…"`, danach `--clear`) oder `❗ Du: …` (PO ist dran, auch wenn du nur auf ihn wartest; dringend `‼️`). Genaue Zeile: `workflow.py endstate`.

Schritt/Phase = Stand AM ENDE dieser Nachricht: Hook-Hinweis („Nächster Pflicht-Schritt“), nach eigenem Phasenwechsel `workflow.py status`; ohne Hinweis keine Statuszeile. Vor `phase8_complete` ist der Schritt Pflicht (nie bei Bedarf/optional), Workflow nie fertig/abgeschlossen/erledigt. In frei formulierten Arbeitsstandsmeldungen steht er vor `/clear`- oder Kosten-Empfehlung (Übergabe-Blöcke oben bleiben unverändert). Platzhalter ersetzen; nach dem Übergabe-Block, ⚙-Zeile wörtlich zuletzt, auch wenn die übrigen Zeilen entfallen.
