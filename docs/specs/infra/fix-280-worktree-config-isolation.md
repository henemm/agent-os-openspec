---
entity_id: fix-280-worktree-config-isolation
type: bugfix
created: 2026-09-30
updated: 2026-09-30
status: draft
version: "1.0"
workflow: fix-280-worktree-config-isolation
tags: [hooks, worktree, gate-events, testing, observability]
test_targets:
  - tests/test_gate_event_log_worktree_280.py
  - tests/test_sync_main_169.py
  - tests/test_session_singleton_guard.py
  - tests/test_gate_event_log_181.py
---

# Gate-Event-Log respektiert Worktree-Wurzel (Issue #280, Befund 2)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #280 (Sammel-Vorgang aus #241 und #265). Diese Spec deckt **ausschließlich Befund 2**
  (#265 — Gate-Event-Log). Befund 1 (#241, `config_loader.load_config()`) ist laut
  Issue-Kommentar bewusst ausgekoppelt und läuft als eigener Vorgang unter **#292** — nicht Teil
  dieser Spec. Ebenso nicht Teil dieser Spec: das unabhängige, frisch angelegte Symlink-/
  node_modules-Thema aus **#293**.

## Purpose

`log_gate_event()` (`core/hooks/hook_utils.py`) löst ihren Schreibort über `find_project_root()`
auf — eine Funktion, die *bewusst* jede Worktree-Sitzung auf den Haupt-Ordner abbildet, weil das
für geteilten Zustand (Workflow-JSONs) richtig ist. Für das Gate-Event-Log, eine reine
Beobachtungs-Funktion ohne Entscheidungswirkung, ist das falsch: eine Blockade in einer
Worktree-Sitzung soll im Log **dieser Sitzung** landen, nicht im Log des Haupt-Ordners. Diese Spec
bindet `log_gate_event()` an die tatsächliche Arbeitswurzel der Sitzung — dasselbe bereits
etablierte Muster, das Issue #96 für die LoC-Messung eingeführt hat — und schließt damit zwei
konkrete, reproduzierte Symptome: (1) jeder vollständige Testlauf hängt reale Zeilen an das echte
`.claude/gate-events.jsonl` dieses Repositories an, weil zwei Testdateien den Guard in-process
aufrufen und dabei die reale Prozess-`cwd` (den Haupt-Ordner) treffen; (2) eine echte
Worktree-Sitzung schreibt ihre Blockaden fälschlich in den Haupt-Ordner statt in ihr eigenes Log.

## Source

- **File:** `core/hooks/hook_utils.py` — **Identifier:** `log_gate_event` (Zeile 529–552, Root-
  Auflösung in Zeile 537)
- **Referenz (unverändert, bereits etabliertes Muster):** `hook_utils.find_worktree_root`
  (Zeile 887–904) und dessen Verwendung in `observable_surface_report` (Zeile 1149:
  `root = find_worktree_root() or find_project_root()`)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils.find_worktree_root()` | function | Bereits für #96 eingeführte Gegenfunktion zu `find_project_root()` — liefert die Worktree-Wurzel oder `None`, wenn die Sitzung im Haupt-Ordner läuft. Keine Änderung an dieser Funktion. |
| `hook_utils.find_project_root()` | function | Bleibt der Rückfallwert, wenn `find_worktree_root()` `None` liefert (Haupt-Ordner-Sitzung) oder wenn Zustand (nicht Beobachtung) betroffen ist. Keine Änderung an dieser Funktion. |
| `session_singleton_guard._do_guard` | function | Einziger Aufrufer von `log_gate_event` in den beiden betroffenen Testdateien (lokaler Import `from hook_utils import log_gate_event`, Zeile 668–669 in `session_singleton_guard.py`); ruft die real gepatchte Funktion über deren `__globals__`-Bindung an `hook_utils` auf — keine Änderung an dieser Datei nötig. |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | `log_gate_event()`, Zeile 537: `root = find_project_root()` → `root = find_worktree_root() or find_project_root()`. Sonst keine Änderung an der Funktion (Fehlerbehandlung, Schema, Aufrufer-Signatur bleiben identisch). |
| `tests/test_sync_main_169.py` | MODIFY | Autouse-Fixture `_isolate` (Zeile 19–22) erweitert: patcht zusätzlich `hook_utils.find_project_root` und `hook_utils.find_worktree_root` (sowie `ssg.find_project_root`/`ssg.find_worktree_root` mit `raising=False`, analog zum bestehenden Muster `_patch_project_root` in `test_session_singleton_guard.py`) auf `tmp_path` bzw. `None`. Betrifft die drei Tests, die real blockieren: `test_other_bash_blocked_in_main`, `test_other_tools_still_blocked`, `test_carriage_return_not_allowed`. |
| `tests/test_session_singleton_guard.py` | MODIFY | Autouse-Fixture `_isolate_lock_dir` (Zeile 22–34) um denselben Default erweitert (`find_project_root`/`find_worktree_root` auf `tmp_path`/`None` an beiden Bindungen) — bisher isolierten nur die Tests, die den bereits vorhandenen, nicht-autousten Helfer `_patch_project_root` (Zeile 251–259) explizit aufrufen. |
| `tests/test_gate_event_log_worktree_280.py` | CREATE | Neuer Regressionstest analog zum Muster aus #96 (`tests/test_loc_gate_worktree_root_96.py`): echtes Haupt-Repo, echter `git worktree add`, echte Blockade über `hook_utils.block()` bzw. `session_singleton_guard._do_guard`, `monkeypatch.chdir()` statt injizierter Root — deckt AC-1 bis AC-4. |
| `tests/test_gate_event_log_181.py` | MODIFY | **Nachträglich ergänzt (RED→GREEN-Übergang, verifiziert durch echten Testlauf):** `TestLogGateEvent` und `TestBlockAutoLogs` rufen `hook_utils.log_gate_event()`/`hook_utils.block()` in-process auf und isolieren ausschließlich über `monkeypatch.setenv("CLAUDE_PROJECT_DIR", tmp_path)`. Diese Isolation ignoriert `find_worktree_root()` komplett — läuft `pytest` selbst in einem Worktree (wie in dieser Sitzung), gewinnt `find_worktree_root()` gegen den gepinnten `CLAUDE_PROJECT_DIR` und 6 Tests werden rot (real reproduziert, nicht vermutet). Fix: je eine autouse-Fixture in beiden Klassen pinnt `hook_utils.find_worktree_root` zusätzlich auf `None` — identisches Prinzip wie bei den zwei bereits geplanten Testdateien, keine Änderung an Produktivcode oder Testaussagen. |

**Bewusst unverändert:** Jede Stelle, die `find_project_root()` für **Zustandsablage** verwendet
(Workflow-JSONs, `resolve_active_workflow`, Session-Register) bleibt exakt wie heute — diese Spec
ändert ausschließlich den Schreibort einer reinen Beobachtungs-Funktion.

### Estimated Changes

- **Files:** 1 Produktivdatei (1 Zeile), 2 angepasste Testdateien (je ~5–10 Zeilen Fixture-
  Erweiterung), 1 neue Testdatei (~100–150 LoC).
- **LoC:** Produktiv +1/−1, Tests ca. +120/−0. Innerhalb des Standardlimits (250 LoC Produktiv /
  500 LoC Tests) — kein Override nötig.

## Implementation Details

### 1. Der eigentliche Fix (1 Zeile)

`core/hooks/hook_utils.py`, `log_gate_event()`, Zeile 537:

```
root = find_worktree_root() or find_project_root()
```

Identisches Muster wie bereits produktiv in `observable_surface_report()` (Zeile 1149). Läuft die
Sitzung in einem Git-Worktree, liefert `find_worktree_root()` dessen Root und die Funktion
schreibt dorthin; läuft sie im Haupt-Ordner, liefert `find_worktree_root()` `None` und das
Verhalten ist bit-identisch zum heutigen Stand (`find_project_root()` greift wie bisher). Der
`try/except Exception: pass`-Rahmen um die gesamte Funktion (Zeile 536/551–552) bleibt unverändert
— ein Fehler in der Root-Auflösung darf weiterhin nie sichtbar werden.

### 2. Isolations-Fixtures in den beiden betroffenen Testdateien

Beide Dateien rufen den jeweiligen Guard **in-process** auf (`ssg._do_guard(payload)` direkt im
pytest-Prozess), nicht per Subprozess mit eigenem `CLAUDE_PROJECT_DIR` wie im etablierten Muster
aus `tests/test_gate_event_log_181.py`. Die Root-Auflösung muss deshalb per Monkeypatch auf
`tmp_path` gepinnt werden — an **beiden möglichen Bindungen**, wie es der bereits vorhandene
Helfer `_patch_project_root` in `test_session_singleton_guard.py` für `find_project_root` bereits
vormacht (die Implementierung könnte die Funktion modulweit binden oder lokal importieren):

```python
monkeypatch.setattr(hook_utils, "find_worktree_root", lambda: None)
monkeypatch.setattr(ssg, "find_worktree_root", lambda: None, raising=False)
```

kombiniert mit der bestehenden Pinnung von `find_project_root` auf `tmp_path`. `find_worktree_root`
wird bewusst auf `None` gepinnt (nicht auf einen zweiten `tmp_path`-Wert) — das erzwingt in jedem
Testfall den Rückfall auf das bereits isolierte `find_project_root`, unabhängig davon, ob die
Sitzung, in der `pytest` tatsächlich läuft, zufällig selbst in einem Worktree steht.

`test_sync_main_169.py` hat noch keinen `hook_utils`-Import und keine solche Pinnung; die
bestehende `_isolate`-Fixture (Zeile 19–22) wird um genau diese zwei Zeilen (plus die bereits
vorhandene `find_project_root`-Pinnung nach demselben Muster) erweitert.
`test_session_singleton_guard.py`s `_isolate_lock_dir`-Fixture (Zeile 22–34, bereits autouse) wird
um denselben Default erweitert, statt die Isolation weiterhin nur den Tests zu überlassen, die
`_patch_project_root` manuell aufrufen.

### 3. Neuer Regressionstest

`tests/test_gate_event_log_worktree_280.py`, aufgebaut wie `test_loc_gate_worktree_root_96.py`:
echtes Haupt-Repo (`git init`), echter `git worktree add`, **kein** Monkeypatch der
Root-Auflösung selbst — stattdessen `monkeypatch.chdir(worktree)`, damit
`hook_utils._find_worktree_root()` real über Git auflöst. Die Blockade läuft über die echte
Produktionsfunktion `hook_utils.block()` (bzw. `session_singleton_guard._do_guard` als
zweiter, end-to-end näherer Fall), sodass tatsächlich eine reale Gate-Blockade geloggt wird, kein
synthetischer `log_gate_event()`-Direktaufruf.

## Expected Behavior

- **Input:** Eine reale Blockade (Exit-2-Pfad eines Gate-Hooks) während die Sitzung entweder im
  Haupt-Ordner oder in einem Git-Worktree läuft.
- **Output:** Genau eine JSON-Zeile im `gate-events.jsonl` **der Wurzel, in der die Sitzung
  tatsächlich arbeitet** — Worktree-Root bei einer Worktree-Sitzung, Haupt-Ordner sonst
  (unverändert).
- **Side effects:** Keine neuen. `path.parent.mkdir(parents=True, exist_ok=True)` legt bei Bedarf
  `<worktree>/.claude/` an, exakt wie es heute für `<haupt-ordner>/.claude/` passiert.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Eine reale Blockade in einer Worktree-Sitzung landet im Log **des Worktrees**, nicht im Log
      des Haupt-Ordners (AC-1)
- [ ] Eine reale Blockade im Haupt-Ordner verhält sich bit-identisch zum heutigen Stand (AC-2)
- [ ] Die Gegenprobe zeigt: die Blockade wird weiterhin geloggt, nicht verschluckt — kein
      Fail-Open durch die Änderung (AC-3)
- [ ] Nachweis per echtem Lauf: `wc -l .claude/gate-events.jsonl` vor und nach den drei in dieser
      Spec behandelten Testdateien (`test_sync_main_169.py`, `test_session_singleton_guard.py`,
      `test_gate_event_log_181.py`) ergibt **dieselbe Zeilenzahl** (AC-4, automatisiert bewiesen)
  - **Scope-Korrektur (2026-09-30, per Override):** Ein echter Lauf der *gesamten* Suite zeigt
    zusätzliche, reale Log-Zeilen aus **anderen** Testdateien (`bash_gate`-,
    `secret_egress_guard`-Aufrufe in-process, außerhalb dieser Spec) — nicht durch diesen Fix
    verursacht, sondern derselbe Fehlerklasse in Dateien, die hier nie im Scope standen. Diese
    Spec beweist **0 neue Zeilen für die drei oben genannten Dateien**, nicht für die volle Suite.
    Rest-Leck dokumentiert und weiterverfolgt in **#295**.
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/ -q` grün)

## Acceptance Criteria

- **AC-1:** Given ein echtes Haupt-Repo mit einem echten, daran gelinkten Git-Worktree / When aus
  dem Worktree heraus (`cwd` = Worktree) eine reale Gate-Blockade ausgelöst wird / Then landet
  genau eine Event-Zeile in `<worktree>/.claude/gate-events.jsonl` und **keine** Zeile wird an
  `<haupt-repo>/.claude/gate-events.jsonl` angehängt.
  - Test: `test_gate_event_log_worktree_280.py::test_worktree_session_logs_to_worktree_not_main_repo`

- **AC-2:** Given dieselbe Ausgangslage, aber die Sitzung läuft im Haupt-Repo selbst (kein
  Worktree, `cwd` = Haupt-Repo) / When eine reale Gate-Blockade ausgelöst wird / Then landet die
  Event-Zeile weiterhin in `<haupt-repo>/.claude/gate-events.jsonl` — bit-identisches Verhalten
  zum Stand vor dieser Änderung.
  - Test: `test_gate_event_log_worktree_280.py::test_main_repo_session_unchanged`

- **AC-3:** Given eine reale Blockade in einer Worktree-Sitzung / When das Event geloggt wird /
  Then wird **genau eine** Zeile geschrieben (nicht null) — die Korrektur des Schreibortes
  verschluckt das Event nicht (Gegenprobe gegen Fail-Open).
  - Test: `test_gate_event_log_worktree_280.py::test_worktree_blockage_is_still_logged_not_silently_dropped`

- **AC-4:** Given die drei zuvor nachweislich leckenden bzw. potenziell leckenden Testdateien
  (`tests/test_sync_main_169.py`, `tests/test_session_singleton_guard.py`,
  `tests/test_gate_event_log_181.py`) / When sie ausgeführt werden (die ersten beiden per
  Subprozess mit `cwd` = echtes Repository-Wurzelverzeichnis, geprüft durch Vergleich der
  Zeilenzahl von `<repo>/.claude/gate-events.jsonl` vor/nach; die dritte durch ihren eigenen,
  jetzt vollständig grünen Lauf mit gepinnter `find_worktree_root`-Isolation) / Then hinterlässt
  keine der drei Dateien eine Zeile im echten Log. **Explizit nicht Teil dieser AC:** weitere,
  hier nicht untersuchte Testdateien — siehe Out-of-Scope-Hinweis unten und #295.
  - Test: `test_gate_event_log_worktree_280.py::test_previously_leaky_suites_do_not_touch_the_real_log`
    (deckt die ersten zwei Dateien) plus `test_gate_event_log_181.py` selbst (24/24 grün, siehe
    GREEN-Artefakt) für die dritte.

## Test Plan

| Prüfung | Art | Ort |
|---------|-----|-----|
| AC-1 (Worktree-Sitzung loggt in Worktree, nicht Haupt-Repo) | automatisiert, echter Git-Worktree | `tests/test_gate_event_log_worktree_280.py` |
| AC-2 (Haupt-Repo-Sitzung unverändert) | automatisiert, echter Git-Worktree | ebenda |
| AC-3 (Gegenprobe: kein Fail-Open, Event wird weiterhin geschrieben) | automatisiert | ebenda |
| AC-4 (die drei behandelten Dateien hinterlassen 0 Zeilen im echten Log) | automatisiert (2 per Subprozess-Vergleich, 1 per eigenem grünen Lauf) | `test_gate_event_log_worktree_280.py` + `test_gate_event_log_181.py` |
| Vollständiger Regressionslauf inkl. `wc -l` vor/nach der drei behandelten Dateien | Nachstellung (Phase 7) | `python3 -m pytest tests/ -q` aus dem Haupt-Ordner — Rest-Leck aus anderen Dateien erwartet, siehe #295 |

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Kein neues Konzept — die Änderung wendet ein bereits etabliertes, produktiv
  eingesetztes Muster (`find_worktree_root() or find_project_root()`, eingeführt für #96 und
  bereits an einer zweiten Stelle, `observable_surface_report`, in Gebrauch) auf eine weitere,
  strukturell identische Beobachtungs-Funktion an. Die geprüfte Alternative — `log_gate_event()`
  weiterhin immer auf den Haupt-Ordner schreiben zu lassen und stattdessen nur die Tests zu
  isolieren — wurde verworfen: sie behebt das Test-Rauschen (Befund im Issue), lässt aber das
  eigentliche Produktivverhalten (Befund 2 selbst — Worktree-Sitzungen loggen ins falsche
  Verzeichnis) unangetastet.

## Out of Scope

- **Befund 1 / #241** (`config_loader.load_config()` löst im Worktree die Haupt-Ordner-
  `config.yaml` auf) — eigener, engerer Vorgang unter #292, weil ein pauschaler Fix dort die
  bewusste Design-Entscheidung aus #153 (Grenzwerte bleiben Haupt-Ordner-autoritativ) aushebeln
  würde.
- **Symlink-/node_modules-Thema (#293)** — unabhängiger, frisch angelegter Vorgang ohne
  inhaltlichen Bezug zu dieser Spec.
- Rotation, Auswertung oder Clustering des Gate-Event-Logs (`/91-gate-audit`) — unverändert
  zurückgestellt, wie bereits in #181 entschieden.

## Changelog

- 2026-09-30: Initial spec created
- 2026-09-30: Scope um `tests/test_gate_event_log_181.py` erweitert — echter GREEN-Lauf zeigte 6
  Regressionen durch eine In-Process-Isolationslücke (siehe Scope-Tabelle). Freigegeben per
  `override` (Henning), da die Spec bereits genehmigt war.
- 2026-09-30: AC-4/DoD auf die drei tatsächlich behandelten Testdateien präzisiert, nachdem ein
  echter Volllauf weitere, außerhalb dieser Spec liegende Lecks zeigte (→ #295). Selber Override.
