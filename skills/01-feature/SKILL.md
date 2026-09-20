---
description: "Plan a new feature or change"
disable-model-invocation: false
---

# Feature planen oder aendern

Starte den `feature-planner` Agenten aus `core/agents/feature-planner.md`.

**Anfrage:** $ARGUMENTS

---

## Schritt 0: GitHub Issues durchsuchen (IMMER ZUERST)

Bevor irgendeine Analyse beginnt:
```bash
# Offene Feature-Issues anzeigen
gh issue list --label "enhancement" --state open

# Keyword-Suche (aus $ARGUMENTS ableiten)
gh issue list --search "$ARGUMENTS" --state open
```

Falls passendes Issue gefunden → Issue-Nummer notieren und weiter mit Analyse.
Falls kein Issue → `feature-planner` erstellt am Ende eines neues Issue.

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

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen zwei Zeilen, in dieser Reihenfolge:

Workflow `<name>` · Phase `<x>` von 8 · Nächster Pflicht-Schritt: `/<befehl> #<N>`
⚙ /01-feature · agent-os-openspec 3.26.1

Die Statuszeile übernimmst du aus dem Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert — Phase und Schritt wörtlich von dort. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfällt die Statuszeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In der Statuszeile ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Beide Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die Statuszeile entfällt.
