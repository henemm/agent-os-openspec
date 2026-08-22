# Context: fix-120-121-session-register

## Request Summary

Das Session-Register (`.claude/session-locks/`) soll die Frage "arbeitet gerade jemand an Issue #N?"
verlässlich beantworten. Heute kann es das nicht: aktive Sessions verschwinden dauerhaft (#120) und
die Issue-Nummer wird aus dem Workflow-Namen geraten statt beim Intake gesetzt (#121).

- **#120** — Eine gereapte Session kommt nie zurück, weil `_heartbeat()` bei fehlender Lock-Datei
  aussteigt.
- **#121** — `/00-intake #N` kennt die Nummer ab Sekunde eins, gibt sie aber nirgends weiter;
  `_extract_issue_number()` rät stattdessen die erste Ziffernfolge des Workflow-Namens.

Beide Issues fassen dieselben Funktionen an; #121 setzt #120 laut Issue-Text voraus.

## Related Files

| File | Relevanz |
|------|----------|
| `core/hooks/session_singleton_guard.py` | Kern der Änderung. 506 Zeilen. `_is_alive()` :86, `_reap_dead()` :116, `_extract_issue_number()` :218, `_context_fields()` :270, `_apply_context_fields()` :303, `_heartbeat()` :312, `_do_register()` :374, `_do_guard()` :421, `_do_cleanup()` :470, `main()` :487 |
| `tests/test_session_singleton_guard.py` | 651 Zeilen, 37 Tests. Direktimport (kein Subprozess), `SystemExit` wird als Exit-Code abgefangen |
| `core/commands/00-intake.md` | Muss den Claim-Aufruf bekommen. Konvention hier: hartkodiert `python3 .claude/hooks/<script>.py` |
| `skills/00-intake/SKILL.md` | **Zweite, nicht automatisch synchronisierte Kopie** desselben Commands. Hat einen dreistufigen `## Setup`-Block für die Hook-Pfad-Auflösung (`${CLAUDE_PLUGIN_ROOT}` → `installed_plugins.json` → `.claude/hooks`) |
| `core/hooks/workflow.py` | `cmd_sessions()` :1256, `_read_session_entries()` :1239, `_sessions_age()` :1227, `SESSIONS_PLACEHOLDER = "–"` :45. Nur betroffen, falls die Issue-Spalte mehrere Nummern zeigen soll |
| `hooks/hooks.json` | Registrierung: SessionStart `register` (:3-13), PreToolUse Matcher `""` = alle Tools `guard` (:14-22), SessionEnd `cleanup` (:119-129), je `timeout: 5` |
| `docs/specs/feat-106-session-register.md` | Enthält AC-11, das dem #120-Fix wörtlich widerspricht. Muss revidiert werden |
| `CHANGELOG.md` | Aktuell 3.15.0 |

## Live-Befund aus dieser Session (empirisch, nicht aus dem Issue übernommen)

Eigener Registereintrag, gelesen am 2026-08-21:

```json
{ "session_id": "fbb54633-23ac-423d-87d8-313e8366b7fc",
  "cwd": "/home/hem/agent-os-openspec/.claude/worktrees/intake-120-121",
  "pid": 909132, "started_at": 1787335588.13, "last_seen": 1787335957.87,
  "branch": "worktree-intake-120-121", "agent_name": "agent-os-openspec-c6",
  "worktree": "intake-120-121", "workflow": "fix-120-121-session-register",
  "issue": "120", "phase": "phase1_context" }
```

Drei verifizierte Fakten:

1. **Die gespeicherte `pid` 909132 ist tot** (`/proc/909132` existiert nicht) — wie im Code-Kommentar
   bei `_is_alive()` :92-97 beschrieben. `os.getppid()` liefert die transiente Hook-Shell.
2. **`CLAUDE_PID=909014` lebt** und hat `cmdline == "claude"`. Es gibt also eine stabile
   Liveness-Quelle, die der bisherige Code nicht nutzt.
3. **`CLAUDE_CODE_SESSION_ID` ist byte-identisch mit `session_id`** im Eintrag. Ein Bash-Aufruf aus
   einem Slash-Command heraus kann sich damit selbst identifizieren — das war die offene
   Konstruktionsfrage bei #121 (a).

Zusätzlich: `$TMUX` und `$TMUX_PANE` sind in dieser Session gesetzt (#121 c ist umsetzbar).
`grep -rn "tmux"` über das Repo liefert **0 Treffer** — es gibt keinerlei Bestandsmuster für tmux.

Und: Das Feld `"issue": "120"` ist für diesen Workflow **unvollständig** — die Session hält #120
*und* #121. Der Regex-Bug aus #121 ist damit am eigenen Workflow belegt.

## Existing Patterns

- **Fail-safe ist die oberste Regel.** Globaler Wrapper `except Exception: sys.exit(0)` (:501-506)
  plus lokale `try/except: pass` pro Datenquelle (:186, :214, :236, :263, :272, :366, :409, :476).
  Jede neue Quelle muss einzeln gekapselt werden — ein Ausfall darf den Bestandseintrag nie
  verhindern (so bereits als AC-8 in feat-106 festgehalten).
- **Hot-Path-Schutz.** `guard` läuft bei *jedem* Tool-Call. Deshalb: Heartbeat-Throttle 60s
  (`_HEARTBEAT_THROTTLE_SECONDS`), agent_name-Lookup-Zeitdeckel 60s
  (`_AGENT_NAME_LOOKUP_WINDOW_SECONDS`), höchstens **ein** Datei-Write pro Aufruf.
- **`hook_utils` wird lazy importiert**, innerhalb von Funktionen (:70, :230, :286) — die Tests
  patchen deshalb in `_patch_project_root()` **beide** Bindungen.
- **`started_at` wird bei erneutem `register` bewahrt** (:395-403), damit `/clear` keine
  Inhaberschaft verliert. Relevant für die Reihenfolge im Register (`_owner_sid` sortiert danach).
- `session_singleton_guard.py` nutzt `block()`/`allow()` aus `hook_utils` **nicht**, sondern
  schreibt direkt auf stderr und ruft `sys.exit(2)` (:455-467).

## Test-Konventionen

Direktimport `import session_singleton_guard as ssg` (`tests/…:16-19`). Helper:

- `_make_guard_payload(tool_name, cwd, session_id="sess-abc") -> dict` (:104)
- `_run_guard(payload) -> int` (:117) — `redirect_stderr`, fängt `SystemExit`, 0=allow / 2=block
- `_run_register(payload) -> int` (:475)
- `_hermetic_guard(monkeypatch, tmp_path)` (:147) — patcht `_has_override_token`→False, `_locks_dir`→tmp_path
- `_patch_project_root(monkeypatch, root)` (:236) — patcht beide `find_project_root`-Bindungen
- `_patch_active_workflow(monkeypatch, name, source="file")` (:247)
- `_isolate_harness_home(monkeypatch, tmp_path) -> Path` (:253) — setzt `HOME`, löscht `USERPROFILE`
- `_heartbeat_env(monkeypatch, tmp_path, workflow=("", "none"))` (:266) → `(locks_dir, harness_sessions_dir)`
- `_write_lock(locks, session_id="sess-abc", **fields) -> Path` (:281) — Default-PID `999999999` (tot)
- `_write_workflow_state(root, name, phase) -> Path` (:298)

Konstanten `MAIN_CWD` / `WORKTREE_CWD` (:113-114). Keine `@pytest.fixture` — reine Funktions-Helper.

## Dependencies

- **Upstream:** `hook_utils.find_project_root()`, `hook_utils.resolve_active_workflow()`,
  `/proc` (Linux-spezifisch), `~/.claude/sessions/*.json` (undokumentiertes Harness-Internal),
  neu hinzukommend: `CLAUDE_PID`, `CLAUDE_CODE_SESSION_ID`, `TMUX` (alle als Env-Vars, alle optional)
- **Downstream:** `workflow.py sessions` liest die Einträge; `_owner_sid()` sortiert nach
  `started_at`; jedes Konsumenten-Projekt lädt den Hook bei **jedem** PreToolUse

## Existing Specs

- `docs/specs/feat-106-session-register.md` — die Vorgänger-Spec. **AC-11 (:435-437)** verlangt
  wörtlich, dass `guard` bei fehlender Lock-Datei *keine* Datei anlegt. Gelesen: das war eine reine
  Scope-Abgrenzung für #106 ("guard ist kein Register-Ersatz"), keine Sicherheits-Invariante.
  Muss mit Begründung revidiert werden.
- `docs/specs/session-singleton-guard.md` — Ursprungs-Spec des Guards.

## Risks & Considerations

1. **AC-11-Revision.** Der #120-Fix hebt eine bereits freigegebene AC auf. Das ist vertretbar
   (Scope-Abgrenzung, keine Invariante), muss aber in der neuen Spec explizit begründet und in
   feat-106 als überholt markiert werden — sonst widersprechen sich zwei Specs im Repo.
2. **Reap darf nicht wirkungslos werden.** Wenn `_heartbeat()` neu anlegt, muss sichergestellt
   sein, dass wirklich tote Sessions weiterhin verschwinden. Das ist gegeben: eine tote Session
   ruft keinen `guard` mehr auf. Restrisiko ist ein Race zwischen `cleanup` (SessionEnd) und einem
   verspäteten `guard`-Aufruf derselben Session — Folge wäre ein verwaister Eintrag, der nach
   `_STALE_SECONDS` regulär gereapt wird. Vertretbar, aber in der Spec als Edge Case zu benennen.
3. **`CLAUDE_PID` ist ein undokumentiertes Harness-Internal**, genau wie `~/.claude/sessions/`.
   Es darf nur additiv genutzt werden: fehlt es, muss das bisherige Verhalten exakt erhalten
   bleiben. Kein Verlass darauf, dass es in älteren/anderen Claude-Code-Versionen existiert.
4. **Zwei Command-Dateien.** `core/commands/00-intake.md` und `skills/00-intake/SKILL.md` werden
   **nicht** automatisch synchronisiert (kein Generator-Skript; `scripts/` enthält nur
   `release_check.py`). Wird nur eine angefasst, driften sie auseinander.
   `tests/test_clear_checkpoint_blocks.py` prüft strukturelle Blöcke in `core/commands`.
5. **Hot-Path.** Der Guard läuft bei jedem Tool-Call in jedem Konsumenten-Projekt. Ein
   Re-Register im Heartbeat darf nicht bei jedem Aufruf feuern, sondern nur wenn die Datei fehlt.
6. **Mehrere Issues pro Workflow.** Dieser Workflow selbst hält zwei Nummern. Ob das Feld `issue`
   eine Liste erlauben soll, ist eine Design-Entscheidung mit Auswirkung auf die 5 Zeichen breite
   Issue-Spalte in `cmd_sessions()`.
7. **tmux ohne Bestandsmuster.** Punkt (c) aus #121 führt eine ganz neue externe Abhängigkeit ein.
   Muss strikt fail-safe sein (kein `$TMUX` → kein Fehler, kein Abbruch, kein Output).

## Bewusst NICHT im Scope

- **Datei-Ebene im Register** ("fasst jemand `alert/render.py` an?", Nebenbeobachtung 2 in #120) —
  eigenständiger, deutlich größerer Wunsch. Gehört in ein separates Issue.
- Ablösung der `SendMessage`-Rundfragen — Folge, nicht Gegenstand dieser Änderung.

---

## Nachtrag: Messungen zur Auflösung der Challenger-Befunde (2026-08-21)

Der `analysis-challenger` gab **NEEDS REVIEW** mit vier Punkten. Zwei davon waren als
"nicht prüfbar ohne Bash" markiert und wurden hier gemessen.

### M1 — Sub-Agenten erben die Session-Identität vollständig

Ein per `Task` gestarteter Sub-Agent gibt aus:

```
CLAUDE_CODE_SESSION_ID=fbb54633-23ac-423d-87d8-313e8366b7fc   ← identisch mit Parent
CLAUDE_PID=909014                                             ← identisch mit Parent
CLAUDE_CODE_CHILD_SESSION=1                                   ← einziger Unterschied
```

Gegenprobe am Register: In dieser Session liefen bis dahin drei Sub-Agenten
(Explore, analysis-challenger, ein Messagent), alle mit Bash-/Read-Aufrufen und damit
`guard`-Durchläufen. Das Lock-Verzeichnis enthält trotzdem **genau eine** Datei.

**Folge:** Die vom Challenger als binäres Ja/Nein benannte Registerflut-Gefahr für A2
**besteht nicht**. Sub-Agenten schreiben in den Eintrag des Parents.

**Rest-Risiko, das bleibt:** Ein Sub-Agent, der `claim` aufriefe, überschriebe den
Parent-Eintrag. `claim` wird ausschliesslich aus `/00-intake` heraus aufgerufen, nie von
Agenten — in der Spec als Einschränkung zu benennen, nicht technisch zu verhindern.

### M2 — `os.kill(pid, 0)` ersetzt `/proc` plattformneutral

Der Challenger hat zu Recht beanstandet, dass `_pid_alive()` (:83-87) mit
`Path(f"/proc/{pid}").exists()` auf macOS **immer `False`** liefert — dort ist das PID-Feld
seit jeher wirkungslos. Gemessen:

| Prüfling | `os.kill(pid, 0)` | `/proc/<pid>` |
|---|---|---|
| `CLAUDE_PID` 909014 (lebt) | lebt, kein Fehler | True |
| gespeicherte Shell-PID 909132 (tot) | `ProcessLookupError` | False |
| PID 1 (lebt, fremder User) | `PermissionError` → **lebt** | – |
| PID 4000000 (existiert nicht) | `ProcessLookupError` | – |

**Folge:** A1 muss nicht als "Linux-spezifische Verbesserung mit No-Op auf macOS"
beschrieben werden — die Umstellung auf `os.kill` macht daraus einen universellen Fix und
behebt nebenbei den bestehenden macOS-Totalausfall der PID-Prüfung.

**Fallstrick für die Spec:** `os.kill(0, 0)` adressiert die **gesamte Prozessgruppe**,
negative Werte ebenfalls. Die gespeicherte PID muss vor dem Aufruf auf `> 0` validiert werden.

### M3 — `boot_id` ist verfügbar (PID-Recycling)

`/proc/sys/kernel/random/boot_id` ist lesbar. Nach einem Reboot kann eine recycelte PID einen
toten Eintrag als "lebendig" erscheinen lassen — heute wie nach A1. Wird die boot_id im Eintrag
mitgeschrieben, ist die PID bei abweichender boot_id als wertlos erkennbar. Linux-spezifisch,
aber fail-safe degradierbar (keine boot_id lesbar → Verhalten wie bisher).

### M4 — Nicht gemessen, aus dem Challenger übernommen

- **AC-11 ist keine vergessene Nebensächlichkeit.** `docs/specs/feat-106-session-register.md:75-87`
  enthält eine ausdrückliche Kosten-Nutzen-Abwägung gegen Schreibzugriffe im Hot-Path; der
  zugehörige Test heisst `test_guard_without_lock_file_creates_nothing`
  (`tests/test_session_singleton_guard.py:568-582`). Die Revision braucht eine echte Widerlegung,
  keine Fussnote.
- **A1 ist der dritte Anlauf am selben Liveness-Problem** (v3.4.9 und v3.4.10 laut
  `CHANGELOG.md:1131-1193`). Die Spec muss begründen, warum Versuch 3 anders ausgeht — Antwort:
  Anlauf 1+2 hatten weder eine stabile PID-Quelle (`CLAUDE_PID`) noch eine funktionierende
  Prüfmethode (`/proc` statt `os.kill`).
- **`claim` braucht eine Invalidierungsregel.** Ohne sie friert ein Claim einen falschen Wert
  dauerhaft ein — schlechter als der heutige Regex-Fehler, der sich bei jedem Workflow-Wechsel
  selbst korrigiert.
