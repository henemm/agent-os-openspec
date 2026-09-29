# Context: fix-259-adversary-diff-binding

## Request Summary

Issue #259 (Folge zu #253 / PR #255, Befunde F001–F004): Commit-Gate und Phase 8 akzeptieren ein
gültiges, gestempeltes Dialog-Artefakt, ohne zu prüfen, ob es die Änderung abdeckt, die übernommen
werden soll. Ziel: Ein Nachweis zählt nur, wenn jede geänderte Code-Datei im Protokoll per
`Code reference:` zitiert und im Block `## Geprüfte Dateien` gehasht ist (Commit: gestagte Dateien,
Phase 8: Diff gegen eine Basis), und registrierte Artefakt-Pfade liegen innerhalb von Projekt oder
Worktree. F003 (Textkopplung per Substring) und F004 (Namens-Fallback) laufen im selben Zug mit.

## Reproduktion F001 (2026-09-27, gegen `db346fa` = `main`)

Wegwerf-Git-Repo mit Initial-Commit, kein Remote (Rebase-Check 5b überspringt still), echte
Hook-Skripte aus `core/hooks/`. Workflow A hat ein echtes, gestempeltes Protokoll, das nur
`src_A/module_a.py` zitiert. Workflow B (`feature`, `phase6_implement`, Verdict `VERIFIED`)
registriert dieses fremde Protokoll per `workflow.py add-artifact adversary_dialog
docs/artifacts/A/adversary-dialog.md …` und staged `src/module_b.py`:

```
1 Datei(en) gehasht und in docs/artifacts/A/adversary-dialog.md gespeichert.
Artifact added to B: adversary_dialog (fremdes Protokoll)
--- staged:
src/module_b.py
E2E scope: backend
bash_gate (git commit) exit=0  (0 = Commit erlaubt)
Set phase to: phase8_complete
workflow.py phase phase8_complete exit=0
```

Commit und Phase 8 gehen durch, obwohl kein Adversary `src/module_b.py` gesehen hat.

## Root Cause

- `check_dialog_evidence(wf)` (`adversary_dialog.py:713`) sieht nur Workflow-State und Artefakt,
  keine Änderungsmenge.
- `bash_gate.py` berechnet `staged_list` (Z. 628–633) und reicht die Liste nur an 5a/5d weiter,
  nicht an 5c (`_require_dialog_evidence`, Z. 483).
- Der Phase-8-Übergang (`workflow.py:1005–1020`) hat keinerlei Diff-Bezug; `_new_workflow`
  (Z. 525) speichert keinen Start-Commit.
- Die Hash-Bindung aus #131 bindet nur die zitierten Dateien an ihren Ist-Stand, nicht den
  Umfang der Änderung. `find_dialog_artifact` nimmt jeden registrierten Pfad, auch fremde
  Workflow-Ordner und absolute Pfade außerhalb des Repos (`_resolve_artifact_path`, Z. 681–692).

## Related Files

| Datei | Relevanz |
|---|---|
| `core/hooks/adversary_dialog.py` | `validate_dialog_artifact_ex` (Z. 412–537, 3-Tupel = öffentliche API, von `qa_gate` entpackt); `_extract_examined_files` (545–560, Quelle: `Code reference:`); `_hash_root` (563–571, Worktree vor Hauptrepo); `_parse_examined_files_section` (587–604, letzter Block gewinnt); `_verify_examined_file_hashes` (605–628, vergleicht gegen den **Arbeitsbaum**); `stamp_dialog_artifact` (631–673); `DEFAULT_DIALOG_ARTIFACT` (678); `_resolve_artifact_path` (681–692, absolut = unverändert); `find_dialog_artifact` (695–710, F004: `wf.get("name", "")`); `check_dialog_evidence` (713–742, F003: `"AMBIGUOUS" in message` Z. 737; F004: Meldung nutzt `"<workflow>"` Z. 717) |
| `core/hooks/bash_gate.py` | `_measurement_root` (143–161, Worktree vor `_root`, #155); `_commit_content_files` (397–441: Index, `-a` → Arbeitsbaum gegen HEAD, `--amend` → gegen `HEAD~1`; heute nur informativ und fail-open); `_require_dialog_evidence` (483–512, Override-Token hebt den Block auf); `main` 5 (626–706): 5b Rebase-Pflicht gegen hartkodiertes `origin/main`, 5c nur in `phase6_implement`/`phase6b_adversary`/`phase7_validate`, `bug`/`feature-fast` ausgenommen |
| `core/hooks/workflow.py` | `_new_workflow` (525–544, kein Basis-Commit); `cmd_start` (1028–1082); `_validate_transition` (947–1022: `bug` → keine Prüfung, `feature-fast` → nur Spec-Gates, Rückwärts/gleiche Phase frei; Phase-8-Block 1005–1020, kein Override-Pfad); `cmd_add_artifact` (1283–1304, keine Pfadprüfung); `cmd_complete` (1380–1405, ruft `_validate_transition`, gilt auch für `finish`) |
| `core/hooks/qa_gate.py` | Z. 271 `if "AMBIGUOUS" in cl_message` — Zwilling von F003 |
| `core/hooks/edit_gate.py` | Heutige Definition von „Code“ für das Phasen-/TDD-Gate: `CODE_EXTENSIONS` (37–40), `ALWAYS_ALLOWED_DIRS` (42–45, u. a. `tests/`, `docs/`, `scripts/`, `tools/`, `.claude/commands/`), `ALWAYS_ALLOWED_PATTERNS` (47–51, `.md/.txt/.json/.yaml/.yml/.toml`, README/CHANGELOG/LICENSE); per `config.yaml` → `strict_code_gate` überschreibbar (431–433); Klassifikation inline in `main()` (475–494, Verzeichnis-Match komponentenweise) |
| `core/hooks/hook_utils.py` | `is_code_file` (680–688, hartkodierte Endungsliste ohne `.hpp`, ohne Config) — eine zweite Definition; `find_worktree_root`, `find_project_root` |
| `scripts/ci_spec_gate.py` | `_changed_files_from_git` (123–135: `git merge-base <base> HEAD`, dann `diff <ref>...HEAD`); `_is_exempt` (146–151: `docs/`, `tests/`, `.github/`, `.claude/`, `openspec/`, `.md/.txt/.lock`) — eine dritte, breitere Definition von „Code“ |
| `config.yaml` | `strict_code_gate` (85–127) |
| `core/commands/50-implement.md` | Step 8c (Z. 229–258): Protokoll-Pfad, `add-artifact`, `stamp`, Absatz „Gate-Wirkung (#253)“ |
| `core/commands/60-validate.md` | „Gate-Wirkung (#253)“ (98–102); Step 2b Auto-Fix (139–152); Step 3 docs-updater (155–167) |
| `core/agents/implementation-validator.md` | Step 3 „For each changed file“ (46); Pflicht-`Code reference` je Finding/Confirmation (74–97); Step 6 `stamp` (163–177) |
| `tests/test_adversary_evidence_gate_253.py` | Hermetische E2E-Fixtures über die echten Hooks: `_make_project` (**ohne Initial-Commit, kein HEAD**, Prüfling bleibt untracked), `_make_worktree`, `_dialog_text`/`_make_dialog` (zitiert `src/checked_module.py`), `_phase7_workflow`, `_commit_gate` |
| `tests/test_adversary_dialog_hash_binding_131.py` | Hash-Block-/`stamp`-Tests |

## Existing Patterns

1. **Eine Regel, zwei Gates (#253):** `check_dialog_evidence` ist die einzige Prüfung für
   Commit-Gate und Phase 8. Eine Abdeckungsprüfung gehört als Erweiterung dort hinein (z. B.
   zusätzlicher Parameter „geänderte Dateien“), nicht dupliziert in beide Aufrufer.
2. **Messen im Arbeitsbaum, State im Hauptrepo (#96/#144/#155):** `git diff` läuft in
   `_measurement_root()`; relative Pfade im Artefakt lösen gegen `_hash_root()` auf.
3. **Relative Pfade (#80/#96/#131):** zuerst Worktree-Root, sonst Projekt-Root; absolute Pfade
   bisher unverändert — genau das öffnet F002.
4. **Fail-closed (#253):** interne Fehler werden zur Grund-Meldung, nie zur Exception;
   fehlendes Modul = Nachweis nicht erbracht.
5. **Notausgänge:** Override-Token hebt den Commit-Block auf; Phase 8 kennt keinen Override,
   nur `abandon`. `bug`/`feature-fast` sind an beiden Stellen ausgenommen.
6. **Regeln wiederverwenden statt kopieren:** `ci_spec_gate.py` ruft
   `workflow.check_briefing_content` usw. auf.
7. **Last-wins:** zuletzt registriertes Artefakt, letzter Hash-Block, letztes Verdict.
8. **Selbsterklärende Gates (`docs/specs/selfexplaining-gates.md`):** Block-Meldungen nennen den
   Ausweg und hängen `gate_diagnostics(...)` an.

## Dependencies

- **Upstream:** git-CLI (`diff --cached`, `diff <ref>`, `ls-files --others --exclude-standard`,
  `merge-base`, `rev-parse`), `hook_utils` (Root-Auflösung), `config_loader`
  (`strict_code_gate`-Listen), `override_token`.
- **Downstream:** `bash_gate.py` 5c, `workflow.py` (`phase phase8_complete`, `complete`,
  `finish`), `qa_gate.py --checklist`, Befehle `/50-implement` und `/60-validate`, Agent
  `implementation-validator` (was er zitieren muss), `setup.py` (kopiert Hooks in
  Konsumenten-Projekte → jedes Konsumenten-Commit-Gate).

## Existing Specs

- `docs/specs/fix-253-adversary-evidence-gate.md` — direkter Vorgänger; Known Limitation 2
  verweist auf #259; Known Limitation 3 („Auto-Fix ändert zitierte Datei → Phase 8 blockt, gewollt“).
- `docs/specs/fix-131-adversary-dialog-hash-binding.md` — Hash-Block, `Code reference:` als Quelle.
- `docs/specs/selfexplaining-gates.md` — Meldungsformat.

## Empirischer Abgleich: Hätte die neue Regel echte Läufe blockiert?

Der Dialog aus #253 (`docs/artifacts/fix-253-adversary-evidence-gate/adversary-dialog.md`)
zitiert und hasht genau fünf Dateien: `adversary_dialog.py`, `bash_gate.py`, `post_bash.py`,
`qa_gate.py`, `workflow.py`. Der Commit `b7519f0` änderte zusätzlich Doku (`*.md`, `skills/`,
`docs/`), Tests (`tests/*.py`) **und `setup.py`** — dort nur Tabellentext in einem eingebetteten
Doku-String. Nach der `edit_gate`-Definition ist `setup.py` Code (`.py`, kein freigestellter
Ordner). Eine reine Dateityp-Regel hätte den #253-Commit also geblockt, bis der Adversary auch
`setup.py` zitiert. `db346fa` (#147) hätte sie nicht berührt (nur Doku, Skills, Tests).

## Risks & Considerations (offen für `/20-analyse`)

1. **Was ist „Code“?** Drei bestehende Definitionen (edit_gate konfigurierbar; `is_code_file`
   hartkodiert; ci_spec_gate breit). Kandidat: die `edit_gate`-Definition, in eine gemeinsame
   Funktion extrahiert — genau die Dateien, deren Bearbeitung schon Phase 6 + RED verlangte.
   Folgen: `tests/`, `scripts/`, `docs/` frei; `setup.py`-artige Dateien mit reinem Textinhalt
   sind Code (siehe Abgleich oben).
2. **Diff-Basis Phase 8:** Workflow-Start (neues State-Feld, alte Workflows ohne Feld) vs.
   `merge-base` mit einem Basis-Branch (hartkodiert `origin/main` wie 5b, oder konfigurierbar).
   Fallen: Die Rebase-Pflicht 5b erzwingt `git rebase origin/main` → ein gespeicherter
   Start-Commit zählte danach fremde Upstream-Änderungen mit; ein `merge-base` zählte frühere,
   noch nicht gemergte Workflows auf demselben Branch mit; Repos ohne Commit (Test-Fixtures!)
   oder ohne Remote.
3. **Arbeitsbaum zählt:** Auto-Fixes sind oft uncommittet → `git diff <basis>` plus untracked
   Dateien (`ls-files --others --exclude-standard`).
4. **Gelöschte Dateien** lassen sich weder zitieren noch hashen (`_verify_examined_file_hashes`
   meldet „nicht mehr lesbar“) → ausnehmen; Umbenennung → neuer Pfad zählt.
5. **Commit-Varianten:** `-a`, `--amend` (`_commit_content_files` wiederverwendbar, heute aber
   fail-open), `git commit <pfad>` (Pathspec, nicht im Index) → Phase 8 als Auffangnetz oder
   Known Limitation.
6. **Index ≠ Arbeitsbaum:** Die Hash-Prüfung vergleicht mit dem Arbeitsbaum; eine teilweise
   gestagte Datei könnte Inhalt committen, den der Adversary nie sah. Option: für gestagte
   Dateien den Blob-Hash (`git show :<pfad>`) prüfen — Scope-Frage.
7. **Auto-Fix in `/60-validate`:** Berührt er eine nicht zitierte Code-Datei, blockt Phase 8 bis
   zu einem neuen Dialog (konsistent mit #253 für zitierte Dateien). Alternative: Vereinigung
   mehrerer registrierter Protokolle — widerspricht dem Last-wins-Muster.
8. **Pfad-Normalisierung:** `Code reference:` kann `./src/x.py`, absolut oder
   worktree-relativ sein; git liefert repo-relative POSIX-Pfade.
9. **F002 Pfad-Einschränkung:** registriertes Artefakt muss (Symlinks aufgelöst) unter
   Projekt- oder Worktree-Root liegen; prüfen zur Gate-Zeit, optional schon bei `add-artifact`.
10. **F003:** strukturierter Rückgabewert statt Substring — ohne das 3-Tupel von
    `validate_dialog_artifact_ex` zu brechen (`qa_gate` entpackt es).
11. **F004:** leerer Name → kein Standardpfad, Meldung mit demselben Wert.
12. **Blast Radius:** Jedes Konsumenten-Commit-Gate in Phase 6–7 und jeder Abschluss. Ein
    falscher Treffer blockt alle Commits; Meldungen müssen die nicht abgedeckten Dateien und den
    Ausweg nennen (neuer Dialog / Override-Token / `abandon`).
13. **Bestandstests:** `_make_project` (#253) hat kein HEAD und lässt alles untracked; die
    Commit-Gate-Tests stagen nichts. Phase 8 muss „kein HEAD“ tragen (alles untracked = geändert).
14. **Fast Track** (`bug`, `feature-fast`) bleibt ausgenommen.

## Analysis

Quellen: 3× Explore (Haiku: betroffene Dateien und Tests, Spec-Landschaft, Dependency-Karte), 1× Plan (Sonnet: strategisches Gutachten). Strittige Aussagen der Agenten sind unten gegen Code und Git nachgeprüft (Stand `db346fa`).

### Type

**Bugfix:** Das Commit-Gate und Phase 8 lassen sich mit einem fremden Nachweis umgehen (F001, reproduziert). Der Workflow läuft trotzdem als `feature` im Full Process. Der Fast Track (`bug`) würde genau die Adversary-Prüfung überspringen, um die es hier geht.

### Nachgeprüfte Fakten (korrigieren die Agenten, wo nötig)

- **`hook_utils.is_code_file` hat keine Aufrufer.** Das ist toter Code, keine konkurrierende Definition. Er bleibt unangetastet.
- **`edit_gate.CODE_EXTENSIONS` enthält `.hpp`** und ist identisch mit `config.yaml` → `strict_code_gate`. Eine gegenteilige Aussage eines Explore-Agenten war falsch.
- **Pfadangaben beim Commit:** `git commit <neue-datei>` scheitert mit `pathspec … did not match any file(s) known to git`. Eine Datei kommt also nie ohne `git add` in einen Commit. Eine Commit-Menge nur aus versionierten Dateien ist vollständig.
- **Leeres `.git`-Verzeichnis:** Ein leeres `.git`-Verzeichnis, wie es 12 Testdateien per `(tmp_path / ".git").mkdir()` anlegen, meldet `git rev-parse` als `not a git repository`. Das ist dasselbe Ergebnis wie für einen Ordner ohne Git.
- **Repo ohne Commit:** Ein Repo ohne Commit liefert für `rev-parse --is-inside-work-tree` den Wert `true`, `rev-parse --verify -q HEAD` endet mit Exit 1.
- **Keine Registrierung nötig:** `setup.py:227` kopiert `core/hooks/*.py` per Glob. Ein neues Hilfsmodul muss nirgends registriert werden.
- **Basis-Branch:** Er existiert nur hartkodiert als `origin/main` in `bash_gate.py` 5b. Einen Config-Schlüssel dafür gibt es nicht. `ci_spec_gate.py` nimmt `--base` als CLI-Argument.
- **Zeilenlimit:** Das Scope-Gate (`edit_gate.py` S3) begrenzt standardmäßig auf 250 LoC Produktivcode und 500 LoC Tests (`config_loader.py:315/339`). Ein höheres Limit geht nur per `workflow.py set-field loc_limit_override <N>`.
- **Adversary-Limit:** Es ist reine Prompt-Konvention. `fix_loop_iterations` zählt nur `phase6b_adversary → phase6_implement`, und kein Hook prüft einen Grenzwert.

### Entscheidungen (Tech Lead, nach Best Practice; Gutachten eingearbeitet)

| # | Frage | Entscheidung | Begründung |
|---|---|---|---|
| E1 | Was ist „Code“? | Die `edit_gate`-Regeln (`CODE_EXTENSIONS`, `ALWAYS_ALLOWED_DIRS` komponentenweise, `ALWAYS_ALLOWED_PATTERNS`, überschreibbar per `strict_code_gate`) wandern in eine gemeinsame Funktion in `hook_utils`, die Config kommt als Parameter. `edit_gate` delegiert verhaltensgleich. **Reine Textänderungen in Code-Dateien zählen mit.** | Eine Definition für TDD-Gate und Nachweis-Gate verhindert Drift. „Nur Kommentar geändert“ ist ohne AST pro Sprache nicht verlässlich erkennbar, und eine solche Heuristik wäre die erste Umgehung. Folge: Ein Lauf wie #253 hätte `setup.py` zitieren müssen. |
| E2 | Änderungsmenge beim Commit | Normalfall: der Index. Bei `-a`, leerem Index oder Pfadangaben: Arbeitsbaum gegen HEAD. Bei `--amend`: gegen `HEAD~1`. Gelöschte Dateien fallen weg (`--diff-filter=d`), dann greift der E1-Filter. Ohne HEAD zählt nur der Index. | Die Menge ist bei Pfadangaben bewusst konservativ, also eine Obermenge. Untracked Dateien kommen nicht hinzu: `-a` übernimmt sie nicht, und git verweigert sie als Pfadangabe (nachgeprüft). |
| E3 | Diff-Basis für Phase 8 | Diff von der Basis zum Arbeitsbaum, dazu untracked Dateien (`--exclude-standard`). Gelöschte Dateien fallen weg, dann greift der E1-Filter. **Basis ist der neuere von zwei Kandidaten, jeweils nur wenn er Vorfahre von HEAD ist:** `merge-base(origin/main, HEAD)` oder das neue State-Feld `base_commit` (HEAD des Mess-Roots bei `workflow.py start`). Rückfall-Kette: einer der Kandidaten → nur HEAD (ungecommittet, degradiert, Hinweis in der Meldung) → ohne HEAD alle untracked Dateien → kein Git-Arbeitsbaum: Prüfung entfällt. Alle git-Aufrufe laufen im Mess-Root (Worktree vor Hauptrepo). | Die Rebase-Pflicht (5b) zieht Upstream-Änderungen herein: Ein alter Start-Commit zählte sie mit, `merge-base` nicht. Umgekehrt zählte `merge-base` frühere, noch nicht gemergte Workflows auf demselben Branch mit, ein jüngerer Start-Commit nicht. Geprüft wurden Rebase, Merge, mehrere Workflows auf einem Branch, kein Remote, kein HEAD und Detached HEAD. |
| E3a | Git-Fehler | **Fail-closed, sobald ein gültiger Git-Arbeitsbaum feststeht.** Scheitert dann ein Diff unerwartet, blocken Commit bzw. Phase 8 mit Grund. Nur strukturelles Fehlen degradiert: kein Remote, kein `base_commit`, kein HEAD, kein Repo. | Das entspricht der #253-Linie. Phase 8 hat keinen Override; eine still leere Menge wäre dort die teuerste Lücke. |
| E4 | Abdeckung | Jede Datei der Änderungsmenge steht im **letzten** `## Geprüfte Dateien`-Block, den es schon gibt und der an Hashes gebunden ist. Beide Seiten werden gegen `_hash_root()` normalisiert, also repo-relativ, als POSIX-Pfad, Worktree vor Hauptrepo, **nicht** über `_resolve_artifact_path`. `check_dialog_evidence(wf, changed_files=None)` bekommt die Menge vom Aufrufer. `None` bedeutet heutiges Verhalten. | Eine Regel, zwei Aufrufer (Muster #253). Nur gehashte Dateien sind nachweislich frisch geprüft. |
| E5 | Auto-Fix in `/60-validate` | Nur Doku, kein neuer Hook-Code. Step 2b darf ausschließlich Nicht-Code (nach E1) ändern. Braucht ein Validierungsfehler eine Code-Änderung, gilt er als **BROKEN-Pfad**: zurück zu Phase 6, gezielter Fix, eine weitere Adversary-Runde. Diese Runde verbraucht **dasselbe Kontingent** wie ein BROKEN-Verdict; ist es aufgebraucht, geht der Fall an den User. Das kommt als Klarstellung ins Adversary-Limit im `CLAUDE.md`. | Phase 8 erzwingt das technisch ohnehin: bei zitierten Dateien per Hash (#253), bei allen anderen per Abdeckung. Ohne die Klarstellung ließen sich mit immer neuen Validierungsgründen beliebig viele Runden rechtfertigen. |
| E6 | F002 | Zur Gate-Zeit prüfen: Der aufgelöste Artefakt-Pfad (realpath, Symlinks aufgelöst) muss unter Projekt- oder Worktree-Root liegen, sonst ist der Nachweis nicht erbracht. | Das ist sicherheitsrelevant. Die Frühwarnung bei `add-artifact` wäre nur UX und fällt deshalb weg. |
| E7 | F003 | Das Verdict wird strukturiert geparst (eigene Funktion). Das 3-Tupel von `validate_dialog_artifact_ex` bleibt unverändert. `check_dialog_evidence` und `qa_gate.py:271` vergleichen den geparsten Wert. | Heute ist das nicht ausnutzbar, weil die Templates fest sind; es geht um Robustheit. Der Aufwand ist gering. |
| E8 | F004 | Bei leerem Namen wird kein Standardpfad geprüft, und die Meldung nennt denselben Wert. | So steht es im Issue. |
| E9 | Kill-Switch und Migration | `config.yaml` → `adversary_coverage_gate.enabled: true`. Der Schalter umschließt **nur** E2, E3, E4 und E11, nicht #253 und nicht F002–F004. Release als MINOR mit Migrationshinweis im Stil von #253: Laufende Workflows brauchen einen neuen Dialog, der alle geänderten Code-Dateien zitiert. Beim Commit hilft der Override-Token, in Phase 8 der Kill-Switch oder `abandon`. | „Keine Breaking Changes ohne Migrationspfad“ (CLAUDE.md). Kill-Switches sind hier üblich: `po_briefing_gate`, `ci_spec_gate`. |
| E10 | Bedienbarkeit | Die Block-Meldung nennt die nicht abgedeckten Dateien (gekappt) und den Ausweg. Die neue CLI `adversary_dialog.py required-files` gibt die Phase-8-Menge aus. `implementation-validator` (Step 3 und 6) und `/50-implement` 8c verlangen, jede gelistete Datei zu zitieren. **Nicht** enthalten ist eine Warnung in `stamp`. | Nur mit der CLI weiß der Adversary vorher, was er zitieren muss; Code-Definition und Basis-Wahl lassen sich nicht erraten. Es ist dieselbe Funktion wie für Phase 8, also etwa 20 LoC. |
| E11 | Index ≠ Arbeitsbaum | Eine gestagte Code-Datei, die zusätzlich ungestagte Änderungen hat, blockt den Commit („teilweise gestagt“). Das gilt nur, wenn der Commit-Inhalt aus dem Index kommt, nicht bei `-a`. | Der geprüfte Hash gilt für den Arbeitsbaum. Ohne diese Prüfung könnte ein Inhalt committet werden, den kein Adversary gesehen hat. Das kostet etwa 10–15 LoC und würde nicht zum zweiten Mal verschoben. |
| E12 | Ausnahmen | Unverändert: `bug` und `feature-fast` sind an beiden Gates ausgenommen, das Commit-Gate prüft nur in den Phasen 6–7. | Der Code verzweigt dafür bereits früh (`bash_gate.py:673`, `workflow.py:950–969`). |

**Verworfen:**
- **Aufteilung entlang der Gate-Grenze** (erst Commit, später Phase 8), wie das Gutachten sie vorschlug: Ohne Phase 8 bliebe F001 offen. Man käme mit fremdem Protokoll durch Phase 8 und committete danach, denn nach Phase 8 prüft 5c nicht mehr.
- **Untracked Dateien in der Commit-Menge:** Git committet sie ohne `add` nicht, und bei `-a` würde das zu viel blockieren.
- **Heuristik „nur Text geändert“.**
- **Warnung in `stamp`** und **Frühwarnung bei `add-artifact`:** Beides ist reine UX. Nur bei Bedarf entsteht dafür ein Folge-Issue.

### Affected Files (with changes)

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | E1: gemeinsame Code-Klassifikation (Config als Parameter) |
| `core/hooks/edit_gate.py` | MODIFY | E1: Klassifikation delegieren. Verhaltensgleich; Beleg sind die bestehenden edit_gate-Tests, die grün bleiben müssen. |
| `core/hooks/adversary_dialog.py` | MODIFY | E4: Abdeckung in `check_dialog_evidence(wf, changed_files)` und Pfad-Normalisierung. E3: Phase-8-Menge mit Basis-Wahl. E6, E7, E8. E10: CLI `required-files`. |
| `core/hooks/bash_gate.py` | MODIFY | E2: Commit-Menge (ohne Löschungen, fail-closed im gültigen Arbeitsbaum). E11. Anbindung in 5c und Block-Meldung. |
| `core/hooks/workflow.py` | MODIFY | E3: `base_commit` in `_new_workflow`/`cmd_start` (Mess-Root). Anbindung im Phase-8-Block, gilt auch für `complete` und `finish`. |
| `core/hooks/qa_gate.py` | MODIFY | E7 (1–3 Zeilen) |
| `config.yaml` | MODIFY | E9: `adversary_coverage_gate.enabled` |
| `tests/test_adversary_coverage_gate_259.py` | CREATE | E2E über die echten Hook-Skripte. Enthält die F001-Reproduktion als RED-Test und die Basis-Matrix: Rebase, mehrere Workflows auf einem Branch, kein Remote, kein HEAD, Worktree, `complete`/`finish`. Dazu E3a, E6–E9 und E11. |
| `tests/test_adversary_evidence_gate_253.py` | MODIFY (evtl.) | Bleibt nach Gutachten grün, aber nur zufällig durch die Fixture (einzige untracked Code-Datei = zitierter Prüfling). Die Negativfälle kommen in die neue Datei. |
| `core/commands/50-implement.md` | MODIFY | 8c: `required-files` ausführen und jede gelistete Datei zitieren. Gate-Wirkung um #259 ergänzen. |
| `core/commands/60-validate.md` | MODIFY | Gate-Wirkung. Step 2b: nur Nicht-Code, Code-Fix läuft über den BROKEN-Pfad (E5). |
| `core/agents/implementation-validator.md` | MODIFY | Step 3 nutzt die `required-files`-Liste. Step 6 sagt, was zitiert sein muss. |
| `CLAUDE.md` | MODIFY | Hooks-Absatz im Adversary System. Adversary-Limit: Ein durch Validierung erzwungener Code-Fix zählt wie BROKEN. |
| `docs/WORKFLOW_GUIDE.md` | MODIFY | Z. 147/165/226: Gate-Beschreibung um die Abdeckung ergänzen |
| `core/commands/80-workflow.md`, `.claude/commands/80-workflow.md` | MODIFY (prüfen) | Hinweiszeile zu `--checklist` (#253), ggf. ergänzen. Wie die `.claude`-Kopie entsteht, klärt die Spec. |
| `skills/*/SKILL.md` | MODIFY (generiert) | `python3 scripts/sync_skills.py` |
| `CHANGELOG.md` | MODIFY | `[Unreleased]` mit Migrationshinweis (E9) |
| `docs/specs/fix-259-adversary-diff-binding.md` | CREATE | Phase 3 |

Laut Gutachten **nicht betroffen:**
- `tests/test_gate_fixes_26_38_34.py`: Die #34-Fixtures haben kein `.git`, bei #26 ist die Änderungsmenge leer.
- `tests/test_status_note_325.py`: Das sind reine Footer-Tests.
- `tests/test_workflow_finish_alias.py`: Typ `bug`.
- `tests/test_workflow_name_validation.py`: leeres `.git`, also kein Repo, die Prüfung entfällt. Die Assertions dort sind allerdings schwach.

Endgültig zeigt das der RED- bzw. GREEN-Lauf der vollen Suite.

### Scope Assessment

- **Dateien:** 7 Produktivdateien (davon `qa_gate.py` und `config.yaml` mit wenigen Zeilen), 1–2 Testdateien, 6–8 Doku-Dateien plus generierte Skills.
- **Estimated LoC:**
  - Produktiv etwa +300 bis +400 / −20
  - Tests etwa +500 bis +700
  - Doku etwa +80 bis +120
- **Budget:** Das übersteigt das Standard-Limit von 250 LoC Produktivcode. Die Spec legt deshalb ein begründetes Budget fest (`loc_limit_override`, etwa 450). Die Ursache ist die Basis-Logik aus E3, keine Aufblähung. Eine Aufteilung ist verworfen (siehe oben).
- **Risk Level: HIGH.** Die Änderung trifft jedes Konsumenten-Commit-Gate in den Phasen 6–7 und jeden Abschluss eines Workflows außerhalb des Fast Track. Phase 8 hat keinen Override. Ein Fehler in der Basis-Wahl blockiert also, bis Kill-Switch oder `abandon` greifen.
- **Gegenmittel:**
  - Kill-Switch (E9)
  - fail-closed erst im nachweislich gültigen Arbeitsbaum (E3a)
  - Meldungen mit Dateiliste und Ausweg, dazu `required-files` (E10)
  - E2E-Matrix über die echten Hooks
  - E1 als eigener, verhaltensgleicher erster Schritt

### Technical Approach

Die Reihenfolge ist für Phase 6 so festgelegt:
1. F002–F004 (E6–E8). Klein und unabhängig.
2. E1 extrahieren. Die edit_gate-Tests müssen unverändert grün bleiben.
3. Kill-Switch lesen (E9). Er umschließt von Anfang an jeden neuen Prüfpunkt.
4. Commit-Hälfte: E2, E4, E11, Anbindung in `_require_dialog_evidence`. Der bestehende Override-Pfad greift automatisch, weil die Abdeckung als zusätzlicher `reason` zurückkommt.
5. Phase-8-Hälfte: E3 und E3a, `base_commit` bei `start`, Anbindung in `_validate_transition`, CLI `required-files`.
6. Doku (E5, E10, `CLAUDE.md`, WORKFLOW_GUIDE, CHANGELOG), dann `sync_skills.py`.

Die RED-Tests in Phase 5 decken dieselben Punkte ab. Die F001-Reproduktion aus dem Issue ist dabei End-to-End: Erwartet wird Exit 2 mit dem Namen der nicht abgedeckten Datei.

### Dependencies

- **Upstream:**
  - git-CLI: `rev-parse`, `diff --cached`, `diff <ref>`, `diff --diff-filter=d`, `ls-files --others --exclude-standard`, `merge-base`, `merge-base --is-ancestor`
  - `hook_utils` (Root-Auflösung, neue Klassifikation)
  - `config_loader`
  - `override_token`
- **Downstream:**
  - `bash_gate.py` 5c
  - `workflow.py` (`phase phase8_complete`, `complete`, `finish`)
  - `qa_gate.py`
  - `/50-implement`, `/60-validate`, `implementation-validator`
  - alle Konsumenten-Projekte per `setup.py`
- **`ci_spec_gate.py` bleibt unberührt.** Es behält seine breitere, serverseitige Definition, die einem anderen Zweck dient (Spec-Pflicht).

### Known Limitations (vorgesehen für die Spec)

1. **Selbst geschriebener Nachweis:** Ein selbst geschriebenes und gestempeltes Protokoll besteht weiterhin (#253 KL 1). Diese Änderung bindet den Umfang, nicht den Autor.
2. **Commit mit Pfadangabe:** Das Gate zählt dann konservativ den ganzen Arbeitsbaum gegen HEAD.
3. **Degradierter Rückfall:** Nur alte Workflows ohne `base_commit` in Repos ohne `origin/main` fallen auf „nur ungecommittet“ zurück. Die Meldung nennt das.
4. **Mehrere Workflows auf einem Branch:** Liegt dort ein früherer, ungemergter Workflow und wurde danach rebased, zählt dessen Diff mit. Bei einem Worktree pro Workflow, wie empfohlen, tritt das nicht auf.
5. **Gelöschte Dateien** sind nicht gebunden. Bei Umbenennungen zählt der neue Pfad.
6. **Framework-Update mitten im Workflow:** Ein `setup.py --update` macht die aktualisierten `.claude/hooks/*.py` zu Änderungen des Workflows. Updates sollten deshalb außerhalb laufender Workflows passieren.
7. **Basis-Branch fest `origin/main`:** Das entspricht 5b. Ein konfigurierbarer Basis-Branch für 5b und die Abdeckung zusammen wäre ein möglicher Folgeschritt.
8. **Adversary-Limit ohne Technik:** Es bleibt Prompt-Konvention. `fix_loop_iterations` zählt keine Rücksprünge `phase7 → phase6`.

### Open Questions

Keine davon blockiert, alle werden in der Spec entschieden:
- [ ] Exakte Namen und Orte der neuen Funktionen und Wortlaut der Meldungen
- [ ] Soll `workflow.py status` `base_commit` anzeigen? (Nice-to-have, nicht vorgesehen)
- [ ] Wie entsteht `.claude/commands/80-workflow.md`, und wird es mitgeändert?

## TDD RED — Hinweise für die Implementierung (2026-09-28)

RED-Stand: `tests/test_adversary_coverage_gate_259.py`, 122 Tests, davon 94 rot und 28 grüne
Regressionswächter, 0 Collection-Fehler. Basis ist `36d0101`, also `main` nach
[#271](https://github.com/henemm/agent-os-openspec/pull/271) und
[#274](https://github.com/henemm/agent-os-openspec/pull/274). Die übrige Suite ist grün
(1379 passed). Beleg: `docs/artifacts/fix-259-adversary-diff-binding/test-red-output.txt`.

Klärungen des Test-Agenten, entschieden (Tech Lead):
1. **F004 auch im Commit-Gate-Hinweis:** `bash_gate._require_dialog_evidence` baut seinen
   Ausweg-Hinweis mit `wf.get("name", "<workflow>")`. Bei leerem Namen darf dieser Hinweis
   keinen `docs/artifacts/<workflow>/…`-Pfad vorschlagen, sondern nur den `add-artifact`-Weg.
   Das folgt der Absicht von F004, denselben Wert in der Meldung zu nennen. Die Tests prüfen
   den Grund-Text von `check_dialog_evidence`.
2. **`.claude/commands/` in `ALWAYS_ALLOWED_DIRS`:** Der Eintrag hat zwei Pfad-Komponenten und
   trifft beim komponentenweisen Vergleich deshalb nie. `is_gated_code_path` bildet das
   unverändert nach (§1: verhaltensgleich). Harmlos, weil `.md` ohnehin freigestellt ist. Eine
   mögliche Folgebeobachtung, nicht Teil von #259.
3. **CHANGELOG:** Der Eintrag gehört unter das oberste `## [Unreleased]` (Z. 8). Er braucht den
   Migrationshinweis und nennt `required-files` bzw. `base_commit`. Weiter unten steht noch ein
   veralteter `[Unreleased]`-Block, der wird nicht angefasst.
4. **Meldungskerne werden wörtlich getestet**, wie sie im Abschnitt Error Handling der Spec
   stehen: „nicht zitiert“, „teilweise gestagt“, „nicht ermittelbar“, „nur HEAD“,
   „außerhalb“/„ausserhalb“, „Standardpfad“, „Widerspruch“.
5. **`required-files`:** Ohne aktiven Workflow steht „workflow“ auf stderr, bei einem Git-Fehler
   „diff“. In beiden Fällen ist der Exit-Code 1.
6. **Doku-Stichworte (AC-16, case-sensitiv geprüft):**
   - CLAUDE.md, Abschnitt `### Hooks`, und WORKFLOW_GUIDE: `#259`, `required-files` und
     `Änderungsmenge`/`Abdeckungsprüfung`
   - CLAUDE.md, Abschnitt `## Adversary-Limit`: `#259`, `60-validate`/Auto-Fix
   - `implementation-validator`, Step 3 und Step 6: `required-files` bzw. „gelistet“/„listed“
   - `/60-validate` Step 2b: `BROKEN` und `phase6_implement`, `/50-implement` oder Phase 6
7. **Neu seit #271:** `hook_utils` enthält jetzt Helfer für Basis-Stand und Dateiliste
   (`has_observable_surface`). Vor dem Neuschreiben ist zu prüfen, ob sie sich
   wiederverwenden lassen, ohne die Semantik aus §2/§5 der Spec zu verändern (NUL-getrennt,
   Toplevel als cwd, Basis-Wahl).
8. **LoC-Budget:** Die Tests liegen als eigener Commit vor (`587ab18`, noch nicht gepusht).
   Das Test-Delta der Implementierung zählt deshalb ab diesem Stand.
