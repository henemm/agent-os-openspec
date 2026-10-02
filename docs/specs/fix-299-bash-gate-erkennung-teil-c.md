---
entity_id: fix-299-bash-gate-erkennung-teil-c
type: bugfix
created: 2026-10-02
updated: 2026-10-02
status: draft
version: "1.0"
tags: [bash-gate, state-integrity, kommentar, umleitung, cd-kontext, teil-c]
test_targets: ["tests/test_bash_gate_erkennung_299_teil_c.py"]
---

# bash_gate: Restlücken der State-Integrity-Prüfung — Teil C von #299

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #299 (Sammel-Vorgang, Epic #200), Teil C. Enthält die vorbestehenden Umgehungen der State-Integrity-Prüfung (3b) aus #316 sowie die Kommentar-Apostroph-Lücke aus #319 (beide als Issues in #299 zusammengeführt). Die zwei übrigen Restposten sind eigene Issues: Env-Aliase #324, CI-Gate für den Adversary-Nachweis #325 — **nicht** Teil dieser Spec.

## Purpose

`bash_gate.py` schützt die Workflow-Dateien (`.claude/workflows/*.json`, Freigabe-Marker) vor direktem Schreiben per Bash. Teil A und B haben die Commit-Erkennung gehärtet; drei Schreibweisen umgehen den Schutz der Zustandsdateien aber weiterhin, ohne dass dafür Absicht nötig wäre: ein `cd` in den Workflow-Ordner mit anschließendem Schreiben auf den bloßen Dateinamen, eine Umleitung (`>`) auf eine geschützte Datei hinter einem erlaubten Befehl wie `git status`, und ein Apostroph in einem `#`-Kommentar (`# don't`), der die Zerlegung des Befehls kippen lässt und damit die gesamte Whitelist-Prüfung aushebelt. Diese Spec schließt genau diese drei Lücken mit Regeln (Token-Scan, Kommentar-Scanner), ohne Modell, ohne neuen Subprozess, ohne Abhängigkeit.

## Source

- **File:** `core/hooks/bash_gate.py` — `main()` Schritt 3b, `_protected_outside_whitelist`, `_references_protected`, `_has_real_redirect`, `PROTECTED_FILE_PATTERNS`
- **File:** `core/hooks/hook_utils.py` — `_git_lex`, `_git_segments`
- **Analyse:** `docs/context/fix-299-teil-c.md`, Abschnitt „Analysis“ (Reproduktion von 21 Fällen am echten Gate, Ursachen, Alternativen)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/hook_utils.py::_git_lex` | Funktion | Zerlegung für alle Gate-Prüfungen (3a, 3b, Commit-Erkennung, `git_subcommands`); Änderung wirkt auf alle |
| `core/hooks/bash_gate.py` | Modul | Kern-Gate Bash, Schritt 3b |
| `tests/test_bash_gate_erkennung_299.py`, `…_teil_b.py` | Test | Sandbox-Muster (Subprozess gegen echtes Gate, Wegwerf-Repo, Workflow phase6) |
| `tests/test_bash_gate_false_positives.py`, `tests/test_bash_gate_freetext_fixes_64_75.py` | Test | Regressionsschutz gegen Über-Blockierung und Freitext |
| Bash-Handbuch „Comments“ | extern | `#` beginnt nur am Wortanfang einen Kommentar (nicht in Quotes, nicht in `a#b`, `$#`, `${#x}`) |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | `_strip_shell_comments(command)`: entfernt Kommentare (Wortanfangs-`#`, quote-/escape-bewusst); `_git_lex` ruft ihn vor der Zerlegung |
| `core/hooks/bash_gate.py` | MODIFY | 3b: (1) cd-Kontext, (2) Umleitungsziele aller Segmente gegen `PROTECTED_FILE_PATTERNS` und Marker-Muster |
| `tests/test_bash_gate_erkennung_299_teil_c.py` | CREATE | Subprozess-Tests gegen das echte Gate, beide Fehlerrichtungen |
| `CHANGELOG.md` | MODIFY | `[Unreleased]` |

### Estimated Changes

- Files: 4
- LoC: ca. +200 (Produktivcode ca. 90, Tests ca. 110). Spec/Kontext/Briefing zählen im LoC-Gate zusätzlich (#294). `core/hooks/` ist Infrastruktur: mit laufendem Workflow ab phase6 entfällt der Override (#322).

## Implementation Details

**1. Kommentare (`hook_utils._strip_shell_comments`, #319).** `_git_lex` setzt `commenters = ""`, damit `git log --grep=#1431` nicht abgeschnitten wird. Folge: Ein Apostroph in einem Kommentar (`git status && sed -i … <state> # don't`) bleibt für `shlex` ein offenes Quote, `_git_lex` liefert `None`, `_git_segments` ebenfalls, und `_is_whitelisted` fällt auf „irgendein Treffer“ zurück — das `sed` wird nicht mehr als fremdes Segment gesehen. Neu: ein kleiner Zeichen-Scanner entfernt vor der Zerlegung jeden Kommentar. Ein `#` beginnt einen Kommentar nur, wenn es (a) außerhalb von `'…'`, `"…"` und `$'…'` steht, (b) nicht durch `\` maskiert ist und (c) am Wortanfang steht, also am Textanfang oder direkt nach Leerraum, Zeilenumbruch oder einem der Zeichen `; & | ( )`. Der Kommentar reicht bis zum Zeilenende; der Zeilenumbruch bleibt erhalten (er trennt Befehle). Nicht kommentar sind damit `a#b`, `$#`, `${#x}`, `--grep=#1431`, `-m "x # y"`. Sind die Quotes im Befehl unausgewogen (Scanner endet innerhalb eines Quotes), wird der Befehl **unverändert** zurückgegeben — Verhalten wie heute (fail-open, Drei-Fälle-Regel). Der Scanner ersetzt die Whitelist-Logik nicht, er stellt nur her, dass der Lexer nicht mehr an Kommentartext scheitert.

**2. Umleitungsziele (`bash_gate`, 3b).** `_protected_outside_whitelist` zählt nur Segmente, die selbst nicht whitelisted sind. Steht der geschützte Pfad ausschließlich als **Ziel einer Umleitung** hinter einem whitelisted Segment (`git status > <state>`, `workflow.py status > <state>`, `git status > .claude/user_approved_validation_x`), erkennt 3b ihn nicht. Neu: Zusätzlich prüft 3b im Token-Strom jedes Segments (auch whitelisted), ob auf einen Ausgabe-Umleitungsoperator (`>`, `>>`, `N>`, `N>>`, `&>`, `&>>`, `>|`; nicht `>&N` und nicht `/dev/null`) ein Ziel folgt, das auf `PROTECTED_FILE_PATTERNS` oder ein Marker-Namensmuster passt. Ein solches Ziel blockt mit der bestehenden 3b-Meldung — ein Schreib-Indikator ist durch die Umleitung selbst gegeben. `git log > out.txt`, `git status 2>&1`, `git status | tee out.txt` bleiben frei.

**3. cd-Kontext (`bash_gate`, 3b).** `cd .claude/workflows && echo x > <wf>.json` umgeht das Schutzmuster, weil `PROTECTED_FILE_PATTERNS` Ordner und `.json`-Name in einem Token verlangt. Neu: Enthält der Befehl ein `cd`/`pushd` mit einem Ziel, dessen Pfadkomponenten `.claude` enthalten, so gelten danach alle `.json`-Token (und Marker-Namen) desselben Befehls als geschützt; zusammen mit einem Schreib-Indikator blockt 3b. Der Roh-Scan auf den Indikator bleibt bewusst (damit auch `python3 -c "open('x.json','w')"` fällt). `cd .claude/workflows` allein, `cd .claude/workflows && ls` und `cd .claude/workflows && cat <wf>.json` bleiben frei. Nicht zerlegbare Befehle: fail-open wie bisher.

**Alternativen (Regelweg vorn; Details in der Analyse):**

- **Gewählt: Regeln im bestehenden Gate.** Kein Modell nötig: Shell-Tokenisierung ist deterministisch, die Nulllinie ist die Regel.
- **A: Zustand statt Text prüfen** (State-Dateien vor/nach dem Befehl hashen): würde #316 als Klasse schließen, braucht aber einen Beglaubigungsweg, weil `workflow.py phase` den State legitim ändert (≫ 250 LoC) und erkennt erst nach der Tat. Verworfen für jetzt; gekippt würde die ADR „Gate prüft Befehlstext“.
- **B: Lücken als Known Limitation belassen:** für 3b vertretbar (Absicht nötig), nicht für #319 (`don't` im Kommentar passiert unabsichtlich und hebt die Whitelist-Prüfung auf).
- **C: Rückfall bei unzerlegbarem Befehl auf „nicht whitelisted“ drehen:** einfacher, blockt aber jeden harmlosen Befehl mit unbalancierten Quotes — verletzt die Drei-Fälle-Regel (fail-open). Verworfen.

## Expected Behavior

- **Input:** Ein Bash-Befehl durch `bash_gate.py`, Projekt mit aktivem Workflow in phase6.
- **Output:** Die drei Umgehungen oben enden mit Exit 2 und der Meldung „Direct state file manipulation“. Alle Kontrollfälle laufen weiter mit Exit 0.
- **Side effects:** Keine neuen Subprozesse. Kommentare werden nur für die Zerlegung entfernt, der Befehl selbst läuft unverändert.

| Befehl | Heute | Soll |
|--------|-------|------|
| `cd .claude/workflows && echo x > <wf>.json` (auch `sed -i`, `python3 -c "open(…,'w')"`) | 0 | 2 |
| `git status > <state>`, `workflow.py status > <state>`, `git status > <marker>` | 0 | 2 |
| `git status && sed -i … <state> # don't` | 0 | 2 |
| `cd .claude/workflows`, `cd .claude/workflows && ls`, `cd .claude/workflows && cat <wf>.json` | 0 | 0 |
| `git log > out.txt`, `git status 2>&1`, `git status \| tee out.txt` | 0 | 0 |
| `git status # don't panic`, `git log --grep='#1431'`, `echo "it's" > out.txt` | 0 | 0 |

## Known Limitations

- **Bedrohungsmodell unverändert:** Verhindert wird das **versehentliche** Umgehen. Vorsätzliche Verschleierung (`eval`, Wrapper-Skripte, Variablen im Pfad, Here-Strings) bleibt Known Limitation; Backstop ist der Phase-8-Übergang.
- **Nicht Teil dieser Spec:** Env-Aliase über `GIT_CONFIG_COUNT`/`--config-env`/`GIT_CONFIG_PARAMETERS` im Befehl (#324) und das CI-Gate für den Adversary-Nachweis (#325).
- **Kommentar-Scanner ist bewusst konservativ:** Bei unausgewogenen Quotes oder Sonderformen (`$(…)` mit Kommentar im Inneren, Heredoc-Körper) bleibt der Befehl unverändert; dort gilt das heutige Verhalten.
- **cd-Kontext ist textbasiert:** Ein `cd` über Variable (`cd "$D"`) oder `cd -` wird nicht aufgelöst.
- **Verteilung:** wirkt in Konsumenten-Projekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Die drei Umgehungen (cd-Kontext, Umleitung hinter erlaubtem Befehl, Apostroph im Kommentar) werden am echten Gate mit Exit 2 abgewiesen, und die Kontrollfälle laufen weiter durch
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, insbesondere False-Positive-, Freitext- sowie Teil-A/B-Tests)

## Acceptance Criteria

- **AC-1:** Given ein aktiver Workflow in phase6 / When ein Befehl per `cd .claude/workflows` (oder `pushd`) in den Workflow-Ordner wechselt und danach mit Schreib-Indikator (`>`, `sed -i`, `python3 -c "open(…,'w')"`) auf einen bloßen `.json`-Namen schreibt / Then blockt das Gate mit Exit 2
  - Test: `tests/test_bash_gate_erkennung_299_teil_c.py::test_cd_in_state_ordner_dann_schreiben_blockt`
- **AC-2:** Given ein aktiver Workflow in phase6 / When ein erlaubter Befehl (`git status`, `workflow.py status`) seine Ausgabe per `>` oder `>>` auf eine State-Datei oder einen Freigabe-Marker umleitet / Then blockt das Gate mit Exit 2
  - Test: `tests/test_bash_gate_erkennung_299_teil_c.py::test_umleitung_hinter_erlaubtem_befehl_auf_state_blockt`
- **AC-3:** Given ein aktiver Workflow in phase6 / When `git status && sed -i … <state>` mit einem Kommentar `# don't` endet / Then blockt das Gate mit Exit 2 (genau wie mit `# dont`)
  - Test: `tests/test_bash_gate_erkennung_299_teil_c.py::test_apostroph_im_kommentar_hebt_schutz_nicht_auf`
- **AC-4:** Given ein aktiver Workflow in phase6 / When `cd .claude/workflows`, `cd .claude/workflows && ls`, `cd .claude/workflows && cat <wf>.json`, `git log > out.txt`, `git status 2>&1` oder `git status | tee out.txt` läuft / Then lässt das Gate sie mit Exit 0 durch
  - Test: `tests/test_bash_gate_erkennung_299_teil_c.py::test_harmlose_kontrollfaelle_bleiben_frei`
- **AC-5:** Given ein aktiver Workflow in phase6 / When ein `#` kein Kommentar ist (`git log --grep='#1431'`, `echo "it's" > out.txt`, `git status # don't panic`, `a#b`, `$#`) / Then bleibt das Verhalten unverändert (Exit 0, keine Fehlalarme) und `_strip_shell_comments` entfernt nur echte Kommentare
  - Test: `tests/test_bash_gate_erkennung_299_teil_c.py::test_hash_ohne_kommentar_bleibt_unveraendert`
- **AC-6:** Given unausgewogene Quotes im Befehl / When `_strip_shell_comments` aufgerufen wird / Then kommt der Befehl unverändert zurück (fail-open)
  - Test: `tests/test_bash_gate_erkennung_299_teil_c.py::test_unausgewogene_quotes_bleiben_unveraendert`
- **AC-7:** Given der bestehende Testbestand / When die Regressionstests laufen / Then bleiben sie grün
  - Test: `tests/test_bash_gate_false_positives.py`, `tests/test_bash_gate_freetext_fixes_64_75.py`, `tests/test_bash_gate_erkennung_299.py`, `tests/test_bash_gate_erkennung_299_teil_b.py` (unverändert, Lauf grün)

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_bash_gate_erkennung_299_teil_c.py` (AC-1 bis AC-6; Subprozess gegen das echte Gate im Wegwerf-Repo, beide Fehlerrichtungen)
- Regressionslauf: `pytest tests/test_bash_gate_false_positives.py tests/test_bash_gate_freetext_fixes_64_75.py tests/test_bash_gate_erkennung_299.py tests/test_bash_gate_erkennung_299_teil_b.py` (AC-7), danach die Vollsuite

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Schließt Erkennungslücken innerhalb der bestehenden Entscheidung „Gate prüft Befehlstext per Regeln“; kein neues Muster, keine neue Abhängigkeit. Die Alternative „Zustand statt Text prüfen“ (A) ist bewertet und bewusst auf später verschoben, sie würde diese ADR kippen.

## Changelog

- 2026-10-02: Initial spec created (Teil C von #299)
