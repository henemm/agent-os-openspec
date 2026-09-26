---
entity_id: fix-237-egress-guard-scratchpad
type: bugfix
created: 2026-09-26
updated: 2026-09-26
status: draft
version: "1.0"
tags: [secret-egress-guard, bash-gate, scratchpad, redirect-guard, config-drift]
---

# Secret-Egress-Guard erlaubt /dev/null, Standard-Kanäle und das Sitzungs-Scratchpad (#237, #239)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue #237:** `secret_egress_guard` blockt `/dev/null` (sobald ein Trennzeichen ohne
  Leerzeichen folgt) und das Sitzungs-Scratchpad, obwohl die eigene Blockade-Meldung das
  Scratchpad als richtiges Ausweich-Ziel benennt.
- **Issue #239 (mitgefixt, vom PO am 2026-09-25 freigegeben):** `extra_allowed_write_dirs`
  wirkt seit Einführung (#97) nie, weil das Muster gegen den bereits **aufgelösten** Pfad
  geprüft wird (`/tmp/…` löst auf macOS zu `/private/tmp/…` auf).

## Purpose

`secret_egress_guard.py` prüft Bash-Umleitungsziele gegen eine Sicherheitszone (Projekt plus
konfigurierte Ausnahmen) und blockiert dabei drei Ziele fälschlich, die es nicht blockieren
dürfte: `/dev/null`/`/dev/stdout`/`/dev/stderr` mit angehängtem Shell-Trennzeichen, jedes echte
Ziel mit angehängtem Trennzeichen (verstümmelter Name in der Meldung), und das private
Sitzungs-Scratchpad. Diese Änderung behebt beide Root Causes, macht die seit #97 nie wirkende
Konfigurationsausnahme (#239) endlich funktionsfähig und zieht denselben Tokenisierungsfehler
in der bewussten Parallel-Kopie `bash_gate.py` nach — ohne die Wert-Prüfung (`find_leaks()`)
oder das Fail-open-Prinzip des Guards zu verändern.

## Source

- **File:** `core/hooks/secret_egress_guard.py`
- **Identifier:** `_shell_write_targets()`, `_is_outside_safe_zone()`, `_read_payload()`,
  `find_unsafe_redirects()`, `main()`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/bash_gate.py::_has_real_redirect()` / `_raw_redirect()` | Funktion (bewusste Parallel-Kopie) | Teilt exakt dieselbe Tokenisierungslücke (D5) — wird in derselben Änderung mitgefixt, nur die Bereinigung, nicht Geräte-Liste oder Scratchpad |
| Claude-Code-Hook-Payload-Feld `scratchpad_dir` (stdin-JSON) | Payload-Feld | Einzige belegte Quelle des Sitzungs-Scratchpad-Pfads (verfügbar ab Claude Code v2.1.257); es existiert **keine** Umgebungsvariable dafür — die Annahme `CLAUDE_SCRATCHPAD_DIR` im Issue-Text ist widerlegt |
| `core/hooks/hook_utils.py::find_project_root()` | Funktion | unverändert weiterverwendet, liefert die Projekt-Wurzel für den bestehenden Zonen-Vergleich |
| `core/hooks/override_token.py::has_valid_token()` | Funktion | unverändert weiterverwendet, hebt den Redirect-Check weiterhin auf |
| `config_loader.load_config()` | Funktion | unverändert weiterverwendet |
| `config.yaml::secret_egress_guard.extra_allowed_write_dirs` | Config-Sektion | bestehendes Feld, Prüf-Logik wird um den unaufgelösten Pfad ergänzt (D4/#239) — Feldname und Default bleiben unverändert |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/secret_egress_guard.py` | MODIFY | D1 Ziel-Bereinigung in `_shell_write_targets()` (beide Rückfall-Zweige mit); D2 Konstante `_ALLOWED_DEVICES`; D4 Muster-Prüfung gegen beide Pfad-Formen in `_is_outside_safe_zone()`; D3 `_read_payload()` liefert `scratchpad_dir` mit, neue Ausnahme in `_is_outside_safe_zone()`, Durchreichen über `find_unsafe_redirects()`/`main()`; Meldungstext nennt das Scratchpad nur noch, wenn die Sitzung eins hat (AC-15) |
| `core/hooks/bash_gate.py` | MODIFY | D5: dieselbe rechtsseitige Bereinigung in `_has_real_redirect()` und `_raw_redirect()` — keine Geräte-Liste, kein Scratchpad |
| `tests/test_secret_egress_redirect_guard_97.py` | MODIFY | neue Fälle zu D1–D4 (siehe Acceptance Criteria); die zwei seit #97 roten #239-Tests (`test_redirect_matching_extra_allowed_dir_is_allowed`, `TestIsOutsideSafeZoneUnit::test_extra_allowed_pattern_makes_it_safe`) werden grün, **ohne umgeschrieben zu werden** |
| `tests/test_bash_gate_false_positives.py` | MODIFY | 1–2 neue Fälle zu D5 (`_has_real_redirect()` mit angehängtem Trennzeichen) |
| `config.yaml` | MODIFY | Kommentar bei `extra_allowed_write_dirs` (Zeile 165): das Beispiel `^/tmp/claude-\d+/` „fuers eigene Scratchpad" wird durch D3 gegenstandslos — Kommentar wird zu einem allgemeinen Projekt-Ausnahme-Hinweis umformuliert, Feldname/Default bleiben unverändert (kein neuer Drift der Klasse #145/#146) |
| `CHANGELOG.md` | MODIFY | Neuer Abschnitt unter der aktuellen Version, PATCH-Bump (siehe ADR) |

### Estimated Changes

- Files: **6** — eine über der Hausregel (4–5). Vom PO am 2026-09-25 bewusst freigegeben
  („Alles zusammen"), weil derselbe Defekt an zwei Stellen sitzt und zwei der sechs Dateien
  (`config.yaml`-Kommentar, `CHANGELOG.md`) keinen inhaltlichen Umfang tragen.
- LoC: **+185 / −30** (Code ca. 55, Tests ca. 130) — inkl. AC-15 (bedingter Meldungstext).

## Implementation Details

Reihenfolge bindend (aus der Analyse, Abschnitt „Technischer Ansatz — Reihenfolge"):

**1. D1 — Ziel-String rechtsseitig bereinigen (`secret_egress_guard.py::_shell_write_targets()`)**
Neue kleine Hilfsfunktion `_strip_trailing_shell_noise(target: str) -> str`, die eine beliebige
Folge aus `;`, `&`, `|`, `)` am rechten Rand des gefundenen Ziel-Strings entfernt. Sie wird an
allen vier Fundstellen angewendet (shlex-Zweig, `sh -c`/`eval`-Rohtext-Zweig,
`ValueError`-Rohtext-Zweig — dieselbe Bereinigung dreifach, weil jeder Zweig den Zielstring an
einer eigenen Stelle extrahiert) — und zwar **vor** den Ausnahme-Prüfungen
(`target != "/dev/null"`, `re.match(r"^&\d+$", target)`). Die Reihenfolge ist bindend: zuerst
bereinigen, dann prüfen. Andersherum (zuerst prüfen, dann bereinigen — so hatte der
unabhängige Plan-Agent es zunächst vorgeschlagen, siehe Analyse-Korrektur) bleibt
`2>&1; echo x` ein Fehlalarm, weil `^&\d+$` gegen den unbereinigten String `&1;` nicht passt;
ein führendes `&` (wie in `>&2`) wird von einer rein rechtsseitigen Bereinigung nie berührt,
die Ausnahme bleibt also für den echten Fall unangetastet.

**2. D2 — Geräte-Positiv-Liste (dieselbe Funktion, dieselben vier Fundstellen)**
Neue Modul-Konstante `_ALLOWED_DEVICES = {"/dev/null", "/dev/stdout", "/dev/stderr"}`. Der
Vergleich `target != "/dev/null"` wird durch `target not in _ALLOWED_DEVICES` ersetzt.

**3. D4 — #239 in `_is_outside_safe_zone()`, vor D3**
Die Muster-Schleife (`for pattern in cfg["extra_allowed_write_dirs"]: if re.match(pattern,
resolved): return False`) prüft heute ausschließlich gegen `resolved` (den mit
`Path.resolve()` aufgelösten Pfad). Ergänzt wird eine zweite Prüfung gegen den absolut
gemachten, aber **unaufgelösten** Pfad (`str(p)`, vor `.resolve()`) — ODER-verknüpft: matcht
eines der beiden Pfad-Formen, ist das Ziel sicher. Damit greift ein Muster wie
`^/tmp/claude-\d+/` erstmals auch dann, wenn `/tmp` zur Laufzeit zu `/private/tmp` aufgelöst
wird. Diese Reparatur steht bewusst vor D3, damit die neue Scratchpad-Ausnahme (Schritt 4) auf
einer funktionierenden Pfad-Prüfung aufsetzt.

**4. D3 — Scratchpad-Ausnahme**
- `_read_payload()` ändert die Signatur auf ein 3-Tupel `(tool_name, tool_input,
  scratchpad_dir)`: der volle geparste stdin-JSON wird nicht mehr sofort auf
  `tool_name`/`tool_input` reduziert, `data.get("scratchpad_dir")` wird zusätzlich
  zurückgegeben. Der `CLAUDE_TOOL_INPUT`/`CLAUDE_TOOL_NAME`-Env-Zweig (Alt-Pfad ohne stdin)
  liefert dafür `None` — aus zwei isolierten Env-Variablen lässt sich kein Scratchpad-Pfad
  gewinnen.
- `main()` reicht `scratchpad_dir` an `find_unsafe_redirects()` weiter, das es unverändert an
  `_is_outside_safe_zone()` durchgibt (neuer optionaler Parameter `scratchpad_dir: str | None`).
- In `_is_outside_safe_zone()`, vor der Muster-Schleife aus Schritt 3: ist `scratchpad_dir`
  gesetzt, wird `resolved` gegen diesen Pfad geprüft — exakte Gleichheit ODER `resolved`
  beginnt mit `scratchpad_dir + os.sep` (Unterordner des Scratchpads eingeschlossen, kein
  Regex, kein Muster-Fallback). Treffer → `return False` (sicher). Fehlt `scratchpad_dir` im
  Payload (Feld nicht vorhanden), wird dieser Zweig komplett übersprungen — es gibt dann für
  diese Sitzung auch kein Scratchpad, das zu erlauben wäre (siehe Known Limitations).

**5. D5 — dieselbe Bereinigung in `bash_gate.py`**
`_has_real_redirect()` und `_raw_redirect()` bekommen dieselbe rechtsseitige Bereinigung als
eigene, parallele Kopie von `_strip_trailing_shell_noise()` (kein gemeinsamer Import zwischen
den beiden Guards — Begründung siehe ADR), angewendet vor der bestehenden
`/dev/null`/`^&\d+$`-Ausnahmeprüfung. Keine Geräte-Liste (D2 bleibt `secret_egress_guard`-
exklusiv, `bash_gate.py` kennt weiterhin nur `/dev/null`), kein Scratchpad (`bash_gate.py` hat
keinen Sicherheitszonen-Begriff — das wäre ein Scope-Sprung über die Analyse hinaus).

**6. Meldungstext, `config.yaml`, `CHANGELOG.md`**
Der Meldungstext in `_block_unsafe_redirect()` benennt „das private Sitzungs-Scratchpad" als
richtiges Ziel. Nach D3 ist dieser Rat erstmals wahr — aber nur, wenn die Sitzung ein Scratchpad
hat. `_block_unsafe_redirect()` bekommt deshalb `scratchpad_dir` durchgereicht und lässt diese
Zeile weg, wenn das Feld fehlt (AC-15): ein Rat, der auf ein nicht existierendes Verzeichnis
zeigt, kostet bei jedem Treffer einen Fehlversuch — genau der Vorwurf aus #237.
`config.yaml` Zeile 165: der Kommentar
„fuers eigene Scratchpad" beim Beispielmuster wird entfernt/umformuliert, weil das Scratchpad
ab jetzt automatisch über D3 erlaubt ist, nicht mehr über ein manuell eingetragenes Muster —
Feldname und Default (`[]`) bleiben unverändert. `CHANGELOG.md` bekommt einen neuen Abschnitt
(PATCH-Bump, siehe ADR).

**7. Regressionslauf**
Vollständiger Lauf `pytest tests/ -q` (siehe Test Plan) — muss vollständig grün sein,
insbesondere die zwei zuvor roten #239-Tests.

## Expected Behavior

- **Input:** Eine `PreToolUse`-Payload für das `Bash`-Tool (`command`-Feld) plus, sofern von
  Claude Code gesetzt, das stdin-JSON-Feld `scratchpad_dir` der aktuellen Sitzung.
- **Output:** Exit 0 in mehr Fällen als bisher — `/dev/null`/`/dev/stdout`/`/dev/stderr` mit
  angehängtem Trennzeichen, jedes Ziel mit angehängtem Trennzeichen innerhalb der Zone,
  `2>&1`/`>&2` mit angehängtem Trennzeichen, Umleitungen ins eigene Sitzungs-Scratchpad, ein
  `extra_allowed_write_dirs`-Muster gegen den unaufgelösten Pfad. Exit 2 bleibt unverändert für
  jedes echte Ziel außerhalb der Zone (auch mit angehängtem Trennzeichen — nur der gemeldete
  Name wird dabei bereinigt) und für jedes fremde Scratchpad.
- **Side effects:** Keine neuen Zustandsänderungen. Die bestehende Wert-Prüfung (`find_leaks()`)
  bleibt in Verhalten und Reihenfolge unverändert — sie läuft weiterhin zuerst und exklusiv;
  nur der nachgelagerte Ziel-Check wird gelockert. Fail-open (jeder interne Fehler → Exit 0)
  bleibt unverändert.

## Known Limitations

- **(a) Verstümmelter Name in der Fehlermeldung bei gequotetem Sonderfall.** Ein Dateiname, der
  legitim (nur erreichbar mit Anführungszeichen) auf `;`, `&`, `|` oder `)` endet
  (`> "datei.log;"`), wird in der Meldung um dieses Zeichen gekürzt. Die Sicherheitszone bleibt
  dieselbe — das Verzeichnis, gegen das geprüft wird, ändert sich nicht, nur der angezeigte
  Name ist falsch.
- **(b) `/dev/tty` und `/dev/fd/N` bleiben bewusst blockiert.** `/dev/fd/N` zeigt auf einen
  beliebigen offenen Deskriptor des Prozesses und könnte den Guard über einen Umweg genau in
  dem Fall aushebeln, den er verhindern soll — deshalb nicht in `_ALLOWED_DEVICES` aufgenommen
  (D2).
- **(c) Fehlt `scratchpad_dir` im Payload, existiert kein Scratchpad und keine Ausnahme.** Die
  Feld-Emission und die Anlage des Scratchpad-Verzeichnisses hängen laut Analyse an derselben
  Bedingung in Claude Code — kein Muster-Fallback, weil ein solcher Fallback fremde Sitzungen
  auf derselben Maschine miteinschließen würde (D3).
- **(d) Der Beweis, dass `scratchpad_dir` im realen Payload ankommt, ist offen.** Er steht
  aktuell auf der ausgelesenen Programmdatei von Claude Code 2.1.274, nicht auf einem
  abgefangenen PreToolUse-Payload einer Sitzung, die nachweislich ein Scratchpad hat. Fällt der
  Nachweis in Phase 7 anders aus, greift die Scratchpad-Ausnahme in der Praxis nicht — die
  reparierte Konfigurationsausnahme aus D4 bliebe dann das Sicherheitsnetz, um das Scratchpad
  projektseitig per Muster einzutragen.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Bash-Kommando wie `ls -d ~/x 2>/dev/null; echo done` wird nicht mehr blockiert
      (beobachtbar am Exit-Code 0 des Hooks, nicht an einer manuellen Session)
- [ ] Eine Umleitung in das Sitzungs-Scratchpad wird nicht mehr blockiert, eine Umleitung in ein
      FREMDES Scratchpad bleibt blockiert
- [ ] Die zwei seit Einführung von #97 roten Tests zu `extra_allowed_write_dirs` sind grün, ohne
      umgeschrieben worden zu sein
- [ ] Ein echtes Ziel außerhalb der Zone (kein Gerät, kein Scratchpad) wird weiterhin blockiert —
      die Lockerung betrifft ausschließlich die drei genannten Fälle
- [ ] `CHANGELOG.md` und `config.yaml` sind aktualisiert, `config.yaml` und der Code-Default
      bleiben für `extra_allowed_write_dirs`/`redirect_guard_enabled` identisch
- [ ] Vollständiger Regressionslauf `pytest tests/ -q` ist grün (Eigen-venv mit pytest + pyyaml)
- [ ] Phase 7: ein realer PreToolUse-Payload aus einer Sitzung mit nachgewiesenem Scratchpad
      wurde abgefangen und sein Inhalt bezüglich `scratchpad_dir` dokumentiert (Treffer oder
      Widerlegung — beides schließt diesen Punkt ab)

## Acceptance Criteria

- **AC-1:** Given das Bash-Kommando `ls -d ~/x 2>/dev/null; echo done` / When
  `secret_egress_guard.py` es prüft / Then Exit 0 (kein Block, `/dev/null` mit angehängtem `;`).
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-2:** Given das Bash-Kommando `cmd 2>/dev/null&` / When geprüft / Then Exit 0 (`/dev/null`
  mit angehängtem `&`).
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-3:** Given das Bash-Kommando `(cmd 2>/dev/null)` / When geprüft / Then Exit 0 (`/dev/null`
  mit angehängtem `)`).
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-4:** Given das Bash-Kommando `cmd >/dev/stdout` / When geprüft / Then Exit 0.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-5:** Given das Bash-Kommando `cmd 2>/dev/stderr` / When geprüft / Then Exit 0.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-6:** Given das Bash-Kommando `echo x > ~/bericht.txt; echo fertig` (echtes Ziel außerhalb
  der Zone — absoluter Pfad im Home-Verzeichnis, nicht im Projekt —, mit angehängtem
  Trennzeichen) / When geprüft / Then Exit 2, und die Meldung nennt das bereinigte Ziel
  (`…/bericht.txt`, nicht `…/bericht.txt;`).
  *Hinweis: Ein **relativer** Name wie `bericht.txt` löst gegen die CWD auf und liegt damit
  innerhalb des Projekts — der wäre korrekt Exit 0 und taugt nicht als Kriterium.*
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-7:** Given das Bash-Kommando `cmd 2>&1; echo x` (FD-Duplizierung mit angehängtem
  Trennzeichen) / When geprüft / Then Exit 0 — die Ausnahme für `2>&1`/`>&2` bleibt auch mit
  angehängtem Trennzeichen wirksam.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-8:** Given eine `PreToolUse`-Payload mit gesetztem `scratchpad_dir` UND ein Bash-Kommando,
  das per `>` in eine Datei innerhalb dieses Pfads (auch in einem Unterordner) schreibt / When
  geprüft / Then Exit 0.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-9:** Given eine `PreToolUse`-Payload mit gesetztem `scratchpad_dir` UND ein Bash-Kommando,
  das in ein ANDERES Scratchpad-Verzeichnis schreibt (abweichender Session-Pfad, nicht Präfix
  von `scratchpad_dir`) / When geprüft / Then Exit 2.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-10:** Given eine `PreToolUse`-Payload OHNE `scratchpad_dir`-Feld UND ein Bash-Kommando,
  das in ein Verzeichnis unter `/tmp` schreibt, das keinem konfigurierten Muster entspricht /
  When geprüft / Then Exit 2 — kein Muster-Fallback, das Verhalten bleibt wie vor dieser
  Änderung.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-11:** Given `config.yaml::secret_egress_guard.extra_allowed_write_dirs` enthält
  `["^/tmp/"]` UND ein Bash-Kommando schreibt nach `/tmp/pytest_full.log` (macOS: löst zu
  `/private/tmp/…` auf) / When geprüft / Then Exit 0 — die zwei seit #97 roten Tests
  (`test_redirect_matching_extra_allowed_dir_is_allowed`,
  `TestIsOutsideSafeZoneUnit::test_extra_allowed_pattern_makes_it_safe`) werden grün, ohne
  umgeschrieben zu werden.
  - Test: `tests/test_secret_egress_redirect_guard_97.py::test_redirect_matching_extra_allowed_dir_is_allowed`, `tests/test_secret_egress_redirect_guard_97.py::TestIsOutsideSafeZoneUnit::test_extra_allowed_pattern_makes_it_safe`
- **AC-12:** Given die Kommandos `cmd 2>/dev/null; echo x`, `(cmd 2>/dev/null)` und
  `cmd 2>/dev/null&` / When `bash_gate.py::_has_real_redirect()` sie prüft / Then liefert die
  Funktion für alle drei `False` (kein fälschlicher Write-Indikator mehr).
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-13:** Given ein Bash-Kommando, das gleichzeitig einen ausgeschriebenen Secret-Wert aus
  der `.env` enthält UND ein Ziel außerhalb der Zone / When `secret_egress_guard.py` es prüft /
  Then Exit 2 mit der Literal-Wert-Meldung (unverändertes Vorrang-Verhalten, `find_leaks()`
  bleibt von dieser Änderung unberührt).
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-14:** Given der vollständige Testbaum dieses Repositories / When `pytest tests/ -q`
  läuft / Then alle Tests bestehen (0 Fehlschläge, keine neuen Skips).
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-15:** Given ein blockiertes Ziel außerhalb der Zone UND eine Payload OHNE
  `scratchpad_dir` / When `secret_egress_guard.py` blockiert / Then nennt die Meldung das
  Sitzungs-Scratchpad **nicht** als richtiges Ziel (diese Sitzung hat keins — der Rat wäre
  nicht befolgbar). Ist `scratchpad_dir` gesetzt, nennt die Meldung es weiterhin.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

## Test Plan

Automatische Tests, subprozessbasiert gegen die echten Hooks (Stilvorlage: bestehende Klassen
in denselben Dateien):

- `tests/test_secret_egress_redirect_guard_97.py` — neue Fälle zu AC-1 bis AC-11, AC-13, AC-15
  (Integrationstests gegen `secret_egress_guard.py` als Subprozess plus Unit-Tests direkt gegen
  `_shell_write_targets()`/`_is_outside_safe_zone()`/`_read_payload()` für die Randfälle aus den
  Known Limitations)
- `tests/test_bash_gate_false_positives.py` — neue Fälle zu AC-12, in der bestehenden Klasse
  `TestFdDuplicationNotRedirect`
- **Vorher/Nachher-Beweis für #239:** `test_redirect_matching_extra_allowed_dir_is_allowed` und
  `TestIsOutsideSafeZoneUnit::test_extra_allowed_pattern_makes_it_safe` sind vor dieser Änderung
  rot (Analyse, Phase 2: „2 failed, 39 passed") und müssen danach grün sein, ohne dass ihr
  Testcode verändert wurde
- **Phase-7-Nachweis (AC nicht testbar, aber Pflichtpunkt der Definition of Done):** ein
  abgefangener PreToolUse-Payload aus einer Sitzung mit nachgewiesenem Scratchpad wird auf das
  Vorhandensein von `scratchpad_dir` geprüft — Ergebnis wird dokumentiert, unabhängig vom
  Ausgang
- Vollständiger Regressionslauf: `pytest tests/ -q`
- **Umgebungshinweis:** kein System-`pytest` verfügbar — eigenes Scratchpad-venv mit `pytest`
  UND `pyyaml` anlegen, sonst laufen die Tests in stillem Leerlauf (bekannte Falle in diesem
  Repository, siehe Memory-Eintrag „Pytest-Umgebung agent-os-openspec")

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Kein neues architekturelles Element (kein neuer Hook, kein neues Event, keine
  neue Payload-Konvention) — ein Bugfix an einer bestehenden Prüfung plus das Nachziehen
  derselben Reparatur in einer bewusst bestehenden Parallel-Kopie. Zwei Entscheidungen der
  Analyse berühren dennoch Architektur-Konventionen dieses Repos und gehören deshalb hier
  dokumentiert, statt in einer eigenen ADR-Nummer:

  1. **D1 — lokale Bereinigung statt `shlex.shlex(punctuation_chars=True)`.** Die technisch
     sauberere Alternative (Shell-Operatoren als eigene Token liefern) wurde verworfen, weil sie
     alle Token-Grenzen verschieben würde — auch die `tee`-Ziel-Erkennung und die
     Datei-Token-Prüfungen in `bash_gate.py`, die von dieser Änderung unberührt bleiben sollen.
     Eine reine rechtsseitige String-Bereinigung des bereits gefundenen Ziels hat den kleinsten
     Wirkungsradius gegen die zehn bestehenden AC-Tests aus #97.
  2. **D5 — bestätigt die bestehende Konvention „bewusste Parallel-Kopien statt geteiltem
     Import"** (CLAUDE.md, Abschnitt Hook-Entwicklung; bereits in der ADR von #97 als
     Architektur-Entscheidung festgehalten). Verworfene Alternative: ein gemeinsamer Helfer für
     `_strip_trailing_shell_noise()` zwischen `secret_egress_guard.py` und `bash_gate.py` — das
     wäre ein Bruch dieser Konvention gewesen und wurde deshalb abgelehnt; ebenfalls verworfen:
     das Nachziehen in `bash_gate.py` als eigenes, späteres Ticket (vom PO am 2026-09-25 explizit
     abgelehnt — „Alles zusammen", weil ein getrenntes Ticket genau den Drift zwischen den beiden
     Kopien riskiert, den die Konvention verhindern soll).

  Kein Versionssprung über PATCH hinaus: diese Änderung korrigiert bestehendes Fehlverhalten
  (Über-Blockieren), führt keine neue Fähigkeit ein — konsistent mit der Repo-Konvention aus dem
  CHANGELOG (PATCH für reine Bugfixes wie 3.30.1–3.30.4, MINOR nur für neue Fähigkeiten).

## Changelog

- 2026-09-26: Initial spec created
- 2026-09-26: AC-6 korrigiert (relatives Ziel liegt im Projekt und wäre korrekt Exit 0 — jetzt
  absoluter Pfad außerhalb); AC-15 ergänzt: Meldungstext empfiehlt das Scratchpad nur noch
  Sitzungen, die eins haben (die Analyse verlangte eine Anpassung des Meldungstextes, die erste
  Spec-Fassung hatte sie für unnötig erklärt)
