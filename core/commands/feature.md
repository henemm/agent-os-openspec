# Feature planen oder aendern

Starte den `feature-planner` Agenten aus `core/agents/feature-planner.md`.

**Anfrage:** $ARGUMENTS

---

## Modus erkennen

| Formulierung | Modus |
|--------------|-------|
| "Neues Feature...", "Fuege hinzu...", "Implementiere..." | **NEU** |
| "Aenderung an...", "Passe an...", "Erweitere...", "Modifiziere..." | **AENDERUNG** |

---

## Injizierte Standards

- `global/analysis-first.md`
- `global/scoping-limits.md`
- `global/documentation-rules.md`

---

## Workflow

1. **Modus bestimmen:** NEU oder AENDERUNG?
2. Feature-Intent verstehen (WAS, WARUM, Kategorie)
3. **Bei AENDERUNG:** Aktuellen Zustand dokumentieren, Delta identifizieren
4. Bestehende Systeme pruefen (KRITISCH!)
5. Scoping (Max 4-5 Dateien, +/-250 LoC)
6. Dokumentiere in Roadmap
7. **NEU:** Erstelle OpenSpec Proposal in `openspec/changes/[feature-name]/`
8. **AENDERUNG:** Aktualisiere bestehende Spec in `openspec/specs/`

---

## STOP-Bedingungen

Stoppe und frage nach wenn:
- Feature-Intent unklar
- Scoping ueberschritten (>5 Dateien, >250 LoC)
- Bestehendes System gefunden (erweitern oder neu?)

**KEINE direkte Implementierung ohne Spec-Freigabe!**
