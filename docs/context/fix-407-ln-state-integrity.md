# Context: fix-407-ln-state-integrity

## Request Summary
`bash_gate` Prüfung 3b (State-Integrity) erkennt Schreibzugriffe nur an einer festen Liste von
Schreibbefehlen. `ln`/`link` fehlen. Über einen zweiten Namen (Verweis) lässt sich eine geschützte
Datei an einem unverdächtigen Pfad beschreiben (Issue #407, DoD: `ln .claude/workflows/<wf>.json <x>`
wird blockiert, mit Test).

## Reproduktion (2026-10-09, Stand dieses Arbeitsbaums = origin/main + #345)
Echter Gate-Subprozess `core/hooks/bash_gate.py`, Workflow aktiv. Skripte im Scratchpad
(`repro407.py`, `repro407b.py`).

| Befehl | Exit | Erwartet |
|---|---|---|
| `ln .claude/workflows/<wf>.json docs/x/notes.txt` | 0 | 2 |
| `ln -f …`, `ln -s …`, `link …` (gleiche Argumente) | 0 | 2 |
| `ln docs/x/notes.txt .claude/workflows/<wf>.json` (geschützt als Ziel) | 0 | 2 |
| `ln .claude/user_override_token.json …`, `ln .claude/settings.json …` | 0 | 2 |
| `ln -s ../core/hooks/x.py .claude/hooks/x.py` | 0 | 2 |
| `cp .claude/workflows/<wf>.json docs/x/notes.txt` (Vergleich) | **2** | 2 |
| `ln -s docs/a docs/b` (harmlos) | 0 | 0 |

**Über das Issue hinaus gefunden:**

| Befehl | Exit | Bemerkung |
|---|---|---|
| `ln -s .claude/workflows docs/w` danach `echo x > docs/w/<wf>.json` | 0 / 0 | **Verzeichnis-Verweis**: Kein Argument passt auf `PROTECTED_FILE_PATTERNS` (die verlangen `…/<name>.json`). Ein reiner `ln`-Indikator schließt das NICHT. |
| `ln -s .claude docs/c` | 0 | dito, ganze `.claude` |
| `echo x > .claude/config.yaml`, `sed -i … .claude/config.yaml` | 0 | `config.yaml` steht gar nicht in `PROTECTED_FILE_PATTERNS` — der Hardlink-Hinweis im Issue ist dafür gegenstandslos, direktes Schreiben geht schon. Eigenes Thema (Kill-Switches), nicht #407. |
| `ln/cp .claude/workflows/fix* docs/x/` | 0 / 0 | Glob ohne `.json`-Endung umgeht das Pfadmuster — allgemeine Schwäche, betrifft `cp` genauso. Eigenes Thema. |

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/bash_gate.py:56-63` | `PROTECTED_FILE_PATTERNS` (Datei-Muster, keine Verzeichnisse) |
| `core/hooks/bash_gate.py:100-107` | `WRITE_INDICATORS` — hier fehlt `ln`/`link` |
| `core/hooks/bash_gate.py:415` | `_has_write_indicator` |
| `core/hooks/bash_gate.py:243-345` | `_protected_outside_whitelist`, `_cd_into_claude`, `_cd_context_protected`, `_references_protected` (Token-Analyse, Freitext-Ausnahme #53/#64) |
| `core/hooks/bash_gate.py:947-958` | Prüfung 3b im Hauptablauf |
| `core/hooks/workflow.py:313-331` | `_atomic_write` (tempfile + rename) / `_read_workflow` (kein nlink-Check) |
| `core/hooks/qa_gate.py:544` | #345: `st_nlink != 1` → Abbruch (nur für das eigene Artefakt) |
| `tests/test_bash_gate_erkennung_299*.py` | Testmuster: echter Gate-Subprozess gegen Sandbox, beide Fehlerrichtungen, `_expect`/`_sandbox`/`_assert_allowed` |
| `tests/test_bash_gate_false_positives.py` | Freitext-/Lese-Befehle, die NICHT blocken dürfen |
| `CHANGELOG.md` | Eintrag unter [Unreleased] |

## Existing Patterns
- Neue Schreibbefehle werden als Regex mit Wortgrenze in `WRITE_INDICATORS` ergänzt (`\bunlink\b`, `\btruncate\b`, #64 Wortgrenze gegen Freitext-Treffer).
- Pfaderkennung ist tokenbasiert mit Freitext-Flag-Ausnahme; `sh -c`/`eval`/Parse-Fehler → Roh-Scan (fail-closed).
- Verzeichnis-Sonderfall gibt es schon: `_cd_into_claude` behandelt `.claude` und `.claude/workflows` als Zustandsordner, `.claude/worktrees/…` und `.claude/hooks` bewusst nicht (sonst blockt jede Worktree-Arbeit).
- Tests: Teil-A/B/C-Dateien zu #299 — echte Subprozesse, Abweichungen gesammelt.

## Dependencies
- Upstream: `hook_utils` (`strip_heredoc_bodies`, `_git_segments`/`_git_lex`, Freitext-Flags), `framework_disabled()`.
- Downstream: Jede Bash-Ausführung in jedem Konsumentenprojekt (Kern-Gate). Jeder Leser des Workflow-State (`workflow.py`, `edit_gate`, `phase_listener`, `tdd_enforcement`, `post_implementation_gate`, `session_singleton_guard`, `hook_utils`, `bash_gate`) — relevant für die Alternative „nlink beim Lesen“.

## Existing Specs
- `docs/specs/fix-299-bash-gate-erkennung.md`, `…-teil-c.md` — Struktur der 3b-Erkennung
- `docs/specs/feat-345-qa-gate-selbst-ausfuehren.md` — nlink-Absicherung des eigenen Artefakts

## Lösungswege (für /20-analyse)
1. **`ln`/`link` als Schreibindikator** (Issue-Vorschlag): kleinste Änderung; deckt Datei-Verweise in beide Richtungen ab, nicht aber Verzeichnis-Verweise (`ln -s .claude/workflows docs/w`).
2. **`ln`/`link` mit einem Argument unter `.claude`, `.claude/workflows`, `.claude/hooks` oder einem geschützten Muster → blocken** (eigene Segmentprüfung, analog `_cd_into_claude`): schließt auch Verzeichnis-Verweise; `.claude/worktrees/…` bleibt frei.
3. **nlink/Symlink-Prüfung beim Lesen des Zustands** (Issue-Alternative): fail-closed an der Quelle, wirkt unabhängig vom Befehl. Aber: viele Leser (≥8 Dateien) → sprengt das Limit; schützt nur Workflow-JSON, nicht `settings.json`/Hooks/Token; ein Verzeichnis-Verweis erzeugt kein nlink>1 (Datei hat weiter einen Namen). `_atomic_write` zerreißt einen Hardlink beim nächsten Schreiben ohnehin, das Fenster bis dahin bleibt.

## Risks & Considerations
- False Positives: Im Framework selbst gibt es keine `ln`-Aufrufe in Commands/Agents/Skripten (grep leer). Worktree-Setups verlinken z.B. `node_modules` (#293) — Pfade unter `.claude/worktrees/` dürfen nicht blocken.
- `\bln\b` als reiner Regex träfe Freitext („ln“ in Texten, `-ln`-Flags wie `ls -ln`?) — nur greifen, wenn auch ein geschützter Pfad im selben Segment steht (wie alle Indikatoren) bzw. tokenbasiert auf das Kommandowort prüfen.
- Glob- und `config.yaml`-Lücke sind eigene Ziele → gebündelt in **#410** (mit Teil 3 „Prüfung an der Quelle“), nicht Teil dieses Workflows.

## Analysis

### Type
Bug (Sicherheitslücke im Kern-Gate, nie funktioniert — kein Regressionsfall: `ln` stand nie in `WRITE_INDICATORS`)

### Zusätzliche Reproduktion (2026-10-09, `repro407c.py`, echter Gate-Subprozess, Workflow aktiv)
| Befehl | Exit | Erwartet |
|---|---|---|
| `mv .claude/workflows docs/w` | 0 | 2 |
| `cp -r .claude/workflows docs/w` / `cp -r docs/w .claude/workflows` | 0 / 0 | 2 / 2 |
| `rsync -a docs/w/ .claude/workflows/` | 0 | 2 |
| `install docs/x .claude/workflows/<wf>.json` | 0 | 2 |
| `ls -ln <state>`, `cat <state>` | 0 | 0 |

Ursache doppelt: (a) `ln`, `link`, `install`, `rsync` fehlen in `WRITE_INDICATORS` (`bash_gate.py:100`); (b) `PROTECTED_FILE_PATTERNS` (`:56`) verlangen Dateinamen, ein Ordner-Token `.claude` / `.claude/workflows` passt nie — daher greifen selbst `mv`/`cp` nicht, wenn der ganze Ordner bewegt wird.

### Recherche
- Pfadbasierte Prüfungen können Verweise grundsätzlich nicht vollständig erfassen; robust nur fd-basiert bzw. `st_nlink`-Prüfung an der Quelle, und auch die erkennt Verzeichnis-Symlinks nicht ([CERT POS01-C](https://wiki.sei.cmu.edu/confluence/spaces/c/pages/87152372/POS01-C.+Check+for+the+existence+of+links+when+dealing+with+files), [POSIX hardlink heartache](https://michael.orlitzky.com/articles/posix_hardlink_heartache.xhtml)).
- Claude Code selbst: Hooks sind werkzeugbezogen, Schutz muss handlungsbezogen sein ([anthropics/claude-code#29709](https://github.com/anthropics/claude-code/issues/29709)) — bestätigt den Ansatz, die Bash-Erkennung zu verbreitern.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | `\bln\b`, `\blink\b`, `install` (als Kommandowort), `\brsync\b` in `WRITE_INDICATORS`; neue Liste `PROTECTED_DIR_TOKEN_PATTERNS` (Ordner-Token `.claude`, `.claude/workflows`, Slash am Ende erlaubt, `./` und absolut; NICHT `.claude/worktrees/…`, NICHT `.claude/hooks`) — nur in 3b über `_protected_outside_whitelist`/`_references_protected` |
| `tests/test_bash_gate_ln_state_407.py` | CREATE | Echter Gate-Subprozess, beide Fehlerrichtungen (Muster aus `test_bash_gate_erkennung_299*.py`: `_sandbox`/`_expect`) |
| `CHANGELOG.md` | MODIFY | Eintrag unter [Unreleased] |

### Scope Assessment
- Files: 3
- Estimated LoC: ~+190/-2 (Gate ~30, Test ~150, Changelog ~5)
- Risk Level: MEDIUM — Kern-Gate läuft bei jedem Bash-Aufruf in jedem Konsumentenprojekt; neue Blocks nur bei aktivem Workflow und nur mit geschütztem Pfad im selben Segment.

### Technical Approach (Empfehlung, Weg B)
1. Indikatoren ergänzen, aber **nicht** als `\bln\b`: belegt (2026-10-09, `re.search(r'\bln\b', 'ls -ln docs/x.txt')` → `True`), dass `\bln\b` auch das Flag `ls -ln` trifft (`-` ist Nicht-Wortzeichen) — `ls -ln <state>` würde fälschlich blocken. Die Plan-Bewertung lag hier falsch. Daher `ln`/`link`/`install`/`rsync` als **Kommandowort** erkennen (Segmentanfang bzw. nach `;`, `&&`, `|`, `(`, `sudo`/`env` o. ä., nie mit führendem `-`). `install` so auch nicht bei `pip install`/`npm install`.
2. Ordner-Muster mit Lookahead statt `$`, damit es im Token-Pfad (`re.search` pro Token, `_matches_file_token`) UND im Roh-Scan-Fallback (`sh -c`/`eval`/shlex-Fehler, ganzer String) wirkt: `(?<![\w.-])(?:\./)?(?:[^\s'"]*/)?\.claude(?:/workflows)?/*(?=[\s"';&|)]|$)`.
3. Nicht berührt: `_redirects_to_protected` (eigene Liste), Secrets-Pfade, `_cd_context_protected`.
4. Gegenproben im Test: `ls -ln <state>`, `cat <state>`, `ln -s docs/a docs/b`, `ln -s … .claude/worktrees/x/node_modules`, Freitext in `-m`/`--body`, `pip install x`.

### Alternativen
- **A (Issue-Vorschlag, nur `ln`/`link`):** 2 Zeilen; schließt Datei-Verweise, lässt Ordner-Verweise und `mv`/`cp -r` des Ordners offen. Erfüllt die DoD von #407 wörtlich, aber nicht ihr Ziel.
- **C (nlink/Symlink-Prüfung beim Lesen des Zustands):** wirkt unabhängig von der Befehlsform (auch `python -c os.link`), aber ≥8 Leser-Dateien (sprengt Limit), schützt nur Workflow-JSON, und Ordner-Symlinks erzeugen kein nlink>1. Als Ergänzung in #410 Teil 3 geführt, nicht als Ersatz.
- Kippt keine ADR; erweitert die #299-Struktur von 3b.

### Dependencies
- `hook_utils` (`_git_segments`, `_git_lex`, Freitext-Flags), `_matches_file_token`/`_is_sensitive`.
- Bestandstests `tests/test_bash_gate*.py` komplett laufen lassen (erkennung_299 A/B/C, false_positives, freetext_64_75, env_aliase_324).

### Restrisiko (bewusst)
- `cp -r ~/.claude backup` / `rsync ~/.claude/ x` blockt bei aktivem Workflow (Home-Ordner textlich nicht unterscheidbar). Selten, nur im Workflow, akzeptiert — in der Spec benennen.
- `.claude/hooks` als Ordner bleibt offen (konsistent mit `_cd_into_claude`), einzelne `.py` sind geschützt.

### Open Questions
- keine PO-Frage offen; Umfang B statt A ist technische Entscheidung (Ziel des Issues statt Wortlaut).
