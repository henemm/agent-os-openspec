---
entity_id: feat-655-countdown
type: feature
created: 2026-11-25
updated: 2026-11-25
status: draft
workflow: feat-655-countdown
version: "1.0"
tags: [plan, seitenleiste, zeitschaetzung, countdown, herdr]
test_targets: ["tests/test_countdown_655.py"]
---

# Plan-Seitenleiste: grober Countdown der verbleibenden Zeit — #655

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #655. Baut auf #620 (Zeitschätzung), #642 (Freigabe-/Ende-Zeilen, Basiszeile), #637 (Anzeigezone) und #645 (Ist-Zeit nach Auslieferung) auf.
- **PO-Entscheidungen (2026-11-24, per Auswahl):** nach der Freigabe eine Spanne („Noch ca. 35–80 Min“), vor der Freigabe ein Countdown bis zur Freigabe. Ein Einzelwert und ein Countdown bis zum Ende schon vor der Freigabe wurden abgewählt. PO-Auftrag 2026-11-25: autonom umsetzen.
- **Analyse:** `docs/context/feat-655-countdown.md`

## Purpose

Die Plan-Seitenleiste (`workflow.py plan --watch`) zeigt im Zeit-Block bisher nur Uhrzeiten („Freigabe ca. 14:30“, „Ende ca. 15:15–16:00“). Wer nebenher arbeitet, will auf einen Blick wissen, wie lange es noch dauert. Eine zusätzliche Zeile nennt deshalb grob die verbleibende Zeit: nach der Freigabe als Spanne, vor der Freigabe als Zeit bis zur Freigabe. Reine Anzeige, rein regelbasiert, ohne Modell, ohne neuen Hook, fail-open.

## Source

- **File:** `core/hooks/workflow.py` — `_plan_time_lines` (~Z.1359), `estimate_remaining` (~Z.1158), `current_estimate` (~Z.1209), `render_plan` und `_wrap_time_line` (~Z.704, Breite 34, `TIME_INDENT` ~Z.814)
- **Identifier:** `_plan_time_lines` (geändert), `_countdown_text` (neu, pure)
- **Analyse:** `docs/context/feat-655-countdown.md`
- **Ursprungsanfrage:** GitHub-Issue #655

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `estimate_remaining` | Funktion in `workflow.py` | liefert `now`, `approval`, `end_low`, `end_high`; unverändert |
| `current_estimate` | Funktion in `workflow.py` | rechnet bei jedem Zeichnen mit frischem `now` neu; unverändert |
| `_plan_watch` | Funktion in `workflow.py` | zeichnet jede Sekunde neu (`OPENSPEC_PLAN_WATCH_INTERVAL`), dadurch läuft der Countdown von selbst; unverändert |
| `_before_approval`, `awaiting_human_approval`, `_estimate_basis`, `_parse_time` | Funktionen in `workflow.py` | Fallunterscheidung und Basiszeile; unverändert |
| `render_plan`, `_wrap_time_line` | Funktionen in `workflow.py` | Umbruch des Zeit-Blocks bei schmalem Pane; unverändert |
| `cmd_estimate`, `_estimate_kv_lines` | Funktionen in `workflow.py` | Chat-Ausgabe (`LINE=`); bleiben unberührt |
| `tests/test_zeitschaetzung_620.py`, `_642.py`, `test_anzeige_zeitzone_637.py`, `test_plan_zeit_auslieferung_645.py`, `test_arbeitszeit_628.py` | Tests | bestehende Zeit-Tests; Regressionsnetz |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/workflow.py` | MODIFY | Neue pure Hilfsfunktion `_countdown_text(estimate, data)`; `_plan_time_lines` fügt deren Zeile zwischen Mittelzeile und Basiszeile ein |
| `tests/test_countdown_655.py` | CREATE | Tests mit festem `now`, keine Wanduhr |
| bestehende Zeit-Tests | MODIFY nur falls eine Wortlaut-Liste die neue Zeile nicht zulässt (anpassen, nie abschwächen) | |
| `CHANGELOG.md` | MODIFY | Eintrag `[4.22.0]` samt Known Limitations |
| `.claude-plugin/plugin.json`, `CLAUDE.md` (Kopfzeile), `README.md` (Kopfzeile), `skills/*/SKILL.md` und `.claude/commands/*.md` (Befehls-Marker `agent-os-openspec 4.2x`) | MODIFY | Version 4.22.0; Skills und Marker über `python3 scripts/sync_skills.py`, nie von Hand |

**Nicht ändern:** `estimate_remaining`, `current_estimate`, `cmd_estimate`, `_estimate_kv_lines`, Ist-Block (`_actual_time_lines`), Config-Schlüssel.

### Estimated Changes

- Files: 1 Code-Datei, 1 Testdatei, dazu Changelog und Versionsstellen
- LoC: ca. +35/-2 im Code, ca. +120 in den Tests
- Jede Funktion bleibt unter 50 Zeilen.

## Implementation Details

**1. Neue Zeile, feste Stelle.** Der Zeit-Block ist `["", "Start  HH:MM", <Mittelzeile>, <Countdown>, TIME_INDENT + Basiszeile]`. Die Countdown-Zeile steht direkt unter der Mittelzeile; die Basiszeile bleibt die letzte Zeile. Gibt `_countdown_text` nichts zurück, entfällt die Zeile und der Block sieht aus wie bisher.

**2. Minuten aus der angezeigten Spanne.** Der Countdown wird aus `end_low`, `end_high` bzw. `approval` minus `now` abgeleitet (Differenz in Minuten, `now` über `_parse_time`), nicht aus den ungerundeten `low_min`/`high_min`. So widersprechen sich „Ende ca. A–B“ und „Noch ca. L–H“ nie. Die Anzeigezone (`display_tz`, #637) fließt nicht ein: beides sind Zeitpunkte, ihre Differenz ist zonenunabhängig.

**2a. Rundung nach der Freigabe.** Aus `L = end_low - now` und `H = end_high - now` (Minuten) wird `L5 = floor(L/5)*5` und `H5 = ceil(H/5)*5`. Die Spanne wird nach außen gerundet, nie schmaler.

**3. Textform nach der Freigabe** (Mittelzeile „Ende ca. A–B“ vorhanden):

- `H <= 0`: keine Zeile (Schätzung überschritten).
- `L5 <= 0 < H`: `Noch  bis ca. {H5} Min`.
- `L5 == H5`: `Noch  ca. {H5} Min` (eine Zahl).
- sonst `Noch  ca. {L5}–{H5} Min`.
- Ab `H5 >= 120` wechselt die Zeile auf Stunden in halben Stunden mit deutschem Komma: `L_h = max(0,5; floor(L/30)/2)`, `H_h = ceil(H/30)/2`; Form `Noch  ca. 1,5–3 h`, bei gleichen Werten `Noch  ca. 2 h`, mit `L5 <= 0` `Noch  bis ca. 2 h`. Ganze Stunden ohne Komma („2“, nicht „2,0“).

**4. Textform vor der Freigabe** (Mittelzeile „Freigabe ca. HH:MM“): `N = approval - now` in Minuten, auf 5 Minuten gerundet (kaufmännisch), mindestens 5; Zeile `Noch  ca. {N} Min bis Freigabe`. `approval <= now`: keine Zeile.

**5. Keine Zeile** bei Mittelzeile „Freigabe  wartet auf dich“, „Ende  offen“, ohne Vergleichsdaten (`n = 0`), im Ist-Block (`actual`, auch Auslieferung) und bei abgebrochenem Workflow (`_plan_time_lines` gibt dort schon `[]`).

**6. Schmaler Pane.** Alle Texte bleiben bei den vorgesehenen Zahlen unter 34 Zeichen (längste Form `Noch  ca. 120 Min bis Freigabe`, 30 Zeichen). Bei noch schmalerem Pane (#643) bricht `_wrap_time_line` am Wortende um; Zahl und Einheit bleiben unzerschnitten, solange die Breite über `len(TIME_INDENT)` liegt.

**7. Fail-open.** `_countdown_text` und der Einbau stehen im bestehenden `try/except` von `_plan_time_lines`; ein Fehler liefert `[]` wie bisher. Chat-Ausgabe `workflow.py estimate` bleibt unverändert.

## Expected Behavior

- **Input:** `_plan_time_lines(data, estimate)` mit festem `now` (Eingaben `now`, `end_low`, `end_high`, `approval`, `n`).
- **Output:** Zeit-Block mit höchstens einer zusätzlichen Zeile „Noch …“ unter der Mittelzeile.
- **Side effects:** keine; kein Schreibzugriff, keine neuen Config-Schlüssel.

Beispiele (`now` = 10:00:00, Anzeigezone beliebig, `n` ≥ 1):

| Phase | now | end_low | end_high | approval | angezeigte Countdown-Zeile |
|-------|-----|---------|----------|----------|----------------------------|
| nach Freigabe | 10:00 | 10:30 | 11:15 | – | `Noch  ca. 30–75 Min` |
| nach Freigabe | 10:07 | 10:30 | 11:15 | – | `Noch  ca. 20–70 Min` |
| nach Freigabe | 10:00 | 10:45 | 10:45 | – | `Noch  ca. 45 Min` |
| nach Freigabe | 10:00 | 10:00 | 10:45 | – | `Noch  bis ca. 45 Min` |
| nach Freigabe | 10:00 | 09:45 | 10:15 | – | `Noch  bis ca. 15 Min` |
| nach Freigabe | 10:00 | 09:00 | 09:45 | – | keine Zeile |
| nach Freigabe | 10:00 | 11:00 | 13:30 | – | `Noch  ca. 1–3,5 h` |
| nach Freigabe | 10:00 | 12:00 | 12:00 | – | `Noch  ca. 2 h` |
| nach Freigabe | 10:00 | 11:40 | 12:15 | – | `Noch  ca. 1,5–2,5 h` |
| vor Freigabe | 10:00 | – | – | 10:45 | `Noch  ca. 45 Min bis Freigabe` |
| vor Freigabe | 10:00 | – | – | 10:02 | `Noch  ca. 5 Min bis Freigabe` |
| vor Freigabe | 10:00 | – | – | 09:45 | keine Zeile |
| vor Freigabe, „wartet auf dich“ | 10:00 | – | – | – | keine Zeile |
| „Ende offen“ / `n = 0` | 10:00 | – | – | – | keine Zeile |
| Ist-Block / abgebrochen | 10:00 | – | – | – | keine Zeile |

## Known Limitations

- **Der Countdown springt:** `end_low`/`end_high` stehen auf Viertelstunden, die Zahl ändert sich also nicht minütlich, sondern läuft zwischen den Sprüngen der Ende-Spanne herunter und springt, wenn die Schätzung neu rechnet (Viertelstundengrenze der Spanne). Das ist gewollt: ein grober Wert, kein Sekundenzähler.
- **Stunden-Untergrenze (Adversary F001):** In der Stundenform steht die Untergrenze mindestens bei 0,5 h; liegt die echte Untergrenze darunter (z. B. 10 Min bei Obergrenze 200 Min), zeigt die Zeile „ca. 0,5–3,5 h“ und ist damit unten etwas enger als die Schätzung. Bewusst so gelassen: „0–3,5 h“ läse sich wie „fertig“.
- **Unplausible Eingaben (F003):** Liefert die Schätzung `end_low > end_high` (kommt aus `estimate_remaining` nicht vor), erscheint die Spanne verkehrt herum.
- **Schmaler Pane (#643):** Unterhalb von 34 Zeichen Breite bricht die Zeile um (z. B. „Noch  ca. 45 Min bis“ / „  Freigabe“); die Zahl bleibt vollständig. Die Breite des Panes selbst ist Issue #643.
- Nach „Schätzung überschritten“ (H ≤ 0) zeigt der Plan keine Zeile statt einer negativen Zahl; die Ende-Zeile bleibt stehen.
- Der Countdown nennt keine Sekunden und keine Prozentzahl; die Zuverlässigkeit steht weiter in der Basiszeile.
- Verteilung: wirkt in Konsumentenprojekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test mit festem `now` belegt
- [ ] Die Plan-Seitenleiste zeigt nach der Freigabe unter „Ende ca. …“ eine Zeile „Noch  ca. L–H Min“ (ab 2 Stunden in Stunden) und vor der Freigabe „Noch  ca. N Min bis Freigabe“
- [ ] Bei „wartet auf dich“, „Ende offen“, ohne Vergleichsdaten und im Ist-Block erscheint keine Countdown-Zeile; die Basiszeile bleibt die letzte Zeile
- [ ] Im schmalen Pane (Breite 34) ist keine Zahl abgeschnitten
- [ ] Chat-Ausgabe `workflow.py estimate` ist unverändert
- [ ] CHANGELOG-Eintrag `[4.22.0]` mit Known Limitations; Version 4.22.0 an allen Stellen (plugin.json, CLAUDE.md, README.md, Skills und Befehls-Marker per `sync_skills.py`)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (bestehende Zeit-Tests und Vollsuite grün)

## Acceptance Criteria

- **AC-1:** Given ein Workflow nach der Freigabe mit Ende-Spanne und festem `now` / When der Plan gezeichnet wird / Then steht unter „Ende ca. A–B“ die Zeile „Noch  ca. L–H Min“, L auf 5 Minuten abgerundet, H auf 5 Minuten aufgerundet, und bei gleichen gerundeten Werten nur eine Zahl
  - Test: tests/test_countdown_655.py::test_spanne_nach_freigabe_rundet_5_min_ab_und_auf
- **AC-2:** Given ein Workflow nach der Freigabe, dessen aufgerundete Obergrenze mindestens 120 Minuten beträgt / When der Plan gezeichnet wird / Then zeigt die Zeile Stunden in halben Stunden mit deutschem Komma („Noch  ca. 1–3,5 h“, bei gleichen Werten „Noch  ca. 2 h“)
  - Test: tests/test_countdown_655.py::test_ab_120_min_stunden_mit_halben_und_komma
- **AC-3:** Given ein Workflow nach der Freigabe, dessen Untergrenze bereits erreicht oder überschritten ist, die Obergrenze aber noch in der Zukunft liegt / When der Plan gezeichnet wird / Then lautet die Zeile „Noch  bis ca. H Min“ (ab 120 Minuten „bis ca. H h“)
  - Test: tests/test_countdown_655.py::test_untergrenze_erreicht_zeigt_bis_ca
- **AC-4:** Given ein Workflow nach der Freigabe, dessen Obergrenze nicht mehr in der Zukunft liegt / When der Plan gezeichnet wird / Then erscheint keine Countdown-Zeile und die Ende-Zeile bleibt stehen
  - Test: tests/test_countdown_655.py::test_obergrenze_ueberschritten_keine_zeile
- **AC-5:** Given ein Workflow vor der Freigabe mit Freigabezeitpunkt in der Zukunft / When der Plan gezeichnet wird / Then lautet die Zeile „Noch  ca. N Min bis Freigabe“ mit N auf 5 Minuten gerundet und mindestens 5
  - Test: tests/test_countdown_655.py::test_vor_freigabe_countdown_bis_freigabe_mind_5
- **AC-6:** Given ein Workflow vor der Freigabe, dessen Freigabezeitpunkt jetzt oder schon vorbei ist / When der Plan gezeichnet wird / Then erscheint keine Countdown-Zeile
  - Test: tests/test_countdown_655.py::test_freigabe_erreicht_keine_zeile
- **AC-7:** Given die Mittelzeile „Freigabe  wartet auf dich“, „Ende  offen“ oder ein Workflow ohne Vergleichsdaten / When der Plan gezeichnet wird / Then erscheint keine Countdown-Zeile
  - Test: tests/test_countdown_655.py::test_wartet_ende_offen_und_ohne_daten_keine_zeile
- **AC-8:** Given ein abgeschlossener, in Auslieferung befindlicher oder abgebrochener Workflow (Ist-Block) / When der Plan gezeichnet wird / Then erscheint keine Countdown-Zeile und der Ist-Block bleibt unverändert
  - Test: tests/test_countdown_655.py::test_ist_block_und_abbruch_ohne_countdown
- **AC-9:** Given ein Zeit-Block mit Countdown-Zeile / When der Plan gezeichnet wird / Then steht die Countdown-Zeile unter der Mittelzeile und die eingerückte Basiszeile bleibt die letzte Zeile des Blocks
  - Test: tests/test_countdown_655.py::test_basiszeile_bleibt_letzte_zeile
- **AC-10:** Given ein schmaler Pane der Breite 34 / When `render_plan` mit dieser Breite zeichnet / Then ist keine Countdown-Zahl abgeschnitten und keine Zeile länger als 34 Zeichen
  - Test: tests/test_countdown_655.py::test_schmaler_pane_breite_34_ohne_abgeschnittene_zahl
- **AC-11:** Given dieselben Zeitpunkte in verschiedenen Anzeigezonen (#637) / When der Plan gezeichnet wird / Then sind die Minuten der Countdown-Zeile identisch, nur die Uhrzeiten der anderen Zeilen unterscheiden sich
  - Test: tests/test_countdown_655.py::test_anzeigezone_aendert_countdown_minuten_nicht
- **AC-12:** Given ein Workflow mit Schätzung / When `workflow.py estimate` die Chat-Ausgabe erzeugt / Then ist sie Zeichen für Zeichen dieselbe wie vor der Änderung (keine Countdown-Zeile, `LINE=` unverändert)
  - Test: tests/test_countdown_655.py::test_chat_ausgabe_estimate_unveraendert
- **AC-13:** Given der bestehende Testbestand der Zeitschätzung / When `tests/test_zeitschaetzung_620.py`, `tests/test_zeitschaetzung_642.py`, `tests/test_anzeige_zeitzone_637.py`, `tests/test_plan_zeit_auslieferung_645.py` und `tests/test_arbeitszeit_628.py` laufen / Then bleiben sie grün
  - Test: tests/test_zeitschaetzung_642.py (Regressionslauf grün, Wortlaut nur angepasst, nie abgeschwächt)

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden), alle mit festem `now` und festen `end_low`/`end_high`/`approval`, nie mit der Wanduhr:

- `pytest tests/test_countdown_655.py` — ruft `_plan_time_lines` und `render_plan` mit handgebauten Schätzungs-Wörterbüchern auf (Muster aus `tests/test_zeitschaetzung_642.py` und `tests/test_anzeige_zeitzone_637.py`); die Beispieltabelle oben ist die Testtabelle. Der Chat-Test ruft `cmd_estimate` mit festem `now` auf und vergleicht gegen die bisherige Ausgabe.
- RED: vor der Implementierung fehlt die Zeile in allen Fällen mit erwarteter Countdown-Zeile (AC-1 bis AC-3, AC-5, AC-9, AC-10); die Fälle „keine Zeile“ (AC-4, AC-6 bis AC-8) und AC-12 sind schon vor der Änderung grün und sichern, dass die Erweiterung keine Zeile zu viel erzeugt.
- Regression: `pytest tests/test_zeitschaetzung_620.py tests/test_zeitschaetzung_642.py tests/test_anzeige_zeitzone_637.py tests/test_plan_zeit_auslieferung_645.py tests/test_arbeitszeit_628.py` sowie die Plan-Tests (`tests/test_plan_*`, `tests/test_herdr_plan_*`), danach die Vollsuite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** ADR-0655 (Konvention: ADR-Nummer = Issue-Nummer): „Die Plan-Seitenleiste zeigt die verbleibende Zeit grob und aus den bereits angezeigten, gerundeten Zeitpunkten: nach der Freigabe eine Spanne, vor der Freigabe der Countdown bis zur Freigabe.“ Ergänzt ADR-0642.
- **Rationale:** Die Zahl wird aus `end_low`/`end_high`/`approval` abgeleitet, damit sie der Uhrzeit-Zeile nie widerspricht; die Spanne bleibt ehrlich (kein Einzelwert, der genauer wirkt, als er ist). Verworfene Alternativen: (A) Countdown aus den ungerundeten Restminuten `low_min`/`high_min` — widerspricht der auf Viertelstunden gerundeten Ende-Zeile und fiele für die ADR „Countdown rechnet unabhängig von der Anzeige“. (B) Ein Einzelwert (Median) — vom PO abgewählt, wirkt genauer als er ist; fiele für die ADR „Ein Punktwert statt Spanne“. (C) Countdown bis zum Ende schon vor der Freigabe — vom PO abgewählt, vor der Freigabe zu ungenau; fiele für die ADR „Ein Countdown über den ganzen Workflow“. (D) Chat-Zeile `LINE=` ebenfalls erweitern — verworfen, Ziel ist nur die Seitenleiste, die Chat-Ausgabe bleibt stabil.

## Changelog

- 1.0 (2026-11-25): Erstfassung nach PO-Entscheidungen zu #655.
- Release-Hinweis: CHANGELOG `[4.22.0]` — „Plan-Seitenleiste: neue Zeile mit grobem Countdown der verbleibenden Zeit (nach der Freigabe als Spanne „Noch ca. L–H Min“, ab 2 Stunden in Stunden; vor der Freigabe „Noch ca. N Min bis Freigabe“); Chat-Ausgabe unverändert (#655)“
