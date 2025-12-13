# Feature planen oder aendern

Starte den `feature-planner` Agenten aus `.agent-os/agents/feature-planner.md`.

**Anfrage:** $ARGUMENTS

---

## Modus erkennen

| Formulierung | Modus |
|--------------|-------|
| "Neues Feature...", "Fuege hinzu...", "Implementiere..." | **NEU** |
| "Aenderung an...", "Passe an...", "Erweitere...", "Modifiziere..." | **AENDERUNG** |

---

**Befolge den Workflow aus `.agent-os/workflows/feature-workflow.md`**

**Injizierte Standards:**
- `.agent-os/standards/global/analysis-first.md`
- `.agent-os/standards/global/scoping-limits.md`
- `.agent-os/standards/global/documentation-rules.md`
- `.agent-os/standards/swiftui/state-management.md`

---

## ⛔ ZWINGENDE CHECKPOINTS

Der Feature-Workflow hat **BLOCKING Checkpoints**. Diese MUESSEN erfuellt sein:

| Checkpoint | Wann | Blockiert |
|------------|------|-----------|
| ⛔ Tests definieren | VOR Implementierung | Ja |
| ⛔ Unit Tests | NACH Implementierung | Ja |
| ⛔ UI Tests | VOR User-Test | Ja |

---

## Anweisung

1. **Modus bestimmen:** NEU oder AENDERUNG?
2. Feature-Intent verstehen (WAS, WARUM, Kategorie)
3. **Bei AENDERUNG:** Aktuellen Zustand dokumentieren, Delta identifizieren
4. Bestehende Systeme pruefen (KRITISCH!)
5. Scoping (Max 4-5 Dateien, +/-250 LoC)
6. ⛔ **ERST Tests definieren** in `openspec/changes/[feature-name]/tests.md`
7. Dokumentiere in DOCS/ACTIVE-roadmap.md
8. **NEU:** Erstelle OpenSpec Proposal in `openspec/changes/[feature-name]/`
9. **AENDERUNG:** Aktualisiere bestehende Spec in `openspec/specs/`
10. Implementieren
11. ⛔ **Unit Tests ausfuehren** - Bei Fail: STOP
12. ⛔ **UI Tests** - Bei Fail: STOP
13. Erst dann: User fuer manuellen Test fragen

**KEINE direkte Implementierung ohne Tests.md!**
