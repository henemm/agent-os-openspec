---
description: "/90-retro — Workflow-Retro"
disable-model-invocation: false
---

# /90-retro — Workflow-Retro

Analysiere einen abgeschlossenen Workflow aus dem Archiv: Zeiten pro Phase, Qualitätssignale, Optimierungshinweise. Aufruf: `/90-retro` (zuletzt abgeschlossener), `/90-retro <name>`, `/90-retro list`.

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

**Aufruf als `/90-retro #<N>`?** Der Workflow ist **archiviert** — deshalb kein `workflow.py switch` (nur für laufende Workflows), sondern Suche im Archiv, danach `retro <name>`:

```bash
ISSUE=42   # die übergebene Nummer (ohne #)
python3 - "$ISSUE" <<'PY'
import sys, json, glob, re, os
i = sys.argv[1].lstrip('#'); pat = re.compile(rf'(^|[-_]){re.escape(i)}([-_]|$)')
fs = [f for f in glob.glob('.claude/workflows/_archive/*.json') + glob.glob('.claude/workflows/*.json') if pat.search(os.path.basename(f)[:-5])]
for f in fs: print('GEFUNDEN:', os.path.basename(f)[:-5], '| Phase=' + str(json.load(open(f)).get('current_phase')), '|', 'archiviert' if '_archive' in f else 'LAEUFT NOCH')
print('\nNAME=' + os.path.basename(fs[0])[:-5] if fs else f'KEIN Workflow fuer #{i}.')
PY
```

**Fasse dem User in 2 Sätzen zusammen**, welchen Workflow du analysierst; bei `LAEUFT NOCH` zuerst das sagen und den offenen Pflicht-Schritt nennen (Retro verfrüht).

## Ablauf

1. `list` → `$WF retro-list`, fragen: "Welchen Workflow möchtest du analysieren?", dann `retro <name>`.
   Ohne Argument: `retro-list` kurz zeigen, dann ohne Nachfrage `$WF retro`.
2. `$WF retro <name>`
3. PO-Zusammenfassung in einfacher Sprache (2–4 Sätze): Gesamtdauer, Qualitätsprobleme (Fix-Loops, Override, fehlendes TDD), langsamste Phase und warum, was gut lief. Kein Fachjargon, keine Dateinamen.

## Versions-Marker (Pflicht)

Letzte Nachricht endet so (Gründe: `docs/befehle/fusszeile.md`):

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /90-retro · agent-os-openspec 4.28.1

Erste Zeile genau einmal, in einer Form: `✅ Erledigt: <was>. …` (abgeschlossen), `⏳ Läuft noch: <worauf gewartet wird>. …` (vorher `workflow.py waiting "…"`, danach `--clear`) oder `❗ Du: …` (PO ist dran, auch wenn du nur auf ihn wartest; dringend `‼️`). Genaue Zeile: `workflow.py endstate`.

Schritt/Phase = Stand AM ENDE dieser Nachricht: Hook-Hinweis („Nächster Pflicht-Schritt“), nach eigenem Phasenwechsel `workflow.py status`; ohne Hinweis keine Statuszeile. Vor `phase8_complete` ist der Schritt Pflicht (nie bei Bedarf/optional), Workflow nie fertig/abgeschlossen/erledigt. In frei formulierten Arbeitsstandsmeldungen steht er vor `/clear`- oder Kosten-Empfehlung (Übergabe-Blöcke oben bleiben unverändert). Platzhalter ersetzen; nach dem Übergabe-Block, ⚙-Zeile wörtlich zuletzt, auch wenn die übrigen Zeilen entfallen.
