---
entity_id: fix-230-spec-freeze-after-approval
type: bugfix
created: 2026-09-28
updated: 2026-09-28
status: draft
version: "1.0"
tags: [edit_gate, po-briefing-gate, hooks]
---

# Fix #230: Spec-Freeze nach Freigabe

## Approval

- [ ] Approved

## Purpose

`/60-validate` blockierte den Übergang nach `phase8_complete`, weil Step 3 (docs-updater-Agent)
die bereits freigegebene Spec-Datei anfasste (Status-Feld, AC-Checkboxen) und damit ihren
`spec_sha256()`-Hash veränderte — bevor Step 4 (`workflow.py phase phase8_complete`) lief.
`_check_po_briefing()` prüft diesen Hash für **jede** Vorwärts-Transition mit `tgt_idx >=
PHASES.index("phase4_approved")`, trifft also auch `phase8_complete`, und blockt mit „PO-Briefing
ist veraltet — die Spec wurde nach dem Briefing geändert." Dieser Fix erzwingt technisch (nicht nur
per Dokumentation), dass eine freigegebene Spec danach nicht mehr verändert wird — der eigentliche
Auslöser des Hash-Drifts entfällt damit, statt ihn abzufedern.

## Source

- **File:** `core/hooks/edit_gate.py`
- **Identifier:** `main()` — neuer Check „1d. Spec-Freeze nach Freigabe", eingefügt nach Schritt 1c
  (Path Origin) und vor Schritt 2 (Always-Allowed Dirs/Patterns)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/workflow.py::_check_po_briefing` | Function | Der Hash-Vergleich, den dieser Guard proaktiv verhindert statt reaktiv zu erkennen |
| `core/hooks/workflow.py::PHASES` | Constant | Referenz für den `phase4_approved`-Index, gegen den der neue Check vergleicht |
| `core/hooks/override_token.py::has_valid_token` | Function | Bestehender Fluchtweg (User tippt „override", 1h TTL) für eine echte, gewollte Nachbesserung |
| `core/agents/docs-updater.md` | Agent-Doku | Darf die Entity-Spec nach Freigabe nicht mehr als Bearbeitungsziel führen |
| `core/commands/60-validate.md` | Command-Doku | Step 3 darf `spec_file_path` nicht mehr als Edit-Ziel an den docs-updater übergeben |
| `docs/specs/_template.md` | Template | Darf keinen Platzhalter mehr enthalten, der eine nachträgliche Spec-Änderung verspricht |

## Scope

- **Affected Files:** `core/hooks/edit_gate.py`, `core/agents/docs-updater.md`,
  `core/commands/60-validate.md`, `docs/specs/_template.md`,
  `tests/test_edit_gate_spec_freeze_230.py` (neu)
- **Estimated Changes:** ~+90/-15 LoC (überwiegend Markdown-Text, ein neuer Check in
  `edit_gate.py`, ein neues Testfile)

## Implementation Details

**Root Cause (Prüfreihenfolge in `edit_gate.py::main()`):** Die Spec liegt unter
`docs/specs/*.md`. Zwei bestehende, früh greifende Kurzschlüsse würden den neuen Check nie
erreichen, wenn er zu spät eingefügt wird:

- Schritt 2 (`ALWAYS_ALLOWED_DIRS`, Zeile ~42-45): enthält `"docs/"` — jede Datei unter `docs/`
  wird hier sofort per `allow()` durchgewunken.
- Schritt 2b (`ALWAYS_ALLOWED_PATTERNS`, Zeile ~47-50): enthält `r"\.md$"` — jede `.md`-Datei wird
  hier sofort per `allow()` durchgewunken.

Der neue Check **muss deshalb vor Schritt 2** eingefügt werden — direkt nach Schritt 1c (Path
Origin, `_is_outside_project`), analog zur Position von `claude_md_protection.py` im
`hooks.json`-Kettenmuster (eigenständiger Schutz-Check, der VOR den allgemeinen
Always-Allowed-Regeln greift).

```
1. Protected State Files → BLOCK
1b. Orchestrator-Only Files → BLOCK
1c. Path Origin (ausserhalb Projekt) → ALLOW
1d. Spec-Freeze nach Freigabe (NEU) → BLOCK, wenn Ziel-Datei eine bereits
    freigegebene spec_file ist und kein Override-Token vorliegt
2. Always-Allowed Dirs (docs/, tests/, ...) → ALLOW
2b. Always-Allowed Patterns (.md, .json, ...) → ALLOW
...
```

**Neue Helper-Funktion** `_find_workflow_by_spec_file(file_path) -> dict | None`, analog zu
`_find_workflow_for_file()` (Zeile ~178-198), aber mit anderem Matching-Feld:

```python
def _find_workflow_by_spec_file(file_path: str) -> dict | None:
    """Findet den Workflow, dessen `spec_file` dem Zielpfad entspricht.

    Prüft zuerst den aktiven Workflow (_read_active_workflow()), dann alle
    Workflow-JSONs (Vorbild: _find_workflow_for_file, aber Matching-Feld ist
    `spec_file`, nicht `affected_files`). Archivierte Workflows (`_archive/`)
    werden ausgeschlossen — eine archivierte Spec ist kein Freeze-Ziel mehr.
    """
    candidate = _read_active_workflow()
    if candidate and _matches_spec_file(candidate, file_path):
        return candidate
    wf_dir = _root / ".claude" / "workflows"
    if not wf_dir.exists():
        return None
    for f in wf_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if _matches_spec_file(data, file_path):
            return data
    return None
```

`_matches_spec_file(data, file_path)` normalisiert beide Pfade relativ zu `_root` (gleiches Muster
wie in `_find_workflow_for_file`: `rel.endswith("/" + af) or af.endswith("/" + rel)`) und vergleicht
gegen `data.get("spec_file")`.

**Neuer Check (Schritt 1d):**

```python
# 1d. Spec-Freeze nach Freigabe (#230): eine freigegebene Spec darf nicht mehr
# angefasst werden — jede Änderung verschiebt spec_sha256() und blockt jede
# spätere Transition >= phase4_approved über _check_po_briefing().
spec_workflow = _find_workflow_by_spec_file(file_path)
if spec_workflow is not None:
    phase = spec_workflow.get("current_phase", "phase0_idle")
    from workflow import PHASES  # gleiche Quelle wie _check_po_briefing
    if phase in PHASES and PHASES.index(phase) >= PHASES.index("phase4_approved"):
        wf_name = spec_workflow.get("name", "unknown")
        if not (_has_override_token(wf_name) or _has_override_token("__infra__")
                or _has_override_token()):
            block(
                "BLOCKED: Freigegebene Spec darf nicht mehr geändert werden "
                f"({Path(file_path).name}, Phase {phase}).\n"
                "→ Jede Änderung verschiebt den PO-Briefing-Hash und blockt "
                "phase8_complete (#230).\n"
                "→ Regulärer Weg für eine gewollte Nachbesserung: User tippt "
                "'override' (gilt 1 h, protokolliert in "
                ".claude/user_override_token.json)."
            )
```

Import von `PHASES` aus `workflow.py` folgt demselben Modul-Import-Muster wie andere
Cross-Referenzen in `edit_gate.py` (z.B. `override_token.has_valid_token`) — kein neuer
Abhängigkeitspfad.

**Docs-Änderungen (Begleitmaßnahme, nicht der technische Kern):**

- `core/agents/docs-updater.md`: Zeile „Entity specs | `docs/specs/[type]/[entity_id].md`" in der
  Tabelle „Documentation Locations" bekommt einen expliziten Zusatz: Freigegebene Specs (Phase ≥
  `phase4_approved`) sind schreibgeschützt — der Agent aktualisiert Status/AC-Checkboxen dort
  NICHT, auch nicht nach erfolgreicher Validierung. Grund im Fließtext kurz benennen (Hash-Bindung
  an PO-Briefing).
- `core/commands/60-validate.md`: Step 3 (docs-updater-Dispatch) übergibt `spec_file_path` weiterhin
  als **Kontext** (der Agent darf sie lesen, um Feature-Docs zu aktualisieren), aber der Auftragstext
  nennt sie nicht mehr als Bearbeitungsziel. Ergänzender Hinweis im Prompt-Text: „Die Spec-Datei
  selbst NICHT bearbeiten — sie ist nach Freigabe eingefroren (#230)."
- `docs/specs/_template.md`: Platzhalter `Test: *(wird nach der TDD-RED-Phase eingetragen)*` unter
  „Acceptance Criteria" entfernt/umformuliert zu einem Hinweis, dass die Test-Zuordnung in den
  TDD-RED-Artefakten (`workflow.py add-artifact`) bzw. im Test Plan der Spec selbst — bereits bei
  Erstellung — erfolgt, nicht als nachträgliche Bearbeitung der freigegebenen Datei.

## Expected Behavior

- **Input:** Ein `Edit`/`Write`-Tool-Aufruf, dessen `file_path` der `spec_file` eines Workflows
  entspricht.
- **Output:**
  - Phase des Workflows `< phase4_approved` → `allow()` (unverändert wie bisher, Spec darf während
    der Erstellung frei bearbeitet werden).
  - Phase `>= phase4_approved` (also `phase4_approved` bis `phase8_complete`) ohne gültigen
    Override-Token → `block()` mit Hinweis auf den Override-Weg.
  - Phase `>= phase4_approved` **mit** gültigem Override-Token (`wf_name`, `__infra__` oder
    global) → `allow()`.
- **Side effects:** `docs-updater` bearbeitet die Entity-Spec nach Freigabe nicht mehr — der
  PO-Briefing-Hash bleibt über die gesamte Restlaufzeit des Workflows stabil, `phase8_complete`
  wird nicht mehr durch Fremd-Änderungen an der Spec blockiert.

## Known Limitations

- Der Guard matcht ausschließlich über den in der Workflow-JSON gespeicherten `spec_file`-Pfad
  (relativer Pfadvergleich, gleiches Muster wie `_find_workflow_for_file`). Wird eine Spec
  außerhalb dieses erfassten Pfads verschoben oder umbenannt, greift der Schutz nicht mehr — dieselbe
  Einschränkung, die auch der bestehende `_find_workflow_for_file`-Mechanismus hat.
- Für bereits vor diesem Fix hängengebliebene Workflows (z.B. Issue #230 selbst, dessen
  Briefing-Hash schon vor dem Fix veraltet ist) löst dieser Guard das bestehende Drift-Problem
  nicht rückwirkend — dafür bleibt der bestehende `override`-Fluchtweg der Ausweg.
- `scripts/ci_spec_gate.py` bleibt unverändert: Da die Spec nach diesem Fix gar nicht mehr
  nachträglich verändert wird, entsteht der Hash-Drift serverseitig erst gar nicht — eine
  CI-seitige Spiegelung dieses Guards ist nicht nötig, solange niemand den lokalen Override nutzt,
  um trotzdem eine freigegebene Spec zu ändern, ohne das Briefing neu zu stempeln (bestehendes,
  unverändertes Restrisiko, nicht neu durch diesen Fix).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein `/60-validate`-Durchlauf, bei dem der docs-updater aktiv Feature-Docs aktualisiert, ändert
      die Entity-Spec-Datei nicht mehr — sichtbar daran, dass `phase8_complete` erreicht wird, ohne
      dass „PO-Briefing ist veraltet" ausgelöst wird
- [ ] Ein Versuch, die freigegebene Spec-Datei direkt per Edit/Write zu ändern, wird ohne
      Override-Wort mit einer klaren Fehlermeldung blockiert; mit dem Wort „override" gelingt die
      Änderung trotzdem
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, insbesondere
      `tests/test_po_briefing_gate.py` und die bestehenden `edit_gate`-Tests)

## Acceptance Criteria

- **AC-1:** Given ein Workflow in Phase `phase3_spec` (vor Freigabe) mit gesetztem `spec_file` / When ein Edit-Tool-Aufruf genau diese Spec-Datei ändert / Then erlaubt `edit_gate.py` die Änderung unverändert wie bisher (`allow()`, Exit-Code 0).
- **AC-2:** Given ein Workflow in Phase `phase4_approved` oder später (z.B. `phase8_complete`) mit gesetztem `spec_file` und ohne registrierten Override-Token / When ein Edit-Tool-Aufruf genau diese Spec-Datei ändert / Then blockiert `edit_gate.py` die Änderung (`block()`, Exit-Code 2) mit einer Meldung, die auf den Override-Weg verweist.
- **AC-3:** Given derselbe Workflow-Zustand wie in AC-2 (Phase `>= phase4_approved`), aber mit einem gültigen, nicht abgelaufenen Override-Token für diesen Workflow / When derselbe Edit-Tool-Aufruf auf die Spec-Datei erfolgt / Then erlaubt `edit_gate.py` die Änderung trotzdem (`allow()`, Exit-Code 0).
- **AC-4:** Given die Datei `core/agents/docs-updater.md` nach diesem Fix / When ihr Abschnitt „Documentation Locations" gelesen wird / Then enthält er eine explizite Regel, dass eine bereits freigegebene Entity-Spec (Phase ≥ approved) nicht mehr bearbeitet werden darf, statt sie unbedingt als Bearbeitungsziel zu listen.
- **AC-5:** Given die Datei `core/commands/60-validate.md` nach diesem Fix / When der Auftragstext von Step 3 (docs-updater-Dispatch) gelesen wird / Then nennt er die Spec-Datei nicht mehr als Bearbeitungsziel, sondern höchstens als Lesekontext, und weist ausdrücklich darauf hin, dass die Spec eingefroren ist.
- **AC-6:** Given die Datei `docs/specs/_template.md` nach diesem Fix / When der Abschnitt „Acceptance Criteria" gelesen wird / Then enthält er nicht mehr den Platzhaltertext „wird nach der TDD-RED-Phase eingetragen", der eine nachträgliche Bearbeitung der freigegebenen Spec verspricht.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden), neu in
`tests/test_edit_gate_spec_freeze_230.py`:

- `test_edit_before_approval_allowed` (AC-1): Workflow-JSON mit `current_phase: phase3_spec` und
  `spec_file` auf eine Test-Spec, Edit-Tool-Input auf dieselbe Datei → Exit-Code 0.
- `test_edit_at_approval_blocked` (AC-2): `current_phase: phase4_approved`, kein Override-Token →
  Exit-Code 2, Meldung erwähnt „override".
- `test_edit_after_approval_blocked` (AC-2): `current_phase: phase8_complete`, kein Override-Token
  → Exit-Code 2 (deckt den ursprünglichen #230-Fall ab, in dem der Block erst spät in der Phase
  auftrat).
- `test_edit_with_override_allowed` (AC-3): `current_phase: phase8_complete` +
  vorbereitete `.claude/user_override_token.json` mit gültigem, nicht abgelaufenem Token → Exit-Code
  0.
- `test_docs_updater_no_longer_promises_unconditional_spec_edit` (AC-4): liest
  `core/agents/docs-updater.md`, prüft per Regex/Substring auf die neue Freeze-Regel.
- `test_validate_command_spec_file_not_edit_target` (AC-5): liest `core/commands/60-validate.md`,
  prüft, dass der Step-3-Prompt-Text die Spec nicht mehr als Bearbeitungsziel nennt und den
  Freeze-Hinweis enthält.
- `test_template_placeholder_removed` (AC-6): liest `docs/specs/_template.md`, prüft Abwesenheit von
  „wird nach der TDD-RED-Phase eingetragen".

Setup-Muster (Workflow-JSON + Tool-Input simulieren, Override-Token vorbereiten) folgt einem
bestehenden `test_edit_gate_*`-File im `tests/`-Verzeichnis (z.B.
`tests/test_loc_gate_worktree_root_96.py`).

Zusätzlich Regressionslauf der vollständigen Suite, insbesondere `tests/test_po_briefing_gate.py`
(27 bestehende Tests) und aller vorhandenen `edit_gate`-Tests.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung erweitert bestehende Kernlogik in `edit_gate.py` um einen zusätzlichen
  Schutz-Check, exakt nach dem bereits etablierten Muster von `claude_md_protection.py`
  (Datei-Schutz + Override-Fluchtweg). Es wird kein neues Architekturmuster, keine neue Technologie
  und kein neuer Dienst eingeführt — die Entscheidung ist eine lokale, technische Ergänzung
  innerhalb des Verantwortungsbereichs von Claude (CLAUDE.md-Rollenregel), kein PO-Thema.

## Changelog

- 2026-09-28: Initial spec created (Issue #230, Weg 3 aus der Analyse — Spec-Freeze nach Freigabe,
  technisch durchgesetzt über `edit_gate.py`)
