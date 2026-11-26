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
