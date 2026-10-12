---
entity_id: fix-411-allowlist-pfade
type: module
created: 2026-10-12
updated: 2026-10-12
status: draft
version: "1.0"
tags: [hooks, gate, allowlist, sicherheit]
---

# Immer-erlaubt-Liste: Pfad-Randfälle (#411)

## Approval

- [ ] Approved

## Purpose

Die „immer erlaubt“-Liste von `tdd_enforcement` und `post_implementation_gate` entscheidet, welche Dateien ohne Phasen-/TDD-Prüfung bearbeitet werden dürfen (Dokumentation, `.claude/`, Markdown). Drei Randfälle aus der Adversary-Prüfung zu #409 lassen sich heute ausnutzen oder lösen einen Absturz aus; sie werden geschlossen, ohne harmlose Pfade zu verändern.

## Source

- **File:** `core/hooks/hook_utils.py`
- **Identifier:** `_relative_for_allowlist` (Aufrufer `is_hook_always_allowed`; genutzt von `tdd_enforcement.py:256` und `post_implementation_gate.py:155`)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `posixpath` | stdlib (neu) | Normalisierung von `..` und `.` im relativen Pfad |
| `_hook_candidate_roots` | function | Wurzel-Ermittlung (unverändert) |
| `tests/test_always_allowed_worktree_409.py` | tests | Vorlage und Ablageort der neuen Tests |

## Scope

- **Affected Files:** `core/hooks/hook_utils.py`, `tests/test_always_allowed_worktree_409.py`, `CHANGELOG.md`
- **Estimated Changes:** ~15 LoC Code, ~40 LoC Tests
- Die beiden Aufrufer bleiben unverändert. Nicht im Scope: `edit_gate.py`, `bash_gate.py` (#417).

## Implementation Details

Reihenfolge in `_relative_for_allowlist` (festgelegt, Rückgabe `None` = „außerhalb, frei“, `""` = „nicht frei“, weil keine Regex-Alternative auf den leeren String passt):

```
1. Pfad bestimmen wie bisher
   - absolut: resolve() + relativ zur Wurzel
   - relativ: "\" -> "/"
   - resolve() darf zusätzlich ValueError (NUL-Byte) werfen -> Ergebnis "" (F002)
2. rel = posixpath.normpath(rel)            # docs/../src/x.py -> src/x.py (F001)
   beginnt rel mit ".." oder ist absolut    -> "" (Ausbruch nach oben: nicht frei)
3. Worktree-Präfix ".claude/worktrees/<n>/" in Schleife entfernen,
   bis keiner mehr passt (F003; absolute und relative Pfade)
```

Normalisieren **vor** dem Präfix-Abschneiden: So wird `.claude/worktrees/a/../../../src/x.py` zu `../src/x.py` und gilt als nicht frei. Harmlose Pfade bleiben unverändert (`docs/a.md`, `./docs/a.md` → `docs/a.md`, `.claude/x`).

## Expected Behavior

- **Input:** Dateipfad (absolut oder relativ) aus dem Tool-Aufruf.
- **Output:** `is_hook_always_allowed` liefert für `docs/../src/x.py`, `../x`, `docs/../../x`, NUL-Byte-Pfade und verschachtelte Worktree-Präfixe vor Code-Dateien `False`; für `docs/a.md`, `./docs/a.md`, `.claude/x` weiter `True`.
- **Side effects:** Keine. Kein Traceback mehr bei NUL-Byte im Pfad.

## Known Limitations

- Symlinks in relativen Pfaden werden nicht aufgelöst (wie bisher); nur die Zeichenkette wird normalisiert.
- Die Liste bleibt bewusst nicht an `edit_gate` angeglichen.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Pfad wie `docs/../src/x.py` wird von beiden Gates wie eine normale Code-Datei geprüft statt durchgewunken
- [ ] Ein Pfad mit NUL-Byte führt zu einer normalen Prüfung statt zu einem Absturz (Exit 1)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given ein relativer Pfad mit `..`, der aus einem Freigabe-Ordner auf Code zeigt (`docs/../src/x.py`) / When `is_hook_always_allowed` ihn prüft / Then ist das Ergebnis `False`
  - Test: tests/test_always_allowed_worktree_409.py::test_relativer_pfad_mit_punktpunkt_ist_nicht_frei
- **AC-2:** Given ein Pfad, der nach oben aus der Wurzel ausbricht (`../x`, `docs/../../x`, `.claude/worktrees/a/../../../src/x.py`) / When geprüft / Then ist das Ergebnis `False`
  - Test: tests/test_always_allowed_worktree_409.py::test_ausbruch_nach_oben_ist_nicht_frei
- **AC-3:** Given ein Pfad mit NUL-Byte (absolut und relativ) / When geprüft / Then wirft die Funktion keine Ausnahme und liefert `False`
  - Test: tests/test_always_allowed_worktree_409.py::test_nul_byte_im_pfad_ist_nicht_frei_ohne_absturz
- **AC-4:** Given ein verschachteltes Präfix `.claude/worktrees/a/.claude/worktrees/b/src/x.py` (absolut und relativ) / When geprüft / Then ist das Ergebnis `False`, während `.claude/worktrees/a/.claude/worktrees/b/docs/x.md` `True` bleibt
  - Test: tests/test_always_allowed_worktree_409.py::test_verschachtelte_worktree_praefixe
- **AC-5:** Given harmlose Pfade (`docs/a.md`, `./docs/a.md`, `.claude/x`) / When geprüft / Then bleiben sie `True`; die bestehenden #409-Tests bleiben grün
  - Test: tests/test_always_allowed_worktree_409.py::test_harmlose_pfade_bleiben_frei
- **AC-6:** Given ein Edit-Aufruf mit NUL-Byte-Pfad / When `tdd_enforcement.py` bzw. `post_implementation_gate.py` als Subprozess läuft / Then endet keiner mit Traceback (Exit 1)
  - Test: tests/test_always_allowed_worktree_409.py::test_gates_stuerzen_bei_nul_byte_nicht_ab

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_always_allowed_worktree_409.py`
- Regressionslauf: `pytest tests/` (Gate-Tests)

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Lokale Härtung einer Hilfsfunktion; keine neue Struktur- oder Technikentscheidung, die Aufrufer und Schnittstelle bleiben gleich.

## Changelog

- 2026-10-12: Initial spec created
