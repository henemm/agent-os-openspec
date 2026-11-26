# User Story Discovery (JTBD-basiert)

Du führst einen **strukturierten Dialog** mit dem Product Owner, um eine User Story nach Jobs to be Done (JTBD) zu ermitteln und zu dokumentieren.

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/83-user-story.md` im Plugin-Ordner — nur bei Bedarf lesen; dort Fragen und Output-Template.

## Argument prüfen (ZUERST)

Normalerweise ist das Argument ein **Thema** (`/83-user-story Kalender-Integration`) — dann weiter mit Schritt 1.

**Nur eine Nummer** (`/83-user-story #1761`)? Laufenden Workflow auflösen und aktivieren:

```bash
python3 .claude/hooks/workflow.py find 42   # die übergebene Nummer
python3 .claude/hooks/workflow.py switch <NAME-aus-obigem-Output>
python3 .claude/hooks/workflow.py status
```

**Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht**, und frage, für welches Feature die Story gesucht ist. Findet der Block nichts, behandle das Argument als Thema.

## Dein Vorgehen

1. **Kontext klären:** Gesamtes Produkt, neues Epic/Feature oder bestehendes Feature verbessern?
2. **JTBD-Interview:** Fragen **nacheinander** (nicht alle auf einmal; `AskUserQuestion` oder frei im Chat): Situation (When…), Job (I want to…), Ergebnis (So that…), Dimensionen (funktional, emotional, sozial), Timeline (optional), Alternativen.
3. **Zusammenfassung validieren:** Story zusammenfassen und bestätigen lassen, bevor du speicherst.
4. **Dokumentieren:** speichern unter `docs/stories/[name].md` nach dem Output-Template.

Frag nach, bis du es wirklich verstehst; nutze die Sprache des Users; das "Warum" ist wichtiger als das "Was".
