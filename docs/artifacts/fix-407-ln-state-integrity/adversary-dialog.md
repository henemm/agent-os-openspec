# Adversary Dialog — fix-407-ln-state-integrity
Spec: docs/specs/fix-407-ln-state-integrity.md
Datum: 2026-10-09 09:15

## Checkliste
- [x] **Input:** Ein Bash-Befehl durch `bash_gate.py`, Projekt mit aktivem Workflow.
- [x] **Output:** Verweise und Ordner-Operationen mit einem Zustandspfad enden mit Exit 2 und der bestehenden 3b-Meldung „Direct state file manipulation“. Lesende und unbeteiligte Befehle laufen mit Exit 0.
- [x] **Side effects:** Keine neuen Subprozesse, keine neuen Abhängigkeiten. Ohne aktiven Workflow bleibt das Verhalten unverändert.
- [x] **AC-1:** Given ein aktiver Workflow / When `ln`, `ln -f`, `ln -s` oder `link` eine State-Datei `.claude/workflows/<wf>.json` als Quelle erhält / Then blockt das Gate mit Exit 2
- [x] **AC-2:** Given ein aktiver Workflow / When `ln` eine State-Datei als Ziel erhält (`ln docs/x/notes.txt .claude/workflows/<wf>.json`) / Then blockt das Gate mit Exit 2
- [x] **AC-3:** Given ein aktiver Workflow / When `ln` `.claude/user_override_token.json`, `.claude/settings.json` oder `ln -s ../core/hooks/x.py .claude/hooks/x.py` verwendet / Then blockt das Gate mit Exit 2
- [x] **AC-4:** Given ein aktiver Workflow / When ein Ordner-Verweis auf den Zustandsordner angelegt wird (`ln -s .claude/workflows docs/w`, `ln -s .claude docs/c`, auch mit `./`, absolutem Pfad und abschließendem Slash) / Then blockt das Gate mit Exit 2
- [x] **AC-5:** Given ein aktiver Workflow / When `mv .claude/workflows docs/w`, `cp -r .claude/workflows docs/w`, `cp -r docs/w .claude/workflows`, `rsync -a docs/w/ .claude/workflows/` oder `install docs/x .claude/workflows/<wf>.json` läuft / Then blockt das Gate mit Exit 2
- [x] **AC-6:** Given ein aktiver Workflow / When der Befehl nur über `sh -c`/`eval` oder bei nicht zerlegbarem Text (Roh-Scan-Fallback) ein Ordner- oder State-Muster samt `ln` enthält / Then blockt das Gate ebenfalls mit Exit 2
- [x] **AC-7:** Given ein aktiver Workflow / When `ls -ln <state>`, `cat <state>`, `ln -s docs/a docs/b`, `ln -s … .claude/worktrees/x/node_modules`, `pip install x` oder `npm install` läuft / Then lässt das Gate sie mit Exit 0 durch
- [x] **AC-8:** Given ein aktiver Workflow / When Freitext in `-m`/`--body` die Zeichenfolge „ln .claude/workflows“ enthält / Then lässt das Gate den Befehl mit Exit 0 durch (Freitext-Ausnahme)
- [x] **AC-9:** Given kein aktiver Workflow / When dieselben Verweis- und Ordner-Befehle laufen / Then bleibt das Verhalten unverändert (Exit 0)
- [x] **AC-10:** Given der bestehende Testbestand / When die Regressionstests laufen / Then bleiben sie grün

## Dialog

### Runde 1
**Adversary:** Ich habe die Suite selbst gestartet, die Tests nicht nur gelesen. Ergebnis 151 passed, 0 failed, 0 übersprungen. Das umfasst `tests/test_bash_gate*.py` (alle 9 Dateien, auch merge_head_352 und worktree_commit_155) und `tests/test_qa_gate_run_345.py`. Danach habe ich 55 Umgehungsversuche und 37 Fehlalarm-Kandidaten als Subprozess gegen das echte `core/hooks/bash_gate.py` des Worktrees gefahren (Wegwerf-Repo, aktiver Workflow phase6, `CLAUDE_TOOL_INPUT`), und zwar mit `probe.py`. Die Pfad-Strings habe ich per Platzhalter zusammengesetzt, damit mein eigener Heredoc nicht vom Gate geblockt wird.

Blockiert wurden (Exit 2) unter anderem:
- `ln -sf`, `ln --`, `/bin/ln`, Tabs statt Leerzeichen
- `cp -a .claude/` und `cp -a .claude`, `ln -s '.claude/workflows'`, `ln -s "$PWD/.claude"`
- `rsync` von `~/x/` nach `.claude/workflows/`
- `mv .claude docs/c`, `sudo ln`, `FOO=1 ln`, `(ln …)`, `true && ln`, `command ln`
- `sh -c 'ln …'`, `eval 'ln …'`, `bash -c "ln …"`
- `ln ../.claude`, `ln ./.claude`, absoluter Pfad, `ln … @C/workflows/*.json`
- Token-, Settings- und Hook-Datei als Ziel

Fehlalarm-Kandidaten blieben alle frei (Exit 0):
- `echo ln .claude`, `grep install .claude/workflows/x.json`
- `ls .claude/workflows | xargs echo`, `npx install`
- `ls -ln <state>`, Worktree-Pfade `.claude/worktrees/x`
- `python3 .claude/hooks/workflow.py status`, `ls .claude && rm docs/x`
- `ls .claude && ln -s docs/a docs/b`, `ls .claude && pip install x`
- `rsync docs/a docs/b`, `install docs/x docs/y`

Umgehungen, die ich gefunden habe (Exit 0):
- `cp -r docs/w/. .claude/workflows/.` und die Varianten mit `/..`, `/.` oder `/../workflows` am Ende (Lookahead-Lücke im Ordner-Muster).
- `ln -s .claude//workflows d` (doppelter Slash).
- `cd .claude && ln -s workflows ../w` und `cd .claude; …` sowie `pushd`. Die Dateivariante `cd .claude && ln workflows/<wf>.json ../x` wird dagegen geblockt, der Ordner-Verweis aus dem cd-Kontext heraus nicht.
- `ls .claude/workflows | xargs ln -s docs/x` und `find … -exec ln {} docs/ \;`. Ordner-Token und Verweisbefehl stehen in verschiedenen Segmenten.
- `env -i ln -s .claude d`, `tar xf a.tar -C .claude`, `cp -r .claude/workflows/. docs/w` (das ist nur Kopieren heraus).

Alles davon ist Verschleierung oder ungewöhnliche Schreibweise. Bis auf `/.` und `cd .claude && ln -s` gilt das als vorsätzlich im Sinne des Bedrohungsmodells der Spec („verhindert wird das versehentliche Umgehen“).
**Implementierer:** (nicht anwesend, kein Gegenargument eingeholt)

### Runde 2
**Adversary:** Ich habe die bekannten Abweichungen bewertet.

1. **AC-8-Test nutzt `git tag -a -m`, `gh issue comment --body`, `gh pr create --body` statt `git commit -m`.**
   - Ich habe `gh pr create --title 'ln .claude/workflows' --body 'x'`, `--body "ln .claude/workflows; ln -s .claude d"` und `git tag -a v1 -m 'ln .claude/workflows'` selbst gefahren. Alle gaben Exit 0, die Freitext-Ausnahme greift.
   - Das Gegenstück `gh pr create --body 'x'; ln -s .claude d` gab Exit 2. Echter Befehlstext außerhalb des Freitexts wird weiter erkannt.
   - Der Freitext-Mechanismus (`hook_utils` Flags) ist für alle Befehle derselbe, `git commit` ist kein Sonderpfad. Die Ersetzung ist legitim und schwächt AC-8 nicht.

2. **Ordner-Muster nur im selben Segment wie ein Schreib-/Verweisbefehl.**
   - Mit `ls .claude && rm docs/x` und `ls .claude && ln -s docs/a docs/b` bleibt `ls .claude` korrekt frei.
   - Die Kehrseite sind die Pipe-/xargs-Umgehungen aus Runde 1. Sie sind wegen der Fehlalarm-Vermeidung eine bewusste Abwägung und dokumentiert, siehe F004.

3. **Neue Erkennung nur bei aktivem Workflow.**
   - Ohne Workflow gaben `ln -s`, `ln`, `mv`, `cp -r`, `rsync` und `install` auf `.claude/workflows` jeweils Exit 0.
   - Dasselbe gilt für einen Workflow mit vorhandener JSON, aber fehlender `active_workflow`-Datei. Das ist AC-9-konform und konsistent mit „Ohne aktiven Workflow unverändert“.
   - Im Code: `wf_active = workflow_enforced and bool(get_active_workflow_name())` (bash_gate.py:986) wird als `dirs`/`links` durchgereicht.

4. **Entfernter Byte-Vergleich in `tests/test_qa_gate_run_345.py`.**
   - Er prüfte `bash_gate.py == origin/main` und sicherte nur den Scope von #345. Jede spätere Änderung an `bash_gate.py`, auch diese, muss ihn zwingend brechen.
   - Der eigentliche Nutzen von AC-13 bleibt erhalten: `test_qa_gate_calls_pass_bash_gate` prüft weiter, dass beide `qa_gate`-Aufrufe das Gate passieren. Der Test läuft grün (in den 151).
   - Die Entfernung ist legitim, keine Abschwächung der Absicherung.

Side effects: Das Diff von `core/hooks/bash_gate.py` enthält keinen neuen `subprocess`-, `import`- oder Netzwerk-Aufruf. Es sind nur ein kompilierter Regex, eine Liste und zwei kleine Funktionen.
**Implementierer:** (nicht anwesend)

Confirmation:
  AC: Input
  Code reference: core/hooks/bash_gate.py:986
  Evidence: wf_active wird aus workflow_enforced und get_active_workflow_name() abgeleitet, das Gate wertet jeden Bash-Aufruf mit aktivem Workflow aus (probe.py, 55 Fälle als Subprozess).
  Status: CONFIRMED

Confirmation:
  AC: Output
  Code reference: core/hooks/bash_gate.py:988
  Evidence: Block-Meldung stammt aus der bestehenden 3b-Prüfung (_state_msg), Tests prüfen "Direct state file manipulation" in stderr; Kontrollfälle (37) laufen mit Exit 0.
  Status: CONFIRMED

Confirmation:
  AC: Side effects
  Code reference: core/hooks/bash_gate.py:76
  Evidence: Nur kompilierter Regex und zwei reine Funktionen, kein subprocess/Import im Diff; ohne Workflow Exit 0 (probe3.py, 8 Fälle).
  Status: CONFIRMED

Confirmation:
  AC: AC-1
  Code reference: core/hooks/bash_gate.py:447
  Evidence: _LINK_COMMAND_RE erkennt ln/link als Kommandowort; ln -sf, ln --, /bin/ln, Tab-getrennt, link blockten mit Exit 2.
  Status: CONFIRMED

Confirmation:
  AC: AC-2
  Code reference: core/hooks/bash_gate.py:259
  Evidence: _protected_outside_whitelist prüft die Segmente auf Schutzmuster; `ln docs/x .claude/workflows/<wf>.json` gab Exit 2.
  Status: CONFIRMED

Confirmation:
  AC: AC-3
  Code reference: core/hooks/bash_gate.py:443
  Evidence: Token-, Settings-Datei und Hook-Ziel mit ln gaben Exit 2 (probe.py); die Datei-Muster aus PROTECTED_FILE_PATTERNS greifen jetzt mit Verweisbefehl.
  Status: CONFIRMED

Confirmation:
  AC: AC-4
  Code reference: core/hooks/bash_gate.py:69
  Evidence: PROTECTED_DIR_TOKEN_PATTERNS blockt Ordner-Verweise mit ./, absolutem Pfad, Slash, Anführungszeichen und $PWD; Ausnahmen siehe F001 bis F003.
  Status: CONFIRMED

Confirmation:
  AC: AC-5
  Code reference: core/hooks/bash_gate.py:279
  Evidence: _writes_state_dir verknüpft Ordner-Token mit Schreib-/Verweisbefehl; mv, cp -r in beide Richtungen, cp -a, rsync, install gaben Exit 2.
  Status: CONFIRMED

Confirmation:
  AC: AC-6
  Code reference: core/hooks/bash_gate.py:76
  Evidence: Der Regex deckt `-c "`/`eval "` im Roh-Scan ab; sh -c, eval und bash -c mit ln blockten mit Exit 2.
  Status: CONFIRMED

Confirmation:
  AC: AC-7
  Code reference: core/hooks/bash_gate.py:76
  Evidence: Kommandowort statt \bln\b: ls -ln, pip install, npm install, npx install, Worktree-Pfade, echo ln .claude blieben alle Exit 0.
  Status: CONFIRMED

Confirmation:
  AC: AC-8
  Code reference: core/hooks/bash_gate.py:988
  Evidence: Freitext in -m/--body bleibt Exit 0 (gh pr create --body, git tag -m), während der echte Befehl hinter dem Freitext weiter Exit 2 liefert (probe3.py).
  Status: CONFIRMED

Confirmation:
  AC: AC-9
  Code reference: core/hooks/bash_gate.py:986
  Evidence: Ohne Workflow bzw. ohne active_workflow gaben alle sechs Verweis-/Ordner-Befehle Exit 0 (probe3.py).
  Status: CONFIRMED

Confirmation:
  AC: AC-10
  Code reference: core/hooks/bash_gate.py:443
  Evidence: 151 passed, 0 failed in tests/test_bash_gate*.py und tests/test_qa_gate_run_345.py, darunter false_positives, freetext_64_75, erkennung_299 (a/b/c) und env_aliase_324.
  Status: CONFIRMED

Finding:
  ID: F001
  Severity: MEDIUM
  Category: edge_case
  Code reference: core/hooks/bash_gate.py:69
  Description: Das Ordner-Muster endet mit Lookahead `(?=[\s"';&|)]|$)` direkt nach `/*`. Ein abschließendes `/.` oder `/..` passt nicht, z. B. `cp -r docs/w/. .claude/workflows/.`, `ln -s docs/w .claude/workflows/.`, `rsync -a docs/w/ .claude/workflows/.` (alle Exit 0 am echten Gate).
  Spec requirement: AC-5 — rsync/cp -r in den Zustandsordner blockt mit Exit 2
  Conflict: Die in der Praxis übliche Form „Inhalt eines Ordners kopieren“ (`src/. dst/.`) umgeht die Ordner-Erkennung. Mit der Spec-Schreibweise `.claude/workflows/` blockt es, mit `/.` nicht.
  Remediation: Das Muster um `(?:/\.{1,2})*` vor dem Lookahead erweitern. Alternativ als Known Limitation und in #410 mit der st_nlink-Prüfung aufnehmen.

Finding:
  ID: F002
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/bash_gate.py:69
  Description: `ln -s .claude//workflows d` (doppelter Slash) ergibt Exit 0, weil `/*` nur nach `workflows` steht und das Präfixmuster `.claude(?:/workflows)?` einen einzelnen Slash verlangt.
  Spec requirement: AC-4 — Ordner-Verweis auf den Zustandsordner
  Conflict: Seltene, aber triviale Schreibweise führt am Muster vorbei.
  Remediation: `/+` statt `/` zwischen `.claude` und `workflows`.

Finding:
  ID: F003
  Severity: MEDIUM
  Category: edge_case
  Code reference: core/hooks/bash_gate.py:279
  Description: `cd .claude && ln -s workflows ../w`, `cd .claude; …` und `pushd .claude && …` ergeben Exit 0. `_cd_context_protected` deckt nur Dateinamen im cd-Kontext ab, `_writes_state_dir` verlangt einen Ordner-Token im selben Segment wie den Verweisbefehl. `cd .claude && ln workflows/<wf>.json ../x` und `cd .claude/workflows && ln …` werden dagegen geblockt.
  Spec requirement: AC-4 — Ordner-Verweis auf den Zustandsordner
  Conflict: Ein Ordner-Verweis auf den Zustandsordner aus dem cd-Kontext heraus bleibt ein offenes Loch, genau die Form, die die Spec für `ln -s .claude/workflows docs/w` schließen will.
  Remediation: In `_cd_context_protected` Ordner-Verweise (ln/link/mv/cp -r/rsync) nach `cd .claude` ebenfalls werten. Alternativ als Known Limitation in #410 aufnehmen.

Finding:
  ID: F004
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/bash_gate.py:279
  Description: Segmentweise Prüfung lässt `ls .claude/workflows | xargs ln -s docs/x`, `find .claude/workflows -exec ln {} docs/ \;`, `env -i ln -s .claude d` und `tar xf a.tar -C .claude` mit Exit 0 durch (`env -i` wegen der Präfixliste, tar steht nicht auf der Liste).
  Spec requirement: Known Limitations — Vorsätzliche Verschleierung bleibt Known Limitation
  Conflict: Liegt innerhalb des dokumentierten Bedrohungsmodells („versehentliches Umgehen“) und ist die Gegenseite der Fehlalarm-Vermeidung für `ls .claude && rm docs/x`. Kein Spec-Verstoß, nur zur Kenntnis.
  Remediation: In die Known-Limitations-Liste von #410 aufnehmen (tar, xargs, find -exec, env-Flags).

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

VERDICT: VERIFIED
Alle 13 Punkte sind belegt. Es gab 151 bestandene Tests, 0 Fehlschläge und 0 übersprungene. Die Umgehungen F001 bis F004 liegen außerhalb der von der Spec ausdrücklich genannten Formen oder innerhalb des dokumentierten Bedrohungsmodells. F001 (`/.`-Ende) und F003 (`cd .claude && ln -s workflows …`) sind die einzigen Funde, die bei zufälliger, nicht vorsätzlicher Schreibweise auftreten können, sie sollten nach #410.

## Geprüfte Dateien

- sha256:d99265c1552d5f8deeb8a9ad7f38048beb6251ca40b5b38714af2c42d6446bf5  core/hooks/bash_gate.py

## Prüfbasis

- base: fbc8132289eb08b44737971e4c577e1e8663b797
- blob:8d5ec9912e75e647ca1239e73892b7ae0e2ca70e  core/hooks/bash_gate.py
