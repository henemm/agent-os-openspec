---
entity_id: fix-277-freigabe-woerter
type: bugfix
created: 2026-10-01
updated: 2026-10-01
status: draft
version: "1.0"
tags: [phase-listener, approval-gate, green-approval, sperrmeldung, systemMessage, einschraenkungswoerter]
test_targets: ["tests/test_phase_listener_restrictions_277.py"]
---

# Freigabe-Wörter: Sperrmeldung aus Config, Einschränkungen heben auf, Rückmeldung sichtbar (#277, #310)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #277 — Sammel-Vorgang, fasst #268 (Sperrmeldung nennt unwirksame Wörter) und #175 (Einschränkungen heben die Freigabe nicht auf). Dazu #310 (Hook-Rückmeldungen gehen auf stderr und erreichen niemanden), gemeinsam umgesetzt, weil die DoD „Rückmeldung statt stiller Wirkungslosigkeit" ohne #310 nicht erfüllbar ist. Gehört zum Epic #200.

## Purpose

Das Post-Implementation-Gate sagt dem Nutzer „tippe 'go', 'freigabe' oder 'approved'", obwohl in phase6 nur `go` wirkt; der Nutzer folgt der Anweisung und bleibt gesperrt. Umgekehrt setzen Sätze wie „go, erst noch die Doku" oder „Freigabe fehlt noch" eine Freigabe, weil `NEGATION_WORDS` deutsche Einschränkungen nicht kennt. Und alle Rückmeldungen des `phase_listener` (verworfene Freigabe, falsche Phase, „GREEN approved") gehen auf stderr, das laut Hooks-Doku bei `UserPromptSubmit` weder Nutzer noch Claude erreicht — jedes „kein stilles Verwerfen" (#90, #170) ist faktisch still. Diese Spec behebt alle drei Ursachen mit Regeln (Wortliste, Meldungstext aus Config, JSON-Kanal), ohne Modell.

## Source

- **File:** `core/hooks/phase_listener.py` — `NEGATION_WORDS`, `_discard_notice()`, Ausgabe-Pfade in `main()` (`deferred_notices`, `_emit_status_note`)
- **File:** `core/hooks/post_implementation_gate.py` — die beiden Sperrmeldungen („Neue Freigabe noetig …" und „Freigabe — und zwar AUSSCHLIESSLICH durch den User …")
- **Vorbild:** `core/hooks/workflow.py::_not_approved_msg()` (#90) — Meldung aus den tatsächlich konfigurierten Phrasen

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `docs/specs/fix-170-go-freigabe-phrase.md` | Spec (Vorläufer) | Satzbau-Regel; Quelle von F001/F002/F004/F005/F007. Schritt 4 der Implementation Details wird hier an Tabelle/AC-4 angeglichen (F004) |
| `core/hooks/config_loader.py` | Modul | Liefert `workflow.green_phrases` / `approval_phrases` (Projekte überschreiben sie) |
| `core/hooks/workflow.py` | Modul | `status_note()` (Statusvermerk, bisher stdout) und `_not_approved_msg()` (Vorbild) |
| `tests/test_phase_listener_keyword_guard.py` | Test | Realfall #46 `approved (oder kann ich nicht einfach selbst weitermachen?)` muss weiter freigeben |
| `tests/test_phase_listener_dropped_approval_90.py` | Test | Projekt-Config mit „go" in beiden Phrasen-Sets |

## Scope

- **Affected Files:**
  `core/hooks/phase_listener.py` (MODIFY),
  `core/hooks/post_implementation_gate.py` (MODIFY),
  `tests/test_phase_listener_restrictions_277.py` (CREATE),
  `tests/test_phase_listener_go_discussion_170.py` (MODIFY, nur Tabelle bei Bedarf),
  `CHANGELOG.md` (MODIFY, [Unreleased]),
  `docs/specs/fix-170-go-freigabe-phrase.md` (MODIFY, nur Prosa Schritt 4, F004)
- **Estimated Changes:** ca. +90 LoC Produktivcode (davon ca. 40 für den gebündelten Ausgabekanal), ca. +150 LoC Tests, je ein Changelog-Eintrag und ein Prosa-Absatz. Gesamt unter 250 LoC, 6 Dateien (an der Grenze).

## Implementation Details

**1. Sperrmeldung aus der Konfiguration (Befund 1, #268).** Neuer kleiner Helfer in `phase_listener.py`, der die wirksamen GREEN-Phrasen liefert (`_load_phrases()["green"]`, Fallback `GREEN_PHRASES`) und als Text formatiert (`'go'` bzw. `'go', 'green ok', …`). `post_implementation_gate.py` importiert ihn und setzt den Text in beide Sperrmeldungen ein; die fest verdrahtete Aufzählung `'go', 'freigabe' oder 'approved'` entfällt. Vorbild ist `_not_approved_msg()`: kein Wort in der Meldung, das nicht in der tatsächlich wirkenden Liste steht, auch nicht bei abweichender Projekt-Config. `approved`/`freigabe` bleiben ausschließlich Spec-Freigabe (phase3_spec).

**2. Einschränkungswörter (Befund 2, #175).** `NEGATION_WORDS` wird um erst, später, spaeter, wenn, noch, war, fehlt, nein, nie, niemals, nichts, moment, nö erweitert. `_NEGATION_RE` prüft die ganze erste Zeile (ohne Klammer-Einschübe), also greift die Erweiterung automatisch für Spec-Freigabe (approval), GREEN und Override, weil alle über `_leading_approval_phrase` laufen. Ein Satz mit einem dieser Wörter ist keine Freigabe. Wortgrenzen-Regel wie bisher (`erste`, `nochmal`, `warum` treffen nicht).

**3. Rückmeldungen sichtbar (#310).** Alle bisherigen stderr-Meldungen des `phase_listener` (Override-Token, „Spec approved", „GREEN approved", „Freigabe blockiert", `deferred_notices`: verworfenes Stichwort, falsche Phase, „bereits freigegeben", „kein auflösbarer Workflow") werden in einer Liste gesammelt und am Ende des Hook-Laufs **einmal** ausgegeben. Format: ein einziges JSON-Objekt auf stdout:

```
{"systemMessage": "<Meldungen, durch Zeilenumbruch getrennt>",
 "hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                        "additionalContext": "<Statusvermerk aus _emit_status_note, falls vorhanden>"}}
```

Zusammenspiel mit `_emit_status_note` (bisher `print(note)` direkt auf stdout): stdout darf pro Hook-Lauf entweder reiner Text oder ein JSON-Objekt sein, nicht beides. Deshalb liefert `_emit_status_note` den Vermerk künftig zurück statt ihn zu drucken, und ein gemeinsamer Ausgabeschritt entscheidet: gibt es **keine** Meldungen, bleibt es beim reinen Text (Verhalten wie 3.25.0, bestehende Tests unverändert); gibt es Meldungen, geht alles in das eine JSON-Objekt (Statusvermerk als `additionalContext`, damit Claude ihn weiter sieht). Der Ausgabeschritt läuft an **allen** Austrittspunkten von `main()` (Stop-Lock-Exit, Exit ohne Workflow, Notification-Turn, Hauptende). Notification-Turns erzeugen keine Meldungen, dort bleibt nur der Statusvermerk als reiner Text. Der stderr-Spiegel der Meldungen bleibt als Debug-Hilfe unverändert bestehen (bestehende Tests lesen stderr).

**4. Verworfen-Hinweis aus der Konfiguration (F005).** `_discard_notice` bekommt die Beispielphrase als Parameter: in phase6/6b die erste konfigurierte GREEN-Phrase, in phase3 die erste konfigurierte Approval-Phrase, beim Override die erste Override-Phrase. Der fest verdrahtete Satz `(z. B. "go" oder "approved")` entfällt. Ebenso nennt die Falsche-Phase-Warnung („wirkt nur in phase3_spec") bei einem Approval-Wort in phase6 zusätzlich die konfigurierte GREEN-Phrase („in phase6 gilt: 'go'"), damit der Nutzer erfährt, was stattdessen wirkt.

**5. Rückmeldung für freigabe-ähnliche, nicht erkannte Eingabe.** Jede Eingabe mit Freigabe-Stichwort in der ersten Zeile, die keinen Zustand ändert (Einschränkung, Frage, falsche Phase), erzeugt über den Kanal aus Punkt 3 eine sichtbare Meldung mit dem Stichwort. Die Sätze mit den neuen Einschränkungswörtern fallen automatisch unter den bestehenden Verworfen-Hinweis, weil `_mentioned_phrase` die Phrase findet, `_leading_approval_phrase` sie aber verwirft.

**6. F004 (Spec #170).** Schritt 4 der Implementation Details in `fix-170-go-freigabe-phrase.md` wird so umformuliert, wie Tabelle und AC-4 es beschreiben und der Code es tut: der Kopfsatz (Phrase bis zum ersten Klauselzeichen) darf höchstens 2 Zusatzwörter enthalten; bei Override gilt, dass die Phrase allein steht (kein Zusatzwort bis Zeilenende).

**Alternativen (Regelweg vorn):**

- **Gewählt:** Negationsliste erweitern (Regel, deterministisch). Behält die #170-Satzbau-Regel (≤ 2 Zusatzwörter im Kopfsatz) unverändert und trifft echte Freigaben nicht.
- **Alternative B, Positivliste statt Negationsliste:** nach der Phrase wären nur Füllwörter erlaubt (bitte, passt, danke, umsetzen …), alles andere verwirft. Robuster gegen unbekannte Einschränkungen, aber **verworfen**: sie kippt die Satzbau-Regel aus #170 („≤ 2 beliebige Zusatzwörter") und ist strenger gegen echte Freigaben („go, dann mal los", „Passt für mich"). Die Listenpflege der Positivliste wäre ein neuer Dauerbrenner (zu streng = echte Freigabe verworfen).
- **Alternative A zu Befund 1, `approved` in phase6 aufnehmen:** verworfen (PO-Entscheidung), weil `approved` sonst je nach Phase zwei Bedeutungen hätte.
- **Alternative C zum Kanal, stdout-Text statt systemMessage:** Claude würde es sehen, der Nutzer nicht zuverlässig. Verworfen (PO-Entscheidung: direkt im Terminal sichtbar).
- **Kein Modell:** Alle drei Probleme sind Wortlisten und Textformatierung. Ohne Modell geht es, weil die Nulllinie die Regel ist: die sechs Beispielsätze aus dem Issue sind durch genau diese Wörter eindeutig getrennt von den echten Freigaben.

## Expected Behavior

- **Input:** Eine echte User-Nachricht (kein Notification-Turn) in einer beliebigen Phase; ein Edit, den das Post-Implementation-Gate sperrt.
- **Output:** Nur Nachrichten, die selbst eine Freigabe sind und kein Einschränkungswort enthalten, setzen `spec_approved`, `green_approved` bzw. den Override-Token. Jede Sperrmeldung nennt nur Wörter, die in der Phase tatsächlich wirken. Jede Meldung des Hooks erscheint dem Nutzer als `systemMessage`.
- **Side effects:** stdout enthält bei Meldungen ein einziges JSON-Objekt statt reinem Text; Statusvermerk wandert dann in `additionalContext`. Kein Zustandswechsel bei verworfenen Nachrichten.

Beispiele (Standard-Config, phase6_implement bzw. phase3_spec):

| Nachricht | Phase | Ergebnis |
|-----------|-------|----------|
| `go` / `go, passt` / `go bitte umsetzen` | phase6 | GREEN-Freigabe |
| `approved (oder kann ich nicht einfach selbst weitermachen?)` | phase3 | Spec-Freigabe (Realfall #46) |
| `Passt für mich` (Projekt-Config mit „passt") | phase3 | Spec-Freigabe |
| `Go war falsch` / `go, erst noch die Doku` / `go, wenn Tests grün` / `go, nein` / `go, niemals` | phase6 | keine Freigabe, Hinweis sichtbar |
| `Freigabe fehlt noch` / `approved, erst noch die Doku` | phase3 | keine Freigabe, Hinweis sichtbar |
| `approved` / `freigabe` | phase6 | keine GREEN-Freigabe, Warnung nennt `go` |

## Known Limitations

- **F002 bleibt bewusst wirkungslos:** Negation in Klammern (`go (aber nicht jetzt)`, `override (danach weiter)`) wird weiter ignoriert. Klammern gelten als Nebenbemerkung — dieselbe Regel lässt den Realfall `approved (oder kann ich nicht einfach selbst weitermachen?)` (#46) wirken. Eine Änderung würde echte Freigaben verwerfen. Nicht-Ziel dieser Spec.
- **Wortliste ist endlich:** Eine Einschränkung mit einem nicht gelisteten Wort setzt weiter eine Freigabe, solange der Satz kurz ist. Der wirksame Schutz dahinter bleibt: Spec-Freigabe braucht das unabhängige PO-Briefing, der Commit den Adversary-Verdict.
- **Echte Freigaben mit Listenwort** („go, noch heute?" ist ohnehin Frage; „go, das war gut") werden verworfen — dafür gibt es jetzt die sichtbare Meldung, der Nutzer sagt es dann ohne das Wort erneut.
- **Verteilung:** wirkt in Konsumenten-Projekten erst nach dem Plugin-Update.
- **Default-Config enthält „passt" nicht** (nur die Vorlage `config.yaml`): bleibt unverändert, nicht Teil dieser Spec.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Jedes Wort, das eine Sperrmeldung des Post-Implementation-Gates nennt, steht in der Liste, die in dieser Phase wirkt — maschinell durch einen Abgleichtest belegt, auch bei abweichender Projekt-Config
- [ ] Die sechs Einschränkungssätze aus F001/F007 setzen weder Spec- noch GREEN-Freigabe; `go`, `go, passt`, `go bitte umsetzen`, `Passt für mich` (Projekt-Config) und `approved (oder kann ich nicht einfach selbst weitermachen?)` wirken weiter
- [ ] Eine nicht erkannte, aber freigabe-ähnliche Eingabe erzeugt eine für den Nutzer sichtbare Rückmeldung (`systemMessage`), und der Hook gibt pro Lauf genau ein JSON-Objekt aus
- [ ] Der Verworfen-Hinweis in phase6 nennt die konfigurierte GREEN-Phrase, nicht `approved`
- [ ] Spec-Prosa zu #170 (Schritt 4) stimmt mit Tabelle/AC-4 überein
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given ein Post-Implementation-Gate in phase6 mit Standard-Config / When ein Edit gesperrt wird / Then nennt die Sperrmeldung `'go'` und weder `freigabe` noch `approved`.
  - Test: tests/test_phase_listener_restrictions_277.py::test_sperrmeldung_nennt_nur_green_phrasen
- **AC-2:** Given ein Projekt mit abweichender `green_phrases`-Liste (z. B. `["los", "go"]`) / When das Gate sperrt / Then stehen genau diese Phrasen in der Sperrmeldung.
  - Test: tests/test_phase_listener_restrictions_277.py::test_sperrmeldung_folgt_projekt_config
- **AC-3:** Given beliebige Config / When jede Phrase aus den Sperrmeldungen des Gates extrahiert und als Nachricht in phase6 an den Hook gesendet wird / Then setzt jede `green_approved` (maschineller Abgleich Meldungstext gegen wirkende Wortliste, beide Gate-Meldungen).
  - Test: tests/test_phase_listener_restrictions_277.py::test_jede_genannte_phrase_wirkt_in_phase6
- **AC-4:** Given ein Workflow in phase6_implement / When der User `Go war falsch`, `go, erst noch die Doku`, `go, wenn Tests grün`, `go, nein` oder `go, niemals` sendet / Then bleibt `green_approved` false und kein Freigabe-Marker entsteht.
  - Test: tests/test_phase_listener_restrictions_277.py::test_einschraenkungssaetze_setzen_keine_green_freigabe
- **AC-5:** Given ein Workflow in phase3_spec / When der User `Freigabe fehlt noch`, `approved, erst noch die Doku`, `approved, wenn Tests grün` oder `approved, nein` sendet / Then bleibt `spec_approved` false und die Phase phase3_spec.
  - Test: tests/test_phase_listener_restrictions_277.py::test_einschraenkungssaetze_setzen_keine_spec_freigabe
- **AC-6:** Given Workflows in phase6 bzw. phase3 / When der User eine echte Freigabe sendet (`go`, `go, passt`, `go bitte umsetzen`, `approved (oder kann ich nicht einfach selbst weitermachen?)`, `Passt für mich` mit Projekt-Config, die „passt" enthält) / Then wirkt sie wie bisher.
  - Test: tests/test_phase_listener_restrictions_277.py::test_echte_freigaben_wirken_weiter
- **AC-7:** Given die Wortliste / When Sätze mit Wörtern gesendet werden, die nur Teil eines Listenworts sind (`go, erste Version`, `go, nochmal bitte`) / Then gilt die Wortgrenzen-Regel und die Freigabe wirkt weiter.
  - Test: tests/test_phase_listener_restrictions_277.py::test_listenwort_als_wortteil_hebt_nicht_auf
- **AC-8:** Given `go (aber nicht jetzt)` in phase6 / When der Hook läuft / Then wirkt die Freigabe weiterhin (F002 bewusst dokumentiert, Klammern bleiben Nebenbemerkung).
  - Test: tests/test_phase_listener_restrictions_277.py::test_negation_in_klammern_bleibt_wirkungslos
- **AC-9:** Given ein verworfenes oder phasenfremdes Freigabe-Stichwort (`go, nein` in phase6; `approved` in phase6) / When der Hook läuft / Then enthält stdout genau ein JSON-Objekt, dessen `systemMessage` das Stichwort nennt; stderr bleibt als Spiegel gefüllt.
  - Test: tests/test_phase_listener_restrictions_277.py::test_meldung_als_systemmessage_ein_json_objekt
- **AC-10:** Given ein Workflow mit Statusvermerk und gleichzeitig einer Meldung / When der Hook läuft / Then ist stdout ein einziges parsbares JSON-Objekt, der Statusvermerk steht in `additionalContext`; Given keine Meldung / Then bleibt stdout der reine Statusvermerk wie bisher.
  - Test: tests/test_phase_listener_restrictions_277.py::test_status_note_und_meldung_ein_objekt
- **AC-11:** Given ein Stop-Lock-Satz bzw. ein Lauf ohne Workflow, der eine Meldung erzeugt / When der Hook den frühen Austrittspunkt nimmt / Then erscheint die Meldung ebenfalls als einziges JSON-Objekt.
  - Test: tests/test_phase_listener_restrictions_277.py::test_fruehe_austrittspunkte_nutzen_denselben_kanal
- **AC-12:** Given `go, nein` in phase6 mit Standard-Config / When der Verworfen-Hinweis erscheint / Then nennt er die konfigurierte GREEN-Phrase `go` als Beispiel und nicht `approved`; bei abweichender Config die dortige Phrase.
  - Test: tests/test_phase_listener_restrictions_277.py::test_verworfen_hinweis_nennt_konfigurierte_phrase
- **AC-13:** Given Notification-Turns und Stop-Lock-Nachrichten / When sie nach der Änderung verarbeitet werden / Then verhalten sie sich unverändert (Notification-Turn überspringt Keyword-Erkennung, Statusvermerk bleibt reiner Text), und die bestehenden Testdateien `test_phase_listener_go_discussion_170.py`, `test_phase_listener_keyword_guard.py`, `test_phase_listener_dropped_approval_90.py` bleiben grün.
  - Test: tests/test_phase_listener_restrictions_277.py::test_notification_turn_unveraendert
- **AC-14:** Given die Spec #170 / When sie gelesen wird / Then widerspricht Schritt 4 weder Tabelle noch AC-4 (Kopfsatz ≤ 2 Zusatzwörter; Override: Phrase allein).
  - Test: tests/test_phase_listener_restrictions_277.py::test_spec_170_schritt4_passt_zur_tabelle

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden). Die Tests steuern `core/hooks` des Worktrees per `subprocess` an (Muster der #170-Tests), nicht die installierte Plugin-Fassung:

- `pytest tests/test_phase_listener_restrictions_277.py` — AC-1 bis AC-14: Tabellenfälle für beide Fehlerrichtungen (zu locker: Einschränkungssätze; zu streng: echte Freigaben), Sperrmeldungs-Abgleich gegen Wortlisten (Standard- und Projekt-Config), JSON-Kanal an allen Austrittspunkten
- `pytest tests/test_phase_listener_go_discussion_170.py tests/test_phase_listener_keyword_guard.py tests/test_phase_listener_dropped_approval_90.py tests/test_phase_listener_agent_handback_141.py` — bestehende Tests als Regressionsschutz (AC-13)
- `pytest tests` — Gesamtlauf

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Erweiterung bestehender Wortlisten, Meldungstext aus bestehender Konfiguration (Muster #90) und ein gebündelter Ausgabeschritt innerhalb eines bestehenden Hooks. Keine neue Komponente, Konfigurationsoption oder Schnittstelle. Die Abwägung (Negationsliste gegen Positivliste, systemMessage gegen stdout-Text, `approved` in phase6 gegen Meldung korrigieren) steht oben unter „Alternativen" und im Kontext-Dokument.

## Entscheidungen des Tech Leads (für den PO)

- **Rückmeldung zusätzlich als stderr-Spiegel:** die Meldungen bleiben im Debug-Log, damit bestehende Tests und die Fehlersuche unverändert funktionieren; neu ist nur, dass der Nutzer sie sieht.
- **Ein JSON-Objekt, nicht zwei Ausgaben:** der Statusvermerk wandert bei Meldungen in `additionalContext`, damit Claude ihn weiterhin im Kontext hat; ohne Meldung ändert sich nichts.
- **Einschränkungswörter gelten für alle drei Freigabearten** (Spec, GREEN, Override), weil sie über dieselbe Prüfung laufen; ein zweiter Wortlistenpfad wäre mehr Code für denselben Zweck.

## Changelog

- 2026-10-01: Initial spec created
