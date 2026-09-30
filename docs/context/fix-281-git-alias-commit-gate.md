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

## Analysis

Stand 2026-09-30.

- **Grundlage:**
  - drei parallele Explore-Agenten: betroffene Dateien, bindende Vorentscheidungen, Laufzeit-Abhängigkeiten mit Messungen;
  - eine strategische Bewertung (Plan/Sonnet), die den Kern als In-Memory-Prototyp gegen echtes git 2.43 geprüft hat;
  - eigene Nachprüfung der Befunde.
- **Designentscheidungen:** Sie trifft der Tech Lead (Delegation durch den PO).

### Type

Bug, genauer eine Sicherheitslücke im Commit-Gate: Eine Umgehung ist ohne Manipulation möglich.

### Designentscheidungen

**E1 — Eigener Resolver statt Umbau der Text-Parser.**

- **Das Modul:** Neu ist `core/hooks/git_alias.py` mit
  `resolve_git_aliases(command, cwd=None, environ=None, run=None) -> GitAliasView(expansions, shell_bodies, unresolved)`.
  - Der Resolver wirft nie und blockt nie; er liefert nur eine Sicht.
  - Bei `"git" not in command` gibt er sofort eine leere Sicht zurück.
  - Die Text-Parser in `hook_utils` (`git_subcommands`, `is_pure_git_command`, `git_head_subcommands` …) bleiben rein und unverändert; der Resolver nutzt `_git_segments` und `_git_subcommand_after`.
- **Anbindung:** `bash_gate.main()` ruft den Resolver genau einmal auf, direkt nach dem Stop-Lock (Schritt 1). Das Ergebnis gibt es an die Entscheidungsstellen weiter.
- **Warum nicht in die Parser:**
  - Die Parser sind `(command) -> …`-Funktionen ohne cwd und env und werden pro Aufruf 6–8-mal gerufen.
  - Die Bestandstests rufen sie nicht hermetisch; eine `~/.gitconfig` des Entwicklers würde durchschlagen.
  - Shell-Aliase brauchen Seitenkanäle (Rumpf-Text, Reinheit), die eine `list[str]` nicht trägt.
- **Verpackung:** `setup.py` kopiert `core/hooks/*.py` per Glob, der Plugin-Modus nutzt den ganzen Ordner. Eine Registrierung ist nicht nötig, denn es ist kein Hook, sondern ein Hilfsmodul wie `adversary_dialog.py`.

**E2 — Wann nachgeschlagen wird.**

- **Builtins nie:** Nur ein Unterbefehl, der **kein** Builtin ist, löst eine Abfrage aus.
  - Builtins stehen als statisches `GIT_BUILTINS` (die 140 Namen von git 2.43) im Modul.
  - Ein Drift-Test prüft `GIT_BUILTINS ⊆ git --list-cmds=builtins` und wird übersprungen, wenn git älter ist oder fehlt.
  - Damit kostet der heiße Pfad (`git status`, `git add`, `git commit` …) keinen einzigen zusätzlichen Prozess und bekommt keinen neuen Fehlermodus.
- **Schatten-Regel wie git:** Ein Alias mit Builtin-Namen wird ignoriert.
- **Externe `git-<name>`-Kommandos** werden nicht befragt. Den Alias trotzdem aufzulösen, führt höchstens zu Über-Erkennung, also in die sichere Richtung. Weiteres in #297.

**E3 — Die Abfrage.**

- **Befehl:** `git <nachgespielte Optionen> config -z --get-regexp ^alias\.`
- **argv[0]** ist immer `git` aus dem `PATH` des Hooks, nie ein Pfad aus dem Befehlstext (`./git ci` wird nicht ausgeführt).
- **Laufparameter:** cwd `os.getcwd()`, also derselbe Ort, an dem der Befehl startet; Timeout 2 s; `stdin=DEVNULL`.
- **`-z`** ist nötig, weil Alias-Werte Zeilenumbrüche enthalten dürfen.
- **Rückgabecodes:**
  - rc 0 oder 1 liefert die Tabelle; rc 1 tritt auch außerhalb eines Repos auf und ist kein Fehler.
  - Jeder andere rc, ein Timeout oder ein OSError ergibt `unresolved`.
- **Cache und Budget:**
  - Das Ergebnis wird je Kontext gecacht.
  - Höchstens 3 Abfragen pro Bash-Befehl; darüber wird der Rest `unresolved`.
- **Groß- und Kleinschreibung:** Namen werden kleingeschrieben verglichen, denn git behandelt Alias-Schlüssel case-insensitiv.

**E4 — Dieselbe Konfiguration wie der echte Aufruf.**

- **Nachgespielt:** `-C`, `-c`, `--git-dir` und `--work-tree` unverändert. `--config-env=K=E` wird zu `-c K=<Wert>`, mit dem Wert aus der Präfix-Zuweisung oder der Hook-Umgebung; das ist verifiziert identisch zu git.
- **Umgebung:** Die eigene Hook-Umgebung plus Präfix-Zuweisungen aus dem Befehl (`VAR=x git …`, `env VAR=x git …`), aber **nur** aus dieser Freigabeliste:
  - `GIT_CONFIG_GLOBAL|SYSTEM|NOSYSTEM|COUNT|PARAMETERS`
  - `GIT_CONFIG_KEY_n`, `GIT_CONFIG_VALUE_n`
  - `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR`, `GIT_CEILING_DIRECTORIES`
  - `HOME`, `XDG_CONFIG_HOME`
- **Warum die Liste Pflicht ist:** Nachgewiesen ist, dass `GIT_TRACE=<pfad>` und `GIT_TRACE2=<pfad>` selbst ein `git config` in diese Datei schreiben lassen. Die Abfrage des Hooks könnte so einen Freigabe-Marker erzeugen. Aus demselben Grund sind `LD_*`, `PATH`, `GIT_EXEC_PATH` sowie Pager- und Editor-Variablen ausgeschlossen.
- **Unsichere Werte:** Enthält ein Wert Shell-Syntax (`$`, Backtick, `*`, `?`, `[`, `]`, `{`, `}`), wird er `unresolved`. Ein führendes `~` wird expandiert.

**E5 — Änderungen im selben Aufruf („Taint“).** Die Abfrage sieht den Stand **vor** dem Befehl. Deshalb wird ein späterer Nicht-Builtin-Unterbefehl `unresolved`, wenn im selben Befehl davor eines davon vorkommt:

- eine Zuweisung, `export`, `declare` oder `unset` eines freigegebenen Env-Namens;
- ein `git config`- oder `git clone`-Segment, das `alias.` oder `include.` nennt;
- ein Token, das `.gitconfig` oder `.git/config` enthält.

Das schließt `git config alias.ci commit && git ci -m x`; `git config user.name x && git st` bleibt unberührt, beides im Prototyp verifiziert.

**`cd`/`pushd`** mit literalem Pfad wird als implizites `-C <pfad>` für die folgenden Segmente modelliert. Ein Pfad mit Variable, `cd` ohne Argument, `cd -` und `popd` machen dagegen `unresolved`. So bleibt das häufige `cd x && git <alias>` präzise.

**E6 — Ketten.**

- Aufgelöst wird in einer Schleife: Unterbefehl → Alias-Wert (`shlex.split`) plus angehängte Argumente.
- Bei jedem Schritt wird geprüft, ob ein Builtin erreicht ist.
- Die Schleife führt eine Besucht-Menge und bricht nach höchstens 8 Schritten ab.
- Eine Schleife, ein nicht zerlegbarer Wert oder das Überschreiten der Obergrenze ergeben `unresolved`. git selbst bricht bei einer Schleife ab, ohne etwas auszuführen; unser Verhalten ist also die Obermenge.

**E7 — Shell-Aliase (`!…`).**

- **Rumpf:** Text ist `rumpf + " " + shlex.join(args)`, denn git hängt `"$@"` an. Er landet in `shell_bodies` und `expansions` und wird rekursiv aufgelöst, höchstens bis Tiefe 2, wie bei `sh -c`. Rümpfe erben die Optionen des Elternaufrufs; git exportiert dafür `GIT_CONFIG_PARAMETERS`.
- **In `bash_gate`:**
  - `git_only = is_pure_git_command(command) and not (view.shell_bodies or view.unresolved)`. Ein Shell-Alias verliert damit Schnellpfad und 3a-Ausnahme.
  - `scan_cmd` bekommt die Rümpfe angehängt, für 3a (Marker), 3b und 4 (Secrets). Die 4b-Credential-Prüfung bekommt sie nicht, denn Rümpfe sind Nutzer-Konfiguration, kein Text des Agenten.
- **Commit-Erkennung im Rumpf:** über `is_git_subcommand(rumpf, "commit")`, einschließlich Fall 3 der Drei-Fälle-Regel für nicht zerlegbare Rümpfe.

**E8 — Commit-Menge (#259).**

- **Signatur:** `_commit_form(command, view=None)` faltet über `[command, *view.expansions]`. Aus einem `cam = commit -a -m` wird so `-a` sichtbar. Ein `add` in einem der Texte zählt als begleitendes `git add`.
- **Nebeneffekt:** Das schließt nebenbei eine heute offene #259-Lücke. Mit `a = add` liefert `git a neu.py && git commit -m x` heute `(F, F, F, F)`, und die neue Datei fehlt in der Menge.
- **Unsicherheit:** `view.unresolved` oder kein zerlegbarer Commit ergeben wie bisher `(True, True, True, True)`.
- **Weitergabe:** `view` wird über `_commit_change_set` und `_require_dialog_evidence` gereicht.

**E9 — Entscheidungsstellen in `main()`.**

- `committing = is_git_subcommand(command, "commit") or view.unresolved or any(is_git_subcommand(t, "commit") for t in view.expansions)`.
- Schritt 2 wird zu `if git_only and not committing: allow()`.
- Schritt 5 prüft `committing` statt `is_git_subcommand(command, "commit")`.

**E10 — Whitelist bleibt unverändert.** `_is_whitelisted` sieht weiter nur den Originaltext mit dem strengen `git_head_subcommands`; ein Alias ist nie ein Whitelist-Treffer. Die davon unabhängige Lücke in 3b steht in #296 und bleibt außerhalb dieses Umfangs.

**E11 — Meldungen.**

- Erkennt das Gate einen Commit über einen Alias, nennt die Block-Meldung die Auflösung, etwa „`git ci` → `git commit`“.
- Bei `unresolved` nennt sie Grund und Ausweg: den Unterbefehl ausschreiben oder den Aufruf trennen.

**E12 — Fehlerrichtungen.** „Prüfen“ heißt: kein Schnellpfad, keine 3a-Ausnahme, Schritt 5 läuft.

| Situation | Ergebnis |
|---|---|
| Builtin-Unterbefehl | Keine Abfrage, Verhalten wie bisher |
| Abfrage ok, kein Alias (auch ohne Repo) | Durchlassen wie bisher |
| git fehlt, OSError, Timeout, rc ∉ {0,1} | `unresolved`, also prüfen |
| Unzerlegbarer Wert, Schleife, > 8 Schritte, > 3 Kontexte, Taint, `$`-Wert | `unresolved`, also prüfen |
| Unzerlegbarer Shell-Rumpf | Fall 3 auf dem Rumpf; der Befehl gilt nicht als rein |
| Unzerlegbarer Gesamtbefehl | Unverändert: nichts aufgelöst, Known Limitation |
| Ausnahme im Resolver | Intern gefangen; `unresolved`, falls ein Nicht-Builtin-Kandidat gesehen wurde, sonst leere Sicht |
| `ImportError` des Moduls | Altes Verhalten plus Hinweis auf stderr; Bash wird nie lahmgelegt |

Ein fälschliches „prüfen“ wirkt nur, wenn ein Workflow aktiv ist:
- in Phase 6–7 über 5c (VERIFIED-Pflicht);
- in jeder Phase über 5a, 5b und 5d.

Es entsteht nur bei `unresolved`, also in seltenen Fällen, und hat einen dokumentierten Ausweg. Bug-, feature-fast- und workflowlose Sitzungen bleiben unberührt.

### Affected Files (with changes)

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/git_alias.py` | CREATE | Resolver, `GIT_BUILTINS`, Kontext-Nachspielen, Env-Freigabeliste, Taint, Ketten, Shell-Rümpfe; Docstring mit den Rest-Grenzen |
| `core/hooks/bash_gate.py` | MODIFY | `main()`: Sicht nach Schritt 1, `git_only`, `committing`, `scan_cmd`; `_commit_form(command, view)` samt Weitergabe über `_commit_change_set` und `_require_dialog_evidence`; Meldungen (E11) |
| `core/hooks/hook_utils.py` | — | Keine Änderung; der Resolver nutzt die bestehenden Zerlegungs-Helfer |
| `tests/test_git_alias_commit_gate_281.py` | CREATE | E2E gegen das echte `bash_gate.py` in hermetischen echten Repos, Unit-Tests mit injiziertem Runner, Drift-Test |
| `tests/test_git_invocation_detection.py`, `tests/test_adversary_coverage_gate_259.py`, `tests/test_bash_gate_*.py` | CHECK | Regressionswächter, sollen unverändert grün bleiben |
| `docs/WORKFLOW_GUIDE.md` | MODIFY | Zeile „2. Reiner git-Befehl (kein commit)? → ALLOW (Fast Path)“ um die Alias-Auflösung ergänzen |
| `CLAUDE.md` | MODIFY | Neues Hilfsmodul im Architektur-Baum und in „Wichtige Dateien“, je eine Zeile |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]`, inklusive der neuen Blocks |
| `README.md` | CHECK | Gate-Übersicht; voraussichtlich keine Änderung |

### Scope Assessment

- **Dateien:** 2 produktiv (1 neu), 1 neue Testdatei, 3 Doku-Dateien.
- **Geschätzte LoC:**
  - Produktiv etwa +225 bis +260: `git_alias.py` etwa 170–200, `bash_gate.py` etwa +35/−8.
  - Tests etwa +450 bis +550.
- **LoC-Budget:** Das liegt am bzw. über dem Standardlimit von 250 Produktiv- und 500 Testzeilen. In der Spec begründet: `loc_limit_override` 320, `test_loc_limit_override` 700.
- **Risiko: HOCH beim Blast Radius.** Jeder Bash-Aufruf in jedem Projekt, das das Framework nutzt, läuft durch den Code. Gemildert wird das so:
  - Builtins verursachen keinen zusätzlichen Prozess.
  - `"git" not in command` beendet den Resolver sofort.
  - Der Resolver wirft nie.
  - Unsicherheit wirkt nur, wenn ein Workflow aktiv ist.
- **Laufzeit:**
  - `bash_gate.py` braucht gemessen etwa 61 ms für `git status` wie für `ls`.
  - Eine Abfrage kostet etwa 2,3 ms (etwa +4 %) und nur bei Nicht-Builtins.
- **Bestandstests:** Die Suite ruft `bash_gate` nirgends mit einem Nicht-Builtin-Unterbefehl auf, ein Regressionsrisiko für sie ist also kaum vorhanden.

### Technical Approach

Wie E1–E12. Die Test-Strategie hat drei Teile.

**E2E** gegen das echte `bash_gate.py` als Subprozess:
- **Umgebung:** echte, hermetische Repos, Scrub wie in `_env()` aus #259, globale Aliase über `GIT_CONFIG_GLOBAL=<tmpdatei>`, Phase 6 ohne Verdict.
- **Muss blocken (rc 2):**
  - Aliase lokal, global, per `include.path`, inline `-c`, per `GIT_CONFIG_COUNT`-Präfix und per `env` mit `--config-env`;
  - `-C anderes-repo`, eine Kette, ein Shell-Alias mit Commit, verschachteltes `bash -c`;
  - `git config alias… && git ci` im selben Aufruf, `cd anderes && git ci` und `git CI`.
- **Muss durchlassen (rc 0):**
  - `git st` und `git lg`;
  - `alias.status=commit` mit anschließendem `git status`;
  - ein harmloses `!echo hi`.
- **Marker:** Ein Shell-Alias `!touch .claude/user_approved_…` löst den 3a-Block aus.
- **Fehlerrichtung:**
  - Ein `PATH`-Wrapper lässt `config` scheitern: `git st` ergibt rc 2, `git status` rc 0, und für Builtins gibt es null Abfragen.
  - Ein Schleifen-Alias ergibt rc 2.
  - Zwei Nicht-Builtins im selben Kontext kosten eine Abfrage; der vierte Kontext ist `unresolved`.
- **Sicherheit:**
  - `GIT_TRACE=<marker> git -c alias.ci=commit ci` darf die Marker-Datei nicht erzeugen.
  - `./git ci` wird nie ausgeführt.

**#259-Präzision:**
- Mit `ci = commit` ergeben gestagtes B (zitiert) und getrackt geändertes C (nicht zitiert) rc 0.
- `cam = commit -a -m` ergibt rc 2 und nennt C.
- `a = add` plus `git a NEU && git ci` ergibt rc 2 und nennt NEU.

**Unit** mit injiziertem Runner, ohne git:
- Nachspielen von `-C` und `-c`, Übersetzung von `--config-env`;
- ein Recorder für die Env-Freigabeliste: kein `GIT_TRACE*`, kein `LD_*`, kein `PATH`;
- Kette, Schleife, Obergrenze, Schatten-Regel, Groß- und Kleinschreibung, leere und unzerlegbare Werte, `-z` mit Zeilenumbruch;
- die Taint-Matrix, Cache und Budget, Rumpf-Aufbau, Ausnahme-Fallback;
- `_commit_form`-Faltung, Drift-Test;
- Whitelist: Ist der Resolver auf „wirft“ gepatcht, bleibt `_is_whitelisted("git ci -m x")` False.

### Dependencies

- **Upstream:**
  - git-CLI (`config -z --get-regexp`), in `bash_gate` nur als Nutzer der Sicht;
  - `hook_utils._git_segments`, `_git_subcommand_after` und `_looks_like_git`;
  - `shlex`.
- **Downstream:**
  - `bash_gate.main()` (Schritte 2, 3a, 3b, 4, 5) und `_commit_form` / `_commit_change_set` / `_require_dialog_evidence` (#259);
  - alle Konsumenten-Projekte über `setup.py --update` bzw. das Plugin, ohne Migration.

### Verworfene Optionen

- **A — Auflösung in `git_subcommands` / `is_pure_git_command`:** Es gibt keinen cwd- und env-Kontext, der Test-Kontext wäre nicht hermetisch, und Shell-Aliase lassen sich nicht darstellen. Siehe E1.
- **C — Befehlstext umschreiben und die alte Pipeline füttern:** Die Rück-Serialisierung ist verlustbehaftet, und die Regex-Scans sähen synthetischen Text. Die nützliche Idee daraus, kanonische Expansions-Texte für die bestehenden Parser, steckt in E7 und E8.
- **D — Jeder unbekannte Unterbefehl gilt als Commit, ohne Abfrage:** Das blockt `git st`, `git lg`, `git lfs` und Projekt-Aliase. Übrig bleibt davon nur die Semantik von `unresolved`.
- **Builtin-Liste zur Laufzeit (`--list-cmds=builtins`):** Das kostet einen Prozess bei **jedem** git-Befehl. Ersetzt wird es durch die statische Liste plus Drift-Test.
- **Durchsetzung an git's eigenem Engpass** (`pre-commit` / `reference-transaction`-Hook): Das wäre unabhängig von der Schreibweise, braucht aber eine Installation pro Konsument und kollidiert mit husky/pre-commit. Siehe #297.

### Known Limitations (Kandidaten für die Spec)

- **Externe `git-<name>`** im `PATH` haben bei git Vorrang vor Aliasen. Nicht befragt, siehe #297.
- **Weitere Code-Ausführung in „reinem git“:**
  - `-c core.pager|editor|sshCommand`, `diff.external`, `credential.helper=!…`;
  - `rebase --exec`, `bisect run`, `submodule foreach`, `difftool -x`, `mergetool`, `filter-branch`;
  - git-Hooks.

  Siehe #297.
- **Commits ohne `commit`:** `merge`, `cherry-pick`, `revert`, `am` und `pull` erzeugen Commits ohne Gate. Das ist eine Produktentscheidung, siehe #297.
- **Nicht aufgelöste Ausweichwege:**
  - vorsätzlich manipuliertes git (wie Known Limitation aus #259);
  - verschleierte Config-Schreibzugriffe im selben Aufruf (per Skript oder zusammengesetztem Pfad);
  - `source` und eine Shell-Funktion namens `git`;
  - Schachtelung tiefer als 2;
  - nicht zerlegbare Gesamtbefehle (Verhalten unverändert);
  - Race-Condition bei parallel ausgeführten Tool-Aufrufen.
- **Andere Hooks:** Alias-Rümpfe sind für `secrets_guard.py` und `secret_egress_guard.py` unsichtbar, denn beide lesen nur den Befehlstext.
- **Whitelist-Wechselwirkung:** Solange #296 offen ist, wird `git ci … .claude/settings.json` geprüft, das wörtliche `git commit …` dagegen nicht. Dieses Gefälle bleibt bewusst stehen: Die Whitelist darf nicht aufgeweicht werden.
- **Ablösung einer #259-Grenze:** Der Satz zu Aliasen in der Known Limitation der #259-Spec war zu eng. Diese Spec löst ihn ab; die archivierte #259-Spec bleibt unverändert.

### Open Questions

- [x] Modul, Budget, Env-Freigabeliste, Taint und `cd`-Modellierung sind als Tech-Lead-Entscheidung E1–E12 festgelegt.
- [ ] Keine blockierende PO-Frage. Zur Kenntnis:
  1. Bei `unresolved` wird im Zweifel geprüft; ein harmloser Nicht-Builtin-Unterbefehl kann in seltenen Fällen blocken. Ausweg: Unterbefehl ausschreiben.
  2. Ob die Adversary-Pflicht auch für `merge`/`cherry-pick`/`revert`/`am`/`pull` gilt, ist eine Produktfrage in #297, nicht in #281.
