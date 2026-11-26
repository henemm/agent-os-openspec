# Hintergrund zu /30-write-spec

Begründungen und Sonderfälle zu core/commands/30-write-spec.md; der Befehlstext enthält Ablauf und Pflichtschritte.

## Step 0: Workflow-State auflösen

**Wurde dieser Befehl mit einer Issue-Nummer aufgerufen** (z. B. `/30-write-spec #42` — typisch nach einem `/clear`)? Dann aktiviere den Workflow explizit. Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58).

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen) und den Stand verifizieren:

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Analyse-Stand. Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht — damit sichtbar ist, dass der `/clear` nichts verloren hat.

**Ohne Issue-Argument** (laufende Session, kein `/clear` dazwischen): `workflow.py status` reicht direkt.

## Fast Track (workflow_type == feature-fast)

Prüfe zuerst den Workflow-Typ:
```bash
python3 .claude/hooks/workflow.py status
```

Wenn `workflow_type: feature-fast` → **kein Sonnet-Agent, kein Haiku-Validator**.
Schreibe direkt eine Mini-Spec im Hauptkontext:

- Datei: `docs/specs/fast/[name].md`
- Format: laut `/00-intake` → Mini-Spec-Template
- Dann: `workflow.py set-field spec_file "docs/specs/fast/[name].md"`
- Dann: Freigabe vom User abwarten ("approved")
- **Kein PO-Briefing** (Gate überspringt Fast Track). Wer es auch hier will:
  `config.yaml` → `po_briefing_gate.skip_fast_track: false`, dann gilt Step 3b auch im Fast Track.
- Nach Freigabe: direkt zu `/50-implement`

**Workflows im vollen Prozess** folgen dem normalen Ablauf unten.

## Prerequisites (voller Prozess)

- Analysis completed (`phase2_analyse`)
- Context document exists with affected files list

Check current workflow:
```bash
python3 .claude/hooks/workflow.py status
```

## Step 1: Autarker Auftrag (#622)

**Autarker Auftrag (#622):** Läuft der Auftrag autark (`workflow.py queue` meldet `AUTARK=on`),
plane in der Spec keine Schritte ein, die eine menschliche Sperre (override) brauchen, wenn
eingebaute Standardwerte oder ein anderer Weg genügen. Vermeide insbesondere Änderungen an
der wirksamen Gate-Config; nur die reinen Anzeige-Abschnitte `next_suggestion` und
`time_estimate` sind per Edit ohne override änderbar. Reiche diesen Hinweis im Spec-Auftrag
an den spec-writer weiter.

## Hängende Subagenten

Primärer Schutz gegen einen hängenden Subagenten: Die Sitzung wird automatisch erneut aufgerufen,
sobald der Hintergrund-Agent fertig ist. Liegt beim nächsten eigenen Zug noch kein Bericht vor,
`TaskList` prüfen — ist der Agent dort noch als aktiv gelistet, ihn mit `TaskStop` beenden und
mit präziserem Briefing neu starten. Kein endloses Warten.

Nur falls dieser Befehl innerhalb eines `/loop`-Laufs (Selbsttaktung, dynamischer Modus) läuft,
zusätzlich dieser Rückfall:

```
ScheduleWakeup(1200, "Spec-Schreiben Rückfall [30-write-spec], nur im /loop-Kontext: TaskList → noch aktiver Spec-Writer-/Validator-/PO-Briefer-Agent? JA → TaskStop, dann User: 'Agent hängt — bitte /30-write-spec neu starten.' NEIN → ignorieren, fertig.")
```

## Agent-Typen und Fallback (#577)

Die Agenten dieses Befehls sind eigene Agent-Typen (Projekt-Agenten in `.claude/agents/`, lokal auch als Plugin-Agent). Starte sie mit `subagent_type="<name>"` **ohne `model`**: das Modell steht im Frontmatter des Agenten, ein `model`-Parameter würde es überstimmen. Die Definition liest der Agent nicht nach, sie ist sein Systemprompt.

**Fallback, wenn ein Typ in der Agent-Liste fehlt:** zuerst der Plugin-Name, sonst `general-purpose` mit dem Modell aus dem Frontmatter, und der Agent liest seine Definition (`.claude/agents/<name>.md`, im Framework-Repo `core/agents/<name>.md`) als Erstes:

## Step 2: Spec erstellen (spec-writer/Sonnet)

Dispatche den **spec-writer**:

```
Agent(subagent_type="spec-writer", description="Spec schreiben", run_in_background=true, prompt="
  Input:
  - feature_name: [Name]
  - analysis_summary: [Zusammenfassung aus Phase 2]
  - affected_files: [Liste aus Analyse]
  - dependencies: [Liste aus Analyse]
  - workflow_name: [Workflow-Name]

  Erstelle eine vollstaendige Spec in docs/specs/[category]/[entity].md
  nach dem spec-writer Workflow. Beachte alle Qualitaetsregeln.")
```

## Step 3: Spec validieren (spec-validator/Haiku)

Dispatche den **spec-validator/Haiku** zur Validierung:

**Im Vordergrund starten (`run_in_background: false`, #83):** Das Ergebnis wird sofort gebraucht, der Orchestrator hat währenddessen nichts zu tun. Hintergrund-Starts kurzlebiger Prüfagenten ohne Worktree-Isolation kamen wiederholt ohne Bericht zurück — Nachfordern oder Doppelstart kostete jedes Mal eine volle Runde.

```
Agent(subagent_type="spec-validator", description="Spec validieren", run_in_background=false, prompt="
  Validiere die Spec: docs/specs/[category]/[entity].md
  Pruefe alle Required Fields, Sections, Placeholders.
  Output: VALID oder INVALID mit Details.")
```

**Bei INVALID:**
1. Behebe die gemeldeten Fehler in der Spec
2. Dispatche spec-validator erneut
3. Wiederhole bis VALID

## Step 3b: PO-Briefing erstellen (po-briefer/Sonnet)

Die Freigabe ist die einzige Stelle, an der ein Mensch entscheidet. Sie darf nicht
auf deiner eigenen Zusammenfassung beruhen — du hast die Spec beauftragt, du bist
befangen. Dispatche deshalb einen **unabhängigen** Briefer, der die Spec gegen die
Ursprungsanfrage prüft, ohne deinen Gesprächsverlauf zu kennen:

```
Agent(subagent_type="po-briefer", description="PO-Briefing schreiben", run_in_background=true, prompt="
  ## Spec
  docs/specs/[category]/[entity].md

  ## Ursprungsanfrage
  Issue #[N]: [Titel + Text]   (ersatzweise: docs/context/[workflow].md)

  ## Workflow
  [workflow-name]

  Folge dem po-briefer Protokoll. Schreibe docs/briefings/[workflow-name].md.")
```

Danach registrieren — ohne diesen Schritt blockiert das Gate die Freigabe:

Der Befehl bindet das Briefing per SHA-256 an die gelesene Spec-Fassung. **Änderst
du die Spec danach noch, wird das Briefing ungültig** — dann Step 3b wiederholen,
nicht die Registrierung von Hand nachziehen.

Nach einem Rücksprung auf Analyse oder Spec ist das alte Briefing verworfen
(`po_briefing_history`, #647): Ein neues Briefing nach Step 3b ist Pflicht, vorher
gibt es weder Freigabe noch Auto-Freigabe.

Das Briefing wird dem User **wörtlich** ausgegeben (siehe unten). Du fasst es nicht
zusammen, kürzt es nicht und glättest seine kritischen Anmerkungen nicht — sonst ist
die Unabhängigkeit wieder weg.

## Step 4: Workflow State aktualisieren

```bash
# Update spec file path in workflow
python3 .claude/hooks/workflow.py set-field spec_file "docs/specs/[category]/[entity].md"

# Advance to spec_written phase
python3 .claude/hooks/workflow.py phase phase3_spec
```

## Step 4b: Auto-Freigabe versuchen (#470)

Der Befehl endet immer mit Exit 0 und gibt zwei Zeilen aus: `AUTO_APPROVE=done|human`
und `REASON=…`. Er gibt die Spec nur frei, wenn der Auto-Modus (`autonomy.mode: auto`
in der wirksamen Config) an ist, das registrierte Briefing seit `set-briefing`
unverändert ist, zur aktuellen Spec passt und `Ampel: gruen` trägt.

- **`AUTO_APPROVE=done`** — die Spec ist automatisch freigegeben (`phase4_approved`,
  protokolliert in `approvals`). Gib das Briefing wörtlich als Info aus (ab
  `## Was gebaut wird`), mit dem Hinweis „automatisch freigegeben (Ampel grün)",
  **ohne** ❗Du-Zeile — der PO muss nichts tippen. Danach rufst du den Skill
  `40-tdd-red` sofort selbst auf (vorher die Kontext-Prüfung aus „Next Step“ unten).
- **`AUTO_APPROVE=human`** — der PO entscheidet wie bisher: unten folgt die
  normale Freigabe-Ausgabe samt ❗Du-Zeile `approved`. Den `REASON` nennst du dem
  PO nur, wenn der Auto-Modus an ist (sonst ist `human` der Normalfall).

## Freigabe-Ausgabe an den User

Du schreibst **keine eigene Zusammenfassung** der Spec. Was gebaut wird, wo vom
Ticket abgewichen wurde und was fragwürdig ist, steht im unabhängigen Briefing —
eine zweite Fassung von dir wäre wieder Selbstauskunft und verdoppelt nur den Text.

Die Ausgabe besteht aus genau diesen Teilen, in dieser Reihenfolge:

1. **Das Briefing wörtlich** — Inhalt von `docs/briefings/<workflow-name>.md` ab
   `## Was gebaut wird` bis zum Ende. Nichts weglassen, nichts umformulieren.
2. **Optional: deine Gegenstimme** — nur zu einer *Kritischen Anmerkung*, der du
   widersprichst, je genau eine Zeile `Meine Einschätzung: …`, höchstens 3 Zeilen
   insgesamt. Stimmst du allen Anmerkungen zu: nichts schreiben.
3. **❗Du-Zeile + Marker-Zeile** — wörtlich, als letzte beiden Zeilen, `⚙` ganz zuletzt:
   `❗ Du: \`approved\` — Freigabe der Spec, danach beginnt die Umsetzung`
   `⚙ PO-Briefing unabhängig erstellt · agent-os-openspec {{OPENSPEC_VERSION}}`
   Diese Freigabe verlangt *immer* eine PO-Entscheidung — anders als bei den generischen
   Pflicht-Markern in anderen Befehlen gibt es hier keine `⏳ Läuft noch`- und keine
   `✅ Erledigt`-Variante.

## After Approval

When user approves:
1. `workflow_state_updater` hook detects approval phrase
2. State advances to `phase4_approved`
3. Next: `/40-tdd-red` to write failing tests

Ohne `/clear` in derselben Session: Rufe den Skill `40-tdd-red` jetzt sofort selbst
auf — warte nicht auf eine weitere User-Eingabe, die Freigabe ("approved") ist
bereits die Entscheidung.

Mit `/clear` dazwischen: Der Checkpoint-Block unten zeigt den regulären
Wiedereinstieg über den expliziten Befehl `/40-tdd-red #<N>`.

Vor dem Selbstaufruf zusätzlich `python3 .claude/hooks/workflow.py context` ausführen (Kontext-Haushalt): Bei `CONTEXT_STOP=on` (Kontext über der wirksamen Schwelle `CONTEXT_THRESHOLD` aus `context_budget`: Grundkontext der Sitzung + `growth_tokens`, mindestens `clear_threshold_tokens`, Default 100.000 Token, nur im Modus manual) den Skill `40-tdd-red` NICHT selbst aufrufen, sondern die Antwort mit dem Checkpoint und der ❗Du-Zeile `/40-tdd-red #<N>` beenden — der Stand liegt auf der Platte, der PO tippt `/clear`. Ein Schritt mit 200k Token Kontext kostet etwa das Fünffache eines Schritts mit 40k. Bei `CONTEXT_STOP=off` (auch mit `CONTEXT_REASON=AUTO_NO_CLEAR`: Auto-Modus, niemand tippt `/clear`, Nachschlagen an Teilagenten abgeben, Claude Code komprimiert automatisch) oder `CONTEXT_TOKENS=unknown`: Kette unverändert selbst fortsetzen (#658).

Nach der Freigabe kannst du dem User zusätzlich den Kontext-Reset anbieten:

## IMPORTANT

**IMPORTANT:**
- Do NOT implement until approved
- Die Spec-Freigabe nie per Auswahldialog (`AskUserQuestion`) erfragen, sondern immer mit der ❗Du-Zeile `approved`: der `phase_listener` sieht ausschließlich getippte Nachrichten, eine im Dialog geklickte Freigabe wirkt nicht. Hat der PO im Dialog bereits freigegeben, bitte in genau einer Zeile um das Stichwort (#183, #485)
- Do NOT skip TDD RED phase after approval
- Die Freigabe-Ausgabe ist das Briefing wörtlich plus Marker-Zeile — keine eigene
  Zusammenfassung davor oder danach. Abweichungen vom Ticket benennt der po-briefer
  unter *Kritische Anmerkungen*. Widersprichst du einer Anmerkung: eine
  "Meine Einschätzung"-Zeile je Anmerkung, max. 3 — kein eigener Block.
