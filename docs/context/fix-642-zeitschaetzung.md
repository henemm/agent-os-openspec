# Context: fix-642-zeitschaetzung

## Request Summary
Die Zeitschätzung im Plan-Pane ist trotz #628 unbrauchbar (gregor_zwanzig #3208: „1 h 40 min–8 h 22 min“, Ende am nächsten Morgen). Zusätzlich wird die Datengrundlage „(aus N Workflows)“ im schmalen Pane abgeschnitten, und Start + Dauer ergibt sichtbar nicht das angezeigte Ende (zweiter Screenshot: Start 19:50, Dauer 1–2 h, Ende 21:46–22:46).

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py:938` `_archive_phase_entry` | Aktivminuten nur mit Aktivitätsdatei; sonst `phase_log`-Wanduhr minus nur Spec-Freigabe-Wartezeit → Leerlauf/Nacht zählt als Arbeit |
| `core/hooks/workflow.py:815` `_po_wait_span` | zieht nur [Briefing, Freigabe] ab |
| `core/hooks/workflow.py:1062` `_estimate_group` | mischt Workflows mit und ohne Aktivitätsdaten gleichberechtigt |
| `core/hooks/workflow.py:1073` `_estimate_rests`, `:1094` `estimate_remaining` | Quantile (0.25/0.75) über Restdauern; `total_* = elapsed + rest`, `end_* = now + rest` |
| `core/hooks/workflow.py:1233` `_plan_time_lines` | baut `Start`/`Dauer ca. … (aus N Workflows)`/`Ende` in einer Zeile je Wert |
| `core/hooks/workflow.py:669` `render_plan` | kappt jede Zeile hart auf `width` (`line[:width]`) → Basis abgeschnitten; nur die Schlusszeile wird umgebrochen (`_wrap_plan_tail`, #550) |
| `core/hooks/workflow.py:1283` `_estimate_span_text`, `_estimate_basis` | Text der Spanne/Basis, auch von `_estimate_kv_lines` (`workflow.py estimate`, `LINE=`) genutzt |
| `core/hooks/workflow.py:899` `note_activity`, `_idle_gap_min` | Aktivitätsdatei, `idle_gap_min` (Default 15) |
| `config.yaml:366` `time_estimate` | `min_samples: 3`, `quantiles: [0.25, 0.75]`, Defaults |
| `tests/test_zeitschaetzung_620.py`, `tests/test_arbeitszeit_628.py`, `tests/test_anzeige_zeitzone_637.py` | bestehende Tests der Schätzung |

## Existing Patterns
- Pure Funktionen + dünne I/O-Hüllen, „wirft nie“, fail-open bei kaputten Daten.
- Umbruch statt Kappen gibt es schon für die Schlusszeile (`_wrap_plan_tail`, #550) und Kurztitel (`textwrap.wrap`, ~Z. 763).
- Konfiguration über `time_estimate` mit `TIME_ESTIMATE_DEFAULTS` und `_valid_estimate_config` (ungültig → aus).

## Dependencies
- Upstream: Archiv `.claude/workflows/_archive/*.json`, Aktivitätsdateien `.claude/workflows/_activity/<name>.json`, Config.
- Downstream: `render_plan` (Plan-Pane, `plan --watch`), `workflow.py estimate` (`LINE=` im Intake), Herdr-Bridge zeigt den Plan.

## Existing Specs
- `docs/specs/feat-620-zeitschaetzung.md` — Schätzung aus Erfahrungswerten.
- `docs/specs/feat-628-schaetzung-arbeitszeit.md` — Arbeitszeit; Known Limitation Z. 88: Alt-Archive behalten Leerlauf, „die Quantile dämpfen das“. Geprüft wurde dort nur das eigene Archiv (11 Workflows); gregor_zwanzig hat viel mehr Alt-Workflows ohne Aktivitätsdatei — die Annahme trägt dort nicht.

## Risks & Considerations
- Echte Archivdaten liegen nur auf dem Mac; Nachweis über synthetische Fixtures (Alt-Workflow mit Nachtsegment).
- Kappung je Segment darf echte lange Phasen (Implementierung 2 h) nicht zerstören; Alt-Segmente haben keine Aktivitätsauflösung, nur Gesamtdauer je Phase.
- „Dauer“ (Arbeitszeit) und „Ende“ (Wanduhr) sind verschiedene Größen; die Anzeige muss das auflösen, ohne zu lügen.
- `_estimate_span_text`/`_estimate_basis` werden auch im Chat (`LINE=`) genutzt — dort kein Pane-Umbruch nötig.
- Tests der Specs #620/#628/#637 prüfen konkrete Zeilenformate; Änderungen am Format müssen diese mitziehen.
