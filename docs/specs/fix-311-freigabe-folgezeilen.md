---
entity_id: fix-311-freigabe-folgezeilen
type: bugfix
created: 2026-10-01
updated: 2026-10-01
status: draft
version: "1.0"
tags: [phase-listener, approval-gate, green-approval, override, folgezeilen, einschraenkungswoerter]
test_targets: ["tests/test_phase_listener_followlines_311.py"]
---

# Freigabe: Einschränkungen in Folgezeilen und Bedingungswörter (#311)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #311 — Befunde F001, F007 und F008 aus dem Sammel-Vorgang #277 (F006 wird mit erledigt, weil dieselbe Spec-170-Stelle angefasst wird). Gehört zum Epic #200. Bewusst nicht Teil: F003 (die Stop-Lock-Meldung `Stop-lock enabled.` bleibt auf stderr, ein bestehender Test verlangt das).

## Purpose

Eine Freigabe (`go`, `approved`, `override`) wird heute nur anhand der ersten Zeile der Nachricht bewertet. `go⏎erst die Doku` setzt `green_approved`, `Approved⏎später` löst die Spec-Freigabe aus, und ein Override entsperrt eine Stunde lang alle Gates — jeweils ohne jeden Hinweis, obwohl der Nutzer in Zeile 2 das Gegenteil gesagt hat. Dazu kennt `NEGATION_WORDS` keine Bedingungs- und Zeitwörter (`falls`, `sobald`, `bevor`, `solange`, `sofern`, `unless`, `until`, `once`): `go, falls Henning zustimmt` ist heute eine Freigabe. Diese Spec schließt beide Lücken mit Regeln (Wortliste und Regex), ohne Modell.

## Source

- **File:** `core/hooks/phase_listener.py` — `NEGATION_WORDS`, `_NEGATION_RE`, `_leading_line()`, `_leading_approval_phrase()`, `_mentioned_phrase()`, `_discard_notice()`
- **File:** `core/hooks/bash_gate.py` — nur der Kommentar um Zeile 70 (F008)
- **Vorbild:** `docs/specs/fix-277-freigabe-woerter.md` (Einschränkungswörter in Zeile 1, Rückmeldekanal `_notify` → `systemMessage`)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `docs/specs/fix-170-go-freigabe-phrase.md` | Spec (Vorläufer) | Entscheidung „nur die erste Zeile zählt“ (Known Limitations), Beispieltabelle und Schritt 6 (Negationsliste) werden hier teilweise gekippt bzw. angeglichen (F006) |
| `docs/specs/fix-277-freigabe-woerter.md` | Spec (Vorläufer) | Quelle von F001/F006/F007/F008; Wortliste aus #277 wird erweitert, Rückmeldekanal (#310) wird mitbenutzt |
| `core/hooks/config_loader.py` | Modul | Phrasenlisten (`approval_phrases`, `green_phrases`, Override-Keywords) |
| `tests/test_phase_listener_restrictions_277.py` | Test | Einzeilige Einschränkungsfälle; muss unverändert grün bleiben |
| `tests/test_phase_listener_go_discussion_170.py` | Test | Satzbau-Regel; Zeile 429 hat den einzigen mehrzeiligen Fall (`go⏎⏎<task-notification>…`, Harness-Marker) |
| `tests/test_phase_listener_keyword_guard.py` | Test | Realfall #46 `approved (oder kann ich nicht einfach selbst weitermachen?)` |
| `tests/test_phase_listener_dropped_approval_90.py` | Test | Projekt-Config mit „go“ in beiden Phrasen-Sets |

## Scope

- **Affected Files:**
  `core/hooks/phase_listener.py` (MODIFY),
  `core/hooks/bash_gate.py` (MODIFY, nur Kommentar),
  `tests/test_phase_listener_followlines_311.py` (CREATE),
  `docs/specs/fix-170-go-freigabe-phrase.md` (MODIFY, nur Prosa: Known Limitations, Beispieltabelle, Schritt 6),
  `CHANGELOG.md` (MODIFY, [Unreleased])
- **Estimated Changes:** ca. +120 / −10 LoC gesamt (Produktivcode ca. 30, Tests ca. 80, Rest Prosa/Changelog). 5 Dateien, unter 250 LoC.
- `tests/test_phase_listener_restrictions_277.py` wird nicht geändert.

## Implementation Details

**1. Einschränkungsprüfung über die gesamte Nachricht (F001).** In `phase_listener.py` kommt ein kleiner Helfer, der die Folgezeilen liefert: alles nach der ersten Zeile, kleingeschrieben, Klammer-Einschübe wie in `_leading_line` entfernt (geschlossene `( … )` und eine nicht geschlossene Klammer bis Textende). Die Folgezeilen werden **nicht** auf `LEADING_CHARS` gekappt: eine Einschränkung in Zeile 40 hebt die Freigabe genauso auf wie in Zeile 2. `_leading_approval_phrase` prüft zusätzlich zur bisherigen Zeile-1-Prüfung (`"?" in line or _NEGATION_RE.search(line)`) dieselbe Bedingung (`?` und `_NEGATION_RE`) auf den Folgezeilen. Trifft sie, ist die Nachricht keine Freigabe (Rückgabe `None`).

**2. Was auf Zeile 1 bleibt.** Phrasenerkennung, Füllwort-Vorspann (`_FILLER_RE`), Zusatzwort-Budget (≤ 2 bzw. 0 bei Override) und `_CLAUSE_RE` laufen unverändert nur auf Zeile 1. Eine Folgezeile ohne `?` und ohne Einschränkungswort ändert nichts: `go⏎⏎Bitte Doku schreiben` bleibt eine Freigabe. Die Harness-Marker-Prüfung (`_is_notification_turn`) ist unberührt und schaltet die Erkennung für den ganzen Turn ab, unabhängig von Zeilen.

**3. Override ist strenger.** Für Override (Zusatzwort-Budget 0, bestimmt über `_extra_word_budget`) müssen die Folgezeilen nach Entfernen der Klammer-Einschübe **leer** sein. Ein Override entsperrt eine Stunde lang alle Gates; zu jeder Zeile darunter gilt: wer mehr schreibt, hat nicht nur „override“ gesagt. `override⏎irgendwas` wird verworfen, `override⏎⏎` (nur Leerraum) bleibt wirksam.

**4. Bedingungs- und Zeitwörter (F007).** `NEGATION_WORDS` wird um `falls`, `sobald`, `bevor`, `solange`, `sofern`, `unless`, `until`, `once` erweitert. Die Wortgrenzen-Regel bleibt (`_BOUNDARY_BEFORE`/`_BOUNDARY_AFTER`): Wörter, die nur ein Listenwort enthalten, treffen nicht (z. B. `bevorzugt`, `oncology`, `sobaldig`). Weil alle drei Freigabearten über `_leading_approval_phrase` laufen, gilt die Erweiterung für Spec-Freigabe, GREEN und Override.

**5. Verworfen-Hinweis nennt die Folgezeile.** `_mentioned_phrase` sucht weiter nur in Zeile 1 (dort steht die Phrase); `_discard_notice` bleibt der einzige Hinweis-Erzeuger und läuft über `_notify`, also seit #310 als `systemMessage`. Wird eine Nachricht verworfen, weil die Einschränkung (`?` oder Listenwort, bei Override jede nichtleere Zeile) in einer Folgezeile steht und Zeile 1 für sich eine Freigabe wäre, ergänzt der Hinweis den Satz, dass die Einschränkung in einer Folgezeile steht, mit dem betroffenen Wort bzw. Fragezeichen. Der Nutzer erfährt so, warum `go` nicht gewirkt hat, und kann es ohne Folgezeile wiederholen.

**6. F008 (bash_gate.py).** Der Kommentar um Zeile 70 nennt fest `"go"/"freigabe"/"approved"` als Auslöser des `phase_listener`. Er wird so umformuliert, dass er auf die konfigurierten Freigabe-Phrasen verweist. Nur Kommentar, keine Codeänderung.

**7. Spec #170 angleichen (F006 und Folgezeilen-Regel).** In `fix-170-go-freigabe-phrase.md`: (a) Schritt 6 nennt die vollständige, aktuelle Negations-/Einschränkungsliste statt der alten (Verweis auf `NEGATION_WORDS` in `phase_listener.py` als maßgebliche Quelle, plus Folgezeilen-Geltung); (b) Known Limitations: „Nur die erste Zeile zählt (unverändert)“ wird ersetzt durch: Phrase, Füllwort und Zusatzwörter gelten nur in Zeile 1, die Einschränkungsprüfung (`?`, Negations-/Einschränkungswörter) gilt für die gesamte Nachricht, Override verlangt leere Folgezeilen (#311); (c) die Beispieltabelle erhält die Zeilen `go⏎erst die Doku` (keine Freigabe) und `go⏎⏎Bitte Doku schreiben` (Freigabe).

**Alternativen (Regelweg vorn):**

- **Gewählt, Alternative A (Einschränkungsprüfung über die ganze Nachricht):** deterministisch, wenige Zeilen, trifft die gemeldeten Fälle exakt. Begründung der Strenge: Eine Falschverwerfung kostet eine Wiederholung („go“), eine Falschfreigabe eine ungeprüfte Implementierung bzw. eine Stunde offener Gates. Gekippt wird nur die Entscheidung aus Spec #170 „nur die erste Zeile zählt“.
- **Alternative B, nur kurze Nachrichten als Freigabe zulassen** (z. B. ≤ N Zeichen oder ≤ 2 Zeilen): einfacher, löst den Fehler aber nicht, denn `go⏎erst die Doku` ist kurz und bliebe eine Freigabe.
- **Alternative C, mehrzeilige Nachrichten nie als Freigabe werten:** maximal sicher, kippt aber „go + Absatz mit Zusatzinfo“ komplett und verwirft damit auch `go⏎⏎Bitte Doku schreiben`.
- **Alternative D, Freigabe nur als Vorschlag melden, der Nutzer bestätigt:** nimmt die Hook-Automatik weg, größter Eingriff; würde die Entscheidung kippen, dass der `phase_listener` Freigaben selbst setzt.
- **Kein Modell:** Ohne Modell geht es, weil die Nulllinie die Regel ist: Wortliste und Regex trennen die Fälle der Reproduktionstabelle eindeutig (Einschränkung ja/nein), ein Sprachmodell würde nur Latenz und Fehlerquote hinzufügen.

## Expected Behavior

- **Input:** Eine echte User-Nachricht (kein Notification-Turn), ein- oder mehrzeilig, in einer Phase, in der ein Freigabe-Wort etwas bewirken könnte.
- **Output:** Eine Nachricht setzt `spec_approved`, `green_approved` bzw. den Override-Token nur, wenn Zeile 1 eine Freigabe ist **und** weder Fragezeichen noch Einschränkungswort in einer Folgezeile steht (Klammern ausgenommen); bei Override zusätzlich nur, wenn alle Folgezeilen leer sind. Wird verworfen, erscheint dem Nutzer ein Hinweis (`systemMessage`), der die Folgezeile als Grund nennt.
- **Side effects:** Kein Zustandswechsel bei verworfenen Nachrichten; zusätzliche Hinweiszeile im bestehenden JSON-Kanal (#310). Stop-Lock-Phrasen bleiben unverändert (laufen ohne `leading_only`).

Beispiele (Standard-Config, phase6_implement bzw. phase3_spec; ⏎ = Zeilenumbruch):

| Nachricht | Heute | Soll |
|-----------|-------|------|
| `go⏎erst die Doku` | GREEN-Freigabe | verworfen + Hinweis (Folgezeile) |
| `approved⏎später` | Spec-Freigabe | verworfen + Hinweis (Folgezeile) |
| `go⏎warum ist das so?` | Freigabe | verworfen + Hinweis (Fragezeichen in Folgezeile) |
| `go, falls Henning zustimmt` | Freigabe | verworfen + Hinweis (F007) |
| `go, sobald CI gruen` | Freigabe | verworfen + Hinweis (F007) |
| `go⏎⏎Bitte Doku schreiben` | Freigabe | bleibt Freigabe (Leerzeile, keine Einschränkungswörter) |
| `approved⏎(oder später?)` | Freigabe | bleibt Freigabe (Klammer-Einschub in Folgezeile, #46) |
| `override⏎irgendwas` | Token | verworfen + Hinweis (Override: Folgezeilen müssen leer sein) |
| `go⏎⏎<task-notification>…` | übersprungen (Harness-Marker) | unverändert übersprungen |
| `go⏎Danke, bitte danach noch X prüfen` | Freigabe | verworfen + Hinweis (Restrisiko, siehe unten) |

## Known Limitations

- **Restrisiko Falschverwerfung:** `go⏎Danke, bitte danach noch X prüfen` wird verworfen, weil `noch` in der Folgezeile steht. Das ist bewusst in Kauf genommen: der Hinweis erscheint sichtbar, eine Wiederholung von `go` genügt. Die umgekehrte Fehlerrichtung (ungeprüfte Implementierung, offene Gates) ist teurer.
- **Wortliste ist endlich:** Eine Einschränkung in einer Folgezeile mit nicht gelistetem Wort und ohne Fragezeichen setzt weiter eine Freigabe. Der wirksame Schutz dahinter bleibt: Spec-Freigabe braucht das unabhängige PO-Briefing, der Commit den Adversary-Verdict.
- **Klammern bleiben Nebenbemerkung (F002):** Einschränkungen in Klammern, auch in Folgezeilen, werden ignoriert; dieselbe Regel lässt den Realfall #46 wirken.
- **Folgezeilen ohne Kappung:** Sehr lange Nachrichten mit „go“ in Zeile 1 und einem Listenwort irgendwo im Text (z. B. „noch“ in einem Absatz Zusatzinfo) werden verworfen. Gleiche Abwägung wie oben.
- **Nicht Teil:** F003 (Stop-Lock-Meldung bleibt stderr).
- **Verteilung:** wirkt in Konsumenten-Projekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] `go⏎erst die Doku`, `approved⏎später`, `go⏎warum ist das so?`, `go, falls Henning zustimmt` und `go, sobald CI gruen` setzen weder GREEN- noch Spec-Freigabe, und der Nutzer sieht den Hinweis mit dem Grund
- [ ] `go⏎⏎Bitte Doku schreiben`, `approved⏎(oder später?)` und der Notification-Fall wirken bzw. verhalten sich wie bisher
- [ ] `override⏎irgendwas` setzt keinen Override-Token
- [ ] Spec #170 (Known Limitations, Tabelle, Schritt 6) stimmt mit dem Code überein
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given ein Workflow in phase6_implement / When der User `go⏎erst die Doku` oder `go⏎nein, später` sendet / Then bleibt `green_approved` false und kein Freigabe-Marker entsteht.
  - Test: tests/test_phase_listener_followlines_311.py::test_folgezeile_einschraenkung_setzt_keine_green_freigabe
- **AC-2:** Given ein Workflow in phase3_spec / When der User `Approved⏎später` oder `approved⏎erst noch die Doku` sendet / Then bleibt `spec_approved` false und die Phase phase3_spec.
  - Test: tests/test_phase_listener_followlines_311.py::test_folgezeile_einschraenkung_setzt_keine_spec_freigabe
- **AC-3:** Given ein Workflow in phase6 bzw. phase3 / When der User `go⏎warum ist das so?` bzw. `approved⏎ist das so richtig?` sendet / Then wird keine Freigabe gesetzt (Fragezeichen in Folgezeile).
  - Test: tests/test_phase_listener_followlines_311.py::test_frage_in_folgezeile_verwirft_freigabe
- **AC-4:** Given die erweiterte Wortliste / When der User `go, falls Henning zustimmt`, `go, sobald CI gruen`, `go, bevor wir mergen`, `go, solange Tests laufen`, `go, sofern möglich`, `go, unless broken`, `go, until Friday` oder `go, once CI is green` sendet / Then wird keine Freigabe gesetzt, sowohl in Zeile 1 als auch als Folgezeile.
  - Test: tests/test_phase_listener_followlines_311.py::test_bedingungswoerter_f007_heben_freigabe_auf
- **AC-5:** Given die Wortgrenzen-Regel / When der User Sätze mit Wörtern sendet, die ein Listenwort nur enthalten (`go, bevorzugt Variante A`, `go⏎oncology`, `go⏎erste Version`) / Then wirkt die Freigabe weiter.
  - Test: tests/test_phase_listener_followlines_311.py::test_listenwort_als_wortteil_in_folgezeile_hebt_nicht_auf
- **AC-6:** Given einen Workflow in phase3_spec / When der User `approved⏎(oder später?)` sendet (Klammer-Einschub mit Frage und Listenwort in einer Folgezeile, auch nicht geschlossen) / Then wirkt die Freigabe weiter (Klammerregel #46).
  - Test: tests/test_phase_listener_followlines_311.py::test_klammer_in_folgezeile_bleibt_ausnahme
- **AC-7:** Given eine beliebige Session / When der User `override⏎irgendwas` sendet / Then entsteht kein Override-Token; When er `override⏎⏎` (nur Leerraum in den Folgezeilen) bzw. `override⏎(danach weiter)` sendet / Then entsteht der Token.
  - Test: tests/test_phase_listener_followlines_311.py::test_override_verlangt_leere_folgezeilen
- **AC-8:** Given ein Workflow in phase6 / When `go⏎erst die Doku` verworfen wird / Then enthält stdout genau ein JSON-Objekt, dessen `systemMessage` das Stichwort `go` nennt und darauf hinweist, dass die Einschränkung in einer Folgezeile steht; stderr bleibt als Spiegel gefüllt.
  - Test: tests/test_phase_listener_followlines_311.py::test_verworfen_hinweis_nennt_folgezeile_als_systemmessage
- **AC-9:** Given ein Workflow in phase6 / When der User `go⏎⏎Bitte Doku schreiben` sendet / Then wirkt die GREEN-Freigabe (Leerzeile und Zusatztext ohne Einschränkungswort).
  - Test: tests/test_phase_listener_followlines_311.py::test_leerzeile_und_zusatztext_bleibt_freigabe
- **AC-10:** Given ein Prompt mit Harness-Marker (`go⏎⏎<task-notification>…`) und eine Stop-Lock-Nachricht / When der Hook sie verarbeitet / Then verhalten sie sich unverändert (Notification-Turn überspringt die Erkennung komplett, Stop-Wort mitten im Satz sperrt weiterhin).
  - Test: tests/test_phase_listener_followlines_311.py::test_notification_turn_und_stop_lock_unveraendert
- **AC-11:** Given die Spec #170 / When sie gelesen wird / Then sagt Known Limitations nicht mehr „nur die erste Zeile zählt“ ohne Einschränkung, die Beispieltabelle enthält `go⏎erst die Doku` (keine Freigabe) und `go⏎⏎Bitte Doku schreiben` (Freigabe), und Schritt 6 nennt die Wörter aus F007 (`falls`, `sobald`, `bevor`, `solange`, `sofern`, `unless`, `until`, `once`).
  - Test: tests/test_phase_listener_followlines_311.py::test_spec_170_konsistenz_folgezeilen_tabelle_schritt6
- **AC-12:** Given die bestehenden Testdateien zu Satzbau-Regel, Einschränkungswörtern, Klammerfall und verworfener Freigabe / When sie nach der Änderung laufen / Then bleiben `test_phase_listener_go_discussion_170.py`, `test_phase_listener_restrictions_277.py`, `test_phase_listener_keyword_guard.py` und `test_phase_listener_dropped_approval_90.py` unverändert grün.
  - Test: tests/test_phase_listener_followlines_311.py::test_bestehende_freigabe_tests_bleiben_gruen
- **AC-13:** Given der Kommentar in `bash_gate.py` um Zeile 70 / When er gelesen wird / Then nennt er nicht mehr fest `"go"/"freigabe"/"approved"`, sondern verweist auf die konfigurierten Freigabe-Phrasen (F008).
  - Test: tests/test_phase_listener_followlines_311.py::test_bash_gate_kommentar_nennt_keine_festen_phrasen

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden). Die Tests steuern `core/hooks` des Worktrees per `subprocess` an (Muster aus `test_phase_listener_restrictions_277.py`: Wegwerf-Projekt, `.git` als Verzeichnis), nicht die installierte Plugin-Fassung:

- `pytest tests/test_phase_listener_followlines_311.py` — AC-1 bis AC-13: Tabellenfälle für beide Fehlerrichtungen (zu locker: Folgezeilen-Einschränkungen, F007-Wörter; zu streng: Leerzeile + Zusatztext, Klammer, Wortteil), Override-Strenge, Hinweis als `systemMessage`, Spec-170-Konsistenz per Textprüfung, Kommentar-Prüfung in `bash_gate.py`
- `pytest tests/test_phase_listener_go_discussion_170.py tests/test_phase_listener_restrictions_277.py tests/test_phase_listener_keyword_guard.py tests/test_phase_listener_dropped_approval_90.py` — bestehende Tests als Regressionsschutz (AC-12)
- `pytest tests` — Gesamtlauf

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung erweitert eine bestehende Wortliste und dehnt eine bestehende Prüfung (`?`, `_NEGATION_RE`) von Zeile 1 auf die ganze Nachricht aus, innerhalb eines bestehenden Hooks. Keine neue Komponente, Konfigurationsoption oder Schnittstelle. Die Abwägung (Prüfung über die ganze Nachricht gegen Längenbegrenzung, Mehrzeiliges nie als Freigabe, Freigabe nur als Vorschlag) steht oben unter „Alternativen“ und im Kontext-Dokument. Gekippt wird allein die Detailentscheidung „nur die erste Zeile zählt“ aus Spec #170, die dort nicht als ADR geführt wird.

## Entscheidungen des Tech Leads (für den PO)

- **Streng bei Folgezeilen:** Lieber einmal `go` wiederholen als eine Freigabe setzen, die der Nutzer in Zeile 2 zurückgenommen hat. Der Hinweis erscheint immer, die Wiederholung ist billig.
- **Override am strengsten:** Er entsperrt eine Stunde lang alle Gates, darum darf unter `override` nichts weiter stehen (außer Klammern und Leerraum).
- **Leerzeile plus Zusatztext bleibt Freigabe:** `go` mit anschließender Beschreibung, was als Nächstes zu tun ist, ist der Normalfall und soll weiter wirken, solange der Text keine Einschränkung enthält.
- **Kein Modell:** Wortliste und Regex genügen und sind messbar.

## Changelog

- 2026-10-01: Initial spec created
