# Hintergrund zu /20-analyse

Begründungen und Sonderfälle zu core/commands/20-analyse.md; der Befehlstext enthält Ablauf und Pflichtschritte.

## Step 0: Workflow-State auflösen

**Wurde dieser Befehl mit einer Issue-Nummer aufgerufen** (z. B. `/20-analyse #42` — typisch nach einem `/clear`)? Dann aktiviere den Workflow explizit. Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58).

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen) und den Stand verifizieren:

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec. Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht — damit sichtbar ist, dass der `/clear` nichts verloren hat.

**Ohne Issue-Argument** (laufende Session, kein `/clear` dazwischen): `workflow.py status` reicht direkt.

## Prerequisites

- Context gathered (`/10-context` completed, or combined with analysis)
- Active workflow exists

## Step 1: Bug vs. Feature Routing

Bestimme aus dem Kontext:
- **Bug:** User meldet ein Problem, etwas funktioniert nicht wie erwartet
- **Feature:** User wuenscht neue Funktionalitaet oder Aenderung

## Hängende Subagenten

Primärer Schutz gegen einen hängenden Subagenten: Die Sitzung wird automatisch erneut aufgerufen,
sobald der Hintergrund-Agent fertig ist. Liegt beim nächsten eigenen Zug noch kein Bericht vor,
`TaskList` prüfen — ist der Agent dort noch als aktiv gelistet, ihn mit `TaskStop` beenden und
mit präziserem Briefing neu starten. Kein endloses Warten.

Nur falls dieser Befehl innerhalb eines `/loop`-Laufs (Selbsttaktung, dynamischer Modus) läuft,
zusätzlich dieser Rückfall:

```
ScheduleWakeup(1200, "Analyse-Agenten Rückfall [20-analyse], nur im /loop-Kontext: TaskList → noch aktiver Explore-/Bug-Intake-/Plan-Agent? JA → TaskStop, dann User: 'Analyse-Agent hängt — bitte /20-analyse neu starten.' NEIN → ignorieren, fertig.")
```

## Step 2a: Feature-Analyse (3x Explore/Haiku parallel)

Bei Features dispatche **3 parallele Subagenten** fuer schnelle Kontextsammlung:

```
Agent(subagent_type="Explore", model="haiku", description="Betroffene Dateien", run_in_background=true, prompt="
  Finde alle Dateien die von [Feature-Bereich] betroffen
  sind. Liste: Dateipfad, Typ (MODIFY/CREATE/DELETE), Begruendung.")

Agent(subagent_type="Explore", model="haiku", description="Bestehende Specs", run_in_background=true, prompt="
  Suche nach bestehenden Specs in docs/specs/ die
  [Feature-Bereich] betreffen. Liste gefundene Specs mit Status.")

Agent(subagent_type="Explore", model="haiku", description="Dependencies", run_in_background=true, prompt="
  Identifiziere Dependencies und Imports fuer
  [Feature-Bereich]. Welche Module haengen davon ab? Welche werden importiert?")
```

Anonyme Starts (`Explore`, `Plan`, `general-purpose`) tragen immer ein `model`, sonst erben sie das Modell der Hauptsitzung (#577).

## Step 2b: Bug-Analyse (bug-intake/Haiku)

Bei Bugs dispatche den **bug-intake Agent** — eigener Agent-Typ (Projekt-Agent in `.claude/agents/`, lokal auch als Plugin-Agent), Start **ohne `model`**, das Modell steht im Frontmatter (#577):

## Step 3: Strategische Bewertung (Plan/Sonnet)

Dispatche einen **Plan/Sonnet Subagenten** fuer die strategische Bewertung:

```
Agent(subagent_type="Plan", model="sonnet", description="Strategische Bewertung", run_in_background=true, prompt="
  Basierend auf folgenden Investigation-Ergebnissen:
  [Ergebnisse aus Step 2]

  Bewerte:
  1. Technischer Ansatz (wie implementieren?)
  2. Risiko-Bewertung (was koennte brechen?)
  3. Scope-Schaetzung (Dateien, LoC)
  4. Abhaengigkeiten und Reihenfolge
  5. Befunde, die gegen den Plan sprechen (oder „keine“ mit Begruendung); bei Mess- oder
     Variantenvergleichen alle Varianten mit Zahlen in einer Tabelle, BEVOR die Empfehlung kommt
  6. Empfehlung (eine klare Empfehlung)")
```

## Step 4: Vorlage Synthese

Fasse die Ergebnisse zusammen und aktualisiere `docs/context/[workflow-name].md`:

```markdown
## Analysis

### Type
[Bug / Feature]

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| src/auth.py | MODIFY | Add OAuth provider |
| tests/test_auth.py | CREATE | New test file |

### Scope Assessment
- Files: [N]
- Estimated LoC: +[N]/-[N]
- Risk Level: LOW/MEDIUM/HIGH

### Technical Approach
[Empfehlung aus Plan/Sonnet Bewertung]

### Dependencies
[Aus Explore-Ergebnis]

### Open Questions
- [ ] Question 1?
```

## Auto-Modus: Kette selbst fortsetzen (#472)

Bei `AUTONOMY=auto`, ohne offene Frage an den User und ohne `/clear` in derselben Session: Rufe den Skill `30-write-spec` jetzt sofort selbst auf — warte nicht auf eine User-Eingabe. Eine offene Frage an den User stoppt die Kette auch im Auto-Modus. Der Checkpoint-Block oben bleibt trotzdem in der Ausgabe (Wiedereinstieg über `/30-write-spec #<N>`). Bei `AUTONOMY=manual` (oder jeder anderen Ausgabe): wie bisher auf den User warten.

## Kontext-Haushalt beim Selbstaufruf

Ein Schritt mit 200k Token Kontext kostet etwa das Fünffache eines Schritts mit 40k. Bei `CONTEXT_STOP=off` (auch mit `CONTEXT_REASON=AUTO_NO_CLEAR`: Auto-Modus, niemand tippt `/clear`, Nachschlagen an Teilagenten abgeben, Claude Code komprimiert automatisch) oder `CONTEXT_TOKENS=unknown`: Kette unverändert selbst fortsetzen (#658).
