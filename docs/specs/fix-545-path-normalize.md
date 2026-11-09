---
entity_id: fix-545-path-normalize
type: bugfix
created: 2026-11-09
updated: 2026-11-09
status: draft
version: "1.0"
workflow: fix-545-path-normalize
tags: [hooks, edit-gate, bash-gate, path-normalization, security]
test_targets:
  - tests/test_path_normalize_545.py
  - tests/test_edit_gate_settings_plugins_543.py
  - tests/test_edit_gate_orchestrator_files.py
  - tests/test_bash_gate_false_positives.py
---

# Pfad-Normalisierung vor den Pfad-Sperren in edit_gate.py und bash_gate.py (#545)

## Approval

- [ ] Approved

## GitHub Issue

- **#545:** `edit_gate.py` Schritt 1b vergleicht `ORCHESTRATOR_FILES` per Substring gegen den
  rohen `file_path`. Schreibweisen wie `<projekt>/.claude//settings.json` oder
  `<projekt>/./.claude/./settings.json` treffen keinen Eintrag und fallen in die
  Always-Allowed-Regel für `.json`. Ein Write, der `hooks` ändert und `disableAllHooks: true`
  setzt, kam mit Exit 0 durch. Gleiches gilt für `settings.local.json` und `active_workflow`.
  Die Prüfung zeigt: Schritt 1 (Workflow-State), Schritt 4 (Infrastruktur) und `bash_gate.py`
  haben dieselbe Schwäche.

## Purpose

Jede Schreibweise eines geschützten Pfades (doppelter Schrägstrich, `./`, `..`, `~`, Symlink) trifft
dieselbe Sperre wie die saubere Schreibweise. Heute genügt ein zusätzlicher Schrägstrich, um
Hooks, Workflow-State und Infrastruktur an den Gates vorbei zu überschreiben. Der Fix
normalisiert den Pfad vor dem Vergleich, ohne dass dabei eine Freigabe-Regel zusätzliche Pfade
öffnet.

## Source

- **File:** `core/hooks/edit_gate.py` — **Identifier:** `main()` Schritte 1, 1b, 2, 4; neue
  Hilfsfunktion für Pfad-Varianten; `_settings_plugin_change_reason` (#543, unverändert)
- **File:** `core/hooks/bash_gate.py` — **Identifier:** `_matches_file_token`, `_is_sensitive`,
  `_references_protected`, `_redirects_to_protected`, `_cd_into_claude`
- Reproduziert (origin/main eab24f1, Wegwerf-Projekt): `.claude//settings.json`,
  `./.claude/./settings.json`, `.claude//settings.local.json`, `.claude/./active_workflow`,
  `.claude//workflows/x.json` ergeben in `edit_gate` Exit 0; `.claude//settings.json`,
  `./.claude/./settings.json`, `.claude//workflows/x.json` ergeben in `bash_gate` Exit 0.
  Zusätzlich: `<proj>/tests/../.claude/hooks/x.py` (Schritt 2 erlaubt wegen der Komponente
  `tests`) und `cd .claude/./workflows && echo x > w.json` (`_cd_into_claude`) kommen mit Exit 0
  durch.

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `os.path.normpath`, `os.path.expanduser` | stdlib | Lexikalische Normalisierung (`//`, `./`, `..`, `~`) |
| `pathlib.Path.resolve` | stdlib | Aufgelöster Pfad (Symlinks), nur in `edit_gate.py` |
| `edit_gate` Beleg-Prüfung (#447/#448, `PROOF_FILE_RE`) | function | Vorbild: normpath ODER resolve; keine Änderung |
| `bash_gate._proof_path_hit_one` | function | Vorbild für Bash; keine Änderung |
| `edit_gate._settings_plugin_change_reason` (#543) | function | Bekommt weiter den rohen Pfad und lehnt unsaubere Schreibweisen ab; keine Änderung |
| `edit_gate` Home-Ausnahme `~/.claude/...` (#48) | rule | Arbeitet bereits auf dem aufgelösten Pfad; keine Änderung |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/edit_gate.py` | MODIFY | Hilfsfunktion für Pfad-Varianten (roh, `normpath(expanduser)` mit `/`, aufgelöst); Schritte 1, 1b, 4 sperren bei irgendeiner Variante; Schritt 2 (Freigabe) rechnet nur auf der normalisierten Variante |
| `core/hooks/bash_gate.py` | MODIFY | Option `normalize` in `_matches_file_token`/`_is_sensitive`, gesetzt nur von `_references_protected`; `_redirects_to_protected` prüft Ziel roh und normalisiert; `_cd_into_claude` normalisiert das cd-Ziel |
| `tests/test_path_normalize_545.py` | CREATE | Tests für alle Schreibweisen (edit und bash), Plugin-Ausnahme, Home-Ausnahme, Regressionen |
| `tests/test_edit_gate_settings_plugins_543.py` | MODIFY | strict-xfail `#545` in `_UNCLEAN` entfernen |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]` |

### Estimated Changes

- Files: 5
- LoC: +60 bis +100 Code, +150 bis +200 Tests, -3 (xfail)
- Risiko: HOCH (Gate-Code); Adversary mindestens 2 Dialog-Runden

### Nicht im Scope

Neue Schutzmuster in `bash_gate.py` für `settings.local.json` und `active_workflow`; `resolve()`
je Bash-Token; Normalisierung für Ordner-, Glob- und Secrets-Muster; der Raw-Scan-Fallback in
Bash (`sh -c`, `eval`). Siehe Known Limitations.

## Implementation Details

1. **`edit_gate.py`:** Neue Hilfsfunktion liefert die Vergleichsvarianten eines `file_path` als
   Liste: roh, `os.path.normpath(os.path.expanduser(p))` mit `/` als Trenner, und
   `Path(p).resolve()`. Jede Berechnung steht in `try/except (OSError, RuntimeError, ValueError)`;
   eine nicht berechenbare Variante entfällt, die rohe bleibt immer enthalten.
2. **Sperren (Schritte 1, 1b, 4):** Der Substring-Vergleich (`PROTECTED_STATE_FILES`,
   `ORCHESTRATOR_FILES`, Infrastruktur-Muster) trifft, wenn IRGENDEINE Variante das Muster
   enthält. Varianten vergrößern nur die Treffermenge, es entsteht keine neue Lücke.
3. **Freigabe (Schritt 2, always-allowed dirs):** Die Prüfung über `Path(file_path).parts` rechnet
   NUR auf der normalisierten Variante. Sonst erlaubt eine Komponente wie `tests` in
   `<proj>/tests/../.claude/hooks/x.py` den Pfad, bevor Schritt 4 läuft.
4. **#543-Ausnahme:** `_settings_plugin_change_reason` bekommt weiter den rohen Pfad und lehnt
   unsaubere Schreibweisen ab (fail-closed). Eine reine Plugin-Änderung per `.claude//settings.json`
   wird damit mit dem Grund „Pfad nicht eindeutig" geblockt, statt durchgewunken zu werden. Die
   saubere Schreibweise bleibt erlaubt.
5. **Home-Ausnahme (#48):** unverändert auf dem aufgelösten Pfad.
6. **`bash_gate.py`:** `_matches_file_token`/`_is_sensitive` bekommen einen Parameter
   `normalize` (Default aus). `_references_protected` setzt ihn für `PROTECTED_FILE_PATTERNS`;
   dann wird der Token zusätzlich als `normpath(expanduser(token))` geprüft, der rohe Vergleich
   bleibt. `_redirects_to_protected` prüft das Umleitungsziel roh UND normalisiert.
   `_cd_into_claude` normalisiert das cd-Ziel, damit `.claude/./workflows` als `.claude/workflows`
   erkannt wird. Kein `resolve()` je Token.
7. **Fail-safe:** Ein Fehler bei der Variantenberechnung führt in keinem der beiden Gates zum
   Absturz (Exit 1 würde als „durchgelassen" gelten); der rohe Vergleich bleibt.

## Expected Behavior

- **Input:** Edit/Write/MultiEdit (edit_gate) bzw. Bash-Befehl mit Schreibziel (bash_gate) auf
  einen geschützten Pfad in beliebiger Schreibweise.
- **Output:** Exit 2 mit der bisherigen Sperr-Meldung, genau wie bei der sauberen Schreibweise.
  Bei einer reinen Plugin-Änderung an `settings.json` in unsauberer Schreibweise Exit 2 mit
  „Pfad nicht eindeutig"; in sauberer Schreibweise weiter Exit 0.
- **Unverändert:** Home-Ausnahme `~/.claude/...` (#48), Override-Token, alle bisher erlaubten
  sauberen Pfade, False-Positive-Schutz im Bash-Gate (#53/#64).
- **Side effects:** keine.

## Known Limitations

- Raw-Scan-Fallback in Bash (`sh -c "…"`, `eval`, kaputte Quotes) normalisiert nicht: `normpath`
  auf einen ganzen Befehlsstring greift nur am ersten Pfadblock. `sh -c "echo x > .claude//settings.json"`
  bleibt offen (Folge-Issue).
- `bash_gate.py` schützt `settings.local.json` und `active_workflow` gar nicht als Muster
  (bestehender Scope, Folge-Issue); die Pfad-Normalisierung ändert daran nichts.
- Kein `resolve()` je Bash-Token. Korrektur einer früheren Annahme: `bash_gate` blockt `ln -s`
  auf `.claude/hooks` NICHT (`PROTECTED_DIR_TOKEN_PATTERNS` lässt `.claude/hooks` bewusst aus, #407
  deckt nur `.claude` und `.claude/workflows`). Ein Symlink auf die Infrastruktur kann also per
  Bash entstehen. `edit_gate` löst ihn auf (Schritte 2/2b/3 geben einen Pfad, der per Symlink auf
  Infrastruktur-Code zeigt, nicht frei, Schritt 4 entscheidet); in Bash wird ein vorhandener
  Symlink nicht aufgelöst (Folge-Issue).
- Normalisierung in Bash gilt nur für `PROTECTED_FILE_PATTERNS`, nicht für Ordner-, Glob- und
  Secrets-Muster.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] `.claude//settings.json`, `./.claude/./settings.json` und `.claude/../.claude/settings.json`
      mit Hook-Änderung sind in `edit_gate` gesperrt, ebenso für `settings.local.json` und
      `active_workflow` (AC-1, AC-2)
- [ ] Workflow-State und Infrastruktur sind in unsauberer Schreibweise gesperrt, der `..`-Umweg
      über einen always-allowed Ordner ist zu (AC-3 bis AC-5)
- [ ] Die #543-Ausnahme und die Home-Ausnahme (#48) verhalten sich wie spezifiziert (AC-6, AC-7)
- [ ] `bash_gate` blockt dieselben Schreibweisen für die geschützten Dateimuster und den
      `cd`-Umweg (AC-8 bis AC-10)
- [ ] Fehler bei der Variantenberechnung führen nicht zum Absturz (AC-11)
- [ ] Die Regressionstests laufen grün (AC-12) und `CHANGELOG.md` ist unter `[Unreleased]` ergänzt

## Acceptance Criteria

- **AC-1:** Given ein Projekt mit `.claude/settings.json` / When Write mit Änderung an `hooks`
  bzw. `disableAllHooks: true` über `.claude//settings.json`, `./.claude/./settings.json` oder
  `.claude/../.claude/settings.json` / Then Exit 2.
  - Test: `tests/test_path_normalize_545.py::test_settings_json_unclean_spellings_blocked`
- **AC-2:** Given ein Projekt / When Write über dieselben drei Schreibweisen auf
  `settings.local.json` oder `active_workflow` / Then Exit 2.
  - Test: `tests/test_path_normalize_545.py::test_local_settings_and_active_workflow_unclean_blocked`
- **AC-3:** Given ein Workflow-State `.claude/workflows/x.json` / When Write über
  `.claude//workflows/x.json` oder `./.claude/./workflows/x.json` (Schritt 1) / Then Exit 2.
  - Test: `tests/test_path_normalize_545.py::test_workflow_state_unclean_blocked`
- **AC-4:** Given kein Override-Token / When Write auf `.claude//hooks/x.py` bzw.
  `./.claude/./hooks/x.py` (Schritt 4, Infrastruktur) / Then Exit 2.
  - Test: `tests/test_path_normalize_545.py::test_infra_unclean_blocked_without_override`
- **AC-5:** Given ein Projekt mit Ordner `tests` / When Write auf `<proj>/tests/../.claude/hooks/x.py`
  / Then wird der Pfad nicht mehr von Schritt 2 (always-allowed dirs) freigegeben, Exit 2.
  - Test: `tests/test_path_normalize_545.py::test_dotdot_via_allowed_dir_not_allowed`
- **AC-6:** Given eine `settings.json` / When eine reine Plugin-Änderung (`enabledPlugins`) über
  eine unsaubere Schreibweise kommt / Then Exit 2 mit „Pfad nicht eindeutig"; die saubere
  Schreibweise `<proj>/.claude/settings.json` bleibt Exit 0.
  - Test: `tests/test_path_normalize_545.py::test_plugin_change_unclean_blocked_clean_allowed`
  - Test: `tests/test_edit_gate_settings_plugins_543.py::test_unclean_path_not_excepted`
- **AC-7:** Given die Home-Ausnahme `~/.claude/...` (#48) und ein Override-Token / When Write auf
  Pfade unter dem Home-Ordner bzw. mit Token / Then Verhalten unverändert zu vor dem Fix.
  - Test: `tests/test_path_normalize_545.py::test_home_exception_and_override_unchanged`
- **AC-8:** Given ein Projekt / When Bash `echo x > .claude//settings.json` bzw.
  `echo x > ./.claude/./settings.json` / Then Exit 2.
  - Test: `tests/test_path_normalize_545.py::test_bash_redirect_settings_unclean_blocked`
- **AC-9:** Given ein Workflow-State / When Bash `echo x > .claude//workflows/x.json` / Then Exit 2.
  - Test: `tests/test_path_normalize_545.py::test_bash_redirect_workflow_state_unclean_blocked`
- **AC-10:** Given ein Projekt / When Bash `cd .claude/./workflows && echo x > w.json` / Then
  Exit 2 (`_cd_into_claude` normalisiert das cd-Ziel).
  - Test: `tests/test_path_normalize_545.py::test_bash_cd_dot_segment_blocked`
- **AC-11:** Given eine Pfadvariante, deren Berechnung eine Ausnahme wirft (z. B. Null-Byte oder
  Resolve-Fehler) / When das Gate läuft / Then kein Absturz, die rohe Prüfung bleibt und
  entscheidet (geschützter roher Pfad weiter Exit 2).
  - Test: `tests/test_path_normalize_545.py::test_variant_failure_keeps_raw_check`
- **AC-12:** Given die bestehenden Gate-Tests / When `tests/test_bash_gate_false_positives.py`,
  `tests/test_edit_gate_orchestrator_files.py` und `tests/test_edit_gate_settings_plugins_543.py`
  laufen (strict-xfail `#545` entfernt) / Then alle grün.
  - Test: `tests/test_edit_gate_settings_plugins_543.py::test_unclean_path_not_excepted`

## Test Plan

Hermetische Subprozess-Tests nach Vorlage `tests/test_edit_gate_orchestrator_files.py`
(Fake-HOME, Fake-Projekt mit `.git`, `CLAUDE_PROJECT_DIR`, Payload mit `tool_name`).

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN Projekt mit `.claude/settings.json` WHEN Write mit Hook-Änderung über `//`,
      `./.` und `..`-Schreibweise THEN Exit 2 (AC-1)
- [ ] Test 2: GIVEN dieselben Schreibweisen für `settings.local.json` und `active_workflow` WHEN
      Write THEN Exit 2 (AC-2)
- [ ] Test 3: GIVEN `.claude//workflows/x.json` und `./.claude/./workflows/x.json` WHEN Write THEN
      Exit 2 (AC-3)
- [ ] Test 4: GIVEN `.claude//hooks/x.py` ohne Override WHEN Write THEN Exit 2 (AC-4)
- [ ] Test 5: GIVEN `<proj>/tests/../.claude/hooks/x.py` WHEN Write THEN Exit 2 (AC-5)
- [ ] Test 6: GIVEN reine Plugin-Änderung WHEN unsaubere Schreibweise THEN Exit 2 mit „Pfad nicht
      eindeutig", WHEN saubere Schreibweise THEN Exit 0 (AC-6)
- [ ] Test 7: GIVEN Home-Pfad `~/.claude/...` und Override-Token WHEN Write THEN wie vor dem Fix (AC-7)
- [ ] Test 8: GIVEN Bash-Umleitung auf `.claude//settings.json`, `./.claude/./settings.json`,
      `.claude//workflows/x.json` WHEN bash_gate THEN Exit 2 (AC-8, AC-9)
- [ ] Test 9: GIVEN `cd .claude/./workflows && echo x > w.json` WHEN bash_gate THEN Exit 2 (AC-10)
- [ ] Test 10: GIVEN eine fehlschlagende Variantenberechnung WHEN Gate läuft THEN kein Absturz,
      roher Pfad entscheidet (AC-11)
- [ ] Test 11 (Adversary F001): GIVEN Ordner-Symlink `docs/h -> ../.claude/hooks` bzw.
      Datei-Symlink `notes.md -> .claude/hooks/x.py` WHEN Write THEN Exit 2; normales
      `docs/x.md`/`docs/x.py` Exit 0
      (`test_symlink_into_infra_via_allowed_dir_blocked`)
- [ ] Test 12 (Adversary F002): GIVEN `.claude/hooks/x.py\x00` bzw. `.claude//hooks/x.py\x00`
      WHEN Write THEN Exit 2 (`test_null_byte_infra_not_released`)
- [ ] Test 13 (Adversary F003): GIVEN `README/../.claude/hooks/x.py`, `CHANGELOG/../.claude/hooks/x.py`
      WHEN Write THEN Exit 2 (erweitert `test_dotdot_via_allowed_dir_not_allowed`)

Regression:

- `pytest tests/test_path_normalize_545.py tests/test_edit_gate_settings_plugins_543.py
  tests/test_edit_gate_orchestrator_files.py tests/test_bash_gate_false_positives.py` (AC-12)
- `pytest tests/ -q` im venv mit `pytest` und `pyyaml`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Der Fix folgt dem bestehenden Muster aus #447/#448 (normpath ODER resolve, roher
  Pfad bleibt im Vergleich) und führt keinen neuen Hook, keine neue Konfiguration und keine neue
  Abhängigkeit ein. Drei Entscheidungen:
  (a) Sperren treffen bei IRGENDEINER Variante (roh, normpath, resolve), weil Varianten nur die
  Treffermenge vergrößern; Freigaben (Schritt 2, always-allowed dirs) rechnen nur auf der
  normalisierten Variante, sonst öffnet der rohe Pfad den `..`-Umweg. Verworfen: nur `resolve()`
  (verliert den Schutz, wenn ein Zustandsordner selbst ein Symlink ist) bzw. nur `normpath`
  (übersieht Symlinks).
  (b) Die #543-Ausnahme bleibt fail-closed für unsaubere Schreibweisen: Sie werden mit „Pfad nicht
  eindeutig" geblockt. Das erfüllt das Issue-Kriterium „folgt der #543-Ausnahme" als „dieselben
  Regeln für jede Schreibweise", ohne die Ausnahme aufzuweichen; die saubere Schreibweise bleibt
  erlaubt. Verworfen: unsaubere Pfade normalisieren und dann ausnehmen (würde die in #543
  beschlossene Strenge F003 zurücknehmen).
  (c) Bash normalisiert nur lexikalisch und nur für `PROTECTED_FILE_PATTERNS`: kein `resolve()` je
  Token (Kosten, Fehlerquellen, Symlinks werden beim Anlegen per `ln` geblockt, #407) und keine
  Normalisierung für Ordner-, Glob- und Secrets-Muster (der Ordner-Mustercode behandelt `.` und
  `..` selbst, der `worktrees`-Ausschluss bliebe sonst nicht erhalten, Secrets ist eine andere
  Schutzklasse).

## Changelog

- 2026-11-09: Initial spec created
- 2026-11-09: Adversary F001–F003 behoben (Symlink auf Infrastruktur über Freigabe-Schritte,
  Null-Byte im Suffix, Test für Schritt 2b); Known Limitations zu `ln -s` korrigiert
