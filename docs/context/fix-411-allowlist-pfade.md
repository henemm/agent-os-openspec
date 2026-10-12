# Context: fix-411-allowlist-pfade

## Request Summary
Issue #411 (Epic #429, Meilenstein 3.41): Drei Restbefunde aus der Adversary-Prüfung zu #409 in der
„immer erlaubt“-Liste von `tdd_enforcement` und `post_implementation_gate` schließen: relative
`..`-Pfade (F001, MEDIUM, Regression), NUL-Byte im Pfad (F002), verschachtelte Worktree-Präfixe (F003).

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/hook_utils.py:1790-1865 | `_HOOK_ALWAYS_ALLOWED`, `_WORKTREE_PREFIX_RE`, `_relative_for_allowlist`, `is_hook_always_allowed` — die einzige Code-Stelle der Änderung |
| core/hooks/tdd_enforcement.py:256 | Einziger Aufrufer 1: `if is_hook_always_allowed(file_path): allow` |
| core/hooks/post_implementation_gate.py:155 | Einziger Aufrufer 2, gleiche Verwendung |
| tests/test_always_allowed_worktree_409.py | Bestehende Tests des Helfers (#409); Vorlage für Stil und Sandbox |

## Ist-Verhalten je Befund
- **F001:** Relative Pfade gehen ungeprüft durch (`rel = raw.replace("\\", "/")`). `docs/../src/x.py`
  trifft die Regex (`(^|/)docs/`) und gilt als frei, obwohl er auf `src/x.py` zeigt. Absolute Pfade sind
  sicher, weil `resolve()` normalisiert.
- **F002:** `Path.resolve()` wirft bei NUL-Byte `ValueError`; gefangen werden nur `OSError, RuntimeError`.
  Folge: Traceback, Exit 1 in beiden Gates (faktisch fail-open).
- **F003:** `_WORKTREE_PREFIX_RE.sub(..., count=1)` schneidet nur ein `.claude/worktrees/<n>/` ab. Bei
  `.claude/worktrees/a/.claude/worktrees/b/src/x.py` bleibt `.claude/worktrees/b/src/x.py` übrig; die
  Regex `^\.claude/` gibt es frei.

## Existing Patterns
- Rückgabe `None` bedeutet „außerhalb Projekt/Worktree“ und wird vom Aufrufer als FREI gewertet. Ein
  „nicht frei“-Ergebnis muss deshalb ein String sein, auf den die Regex nicht passt (z. B. `""`).
- Fail-safe-Prinzip im Bestand: ist die Wurzel nicht ermittelbar, wird nur der Dateiname bewertet.
- Die Funktion ist bewusst nicht an `edit_gate` angeglichen (Kommentar im Code).

## Dependencies
- Upstream: `find_project_root`, `_find_worktree_root`, `pathlib`, `re`. Neu: `posixpath.normpath`.
- Downstream: genau die zwei Aufrufer oben; keine weiteren Verwender (`grep` über `core/`).

## Existing Specs
- Keine Entity-Spec; Vorgänger-Arbeit #409 liegt in `tests/test_always_allowed_worktree_409.py`.

## Risks & Considerations
- **Hochrisiko-Datei:** Gate-Hilfsfunktion; ein zu großzügiger Fix öffnet eine Schutzlücke, ein zu strenger
  blockt legitime `docs/`-Edits. Adversary mit 2 Runden.
- Normalisierung darf harmlose relative Pfade nicht ändern (`docs/a.md`, `./docs/a.md`, `.claude/x`).
- `..`-Ausbruch nach oben (`../x`, `docs/../../x`) ist weder „innerhalb“ noch „außerhalb“ sicher
  bewertbar → als NICHT frei werten (Gate prüft).
- Reihenfolge: erst Worktree-Präfix(e) entfernen, dann normalisieren, sonst umgeht
  `.claude/worktrees/a/../../../src/x.py` die Prüfung — oder umgekehrt; in der Spec festlegen.
- Auch absolute Pfade durchlaufen die Präfix-Schleife (F003 gilt für beide Pfadarten).
- Abgrenzung #417 (Bash-Schreibziele): anderer Code (`bash_gate.py`), keine Überschneidung.

## Analysis

### Type
Bug (Sicherheitslücke in Gate-Hilfsfunktion, Regression aus #409)

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/hook_utils.py | MODIFY | `_relative_for_allowlist`: Normalisierung, Präfix-Schleife, ValueError fangen |
| tests/test_always_allowed_worktree_409.py | MODIFY | Je ein Test pro Befund F001/F002/F003 (+ Regressionsfälle) |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Scope Assessment
- Files: 3
- Estimated LoC: +~15 Code / +~40 Tests
- Risk Level: MEDIUM (Gate-Hilfsfunktion; Fehler öffnet Schutzlücke oder blockt `docs/`-Edits)

### Technical Approach
Reihenfolge in `_relative_for_allowlist` (festgelegt):
1. Pfad bestimmen wie bisher (absolut: `resolve()` + relativ zur Wurzel; relativ: `\` → `/`).
2. `posixpath.normpath` auf den relativen String. Beginnt das Ergebnis mit `..` (Ausbruch nach oben) → `""` zurückgeben (= nicht frei, Regex passt nicht; `None` wäre "frei").
3. Worktree-Präfix `.claude/worktrees/<n>/` in Schleife entfernen, bis keiner mehr passt (F003, gilt für absolut und relativ).
4. Normalisieren zuerst, Präfix danach: so umgeht `.claude/worktrees/a/../../../src/x.py` die Prüfung nicht (wird zu `../src/x.py` → nicht frei).
5. F002: `ValueError` zusätzlich zu `OSError, RuntimeError` fangen; bei NUL-Byte `""` (nicht frei, fail-safe), nicht `None`.
Harmlose Pfade bleiben unverändert (`docs/a.md`, `./docs/a.md` → `docs/a.md`, `.claude/x`).

### Dependencies
Nur `posixpath` (stdlib) neu; Aufrufer `tdd_enforcement.py:256`, `post_implementation_gate.py:155` bleiben unverändert.

### Open Questions
- [x] Reihenfolge Präfix/Normalisierung → Normalisieren zuerst (s. oben)
- [x] Rückgabe bei Ausbruch/NUL → `""` (nicht frei)
