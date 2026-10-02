# Adversary-Dialog fix-277-freigabe-woerter (Runde 1 + Runde 2)

Spec: docs/specs/fix-277-freigabe-woerter.md (AC-1..AC-14). Geänderte Code-Dateien: core/hooks/phase_listener.py, core/hooks/post_implementation_gate.py, core/hooks/bash_gate.py.
Alle Proben liefen als echte Subprozesse gegen `core/hooks` des Worktrees in Wegwerf-Projekten im Scratchpad.

## Dialog

### Runde 1 (Zusammenfassung)

Ergebnis Runde 1: AMBIGUOUS. 41 Einzelnachrichten durch phase_listener.py, Gate-Läufe, Austrittspunkte.

| ID | Sev | Kategorie | Befund | Stand |
|---|---|---|---|---|
| F001 | MEDIUM | edge_case | Einschränkung erst in Zeile 2 einer mehrzeiligen Nachricht wirkt nicht (Altverhalten) | ausgelagert: Issue #311, zählt nicht |
| F002 | MEDIUM | spec_violation | bash_gate-Marker-Sperrmeldung nannte 'go'/'freigabe'/'approved' | behoben, Runde 2 bestätigt |
| F003 | LOW | anti_pattern | Stop-Lock-Bestätigung bleibt stderr | akzeptiert (Test verlangt leere Ausgabe) |
| F004 | MEDIUM | edge_case | SystemExit beim Import in `_green_text` hätte das Gate geöffnet | behoben, Runde 2 bestätigt |
| F005 | LOW | edge_case | `green_phrases_text()` bei leerer/nicht-listenförmiger Config | behoben, Runde 2 bestätigt |
| F006 | LOW | anti_pattern | Prosa Spec #170 Schritt 6 nennt alte Negationsliste | Folge, Issue #311 |

Runde-1-Nachweise: AC-1..3 Gate-Läufe rc 2 mit Config-Phrasen; AC-4 17 Einschränkungsvarianten verworfen; AC-5 'approved, erst noch die Doku', 'Freigabe fehlt noch', 'approved, wenn' verworfen; AC-6 go/Go/GO/go, passt/go bitte/go, danke/approved, danke wirken; AC-7 Wortgrenzen; AC-8 Klammer; AC-9 ein JSON-Objekt mit Stichwort in systemMessage; AC-10 additionalContext; AC-11 Stop-Lock/ohne Workflow ein JSON-Objekt; AC-12 Hinweis nennt konfigurierte Phrase; AC-13 Notification-Turn unverändert; AC-14 Spec #170 Schritt 4 passt. Hooks-Doku (code.claude.com/docs/en/hooks.md) bestätigt systemMessage und hookSpecificOutput.additionalContext für UserPromptSubmit. Vollsuite 1636 passed.

### Runde 2 (neue echte Läufe)

**Fix F002, bash_gate Marker-Sperre.** `touch .claude/<Marker>` und `cd .claude && echo 1 > <Marker>` liefern rc 2. Die Meldung lautet "WARTE auf seine ausdrueckliche Freigabe. Der phase_listener-Hook setzt den Marker dann selbst." Keine zu tippenden Wörter mehr.
Code reference: core/hooks/bash_gate.py:686

**Fix F004, Gate-Fallback.** Hooks-Kopie mit SystemExit beim Import von phase_listener: post_implementation_gate.py liefert rc 2 mit "Der User tippt 'go'." Das Gate bleibt zu.
Code reference: core/hooks/post_implementation_gate.py:79

**Fix F005, leere Config.** `green_phrases: []`, `green_phrases: foo`, `green_phrases:` (None): rc 2 und "Der User tippt 'go', 'green ok', 'tests ok', 'gruen ok'." Nie "tippt .".
Code reference: core/hooks/phase_listener.py:122

**Seiteneffekte der Bash-Gate-Änderung.** Der Diff von bash_gate.py ist 2 Zeilen, nur Text von `_marker_block_msg`; dieselbe Variable an den zwei `block()`-Stellen, Logik unverändert. Grep über core/, skills/, templates/, tests/, modules/, README: kein Test und keine Doku referenziert den alten Meldungstext; nur der Kommentar bash_gate.py:70 (F008).

**Stichproben (neu):** `go, aber vorher noch den Test fixen`, `go sobald die CI gruen ist`, `approved, nur noch die Reihenfolge klaeren`, `approved sofern Tests laufen`, `approved, aber Spec B fehlt noch` verworfen; `go, perfekt`, `Go! Weiter so`, `approved, super` wirken; `approved` in phase6 liefert WARNUNG mit den wirkenden Phrasen; `go`/`approved` ohne Workflow ein JSON-Objekt mit WARNUNG; Stop-Lock rc 0, stdout leer.
Zusatzprobe Negationsliste: `go, solange nichts bricht` und `go, aber Doku` False; `go, falls ok`, `go, sobald CI gruen`, `go, bevor Doku`, `go, unless red` True (F007).

**Suite:** `tests/test_phase_listener_*.py tests/test_status_note_325.py` 118 passed, 0 failed. Vollsuite nach den Fixes: 1638 passed, 25 skipped, 0 failed.

## Findings Runde 2

Finding:
  ID: F007
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/phase_listener.py:70
  Description: NEGATION_WORDS ist endlich. "falls", "sobald", "bevor", "unless" fehlen, `go, falls Henning zustimmt` setzt green_approved.
  Spec requirement: AC-4/AC-5 nennen konkrete Sätze; die Spec wählt ausdrücklich die erweiterbare Negationsliste (Alternative B verworfen, Known Limitations "Wortliste ist endlich").
  Conflict: Keine AC verletzt, Restlücke der benannten Designentscheidung.
  Remediation: Folge-Issue #311.

Finding:
  ID: F008
  Severity: LOW
  Category: anti_pattern
  Code reference: core/hooks/bash_gate.py:70
  Description: Kommentar nennt noch "go"/"freigabe"/"approved"; kein Laufzeiteffekt.
  Spec requirement: sinngemäß AC-1..3
  Conflict: Kosmetisch.
  Remediation: Kommentar kürzen, optional.

## Confirmations

Confirmation:
  AC: AC-1
  Code reference: core/hooks/post_implementation_gate.py:79
  Evidence: `_green_text()` liefert Config-Phrasen; Gate sperrt rc 2, "tippt 'go'", ohne freigabe/approved.
  Status: CONFIRMED

Confirmation:
  AC: AC-2
  Code reference: core/hooks/phase_listener.py:122
  Evidence: `green_phrases_text()` liest workflow.green_phrases; mit ["los","go"] stehen genau diese Phrasen in der Meldung.
  Status: CONFIRMED

Confirmation:
  AC: AC-3
  Code reference: core/hooks/post_implementation_gate.py:177
  Evidence: Beide Gate-Meldungen nennen nur wirkende Phrasen; maschineller Abgleichtest grün; Fallback hält das Gate zu.
  Status: CONFIRMED

Confirmation:
  AC: AC-4
  Code reference: core/hooks/phase_listener.py:70
  Evidence: 17 Varianten in Runde 1 und weitere in Runde 2 verworfen, kein Marker.
  Status: CONFIRMED

Confirmation:
  AC: AC-5
  Code reference: core/hooks/phase_listener.py:70
  Evidence: Drei neue Sätze in phase3_spec: spec_approved False, Phase unverändert.
  Status: CONFIRMED

Confirmation:
  AC: AC-6
  Code reference: core/hooks/phase_listener.py:78
  Evidence: go, go, perfekt, Go! Weiter so wirken in phase6; approved, super in phase3.
  Status: CONFIRMED

Confirmation:
  AC: AC-7
  Code reference: core/hooks/phase_listener.py:90
  Evidence: `go, erste Version`, `go, nochmal bitte`, `go, Nachricht` werden freigegeben (Wortgrenze).
  Status: CONFIRMED

Confirmation:
  AC: AC-8
  Code reference: core/hooks/phase_listener.py:95
  Evidence: Klammer-Nachsatz (Realfall #46) gibt weiter frei.
  Status: CONFIRMED

Confirmation:
  AC: AC-9
  Code reference: core/hooks/phase_listener.py:145
  Evidence: `_finish()` gibt genau ein JSON-Objekt mit systemMessage auf stdout aus, stderr bleibt Spiegel; sechs Fälle in Runde 2.
  Status: CONFIRMED

Confirmation:
  AC: AC-10
  Code reference: core/hooks/phase_listener.py:151
  Evidence: Statusvermerk steht als hookSpecificOutput.additionalContext im selben Objekt; ohne Meldung reiner Text.
  Status: CONFIRMED

Confirmation:
  AC: AC-11
  Code reference: core/hooks/phase_listener.py:136
  Evidence: Ohne Workflow ein JSON-Objekt mit WARNUNG; Stop-Lock-Läufe rc 0; alle Austrittspunkte über `_finish()`.
  Status: CONFIRMED

Confirmation:
  AC: AC-12
  Code reference: core/hooks/phase_listener.py:122
  Evidence: Hinweis nennt konfigurierte Phrase; `approved` in phase6 nennt 'go', 'green ok', 'tests ok', 'gruen ok'.
  Status: CONFIRMED

Confirmation:
  AC: AC-13
  Code reference: core/hooks/phase_listener.py:136
  Evidence: Notification-Turn liefert unverändert den Statusvermerk als Text; Suite 118 passed.
  Status: CONFIRMED

Confirmation:
  AC: AC-14
  Code reference: core/hooks/bash_gate.py:686
  Evidence: Spec #170 Schritt 4 passt zu Tabelle/AC-4 (Test grün); Marker-Sperrmeldung nennt keine unwirksamen Wörter mehr, rc 2 an zwei Umgehungsvarianten.
  Status: CONFIRMED

═══════════════════════════════════════
VERDICT: VERIFIED
═══════════════════════════════════════
Die Implementierung hat den Adversary-Tests in zwei Runden standgehalten.
Tests: 118 passed, 0 failed (Zielsuite), 1638 passed / 25 skipped / 0 failed (Vollsuite)
Edge cases: F002/F004/F005 durch echte Läufe als behoben bestätigt. Offen nur F007 und F008 (LOW). F001 ausgelagert (Issue #311), F003/F006 akzeptiert.
Regressions: Keine.
Checklist: 14/14 Punkte bewiesen (AC-1..AC-14 CONFIRMED)

## Geprüfte Dateien

- sha256:8c6ee94ca159cc905df6df90b19bb37738bdd3e500096d8191058fd22355204d  core/hooks/bash_gate.py
- sha256:bdb78a7d48bad7fb16731c9ecfd014dc5c861068856b13c5dc739e206d8eb470  core/hooks/phase_listener.py
- sha256:6a20f87799cc3ef7452acb39f2f236c0055c510dc58735bcfa86770995c70f0d  core/hooks/post_implementation_gate.py

## Geprüfte Dateien

- sha256:8c6ee94ca159cc905df6df90b19bb37738bdd3e500096d8191058fd22355204d  core/hooks/bash_gate.py
- sha256:bdb78a7d48bad7fb16731c9ecfd014dc5c861068856b13c5dc739e206d8eb470  core/hooks/phase_listener.py
- sha256:6a20f87799cc3ef7452acb39f2f236c0055c510dc58735bcfa86770995c70f0d  core/hooks/post_implementation_gate.py
