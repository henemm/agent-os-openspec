---
entity_id: fix-144-briefing-worktree-path
type: bugfix
created: 2026-09-19
updated: 2026-09-19
status: draft
workflow: fix-144-briefing-worktree-path
---

# Fix: workflow.py löst Spec-/Briefing-Pfade in Worktree-Sessions falsch auf

## Approval

- [ ] Approved

## Purpose

`core/hooks/workflow.py` löst die Pfade der versionierten Spec- und
PO-Briefing-Dateien an vier Stellen über `find_project_root()` auf. Diese
Funktion bildet eine Worktree-Session absichtlich auf das Hauptrepo ab — richtig
für geteilten Workflow-State (`.claude/workflows/`), aber falsch für normale,
committete Repo-Dateien wie Spec und Briefing, die im Arbeitsbaum der Session
(dem Worktree) liegen. Da dieses Repo Worktree-Isolation für jede Session
vorschreibt (`session_singleton_guard.py`), scheitert dadurch in der Praxis
jede Session, die `/30-write-spec` Step 3b befolgt: `workflow.py set-briefing`
findet die eigene Spec/das eigene Briefing nicht, weil beide nur im Worktree
committet sind. Live aufgetreten bei PR #143 (Issue #140), dort mit einem
Workaround umgangen (Issue #144). Diese Spec behebt den Root Cause an allen
vier betroffenen Stellen und macht damit auch das ADR-Gate (`_check_adr`)
wieder scharf, das denselben Fehler bisher lautlos verschluckt hat.

## Source

- **File:** `core/hooks/workflow.py`
- **Identifier:** `def _check_adr`, `def _read_spec_content`, `def _check_po_briefing`, `def cmd_set_briefing`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow._worktree_root_if_any()` | function | Bereits vorhandene, lokale Erkennung ob CWD in einem Git-Worktree liegt (liefert `None` im Hauptrepo). Grundlage des neuen Helpers — bewusst kein Import aus `hook_utils.find_worktree_root()`, um die dort dokumentierte Gefahr zirkulärer Imports zu vermeiden. |
| `workflow.find_project_root()` | function | Bleibt unverändert die Quelle für geteilten State (`.claude/workflows/`, Session-Locks, Logs) — wird NICHT ersetzt, nur um einen worktree-first Vorrang ergänzt für die vier betroffenen Stellen. |
| `core/hooks/edit_gate.py` (Zeile ~254) | reference pattern | Bereits korrekt gelöstes Vorbild für exakt dasselbe Problem bei der Spec-Pfad-Auflösung im TDD-Gate: `spec_path = (wt / spec_file) if (wt is not None and (wt / spec_file).exists()) else (_root / spec_file)`. |
| `phase_listener.py` | consumer | Ruft `_check_adr` und `_check_po_briefing` bei der Freigabe-Phrase auf (Soft-Block) — profitiert direkt vom Fix. |
| `/30-write-spec` Step 3b | consumer | Instruiert den User zu `workflow.py set-briefing docs/briefings/[workflow-name].md` (immer relativer Pfad) — genau der Aufruf, der aktuell in Worktree-Sessions scheitert. |
| `workflow.parse_briefing_frontmatter()` | consumer (test seam) | Von `scripts/ci_spec_gate.py::_find_briefing` genutzt, um `front.get("spec_file")` gegen den Spec-Pfad des PR zu matchen. AC-6 nutzt dieselbe Funktion, um die von `cmd_set_briefing` gestempelte Pfadform gegen die real vom CI-Gate ausgewertete Form zu prüfen — kein bloßer Re-Check von AC-5. |
| `scripts/ci_spec_gate.py` | out-of-scope, aber test-relevant | Läuft serverseitig auf einem normalen PR-Checkout ohne Worktree-Isolation, ist von diesem Fix nicht betroffen. Prüft Pflicht-Sektionen nur über Heading-Namen (`## Scope`, `## Definition of Done`, `## Acceptance Criteria`, `## Test Plan`) — Tabellen- vs. Inline-Format innerhalb einer Section spielt für das Gate keine Rolle. |

## Scope

### Affected Files
| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/workflow.py` | MODIFY | Zwei neue private Helper (`_worktree_first_root(rel)`, `_worktree_first_path(rel)`) auf Basis von `_worktree_root_if_any()`; ersetzen die vier Inline-`find_project_root()`-Aufrufe in `_check_adr` (Zeile ~459), `_read_spec_content` (Zeile ~556), `_check_po_briefing` (Zeile ~673) und `cmd_set_briefing` (Zeile ~977). Reaktiviert dabei das ADR-Gate in Worktree-Sessions (siehe Known Limitations). |
| `tests/test_workflow_resolution_consolidation.py` | MODIFY | 7 neue Testfälle nach dem dort bereits etablierten In-Process-Monkeypatch-Muster: `set-briefing` im Worktree, PO-Gate-Read im Worktree, ADR-Gate-Reaktivierung im Worktree (inkl. korrektem Block bei fehlender ADR-Sektion), worktree-relative Pfadform nach `set-briefing`, Übereinstimmung mit `parse_briefing_frontmatter()`, Hauptrepo-Regression, volle Testsuiten-Regressionsfreiheit. |
| `CHANGELOG.md` | MODIFY | Neuer Eintrag unter `[Unreleased]` → `Fixed`: Konsolidierung der Spec-/Briefing-Pfadauflösung in `workflow.py` auf worktree-first, referenziert Issue #144; benennt explizit die ADR-Gate-Reaktivierung als Verhaltensänderung (nicht nur als Nebensatz der Bugfix-Beschreibung). |

### Estimated Changes
- Files: 3
- LoC: +30/-10 (workflow.py: zwei kleine Helper ~15 Zeilen, vier Callsites je 1-3 Zeilen geändert; Testdatei: +70-100 Zeilen für 7 neue Testfälle; CHANGELOG: +10-15 Zeilen)

## Implementation Details

Zwei neue private Funktionen in `core/hooks/workflow.py`, direkt unterhalb von
`_worktree_root_if_any()`:

```python
def _worktree_first_root(rel: str) -> Path:
    """Root für versionierte Repo-Inhalte (Spec/Briefing): Worktree vor Hauptrepo.

    Anders als find_project_root() (Quelle für geteilten Workflow-State) muss
    hier der tatsächliche Arbeitsbaum gewinnen, wenn die Datei dort existiert
    (Vorbild: edit_gate.py:254). Existiert `rel` in keinem Worktree, bleibt
    find_project_root() der Fallback (Hauptrepo-Sessions, Regressionsfreiheit).
    """
    wt = _worktree_root_if_any()
    if wt is not None and (wt / rel).exists():
        return wt
    return find_project_root()


def _worktree_first_path(rel: str) -> Path:
    return _worktree_first_root(rel) / rel
```

**Callsites:**
- `_check_adr`: `spec_path = find_project_root() / spec_file` → `spec_path = _worktree_first_path(spec_file)`.
- `_read_spec_content`: `(find_project_root() / spec_file).read_text()` → `_worktree_first_path(spec_file).read_text()`.
- `_check_po_briefing`: `(find_project_root() / entry["file"]).read_text()` → `_worktree_first_path(entry["file"]).read_text()`.
- `cmd_set_briefing`, relativer Pfad (dokumentierter Fall aus `/30-write-spec`, z.B. `docs/briefings/x.md`): `root = find_project_root()` → `root = _worktree_first_root(rel)`, danach unverändert `briefing_path = root / rel`. Weil `root` jetzt der Worktree-Root ist, ist `rel` — unverändert der vom User übergebene String — bereits die korrekte worktree-relative Form; keine weitere Umrechnung nötig.
- `cmd_set_briefing`, absoluter Pfad (Randfall, nicht der dokumentierte Aufrufweg): Die bestehende Zeile `rel = str(path.relative_to(root))` wird VOR der obigen Root-Wahl ausgewertet und versucht zuerst `path.relative_to(_worktree_root_if_any() or find_project_root())`; schlägt das mit `ValueError` fehl (Pfad liegt weder im Worktree noch im Hauptrepo), bleibt die bisherige Fehlermeldung `"BLOCKED: Briefing liegt ausserhalb des Projekts"` unverändert. Damit ist die Auswertungsreihenfolge für beide Argumentformen (relativ/absolut) explizit festgelegt, nicht implementierungsoffen.

**Zwei Helper statt einem:** `_read_spec_content`/`_check_adr`/`_check_po_briefing` brauchen nur den fertig zusammengesetzten Pfad, `cmd_set_briefing` braucht zusätzlich den reinen Root-Wert (für die `relative_to()`-Umwandlung bei absolut übergebenen Pfaden). Ein Root-Resolver plus ein dünner Join-Wrapper vermeidet, diese Fallunterscheidung an der Callsite zu duplizieren.

**Kein Touch an:**
- `hook_utils.py` — bereits korrekt (`resolve_active_workflow()` ist das etablierte Vorbild für dasselbe Muster, betrifft aber Workflow-Namen, nicht Datei-Pfade).
- `edit_gate.py` — dient nur als Referenz, ist selbst nicht betroffen.
- `scripts/ci_spec_gate.py` — läuft ohne Worktree-Isolation, nicht betroffen.
- `.claude/workflows/`, `.claude/active_workflow`, Session-Locks, Logs (Zeilen 116, 283, 902, 1092, 1147, 1272, 1463, 1513 in `workflow.py`) — bleiben unverändert auf `find_project_root()`, siehe Known Limitations.

## Expected Behavior

- **Input:** `workflow.py set-briefing docs/briefings/<workflow>.md` (oder `_check_adr`/`_check_po_briefing`/`_read_spec_content` intern) in einer Worktree-Session, bei der Spec und Briefing nur im Worktree committet sind, nicht im Hauptrepo-Checkout.
- **Output:** `set-briefing` registriert das Briefing erfolgreich und stempelt den worktree-relativen Pfad (z.B. `docs/briefings/x.md`) ins Frontmatter; `_check_po_briefing` liest die Briefing-Datei zur Freigabe-Zeit erfolgreich; `_check_adr` liest die Spec erfolgreich und blockiert wie vorgesehen bei fehlender/nicht ausgefüllter ADR-Sektion.
- **Side effects:** Das ADR-Gate (`_check_adr`) wird in Worktree-Sessions reaktiviert. Seit der Worktree-Pflicht (3.4.10) griff es dort lautlos nicht (lenientes Design: Leseausfall → `None` → kein Block), es war also faktisch in jeder Worktree-Session inaktiv. Nach diesem Fix kann die Freigabe-Phrase wieder wegen einer fehlenden/nicht ausgefüllten ADR-Sektion blockiert werden — für Feature-Branches, die sich unwissentlich auf das stille Aussetzen verlassen haben, ist das eine sichtbare Verhaltensänderung, keine reine Fehlerbehebung.

## Known Limitations

- **Geteilter State bleibt bewusst unverändert:** `.claude/workflows/`, `.claude/active_workflow`, Session-Locks und Logs werden weiterhin ausschließlich über `find_project_root()` aufgelöst, nicht über den neuen Helper. Würde man den Helper auch dort einsetzen, entstünde ein Rückfall in das mit `resolve_active_workflow()` bereits gelöste Cross-Session-Kontaminationsproblem (Issue #58): ein anderer Workflow-State könnte fälschlich aus einem fremden Worktree gelesen werden. Diese Trennung ist eine Invariante dieses Fixes, siehe AC-4.
- **`ci_spec_gate.py` bleibt unangetastet:** Läuft serverseitig auf einem normalen PR-Checkout ohne Worktree-Präfix — der Root kommt dort über CWD/CLI-Argument, nicht über die hier geänderten Funktionen. AC-6 verifiziert stattdessen mit derselben Funktion (`parse_briefing_frontmatter`), dass die von `cmd_set_briefing` im Worktree erzeugte Pfadform exakt der Form entspricht, die `ci_spec_gate.py` nach dem Merge einliest.
- **Absolute Pfade als `set-briefing`-Argument:** Der dokumentierte und einzige in `/30-write-spec` verwendete Aufruf übergibt einen relativen Pfad. Für diesen Fall ist der Fix vollständig getestet (AC-1, AC-5, AC-6). Der absolute-Pfad-Randfall ist in den Implementation Details eindeutig spezifiziert (Auflösung zuerst gegen Worktree-Root, Fallback Hauptrepo-Root), aber nicht durch eine eigene Acceptance Criterion abgedeckt, da er außerhalb des dokumentierten Nutzungsmusters liegt.
- **ADR-Gate-Reaktivierung ist eine offene PO-Entscheidung:** Ob die Reaktivierung im CHANGELOG als eigener Eintrag (statt nur als Teilsatz des Bugfix-Eintrags) erscheinen soll, wird bei der Freigabe dieser Spec vom PO entschieden — siehe Vorschlag im CHANGELOG-Scope-Eintrag oben.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] In einer echten Worktree-Session gelingt `workflow.py set-briefing docs/briefings/<name>.md` für eine Spec/ein Briefing, das ausschließlich im Worktree committet ist — als Live-Nachweis wird in Phase 7 dieses Fix-Workflows der reale `set-briefing`-Aufruf verwendet (statt des PR-#143-Workarounds über `spec_sha256()`/`stamp_briefing_frontmatter()` direkt)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1**: GIVEN eine Worktree-Session, in der Spec und Briefing nur im Worktree (nicht im simulierten Hauptrepo) existieren, WHEN `workflow.py set-briefing docs/briefings/x.md` aufgerufen wird, THEN gelingt die Registrierung (kein `BLOCKED: Keine lesbare Spec im Workflow`) und das Frontmatter der Briefing-Datei wird mit `spec_sha256` gestempelt.
- **AC-2**: GIVEN eine Worktree-Session, in der die Briefing-Datei nur im Worktree existiert und im Workflow-State als `po_briefing.file` registriert ist, WHEN `_check_po_briefing()` (bzw. die Freigabe-Phrase über `phase_listener.py`) ausgeführt wird, THEN wird die Briefing-Datei erfolgreich gelesen und das Gate liefert `None` (kein Block wegen Unlesbarkeit).
- **AC-3**: GIVEN eine Worktree-Session, in der die Spec nur im Worktree existiert und KEINE ausgefüllte `## Architektur-Entscheidung (ADR)`-Sektion enthält, WHEN `_check_adr()` ausgeführt wird, THEN wird die Spec erfolgreich gelesen UND das Gate blockiert korrekt mit der Standard-ADR-Fehlermeldung (Nachweis der Reaktivierung, nicht nur eines gelungenen Lesezugriffs).
- **AC-4**: GIVEN kein Worktree (`_worktree_root_if_any()` liefert `None`, simulierter Hauptrepo-Fall), WHEN `_check_adr`, `_read_spec_content`, `_check_po_briefing` oder `cmd_set_briefing` aufgerufen werden, THEN bleibt die Auflösung unverändert ausschließlich über `find_project_root()` (Regressionsfreiheit für Nicht-Worktree-Sessions).
- **AC-5**: GIVEN eine Worktree-Session, WHEN `workflow.py set-briefing docs/briefings/x.md` erfolgreich durchläuft, THEN ist der im Workflow-State (`po_briefing.file`) gespeicherte Pfad worktree-relativ (`docs/briefings/x.md`), NICHT mit einem Worktree-Präfix (z.B. NICHT `.claude/worktrees/<name>/docs/briefings/x.md`).
- **AC-6**: GIVEN die im Worktree entstandene, gestempelte Briefing-Datei aus AC-5, WHEN ihr Inhalt mit `workflow.parse_briefing_frontmatter()` geparst wird (derselben Funktion, die `scripts/ci_spec_gate.py::_find_briefing` serverseitig nutzt), THEN liefert `front.get("spec_file")` exakt den worktree-relativen Pfad der Spec (`docs/specs/x.md`), der nach einem Merge auch im Hauptrepo-Checkout unter demselben Pfad läge.
- **AC-7**: GIVEN die volle Testsuite (`pytest tests/`) vor diesem Fix als Baseline, WHEN die Suite nach diesem Fix erneut ausgeführt wird, THEN gibt es keine neuen Fehlschläge gegenüber der Baseline (nur die in AC-1 bis AC-6 genannten neuen Tests wechseln von rot zu grün).

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden), erweitert in
`tests/test_workflow_resolution_consolidation.py` nach dem dort bereits
etablierten In-Process-Monkeypatch-Muster. Da `workflow.py` `find_project_root`
per `from hook_utils import find_project_root` importiert (Namens-Bindung im
Modul selbst, nicht nur in `hook_utils`), muss in den Tests
`monkeypatch.setattr(wf_module, "find_project_root", ...)` verwendet werden —
ein Patch nur auf `hook_utils.find_project_root` hätte keine Wirkung auf die
vier geänderten Callsites. Ebenso wird `wf_module._worktree_root_if_any`
gemockt (lokale Funktion, kein `hook_utils`-Import), um Worktree- und
Hauptrepo-Root unabhängig voneinander auf zwei unterschiedliche `tmp_path`-
Unterverzeichnisse zu legen (nicht wie im Bestandscode denselben Pfad für
beide) — nur so lässt sich "Datei existiert nur im Worktree, nicht im
Hauptrepo" hermetisch simulieren. AC-6 ruft zusätzlich
`workflow.parse_briefing_frontmatter()` direkt auf der geschriebenen
Briefing-Datei auf, statt nur den Workflow-State zu inspizieren.

- `pytest tests/test_workflow_resolution_consolidation.py -k worktree_first`
- `pytest tests/test_po_briefing_gate.py`
- `pytest tests/test_adr_gate.py`
- `pytest tests/` (volle Regression, AC-7)

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Dieser Fix wendet ein im selben Repo bereits etabliertes, korrektes Muster (`edit_gate.py:254`: Worktree-Root vor Hauptrepo-Root für versionierte Arbeitsbaum-Inhalte) auf vier zusätzliche Stellen in `workflow.py` an. Es wird keine neue Architektur-Entscheidung getroffen, sondern eine bestehende konsequent zu Ende geführt — analog zur Begründung in `resolve-execution-context-consolidation.md`, die aus demselben Grund ebenfalls ohne neue ADR auskam.

## Changelog

- 2026-09-19: Initial spec created
