---
entity_id: feat-640-auslieferung-schneller
type: feature
created: 2026-11-21
updated: 2026-11-21
status: draft
version: "1.0"
workflow: feat-640-auslieferung-schneller
tags: [ci, release, tests, pytest-xdist, arbeitsweise]
---

# Auslieferung schneller: parallele Testsuite und Versions-Bump im Fix-PR bei Einzel-Auslieferung (Issue #640)

## Approval

- [ ] Approved

## Purpose

Die Strecke vom fertigen Fix bis zur veröffentlichten Version kostet heute zwei serielle Testläufe (rund 12 und 9,5 min, bei #637 zusammen rund 21,5 min). Künftig läuft die Suite parallel (pytest-xdist) und bei Einzel-Auslieferung enthält der Fix-PR den Versions-Bump selbst, sodass ein einziger Testlauf genügt und `release.yml` per Tested-Nachweis (#633) nur noch veröffentlicht.

Entscheidung PO (2026-11-21, nach #637): „Das ist jetzt aber auch nicht wirklich schnell.“ und „Das hast du doch nach der letzten Version schon gesagt! Was läuft falsch?“ Gewählt ist Variante A, B und C sind verworfen (siehe ADR-Abschnitt).

## Source

- Issue #640, Befund und Analyse: `docs/context/feat-640-auslieferung-schneller.md` (Messung: seriell 708 s, lokal parallel mit 4 Kernen 192 s, 3935 passed, 30 skipped).
- **File:** `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `scripts/release_check.py`
- **Identifier:** Job `tests` in `ci.yml`; Schritt „Install dependencies“ in `release.yml`; neu `build_suite_command(xdist_available)` und `xdist_available()` in `release_check.py`, genutzt von `check_tests`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `pytest-xdist` | pip package | Parallele Testausführung (`-n auto`), in CI und im Release-Rückfall installiert |
| `scripts/release_check.py::check_tests` | function | Rückfall-Suite im Release ohne Nachweis; baut künftig das Kommando über `build_suite_command` |
| `scripts/release_check.py --tested-proof` (#633) | CLI-Modus | Greift auch, wenn der Bump im Fix-PR steckt (Baum des PR-Heads gleich Merge-Baum) |
| `scripts/release_check.py --pr-gate`, Job `release-readiness` | CLI-Modus / Job | Prüft einen Bump schon im PR, bleibt unverändert |
| `scripts/sync_skills.py` | script | Erzeugt `skills/60-validate/SKILL.md` aus `core/commands/60-validate.md` |
| `setup.py --refresh-aliases` | CLI-Modus | Teil des Bumps (Kurzbefehle unter `.claude/commands/`) |
| `tests/test_release_tested_proof_633.py` | test | Vorbild für Teststil, bleibt grün |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `.github/workflows/ci.yml` | MODIFY | `tests`-Job: `pip install pytest pyyaml pytest-xdist`, Aufruf `python3 -m pytest tests/ -q -n auto` |
| `.github/workflows/release.yml` | MODIFY | Schritt „Install dependencies“ installiert zusätzlich `pytest-xdist` |
| `scripts/release_check.py` | MODIFY | Funktionen `xdist_available`, `build_suite_command`; `check_tests` nutzt sie |
| `CLAUDE.md` | MODIFY | Z. 20 (Arbeitsweise) und Z. 371 (Konvention 3): Einzel-Auslieferung mit Bump im PR, getrennter Release-PR nur beim Bündeln |
| `docs/arbeitsweise.md` | MODIFY | Z. 77–86: Regel „keine Versionsnummer in Fix-PRs“ mit Ausnahme Einzel-Auslieferung, Release-Absatz angepasst |
| `core/commands/60-validate.md` | MODIFY | Auto-Ship-Abschnitt: Hinweis auf die Einzel-Auslieferungs-Regel des Projekts |
| `skills/60-validate/SKILL.md` | GENERATED | per `python3 scripts/sync_skills.py`, nie von Hand (zählt nicht zum Umfang) |
| `tests/test_auslieferung_schneller_640.py` | CREATE | Tests aller ACs |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]`, in diesem Fix-PR aber als Abschnitt der neuen Version (siehe Implementation Details 5) |

### Estimated Changes

- Files: 8 Produktiv-/Doku-/Testdateien plus 1 generierte (Grenze 5 überschritten): Davon sind 4 reine Text- bzw. Konfigurationszeilen (`ci.yml`, `release.yml`, `CLAUDE.md`, `arbeitsweise.md`, `60-validate.md`, `CHANGELOG.md`), Produktivcode nur `release_check.py`. Ein Schnitt in zwei Teile würde die Regel und ihre Doku trennen und eine halb gültige Arbeitsweise veröffentlichen; deshalb ein Schnitt, im PR begründet.
- LoC: Produktivcode ca. +25/-3 (Grenze ±250), Doku ca. +25/-10, Tests ca. +130.

## Implementation Details

**1. CI.** Im Job `tests` von `ci.yml` wird `pytest-xdist` mitinstalliert und die Suite mit `python3 -m pytest tests/ -q -n auto` gestartet. GitHub-Runner `ubuntu-latest` haben 4 vCPUs.

**2. Rückfall-Suite im Release-Wächter.** `xdist_available()` liefert `True`, wenn `importlib.util.find_spec("xdist")` ein Modul findet, sonst `False`. `build_suite_command(xdist)` ist pure und liefert `[sys.executable, "-m", "pytest", "tests/", "-q"]`, bei `xdist=True` zusätzlich `"-n", "auto"`. `check_tests` ruft `build_suite_command(xdist_available())` auf. Lokal ohne Plugin läuft die Suite wie bisher seriell.

**3. Release-Workflow.** `release.yml` installiert `pytest-xdist` im Schritt „Install dependencies“, damit die Rückfall-Suite (Fall `proof != 'yes'`) parallel läuft. Alle sonstigen Schritte bleiben unverändert.

**4. Regel Einzel-Auslieferung.** Wird ein Issue allein und sofort veröffentlicht, enthält der Fix- oder Feature-PR den Versions-Bump: `.claude-plugin/plugin.json`, README, `CLAUDE.md` (`**Version**:`), CHANGELOG-Abschnitt der neuen Version statt `[Unreleased]`, `python3 scripts/sync_skills.py` und `python3 setup.py . --refresh-aliases`. Ein getrennter Release-PR bleibt nur beim Bündeln mehrerer Issues. Der Tested-Nachweis aus #633 greift unverändert, weil Head-Baum und Merge-Baum gleich sind; `release-readiness` prüft den Bump schon im PR.

**5. CHANGELOG und Auslieferung dieses PRs.** Dieser PR wendet die neue Regel bereits an: Er enthält den Bump auf 4.19.0 (CHANGELOG-Abschnitt `[4.19.0]`, plugin.json, README, CLAUDE.md, skills, Kurzbefehle). Damit belegt die Auslieferung selbst die Gesamtstrecke mit einem einzigen Testlauf.

**6. Doku-Konsistenz.** `CLAUDE.md` (Z. 20, Z. 371), `docs/arbeitsweise.md` und `core/commands/60-validate.md` nennen dieselbe Regel; keine Stelle verlangt mehr „keine Versionsnummer in Fix-/Feature-PRs“ ohne die Ausnahme. `skills/` wird nur per Skript erzeugt.

## Expected Behavior

- **Input:** Ein Pull Request (oder Push auf main) löst den Job `tests` aus; `release_check.py` ohne `--no-tests` startet die Rückfall-Suite.
- **Output:** Die Suite läuft parallel auf allen verfügbaren Kernen (bei fehlendem Plugin seriell); bei Einzel-Auslieferung genügt ein Testlauf je Auftrag.
- **Side effects:** Keine; Testergebnisse und Gates bleiben inhaltlich gleich.

## Known Limitations

- Tests mit festen Pfaden im Repo oder gemeinsamem globalem Zustand wären unter Parallelität anfällig; der Probelauf (3935 passed) zeigte keine. Tritt ein Flake auf, wird der betroffene Test isoliert, nicht die Parallelität zurückgenommen.
- Ein Release-PR, der ohne grünen `tests`-Check auf dem PR-Head veröffentlicht wird, läuft weiter über die volle (jetzt parallele) Suite.
- Der Zeitgewinn hängt von der Runner-Größe ab (4 vCPUs gemessen vorausgesetzt).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Der Job `tests` ist im PR messbar schneller; die Dauer vorher (rund 10–12 min) und nachher steht im PR (Messung in der CI, deshalb kein AC)
- [ ] Drei grüne CI-Läufe in Folge ohne Flake (lokal parallel gemessen: 192 s statt 708 s seriell)
- [ ] Eine Einzel-Auslieferung braucht nach der neuen Regel nur noch einen Testlauf bis zur veröffentlichten Version
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, `python3 scripts/release_check.py --no-tests` grün)
- [ ] CHANGELOG-Abschnitt `[4.19.0]` mit dem Eintrag (#640), Bump im selben PR

## Acceptance Criteria

- **AC-1:** Given die Datei `.github/workflows/ci.yml` / When sie als YAML geparst wird / Then installiert der Job `tests` `pytest-xdist` und ruft die Suite mit `python3 -m pytest tests/ -q -n auto` auf.
  - Test: tests/test_auslieferung_schneller_640.py::test_ci_tests_job_installiert_xdist_und_laeuft_parallel
- **AC-2:** Given xdist ist verfügbar / When `build_suite_command` das Suite-Kommando baut / Then enthält es `-n auto`, und ohne verfügbares xdist lautet es wie bisher seriell `pytest tests/ -q` ohne `-n`.
  - Test: tests/test_auslieferung_schneller_640.py::test_suite_kommando_parallel_nur_mit_xdist
- **AC-3:** Given der Release-Wächter läuft lokal ohne installiertes xdist / When `check_tests` das Kommando bestimmt / Then wird das serielle Kommando verwendet und es entsteht keine Ausnahme, die Verfügbarkeit stammt aus `xdist_available()`.
  - Test: tests/test_auslieferung_schneller_640.py::test_check_tests_faellt_ohne_xdist_auf_seriell_zurueck
- **AC-4:** Given die Datei `.github/workflows/release.yml` / When sie als YAML geparst wird / Then installiert der Schritt „Install dependencies“ `pytest-xdist` zusätzlich zu `pytest` und `pyyaml`.
  - Test: tests/test_auslieferung_schneller_640.py::test_release_workflow_installiert_xdist
- **AC-5:** Given `CLAUDE.md`, `docs/arbeitsweise.md` und `core/commands/60-validate.md` / When ihr Text gelesen wird / Then verlangt keine Stelle mehr „keine Versionsnummer in Fix- oder Feature-PRs“ ohne die Ausnahme Einzel-Auslieferung (Bump im PR, getrennter Release-PR nur beim Bündeln mehrerer Issues). (Doku-Konsistenz, als `# doc-compliance-test` markiert)
  - Test: tests/test_auslieferung_schneller_640.py::test_doku_nennt_einzel_auslieferung_ausnahme_konsistent
- **AC-6:** Given die generierte Datei `skills/60-validate/SKILL.md` / When `scripts/sync_skills.py` im Prüfmodus läuft / Then meldet es keine Abweichung zu `core/commands/60-validate.md`.
  - Test: tests/test_auslieferung_schneller_640.py::test_skills_60_validate_ohne_drift

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `python3 -m pytest tests/test_auslieferung_schneller_640.py -q` (im venv mit `pytest`, `pyyaml`): AC-1 bis AC-6.
- `python3 -m pytest tests/test_release_tested_proof_633.py tests/test_release_check_93.py -q`: Regression des Release-Wächters.
- Messung außerhalb der ACs: `python3 -m pytest tests/ -q -n auto` dreimal, kein Flake.

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN `ci.yml` WHEN geparst THEN Installation von `pytest-xdist` und `-n auto` im Job `tests`.
- [ ] Test 2: GIVEN eingespeiste Verfügbarkeit True und False WHEN `build_suite_command` läuft THEN `-n auto` nur bei True.
- [ ] Test 3: GIVEN `xdist_available` auf False gesetzt WHEN `check_tests` das Kommando baut THEN seriell, ohne Ausnahme.
- [ ] Test 4: GIVEN `release.yml` WHEN geparst THEN `pytest-xdist` im Installationsschritt.
- [ ] Test 5: GIVEN die drei Doku-Dateien WHEN gelesen THEN Ausnahme Einzel-Auslieferung überall genannt, kein uneingeschränktes Verbot (doc-compliance).
- [ ] Test 6: GIVEN `skills/60-validate/SKILL.md` WHEN gegen `core/commands/60-validate.md` geprüft THEN kein Drift.

RED-Artefakt: `docs/artifacts/640-red.log`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Es entsteht keine neue Architektur, sondern eine andere Ausführung der Tests (Parallelität) und eine Prozessregel zur Reihenfolge von Fix und Bump. Verworfen sind Alternative B (Tests in reinen Release-PRs überspringen: der Nachweis aus #633 braucht einen grünen `tests`-Check auf dem PR-Head, sonst fällt der Release auf die volle Suite zurück und nichts wird gespart) und Alternative C (Suite auf mehrere CI-Jobs als Matrix-Shards verteilen: mehr Konfiguration und Job-Start-Overhead je Shard, xdist erreicht den Großteil mit einer Zeile; bei Wahl von C fiele eine ADR zur Sharding-Strategie). Fail-closed bleibt: ohne Plugin läuft die Suite seriell, ohne Nachweis läuft sie im Release voll.

## Changelog

- 1.0 (2026-11-21): Erstfassung nach PO-Rückmeldung zu #637, Variante A gewählt.
