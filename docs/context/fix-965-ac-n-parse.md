# Context: fix-965-ac-n-parse

## Request Summary
`adversary_dialog.py parse <spec>` erkennt nur die alte `## Expected Behavior`-Bullet-Liste.
Specs im seit Epic #191 (gregor_zwanzig) vorgeschriebenen AC-N-Format (`## Acceptance
Criteria` mit `- **AC-N:** Given.../When.../Then...`) liefern "Keine Expected-Behavior-Punkte
gefunden." — die Checkliste für den Adversary-Dialog muss dann manuell aus der Spec
extrahiert werden. Ursprungs-Issue: `gregor_zwanzig#965`.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/adversary_dialog.py` | Enthält `parse_spec_expected_behavior()` (Zeile 52-93) — die zu erweiternde Funktion; genutzt von CLI-Kommando `parse` (main(), Zeile 343-354) |
| `templates/spec_template.md` | Aktuelle Spec-Vorlage nutzt bereits `## Acceptance Criteria` (Zeile 63) statt `## Expected Behavior` — Vorlage ist dem Parser bereits vorausgeeilt |
| `docs/specs/_template.md` | Ältere Vorlage, nutzt noch `## Expected Behavior` (Zeile 38) — beide Formate sind im Repo gleichzeitig im Umlauf |
| `docs/specs/session-singleton-guard.md`, `bash-gate-false-positive-fix.md`, `qa-gate-path-resolution.md` u.a. (10 Dateien via Grep) | Reale Beispiel-Specs im AC-N-Format — liefern die tatsächliche Formatvariation (s. Risiken) |
| `core/commands/50-implement.md` (Zeile 186) | Ruft `adversary_dialog.py parse <spec-pfad>` während der Implementierungsphase auf — Hauptverbraucher der Funktion |
| `core/agents/implementation-validator.md` (Zeile 76) | Referenziert `adversary_dialog.py schema`, nutzt implizit die geparste Checkliste |
| `tests/test_artifact_types.py` | Einziger bestehender Test mit Bezug zu `adversary_dialog` — testet aber nur den Artefakt-Typ in `workflow.py`, NICHT das Parsing selbst |

## Existing Patterns
- `parse_spec_expected_behavior()` erkennt eine Section per Regex `^##\s+Expected Behavior`
  (case-insensitive), sammelt Zeilen bis zur nächsten `## `-Section, akzeptiert `- `- und
  `\d+. `-Bullets als je einen Punkt (kein Multi-Line-Support).
- Analoge Struktur ist für den neuen Zweig wiederverwendbar (Section-Erkennung →
  Bullet-Sammlung → Abbruch bei nächster `## `-Section), aber das AC-N-Bullet-Format selbst
  unterscheidet sich strukturell (siehe Risiken).

## Dependencies
- **Upstream:** Spec-Dateien unter `docs/specs/` (bzw. im Consumer-Projekt, z.B.
  `gregor_zwanzig/docs/specs/modules/`) — reine Markdown-Textform, kein strukturiertes Format.
- **Downstream:** `core/commands/50-implement.md` (Adversary-Dialog-Checkliste),
  `implementation-validator`-Agent (nutzt die Checkliste als Grundlage für Findings).
  Kein automatischer Aufrufer verlässt sich derzeit auf einen nicht-leeren Rückgabewert
  (kein Crash bei leerem Result) — die Funktion ist rein additiv erweiterbar.

## Existing Specs
- Keine vorhandene Spec zu `adversary_dialog.py` selbst — Erstimplementierung ohne
  begleitende Spec (siehe CHANGELOG.md Zeile ~1004).

## Risks & Considerations
- **Multi-Line-Prosa:** Reale AC-N-Einträge sind oft über mehrere Zeilen weich umgebrochen,
  z.B. `qa-gate-path-resolution.md` AC-1: die Fortsetzungszeilen tragen KEIN `-`-Präfix
  (reiner Fließtext, eingerückt). Ein 1:1-Analogon zum `Expected Behavior`-Zweig (nur
  Single-Line-Bullets) würde diese Fortsetzungszeilen abschneiden und nur den ersten
  Teilsatz jedes AC erfassen.
- **Verschachtelte `- Test:`-Sub-Bullets:** Die Spec-Vorlage (`templates/spec_template.md`
  Zeile 66/69) und reale Specs (z.B. `gregor_zwanzig/docs/specs/modules/issue_956_email_format.md`
  Zeile 198 `  - Test: ...`) hängen unter jedem AC einen eingerückten `- Test: ...`-Bullet an.
  Nach `strip()` beginnt auch diese Zeile mit `- ` — ein naiver Bullet-Regex würde sie
  fälschlich als eigenen, zusätzlichen Checklist-Punkt zählen statt sie zu ignorieren oder
  dem vorherigen AC zuzuordnen.
- **Format-Koexistenz:** Beide Formate (`## Expected Behavior` und `## Acceptance Criteria`)
  sind aktuell gleichzeitig im Repo im Umlauf (ältere vs. neuere Specs) — der Fix muss
  additiv sein, darf den bestehenden `Expected Behavior`-Zweig nicht brechen.
- **Kein Bestandstest:** Es existiert kein automatisierter Test für
  `parse_spec_expected_behavior()` — TDD-RED-Phase muss die Testdatei komplett neu anlegen
  (kein Refactoring von Bestandstests).
- **Cross-Repo-Wirkung:** `adversary_dialog.py` ist Kern-Framework-Code, der von allen
  Consumer-Projekten (u.a. `gregor_zwanzig`) über den installierten Plugin-Pfad genutzt wird
  — Änderungen wirken erst nach `setup.py --update` im jeweiligen Consumer-Projekt.

## Analysis

### Type
Bug (Parser erkennt gültiges, vorgeschriebenes Spec-Format nicht — kein Feature-Wunsch).

### Bug-Intake-Ergebnis (verifiziert)
- Root Cause 1: Section-Header-Regex kennt nur `^##\s+Expected Behavior`, nicht `Acceptance Criteria`.
- Root Cause 2: Bullet-Erkennung passt nicht zum AC-N-Format (`- **AC-N:** Given/When/Then`) und
  nicht zu dessen Mehrzeiligkeit.
- Zwei weitere reale Reproduktionsfälle bestätigt: `docs/specs/resolve-execution-context-consolidation.md`
  (6 ACs → 0 Treffer), `docs/specs/fast/retro-command.md` (ACs vorhanden → 0 Treffer).
- ~10 Specs im Repo nutzen bereits ausschließlich `## Acceptance Criteria`.
- Koexistenz beider Sections in derselben Datei bestätigt: `qa-gate-path-resolution.md` hat sowohl
  `## Expected Behavior` (Zeile 195) als auch `## Acceptance Criteria` (Zeile 244).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/adversary_dialog.py` | MODIFY | `parse_spec_expected_behavior()` (Zeile 52-93) auf State-Machine umgebaut: Section-Typ-Tracking (`expected_behavior`/`acceptance_criteria`), neuer AC-N-Bullet-Erkennungszweig, Fortsetzungszeilen-Handling, Sub-Bullet-Ausschluss |
| `tests/test_adversary_dialog_parse.py` (Name final in TDD-RED) | CREATE | ~8-12 Fälle: AC-only, EB-only, beide koexistierend, geklammertes AC-Label (`AC-8 (präzisiert):`), Sub-Bullet-Ausschluss, Soft-Wrap-Fortsetzung, leere Datei/keine Section — zusätzlich Regressionsfixtures gegen 3 echte Specs |

### Scope Assessment
- Files: 1 MODIFY + 1 CREATE
- Estimated LoC: +150/-0 bis +200/-10 (Funktion wächst um ~40-60 LoC, Testdatei ~100-150 LoC)
- Risk Level: LOW (additiv, kein Caller muss geändert werden, `create_checklist()` nimmt weiterhin nur `list[str]`)

### Technical Approach (Empfehlung des Plan-Agenten)
State-Machine statt einfachem `in_section`-Bool:
- Section-Start zusätzlich für `^##\s+Acceptance Criteria` (case-insensitive) erkennen, gleiches
  Break-Verhalten bei nächstem `^##\s+`.
- Neuer AC-Punkt beginnt bei **unindentierter** Zeile, die `^-\s+\*\*AC-\d+[^*:]*:\*\*` matcht — die
  Zeichenklasse `[^*:]*` deckt Varianten wie `- **AC-8 (präzisiert):**` ab (belegt in
  `bash-gate-false-positive-fix.md:253`).
- Unterscheidung Sub-Bullet vs. Fortsetzungszeile über **Einrückung der Rohzeile** (nicht des
  gestrippten Strings): eingerückt + beginnt mit `-` → Sub-Bullet (z.B. `  - Test:`), verwerfen.
  Eingerückt + beginnt NICHT mit `-` → Fortsetzung, an aktuellen Punkt anhängen (je Zeile
  `.strip()`, mit Leerzeichen verbunden). Robust, weil AC-Bullets in allen geprüften Specs exakt
  bei Spalte 0 stehen.
- Merge bei Koexistenz: beide Listen additiv konkatenieren (Expected-Behavior zuerst, dann AC),
  keine Priorisierungs-Heuristik nötig.
- Normalisierung: ein String pro AC-Punkt, Label `**AC-N:**` im Ergebnisstring behalten
  (Traceability für den Adversary-Dialog).
- Expected-Behavior-Zweig bleibt unverändert (kein Beleg für Soft-Wrap dort, Scope-Disziplin).

### Risiken (bewertet)
- Naive `^-\s+`-Erkennung ohne Einrückungs-Check würde `- Test:`-Sub-Bullets fälschlich als
  eigenen Punkt zählen → vermieden durch Spalten-0-Heuristik.
- Regex ohne Klammer-Toleranz matcht `AC-8 (präzisiert):` nicht → explizit über `[^*:]*` abgedeckt.
- Fehlende Leerzeile zwischen zwei ACs ist **kein** Risiko — jede AC-Zeile startet eindeutig
  unindentiert mit `- **AC-`, terminiert die vorherige Fortsetzung sauber.
- Bekannte Limitation (dokumentieren, nicht lösen): Fließtext einer AC, der selbst mit `-`
  beginnt, würde fälschlich als Sub-Bullet verworfen — in allen geprüften Specs nicht vorhanden.

### Dependencies / Reihenfolge
1. Unit-Tests zuerst (TDD RED) gegen synthetische Fixture-Strings (`tmp_path`), alle o.g. Fälle.
2. Parser auf State-Machine umbauen, beide Zweige implementieren.
3. Regressionscheck gegen 3 echte Specs (`qa-gate-path-resolution.md`,
   `bash-gate-false-positive-fix.md`, `templates/spec_template.md`) als zusätzliche Fixtures.
4. Keine Caller-Änderungen nötig (bestätigt additiv).

### Open Questions
- Keine offenen Fragen an den User — Ansatz ist durch reale Spec-Beispiele vollständig belegt.
