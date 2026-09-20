# Fast Track: Commit-Inhalt im Worktree messen (3.25.1)

## Problem

`bash_gate.py` ermittelte die vorgemerkten Dateien mit `cwd=_root`. `_root = find_project_root()`
löst einen Worktree bewusst auf das **Hauptrepo** auf — richtig für geteilten Zustand
(`.claude/workflows/*.json`), falsch für eine Messung am **Arbeitsbaum**. Der Commit passiert im
Worktree, im Hauptrepo ist nichts vorgemerkt → die Liste kam leer zurück.

Folgen (live gemeldet aus gregor_zwanzig, 2026-09-20):

1. `_detect_e2e_scope` sah keine Non-Doc-Datei und meldete immer `docs-only`. `/70-deploy`
   überspringt daraufhin die Staging-Validierung, die die Spec verlangt — ein Deploy geht
   ungeprüft durch.
2. `required_staged_files` prüfte gegen dieselbe leere Liste; auch der Fallback
   (`git diff --name-only -- <datei>`) lief im falschen Baum → das Gate blockte nie.

Seit der Worktree-Pflicht (3.4.10) läuft praktisch jede Sitzung im Worktree: das war der
Normalfall, nicht die Ausnahme. Gleiche Fehlerklasse wie #96 (LoC-Gate) und #144 (Spec-/
Briefing-Pfade); der dokumentierte Gegenpart `find_worktree_root()` existierte bereits.

## Scope

- `core/hooks/bash_gate.py`: neues `_measurement_root()` (Worktree-first, Fallback `_root`,
  pro Aufruf aufgelöst) als `cwd` für beide git-Aufrufe in Abschnitt 5
- `core/hooks/bash_gate.py`: neues `_commit_content_files()` — Rückfall auf
  `git diff --name-only HEAD`, wenn der Index leer ist (`git commit -a`/`-am`). Nur für die
  Scope-Erkennung; `required_staged_files` behält die strenge Index-Semantik
- Nicht enthalten: `_write_e2e_scope` schreibt weiterhin in den geteilten State im Hauptrepo —
  das ist die richtige Wurzel für Zustand und bleibt bewusst unverändert

## Definition of Done

Ein Commit aus einem Worktree wird nach seinem eigenen Inhalt eingestuft, nicht nach dem
(leeren oder fremden) Index des Hauptrepos; der ermittelte Wert landet weiterhin im geteilten
Workflow-State im Hauptrepo.

## Acceptance Criteria

- **AC-1:** Given eine Sitzung im Worktree mit vorgemerkter Produktivdatei, When `git commit`
  durch das Gate läuft, Then steht `e2e_scope` auf `backend`, nicht auf `docs-only`.
- **AC-2:** Given ein reiner Doku-Commit im Worktree, When das Gate läuft, Then bleibt
  `e2e_scope` auf `docs-only` — der Fix stuft nicht pauschal hoch.
- **AC-3:** Given das Hauptrepo hat eine Produktivdatei vorgemerkt und der Worktree committet
  nur Doku, When das Gate läuft, Then fließt der fremde Index nicht ein (`docs-only`).
- **AC-4:** Given eine Sitzung im Hauptrepo (kein Worktree), When das Gate läuft, Then ist das
  Verhalten unverändert zum Bestand.
- **AC-5:** Given `git commit -am` mit geänderter, nicht vorgemerkter Produktivdatei, When das
  Gate läuft, Then wird der Arbeitsbaum gegen HEAD gezählt (`backend`).
- **AC-6:** Given `required_staged_files` ist konfiguriert und die Pflichtdatei ist im Worktree
  geändert, aber nicht vorgemerkt, When das Gate läuft, Then blockt es (Exit 2); ist sie
  vorgemerkt, blockt es nicht.
- **AC-7:** Given der Fix greift, When das Gate schreibt, Then entsteht keine zweite,
  worktree-lokale Workflow-Ablage — der State bleibt im Hauptrepo.

## Test Plan

- `tests/test_bash_gate_worktree_commit_155.py`: 8 Tests (AC-1 bis AC-7), echtes
  `git worktree add`, Hook als Subprozess mit `cwd=worktree` und echter stdin-Payload.
  Ein Direktaufruf von `_detect_e2e_scope()` würde vor und nach dem Fix identisch bestehen —
  der Defekt liegt nicht im Klassifikator, sondern in dem, was in ihn hineingereicht wird.
- RED vor dem Fix: 5 von 8 rot (genau die Worktree-Fälle), 3 Gegenproben grün.
- Volle Suite: 842 passed.

## ADR

**Entscheidung:** Zwei getrennte Wurzeln statt einer. `_root` (Hauptrepo) bleibt die Wurzel für
ZUSTAND, `_measurement_root()` (Worktree) wird die Wurzel für MESSUNG.

**Alternative:** `find_project_root()` so ändern, dass sie Worktrees nicht mehr auflöst. Verworfen:
dann läge der Workflow-State pro Worktree getrennt, parallele Sitzungen verlören ihren geteilten
Zustand — ein größerer Schaden als der behobene.

**Entscheidung 2:** Der `-a`-Rückfall gilt nur für die Scope-Erkennung. Die ist informativ und
blockt nie; over-reporting bedeutet dort höchstens eine Validierung zu viel. Bei
`required_staged_files` ist „nicht vorgemerkt" dagegen genau die Bedingung, auf die das Gate
hinweisen soll — ein Rückfall würde es entschärfen.
