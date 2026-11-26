# Context: fix-653-target-dir-flag (Issue #653)

## Request Summary
Die gemeinsame Schreibziel-Erkennung von `bash_gate.py` (Prüfung 1b „wirksame Config“,
1c „Haupt-Ordner aus Worktree“) erkennt das Zielordner-Flag von `cp`/`install`/`ln`/`mv`
nur als exaktes `-t DIR` bzw. `--target-directory=DIR`. Alle anderen gültigen
getopt-Schreibweisen sollen `DIR/<basename>` je Quelle als Schreibziel liefern.

## Nachgestellt (Ist-Zustand, `_config_write_targets`)
| Befehl | Ergebnis heute | Soll |
|---|---|---|
| `cp --target-directory D x` | `['x']` | `D/x` |
| `cp --target-dir=D x` | `['x']` | `D/x` |
| `ln -sft D x` | `['x']` | `D/x` |
| `ln --target-directory D x` | `['x']` | `D/x` |
| `cp -vt D x` | `['x']` | `D/x` |
| `install -Dt D x` | `['x']` | `D/x` |
| `mv -tD x`, `mv --target-dir=D x` | enthält `D/x` (seit #435 via `_mv_dir_targets`) | bleibt |
| `cp -t D x`, `install -m 644 -t D x` | `D/x` | bleibt |

## Related Files
- `core/hooks/bash_gate.py`
  - `_copy_targets`: Ursache — nur `tok == "-t"` und `--target-directory=`.
  - `_CONFIG_WRITERS`: `cp`/`install`/`ln` → `_copy_targets`, `mv` → `_positional + _copy_targets`.
  - `_config_write_targets` / `_segment_write_targets`: gemeinsame Basis für 1b und 1c.
  - `_into_dir_targets` und `_dir_removal_targets`: gleiche exakte Erkennung (`"-t" in args`),
    entscheiden „Zielordner-Modus oder nicht“.
  - `_target_dir_values` / `_mv_dir_targets` (#435): grobe Erkennung nur für `mv`.
  - `_cp_target_dir` (#453): getopt-Parser nur für den Beleg-Schutz (1d) — nicht anfassen.
- Tests: `tests/test_bash_gate_main_write_417.py` (1c), `tests/test_bash_gate_config_lock_418.py` (1b),
  `tests/test_bash_gate_symlink_parent_435.py`, `tests/test_proof_lock_453.py`.

## Existing Patterns
- Subprozess-Tests gegen das echte Gate mit Worktree-Sandbox (`_worktree_sandbox`, `_expect`,
  `OVERRIDE_HINT` aus `test_bash_gate_state_integrity_410`).
- getopt-Logik: Kurzflag-Gruppe, Rest nach Wertbuchstabe ist Wert (`_has_flag`, `_cp_target_dir`).

## Analyse / Ansatz
Ein gemeinsamer, befehlsbezogener getopt-Zerleger `_target_dir_split(cmd, args) -> (zielordner, positionale)`:
- Kurz-Wertbuchstaben je Befehl (GNU coreutils): `cp`/`mv`/`ln`: `S t`; `install`: `g m o S t`.
- Lang-Wertoptionen exakt (`--suffix`, `--mode`, `--owner`, `--group`, `--strip-program`,
  `--no-preserve`, `--sparse`), `--target-directory` zusätzlich in jeder Abkürzung `--t…`
  (bei allen vier Befehlen eindeutig); Wert mit `=` oder als nächstes Token.
- `--` beendet Optionen; Optionen dürfen überall stehen (GNU-Permutation).
- Mehrere Zielordner: alle zählen (fail-closed).
Nutzung in `_copy_targets` (cp/install/ln/mv), `_into_dir_targets`, `_dir_removal_targets`.
Unbekannte Lang-Abkürzungen gelten als wertlos → ihr Folgetoken bleibt positional
(eher zu viele als zu wenige Ziele).

## Dependencies / Dependents
- 1b, 1c und Link-Regel (#435) nutzen `_config_write_targets`/`_dir_removal_targets`.
- 1d (Beleg-Schutz) nutzt `_config_write_targets` zusätzlich; eigener Parser `_cp_target_dir` bleibt.

## Risks
- Hoch-Risiko-Datei (Gate-Code): falsche Wertzuordnung kann Ziele verschlucken → Tests je Schreibweise;
  bestehende Regressionstests 417/418/435/447/448/453 müssen grün bleiben.
- Fehlalarme (zusätzliche Ziele) sind akzeptabel, verschluckte Ziele nicht.
