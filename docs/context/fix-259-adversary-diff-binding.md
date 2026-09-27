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
