# Fast Track: Gate-Event-Log (#181, Epic #199, 3.29.0)

## Problem

Blockaden der Kern-Gates und ergänzenden Guards waren bisher nur im Transcript sichtbar. Es
gibt keine Kennzahl und keinen systematischen Weg von einem Fehlalarm zum Regressionstest. Laut
/insights-Report vom 21.09.2026 (241 Sessions, 15.482 Bash-Aufrufe): „Eigene Guardrails sind die
größte Reibungsquelle." Fünf offene Vorschläge im Backlog (#178, #180, #184, #186, #194) fügen
jeweils weitere Prüfungen hinzu — ohne Messung ist die Entscheidung über jeden davon eine Meinung
gegen eine andere.

Herkunft: Backlog-Triage 21.09.2026, Epic #199, eigener Kommentar auf #181 vom selben Tag
(„umsetzen — und zwar zuerst").

## Scope

- `core/hooks/hook_utils.py`:
  - `log_gate_event(hook, tool, reason, command_excerpt="")` — hängt eine JSON-Zeile an
    `.claude/gate-events.jsonl` (unter `find_project_root()`, damit Worktree-Sessions in dasselbe
    Log wie der Hauptordner schreiben — dieselbe Auflösung wie `session-locks/` und `workflows/`)
  - `mask_and_truncate_excerpt(text)` — öffentliche Maskierungs-/Kappungsfunktion
  - `block()` erweitert um optionale `hook`/`tool`/`command_excerpt`-Kwargs, ruft
    `log_gate_event()` intern auf; bestehende Aufrufer mit nur einem Positionsargument
    funktionieren unverändert weiter
- Fünf Dateien mit rohem `sys.exit(2)` um je einen Log-Aufruf vor dem Exit ergänzt:
  `claude_md_protection.py`, `secret_egress_guard.py` (bewusst ohne Inhalt), `secrets_guard.py`
  (4 Stellen), `session_singleton_guard.py`, `worktree_write_guard.py`
- `.gitignore` (dieses Repo) und `setup.py::GITIGNORE_RUNTIME_ENTRIES` um
  `.claude/gate-events.jsonl` ergänzt
- Version 3.29.0, CHANGELOG, README
- **Nicht enthalten:** `/91-gate-audit` (Clustering, Häufigkeitstabelle, Fehlalarm-Triage-Dialog).
  Der Entwurf im Issue selbst stuft das als zweitrangig ein („Reicht das Log allein, und ist
  `/91-gate-audit` erst danach nötig?"); ohne echte Daten wäre jede Auswertungslogik jetzt
  spekulativ.
- **Nicht enthalten:** Log-Rotation. Kein Anlass ohne gemessenes Volumen; ein Folge-Ticket, sobald
  Dateigröße real ein Problem wird.
- **Nicht enthalten:** Eine Kennzahl „Blockaden pro Workflow" in `/90-retro` (im Issue als
  „optional" markiert) — baut auf `/91-gate-audit` auf, folgt später.

## Definition of Done

Jede Stelle in `core/hooks/*.py`, die `sys.exit(2)` aufruft, schreibt vorher ein Event nach
`.claude/gate-events.jsonl`. Die Events enthalten keine Geheimnis-Werte, auch nicht maskiert
teilweise sichtbar. Ein Logging-Fehler ändert nie den Exit-Code eines Gates. Bestehende Aufrufer
von `block()` brauchen keine Änderung.

## Acceptance Criteria

- **AC-1:** Given jede der neun Stellen in `core/hooks/*.py`, die `sys.exit(2)` mit einer Blockade-Meldung aufruft, When sie auslöst, Then steht danach ein passendes Event in `.claude/gate-events.jsonl` (getestet für alle fünf Dateien mit rohem `sys.exit(2)` sowie stellvertretend für die vier über `block()` laufenden Kern-Gates, deren Mechanismus identisch ist).
- **AC-2:** Given ein `command_excerpt`, das ein Geheimnis-Schlüsselwort mit Zuweisung enthält (`API_KEY=…`, `Authorization: Bearer …`), When es durch `log_gate_event`/`mask_and_truncate_excerpt` läuft, Then taucht der Geheimnis-Wert an keiner Stelle in der geschriebenen Zeile auf — auch nicht das auf das Schlüsselwort folgende Token.
- **AC-3:** Given ein Dateiname, der zufällig ein Schlüsselwort-Substring trägt (`…keyword_guard.py`), When er durch dieselbe Maskierung läuft, Then bleibt er unverändert — die Maskierung darf die Diagnoseinformation nicht zerstören, die #89/#145 gebraucht hätten.
- **AC-4:** Given `log_gate_event()` kann nicht schreiben (Zielpfad durch eine reguläre Datei blockiert), When sie aufgerufen wird, Then wirft sie keine Ausnahme.
- **AC-5:** Given `block()` wird wie bisher mit nur der Nachricht aufgerufen, When es ausgeführt wird, Then loggt es trotzdem (Herkunft von hook/tool/excerpt aus `sys.argv`/Env-Vars) und der Exit-Code bleibt 2 — auch wenn das Logging selbst fehlschlägt.
- **AC-6:** Given `secret_egress_guard.py` blockiert einen geleakten Wert, When das Event geschrieben wird, Then enthält weder `reason` noch `command_excerpt` den ausgeschriebenen Wert — nur die Schlüssel-Namen, die die User-Meldung ohnehin schon nennt.
- **AC-7:** Given `.gitignore` und `setup.py`, When sie geprüft werden, Then führen beide `.claude/gate-events.jsonl` als Laufzeit-Zustand.

## Test Plan

`tests/test_gate_event_log_181.py`, 24 Tests in sechs Klassen:

- `TestMaskAndTruncateExcerpt` — Durchreichen, leer/None, Kappung, vier Geheimnis-Schlüsselwörter,
  der Bearer-Token-Sonderfall, die Dateiname-Gegenprobe (AC-2, AC-3)
- `TestLogGateEvent` — Schema, Anhängen statt Überschreiben, root-sicherer Schreibfehler (kein
  `chmod`, da diese Umgebung als root läuft und Dateirechte ignoriert — stattdessen ein
  Pfadsegment, das bereits eine reguläre Datei ist), Session-ID, Ende-zu-Ende-Maskierung (AC-4)
- `TestBlockAutoLogs` — unverändertes Ein-Argument-`block()` loggt trotzdem, Exit-Code bleibt 2
  auch bei kaputtem Logger, explizite Kwargs überschreiben die Env-Herleitung (AC-5)
- `TestAllBlockingHooksLogAnEvent` — je ein Subprozess-Fall für `claude_md_protection.py`,
  `worktree_write_guard.py`, `secrets_guard.py`, `secret_egress_guard.py` (AC-1, AC-6)
- `TestGitignoreCoversTheLogFile` — beide Vorlagen (AC-7)

Nachweis:

- Ausgangsstand (main nach #145): 1044 passed, 4 skipped
- GREEN: 1068 passed, 4 skipped (24 neue, keine bestehenden verändert)

**Gegenprobe (Mutation).** Sechs gezielte Verfälschungen, jede wurde rot: Log-Aufruf aus `block()`
entfernt · Schlüsselwort-Erkennung der Maskierung abgeschaltet · Log-Aufruf aus
`worktree_write_guard.py` entfernt · `secret_egress_guard.py` so geändert, dass es den Wert doch
mitschickt · `.gitignore`-Eintrag entfernt · `setup.py`-Eintrag entfernt. Arbeitsbaum danach
nachweislich sauber wiederhergestellt.

Eine ursprüngliche Testfassung für AC-4 nutzte `chmod 0o500`, was diese als root laufende Umgebung
stillschweigend ignoriert (root umgeht Dateirechte) — der Test wäre auch ohne die
`try/except`-Absicherung grün geblieben. Durch die root-unabhängige Variante ersetzt (Pfadsegment
als Datei statt Verzeichnis blockiert), bevor der Test in diese Spec aufgenommen wurde.
