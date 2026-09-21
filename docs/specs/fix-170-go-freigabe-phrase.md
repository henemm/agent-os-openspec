---
entity_id: fix-170-go-freigabe-phrase
type: bugfix
created: 2026-09-21
updated: 2026-09-21
status: draft
version: "1.0"
tags: [phase-listener, approval-gate, green-approval, override]
---

# fix-170-go-freigabe-phrase

## Approval

- [ ] Approved

## Purpose

Ein beiläufiges Freigabe-Wort ("go", "approved", "passt" …) in einer Diskussionsnachricht wird als echte Freigabe gewertet (Issue #170). Am 2026-09-21 setzte die Nachricht „die mischung aus go, approved und der eingabe von slash-commands ist unglücklich" die GREEN-Freigabe und entsperrte damit das Post-Implementation-Gate, obwohl der User nichts freigeben wollte. Die Freigabe ist der Selbstzertifizierungs-Schutz des Frameworks (#147); sie darf nur durch eine echte Entscheidung entstehen. Diese Spec ersetzt die reine Positions-Prüfung ("Wort steht irgendwo in den ersten 120 Zeichen") durch eine Satzbau-Prüfung ("die Nachricht *ist* eine Freigabe") und macht verworfene wie wirkende Freigaben sichtbar.

## Source

- **File:** `core/hooks/phase_listener.py`
- **Identifier:** `_matches()` (Modus `leading_only=True`), Aufrufer für override, approval und GREEN im Hook-Hauptteil

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `docs/specs/fix-141-stop-lock-false-positive.md` | Spec (Vorläufer) | Gleiche Fehlerklasse beim Stop-Lock; Stop-/Continue-Phrasen bleiben hier bewusst unverändert (Not-Aus greift großzügig) |
| `docs/specs/fast/fix-46-notification-keyword-bypass.md` | Spec (Vorläufer) | `NOTIFICATION_MARKERS` und erste `leading_only`-Stufe; bleiben unverändert |
| `core/hooks/config_loader.py` | Modul | Liefert die konfigurierbaren Phrasenlisten (approval, green, override) |
| `core/hooks/post_implementation_gate.py` | Modul | Wird durch den GREEN-Marker entsperrt; Schaden bei Fehlalarm |

## Scope

- **Affected Files:**
  `core/hooks/phase_listener.py` (MODIFY),
  `tests/test_phase_listener_go_discussion_170.py` (CREATE),
  `CHANGELOG.md` (MODIFY),
  `config.yaml` (MODIFY, nur Kommentar bei den Phrasenlisten)
- **Estimated Changes:** ca. +60 LoC Produktivcode in `phase_listener.py`, ca. +150 LoC Tests, je ein Changelog- und Kommentar-Eintrag

## Implementation Details

`_matches(message, phrases, leading_only=True)` gilt für die drei freigabe-relevanten Listen (approval, GREEN, override). Ohne `leading_only` (Stop-/Continue-Phrasen) bleibt das Verhalten unverändert.

Neue Prüfung, angewandt auf die **erste Zeile** der Nachricht (Zeilenlogik und `LEADING_CHARS = 120` bleiben als äußere Grenze bestehen):

1. **Klammer-Einschübe entfernen.** Text in runden Klammern (auch unvollständig, wenn die Zeile vor `)` endet) gilt als Nebenbemerkung und wird für alle folgenden Schritte ignoriert. Dort steht der Nachsatz des Realfalls "approved (oder kann ich nicht einfach selbst weitermachen?)".
2. **Vorspann.** Führende Zeichen, die weder Buchstabe noch Ziffer sind (Anführungszeichen, `*`, `>`, Emojis), werden ignoriert. Danach darf höchstens EIN Füllwort aus {ja, ok, okay, yes, klar, danke, super, top} vor der Phrase stehen. Eine führende Ziffer ("1.", "1)") wird NICHT ignoriert: ein Listenpunkt einer Diskussion ist keine Freigabe.
3. **Phrase führt.** Danach muss eine Phrase der Liste beginnen (Wortgrenzen-Regel wie bisher). Bei mehreren passenden Phrasen gewinnt die längste ("ich genehmige" vor "genehmige").
4. **Kopfsatz.** Der Text vom Phrasenende bis zum ersten Klauselzeichen (`, . ; : ! ? …`, " - ", " — " oder Zeilenende) darf höchstens **2 Zusatzwörter** enthalten, bei **override 0**. Wörter sind `\w+`-Token (Umlaute zählen mit, Zeichen und Emojis nicht).
5. **Kein Fragezeichen** außerhalb von Klammern in der Zeile.
6. **Keine Negation oder Einschränkung** außerhalb von Klammern in der Zeile: nicht, kein, keine, keinen, not, no, aber, but, warte, wait.

Sichtbarkeit (alle Meldungen gehen wie bisher auf stderr, also an den User):

- **Wirkende Freigabe** nennt den Auslöser: `GREEN approved (durch: '<erste 60 Zeichen der Nachricht>').` Analog bei Spec-Freigabe und Override-Token.
- **Verworfenes Stichwort (kein stilles Verwerfen, #90):** Hätte die bisherige Regel die Nachricht als Freigabe gewertet, die neue nicht, und wäre die Freigabe in der aktuellen Phase relevant (approval: phase3 ohne `spec_approved`; GREEN: phase6/6b ohne `green_approved`; override: immer), erscheint: `Stichwort '<phrase>' erkannt, aber nicht als Freigabe gewertet — eine Freigabe ist eine kurze Nachricht, die mit dem Stichwort beginnt (z. B. 'go' oder 'approved').` Der Hinweis läuft über `deferred_notices` und entfällt, wenn dieselbe Nachricht über das andere Gate gewirkt hat ("go" steht in manchen Projekten in beiden Listen).

## Expected Behavior

- **Input:** Eine echte User-Nachricht (kein Notification-Turn) in einer Phase, in der ein Freigabe-Wort etwas bewirken könnte.
- **Output:** Nur Nachrichten, die selbst eine Freigabe sind, setzen `spec_approved`, `green_approved` bzw. den Override-Token. Erwähnungen, Fragen, Einschränkungen und Listenpunkte einer Diskussion ändern den Workflow-Zustand nicht.
- **Side effects:** Zusätzliche stderr-Zeilen (Auslöser bei Wirkung, Hinweis bei verworfenem Stichwort). Kein Zustandswechsel bei verworfenen Nachrichten.

Beispiele (Freigabe = ja):

| Nachricht | Ergebnis | Grund |
|-----------|----------|-------|
| `go` / `Go.` / `go, passt` / `go!` | Freigabe | Phrase führt, Kopfsatz kurz |
| `ja, go` / `ok, passt` / `Danke, passt so` | Freigabe | ein Füllwort als Vorspann |
| `go bitte umsetzen` / `Passt für mich` | Freigabe | 2 Zusatzwörter erlaubt |
| `approved (oder kann ich nicht einfach selbst weitermachen?)` | Freigabe | Klammer-Nachsatz ignoriert (Realfall aus #46) |
| `1. die mischung aus go, approved und ... ist unglücklich` | keine | Zeile beginnt mit Ziffer, Phrase führt nicht |
| `Passt das so?` / `Approved? Wirklich?` | keine | Fragezeichen |
| `Passt nicht.` / `Go, aber nur für Teil 1` | keine | Negation / Einschränkung |
| `Go check the spec first` | keine | Kopfsatz 4 Wörter |
| `override` | Token | override braucht die Phrase allein |
| `Override?` / `override, bitte erklären` | kein Token | override erlaubt 0 Zusatzwörter |

## Known Limitations

- **Restrisiko bleibt:** Kurze Sätze, die mit einer Phrase beginnen und weder Fragezeichen noch Negation enthalten (z. B. "Go back", "Freigabe fehlt"), gelten weiterhin als Freigabe. Das ist bewusst: strengere Regeln würden natürliche Freigaben ("Passt für mich") verwerfen. Der wirksame Schutz dahinter bleibt: Spec-Freigabe braucht das unabhängige PO-Briefing, der Commit den Adversary-Verdict.
- **Nur die erste Zeile zählt** (unverändert): "Passt" in Zeile 1, Fremdtext darunter, gilt als Freigabe.
- **Zitat-Präfixe** (`"go"`, `> go`) werden durch den Vorspann-Schritt freigegeben. Bewusster Kompromiss.
- **Umlaute** gelten in der Lookaround-Regel der Wortgrenze nicht als Buchstaben (bestehendes Verhalten, nicht Teil dieser Änderung).
- **Verteilung:** Wirkt in Konsumenten-Projekten erst nach dem Plugin-Update; lokale Patches sind wirkungslos.
- **Nicht Teil dieser Spec:** #146 ("halt" als Stop-Phrase) ist eine andere Fehlerklasse (Stop-Lock) und bleibt eigenes Issue.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Die Nachricht aus dem Issue (Diskussion mit "go" und "approved") setzt in phase6 weder `green_approved` noch den Freigabe-Marker.
- [ ] Echte Freigaben ("go", "go, passt", "ja, go", "approved (…)") wirken weiterhin, und die Meldung nennt den Auslöser.
- [ ] Ein verworfenes Stichwort erzeugt einen sichtbaren Hinweis statt stillem Verwerfen.
- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt.
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün).

## Acceptance Criteria

- **AC-1:** Given ein aktiver Workflow in phase6_implement / When der User eine Diskussionsnachricht sendet, die "go" und "approved" mitten im Satz enthält (Wortlaut aus Issue #170) / Then bleibt `green_approved` false und der Marker `user_approved_validation_<workflow>` wird nicht angelegt.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-2:** Given ein Workflow in phase6_implement bzw. phase3_spec / When der User eine echte Freigabe sendet (`go`, `Go.`, `go, passt`, `ja, go`, `ok, passt`, `go bitte umsetzen`, `approved (oder kann ich nicht einfach selbst weitermachen?)`) / Then wirkt die Freigabe wie bisher.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-3:** Given ein Workflow in phase6_implement / When die Nachricht mit einem Freigabe-Wort beginnt, aber eine Frage oder Einschränkung ist (`Passt das so?`, `Approved? Wirklich?`, `Passt nicht.`, `Go, aber nur für Teil 1`, `Go check the spec first`) / Then wird keine Freigabe gesetzt.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-4:** Given eine beliebige Session / When der User `override` allein sendet / Then entsteht der Override-Token; When er `Override?` oder `override, bitte erklären` sendet / Then entsteht kein Token.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-5:** Given ein Workflow in einer Phase, in der die Freigabe relevant wäre / When ein Stichwort erkannt, aber verworfen wird / Then erscheint auf stderr ein Hinweis mit dem Stichwort; When dieselbe Nachricht über das andere Gate regulär wirkt (Phrase "go" in beiden Listen) / Then erscheint kein Hinweis.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-6:** Given eine wirkende GREEN-Freigabe, Spec-Freigabe oder ein neu angelegter Override-Token / When der Hook sie verarbeitet / Then nennt die stderr-Meldung den auslösenden Nachrichtentext (erste 60 Zeichen).
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-7:** Given Stop-Lock-Nachrichten und Notification-Turns / When sie nach der Änderung verarbeitet werden / Then verhalten sie sich unverändert (Stop-Wort mitten im Satz sperrt weiterhin, Notification-Turns werden weiterhin komplett übersprungen), und die bestehende Testsuite bleibt grün.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_phase_listener_go_discussion_170.py` — Unit-Tabelle für `_matches` (AC-1 bis AC-4) plus End-to-End-Läufe des Hooks gegen einen temporären Workflow (AC-1, AC-5, AC-6)
- `pytest tests/test_phase_listener_keyword_guard.py tests/test_phase_listener_dropped_approval_90.py tests/test_phase_listener_agent_handback_141.py` — bestehende Tests als Regressionsschutz (AC-2, AC-7)
- `pytest tests` — Gesamtlauf (AC-7)

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Verschärfung einer bestehenden Prüfung innerhalb einer Funktion, ohne neue Komponente, Schnittstelle oder Konfigurationsoption. Die Abwägung (Satzbau-Regel statt Wortzahl-Grenze oder Rückfrage) ist in dieser Spec und im Kontext-Dokument festgehalten.

## Entscheidungen des Tech Leads (für den PO)

- **Zwei Zusatzwörter statt einem:** natürliche deutsche Freigaben ("Go bitte umsetzen", "Passt für mich") sollen nicht verworfen werden. Fragezeichen und Negationswörter sind ohnehin getrennt gesperrt, das Restrisiko ist dadurch klein.
- **Override strenger als Freigabe:** ein Override-Token entsperrt eine Stunde lang alle Gates, deshalb zählt nur die Phrase allein.
- **Keine Rückfrage "Wirklich freigeben?":** würde jede echte Freigabe verlangsamen (#140); stattdessen sichtbare Meldung bei Wirkung und bei Verwerfung.

## Changelog

- 2026-09-21: Initial spec created
- 2026-09-21: AC-6 um die Override-Meldung ergänzt (Befund aus dem PO-Briefing)
