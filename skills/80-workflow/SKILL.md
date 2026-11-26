---
description: "Manage workflows"
disable-model-invocation: true
---

# Workflow Management

Manage multiple parallel workflows with isolated state (v3).

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/80-workflow.md` im Plugin-Ordner — nur bei Bedarf lesen.

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

**Wurde dieser Befehl als `/80-workflow #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf. Alle anderen Argumente (`list`, `status`, `switch <name>` …) laufen wie unten beschrieben:

```bash
$WF find 42   # die übergebene Nummer
```

**PFLICHT direkt danach** — Workflow wirklich aktivieren (ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT):

```bash
$WF switch <NAME-aus-obigem-Output>
$WF status
```

**Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht**, inklusive des nächsten Pflicht-Schritts.

**Ohne Argument** gilt der Rest dieser Datei unverändert.

## Commands

```bash
$WF list                 # alle Workflows
$WF sessions [--json]    # aktive Sitzungen (Session-Register)
$WF status               # aktueller Stand
$WF start "feature-name"
$WF switch "other-feature"
$WF phase phase4_approved
$WF set-field spec_file "docs/specs/auth/login.md"
$WF set-field context_file "docs/context/login.md"
$WF set-field github_issue 42
$WF set-affected-files src/auth.py src/login.py
$WF add-artifact test_output \
    "docs/artifacts/feature/test-red.txt" "Test FAILED: assertion error" phase5_tdd_red
$WF mark-red "3 tests failed"
$WF mark-ui-red "UI test assertion"
$WF write-log success|partial|reverted   # Pflicht vor finish
$WF override-ambiguous "reason for proceeding"
$WF set-field loc_limit_override 500          # Produktivcode
$WF set-field test_loc_limit_override 800     # Testcode
$WF finish
$WF abandon --reason "Analyse-Vorlauf, Umsetzung in FEAT_002 abgeschlossen"
$WF retro-list | retro [<name>]   # Slash-Command: /90-retro
python3 ${_H}/qa_gate.py --run [--checklist <dialog.md>]   # Testlauf aus qa_gate.test_command, setzt Adversary-Verdict (Details: docs/befehle/80-workflow.md, "QA Gate")
```

Mit Issue-Nummer im Namen registriert `start` die Sitzung als Kommentar am Issue (#461). Ist
dort schon eine andere Sitzung registriert, bricht `start` ohne Workflow ab und nennt Sitzung,
Ort, Beginn und Erreichbarkeit. Übersicht: `workflow.py claim status`; Nachholen nach Offline-Start:
`workflow.py claim nachholen`; bewusste Übernahme: `workflow.py start "feature-name" --uebernehmen`.

`abandon` nur für Workflows OHNE Prüfgegenstand (nie in phase6_implement); NICHT den
workflow_type umklassifizieren, um das Gate loszuwerden. Die Begründung ist Pflicht.

### Endzustand der Fußzeile (#550)
```bash
$WF endstate [#N|name]
$WF waiting "<text>"
$WF waiting --clear
```
`endstate` gibt die Schlusszeile aus: `✅ Erledigt`, `⏳ Läuft noch` oder `❗ Du`.

### Auftragsliste (#551)
```bash
$WF queue add <N...> [--autark] [--note "<Wortlaut>"]
$WF queue            # bzw. queue list
$WF queue done <N>
$WF queue clear
$WF queue claim      # verwaisten Auftrag übernehmen (#613)
```
Ausgabe `QUEUE=`, `AUTARK=`, `NEXT=` und bei offenem Auftrag `PROMPT=/00-intake #<NEXT>`.

### Übergabe an eine frische Sitzung (#667)
```bash
$WF handoff                 # Weg + Startauftrag
$WF handoff --start         # Herdr: neue Sitzung im neuen Pane
$WF handoff --mark cloud    # Start vermerken (nach create_session)
```
Ausgabe `HANDOFF=cloud|herdr|inline|none`, `NEXT=`, Startauftrag zwischen `PROMPT_BEGIN`/`PROMPT_END`.
`--start` meldet `STARTED=yes|no|already`. Ist für `NEXT` schon ein Start vermerkt, folgt
`HANDOFF_DONE=<weg>` (#668: keine zweite Sitzung starten). `--mark` meldet `MARKED=yes|no`;
scheitert der Vermerk, folgt `WARN=Vermerk fehlgeschlagen (<Typ>)`.

## Versions-Marker (Pflicht)

Letzte Nachricht endet so (Gründe: `docs/befehle/fusszeile.md`):

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /80-workflow · agent-os-openspec 4.26.6

Erste Zeile genau einmal, in einer Form: `✅ Erledigt: <was>. …` (abgeschlossen), `⏳ Läuft noch: <worauf gewartet wird>. …` (vorher `workflow.py waiting "…"`, danach `--clear`) oder `❗ Du: …` (PO ist dran, auch wenn du nur auf ihn wartest; dringend `‼️`). Genaue Zeile: `workflow.py endstate`.

Schritt/Phase = Stand AM ENDE dieser Nachricht: Hook-Hinweis („Nächster Pflicht-Schritt“), nach eigenem Phasenwechsel `workflow.py status`; ohne Hinweis keine Statuszeile. Vor `phase8_complete` ist der Schritt Pflicht (nie bei Bedarf/optional), Workflow nie fertig/abgeschlossen/erledigt. In frei formulierten Arbeitsstandsmeldungen steht er vor `/clear`- oder Kosten-Empfehlung (Übergabe-Blöcke oben bleiben unverändert). Platzhalter ersetzen; nach dem Übergabe-Block, ⚙-Zeile wörtlich zuletzt, auch wenn die übrigen Zeilen entfallen.
