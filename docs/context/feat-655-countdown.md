# Context: feat-655-countdown

## Request Summary
Issue #655: Die Plan-Seitenleiste (Herdr-Pane `workflow.py plan --watch`) zeigt im Zeit-Block nur Uhrzeiten
(„Freigabe ca. HH:MM“, „Ende ca. A–B“). Gewünscht ist zusätzlich ein grober Countdown der verbleibenden Zeit.
PO-Entscheidungen (2026-11-24, per Auswahl): nach der Freigabe eine **Spanne** („Noch ca. 35–80 Min“),
vor der Freigabe **Countdown bis zur Freigabe**. PO-Auftrag 2026-11-25: autonom umsetzen.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py` `_plan_time_lines` (~Z.1358) | Zeit-Block; hier kommt die neue Zeile hinzu |
| `core/hooks/workflow.py` `current_estimate` (~Z.1210) | rechnet die Schätzung bei JEDEM Zeichnen mit frischem `now` neu (Archiv gecacht) |
| `core/hooks/workflow.py` `estimate_remaining` (~Z.1158) | liefert `approval` (Viertelstunde abgerundet), `end_low` (ab-), `end_high` (aufgerundet), `now` |
| `core/hooks/workflow.py` `_plan_watch` (~Z.3570) | zeichnet jede Sekunde neu (`OPENSPEC_PLAN_WATCH_INTERVAL`, Default 1 s) → Countdown läuft von selbst |
| `core/hooks/workflow.py` `render_plan` (~Z.670), `_wrap_time_line` | schmaler Pane: Zeit-Block wird umgebrochen (#642), Breite 34 (`TIME_INDENT`-Kommentar) |
| `core/hooks/workflow.py` `cmd_estimate` (~Z.5288) / `_estimate_kv_lines` | Chat-Zeile `LINE=` (Intake); bleibt unverändert (nur Seitenleiste ist Ziel) |
| `tests/test_zeitschaetzung_620.py`, `_642.py`, `test_anzeige_zeitzone_637.py`, `test_plan_zeit_auslieferung_645.py`, `test_arbeitszeit_628.py` | bestehende Tests des Zeit-Blocks (Wortlaut-Erwartungen prüfen!) |

## Existing Patterns
- Zeit-Block = `["", "Start  HH:MM", <middle>, TIME_INDENT + basis]`; `<middle>` ist „Freigabe wartet auf dich“, „Freigabe ca. HH:MM“, „Ende ca. A–B“ oder „Ende offen“; Ist-Block nach Abschluss (`actual`).
- Alles fail-open (`try/except → []`), pure Funktionen mit `now` aus dem Estimate.
- Uhrzeiten in Anzeigezone `display_timezone` (#637).

## Dependencies
- Upstream: `estimate_remaining`, `_quarter_floor/_ceil`, `_format_clock`, `_display_time`.
- Downstream: `render_plan` (Seitenleiste, `workflow.py plan`), Herdr-Pane; Chat-Ausgaben nicht betroffen.

## Existing Specs
- #620 (Zeitschätzung), #642 (Freigabe/Ende-Zeilen, Basiszeile), #637 (Anzeigezone), #645 (Ist-Zeit nach Auslieferung).

## Risks & Considerations
- Bestehende Tests erwarten exakte Zeilenlisten → neue Zeile kann Wortlaut-Tests brechen (anpassen, nicht abschwächen).
- Schmaler Pane (34 Zeichen, offenes #643): Zeile kurz halten.
- Countdown konsistent zur angezeigten Ende-Spanne: aus `end_low/end_high - now` ableiten (nicht aus ungerundeten Rest-Minuten), sonst widersprechen sich die zwei Zeilen.

## Analysis

### Type
Feature (reine Anzeige), Intake-Summe 1 → Kontext und Analyse in einem Durchgang.

### Affected Files
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/workflow.py` | MODIFY | `_plan_time_lines` + kleine pure Hilfsfunktion `_countdown_text(...)` |
| `tests/test_countdown_655.py` | CREATE | Tests mit festem `now` |
| bestehende Zeit-Tests | MODIFY nur falls Wortlaut-Listen die neue Zeile nicht zulassen |
| `CHANGELOG.md`, Versionsstellen | MODIFY | 4.22.0 (Feature) |

### Scope Assessment
- Code: 1 Datei, ca. +30 LoC; Tests ca. +100. Risiko LOW (Anzeige, fail-open).

### Technical Approach (Entscheidung Tech Lead)
- Nach der Freigabe (Zeile „Ende ca. A–B“ vorhanden): neue Zeile direkt darunter
  `Noch  ca. L–H Min` mit L = `end_low - now`, H = `end_high - now` (Minuten), L auf 5 min abgerundet, H auf 5 min aufgerundet;
  bei L == H eine Zahl. Ab 120 Minuten in Stunden mit halben Stunden (`ca. 2–3,5 h`, deutsches Komma).
  L ≤ 0 < H: `Noch  bis ca. H Min`. H ≤ 0 (Schätzung überschritten): keine Noch-Zeile.
- Vor der Freigabe (Zeile „Freigabe ca. HH:MM“): neue Zeile `Noch  ca. N Min bis Freigabe`, N = `approval - now`
  auf 5 min gerundet (mindestens 5); ≤ 0: keine Zeile.
- Keine Zeile bei „Freigabe wartet auf dich“, „Ende offen“, ohne Vergleichsdaten, Ist-Block, Abbruch.
- Basiszeile bleibt letzte Zeile des Blocks. Chat-Ausgabe `workflow.py estimate` unverändert.

### Verworfene Alternativen
- Countdown aus ungerundeten Rest-Minuten (`low_min/high_min`): widerspricht der angezeigten, auf Viertelstunden gerundeten Ende-Spanne.
- Ein Einzelwert (Median): vom PO abgewählt (wirkt genauer als er ist).
- Countdown bis Ende schon vor der Freigabe: vom PO abgewählt (zu ungenau).

### Open Questions
- keine
