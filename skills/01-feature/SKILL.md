---
description: "Plan a new feature or change"
disable-model-invocation: false
---

# Feature planen oder aendern

Starte nach Schritt 0 den `feature-planner` Agenten — eigener Agent-Typ, Start **ohne `model`** (#577):

```
Agent(subagent_type="feature-planner", description="Feature planen", prompt="
  Anfrage: $ARGUMENTS
  Gefundenes Issue: [#N oder keins, aus Schritt 0]
  Modus: [NEU oder AENDERUNG]")
```

**Fallback, wenn der Typ in der Agent-Liste fehlt:** feature-planner → `agent-os-openspec:feature-planner`, sonst `Agent(subagent_type="general-purpose", model="sonnet", prompt="Lies zuerst .claude/agents/feature-planner.md (im Framework-Repo core/agents/feature-planner.md) und folge ihr. …")`.

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/01-feature.md` im Plugin-Ordner — nur bei Bedarf lesen.

**Anfrage:** $ARGUMENTS

## Schritt 0: GitHub Issues durchsuchen (IMMER ZUERST)

```bash
gh issue list --label "enhancement" --state open
gh issue list --search "$ARGUMENTS" --state open
```

Kein passendes Issue → `feature-planner` legt am Ende eines an.

## Workflow

1. **Modus:** NEU oder AENDERUNG (dann Ist-Zustand und Delta dokumentieren)?
2. Zweck in zwei bis drei Sätzen (Nutzerproblem, riskanteste Annahme) **vom PO bestätigen lassen, bevor ein Issue angelegt wird** (#187)
3. Bestehende Systeme pruefen (KRITISCH!), Scoping (max. 4-5 Dateien, +/-250 LoC), Roadmap
4. **NEU:** Proposal in `openspec/changes/[feature-name]/`; **AENDERUNG:** Spec in `openspec/specs/` aktualisieren

## STOP-Bedingungen

Stoppe und frage nach, wenn der Feature-Intent unklar ist, der Zweck vom PO noch nicht bestätigt ist (dann kein Issue anlegen), das Scoping ueberschritten ist (>5 Dateien, >250 LoC) oder ein bestehendes System gefunden wurde (erweitern oder neu?).

**KEINE direkte Implementierung ohne Spec-Freigabe!**

## Versions-Marker (Pflicht)

Letzte Nachricht endet so (Gründe: `docs/befehle/fusszeile.md`):

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /01-feature · agent-os-openspec 4.28.0

Erste Zeile genau einmal, in einer Form: `✅ Erledigt: <was>. …` (abgeschlossen), `⏳ Läuft noch: <worauf gewartet wird>. …` (vorher `workflow.py waiting "…"`, danach `--clear`) oder `❗ Du: …` (PO ist dran, auch wenn du nur auf ihn wartest; dringend `‼️`). Genaue Zeile: `workflow.py endstate`.

Schritt/Phase = Stand AM ENDE dieser Nachricht: Hook-Hinweis („Nächster Pflicht-Schritt“), nach eigenem Phasenwechsel `workflow.py status`; ohne Hinweis keine Statuszeile. Vor `phase8_complete` ist der Schritt Pflicht (nie bei Bedarf/optional), Workflow nie fertig/abgeschlossen/erledigt. In frei formulierten Arbeitsstandsmeldungen steht er vor `/clear`- oder Kosten-Empfehlung (Übergabe-Blöcke oben bleiben unverändert). Platzhalter ersetzen; nach dem Übergabe-Block, ⚙-Zeile wörtlich zuletzt, auch wenn die übrigen Zeilen entfallen.
