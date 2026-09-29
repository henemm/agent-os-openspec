# Context: fix-281-git-alias-commit-gate

## Request Summary

Issue #281: Das Commit-Gate in `bash_gate.py` erkennt einen Commit nur am wörtlichen Unterbefehl
`commit`. Ein git-Alias (`git config alias.ci commit` → `git ci -m x`) umgeht damit die gesamte
Adversary-Prüfung am Commit: die VERIFIED-Pflicht aus #253 und die Abdeckungsprüfung aus #259.
Gefunden hat das der Adversary in Runde 3 von #259 als Nebenbefund. Der Fehler bestand vorher schon.

## Reproduktion (2026-09-29, git 2.43, Stand `edc9d68`)

```python
>>> hook_utils.git_subcommands("git ci -m x")
['ci']
>>> hook_utils.git_subcommands("git -c alias.ci=commit ci -m x")
['ci']
```

Der Ablauf in `bash_gate.main()`:

1. `git ci -m x` ist ein „reiner git-Aufruf“ (`is_pure_git_command` → True).
2. `is_git_subcommand(command, "commit")` → False.
3. Deshalb greift der **Git-Schnellpfad** (Schritt 2) und ruft `allow()`, und zwar vor
   Marker-Schutz (3a), State-Integrity (3b), Secrets-Guard (4), Credential-Prüfung (4b) und allen
   Commit-Gates (5).

## Related Files

| File | Relevance |
|------|-----------|
| `core/hooks/hook_utils.py` | Die Erkennung: `_looks_like_git`, `_git_subcommand_after`, `_git_subcommand_of_segment` (kopf-gebunden), `_git_subcommands_in_segment` (jedes git-Token), `_git_nested_subcommands` (`sh -c`, `eval`, Tiefe ≤ 2), `_git_lex`, `_git_segments`, `git_subcommands`, `git_head_subcommands`, `is_git_subcommand` (Drei-Fälle-Regel), `is_pure_git_command`, `_is_confidently_decomposed`. Konstanten `_GIT_OPTS_WITH_VALUE` (enthält `-c`, `-C`, `--config-env`), `_GIT_COMMAND_PREFIXES`, `_ENV_ASSIGN_RE`. Hier läuft bisher kein git; die Datei zerlegt nur Text (einzige Ausnahme: `_observable_git` für #260). |
| `core/hooks/bash_gate.py` | Die Verbraucher der Erkennung, siehe nächste Tabelle. |
| `tests/test_git_invocation_detection.py` | Bestehende Tests zur Aufrufform-Erkennung (Issue #1431 aus einem Konsumenten-Projekt, 497 Zeilen). Zwei Ebenen: `hook_utils` direkt und das echte `bash_gate.py` als Subprozess gegen eine Sandbox (`_sandbox`, `_run_bash_gate` mit `CLAUDE_TOOL_INPUT`). Der Test `test_echter_commit_aufruf_wird_immer_erkannt` hält die Untergrenze über eine breite Fallsammlung fest. |
| `tests/test_adversary_coverage_gate_259.py` | Commit-Mengen-Tests (#259) über `_commit_form` / `_commit_change_set`; hier landen Alias-Formen, die die Menge betreffen. |
| `docs/specs/fix-259-adversary-diff-binding.md` | Known Limitation: „git-Aliase (z. B. `git ci`) werden von der `git add`-Erkennung nicht gezielt erfasst“. Sie ist zu eng formuliert, denn tatsächlich wird das ganze Commit-Gate umgangen. Die Spec ist freigegeben und archiviert und wird nicht geändert; die Einordnung gehört in die neue Spec. |

### Verbraucher in `bash_gate.py`

| Stelle | Aufruf | Bedeutung für Aliase |
|--------|--------|----------------------|
| Schritt 2, Git-Schnellpfad (etwa Z. 656–665) | `is_pure_git_command`, `git_subcommands`, `is_git_subcommand(…, "commit")` | Hier liegt der Bypass. Ein Alias gilt als „reiner git-Aufruf, kein Commit“ und wird durchgelassen. |
| Schritt 3a, Marker-Schutz (`is_git_command = git_only`) | Ausnahme für reine git-Aufrufe | **Geschwister-Lücke:** Ein Shell-Alias (`alias.x = !touch …user_approved…`) ist ein „reiner git-Aufruf“ und damit von der Marker-Prüfung ausgenommen. Wegen des Schnellpfads kommt er ohnehin nie bis 3a. |
| Schritt 5, Commit-Gates (Z. 724) | `is_git_subcommand(command, "commit")` | 5a `required_staged_files`, 5b Rebase-Pflicht, 5c Adversary-Verdict/Nachweis (#253/#259), 5d E2E-Scope. |
| `_commit_form` (Z. 491 ff.) | `_git_segments`, `_looks_like_git`, sucht das Token `"commit"` | Bestimmt `-a`, Pfadangabe, `--amend` und begleitendes `add` für die Commit-Menge (#259 §3). Ohne `commit`-Token gilt heute die Unsicherheitsregel, also die größte Menge. Die Argumente aus einer Alias-Definition (`cam = commit -a -m`) sieht die Funktion nicht. |
| `_commit_form` → `"add" in git_subcommands(command)` | `git_subcommands` | Ein Alias für `add` (`a = add`) in `git a neu.py && git commit` wird nicht als begleitendes `add` erkannt. Dann fehlt die neue, untrackte Datei in der Menge. |
| `_is_whitelisted` (Z. 180–203) | `git_head_subcommands` (streng) | Hier ist Über-Erkennung die **gefährliche** Richtung: Ein Whitelist-Treffer überspringt Prüfungen. Die Stelle darf Aliase deshalb nicht großzügig auflösen. Unter-Erkennung heißt dort nur „zusätzlich prüfen“. |
| `_commit_content_files` / `_is_amend` | Regex (nur E2E-Scope-Anzeige) | Informativ, blockt nie. Nicht sicherheitsrelevant. |

Andere Hooks werten keine git-Unterbefehle aus: Weder `"commit"`, `"push"`, `git commit` noch `git push`
kommt außerhalb von `bash_gate.py` und `hook_utils.py` vor.

## Git-Alias-Semantik (empirisch geprüft, git 2.43, Wegwerf-Repo)

| # | Fall | Ergebnis |
|---|------|----------|
| 1 | `git config alias.ci commit` → `git ci -qm x` | committet |
| 2 | `alias.status = commit` → `git status` | **ignoriert**: Aliase, die einen Builtin überschatten, wirken nicht |
| 3 | Kette `alias.c2 = ci`, `alias.ci = commit` → `git c2` | committet (git löst Ketten auf und erkennt Schleifen) |
| 4 | Inline `git -c alias.xx=commit xx -m x` | committet |
| 5 | Env `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.yy GIT_CONFIG_VALUE_0=commit git yy` | committet |
| 6 | `ZZ=commit git --config-env=alias.zz=ZZ zz` | committet |
| 7 | Shell-Alias `alias.sh1 = !git commit` → `git sh1 -m x` | committet: beliebiger Shell-Code, Argumente werden angehängt |
| 8 | Alias mit Argumenten `alias.cam = commit -a -m` → `git cam msg` | committet **mit `-a`**, also Arbeitsbaum statt Index |
| 9 | Externes `git-foo` im `PATH` plus `alias.foo` | **das externe Kommando gewinnt** (Vorrang: Builtin → `git-<name>` → Alias) |
| 10 | Aliase aus `--global` (HOME) und lokal | `git config --get-regexp '^alias\.'` liefert beide Ebenen |
| 11 | `alias.CI2` | wird als `alias.ci2` gespeichert, Schlüssel sind case-insensitiv |
| 12 | `include.path` mit `[alias]`-Abschnitt | per `--get-regexp` sichtbar |
| 13 | Kosten | etwa 2 ms je `git config --get`-Aufruf |

Weitere Werkzeuge: `git --list-cmds=builtins` (140 Einträge), `git --list-cmds=alias` und
`git help <alias>` („'ci' is aliased to 'commit'“).

## Existing Patterns

- **Drei-Fälle-Regel** (`is_git_subcommand`): Erkennt die Zerlegung den Aufruf, wird geprüft.
  Findet sie sicher nichts, wird durchgelassen. Im Zweifel greift die Teilstring-Untergrenze.
  Die alte Teilstring-Prüfung ist die **Untergrenze**, darunter darf nichts rutschen.
- **Verschachtelte Shells** (`_git_nested_subcommands`): Der Rumpf von `sh -c "…"` und `eval "…"`
  wird rekursiv mit `git_subcommands` zerlegt, mit Tiefenlimit 2. Das ist das direkte Vorbild für
  Shell-Aliase: Der Rumpf nach `!` ist ein Shell-Kommando.
- **Streng oder großzügig je nach Fehlerrichtung:** `git_head_subcommands` ist die strenge Variante
  für die Whitelist, `git_subcommands` / `is_git_subcommand` die großzügige für Prüf-Entscheidungen
  (#1431).
- **Unsicherheit → größere Menge** (#259 §3): `_commit_form` liefert `(True, True, True, True)`,
  wenn es keinen direkten Commit-Aufruf zerlegen kann.
- **git-Aufrufe im Hook:** `adversary_dialog.run_git` (probe / fail-closed, Timeout 30 s) und
  `hook_utils._observable_git` (#260). Gemessen wird im Mess-Root
  (`bash_gate._measurement_root()` = Worktree vor Hauptrepo, #155).

## Dependencies

- **Upstream:** git-CLI (`git config --get-regexp`, `--list-cmds`), Python `shlex`, der Mess-Root
  aus `hook_utils.find_worktree_root` / `find_project_root`.
- **Downstream:** Jeder Bash-Aufruf in jedem Projekt, das das Framework nutzt, läuft durch
  `bash_gate.py`. Der Git-Schnellpfad ist dabei performancekritisch, denn er trifft jeden reinen
  git-Befehl. Dazu kommen die #259-Commit-Menge (`_commit_form`), die Projekt-Whitelist
  (`_is_whitelisted`) und die Tests in `test_git_invocation_detection.py` und
  `test_adversary_coverage_gate_259.py`.

## Existing Specs

- `docs/specs/fix-259-adversary-diff-binding.md`: Commit-Menge (§3), Known Limitation zu Aliasen
  (zu eng formuliert, siehe oben).
- Keine eigene Spec zu #1431 in diesem Repo; die Entscheidungsregeln stehen im Docstring von
  `tests/test_git_invocation_detection.py` und in den `hook_utils`-Kommentaren.

## Risks & Considerations

1. **Über-Blockierung:** In Phase 6–7 ohne VERIFIED blockt jeder als Commit erkannte Aufruf. Eine
   zu großzügige Auflösung, etwa jeder unbekannte Unterbefehl oder jeder Shell-Alias gilt als
   Commit, würde alltägliche Aliase (`git lg = log --graph`, `git st = status`) sperren.
   Aliase, die einen Builtin überschatten, muss die Auflösung genau wie git ignorieren (Fall 2).
2. **Shell-Aliase sind beliebiger Code:** `!…` kann committen, Dateien schreiben (Marker 3a) oder
   Secrets ausgeben. Der Rumpf lässt sich wie `sh -c` zerlegen. Ist er nicht sicher zerlegbar,
   gilt die Zweifels-Regel. Ob ein Shell-Alias noch als „reiner git-Aufruf“ gelten darf (Schnellpfad,
   3a-Ausnahme), ist eine Kernfrage der Analyse. Wahrscheinlich nicht.
3. **Welche Konfiguration gilt:** Aliase hängen am Repo, in dem git läuft: `-C <dir>`, `--git-dir`,
   Inline-`-c`, `--config-env`, `GIT_CONFIG_*`/`GIT_CONFIG_GLOBAL`-Zuweisungen vor dem Aufruf oder
   per `env`. Die Auflösung muss dieselbe Sicht haben wie der spätere Aufruf, sonst läuft sie ins
   Leere.
4. **Externe `git-<name>`-Kommandos** haben Vorrang vor Aliasen (Fall 9) und können beliebiges tun.
   Das gleicht der Known Limitation „vorsätzlich manipuliertes git“ aus #259. Zu entscheiden ist, ob
   wir das erkennen (`git --list-cmds=others`) oder dokumentiert ausschließen.
5. **Performance:** Die Auflösung braucht mindestens einen git-Aufruf. Der Schnellpfad trifft jeden
   git-Befehl, deshalb sollte nur ein Unterbefehl nachgeschlagen werden, der kein Builtin ist. Die
   Builtin-Liste ist statisch oder kommt per `--list-cmds=builtins` einmal je Hook-Prozess.
6. **Fail-Richtung bei git-Fehlern:** Scheitert das Nachschlagen (kein Repo, kaputtes git), muss die
   Zweifels-Regel greifen, bis zur Untergrenze der Teilstring-Prüfung, ohne Absturz.
7. **Whitelist bleibt streng:** `_is_whitelisted` darf Aliase nicht als Whitelist-Treffer werten,
   denn Über-Erkennung ist dort die gefährliche Richtung.
8. **Commit-Menge (#259):** Die Argumente einer Alias-Definition (`-a`, Pfade, `--amend`) müssen in
   `_commit_form` einfließen. Heute greift mangels `commit`-Token die Unsicherheitsregel (größte
   Menge); das ist sicher, blockt aber unnötig breit.
9. **Weitere Code-Ausführungswege in „reinem git“** (`-c core.pager=…`, `rebase --exec`,
   `bisect run`, `submodule foreach`, `difftool -x`, Hooks) teilen die Wurzel „reines git ≠
   harmlos“. Sie gehören nicht zu #281. Die Analyse grenzt sie ab und nennt sie als Folge-Thema.
10. **Konsumenten:** Die Änderung erreicht alle Projekte per `setup.py --update` bzw. per Plugin. Es
    braucht keine Migration; dokumentiert werden müssen die neuen Blocks, etwa wenn ein Alias
    committet.
