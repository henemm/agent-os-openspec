# Context: feat-447-evidence-gate

## Request Summary
Issue #447 (Teil von Epic #430, Herkunft henemm/loose-ends#145 Schnitt 2): Wenn ein Projekt es per
Config einschaltet, ist `phase8_complete` (auch `complete`/`finish`) nur mit einem gültigen,
maschinell erzeugten Simulator-Beleg erreichbar. Der Beleg wird neu aus `run.xcresult` abgeleitet.
Außerdem gilt eine Schreibsperre auf die Beleg-Dateien. Ohne Config ändert sich nichts.

## Quellen
- Issue #447 (Gate 2a + Schreibsperre 2b, DoD), Epic #430.
- loose-ends#145: Anlass und Forderung. „Darf nicht von Hand setzbar sein“, „Prüfsumme passt zum
  aktuellen Stand“.
- Die in #447 genannte Analyse `docs/context/feat-145-s2-gate.md` ist auf GitHub (Default-Branch und
  Branches) **nicht auffindbar**, vermutlich liegt sie nur lokal oder in einem nicht gepushten
  Worktree. Maßgeblich ist deshalb der Issue-Text.
- loose-ends `scripts/sim_proof.py` (Default-Branch) erzeugt den Beleg. Format siehe unten.

## Belegformat (aus `sim_proof.py`, Schnitt 1)
Datei `docs/artifacts/<wf>/simulator-run.txt`, atomar geschrieben (tempfile + `os.replace`):
```
# Simulator-Beleg
erzeugt: <iso>
befehl: <befehl>
workflow: <wf>
head: <sha>
basis: <sha> (merge-base origin/main HEAD)
testklasse: <klasse>
ergebnis: Passed|Failed|Unbekannt
xcodebuild: <endzeile>
tests: N gesamt, P bestanden, F fehlgeschlagen, S übersprungen
start: <startTime>  ende: <finishTime>
geraet: <name>, iOS <ver> | unbekannt
summary: docs/artifacts/<wf>/simulator-run/summary.json  sha256:<hex>   | "fehlt (kein Ergebnisbündel)"
xcresult: docs/artifacts/<wf>/simulator-run/run.xcresult  (gitignored)
screenshots: docs/artifacts/<wf>/simulator-run/*.png (<n> Stück)

## Geprüfte Dateien
- sha256:<hex>  <repo-relativer pfad>        | "(keine Code-Dateien geändert)"
```
- `summary.json` ist die wörtliche Ausgabe von
  `xcrun xcresulttool get test-results summary --path <bundle> --compact`. Felder: `result`,
  `totalTestCount`, `passedTests`, `failedTests`, `skippedTests`, `startTime`, `finishTime`,
  `devicesAndConfigurations[0].device`.
- `ergebnis: Passed` setzt `result == Passed`, xcodebuild-Exit 0 und `gesamt >= 1` voraus.
- Die Dateiliste spiegelt `is_gated_code_path` aus hook_utils, Stand 3.34.0, ohne Config-Override.
  Sie ist repo-relativ und umfasst die Änderungen gegen `merge-base origin/main HEAD` plus
  untrackte Dateien.
- Der Bündel-Ort `run.xcresult` liegt unter `simulator-run/`, `head:` ist der HEAD zum Zeitpunkt
  des Laufs. Laut #447 wird `head:` **nicht** gebunden: Es zählt der Arbeitsbaum-Hash.

## Related Files
| Datei | Relevanz |
|-------|----------|
| `core/hooks/workflow.py:1035` `_validate_transition` | Phase-8-Zweig (Z. 1092–1116): Verdict, dann `adversary_dialog.check_dialog_evidence`. Der neue Aufruf `evidence_gate.check_evidence` kommt **danach**. Aufrufer: `cmd_phase` (Z. 1357) und `cmd_complete` (Z. 1771, auch `finish` → `cmd_complete`, Z. 2360). |
| `core/hooks/workflow.py:1439` `_user_override(name)` | Vorhandener Override-Token-Check. `_validate_transition(data, target)` kennt heute **keinen** Workflow-Namen, er muss für den `override`-Ausweg durchgereicht oder aus `data` gelesen werden. |
| `core/hooks/adversary_dialog.py:1324` `phase8_code_files(wf)` | Liefert die Gate-Menge: Code-Dateien realpath-absolut plus Basis-Info, wirft `ChangeSetError`, gibt ohne Git-Baum `None` zurück. Die Basis kommt aus `_phase8_base` (base_commit / merge-base / HEAD). Für den Vergleich mit dem Beleg muss relativ zu `_hash_root()` umgerechnet werden (`display_path`). |
| `core/hooks/adversary_dialog.py:607` `_hash_root()` | Worktree vor Hauptrepo. Dort liegt auch `docs/artifacts/<wf>/`. |
| `core/hooks/adversary_dialog.py:622` `render_examined_files_section` | Dasselbe Zeilenformat `- sha256:<hex>  <pfad>` wie im Beleg, ein Parser lässt sich wiederverwenden bzw. analog bauen. |
| `core/hooks/adversary_dialog.py:1185` `coverage_gate_enabled()` | Muster für das Lesen der Config (fail-closed bei kaputter Config). |
| `core/hooks/bash_gate.py:57` `PROTECTED_FILE_PATTERNS` | Ziel von 2b. Wirkt in `_redirects_to_protected` (Z. 292, Umleitungen auch hinter erlaubtem Befehl) und in 3b (Z. 1270ff, geschützter Pfad + Schreibindikator). Beides greift nur bei `workflow_enforced`. Lesen (`cat`) bleibt erlaubt. |
| `core/hooks/edit_gate.py:45` `PROTECTED_STATE_FILES` + Z. 655 | Ziel von 2b für Write/Edit: einfacher Substring-Test, blockt immer. |
| `core/hooks/config_loader.py` | `load_config()` (openspec.yaml / config.yaml / .openspec.yaml + Local Overrides). |
| `config.yaml` | Template: neuer Abschnitt `evidence_checks` (Default leer) mit Kommentar. |
| `core/hooks/hook_utils.py` `is_gated_code_path` | Code-Klassifikation, gemeinsame Quelle. sim_proof spiegelt sie (Drift-Risiko). |
| loose-ends `scripts/sim_proof.py` | Erzeuger, Referenz für das Format und für den grünen Testfall (echtes Format). |

## Existing Patterns
- **#253/#259 Dialog-Nachweis**: Phase 8 akzeptiert ein Verdict nur mit Artefakt, das per
  Hash-Block jede Code-Datei der Änderungsmenge bindet. Ist ein Dateihash veraltet, wird
  abgewiesen. Das ist fail-closed (`except Exception` → Grund), mit Kill-Switch per Config. Das
  neue Gate ist strukturell der Zwilling: gleiche Gate-Menge, gleiches Hash-Format, anderer Inhalt.
- **#337**: `complete`/`finish` prüft immer voll, auch bei Same-Phase-Transition `phase8_complete`.
- **#418/#410**: Config-Schutz in bash_gate (`_writes_effective_config`). Ein Bash-Schreibzugriff
  auf die wirksame Gate-Config ist nur mit `override` erlaubt. Damit lässt sich `evidence_checks`
  per Bash nicht still abschalten.
- **Tests**: `tests/test_adversary_coverage_gate_259.py`, `tests/test_adversary_evidence_gate_253.py`,
  `tests/test_complete_recheck_337.py` und `tests/test_bash_gate_state_integrity_410.py` sind die
  Vorlagen für Gate- und Sperr-Tests (Subprozess-Aufrufe der Hooks, tmp-Projekte, conftest).

## Dependencies
- Upstream: `adversary_dialog` (Gate-Menge, Hash-Root, display_path), `config_loader`,
  `override_token`, `git`, extern `xcrun xcresulttool` (nur macOS mit Xcode).
- Downstream: Alle Konsumenten-Projekte durchlaufen `_validate_transition`. Ohne `evidence_checks`
  darf sich kein Verhalten ändern (DoD). Die Sperrmuster in bash_gate/edit_gate wirken dagegen
  **in allen Projekten**, auch ohne Config. Ob die Sperre nur bei eingeschalteten
  `evidence_checks` gelten soll, ist zu klären.
- loose-ends: Einschalten erst nach Release (#145).

## Existing Specs
- `docs/specs/` enthält Specs zu #253/#259 (Adversary-Nachweis/Abdeckung). Sie sind die Referenz
  für Struktur und AC-Formulierung des Zwillings-Gates.

## Risks & Considerations
1. **Testbarkeit ohne macOS**: `xcresulttool` fehlt auf dem Server. Grüner Fall und
   Semantik-Vergleich brauchen eine austauschbare Ausführung, z. B. ein gefälschtes `xcrun` im
   `PATH` des Testprozesses oder einen injizierbaren Runner. Eine echte `summary.json` aus loose-ends
   wäre als Fixture ideal. Fehlendes Tool führt laut Issue zur Abweisung.
2. **Fast Track**: `_validate_transition` kehrt für `feature-fast` früh zurück (ohne Phase-8-Prüfung).
   Laut #447 läuft der Aufruf im Phase-8-Zweig. Dann umgeht ein Fast-Track-Workflow das neue Gate.
   Das ist eine Lücke gegenüber #145 („nicht umgehbar“) und in der Analyse zu entscheiden.
3. **Override-Ausweg**: Laut #447 genügt das getippte `override`. `_validate_transition` kennt den
   Namen nicht. Zu klären ist außerdem, ob der Override nur das Evidence-Gate öffnen darf (nicht das
   Dialog-Gate).
4. **Pfad-Normalisierung**: `phase8_code_files` liefert realpath-absolute Pfade, der Beleg
   repo-relative. Symlinks, Worktree vs. Hauptrepo und Nicht-ASCII-Pfade sind zu bedenken.
5. **Klassifikations-Drift**: sim_proof spiegelt `is_gated_code_path` (3.34.0, ohne Config). Weicht
   die Projekt-Config (`strict_code_gate`) ab, kann eine Gate-Datei im Beleg fehlen. Das ergibt eine
   fail-closed-Abweisung mit klarer Meldung, ist aber kein Fälschungsweg. „Obermenge erlaubt“ deckt
   die Gegenrichtung ab.
6. **Schreibsperre wirkt global**: Neue Muster in `PROTECTED_FILE_PATTERNS`/`PROTECTED_STATE_FILES`
   treffen alle Projekte. 3b greift nur mit Schreibindikator, edit_gate dagegen immer. Fehlalarme
   bei Doku-/Freitext-Erwähnungen sind die bekannte Klasse (#30/#53/#64). Außerdem wird `rm` eines
   veralteten Belegs gesperrt. Neu erzeugen geht nur über den Erzeuger, das ist gewollt.
7. **Edit-Weg auf die Config**: Der Config-Schutz (#418) ist in bash_gate. Ob ein Edit/Write auf
   `openspec.yaml` `evidence_checks` still entfernen kann, ist in der Analyse zu prüfen. Es wäre
   eine bestehende, allgemeine Lücke und nicht Teil von #447, ein Folge-Issue ist zu erwägen.
8. **Timeout/Fehler von xcresulttool**: Nicht-null-Exit, ungültiges JSON und Timeout führen alle zur
   Abweisung (fail-closed), mit einer Meldung, die den Grund nennt.
9. **Semantischer Vergleich**: `result` plus vier Zähler aus der Neuableitung werden gegen
   `summary.json`, die `ergebnis:`-Zeile und die `tests:`-Zeile verglichen. Ein Bytevergleich
   scheitert an nicht-deterministischen Feldern, deshalb semantisch.
10. **Verifier-Registry**: `xcresult_proof` ist das erste Mitglied, weitere Belegtypen sollen nur Config
    kosten. Ein unbekannter `verifier`-Name in der Config führt zur Abweisung (fail-closed).

## Analysis

### Type
Feature (opt-in Gate + Schreibsperre), Hochrisiko-Bereich (Phase-8-Gate, alle Konsumenten).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/evidence_gate.py` | CREATE | Verifier-Registry `VERIFIERS = {"xcresult_proof": ...}`, Einstieg `check_evidence(target, data, *, runner=None) -> str \| None`, Config-Lesen, Beleg-Parser, Neuableitung via `xcrun xcresulttool` |
| `core/hooks/workflow.py` | MODIFY | `_validate_transition`: Aufruf im Phase-8-Zweig nach dem Dialog-Check (vor `return None`, ~Z. 1115) **und** im feature-fast-Zweig nur für `target == "phase8_complete"` (~+12 LoC) |
| `core/hooks/edit_gate.py` | MODIFY | Schreibsperre Beleg-Dateien für Write/Edit (eng: `docs/artifacts/<wf>/simulator-run.txt` und `docs/artifacts/<wf>/simulator-run/`), Regex statt reinem Substring (~+4) |
| `core/hooks/bash_gate.py` | MODIFY | `PROTECTED_FILE_PATTERNS` um dieselben zwei Muster erweitern (~+3) |
| `config.yaml` | MODIFY | Abschnitt `evidence_checks` (Default leer, kommentiert) + `exempt_paths` |
| `tests/test_evidence_gate_447.py` | CREATE | je ein Test pro Ablehnungsgrund, grüner Fall (echtes Format), Fast Track, Override, ohne Config identisch, Schreibsperre |
| `tests/fixtures/evidence_447/` | CREATE | `summary.json` + `simulator-run.txt` im Format von loose-ends `sim_proof.py`, Fake-`xcrun`-Skript |
| `docs/specs/feat-447-evidence-gate.md` | CREATE | Spec (Zwilling von `fix-253-…`/`fix-259-…`) |
| `CHANGELOG.md`, `setup.py`, Versionsstellen | MODIFY | Release |

### Scope Assessment
- Files: ~9 (davon 3 neu)
- Estimated LoC: Produktiv ~+220–240, Tests ~+350 (Limits: 250 / 500 laut `config_loader.py:582,622`). Passt in **einen** Workflow, aber knapp. Bei Überschreitung `loc_limit_override` statt Aufteilung.
- Risk Level: HIGH (Phase-8-Gate, alle Konsumenten durchlaufen `_validate_transition`; Schreibsperre wirkt global)

### Technical Approach (Empfehlung, Plan/Sonnet + eigene Code-Prüfung)
1. **Signatur abweichend vom Issue:** `check_evidence(target, data)` statt `(target_phase, wf)`, weil `phase8_code_files(data)` das Datendict braucht. `wf = data["name"]`. Im Spec begründen.
2. **Opt-in zuerst:** Erster Schritt liest `evidence_checks`. Fehlt der Schlüssel → sofort `None`, vor jedem Import/Git-Aufruf. Vorhanden, aber kaputt (Nicht-Liste/Dict, unbekannter `verifier`, fehlendes `file`) → Abweisung. Config nicht ladbar, obwohl Datei vorhanden → Abweisung (invertiert zu `coverage_gate_enabled`). Ohne Config liefert `load_config` `{}` → kein Verhalten.
3. **Gate-Menge:** `phase8_code_files(data)` direkt aufrufen, **unabhängig** von `coverage_gate_enabled()` (heute nur dort aufgerufen). Minus `exempt_paths` (fnmatch auf repo-relativem `display_path`). Leer → kein Beleg nötig. `None` (kein Git-Baum) bzw. `ChangeSetError` → Abweisung (fail-closed).
4. **Beleg-Ort:** `_hash_root()/docs/artifacts/<wf>/<file>`. `wf` darf kein `/` oder `..` enthalten; nach `realpath` muss der Pfad unter `_hash_root()` liegen (Symlink-Ausbruch → Abweisung).
5. **Pfad-Vergleich:** Belegpfade über `realpath(_resolve_hash_path(rel))` auflösen und mit der realpath-absoluten Gate-Menge vergleichen, wie `_uncovered_files` (`adversary_dialog.py:1209ff`). Parser von `_parse_examined_files_section` wiederverwenden, nur auf den Abschnitt `## Geprüfte Dateien` angewendet. UTF-8.
6. **Prüfkette (`xcresult_proof`):** Datei vorhanden → jede Gate-Datei mit aktuellem Arbeitsbaum-Hash im Block (Obermenge erlaubt, `head:` ungebunden) → `summary.json` existiert und passt zur `summary:`-Prüfsumme → `run.xcresult` vorhanden → `xcrun xcresulttool get test-results summary --path … --compact` mit Timeout → JSON semantisch vergleichen (`result` + `totalTestCount`/`passedTests`/`failedTests`/`skippedTests`) mit `summary.json`, `ergebnis:` und `tests:` → verlangt `Passed` und `passedTests >= 1`. Fehlendes Tool, Nicht-null-Exit, ungültiges JSON, Timeout → Abweisung mit Grund.
7. **Testbarkeit:** Zwei Seams. (a) `runner`-Parameter nur für Unit-Tests, **nicht** per Config/Env überschreibbar (sonst Fälschungsweg). (b) Fake-`xcrun` im `PATH` des Subprozesses für Hook-Pfad-Tests (auch „Tool fehlt“, „Timeout“, „ungültiges JSON“).

### Decisions (vom Tech Lead getroffen, im Spec als „Wo ich für dich entschieden habe“ ausweisen)
- **Fast Track:** Gate greift auch im feature-fast-Zweig, aber nur bei gesetztem `evidence_checks` und nur für `phase8_complete`. Grund: `start --type feature-fast` ist frei, sonst wäre das Gate per Fast Track vollständig umgehbar (#145 „nicht umgehbar“). Ohne Config unverändert.
- **Override:** `_user_override(data["name"])` öffnet **nur** das Evidence-Gate, innerhalb `check_evidence`. Das Dialog-Gate (#253) behält keinen Override-Pfad. Kein Token-Verbrauch (bestehender Standard, `has_valid_token` ist lesend); sichtbarer Hinweis „Evidence-Gate per override umgangen“ auf stderr.
- **Schreibsperre:** global und immer (wie die übrigen geschützten Dateien), aber mit engen Mustern. Bash-Seite greift nur mit Schreibindikator bei `workflow_enforced`, Freitext-Flags sind ausgenommen (`bash_gate.py:721ff`). Edit-Seite prüft nur `file_path`, nicht den Inhalt; Doku, die den Pfad erwähnt, bleibt editierbar. `rm` eines veralteten Belegs bleibt gesperrt (gewollt: neu erzeugen nur über den Erzeuger). Nebenwirkung für Konsumenten mit eigenem `docs/artifacts/*/simulator-run.txt` im CHANGELOG benennen.
- **Ein Workflow** statt Aufteilung 2a/2b (LoC passt). Reihenfolge in TDD: 2b-Tests und 2a-Tests gemeinsam rot, Implementierung 2b zuerst (klein, unabhängig).

### Dependencies
- Upstream: `adversary_dialog` (`phase8_code_files`, `_hash_root`, `display_path`, `_resolve_hash_path`, `_parse_examined_files_section`), `config_loader.load_config`, `override_token.has_valid_token`, `git`, extern `xcrun xcresulttool`.
- Downstream: alle Konsumenten über `_validate_transition` (cmd_phase, cmd_complete, finish). loose-ends schaltet nach Release ein (#145).

### Known Limitations (für Spec + CHANGELOG)
1. Ein älteres `run.xcresult` eines früheren grünen Laufs kann wiederverwendet werden; `head:` ist laut #447 nicht gebunden, der Hash-Block bindet nur den Quellstand.
2. Ein echter grüner Lauf einer anderen Testklasse ist nicht unterscheidbar (Testklasse wird nicht gegen die Spec geprüft).
3. Schreibsperre wirkt nur über die Hooks, nicht gegen Prozesse außerhalb.
4. Edit/Write auf die Config (`evidence_checks` entfernen): Im Worktree ist die wirksame Config im Hauptordner durch `worktree_write_guard` gesperrt, per Bash durch `_writes_effective_config` (#418). Restlücke nur in einer Hauptordner-Sitzung (durch Worktree-Pflicht ohnehin geblockt) → kein Folge-Issue nötig.
5. CI-Zielbild (Testklasse im PR ausführen) löst 1 und 2, ist laut Issue vertagt.

### Open Questions
- Keine blockierenden. Die in #447 referenzierte Analyse `feat-145-s2-gate.md` ist nicht auffindbar; maßgeblich ist der Issue-Text (Restrisiko verdeckter Anforderungen, im Spec benennen).

## Hinweise aus Phase 5 (RED) für die Umsetzung
Tests: `tests/test_evidence_gate_447.py` (63 rot, 2 grün als Wächter: AC-25 own-token-no-dialog, AC-29).
- `runner` ersetzt `subprocess.run(argv_list, **kw)`, liefert `CompletedProcess` mit Text-stdout, nur für den xcrun-Aufruf. Nur AC-17 (Timeout via `TimeoutExpired`) und AC-26 übergeben ihn; sonst Fake-`xcrun` im PATH.
- Config im Testprojekt: `.claude/config.yaml`; `exempt_paths` steht UNTER `evidence_checks`.
- Bündel: `docs/artifacts/<wf>/simulator-run/run.xcresult`; xcrun-Aufruf `xcrun xcresulttool get test-results summary --path <bundle> --compact`.
- Fake-xcrun liefert inhaltsgleiches, nicht bytegleiches JSON → semantischer Vergleich nötig.
- AC-26: `evidence_gate.py` darf weder `os.environ` noch `getenv` enthalten (Quelltext-Prüfung).
- AC-3: `load_config` liefert bei kaputtem YAML nur Warnung + Defaults → das Gate muss Nicht-Ladbarkeit selbst erkennen.
- AC-6: Test schaltet `adversary_coverage_gate` ab, damit der Dialog-Check nicht vorher scheitert.
- Erwartete Meldungsinhalte: AC-9 `simulator-run.txt` + wf-Name; AC-10/11 Dateipfad; AC-15 Exit-Code als Wort; AC-18 JSON-Feldname; AC-19 `ergebnis`/`tests`; AC-2/3 `config`/`evidence_checks`; AC-6 `Änderungsmenge`/`nicht ermittelbar`/`Git-Arbeitsbaum`; AC-12 `summary`; AC-13 `xcresult` (ohne xcrun-Aufruf); AC-17 `timeout`/`zeitlimit`.
- **Falle AC-29(b):** `echo "Beleg: docs/artifacts/wf-447/simulator-run.txt" >> docs/notes.md` muss erlaubt bleiben. Die neuen Muster dürfen daher nicht in die 3b-Prüfung „geschützter Pfad irgendwo + Schreibindikator“ fallen, sondern müssen ans tatsächliche Schreibziel gebunden sein (Umleitungsziel, Ziel-Token von cp/mv/tee/sed -i/rm).
- LoC: Testdatei ~600 Zeilen (über 500er-Limit) → bei Bedarf `test_loc_limit_override`.
