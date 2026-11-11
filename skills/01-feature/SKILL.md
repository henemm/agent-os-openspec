---
description: "Plan a new feature or change"
disable-model-invocation: false
---

# Feature planen oder aendern

Starte nach Schritt 0 den `feature-planner` Agenten — eigener Agent-Typ (Projekt-Agent in `.claude/agents/`, lokal auch als Plugin-Agent), Start **ohne `model`**, das Modell steht im Frontmatter (#577):

```
Agent(subagent_type="feature-planner", description="Feature planen", prompt="
  Anfrage: $ARGUMENTS
  Gefundenes Issue: [#N oder keins, aus Schritt 0]
  Modus: [NEU oder AENDERUNG]")
```

**Fallback, wenn der Typ in der Agent-Liste fehlt:** feature-planner → `agent-os-openspec:feature-planner`, sonst `Agent(subagent_type="general-purpose", model="sonnet", prompt="Lies zuerst .claude/agents/feature-planner.md (im Framework-Repo core/agents/feature-planner.md) und folge ihr. …")`.

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
2. Feature-Intent verstehen (WAS, WARUM, Kategorie). Den Zweck in zwei bis drei Sätzen formulieren (welches Nutzerproblem, welche riskanteste Annahme) und **vom PO bestätigen lassen, bevor ein Issue angelegt wird** (#187)
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
- Zweck vom PO noch nicht bestätigt — dann kein Issue anlegen
- Scoping ueberschritten (>5 Dateien, >250 LoC)
- Bestehendes System gefunden (erweitern oder neu?)

**KEINE direkte Implementierung ohne Spec-Freigabe!**

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /01-feature · agent-os-openspec 4.11.0

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von drei Formen (es gibt keine vierte):

- `✅ Erledigt: <was>. Du kannst /clear ausführen und das nächste Issue starten.` — nur wenn der Workflow wirklich abgeschlossen ist.
- `⏳ Läuft noch: <worauf gewartet wird>. Du musst nichts tun, ich melde mich.` — du wartest auf CI, einen Hintergrund-Agenten oder einen Server.
- `❗ Du: …` (`❗ Du: <Schritt> — <warum>`), wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist immer ❗, nie ⏳.

Beendest du einen Turn, während du auf CI, Agent oder Server wartest, setze vorher `workflow.py waiting "<worauf>"` und gib die ⏳-Zeile aus; ist das Ergebnis da, `workflow.py waiting --clear`. Die passende Zeile liefert `workflow.py endstate [#<N>]` als `FOOTER=…` — gib sie wörtlich aus. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase geben den Stand AM ENDE dieser Nachricht wieder. Quelle ist der Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — aber nur, solange du die Phase in dieser Nachricht nicht selbst gewechselt hast. Hast du per `workflow.py phase <x>` (oder `complete`) gewechselt, beschreibt der Hinweis den Stand von Turn-Beginn; maßgeblich ist dann der neue Stand, den `workflow.py status` zeigt. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfällt die Statuszeile; die erste Zeile kommt dann aus `workflow.py endstate #<N>` und entfällt nur ohne Workflow. Die Marker-Zeilen entfallen NIE wegen eines Phasenwechsels; die ⚙-Zeile bleibt immer die letzte Zeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.
