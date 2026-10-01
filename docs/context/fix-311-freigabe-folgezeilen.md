# Context: fix-311-freigabe-folgezeilen

## Request Summary
Eine Freigabe (`go`, `approved` …) wird nur anhand der ersten Zeile der Nachricht bewertet.
`go⏎erst die Doku` setzt `green_approved=True`, `Approved⏎später` löst die Spec-Freigabe aus —
ohne jeden Hinweis. Die Einschränkungswörter aus #277 greifen nur in Zeile 1 (Befund F001 aus #277).

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/phase_listener.py:189` | `_leading_line` — schneidet per `split("\n", 1)[0]` auf Zeile 1 und kappt auf `LEADING_CHARS`; die eigentliche Fehlerstelle |
| `core/hooks/phase_listener.py:216` | `_leading_approval_phrase` — Fragezeichen- und Negationsprüfung laufen nur auf `_leading_line` |
| `core/hooks/phase_listener.py:241` | `_mentioned_phrase` — ebenfalls nur Zeile 1; speist den Verworfen-Hinweis (`_discard_notice`) |
| `core/hooks/phase_listener.py:272` | `_matches(leading_only=True)` — Einstieg für approval, GREEN und override |
| `core/hooks/phase_listener.py:71` | `NEGATION_WORDS` (aus #277 erweitert) |
| `tests/test_phase_listener_restrictions_277.py` | Tests zu den Einschränkungswörtern (nur einzeilige Fälle) |
| `tests/test_phase_listener_go_discussion_170.py` | Tests zur Satzbau-Regel; Zeile 429 hat den einzigen mehrzeiligen Fall (`go⏎⏎<task-notification>…`) |
| `docs/specs/fix-170-go-freigabe-phrase.md` | Z. 86: „Nur die erste Zeile zählt (unverändert)“ — bewusste frühere Entscheidung, die dieses Ticket teilweise kippt |
| `docs/specs/fix-277-freigabe-woerter.md` | Punkt 2 (Einschränkungswörter), Punkt 6 (F004 an Spec 170) |

## Existing Patterns
- Alle drei freigabe-relevanten Sets (approval, GREEN, override) laufen über `_leading_approval_phrase`. Eine Änderung dort wirkt auf alle drei, das ist gewollt.
- Klammer-Einschübe werden vor jeder Prüfung entfernt (#46: `approved (oder kann ich nicht einfach selbst weitermachen?)`).
- Stop-Lock-Phrasen laufen bewusst ohne `leading_only` und sind nicht betroffen.
- Harness-Marker (`<task-notification>` u. a.) schalten die Erkennung für den ganzen Turn ab, unabhängig von Zeilen — der Fall in Test Z. 429 bleibt davon unberührt.
- Rückmeldung läuft seit #310 über `_notify` → `systemMessage`.

## Dependencies
- Upstream: `re`, `hook_utils`, `config_loader` (Phrasenlisten aus `config.yaml`).
- Downstream: `phase_listener.main()` — Spec-Freigabe (`spec_approved`, Phasenwechsel nach phase4), `green_approved` (Marker für `post_implementation_gate`), Override-Token (entsperrt alle Gates 1 h).

## Existing Specs
- `docs/specs/fix-170-go-freigabe-phrase.md` — Satzbau-Regel; sagt ausdrücklich „nur erste Zeile“
- `docs/specs/fix-277-freigabe-woerter.md` — Einschränkungswörter, Rückmeldekanal

## Risks & Considerations
- **Falschverwerfung echter Freigaben:** Mehrzeilige Nachrichten mit Freigabe im Kopf und längerem Anschlusstext („go⏎Danke, und bitte danach noch X prüfen“) dürfen nicht pauschal verworfen werden — „noch“ wäre dort ein Einschränkungswort. Genau diese Abwägung ist der Kern der Entscheidung (Länge begrenzen vs. alle Folgezeilen prüfen).
- **Override ist am strengsten:** Er entsperrt eine Stunde lang alle Gates; Folgezeilen mit Einschränkung müssen ihn erst recht verwerfen.
- **Verworfen-Hinweis:** Wird eine Freigabe wegen Folgezeile verworfen, muss der Nutzer das erfahren (#90/#310), sonst wird aus dem stillen Wirken ein stilles Ignorieren.
- **Klammerregel (#46)** darf nicht kippen: Klammer-Einschübe in Folgezeilen müssen weiter ausgenommen sein.
- **Spec-Konflikt:** Spec 170 Z. 86 und die Tabelle dort müssen mit angepasst werden (zusammen mit F006: Schritt 6 nennt nur die alte Negationsliste).
- **Bewusst nicht Teil:** F003 (`Stop-lock enabled.` bleibt auf stderr, ein Test verlangt das).

## Analysis

### Type
Bug (Lücke in der Freigabe-Erkennung; Befunde F001 + F007 + F008 aus #277)

### Reproduktion (2026-10-01, `_leading_approval_phrase` direkt aufgerufen)
| Nachricht | Ergebnis heute | Soll |
|-----------|----------------|------|
| `go⏎erst die Doku` | Freigabe `go` | verworfen + Hinweis |
| `approved⏎später` | Freigabe `approved` | verworfen + Hinweis |
| `go⏎warum ist das so?` | Freigabe | verworfen |
| `go, falls Henning zustimmt` / `go, sobald CI gruen` | Freigabe | verworfen (F007) |
| `go⏎⏎Bitte Doku schreiben` | Freigabe | bleibt Freigabe |

### Root Cause
`_leading_line` (phase_listener.py:189) schneidet per `split("\n", 1)[0]` auf Zeile 1; Fragezeichen-
und Negationsprüfung (`_leading_approval_phrase`) und `_mentioned_phrase` sehen Folgezeilen nie.
`NEGATION_WORDS` kennt keine Bedingungs-/Zeitwörter (falls, sobald, bevor, solange, sofern,
unless, until, once).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/phase_listener.py | MODIFY | Folgezeilen auf `?` und Negation prüfen (Klammern ausgenommen); Override: Folgezeilen müssen leer sein; `NEGATION_WORDS` um F007-Wörter; Verworfen-Hinweis konsistent |
| core/hooks/bash_gate.py | MODIFY | F008: Kommentar Z. 70 nennt nicht mehr fest "go/freigabe/approved" (nur Kommentar) |
| tests/test_phase_listener_followlines_311.py | CREATE | Mehrzeilige Fälle, F007-Wörter, Klammer-Ausnahme, Override-Strenge, Hinweis |
| docs/specs/fix-170-go-freigabe-phrase.md | MODIFY | Z. 86 „nur erste Zeile“ und Tabelle anpassen (zusammen mit F006) |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Scope Assessment
- Files: 5, Estimated LoC: +120/-10, Risk: MEDIUM (Freigabe-Pfad aller drei Sets; Override entsperrt 1 h alle Gates)

### Technical Approach (Regelweg, kein Modell nötig — Wortliste/Regex, wie #277)
Empfehlung A: Die Einschränkungsprüfung (`?` + `_NEGATION_RE`) läuft über die GESAMTE Nachricht
(Klammer-Einschübe vorher entfernt; Harness-Marker-Turns bleiben abgeschaltet). Phrasen-, Füllwort-
und Zusatzwort-Prüfung bleiben auf Zeile 1. Override zusätzlich: Folgezeilen müssen leer sein.
Der Verworfen-Hinweis (`_notify`) nennt, dass die Einschränkung in einer Folgezeile steht.
Begründung: Falschverwerfung kostet eine Wiederholung („go“), Falschfreigabe kostet eine ungeprüfte
Implementierung bzw. eine Stunde offene Gates. Die Asymmetrie spricht für streng.

Alternativen:
- B) Nur kurze Nachrichten (N Zeichen/2 Zeilen) als Freigabe zulassen: einfacher, aber „go⏎erst die Doku“ bleibt bei kurzer Länge durch — löst den Fehler nicht.
- C) Mehrzeilige Nachrichten nie als Freigabe werten: maximal sicher, kippt aber „go + Absatz Zusatzinfo“ komplett.
- D) Freigabe nur als Vorschlag melden, Nutzer bestätigt: verwirft die Hook-Automatik, größter Eingriff.
Gekippt wird bei A nur die Spec-170-Entscheidung „nur erste Zeile zählt“.

### Dependencies
`re`, `hook_utils`, `config_loader`; downstream `main()` (spec_approved, green_approved, Override-Token).

### Open Questions
- [ ] Keine für den PO. Restrisiko von A: „go⏎Danke, bitte danach noch X prüfen“ wird verworfen (Hinweis erscheint, Wiederholung genügt). Empfehlung: in Kauf nehmen.
- Bewusst nicht Teil: F003 (stderr-Meldung Stop-Lock).
