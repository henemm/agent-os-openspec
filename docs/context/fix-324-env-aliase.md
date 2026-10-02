# Context: fix-324-env-aliase

## Request Summary

Issue #324 (aus #299 Teil C): Aliase, die im geprüften Befehl selbst über git-Umgebungsvariablen
gesetzt werden, erreichen die Alias-Auflösung aus Teil B nicht. `bash_gate` lässt dann
`git ci -m x` mit Exit 0 durch, obwohl `ci` auf `commit` zeigt. Vier nachgestellte Fälle:

1. `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit git ci -m x`
2. `export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit; git ci -m x`
3. `GIT_CONFIG_PARAMETERS="'alias.ci=commit'" git ci -m x`
4. `X=commit git --config-env=alias.ci=X ci -m x`

Bedrohungsmodell unverändert (#299): versehentliches Umgehen verhindern, vorsätzliche
Verschleierung ist Known Limitation.

## Recherche (Stand 2026-10-02)

- `GIT_CONFIG_COUNT` + `GIT_CONFIG_KEY_<i>`/`GIT_CONFIG_VALUE_<i>` (i in [0,n)): Paare werden zur
  Laufzeit-Konfiguration addiert; fehlendes Key/Value ist ein git-Fehler; leeres COUNT = 0.
  Quelle: https://lore.kernel.org/all/X9NzE5+LNYqG1s+o@ncase/T/ (Patch-Serie, git 2.31)
- `--config-env=<name>=<envvar>`: Wert kommt aus der Umgebungsvariable `<envvar>`.
  Quelle: https://code.googlesource.com/git/+/ce81b1da230cf04e231ce337c2946c0671ffb303
- `GIT_CONFIG_PARAMETERS`: interner Mechanismus (Format `'key=value' 'key2=value2'`), von `-c`
  intern genutzt; laut git-Entwicklern nicht als öffentliche Schnittstelle gedacht.
- Zusätzlich im Issue geprüft: git liest alle drei Env-Wege, aber nur aus dem Prozess-Env des
  git-Aufrufs, nicht aus dem Gate-Prozess.

## Related Files

| File | Relevance |
|------|-----------|
| `core/hooks/hook_utils.py` Z. 83–155 | `_GIT_OPTS_WITH_VALUE` (enthält `--config-env`, wird übersprungen), `_repo_aliases` (fragt `git config` im Gate-Prozess), `_inline_aliases` (kennt nur `-c alias.…`), `_resolve_alias` |
| `core/hooks/hook_utils.py` Z. 157–180 | `_git_subcommand_after`: einziger Aufrufer von `_inline_aliases`, sieht nur Tokens AB `git` |
| `core/hooks/hook_utils.py` Z. 227–263 | `_git_subcommand_of_segment` (überspringt `VAR=`-Präfix und `env`/`sudo`-Wrapper), `_git_subcommands_in_segment` |
| `core/hooks/hook_utils.py` Z. 448–497 | `_git_segments` (Segmentierung an `;`/`&&`), `git_subcommands`, `git_head_subcommands` |
| `core/hooks/bash_gate.py` Z. 763–839 | Aufrufer: `is_pure_git_command`, `is_git_subcommand(command, "commit")` |
| `tests/test_bash_gate_erkennung_299_teil_b.py` | Sandbox-Muster (Subprozess gegen echtes Gate, Wegwerf-Repo, Workflow phase6), Vorlage für die neuen Tests |

## Existing Patterns

- Alias-Auflösung: Repo-Aliase (`_repo_aliases`, je Prozess einmal) + inline (`-c`) → `_resolve_alias`
  liefert erstes Wort des Alias-Werts; `commit` ist nie Alias-Ziel (Builtins gewinnen).
- Fail-open-Grundhaltung: nicht zerlegbar → Zweifels-Regel (Fall 3), im Zweifel prüfen.
- Regelweg statt Modell: reine Token-Auswertung, keine externen Aufrufe.

## Kernbefund für die Analyse

Die Env-Zuweisungen stehen VOR dem `git`-Token (Fälle 1, 3, 4: Präfix im selben Segment) oder in
einem VORHERIGEN Segment (Fall 2: `export …; git ci`). `_inline_aliases` bekommt aber nur Tokens ab
`git`. Fall 4 braucht zusätzlich die Zuweisung `X=commit` aus dem Präfix, um `--config-env` aufzulösen.
Fall 2 verlangt Wissen über Segmentgrenzen hinweg → die Env-Sammlung muss command-weit geschehen,
nicht pro Segment.

## Dependencies

- Upstream: `shlex`, `os.environ`, `subprocess` (`git config`).
- Downstream: alle Commit-/Marker-/Foreign-Code-Prüfungen in `bash_gate.py` über die drei
  öffentlichen Funktionen (`git_subcommands`, `git_head_subcommands`, `git_runs_foreign_code`).

## Existing Specs

- `docs/specs/fix-299-bash-gate-erkennung.md` (Teil A/B), `docs/specs/fix-299-bash-gate-erkennung-teil-c.md`
- `docs/context/fix-299-bash-gate-erkennung.md`, `docs/context/fix-299-teil-c.md`

## Risks & Considerations

- **Fehlalarm-Risiko:** „nicht auflösbar ⇒ Aliasname gilt als Commit-verdächtig" darf nur greifen,
  wenn tatsächlich ein Env-Alias für genau diesen Namen existiert, nie für jeden unbekannten
  Unterbefehl.
- **Über-Erkennung bei `export` in anderem Segment:** command-weite Sammlung ist bewusst
  großzügig (sichere Richtung: Gate läuft zusätzlich).
- **`os.environ` des Gate-Prozesses:** Nicht-Aufgelöstes (`--config-env=…=X`, X nicht in der Zeile)
  fällt auf `os.environ` zurück; `_repo_aliases` sieht GIT_CONFIG_* im Gate-Prozess bereits.
- Scope: eine Produktivdatei, ca. 50 LoC; Funktionen ≤ 50 LoC.
- Alternative (Known Limitation) bleibt in der Analyse zu bewerten.

## Analysis

### Type
Bug (Erkennungslücke im bash_gate, Folge aus #299). Reproduziert 2026-10-02 gegen
`hook_utils.is_git_subcommand` (die Funktion, die das Gate aufruft): alle vier Fälle liefern
`git_subcommands == ['ci']`, `is_git_subcommand(…, 'commit') == False`.

### Root Cause
`_git_subcommand_after` übergibt `_inline_aliases` nur Tokens ab `git`; die Env-Zuweisungen stehen
davor (Präfix, Fälle 1/3/4) oder in einem anderen Segment (Fall 2). `--config-env` wird als
Option mit Wert übersprungen. `_repo_aliases` sieht nur die Umgebung des Gate-Prozesses.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/hook_utils.py | MODIFY | `_command_env_aliases(segments)` sammelt command-weit `VAR=wert`, wertet GIT_CONFIG_COUNT/KEY_i/VALUE_i, GIT_CONFIG_PARAMETERS und `--config-env=alias.<n>=VAR` aus; Ergebnis fließt in `_resolve_alias` ein |
| tests/test_bash_gate_env_aliase_324.py | CREATE | 4 Fälle + Negativfälle am echten Gate (Muster aus test_bash_gate_erkennung_299_teil_b.py) |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Scope Assessment
- Files: 3 (1 Produktiv)
- Estimated LoC: +50 Produktion, +90 Tests
- Risk Level: LOW (nur zusätzliche Erkennung, sichere Richtung; kein Fehlalarm ohne Env-Alias für genau diesen Namen)

### Technical Approach (Regelweg, kein Modell)
Ohne Modell geht es nicht? — Doch, es geht rein per Token-Auswertung; kein Modell nötig.
1. In den drei öffentlichen Einstiegen (`git_subcommands`, `git_head_subcommands`,
   `git_runs_foreign_code`) einmal `env_aliases = _command_env_aliases(segments)` bilden und bis
   `_resolve_alias` durchreichen (Parameter statt Modul-Global, damit kein Zustand zwischen Aufrufen leckt).
2. Sammlung command-weit über alle Segmente: jedes Token `VAR=wert` (deckt Präfix, `env`, `export`).
3. Aliase daraus: KEY_i/VALUE_i für i<COUNT; `GIT_CONFIG_PARAMETERS` per zweitem `shlex.split`
   (Format `'k=v' 'k2=v2'`); `--config-env=alias.<n>=VAR` bzw. getrenntes Token → Wert aus Zeile,
   sonst `os.environ`, sonst „nicht auflösbar“ ⇒ Wert `commit` (Aliasname gilt als Commit-verdächtig,
   nur für genau diesen Namen).
4. Kaputte Eingaben (COUNT nicht numerisch, KEY ohne VALUE) ⇒ fail-open ignorieren.

### Alternativen
- **A (empfohlen): auflösen** wie oben — präzise, kein Fehlalarm für `git status` mit Env-Alias.
- **B: Known Limitation** belassen (Issue-Alternative): 0 LoC, aber vier belegte Umgehungen bleiben,
  und genau dieser Weg wurde im Teil-B-Versprechen („Aliase erkannt“) schon als Ziel gesetzt.
- **C: Pauschalregel** — enthält die Zeile `GIT_CONFIG_*`/`--config-env` zusammen mit `alias.`,
  gilt jeder git-Unterbefehl als commit-verdächtig (~8 LoC). Gröber: Fehlalarm bei `git status`
  mit Env-Alias, dafür kein Parsing von COUNT/PARAMETERS. Kippt keine ADR, nur die „präzise“-Linie
  aus Teil B.
Keine frühere ADR wird für A gekippt.

### Dependencies
Nur hook_utils-intern; Aufrufer in bash_gate.py unverändert (Signaturen der öffentlichen Funktionen bleiben).

### Open Questions
- [ ] Keine PO-Frage nötig (rein technisch).
