# Mini-Spec: Haupt-Ordner nach Workflow-Abschluss nachziehen (#169)

## Problem

Jede Session muss im Worktree laufen. Ein Workflow endet per Pull Request auf `main` (GitHub);
der Haupt-Ordner auf der Platte bleibt auf altem Stand. Ihn zu aktualisieren ist aus keiner Session
vorgesehen: im Haupt-Ordner sperrt der Guard `Bash`, und in einer Worktree-Session verweigert
Claude Code selbst jeden Git-Befehl, der auf den Haupt-Ordner zeigt (`git -C <Haupt-Ordner> …`).

## Grenze dieser Änderung

Die Sperre von Claude Code für Worktree-Sessions liegt außerhalb des Frameworks und bleibt. Der
Weg ist daher: **neue Session im Haupt-Ordner öffnen, ein Befehl.** Aus einer Worktree-Session
heraus lässt sich der Haupt-Ordner weiterhin nicht nachziehen.

## Was ändert sich

- `core/hooks/session_singleton_guard.py`: neuer CLI-Modus `sync-main`
  (`python3 .claude/hooks/session_singleton_guard.py sync-main`). Er führt nur aus:
  1. Preflight: cwd ist kein Worktree, sondern die Wurzel eines Git-Repos; Branch hat einen Upstream;
     keine Änderungen an versionierten Dateien (`git status --porcelain --untracked-files=no` leer).
  2. `git fetch <remote>` für den Upstream-Remote.
  3. `git merge --ff-only <upstream>`.
  Jeder Abbruchgrund liefert eine klare deutsche Meldung und lässt den Ordner unverändert.
- `_do_guard`: im Haupt-Ordner wird `Bash` durchgelassen, wenn der Befehl **genau** dieser
  `sync-main`-Aufruf ist (kein Shell-Metazeichen, exakt drei Tokens, Interpreter `python`/`python3`,
  Skriptpfad löst auf den laufenden Guard oder auf `<cwd>/.claude/hooks/session_singleton_guard.py`
  auf). Freie `git`-Befehle bleiben gesperrt.
- `core/commands/70-deploy.md`: Abschlussschritt „Haupt-Ordner nachziehen".
- `docs/specs/session-singleton-guard.md`, `CHANGELOG.md`, Version 3.27.0.

## Was darf sich nicht ändern

- Alle anderen schreibenden Tools (`Edit`, `Write`, `MultiEdit`, `Task`, `Agent`) und jeder andere
  `Bash`-Befehl bleiben im Haupt-Ordner gesperrt.
- Lesende Tools werden weiter nie blockiert; Worktree-Sessions unverändert.
- `sync-main` überschreibt nie Arbeit: kein `reset`, `checkout`, `stash`, `pull --rebase`, `--force`.

## Wo ich für dich entschieden habe

- **Eigener Modus statt freier Git-Befehle im Guard:** Ausnahmen wie `git pull --ff-only` wären über
  Flags (`-c`, `--upload-pack`, `--exec`) zur Code-Ausführung missbrauchbar und erkennen einen
  schmutzigen Ordner nicht. Ein fester Befehl mit eigener Vorprüfung hat den kleinsten Wirkungsradius.
- **`fetch` + `merge --ff-only`** statt `pull`: unabhängig von der `pull.rebase`-Konfiguration des Users.
- **Nicht versionierte Dateien blockieren nicht:** kollidieren sie mit eingehenden Dateien, bricht
  `merge --ff-only` selbst ab; ohne Kollision ist nichts gefährdet.

## Acceptance Criteria

- **AC-1:** Given eine Session im Haupt-Ordner, When Bash den exakten `sync-main`-Aufruf ausführt,
  Then blockt der Guard nicht.
- **AC-2:** Given eine Session im Haupt-Ordner, When Bash etwas anderes ausführt (auch
  `git pull --ff-only`, `sync-main; rm -rf x`, `sync-main --foo`, fremder Skriptpfad), Then blockt
  der Guard weiterhin.
- **AC-3:** Given `Edit`/`Write`/`Task` im Haupt-Ordner, Then bleiben sie blockiert.
- **AC-4:** Given ein Haupt-Ordner hinter dem Upstream und sauber, When `sync-main` läuft, Then
  steht der Ordner danach auf dem Upstream-Stand.
- **AC-5:** Given ein Haupt-Ordner mit geänderter versionierter Datei, When `sync-main` läuft,
  Then wird nichts verändert und die Meldung nennt den Grund.
- **AC-6:** Given abweichende Historie (lokale Commits, die der Upstream nicht hat), When
  `sync-main` läuft, Then wird nichts verändert und die Meldung nennt den Grund.
- **AC-7:** Given `sync-main` aus einem Worktree oder einem Ordner ohne Upstream, Then Abbruch mit
  Meldung, nichts verändert.
- **AC-8:** Given ein bereits aktueller Haupt-Ordner, Then Meldung „bereits aktuell", Exit 0.

## Test Plan

`tests/test_session_singleton_guard.py` (Guard-Ausnahme, AC-1–3) und
`tests/test_sync_main_169.py` (echte Git-Repos in `tmp_path`, AC-4–8).
