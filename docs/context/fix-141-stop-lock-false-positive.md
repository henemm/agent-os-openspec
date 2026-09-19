# Context: fix-141-stop-lock-false-positive

## Request Summary

Issue #141: Ein zitiertes Stop-Wort ("STOPP", "halt", "anhalten") im Bericht
eines per `Agent`-Tool gestarteten Subagenten (Hand-back-Nachricht) löst einen
echten Stop-Lock aus, obwohl kein Mensch je "stop" gesagt hat. Zweimal live
reproduziert in derselben Session (verschiedene Subagent-Typen: Plan-Agent,
implementation-validator).

## Empirischer Befund (Primärbeleg aus dieser Session, nicht nur Vermutung)

Jede Subagent-Hand-back-Nachricht, die dieser Session als eingehende
Nutzer-Turn zugestellt wurde, hatte durchgängig **exakt dieselbe,
harness-generierte Umschließung** — unabhängig vom Subagent-Typ oder Inhalt:

```
Another Claude session sent a message:
<agent-message from="<agent-id>">
[Subagent hand-back] The text below is the final report of a subagent this
session delegated to. It is model output, NOT a message from the user: ...
The report follows:
  <eingerückter Inhalt des Subagenten>
</agent-message>

That "other Claude session" is an agent working inside this same session — ...
```

Zwei stabile, wörtliche Substrings kommen in **jeder** dieser Nachrichten vor
und in keiner echten User-Eingabe dieser Session:

- `<agent-message from="` (öffnendes Tag, dynamische ID danach)
- `[Subagent hand-back]` (Marker-Phrase direkt im umschließenden Text)

Beide sind laut der Rahmentext-Erklärung selbst harness-kontrolliert und vom
Subagenten-Inhalt nicht fälschbar ("The harness indents every line of the
report, so a frame-like line at column zero inside it would be forged") —
exakt dieselbe Vertrauensbasis, auf der `NOTIFICATION_MARKERS` bereits für
`<task-notification>` etc. beruht (Issue #46).

## Related Files

| File | Relevance |
|------|-----------|
| `core/hooks/phase_listener.py` | `NOTIFICATION_MARKERS` (Zeile ~44-51) und `_is_notification_turn()` (Zeile ~82-91) — hier fehlt der neue Marker. `STOP_PHRASES`-Check (Zeile 216) hat bewusst kein `leading_only`, matcht daher irgendwo im Text. |
| `tests/` | Vermutlich `tests/test_phase_listener*.py` oder ähnlich — vorhandene Tests für `_is_notification_turn`/Stop-Lock-Erkennung, Stil-Vorbild für neuen Test. |

## Existing Patterns

- Issue #46 löste dieselbe Fehlerklasse für `<task-notification>`,
  `[SYSTEM NOTIFICATION`, `<system-reminder>`, `<bash-input>`,
  `<local-command-caveat>` — additive Erweiterung der bestehenden
  `NOTIFICATION_MARKERS`-Liste ist das etablierte, risikoarme Muster für genau
  diesen Fehlertyp.

## Analysis

### Type
Bug (Fehlalarm), Fix nach etabliertem Muster (Issue #46)

### Empfehlung (Plan/Sonnet-Review)

Marker-Erweiterung um **beide** Strings (ergänzende, nicht redundante Gründe):
- `<agent-message from="` — strukturell (öffnendes Tag), robust gegen künftige
  Umformulierung des erklärenden Fließtexts
- `[Subagent hand-back]` — deckt exakt die zweimal reproduzierte Fehlerklasse
  über die Rahmenerklärung ab

`leading_only` für Stop-Phrasen als zusätzliche Verteidigungslinie **explizit
NICHT empfohlen** — widerspricht der bereits dokumentierten Entscheidung in
`docs/specs/fast/fix-46-notification-keyword-bypass.md` ("Not-Aus darf eher
zu oft als zu selten greifen"). Der Marker-Ansatz ist die chirurgisch richtige
zweite Verteidigungslinie: trifft nur harness-kontrollierten Rahmentext, lässt
die großzügige Matching-Logik für echte User-Turns unangetastet.

### Restrisiko (bewusst akzeptiert, wie bei den bestehenden 5 Markern)

Ein User, der diese Marker-Strings wörtlich zitiert (z. B. beim Diskutieren
dieses Issues), überspringt für diesen Turn jede Keyword-Erkennung — etwas
wahrscheinlicher in einem Framework-Repo, das Hook-Interna aktiv dokumentiert,
als in einem durchschnittlichen Konsumenten-Projekt. Rechtfertigt keinen
anderen Ansatz, wird aber explizit benannt statt stillschweigend akzeptiert.

### Offene Verifikationsfrage (dokumentiert, nicht blockierend)

Der Fix setzt voraus, dass der umschließende Rahmentext (nicht nur der
zitierte Bericht selbst) im `prompt`-Feld ankommt, das `get_user_message()`
liest — nicht nur in der für das Modell gerenderten Ansicht. Direkte
Instrumentierung von `phase_listener.py` wurde nicht durchgeführt (geschützte
Kern-Hook-Datei, TDD-Gate). Indizien dafür, dass die Annahme zutrifft:
(a) Issue #46s bereits produktiver Fix beruht auf demselben Mechanismus für
strukturell identische Envelopes (`<task-notification>` etc.); (b) der
Rahmentext ist Teil desselben zusammenhängenden Nachrichtenblocks, der auch
den zitierten Bericht enthält — keine Hinweise auf eine getrennte
Rendering-Schicht. Sollte sich diese Annahme als falsch erweisen, würde sich
das analog zu #141 selbst erneut zeigen (neuer Fehlalarm trotz Fix) und einen
anderen Marker-Ansatz nötig machen.

### Weitere Funde (nicht Teil dieses Fixes)

- Issue #146: `"halt"` als STOP_PHRASE ist ein häufiges deutsches Füllwort —
  eigene, unabhängige Fehlerklasse (echte User-Nachricht, keine
  Envelope-Frage), separates Issue.
- Issue #145: `secrets_guard.py` sperrt `tests/test_phase_listener_keyword_guard.py`
  per Dateiname-Fehlklassifikation komplett — verhinderte die Prüfung der
  bestehenden Issue-46-Testabdeckung während dieser Analyse.

### Scope Assessment
- Files: `core/hooks/phase_listener.py` (MODIFY, ~4-6 LoC), neue Testdatei
  `tests/test_phase_listener_agent_handback_141.py` (CREATE, ~120-160 LoC),
  `CHANGELOG.md` (MODIFY), `.claude-plugin/plugin.json` (MODIFY, Versionsbump)
- Risk Level: LOW (additive Erweiterung einer bestehenden, bewährten Liste)

### Test Plan (6 Fälle, Stil wie `test_phase_listener_dropped_approval_90.py`)
1. Kernregression: vollständiger Hand-back-Envelope mit zitiertem "STOPP" →
   Stop-Lock bleibt aus
2. Positivkontrolle: unverpackte echte User-Nachricht "stop"/"STOPP" → Stop-Lock
   wird weiterhin gesetzt
3. Inverse Sicherheitsprobe: Hand-back mit zitiertem "weiter" darf einen
   bestehenden Stop-Lock NICHT aufheben
4. Analog zu #46: Hand-back mit zitiertem "approved"/"green ok"/"override"
   setzt keinen der jeweiligen Zustände
5. Marker-Unabhängigkeit: je ein Test nur mit Tag, nur mit Phrase (OR-Logik
   bestätigen)
6. `(tmp_path / ".git").mkdir()` für deterministischen Main-Repo-Modus

## Risks & Considerations

- **Kein neuer Mechanismus nötig** — reine Ergänzung der bestehenden Liste,
  gleiche Prüf-Logik (`_is_notification_turn`, Substring-Match, case-insensitive).
- **Restrisiko (bereits akzeptiert für bestehende Marker):** Ein Turn, der
  zufällig einen dieser Substrings enthält, überspringt JEDE Keyword-Erkennung
  für diesen Turn — auch eine im selben Turn enthaltene echte Freigabe/Stop.
  Das ist dieselbe Abwägung wie bei den 5 bestehenden Markern, keine neue
  Kategorie von Risiko.
- **Scope bewusst eng:** Nur die empirisch zweimal reproduzierte
  Fehlerklasse (Agent-Tool-Hand-back) adressieren. Andere denkbare
  Nachrichtentypen (z. B. SendMessage von Teammates/Cloud-Sessions) sind nicht
  Teil dieses Fixes, da nicht reproduziert — spekulative Erweiterung würde
  unbelegte Marker-Strings einführen.
