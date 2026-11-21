# Mini-Spec: fix-637-anzeige-zeitzone

Issue #637, Befund 1 (Zeitzone). Befund 2 (Ende bei laufender Auslieferung) bleibt im Issue offen.

PO 2026-11-21: „Auf meinem Server zeigt das Plugin UTC an, nicht CET.“ Der Server läuft auf `Etc/UTC`, das Plugin zeigt Uhrzeiten in der Systemzone des Prozesses.

## Was ändert sich
- Neue Einstellung `time_estimate.display_timezone` (IANA-Name), Standard `Europe/Berlin`; Wert `local` heißt Systemzone wie bisher.
- Alle Uhrzeiten der Zeitschätzung (Plan-Pane: Start, Ende, Prognose; `workflow.py estimate`: `ESTIMATE_START`, `ESTIMATE_END_LOW`, `ESTIMATE_END_HIGH`, Satz in `LINE=`) werden vor der Anzeige in diese Zone umgerechnet. Naive gespeicherte Zeitstempel gelten als Systemzeit des Prozesses, Zeitstempel mit Zone werden korrekt umgerechnet. Der Datumsvergleich „heute“ erfolgt in der Anzeigezone.
- Ungültiger Zonenname oder fehlende Zonendaten: Rückfall auf die Systemzone, keine Ausnahme (fail-open wie die übrige Zeitschätzung).
- `config.yaml` dokumentiert die Einstellung, CHANGELOG unter [Unreleased].

## Was darf sich nicht ändern
- Gespeicherte Zeitstempel und Dauern bleiben unverändert, nur die Anzeige wird umgerechnet.
- Dauer-Spannen, Quantile und alle Tests aus #620 und #628 bleiben grün.

## Acceptance Criteria
- **AC-1:** Given ein Prozess in Systemzone UTC und `display_timezone` Standard / When der Plan-Block für einen Workflow mit Start 16:46 UTC (November) gerendert wird / Then zeigt er `Start  17:46`.
- **AC-2:** Given `display_timezone: local` / When derselbe Block gerendert wird / Then zeigt er `Start  16:46` wie bisher.
- **AC-3:** Given ein ungültiger Zonenname / When Plan und `estimate` laufen / Then fällt die Anzeige ohne Ausnahme auf die Systemzone zurück.
- **AC-4:** Given Systemzone UTC und Standard / When `workflow.py estimate` läuft / Then stehen `ESTIMATE_START`/`ESTIMATE_END_*` und das „Ende ca.“ in `LINE=` in deutscher Zeit.

## Manuelle Test-Schritte
1. Entfällt; alles automatisiert über `TZ=UTC` im Test.

## Inline-Test (wird während Implementierung geschrieben)
- [ ] `tests/test_anzeige_zeitzone_637.py`: AC-1 bis AC-4 mit `TZ=UTC` und `time.tzset()`.

## Architektur-Entscheidung (ADR)
- **ADR-Nr.:** keine
- **Rationale:** Reine Anzeigeumrechnung im bestehenden Abschnitt `time_estimate` (ohne Override änderbar, #622); keine neue Datenquelle, kein Gate. Standard `Europe/Berlin`, weil alle Konsumenten-Projekte dem PO gehören und Server auf UTC laufen; `local` stellt das alte Verhalten her.
