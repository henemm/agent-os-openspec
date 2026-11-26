# Workflow Management

Manage multiple parallel workflows with isolated state (v3).

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/80-workflow.md` im Plugin-Ordner — nur bei Bedarf lesen.

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/80-workflow #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf. Alle anderen Argumente (`list`, `status`, `switch <name>` …) laufen wie unten beschrieben:

```bash
python3 .claude/hooks/workflow.py find 42   # die übergebene Nummer
```

**PFLICHT direkt danach** — Workflow wirklich aktivieren (ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT):

```bash
python3 .claude/hooks/workflow.py switch <NAME-aus-obigem-Output>
python3 .claude/hooks/workflow.py status
```

**Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht**, inklusive des nächsten Pflicht-Schritts.

**Ohne Argument** gilt der Rest dieser Datei unverändert.

## Commands

```bash
python3 .claude/hooks/workflow.py list                 # alle Workflows
python3 .claude/hooks/workflow.py sessions [--json]    # aktive Sitzungen (Session-Register)
python3 .claude/hooks/workflow.py status               # aktueller Stand
python3 .claude/hooks/workflow.py start "feature-name"
python3 .claude/hooks/workflow.py switch "other-feature"
python3 .claude/hooks/workflow.py phase phase4_approved
python3 .claude/hooks/workflow.py set-field spec_file "docs/specs/auth/login.md"
python3 .claude/hooks/workflow.py set-field context_file "docs/context/login.md"
python3 .claude/hooks/workflow.py set-field github_issue 42
python3 .claude/hooks/workflow.py set-affected-files src/auth.py src/login.py
python3 .claude/hooks/workflow.py add-artifact test_output \
    "docs/artifacts/feature/test-red.txt" "Test FAILED: assertion error" phase5_tdd_red
python3 .claude/hooks/workflow.py mark-red "3 tests failed"
python3 .claude/hooks/workflow.py mark-ui-red "UI test assertion"
python3 .claude/hooks/workflow.py write-log success|partial|reverted   # Pflicht vor finish
python3 .claude/hooks/workflow.py override-ambiguous "reason for proceeding"
python3 .claude/hooks/workflow.py set-field loc_limit_override 500          # Produktivcode
python3 .claude/hooks/workflow.py set-field test_loc_limit_override 800     # Testcode
python3 .claude/hooks/workflow.py finish
python3 .claude/hooks/workflow.py abandon --reason "Analyse-Vorlauf, Umsetzung in FEAT_002 abgeschlossen"
python3 .claude/hooks/workflow.py retro-list | retro [<name>]   # Slash-Command: /90-retro
python3 .claude/hooks/qa_gate.py --run [--checklist <dialog.md>]   # Testlauf aus qa_gate.test_command, setzt Adversary-Verdict (Details: docs/befehle/80-workflow.md, "QA Gate")
```

Mit Issue-Nummer im Namen registriert `start` die Sitzung als Kommentar am Issue (#461). Ist
dort schon eine andere Sitzung registriert, bricht `start` ohne Workflow ab und nennt Sitzung,
Ort, Beginn und Erreichbarkeit. Übersicht: `workflow.py claim status`; Nachholen nach Offline-Start:
`workflow.py claim nachholen`; bewusste Übernahme: `workflow.py start "feature-name" --uebernehmen`.

`abandon` nur für Workflows OHNE Prüfgegenstand (nie in phase6_implement); NICHT den
workflow_type umklassifizieren, um das Gate loszuwerden. Die Begründung ist Pflicht.

### Endzustand der Fußzeile (#550)
```bash
python3 .claude/hooks/workflow.py endstate [#N|name]
python3 .claude/hooks/workflow.py waiting "<text>"
python3 .claude/hooks/workflow.py waiting --clear
```
`endstate` gibt die Schlusszeile aus: `✅ Erledigt`, `⏳ Läuft noch` oder `❗ Du`.

### Auftragsliste (#551)
```bash
python3 .claude/hooks/workflow.py queue add <N...> [--autark] [--note "<Wortlaut>"]
python3 .claude/hooks/workflow.py queue            # bzw. queue list
python3 .claude/hooks/workflow.py queue done <N>
python3 .claude/hooks/workflow.py queue clear
python3 .claude/hooks/workflow.py queue claim      # verwaisten Auftrag übernehmen (#613)
```
Ausgabe `QUEUE=`, `AUTARK=`, `NEXT=` und bei offenem Auftrag `PROMPT=/00-intake #<NEXT>`.

### Übergabe an eine frische Sitzung (#667)
```bash
python3 .claude/hooks/workflow.py handoff                 # Weg + Startauftrag
python3 .claude/hooks/workflow.py handoff --start         # Herdr: neue Sitzung im neuen Tab
python3 .claude/hooks/workflow.py handoff --mark cloud    # Start vermerken (nach create_session)
```
Ausgabe `HANDOFF=cloud|herdr|inline|none`, `NEXT=`, Startauftrag zwischen `PROMPT_BEGIN`/`PROMPT_END`.
`--start` meldet `STARTED=yes|no|already`. Ist für `NEXT` schon ein Start vermerkt, folgt
`HANDOFF_DONE=<weg>` (#668: keine zweite Sitzung starten). `--mark` meldet `MARKED=yes|no`;
scheitert der Vermerk, folgt `WARN=Vermerk fehlgeschlagen (<Typ>)`. Die neue Sitzung (eigener
Tab „#M Titel“, #694) schließt den Tab der Vorgängerin nach sauberer Übergabe (⏳).
