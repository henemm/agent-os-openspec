---
entity_id: fix-253-adversary-evidence-gate
type: bugfix
created: 2026-09-26
updated: 2026-09-26
status: draft
version: "1.0"
tags: [adversary, commit-gate, post-bash, phase8, hash-binding]
test_targets: ["tests/test_adversary_evidence_gate_253.py"]
---

# Commit-Gate und Phase 8 verlangen einen gültigen Adversary-Dialog-Nachweis (#253)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #253 — Commit-Gate prüft nur den `adversary_verdict`-String; `post_bash.py`
  kann ihn ohne Adversary-Agent auf VERIFIED setzen.

## Purpose

Das Feld `adversary_verdict` hat heute zwei unkoordinierte Schreiber: `qa_gate.py` (nach einem
gestempelten Adversary-Dialog) und `post_bash.py` (automatisch nach JEDEM grünen Testkommando,
egal wer es ausführt und in welcher Phase). Commit-Gate (`bash_gate.py` 5c) und
Phase-8-Übergang (`workflow.py`) prüfen nur den String-Präfix und können beide Fälle nicht
unterscheiden: Der eigene GREEN-Testlauf des Developer Agents öffnet den Commit, bevor der
verpflichtende Adversary-Dialog (`/50-implement` Step 8) überhaupt lief, und nach einem
BROKEN-Verdict überschreibt ein direkter `pytest`-Lauf das Urteil kommentarlos wieder mit
VERIFIED. Diese Spec trennt Beobachtung und Urteil: `post_bash.py` vermerkt Testläufe nur noch
als Hinweis (`last_test_run`), und beide Gates verlangen zusätzlich zum String ein gültiges,
gestempeltes, zum Ist-Stand passendes Dialog-Artefakt.

## Source

- **File:** `core/hooks/adversary_dialog.py` — **Identifier:** neu `find_dialog_artifact`, `check_dialog_evidence`
- **File:** `core/hooks/bash_gate.py` — **Identifier:** `main()`, Abschnitt 5c
- **File:** `core/hooks/workflow.py` — **Identifier:** `_validate_transition` (Ziel `phase8_complete`, damit auch `complete`/`finish`)
- **File:** `core/hooks/post_bash.py` — **Identifier:** `_detect_test_output`; `_set_adversary_verdict` entfällt zugunsten von `_record_test_run`
- **File:** `core/hooks/qa_gate.py` — **Identifier:** `main()`, Abschlussmeldung

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `adversary_dialog.validate_dialog_artifact_ex` | function | Bestehende Prüfung (Checkliste, ≥ 2 Runden, Verdict, Hash-Block aus #131) — unverändert wiederverwendet |
| `hook_utils.find_worktree_root` / `find_project_root` | function | Worktree-zuerst-Auflösung relativer Artefakt-Pfade (Muster aus #80/#96/#131) |
| `override_token.has_valid_token` | function | Notbremse im Commit-Gate bleibt unverändert wirksam |
| `workflow.py add-artifact adversary_dialog …` | CLI | Registrierung des Artefakts, dokumentiert in `/50-implement` Step 8c |

## Scope

- **Affected Files:**
  - Code: `core/hooks/adversary_dialog.py`, `core/hooks/bash_gate.py`, `core/hooks/workflow.py`,
    `core/hooks/post_bash.py`, `core/hooks/qa_gate.py`
  - Tests: `tests/test_adversary_evidence_gate_253.py` (neu). Angepasst werden Bestandstests, die
    das fehlerhafte Verhalten festschreiben (`tests/test_verdict_pipeline_77.py`, post_bash-Teil:
    "grüner Lauf setzt VERIFIED") bzw. einen Commit/Phase-8-Übergang mit VERIFIED ohne Artefakt
    als erlaubt voraussetzen (`tests/test_gate_fixes_26_38_34.py`, Fixtures zu #26 und #34;
    `tests/test_workflow_name_validation.py`, Fixture AMBIGUOUS+Override) — dort bekommt die
    Fixture ein gültiges Artefakt, die Aussage des Tests bleibt dieselbe.
  - Doku: `CLAUDE.md`, `README.md`, `docs/WORKFLOW_GUIDE.md`, `core/commands/50-implement.md`,
    `core/commands/60-validate.md` (Quelle — `skills/*/SKILL.md` werden per
    `scripts/sync_skills.py` regeneriert, nicht von Hand editiert; die veralteten
    Installations-Kopien unter `.claude/commands/` bleiben wie in #131 außen vor),
    `CHANGELOG.md` (Abschnitt `[Unreleased]`)
- **Estimated Changes:** Produktivcode ~+130/−40 LoC, neue Testdatei ~350 LoC,
  Bestandstest-Fixtures ~+60 LoC, Doku ~60 Zeilen

## Implementation Details

**1. `post_bash.py` — Beobachtung statt Urteil.** Die Erkennung bleibt (Test-Indikator im
Befehl, Fehler-Evidenz, Pass-Muster), das Ergebnis landet aber ausschließlich in einem neuen,
nicht gate-relevanten Feld:

```python
data["last_test_run"] = {"result": "passed" | "failed", "runner": "<Indikator>", "at": "<ISO>"}
```

`runner` ist der im Befehl gefundene Test-Indikator (`pytest`, `cargo test`, …) — bewusst nicht
der Befehl selbst (der kann Inline-Credentials tragen). Fehler-Evidenz schreibt `failed`, damit
der Hinweis nach einem roten Lauf nicht grün stehen bleibt; Nicht-Test-Befehle und
unbestimmbare Ausgaben lassen den State unberührt. `adversary_verdict` wird von `post_bash.py`
nie mehr gelesen oder geschrieben.

**2. `adversary_dialog.check_dialog_evidence(wf) -> str | None`** — die eine Regel für beide
Gates. `None` heißt: ein gültiges Artefakt deckt das Verdict im State; sonst der Grund als Text.

- Artefakt-Suche (`find_dialog_artifact`): (a) das zuletzt registrierte `test_artifacts`-Element
  mit `type == "adversary_dialog"` — neuestes gewinnt, analog Last-Verdict-Wins im Artefakt;
  (b) sonst der Standardpfad `docs/artifacts/<workflow-name>/adversary-dialog.md`, falls er
  existiert. Relative Pfade werden zuerst gegen den Worktree-Root aufgelöst (falls die Datei
  dort liegt), sonst gegen den Projekt-Root; absolute Pfade unverändert.
- Prüfung: `validate_dialog_artifact_ex` unverändert — damit gelten Checkliste, Mindest-Runden,
  Verdict (BROKEN blockt) und die Hash-Bindung aus #131 ("Prüfling seit dem Dialog geändert").
- Zusätzlich: behauptet der State `VERIFIED`, belegt das Artefakt aber nur `AMBIGUOUS`, ist das
  ein Widerspruch und blockt.
- Wirft nie: ein interner Fehler wird zu einer Grund-Meldung (fail-closed).

**3. `bash_gate.py` 5c.** Unverändert: Fast-Track-Typen (`bug`, `feature-fast`) sind
ausgenommen; `AMBIGUOUS` ohne `adversary_ambiguous_override` blockt wie bisher. Neu: `VERIFIED`
sowie `AMBIGUOUS` mit Override zählen nur, wenn `check_dialog_evidence` `None` liefert. Sonst
Block mit Grund, dem Satz "Ein grüner Testlauf ersetzt den Adversary-Dialog nicht" und dem Weg
(`/50-implement` Step 8: Dialog, `stamp`, `add-artifact`) plus `gate_diagnostics`. Ein gültiger
User-Override-Token hebt diesen Block auf — dieselbe Notbremse wie beim fehlenden Verdict.
Schlägt der Import von `adversary_dialog` fehl, gilt der Nachweis als nicht erbracht.

**4. `workflow._validate_transition` (Ziel `phase8_complete`).** Dieselbe Regel über dieselbe
Funktion: `VERIFIED` bzw. `AMBIGUOUS`+Override und `check_dialog_evidence(...) is None`, sonst
`"Adversary verdict ohne gültigen Dialog-Nachweis — <Grund>"`. Da `cmd_complete` (und damit
`finish`) diese Funktion bereits aufruft, gilt die Regel für alle drei Abschlusswege. Wie bisher
kein Override-Token-Pfad in Phase 8.

**5. `qa_gate.py`.** Ohne `--checklist` setzt `qa_gate` weiterhin `VERIFIED:<Testergebnis>`
(dokumentierte Nutzung in `/80-workflow`), behauptet aber nicht mehr "Commit is now allowed.",
sondern weist darauf hin, dass Commit-Gate und Phase 8 zusätzlich ein gestempeltes
Dialog-Artefakt verlangen. Mit `--checklist` unverändert.

## Expected Behavior

- **Input:** Workflow-State (Verdict, `test_artifacts`, Name, Phase, Typ), das registrierte bzw.
  am Standardpfad liegende Dialog-Artefakt und der aktuelle Stand der darin gehashten Dateien.
- **Output:** Commit-Gate: Exit 0 oder Exit 2 mit Grund. Phase-8-Übergang: Erfolg oder
  `BLOCKED: <Grund>` mit Exit ≠ 0. `post_bash.py`: immer Exit 0.
- **Side effects:** `post_bash.py` schreibt `last_test_run` in den aktiven Workflow-State und
  sonst nichts; die Gates lesen nur.

## Error Handling

- Kein Artefakt registriert und keins am Standardpfad → Grund nennt beide Wege.
- Registrierter Pfad existiert nicht mehr → Grund nennt den Pfad (kein stiller Rückfall auf den
  Standardpfad: die ausdrückliche Registrierung gewinnt).
- Artefakt ungültig (offene Punkte, < 2 Runden, BROKEN, kein Hash-Block, geänderte Datei) → die
  Meldung von `validate_dialog_artifact_ex` wird durchgereicht.
- Unerwarteter Fehler in der Prüfung oder fehlendes Modul → Block mit Fehlerklasse im Text;
  Ausweg im Commit-Gate: Override-Token; in Phase 8: `workflow.py abandon`.

## Known Limitations

- Ein bewusst gefälschtes Artefakt (selbst geschriebener Dialog, danach gestempelt) besteht die
  Prüfung weiterhin — geprüft werden Form und Hash-Bindung, nicht die Urheberschaft. Diese Spec
  schließt den beiläufigen Weg (grüner Testlauf, `set-field`), nicht den vorsätzlichen.
- Hash-gebunden sind nur Dateien, die im Dialog per `Code reference:` zitiert wurden
  (vorbestehend aus #131). Ändert ein Auto-Fix in `/60-validate` eine zitierte Datei, blockt
  Phase 8 bis zu einem neuen Dialog — gewollt ("passend zur aktuellen Codebasis").
- Laufende Workflows, deren `VERIFIED:<framework>` aus `post_bash.py` stammt, blocken nach dem
  Update bei Commit und Phase 8, bis ein echter Dialog registriert ist. Migrationspfad: Dialog
  nachholen (`/50-implement` Step 8), einmalig per Override-Token committen oder `abandon`.
- `qa_gate.py` registriert ein per `--checklist` geprüftes Artefakt nicht selbst; liegt es
  weder am Standardpfad noch ist es per `add-artifact` registriert, blockt das Gate mit
  genau diesem Hinweis.
- `config.yaml` → `adversary_gate.test_patterns` ("Used by post_bash.py") wird von
  `post_bash.py` schon heute nicht gelesen — vorbestehend, bleibt unangetastet.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Die Reproduktion aus Issue #253 (grüner `pytest`-Lauf in `phase6_implement`, danach
      `git commit`, kein Dialog) wird blockiert — nachgewiesen durch einen End-to-End-Test über
      die echten Hook-Skripte
- [ ] Der dokumentierte Weg (Dialog → `stamp` → `add-artifact` → `qa_gate --checklist`) erlaubt
      Commit und Phase 8 weiterhin ohne Zusatzschritt
- [ ] Keine Doku behauptet mehr, dass `post_bash.py` das Adversary-Verdict setzt
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given ein aktiver Workflow mit `adversary_verdict` null bzw. `BROKEN:…` / When
  `post_bash.py` einen grünen Testlauf verarbeitet (pytest, jest, xcodebuild, go test,
  cargo test; Ausgabe über `tool_response` oder Legacy-`tool_input.stdout`) / Then bleibt
  `adversary_verdict` byte-gleich und `last_test_run` enthält `result: "passed"`, den
  Indikator als `runner` und einen ISO-Zeitstempel in `at`.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

- **AC-2:** Given ein aktiver Workflow / When `post_bash.py` einen Testlauf mit Fehler-Evidenz
  verarbeitet (z. B. `2 failed, 3 passed`) / Then ist `last_test_run.result == "failed"` und
  `adversary_verdict` unverändert; bei einem Nicht-Test-Befehl oder einer Testausgabe ohne
  erkennbares Ergebnis bleibt die State-Datei vollständig unverändert.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

- **AC-3:** Given ein `feature`-Workflow in `phase6_implement`, `phase6b_adversary` oder
  `phase7_validate` mit `adversary_verdict: "VERIFIED:pytest"`, ohne registriertes Artefakt und
  ohne Datei am Standardpfad / When `bash_gate.py` einen `git commit` prüft / Then Exit 2; die
  Meldung nennt den fehlenden Dialog-Nachweis, den Satz "Ein grüner Testlauf ersetzt den
  Adversary-Dialog nicht" und die Schritte `stamp` und `add-artifact adversary_dialog`.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

- **AC-4:** Given derselbe Workflow mit `VERIFIED` und einem per `add-artifact` registrierten
  Artefakt (alle Punkte `[x]`, ≥ 2 Runden, `VERDICT: VERIFIED`, per `stamp` gestempelt, alle
  gehashten Dateien unverändert) / When `git commit` geprüft wird / Then Exit 0.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

- **AC-5:** Given `VERIFIED` im State und ein registriertes Artefakt, das (a) eine seit dem
  Stempeln geänderte Datei hasht, (b) keinen Hash-Block hat, (c) `VERDICT: BROKEN` trägt,
  (d) unter dem registrierten Pfad nicht existiert oder (e) gültig ist, aber nur `AMBIGUOUS`
  belegt / When `git commit` geprüft wird / Then Exit 2 mit dem jeweiligen Grund — bei (a)
  enthält die Meldung "Prüfling seit dem Dialog geändert" und den Dateinamen.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

- **AC-6:** Given `adversary_verdict: "AMBIGUOUS…"` mit `adversary_ambiguous_override` / When
  `git commit` geprüft wird / Then Exit 0 nur mit gültigem Artefakt (Verdict VERIFIED oder
  AMBIGUOUS), ohne Artefakt Exit 2 mit Dialog-Nachweis-Grund; AMBIGUOUS ohne Override blockt
  wie bisher mit dem `override-ambiguous`-Hinweis.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

- **AC-7:** Given `VERIFIED` ohne Artefakt und ein gültiger User-Override-Token für den
  Workflow (bzw. ein Workflow vom Typ `bug` oder `feature-fast` ganz ohne Token) / When
  `git commit` geprüft wird / Then Exit 0 — Notbremse und Fast-Track-Ausnahme bleiben
  unverändert wirksam.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

- **AC-8:** Given zwei registrierte Dialog-Artefakte (älteres gültig, neueres BROKEN) bzw. kein
  registriertes, aber ein gültiges Artefakt am Standardpfad bzw. eine Sitzung in einem
  Git-Worktree mit relativ registriertem Artefakt, das nur im Worktree liegt / When
  `git commit` geprüft wird / Then zählt das neueste registrierte Artefakt (Block), greift der
  Standardpfad (Exit 0) und wird das Artefakt im Worktree gefunden (Exit 0).
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

- **AC-9:** Given ein `feature`-Workflow in `phase7_validate` mit `VERIFIED` (bzw.
  AMBIGUOUS+Override) ohne gültiges Artefakt / When `workflow.py phase phase8_complete` oder
  `workflow.py complete` läuft / Then Exit ≠ 0 und stderr enthält "Adversary verdict" und den
  Dialog-Nachweis-Grund; mit gültigem Artefakt gelingt der Übergang wie bisher.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

- **AC-10:** Given die Reproduktion aus Issue #253 — Workflow in `phase6_implement`,
  `adversary_verdict: null`, kein Dialog / When `post_bash.py` einen grünen `pytest`-Lauf
  verarbeitet und danach `bash_gate.py` einen `git commit` prüft / Then bleibt das Verdict null
  und der Commit wird mit Exit 2 blockiert.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

- **AC-11:** Given `qa_gate.py` ohne `--checklist` mit grüner Testausgabe / When es das Verdict
  setzt / Then enthält stdout NICHT "Commit is now allowed.", sondern den Hinweis auf das
  zusätzlich nötige gestempelte Dialog-Artefakt; mit gültigem `--checklist` bleibt die Meldung
  "Commit is now allowed." erhalten.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `python3 -m pytest tests/test_adversary_evidence_gate_253.py -q` (AC-1 bis AC-11)
- Angepasste Bestandstests: `tests/test_verdict_pipeline_77.py`,
  `tests/test_gate_fixes_26_38_34.py`, `tests/test_workflow_name_validation.py`
- Regressionslauf: `python3 -m pytest tests/ -q`
- Drift-Checks: `python3 scripts/sync_skills.py --check`,
  `python3 scripts/ci_spec_gate.py --base origin/main`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Keine neue Architektur — ein bestehendes Gate wird an eine bestehende Prüfung
  gebunden. Drei Festlegungen:
  1. **Eine Regel, zwei Aufrufer.** `check_dialog_evidence` liegt in `adversary_dialog.py` (dem
     Eigentümer der Artefakt-Validierung) und wird von `bash_gate.py` 5c und
     `workflow._validate_transition` importiert — Muster wie `check_adr_content` im CI-Gate.
     Die bewusste Parallel-Kopie aus #97 gilt für Redirect-Parser zweier Guards; hier müssen
     beide Gates identisch entscheiden, eine Drift würde die Lücke wieder öffnen.
  2. **Separates Feld statt Entfernen.** `last_test_run` bewahrt die Beobachtung für Menschen und
     spätere Sessions, ohne Gate-Wirkung; es hält auch rote Läufe fest, damit ein grüner Hinweis
     nicht veraltet stehen bleibt.
  3. **AMBIGUOUS+Override braucht das Artefakt ebenfalls.** Sonst bliebe dieselbe Lücke über
     `set-field adversary_verdict AMBIGUOUS` plus `override-ambiguous` offen; der dokumentierte
     Weg erzeugt AMBIGUOUS ohnehin nur aus einem geprüften Artefakt.

## Changelog

- 2026-09-26: Initial spec created
