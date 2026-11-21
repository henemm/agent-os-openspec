---
entity_id: fix-642-zeitschaetzung
type: feature
created: 2026-11-21
updated: 2026-11-21
status: draft
version: "1.1"
workflow: fix-642-zeitschaetzung
tags: [plan-pane, zeitschaetzung, workflow]
---

# Zeitschätzung: verlässlich statt früh, Viertelstunden, 80 % Sicherheit (Issue #642)

## Approval

- [ ] Approved

## Purpose

Die Zeitschätzung im Plan zeigt trotz #628 Spannen wie „1 h 40 min–8 h 22 min“ mit einem Ende am nächsten Morgen, weil alte Archiv-Workflows ohne Aktivitätsdatei Nacht und Pausen als Arbeit zählen. Die Datengrundlage „(aus N Workflows)“ wird im schmalen Pane abgeschnitten, und „Start + Dauer“ ergibt sichtbar nicht das „Ende“, weil „Dauer“ Arbeitszeit und „Ende“ Wanduhr ist.

PO-Entscheidungen (Henning, 2026-11-21, Issue-Kommentar): ein späterer, verlässlicher Wert, der laufend nachgeschliffen wird, ist wichtiger als ein früher; 15–20 min Genauigkeit genügt; Start und Ende bleiben sichtbar; vor der Spec-Freigabe nur Start und der ungefähre Zeitpunkt der Freigabe; danach eine Ende-Spanne mit 80 % Sicherheit, eine Prozentangabe nur, wenn sie nachgemessen ist; keine Prognose der Wartezeit auf den PO. Diese Spec ergänzt `feat-620-zeitschaetzung.md` und `feat-628-schaetzung-arbeitszeit.md` und ändert deren Anzeigeformat.

## Source

- Issue #642 mit zwei Nachträgen; Kontext und Analyse: `docs/context/fix-642-zeitschaetzung.md` (Variante A gewählt, B und C verworfen).
- **File:** `core/hooks/workflow.py`
- **Identifier:** `_measured_hit_rate` (neu), `_archive_phase_entry`, `_estimate_group`, `_estimate_rests`, `estimate_remaining`, `_plan_time_lines`, `render_plan`, `_estimate_kv_lines`, `_estimate_basis`; neu `_quarter_floor`, `_quarter_ceil`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.py::load_activity`, `_activity_phases` | function | Aktivitätsdatei (#628) entscheidet, ob ein Archiv-Workflow „sauber“ ist |
| `workflow.py::awaiting_human_approval` | function | „Freigabe  wartet auf dich“ |
| `workflow.py::_display_time`, `_format_clock` | function | Anzeigezone (#637) |
| `config.yaml` Abschnitt `time_estimate` | config | `quantiles`, `min_samples`; Anzeige-Abschnitt, kein Gate |
| `core/commands/00-intake.md` → `skills/00-intake/SKILL.md` | doc | Beispielsatz für `LINE=` |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/workflow.py` | MODIFY | saubere Vergleichsgruppe, Freigabe-Prognose, Ende-Spanne auf Viertelstunden, Basiszeile, Umbruch des Zeit-Blocks, `LINE=` |
| `config.yaml` | MODIFY | `quantiles: [0.1, 0.9]` |
| `tests/test_zeitschaetzung_642.py` | CREATE | Tests AC-1 bis AC-8 |
| `tests/test_zeitschaetzung_620.py`, `tests/test_arbeitszeit_628.py`, `tests/test_anzeige_zeitzone_637.py` | MODIFY | an das neue Anzeigeformat anpassen, Rechenlogik unverändert prüfen |
| `core/commands/00-intake.md`, `skills/00-intake/SKILL.md` | MODIFY | Beispielsatz der Schätzung (Skill per `scripts/sync_skills.py`) |
| `CHANGELOG.md`, `.claude-plugin/plugin.json` | MODIFY | Eintrag, Versions-Bump (Einzel-Auslieferung) |

### Estimated Changes

- Produktivcode ca. +110/-40 LoC in `workflow.py` (Grenze ±250), Tests ca. +200.
- Keine Gate-Wirkung: reine Anzeige, fail-open, wirft nie.

## Implementation Details

**1. Saubere Vergleichsgruppe.** `_archive_phase_entry` markiert Einträge mit Aktivitätsdatei als `"clean": True`, sonst `False`. `_estimate_group` berücksichtigt nur Einträge mit `clean is True`; der Rest der Gruppierung (Score-Stufe, sonst Typ, `min_samples`) bleibt. `_finished_work_min` (Ist-Block) nutzt weiterhin auch den `phase_log`-Rückfall.

**2. Keine Zahl ohne Daten.** Ist die saubere Gruppe leer, liefert `estimate_remaining` `n = 0`, `source = "none"` und keine Spanne (`end_low`/`end_high`/`approval` = None). Die Startwerte `time_estimate.defaults` werden für die Anzeige nicht mehr genutzt (Schlüssel bleiben gültig, keine Config bricht).

**3. Vor der Freigabe** (aktuelle Phase im Plan vor `phase4_approved`): Restarbeit bis zur Freigabe je Vergleichs-Workflow = Rest der laufenden Phase + Summe der folgenden Planphasen bis einschließlich `phase3_spec`. Median davon → `approval = now + Median`, gerundet auf die nächste Viertelstunde. Kein Ende.

**4. Ab der Freigabe:** Restarbeit bis zum Ende wie bisher, Spanne aus den Quantilen `time_estimate.quantiles` (neuer Standard `[0.1, 0.9]`, also 80 % der Vergleichsgruppe innerhalb). `end_low` auf die Viertelstunde abgerundet, `end_high` aufgerundet (nie enger als die Rohspanne). Sind beide gleich, eine einzige Uhrzeit.

**5. Plan-Zeitblock (Prognose):**
```
Start  19:50
Freigabe  ca. 20:30          (vor der Freigabe)
Freigabe  wartet auf dich    (awaiting_human_approval)
Ende  ca. 21:45–22:45        (ab der Freigabe)
      80 % sicher, aus 32 Workflows
```
Die Startzeit bleibt minutengenau (Tatsache). Keine „Dauer“-Zeile mehr in der Prognose. Die Basiszeile steht immer in einer eigenen Zeile: ab 10 Vergleichs-Workflows (`PERCENT_MIN_SAMPLES = 10`) „<P> % sicher, aus N Workflows“, darunter nur „aus N Workflows“. `P` ist **nachgemessen**, nicht angenommen: Leave-one-out über die Vergleichsgruppe — für jeden Workflow i wird aus den übrigen die Spanne (Quantile `quantiles`) der Restarbeit ab `phase4_approved` gebildet und geprüft, ob die tatsächliche Restarbeit von i darin lag; `P = round(100 · Treffer / N)`. Neue reine Funktion `_measured_hit_rate(group, phases, quantiles)`. Ohne saubere Gruppe: „Ende  offen“ und Basiszeile „zu wenig Vergleichsdaten“. Ist-Block fertiger Workflows bleibt wie in #628.

**6. Umbruch statt Kappen.** `render_plan` bricht die Zeilen des Zeitblocks bei `width` um (Folgezeilen mit 6 Leerzeichen eingerückt), statt sie hart zu kappen; alle anderen Zeilen bleiben wie bisher.

**7. `workflow.py estimate`.** Die Schlüssel `ESTIMATE=…`, `ESTIMATE_START`, `ESTIMATE_BASIS` bleiben; `ESTIMATE_LOW_MIN`, `ESTIMATE_HIGH_MIN`, `ESTIMATE_END_LOW`, `ESTIMATE_END_HIGH` nur, wenn eine Ende-Spanne existiert; neu `ESTIMATE_APPROVAL=<iso>` vor der Freigabe. `LINE=` folgt dem Plan: „Start 21:41, Freigabe ca. 22:15 (aus N Workflows)“, „Ende ca. 22:15–23:15 (80 % sicher, aus N Workflows)“ bzw. „Noch keine Zeitschätzung: zu wenig Vergleichsdaten“.

**8. Fail-open.** Jede Ausnahme ergibt wie bisher `None` bzw. `[]`; nie eine Ausnahme nach außen.

## Expected Behavior

- Alte Workflows ohne Aktivitätsdatei verzerren die Schätzung nicht mehr; kein Ende über Nacht aus Leerlaufdaten.
- Vor der Freigabe zeigt der Plan Start und ungefähre Freigabezeit; danach eine Ende-Spanne auf Viertelstunden, die mit jeder Phase enger wird.
- Die Datengrundlage ist bei jeder Pane-Breite vollständig lesbar.
- Es gibt keine Zeile mehr, die sich mit Start und Ende widerspricht.

## Known Limitations

- Solange ein Projekt weniger als `min_samples` Workflows mit Aktivitätsdatei hat, zeigt der Plan keine Prognose; das wächst mit jedem abgeschlossenen Workflow nach.
- Die Prozentzahl ist die nachgemessene Leave-one-out-Trefferquote früherer Workflows ab der Freigabe, keine Garantie für den einzelnen Workflow; sie kann von 80 % abweichen (die Spanne zielt auf 80 %, angezeigt wird, was tatsächlich getroffen wurde). Unter 10 Vergleichen steht keine Prozentzahl.
- Wartezeit auf den PO und Fehlerschleifen werden nicht vorhergesagt; das Ende rückt dann bei der nächsten Aktualisierung nach.

## Definition of Done

- AC-1 bis AC-8 durch `tests/test_zeitschaetzung_642.py` belegt; angepasste Tests aus #620/#628/#637 und die gesamte Suite grün.
- Plan-Pane in 34 Zeichen Breite zeigt Start, Freigabe/Ende und die Basiszeile vollständig.
- CHANGELOG, Versions-Bump, `python3 scripts/release_check.py --no-tests` grün, ausgeliefert.

## Acceptance Criteria

- **AC-1:** Given ein Archiv mit drei Workflows mit Aktivitätsdatei und fünf ohne (darunter einer mit 10-h-Nachtsegment) / When `load_archive_phase_durations` und `_estimate_group` laufen / Then besteht die Vergleichsgruppe nur aus den drei Workflows mit Aktivitätsdatei, und das Nachtsegment beeinflusst keine Spanne.
  - Test: tests/test_zeitschaetzung_642.py::test_gruppe_nur_workflows_mit_aktivitaet
- **AC-2:** Given weniger als `min_samples` saubere Vergleichs-Workflows / When Plan und `workflow.py estimate` rendern / Then steht „Ende  offen“ mit „zu wenig Vergleichsdaten“, keine Uhrzeit-Spanne und kein Startwert aus `defaults`.
  - Test: tests/test_zeitschaetzung_642.py::test_ohne_saubere_daten_keine_zahl
- **AC-3:** Given ein Workflow in `phase2_analyse` mit sauberer Vergleichsgruppe / When der Plan rendert / Then zeigt er „Start“ und „Freigabe  ca. HH:MM“ (Minute 00, 15, 30 oder 45, Median der Restarbeit bis zur Freigabe) und keine „Ende“- und keine „Dauer“-Zeile; wartet eine menschliche Freigabe, steht „Freigabe  wartet auf dich“.
  - Test: tests/test_zeitschaetzung_642.py::test_vor_freigabe_nur_start_und_freigabezeit
- **AC-4:** Given ein Workflow ab `phase4_approved` mit sauberer Vergleichsgruppe / When der Plan rendert / Then zeigt er „Ende  ca. A–B“ mit A auf die Viertelstunde abgerundet und B aufgerundet aus den Quantilen 0.1/0.9, bei A = B eine einzige Uhrzeit, und keine „Dauer“-Zeile.
  - Test: tests/test_zeitschaetzung_642.py::test_ende_spanne_viertelstunden_quantile
- **AC-5:** Given 10 oder mehr bzw. weniger als 10 saubere Vergleichs-Workflows mit bekannter Restarbeit ab der Freigabe / When der Plan rendert / Then steht in einer eigenen Zeile „P % sicher, aus N Workflows“ mit P = Leave-one-out-Trefferquote (z. B. 8 von 10 getroffen → „80 % sicher“) bzw. nur „aus N Workflows“.
  - Test: tests/test_zeitschaetzung_642.py::test_basiszeile_prozent_erst_ab_zehn
- **AC-6:** Given `render_plan` mit `width=34` und einer Prognose mit Basiszeile / When gerendert wird / Then ist keine Zeile länger als 34 Zeichen und der vollständige Text der Basiszeile („… aus 32 Workflows“) ist im Ergebnis enthalten.
  - Test: tests/test_zeitschaetzung_642.py::test_zeitblock_umbrochen_nicht_gekappt
- **AC-7:** Given ein Workflow vor bzw. nach der Freigabe / When `workflow.py estimate` läuft / Then enthält die Ausgabe `ESTIMATE_APPROVAL=` bzw. `ESTIMATE_END_LOW=`/`ESTIMATE_END_HIGH=` und eine `LINE=` im Format aus Implementation Details 7, ohne Minutenspanne der Dauer.
  - Test: tests/test_zeitschaetzung_642.py::test_estimate_cli_line_und_schluessel
- **AC-8:** Given kaputte Aktivitätsdateien, leeres Archiv und ungültige Zeitstempel / When Plan und `estimate` laufen / Then entsteht keine Ausnahme, und der Ist-Block fertiger Workflows bleibt unverändert.
  - Test: tests/test_zeitschaetzung_642.py::test_fail_open_und_ist_block_unveraendert

## Test Plan

- `python3 -m pytest tests/test_zeitschaetzung_642.py -q` (venv): AC-1 bis AC-8.
- `python3 -m pytest tests/test_zeitschaetzung_620.py tests/test_arbeitszeit_628.py tests/test_anzeige_zeitzone_637.py -q`: Regression, an neues Format angepasst.
- Gesamte Suite vor der Auslieferung.

### Automated Tests (TDD RED)

- [ ] Test 1: saubere Gruppe ohne Alt-Workflows (AC-1)
- [ ] Test 2: keine Zahl ohne saubere Daten (AC-2)
- [ ] Test 3: vor Freigabe Start + Freigabezeit, wartet auf dich (AC-3)
- [ ] Test 4: Ende-Spanne auf Viertelstunden, Quantile 0.1/0.9 (AC-4)
- [ ] Test 5: Prozent erst ab 10 Vergleichen (AC-5)
- [ ] Test 6: Umbruch bei 34 Zeichen (AC-6)
- [ ] Test 7: CLI-Schlüssel und `LINE=` (AC-7)
- [ ] Test 8: fail-open, Ist-Block unverändert (AC-8)

RED-Artefakt: `docs/artifacts/642-red.log`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** ADR-0642 (Konvention: ADR-Nummer = Issue-Nummer): „Die Zeitschätzung rechnet nur mit Workflows, deren Arbeitszeit gemessen wurde; ohne solche Daten zeigt sie keine Zahl. Vor der Spec-Freigabe zeigt sie nur den Freigabezeitpunkt, danach eine 80-%-Spanne auf Viertelstunden.“ Ergänzt ADR-0628.
- **Rationale:** PO-Vorgabe „verlässlich vor früh“. Alt-Workflows ohne Aktivitätsdatei enthalten Leerlauf und sind in Projekten mit großem Archiv die Mehrheit; die Quantile dämpfen das nicht (Befund #642). Alternative B (Alt-Daten behalten, Segmente über einer Schwelle kappen) verworfen: willkürlicher Grenzwert, verfälscht legitim lange Phasen, schon in ADR-0628 verworfen; sie würde die ADR „Alt-Daten bleiben mit Lückenkappung“ begründen. Die angezeigte Prozentzahl ist nachgemessen (Leave-one-out, ab 10 Vergleichen), weil der PO eine Prozentangabe nur „wenn seriös“ will; die reine In-sample-Quote des Quantils wäre per Konstruktion immer 80 % und damit keine Messung. Alternative C (die Spanne selbst per Leave-one-out kalibrieren, also die Quantile so lange weiten, bis 80 % getroffen werden) verworfen: bei kleinen Gruppen instabil, die Spanne würde springen; sie fiele für die ADR „Spanne wird auf die Zielquote kalibriert“.

## Changelog

- 1.0 (2026-11-21): Erstfassung nach PO-Entscheidungen zu #642.
- 1.1 (2026-11-21): Prozentangabe nachgemessen (Leave-one-out) statt aus der Quantilbreite, nach Briefing-Befund.
