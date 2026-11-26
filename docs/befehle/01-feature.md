# Hintergrund zu /01-feature

Tabellen und Erläuterungen zu core/commands/01-feature.md; der Befehlstext enthält Agent-Aufruf, Ablauf und STOP-Bedingungen.

## Agent-Typ

Der `feature-planner` ist ein eigener Agent-Typ (Projekt-Agent in `.claude/agents/`, lokal auch als Plugin-Agent), Start **ohne `model`**, das Modell steht im Frontmatter (#577).

## Schritt 0: GitHub Issues durchsuchen

Bevor irgendeine Analyse beginnt:
```bash
# Offene Feature-Issues anzeigen
gh issue list --label "enhancement" --state open

# Keyword-Suche (aus $ARGUMENTS ableiten)
gh issue list --search "$ARGUMENTS" --state open
```

Falls passendes Issue gefunden → Issue-Nummer notieren und weiter mit Analyse.
Falls kein Issue → `feature-planner` erstellt am Ende eines neues Issue.

## Modus erkennen

| Formulierung | Modus |
|--------------|-------|
| "Neues Feature...", "Fuege hinzu...", "Implementiere..." | **NEU** |
| "Aenderung an...", "Passe an...", "Erweitere...", "Modifiziere..." | **AENDERUNG** |

## Injizierte Standards

- `global/analysis-first.md`
- `global/scoping-limits.md`
- `global/documentation-rules.md`

## Workflow (Langfassung)

1. **Modus bestimmen:** NEU oder AENDERUNG?
2. Feature-Intent verstehen (WAS, WARUM, Kategorie). Den Zweck in zwei bis drei Sätzen formulieren (welches Nutzerproblem, welche riskanteste Annahme) und **vom PO bestätigen lassen, bevor ein Issue angelegt wird** (#187)
3. **Bei AENDERUNG:** Aktuellen Zustand dokumentieren, Delta identifizieren
4. Bestehende Systeme pruefen (KRITISCH!)
5. Scoping (Max 4-5 Dateien, +/-250 LoC)
6. Dokumentiere in Roadmap
7. **NEU:** Erstelle OpenSpec Proposal in `openspec/changes/[feature-name]/`
8. **AENDERUNG:** Aktualisiere bestehende Spec in `openspec/specs/`
