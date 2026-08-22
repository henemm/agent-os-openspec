---
entity_id: fix-120-121-session-register
type: bugfix
created: 2026-08-21
updated: 2026-08-21
status: draft
workflow: fix-120-121-session-register
version: "1.0"
tags: [bugfix, feature, hooks, session-singleton-guard, workflow-py, tmux, session-register]
test_targets:
  - core/hooks/session_singleton_guard.py
  - core/hooks/workflow.py
  - core/commands/00-intake.md
  - skills/00-intake/SKILL.md
  - tests/test_session_singleton_guard.py
---

# Fix #120 / #121: Session-Register — Liveness-Reparatur, Re-Register-Sicherheitsnetz, Issue-Claim

## Approval

- [ ] Approved

## GitHub Issue

- **Issue #120** — Eine gereapte Session kommt nie zurück, weil `_heartbeat()` bei fehlender
  Lock-Datei aussteigt (`return`), statt einen neuen Eintrag anzulegen. Wurzelursache:
  `_pid_alive()` prüft `Path(f"/proc/{pid}").exists()` statt einer echten Liveness-Prüfung — die
  gespeicherte `pid` (`os.getppid()`, die transiente Hook-Shell) ist bereits beim ersten
  nachfolgenden `guard`-Aufruf tot, sodass praktisch nur `last_seen` trägt.
- **Issue #121** — `/00-intake #N` kennt die Issue-Nummer ab Sekunde eins, gibt sie aber nirgends
  an das Register weiter; `_extract_issue_number()` errät stattdessen die erste Ziffernfolge des
  Workflow-Namens. Bei mehreren Issues pro Workflow (siehe Live-Befund unten) oder Workflow-Namen
  ohne führende Issue-Ziffer liefert das falsche oder gar keine Werte. #121 setzt laut Issue-Text
  #120 voraus (der Claim braucht einen belastbaren Registereintrag, den A2 garantiert).

Beide Issues ändern dieselben Funktionen in `core/hooks/session_singleton_guard.py` und werden
gemeinsam in dieser Spec behandelt.

## Purpose

Das Session-Register (`.claude/session-locks/<session_id>.json`) soll zuverlässig beantworten
können, ob gerade jemand an Issue #N arbeitet. Diese Spec behebt zwei getrennte, aber
zusammenhängende Defekte:

1. **Liveness-Erkennung (A1) + Re-Register-Sicherheitsnetz (A2):** Eine lebende Session darf nie
   dauerhaft aus dem Register verschwinden — weder durch eine kaputte PID-Prüfung noch durch einen
   fehlenden Wiederherstellungspfad, falls die Lock-Datei zwischenzeitlich verloren geht.
2. **Issue-Claim (B1–B3):** `/00-intake #N` trägt die Issue-Nummer(n) aktiv und explizit ins
   Register ein, statt sie aus dem Workflow-Namen zu erraten — mit einer Invalidierungsregel, die
   verhindert, dass ein alter Claim nach einem Themenwechsel dauerhaft falsch bleibt.

## Source

- **File:** `core/hooks/session_singleton_guard.py` (506 Zeilen)
- **Identifier:** `_pid_alive()` (:83), `_is_alive()` (:94), `_extract_issue_number()` (:218),
  `_apply_context_fields()` (:302), `_heartbeat()` (:312), `_do_register()` (:374), `main()` (:487)
- **Zweite Datei:** `core/hooks/workflow.py` — `cmd_sessions()` (:1256), `_read_session_entries()`
  (:1239)
- **Command-Dateien:** `core/commands/00-intake.md`, `skills/00-intake/SKILL.md`

## Live-Befund (empirisch, aus `docs/context/fix-120-121-session-register.md`)

Der eigene Registereintrag dieses Workflows belegt beide Defekte an sich selbst:

- Gespeicherte `pid` war tot (`/proc/<pid>` existiert nicht), obwohl die Session lief —
  `os.kill(pid, 0)` unterscheidet das korrekt (`ProcessLookupError` vs. lebt).
- `CLAUDE_PID` ist eine stabile, lebende PID-Quelle, die der bisherige Code nicht nutzt.
- `CLAUDE_CODE_SESSION_ID` ist byte-identisch mit `session_id` im Eintrag — nutzbar für `claim`.
- Der Workflow hält zwei Issues (#120 **und** #121), das Feld `"issue": "120"` (Regex-Treffer) ist
  unvollständig — der Regex-Bug ist damit am eigenen Workflow nachgewiesen.

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils.find_project_root()` | function | Lock-Verzeichnis, worktree-transparent |
| `hook_utils.resolve_active_workflow()` | function | Aktiver Workflow-Name für Claim-Adoption/-Invalidierung |
| `os.kill(pid, 0)` | stdlib | Plattformneutrale Liveness-Prüfung (ersetzt `/proc`-Check) |
| `CLAUDE_PID` (Env-Var) | undokumentiertes Harness-Internal | Stabile PID-Quelle für `_do_register` |
| `CLAUDE_CODE_SESSION_ID` (Env-Var) | undokumentiertes Harness-Internal | Session-Identifikation für `claim` |
| `/proc/sys/kernel/random/boot_id` | Linux-spezifisch | Schutz gegen PID-Recycling nach Reboot |
| `$TMUX` / `tmux`-Binary | externe Abhängigkeit (neu, kein Bestandsmuster) | Fenstername im Claim-Modus |
| `config_loader.load_config()` | function | Schaltet `tmux_rename` ab (`session_register.tmux_rename`) |

## Scope

### Affected Files

| File | Change Type | Description | Risiko |
|------|-------------|--------------|--------|
| `core/hooks/session_singleton_guard.py` | MODIFY | `_pid_alive` auf `os.kill`; `boot_id`-Schutz in `_is_alive`; `_do_register` liest `CLAUDE_PID`; `_heartbeat` legt bei fehlender Datei neu an; neuer Modus `claim`; neue Helfer `_build_entry`, `_read_boot_id`, `_resolve_register_pid`, `_do_claim`, `_find_claim_target`, `_maybe_rename_tmux_window` | **HOCH** — PreToolUse-Hot-Path, serverweit aktiv |
| `core/hooks/workflow.py` | MODIFY | `cmd_sessions()` Issue-Spalte 5→9 Zeichen, Trenner angepasst, lange Werte abgeschnitten | NIEDRIG |
| `docs/specs/feat-106-session-register.md` | MODIFY | AC-11 als überholt markiert, Verweis auf diese Spec | KEINS funktional |
| `core/commands/00-intake.md` | MODIFY | Claim-Aufruf am Anfang, sobald Issue-Nummer bekannt | NIEDRIG |
| `skills/00-intake/SKILL.md` | MODIFY | Gleicher Claim-Aufruf über `${_H}`-Auflösung | NIEDRIG |
| `tests/test_session_singleton_guard.py` | MODIFY | Neue Tests für A1/A2/B1/B2/B3; **ein** Bestandstest umgeschrieben (`test_guard_without_lock_file_creates_nothing`) | NIEDRIG |

### Estimated Changes

- Files: 6 (5 MODIFY am Code/Docs, plus die o.g. Testdatei)
- LoC: +250/-30 (Schätzung, konzentriert auf `session_singleton_guard.py`)

## Implementation Details

### A1 — Liveness-Erkennung reparieren (#120, Wurzelursache)

`_pid_alive(pid)` (:83-87) wird von `Path(f"/proc/{pid}").exists()` auf `os.kill(pid, 0)`
umgestellt:

```
_pid_alive(pid):
    ProcessLookupError → False (Prozess existiert nicht)
    PermissionError    → True  (Prozess existiert, gehört fremdem User)
    sonstige Exception → False (fail-safe wie bisher)
```

**Sicherheitspflicht (M2):** Die PID wird vor dem Aufruf validiert — `isinstance(pid, int) and not
isinstance(pid, bool) and pid > 0`. `os.kill(0, 0)` adressiert die gesamte Prozessgruppe des
Aufrufers, negative Werte eine ganze Prozessgruppen-ID; beides muss ausgeschlossen werden, bevor
`os.kill` überhaupt aufgerufen wird. Diese Validierung sitzt in `_is_alive()`, nicht in
`_pid_alive()` selbst (Aufrufer-Verantwortung, analog zur bisherigen `isinstance`-Prüfung an
gleicher Stelle).

Nebeneffekt: Diese Umstellung ist auf jeder Plattform mit `os.kill` korrekt (auch macOS, wo
`/proc` nicht existiert und die Funktion heute für JEDE PID `False` liefert — ein Bestandsfehler,
der nebenbei mitbehoben wird).

**`_do_register()` (:402):** Neue Helferfunktion `_resolve_register_pid() -> int` liest
`CLAUDE_PID` aus der Umgebung; ist der Wert eine plausible positive Ganzzahl (`int(...) > 0`),
wird sie zurückgegeben; in jedem anderen Fall (fehlt, leer, kein int, `<= 0`, Exception)
unverändert `os.getppid()`. Lokal try/except-gekapselt.

**Neues Feld `boot_id`:** Neue Helferfunktion `_read_boot_id() -> str | None`, liest
`/proc/sys/kernel/random/boot_id`, vollständig try/except (nicht lesbar, z.B. macOS/Windows →
`None`, Feld fehlt im Eintrag). `_is_alive()` (:94) wird erweitert: Ist im Eintrag ein `boot_id`
gespeichert UND die aktuelle `boot_id` lesbar UND beide weichen voneinander ab, wird die
PID-Prüfung **verworfen** (Schutz gegen PID-Recycling nach Reboot) und direkt auf den
`last_seen`-Fallback zurückgefallen — unabhängig davon, was `_pid_alive` zurückgeben würde. Fehlt
`boot_id` im Eintrag (Bestands-Lock-Dateien vor diesem Fix) oder ist die aktuelle `boot_id` nicht
lesbar, verhält sich die Prüfung wie zuvor (kein Misstrauen, PID-Prüfung greift normal —
Rückwärtskompatibilität).

### A2 — Sicherheitsnetz: Re-Register im Heartbeat (#120)

Neue gemeinsame Helferfunktion:

```
_build_entry(session_id, cwd, started_at, *, reregistered=False) -> dict
```

Baut den Basis-Eintrag (`session_id`, `cwd`, `pid` via `_resolve_register_pid()`, `started_at`,
`last_seen=now`, optional `boot_id` via `_read_boot_id()`, optional `reregistered=True`). Wird
sowohl von `_do_register()` als auch vom neuen Re-Register-Zweig in `_heartbeat()` genutzt —
verhindert Drift zwischen zwei Entstehungswegen für denselben Eintragstyp.

`_do_register()` (:374) nutzt `_build_entry()` für den Basis-Eintrag und ruft danach wie bisher
`_harness_agent_name()` sowie (neu, statt des bisherigen `entry.update(_context_fields(cwd))`)
`_apply_context_fields(entry, cwd)` auf — dieselbe Funktion, die auch der Heartbeat nutzt. Das
vereinheitlicht die Claim-Erhalt/-Invalidierungslogik (B2) an einer einzigen Stelle, statt sie in
`_do_register` und `_heartbeat` getrennt zu pflegen.

`_heartbeat()` (:312-367): Existiert die eigene Lock-Datei nicht mehr (z.B. durch externes
Aufräumen, einen abgelaufenen `_reap_dead`-Lauf einer anderen Session, oder manuelles Löschen),
legt der Heartbeat jetzt einen vollständigen Eintrag NEU an, statt mit `return` auszusteigen:

```
own_file fehlt:
    entry = _build_entry(session_id, cwd, started_at=now, reregistered=True)
    (agent_name best-effort ergänzen, einzeln try/except)
    _apply_context_fields(entry, cwd)
    own_file.parent.mkdir(parents=True, exist_ok=True)
    own_file.write_text(json.dumps(entry))
    return   # genau EIN Schreibvorgang, keine weitere Throttle-Logik in diesem Aufruf
```

`started_at` ist nach einem Reap nicht rekonstruierbar → `now`. Zusätzlich wird `reregistered:
true` gesetzt, damit im Register sichtbar bleibt, dass es kein echter Sessionstart war (verhindert,
dass ein zurückgesetztes `started_at` wie eine neue, jüngere Session aussieht, ohne dass das
kenntlich ist). Der bestehende Throttle- und `agent_name`-Zweig (Datei existiert bereits) bleibt
unverändert; der neue Zweig ist ein separater, früher Ausstieg mit genau einem Write — der
60s-Throttle wird dadurch nicht ausgehebelt, weil dieser Zweig nur greift, wenn die Datei fehlt
(kein wiederholtes Schreiben bei jedem Aufruf).

### A3 — AC-11-Revision (feat-106)

`docs/specs/feat-106-session-register.md` AC-11 (:435-437, "guard legt niemals einen Eintrag an")
wird als überholt markiert (Änderungsmarker + Verweis auf `fix-120-121-session-register.md`, siehe
"Nicht mehr gültig" unten). Begründung (muss die Kosten-Nutzen-Abwägung aus feat-106:75-87
ausdrücklich adressieren, nicht als Fußnote):

- feat-106:75-87 wägt bewusst gegen Harness-Abhängigkeit im Hot-Path ab und hält fest, dass ein
  Re-Register-Schreibvorgang bei **jedem** Guard-Aufruf inakzeptabel wäre (PreToolUse, sechs
  Server-Instanzen). A2 tut das nicht: der neue Schreibvorgang läuft ausschliesslich im
  Ausnahmefall (eigene Lock-Datei fehlt) — im Normalbetrieb (Datei vorhanden) bleibt der bestehende
  60s-Throttle unangetastet und unverändert wirksam. Die ursprüngliche Abwägung galt dem
  Normalfall, nicht diesem Ausnahmefall.
- A1 ist damit der **dritte** Anlauf am selben Liveness-Problem (v3.4.9: `last_seen`-Fallback bei
  toter PID; v3.4.10: Heartbeat vor den Worktree-/Tool-Ausstieg gezogen — `CHANGELOG.md:1131-1193`).
  Warum Anlauf 3 anders ausgeht: Anlauf 1 und 2 hatten weder eine stabile PID-Quelle
  (`CLAUDE_PID`, undokumentiert, aber empirisch verfügbar) noch eine funktionierende Prüfmethode
  (`os.kill` statt `/proc/<pid>`, das auf macOS ohnehin nie greift). Ohne A1 wäre A2 nötig, um
  jede tote PID zu kompensieren; mit A1 wird A2 zum reinen Sicherheitsnetz für den selteneren Fall
  einer verlorenen Lock-Datei bei sonst lebender Session.

### B1 — Neuer vierter Modus `claim` (#121)

```
python3 session_singleton_guard.py claim --issue 120,121
```

Neue Helfer:

- `_validate_issue_arg(raw: str) -> str | None` — akzeptiert nur `[0-9,]+` (kommagetrennte
  Ziffern), sonst `None`.
- `_find_claim_target(locks: Path) -> tuple[str, Path, dict | None] | None`:
  1. `CLAUDE_CODE_SESSION_ID` gesetzt → `(session_id, locks/<safe_sid>.json, entry oder None
     falls Datei fehlt)`.
  2. Env-Var fehlt/leer → Fallback: genau ein Eintrag mit `cwd == os.getcwd()` unter den
     vorhandenen Lock-Dateien → dessen `(session_id, path, entry)`. Kein Treffer oder mehr als
     einer → `None`.
- `_do_claim(argv: list[str]) -> None`: parst `--issue`, validiert; ohne gültigen Wert → Meldung
  auf stdout, `sys.exit(0)`, keine Datei berührt. Ist ein Ziel gefunden: existiert noch kein
  Eintrag (Fall 1.b oben), wird er über `_build_entry(..., reregistered=True)` +
  `_apply_context_fields()` angelegt (nutzt denselben A2-Helper — kein dritter
  Eintrags-Entstehungsweg). Danach: `entry["issue"] = <validierter Wert>`,
  `entry["issue_source"] = "claim"`, `entry["issue_claim_workflow"] = <aktueller Workflow-Name
  via resolve_active_workflow() oder "">`, schreiben, Erfolgsmeldung auf stdout,
  `_maybe_rename_tmux_window(...)` aufrufen, `sys.exit(0)`.
- Ist kein eindeutiges Ziel auffindbar (kein `CLAUDE_CODE_SESSION_ID` und 0 oder >1 cwd-Treffer):
  verständliche Meldung auf stdout, kein Schreibvorgang, `sys.exit(0)`.

Anders als die drei Hook-Modi (`register`/`guard`/`cleanup`, die grundsätzlich still bleiben) ist
`claim` ein direkter CLI-Aufruf ohne stdin-Payload — Meldungen auf stdout sind hier gewollt und
Teil des beobachtbaren Verhaltens.

### B2 — Claim-Invalidierung (kritisch)

Erweiterung von `_apply_context_fields()` (:302-310). Bisher: für jedes Feld in
`_CONTEXT_FIELDS` wird der neu ermittelte Wert übernommen oder das Feld entfernt, falls nicht
mehr auflösbar. Neu: das Feld `issue` wird gesondert behandelt, wenn `entry.get("issue_source")
== "claim"`:

```
aktueller Workflow-Name (via resolve_active_workflow(), "" wenn keiner aktiv)
claim_wf = entry.get("issue_claim_workflow")

Fall 1 — claim_wf ist "" (kein Workflow beim Claim aktiv) und aktueller Workflow ist ebenfalls "":
    Claim bleibt unveraendert bestehen, issue_claim_workflow bleibt "".
Fall 2 — claim_wf ist "" und jetzt erstmals ein Workflow aufloesbar (aktueller Workflow != ""):
    Die Adoption ist an eine Pruefung gebunden. Sei n = _extract_issue_number(aktueller Workflow):

    Fall 2a — n ist None (Workflow-Name ohne Ziffernfolge, z.B. 'retro-cleanup'):
        ADOPTIEREN. issue_claim_workflow wird einmalig gesetzt, issue bleibt unveraendert.
        Begruendung: ein nummernloser Name widerspricht dem Claim nicht, und die Regex-Ableitung
        haette hier ohnehin nichts anzubieten.
    Fall 2b — n ist in der geclaimten Liste enthalten (issue.split(",")):
        ADOPTIEREN wie 2a.
    Fall 2c — n ist gesetzt, aber NICHT in der geclaimten Liste (z.B. Claim '120',
        Workflow 'fix-500-xyz' -> n='500'):
        NICHT adoptieren, sondern sofort VERFALLEN wie Fall 4.
        Ohne diese Pruefung wuerde ein fremder Workflow den Claim adoptieren; danach kann Fall 4
        nie mehr greifen, weil claim_wf und aktueller Workflow ab dann uebereinstimmen — der
        falsche Wert waere dauerhaft eingefroren. Genau das Szenario, gegen das B2 gebaut ist.
Fall 3 — claim_wf == aktueller Workflow (beide nicht-leer, identisch):
    Claim gilt weiter, issue bleibt unveraendert, issue_claim_workflow unveraendert.
Fall 4 — claim_wf != aktueller Workflow (Abweichung, gleich ob claim_wf leer+aktuell gesetzt
    faellt unter Fall 2, oder claim_wf gesetzt+aktuell abweichend/leer):
    Claim verfaellt: issue, issue_source, issue_claim_workflow werden aus dem Eintrag entfernt.
    Anschliessend greift die normale Regex-Ableitung (wie vor dieser Spec) fuer 'issue' —
    liefert resolve_active_workflow()+_extract_issue_number() etwas, wird es gesetzt, sonst
    bleibt 'issue' abwesend.
```

Fehlt `issue_source` (kein Claim aktiv) → unverändertes Bestandsverhalten (`issue` wird per Regex
gesetzt/entfernt wie vor dieser Spec).

### B3 — tmux-Fenstername

Neue Helferfunktion `_maybe_rename_tmux_window(issue_value: str) -> None`, ausschliesslich von
`_do_claim` aufgerufen, vollständig fail-safe:

```
kein $TMUX gesetzt          → return, keine weitere Aktion
config tmux_rename == False → return (config_loader.load_config() lazy importiert,
                                try/except, Default True bei jedem Ladefehler)
tmux nicht in PATH          → return (shutil.which("tmux") is None)
subprocess.run(["tmux", "rename-window", f"#{issue_value}"], timeout=2) wirft/timeout/exit!=0
                             → ignorieren, kein Re-raise
```

Kein Aufrufpfad darf eine Exception nach `_do_claim` durchlassen — der komplette Funktionskörper
liegt in `try/except Exception: pass`. Konfigurationsschlüssel: `session_register.tmux_rename`
(Default `true`), gelesen wie andere Hooks via `config_loader.load_config()` (Muster analog
`get_scope_loc_config()` in `config_loader.py`).

**Known Limitation:** `grep -rn "tmux" .` liefert vor dieser Änderung 0 Treffer im Repo — es
existiert kein Bestandsmuster für einen externen Prozessaufruf dieser Art. Diese Spec führt tmux
als neue, optionale, strikt fail-safe externe Abhängigkeit ein.

### B4 — Command-Dateien

Beide Dateien bekommen denselben Claim-Schritt, **nicht automatisch synchronisiert**:

- `core/commands/00-intake.md`: neuer Abschnitt vor "### 2. Score präsentieren…", der — sobald die
  Issue-Nummer aus dem Aufgaben-Kontext bekannt ist — ausführt:
  ```bash
  python3 .claude/hooks/session_singleton_guard.py claim --issue <N>[,<M>...]
  ```
- `skills/00-intake/SKILL.md`: gleicher Schritt, aber über die bestehende `${_H}`-Auflösung aus dem
  `## Setup`-Block:
  ```bash
  python3 ${_H}/session_singleton_guard.py claim --issue <N>[,<M>...]
  ```
- Platzierung in beiden Dateien: **vor** der Track-Bewertung (Abschnitt "Score präsentieren"),
  nicht erst beim Workflow-Start — der Claim braucht keinen laufenden Workflow (Fall 1/2 aus B2
  deckt das ab).

### B5 — `workflow.py cmd_sessions()` — Anzeige

`_read_session_entries()` (:1239) unverändert. In `cmd_sessions()` (:1256-1290):

- Spaltenbreite `Issue` von `<5` auf `<9` erhöht (passt z.B. `"120,121"` mit 7 Zeichen ohne
  Umbruch, mit Puffer).
- `SEP = "─" * 151` entsprechend um die Differenz (4 Zeichen) auf `"─" * 155` erhöht.
- Werte länger als 9 Zeichen werden auf 9 Zeichen abgeschnitten (z.B. mit `…`-Suffix oder
  Hart-Cut nach Bestandskonvention `col(...)`), statt die Spalte zu sprengen.

## Expected Behavior

- **EB-Fail-Safe (übergreifend):** Jede neue Datenquelle (`CLAUDE_PID`, `boot_id`,
  `CLAUDE_CODE_SESSION_ID`, `tmux`, `config_loader`) ist einzeln in `try/except` gekapselt. Fehlt
  eine Quelle, bleibt das bisherige Verhalten exakt erhalten — zusätzlich zum äusseren
  `except Exception: sys.exit(0)`-Fangnetz in `main()`.
- **EB-Rückwärtskompatibilität:** Bestehende Lock-Dateien ohne `boot_id`, `reregistered`,
  `issue_source`, `issue_claim_workflow` funktionieren unverändert weiter — diese Felder sind rein
  additiv und werden bei ihrer Abwesenheit als "nicht gesetzt" behandelt, nie als Fehler.

## Acceptance Criteria

- **AC-1:** Given eine PID eines aktuell laufenden, eigenen Prozesses, When `_pid_alive(pid)`
  aufgerufen wird, Then liefert es `True` über `os.kill(pid, 0)` (kein `ProcessLookupError`).
- **AC-2:** Given eine PID, die keinem laufenden Prozess entspricht, When `_pid_alive(pid)`
  aufgerufen wird, Then liefert es `False` (`ProcessLookupError` abgefangen).
- **AC-3:** Given eine PID eines laufenden, aber fremden Prozesses (z.B. PID 1, `PermissionError`
  bei `os.kill`), When `_pid_alive(pid)` aufgerufen wird, Then liefert es `True` (Prozess
  existiert, Berechtigungsfehler ist kein Tot-Signal).
- **AC-4:** Given ein Registereintrag mit `pid == 0` oder `pid < 0` oder `pid` kein `int`, When
  `_is_alive(entry, now)` aufgerufen wird, Then wird `os.kill` NICHT mit dieser PID aufgerufen
  (Prozessgruppen-Schutz) und auf den `last_seen`-Fallback zurückgefallen.
- **AC-5:** Given `_pid_alive` wirft eine unerwartete, andere Exception als `ProcessLookupError`
  oder `PermissionError`, When es aufgerufen wird, Then liefert es `False` (fail-safe wie bisher).
- **AC-6:** Given `CLAUDE_PID` ist in der Umgebung gesetzt und eine plausible positive Ganzzahl,
  When `_do_register()` einen neuen Eintrag anlegt, Then steht im gespeicherten Eintrag
  `pid == int(CLAUDE_PID)`.
- **AC-7:** Given `CLAUDE_PID` fehlt, ist leer, kein Integer, `0` oder negativ, When
  `_do_register()` einen neuen Eintrag anlegt, Then steht im Eintrag `pid == os.getppid()`
  (unverändertes Bestandsverhalten).
- **AC-8:** Given `/proc/sys/kernel/random/boot_id` ist lesbar, When `_do_register()` einen neuen
  Eintrag anlegt, Then enthält der Eintrag ein Feld `boot_id` mit dem gelesenen Wert.
- **AC-9:** Given `/proc/sys/kernel/random/boot_id` ist nicht lesbar (Datei fehlt oder wirft),
  When `_do_register()` einen neuen Eintrag anlegt, Then fehlt `boot_id` im Eintrag, kein Fehler.
- **AC-10:** Given ein Eintrag mit gespeicherter `boot_id`, die von der aktuellen `boot_id`
  abweicht, und einer laut `os.kill` lebenden PID, When `_is_alive(entry, now)` aufgerufen wird,
  Then wird die PID-Prüfung verworfen und stattdessen ausschliesslich `last_seen` gegen
  `_STALE_SECONDS` geprüft.
- **AC-11:** Given ein Eintrag ohne `boot_id`-Feld (Bestands-Lock-Datei vor diesem Fix), When
  `_is_alive(entry, now)` aufgerufen wird, Then verhält sich die PID-Prüfung wie ohne
  Boot-ID-Schutz (kein Misstrauen, `os.kill`-Ergebnis zählt).
- **AC-12:** Given ein Eintrag mit gespeicherter `boot_id`, aber die aktuelle `boot_id` ist nicht
  lesbar, When `_is_alive(entry, now)` aufgerufen wird, Then verhält sich die PID-Prüfung
  unverändert (kein Vergleich möglich, kein Misstrauen).
- **AC-13:** Given ein Registereintrag mit `started_at` vor mehr als `_STALE_SECONDS`, toter PID
  (nach A1 korrekt erkannt) UND `last_seen` ebenfalls stale, When ein `_do_guard`-Aufruf für eine
  ANDERE, tatsächlich tote Session-ID stattfindet, Then reapt `_reap_dead` diesen fremden Eintrag
  weiterhin regulär (A1 darf keine tote Session künstlich am Leben halten).
- **AC-14:** Given die eigene Lock-Datei einer Session existiert nicht mehr (z.B. extern gelöscht),
  When `_do_guard()` mit einem beliebigen Tool aufgerufen wird, Then existiert danach eine neue
  Lock-Datei für diese `session_id` mit `reregistered: true` und `started_at` gleich dem
  Aufrufzeitpunkt (nicht rekonstruierbar).
- **AC-15:** Given derselbe Fall wie AC-14, When der Re-Register-Zweig in `_heartbeat()` läuft,
  Then wird genau EIN Schreibvorgang ausgelöst (kein zusätzlicher Write durch den normalen
  Throttle-Zweig im selben Aufruf).
- **AC-16:** Given eine bereits vorhandene, aktuelle Lock-Datei (kein Re-Register-Fall), When
  `_do_guard()` innerhalb des 60s-Throttle-Fensters erneut aufgerufen wird, Then bleibt das
  Bestandsverhalten (höchstens ein Write pro Throttle-Fenster) unverändert erhalten — der neue
  Re-Register-Zweig hebelt den Throttle nicht aus.
- **AC-17:** Given `_do_register()` und der Re-Register-Zweig aus `_heartbeat()` werden mit
  identischer `session_id`/`cwd`/`started_at` aufgerufen (unterschiedliche Aufrufstellen), When
  beide erzeugten Einträge verglichen werden, Then enthalten beide dieselben Pflichtfelder
  (`session_id`, `cwd`, `pid`, `started_at`, `last_seen`) über denselben Helper `_build_entry()`
  (keine Feld-Drift zwischen den zwei Entstehungswegen).
- **AC-18:** Given `docs/specs/feat-106-session-register.md`, When die Datei nach dieser Änderung
  gelesen wird, Then ist AC-11 dort explizit als überholt markiert mit Verweis auf
  `fix-120-121-session-register.md`.
- **AC-19:** Given `CLAUDE_CODE_SESSION_ID` ist gesetzt und passt zu einem vorhandenen
  Registereintrag, When `python3 session_singleton_guard.py claim --issue 120,121` aufgerufen
  wird, Then enthält der Eintrag danach `issue == "120,121"`, `issue_source == "claim"` und
  `issue_claim_workflow` gleich dem zum Claim-Zeitpunkt aktiven Workflow-Namen (oder `""`, falls
  keiner aktiv).
- **AC-20:** Given `CLAUDE_CODE_SESSION_ID` ist nicht gesetzt, aber genau EIN Registereintrag hat
  `cwd == os.getcwd()`, When `claim --issue 42` aufgerufen wird, Then wird genau dieser Eintrag mit
  den Claim-Feldern versehen.
- **AC-21:** Given weder `CLAUDE_CODE_SESSION_ID` noch ein eindeutiger `cwd`-Treffer (0 oder ≥2
  Kandidaten), When `claim --issue 42` aufgerufen wird, Then wird KEINE Datei verändert, eine
  verständliche Meldung erscheint auf stdout, und der Prozess beendet sich mit Exit-Code 0.
- **AC-22:** Given `CLAUDE_CODE_SESSION_ID` ist gesetzt, aber für diese Session existiert noch kein
  Lock-Eintrag, When `claim --issue 42` aufgerufen wird, Then wird über `_build_entry()` (A2-Helper)
  ein neuer Eintrag angelegt und direkt mit den Claim-Feldern geschrieben.
- **AC-23:** Given `--issue` enthält nur Ziffern und Kommas (z.B. `"120,121"`), When `claim`
  aufgerufen wird, Then wird der Wert unverändert akzeptiert und übernommen.
- **AC-24:** Given `--issue` enthält andere Zeichen (z.B. `"120; rm -rf /"`, `"abc"`, `"12.3"`),
  When `claim` aufgerufen wird, Then wird der Aufruf mit einer Meldung abgelehnt, KEINE Datei
  verändert, Exit-Code 0.
- **AC-25:** Given `_do_claim()` läuft, When `register`/`guard`/`cleanup` im selben Testlauf
  aufgerufen werden, Then bleiben diese drei Modi vollständig still auf stdout (unverändertes
  Bestandsverhalten), während `claim` als einziger Modus stdout-Meldungen ausgibt.
- **AC-26 (B2, Fall 1):** Given ein Claim mit `issue_claim_workflow == ""` (kein Workflow beim
  Claim aktiv) UND weiterhin kein aktiver Workflow auflösbar, When der Heartbeat läuft, Then
  bleiben `issue`, `issue_source` und `issue_claim_workflow` unverändert bestehen.
- **AC-27 (B2, Fall 2a — passende Adoption):** Given ein Claim mit `issue_claim_workflow == ""`,
  When danach erstmals ein aktiver Workflow auflösbar wird (`resolve_active_workflow()` liefert
  einen Namen) UND `_extract_issue_number()` auf diesen Namen eine Nummer liefert, die in der
  geclaimten Liste enthalten ist (z.B. Claim `"120,121"`, Workflow `fix-120-121-session-register`
  → `"120"` ist enthalten), und der Heartbeat läuft, Then wird `issue_claim_workflow` auf diesen
  Workflow-Namen gesetzt ("adoptiert"), `issue` bleibt unverändert.
- **AC-39 (B2, Fall 2b — fremde Adoption verfällt):** Given ein Claim mit
  `issue_claim_workflow == ""`, When erstmals ein aktiver Workflow auflösbar wird, dessen per
  `_extract_issue_number()` abgeleitete Nummer NICHT in der geclaimten Liste enthalten ist (z.B.
  Claim `"120"`, danach Workflow `fix-500-xyz` → `"500"`), Then wird der Claim NICHT adoptiert,
  sondern verfällt sofort: `issue`, `issue_source` und `issue_claim_workflow` werden entfernt und
  die Regex-Ableitung übernimmt (identisches Ergebnis wie AC-29). Deckt den Themenwechsel ohne
  erneuten Intake-Lauf ab — ohne diese Regel friert ein einmal adoptierter Fremd-Workflow den
  falschen Wert dauerhaft ein, weil AC-29 danach nie mehr greifen kann.
- **AC-40 (B2, Fall 2c — Workflow ohne Nummer):** Given ein Claim mit
  `issue_claim_workflow == ""`, When erstmals ein aktiver Workflow auflösbar wird, dessen Name
  keine Ziffernfolge enthält (z.B. `retro-cleanup`, vgl. AC-9 in feat-106), Then wird der Claim
  adoptiert wie in AC-27 — ein nummernloser Workflow-Name ist kein Widerspruch zum Claim, und die
  Regex-Ableitung hätte hier ohnehin nichts zu bieten.
- **AC-28 (B2, Fall 3):** Given `issue_claim_workflow` ist gesetzt und stimmt mit dem aktuell
  aufgelösten Workflow überein, When der Heartbeat läuft, Then bleiben `issue` und
  `issue_claim_workflow` unverändert (Claim gilt weiter).
- **AC-29 (B2, Fall 4):** Given `issue_claim_workflow` ist gesetzt und weicht vom aktuell
  aufgelösten Workflow ab (Themenwechsel), When der Heartbeat läuft, Then werden `issue`,
  `issue_source` und `issue_claim_workflow` aus dem Eintrag entfernt, und die Regex-Ableitung
  (`_extract_issue_number()` auf den neuen Workflow-Namen) übernimmt `issue` wieder wie vor dieser
  Spec.
- **AC-30:** Given `$TMUX` ist gesetzt, `tmux` ist im PATH, `session_register.tmux_rename` ist
  nicht auf `false` gesetzt, When `claim --issue 42` erfolgreich abschliesst, Then wird
  `tmux rename-window` mit den geclaimten Nummern aufgerufen.
- **AC-31:** Given `$TMUX` ist NICHT gesetzt, When `claim` aufgerufen wird, Then wird `tmux`
  nicht aufgerufen, kein Fehler, kein Output dazu.
- **AC-32:** Given `tmux` ist nicht im PATH, ODER der Aufruf läuft in einen Timeout, ODER er
  beendet sich mit Exit-Code ≠ 0, When `claim` aufgerufen wird, Then wird das silent ignoriert —
  kein Abbruch von `_do_claim`, keine Exception verlässt `_maybe_rename_tmux_window`.
- **AC-33:** Given `session_register.tmux_rename` ist per Config auf `false` gesetzt, When
  `claim` mit gesetztem `$TMUX` aufgerufen wird, Then wird `tmux rename-window` NICHT aufgerufen.
- **AC-34:** Given `core/commands/00-intake.md`, When die Datei nach dieser Änderung gelesen wird,
  Then enthält sie einen Claim-Aufruf `python3 .claude/hooks/session_singleton_guard.py claim
  --issue ...` VOR dem Abschnitt "Score präsentieren".
- **AC-35:** Given `skills/00-intake/SKILL.md`, When die Datei nach dieser Änderung gelesen wird,
  Then enthält sie einen Claim-Aufruf über `python3 ${_H}/session_singleton_guard.py claim
  --issue ...` an derselben relativen Stelle (vor der Track-Bewertung).
- **AC-36:** Given `python3 core/hooks/workflow.py sessions` wird mit einem Registereintrag
  ausgeführt, dessen `issue`-Wert `"120,121"` lautet (7 Zeichen), When die Tabelle ausgegeben
  wird, Then erscheint der volle Wert ohne Abschneiden und ohne die Spaltenausrichtung zu
  sprengen (Spaltenbreite 9).
- **AC-37:** Given ein `issue`-Wert länger als 9 Zeichen, When `cmd_sessions()` die Tabelle baut,
  Then wird der Wert auf 9 Zeichen gekürzt statt die Spalte zu sprengen.
- **AC-38 (Regression):** Given die 37 bestehenden Tests in `tests/test_session_singleton_guard.py`
  vor dieser Änderung, When die Datei nach der Änderung ausgeführt wird, Then sind 36 davon
  unverändert grün; die einzige benannte Ausnahme ist `test_guard_without_lock_file_creates_nothing`
  (:568-582), die durch A2 bewusst ungültig wird und im Rahmen dieser Spec umgeschrieben werden muss
  auf: "GIVEN keine Lock-Datei für die `session_id`, WHEN `_do_guard` aufgerufen wird, THEN wird
  jetzt ein neuer Eintrag mit `reregistered: true` angelegt" (vormals: "es wird KEINE Datei
  angelegt").

## Edge Cases

- **EB-1:** `CLAUDE_PID` fehlt in der Umgebung → `_do_register()` fällt unverändert auf
  `os.getppid()` zurück (AC-7).
- **EB-2:** `CLAUDE_PID` ist unplausibel (`"0"`, `"-5"`, `"abc"`, leer) → wird verworfen, gleiche
  Behandlung wie EB-1 (AC-7).
- **EB-3:** `boot_id` ist nicht lesbar (Plattform ohne `/proc`, Berechtigungsfehler) →
  `_read_boot_id()` liefert `None`, Feld fehlt, keine Auswirkung auf `_is_alive` (AC-9, AC-12).
- **EB-4:** Gespeicherte `boot_id` weicht von der aktuellen ab (Reboot, PID-Recycling) → PID-Prüfung
  wird verworfen, `last_seen`-Fallback entscheidet (AC-10).
- **EB-5 (Race):** `cleanup` (SessionEnd) läuft, löscht die eigene Lock-Datei; unmittelbar danach
  trifft noch ein verspäteter `guard`-Aufruf derselben (bereits beendeten) Session ein → der
  Re-Register-Zweig aus A2 legt die Datei erneut an (`reregistered: true`, `started_at = now`).
  Der Eintrag verwaist danach. Ob er wieder verschwindet, hängt allein davon ab, was die
  gespeicherte `pid` zum Prüfzeitpunkt ist:
  - **Ist die PID tot** (Normalfall), entfernt `_reap_dead` den Eintrag nach `_STALE_SECONDS`,
    sobald irgendeine Session den nächsten `guard`-Aufruf macht.
  - **Hat inzwischen ein fremder, lebender Prozess dieselbe PID belegt** (PID-Recycling innerhalb
    desselben Boots), liefert `_is_alive()` dauerhaft `True` und der Eintrag wird **nie** entfernt —
    unabhängig davon, wie alt `last_seen` ist. Der `boot_id`-Schutz aus A1 greift hier
    ausdrücklich NICHT: er erkennt nur einen Reboot, nicht die Wiederverwendung einer PID im
    laufenden Boot.

  Das ist **kein** durch diese Spec eingeführter Defekt: der Vorgängercode
  (`Path("/proc/<pid>").exists()`) liefert bei einer recycelten PID genauso `True`. A1 verändert
  das Verhalten in diesem Fall weder zum Besseren noch zum Schlechteren. Behandlung deshalb
  bewusst außerhalb dieser Spec, in einem eigenen Folge-Issue (siehe Known Limitations).

  **Korrektur (2026-08-21):** Frühere Fassungen dieses Abschnitts behaupteten, der verwaiste
  Eintrag werde „nach `_STALE_SECONDS` regulär durch `_reap_dead` entfernt" und der Fall sei
  „per Test abgedeckt". Beides war unzutreffend — die Entfernung gilt nur bei toter PID (s.o.),
  und einen Test dafür gibt es nicht: alle Dead-PID-Tests verwenden `999999999`, eine PID, die
  nie lebt und damit genau den kritischen Fall nicht trifft.
- **EB-6:** Ein per `Task`/`Agent` gestarteter Sub-Agent ruft `claim` auf → überschreibt den
  Parent-Eintrag (beide teilen dieselbe `CLAUDE_CODE_SESSION_ID`, siehe M1 im Context-Doc). Bekannte
  Einschränkung, NICHT technisch verhindert — `claim` wird laut Konvention ausschliesslich aus
  `/00-intake` heraus aufgerufen, nie von Agenten.
- **EB-7:** `--issue` enthält ungültige Zeichen (Shell-Metazeichen, Buchstaben, Leerzeichen,
  Punkte) → Ablehnung mit Meldung, kein Schreibvorgang, Exit 0 (AC-24).
- **EB-8:** Kein Lock-Eintrag existiert für die aktuelle Session UND kein eindeutiger
  `cwd`-Treffer (0 oder mehrere Kandidaten) → `claim` ändert nichts, verständliche Meldung, Exit 0
  (AC-21).

## Nicht im Scope

- **Datei-Ebene im Register** ("fasst jemand `alert/render.py` an?", Nebenbeobachtung 2 aus #120)
  — eigenständiger, deutlich größerer Wunsch, gehört in ein separates Issue.
- **Ablösung der `SendMessage`-Rundfragen** — mögliche Folge dieser Änderung, aber nicht
  Gegenstand dieser Spec.

## Known Limitations

- `boot_id`-Schutz ist Linux-spezifisch (`/proc/sys/kernel/random/boot_id`); auf anderen
  Plattformen bleibt der bisherige, weniger präzise PID-Schutz (ohne Boot-Kontext) bestehen.
- `tmux` ist eine neue, im Repo bislang ungenutzte externe Abhängigkeit (B3) — strikt optional
  und fail-safe, aber ein neues Wartungs-Oberflächenstück.
- `claim` unterscheidet nicht zwischen Parent-Session und Sub-Agent derselben Session (EB-6) —
  bewusste Konventions-Grenze, keine technische Absicherung.
- `core/commands/00-intake.md` und `skills/00-intake/SKILL.md` bleiben zwei unabhängig gepflegte
  Kopien; ein künftiger Drift zwischen beiden ist durch diese Spec nicht ausgeschlossen.
- Innerhalb des 60s-Heartbeat-Throttle-Fensters kann ein per B2 invalidierter Claim bis zu 60s
  nachwirken, bevor die Regex-Ableitung ihn ersetzt — analog zum bestehenden Trade-off aus
  feat-106 für alle throttled Felder.
- **PID-Recycling im laufenden Boot (Bestandsproblem, eigenes Folge-Issue):** Belegt ein fremder,
  lebender Prozess dieselbe PID wie ein toter Registereintrag, gilt dieser Eintrag dauerhaft als
  lebend und wird nie gereapt — `last_seen` kann beliebig alt sein. `boot_id` schützt nur gegen
  Reboot, nicht gegen Recycling im selben Boot. Der Vorgängercode
  (`Path("/proc/<pid>").exists()`) verhält sich identisch; A1 führt das Problem weder ein noch
  verschärft es. Bewusst nicht in dieser Spec behandelt (Scope-Erweiterung mitten im Fix-Zyklus),
  siehe EB-5.
- **Tabellenausrichtung in `cmd_sessions()` (B5):** Gekürzt wird ausschliesslich die
  `Issue`-Spalte (9 Zeichen) — sie ist die einzige, die durch den Claim mehrere Werte aufnehmen
  kann und deren Inhalt manipulierbar ist. Alle übrigen Spalten sind so bemessen, dass die
  Namenskonvention dieses Projekts (`typ-NNN[-MMM]-beschreibung`) vollständig hineinpasst:
  `session_id` 36 (UUID), `agent_name` 20, `worktree` 21, `branch` 30, `workflow` 30, `phase` 18.
  Zwei Grenzen bleiben:
  - Werte **oberhalb** dieser Breiten (z.B. ein Branch-Name > 30 Zeichen) werden nicht gekürzt und
    verschieben die nachfolgenden Spalten dieser Zeile — die Ausrichtung bricht dann, wie schon vor
    dieser Änderung.
  - Die Breitenrechnung zählt **Zeichen, nicht Darstellungsbreite**. CJK-/Emoji-Zeichen (doppelte
    Zellbreite), ANSI-Sequenzen oder Steuerzeichen (Tab, Newline) in einem Branch- oder
    Workflow-Namen brechen die Ausrichtung weiterhin.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine (Repo führt kein separates ADR-Log, siehe feat-106-Präzedenz)
- **Rationale:** Diese Spec revidiert eine bereits freigegebene AC einer Vorgänger-Spec (AC-11 aus
  `feat-106-session-register.md`) — das ist eine Architektur-Entscheidung und wird hier begründet,
  statt sie als Implementierungsdetail zu behandeln. Kern der Entscheidung: die
  Kosten-Nutzen-Abwägung aus feat-106 (kein Re-Register im Hot-Path) betraf den **Normalfall**
  (Lock-Datei vorhanden, throttled). A2 schreibt ausschliesslich im **Ausnahmefall** (Lock-Datei
  fehlt) — eine Situation, die feat-106 nicht in Betracht gezogen hatte, weil sie zum
  Verfassungszeitpunkt noch nicht als Fehlerquelle bekannt war (das Fehlen selbst ist Symptom von
  #120, nicht Ursache). Die Abwägung von feat-106 bleibt für den Normalfall unverändert korrekt und
  gültig; A2 erweitert sie nur um den zuvor unbehandelten Ausnahmefall. Zusätzlich: A1 ist der
  dritte Versuch am selben Liveness-Problem (v3.4.9, v3.4.10, jetzt A1) — die Entscheidung, es
  trotzdem erneut zu versuchen, stützt sich auf zwei diesmal neu verfügbare, empirisch belegte
  Fakten (`CLAUDE_PID` als stabile Quelle, `os.kill` als funktionierende Prüfmethode), die den
  vorigen beiden Anläufen fehlten.

## Changelog

- 2026-08-21: Initial spec created
- 2026-08-21: AC-27 praezisiert und AC-39/AC-40 ergaenzt — die Adoption eines Claims durch den
  erstmals auflösbaren Workflow ist jetzt an eine Nummern-Prüfung gebunden. Ohne sie konnte ein
  fremder Workflow den Claim adoptieren, wodurch AC-29 (Verfall bei Abweichung) danach nie mehr
  greifen konnte und ein falscher Wert dauerhaft eingefroren blieb. Die drei B2-Fall-2-Varianten
  stehen bewusst bei den übrigen B2-ACs statt am Listenende, damit alle Invalidierungsregeln
  beisammen bleiben; die Nummerierung ist dadurch nicht in Dateireihenfolge aufsteigend.
- 2026-08-21: EB-5 wahrheitsgemäß korrigiert (Adversary-Finding F001). Die bisherige Aussage, der
  verwaiste Eintrag werde nach `_STALE_SECONDS` „regulär entfernt" und der Fall sei „per Test
  abgedeckt", war in beiden Halbsätzen falsch: bei einer im laufenden Boot recycelten PID wird der
  Eintrag nie entfernt, und einen Test dafür gibt es nicht (alle Dead-PID-Tests nutzen
  `999999999`, das nie lebt). Als Known Limitation ergänzt, mit Verweis auf ein eigenes
  Folge-Issue — es handelt sich um ein Bestandsproblem, das A1 weder einführt noch verschärft.
- 2026-08-21: Known Limitation zur Spaltenkürzung in B5 ergänzt (Adversary-Finding F004): die
  Kürzung zählt Zeichen, nicht Darstellungsbreite; CJK/Emoji/ANSI/Steuerzeichen können die
  Ausrichtung weiterhin brechen. Kein Rückschritt gegenüber dem Ist-Zustand (der gar nicht kürzte),
  daher bewusst ohne Codeänderung in diesem Zyklus.
- 2026-08-22: B5 korrigiert — die Einschätzung „verschlechtert keinen Fall" vom Vortag war
  widerlegt. Die generische Kürzung ALLER Spalten war ein echter Rückschritt: von den realen
  Werten dieses Projekts verloren `branch` (23 > 22), `workflow` (28 > 22) und `phase` (17 > 16)
  Information, die der alte Code vollständig anzeigte. Ursache war nicht B5 selbst, sondern der
  generisch formulierte RED-Test (`len(row) == len(header)`), der ohne Kürzung aller Spalten nicht
  erfüllbar war. Jetzt: Kürzung nur noch in der `Issue`-Spalte (wie B5 ursprünglich vorsah),
  stattdessen Spalten an der Namenskonvention bemessen (`worktree` 16→21, `branch` 22→30,
  `workflow` 22→30, `phase` 16→18), Gesamtbreite 155→178. Neuer Test mit realistischen
  Projektwerten (`worktree-intake-120-121`, `fix-120-121-session-register`, `phase6b_adversary`),
  der genau diesen Rückschritt verhindert hätte. Known Limitation entsprechend umgeschrieben.
- 2026-08-22: F006/F007 — Schreibfehler in `_reregister()` und Fehler in der Pfadauflösung von
  `_do_claim()` werden nicht mehr stillschweigend vom übergeordneten Fangnetz geschluckt.
