---
entity_id: feat-490-plan-issue-titel
type: feature
created: 2026-10-30
updated: 2026-10-30
status: draft
version: "1.0"
workflow: feat-490-plan-issue-titel
tags: [herdr, workflow, plan, github]
---

# Plan-Pane: Kurztitel des Issues unter der Nummer (Issue #490)

## Approval

- [ ] Approved

## Purpose

Der Workflow-Plan (#476) zeigt nur `Workflow #N` und den Workflow-Namen. Der PO weiss dann oft nicht, welches Thema hinter der Nummer steckt. Kuenftig steht unter dem Namen der Titel des GitHub-Issues, gekuerzt auf hoechstens 6 Woerter. Der Titel wird einmal per `gh` geholt und zwischengespeichert. Ohne `gh`, ohne Netz oder ohne Issue fehlt die Zeile einfach; Start und Anzeige werden nie verzoegert oder blockiert.

## Source

- **File:** `core/hooks/workflow.py`
- **Identifier:** `short_title`, `cached_issue_title`, `fetch_issue_title`, CLI `issue-title`, `render_plan` (liest `issue_title`), `_plan_active`, `_plan_watch`, `cmd_start`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/workflow.py` (#476/#478) | module | `render_plan`, `_plan_active`, `_plan_watch`, `cmd_plan`, `cmd_start`, `issue_number`, `_workflows_dir` |
| `gh` (GitHub CLI) | extern | `gh issue view N --json title -q .title` im Projektordner |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | Kurztitel kuerzen, cachen, holen; Anzeige im Plan; Abruf beim Start (abgekoppelt) und im Watcher |
| tests/test_plan_issue_titel_490.py | CREATE | Kuerzung, Anzeige, Cache, Abruf per Stub-`gh`, Fail-open |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 2 geaendert
- LoC: +70 Produktion / +150 Test
- Risk Level: LOW (nur Anzeige; jeder Fehler fuehrt zu „keine Titelzeile“)

## Implementation Details

**Cache.** `.claude/issue_titles.json` neben dem Workflow-Ordner (`_workflows_dir().parent`), Inhalt `{"<N>": "<Kurztitel>"}`. Bewusst nicht im Workflow-State: kein Wettlauf mit Phasenwechseln, und laufende Workflows profitieren sofort. Schreiben atomar (tmp + replace). Kaputte oder fehlende Datei gilt als leer.

**`short_title(title, max_words=6) -> str`** (pure): Leerraum normalisieren, die ersten 6 Woerter; waren es mehr, folgt `…`. Leer/kein String → `""`.

**`cached_issue_title(issue) -> str | None`:** Eintrag aus dem Cache oder None; wirft nie.

**`fetch_issue_title(issue, timeout=8) -> str | None`:** Ist `gh` nicht auf `PATH` → None. Sonst `gh issue view <N> --json title -q .title` mit `cwd=find_project_root()` und Timeout; Exit != 0, leere Ausgabe, Timeout oder Fehler → None. Bei Erfolg Kurztitel bilden, in den Cache schreiben, zurueckgeben. Wirft nie.

**CLI `workflow.py issue-title <N>`:** ruft `fetch_issue_title`, gibt den Kurztitel oder nichts aus, Exit immer 0.

**Start.** `cmd_start` stoesst bei einer Issue-Nummer im Namen `workflow.py issue-title <N>` abgekoppelt an (`subprocess.Popen`, stdin/stdout/stderr auf devnull, `start_new_session=True`), ohne zu warten; Fehler werden geschluckt. Ist der Titel schon im Cache, entfaellt der Abruf.

**Anzeige.** `render_plan` bleibt pure: Ist `data["issue_title"]` ein nicht leerer String, steht er als dritte Zeile direkt unter dem Namen (vor der Leerzeile), sonst entfaellt die Zeile. `_plan_active` (und der Archiv-Zweig im Watcher) setzt `issue_title` aus dem Cache, falls vorhanden. `_plan_watch` holt einen fehlenden Titel hoechstens einmal je Issue-Nummer und Prozess per `fetch_issue_title` — erst nach dem Zeichnen der Runde, damit die Anzeige nicht wartet; die naechste Runde zeigt ihn.

## Expected Behavior

- **Input:** Workflow `feat-490-plan-issue-titel`, Issue #490 mit Titel „Plan-Pane: Kurzbeschreibung des Issues (5–6 Wörter) unter der Nummer“
- **Output:** Plan zeigt `Workflow #490`, `feat-490-plan-issue-titel`, `Plan-Pane: Kurzbeschreibung des Issues (5–6 Wörter)…`
- **Side effects:** Datei `.claude/issue_titles.json`

## Known Limitations

- Aendert sich der Issue-Titel spaeter, bleibt der zwischengespeicherte Titel stehen (Loeschen der Datei holt ihn neu).
- Nur GitHub-Issues ueber `gh`; andere Tracker zeigen keine Titelzeile.
- Gekuerzt wird mechanisch auf die ersten 6 Woerter, nicht inhaltlich zusammengefasst.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Im Herdr-Plan-Pane steht unter der Nummer der Kurztitel des Issues (manuelle Abnahme durch den PO)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen, insbesondere #476/#478-Tests)

## Acceptance Criteria

- **AC-1:** Given die Titel „Plan-Pane: Kurzbeschreibung des Issues (5–6 Wörter) unter der Nummer“, „Kurzer Titel“, „  a   b  “ und „“ / When `short_title` laeuft / Then ergibt das „Plan-Pane: Kurzbeschreibung des Issues (5–6 Wörter)…“, „Kurzer Titel“, „a b“ und „“
  - Test: tests/test_plan_issue_titel_490.py::test_short_title

- **AC-2:** Given Workflow-Daten mit `issue_title` „Kurzer Titel“ / When `render_plan` laeuft / Then sind die ersten drei Zeilen `Workflow #N`, Name, „Kurzer Titel“; ohne `issue_title` (oder leer) bleibt die Ausgabe exakt wie bisher
  - Test: tests/test_plan_issue_titel_490.py::test_render_shows_title_line

- **AC-3:** Given ein Projekt mit aktivem Workflow `feat-490-x` und Cache-Eintrag `{"490": "Kurzer Titel"}` / When `workflow.py plan` laeuft / Then enthaelt die Ausgabe die Zeile „Kurzer Titel“ direkt unter dem Namen; bei kaputter Cache-Datei fehlt die Zeile und der Exit-Code ist 0
  - Test: tests/test_plan_issue_titel_490.py::test_plan_cli_uses_cache

- **AC-4:** Given ein Stub-`gh` auf `PATH`, der fuer `issue view 490` den Titel ausgibt / When `workflow.py issue-title 490` laeuft / Then gibt es den Kurztitel aus und der Cache enthaelt ihn; liefert der Stub Exit 1 oder fehlt `gh` auf `PATH`, ist die Ausgabe leer, der Exit-Code 0 und der Cache unveraendert
  - Test: tests/test_plan_issue_titel_490.py::test_issue_title_cli_fetch_and_fail_open

- **AC-5:** Given ein Stub-`gh`, das 3 s schlaeft / When `workflow.py start feat-490-x` laeuft / Then endet der Start in unter 2 s mit Exit 0, und kurz danach steht der Titel im Cache
  - Test: tests/test_plan_issue_titel_490.py::test_start_fetches_detached

- **AC-6:** Given `plan --watch` mit 3 Runden (`OPENSPEC_PLAN_WATCH_ROUNDS=3`, Intervall 0), Stub-`gh` mit Titel und leerer Cache / When der Watcher laeuft / Then zeigt eine spaetere Ausgabe den Kurztitel, und der Stub wurde genau einmal aufgerufen
  - Test: tests/test_plan_issue_titel_490.py::test_watch_fetches_once

## Test Plan

Pure Funktionen per Import; CLI per Subprozess in isoliertem Projekt (`CLAUDE_PROJECT_DIR`, Muster `tests/test_herdr_plan_pane_476.py`); Stub-`gh` als Shell-Skript auf `PATH`, das Aufrufe in eine Datei protokolliert.

- `pytest tests/test_plan_issue_titel_490.py`
- Regressionslauf: `pytest tests/`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Reine Anzeige-Erweiterung des bestehenden Plans mit eigener Cache-Datei; kein neues State-Feld, kein Gate. Reversibel durch Loeschen der Datei.

## Changelog

- 2026-10-30: Initial spec created
