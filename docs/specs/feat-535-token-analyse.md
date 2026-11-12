---
entity_id: feat-535-token-analyse
type: feature
created: 2026-11-12
updated: 2026-11-12
status: draft
version: "1.0"
workflow: feat-535-token-analyse
tags: [tools, token, analyse, kosten, protokolle]
---

# Token-Verbrauch je Tätigkeit: Werkzeug `token_analyse` (Issue #535)

## Approval

- [ ] Approved

## Purpose

Der PO will wissen, wofür die Token einer Claude-Code-Sitzung tatsächlich draufgehen: Recherche, Git, Tests, Code, Spec, Teilagenten oder reine Steuerung. Das eigenständige Werkzeug `core/tools/token_analyse.py` liest die Sitzungsprotokolle (`~/.claude/projects/<Projekt>*/**/*.jsonl`), ordnet jede Antwort genau einer Tätigkeit zu und zeigt je Tätigkeit Token, gewichteten Kostenanteil und den Verbrauch nach Kontextgröße. Es liegt in `core/tools/`, damit alle Projekte es über das bestehende Spiegeln von `setup.py` als `.claude/tools/token_analyse.py` erhalten.

## Source

- **File:** `core/tools/token_analyse.py`
- **Identifier:** Modul `token_analyse` mit `main()` (argparse-CLI); Zuordnung, Einlesen/Deduplizieren, Kontextstufen und Bericht als Funktionen des Moduls. Grundlage ist der Entwurf aus PR #536 (Branch `feat/token-analyse-535`), hier mit drei Korrekturen übernommen.

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| Python-Standardbibliothek (`argparse`, `json`, `pathlib`, `re`) | stdlib | einzige Abhängigkeit, keine Fremdpakete |
| Claude-Code-Sitzungsprotokolle (`type: assistant`, `message.id`, `message.usage`, `message.content[]`) | data format | Eingabe; Format nicht offiziell stabil, deshalb tolerantes Lesen |
| `setup.py` (Zeilen um 394-399 und 1474-1475) | script | spiegelt `core/tools/*.py` bereits nach `<projekt>/.claude/tools/`; keine Änderung nötig |
| `scripts/token_report.py` (#332) | script | Schwesterwerkzeug (Phase/Akteur statt Tätigkeit); bleibt unverändert, dessen Doppelzählung über Dateien ist eigenes Issue #581 |
| `docs/specs/phase-token-logging.md` | spec | ältere Spec zur Token-Erfassung je Phase, nur Abgrenzung |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/tools/token_analyse.py | CREATE | Werkzeug aus dem Entwurf PR #536 mit drei Korrekturen (Streaming-Maximum, Kontextgröße mit `input`, Hilfsfunktion nicht zwischen Konstanten) |
| tests/test_token_analyse_535.py | CREATE | Tests zu allen AC, mit synthetischen Protokollen in `tmp_path` |
| CHANGELOG.md | MODIFY | Eintrag unter `[Unreleased]` → `### Added`, nennt #535 |
| docs/specs/feat-535-token-analyse.md | CREATE | diese Spec |

Nicht im Scope: Hooks und Gates, `scripts/token_report.py` (#581), `setup.py`, Versionsnummer.

### Estimated Changes

- Files: 3 neu/geändert im Code-Bereich plus die Spec
- LoC: +280 Code, +90 bis +150 Test
- Risk Level: LOW (eigenständiges, nur lesendes Werkzeug; keine Hooks, keine Gates, keine Importe von anderem Code)

## Implementation Details

**Einlesen und Zählen.** Das Werkzeug durchsucht `~/.claude/projects/` (per `--verzeichnis` änderbar) nach Ordnern, deren Name mit dem angegebenen Präfix beginnt, und liest darin alle `*.jsonl` rekursiv. Je Zeile wird nur `type: assistant` mit `message.id` und `message.usage` berücksichtigt. Kaputte JSON-Zeilen und unlesbare Dateien werden übersprungen.

**Korrektur 1, Doppelzählung.** Claude Code schreibt eine API-Antwort als mehrere Zeilen mit derselben `message.id` (je Inhaltsblock eine Zeile). Je `message.id` zählt die Nutzung (`usage`) der Zeile mit dem höchsten `output_tokens` (robust gegen frühe Streaming-Zeilen mit kleineren Werten; der Entwurf nahm die letzte Zeile). Die Inhaltsblöcke (`tool_use` u. a.) werden über alle Zeilen der Antwort gesammelt, weil die Zuordnung zur Tätigkeit sie braucht. Fortgesetzte Sitzungen kopieren frühere Nachrichten in eine neue Datei; deshalb wird jede `message.id` dateiübergreifend genau einmal gezählt.

**Korrektur 2, Kontextgröße.** Die Kontextgröße einer Antwort ist `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` (der Entwurf ließ `input` weg). Stufen: unter 100.000, 100.000 bis 200.000, über 200.000. Der Bericht weist den Verbrauch je Tätigkeit und je Stufe aus.

**Korrektur 3, Codeordnung.** Die Hilfsfunktion zum Lesen (`_lesen`) steht nicht zwischen den Konstanten, sondern nach dem Konstantenblock. Rein strukturell, keine eigene AC.

**Zuordnung zu einer Tätigkeit.** Jede Antwort gehört zu genau einer Tätigkeit, bestimmt nach Werkzeug, Befehl und Pfad der enthaltenen Werkzeugaufrufe. Kategorien: Lesen Code, Lesen Doku, Lesen Tests, Code schreiben, Tests schreiben, Spec schreiben, Tests ausführen, Git, Steuerung (Workflow-Befehle, Plan-/Aufgabenwerkzeuge), Teilagenten, Web, MCP-Abnahme, Probieren, Warten, Bash sonstiges, ohne Werkzeug (reine Textantwort), Sonstiges. Die Muster sind eine Heuristik. Für Doku-Pfade zählt `openspec/` nur am Wortanfang eines Pfadsegments; `agent-os-openspec/…` ist Code, kein Doku-Pfad. Enthält eine Antwort mehrere Werkzeugaufrufe, entscheidet eine feste, im Modul dokumentierte Rangfolge, sodass das Ergebnis deterministisch ist.

**Bericht.** Je Tätigkeit: Antwortzahl, Rohsummen (frischer Input, Cache schreiben, Cache lesen, Output), gewichteter Kostenanteil, Output-Anteil und Denkanteil (Summe von `usage.output_tokens_details.thinking_tokens`, soweit das Protokoll sie führt). Gewichte als Näherung: frischer Input 1, Cache schreiben 2, Cache lesen 0,1, Output 5. Die Tabelle ist nach Kostenanteil absteigend sortiert. `--json` gibt dieselben Zahlen maschinenlesbar aus.

**CLI.**

- `token_analyse.py <Präfix>`: Bericht für alle Projektordner mit diesem Präfix; ein Präfix, der mit `-` beginnt (Claude-Code-Ordnernamen wie `-home-user-…`), wird als Positionsargument akzeptiert.
- `--liste`: listet die Projekte mit der Zahl ihrer Protokolle; Worktree-Ordner (`…--claude-worktrees-…`) werden zum Stamm-Projekt zusammengefasst.
- `--json`: JSON statt Text. `--verzeichnis <Pfad>`: Protokollwurzel statt `~/.claude/projects`.
- Kein Treffer: Meldung auf stderr, Exit 1.

**Datenschutz.** Protokolle enthalten private Inhalte (Prompts, Dateiinhalte, Befehle). Das Werkzeug gibt ausschließlich Summen, Zähler, Kategorie- und Projektnamen aus, nie Zeilen, Befehle, Pfade oder Texte aus den Protokollen.

## Expected Behavior

- **Input:** Projektpräfix (oder `--liste`) und optional `--verzeichnis`, `--json`
- **Output:** Tabelle bzw. JSON mit Token, Kostenanteil, Output-Anteil und Denkanteil je Tätigkeit sowie Verbrauch je Kontextstufe, nach Kostenanteil sortiert
- **Side effects:** keine; nur lesender Zugriff auf die Protokolle, keine Schreibzugriffe, kein Netzwerk

## Known Limitations

- Die Zuordnung zur Tätigkeit ist eine Heuristik auf Befehls- und Pfadmustern; sie zeigt Größenordnungen, keine Abrechnung.
- Die Kostengewichte (1 / 2 / 0,1 / 5) sind eine Näherung an die Preisverhältnisse, keine exakten Preise; Modellunterschiede (Haiku/Sonnet/Opus) fließen nicht ein.
- Das Protokollformat von Claude Code ist nicht offiziell stabil; unbekannte oder kaputte Zeilen werden übersprungen und nicht gemeldet.
- Der Denkanteil ist nur so genau, wie die Protokolle `thinking_tokens` festhalten; fehlt das Feld, zählt er 0.
- `scripts/token_report.py` (Phase/Akteur) zählt weiterhin nur je Datei dedupliziert (#581); die beiden Werkzeuge können deshalb in Summen abweichen.
- Das Werkzeug wird manuell aufgerufen; es gibt keinen Hook und keine automatische Auswertung.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Der PO kann mit einem Aufruf (`token_analyse.py --liste`, dann mit dem Projektpräfix) sehen, welche Tätigkeit wie viel Kostenanteil verbraucht, ohne dass Protokollinhalte ausgegeben werden
- [ ] Doppelt geschriebene und in fortgesetzte Sitzungen kopierte Antworten werden genau einmal gezählt
- [ ] Das Werkzeug erreicht Konsumenten-Projekte über das bestehende Spiegeln von `core/tools/` ohne Änderung an `setup.py`
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/` grün)

## Acceptance Criteria

Testaufbau: Das Modul wird per `importlib.util.spec_from_file_location` aus `core/tools/token_analyse.py` geladen; Protokolle sind synthetische JSONL-Dateien in `tmp_path`; CLI-Tests laufen als Subprozess mit `--verzeichnis`. Kein Zugriff auf echte Nutzerprotokolle.

- **AC-1:** Given Antworten mit Werkzeugaufrufen auf Code-, Doku- und Testdateien / When sie zugeordnet werden / Then landet jede Antwort in genau einer Tätigkeit (Lesen Code, Lesen Doku, Lesen Tests, Code schreiben, Tests schreiben, Spec schreiben) nach Werkzeug und Pfad
  - Test: tests/test_token_analyse_535.py::TestZuordnung::test_lesen_und_schreiben_nach_pfad

- **AC-2:** Given Bash-Aufrufe mit Testlauf, Git, Workflow-Befehl und sonstigem Befehl, dazu Teilagent-, Web- und MCP-Aufrufe, Probieren, Warten, reine Textantwort und Unbekanntes / When sie zugeordnet werden / Then ergeben sie je die Tätigkeit Tests ausführen, Git, Steuerung, Bash sonstiges, Teilagenten, Web, MCP-Abnahme, Probieren, Warten, ohne Werkzeug bzw. Sonstiges
  - Test: tests/test_token_analyse_535.py::TestZuordnung::test_bash_und_weitere_kategorien

- **AC-3:** Given ein Pfad `openspec/…` und ein Pfad `agent-os-openspec/…` / When sie zugeordnet werden / Then zählt nur der erste als Doku, der zweite als Code
  - Test: tests/test_token_analyse_535.py::TestZuordnung::test_openspec_nur_am_wortanfang_ist_doku

- **AC-4:** Given eine Antwort, die als mehrere Protokollzeilen mit derselben `message.id` und unterschiedlichem `output_tokens` vorliegt / When gezählt wird / Then zählt die Nutzung der Zeile mit dem höchsten `output_tokens` einmal, und die Werkzeugaufrufe aller Zeilen werden für die Zuordnung gesammelt, unabhängig von der Zeilenreihenfolge
  - Test: tests/test_token_analyse_535.py::TestDeduplizierung::test_streaming_zeilen_maximum_output

- **AC-5:** Given dieselbe `message.id` in zwei Protokolldateien (fortgesetzte Sitzung) / When gezählt wird / Then fließt sie genau einmal in die Summen ein
  - Test: tests/test_token_analyse_535.py::TestDeduplizierung::test_dateiuebergreifend_einmal

- **AC-6:** Given Antworten mit Kontextgrößen knapp unter und über 100.000 sowie 200.000, davon eine, die erst durch `input_tokens` die Grenze überschreitet / When die Stufen berechnet werden / Then gilt Kontext = input + cache_creation + cache_read und die Antwort liegt in der Stufe < 100k, 100–200k bzw. > 200k
  - Test: tests/test_token_analyse_535.py::TestKontextstufen::test_stufen_mit_input

- **AC-7:** Given Antworten mit bekannten Rohsummen / When der Bericht entsteht / Then ist der Kostenanteil mit den Gewichten frischer Input 1, Cache schreiben 2, Cache lesen 0,1 und Output 5 berechnet, und Output-Anteil, Denkanteil und Rohsummen stimmen mit den Eingabewerten überein
  - Test: tests/test_token_analyse_535.py::TestBericht::test_gewichtung_anteile_und_rohsummen

- **AC-8:** Given Tätigkeiten mit unterschiedlichem Kostenanteil / When der Bericht (Text und `--json`) ausgegeben wird / Then ist er nach Kostenanteil absteigend sortiert
  - Test: tests/test_token_analyse_535.py::TestBericht::test_sortiert_nach_kostenanteil

- **AC-9:** Given mehrere Projektordner, darunter Worktree-Ordner `…--claude-worktrees-…` / When `--liste` läuft / Then erscheinen die Projekte mit der Zahl ihrer Protokolle, und Worktree-Ordner sind zum Stamm-Projekt zusammengefasst
  - Test: tests/test_token_analyse_535.py::TestCli::test_liste_fasst_worktrees_zusammen

- **AC-10:** Given ein Präfix, das mit `-` beginnt, sowie `--json` und `--verzeichnis` / When das Werkzeug als Subprozess läuft / Then wird das Präfix als Positionsargument akzeptiert, die Protokollwurzel aus `--verzeichnis` gelesen und gültiges JSON ausgegeben
  - Test: tests/test_token_analyse_535.py::TestCli::test_praefix_mit_bindestrich_json_verzeichnis

- **AC-11:** Given ein Präfix ohne passende Projekte / When das Werkzeug läuft / Then endet es mit Exit 1 und einer Meldung auf stderr
  - Test: tests/test_token_analyse_535.py::TestCli::test_kein_treffer_exit_1_stderr

- **AC-12:** Given Protokolle mit kaputten JSON-Zeilen und einer unlesbaren Datei neben gültigen Zeilen / When das Werkzeug läuft / Then werden die defekten Teile übersprungen und die gültigen Antworten gezählt, Exit 0
  - Test: tests/test_token_analyse_535.py::TestCli::test_kaputte_zeilen_und_unlesbare_dateien_werden_uebersprungen

- **AC-13:** Given Protokolle, die erkennbare Marker-Texte in Prompts, Befehlen und Pfaden enthalten / When Text- und JSON-Ausgabe erzeugt werden / Then enthält keine der Ausgaben einen dieser Marker, nur Summen und Kategorienamen
  - Test: tests/test_token_analyse_535.py::TestDatenschutz::test_ausgabe_ohne_protokollinhalte

- **AC-14:** Given das Repository / When geprüft wird / Then liegt `token_analyse.py` in `core/tools/`, und die Spiegel-Logik in `setup.py` erfasst `core/tools/*.py` ohne Sonderfall für diese Datei
  - Test: tests/test_token_analyse_535.py::TestVerteilung::test_datei_in_core_tools_und_setup_spiegelt_tools

- **AC-15:** Given `CHANGELOG.md` / When gelesen / Then steht im Abschnitt `[Unreleased]` unter `### Added` ein Eintrag, der `#535` nennt
  - Test: tests/test_token_analyse_535.py::test_changelog_mentions_535

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_token_analyse_535.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/tools/token_analyse.py`

TDD-Reihenfolge: Die Tests werden vor dem Werkzeug geschrieben und schlagen zuerst fehl (Datei fehlt). Der Entwurf aus PR #536 dient als Vorlage; die Fälle für Streaming-Maximum (AC-4) und Kontextgröße mit `input` (AC-6) kommen neu hinzu.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Ein neues, eigenständiges, nur lesendes Werkzeug nach dem bestehenden Muster in `core/tools/` (Standardbibliothek, argparse, `--json`), ohne Hook, Gate, State oder neue Schnittstelle; per Löschen der Datei vollständig rückbaubar. Verworfen: (a) in `scripts/token_report.py` einbauen, weil dort die Achse Phase/Akteur gilt und #581 ein eigenes Issue ist; (b) Entwurf neu schreiben statt korrigieren, weil der Entwurf bis auf die drei Korrekturen tragfähig ist.

## Changelog

- 2026-11-12: Initial spec created
