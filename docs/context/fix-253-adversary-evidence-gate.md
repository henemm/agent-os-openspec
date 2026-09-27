# Context: fix-253-adversary-evidence-gate

## Request Summary

Issue #253: Das Commit-Gate (`bash_gate.py` 5c) und der Übergang nach `phase8_complete`
(`workflow.py`) prüfen nur den String-Präfix von `adversary_verdict`. `post_bash.py` setzt
genau diesen String nach jedem grünen Testkommando automatisch auf `VERIFIED:<framework>` —
unabhängig davon, wer testet und ob der verpflichtende Adversary-Dialog je lief.

## Reproduktion (2026-09-26, gegen `main` @ c4a6214)

Leeres Git-Projekt, Workflow `repro-253` (`feature`, `phase6_implement`, Verdict `null`),
danach die echten Hook-Skripte aus `core/hooks/`:

```
1) Verdict vorher: None
2) post_bash exit=0          ← Payload: pytest -q, stdout "===== 5 passed in 0.12s ====="
3) Verdict nachher: VERIFIED:pytest
E2E scope: docs-only
4) bash_gate (git commit) exit=0  (0 = Commit erlaubt)
```

Kein Adversary-Agent, kein Dialog-Artefakt — der Commit ist frei.

## Root Cause

Zwei Schreiber, ein Leser, keine Herkunftsprüfung:

| Schreiber | Wann | Nachweis |
|---|---|---|
| `qa_gate.py --checklist` | nach gestempeltem Dialog | `validate_dialog_artifact_ex` inkl. Hash-Bindung (#131) |
| `qa_gate.py` ohne `--checklist` | nach gültiger Testausgabe | keiner (nur Testausgabe) |
| `post_bash.py` | nach JEDEM grünen Testbefehl | keiner |
| `workflow.py set-field` | jederzeit (whitelisted) | keiner |

Leser: `bash_gate.py:643` und `workflow.py:1006` — beide nur `verdict.startswith("VERIFIED")`.
Die vorhandene Artefakt-Prüfung (`adversary_dialog.validate_dialog_artifact_ex`) ist nur in
`qa_gate.py --checklist` und als manueller CLI-Schritt in `/60-validate` verdrahtet.

Gleiche Lücke im AMBIGUOUS-Pfad: `set-field adversary_verdict AMBIGUOUS` plus
`override-ambiguous` öffnet Commit und Phase 8 ebenfalls ohne Dialog.

## Related Files

| Datei | Relevanz |
|---|---|
| `core/hooks/post_bash.py` | `_detect_test_output` / `_set_adversary_verdict` (Z. 59–118) — der automatische Schreiber |
| `core/hooks/bash_gate.py` | 5c (Z. 635–660): String-Prüfung, Override-Token als Notbremse, Fast-Track-Ausnahme |
| `core/hooks/workflow.py` | `_validate_transition` (Z. 1005–1012); `cmd_complete` ruft es für `complete`/`finish` |
| `core/hooks/adversary_dialog.py` | `validate_dialog_artifact_ex`, `_hash_root` (Worktree zuerst) |
| `core/hooks/qa_gate.py` | setzt VERIFIED auch ohne `--checklist`; meldet danach "Commit is now allowed." |
| `core/commands/50-implement.md` | Step 8c: Artefakt unter `docs/artifacts/<wf>/adversary-dialog.md`, `add-artifact adversary_dialog`, `stamp` |

## Betroffene Bestandstests

- `tests/test_verdict_pipeline_77.py::TestPostBashStdoutSource` — zwei Tests schreiben das
  fehlerhafte Verhalten fest ("grüner Lauf setzt VERIFIED").
- `tests/test_gate_fixes_26_38_34.py` — `test_26_worktree_current_not_blocked`,
  `test_34_verified_still_transitions`, `test_34_ambiguous_with_override_transitions` setzen
  VERIFIED bzw. AMBIGUOUS+Override ohne Artefakt als "durchlässig" voraus.
- `tests/test_workflow_name_validation.py::TestAmbiguousBlock::test_ambiguous_with_override_allows`.

## Existing Patterns

- **Eine Regel, zwei Aufrufer:** `workflow.check_adr_content` / `check_briefing_content` werden
  vom lokalen Gate und vom CI-Gate gemeinsam genutzt.
- **Worktree zuerst für Arbeitsbaum-Inhalte:** `workflow._worktree_first_path`,
  `adversary_dialog._hash_root` (#80/#96/#131).
- **Notbremse:** User-Override-Token (`override_token.has_valid_token`) im Commit-Gate;
  `workflow.py abandon` für Workflows ohne Prüfgegenstand (#82).
- **Selbsterklärende Blocks:** Meldung + Weg + `gate_diagnostics(...)`-Suffix.

## Baseline

`python3 -m pytest tests/ -q` → 1181 passed, 4 skipped.
