# Kontext: Session-Register erweitern (#106)

Workflow: `feat-106-session-register` · Track: Full Process · Phase 1 (Context)
Erhoben: 2026-08-21, drei parallele Explore-Agenten + eigene Verifikation

## Kernbefund

**Ein vollständiges, aktuelles Session-Register existiert bereits — es gehört nur nicht uns.**

Claude Code pflegt `~/.claude/sessions/<pid>.json`. Diese Datei enthält genau die Felder, die
Issue #106 vermisst, und pflegt sie zuverlässig nach:

```json
{
  "pid": 3871265,
  "sessionId": "79ba8817-3550-45da-94f9-53d6b71b6aa2",
  "cwd": "/home/hem/agent-os-openspec/.claude/worktrees/intake-106",
  "name": "agent-os-openspec-9a",
  "nameSource": "derived",
  "status": "busy",
  "startedAt": 1787287937909,
  "updatedAt": 1787289691373,
  "bridgeSessionId": "session_01G8zbY5ziuLFDBrgdqeWkKf",
  "kind": "interactive",
  "version": "2.1.238"
}
```

`name` ist exakt die `ListAgents`-Adresse, die AC-1 fordert. `cwd` steht auf dem **Worktree**,
nicht auf dem Hauptverzeichnis — also genau das, was AC-2 verlangt.

### Direkter Vergleich der beiden Register (gemessen 2026-08-21, 05:27)

| | `~/.claude/sessions/` (Harness) | `.claude/session-locks/` (Framework) |
|---|---|---|
| Einträge | 7 | 1 |
| Lebende PIDs | 7 von 7 | 0 von 1 |
| `cwd` korrekt | ja, alle im Worktree | nein, eingefroren auf Hauptverzeichnis |
| Jüngste Aktualisierung | 184 s alt | 2066 s alt |
| Lesbarer Name | ja (`gregor-zwanzig-6d` …) | nein |

Die sieben Harness-Einträge decken alle laufenden Sessions ab — auch die Dauerläufer, die dem
eigenen Register fehlen. Das erklärt Beobachtung 2 aus dem Issue ("`ListAgents` zeigte sechs
Sessions, das Verzeichnis hielt vier Dateien") vollständig: `ListAgents` liest diese Dateien.

## Root Cause der beiden Issue-Beobachtungen

Beide Symptome haben **eine gemeinsame Ursache** in `core/hooks/session_singleton_guard.py`.

In `_do_guard` steht der `last_seen`-Heartbeat (Zeile 243–246) **hinter** dem Worktree-Ausstieg
(Zeile 227–228):

```python
# Worktree-Sitzungen haben eigene Isolation — kein weiterer Check.
if _is_worktree_cwd(cwd):
    sys.exit(0)          # ← Zeile 228: Worktree-Session ist hier raus
...
# Heartbeat aktualisieren (für Diagnostik / reap_dead).
...
own["last_seen"] = now   # ← Zeile 245: wird von Worktree-Sessions nie erreicht
```

Da seit v3.4.10 **alle** Sessions im Worktree laufen müssen, erreicht praktisch **keine** Session
mehr den Heartbeat. Es gibt keinen zweiten Schreiber — `last_seen` wird nur an zwei Stellen
gesetzt (Zeile 206 in `_do_register`, Zeile 245 in `_do_guard`).

Daraus folgen beide Beobachtungen:

1. **Eingefrorenes `cwd`** — der Eintrag wird nach dem initialen `register` nie wieder angefasst.
   Registriert wird beim SessionStart, also **bevor** `EnterWorktree` läuft.
2. **Fehlende Dauerläufer** — `_reap_dead` löscht Einträge, deren PID tot ist **und** deren
   `last_seen` älter als `_STALE_SECONDS` (900 s) ist. Die gespeicherte PID ist `os.getppid()`,
   also die **transiente Hook-Shell**, die Sekunden später beendet ist (so auch im Code-Kommentar
   Zeile 91–95 dokumentiert). Ohne Heartbeat verfällt jede Session nach 15 Minuten — je länger
   sie läuft, desto sicherer verschwindet sie. Ein Register, das systematisch die Dauerläufer
   verliert.

**Live-Beleg:** Der einzige verbliebene Lock-Eintrag ist der dieser Session — `cwd` auf dem
Hauptverzeichnis, PID 3871334 tot, `last_seen` 34 Minuten alt. Er würde beim nächsten
`_reap_dead` gelöscht, während die Session weiterläuft.

## Machbarkeit der vier Akzeptanzkriterien

| AC | Machbar? | Weg |
|----|----------|-----|
| AC-1 (`agent_name` etc.) | **ja** | `name` aus `~/.claude/sessions/*.json` über `sessionId` joinen |
| AC-2 (`cwd` nachführen) | **ja** | Heartbeat vor den Worktree-Ausstieg ziehen; oder `cwd` direkt aus Harness-Datei |
| AC-3 (`issue`/`phase`) | **ja, aber anders als im Issue vorgeschlagen** | siehe unten |
| AC-4 (Dauerläufer) | **ja** | Root Cause oben beheben; `pid` aus Harness-Datei ist die echte, lebende PID |

### AC-3 kann nicht wie vorgeschlagen gebaut werden

Das Issue schlägt vor, `workflow.py` solle `issue` und `phase` in den eigenen Registereintrag
schreiben. **Das geht nicht:** `workflow.py` ist ein CLI-Tool, kein Hook. Es bekommt keinen
Payload und kennt seine `session_id` nicht — kein `session_id`, kein `getppid`, keine
`CLAUDE_SESSION_ID`-Env-Var. Es weiß also nicht, in welche Registerdatei es schreiben soll.

Ergänzend: Die **Issue-Nummer ist gar kein Feld** im Workflow-State. Vorhanden sind `name`,
`workflow_type`, `current_phase`, `spec_file`, `adversary_verdict` u.a. — die Ticketnummer steckt
nur im Namen (`feat-106-session-register`) und müsste per Regex gewonnen werden.

**Der Datenfluss muss umgedreht werden.** Statt dass `workflow.py` in das Register schreibt,
liest der **Hook** (der die `session_id` kennt) über `hook_utils.resolve_active_workflow()` den
aktiven Workflow und übernimmt Name, Phase und die daraus abgeleitete Issue-Nummer in seinen
eigenen Eintrag. Das erfüllt zugleich die Forderung des Issues, keinen zweiten Schreiber auf
denselben Pfad zu setzen ("ein Rennen, kein Register") — der Guard bleibt alleiniger Schreiber.

Praktischer Nebeneffekt: Derselbe Handgriff, der AC-3 löst (Nachführen im Guard-Pfad), behebt
auch die Root Cause von AC-2 und AC-4. Ein Eingriff, drei Kriterien.

## Risiko: `~/.claude/sessions/` ist Harness-Internal

Die Datei ist **nicht dokumentiert** und trägt eine Harness-Version (`2.1.238`). Format und Pfad
können sich mit jedem Claude-Code-Update ändern. Konsequenz für die Analyse-Phase: Das Auslesen
muss rein additiv und defensiv sein — fehlende Datei, unbekanntes Format oder fehlende Felder
dürfen niemals einen Hook zum Blocken bringen. `session_singleton_guard.py` hängt als
`PreToolUse` an **allen** Tools; eine Exception dort sperrt jede Session serverweit aus.

Offene Abwägung für `/20-analyse`: eigenes Register mit Harness-Daten anreichern, oder das
Harness-Register als Wahrheit für Liveness/Name/`cwd` nehmen und nur die Projektebene (Issue,
Branch, Workflow, Phase) selbst führen.

## Betroffene Dateien

| Datei | Rolle |
|-------|-------|
| `core/hooks/session_singleton_guard.py` | Einziger Schreiber des Registers; Root Cause in `_do_guard` (Z. 227/243) |
| `core/hooks/hook_utils.py` | `resolve_active_workflow()` (Z. 623) — Brücke zum aktiven Workflow |
| `core/hooks/workflow.py` | State-Quelle für Phase; **kennt die Session nicht** (kein Schreiber) |
| `tests/test_session_singleton_guard.py` | 19 Tests; **keiner** deckt Heartbeat im Worktree ab |

## Bekannte Risiken

- **Blast Radius:** `PreToolUse` auf allen Tools, global über `~/.claude/settings.json` in sechs
  Instanzen aktiv. Ein Fehler sperrt alle Sessions aus. Jeder neue Pfad braucht `try/except`.
- **Undokumentiertes Harness-Format** (siehe oben).
- **Test-Lücke:** Das Heartbeat-Verhalten im Worktree ist heute ungetestet — deshalb blieb der
  Bug unbemerkt. Die RED-Phase muss genau hier ansetzen.
- **Reaping-Logik:** `_STALE_SECONDS` (900 s) und der PID-Check greifen ineinander; eine Änderung
  am Heartbeat verschiebt auch das Reaping-Verhalten. Bestehende Tests dazu existieren und dürfen
  nicht stillschweigend umgedeutet werden.

---

# Analysis

Erhoben: 2026-08-21, Phase 2 — drei parallele Explore-Agenten + Plan-Bewertung + eigene Verifikation.

## Type

**Feature** mit eingebettetem Bugfix. Die Sichtbarkeits-Erweiterung (AC-1, AC-3) ist neue
Funktionalitaet; AC-2 und AC-4 sind die Behebung eines bestehenden Fehlers.

## Architektur-Entscheidung: Option A (eigenes Register bleibt Wahrheit)

Abgewaegt wurden:

- **(A)** Eigenes Register bleibt Wahrheit, wird additiv angereichert.
- **(B)** Harness-Register (`~/.claude/sessions/`) wird Wahrheit fuer Liveness/Name/`cwd`,
  eigenes Register fuehrt nur die Projektebene.

**Entscheidung: A.** Die Pruefung Feld fuer Feld zeigt, dass nur **ein einziges** Feld ueberhaupt
Harness-Daten braucht:

| AC | Quelle | Harness noetig? |
|----|--------|-----------------|
| AC-1 `agent_name` | `~/.claude/sessions/*.json` → `name` | **ja** — der Name wird vom Harness vergeben (`nameSource: "derived"`) und existiert nirgends sonst |
| AC-2 `cwd`/`worktree` | Guard-Payload (live bei jedem Aufruf) | nein |
| AC-3 `issue`/`phase` | `hook_utils.resolve_active_workflow()` + Workflow-State | nein |
| AC-4 Dauerlaeufer | Root-Cause-Fix am Heartbeat | nein |

Damit schrumpft die Abhaengigkeit vom undokumentierten Harness-Internal auf **ein optionales
Anzeigefeld**. Option B wuerde sie dagegen in den sicherheitskritischen Reaping-Pfad ziehen und
zusaetzlich pro Guard-Aufruf einen Verzeichnis-Scan erzwingen.

**Verifiziert:** `_owner_sid()` (Z. 130) ist toter Code — definiert, aber nirgends aufgerufen
(`grep -rn '_owner_sid' core/ tests/` liefert nur die Definition). Es gibt heute also keinen
Konsumenten, der Liveness oder Ownership aus dem gespeicherten Register ableitet. Alles, was
#106 fordert, ist reine Diagnostik — ein weiteres Argument gegen B.

## Root-Cause-Fix mit Throttle (Abweichung von der Plan-Empfehlung)

Der Heartbeat-Block muss vor den Worktree-Ausstieg. Strittig ist, **bei welchen Tools** er feuert.

Der Plan empfiehlt, ihn hinter dem `_BLOCKING_TOOLS`-Filter zu belassen — also nur bei
`{Edit, Write, MultiEdit, Bash, Task, Agent}`. **Das laesst AC-4 halb offen:** Eine Session, die
15 Minuten lang nur liest (Read/Grep/Glob), bekommt keinen Heartbeat, ihre gespeicherte PID ist
die laengst tote Hook-Shell — `_reap_dead` entfernt sie, obwohl sie laeuft. Genau das Symptom,
das AC-4 abstellen soll.

**Entscheidung: Heartbeat bei allen Tools, aber geschrieben nur wenn ueberfaellig.** Ist
`now - last_seen` kleiner als ein Schwellwert (Vorschlag: 60 s), wird nichts geschrieben. Damit:

- hoechstens ein kleiner JSON-Write pro Minute und Session statt einer pro Tool-Aufruf,
- keine lebende Session verfaellt mehr, unabhaengig davon, welche Tools sie nutzt,
- der teure Pfad (`_read_entries`, `_reap_dead`) bleibt unberuehrt.

Die PID bleibt wie bisher `os.getppid()`. Sie durch die echte Claude-PID aus dem Harness zu
ersetzen wuerde erneut eine Harness-Abhaengigkeit in den Reaping-Pfad ziehen; der bestehende
`last_seen`-Fallback (Z. 91–97, mit fuenf dedizierten Tests) kompensiert die transiente PID
bereits vollstaendig. Ausserhalb des Scopes.

## Kapselung des Harness-Zugriffs

Ein lokaler Helfer in `session_singleton_guard.py` (nicht in `hook_utils.py` — der Utils-Layer
bleibt frei von Harness-Wissen):

- kompletter Body in `try/except Exception: return None`
- fehlendes Verzeichnis, kaputte JSON-Datei, fehlendes Feld, kein Treffer → jeweils `None`
- nur `.get()` auf `sessionId` und `name`, keine Versionspruefung — degradiert bei jedem
  Formatwandel automatisch auf "kein Name" statt zu crashen
- **Aufruf nur in `_do_register`** (einmal pro SessionStart), niemals im Guard-Hot-Path

## Affected Files

| File | Change Type | Description | Risiko |
|------|-------------|-------------|--------|
| `core/hooks/session_singleton_guard.py` | MODIFY | Heartbeat vorziehen + throtteln; `cwd`/`worktree`/`branch`/`issue`/`phase` nachfuehren; `_harness_agent_name()` | **HOCH** — PreToolUse-Hot-Path, serverweit in 6 Instanzen |
| `core/hooks/workflow.py` | MODIFY | Neues Kommando `sessions` + `COMMANDS`-Eintrag | NIEDRIG (additiv) |
| `tests/test_session_singleton_guard.py` | MODIFY | Heartbeat-im-Worktree, Throttle, Harness-Fallbacks, Issue/Phase | NIEDRIG |
| `tests/test_workflow_sessions.py` | CREATE | Lesepfad gegen Fixture-Lock-Verzeichnis | NIEDRIG |
| `docs/specs/session-singleton-guard.md` | MODIFY | Neufassung — beschreibt heute `<PID>.lock` statt `<session_id>.json` | KEINS funktional, aber irrefuehrend |

`core/hooks/hook_utils.py` bleibt unveraendert; die Issue-Regex liegt lokal im Guard.

## Scope Assessment

- Files: 5 (4 MODIFY, 1 CREATE)
- Estimated LoC: +250 bis +400
- Risk Level: **HIGH** — konzentriert auf `session_singleton_guard.py`

## Technical Approach

1. **Root-Cause-Fix isoliert zuerst** — Heartbeat vorziehen + Throttle. Kleinster Diff, behebt
   AC-2 und AC-4 ohne jede Harness-Abhaengigkeit, eigenstaendig revertierbar.
2. **Gebuendelt mit 1:** `issue` und `phase` am selben Heartbeat nachfuehren, nicht nur bei
   `register` — sonst wird `phase` genauso stale, wie `cwd` es war, sobald der Workflow waehrend
   der Session voranschreitet.
3. **`agent_name`-Anreicherung** — unabhaengig, nur in `_do_register`.
4. **`workflow.py sessions`** — der Lesepfad. Gehoert nach `workflow.py`, nicht als vierter
   Guard-Modus: Der Guard ist strikt Hook-getrieben (stdin-Payload, Ausgabe nur als Blocktext auf
   stderr), waehrend `workflow.py` das passende Muster bereits hat (`COMMANDS`-Dict, manuelles
   Argv-Parsing, Tabellen mit `SEP` + f-string-Spalten). Er liest ausschliesslich
   `.claude/session-locks/*.json` — nie `~/.claude/sessions/`, denn `agent_name` steht dann schon
   im eigenen Register. Ein Schreiber, ein Register.
5. **Spec-Neufassung** — spaetestens in `/30-write-spec`.

## Dependencies

- `hook_utils.resolve_active_workflow()` (Z. 623) — Bruecke zum aktiven Workflow
- `hook_utils.find_project_root()` — Lock-Verzeichnis, worktree-transparent
- `~/.claude/sessions/<pid>.json` — **undokumentiertes Harness-Internal**, nur optional gelesen
- Branch per Dateilesen: `.git` → `gitdir:` → `HEAD` → `ref: refs/heads/<branch>` (verifiziert,
  kein Subprozess)

## Kompatibilitaet

Additive Felder brechen nichts. Einziger produktiver Leser/Schreiber ist
`session_singleton_guard.py`; alle Feldzugriffe laufen ueber `.get()` mit Fallbacks, faktisch
erforderlich ist nur `session_id`. Tests lesen `session_id`, `pid`, `last_seen`. Ausserhalb des
Repos wurde kein Leser gefunden.

## Open Questions

- [ ] Throttle-Schwelle: 60 s vorgeschlagen. Kleiner = genauer, groesser = weniger I/O.
      `_STALE_SECONDS` ist 900 s, also reichlich Sicherheitsabstand.
- [ ] Ausgabeformat von `workflow.py sessions`: Tabelle nach Repo-Konvention. Zusaetzlich ein
      `--json`-Flag fuer maschinelle Nutzung? Das Repo kennt heute kein `--json`.
- [ ] Soll der Lesepfad nur Sessions des eigenen Projekts zeigen (so das Issue) oder alle
      bekannten? `find_project_root()` liefert ohnehin nur das eigene.

## Nicht im Scope (eigene Tickets)

- **gregor_zwanzig fuehrt zwei Lock-Systeme parallel:** `.claude/session-locks/` (Plugin-Format)
  und `.claude/.session-locks/<repo-key>/` mit zusaetzlichem `repo_root`-Feld — eine aeltere,
  handnachgezogene Variante. Da das Projekt kein Plugin-Konsument ist, greift dieser Fix dort
  nicht automatisch. Eigenes Ticket.
- **Echte Claude-PID statt transienter Shell-PID** im Register — waere robuster, zieht aber eine
  Harness-Abhaengigkeit in den Reaping-Pfad. Optionale Folge-Verbesserung.
