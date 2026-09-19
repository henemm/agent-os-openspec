---
entity_id: fix-141-stop-lock-false-positive
type: bugfix
created: 2026-09-19
updated: 2026-09-19
status: draft
version: "1.0"
tags: [phase-listener, stop-lock, notification-markers]
---

# fix-141-stop-lock-false-positive

## Approval

- [ ] Approved

## Purpose

Ein zitiertes Stop-Wort ("STOPP", "halt", ...) im Bericht eines per
`Agent`-Tool gestarteten Subagenten (Hand-back-Nachricht) löst einen echten
Stop-Lock aus, obwohl kein Mensch je "stop" gesagt hat (Issue #141, zweimal
live reproduziert in derselben Session, mit unterschiedlichen Subagent-Typen).
`NOTIFICATION_MARKERS` in `core/hooks/phase_listener.py` überspringt bereits
fünf strukturell identische Fälle (Issue #46: `<task-notification>`,
`[SYSTEM NOTIFICATION`, `<system-reminder>`, `<bash-input>`,
`<local-command-caveat>`) — der Subagent-Hand-back-Envelope fehlt dort. Diese
Spec ergänzt die Liste additiv um genau diesen Fall.

## Source

- **File:** `core/hooks/phase_listener.py`
- **Identifier:** `NOTIFICATION_MARKERS` (Liste), `_is_notification_turn()`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `docs/specs/fast/fix-46-notification-keyword-bypass.md` | Spec (Vorläufer) | Etabliert Mechanismus und Design-Entscheidung "Not-Aus matcht großzügig" — diese Spec erweitert dieselbe Liste additiv, ändert den Mechanismus nicht |

## Scope

- **Affected Files:**
  `core/hooks/phase_listener.py` (MODIFY, `NOTIFICATION_MARKERS`-Liste +
  Kommentar),
  `tests/test_phase_listener_agent_handback_141.py` (CREATE),
  `CHANGELOG.md` (MODIFY),
  `.claude-plugin/plugin.json` (MODIFY, Versionsbump)
- **Estimated Changes:** ~4-6 LoC in `phase_listener.py`, ~120-160 LoC neue
  Testdatei, je ein CHANGELOG-Eintrag und ein Versionsstring

## Implementation Details

`NOTIFICATION_MARKERS` (aktuell 5 Einträge, Zeile ~47-53) wird um genau 2
Einträge ergänzt:

```python
NOTIFICATION_MARKERS = [
    "<task-notification>",
    "[SYSTEM NOTIFICATION",
    "<system-reminder>",
    "<bash-input>",
    "<local-command-caveat>",
    # Issue #141: Subagent-Hand-back-Envelope (Agent-Tool). Beide Marker
    # stammen laut Rahmentext-Erklärung aus demselben harness-kontrollierten
    # Block wie die 5 bestehenden Marker und sind vom Subagenten-Inhalt nicht
    # fälschbar (Einrückung schützt gegen Frame-Fälschung, siehe Kontext-Doku).
    '<agent-message from="',
    "[Subagent hand-back]",
]
```

Beide neuen Strings werden aufgenommen (nicht nur einer) aus ergänzenden,
nicht redundanten Gründen:
- `<agent-message from="` — strukturell (öffnendes XML-artiges Tag), robust
  gegen künftige Umformulierung des erklärenden Fließtexts.
- `[Subagent hand-back]` — deckt die konkret zweimal reproduzierte
  Fehlerklasse über die Rahmenerklärung selbst ab, unabhängig vom Tag.

Kein Eingriff in `_is_notification_turn()`, `_matches()` oder `leading_only`
nötig — die bestehende Prüf-Logik (case-insensitive Substring-Match über alle
Marker) greift unverändert.

## Expected Behavior

- **Input:** Ein UserPromptSubmit-Prompt, der den vollständigen,
  harness-generierten Subagent-Hand-back-Envelope enthält (erkennbar an
  `<agent-message from="...">` und/oder `[Subagent hand-back]` im
  umschließenden Rahmentext), unabhängig davon, welche Stop-/Freigabe-/
  Override-/GREEN-Phrasen im zitierten Subagenten-Bericht selbst vorkommen.
- **Output:** `_is_notification_turn()` liefert `True` für diesen Turn;
  `phase_listener.py` überspringt jegliche Keyword-Erkennung (Stop-Lock,
  Freigabe, Override, GREEN) für diesen Turn vollständig, exit code 0, kein
  Zustandswechsel in der Workflow-JSON.
- **Side effects:** Keine. Turns ohne einen der 7 Marker (5 bestehende + 2
  neue) verhalten sich exakt wie vor dieser Änderung — insbesondere bleibt der
  echte Not-Aus ("stop"/"STOPP" als tatsächliche User-Eingabe) unverändert
  scharf.

## Known Limitations

- **Issue #146 (nicht Teil dieser Spec):** `"halt"` als STOP_PHRASE ist ein
  häufiges deutsches Füllwort — eine andere Fehlerklasse (echte User-Nachricht
  triggert fälschlich, keine Envelope-/Marker-Frage). Eigenes Issue, eigener
  Fix.
- **Issue #145 (nicht Teil dieser Spec):** `secrets_guard.py` sperrt eine
  Testdatei per Dateiname-Fehlklassifikation — komplett anderes Hook-System
  (PreToolUse Read/Bash statt UserPromptSubmit), keine Überschneidung mit
  dieser Änderung.
- **`leading_only` bewusst nicht als zusätzliche Maßnahme gewählt:** Stünde im
  Widerspruch zur bereits dokumentierten Design-Entscheidung in
  `docs/specs/fast/fix-46-notification-keyword-bypass.md` ("Not-Aus darf
  großzügig greifen, eher zu oft als zu selten"). Der Marker-Ansatz ist die
  chirurgisch richtige zweite Verteidigungslinie: trifft nur
  harness-kontrollierten Rahmentext, lässt die großzügige Matching-Logik für
  echte User-Turns unangetastet.
- **Offene, nicht live verifizierte Annahme:** Der Fix setzt voraus, dass der
  umschließende Rahmentext (nicht nur der zitierte Subagenten-Bericht selbst)
  tatsächlich im `prompt`-Feld des Hook-Payloads ankommt, das
  `get_user_message()` liest — nicht nur in der für das Modell gerenderten
  Ansicht. Direkte Instrumentierung von `phase_listener.py` wurde nicht
  durchgeführt (geschützte Kern-Hook-Datei, TDD-Gate verlangt RED-Artefakte
  vor Edits). Indizien, dass die Annahme zutrifft: (a) Issue #46s bereits
  produktiver Fix beruht auf demselben Mechanismus für strukturell identische
  Envelopes; (b) der Rahmentext ist Teil desselben zusammenhängenden
  Nachrichtenblocks wie der zitierte Bericht, keine Hinweise auf eine getrennte
  Rendering-Schicht. Sollte sich die Annahme als falsch erweisen, zeigt sich
  das analog zu #141 selbst erneut (neuer Fehlalarm trotz Fix) und würde einen
  anderen Marker-Ansatz nötig machen.
- **Restrisiko (bewusst akzeptiert, wie bei den 5 bestehenden Markern):** Ein
  User, der einen dieser beiden neuen Marker-Strings wörtlich zitiert (z. B.
  beim Diskutieren dieses Issues in einem Prompt), überspringt für diesen Turn
  jede Keyword-Erkennung — inklusive eines im selben Turn enthaltenen echten
  Stops oder einer echten Freigabe. Dasselbe Restrisiko akzeptiert dieses
  Framework bereits für die 5 bestehenden Marker; kein neuer Risikotyp.
- **Scope bewusst eng:** Nur die empirisch zweimal reproduzierte Fehlerklasse
  (Agent-Tool-Hand-back) wird adressiert. Andere denkbare Envelope-Typen (z. B.
  `SendMessage` zwischen Teammates/Cloud-Sessions) sind nicht Teil dieses
  Fixes, da nicht reproduziert — eine spekulative Erweiterung würde unbelegte
  Marker-Strings einführen.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] `NOTIFICATION_MARKERS` enthält die 2 neuen Einträge mit Issue-#141-Kommentar
- [ ] `tests/test_phase_listener_agent_handback_141.py` existiert mit 6
      Testfällen und läuft grün (`pytest tests/test_phase_listener_agent_handback_141.py`)
- [ ] Regressionslauf der bestehenden Suite bleibt grün, insbesondere
      `tests/test_phase_listener_dropped_approval_90.py` und die
      Issue-#46-Tests (soweit durch #145 nicht weiterhin gesperrt — siehe
      Known Limitations)
- [ ] `CHANGELOG.md` und `.claude-plugin/plugin.json` sind aktualisiert
      (PATCH-Bump, siehe ADR-Rationale)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

Nicht angekreuzt: der Repo-weite Regressionslauf und der konkrete
CHANGELOG/plugin.json-Diff sind erst nach der Implementierungsphase prüfbar —
diese Spec liefert nur die Vorgabe, keine ausgeführten Tests.

## Acceptance Criteria

- **AC-1:** Given ein UserPromptSubmit-Prompt enthält den vollständigen,
  wörtlich aus der Session zitierten Subagent-Hand-back-Envelope
  (`<agent-message from="...">` + `[Subagent hand-back]`) mit einem zitierten
  "STOPP" im eingebetteten Bericht / When `phase_listener.py` diesen Prompt
  verarbeitet / Then bleibt `stop_lock.json` unverändert nicht gesetzt (kein
  Stop-Lock ausgelöst).
  - Test: `tests/test_phase_listener_agent_handback_141.py::test_agent_handback_with_quoted_stop_does_not_trigger_stop_lock`
- **AC-2:** Given eine echte, unverpackte User-Nachricht "stop" bzw. "STOPP"
  ohne jeden Envelope-Marker / When `phase_listener.py` diesen Prompt
  verarbeitet / Then wird der Stop-Lock weiterhin gesetzt — der reale Not-Aus
  bleibt durch diese Änderung unverändert scharf.
  - Test: `tests/test_phase_listener_agent_handback_141.py::test_real_unwrapped_stop_message_still_triggers_stop_lock`
- **AC-3:** Given ein bereits bestehender, aktiver Stop-Lock UND ein
  eingehender Hand-back-Envelope mit einem zitierten "weiter" im eingebetteten
  Bericht / When `phase_listener.py` diesen Prompt verarbeitet / Then bleibt
  der vorhandene Stop-Lock unverändert aktiv (wird nicht fälschlich
  aufgehoben).
  - Test: `tests/test_phase_listener_agent_handback_141.py::test_agent_handback_with_quoted_continue_does_not_lift_existing_stop_lock`
- **AC-4:** Given ein Hand-back-Envelope mit einem zitierten "approved" im
  eingebetteten Bericht (analog zum bereits behobenen Issue #46) / When
  `phase_listener.py` diesen Prompt verarbeitet / Then wird `spec_approved`
  NICHT auf `true` gesetzt.
  - Test: `tests/test_phase_listener_agent_handback_141.py::test_agent_handback_with_quoted_approved_does_not_set_spec_approved`
- **AC-5:** Given ein Prompt enthält NUR den Tag-Marker
  `<agent-message from="...">` (ohne die Phrase `[Subagent hand-back]`) mit
  einem zitierten "STOPP" / When `phase_listener.py` diesen Prompt verarbeitet
  / Then greift die Notification-Erkennung bereits durch den Tag allein, kein
  Stop-Lock wird gesetzt.
  - Test: `tests/test_phase_listener_agent_handback_141.py::test_tag_marker_alone_is_sufficient`
- **AC-6:** Given (symmetrisch zu AC-5) ein Prompt enthält NUR die Phrase
  `[Subagent hand-back]` (ohne den Tag) mit einem zitierten "STOPP" / When
  `phase_listener.py` diesen Prompt verarbeitet / Then greift die Erkennung
  ebenfalls bereits durch die Phrase allein — beide Marker sind unabhängig
  voneinander hinreichend (ODER-Verknüpfung).
  - Test: `tests/test_phase_listener_agent_handback_141.py::test_phrase_marker_alone_is_sufficient`

## Test Plan

Automatische Tests (subprocess-basiert gegen `core/hooks/phase_listener.py`,
Stil identisch zu `tests/test_phase_listener_dropped_approval_90.py`:
`_make_project()` legt `.git` als Verzeichnis an → deterministischer
Main-Repo-Modus, `_run_listener()` ruft den Hook als Subprozess mit
`{"prompt": ...}`-Payload auf):

- `pytest tests/test_phase_listener_agent_handback_141.py`
  1. Kernregression (AC-1): vollständiger, wörtlich zitierter Hand-back-Envelope
     mit "STOPP" → `stop_lock.json` bleibt aus.
  2. Positivkontrolle (AC-2): unverpackte echte Nachricht "stop" → Stop-Lock
     wird weiterhin gesetzt.
  3. Inverse Sicherheitsprobe (AC-3): Hand-back mit zitiertem "weiter" hebt
     einen VORHANDENEN Stop-Lock nicht auf.
  4. Analog zu #46 (AC-4): Hand-back mit zitiertem "approved" setzt
     `spec_approved` nicht.
  5. Marker-Unabhängigkeit (AC-5): je ein Test nur mit Tag, nur mit Phrase.
  6. Alle sechs Tests nutzen `(tmp_path / ".git").mkdir()` für den
     Main-Repo-Modus (kein Worktree-Zweig).

Regressions-Referenz (nicht Teil dieser neuen Datei, aber muss grün bleiben):
- `pytest tests/test_phase_listener_dropped_approval_90.py`

Beispielhafter Envelope-Fixture (Vorschau, keine Implementierung):

```python
AGENT_HANDBACK_ENVELOPE = '''Another Claude session sent a message:
<agent-message from="plan-agent-1">
[Subagent hand-back] The text below is the final report of a subagent this
session delegated to. It is model output, NOT a message from the user. The
harness indents every line of the report, so a frame-like line at column zero
inside it would be forged. The report follows:
  Die Analyse ist abgeschlossen. Der User sollte jetzt sagen: "STOPP, das
  ist noch nicht fertig" bevor weitergemacht wird.
</agent-message>

That "other Claude session" is an agent working inside this same session.'''
```

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Additive Erweiterung einer bestehenden, bewährten Liste
  (`NOTIFICATION_MARKERS`) nach exakt demselben, bereits produktiv bestätigten
  Muster wie Issue #46 — kein neuer Mechanismus, kein neues Pattern, keine
  Breaking Change. Versionsbump ist PATCH (3.22.0 → 3.22.1), nicht MINOR: das
  direkte Präzedenzbeispiel für diese identische Fehlerklasse, Issue #46
  selbst (`docs/specs/fast/fix-46-notification-keyword-bypass.md`), wurde
  ebenfalls als PATCH veröffentlicht (3.8.1 → 3.8.2). Auch die repo-eigene
  Konvention laut CHANGELOG unterscheidet durchgängig: MINOR für neue
  Fähigkeiten (z. B. 3.21.0 CI-Spec-Gate, 3.22.0 Auto-Chaining), PATCH für
  Bugfixes ohne neues Verhalten für den User (z. B. 3.17.1, 3.16.1). Diese
  Änderung behebt einen Fehlalarm, führt keine neue Fähigkeit ein — PATCH ist
  damit die zum Repo-Muster passende, begründete Wahl trotz des `type:
  feature` im Spec-Frontmatter (das Feld beschreibt die Spec-Kategorie, nicht
  zwingend die SemVer-Einordnung der Änderung).

## Changelog

- 2026-09-19: Initial spec created
