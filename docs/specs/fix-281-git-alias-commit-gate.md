---
entity_id: fix-281-git-alias-commit-gate
type: bugfix
created: 2026-09-30
updated: 2026-09-30
status: draft
version: "1.0"
workflow: fix-281-git-alias-commit-gate
tags: [commit-gate, git-alias, bash-gate, fast-path, adversary, resolver]
test_targets: ["tests/test_git_alias_commit_gate_281.py"]
---

# Commit-Gate löst git-Aliase auf (#281)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #281 — „Commit-Gate erkennt git-Aliase nicht — `git ci` umgeht die gesamte
  Adversary-Prüfung“. Gefunden vom Adversary in Runde 3 von #259
  (`docs/specs/fix-259-adversary-diff-binding.md`) als Nebenbefund; der Fehler bestand schon
  vorher. Reproduktion (git 2.43): `git config alias.ci commit`, dann `git ci -m x` → Exit 0 ohne
  Dialog-Artefakt; ebenso inline `git -c alias.ci=commit ci -m x`. Abgegrenzt sind die
  Folge-Issues #296 (Whitelist-Gefälle in Schritt 3b), #297 (externe `git-<name>`, weitere
  Code-Ausführung in „reinem git“, Commits ohne `commit`) und #298 (verschachtelte Shells mit
  Optionsbündel wie `bash -lc`) — siehe Known Limitations.

## Purpose

Das Commit-Gate in `bash_gate.py` erkennt einen Commit nur am wörtlichen Unterbefehl `commit`. Ein
git-Alias (`git config alias.ci commit`, dann `git ci -m x`) umgeht es deshalb vollständig, ebenso
der Inline-Alias `git -c alias.ci=commit ci -m x`: `git ci` gilt als „reiner git-Aufruf, kein
Commit“, der Git-Schnellpfad (Schritt 2) lässt ihn durch — noch vor Marker-Schutz (3a),
State-Integrity (3b), Secrets-Guard (4), Credential-Prüfung (4b) und allen Commit-Gates (5). Damit
entfallen am Commit die VERIFIED-Pflicht (#253) und die Abdeckungsprüfung (#259), reproduziert ohne
jede Manipulation.

Diese Spec löst Aliase vor der Entscheidung auf. Ein neues Hilfsmodul `core/hooks/git_alias.py`
liefert eine „Sicht“ auf den Bash-Befehl — welche Alias-Aufrufe zu welchen Befehlen expandieren,
welche Shell-Rümpfe mitlaufen, was sich nicht sicher auflösen ließ —, die `bash_gate.py` an seinen
Entscheidungsstellen auswertet. Drei Grundsätze: Builtins werden nie nachgeschlagen (kein
zusätzlicher Prozess im heißen Pfad); Aliase werden dort und mit der Konfiguration aufgelöst, mit
der der Aufruf tatsächlich läuft (Verzeichnis, Optionen, Umgebung), ohne dass die Abfrage selbst
etwas bewirkt; und was sich nicht sicher auflösen lässt, wird wie ein Commit geprüft. Als
Geschwister-Lücke schließt die Spec, dass ein Shell-Alias (`!touch …user_approved…`) als „reiner
git-Aufruf“ die Marker-Sperre umging, und dass die Argumente aus einer Alias-Definition
(`cam = commit -a -m`) die #259-Commit-Menge bestimmen.

## Source

- **File:** `core/hooks/git_alias.py` (neu) — **Identifier:** `resolve_git_aliases`,
  `GitAliasView`, `GIT_BUILTINS`
- **File:** `core/hooks/bash_gate.py` — **Identifier:** `main()` (Schritte 2, 3a, 3b, 4, 5),
  `_commit_form`, `_commit_change_set`, `_require_dialog_evidence`
- **File:** `core/hooks/hook_utils.py` — unverändert; genutzt werden seine Zerlegungs-Helfer
  (`_git_lex`, `_git_segments`, `_git_subcommand_after`, `_looks_like_git`, `_is_git_separator`,
  `_GIT_OPTS_WITH_VALUE`, `_GIT_COMMAND_PREFIXES`, `_ENV_ASSIGN_RE`)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils`-Zerlegungs-Helfer (`_git_lex`, `_git_segments`, `_git_subcommand_after`, `_looks_like_git`, `_is_git_separator`, `_GIT_OPTS_WITH_VALUE`, `_GIT_COMMAND_PREFIXES`, `_ENV_ASSIGN_RE`) | function/const | Segmente, Token und Unterbefehl-Bestimmung des Resolvers; bleiben unverändert |
| `hook_utils.is_git_subcommand` / `git_subcommands` / `is_pure_git_command` / `git_head_subcommands` | function | Bestehende, reine Text-Parser; `git_head_subcommands` bleibt der strenge Maßstab der Whitelist |
| `bash_gate._commit_form` / `_commit_change_set` / `_require_dialog_evidence` (#259) | function | Bekommen die Sicht durchgereicht, damit Alias-Argumente die Commit-Menge bestimmen |
| `override_token.has_valid_token` | function | Notbremse im Commit-Gate; gilt unverändert auch für einen über Alias erkannten Commit |
| git-CLI (`config -z --get-regexp`, `--list-cmds=builtins`) | external | Abfrage der Alias-Tabelle, nur für Nicht-Builtins; die Builtin-Liste wird nur im Drift-Test abgefragt |
| Python `shlex`, `subprocess`, `dataclasses` | stdlib | Zerlegung der Alias-Werte, Abfrage, Struktur der Sicht |
| `docs/context/fix-281-git-alias-commit-gate.md` | doc | Analyse mit den Designentscheidungen E1–E12, nach denen Abschnitte 1 bis 13 nummeriert sind |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/git_alias.py` | CREATE | Resolver, `GIT_BUILTINS`, Kontext-Nachspielen, Env-Freigabeliste, im Befehl benannte Konfigurationsquellen, Taint, Ketten, Shell-Rümpfe; Modul-Docstring mit den Rest-Grenzen |
| `core/hooks/bash_gate.py` | MODIFY | `main()`: Sicht nach Schritt 1, `git_only`, `committing`, `scan_cmd`, Meldungen; `_commit_form(command, view)` (zählt auch `stage` als begleitendes `add`) samt Weitergabe über `_commit_change_set` und `_require_dialog_evidence` |
| `core/hooks/hook_utils.py` | — | Keine Änderung; der Resolver nutzt die bestehenden Zerlegungs-Helfer |
| `tests/test_git_alias_commit_gate_281.py` | CREATE | E2E gegen das echte `bash_gate.py` in hermetischen echten Repos, Unit-Tests mit injiziertem Runner, Drift- und Doku-Test |
| `tests/test_git_invocation_detection.py`, `tests/test_adversary_coverage_gate_259.py`, `tests/test_adversary_evidence_gate_253.py`, `tests/test_bash_gate_*.py`, `tests/test_gate_fixes_26_38_34.py`, `tests/test_selfexplaining_gates.py` | CHECK | Regressionswächter, bleiben unverändert grün |
| `docs/WORKFLOW_GUIDE.md` | MODIFY | Fast-Path-Zeile der `bash_gate.py`-Übersicht nennt die Alias-Auflösung |
| `CLAUDE.md` | MODIFY | `git_alias.py` als Hilfsmodul im Architektur-Baum und in „Wichtige Dateien“, je eine Zeile |
| `README.md` | MODIFY | Architektur-Baum unter `core/hooks/`: eine Zeile für `git_alias.py` als Hilfsmodul (kein Hook), analog zu `precondition_origins.py` |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]` mit den neuen Block-Fällen und dem `git stage`-Nebeneffekt |
| `docs/specs/fix-281-git-alias-commit-gate.md` | CREATE | Diese Spec |

**Bewusst unverändert:**
- `docs/specs/fix-259-adversary-diff-binding.md` — freigegeben und eingefroren (#230). Jede
  Änderung macht ihr PO-Briefing ungültig, und `scripts/ci_spec_gate.py` prüft den
  `spec_sha256`-Stempel jeder im PR geänderten Spec: der PR würde rot. Die dortige Alias-Grenze
  löst diese Spec ab (Known Limitations).
- `core/hooks/hook_utils.py` — die Text-Parser bleiben rein (ADR, Festlegung 1).
- `hooks/hooks.json` und `setup.py` — `git_alias.py` ist ein Hilfsmodul wie `adversary_dialog.py`,
  kein Hook; `setup.py` kopiert `core/hooks/*.py` per Glob, der Plugin-Modus nutzt den ganzen Ordner.
- `bash_gate._is_whitelisted` — bleibt streng und sieht keine Aliase (Abschnitt 11).

### Estimated Changes

- **Files:** 2 Produktivdateien (davon 1 neu), 1 neue Testdatei, 4 Doku-Dateien, plus diese Spec.
- **LoC:** Produktiv ca. +325 bis +355 (`git_alias.py` ca. 290–315, `bash_gate.py` ca. +37/−8),
  Tests ca. +700 bis +800, Doku ca. +30 bis +50 (überwiegend der CHANGELOG-Eintrag).

**Budget-Überschreitung begründet:** Das Standardlimit (250 LoC Produktiv / 500 LoC Tests) reicht
nicht, weil jeder der folgenden Bausteine einen eigenen Weg schließt, auf dem ein Alias sonst am
Gate vorbeiliefe: das Nachspielen des Aufruf-Kontexts (Verzeichnis, Optionen, Umgebungs-
Freigabeliste, im Befehl benannte Konfigurationsquellen), die Taint-Regeln für Änderungen im selben
Aufruf, das `cd`-Modell, die Auflösung von Ketten und Optionen im Alias-Wert sowie die Shell-Rümpfe
samt Anbindung an Marker-Schutz und Commit-Menge. Eine Aufteilung entlang dieser Bausteine wurde
verworfen: Jedes Teilstück allein ließe einen der Bypass-Wege offen (etwa `cd B && git ci` oder
`git config alias.ci commit && git ci`) und wäre damit nur halb gelöst — die Ursache ist die Zahl
der Wege, keine Aufblähung. Bei der Implementierung zu setzen, mit dieser Begründung im
Commit-Bezug:

```bash
python3 .claude/hooks/workflow.py set-field loc_limit_override 380
python3 .claude/hooks/workflow.py set-field test_loc_limit_override 850
```

## Implementation Details

Die Nummerierung folgt den Designentscheidungen E1–E12 der Analyse
(`docs/context/fix-281-git-alias-commit-gate.md`); die Abschnitte 14 bis 16 fassen Budget und Cache,
unzerlegbare Befehle sowie Doku und Verteilung zusammen. Leitregel für alles Folgende: Bei leerer
Sicht verhält sich `bash_gate.py` exakt wie vor dieser Änderung.

### 1. Eigener Resolver statt Umbau der Text-Parser (E1)

`core/hooks/git_alias.py` ist ein Hilfsmodul wie `adversary_dialog.py`: kein Hook, keine
Registrierung in `hooks/hooks.json`. Öffentlich sind `GIT_BUILTINS` und

```
resolve_git_aliases(command, cwd=None, environ=None, run=None) -> GitAliasView
```

- `cwd=None` bedeutet `os.getcwd()`, `environ=None` bedeutet `os.environ`, `run=None` den
  Standard-Runner. Ein Runner hat die Form `run(argv, cwd, env) -> (rc, stdout_bytes)` und darf
  `OSError` und `subprocess.TimeoutExpired` werfen — beides ergibt `unresolved`. Tests injizieren
  ihn und brauchen dann kein git.
- Der Resolver wirft nie und blockt nie; er liefert nur die Sicht. Enthält der Befehl das Teilwort
  `git` nicht, kommt sofort die leere Sicht zurück.
- `GitAliasView` hat fünf Listen, alle leer heißt „nichts zu tun“:

| Feld | Inhalt |
|------|--------|
| `expansions` | argv-Token-Listen je aufgelöstem Alias-Aufruf, z. B. `["git", "commit", "-a", "-m", "msg"]` — kein zurückserialisierter Text |
| `shell_bodies` | Rümpfe von Shell-Aliasen als Text (`rumpf + " " + shlex.join(args)`) |
| `unresolved` | Gründe (Text), aus denen ein Nicht-Builtin nicht sicher aufgelöst werden konnte; leer = sicher |
| `unresolved_subs` | die betroffenen Unterbefehle (für die Meldung), ohne Duplikate |
| `resolutions` | Auflösungszeilen für die Meldung, z. B. `git ci → git commit` |

Die Text-Parser in `hook_utils` (`git_subcommands`, `is_pure_git_command`,
`git_head_subcommands`, `is_git_subcommand`) bleiben rein und unverändert; der Resolver nutzt deren
Zerlegungs-Helfer. Warum nicht in die Parser: Sie sind `(command) -> …`-Funktionen ohne cwd und
Umgebung und werden pro Aufruf sechs- bis achtmal gerufen; die Bestandstests rufen sie nicht
hermetisch, eine `~/.gitconfig` des Entwicklers würde durchschlagen; und Shell-Aliase brauchen
Seitenkanäle (den Rumpf-Text), die eine `list[str]` nicht trägt.

`bash_gate.py` ruft den Resolver genau einmal auf, über einen kleinen Helfer `_alias_view(command)`
direkt nach dem Stop-Lock (Schritt 1) — ein gesperrter Hook startet so keinen git-Prozess. Es
bindet das Modul (`import git_alias`), nicht die Funktion, damit Tests an einer einzigen Stelle
patchen können. Schlägt der Import mit `ImportError` fehl (Hook-Kopie ohne die Datei), gibt der
Helfer die leere Sicht zurück — altes Verhalten — plus eine stderr-Zeile, die `git_alias` nennt.
Das Modul-Docstring führt die Rest-Grenzen aus den Known Limitations auf.

### 2. Wann nachgeschlagen wird (E2)

- **Builtins nie.** Nur ein Unterbefehl, der kein Builtin ist, löst eine Abfrage aus. `GIT_BUILTINS`
  (`frozenset`) enthält statisch die 140 Namen von `git --list-cmds=builtins` aus git 2.43; der
  Abgleich ist exakt und case-sensitiv. Damit kostet der heiße Pfad (`git status`, `git add`,
  `git diff`, `git commit` …) keinen einzigen zusätzlichen Prozess und bekommt keinen neuen
  Fehlermodus.
- **Schreibweise.** Der Alias-Abgleich ist dagegen case-insensitiv: git speichert Alias-Schlüssel
  kleingeschrieben (`alias.CI2` wird `alias.ci2`), die Tabelle des Resolvers ebenso. Geprüft mit
  git 2.43: Mit `alias.ci=commit` committet `git CI`; mit `alias.status=commit` committet
  `git STATUS` (Großschreibung ist kein Builtin), während `git status` den Builtin nimmt.
- **Schatten-Regel wie git.** Ein Alias mit Builtin-Namen wirkt nicht (`alias.status=commit` und
  `git status` bleibt `status`) — auch mitten in einer Kette: Erreicht sie einen Builtin, ist sie
  zu Ende.
- **Nicht bestimmbarer Unterbefehl.** Enthält das Unterbefehl-Token Shell-Syntax (`$`, Backtick,
  `*`, `?`, `[`, `{`), steht sein tatsächlicher Name erst zur Laufzeit fest (`git $CMD -m x`,
  `git com* -m x`): `unresolved`, ohne Abfrage. Eine Abfrage nach dem wörtlichen Token fände nie
  einen Alias und meldete fälschlich „sicher“ — das ist ein Korrektheitsanspruch des Resolvers
  selbst, deshalb gehört die Regel zu #281. Weil der Lexer einen Backtick als eigenen Trenner
  abspaltet, zählt auch ein Backtick-Trenner unmittelbar hinter einem am Segmentkopf stehenden
  `git` samt Optionen (`` git `echo commit` -m x ``): Das Segment endet dort ohne Unterbefehl-Token.
  Dieselbe Regel gilt für Unterbefehle in Alias-Werten und Shell-Rümpfen.
- **Externe `git-<name>`** im `PATH` haben bei git Vorrang vor Aliasen und werden nicht befragt
  (siehe #297). Den Alias trotzdem aufzulösen führt höchstens zu Über-Erkennung, also in die
  sichere Richtung.
- **Drift und Version.** Ein Drift-Test prüft `GIT_BUILTINS ⊆ git --list-cmds=builtins` und wird
  übersprungen, wenn git fehlt oder älter als 2.43 ist (AC-17). Neuere git-Versionen mit
  zusätzlichen Builtins führen nur zu Über-Erkennung; die Grenze für ältere Versionen steht in den
  Known Limitations.

### 3. Die Abfrage (E3)

```
git <nachgespielte Optionen> config -z --get-regexp ^alias\.
```

- `argv[0]` ist immer `git` aus dem `PATH` des Hooks, nie ein Pfad aus dem Befehlstext: `./git ci`
  wird nicht ausgeführt, sondern wie `git ci` aufgelöst (AC-11).
- Die Abfrage läuft dort, wo der Aufruf läuft: cwd `os.getcwd()` (bzw. der Parameter `cwd`) plus
  die nachgespielte `-C`-/`cd`-Kette (Abschnitte 4 und 6) — nicht im Mess-Root
  (`_measurement_root()`) des Commit-Gates. Das weicht bewusst vom Lösungsvorschlag des Issues ab
  („im Mess-Root“), weil es git-genau ist: Aliase hängen an dem Repository, in dem git läuft.
- Laufparameter: Timeout 2 s, `stdin=DEVNULL`, stderr verworfen. `-z`, weil Alias-Werte
  Zeilenumbrüche enthalten dürfen; ein Eintrag ist `alias.<name>`, Zeilenumbruch, Wert, NUL.
- Rückgabecodes: rc 0 oder 1 liefern die Tabelle (rc 1 heißt „kein Treffer“ und tritt auch
  außerhalb eines Repositorys auf — das ist kein Fehler). Jeder andere rc, ein Timeout oder ein
  `OSError` (auch: git fehlt) ergibt `unresolved`.
- Mehrfach definierte Schlüssel: `--get-regexp` listet alle Ebenen in Vorrang-Reihenfolge (system,
  global, lokal, worktree, Kommandozeile); wie bei git gilt der zuletzt gelistete Wert. Geprüft:
  lokales `alias.dup=log` plus `-c alias.dup=commit` committet.
- Umgebung: Basis ist die Hook-Umgebung, daraus entfernt `GIT_CONFIG` (nur `git config` selbst
  beachtet es — die Abfrage läse allein diese Datei, während `git ci` sie ignoriert; geprüft) und
  alle `GIT_TRACE*` (Begründung in Abschnitt 4). Darüber liegen die freigegebenen
  Präfix-Zuweisungen des Segments.

### 4. Dieselbe Konfiguration wie der echte Aufruf (E4)

Die Abfrage braucht dieselbe Sicht wie der spätere Aufruf, sonst läuft sie ins Leere. Für jedes
git-Token eines Segments — am Kopf, nach Präfix-Zuweisungen und den Wrappern `sudo`, `env`, `nice`,
`command`, `time`, `nohup`, oder irgendwo sonst (`xargs … git ci`, `timeout 5 git ci`) — wird der
Unterbefehl wie in `_git_subcommands_in_segment` bestimmt. Ein Nicht-Builtin wird in seinem
Kontext aufgelöst:

- **Nachgespielte Optionen** (Vor-Optionen des git-Tokens, in Aufrufreihenfolge): `-C`, `-c`,
  `--git-dir` und `--work-tree` unverändert. `--config-env=K=E` wird zu `-c K=<Wert>`, mit dem Wert
  aus einer Präfix-Zuweisung desselben Segments (beliebiger Name) oder aus der Hook-Umgebung —
  verifiziert git-identisch (`ZZ=commit git --config-env=alias.zz=ZZ zz` committet). Ist die
  Variable nirgends gesetzt, ist der Wert nicht bestimmbar (`unresolved`).
- **Umgebung der Abfrage:** Die Präfix-Zuweisungen des Segments (`VAR=x git …`, `env VAR=x git …`)
  kommen nur durch, wenn ihr Name auf der Freigabeliste steht: `GIT_CONFIG_GLOBAL`,
  `GIT_CONFIG_SYSTEM`, `GIT_CONFIG_NOSYSTEM`, `GIT_CONFIG_COUNT`, `GIT_CONFIG_PARAMETERS`,
  `GIT_CONFIG_KEY_n`, `GIT_CONFIG_VALUE_n`, `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR`,
  `GIT_CEILING_DIRECTORIES`, `GIT_DISCOVERY_ACROSS_FILESYSTEM`, `HOME`, `XDG_CONFIG_HOME`. Alles
  andere wird nicht durchgereicht (`LD_*`, `PATH`, `GIT_EXEC_PATH`, Pager- und Editor-Variablen,
  `GIT_TRACE*`). Die Liste ist Pflicht: Nachgewiesen ist, dass `GIT_TRACE=<pfad>` und
  `GIT_TRACE2=<pfad>` selbst ein `git config` in diese Datei schreiben lassen — die Abfrage des
  Hooks könnte so einen Freigabe-Marker erzeugen.
- **Kopf-Kontext und Wrapper:** Präfix-Zuweisungen gelten nur für ein git-Token, das ihnen
  unmittelbar folgt (nach den genannten Wrappern). `env` mit Optionen (`-i`, `-u`, `-C`, `-S` …)
  oder `sudo` vor git ergibt `unresolved` für die Nicht-Builtins dieses Segments. Für git-Tokens, vor
  denen ein anderes Kommando steht (`xargs … git ci`, `timeout 5 git ci`, eine verschachtelte
  Shell), gilt der Kontext ohne Präfix-Zuweisungen; steht im selben Segment (bei einer verschachtelten
  Shell: im Segment des Shell-Aufrufs) eine Zuweisung eines freigegebenen Namens, deren Reichweite
  damit nicht bestimmbar ist, wird der Aufruf `unresolved`.
- **Unsichere Werte:** Enthält ein nachgespielter Wert (Pfad, `-c`-Wert, `--config-env`-Wert) oder
  der Wert einer Freigabe-Zuweisung Shell-Syntax (`$`, Backtick, `*`, `?`, `[`, `]`, `{`, `}`), ist
  er nach der Shell-Expansion unbekannt: `unresolved`. Ein führendes `~` wird mit `HOME` der
  Hook-Umgebung expandiert.
- **Im Befehl benannte Konfigurationsquellen:** Nennt der nachgespielte Kontext eine
  Konfigurationsdatei — den Wert einer Präfix- oder `env`-Zuweisung von `GIT_CONFIG_GLOBAL` oder
  `GIT_CONFIG_SYSTEM`, oder einen Eintrag `include.path` bzw. `includeIf.<bedingung>.path` aus
  `-c`, aus `--config-env` (Wert aus einer Präfix-Zuweisung) oder aus `GIT_CONFIG_KEY_n` und
  `GIT_CONFIG_VALUE_n` —, ist jeder Nicht-Builtin-Unterbefehl dieses Aufrufs `unresolved` (ohne
  Abfrage), wenn die Datei zur Hook-Zeit nicht existiert oder ihr Pfad oder Dateiname in einem
  anderen Token desselben Befehls noch einmal vorkommt. Typisch ist das Schreibziel im selben
  Aufruf: `printf '[alias]\n\tci = commit\n' > /tmp/f && GIT_CONFIG_GLOBAL=/tmp/f git ci -m x`.
  Eine Präfix- oder `env`-Zuweisung von `GIT_CONFIG_PARAMETERS`, deren Wert (kleingeschrieben)
  `include` enthält, macht die Nicht-Builtins dieses Aufrufs ohne weitere Prüfung `unresolved` —
  das interne Quoting dieses Werts wird bewusst nicht nachgebaut.
- **Grund und Grenzen dieser Prüfung:** Die Abfrage sieht den Stand vor dem Befehl; eine Datei, die
  der Befehl erst anlegt oder beschreibt, ist für sie leer oder fehlt. Werte aus der Hook-Umgebung
  selbst sind ausgenommen, denn eine fehlende globale Konfiguration ist dort legitim. Relative
  Pfade gelten gegen das Verzeichnis des Aufrufs (cwd, `cd`-Kette und `-C`; ist es unbekannt, ist
  der Aufruf ohnehin `unresolved`), ein führendes `~` wird wie oben expandiert. Als „noch einmal
  vorkommen“ zählt eine Teilzeichenfolge in einem Token des Befehls, einschließlich der Tokens
  verschachtelter Shell-Texte; nicht mitgezählt werden die Tokens, die selbst eine
  Konfigurationsquelle benennen, und ein verschachtelter Shell-Text als Ganzes.

### 5. Änderungen im selben Aufruf: Taint (E5)

Die Abfrage sieht den Stand **vor** dem Befehl. Ein späterer Nicht-Builtin-Unterbefehl desselben
Bash-Befehls (in Textreihenfolge, auch über verschachtelte Shells hinweg) wird deshalb
`unresolved`, wenn davor eines davon vorkommt:

- **(a)** ein Segment `git config` oder `git clone`, in dem ein Token (kleingeschrieben) `alias.`
  oder `include` enthält — das deckt `include.path` und `includeIf.*` ab, denn Abschnittsnamen sind
  case-insensitiv;
- **(b)** ein Token, das (kleingeschrieben) `.gitconfig`, `git/config` (deckt `.git/config` und
  `~/.config/git/config`) oder `config.worktree` enthält, oder das eine Konfigurations-Variable
  referenziert (`$GIT_CONFIG…` bzw. `${GIT_CONFIG…`, etwa ein Schreibziel `> "$GIT_CONFIG_GLOBAL"`);
- **(c)** eine Zuweisung, `export`, `declare`, `typeset`, `readonly`, `local` oder `unset` eines
  Namens der Freigabeliste (Abschnitt 4), die nicht unmittelbar Präfix des ausgewerteten
  git-Segments ist.

Damit ist `git config alias.ci commit && git ci -m x` geprüft, während
`git config user.name x && git st` unberührt bleibt (AC-7). Eine Datei, die ein Aufruf selbst als
Konfigurationsquelle nennt (`GIT_CONFIG_GLOBAL=/tmp/f`), prüft Abschnitt 4 unabhängig von ihrem
Namen; (b) deckt die üblichen Namen auch dann ab, wenn der Befehl sie nur beschreibt.

### 6. Arbeitsverzeichnis: `cd`-Modell (E5)

Aliase hängen an dem Verzeichnis, in dem git läuft. `cd` oder `pushd` mit genau einem literalen
Argument (kein `$`, Backtick oder Glob-Zeichen, beginnt nicht mit `-`; ein führendes `~` wird
expandiert) auf oberster Ebene wird als implizites `-C <pfad>` für alle späteren Segmente
modelliert; mehrere addieren sich wie verkettete `-C` (ein relativer Pfad gilt relativ zum
vorigen). So bleibt das häufige `cd B && git <alias>` präzise. Existiert das Verzeichnis nicht,
scheitert die Abfrage mit rc 128 und der Aufruf ist `unresolved`.

Das Arbeitsverzeichnis gilt dagegen als **unbekannt** — spätere Nicht-Builtins werden `unresolved` —
bei `cd` ohne Argument, `cd -`, `popd`, einem nicht-literalen Pfad und cd-Optionen; bei einem `cd`,
`pushd` oder `popd` direkt hinter einem Kontrollwort am Segmentanfang (`if`, `then`, `else`,
`elif`, `do`, `while`, `until`), denn ob es ausgeführt wird, hängt von einer Bedingung ab; und wenn
der Befehl irgendwo ein Subshell-, Pipeline- oder Hintergrund-Token enthält (`(`, `)`, `|`, `|&`,
`&`; ein Punktuations-Token mit Klammer zählt mit, `&&`, `||`, `;` und Umleitungen nicht) und
zugleich ein `cd`, `pushd` oder `popd` vorkommt — dann ist die Reichweite des Verzeichniswechsels
aus den Segmenten nicht bestimmbar.

Verschachtelte Shells (`sh -c`, `bash -c`, `eval`, Tiefe höchstens 2) erkennt der Resolver nach
denselben Merkmalen wie `_git_nested_subcommands` und löst sie auf (deren Grenze steht in den Known
Limitations, #298); ihr Kontext startet beim Modell-Stand an dieser Stelle (Verzeichnis, Taint),
ein `cd` darin wirkt nicht nach außen. Shell-Alias-Rümpfe (Abschnitt 8) führt git dagegen im
Wurzelverzeichnis des Arbeitsbaums aus, nicht im Aufrufverzeichnis: Ein relatives `cd` oder
`pushd` in einem Rumpf macht das Verzeichnis deshalb unbekannt (absolute Pfade und `~` bleiben
modellierbar).

### 7. Ketten und Optionen im Alias-Wert (E6)

Aufgelöst wird in einer Schleife: Unterbefehl, Alias-Wert (mit `shlex.split` zerlegt) und die
Argumente des Aufrufs. Bei jedem Schritt wird geprüft, ob ein Builtin erreicht ist (exakt,
case-sensitiv); dann ist die Kette zu Ende. Endet sie bei einem Namen, der weder Builtin noch
Alias ist (ein externes `git-<name>`), ist sie ebenfalls zu Ende, ohne `unresolved`. Die Schleife
führt eine Besucht-Menge (kleingeschriebene Namen) und bricht nach höchstens 8 Schritten ab. Eine
Schleife, ein leerer oder nicht zerlegbarer Wert, ein Unterbefehl mit Shell-Syntax (Abschnitt 2)
und das Überschreiten der Obergrenze ergeben `unresolved`; git selbst bricht bei einer Schleife
ab, ohne etwas auszuführen, unser Verhalten ist also die Obermenge.

**Optionen im Alias-Wert:** git erlaubt globale Optionen vor dem Unterbefehl eines Alias-Werts
(`alias.cx = "-c user.name=zz commit"` committet; `-C .` und `--no-pager` lehnt git mit „changes
environment variables“ ab). Der nächste Unterbefehl eines Werts wird deshalb genau wie beim äußeren
Aufruf bestimmt: Optionen samt Werten überspringen, Semantik von `_git_subcommand_after`. Ein
kleiner Helfer in `git_alias.py` liefert dafür Index und Wert, damit `hook_utils.py` unverändert
bleibt. Ein `-c` oder `--config-env` im Alias-Wert, dessen Schlüssel (case-insensitiv) mit `alias.`
oder `include` beginnt, ändert die Alias-Tabelle mitten in der Auflösung: `unresolved`.

**Ergebnis je Aufruf:** die Expansion als argv-Token-Liste
`["git", <Optionen des Werts>, <Builtin>, <Argumente>]` — Zurückserialisieren in Text ist
verlustbehaftet (ein Argument `&&` in einem Nicht-Shell-Alias würde zum Trenner) — und eine
Auflösungszeile wie `git c2 → git ci → git commit`.

### 8. Shell-Aliase (E7)

Ein Wert mit führendem `!` ist ein Shell-Alias: beliebiger Shell-Code, an den git die Argumente des
Aufrufs anhängt (`"$@"`). Der Rumpf bleibt Text, weil die Shell ihn parst:
`rumpf + " " + shlex.join(args)`. Er landet in `shell_bodies` und wird rekursiv aufgelöst
(git-Aufrufe im Rumpf, Tiefe höchstens 2 wie bei `sh -c`), mit denselben Regeln wie im äußeren
Aufruf — auch der Regel für Unterbefehle mit Shell-Syntax aus Abschnitt 2. Rümpfe erben die
Optionen des Elternaufrufs (git exportiert dafür `GIT_CONFIG_PARAMETERS`), teilen also seinen
Kontext und die gecachte Tabelle.

Folgen in `bash_gate.py`:
- Ein Shell-Alias gilt nicht mehr als „reiner git-Aufruf“: kein Schnellpfad und keine
  3a-Ausnahme. Das schließt die Geschwister-Lücke, dass `alias.x = !touch …user_approved…` als
  reiner git-Aufruf die Marker-Sperre umging.
- `scan_cmd` bekommt die Rümpfe angehängt, für 3a (Marker), 3b und 4 (Secrets). Die
  4b-Credential-Prüfung bekommt sie nicht: Rümpfe sind Nutzer-Konfiguration, kein Text des Agenten.
- Ein Commit im Rumpf wird über `is_git_subcommand(rumpf, "commit")` erkannt, einschließlich Fall 3
  der Drei-Fälle-Regel für nicht zerlegbare Rümpfe.

### 9. Commit-Menge #259 (E8)

Die #259-Commit-Menge hängt an der Aufrufform von `commit` (`-a`, Pfadangabe, `--amend`,
begleitendes `add` oder `stage`). Bei einem Alias steht sie teils in der Alias-Definition
(`cam = commit -a -m`), teils im Aufruf; ohne Kenntnis der Definition griffe die Unsicherheitsregel
(größte Menge). Deshalb bekommt `_commit_form(command, view=None)` die Sicht:

- Die Segmentliste ist `_git_segments(command)`, dazu die Token-Listen aus `view.expansions`
  direkt (sie beginnen mit `git`, die bisherige `commit`-Suche bleibt unverändert) und die Segmente
  der Shell-Rümpfe. Aus `cam = commit -a -m` wird so `-a` sichtbar.
- Ein begleitendes `add` zählt auch, wenn der Unterbefehl einer Expansion `add` ist oder ein Rumpf
  `add` enthält. `stage`, das Builtin-Synonym für `add`, zählt in allen drei Quellen — Befehlstext,
  Expansionen, Rümpfe — wie `add`; sonst verkleinerte ein Alias auf `stage` (`alias.s=stage`) die
  Commit-Menge, ein Alias-Bypass. Das schließt nebenbei heute offene #259-Lücken: Mit `a = add`
  liefert `git a neu.py && git commit -m x` heute `(False, False, False, False)`, und die neue,
  untrackte Datei fehlt in der Menge; dasselbe gilt für das wörtliche
  `git stage neu.py && git commit -m x`, das ab jetzt korrekt erfasst wird (Hinweis im CHANGELOG,
  Abschnitt 16).
- Unsicherheit — `view.unresolved` oder kein zerlegbarer Commit — ergibt wie bisher
  `(True, True, True, True)`, die größere Menge.
- `view` wird über `_commit_change_set(command, view=None)` und
  `_require_dialog_evidence(wf, verdict, command, view=None)` gereicht. Alle drei Parameter sind
  optional; ein Aufruf ohne Sicht verhält sich wie bisher.
- `_commit_content_files` und `_is_amend` (nur die Anzeige des E2E-Scopes, blockt nie) bleiben
  unverändert und sehen Alias-Argumente nicht.

### 10. Entscheidungsstellen und Ablauf in `main()` (E9)

| Stelle | Änderung |
|--------|----------|
| Schritt 2, Git-Schnellpfad | `git_only` ohne Shell-Aliase und `unresolved`; Fail-open-Zweig nur ohne `unresolved`; `committing` statt wörtlichem Commit |
| Schritt 3a, Marker-Ausnahme | `is_git_command = git_only` — ein Shell-Alias verliert die Ausnahme |
| Schritte 3a, 3b, 4 | laufen auf `scan_cmd` einschließlich der Shell-Rümpfe |
| Schritt 4b, Credentials | unverändert, nur auf `command` |
| Schritt 5, Commit-Gates | läuft bei `committing` statt bei wörtlichem `git commit`; 5c reicht die Sicht weiter |
| `_commit_form` und Folgefunktionen | bekommen die Sicht (Abschnitt 9) |
| `_is_whitelisted` | unverändert (Abschnitt 11) |

Neue Reihenfolge in `main()`:

```python
# 1. Stop-Lock → block                                          (unverändert)
view = _alias_view(command)              # NEU: genau einmal, nie werfend
# 2. Git-Schnellpfad
git_only = is_pure_git_command(command) and not (view.shell_bodies or view.unresolved)
if (not git_only and not git_subcommands(command) and command.lstrip().startswith("git ")
        and "git commit" not in command and not view.unresolved):
    git_only = True                      # Fail-open-Zweig, nur noch ohne unresolved
committing = (is_git_subcommand(command, "commit") or bool(view.unresolved)
              or any(_git_subcommand_after(t, 1) == "commit" for t in view.expansions)
              or any(is_git_subcommand(b, "commit") for b in view.shell_bodies))
if git_only and not committing:
    allow()
scan_cmd = strip_heredoc_bodies(command)          # plus "\n" + Rümpfe, falls vorhanden
# 3a/3b/4 auf scan_cmd (3a-Ausnahme: is_git_command = git_only); 4b weiter nur auf command
# 5. if workflow_enforced and committing:
#        Meldungszeile auf stderr, wenn der Commit nur über die Sicht erkannt wurde (Abschnitt 12)
#        5a/5b/5d wie bisher; 5c ruft _require_dialog_evidence(wf, verdict, command, view)
```

`committing` ist genau `is_git_subcommand(command, "commit")`, solange die Sicht leer ist — daran
hängt die Leitregel oben.

### 11. Whitelist bleibt unverändert (E10)

`_is_whitelisted` sieht weiter nur den Originaltext mit dem strengen `git_head_subcommands`; ein
Alias ist nie ein Whitelist-Treffer, und die Funktion ruft den Resolver nie auf. Über-Erkennung ist
dort die gefährliche Richtung, denn ein Whitelist-Treffer überspringt Prüfungen; Unter-Erkennung
heißt nur „zusätzlich prüfen“. Die davon unabhängige Lücke in 3b steht in #296 und bleibt außerhalb
dieses Umfangs.

### 12. Meldungen (E11)

Wird der Commit nur über die Sicht erkannt — der Befehl selbst enthält kein wörtliches
`git commit` —, schreibt `bash_gate.py` am Anfang von Schritt 5, vor den Commit-Gates, eine Zeile
auf stderr:

```
Commit erkannt über Alias: git ci → git commit
Unterbefehl nicht auflösbar (<Grund>): git <sub> — wird wie ein Commit geprüft. Ausweg: Unterbefehl ausschreiben (z. B. git commit statt git ci) oder den Aufruf auftrennen.
```

Die erste Form nennt die Auflösungszeile(n) der Sicht, deren Ziel `commit` enthält (Kette:
`git c2 → git ci → git commit`; Shell-Alias: `git sh1 → !git commit`). Die zweite gilt bei
`unresolved`: `<Grund>` sind die Einträge aus `view.unresolved` (mit `; ` verbunden), `<sub>` die
Unterbefehle aus `view.unresolved_subs`. Die bestehenden Block-Meldungen (5a bis 5c, die Marker-Meldung
aus 3a) bleiben unverändert.

### 13. Fehlerrichtungen (E12)

„Prüfen“ heißt: kein Schnellpfad, keine 3a-Ausnahme, Schritt 5 läuft.

| Situation | Ergebnis |
|-----------|----------|
| Builtin-Unterbefehl | Keine Abfrage, Verhalten wie bisher |
| Abfrage ok, kein Alias dieses Namens (auch ohne Repository, rc 1) | Durchlassen wie bisher |
| git fehlt, `OSError`, Timeout, rc weder 0 noch 1 | `unresolved`, also prüfen |
| Schleife, mehr als 8 Schritte, leerer oder nicht zerlegbarer Alias-Wert, `-c` oder `--config-env` mit `alias.`/`include` im Alias-Wert | `unresolved` |
| Shell-Syntax in einem nachgespielten Wert, unbekannte `--config-env`-Variable, `env` mit Optionen oder `sudo`, Zuweisung mit nicht bestimmbarer Reichweite | `unresolved` |
| Mehr als 3 Kontexte, Taint, unbekanntes Arbeitsverzeichnis | `unresolved` |
| Im Befehl benannte Konfigurationsdatei fehlt zur Hook-Zeit oder kommt in einem anderen Token des Befehls noch einmal vor; `GIT_CONFIG_PARAMETERS` mit `include` | `unresolved`, ohne Abfrage (Abschnitt 4) |
| Unterbefehl mit Shell-Syntax, auch in Alias-Wert oder Rumpf | `unresolved`, ohne Abfrage (Abschnitt 2) |
| Shell-Alias | Kein reiner git-Aufruf; Rumpf wird auf Commit, Marker und Secrets geprüft; nicht zerlegbarer Rumpf: Fall 3 auf dem Rumpf |
| Gesamtbefehl nicht zerlegbar | Nicht-Builtin-Kandidat: `unresolved` (Abschnitt 15); sonst unverändert |
| Ausnahme im Resolver | Intern gefangen: `unresolved`, falls die naive Kandidatensuche aus Abschnitt 15 ein Nicht-Builtin findet, sonst leere Sicht |
| `git_alias.py` nicht importierbar | Altes Verhalten (leere Sicht) plus stderr-Hinweis; Bash wird nie lahmgelegt |

Ein fälschliches „prüfen“ hat nur dort Wirkung, wo auch ein wörtliches `git commit` geprüft würde:
5c in Phase 6 bis 7 (Workflows vom Typ `bug` und `feature-fast` überspringen 5c), 5b bei aktivem
Workflow, 5a bei konfiguriertem `required_staged_files`; 5d blockt nie. Es entsteht nur bei
`unresolved`, also in seltenen Fällen, und hat einen dokumentierten Ausweg.

### 14. Budget und Cache

Höchstens 3 Abfragen pro Bash-Befehl. Der Cache-Schlüssel ist (modelliertes Verzeichnis,
nachgespielte Optionen, Env-Overlay); Ketten und wiederholte Unterbefehle im selben Kontext nutzen
die gecachte Tabelle, `git st && git lg` kostet also eine Abfrage. Ein vierter unterschiedlicher
Kontext wird `unresolved` (Grund: Budget), jeder weitere neue ebenso; Aufrufe in bereits
abgefragten Kontexten bleiben aus dem Cache auflösbar. Bei Timeout 2 s je Abfrage bremst ein
hängendes git den Befehl um höchstens 6 s.

### 15. Unzerlegbarer Gesamtbefehl

Liefert `_git_segments(command)` `None` — der Lexer scheitert an Quotes, die Bash versteht, `shlex`
aber nicht, etwa `$'it\'s'` —, zerlegt der Resolver den Befehl naiv nach Whitespace, sucht git-Tokens
und deren Unterbefehl (Semantik von `_git_subcommand_after`) und löst nichts auf. Ist einer dieser
Unterbefehle ein Nicht-Builtin, ist die Sicht `unresolved`, ohne Abfrage; Builtin-Befehle behalten
das alte Verhalten. Der Fail-open-Zweig in Schritt 2 greift deshalb nur noch, wenn die Sicht nicht
`unresolved` ist. Beispiel: `git ci -m $'it\'s'` ist gültiges Bash, für `shlex` aber unzerlegbar —
bisher Fail-open-Durchlass, künftig „prüfen“; `git status $'it\'s'` bleibt durchgelassen. Dieselbe
naive Kandidatensuche dient als Rückfall bei einer Ausnahme im Resolver (Abschnitt 13).

### 16. Doku und Verteilung

Konsumenten erhalten `git_alias.py` per `setup.py --update` (Glob über `core/hooks/*.py`) bzw. über
das Plugin; eine Migration ist nicht nötig. Eine Hook-Kopie ohne die Datei behält das alte Verhalten
plus stderr-Hinweis. Anker für AC-16:

- `docs/WORKFLOW_GUIDE.md`: Die Zeile „2. Reiner git-Befehl (kein commit)? → ALLOW (Fast Path)“ der
  `bash_gate.py`-Übersicht nennt die Alias-Auflösung (Anker: `Alias`).
- `CLAUDE.md`: je eine Zeile im Architektur-Baum und in „Wichtige Dateien“ nennt `git_alias.py` als
  Hilfsmodul ohne Hook (Anker: `git_alias.py` und `KEIN Hook` in derselben Zeile).
- `README.md`: eine Zeile im Architektur-Baum unter `core/hooks/`, analog zu
  `precondition_origins.py` (Anker: `git_alias.py` und `NOT a hook` in derselben Zeile).
- `CHANGELOG.md`, Abschnitt `[Unreleased]`: Eintrag zu #281 mit den neuen Block-Fällen und dem
  Nebeneffekt, dass auch ein wörtliches `git stage neu.py && git commit` jetzt in der Commit-Menge
  erfasst wird (Anker: `#281`, `Alias`, `nicht auflösbar` und `stage`).

## Expected Behavior

- **Input:** Bash-Befehl des Tool-Aufrufs, cwd und Umgebung des Hooks, aktiver Workflow-State und die Alias-Konfiguration an dem Ort, an dem der Aufruf läuft.
- **Output:** `bash_gate.py` endet mit Exit 0 oder 2; bei einem nur über die Sicht erkannten Commit steht zusätzlich eine Zeile auf stderr, die Block-Meldungen bleiben unverändert; `resolve_git_aliases` liefert eine `GitAliasView`.
- **Side effects:** Höchstens drei lesende `git config`-Abfragen je Bash-Befehl und nur für Nicht-Builtin-Unterbefehle; die Abfrage schreibt nichts und führt nie Code aus dem Befehlstext aus; sonst keine.
- **Builtins:** Ein Builtin-Unterbefehl löst nie eine Abfrage aus und wird nie von einem Alias überschattet; Alias-Namen gelten case-insensitiv, Builtin-Namen exakt.
- **Unterbefehl:** Ein Unterbefehl, dessen Name erst zur Laufzeit feststeht (`git $CMD`), wird ohne Abfrage als `unresolved` geprüft — auch in Alias-Werten und Shell-Rümpfen.
- **Alias auf `commit`:** Er gilt wie `commit` (lokal, global, `include.path`, `-c`, `--config-env`, Umgebung, Ketten, Optionen im Alias-Wert), seine Argumente bestimmen die #259-Commit-Menge, und ein begleitendes `add` oder `stage` zählt auch über Alias und Rumpf.
- **Shell-Aliase:** Ein Shell-Alias ist kein reiner git-Aufruf; sein Rumpf wird auf Commit, Marker-Schreiben und Secrets geprüft.
- **Kontext:** Nachgespielt wird der Kontext des echten Aufrufs (cwd, `-C`, `cd`, `-c`, freigegebene Präfix-Zuweisungen); eine Alias-Änderung im selben Befehl, eine im Befehl benannte Konfigurationsdatei, die es noch nicht gibt oder die derselbe Befehl schreibt, oder ein unbestimmbarer Kontext macht spätere Nicht-Builtins `unresolved`.
- **Fehlerrichtung:** Was sich nicht sicher auflösen lässt, wird wie ein Commit geprüft (kein Schnellpfad, Schritt 5 läuft), mit Wirkung nur dort, wo auch ein wörtlicher Commit geprüft würde.
- **Invarianz:** Bei leerer Sicht verhält sich `bash_gate.py` exakt wie vor dieser Änderung, und `_is_whitelisted` sieht keine Aliase.

## Error Handling

- **Commit über Alias erkannt:** stderr-Zeile `Commit erkannt über Alias: git ci → git commit`
  (Kette: `git c2 → git ci → git commit`), danach die bestehenden Block-Meldungen unverändert,
  etwa die 5c-Meldung „Adversary verdict missing or not VERIFIED“. Weg wie bei jedem Commit:
  Adversary-Dialog und VERIFIED; Notbremse: Override-Token (Commit-Gate, wie bisher).
- **Unterbefehl nicht auflösbar:** die zweite stderr-Zeile aus Abschnitt 12
  (`Unterbefehl nicht auflösbar (<Grund>): git <sub> — wird wie ein Commit geprüft. Ausweg: …`) mit dem
  Ausweg „Unterbefehl ausschreiben (z. B. git commit statt git ci) oder den Aufruf auftrennen“.
  Gründe: Abfrage gescheitert (rc, Timeout, git fehlt), Schleife, mehr als 8 Schritte, leerer oder
  nicht zerlegbarer Wert, Taint, Shell-Syntax im nachgespielten Wert oder im Unterbefehl,
  im Befehl benannte Konfigurationsdatei, die es noch nicht gibt oder die derselbe Befehl erneut
  nennt, unbekanntes Arbeitsverzeichnis, `env` mit Optionen oder `sudo`, Budget, Gesamtbefehl nicht
  zerlegbar, interner Fehler.
- **Modul fehlt:** `git_alias.py` nicht importierbar — eine stderr-Zeile nennt `git_alias`, die
  Sicht bleibt leer, `bash_gate.py` läuft mit dem alten Verhalten weiter.
- **Marker über Shell-Alias:** Der Rumpf eines Shell-Alias, der einen Freigabe-Marker schreibt,
  löst die unveränderte Marker-Meldung aus Schritt 3a aus; die Datei entsteht nicht.
- **Preis der Vorsicht:** Ein nachgespielter Wert mit Shell-Syntax (`git -C "$REPO" st`), ein
  Unterbefehl mit Shell-Syntax (`git $CMD`), eine im Befehl benannte Konfigurationsdatei, die es
  noch nicht gibt (`GIT_CONFIG_GLOBAL=/tmp/neu git st`), und ein Aufruf über `sudo` oder `env -i`
  machen Nicht-Builtin-Unterbefehle `unresolved` — geprüft statt durchgelassen. Ausweg: den Wert
  literal angeben, die Datei vorher in einem eigenen Aufruf anlegen, den Unterbefehl ausschreiben
  oder den Aufruf auftrennen.

## Known Limitations

- **Externe `git-<name>`** im `PATH` haben bei git Vorrang vor Aliasen und werden nicht befragt;
  siehe #297.
- **Weitere Code-Ausführung in „reinem git“:** `-c core.pager|editor|sshCommand`,
  `diff.external`, `credential.helper=!…`; `rebase --exec`, `bisect run`, `submodule foreach`,
  `difftool -x`, `mergetool`, `filter-branch`; git-Hooks. Siehe #297.
- **Commits ohne `commit`:** `merge`, `cherry-pick`, `revert`, `am` und `pull` erzeugen Commits
  ohne Gate. Das ist eine Produktentscheidung, siehe #297.
- **Verschleierte Config-Schreibzugriffe im selben Aufruf:** Erfasst sind nur Wege, die eine im
  Befehl benannte Konfigurationsquelle (Abschnitt 4) oder einen üblichen Dateinamen (Abschnitt 5)
  nennen. Nicht erfasst sind wirklich verschleierte Wege: zusammengesetzte Pfade (`$d/$f`),
  Schreiben per Skript ohne Nennung des Pfads und das Überschreiben einer Datei, die die bestehende
  Konfiguration schon per `include.path` einbindet (`printf … > inc.cfg && git ci`).
- **Nicht aufgelöste Ausweichwege:** vorsätzlich manipuliertes git (wie in der #259-Spec);
  `source` und eine Shell-Funktion namens `git`; ein Unterbefehl aus stdin (`… | xargs git`);
  Schachtelung tiefer als 2; ein bedingt ausgeführtes `cd` (`[ -d B ] && cd B; git ci`), das das
  Modell als ausgeführt unterstellt; Race-Condition bei parallel ausgeführten Tool-Aufrufen. Die
  Sicht ist eine Momentaufnahme vor dem Befehl.
- **Shell-Aufrufe mit zusammengesetzten oder weiteren Flags** (`bash -lc`, `sh -ec`,
  `bash --login -c`): `_git_nested_subcommands` erkennt nur ein `-c` unmittelbar hinter dem
  Shell-Namen. Das ist eine vorbestehende Lücke (Issue #298), bewusst nicht Teil von #281. Der
  Resolver folgt derselben Verschachtelungs-Erkennung und hat dieselbe Lücke; beim Fix von #298 ist
  er mit anzugleichen.
- **Nicht zerlegbare Gesamtbefehle:** Mit Nicht-Builtin-Kandidat werden sie jetzt geprüft; ohne
  Kandidaten bleibt der Fail-open-Durchlass aus #1431 unverändert.
- **`cd`-Modell:** Es kennt nur literale Pfade auf oberster Ebene. `cd` ohne Argument, `cd -`,
  `popd`, nicht-literale Pfade, ein `cd` hinter einem Kontrollwort und jeder Verzeichniswechsel in
  Verbindung mit Subshell, Pipeline oder Hintergrund machen das Verzeichnis unbekannt, der
  Unterbefehl wird geprüft.
- **Andere Hooks:** Alias-Rümpfe sind für `secrets_guard.py` und `secret_egress_guard.py`
  unsichtbar, denn beide lesen nur den Befehlstext.
- **Whitelist-Gefälle:** Solange #296 offen ist, wird `git ci … .claude/settings.json` geprüft, das
  wörtliche `git commit …` dagegen nicht. Dieses Gefälle bleibt bewusst stehen: Die Whitelist darf
  nicht aufgeweicht werden.
- **Ältere git-Versionen:** `GIT_BUILTINS` entspricht git 2.43. Auf git älter als 2.43 wird ein
  Alias, dessen Name dort noch kein Builtin ist, aber in der Liste steht (etwa `diagnose` oder
  `hook`), nicht aufgelöst. Neuere git-Versionen mit zusätzlichen Builtins führen nur zu
  Über-Erkennung.
- **Umgebung:** Die Abfrage sieht die Hook-Umgebung; die Shell des Bash-Tools kann abweichen
  (Profil- und Shell-Snapshot-Exporte, `CLAUDE_ENV_FILE`). Dann kann die Abfrage eine andere
  globale Konfiguration sehen als der echte Aufruf.
- **Ablösung einer #259-Grenze:** Der Satz in den Known Limitations von
  `fix-259-adversary-diff-binding.md`, git-Aliase (z. B. `git ci`) würden von der
  `git add`-Erkennung „nicht gezielt erfasst“, war zu eng: Tatsächlich umging ein Alias das ganze
  Commit-Gate. Er ist mit dieser Spec überholt (der `git mv`-Teil des Satzes gilt weiter). Die
  #259-Spec bleibt aus den unter „Bewusst unverändert“ genannten Gründen unverändert.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Die Reproduktion aus #281 — `git config alias.ci commit` mit `git ci -m x` und inline
      `git -c alias.ci=commit ci -m x` — wird im gesperrten Zustand über das echte `bash_gate.py`
      blockiert (Exit 2) statt durchgelassen
- [ ] Alltägliche Aliase (`git st`, `git lg`) und alle Builtins laufen wie bisher; Builtins
      lösen keinen zusätzlichen git-Prozess aus (gemessen, AC-9)
- [ ] Regressionslauf `python3 -m pytest tests/ -q` ist grün
- [ ] `python3 scripts/ci_spec_gate.py --base origin/main` ist grün

## Acceptance Criteria

**Gesperrter Zustand** (gemeinsame Vorbedingung, wo eine AC nichts anderes nennt): hermetisches
echtes Repo, aktiver Workflow (Full Process, `workflow_type: feature`) in `phase6_implement` ohne
Verdict, gestagte Änderung; geprüft über das echte `bash_gate.py`. Ein wörtliches `git commit -m x`
endet darin schon heute mit Exit 2 (Schritt 5c).

- **AC-1:** Given der gesperrte Zustand und ein lokales `alias.ci=commit` / When `bash_gate.py`
  `git ci -m x` prüft (die Reproduktion aus #281) / Then Exit 2, und stderr enthält die bestehende
  5c-Meldung („Adversary verdict missing or not VERIFIED“) sowie die Auflösung
  `git ci → git commit`.
  - Test: test_ac1_local_alias_commit_blocks — in tests/test_git_alias_commit_gate_281.py

- **AC-2:** Given der gesperrte Zustand und ein Alias auf `commit`, der aus einer der folgenden
  Quellen stammt / When `bash_gate.py` `git ci -m x` prüft (bei Quelle h den Aufruf
  `git -c alias.dup=commit dup -m x`) / Then Exit 2 für jede Quelle: (a) global über
  `GIT_CONFIG_GLOBAL` in der Hook-Umgebung; (b) per `include.path` in der lokalen Konfiguration;
  (c) inline `git -c alias.ci=commit ci -m x` (zweite Reproduktionsform aus #281); (d) Präfix
  `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit git ci -m x`;
  (e) `ZZ=commit git --config-env=alias.ci=ZZ ci -m x`;
  (f) `env GIT_CONFIG_GLOBAL=<datei> git ci -m x` mit vorhandener Datei, die den Alias trägt;
  (g) eine Hook-Umgebung mit
  `GIT_CONFIG=<datei ohne Aliase>` bei lokalem `alias.ci=commit` (die Abfrage ignoriert
  `GIT_CONFIG`, wie es `git ci` tut); (h) ein lokal auf `log` gesetztes `alias.dup`, das der
  Inline-`-c` desselben Aufrufs überschreibt (der zuletzt gelistete Wert gilt, hier die
  Kommandozeile).
  - Test: test_ac2_alias_sources_block (parametrisiert über a bis h) — in tests/test_git_alias_commit_gate_281.py

- **AC-3:** Given der gesperrte Zustand in Repo A und `alias.ci=commit` nur in der Konfiguration
  von Repo B (A definiert keinen Alias) / When `bash_gate.py` mit cwd in A `git -C B ci -m x`,
  `cd B && git ci -m x`, `bash -c "cd B && git ci -m x"` bzw. `cd "$X" && git ci -m x` prüft /
  Then Exit 2 in allen vier Fällen: Die Abfrage läuft dort, wo der Aufruf läuft (nachgespieltes
  `-C`, modelliertes `cd`, auch in der verschachtelten Shell), und ein nicht bestimmbares
  Verzeichnis (`$X`) macht den Unterbefehl `unresolved`, statt ihn im falschen Repo nachzuschlagen.
  - Test: test_ac3_context_replay_other_repo — in tests/test_git_alias_commit_gate_281.py

- **AC-4:** Given der gesperrte Zustand mit lokalem `alias.ci=commit` bzw. `alias.status=commit` /
  When `git CI -m x` bzw. `git STATUS -m x` geprüft wird / Then Exit 2 in beiden Fällen:
  Alias-Namen gelten case-insensitiv, ein Builtin nur in exakter Schreibweise (`git status` bleibt
  der Builtin, `git STATUS` ist keiner und wird wie in git als Alias aufgelöst).
  - Test: test_ac4_alias_names_case_insensitive — in tests/test_git_alias_commit_gate_281.py

- **AC-5:** Given der gesperrte Zustand / When (a) `alias.c2=ci` plus `alias.ci=commit` mit
  `git c2 -m x`, (b) `alias.cx="-c user.name=zz commit"` mit `git cx -m x` und (c) die Schleife
  `alias.l1=l2`, `alias.l2=l1` mit `git l1` geprüft werden / Then Exit 2 in allen drei Fällen
  (Kette, Optionen im Alias-Wert, Schleife als `unresolved`); bei (c) nennt stderr den Grund und den
  Ausweg.
  - Test: test_ac5_chains_option_values_and_loops — in tests/test_git_alias_commit_gate_281.py

- **AC-6:** Given der gesperrte Zustand und Shell-Aliase / When `git sh1 -m x` mit
  `alias.sh1="!git commit"`, `git mk` mit `alias.mk="!touch .claude/user_approved_validation_x"`
  bzw. `git hi` mit `alias.hi="!echo hi"` geprüft wird / Then Exit 2 (Commit im Rumpf erkannt),
  Exit 2 mit der Marker-Meldung aus Schritt 3a, ohne dass die Marker-Datei entsteht, bzw. Exit 0
  für den harmlosen Alias.
  - Test: test_ac6_shell_aliases — in tests/test_git_alias_commit_gate_281.py

- **AC-7:** Given der gesperrte Zustand / When (a) `git config alias.ci commit && git ci -m x`,
  (b) `export GIT_CONFIG_GLOBAL=<datei mit ci=commit>; git ci -m x`, (c)
  `git config user.name y && git st` (mit `alias.st=status`) und (d)
  `printf '[alias]\n\tci = commit\n' > <tmp>/f && GIT_CONFIG_GLOBAL=<tmp>/f git ci -m x` (die Datei
  `<tmp>/f` gibt es zur Hook-Zeit noch nicht) geprüft werden / Then Exit 2 für (a), (b) und (d) —
  die Abfrage sähe den Stand vor dem Befehl, die Änderung im selben Aufruf und eine im Befehl
  benannte, noch nicht vorhandene Konfigurationsdatei machen den späteren Nicht-Builtin
  `unresolved` — und Exit 0 für (c) (keine Alias-Änderung, kein Taint).
  - Test: test_ac7_same_call_changes_taint — in tests/test_git_alias_commit_gate_281.py

- **AC-8:** Given der gesperrte Zustand mit `alias.st=status`, `alias.lg="log --graph --oneline"`
  und `alias.status=commit` / When `git st`, `git lg` bzw. `git status` geprüft werden / Then
  Exit 0 in allen drei Fällen: keine Über-Erkennung, und ein Alias auf einen Builtin-Namen bleibt
  wirkungslos wie in git.
  - Test: test_ac8_harmless_aliases_pass — in tests/test_git_alias_commit_gate_281.py

- **AC-9:** Given ein `git`-Wrapper im `PATH`, der jede Abfrage `config -z --get-regexp`
  protokolliert, und (Unit) ein injizierter Runner / When `git status`, `git add f`, `git diff`
  und `git commit -m x` (ohne Workflow) sowie `git st && git lg` im selben Kontext geprüft werden
  und ein Befehl vier verschiedene Kontexte anspricht, nämlich
  `git -C a st; git -C b st; git -C c st; git -C d st` / Then lösen die vier Builtin-Befehle null
  Abfragen aus, `git st && git lg` genau eine, und der vierte Kontext ist `unresolved` (Budget von
  drei Abfragen).
  - Test: test_ac9_builtins_cost_no_lookup (E2E mit Wrapper), test_ac9_cache_and_budget (Unit mit injiziertem Runner) — in tests/test_git_alias_commit_gate_281.py

- **AC-10:** Given ein `git`-Wrapper im `PATH`, der `config` mit rc 128 scheitern lässt / When im
  gesperrten Zustand `git st` bzw. `git status` geprüft wird, und `git st` zusätzlich ohne aktiven
  Workflow / Then `git st` Exit 2 mit „nicht auflösbar“ und dem Ausweg auf stderr, `git status`
  Exit 0 (Builtin, keine Abfrage) und `git st` ohne aktiven Workflow Exit 0.
  - Test: test_ac10_lookup_failure_checks_only_with_workflow — in tests/test_git_alias_commit_gate_281.py

- **AC-11:** Given ein Befehl mit `GIT_TRACE=<pfad>` als Präfix, ein ausführbares `./git` im cwd,
  das beim Start eine Sentinel-Datei schreibt, und ein Runner-Recorder / When der Hook
  `GIT_TRACE=<pfad> git -c alias.ci=commit ci -m x` bzw. `./git ci -m x` (mit lokalem
  `alias.ci=commit`) prüft / Then Exit 2 in beiden Fällen, die Datei unter `<pfad>` wird vom Hook
  nicht angelegt, das Sentinel entsteht nicht (`./git` wird nie ausgeführt), und die an den Runner
  übergebene Umgebung enthält weder `GIT_TRACE*` noch `GIT_CONFIG`, auch wenn die Hook-Umgebung
  sie enthält (Unit).
  - Test: test_ac11_lookup_never_runs_foreign_code — in tests/test_git_alias_commit_gate_281.py

- **AC-12:** Given Phase 7, Verdict VERIFIED und ein gestempeltes Dialog-Artefakt, das nur B
  zitiert und hasht; B ist gestagt, C ist getrackt geändert, nicht gestagt und nicht zitiert /
  When `git ci -m x` (mit `alias.ci=commit`), `git cam msg` (mit `alias.cam="commit -a -m"`),
  `git a NEU.py && git ci -m x` (mit `alias.a=add`) und `git s NEU.py && git ci -m x` (mit
  `alias.s=stage`) geprüft werden, NEU.py untrackt und nicht zitiert / Then Exit 0 für `git ci`
  (Index-Form, C gehört nicht zum Commit), Exit 2 für `git cam` (die Argumente aus dem Alias-Wert
  machen daraus die Arbeitsbaum-Form, stderr nennt C) und Exit 2 für die beiden Fälle mit `add`-
  bzw. `stage`-Alias (stderr nennt NEU.py).
  - Test: test_ac12_commit_set_follows_alias_arguments — in tests/test_git_alias_commit_gate_281.py

- **AC-13:** Given `alias.ci=commit` in der Konfiguration / When
  `bash_gate._is_whitelisted("git ci -m x")` mit einem auf eine werfende Funktion gepatchten
  Resolver aufgerufen wird / Then ist das Ergebnis False und es tritt kein Fehler auf: Die
  Whitelist wertet nur den Originaltext mit `git_head_subcommands`, ruft den Resolver nie auf und
  hält einen Alias nie für einen Whitelist-Treffer.
  - Test: test_ac13_whitelist_ignores_aliases — in tests/test_git_alias_commit_gate_281.py

- **AC-14:** Given (a) ein Resolver-Aufruf, in dem intern eine Ausnahme auftritt, und (b) eine
  Hook-Kopie ohne `git_alias.py` / When (a) mit einem gesehenen Nicht-Builtin bzw. ohne, (b)
  `git st` im gesperrten Zustand über das echte `bash_gate.py` geprüft wird / Then ist die Sicht
  bei (a) `unresolved`, wenn ein Nicht-Builtin gesehen wurde, sonst leer (Unit), und bei (b) ist
  das Ergebnis Exit 0 wie bisher, mit einem stderr-Hinweis auf die fehlende Datei.
  - Test: test_ac14_resolver_failure_modes — in tests/test_git_alias_commit_gate_281.py

- **AC-15:** Given der gesperrte Zustand und ein Befehl, dessen Unterbefehl nicht bestimmbar ist —
  für `shlex` unzerlegbar oder erst zur Laufzeit bekannt / When `git ci -m $'it\'s'`,
  `git status $'it\'s'` bzw. `CMD=commit; git $CMD -m x` geprüft wird / Then Exit 2 für den
  Alias-Befehl (bisher Fail-open-Durchlass, jetzt geprüft), Exit 0 für den Builtin-Befehl wie
  bisher und Exit 2 für `git $CMD` (der Name des Unterbefehls steht erst zur Laufzeit fest:
  `unresolved`, ohne Abfrage).
  - Test: test_ac15_undeterminable_subcommand_is_checked — in tests/test_git_alias_commit_gate_281.py

- **AC-16:** Given die für #281 vorgesehenen Doku-Stellen (`docs/WORKFLOW_GUIDE.md`, `CLAUDE.md`,
  `README.md`, `CHANGELOG.md`) / When die Implementierung abgeschlossen ist / Then nennt die
  Fast-Path-Zeile der `bash_gate.py`-Übersicht in `docs/WORKFLOW_GUIDE.md` die Alias-Auflösung,
  `CLAUDE.md` (Architektur-Baum und „Wichtige Dateien“) und `README.md` (Baum) listen
  `git_alias.py` als Hilfsmodul ohne Hook, und `CHANGELOG.md` nennt unter `[Unreleased]` #281, die
  neuen Block-Fälle und den Nebeneffekt, dass ein begleitendes `git stage` jetzt in der
  Commit-Menge zählt.
  - Test: test_ac16_docs_mention_alias_resolution — in tests/test_git_alias_commit_gate_281.py

- **AC-17:** Given eine installierte git-Version ab 2.43 / When `GIT_BUILTINS` mit
  `git --list-cmds=builtins` verglichen wird / Then ist `GIT_BUILTINS` eine Teilmenge der
  installierten Builtins; ohne git oder bei git älter als 2.43 wird der Test übersprungen.
  - Test: test_ac17_builtin_list_within_installed_git — in tests/test_git_alias_commit_gate_281.py

## Test Plan

Automatische Tests (jeweils an eine oder mehrere Acceptance Criteria oben gebunden), alle in der
neuen Datei `tests/test_git_alias_commit_gate_281.py`:

- **E2E gegen das echte `bash_gate.py`** (AC-1 bis AC-8, AC-10 bis AC-12, AC-14 (b), AC-15, AC-9
  für Builtins): Subprozess mit Hook-JSON über stdin bzw. `CLAUDE_TOOL_INPUT`, in hermetischen
  echten Repos nach dem Muster von `tests/test_adversary_coverage_gate_259.py` (`_env()` ohne
  `GIT_*`- und Sitzungsvariablen, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL` nur pro Test auf eine
  Datei; Workflow-State in Phase 6 ohne Verdict bzw. Phase 7 mit VERIFIED und gestempeltem
  Dialog; kleine eigene Hilfsfunktionen, kein Import zwischen Testdateien) und
  `tests/test_git_invocation_detection.py` (echtes Gate gegen eine Sandbox). Ein `git`-Wrapper
  vorn im `PATH` protokolliert Abfragen (AC-9) bzw. lässt `config` scheitern (AC-10). Ein
  zweites Repo B und ein ausführbares `./git` tragen AC-3 und AC-11.
- **Unit mit injiziertem Runner, ohne git** (AC-9 Cache und Budget, AC-11 Umgebung, AC-14 (a)):
  Der Runner protokolliert `argv`, cwd und Umgebung. Die Ausnahme für AC-14 (a) löst ein Runner
  bzw. ein `environ`-Objekt aus, das etwas anderes als `OSError` oder `TimeoutExpired` wirft —
  einmal mit `git st` (Nicht-Builtin), einmal mit `git status` (nur Builtin). Dazu Matrizen für
  die Einzelregeln aus den Abschnitten 2 bis 9: Vorrang (zuletzt gelisteter Wert), Nachspielen
  von `-C` und `-c`, Übersetzung von `--config-env`, Env-Freigabeliste, im Befehl benannte
  Konfigurationsquellen (Datei fehlt; Datei existiert und wird erneut genannt; Datei existiert
  ohne weitere Nennung und bleibt auflösbar; Wert aus der Hook-Umgebung ausgenommen; relativer
  Pfad gegen `cd`-Kette und `-C`; `-c include.path`, `--config-env` und
  `GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n`; `GIT_CONFIG_PARAMETERS` mit `include`; verschachtelte
  Shell), Taint (a) bis (c) einschließlich eines Schreibziels `> "$GIT_CONFIG_GLOBAL"`, Unterbefehl
  mit Shell-Syntax (`$CMD`, `$(…)`, Glob, Klammer-Expansion, Backtick-Trenner; im Alias-Wert; im
  Rumpf), `cd`-Modell (literal, unbekannt, Subshell, Kontrollwort, relatives `cd` im
  Shell-Alias-Rumpf), `env` mit Optionen und
  `sudo`, Kette, Schleife, Obergrenze, Schatten-Regel, Groß- und Kleinschreibung, leere und nicht
  zerlegbare Werte, `-z` mit Zeilenumbruch im Wert, Rumpf-Aufbau und `_commit_form`-Faltung
  (einschließlich `stage` in Befehlstext, Expansion und Rumpf).
- **In-process und Text** (AC-13, AC-16, AC-17): `_is_whitelisted` mit gepatchtem Resolver, die
  Doku-Anker aus Abschnitt 16, der Drift-Test der Builtin-Liste.
- **Testaufbau als GIVEN/WHEN/THEN:**
  - GIVEN das gesperrte Repo mit lokalem `alias.ci=commit` WHEN `bash_gate.py` `git ci -m x` prüft
    THEN Exit 2 mit `git ci → git commit` auf stderr (AC-1).
  - GIVEN ein Runner-Recorder WHEN `git st && git lg` aufgelöst wird THEN genau ein Aufruf mit
    `config -z --get-regexp` und ohne `GIT_TRACE*`/`GIT_CONFIG` in der Umgebung (AC-9, AC-11).
  - GIVEN ein `git`-Wrapper, der `config` scheitern lässt WHEN `git st` im gesperrten Zustand
    geprüft wird THEN Exit 2, für `git status` Exit 0 (AC-10).
  - GIVEN eine Konfigurationsdatei `f`, die es zur Hook-Zeit nicht gibt WHEN
    `GIT_CONFIG_GLOBAL=f git st` aufgelöst wird THEN `unresolved`, ohne Abfrage (AC-7).
- **Regressionswächter, unverändert grün:** `tests/test_git_invocation_detection.py`,
  `tests/test_adversary_coverage_gate_259.py`, `tests/test_adversary_evidence_gate_253.py`,
  `tests/test_bash_gate_false_positives.py`, `tests/test_bash_gate_freetext_fixes_64_75.py`,
  `tests/test_bash_gate_worktree_commit_155.py`, `tests/test_gate_fixes_26_38_34.py`,
  `tests/test_selfexplaining_gates.py`.
- Regressionslauf: `python3 -m pytest tests/ -q`.
- Server-Check: `python3 scripts/ci_spec_gate.py --base origin/main`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Keine neue Architektur — das Commit-Gate bekommt eine weitere Eingabe, eine
  Alias-Sicht; seine Regeln und Gates bleiben dieselben. Vier tragende Festlegungen:
  1. **Eigener Resolver statt Umbau der reinen Text-Parser.** `hook_utils` bleibt eine Sammlung
     reiner `(command) -> …`-Funktionen ohne cwd, Umgebung und Prozessaufruf; das neue
     `git_alias.py` trägt allein Kontext, Abfrage und Shell-Rümpfe. So bleiben die Bestandstests
     hermetisch, und ein Fehler im Resolver kann die Parser nicht beschädigen.
  2. **Statische Builtin-Liste plus Drift-Test statt Laufzeit-Abfrage.** `git --list-cmds=builtins`
     bei jedem git-Befehl kostete einen Prozess im heißen Pfad und brächte einen neuen
     Fehlermodus; die statische Liste plus AC-17 kostet nichts, und ihre Schwäche (neuere
     git-Versionen) wirkt nur als Über-Erkennung.
  3. **Kontext-Nachspielen mit Env-Freigabeliste.** Die Abfrage läuft mit derselben Konfiguration
     wie der echte Aufruf (cwd, `-C` und `cd`, `-c`, `--config-env`, freigegebene
     Präfix-Zuweisungen), aber ohne jede Nebenwirkung: Nur Namen der Freigabeliste kommen durch,
     `GIT_TRACE*` und `GIT_CONFIG` nie, und `argv[0]` ist nie ein Pfad aus dem Befehlstext. Weil
     die Abfrage nur den Stand vor dem Befehl sieht, macht eine im Befehl benannte
     Konfigurationsdatei, die es noch nicht gibt oder die derselbe Befehl schreibt, den Aufruf
     `unresolved`.
  4. **Fehlerrichtung „prüfen“, wirksam nur dort, wo auch ein wörtlicher Commit geprüft würde; die
     Whitelist bleibt streng.**
     Was sich nicht sicher auflösen lässt — auch ein Unterbefehl, dessen Name erst zur Laufzeit
     feststeht —, verliert Schnellpfad und 3a-Ausnahme und läuft durch die Commit-Gates, mit
     Wirkung nur dort, wo auch ein wörtlicher Commit geprüft würde. Die Whitelist sieht keine
     Aliase, weil Über-Erkennung dort die gefährliche Richtung ist.

## Changelog

- 2026-09-30: Initial spec created
