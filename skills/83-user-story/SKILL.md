---
description: "User Story Discovery (JTBD)"
disable-model-invocation: false
---

# User Story Discovery (JTBD-basiert)

Du führst einen **strukturierten Dialog** mit dem Product Owner, um eine User Story nach Jobs to be Done (JTBD) zu ermitteln und zu dokumentieren.

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/83-user-story.md` im Plugin-Ordner — nur bei Bedarf lesen; dort Fragen und Output-Template.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
_S="${_H%/core/hooks}/scripts"; [ "$_H" = ".claude/hooks" ] && _S=".claude/scripts"
```

## Argument prüfen (ZUERST)

Normalerweise ist das Argument ein **Thema** (`/83-user-story Kalender-Integration`) — dann weiter mit Schritt 1.

**Nur eine Nummer** (`/83-user-story #1761`)? Laufenden Workflow auflösen und aktivieren:

```bash
$WF find 42   # die übergebene Nummer
$WF switch <NAME-aus-obigem-Output>
$WF status
```

**Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht**, und frage, für welches Feature die Story gesucht ist. Findet der Block nichts, behandle das Argument als Thema.

## Dein Vorgehen

1. **Kontext klären:** Gesamtes Produkt, neues Epic/Feature oder bestehendes Feature verbessern?
2. **JTBD-Interview:** Fragen **nacheinander** (nicht alle auf einmal; `AskUserQuestion` oder frei im Chat): Situation (When…), Job (I want to…), Ergebnis (So that…), Dimensionen (funktional, emotional, sozial), Timeline (optional), Alternativen.
3. **Zusammenfassung validieren:** Story zusammenfassen und bestätigen lassen, bevor du speicherst.
4. **Dokumentieren:** speichern unter `docs/stories/[name].md` nach dem Output-Template.

Frag nach, bis du es wirklich verstehst; nutze die Sprache des Users; das "Warum" ist wichtiger als das "Was".

## Versions-Marker (Pflicht)

Letzte Nachricht endet so (Gründe: `docs/befehle/fusszeile.md`):

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /83-user-story · agent-os-openspec 4.26.5

Erste Zeile genau einmal, in einer Form: `✅ Erledigt: <was>. …` (abgeschlossen), `⏳ Läuft noch: <worauf gewartet wird>. …` (vorher `workflow.py waiting "…"`, danach `--clear`) oder `❗ Du: …` (PO ist dran, auch wenn du nur auf ihn wartest; dringend `‼️`). Genaue Zeile: `workflow.py endstate`.

Schritt/Phase = Stand AM ENDE dieser Nachricht: Hook-Hinweis („Nächster Pflicht-Schritt“), nach eigenem Phasenwechsel `workflow.py status`; ohne Hinweis keine Statuszeile. Vor `phase8_complete` ist der Schritt Pflicht (nie bei Bedarf/optional), Workflow nie fertig/abgeschlossen/erledigt. In frei formulierten Arbeitsstandsmeldungen steht er vor `/clear`- oder Kosten-Empfehlung (Übergabe-Blöcke oben bleiben unverändert). Platzhalter ersetzen; nach dem Übergabe-Block, ⚙-Zeile wörtlich zuletzt, auch wenn die übrigen Zeilen entfallen.
