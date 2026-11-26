# Hintergrund zu /50-implement

Begründungen und Sonderfälle zu core/commands/50-implement.md; der Befehlstext enthält Ablauf und Pflichtschritte.

## Step 0: Workflow-State auflösen

Der komplette State (Phase, Spec, RED-Tests, Verdict) überlebt jeden `/clear` und jeden Worktree.

Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58).

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec/Verdict. Die Zusammenfassung in 2 Sätzen macht sichtbar, dass der `/clear` nichts verloren hat.

**Ohne Issue-Argument** (laufende Session, kein `/clear` dazwischen):
```bash
python3 .claude/hooks/workflow.py status
```

## Step 1: Verify RED Phase Complete

```bash
python3 .claude/hooks/workflow.py status
```

## Hängende Subagenten

Primärer Schutz gegen einen hängenden Subagenten: Die Sitzung wird automatisch erneut aufgerufen,
sobald der Hintergrund-Agent fertig ist. Liegt beim nächsten eigenen Zug noch kein Bericht vor,
`TaskList` prüfen — ist der Agent dort noch als aktiv gelistet, ihn mit `TaskStop` beenden und
mit präziserem Briefing neu starten. Kein endloses Warten.

Nur falls dieser Befehl innerhalb eines `/loop`-Laufs (Selbsttaktung, dynamischer Modus) läuft,
zusätzlich der Rückfall aus dem Befehlstext.

## Agent-Typen und Fallback (#577)

`developer-agent` und `implementation-validator` sind eigene Agent-Typen (Projekt-Agenten in `.claude/agents/`, lokal auch als Plugin-Agent). Starte sie mit `subagent_type="<name>"` **ohne `model`**: das Modell steht im Frontmatter des Agenten, ein `model`-Parameter würde es überstimmen. Anonyme Starts (`Explore`, `general-purpose`) tragen dagegen immer ein `model`, sonst erben sie das Modell der Hauptsitzung.

**Fallback, wenn ein Typ in der Agent-Liste fehlt:** zuerst der Plugin-Name, sonst `general-purpose` mit dem Modell aus dem Frontmatter, und der Agent liest seine Definition (`.claude/agents/<name>.md`, im Framework-Repo `core/agents/<name>.md`) als Erstes.

## Step 2: Kontext laden (Explore/Haiku)

**Im Vordergrund starten (`run_in_background: false`, #83):** Das Ergebnis wird sofort gebraucht, der Orchestrator hat währenddessen nichts zu tun. Hintergrund-Starts kurzlebiger Prüfagenten ohne Worktree-Isolation kamen wiederholt ohne Bericht zurück — Nachfordern oder Doppelstart kostete jedes Mal eine volle Runde.

**Kontext-Haushalt:** Nachschlagefragen („Wo wird X benutzt?“, „Welche Dateien importieren Y?“, „Wie heißt die Funktion für Z?“) gehen an einen Explore-Teilagenten (Haiku), der mit eigenem, kleinem Kontext liest und nur die Antwort zurückgibt — Recherche ist der größte Token-Posten, und im Hauptkontext zahlt jeder Schritt das Wiederlesen aller vorher gelesenen Dateien erneut.

## Step 3: Developer Agent spawnen (ORCHESTRATOR-PRINZIP)

Der Hauptkontext ist ein **Orchestrator** — er koordiniert, plant, und entscheidet.
Code-Edits gehoeren ausschliesslich dem **Developer Agent**.

**Nach Rueckmeldung des Developer Agent:**
- Tests GRUEN → weiter zu Step 4
- Tests noch ROT → Developer Agent erneut beauftragen mit Fehlermeldung (max. 3 Versuche total)
- Nach 3 Versuchen immer noch ROT → Eskalation an User: Root Cause unklar

| Rolle | Darf | Darf NICHT |
|-------|------|------------|
| **Orchestrator** (Hauptkontext) | Read, Grep, Bash (Tests starten, Output lesen), koordinieren | Edit/Write auf Code-Dateien |
| **Developer Agent** (Sub-Task) | Edit, Write, Tests ausfuehren, Code schreiben | Planen, User-Interaktion |

## Step 4: GREEN Artifacts registrieren

Der Developer Agent hat den Test-Output bereits gespeichert.
Orchestrator registriert das Artifact im Workflow-State.

## Step 6: User-Freigabe der GREEN-Ergebnisse

Freigaben nie über den Auswahldialog (`AskUserQuestion`) einholen, nur als Textzeile: der `phase_listener` sieht ausschließlich getippte Nachrichten, eine im Dialog geklickte Freigabe wirkt nicht und der PO muss sie erneut tippen (#183)

## 8a. Spec parsen — Checkliste erstellen

`adversary_dialog.py parse` zeigt dir die zu beweisenden Punkte — geparst aus `## Expected Behavior` und/oder `## Acceptance Criteria` (`- **AC-N:** ...`) der Spec, je nachdem welche Section(s) vorhanden sind.

Danach das Protokoll-Geruest erzeugen (#278) — es ist die einzige Quelle des Formats (Checkliste, `### Runde N`-Koepfe, `## Verdict`); der Adversary-Agent befuellt es, statt das Format zu erraten.

Herkunft der Vorbedingungen (#286): Ist `default_lang` nicht gesetzt, entfaellt der Aufruf; der Agent traegt dann den Hinweistext „kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)" in die Sektion `## Herkunft der Vorbedingungen` ein. Das Gate (`precondition_section_gate`, `mode: warn|block`) prueft, dass die Sektion existiert und jede Verdachtszeile (hoechstens eine Produktions-Schreibstelle) „Bedingung davor" und „Test für diesen Weg" ausgefuellt hat.

## 8b. Adversary-Dialog fuehren

Der Dialog laeuft als Hin-und-Her. **Du als Orchestrator koordinierst:**
1. Adversary Agent nennt naechsten offenen Punkt + was er sehen will
2. Du (Orchestrator) beauftragst Developer Agent, Beweis zu sammeln (Test ausfuehren, Screenshot, Code-Pfad)
3. Developer Agent liefert Beweis-Output → du relayierst an Adversary Agent
4. Adversary Agent bewertet: AKZEPTIERT oder NACHFRAGE
5. Wiederholen bis alle AC-N-Punkte bewiesen ODER Defekt gefunden

## 8c. Dialog-Protokoll speichern

`adversary_dialog.py required-files` listet jede Code-Datei, die seit der Basis des Workflows geaendert ist — dieselbe Menge, die Phase 8
prueft (Basis und ggf. Degradations-Hinweis auf stderr). Das Protokoll muss **jede gelistete Datei**
per `Code reference: <pfad>:<zeile>` zitieren; nur so landet sie beim `stamp` im Hash-Block.

`stamp` hasht jede per `Code reference:` zitierte Datei aus Findings/Confirmations
und haengt einen `## Geprüfte Dateien`-Block an. Das Gate prueft in 8d
gegen diese Hashes statt gegen das Datei-Alter — ohne diesen Schritt wird
das Artifact unabhaengig davon abgelehnt, wie frisch es ist (Issue #131).

**Gate-Wirkung (#253):** Commit-Gate und Phase 8 akzeptieren `VERIFIED` (bzw. `AMBIGUOUS` mit
Override) nur mit diesem registrierten, gestempelten Artifact, dessen gehashte Dateien zum aktuellen
Code passen. Es zaehlt das zuletzt registrierte `adversary_dialog`; ohne Registrierung der
Standardpfad oben. Ein gruener Testlauf aktualisiert nur `last_test_run` — er setzt kein Verdict und
oeffnet keinen Commit. Aendert ein spaeterer Fix (auch ein Auto-Fix in `/60-validate`) eine zitierte
Datei, braucht es einen neuen Dialog.

**Schon beim Wechsel nach Phase 7:** `workflow.py phase phase7_validate` prueft dasselbe — Verdict,
registriertes und gestempeltes Artifact, Abdeckung (#259) — nicht erst Phase 8 oder der Commit. Fehlt
etwas, blockt der Wechsel mit `BLOCKED`. Der BROKEN-Ruecksprung `phase phase6_implement` bleibt frei.

**Aufsetzen auf main nach dem VERIFIED (#289):** `stamp` haelt zusaetzlich einen `## Prüfbasis`-Block
fest (merge-base mit `origin/main`, der gepruefte Stand je Datei als Git-Blob). Aendert main eine
gebundene Datei, gilt der Nachweis nach Rebase/Merge weiter, solange der 3-Wege-Merge (gepruefte
Aenderung auf die neue Basis) konfliktfrei ist und exakt den aktuellen Stand ergibt. Bei Konflikt oder
eigener Nacharbeit ist ein neuer Dialog noetig — deshalb moeglichst **vor** dem Adversary-Dialog auf
main aufsetzen.

**Gate-Wirkung (#259):** Der Hash-Block muss zudem die Aenderungsmenge abdecken — am Commit-Gate jede
Code-Datei des entstehenden Commits, in Phase 8 jede seit der Basis (`base_commit` bzw.
`merge-base(origin/main, HEAD)`) geaenderte Code-Datei, also genau die `required-files`-Liste. Eine
nicht zitierte Datei blockt, am Commit-Gate auch eine teilweise gestagte. Commit-Ausweg: Override-Token;
Kill-Switch: `config.yaml` → `adversary_coverage_gate.enabled: false`.

## 8d. QA-Gate mit Checklist-Validierung

Ohne `--checklist` prueft `qa_gate.py` nur die Testausgabe — das oeffnet weder Commit noch Phase 8.

Ausgaben immer unter `docs/artifacts/<workflow-name>/` ablegen, nie unter `/tmp`: Schreibziele
ausserhalb des Projekts blockt `secret_egress_guard` (Ausnahme: das eigene Sitzungs-Scratchpad).

**Tri-State Verdict:**
- **VERIFIED** — Alle Punkte bewiesen, weiter zu Phase 7
- **BROKEN** — Defekte gefunden, zurueck zu Step 3 (neuer Fix + neuer Dialog!)
- **AMBIGUOUS** — Unklare Befunde, Pipeline NICHT blockiert aber User-Review empfohlen

**Circuit Breaker (max 3 Iterationen):**
Wenn nach 3 QA-Fixer-Loops noch BROKEN: Eskalation an User mit allen Findings.

## Implementation Constraints

Follow scoping limits:
- **Max 4-5 files** per change
- **Max +/-250 LoC** total
- **Functions <= 50 LoC**
- **No side effects** outside spec scope

## Next Step

Kontext-Haushalt: Ein Schritt mit 200k Token Kontext kostet etwa das Fünffache eines Schritts mit 40k.

## Common Mistakes

- **Adding unrequested features** -> Scope creep
- **Skipping tests** -> Not TDD
- **Large functions** -> Hard to test/maintain
- **Not running tests** -> Might still be RED
- **Skipping adversary** -> Commit will be BLOCKED
- **Skipping User-Freigabe** -> Validation BLOCKED without user approval
- **Orchestrator schreibt Code selbst** -> Verletzt Orchestrator-Prinzip, kein Isolation-Schutz
