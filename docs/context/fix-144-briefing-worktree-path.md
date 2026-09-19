# Context: fix-144-briefing-worktree-path

## Request Summary
`workflow.py set-briefing` und das PO-Briefing-Gate scheitern in worktree-isolierten Sessions, weil Spec- und Briefing-Datei (normale versionierte Repo-Dateien im Arbeitsbaum) über `find_project_root()` aufgelöst werden — diese Funktion bildet einen Worktree bewusst auf das Hauptrepo ab. Ist die Spec/das Briefing nur im Worktree committet (Normalfall vor dem Merge), findet der Code sie dort nicht.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py:459` (`_check_adr`) | `spec_path = find_project_root() / spec_file` — ADR-Gate liest Spec über falschen Root; lenientes Design (Exception → `return None`) macht den Fehler hier zum **stillen Skip** statt Block, also selbes Root-Problem, andere Symptomatik |
| `core/hooks/workflow.py:551-558` (`_read_spec_content`) | Kern der gemeldeten Blockade — genutzt von `cmd_set_briefing` UND `_check_po_briefing` |
| `core/hooks/workflow.py:673` (`_check_po_briefing`) | `briefing = (find_project_root() / entry["file"]).read_text()` — selbes Problem beim Lesen der Briefing-Datei zur Freigabe-Zeit. Wichtig: Dieser Pfad ist vom Issue **nicht genannt**, aber vom selben Root Cause betroffen — selbst nach erfolgreichem `set-briefing`-Fix würde die spätere `approved`-Prüfung in `phase_listener.py` weiterhin scheitern, wenn die Briefing-Datei nur im Worktree liegt |
| `core/hooks/workflow.py:966-1029` (`cmd_set_briefing`) | `root = find_project_root()` (Zeile 977) bestimmt sowohl den Lese- als auch den Rückschreibe-Pfad (Frontmatter-Stempel) der Briefing-Datei — genannter Fehlerort aus dem Issue |
| `core/hooks/hook_utils.py:602-621` (`find_project_root`) | Löst Worktree bewusst auf Hauptrepo auf — korrekt für geteilten State (`.claude/workflows/`), falsch für versionierte Repo-Inhalte wie Spec/Briefing |
| `core/hooks/hook_utils.py:719-736` (`find_worktree_root` / `_find_worktree_root`) | Bereits vorhandener Gegenpart — liefert den tatsächlichen Arbeitsbaum-Root oder `None` (dann Fallback auf `find_project_root()`) |
| `core/hooks/workflow.py:50-61` (`_worktree_root_if_any`) | Lokale Dopplung derselben Erkennung, bereits in `workflow.py` selbst verwendet (z.B. Zeile 284 in `_write_active_workflow_state`/Umfeld) — für Konsistenz innerhalb der Datei zu bevorzugen statt eines zusätzlichen Imports aus `hook_utils` |
| `core/hooks/edit_gate.py:250-254` | **Bereits korrekt gelöst** — dient als Referenzmuster für den Fix: `spec_path = (wt / spec_file) if (wt is not None and (wt / spec_file).exists()) else (_root / spec_file)`, Kommentar „Worktree gewinnt vor Hauptrepo (Vorbild: `_is_stop_locked()`)". Bestätigt per Grep über alle `core/hooks/*.py`: `tdd_enforcement.py`/`post_implementation_gate.py` nutzen `find_project_root()` nur für geteilten State (Lock-/Artefakt-Pfade), nicht für `spec_file` — kein fünfter Fundort. Scope bleibt auf `workflow.py` begrenzt. |

## Existing Patterns
- **`hook_utils.resolve_active_workflow()`** (Zeilen 632-716) etabliert exakt das Muster, das hier fehlt: `worktree_root = _find_worktree_root(); if worktree_root is not None: <verwende worktree_root> else: <verwende find_project_root()>`. Kommentar dort erklärt explizit, warum die beiden Roots für unterschiedliche Zwecke da sind (geteilter State vs. Arbeitsbaum-Inhalt).
- `find_worktree_root()`-Docstring benennt selbst den Gegensatz: „the right root for MEASUREMENTS against the working tree" — Spec-/Briefing-Dateien sind genau das: Inhalt des Arbeitsbaums, nicht geteilter Workflow-State.
- Tests zu genau diesem Bug-Muster existieren bereits als Vorlage: `tests/test_workflow_resolution_consolidation.py` patcht `hook_utils._find_worktree_root` und `workflow._worktree_root_if_any` in-process via `monkeypatch`, um Worktree- vs. Hauptrepo-Szenarien hermetisch zu simulieren (kein echtes `.git`-File nötig).
- `tests/test_po_briefing_gate.py` und `tests/test_adr_gate.py` nutzen dagegen einen Subprozess-Runner (`cwd=tmp_path`, `CLAUDE_PROJECT_DIR=tmp_path`) ohne echtes `.git` — das simuliert implizit den Hauptrepo-Fall (kein Worktree), da `_find_worktree_root()` ohne `.git`-Datei-Marker `None` liefert. Für die neuen Worktree-Fälle ist das In-Process-Monkeypatch-Muster besser geeignet.

## Dependencies
- Upstream: `_read_spec_content`, `_check_po_briefing`, `_check_adr`, `cmd_set_briefing` hängen alle von der Root-Auflösung ab (`find_project_root()` / `_worktree_root_if_any()`).
- Downstream: `phase_listener.py` ruft `_check_adr` und `_check_po_briefing` bei der Freigabe-Phrase auf (Soft-Block). `workflow.py phase phase4_approved` ruft denselben Gate-Code hart. `/30-write-spec` Step 3b instruiert den User zu `set-briefing`. `scripts/ci_spec_gate.py` ist NICHT betroffen — läuft auf einem normalen PR-Checkout ohne Worktree-Isolation, `root` kommt dort über CLI-Argument/CWD, nicht über diese Funktionen.

## Existing Specs
- Keine dedizierte Spec zu `find_project_root`/`find_worktree_root` gefunden — Verhalten ist nur in Docstrings dokumentiert (`hook_utils.py`).
- `docs/specs/` enthält keine PO-Briefing-Gate-Spec unter diesem Namen; das Gate selbst wurde laut CLAUDE.md/Memory in 3.20/3.21 eingeführt (siehe `project_po_briefer_gate` Memory).

## Risks & Considerations
- **Scope-Ausweitung ggü. Issue-Text (bewusst, kein Creep)**: Das Issue nennt nur `cmd_set_briefing`/`_read_spec_content`. Die Untersuchung zeigt zwei weitere Stellen mit demselben Root Cause. `_check_po_briefing` (Zeile 673) gehört zwingend mit in den Fix — sonst bleibt das eigentliche Ziel des Issues (worktree-isolierte Freigabe funktioniert) unerreicht: `set-briefing` würde zwar gelingen, aber die anschließende `approved`-Prüfung in `phase_listener.py` würde die Briefing-Datei erneut über `find_project_root()` suchen und weiterhin blocken.
- **`_check_adr` (Zeile 459) ist eine Verhaltensänderung, kein reiner Bugfix**: Weil dieser Gate-Zweig bei Leseausfall `None` (= „kein Block") zurückgibt, hat der Root-Cause-Fehler dort seit der Worktree-Pflicht (3.4.10) NICHT zu einer sichtbaren Blockade geführt, sondern das ADR-Gate in JEDER Worktree-Session lautlos übersprungen — stilles Versagen, nicht Blockade. Der Fix schaltet das Gate wieder scharf. Das ist im Sinne der Heartbeat-Konvention aus CLAUDE.md („Readiness statt Liveness" / kein Sicherheits-Theater) klar richtig, muss dem PO in der Spec aber explizit als Reaktivierung benannt werden, nicht als Nebeneffekt versteckt.
- **Referenzmuster bereits im Code vorhanden**: `edit_gate.py:254` löst exakt dieses Problem bereits korrekt (`wt/spec_file` falls vorhanden, sonst `_root/spec_file`) — der Fix in `workflow.py` sollte dieses Muster übernehmen, nicht ein neues erfinden.
- **Pfad-Form bei `cmd_set_briefing` prüfen**: Die aktuelle Worktree liegt unterhalb des Hauptrepos (`.claude/worktrees/<name>/...`). `path.relative_to(root)` (Zeile 981) mit `root = find_project_root()` (Hauptrepo) liefert deshalb aktuell einen Pfad wie `.claude/worktrees/<name>/docs/briefings/x.md` statt `docs/briefings/x.md` — liest sich zufällig noch korrekt zurück, ist aber die falsche Pfad-Form für `po_briefing.file` im Workflow-State UND für den `spec_file`-Stempel im Briefing-Frontmatter, den `ci_spec_gate.py` gegen `docs/briefings/` matcht. Der Fix muss sicherstellen, dass der gespeicherte/gestempelte Pfad worktree-relativ ist (relativ zu `wt`, nicht zu `root`), sonst bricht der CI-Gate-Abgleich nach dem Merge. Keine Migration für bestehenden State nötig — `.claude/workflows/` ist gitignored und ephemer.
- **Keine Regression bei geteiltem State**: Der Fix darf `.claude/workflows/`, `.claude/active_workflow`, Session-Locks, Logs NICHT anfassen — die bleiben bewusst auf `find_project_root()` (Hauptrepo), sonst Rückfall in das mit `resolve_active_workflow()` bereits gelöste Cross-Session-Kontaminationsproblem (Issue #58).
- **CI-Gate unberührt lassen**: `scripts/ci_spec_gate.py` läuft nicht in einer Worktree-Session dieses Frameworks — keine Änderung dort nötig, aber in der Spec explizit als „out of scope" benennen.
- **Kein fünfter Fundort**: Grep über alle `core/hooks/*.py` bestätigt — nur `workflow.py` betroffen (siehe `edit_gate.py`-Zeile in Related Files).
- **Bootstrap-Henne-Ei für den eigenen Workflow**: Dieser Fix-Workflow selbst durchläuft Spec → Briefing → `set-briefing` → Freigabe und trifft dabei auf genau den Bug, den er behebt. Für die eigene PO-Freigabe kommt der PR-#143-Workaround zum Einsatz (`workflow.spec_sha256()` + `workflow.stamp_briefing_frontmatter()` direkt aufrufen), danach in Phase 7 der echte `set-briefing`-Aufruf als Live-Validierungsnachweis, dass der Fix funktioniert.
- **`core/hooks/` ist geschütztes Infra-Territorium**: Jede Änderung braucht laut CLAUDE.md eine freigegebene Spec plus (im Fast Track) Override-Token — hier ohnehin über den Standard-Track abgedeckt.

## Analysis

### Type
Bug

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/workflow.py` | MODIFY | Neuer privater Helper (z.B. `_worktree_first_path(rel)`), basierend auf bereits vorhandenem `_worktree_root_if_any()`; ersetzt die 4 Inline-`find_project_root()`-Aufrufe an den Zeilen 459 (`_check_adr`), 556 (`_read_spec_content`), 673 (`_check_po_briefing`), 977/981 (`cmd_set_briefing`) |
| `tests/test_workflow_resolution_consolidation.py` | MODIFY | 4 neue Testfälle nach vorhandenem Monkeypatch-Muster: `set-briefing` im Worktree, PO-Gate-Read im Worktree, ADR-Gate-Reaktivierung im Worktree, worktree-relative Pfadform (`relative_to`) |

Kein Touch an `hook_utils.py`, `edit_gate.py`, `ci_spec_gate.py` nötig — durch einen unabhängigen Plan/Sonnet-Agenten verifiziert (eigene Code-Lektüre, nicht nur Übernahme meiner Befunde).

### Scope Assessment
- Files: 2 (1 Code, 1 Test)
- Estimated LoC: Code ca. +15–25, Tests ca. +40–80
- Risk Level: MEDIUM — nicht wegen Code-Komplexität (niedrig), sondern weil Punkt 3 (ADR-Gate-Reaktivierung) eine Verhaltensänderung für alle laufenden Worktree-Sessions ist, siehe unten

### Technical Approach
Ein Helper (Arbeitstitel `_worktree_first_path`) in `workflow.py`, der das bereits in `edit_gate.py:254` etablierte Muster kapselt:
```python
def _worktree_first_path(rel: str) -> Path:
    wt = _worktree_root_if_any()
    if wt is not None and (wt / rel).exists():
        return wt / rel
    return find_project_root() / rel
```
Alle 4 Fundstellen auf diesen Helper umstellen. Kein Import aus `hook_utils` nötig (vermeidet die dort dokumentierte zirkuläre-Import-Gefahr), keine neue Duplikation — Konsolidierung von 4 Inline-Vorkommen auf 1 Funktion. Der `path.relative_to(root)`-Pfad in `cmd_set_briefing` (Zeile 981) wird automatisch korrekt (liefert `docs/briefings/x.md` statt Worktree-Präfix-Pfad), sobald `root` durch den worktree-first Helper ersetzt wird — keine separate Änderung nötig.

### Dependencies
Keine externe Abhängigkeit. Alle 4 Stellen teilen denselben Root-Cause-Mechanismus und können in einem Zug gefixt werden; Reihenfolge ist unkritisch (Helper zuerst, dann Callsites).

### Risks (bestätigt durch unabhängigen Plan-Agenten)
- **ADR-Gate-Reaktivierung**: Seit 3.4.10 in jeder Worktree-Session lautlos inaktiv (lenient-by-design). Reaktivierung kann Feature-Branches blockieren, die sich unwissentlich darauf verlassen haben, keine ADR-Sektion ausfüllen zu müssen. → Muss in Spec + CHANGELOG explizit als Verhaltensänderung benannt werden, nicht als versteckter Nebeneffekt.
- **`ci_spec_gate.py`-Abgleich**: Nicht betroffen (läuft serverseitig auf normalem Checkout ohne Worktree-Präfix), aber ein Testfall sollte sicherstellen, dass ein im Worktree gestempeltes Briefing exakt den Pfad enthält, den `ci_spec_gate.py` erwartet — schließt eine Lücke, die aktuell nur "zufällig" durch den Bug nicht sichtbar wird.

### Empfehlung
Ein PR für alle 4 Stellen — gleiche Root Cause, getrennte PRs erzeugen nur Zwischenzustände mit inkonsistentem Verhalten (z.B. `set-briefing` gefixt, aber Freigabe-Gate-Check noch kaputt).

### Open Questions
- [x] Reicht ein Helper für alle 4 Stellen? → Ja, durch Plan-Agent bestätigt.
- [x] Ist `ci_spec_gate.py` betroffen? → Nein, aber Testfall dafür ergänzen.
- [ ] Soll die ADR-Gate-Reaktivierung als eigener CHANGELOG-Eintrag (nicht nur Teil der Bugfix-Zeile) auftauchen? → In Spec vorschlagen, PO entscheidet bei Freigabe.
