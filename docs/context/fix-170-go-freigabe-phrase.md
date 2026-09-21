# Context: fix-170-go-freigabe-phrase

## Request Summary
Issue #170: `phase_listener.py` wertet ein beiläufiges „go“ (oder „approved“, „passt“ …) in einer
Diskussionsnachricht als Freigabe. Beobachtet am 2026-09-21: Nachricht „1. die mischung aus **go**,
approved und der eingabe von slash-commands ist unglücklich …“ setzte `green_approved = True` und
den Marker `user_approved_validation_<workflow>`, obwohl der User nichts freigeben wollte.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/phase_listener.py` | `_matches(..., leading_only=True)` (Z. 100–120), `LEADING_CHARS = 120` (Z. 63); Aufrufer für override (Z. 246), approval (Z. 280), GREEN (Z. 345), Warn-Zweig ohne Workflow (Z. 261) |
| `core/hooks/config_loader.py` | Default-Listen `approval_phrases` (Z. 211); `get_approval_phrases()` |
| `config.yaml` (Z. 55–76) | Vorlage für `approval_phrases` / `green_phrases`; Projekte überschreiben die Listen |
| `core/hooks/workflow.py` (Z. 892–905) | Fehlermeldung nennt die konfigurierten Freigabe-Wörter (#90) — muss zur neuen Regel passen |
| `tests/test_phase_listener_keyword_guard.py` | Bestehende Unit-Tests für `_matches` (#46). Enthält Realfall-Test, der erhalten bleiben muss |
| `tests/test_phase_listener_dropped_approval_90.py` | Projekt-Config, in der „go“ zugleich Freigabe- und GREEN-Phrase ist |
| `core/hooks/post_implementation_gate.py` | Wird durch den Marker `user_approved_validation_<wf>` entsperrt — hier liegt der Schaden bei Fehlalarm |

## Existing Patterns
- **Schutz-Schichten in `phase_listener.py`:** (1) `NOTIFICATION_MARKERS` (#46/#141) überspringen
  harness-injizierte Turns komplett; (2) `leading_only` = erste Zeile und erste 120 Zeichen.
  #170 ist die Lücke zwischen beiden: echter User-Text, der das Wort nur *erwähnt*.
- **Fehlalarm-Reparaturen dieser Art:** #46 (Benachrichtigungen), #141 (Stop-Lock durch zitierte
  Wörter). Beide: Regel verschärfen + Regressionstests mit Realfall.
- **Kein stilles Verwerfen (#90):** Wird eine Freigabe verworfen, muss das gemeldet werden
  (`deferred_notices`). Gilt sinngemäß für jede neue Verschärfung.
- Stop-Lock-Phrasen bleiben bewusst großzügig (Not-Aus). Nur approval/GREEN/override sind `leading_only`.

## Dependencies
- Upstream: `re`, `config_loader` (Phrasenlisten), Workflow-JSON (`current_phase`, `spec_approved`,
  `green_approved`).
- Downstream: `post_implementation_gate.py` (Marker), `bash_gate.py` (Commit-Gate: Adversary-Verdict),
  `edit_gate.py` (Phase-Checks). Alle Konsumenten-Projekte, sobald das Plugin aktualisiert wird.

## Existing Specs
- `docs/specs/fast/fix-141-stop-lock-false-positive.md` — gleiche Fehlerklasse, Format-Vorbild
- `docs/specs/fast/fix-46-notification-keyword-bypass.md`

## Risks & Considerations
- **Bestehender Test darf nicht brechen:** `"approved (oder kann ich nicht einfach selbst weitermachen?)"`
  muss weiterhin freigeben (10 Wörter). Eine reine Wortzahl-Grenze wie „≤ 3 Wörter“ aus dem Issue
  würde diese echte Freigabe verwerfen. Regel muss die *Position* (Phrase führt die Nachricht) und
  den *Satzbau* (Phrase steht für sich, ist nicht Objekt/Teil eines Satzes) prüfen.
- **Beide Fehlerrichtungen kosten:** zu locker = ungewollte Freigabe (Selbstzertifizierungs-Schutz,
  #147); zu streng = echte Freigabe wird verworfen und der PO muss wiederholen. #90-Warnung
  macht die strenge Richtung sichtbar, die lockere nicht — deshalb im Zweifel streng + melden.
- **Mehrdeutige Phrasen:** „go“, „passt“, „freigabe“ sind normale deutsche/englische Wörter.
  Projekte konfigurieren eigene Listen (im Fundprojekt ist „go“ Freigabe- UND GREEN-Phrase).
- **Sichtbarkeit (Issue-Vorschlag 2):** Wirkende Stichworte mit dem auslösenden Text melden.
- **Verteilung:** Der Fix wirkt in Konsumenten-Projekten erst nach Plugin-Update (lokale Patches
  wirkungslos, siehe 3.4.x-Rollout). Hier laufen noch Hooks der Plugin-Version 3.22.1.
- **Hilfs-Befund:** `secrets_guard` blockiert das Lesen von `tests/test_phase_listener_keyword_guard.py`
  per Dateiname (Issue #145) — Tests dort nur über Grep-Kontext ansehen.
- Core-Hook-Änderung: `edit_gate.py` verlangt für `core/hooks/` einen Override-Token (User tippt „override“).

## Analysis

### Type
Bug (Fehlalarm im Freigabe-Gate; Fehlerklasse wie #46/#141).

### Root Cause
`_matches(..., leading_only=True)` fragt "steht die Phrase irgendwo in Zeile 1 / den ersten 120 Zeichen?".
Das ist eine *Positions*-Prüfung, keine *Absichts*-Prüfung. Eine Diskussion über das Wort „go" steht
ebenfalls in den ersten 120 Zeichen. Die Wortgrenzen-Regex verhindert nur Teilwort-Treffer ("gogo"), nicht
Erwähnungen als eigenes Wort.

### Lösungsansätze
| Ansatz | Bewertung |
|--------|-----------|
| A. Wortzahl-Grenze (≤ 3 Wörter, Vorschlag im Issue) | Verwirft die echte Freigabe "approved (oder kann ich nicht einfach selbst weitermachen?)" (Realfall-Test #46). Zu grob. |
| B. **Phrase muss die Nachricht eröffnen + kurzer Kopfsatz** | Trennt "go, passt" (Freigabe) von "die mischung aus go, approved …" (Diskussion) über Position UND Satzbau. Realfall-Test bleibt grün. **Gewählt.** |
| C. Nachricht muss exakt die Phrase sein | Sicherste Variante, aber verwirft "go, danke" / "approved (…)" — der PO müsste Freigaben künstlich verkürzen. |
| D. Rückfrage "Wirklich freigeben?" | Reibung; widerspricht #140 (Gates nur bei echter Entscheidung). |

### Technical Approach (B)
1. `_matches` mit `leading_only=True` prüft strenger:
   - Nachricht bereinigen: führende Nicht-Buchstaben/Ziffern-Zeichen (Anführungszeichen, `*`, `>`, Emojis) ignorieren.
   - Die Phrase muss **am Anfang** der (bereinigten) ersten Zeile stehen (bisherige Wortgrenzen-Regel bleibt).
   - **Kopfsatz:** der Text zwischen Phrasenende und dem ersten Satz-/Klauselzeichen (`, . ; : ! ? ( ) —` oder Zeilenende) darf höchstens **1 Zusatzwort** enthalten ("go ahead", "passt so", "approved danke" ja; "Passt das so?", "go through the spec" nein).
2. **Kein stilles Verwerfen (#90):** Trifft die *alte* Regel, die neue aber nicht, und die Phase wäre relevant
   (approval in phase3 ohne spec_approved; GREEN in phase6/6b ohne green_approved), kommt ein Hinweis:
   "Stichwort 'go' erkannt, aber nicht als Freigabe gewertet — eine Freigabe beginnt die Nachricht."
3. **Sichtbarkeit (Issue-Vorschlag 2):** Wirkende GREEN-/Spec-Freigabe meldet den auslösenden Text:
   `GREEN approved (durch: 'go, passt').`
4. Gilt für approval, GREEN und override (dieselbe Funktion). Stop-/Continue-Phrasen bleiben unverändert (Not-Aus).
5. `LEADING_CHARS` bleibt als Konstante (Test referenziert sie) — als zusätzliche Obergrenze der Zeile.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/phase_listener.py` | MODIFY | strengere `_matches`-Regel, Near-Miss-Hinweis, Auslöser in Meldungen (~+40 LoC) |
| `tests/test_phase_listener_go_discussion_170.py` | CREATE | Regressionstests (Issue-Zitat, echte Freigaben, Near-Miss-Hinweis, End-to-End) |
| `CHANGELOG.md` | MODIFY | Eintrag unter [Unreleased] |
| `config.yaml` | MODIFY (Kommentar) | Regel bei den Phrasenlisten dokumentieren |

### Scope Assessment
- Files: 4, Estimated LoC: ca. +40 Produktiv, ca. +110 Tests
- Risk Level: HIGH (Freigabe-Gate) — daher Full Process, Adversary-Lauf.

### Dependencies
Keine neuen. Bestehende Tests, die Nachrichten mit Phrase NICHT am Anfang senden, müssen im TDD-Schritt
geprüft werden (Regression-Risiko, z. B. "ja, approved").

### Open Questions
- [x] Nachsatz-Grenze: 2 Zusatzwörter (in der Revision von 1 erhöht: natürliche Freigaben wie "Go bitte umsetzen") (Entscheidung Tech Lead, in Spec unter "Wo ich für dich entschieden habe").
- [x] Challenger-Lauf erfolgt (siehe Revision unten). Keine offenen Fragen an den PO.

### Revision nach Analysis-Challenger (Ansatz B, geschärft)
Der Challenger hat belegt: die erste Fassung ließ "Passt das?", "Approved? Wirklich?", "Override?" und
"Passt, aber warte noch" durch und verwarf dagegen "ja, go" / "ok, passt" (häufigste echte Freigaben).
Übernommen — die Regel für `leading_only`, angewandt auf die erste Zeile **ohne Klammer-Einschübe**
(`( … )`, auch unvollständig; dort steht der Realfall-Nachsatz):
1. **Vorspann:** höchstens EIN Füllwort aus {ja, ok, okay, yes, klar, danke, super, top} darf vor der Phrase stehen.
2. **Phrase führt:** danach beginnt die Phrase (längste passende Phrase gewinnt: "ich genehmige" vor "genehmige").
3. **Kopfsatz:** Text von Phrasenende bis zum ersten Klauselzeichen (`, . ; : ! ? — …`, " - ", Zeilenende):
   höchstens 2 Zusatzwörter (approval/GREEN; Tech-Lead-Entscheidung, siehe Spec), **0 Zusatzwörter bei override**. Wörter = `\w+`-Token (Umlaute,
   Emojis/Zeichen zählen nicht).
4. **Kein Fragezeichen** außerhalb von Klammern in der Zeile ("Passt das?", "Approved? Wirklich?" → keine Freigabe).
5. **Keine Negation/Einschränkung** außerhalb von Klammern: nicht, kein/keine/keinen, not, no, aber, but, warte, wait.
6. Führende Nicht-Alphanumerik (Anführungszeichen, `*`, `>`, Emoji) wird ignoriert; eine führende Ziffer NICHT
   ("1. …" und "1) passt" bleiben verworfen — bewusst: Listenpunkte einer Diskussion sind keine Freigabe).
7. Near-Miss-Hinweis läuft über `deferred_notices` und wird bei `approval_took_effect or green_took_effect`
   unterdrückt ("go" ist in manchen Projekten in beiden Listen). Für override (kennt kein `deferred_notices`)
   eigener Hinweis. Hinweise gehen auf stderr (sichtbar für den User).
Bewusst unverändert: nur Zeile 1 zählt ("Passt\n<Fremdtext>" bleibt Freigabe); Zitat-Präfixe werden gestrippt.
