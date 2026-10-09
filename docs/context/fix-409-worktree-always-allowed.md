# Context: fix-409-worktree-always-allowed

## Request Summary
Issue #409: `tdd_enforcement.py` und `post_implementation_gate.py` geben jede Datei frei, deren
**absoluter** Pfad irgendwo `.claude/` enthält. Jeder Worktree liegt unter
`<repo>/.claude/worktrees/<name>/` — damit sind beide Gates in jeder Worktree-Sitzung (und wegen
der Worktree-Pflicht: in jeder Sitzung) wirkungslos. Soll: Freigabe relativ zur Worktree-/Projekt-
wurzel messen, am Anfang verankern; Präfix `.claude/worktrees/<name>/` ist nie Freigabe.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/tdd_enforcement.py:41-45` | `_ALWAYS_ALLOWED`-Regex (unverankert `\.claude[/\\]`), Kommentar "gespiegelt von edit_gate.py" stimmt nicht (edit_gate prüft anders) |
| `core/hooks/tdd_enforcement.py:248-250` | `if _ALWAYS_ALLOWED.search(file_path): allow()` — die Bypass-Stelle |
| `core/hooks/tdd_enforcement.py:157-175` | `_resolve_artifact_path`: Artefakte worktree-first, dann Hauptrepo (#1478) |
| `core/hooks/post_implementation_gate.py:73-77, 122-124` | identische Regex + identische Bypass-Stelle |
| `core/hooks/post_implementation_gate.py:147-149` | Lock/Marker über `find_project_root()` = **Hauptrepo** |
| `core/hooks/phase_listener.py:28, 593-600` | schreibt Freigabe-Marker ebenfalls unter `find_project_root()` (Hauptrepo) → Lese-/Schreibseite konsistent |
| `core/hooks/hook_utils.py:1276-1284` | `ALWAYS_ALLOWED_DIRS`/`ALWAYS_ALLOWED_PATTERNS` des edit_gate (komponentenweise, nicht betroffen) |
| `core/hooks/hook_utils.py:1308-1331` | `is_gated_code_path()` — komponentenweiser Vergleich über `Path.parts` |
| `core/hooks/hook_utils.py:1368-1387` | `find_project_root()` — löst Worktree auf Hauptrepo auf |
| `core/hooks/hook_utils.py:1525-1540` | `_find_worktree_root()` — Worktree-Wurzel (Verzeichnis mit `.git`-Datei) oder None; per CWD |
| `core/hooks/workflow.py:394-412` | `read_active_workflow_fast()` — Name worktree-lokal (`.claude/active_workflow`), JSON aus Hauptrepo `.claude/workflows/` |
| `tests/test_tdd_enforcement_worktree_artifact_path_1478.py` | Muster für Worktree-Tests (monkeypatch `_find_worktree_root`, echte tmp-Dateien) |
| `tests/test_post_implementation_gate_marker_binding.py` | Subprocess-Tests des Gates; nutzen **relative** `file_path` (`src/foo.py`) |
| `tests/test_tdd_enforcement_*.py` (262, 89, 349) | weitere Tests, die nach dem Fix weiter grün sein müssen |

## Existing Patterns
- **edit_gate.py / `is_gated_code_path`:** Komponentenweise Prüfung `d.rstrip("/") in Path(p).parts` — kein Teilstring-Treffer, aber auch nicht wurzelverankert (`.claude/commands/` als Dir-Eintrag greift faktisch nie, weil `parts` einzelne Komponenten sind).
- **Worktree-first-Auflösung (#1478, #96, #280, #292):** erst `_find_worktree_root()`, Fallback `find_project_root()`. Etabliertes Muster für "relativ zur Worktree-Wurzel".
- Tests injizieren `hook_utils._find_worktree_root` per monkeypatch oder bauen echte Verzeichnisse mit `.git`-**Datei**.

## Dependencies
- Upstream: `hook_utils.find_project_root`, `_find_worktree_root`, `workflow.read_active_workflow_fast`, Lock-/Marker-Pfad-Helfer.
- Downstream: Registriert in `hooks/hooks.json` (PreToolUse Edit|Write|MultiEdit) für **alle** Konsumenten-Projekte im Plugin-Modus; Copy-Modus-Projekte (`setup.py`) bekommen die Datei kopiert.

## Existing Specs
- Keine Spec speziell zu diesen beiden Gates. Verwandt: #134 (Marker-Bindung), #1478 (Artefakt-Pfad im Worktree), #387 (Fehlblockade, geschlossen).

## Risks & Considerations
- **Scharfschaltung in allen Worktree-Sitzungen:** Beide Gates laufen dort heute faktisch nie. Nach dem Fix greifen sie. State-Quellen (vorläufig im Code geprüft, in der Analyse zu bestätigen):
  - Workflow-JSON: Hauptrepo — gelesen über `read_active_workflow_fast` (gleiche Quelle wie edit_gate) ✓
  - RED-Artefakte: worktree-first (#1478) ✓
  - Lock + Freigabe-Marker: beide Seiten (Gate + phase_listener) über `find_project_root()` = Hauptrepo ✓ — aber phase_listener berechnet `_root` beim Import; prüfen, ob der UserPromptSubmit-Hook mit derselben Wurzel läuft.
- **Relative `file_path`** (Tests nutzen `src/foo.py`) müssen weiter funktionieren — Basis dann CWD/Worktree.
- **Pfade außerhalb des Projekts** (z.B. `~/.claude/...`, Scratchpad `/tmp/claude-1000/...`): heute ist `~/.claude/...` frei (Teilstring), `/tmp/...x.py` wird geprüft. Verhalten nach dem Fix muss bewusst festgelegt werden (Analyse).
- **Weitere heute "zufällig" freie Pfade:** Was mit `.md`, `.txt`, `.gitignore`, `/docs/`, `/specs/` passiert, bleibt gleich. Nur der `.claude`-Teil wird verankert. Zu prüfen ist, ob `[/\\]docs[/\\]` unverankert ein ähnliches Problem hat (z.B. Projekt unter `/home/x/docs/proj/`). Dieselbe Fehlerklasse, möglicherweise im Scope.
- **Duplikat:** Die Regex steht doppelt (zwei Dateien). Eine gemeinsame Hilfsfunktion in `hook_utils` beseitigt die Drift.
- **Mutations-Gegenprobe Pflicht:** Mindestens ein Test muss rot werden, wenn das unverankerte `\.claude[/\\]` zurückkommt.
- Die alte Regex enthält `[/\\]\.claude[/\\]` doppelt (redundante Alternative).

## Analysis

### Type
Bug (False-Pass: zwei Gates lassen in jeder Worktree-Sitzung alles durch)

### Root Cause
`_ALWAYS_ALLOWED` in `tdd_enforcement.py` und `post_implementation_gate.py` wird per `search()` auf den
**absoluten** `file_path` angewendet. Die Alternative `\.claude[/\\]` ist unverankert und trifft das
Worktree-Präfix `<repo>/.claude/worktrees/<n>/`. Gleiche Fehlerklasse (schwächer) bei `[/\\]docs[/\\]` und
`[/\\]specs[/\\]`: Ein Vorfahren-Ordner namens `docs`/`specs` (z.B. `/home/x/docs/proj/`) gibt das ganze Projekt frei.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | Neue gemeinsame Funktion (Arbeitstitel `is_hook_always_allowed(file_path)`): Pfad relativ zur Wurzel bestimmen, Regex auf relativen Pfad, `.claude` am Anfang verankert |
| `core/hooks/tdd_enforcement.py` | MODIFY | Eigene `_ALWAYS_ALLOWED`-Regex entfernen, Helfer aufrufen; falschen Kommentar "gespiegelt von edit_gate.py" korrigieren |
| `core/hooks/post_implementation_gate.py` | MODIFY | dito |
| `tests/test_always_allowed_worktree_409.py` | CREATE | Pfad-Tabelle aus dem Issue, Fallback ohne Worktree-Erkennung, Pfade außerhalb, Subprocess-Tests beider Gates mit cwd=echter Worktree-Struktur (tmp_path) |
| `CHANGELOG.md` | MODIFY | Fix + Hinweis "Gates werden in Worktree-Sitzungen scharf" |

### Technical Approach
1. **Relativen Pfad bestimmen** (Helfer in `hook_utils`):
   - Relativer `file_path` → bleibt relativ (Basis CWD/Worktree; bestehende Tests mit `src/foo.py` bleiben gültig).
   - Absoluter Pfad → Kandidaten-Wurzeln `_find_worktree_root()` und `find_project_root()`; **längste passende Wurzel zuerst** (Worktree vor Hauptrepo), Vergleich per `Path.is_relative_to`, NICHT per String-`startswith` (sonst passt `/proj` auf `/proj2/…`). Den edit_gate-Helfer `_relative_to_roots` bewusst NICHT übernehmen — er probiert zuerst das Hauptrepo und liefert `.claude/worktrees/n/src/x.py` → Bypass bliebe.
   - **Zusätzlich explizit** ein führendes `.claude/worktrees/<name>/` abschneiden und den Rest bewerten — wirkt auch, wenn `_find_worktree_root()` per CWD `None` liefert (Hauptrepo-Sitzung, gewandertes CWD).
2. **Freigabe-Muster auf dem relativen Pfad:** `^\.claude/` verankert; `docs/`, `specs/` komponentenweise (`(^|/)docs/`) wie bisher — verschachtelte `src/docs/…` bleiben frei, nur das Vorfahren-Leck verschwindet. `.md`, `.txt`, `.gitignore` unverändert. Inhalt der Liste wird NICHT erweitert (kein Angleichen an edit_gate — Scope).
3. **Pfade außerhalb von Projekt und Worktree → frei** (konsistent mit edit_gate #80 `_is_outside_project`). Ohne das blocken die frisch scharfen Gates in phase6 Schreibzugriffe auf `~/.claude/projects/.../memory/` und das Scratchpad. Kleine Lockerung: `/tmp/x.py` ist heute geprüft, danach frei.
4. Beide Gates rufen denselben Helfer auf → Duplikat und Drift beseitigt.

### State-Quellen im Worktree (geprüft)
- Workflow-JSON: `read_active_workflow_fast()` — Name worktree-lokal, JSON aus Hauptrepo (wie edit_gate) ✓
- RED-Artefakte: `_resolve_artifact_path` worktree-first, Fallback Hauptrepo (#1478) ✓
- Lock + Freigabe-Marker: Gate und `phase_listener` (`_root` beim Import) nutzen beide `find_project_root()`; das wertet zuerst `CLAUDE_PROJECT_DIR` aus und löst Worktrees aufs Hauptrepo auf → beide Hooks landen bei gleicher Umgebung auf derselben Wurzel ✓. Wird in der Spec trotzdem als AC mit Subprocess-Test (cwd = Worktree-Struktur in tmp_path) abgesichert.

### Was durch das Scharfschalten neu wirksam wird (Risiko)
- 24-h-Altersgrenze für RED-Artefakte: in langen phase6-Läufen blockt `tdd_enforcement` dann jeden Nicht-Doku-Edit.
- `tests/`, `.json`, `.yml`, `scripts/` sind in diesen beiden Gates NICHT frei (anders als edit_gate) → `post_implementation_gate` blockt nach dem Batch-Fenster auch Test-Edits bis zur GREEN-Freigabe ("go").
- Konsumenten-Projekte, die beim Plugin-Update in phase6 stehen, sind sofort betroffen → CHANGELOG-Hinweis Pflicht.
- Das ist gewolltes Verhalten der Gates (nur bisher nie wirksam), keine neue Regel.

### Mutations-Gegenprobe (Pflicht in der Spec)
Je ein Test muss rot werden bei:
- (a) Regex wieder auf den absoluten Pfad / unverankertes `\.claude[/\\]`
- (b) fehlendes Abschneiden von `.claude/worktrees/<n>/` (Testfall mit `_find_worktree_root()` → None und absolutem Worktree-Pfad unter dem Hauptrepo)
- (c) String-`startswith` statt `is_relative_to` (Geschwister-Ordner `/proj2`)

### Scope Assessment
- Files: 5 (3 MODIFY Code, 1 CREATE Test, CHANGELOG)
- Estimated LoC: +60/-15 Code, +150 Tests
- Risk Level: HIGH — zentrales Gate, wirkt in allen Konsumenten-Projekten, schaltet bisher tote Prüfungen scharf → 2 Adversary-Runden

### Dependencies
`hook_utils._find_worktree_root`, `find_project_root`; Registrierung in `hooks/hooks.json` unverändert. Bestehende Tests `tests/test_tdd_enforcement_*.py`, `tests/test_post_implementation_gate_marker_binding.py` müssen grün bleiben.

### Wo ich entschieden habe (für die Spec)
- Pfade außerhalb des Projekts bleiben/werden frei (Begründung Punkt 3).
- `docs/`/`specs/` komponentenweise auf relativem Pfad statt am Anfang verankert (keine neue Verschärfung).
- Freigabe-Liste inhaltlich nicht an edit_gate angeglichen (eigenes Issue, falls gewünscht).

### Open Questions
- keine PO-Fragen offen
