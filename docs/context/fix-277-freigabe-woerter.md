# Context: fix-277-freigabe-woerter

## Request Summary
Issue #277 (Sammel-Vorgang aus #268 + #175, Epic #200): Die Sperrmeldung des Post-Implementation-Gates
nennt Freigabe-Wörter, die in der Phase nicht wirken (`freigabe`, `approved` in phase6), und
Einschränkungen („go, erst noch die Doku") heben eine Freigabe nicht auf. Beides läuft ohne Rückmeldung.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/phase_listener.py` Z. 32–40 | `APPROVAL_PHRASES` (Spec-Freigabe) und `GREEN_PHRASES = ["go","green ok","tests ok","gruen ok"]` — `approved`/`freigabe` stehen nur in der ersten Liste |
| `core/hooks/phase_listener.py` Z. 71–73, 87–89 | `NEGATION_WORDS` (nicht, kein, aber, warte …) — deckt deutsche Einschränkungen nicht ab (F001/F007) |
| `core/hooks/phase_listener.py` Z. 142–152 | `_leading_line` entfernt Klammer-Einschübe — F002 (Negation in Klammern) ist dadurch gewollt wirkungslos, gehört aber zur Abwägung |
| `core/hooks/phase_listener.py` Z. 169–191 | `_leading_approval_phrase`: Regel „Nachricht IST eine Freigabe" (#170) |
| `core/hooks/phase_listener.py` Z. 203–216 | `_discard_notice`: Rückmeldung nur, wenn Phrase **in der jeweils geprüften Liste** steht — für `approved` in phase6 sucht sie in `green`, findet nichts, schweigt |
| `core/hooks/phase_listener.py` Z. 485–517 | GREEN-Zweig: wirkt nur in phase6_implement/phase6b_adversary; sonst WARNUNG |
| `core/hooks/post_implementation_gate.py` Z. 166, 196 | Sperrmeldungen: „User tippt 'go', 'freigabe' oder 'approved'" — fest verdrahtet |
| `core/hooks/workflow.py` Z. 923–944 | `_not_approved_msg()` nennt dagegen die TATSÄCHLICH konfigurierten Phrasen (#90) — Vorbild für die Lösung |
| `core/hooks/bash_gate.py` Z. 70 | Kommentar nennt dieselben drei Wörter (nur Prosa) |
| `core/hooks/edit_gate.py` Z. 585, 615 | Sperrmeldungen nennen `override` — Phrase steht in `OVERRIDE_PHRASES`, wirkt |
| `config.yaml` Z. 55–81 | Vorlage `approval_phrases` / `green_phrases` (Projekte überschreiben) |
| `core/hooks/config_loader.py` Z. 211, 272 | Default-Liste `approval_phrases`, `get_approval_phrases()` |
| `tests/test_phase_listener_go_discussion_170.py` | Tabellen-Tests der Satzbau-Regel (AC-2/3) — Erweiterungspunkt für die sechs Einschränkungssätze |
| `tests/test_phase_listener_dropped_approval_90.py` | Projekt-Config mit „go" in beiden Sets |
| `tests/test_phase_listener_keyword_guard.py` | Realfall #46 `approved (oder kann ich nicht einfach selbst weitermachen?)` muss weiter freigeben |

## Existing Patterns
- **#90 „Kein stilles Verwerfen":** Wird eine Freigabe verworfen, meldet der Hook das (`deferred_notices`).
- **#90 Meldung aus der Konfiguration:** `_not_approved_msg()` liest die Phrasen aus `config_loader`, statt sie
  zu verdrahten. Die Sperrmeldungen im Post-Implementation-Gate tun das nicht.
- **#170 Satzbau-Regel:** Phrase eröffnet die erste Zeile, ≤2 Zusatzwörter im Kopfsatz, keine Frage, keine
  Negation; Override streng (0 Zusatzwörter).
- **Parametrisierte Tabellentests** je Beispielzeile der Spec (#170).

## Dependencies
- Upstream: `config_loader` (Phrasenlisten), Workflow-JSON (`current_phase`, `green_approved`),
  Lock/Marker (`pending_validation_lock_path`, `approval_marker_path`).
- Downstream: `post_implementation_gate.py` (Marker entsperrt den Edit), alle Konsumenten-Projekte nach
  Plugin-Update. Projekte überschreiben die Phrasenlisten per Config — jede Lösung muss mit
  abweichenden Listen funktionieren.

## Existing Specs
- `docs/context/fix-170-go-freigabe-phrase.md` + Spec/Adversary-Dialog (`docs/artifacts/fix-170-go-freigabe-phrase/adversary-dialog.md`) — Quelle von F001/F002/F004/F005/F007
- `docs/context/fix-134-approval-marker-binding.md` — Marker-Bindung (eigenständig, #134 geschlossen)

## Befund-Stand (Code gelesen, noch NICHT reproduziert — das folgt in /20-analyse)
1. **Befund 1 (#268):** `approved` in phase6: `_matches(message, green)` ist False; im `elif`-Zweig ruft
   `_discard_notice(message, green)` → `_mentioned_phrase` sucht nur in `green` → None → keine Ausgabe.
   Passt zur Issue-Beschreibung (`green_approved=False`, rc=0, keine Ausgabe).
2. **Befund 2 (#175):** `NEGATION_WORDS` enthält keines von erst, später, wenn, noch, war, fehlt, nein, nie,
   niemals, nichts, moment, nö. Aber: der Kopfsatz-Budget-Check (≤2 Zusatzwörter bis zum ersten Komma)
   fängt „go, erst noch die Doku" NICHT, weil das Komma den Kopfsatz beendet — die Negation wird nur
   über `_NEGATION_RE` auf die ganze erste Zeile gefunden.
3. **F005:** Der Verworfen-Hinweis nennt in phase6 „approved" als Beispiel (`_discard_notice`, Z. 215).

## Risks & Considerations
- **Zwei Fehlerrichtungen** (aus #170): zu locker = ungewollte Freigabe; zu streng = echte Freigabe
  verworfen. Wortliste gegen echte Freigaben abwägen („passt", „go, passt", „Passt für mich"): „noch",
  „wenn", „war" können in legitimen Sätzen stehen.
- **`approved` hat je nach Phase zwei Bedeutungen**, falls es in phase6 aufgenommen wird (Spec-Freigabe vs.
  GREEN). Gegenargument aus dem Issue; ist die PO-Entscheidung.
- **Projekt-Configs:** Phrasenlisten sind überschreibbar; die Sperrmeldung darf deshalb nicht fest
  verdrahtet sein (Vorbild #90).
- **Kill-Switch/Config erreicht Main-Repo nicht aus Worktree** (Memory) — betrifft nur Config-Änderungen, nicht Code.
- **core/hooks/ ist Infrastruktur:** `edit_gate.py` verlangt dafür einen Override-Token (User tippt „override").
- **Scoping:** ≤4–5 Dateien, ±250 LoC. Geplant: `phase_listener.py`, `post_implementation_gate.py`, ggf.
  `config.yaml`, 1–2 Testdateien, `CHANGELOG.md`.
- **Plugin-Verteilung:** Fix wirkt in Konsumenten erst nach Update; die hier laufenden Hooks sind 3.34.0
  aus dem Plugin-Cache, nicht aus dem Worktree — Reproduktion muss `core/hooks` des Worktrees direkt
  ansteuern (wie die #170-Tests per `subprocess`).

## Analysis

### Type
Bug (Sammel-Vorgang #277 = #268 + #175), Hook-Logik in `core/hooks/`.

### Recherche (vor Reproduktion)
- Claude-Code-Hooks-Doku (https://code.claude.com/docs/en/hooks): Bei `UserPromptSubmit` mit Exit 0 landet **stdout im Kontext**
  („plain text … Claude can see and act on"); **stderr geht nur ins Debug-Log, „never the transcript, and Claude never sees it"**.
  Sichtbar für den Nutzer ist nur JSON `systemMessage` oder Exit 2 (blockiert den Prompt).
- `_emit_status_note` (phase_listener.py Z. 303ff, 3.25.0) dokumentiert dasselbe selbst und lässt „alle bestehenden Meldungen auf stderr".

### Reproduktion (throwaway-Projekt, echter Hook per subprocess, Skript im Scratchpad `repro277.py`)
phase6_implement, Standard-Config:
| Eingabe | Ergebnis heute |
|---|---|
| `go` | green_approved=True (korrekt) |
| `approved`, `freigabe` | green_approved=False; nur stderr-WARNUNG „wirkt nur in phase3_spec" |
| `Go war falsch`, `go, erst noch die Doku`, `go, wenn Tests grün`, `go, nein`, `go, niemals` | **green_approved=True (Fehler, alle fünf reproduziert)** |
| `Freigabe fehlt noch` | phase6: nur Warnung; phase3_spec: **Spec freigegeben (Fehler)** |
| `approved, erst noch die Doku` / `approved, wenn Tests grün` / `approved, nein` | phase3_spec: **Spec freigegeben (Fehler)** |
| `go (aber nicht jetzt)` | green_approved=True (F002, Klammer wird bewusst ignoriert) |
| `go, passt`, `go bitte umsetzen` | True (soll so bleiben) |
| `Passt für mich` | kein Effekt, keine Meldung — Default-Config von `config_loader` enthält „passt" nicht (Vorlage `config.yaml` schon) |

### Ursachen
1. **Befund 1 (#268):** `post_implementation_gate.py:166,196` nennt fest `go`/`freigabe`/`approved`; `GREEN_PHRASES` kennt nur `go`.
   Gegenüber der Issue-Beschreibung: `approved` in phase6 ist **nicht** völlig still, es gibt eine stderr-WARNUNG — die aber nie jemand sieht (Ursache 3).
2. **Befund 2 (#175):** `NEGATION_WORDS` (phase_listener.py Z. 71) enthält keines der Einschränkungswörter; der Kopfsatz-Check
   endet am Komma, die Einschränkung steht dahinter. Betrifft Spec- UND GREEN-Freigabe.
3. **NEU, Wurzel der „stillen" Wirkungslosigkeit:** Alle `deferred_notices` und auch „GREEN approved"/„Spec approved" gehen auf stderr
   (10 Stellen) → laut Doku weder Nutzer noch Claude sichtbar. Der DoD-Punkt „freigabe-ähnliche Eingabe erzeugt Rückmeldung" ist damit
   mit reinen Wortlisten-Änderungen NICHT erfüllbar.

### Alternativen
- **Regelweg (empfohlen):** Wortlisten erweitern + Meldungstext aus Config generieren (Vorbild `_not_approved_msg`, #90) + Rückmeldungen auf stdout.
  Kein Modell nötig — alles deterministisch.
- Alternative A zu „approved in phase6 aufnehmen": **Sperrmeldung korrigieren, nur `go`** (nennt die konfigurierten `green_phrases`).
  Vorteil: `approved` behält genau eine Bedeutung. Nachteil: PO tippt weiter intuitiv „approved".
- Alternative B zur Wortliste: **Positivliste statt Negationsliste** — nach der Phrase sind nur Füllwörter erlaubt (bitte, passt, danke, umsetzen …);
  alles andere verwirft. Robuster gegen unbekannte Einschränkungen, aber strenger gegen echte Freigaben. Kippt ADR-Teil der #170-Satzbau-Regel (≤2 Zusatzwörter beliebig).
- Alternative C zu stderr: JSON `systemMessage` (Nutzer sieht es direkt) statt stdout (nur Claude sieht es und müsste es weitergeben).

### Affected Files
| File | Change | Description |
|---|---|---|
| core/hooks/phase_listener.py | MODIFY | Einschränkungswörter; Notices auf stdout/systemMessage; Verworfen-Hinweis aus Config |
| core/hooks/post_implementation_gate.py | MODIFY | Sperrmeldung aus `green_phrases` generieren |
| tests/test_phase_listener_restrictions_277.py | CREATE | 6 Einschränkungssätze, echte Freigaben, Meldungstext-gegen-Wortliste-Abgleich, Notice-Kanal |
| tests/test_phase_listener_go_discussion_170.py | MODIFY (ggf.) | Tabelle erweitern |
| CHANGELOG.md | MODIFY | [Unreleased] |
(+ Spec-Prosa #170, F004: docs/specs/fix-170-go-freigabe-phrase.md)

### Scope Assessment
- Files: 5–6 (an der Grenze), ca. +150/−20 LoC, Risk: MITTEL (zentrale Freigabelogik, zwei Fehlerrichtungen; Wirkung auf alle Konsumenten-Projekte).
- Wortwahl: „noch/wenn/war" kommen in echten Freigaben selten vor, aber „go, passt" muss bleiben → Tabellentest mit beiden Richtungen.

### Open Questions (PO)
- [ ] `approved`/`freigabe` in phase6 aufnehmen (Issue-Empfehlung) oder nur Meldung korrigieren (Alternative A)?
- [ ] Rückmeldungen: stdout (Claude sagt es dir) oder systemMessage (direkt in deinem Terminal)? Empfehlung: systemMessage für Verworfen/Warnung.

### PO-Entscheidungen (2026-10-01)
- `approved`/`freigabe` bleiben Spec-Freigabe; in phase6 gilt nur `go` (Alternative A). Sperrmeldung nennt die konfigurierten `green_phrases`.
- Rückmeldungen des Hooks per JSON `systemMessage` (direkt im Terminal sichtbar). #310 wird mit #277 zusammen umgesetzt.
