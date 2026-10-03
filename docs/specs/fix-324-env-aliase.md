---
entity_id: fix-324-env-aliase
type: bugfix
created: 2026-10-02
updated: 2026-10-02
status: draft
version: "1.0"
tags: [bash-gate, git-alias, umgebungsvariablen, config-env, teil-c]
test_targets: ["tests/test_bash_gate_env_aliase_324.py"]
---

# bash_gate: Aliase über git-Umgebungsvariablen erkennen (#324)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #324 (Rest aus #299 Teil C, Epic #200). Das CI-Gate für den Adversary-Nachweis (#325) ist ein eigenes Issue und **nicht** Teil dieser Spec.

## Purpose

`bash_gate.py` erkennt seit Teil B Aliase auf `commit` (`git ci -m x`), wenn sie im Repo konfiguriert oder per `-c alias.ci=commit` im Befehl gesetzt sind. Setzt der Befehl den Alias aber über git-Umgebungsvariablen (`GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0`/`GIT_CONFIG_VALUE_0`, `GIT_CONFIG_PARAMETERS`, `--config-env`), erreicht er die Alias-Auflösung nie: die Zuweisungen stehen vor dem `git`-Token oder in einem anderen Segment (`export …; git ci`), die Auflösung sieht nur Tokens ab `git`. Das Gate lässt `git ci -m x` dann mit Exit 0 durch, obwohl `ci` auf `commit` zeigt. Diese Spec schließt die vier belegten Fälle mit einer reinen Token-Auswertung, ohne Modell, ohne neuen Subprozess, ohne Abhängigkeit.

## Source

- **File:** `core/hooks/hook_utils.py` — `_GIT_OPTS_WITH_VALUE`, `_repo_aliases`, `_inline_aliases`, `_resolve_alias`, `_git_subcommand_after`, `_git_runs_foreign_code`, `git_runs_foreign_code`, `_git_subcommand_of_segment`, `_git_subcommands_in_segment`, `_git_segments`, `git_subcommands`, `git_head_subcommands`
- **Analyse:** `docs/context/fix-324-env-aliase.md` (Reproduktion der vier Fälle gegen `is_git_subcommand`, Root Cause, Alternativen)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/hook_utils.py` | Modul | Alias-Auflösung und Segmentierung; einzige Produktivdatei |
| `core/hooks/bash_gate.py` | Modul | Aufrufer (`is_git_subcommand(command, "commit")`, `is_pure_git_command`); bleibt unverändert |
| `tests/test_bash_gate_erkennung_299_teil_b.py` | Test | Sandbox-Muster (Subprozess gegen echtes Gate, Wegwerf-Repo, Workflow phase6); Regressionsschutz |
| git-Dokumentation `git(1)` | extern | `GIT_CONFIG_COUNT`/`KEY_<n>`/`VALUE_<n>` (git ab 2.31), `--config-env=<name>=<envvar>`, `GIT_CONFIG_PARAMETERS` (internes Format `'key=value' 'key2=value2'`) |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | `_command_env_aliases(segments)` sammelt command-weit Env-Aliase; Ergebnis wird als Parameter bis `_resolve_alias` durchgereicht |
| `tests/test_bash_gate_env_aliase_324.py` | CREATE | Subprozess-Tests gegen das echte Gate, beide Fehlerrichtungen |
| `CHANGELOG.md` | MODIFY | Eintrag nur unter `[Unreleased]`, kein Versions-Bump |

### Estimated Changes

- Files: 3 (1 Produktivdatei)
- LoC: ca. +140 (Produktivcode ca. 50, Tests ca. 90). Spec/Kontext/Briefing zählen im LoC-Gate zusätzlich (#294). `core/hooks/` ist Infrastruktur: mit laufendem Workflow ab phase6 entfällt der Override (#322).

## Implementation Details

**Root Cause.** `_git_subcommand_after` übergibt `_inline_aliases` nur Tokens ab `git`. Die Env-Zuweisungen stehen davor (Fälle 1, 3, 4: Präfix im selben Segment) oder in einem früheren Segment (Fall 2). `--config-env` steht in `_GIT_OPTS_WITH_VALUE` und wird nur übersprungen. `_repo_aliases` fragt `git config` im Gate-Prozess und sieht damit nur dessen eigene Umgebung.

**1. Sammlung (`_command_env_aliases(segments)`).** Einmal je Aufruf der öffentlichen Funktion, command-weit über alle Segmente (nicht pro Segment, weil `export …; git ci` die Zuweisung in einem anderen Segment hat):

- Jedes Token der Form `VAR=wert` (`_ENV_ASSIGN_RE`) wird in eine lokale Tabelle aufgenommen. Das deckt Präfix, `env VAR=…` und `export VAR=…` gleichermaßen. Bewusst großzügig: auch eine Zuweisung in einem anderen Segment zählt (sichere Richtung — das Gate läuft zusätzlich, statt zu fehlen).
- **Dreiergruppe:** `GIT_CONFIG_COUNT=n` mit `n` numerisch; für `i < n` gilt `GIT_CONFIG_KEY_i` + `GIT_CONFIG_VALUE_i`. Beginnt der Schlüssel (case-insensitiv) mit `alias.`, entsteht der Eintrag `<name> → <wert>`.
- **`GIT_CONFIG_PARAMETERS`:** der Wert wird ein zweites Mal mit `shlex.split` zerlegt (Format `'key=value' 'key2=value2'`); jedes Element `alias.<name>=<wert>` wird aufgenommen.
- **`--config-env`:** in den Tokens ab einem `git` das Token `--config-env=alias.<name>=<VAR>` oder das getrennte Paar `--config-env`, `alias.<name>=<VAR>`. Der Wert kommt aus der Zeilen-Tabelle (Fall 4: `X=commit`), sonst aus `os.environ` des Gate-Prozesses. Ist `<VAR>` auch dort nicht auffindbar, gilt der Wert als `commit` — der Aliasname ist dann commit-verdächtig, aber ausschließlich dieser Name.
- **Fail-open:** COUNT nicht numerisch, KEY ohne VALUE, nicht zerlegbare `GIT_CONFIG_PARAMETERS` (ungebalancierte Quotes), `--config-env` ohne `=` → der betroffene Eintrag wird ignoriert, keine Exception, alle übrigen Einträge bleiben erhalten.

**2. Durchreichen (Parameter statt Modul-Global).** `git_subcommands`, `git_head_subcommands` und `git_runs_foreign_code` bilden nach `_git_segments(command)` einmal `env_aliases = _command_env_aliases(segments)` und reichen es über `_git_subcommand_of_segment`, `_git_subcommands_in_segment`, `_git_runs_foreign_code` und `_git_subcommand_after` bis `_resolve_alias(sub, inline, env_aliases)` durch (neuer Parameter mit Default `None`, damit interne Aufrufer ohne Env-Wissen unverändert bleiben). In `_resolve_alias` gilt die Rangfolge: Repo-Aliase < Env-Aliase < inline (`-c`), wie sie git selbst anwendet (später gesetzte Konfiguration gewinnt). Es wird **kein** Zustand zwischen Aufrufen gehalten; `_REPO_ALIASES` bleibt die einzige bestehende Prozess-Zwischenablage und ist nicht betroffen. Die Signaturen der drei öffentlichen Funktionen (`git_subcommands`, `git_head_subcommands`, `git_runs_foreign_code`) und von `is_git_subcommand` ändern sich nicht. Jede neue oder geänderte Funktion bleibt ≤ 50 LoC.

**Ohne Modell geht es?** Ja: reine Token-Auswertung nach dokumentierten git-Formaten; die Nulllinie ist die Regel (Regelweg vor Modell).

**Alternativen:**

- **A (gewählt): Env-Aliase auflösen.** Präzise: `git status` mit Env-Alias auf `status` bleibt frei, nur ein Alias, der auf `commit` führt (oder bei unauflösbarem `--config-env` genau dieser Aliasname), löst das Gate aus. Kosten: ca. 50 LoC Parsing.
- **B: Known Limitation belassen** (Alternative aus dem Issue). 0 LoC, aber vier am echten Gate belegte Umgehungen bleiben, und Teil B hat „Aliase werden erkannt“ bereits als Ziel gesetzt; die Lücken sind unabsichtlich erreichbar (Hilfsskripte, die `GIT_CONFIG_COUNT` setzen). Verworfen.
- **C: Pauschalregel.** Enthält die Zeile `GIT_CONFIG_*`/`--config-env` zusammen mit `alias.`, gilt jeder git-Unterbefehl als commit-verdächtig (ca. 8 LoC, kein COUNT-/PARAMETERS-Parsing). Gröber: Fehlalarm bei `git status` mit Env-Alias auf `status`. Verworfen.

## Expected Behavior

- **Input:** Ein Bash-Befehl durch `bash_gate.py`, Projekt mit aktivem Workflow in phase6, ohne Commit-Freigabe (Gate würde `git commit` blocken).
- **Output:** Die vier Env-Alias-Schreibweisen von `git commit` enden mit Exit 2 und der üblichen Commit-Gate-Meldung; Kontrollfälle laufen mit Exit 0 weiter.
- **Side effects:** Keine neuen Subprozesse, keine Dateizugriffe; der Befehl selbst läuft unverändert.

| Befehl | Heute | Soll |
|--------|-------|------|
| `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit git ci -m x` | 0 | 2 |
| `export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit; git ci -m x` | 0 | 2 |
| `GIT_CONFIG_PARAMETERS="'alias.ci=commit'" git ci -m x` | 0 | 2 |
| `X=commit git --config-env=alias.ci=X ci -m x` | 0 | 2 |
| `git --config-env=alias.ci=NUR_IM_GATE_ENV ci -m x` (Variable nicht in der Zeile, nicht in `os.environ`) | 0 | 2 |
| `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.st GIT_CONFIG_VALUE_0=status git st` | 0 | 0 |
| `git --config-env=alias.ci=NUR_IM_GATE_ENV status` (anderer Name als der unauflösbare Alias) | 0 | 0 |
| `git status`, `GIT_CONFIG_COUNT=abc git status`, `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci git status`, `GIT_CONFIG_PARAMETERS="'alias.ci=commit" git status` | 0 | 0 |

## Known Limitations

- **Bedrohungsmodell unverändert (#299):** Verhindert wird das **versehentliche** Umgehen. Vorsätzliche Verschleierung (`eval`, Variablen im Variablennamen, Wrapper-Skripte, Alias in einer Datei, die per `GIT_CONFIG_GLOBAL` eingebunden wird) bleibt Known Limitation; Backstop ist der Phase-8-Übergang.
- **Command-weite Sammlung ist großzügig:** Eine Zuweisung in einem anderen Segment zählt auch dann, wenn sie den späteren `git`-Aufruf in der Shell gar nicht erreicht (z. B. in einer Subshell). Folge ist höchstens ein zusätzlicher Gate-Lauf, nie ein verpasster.
- **`GIT_CONFIG_PARAMETERS` ist ein internes git-Format** (Quelle: git-Entwicklerdiskussion zu `-c`); abweichende Formen werden fail-open ignoriert.
- **Verteilung:** wirkt in Konsumenten-Projekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Die vier Env-Alias-Schreibweisen von `git commit` werden am echten Gate mit Exit 2 abgewiesen, und die Kontrollfälle (Env-Alias auf `status`, `git status`, kaputte Eingaben) laufen weiter mit Exit 0
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, insbesondere False-Positive-, Freetext- sowie Teil-A/B/C-Tests)

## Acceptance Criteria

- **AC-1:** Given ein aktiver Workflow in phase6 / When `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit git ci -m x` als VAR-Präfix läuft / Then blockt das Gate mit Exit 2
  - Test: `tests/test_bash_gate_env_aliase_324.py::test_var_praefix_count_key_value_blockt`
- **AC-2:** Given ein aktiver Workflow in phase6 / When `export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit; git ci -m x` läuft (Zuweisung in einem anderen Segment) / Then blockt das Gate mit Exit 2
  - Test: `tests/test_bash_gate_env_aliase_324.py::test_export_in_anderem_segment_blockt`
- **AC-3:** Given ein aktiver Workflow in phase6 / When `GIT_CONFIG_PARAMETERS="'alias.ci=commit'" git ci -m x` läuft / Then blockt das Gate mit Exit 2
  - Test: `tests/test_bash_gate_env_aliase_324.py::test_git_config_parameters_blockt`
- **AC-4:** Given ein aktiver Workflow in phase6 / When `X=commit git --config-env=alias.ci=X ci -m x` läuft (Wert der Variablen steht als Präfix in der Zeile) / Then blockt das Gate mit Exit 2; dasselbe gilt für die getrennte Schreibweise `--config-env alias.ci=X`
  - Test: `tests/test_bash_gate_env_aliase_324.py::test_config_env_mit_wert_aus_praefix_blockt`
- **AC-5:** Given ein aktiver Workflow in phase6 / When `--config-env=alias.<name>=VAR` eine Variable nennt, die weder in der Zeile noch in `os.environ` des Gate-Prozesses steht, bzw. nur in `os.environ` des Gate-Prozesses steht (dort `commit`) / Then gilt genau dieser Aliasname als commit-verdächtig und das Gate blockt `git <name> -m x` mit Exit 2, während `git status` mit derselben `--config-env`-Option mit Exit 0 durchläuft
  - Test: `tests/test_bash_gate_env_aliase_324.py::test_config_env_unaufloesbar_nur_fuer_diesen_namen`
- **AC-6:** Given ein aktiver Workflow in phase6 / When `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.st GIT_CONFIG_VALUE_0=status git st` läuft / Then lässt das Gate den Befehl mit Exit 0 durch (Env-Alias auf `status` ist kein Commit)
  - Test: `tests/test_bash_gate_env_aliase_324.py::test_env_alias_auf_status_bleibt_frei`
- **AC-7:** Given ein aktiver Workflow in phase6 / When `git status` (ohne Alias) oder ein Befehl ohne Env-Alias-Bezug läuft / Then ist das Verhalten unverändert (Exit 0, keine Fehlalarme)
  - Test: `tests/test_bash_gate_env_aliase_324.py::test_git_status_ohne_alias_unveraendert`
- **AC-8:** Given kaputte Eingaben (`GIT_CONFIG_COUNT` nicht numerisch, `GIT_CONFIG_KEY_0` ohne `GIT_CONFIG_VALUE_0`, `GIT_CONFIG_PARAMETERS` mit ungebalancierten Quotes, `--config-env` ohne `=`) / When `git_subcommands`/`git_head_subcommands`/`git_runs_foreign_code` bzw. das Gate sie verarbeiten / Then wirft keine Funktion eine Exception, der betroffene Eintrag wird ignoriert (fail-open) und das Gate lässt `git status` mit Exit 0 durch
  - Test: `tests/test_bash_gate_env_aliase_324.py::test_kaputte_eingaben_fail_open_ohne_exception`
- **AC-9:** Given zwei aufeinanderfolgende Aufrufe von `git_subcommands` im selben Prozess, der erste mit Env-Alias, der zweite ohne / When beide ausgewertet werden / Then löst der zweite Aufruf `ci` nicht mehr auf (kein Zustand zwischen Aufrufen, Env-Aliase werden als Parameter geführt, nicht als Modul-Global); die Signaturen von `git_subcommands`, `git_head_subcommands`, `git_runs_foreign_code` und `is_git_subcommand` sind unverändert und jede neue oder geänderte Funktion hat ≤ 50 LoC
  - Test: `tests/test_bash_gate_env_aliase_324.py::test_kein_zustand_zwischen_aufrufen_und_signaturen_stabil`
- **AC-10:** Given der bestehende Testbestand / When die Regressionstests laufen / Then bleiben sie grün
  - Test: `tests/test_bash_gate_false_positives.py`, `tests/test_bash_gate_freetext_fixes_64_75.py`, `tests/test_bash_gate_erkennung_299.py`, `tests/test_bash_gate_erkennung_299_teil_b.py`, `tests/test_bash_gate_erkennung_299_teil_c.py` (unverändert, Lauf grün)

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_bash_gate_env_aliase_324.py` (AC-1 bis AC-9; Subprozess gegen das echte Gate im Wegwerf-Repo nach dem Muster aus `tests/test_bash_gate_erkennung_299_teil_b.py`; AC-8 und AC-9 zusätzlich mit direkten Funktionsaufrufen; beide Fehlerrichtungen: Umgehung blockt, Kontrollfall bleibt frei). Der Test für den `os.environ`-Zweig von AC-5 setzt die Variable in der Umgebung des Gate-Subprozesses.
- RED-Nachweis: Vor der Implementierung schlagen AC-1 bis AC-5 fehl (Exit 0 statt 2), die Kontrollfälle AC-6 bis AC-8 sind bereits grün.
- Regressionslauf: `pytest tests/test_bash_gate_false_positives.py tests/test_bash_gate_freetext_fixes_64_75.py tests/test_bash_gate_erkennung_299.py tests/test_bash_gate_erkennung_299_teil_b.py tests/test_bash_gate_erkennung_299_teil_c.py` (AC-10), danach die Vollsuite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Schließt eine Erkennungslücke innerhalb der bestehenden Entscheidung „Gate prüft Befehlstext per Regeln“; kein neues Muster, keine neue Abhängigkeit. Reflexion der Alternativen: (A) auflösen — gewählt, weil präzise und ohne Fehlalarm für Env-Aliase auf andere Unterbefehle; (B) Known Limitation — verworfen, weil vier belegte, unabsichtlich erreichbare Umgehungen bestehen blieben und Teil B Alias-Erkennung bereits zugesagt hat; (C) Pauschalregel — verworfen wegen Fehlalarmen bei `git status` mit Env-Alias, sie würde nur die „präzise“-Linie aus Teil B aufgeben. Keine frühere ADR wird gekippt.

## Changelog

- 2026-10-02: Initial spec created (#324, Rest aus #299 Teil C)
