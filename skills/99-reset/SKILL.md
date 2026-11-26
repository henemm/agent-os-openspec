---
description: "Reset or complete the current workflow"
disable-model-invocation: true
---

# Reset Workflow

Schließt den aktiven Workflow ab und archiviert ihn.

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/99-reset.md` im Plugin-Ordner — nur bei Bedarf lesen.

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

**Aufruf als `/99-reset #<N>`?** ZUERST Workflow auflösen und aktivieren — steht der falsche aktiv, trifft es fremde Arbeit:

```bash
$WF find 42   # die übergebene Nummer
$WF switch <NAME-aus-obigem-Output>
$WF status
```

**Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** — vor `phase8_complete` den offenen Pflicht-Schritt nennen und nachfragen, bevor du abschließt. Ohne Argument gilt der aktive Workflow.

## Execute Reset

**Erst prüfen, ob überhaupt gebaut wurde** (`$WF status`):

- Hat der Workflow das Feld `no_build_reason` (PO-Entscheidung „nichts bauen", per `workflow.py no-build --reason "..."`) **oder** wurde nie eine `spec_file` geschrieben, dann **nicht** `finish`, sondern:

  ```bash
  $WF abandon --reason "<Begründung>"
  ```

  Begründung für `workflow.py abandon --reason` = Inhalt von `no_build_reason`; fehlt das Feld, den PO nach dem Grund fragen.
- Nur bei geschriebener Spec und abgeschlossener Arbeit:

```bash
$WF finish
```

Danach neu starten mit `/10-context` bzw. `/20-analyse [feature/bug]`.

## Versions-Marker (Pflicht)

Letzte Nachricht endet so (Gründe: `docs/befehle/fusszeile.md`):

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /99-reset · agent-os-openspec 4.26.4

Erste Zeile genau einmal, in einer Form: `✅ Erledigt: <was>. …` (abgeschlossen), `⏳ Läuft noch: <worauf gewartet wird>. …` (vorher `workflow.py waiting "…"`, danach `--clear`) oder `❗ Du: …` (PO ist dran, auch wenn du nur auf ihn wartest; dringend `‼️`). Genaue Zeile: `workflow.py endstate`.

Schritt/Phase = Stand AM ENDE dieser Nachricht: Hook-Hinweis („Nächster Pflicht-Schritt“), nach eigenem Phasenwechsel `workflow.py status`; ohne Hinweis keine Statuszeile. Vor `phase8_complete` ist der Schritt Pflicht (nie bei Bedarf/optional), Workflow nie fertig/abgeschlossen/erledigt. In frei formulierten Arbeitsstandsmeldungen steht er vor `/clear`- oder Kosten-Empfehlung (Übergabe-Blöcke oben bleiben unverändert). Platzhalter ersetzen; nach dem Übergabe-Block, ⚙-Zeile wörtlich zuletzt, auch wenn die übrigen Zeilen entfallen.
