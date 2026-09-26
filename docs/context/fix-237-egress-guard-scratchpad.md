# Context: fix-237-egress-guard-scratchpad

## Request Summary

Der Redirect-Teil von `secret_egress_guard.py` (Issue #97) blockiert zwei Ziele, die er nicht
blockieren dürfte: `/dev/null` (sobald ein Trennzeichen folgt) und das Sitzungs-Scratchpad, das
die Blockade-Meldung selbst als richtiges Ziel empfiehlt. Issue #237. Richtung vom PO bestätigt:
**Scratchpad erlauben** (nicht nur die Meldung korrigieren).

## Reproduktion (beide Fälle, 2026-09-25)

Fall A — `/dev/null` mit angehängtem Trennzeichen:

```python
seg._shell_write_targets('ls -d ~/x 2>/dev/null')             -> []            # ok
seg._shell_write_targets('ls -d ~/x 2>/dev/null; echo done')  -> ['/dev/null;'] # BLOCK
seg._shell_write_targets('cmd 2>/dev/null | head -5')         -> []            # ok
```

Live in dieser Sitzung ungeplant ausgelöst: `ls … 2>/dev/null; …` wurde vom Hook mit Exit 2
abgewiesen, Ziel `/dev/null;`.

**Root Cause:** `_shell_write_targets()` tokenisiert mit `shlex.split()`. `shlex` ist kein
Shell-Parser — es trennt an Whitespace, nicht an Shell-Operatoren. `2>/dev/null;` bleibt darum ein
Token, `m.group(1)` liefert `/dev/null;`, und der Vergleich `target != "/dev/null"` (Zeile 328)
schlägt fehl. Entscheidend ist das fehlende Leerzeichen, nicht das Semikolon: `… | head` läuft
durch, weil `|` freistehend geschrieben wird. Dieselbe Lücke betrifft `&`, `&&`, `)` .

Fall B — Sitzungs-Scratchpad:

```python
seg._shell_write_targets('echo hi > /private/tmp/claude-501/<slug>/<sess>/scratchpad/a.md')
-> ['/private/tmp/claude-501/…/scratchpad/a.md']   # liegt ausserhalb des Projekts -> BLOCK
```

**Root Cause:** `_is_outside_safe_zone()` kennt als sichere Zone nur den Projekt-Root plus die
konfigurierten `extra_allowed_write_dirs`. Das Scratchpad steht in keiner der beiden Mengen.

## Related Files

| Datei | Relevanz |
|---|---|
| `core/hooks/secret_egress_guard.py` | Trägt beide Fehler: `_shell_write_targets()` (Z. 297–338), `_is_outside_safe_zone()` (Z. 341–362), Meldungstext (Z. 391–405) |
| `core/hooks/bash_gate.py` | `_has_real_redirect()` (Z. 265–293) ist eine bewusst parallele Kopie derselben Tokenisierung — **gleiche `/dev/null;`-Lücke**, andere Folge (Write-Indikator der State-Integrity-Regel) |
| `tests/test_secret_egress_redirect_guard_97.py` | 10 AC-Tests + Unit-Tests, u. a. `test_devnull_is_excluded` und `test_fd_duplication_and_devnull_are_not_flagged_as_targets` — keiner deckt ein angehängtes Trennzeichen ab |
| `config.yaml` | `secret_egress_guard.extra_allowed_write_dirs: []`; ein Test bindet Code-Default und Datei aneinander (Drift-Klasse #145/#146) |
| `core/hooks/hook_utils.py` | `find_project_root()` liefert in einer Worktree-Sitzung den **Haupt-Ordner**, nicht den Worktree |

## Existing Patterns

- **Fail-open by design**: jeder interne Fehler endet mit Exit 0 (Modul-Docstring, `__main__`).
  Eine neue Erlaubnis darf diesen Grundsatz nicht umkehren.
- **Bewusste Parallel-Kopien statt geteiltem Import**: `bash_gate.py` und `secret_egress_guard.py`
  halten die Redirect-Tokenisierung getrennt und kommentiert (Kommentar in Z. 300–304). Ein
  gemeinsamer Helfer wäre ein Bruch dieser Konvention — die Entscheidung gehört in die Analyse.
- **Konfigurierbare Ausnahme + Override-Token** als doppelte Notbremse ist bereits etabliert.
- **Payload-Lesen**: `_read_payload()` nimmt zuerst `CLAUDE_TOOL_INPUT`/`CLAUDE_TOOL_NAME` aus der
  Umgebung, sonst stdin-JSON — und **verwirft dabei alle übrigen Payload-Felder**.

## Dependencies

- Upstream: `hook_utils.find_project_root()`, `hook_utils.log_gate_event()`,
  `override_token.has_valid_token()`, `config_loader.load_config()`
- Downstream: registriert in `hooks/hooks.json` als PreToolUse für **alle** Tools — die Änderung
  wirkt in jedem Projekt, das das Framework installiert hat

## Recherche: Woher kommt der Scratchpad-Pfad?

Geprüft an der Hook-Dokumentation (code.claude.com/docs/en/hooks, abgerufen 2026-09-25):

- Das stdin-JSON jedes Hooks enthält das Feld **`scratchpad_dir`** — „Path to the session's
  scratchpad directory … Absent when the session has no scratchpad or the temp directory is
  unavailable. Requires Claude Code v2.1.257 or later."
- Eine Umgebungsvariable `CLAUDE_SCRATCHPAD_DIR` gibt es **nicht**. Die Annahme im Issue-Text ist
  an dieser Stelle falsch.
- Installierte Version hier: **2.1.274** — Feld also verfügbar.

Offen und in Phase 2 zu beweisen: dass das Feld im *realen* PreToolUse-Payload dieses Hooks
tatsächlich ankommt. Geplanter Beweis ohne Eingriff ins Projekt: ein `claude -p`-Lauf in einem
Wegwerf-Ordner mit eigener `settings.json`, deren Hook das rohe stdin ablegt.

## Existing Specs

- `docs/specs/feat-97-secret-egress-redirect-guard.md` — die Spec, die den Redirect-Check
  eingeführt hat; ihre AC-Liste ist die Regressionsgrundlage
- `docs/specs/fast/fix-145-secrets-config-drift.md` — Drift-Regel zwischen `config.yaml` und
  Code-Default

## Risks & Considerations

1. **`extra_allowed_write_dirs` funktioniert derzeit gar nicht (Issue #239, 2 rote Tests).**
   Ursache ist dieselbe Funktion: `_is_outside_safe_zone()` vergleicht das Muster gegen den
   **aufgelösten** Pfad, `/tmp/…` löst auf macOS zu `/private/tmp/…` auf, `^/tmp/` passt nie.
   Das ist kein Nebenschauplatz: Das Scratchpad liegt genau dort, und die Blockade-Meldung
   empfiehlt genau diesen Ausweg. Ein Muster-basierter Fallback für das Scratchpad wäre ohne
   #239 wirkungslos. **Empfehlung: #239 in derselben Änderung miterledigen** (zwei Zeilen in
   derselben Funktion) — Entscheidung in Phase 2 mit Begründung.
2. **Sicherheitswirkung der Lockerung.** Das Scratchpad ist pro Sitzung privat und liegt unter
   einer uid-gebundenen Wurzel; ein Wert, der dort landet, verlässt das System nicht. Die
   Wert-Prüfung (`find_leaks`) bleibt davon unberührt und greift weiter — nur der Ziel-Check wird
   gelockert. Das muss die Spec ausdrücklich festhalten.
3. **Fallback, wenn `scratchpad_dir` fehlt** (ältere Version, Env-Pfad in `_read_payload`): ein
   Muster wie `^/private/tmp/claude-\d+/.*/scratchpad(/|$)` ist breiter als der exakte Pfad und
   erlaubt fremde Sitzungen mit. Enger vs. robuster — Abwägung gehört in die Spec.
4. **`bash_gate.py` teilt die `/dev/null;`-Lücke.** Dort ist die Folge harmloser (ein Kommando
   gilt fälschlich als Write). Mitfixen erhöht die Zahl berührter Dateien; Nichtfixen lässt eine
   bekannte Lücke stehen. Entscheidung in Phase 2.
5. **Nebenbefund, nicht Teil dieses Tickets:** Der Haupt-Ordner-Checkout trägt eine ältere
   `config.yaml` mit den breiten Mustern `_key`/`_secret`. Weil `find_project_root()` in einer
   Worktree-Sitzung den Haupt-Ordner liefert, blockt `secrets_guard.py` dadurch das Lesen der
   eigenen Testdatei `tests/test_secret_egress_redirect_guard_97.py` und jeden Befehl, der den
   Dateinamen enthält. Verwandt mit #169 (Haupt-Ordner nachziehen). Als **Issue #241** angelegt.

---

## Analysis

### Type

Bugfix (zwei Fehler in einem Wächter, plus derselbe Fehler in einer bewussten Parallel-Kopie).

### Reproduktion — Stand Phase 2 (2026-09-25, gegen unveränderten Code)

Skript: `<scratchpad>/repro_237.py`. Ergebnis:

| Kommando | erkanntes „Schreibziel" | Verhalten |
|---|---|---|
| `ls -d ~/x 2>/dev/null` | – | korrekt durchgelassen |
| `ls -d ~/x 2>/dev/null; echo done` | `/dev/null;` | **Exit 2 (falsch)** |
| `(cmd 2>/dev/null)` | `/dev/null)` | **Exit 2 (falsch)** |
| `cmd 2>/dev/null&` | `/dev/null&` | **Exit 2 (falsch)** |
| `cmd 2>/dev/null \| head -5` | – | korrekt durchgelassen (`\|` steht frei) |
| `cmd >/dev/stdout` | `/dev/stdout` | **Exit 2 (falsch)** |
| `cmd 2>/dev/stderr` | `/dev/stderr` | **Exit 2 (falsch)** |
| `echo hi > <scratchpad>/a.md` | voller Pfad | **Exit 2 (falsch)** |

Dazu `bash_gate.py::_has_real_redirect()` mit denselben Eingaben: `True` für
`… 2>/dev/null; …`, `(… 2>/dev/null)` und `… 2>/dev/null&` — identische Lücke, andere Folge.

**Über den Kontext von Phase 1 hinaus:** Die Lücke betrifft nicht nur `/dev/null`. Jedes Ziel wird
verstümmelt, sobald ein Trennzeichen ohne Leerzeichen folgt — `> bericht.txt; echo fertig` liefert
das Ziel `bericht.txt;`. Bei einem Ziel innerhalb des Projekts bleibt das folgenlos, weil der
Pfad-Vergleich trotzdem greift; die Fehlermeldung würde aber einen falschen Dateinamen nennen.

Issue **#239** ebenfalls hier nachgestellt (pytest 9.1.1, pyyaml, eigenes venv):
`2 failed, 39 passed` — `test_redirect_matching_extra_allowed_dir_is_allowed` und
`TestIsOutsideSafeZoneUnit::test_extra_allowed_pattern_makes_it_safe`. Das ist **AC-3** der
Ursprungs-Spec #97: die konfigurierbare Ausnahme wirkt seit Einführung nicht. Ursache: das Muster
wird gegen den **aufgelösten** Pfad geprüft, `/tmp/x` löst auf macOS zu `/private/tmp/x` auf.
Pikant: Das Beispiel in `config.yaml` Z. 165 lautet `["^/tmp/claude-\\d+/"]` mit dem Kommentar
„fuers eigene Scratchpad" — genau der Fall, der nie greifen kann.

### Herkunft des Scratchpad-Pfads — bewiesen, mit Einschränkung

Die Annahme im Issue-Text (`CLAUDE_SCRATCHPAD_DIR`) ist falsch; eine solche Umgebungsvariable
existiert nicht (Hook-Doku und Programmdatei geprüft). Richtig ist das stdin-Feld `scratchpad_dir`.

Aus der installierten Fassung **2.1.274** extrahiert:

```
Payload-Felder: [hook_event_name, session_id, transcript_path, cwd, scratchpad_dir,
                 prompt_id, permission_mode, agent_id, agent_type, served_call,
                 caller_session_id, effort]
Emission:  scratchpad_dir: tw() ? XC(session_id) ?? undefined : undefined
           function tw(){ if(P("tengu_scratch",false)) return true; return isArtifactToolEligible() }
           function XC(id){ return join(<tmp-root>, id, "scratchpad") }   // pro session_id gecacht
Anlegen:   async function IZ(){ if(!tw()) return null; ... mkdir(XC(), 0o700) }
```

**Entscheidend:** Feld-Emission und Verzeichnis-Anlage hängen an **derselben** Bedingung `tw()`.
Fehlt das Feld, existiert für diese Sitzung auch kein Scratchpad — es gibt dann nichts zu erlauben.
Das ist keine Korrelation, sondern dieselbe Weiche im Programm. Ein Muster-basierter Ersatzweg ist
damit unnötig und wäre schädlich (er würde fremde Sitzungen mit öffnen).

Empirische Gegenprobe (`<scratchpad>/probe/`): vier automatisiert gestartete `claude -p`-Sitzungen
(headless, headless+pty, fortgesetzte Sitzung im echten Worktree, ohne Tool-Einschränkung) lieferten
PreToolUse-Daten **ohne** `scratchpad_dir` — und für keine dieser Sitzungen wurde je ein
Scratchpad-Verzeichnis angelegt. Eine interaktive Sitzung legte sehr wohl eines an. **Offen
geblieben:** ein abgefangener Payload aus einer Sitzung MIT Scratchpad. Die TUI-Automatisierung
(expect) startete die Sitzung, brachte aber keinen Werkzeugaufruf zustande. Das ist der eine Punkt,
der in Phase 7 am laufenden System nachzuweisen ist (siehe Test Plan der Spec).

**Zweite Fundstelle, die die Umsetzung betrifft:** `_read_payload()` (Z. 263–275) bevorzugt die
Umgebungsvariablen `CLAUDE_TOOL_INPUT`/`CLAUDE_TOOL_NAME` und liest dann stdin **gar nicht** —
und verwirft ohnehin alle Felder ausser `tool_name`/`tool_input`. Claude Code setzt diese beiden
Variablen nicht (sie stehen nicht in der Liste der Hook-Umgebungsvariablen); der Zweig ist Altlast
für Tests. `_read_payload()` muss `scratchpad_dir` aus demselben geparsten JSON mitliefern.

### Entschiedene Punkte (Bewertung durch unabhängigen Plan-Agenten, danach geprüft)

| # | Entscheidung | Begründung | Verworfene Alternative |
|---|---|---|---|
| D1 | Ziel-String rechtsseitig von `;`, `&`, `\|`, `)` befreien — **vor** allen weiteren Prüfungen | Lokal, ändert nur den gefundenen Ziel-String, nicht die Tokenisierung. Kleinster Wirkungsradius gegen die 10 AC-Tests aus #97 | `shlex.shlex(punctuation_chars=True)` liefert Operatoren als eigene Token — technisch sauberer, verschiebt aber alle Token-Grenzen und damit auch die `tee`-Ziel-Erkennung und die Datei-Token-Prüfungen in `bash_gate.py`. Zu grosse Angriffsfläche für einen Bugfix |
| D2 | Feste Positiv-Liste `/dev/null`, `/dev/stdout`, `/dev/stderr` | Genau das, was #237 verlangt. Alle drei sind Kanäle des Hook-Prozesses selbst, kein zusätzlicher Abfluss | `/dev/tty` und `/dev/fd/N` mit aufnehmen — abgelehnt: `/dev/fd/N` zeigt auf einen beliebigen offenen Deskriptor und könnte den Wächter über einen Umweg genau in dem Fall aushebeln, den er verhindern soll |
| D3 | Scratchpad ausschliesslich aus dem Payload-Feld `scratchpad_dir`, exakter Pfad-Vergleich (kein Regex) | Feld fehlt ⟺ kein Scratchpad vorhanden (siehe oben). Kein Ersatzweg nötig | Muster `^/private/tmp/claude-\d+/.*/scratchpad(/\|$)` als Fallback — abgelehnt: erlaubt jede fremde Sitzung auf derselben Maschine. Auf geteilten CI-Runnern ist die Wurzel nicht zwingend uid-gebunden |
| D4 | **#239 mitfixen** (Muster gegen unaufgelösten UND aufgelösten Pfad prüfen) | Dieselbe Funktion, die D3 ohnehin anfasst. Macht AC-3 aus #97 erstmals wahr und den Notausgang, den die Blockade-Meldung selbst empfiehlt, funktionsfähig. Zwei rote Tests werden grün | #239 separat und das Scratchpad ohne Reparatur der Muster-Prüfung einbauen — machbar, lässt aber ein seit Einführung defektes Feature liegen, obwohl der günstigste Moment jetzt ist |
| D5 | **`bash_gate.py` mitfixen**, aber nur die Tokenisierung — nicht Geräte-Liste, nicht Scratchpad | Dort hat der Fehler eine andere Folge (Fehlalarm der State-Integrity-Regel), ist aber derselbe Defekt. Die Konvention „bewusste Parallel-Kopien" heisst: jede Änderung muss von Hand in die andere Kopie | Eigenes Ticket nachziehen — vom PO am 2026-09-25 verworfen („Alles zusammen"), weil sonst genau der Drift entsteht, den die Konvention verhindern soll |

**Korrektur an der Bewertung des Plan-Agenten:** Er empfahl, erst die Ausnahme `^&\d+$`
(Kanal-Duplizierung) zu prüfen und danach zu bereinigen. Das ist falsch — `2>&1; echo x` liefert
`&1;`, was die Ausnahme nicht trifft; der Fehlalarm bliebe bestehen. Die Reihenfolge ist umgekehrt:
**erst bereinigen, dann prüfen.** Ein führendes `&` wird von einer rechtsseitigen Bereinigung nie
berührt, `>&2` bleibt also unangetastet.

### Machbarkeit belegt

`<scratchpad>/feasibility_d1.py` spielt die vorgeschlagene Reihenfolge gegen 19 Fälle durch,
darunter alle zehn AC-Fälle aus #97: alle bisher fälschlich blockierten Kommandos gehen durch, alle
echten Ziele werden weiter erkannt (auch mit Trennzeichen dahinter), `2>&1` und `>&2` bleiben
ausgenommen, und `>` in gequotetem Freitext bleibt kein Redirect.

**Bekannte Grenze, in der Spec festzuhalten:** Ein Dateiname, der legitim auf `;`, `&`, `|` oder
`)` endet (nur mit Anführungszeichen erreichbar: `> "datei.log;"`), wird um dieses Zeichen gekürzt.
Folge ist ausschliesslich ein falscher Name in der Fehlermeldung — die Sicherheitszone ist
dieselbe, weil das Verzeichnis unverändert bleibt. Ein gequoteter Name mit `;` in der Mitte
(`"datei;.log"`) bleibt vollständig erhalten (geprüft).

### Affected Files

| Datei | Change Type | Beschreibung |
|---|---|---|
| `core/hooks/secret_egress_guard.py` | MODIFY | D1 Ziel-Bereinigung in `_shell_write_targets()` (beide Rückfall-Zweige mit); D2 Konstante `_ALLOWED_DEVICES`; D3 `_read_payload()` liefert `scratchpad_dir` mit, neue Ausnahme in `_is_outside_safe_zone()`, Durchreichen über `find_unsafe_redirects()`/`main()`; D4 Muster gegen beide Pfad-Formen; Meldungstext an die neue Lage anpassen |
| `core/hooks/bash_gate.py` | MODIFY | D5 dieselbe Bereinigung in `_has_real_redirect()` und `_raw_redirect()` |
| `tests/test_secret_egress_redirect_guard_97.py` | MODIFY | neue Fälle zu D1–D4; die zwei roten #239-Tests werden grün, ohne umgeschrieben zu werden |
| `tests/test_bash_gate_false_positives.py` | MODIFY | 1–2 Fälle zu D5 |
| `config.yaml` | MODIFY | Kommentar Z. 165: das Beispiel `^/tmp/claude-\d+/` „fuers eigene Scratchpad" ist nach D3 gegenstandslos und war nach D4-Logik ohnehin irreführend |
| `CHANGELOG.md` | MODIFY | Projektkonvention |

### Scope Assessment

- Dateien: **6** — eine über der Hausregel (4–5). Vom PO am 2026-09-25 bewusst freigegeben
  („Alles zusammen"), weil derselbe Defekt an zwei Stellen sitzt und die beiden trivialen Dateien
  (`config.yaml`-Kommentar, `CHANGELOG.md`) keinen inhaltlichen Umfang tragen.
- Geschätzte LoC: **+170 / −25** (Code ca. 45, Tests ca. 125) — innerhalb ±250.
- Risiko: **MITTEL**. Der Wächter läuft als PreToolUse für alle Werkzeuge in jedem Projekt, das
  das Framework installiert. Ein Fehler hier blockiert Arbeit statt sie zu schützen. Gegengewicht:
  Fail-open bleibt unverändert, und die Änderung **lockert** nur, verschärft nichts.

### Gefährdete bestehende Tests (vor dem Merge grün zu zeigen)

- `tests/test_secret_egress_redirect_guard_97.py` — vor allem `test_devnull_is_excluded` und
  `test_fd_duplication_and_devnull_are_not_flagged_as_targets` (D1/D2 fassen genau deren Logik an)
- `tests/test_bash_gate_false_positives.py` — `TestFdDuplicationNotRedirect` (D5)
- Die Drift-Tests der Klasse #145/#146 bleiben unberührt, **solange** die Scratchpad-Erlaubnis als
  eigene Bedingung implementiert wird und **nicht** als neuer Vorgabewert in
  `extra_allowed_write_dirs`. Das ist bindend für die Umsetzung.
- Vollständiger Regressionslauf `pytest tests/ -q` ist Pflicht (Eigen-venv: kein System-pytest).

### Technischer Ansatz — Reihenfolge

1. D1 Tokenisierung in `secret_egress_guard.py` — Grundlage, alles andere baut darauf auf
2. D2 Geräte-Positiv-Liste (gleiche Funktion, gleiche Tests)
3. D4 #239 in `_is_outside_safe_zone()` — **vor** D3, damit D3 auf einer funktionierenden
   Pfad-Ausnahme aufsetzt
4. D3 `scratchpad_dir` durchreichen und als eigene Ausnahme auswerten
5. D5 dieselbe Bereinigung in `bash_gate.py`
6. Meldungstext, `config.yaml`-Kommentar, CHANGELOG
7. Vollständiger Regressionslauf

### Dependencies

Unverändert gegenüber Phase 1. Neu hinzu: die Signatur von `_read_payload()` ändert sich
(3 Rückgabewerte statt 2) — Aufrufer ist nur `main()` in derselben Datei; Tests, die
`_read_payload` direkt aufrufen, sind mitzuziehen.

### Open Questions

- [x] Scratchpad erlauben oder nur die Meldung korrigieren? → **erlauben** (PO, Phase 1)
- [x] #239 mitfixen? → **ja** (PO, 2026-09-25)
- [x] `bash_gate.py` mitfixen? → **ja, nur die Tokenisierung** (PO, 2026-09-25)
- [x] Muster-Fallback für das Scratchpad? → **nein**, mit Begründung aus der Programmdatei belegt
- [ ] **Noch zu beweisen (Phase 7, nicht blockierend für die Spec):** ein abgefangener
      PreToolUse-Payload aus einer Sitzung, die nachweislich ein Scratchpad hat, enthält
      `scratchpad_dir`. Bis dahin steht der Beweis auf der Programmdatei von 2.1.274, nicht auf
      einem abgefangenen Payload. Fällt er anders aus, greift die Scratchpad-Erlaubnis in der
      Praxis nicht — der reparierte Notausgang aus D4 wäre dann das Sicherheitsnetz.
