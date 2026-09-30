# Context: fix-278-adversary-protokoll-format

## Request Summary
Issue #278 (Sammel-Vorgang, fasst #263 + #247): Das Prüfprotokoll erzwingt ein Format
(`### Runde N`, Verdict-Zeile), das in keiner Anweisung an den Agenten steht, und es gibt keinen
CLI-Weg, das Gerüst erzeugen zu lassen statt es zu erraten (#263). Gleichzeitig schreibt der
Adversary-Dialog zwei Kennzahlen (`adversary_findings_total`, `scope_files_changed`) nie in den
Workflow-State — beide bleiben strukturell immer 0, obwohl die Daten (Findings, `affected_files`)
im Protokoll bzw. in der Spec vorhanden sind (#247).

## Related Files

| File | Relevance |
|------|-----------|
| `core/hooks/adversary_dialog.py:491` | Rundenzählung `^### Runde \d+` — das erzwungene, nirgends dokumentierte Format |
| `core/hooks/adversary_dialog.py:170-263` | `render_dialog_artifact()` — Generator existiert, erzeugt korrektes Format, aber **kein CLI-Zugang** in `main()` (nur `parse/validate/stamp/required-files/schema`) |
| `core/hooks/adversary_dialog.py:1017-1073` | `main()` — CLI-Einstiegspunkt, dem der `render`-Subcommand fehlt |
| `core/hooks/adversary_dialog.py:419-527` | `validate_dialog_artifact_ex()` — Ort, an dem die Formprüfung sitzt (Schritt 3: Runden, Schritt 4: Verdict) |
| `core/hooks/workflow.py:1378,1380` | `cmd_write_log()` — schreibt `adversary_findings_total`/`scope_files_changed` aus dem State, aber niemand befüllt diese Felder |
| `core/hooks/workflow.py:1291-1302` | `cmd_set_affected_files()` — existierender CLI-Befehl, aber nirgends automatisch aus dem Adversary-Dialog heraus aufgerufen (nur manuell dokumentiert) |
| `core/hooks/workflow.py:1676-1690` | zweite Konsum-Stelle der leeren Kennzahlen (Retro-Ausgabe) |
| `core/agents/implementation-validator.md` (190 Zeilen) | Prüferauftrag — nennt Stempeln (Z. 162-189) und `schema` (Z. 77), sagt aber nichts über Rundenformat, Verdict-Zeile oder Minimum-Rundenzahl |
| `core/commands/50-implement.md:229-243` (Abschnitt 8c) | sagt nur „Speichere das Protokoll" — keine Struktur-Vorgabe |
| `skills/50-implement/SKILL.md` | Skill-seitiges Pendant zu 50-implement.md — vermutlich dieselbe Lücke |

## Existing Patterns

- **Präzedenzfall `## Geprüfte Dateien` (#131/#253):** dieselbe Klasse von Problem (Pflichtformat
  im Prüfprotokoll) wurde bereits gelöst — `_extract_examined_files()`,
  `render_examined_files_section()`, `stamp_dialog_artifact()` (CLI `stamp`),
  `_parse_examined_files_section()`, `_verify_examined_file_hashes()`. Der Bauplan aus #286 verweist
  explizit auf dieses Muster als Vorlage für die nächste Pflichtsektion.
- **Format vs. Inhalt (#77):** `validate_dialog_artifact_ex()` unterscheidet bereits sauber zwischen
  `failure_kind='content'` (inhaltliches Urteil, z. B. offene Checkliste, BROKEN-Verdict) und
  `failure_kind='format'` (Nachweis nicht lesbar). Ein Fix für #278 muss diese Reihenfolge erhalten:
  ein Formfehler darf nie ein Urteil in den State schreiben.
- **Zugehörige Spezifikationen:** `docs/specs/infra/fix-131-adversary-dialog-hash-binding.md` und
  `docs/specs/fix-253-adversary-evidence-gate.md` sind die direkten Vorgänger-Specs für dasselbe
  Gate.

## Dependencies

- **Upstream:** nichts — beide Befunde (#263, #247) sind in sich abgeschlossen, keine offene
  Abhängigkeit zu einem anderen Issue.
- **Downstream:** Issue #286 (Scheibe 2 von Epic #273, „Pflichtsektion Herkunft der
  Vorbedingungen") setzt #278 explizit als Voraussetzung voraus — der Bauplan dort geht davon aus,
  dass Protokoll und Generator bereits sauber zusammenspielen, bevor eine weitere Pflichtsektion
  hinzukommt.
- `/90-retro` liest `adversary_findings_total`/`affected_files` aus dem Workflow-State zur
  Qualitätskennzahlen-Auswertung — bleibt bis zum Fix wirkungslos (immer 0).

## Existing Specs
- `docs/specs/infra/fix-131-adversary-dialog-hash-binding.md` — Vorlage für Pflichtsektionen im Protokoll
- `docs/specs/fix-253-adversary-evidence-gate.md` — Format-vs-Inhalt-Unterscheidung im Gate
- `docs/specs/fix-259-adversary-diff-binding.md` — grenzt an `_cmd_required_files()`/Coverage, nicht Gegenstand hier

## Risks & Considerations
- **Zwei getrennte Reparaturen in einer Datei:** #263 (Format/Generator) und #247 (Kennzahlen) teilen
  sich `adversary_dialog.py`, sind aber unabhängige Codepfade — Spec muss beide sauber trennen, damit
  ein Fix den anderen nicht verdeckt.
- **Rückwärtskompatibilität:** bereits existierende, historisch VERIFIED abgenommene
  Protokoll-Artefakte (z. B. `docs/artifacts/*/adversary-dialog.md`) dürfen durch eine
  Formatänderung nicht rückwirkend invalidiert werden, falls das Gate sie erneut liest.
- **CLI-Erweiterung (`render`-Subcommand):** muss zum bestehenden Muster der anderen Subcommands
  passen (Exit-Codes, Fehlermeldungen) — kein Sonderfall.
- **Kennzahlen-Herkunft:** `adversary_findings_total` müsste aus den strukturierten Findings im
  fertig geschriebenen Artefakt zurückgeparst werden (es gibt aktuell keinen Parser dafür, nur einen
  Renderer) — das ist die eigentliche fehlende Funktion, keine reine Verdrahtung.
- Scoping-Limit (±250 LoC, max. 4-5 Dateien) im Blick behalten — zwei Befunde könnten in Summe eng
  werden, ggf. in Phase 2 gegen einen Teilscope prüfen.

## Analysis

### Type
Bug (Label `type:bug`, Sammel-Vorgang aus #263 + #247)

### Root Cause (mit Code-Stellen)

**Befund 1 (#263) — Rundenformat ist erratbar, nicht dokumentiert:**
- `validate_dialog_artifact_ex()` zaehlt Runden strikt als H3:
  `re.findall(r"(?m)^### Runde \d+", scan)` (`adversary_dialog.py:491`).
- `render_dialog_artifact()` erzeugt genau dieses H3-Format (`adversary_dialog.py:236:
  lines.append(f"### Runde {r['round']}")`) — der Generator ist also korrekt.
- **Aber:** `render_dialog_artifact()` wird nirgends aufgerufen (`grep` ueber `core/`
  und `skills/` liefert nur die Funktionsdefinition selbst und einen Docstring-Verweis
  in einem Test). Kein CLI-Subcommand, kein Skill, kein Hook erzeugt das Geruest.
- Die einzige Anweisung, die der pruefende Agent liest (`implementation-validator.md`),
  nennt weder H2 noch H3 noch das Wort „Runde" als Ueberschrift — Regel 7 sagt nur
  „Minimum 2 dialog rounds", ohne Markup. `50-implement.md` Abschnitt 8c sagt nur
  „Speichere das Protokoll".
- Live-Fall vom 2026-09-27: Agent schrieb `## Runde 1` / `## Runde 2 — …` (H2, wie
  jede andere Top-Level-Sektion des Protokolls). Der Regex verlangt H3 → 0 Treffer →
  Abweisung trotz inhaltlich vollstaendigem, VERIFIED-Protokoll.
- **Ursache ist doppelt:** (a) das Format existiert nur im Kopf des Codes, nicht in der
  gelesenen Anweisung: eine Formvorgabe ohne Quelle kann nur geraten werden — und wird
  es plausibel falsch (H2 statt H3, weil alle anderen Sektionen H2 sind);
  (b) selbst mit korrekter Anweisung waere der Regex unnoetig strikt (kein H2-Fallback).

**Befund 2 (#247) — Kennzahlen sind strukturell tot, nicht nur leer:**
- `cmd_write_log()` liest `data.get('adversary_findings_total', 0)` und
  `len(data.get('affected_files', []))` (`workflow.py:1378,1380`).
- `adversary_findings_total` wird **an keiner Stelle im Repository** geschrieben
  (`grep -rn "adversary_findings_total\s*="` uber `core/hooks/*.py` — kein Treffer
  ausser Lesestellen). Es gibt keinen Parser, der Findings aus einem fertig
  geschriebenen Artefakt zurueckzaehlt — nur `render_finding()`, das beim (ungenutzten)
  Rendern eine Finding-Struktur zu Markdown macht, nicht umgekehrt.
- `affected_files` wird nur ueber `cmd_set_affected_files()` (`workflow.py:1291`)
  gesetzt — ein manueller CLI-Aufruf, der an keiner Stelle aus dem Adversary-Dialog
  oder einem Hook heraus automatisch erfolgt. Bleibt der Aufruf aus (Normalfall),
  bleibt die Liste leer.
- **Bereits vorhandener, wiederverwendbarer Baustein:** `phase8_code_files(wf)`
  (`adversary_dialog.py:955`) berechnet exakt die „ehrlichere" Quelle, die der Issue
  selbst vorschlaegt (Commit-Diff statt Spec-Abschnitt) — dieselbe Menge, die
  `required-files` (Schritt 3 im Adversary-Protokoll) bereits ausgibt. Für
  `scope_files_changed`/`affected_files` muss kein neuer Git-Diff-Code entstehen,
  nur eine bestehende Funktion an der richtigen Stelle aufgerufen werden.
- `adversary_verdict` zeigt das funktionierende Gegenbeispiel: `qa_gate.py`
  (`_set_verdict()`, Zeile 52) schreibt es zuverlaessig zurueck, weil es an einen
  bereits **verpflichtenden** Schritt gekoppelt ist (Checklisten-Validierung vor
  Commit-Freigabe). Die beiden toten Kennzahlen haengen an KEINEM verpflichtenden
  Schritt — das ist der strukturelle Unterschied, nicht fehlender Code an sich.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/adversary_dialog.py` | MODIFY | Rundenregex H2+H3-tolerant; neuer `scaffold`-CLI-Subcommand (Geruest-Generator fuer `parse`); Findings-Zaehl-Funktion; beides an `stamp_dialog_artifact()` gekoppelt (schreibt `adversary_findings_total` + `affected_files` per `set-field`/`set-affected-files`, unter Wiederverwendung von `phase8_code_files()`) |
| `core/hooks/workflow.py` | MODIFY | `cmd_write_log()`: fehlendes Feld → `unbekannt` statt stillem `0`-Vorgabewert (Unterscheidung „nie gesetzt" vs. „explizit 0") |
| `core/agents/implementation-validator.md` | MODIFY | Verweist auf `adversary_dialog.py scaffold` statt Format zu erraten; Step 6 (Stamp) erwaehnt den Kennzahlen-Rueckschrieb als Nebeneffekt |
| `core/commands/50-implement.md` (Abschnitt 8c) | MODIFY | Verweist auf `scaffold` statt „Speichere das Protokoll" ohne Struktur |
| `skills/50-implement/SKILL.md` | GENERATED | Nicht manuell editieren — `python3 scripts/sync_skills.py` nach der `.md`-Aenderung laufen lassen |
| `tests/test_adversary_protokoll_format_278.py` | CREATE | Gegenprobe: H2/H3-Runden akzeptiert, echtes Format-Fehlschlagen bleibt abgewiesen, Findings-Zaehlung, `unbekannt`-Fallback |

### Scope Assessment
- Files (Produktivcode, ohne generiertes Mirror + Test): 4
- Estimated LoC: +120/-15 (grobe Schaetzung: Scaffold-Funktion ~30, Findings-Parser
  ~25, Verdrahtung in `stamp`/`write_log` ~25, Doku-Aenderungen in zwei `.md` ~30,
  Regex-Lockerung ~5) — **nahe der ±250-Grenze, aber innerhalb**. Grund fuer die
  Naehe: zwei unabhaengige Befunde in derselben Datei, wie in „Risks" bereits notiert;
  keine Ueberschreitung, aber Spec-Phase sollte beide Teile sauber als getrennte
  AC-Bloecke fuehren, damit ein Review sie einzeln pruefen kann.
- Risk Level: MEDIUM — Aenderung sitzt im Gate, das jeden Workflow vor Commit
  blockiert; Regression hier blockiert versehentlich ALLE laufenden Workflows.
  Rueckwaertskompatibilitaet (H3-only weiterhin gueltig, nur H2 zusaetzlich) senkt
  das Risiko fuer bestehende, historisch abgenommene Artefakte.

### Technical Approach

**Empfehlung Befund 1:** Format und Anweisung an einer Quelle koppeln (Vorschlag 1
aus dem Issue) — `adversary_dialog.py scaffold <workflow> <spec-path>` gibt das
gueltige Geruest (Checkliste + `## Dialog`-Platzhalter) auf stdout aus;
`implementation-validator.md` und `50-implement.md` verweisen darauf statt die
Struktur zu beschreiben. Zusaetzlich Rundenregex auf H2 **und** H3 lockern
(`^#{2,3} Runde \d+`) — deckt den real aufgetretenen Fall ab, ohne die bestehende
Form zu invalidieren.
*Alternative, die dafuer verworfen wird:* Statt Kopfzeilen zu zaehlen, koennte der
Agent die Rundenzahl einmalig explizit nennen (`Runden: 2`), analog zum
Verdict-Feld — das macht das Geruest formlos und raet nichts mehr falsch, gibt aber
die tatsaechliche Dialog-Struktur im Artefakt auf (nur noch eine behauptete Zahl,
kein nachlesbarer Verlauf). Das kippt die urspruengliche Design-Entscheidung hinter
MIN_ROUNDS (sichtbare Rundenstruktur als Beleg gegen Early-Agreement, nicht nur eine
behauptete Zahl) und ist nicht das, was der Issue selbst vorschlaegt — wird hier nur
als Alternative benannt, nicht empfohlen.

**Empfehlung Befund 2:** Kennzahlen-Rueckschrieb an den bereits verpflichtenden
`stamp`-Schritt haengen (nicht an einen neuen, optionalen Schritt) — genau das
Muster, das bei `adversary_verdict` bereits zuverlaessig funktioniert.
`stamp_dialog_artifact()` zaehlt zusaetzlich eindeutige Finding-IDs (Format aus
`implementation-validator.md`: `ID: F\d+`-Zeilen ausserhalb Fenced-Code) und ruft
`workflow.py set-field adversary_findings_total <n>` sowie — unter Wiederverwendung
von `phase8_code_files()` — `workflow.py set-affected-files --replace <dateien...>`
auf. `cmd_write_log()` unterscheidet danach „Feld nie gesetzt" (Ausgabe `unbekannt`)
von „Feld explizit 0" (echter Befund: Adversary lief, fand nichts).
*Alternative, die dafuer verworfen wird:* Ein neuer, separater CLI-Schritt
(`count-findings`), den der Agent zusaetzlich zu `stamp` aufruft — bildet exakt das
heutige Fehlermuster nach (ein manueller, leicht vergessbarer Zusatzschritt ist der
Grund, warum die Kennzahl seit Erfindung nie geschrieben wurde) und wird deshalb
verworfen zugunsten der Kopplung an einen bereits erzwungenen Schritt.

### Dependencies
- Downstream: Issue #286 setzt #278 als Voraussetzung — der `scaffold`-Befehl und
  die dokumentierten Pflichtmarker sind genau das, was #286 zum Andocken einer
  weiteren Pflichtsektion braucht.
- Keine Upstream-Abhaengigkeit.

### Open Questions
- [x] Soll `adversary_findings_total` zusaetzlich zur Bash-Gate-Schutzliste
  (`APPROVAL_MARKER_PATTERNS_REQUIRE_PATH` in `bash_gate.py`) hinzugefuegt werden?
  **Entschieden (PO, 2026-09-30): Nein.** Bleibt ungeschuetzt — reine Kennzahl ohne
  Freigabe-Wirkung, kein Gate-Risiko.
