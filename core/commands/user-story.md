# User Story Discovery (JTBD-basiert)

Du führst einen **strukturierten Dialog** mit dem Product Owner, um eine User Story zu ermitteln und zu dokumentieren.

## Framework: Jobs to be Done (JTBD)

Kernidee: Menschen "kaufen" Produkte nicht - sie "heuern" sie an, um einen Job zu erledigen.

## Dein Vorgehen

### Phase 1: Kontext klären

Frage zuerst, worum es geht:

```
Für welches Produkt/Feature soll ich die User Story ermitteln?
- Gesamtes Produkt
- Neues Epic/Feature (z.B. "Kalender-Integration")
- Bestehendes Feature verbessern
```

### Phase 2: JTBD Interview (Dialog)

Stelle diese Fragen **nacheinander** (nicht alle auf einmal). Nutze `AskUserQuestion` für strukturierte Fragen, oder frage frei im Chat.

**1. Die Situation (When...)**
> "In welcher Situation befindet sich der Nutzer, wenn das Problem auftritt?"
> "Was macht er gerade? Wo ist er? Was ist der Kontext?"

**2. Der Job (I want to...)**
> "Was will der Nutzer in diesem Moment erreichen?"
> "Was ist die konkrete Aufgabe, die er erledigen will?"

**3. Das gewünschte Ergebnis (So that...)**
> "Was erhofft sich der Nutzer davon?"
> "Wie sieht Erfolg aus? Was ist anders, wenn der Job erledigt ist?"

**4. Die Dimensionen**
- **Funktional:** Was muss technisch passieren?
- **Emotional:** Wie will sich der Nutzer fühlen? (sicher, entspannt, in Kontrolle?)
- **Sozial:** Wie will der Nutzer von anderen wahrgenommen werden?

**5. Die Timeline (optional, bei komplexeren Stories)**
> "Was war der erste Gedanke - wann wurde dir klar, dass du so etwas brauchst?"
> "Welche anderen Lösungen hast du vorher probiert?"
> "Was hat dich motiviert, aktiv nach einer Lösung zu suchen?"

**6. Die Alternativen**
> "Was macht der Nutzer heute, um dieses Problem zu lösen?"
> "Was sind die Nachteile der aktuellen Lösung?"

### Phase 3: Zusammenfassung validieren

Fasse die Story zusammen und lass sie bestätigen:

```markdown
## User Story: [Name]

**Situation:** [When...]
**Job:** [I want to...]
**Ergebnis:** [So that...]

### Das Problem heute
[Was der Nutzer aktuell macht und warum das nicht gut funktioniert]

### Die gewünschte Lösung
[Was das Produkt/Feature anders macht]

### Erfolgskriterien
- [ ] Kriterium 1
- [ ] Kriterium 2
```

### Phase 4: Dokumentieren

Speichere das Ergebnis im Projekt:

```
docs/stories/[name].md
```

Verwende das Template unten.

## Output Template

```markdown
# User Story: [Name]

> Erstellt: [Datum]
> Status: Draft | Approved
> Produkt: [Produktname]

## JTBD Statement

**When** [Situation/Kontext],
**I want to** [Job/Aufgabe],
**So that** [gewünschtes Ergebnis].

## Kontext

### Die Situation
[Detaillierte Beschreibung der Situation, in der das Problem auftritt]

### Das Problem heute
[Wie löst der Nutzer das Problem aktuell? Was sind die Nachteile?]

### Alternativen
- Alternative 1: [Was der Nutzer sonst tun könnte]
- Alternative 2: ...

## Dimensionen

### Funktional
[Was muss technisch passieren?]

### Emotional
[Wie will sich der Nutzer fühlen?]

### Sozial
[Wie will der Nutzer wahrgenommen werden?]

## Erfolgskriterien

- [ ] Kriterium 1
- [ ] Kriterium 2
- [ ] Kriterium 3

## Abgeleitete Features

| Feature | Priorität | Status |
|---------|-----------|--------|
| Feature 1 | Must | Backlog |
| Feature 2 | Should | Backlog |

---
*Ermittelt im JTBD-Dialog am [Datum]*
```

## Wichtig

- **Frag nach, bis du es wirklich verstehst** - keine Annahmen
- **Nutze die Sprache des Users** - keine technischen Begriffe erzwingen
- **Emotional > Funktional** - Das "Warum" ist wichtiger als das "Was"
- **Validiere am Ende** - Lass die Zusammenfassung bestätigen bevor du speicherst
