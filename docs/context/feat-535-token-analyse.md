# Context: feat-535-token-analyse

## Request Summary
Issue #535: Werkzeug, das die Claude-Code-Sitzungsprotokolle (`~/.claude/projects/<Projekt>*/**/*.jsonl`)
auswertet und zeigt, welche Tätigkeit (Recherche, Git, Tests, Code, Spec, Teilagenten, Steuerung) wie
viele Token und welchen gewichteten Kostenanteil verbraucht, dazu den Verbrauch nach Kontextgröße.
Liegt in `core/tools/`, damit es allen Projekten zur Verfügung steht. PO-Auftrag: autark umsetzen.

## Related Files
| File | Relevance |
|------|-----------|
| PR #536, Branch `feat/token-analyse-535` (`core/tools/token_analyse.py`, `tests/test_token_analyse_535.py`) | Fertiger Entwurf ohne Spec/Briefing; `spec-gate` in der CI rot, `tests` grün. Vorlage für diese Umsetzung |
| `scripts/token_report.py` (#332) | Schwesterwerkzeug: Verbrauch je Workflow-Phase und Akteur. Gleiche Quelle, andere Achse. Dedupliziert je `message.id` mit höchstem `output_tokens`, aber nur je Datei (Bug #581) |
| `setup.py:394-399`, `setup.py:1474-1475` | Kopiert/synchronisiert `core/tools/*.py` nach `<projekt>/.claude/tools/` — ein neues Werkzeug dort erreicht Konsumenten ohne weitere Änderung |
| `docs/specs/phase-token-logging.md` | Ältere Spec zur Token-Erfassung je Phase |
| `CHANGELOG.md` `[Unreleased]` | Eintrag unter `### Added` |

## Existing Patterns
- Eigenständige Werkzeuge (kein Hook/Gate) nutzen nur die Standardbibliothek, haben argparse-CLI und `--json` bzw. `--md`.
- Tests laden Werkzeuge per `importlib.util.spec_from_file_location` und arbeiten mit `tmp_path`-Protokollen.
- Streaming-Duplikate: Claude Code schreibt eine API-Antwort als mehrere Zeilen mit derselben `message.id`
  (je Inhaltsblock eine Zeile); `usage.output_tokens` kann in frühen Zeilen kleiner sein. `token_report.py`
  nimmt daher die Zeile mit dem höchsten `output_tokens`.
- Fortgesetzte Sitzungen kopieren frühere Nachrichten in eine neue Datei → Deduplizierung muss
  dateiübergreifend sein (genau das fehlt in `token_report.py`, #581).

## Dependencies
- Upstream: nur Standardbibliothek; Format der Claude-Code-Protokolle (`type: assistant`, `message.id`,
  `message.usage`, `message.content[].type == tool_use`).
- Downstream: keine Importe; `setup.py` verteilt die Datei nach `.claude/tools/`.

## Existing Specs
- `docs/specs/phase-token-logging.md` – Token je Phase (anderes Werkzeug)

## Analyse / Entscheidungen (Summe 1: Kontext und Analyse in einem Durchgang)
- **Entwurf aus PR #536 übernehmen**, nicht neu schreiben; Korrekturen:
  1. Je `message.id` die Nutzung der Zeile mit dem höchsten `output_tokens` nehmen (bisher: letzte Zeile).
  2. Kontextgröße einer Antwort = `input + cache_creation + cache_read` (bisher ohne `input`).
  3. Codeordnung: Hilfsfunktion `_lesen` nicht zwischen Konstanten.
- **Kein Zusammenlegen mit `token_report.py`:** andere Achse (Tätigkeit statt Phase/Akteur), eigenständiges
  Werkzeug; #581 bleibt eigenes Issue.
- **Ablage `core/tools/`** wie im Issue gefordert → Konsumenten bekommen `.claude/tools/token_analyse.py`.
- PR #536 wird nach Auslieferung als ersetzt geschlossen (Branch-Regel dieser Sitzung).

## Risks & Considerations
- Zuordnung ist eine Heuristik (Muster auf Befehle/Pfade) — als Näherung dokumentiert, keine Abrechnung.
- Protokollformat ist nicht offiziell stabil; kaputte Zeilen werden übersprungen.
- Protokolle enthalten private Inhalte — das Werkzeug gibt nur Summen aus, keine Inhalte.

## Analysis

### Type
Feature (neues eigenständiges Werkzeug)

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/tools/token_analyse.py` | CREATE | Werkzeug aus PR #536 mit den drei Korrekturen oben |
| `tests/test_token_analyse_535.py` | CREATE | Tests aus PR #536 + Streaming-Fall + Kontextgröße mit `input` |
| `docs/specs/feat-535-token-analyse.md` | CREATE | Spec |
| `CHANGELOG.md` | MODIFY | `[Unreleased]` → `### Added` |

### Scope Assessment
- Files: 4
- Estimated LoC: +~280 Code, +~90 Tests
- Risk Level: LOW (keine Hooks, keine Gates, keine Importe von anderem Code)

### Technical Approach
Entwurf aus PR #536 übernehmen und korrigieren. Messung am echten Protokoll dieser Sitzung (2026-11-12):
21 Antworten, 19 davon auf mehrere Zeilen verteilt, `output_tokens` in allen Zeilen einer Antwort gleich.
Ältere Claude-Code-Fassungen schrieben laut `token_report.py` steigende Werte → Maximum statt letzter
Zeile ist robust für beide Fälle. Dateiübergreifende Deduplizierung (bereits im Entwurf) bleibt.

### Dependencies
Keine (Standardbibliothek). Verteilung über bestehendes `setup.py`-Spiegeln von `core/tools/`.

### Open Questions
- keine (Tech-Entscheidungen oben; PO-Auftrag „autark")
