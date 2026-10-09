---
entity_id: fix-409-worktree-always-allowed
type: bugfix
created: 2026-10-09
updated: 2026-10-09
status: draft
version: "1.0"
tags: [tdd-enforcement, post-implementation-gate, worktree, always-allowed, false-pass, hook-utils]
test_targets: ["tests/test_always_allowed_worktree_409.py"]
---

# Always-Allowed-Freigabe wurzelrelativ verankern (#409)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #409 (Beobachtung: gregor_zwanzig #2047 S2b, Workflow `fix-2047-s2-prod-gate`, 2026-10-06; Herkunft gregor_zwanzig #1197)

## Purpose

`tdd_enforcement.py` und `post_implementation_gate.py` geben jede Datei frei, deren **absoluter** Pfad irgendwo `.claude/` enthält. Jeder Worktree liegt unter `<repo>/.claude/worktrees/<name>/`, und die Worktree-Pflicht zwingt jede Sitzung in einen Worktree. Damit sind beide Gates in praktisch allen Sitzungen wirkungslos: Auch `src/x.py` oder `.github/workflows/ci.yml` gelten als „immer erlaubt“ (False-Pass).

Diese Spec misst die Freigabe am Pfad **relativ zur Worktree- bzw. Projektwurzel**, verankert `.claude/` am Anfang und stellt beide Gates auf einen gemeinsamen Helfer in `hook_utils.py`. Das Präfix `.claude/worktrees/<name>/` ist nie eine Freigabe.

## Source

- **File:** `core/hooks/tdd_enforcement.py` (Regex `_ALWAYS_ALLOWED`, Bypass-Stelle `if _ALWAYS_ALLOWED.search(file_path): allow()`), `core/hooks/post_implementation_gate.py` (identische Regex und Bypass-Stelle), `core/hooks/hook_utils.py` (neuer gemeinsamer Helfer)
- **Identifier:** `is_hook_always_allowed(file_path)` (neu, Arbeitstitel; Name darf bei der Umsetzung nur mit Anpassung der Testaufrufe geändert werden)
- **Analyse:** `docs/context/fix-409-worktree-always-allowed.md` (Root Cause, Technical Approach, Mutations-Gegenprobe, Entscheidungen)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils._find_worktree_root` | Funktion | Worktree-Wurzel (Verzeichnis mit `.git`-Datei) per CWD, sonst `None`; erste Kandidatenwurzel |
| `hook_utils.find_project_root` | Funktion | Löst Worktrees auf das Hauptrepo auf; zweite Kandidatenwurzel, Basis für Lock und Marker |
| `workflow.read_active_workflow_fast` | Funktion | Workflow-Name worktree-lokal, JSON aus Hauptrepo; State-Quelle beider Gates (unverändert) |
| `phase_listener` (Marker-Schreibseite) | Modul | Schreibt Freigabe-Marker unter `find_project_root()`; muss dieselbe Wurzel treffen wie das Lesen im Gate |
| `tdd_enforcement._resolve_artifact_path` | Funktion | RED-Artefakte worktree-first, dann Hauptrepo (#1478); unverändert |
| `edit_gate.py` / `is_gated_code_path` | Modul | Vergleichsmuster (komponentenweise, #80 `_is_outside_project`); wird bewusst nicht übernommen, nur als Referenz für „außerhalb = frei“ |
| `tests/test_tdd_enforcement_*.py`, `tests/test_post_implementation_gate_marker_binding.py` | Test | Regressionsschutz; nutzen relative `file_path` (`src/foo.py`) |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | Neuer gemeinsamer Helfer `is_hook_always_allowed(file_path)`: Pfad relativ zur Wurzel bestimmen, Freigabe-Regex auf den relativen Pfad, `.claude` am Anfang verankert |
| `core/hooks/tdd_enforcement.py` | MODIFY | Eigene `_ALWAYS_ALLOWED`-Regex entfernen, Helfer aufrufen; falschen Kommentar „gespiegelt von edit_gate.py“ korrigieren |
| `core/hooks/post_implementation_gate.py` | MODIFY | dito |
| `tests/test_always_allowed_worktree_409.py` | CREATE | je AC ein Test; Pfad-Tabelle, Fallback, Geschwister-Ordner, Vorfahren-Ordner, außerhalb, relativ, Subprocess-Tests mit echter Worktree-Struktur, Mutationsnachweise |
| `CHANGELOG.md` | MODIFY | Eintrag nur unter `[Unreleased]`, kein Versions-Bump; Hinweis auf Scharfschaltung |

### Estimated Changes

- Files: 5 (3 Produktiv, 1 Test, 1 Doku)
- LoC: ca. +210 (Produktivcode ca. +60/-15, Tests ca. +150). Spec/Kontext/Briefing zählen im LoC-Gate zusätzlich (#294).
- Risiko: **HIGH** — zentrales Gate in `core/hooks/`, wirkt über das Plugin in allen Konsumenten-Projekten und schaltet bisher tote Prüfungen scharf. Zwei Adversary-Runden nach dem Adversary-Protokoll.

## Implementation Details

**1. Relativen Pfad bestimmen (Helfer in `hook_utils`).**

```
def is_hook_always_allowed(file_path):
    rel = _relative_for_allowlist(file_path)   # None = außerhalb Projekt/Worktree
    if rel is None: return True                # außerhalb -> frei (wie edit_gate #80)
    return bool(_HOOK_ALWAYS_ALLOWED.search(rel))
```

- **Relativer `file_path`** bleibt relativ (Basis CWD/Worktree). Bestehende Tests mit `src/foo.py` bleiben gültig.
- **Absoluter Pfad:** Kandidatenwurzeln sind `_find_worktree_root()` und `find_project_root()`. Es gewinnt die **längste passende Wurzel zuerst** (Worktree vor Hauptrepo). Der Vergleich läuft mit `Path.is_relative_to`, **nicht** mit String-`startswith`, sonst passt `/proj` fälschlich auf `/proj2/…`.
- **Zusätzlich explizit:** Beginnt der relative Rest mit `.claude/worktrees/<name>/`, wird dieses Präfix abgeschnitten und der Rest bewertet. Das wirkt auch, wenn `_find_worktree_root()` per CWD `None` liefert (Hauptrepo-Sitzung, gewandertes CWD).
- Der edit_gate-Helfer `_relative_to_roots` wird bewusst **nicht** übernommen: Er probiert zuerst das Hauptrepo und lieferte `.claude/worktrees/n/src/x.py` — der Bypass bliebe.

**2. Freigabe-Muster auf dem relativen Pfad.** `^\.claude/` ist am Wurzelanfang verankert. `docs/` und `specs/` werden wie bisher komponentenweise erkannt (`(^|/)docs/`, `(^|/)specs/`), sodass `src/docs/…` frei bleibt; nur das Vorfahren-Leck (Projekt unter `/home/x/docs/proj/`) verschwindet. `.md`, `.txt`, `.gitignore` bleiben unverändert. Die Liste wird inhaltlich **nicht** erweitert und **nicht** an edit_gate angeglichen.

**3. Pfade außerhalb von Projekt und Worktree sind frei.** Konsistent mit edit_gate (#80 `_is_outside_project`). Ohne diese Regel würden die frisch scharfen Gates in phase6 Schreibzugriffe auf `~/.claude/projects/.../memory/` und das Sitzungs-Scratchpad blocken. Das ist eine bewusste kleine Lockerung: `/tmp/x.py` wird heute geprüft und ist danach frei.

**4. Ein Helfer für beide Gates.** `tdd_enforcement.py` und `post_implementation_gate.py` rufen denselben Helfer auf; die duplizierte Regex (inklusive der redundanten Alternative `[/\\]\.claude[/\\]`) entfällt, die Drift ist beseitigt.

**State-Quellen im Worktree (geprüft, unverändert):**

- Workflow-JSON: `read_active_workflow_fast()` — Name worktree-lokal, JSON aus dem Hauptrepo (wie edit_gate).
- RED-Artefakte: `_resolve_artifact_path` worktree-first, Fallback Hauptrepo (#1478).
- Lock und Freigabe-Marker: Gate und `phase_listener` nutzen beide `find_project_root()` (wertet `CLAUDE_PROJECT_DIR` zuerst aus, löst Worktrees aufs Hauptrepo auf) und landen bei gleicher Umgebung auf derselben Wurzel. AC-8 sichert das per Subprocess-Test ab.

**Mutations-Gegenprobe (Pflicht).** Je ein Test muss rot werden bei:

- (a) Regex wieder unverankert (`\.claude[/\\]`) bzw. auf den absoluten Pfad angewendet — AC-1 und AC-9
- (b) fehlendem Abschneiden von `.claude/worktrees/<n>/` — AC-3
- (c) String-`startswith` statt `is_relative_to` — AC-4

**Alternativen:**

- **A (gewählt): Gemeinsamer Helfer mit Wurzel-Relativierung, Worktree-Präfix explizit abgeschnitten.** Behebt die Fehlerklasse an einer Stelle, wirkt auch ohne Worktree-Erkennung.
- **B: Nur die Regex in beiden Dateien auf `^\.claude/` verankern.** Auf einem absoluten Pfad trifft `^` nie; ohne Relativierung wäre `.claude`-Freigabe tot. Verworfen.
- **C: edit_gate-Helfer `_relative_to_roots` wiederverwenden.** Probiert das Hauptrepo zuerst, der Bypass bliebe. Verworfen.
- **D: Freigabe-Liste an edit_gate angleichen.** Wäre eine inhaltliche Änderung außerhalb des Fehlers (eigenes Issue). Verworfen.

## Expected Behavior

- **Input:** `file_path` aus dem Tool-Input von Edit/Write/MultiEdit, absolut oder relativ, mit CWD im Projekt, im Worktree oder außerhalb.
- **Output:** Beide Gates behandeln den Pfad identisch: frei oder geprüft.
- **Side effects:** Beide Gates greifen in Worktree-Sitzungen erstmals tatsächlich (siehe Known Limitations und CHANGELOG-Hinweis). Keine neuen Dateien, keine neuen Abhängigkeiten.

| Pfad | Heute | Soll |
|---|---|---|
| `<repo>/.claude/worktrees/<n>/src/x.py` | frei (Bug) | wird geprüft |
| `<repo>/.claude/worktrees/<n>/core/hooks/x.py` | frei (Bug) | wird geprüft |
| `<repo>/.claude/worktrees/<n>/.claude/foo.json` | frei | frei |
| `<repo>/.claude/worktrees/<n>/docs/a.md` | frei | frei |
| `<repo>/.claude/foo.json` | frei | frei |
| `<repo>/src/x.py` | geprüft | geprüft |
| `/home/x/docs/proj/src/x.py` (Projektwurzel `/home/x/docs/proj`) | frei (Bug) | wird geprüft |
| `/proj2/src/x.py` bei Wurzel `/proj` | geprüft | außerhalb, frei |
| `~/.claude/projects/.../memory/x.md` | frei | frei |
| `/tmp/claude-1000/.../x.py` (Scratchpad) | geprüft | frei (bewusste Lockerung) |
| `src/foo.py` (relativ) | geprüft | geprüft |

## Known Limitations

- **Scharfschaltung:** Beide Gates laufen in Worktree-Sitzungen seit Einführung der Worktree-Pflicht faktisch nie. Nach dem Fix greifen sie dort. Konsumenten-Projekte, die beim Plugin-Update in phase6 stehen, sind sofort betroffen. Das ist gewolltes Verhalten der Gates, keine neue Regel.
- **24-h-Artefaktgrenze:** Ältere RED-Artefakte zählen nicht; in langen phase6-Läufen blockt `tdd_enforcement` dann jeden Nicht-Doku-Edit, bis ein frisches Artefakt vorliegt.
- **`tests/` nicht frei:** `tests/`, `.json`, `.yml`, `scripts/` sind in diesen beiden Gates — anders als in edit_gate — nicht frei. `post_implementation_gate` blockt nach dem Batch-Fenster daher auch Test-Edits bis zur GREEN-Freigabe („go“).
- **Freigabe-Liste nicht an edit_gate angeglichen:** bewusst nicht Teil dieser Änderung; bei Bedarf eigenes Issue.
- **Lockerung außerhalb:** Pfade außerhalb von Projekt und Worktree (z. B. `/tmp/x.py`) sind künftig frei, wo sie heute geprüft werden. Kleiner Verlust an Strenge, dafür keine Fehlblockade auf Memory und Scratchpad; konsistent mit edit_gate.
- **Verteilung:** wirkt in Konsumenten-Projekten erst nach dem Plugin-Update bzw. `setup.py --update`.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Code-Edit im Worktree (`<repo>/.claude/worktrees/<n>/src/x.py`) wird von beiden Gates geprüft statt durchgewunken; `.claude/…`, `docs/…`, `.md`, `.txt`, `.gitignore` bleiben frei
- [ ] Beide Gates nutzen denselben Helfer, keine eigene `_ALWAYS_ALLOWED`-Regex mehr
- [ ] Die Mutationsnachweise (a), (b), (c) machen je einen Test rot
- [ ] `CHANGELOG.md` unter `[Unreleased]` nennt den Fix und weist darauf hin, dass beide Gates in Worktree-Sitzungen jetzt erstmals greifen (24-h-Artefaktgrenze, `tests/` in diesen Gates nicht frei)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given ein absoluter Pfad im Worktree `<repo>/.claude/worktrees/<n>/core/hooks/x.py` bzw. `<repo>/.claude/worktrees/<n>/src/x.py` (Worktree-Wurzel erkannt) / When `is_hook_always_allowed` ihn bewertet / Then ist er **nicht** frei (wird geprüft); gleiches gilt für `<repo>/src/x.py`
  - Test: `tests/test_always_allowed_worktree_409.py::test_worktree_code_pfad_ist_nicht_frei`
- **AC-2:** Given `<repo>/.claude/worktrees/<n>/.claude/foo.json` bzw. `<repo>/.claude/foo.json` / When bewertet / Then ist der Pfad frei, weil `.claude/` am Anfang der Wurzel steht
  - Test: `tests/test_always_allowed_worktree_409.py::test_claude_ordner_am_wurzelanfang_ist_frei`
- **AC-3:** Given `_find_worktree_root()` liefert `None` und ein absoluter Worktree-Pfad liegt unter dem Hauptrepo / When bewertet / Then wird das Präfix `.claude/worktrees/<n>/` abgeschnitten und der Rest bewertet: `src/x.py` ist nicht frei, `.claude/foo.json` und `docs/a.md` im Worktree sind frei (Mutation b)
  - Test: `tests/test_always_allowed_worktree_409.py::test_fallback_ohne_worktree_erkennung_schneidet_praefix_ab`
- **AC-4:** Given ein Geschwister-Ordner `/proj2/src/x.py` bei Wurzel `/proj` / When bewertet / Then wird er nicht als relativ zu `/proj` behandelt (`is_relative_to` statt `startswith`), sondern als außerhalb eingestuft und ist frei; `/proj/src/x.py` bleibt geprüft (Mutation c)
  - Test: `tests/test_always_allowed_worktree_409.py::test_geschwisterordner_ist_nicht_relativ_zur_wurzel`
- **AC-5:** Given ein Projekt unter einem Vorfahren-Ordner namens `docs` bzw. `specs` (z. B. `/home/x/docs/proj/`) / When `src/x.py` darin bewertet wird / Then ist die Datei nicht frei; und `docs/a.md`, `src/docs/a.py`, `notes.md`, `notes.txt`, `.gitignore` bleiben frei wie bisher
  - Test: `tests/test_always_allowed_worktree_409.py::test_vorfahren_ordner_docs_gibt_projekt_nicht_frei`
- **AC-6:** Given Pfade außerhalb von Projekt und Worktree (`~/.claude/projects/.../memory/x.md`, Scratchpad `/tmp/claude-1000/.../x.py`) / When bewertet / Then sind sie frei (konsistent mit edit_gate #80); die bewusste kleine Lockerung (`/tmp/x.py` war geprüft, ist jetzt frei) ist im Test dokumentiert
  - Test: `tests/test_always_allowed_worktree_409.py::test_pfade_ausserhalb_von_projekt_und_worktree_sind_frei`
- **AC-7:** Given relative `file_path`-Werte (`src/foo.py`, `docs/a.md`) und die bestehenden Gate-Tests / When sie laufen / Then bleibt das Verhalten gleich (`src/foo.py` geprüft, `docs/a.md` frei) und `tests/test_tdd_enforcement_*.py` sowie `tests/test_post_implementation_gate_marker_binding.py` bleiben unverändert grün
  - Test: `tests/test_always_allowed_worktree_409.py::test_relative_pfade_funktionieren_weiter`, dazu Regressionslauf `tests/test_tdd_enforcement_*.py` und `tests/test_post_implementation_gate_marker_binding.py`
- **AC-8:** Given beide Gates als echte Prozesse mit cwd in einer echten Worktree-Struktur in `tmp_path` (Hauptrepo mit `.claude/worktrees/<n>/`, dort `.git`-**Datei**) / When ein Code-Edit mit absolutem Worktree-Pfad in phase6 ohne RED-Artefakt eingeht / Then blockt `tdd_enforcement` (Exit 2), und `post_implementation_gate` liest Lock und Freigabe-Marker aus derselben Wurzel, in die `phase_listener` schreibt; beide Gates importieren den gemeinsamen Helfer und enthalten keine eigene `_ALWAYS_ALLOWED`-Regex mehr
  - Test: `tests/test_always_allowed_worktree_409.py::test_tdd_enforcement_blockt_code_edit_im_worktree_subprocess`
  - Test: `tests/test_always_allowed_worktree_409.py::test_post_implementation_gate_nutzt_wurzel_des_phase_listener_subprocess`
  - Test: `tests/test_always_allowed_worktree_409.py::test_beide_gates_nutzen_gemeinsamen_helfer`
- **AC-9:** Given die Mutation (a), dass die Freigabe-Regex wieder unverankert (`\.claude[/\\]`) auf den absoluten Pfad läuft / When die Testdatei gegen diese Mutation läuft / Then wird mindestens der Test aus AC-1 rot; der Mutationsnachweis ist im Test automatisiert (Regex-Bewertung des absoluten Worktree-Pfads mit der alten Regex ergibt „frei“, mit dem Helfer „geprüft“)
  - Test: `tests/test_always_allowed_worktree_409.py::test_mutation_unverankerte_regex_wuerde_worktree_pfad_freigeben`
- **AC-10:** Given die Änderung ist umgesetzt / When `CHANGELOG.md` gelesen wird / Then steht unter `[Unreleased]` ein Eintrag zu #409 mit dem Hinweis, dass beide Gates in Worktree-Sitzungen jetzt erstmals greifen (24-h-Artefaktgrenze, `tests/` in diesen Gates nicht frei)
  - Test: `tests/test_always_allowed_worktree_409.py::test_changelog_nennt_scharfschaltung`

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_always_allowed_worktree_409.py` (AC-1 bis AC-10). Der Helfer wird direkt aufgerufen, mit echten Verzeichnissen in `tmp_path` und per monkeypatch injiziertem `hook_utils._find_worktree_root` bzw. `find_project_root` (Muster aus `tests/test_tdd_enforcement_worktree_artifact_path_1478.py`). Die Subprocess-Tests starten beide Gates als echte Prozesse mit cwd in einer Worktree-Struktur (`.git`-Datei, Hauptrepo darüber, `CLAUDE_PROJECT_DIR` wie im Betrieb) und prüfen Exit-Code und Meldung; Lock/Marker werden von der `phase_listener`-Schreibseite erzeugt und vom Gate gelesen.
- RED-Nachweis: Vor der Implementierung schlagen AC-1, AC-3, AC-4, AC-5, AC-6, AC-8 und AC-9 fehl (Helfer fehlt bzw. Regex gibt den Worktree-Pfad frei); AC-2, AC-7 und die Relativpfad-Fälle sind teilweise bereits grün.
- Mutationsnachweis (Pflicht): (a) unverankerte Regex wieder einsetzen — AC-1/AC-9 rot; (b) Präfix-Abschneiden entfernen — AC-3 rot; (c) `startswith` statt `is_relative_to` — AC-4 rot. Die drei Läufe werden im Adversary-Dialog dokumentiert.
- Regressionslauf (AC-7): `tests/test_tdd_enforcement_*.py`, `tests/test_post_implementation_gate_marker_binding.py`, danach die Vollsuite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Bugfix innerhalb der bestehenden Architektur; er folgt dem etablierten Worktree-first-Muster (#1478, #96, #280, #292: erst `_find_worktree_root()`, Fallback `find_project_root()`) und führt keine neue Abhängigkeit oder Schnittstelle ein. Der gemeinsame Helfer ersetzt nur zwei duplizierte Regex-Kopien. Alternativen (nur Regex verankern, edit_gate-Helfer wiederverwenden, Liste angleichen) sind oben unter „Alternativen“ begründet verworfen. Keine frühere ADR wird gekippt.

## Changelog

- 2026-10-09: Initial spec created (#409)
