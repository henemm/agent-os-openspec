---
entity_id: feat-613-610-sitzungs-backlog
type: feature
created: 2026-11-16
updated: 2026-11-16
status: draft
version: "1.0"
workflow: feat-613-610-sitzungs-backlog
tags: [auftrag, herdr, endstate, next-suggestion, parallel-sessions]
---

# Eigener Backlog je Sitzung: Auftrag an die Sitzung gebunden, Vorschlag aus dem Sitzungs-Epic (Issues #613, #610)

## Approval

- [ ] Approved

## Purpose

Parallele Sitzungen eines Projekts (herdr-Workspaces A, B, C …) sollen jede ihren eigenen Backlog haben:

1. **#613:** Der Mehr-Issue-Auftrag (`.claude/auftrag.json`, #551) gilt heute projektweit. Banner, Statushinweis, `endstate`-Kette und `queue` lesen ihn in **jeder** Sitzung; am 16.11.2026 schlugen drei Sitzungen `/00-intake #3048` vor, das eine vierte schon bearbeitete. Soll: Der Auftrag gehört der Sitzung, die ihn anlegt, und nur sie sieht ihn.
2. **#610:** Nach dem Abschluss schlägt `endstate` per `SUGGEST_SOURCE=priority` ein beliebiges wichtiges Issue vor, auch ein fachfremdes oder eines, das eine andere Sitzung gerade bearbeitet. Soll: In einem herdr-Workspace, dessen Name `#N` enthält, kommt der Vorschlag nur aus den offenen Kindern dieses Epics; Issues, die eine andere Sitzung bearbeitet, fallen weg; ohne passendes Kind gibt es keinen Ersatzvorschlag.

## Source

- Issue #613 (Befund gregor_zwanzig 16.11.2026, PO: „Sorge dafür, dass die Sessions einen eigenen Backlog haben.“)
- Issue #610 (Befund gregor_zwanzig 14.11.2026, Workspace `C · #2913 Einstellungen neu`, Vorschlag #2221 fachfremd)

## Dependencies

- #551 Auftragsliste (`hook_utils.read_auftrag`/`write_auftrag`, `workflow.py queue`), #555 Kette, #591 Spur
- #589 Vorschlag nach dem Abschluss (`next_suggestion.choose`/`fetch`/Cache, `workflow.py endstate`)
- #466/#496 herdr-Bridge (`HERDR_BIN_PATH`, `_pp_quick`), Workspace-Token `wf` (User-Hook `herdr-workflow-status.py`)

## Scope

### Affected Files

| Datei | Änderung |
|-------|----------|
| `core/hooks/hook_utils.py` | `auftrag_owner_key()`, `auftrag_path(root, owner)`, Sitzungsdatei `.claude/auftrag/<key>.json` samt `.gitignore`, Nachfolger nach `/clear` über `CLAUDE_PID`, verwaiste Aufträge (`orphan_auftrag()`, `auftrag_claim_orphans()`), `auftrag_clear()` |
| `core/hooks/workflow.py` | `queue` gibt mit Kennung `OWNER=` und ggf. `ALTAUFTRAG=` aus, neues `queue claim`; `queue clear` löscht nur den eigenen Auftrag; Vorschlag mit Sitzungs-Epic, `SUGGEST_SOURCE=epic-leer` |
| `.gitignore` | `.claude/auftrag/` |
| `core/hooks/herdr_bridge.py` | `parse_session_scope()` (pure) und `session_scope()` (`herdr workspace list`) |
| `core/hooks/next_suggestion.py` | `fetch(..., scope=)` holt die Kinder des Sitzungs-Epics (eine Ebene tiefer bei Unter-Epics), `choose` mit Sitzungs-Epic und belegten Issues, Cache-Schlüssel Workspace |
| `core/commands/60-validate.md`, `core/commands/00-intake.md`, `core/commands/80-workflow.md`, `skills/*` | Texte zu `epic-leer`, Sitzungsbindung, `queue claim` |
| `tests/test_sitzungs_backlog_613_610.py` | neue Tests |
| `CHANGELOG.md`, `README.md` | Unreleased-Eintrag, Pfad des Auftrags |

### Estimated Changes

- `hook_utils.py` ca. +120, `workflow.py` ca. +70, `herdr_bridge.py` ca. +50, `next_suggestion.py` ca. +90, Tests ca. +350.

## Implementation Details

**Sitzungskennung.** `auftrag_owner_key()` liefert `herdr-<HERDR_WORKSPACE_ID>`, sonst `session-<CLAUDE_CODE_SESSION_ID>`, sonst `""`; Zeichen außerhalb `[A-Za-z0-9_.-]` werden zu `_`, höchstens 80 Zeichen. herdr hat Vorrang, weil der Workspace `/clear` und Neustarts der Sitzung überdauert; die Sitzungs-Id ist der Ersatz außerhalb von herdr.

**Ablage.** Mit Kennung liegt der Auftrag in `<Haupt-Repo>/.claude/auftrag/<key>.json` (Ordner mit eigener `.gitignore` `*`, damit Konsumenten-Projekte keinen neuen ungetrackten Ordner sehen), ohne Kennung wie bisher in `<Haupt-Repo>/.claude/auftrag.json`. Jede Datei trägt `owner: {"key", "pid", "boot"}` (`CLAUDE_PID`, Boot-Id), rein informativ bis auf den Nachfolger-Fall. Da jede Sitzung ihre eigene Datei hat, kann keine Sitzung den Auftrag einer anderen sehen, abhaken oder überschreiben (Banner, Statushinweis, `endstate`-Kette, `queue`, Spur, Seitenleiste lesen alle über `read_auftrag`).

**Nachfolger nach `/clear`.** `/clear` vergibt eine neue Sitzungs-Id, der Claude-Prozess (`CLAUDE_PID`) bleibt. Fehlt die eigene `session-*`-Datei, gilt eine andere `session-*`-Datei als eigene, wenn ihr `owner.pid` gleich `CLAUDE_PID` ist und die Boot-Id passt (bzw. eine Seite keine kennt); der nächste Schreibvorgang legt sie unter dem neuen Schlüssel ab und entfernt die alte. herdr-Dateien brauchen das nicht.

**Verwaiste Aufträge (Altbestand).** Verwaist sind eine `.claude/auftrag.json` ohne Besitzer aus früheren Fassungen und `session-*`-Dateien, deren Claude-Prozess (`owner.pid`, Boot-Id) nicht mehr läuft. Für Sitzungen ohne Kennung bleibt `.claude/auftrag.json` der Auftrag (unverändert). Eine Sitzung mit Kennung und ohne eigene Datei liest den neuesten verwaisten Auftrag nur dann als ihren, wenn laut Session-Register (`.claude/session-locks`, Lebendprüfung wie `session_singleton_guard._is_alive`, eigener Eintrag und Einträge mit eigenem `CLAUDE_PID` zählen nicht) keine andere Claude-Sitzung läuft; der nächste Schreibvorgang übernimmt ihn in die eigene Datei und entfernt die Quelle. So arbeitet eine einzelne Sitzung nach dem Update und nach einem Neustart ohne herdr wie bisher weiter. Laufen weitere Sitzungen, kann niemand sagen, wem er gehört; ihn allen zu zeigen ist genau der Fehler aus #613. Dann nennen ihn Statushinweis, Banner, Kette und `endstate` nie; `queue` zeigt ihn nur als `ALTAUFTRAG=<offene Nummern>` mit `HINWEIS=` auf `queue claim`, und `queue claim` übernimmt ihn ausdrücklich (fehlende Nummern hinten, `autark`/`note`/`spur` nur, wenn der eigene Auftrag sie nicht hat) und löscht die Quellen. `OWNER=`/`ALTAUFTRAG=` erscheinen nur mit Kennung, ohne Kennung ist die Ausgabe von `queue` byte-gleich.

**Sitzungs-Epic (#610).** `herdr_bridge.parse_session_scope(payload, workspace)` (pure) liest aus der JSON-Antwort von `herdr workspace list` den eigenen Eintrag (`workspace_id == workspace`); die erste Zahl hinter `#` im `label` ist das Epic. Aus allen anderen Workspaces sammelt sie die `#N` aus dem Token `wf` als belegt. `session_scope()` ruft `herdr workspace list` nur bei `HERDR_ENV=1`, gesetzter `HERDR_WORKSPACE_ID`, gültigem `HERDR_BIN_PATH` und `herdr.enabled` != false auf (Zeitlimit 3 s), sonst oder bei jedem Fehler None.

**Vorschlag.** `next_suggestion.fetch(root, done, timeout_s, scope=None)` legt `raw["session"] = {"epic", "busy", "sub_issues"}` an; mit Epic holt es `issues/E/sub_issues` und für jedes Kind mit offenen Unter-Issues dessen `sub_issues` (eine Ebene, an der Stelle des Kindes eingefügt). `choose` zählt `busy` zu den belegten Nummern. Mit Epic sind die Kandidaten ausschließlich die Kinder in der Reihenfolge der Sub-Issue-Liste (Arbeitsplan), danach offene Issues mit „Teil von #E“ / „Part of #E“ im Text nach Nummer; der erste nicht ausgeschlossene gewinnt, Quelle `epic`. Ohne Kandidat liefert `choose` `{"n": None, "source": "epic-leer", "epic": E, "reason": …}`; die ✅-Zeile nennt dann kein Issue, `endstate` gibt `SUGGEST_SOURCE=epic-leer`, `SUGGEST_EPIC=E` und `SUGGEST_REASON=` (Abschlusskriterium des Epics prüfen) aus. Ohne Epic (kein herdr, Label ohne `#N`) bleibt die bisherige Rangfolge, nur ohne belegte Issues. Ist die Sitzung eine aktive herdr-Sitzung, die Workspace-Liste aber nicht lesbar, gibt es keinen Vorschlag und keinen Cache-Eintrag (lieber keiner als einer außerhalb des Epics; Adversary F002). Eine `session-*`-Datei ohne bekannte PID gilt nie als verwaist (Adversary F001). Der Cache `.claude/next_suggestion.json` trägt den Workspace; eine andere Sitzung verwirft ihn.

## Expected Behavior

- Sitzung A (Workspace w1) legt `queue add 3048 3052` an; Sitzung C (w3) sieht in Banner, Statushinweis, `queue` und `endstate` keinen Auftrag und schlägt #3048 nie vor.
- Nach `/clear` in Sitzung A ist der Auftrag weiter da (herdr: gleicher Workspace; ohne herdr: gleicher Claude-Prozess).
- Sitzung C im Workspace `C · #2913 Einstellungen neu` beendet #3003: die ✅-Zeile nennt das nächste offene Kind von #2913 in Plan-Reihenfolge, nie ein Issue außerhalb, nie eines, das ein anderer Workspace gerade im Token `wf` führt. Sind alle Kinder erledigt oder belegt: ✅ ohne Nummer, `SUGGEST_SOURCE=epic-leer`.
- Ohne herdr und ohne Sitzungs-Id verhält sich alles wie in 4.13.0.

## Known Limitations

- Ohne herdr bindet der Auftrag an den Claude-Prozess: nach einem Neustart von Claude Code (neuer Prozess, neue Sitzungs-Id) findet die Sitzung ihn nur automatisch wieder, wenn sonst keine Sitzung im Projekt läuft; sonst per `queue claim`.
- Die Lebendprüfung stützt sich auf das Session-Register; ein Eintrag, dessen PID ein fremder Prozess recycelt hat (#122), zählt als lebend, dann bleibt der verwaiste Auftrag sicherheitshalber ein Hinweis.
- Das Token `wf` setzt ein Nutzer-Hook (`~/.claude/hooks/herdr-workflow-status.py`), nicht das Plugin; fehlt er, werden nur die Sitzungen aus dem Session-Register ausgeschlossen (wie bisher).
- Unter-Epics werden eine Ebene tief aufgelöst; tiefere Verschachtelung bleibt unsichtbar.
- `/next-ticket` ist ein projekteigener Befehl (gregor_zwanzig) und liegt außerhalb dieses Repos; er kann `workflow.py endstate` bzw. die neuen Funktionen nutzen.

## Definition of Done

- AC-1 bis AC-9 durch `tests/test_sitzungs_backlog_613_610.py` belegt; Bestandstests #551, #555, #589, #591 grün; gesamte Suite grün.
- `scripts/sync_skills.py --check` ohne Drift.

## Acceptance Criteria

- **AC-1:** Given zwei Sitzungen mit verschiedenen `HERDR_WORKSPACE_ID` im selben Projekt / When Sitzung A `queue add 3048 3052` ausführt / Then zeigt `queue` in A `QUEUE=3048,3052` und in B `QUEUE=none`, B kann eigene Nummern anlegen, ohne A zu verändern, und `queue done`/`clear` in B ändern A nicht.
- **AC-2:** Given ein Auftrag von Sitzung A / When Sitzung B `status_note`, Banner-Kontext, `queue_end_args` bzw. `endstate` nach einem fertigen Workflow abfragt / Then nennt keine dieser Ausgaben #3048 und die ✅-Zeile von B enthält kein „aus deinem Auftrag“.
- **AC-3:** Given eine Sitzung ohne herdr mit `CLAUDE_CODE_SESSION_ID=s1` und `CLAUDE_PID=P` / When nach `/clear` die neue Id `s2` mit demselben `CLAUDE_PID` den Auftrag liest und danach schreibt / Then sieht sie den Auftrag, nach dem Schreiben liegt er unter dem Schlüssel `session-s2` und die Datei von `s1` ist weg; eine Sitzung mit anderem `CLAUDE_PID` sieht ihn nicht.
- **AC-4:** Given keine Kennung (weder herdr noch Sitzungs-Id) / When `queue add/list/done/clear` laufen / Then liegt der Auftrag wie bisher in `.claude/auftrag.json`, ohne `owner`, und die Ausgabe enthält kein `OWNER=` (wie in 4.13.0).
- **AC-5:** Given eine besitzerlose `.claude/auftrag.json` mit offenen Nummern und eine weitere lebende Sitzung im Session-Register / When eine Sitzung mit Kennung `queue` aufruft / Then `QUEUE=none`, `ALTAUFTRAG=<Nummern>` mit Hinweis auf `queue claim`, Statushinweis und `endstate` nennen die Nummern nicht; nach `queue claim` stehen sie im eigenen Auftrag und die alte Datei ist gelöscht. Ohne weitere lebende Sitzung liest die einzige Sitzung den verwaisten Auftrag (auch den einer beendeten Sitzung nach einem Neustart) als ihren und übernimmt ihn beim nächsten Schreiben.
- **AC-6:** Given die JSON-Antwort von `herdr workspace list` / When `parse_session_scope` mit der eigenen Workspace-Id läuft / Then ist das Epic die Zahl aus `#N` im eigenen Label (None ohne `#N` oder ohne eigenen Eintrag) und `busy` enthält die `#N` aus dem Token `wf` aller anderen Workspaces, nicht die des eigenen.
- **AC-7:** Given Rohdaten mit Sitzungs-Epic E, dessen Kinder teils geschlossen, teils belegt sind, plus ein höher priorisiertes Issue außerhalb von E / When `choose` läuft / Then ist der Vorschlag das erste freie offene Kind in Plan-Reihenfolge (Quelle `epic`), nie das Issue außerhalb; sind alle Kinder erledigt oder belegt, ist das Ergebnis `n=None`, Quelle `epic-leer`, und die ✅-Zeile von `end_state` nennt keine Nummer.
- **AC-8:** Given ein `gh`-Stub und ein `herdr`-Stub-Binary mit Workspace-Label `C · #2913 …` / When `workflow.py endstate` nach einem fertigen Workflow läuft / Then werden `issues/2913/sub_issues` abgefragt, `SUGGEST_ISSUE` ist ein Kind von #2913 und kein vom Workspace B im `wf`-Token belegtes; ohne freies Kind `SUGGEST_SOURCE=epic-leer`, `SUGGEST_EPIC=2913`, kein `SUGGEST_ISSUE`.
- **AC-9:** Given ein Vorschlags-Cache, den Workspace w1 geschrieben hat / When Workspace w3 ihn liest / Then wird er verworfen (neu geholt), in w1 wird er verwendet.

## Test Plan

- `python -m pytest tests/test_sitzungs_backlog_613_610.py -q` — AC-1 bis AC-9.
- `python -m pytest tests/test_auftrag_551.py tests/test_naechster_vorschlag_589.py tests/test_spur_591.py -q` — Bestand.
- `python -m pytest tests -q` — gesamte Suite.

### Automated Tests (TDD RED)

- Test: `tests/test_sitzungs_backlog_613_610.py` — vor der Umsetzung rot (gemeinsamer Auftrag, kein `parse_session_scope`, kein Epic-Modus).

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Keine neue Architektur: der Auftrag bleibt eine Datei im Haupt-Repo (#551), nur je Sitzung; der Vorschlag bleibt `next_suggestion` (#589) mit einer zusätzlichen, vorrangigen Quelle. herdr bleibt optional und fail-open wie in #466.

## Changelog

- 1.0 (2026-11-16): Erstfassung.
