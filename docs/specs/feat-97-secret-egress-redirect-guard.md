---
entity_id: feat-97-secret-egress-redirect-guard
type: feature
created: 2026-09-22
updated: 2026-09-22
status: draft
version: "1.0"
tags: [secret-egress-guard, bash-gate, secrets, egress]
---

# feat-97-secret-egress-redirect-guard

## Approval

- [x] Approved

PO-Briefing: `docs/briefings/feat-97-secret-egress-redirect-guard.md` (unabhängig erstellt,
ohne Kenntnis dieses Gesprächs — nur Spec + Issue #97 gelesen). Freigabe-Frage dort beantwortet:
**Ja, mit den drei genannten Einschränkungen freigeben.** Alle drei sind bereits als bewusste,
begründete Scope-Entscheidungen in dieser Spec dokumentiert (Scratchpad-Default, `--output`-Flags
zurückgestellt, Override-Dauer folgt dem Framework-Standard) — kein neuer Fund, der die
Freigabe aufhalten sollte. Der Fix schließt eine gemessene, aktiv ausgenutzte Lücke (75 reale
Leck-Fälle); auf eine vollständigere Lösung zu warten hieße, in der Zwischenzeit gar keinen
Schutz zu haben. Tech-Lead-Entscheidung.

## GitHub Issue

- **Issue:** #97 — secret_egress_guard prüft nur Werkzeug-Eingaben, Lecks als Prozess-Ausgabe
  bleiben unsichtbar (75 belegte Fälle nach Scharfstellen)

## Purpose

`secret_egress_guard.py` vergleicht heute nur den **Input** eines Tool-Aufrufs gegen bekannte
Secret-Werte. Ein Wert, der erst als **Ausgabe eines Prozesses** entsteht (z. B. eine
fehlschlagende Test-Assertion, die einen Konfigurationswert im Klartext druckt) und per
Shell-Redirect in eine Datei geschrieben wird, steht zu keinem Zeitpunkt im Tool-Input — der
Guard sieht ihn nie. Nach dem Schärfen des bestehenden Guards (2026-07-25) entstanden dennoch 75
belegte Klartext-Dateien mit gültigen Zugangsdaten außerhalb jedes geschützten
Sitzungsordners, alle über exakt diesen Weg (`Befehl > /tmp/datei.log`).

Diese Spec fügt eine zweite, unabhängige Prüfung hinzu: keine Inhaltsanalyse der Ausgabe
(unmöglich in `PreToolUse`, bevor die Ausgabe existiert), sondern eine **syntaktische Prüfung
des Bash-Kommandotexts** auf Schreibziele außerhalb von Projekt und konfigurierten
Ausnahme-Verzeichnissen. Das Umleitungsziel steht im Kommando, bevor die Shell es ausführt — im
Gegensatz zum Wert selbst ist es in `PreToolUse` prüf- und blockierbar.

## Source

- **File:** `core/hooks/secret_egress_guard.py`
- **Identifier:** neue Funktionen `_shell_write_targets()`, `_is_outside_safe_zone()`,
  `find_unsafe_redirects()`; Erweiterung von `main()`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/bash_gate.py::_has_real_redirect()` / `_raw_redirect()` | Funktion (Vorlage, nicht importiert) | Bereits gehärtetes Muster für Shell-Redirect-Erkennung via `shlex` mit Fallback bei verschachtelter Shell (`sh -c`, `eval`) — dieselbe Tokenisierung, hier um Ziel-Extraktion statt reiner Bool-Erkennung erweitert. Bewusst eine parallele, kommentierte Kopie statt eines Imports (siehe ADR) — demselben Muster folgend wie die bestehende, im Code selbst dokumentierte Duplikation zwischen `bash_gate.py` und `secrets_guard.py` ("kein Guard-Drift"). |
| `core/hooks/override_token.py::has_valid_token()` | Funktion | Erlaubt die neue Prüfung zu übersteuern (siehe Scope) — anders als die bestehende Literal-Wert-Prüfung, die absichtlich NIE übersteuerbar ist |
| `core/hooks/hook_utils.py::find_project_root()`, `log_gate_event()` | Funktion | Bereits von `secret_egress_guard.py` genutzt, unverändert weiterverwendet |
| `config.yaml::secret_egress_guard` | Config-Sektion | Erweitert um zwei neue, optionale Felder (siehe Scope) |

## Scope

- **Affected Files:**
  `core/hooks/secret_egress_guard.py` (MODIFY — neue Funktionen + `main()`-Erweiterung),
  `config.yaml` (MODIFY — zwei neue Felder unter `secret_egress_guard:`, mit Kommentar),
  `tests/test_secret_egress_redirect_guard_97.py` (CREATE),
  `CHANGELOG.md` (MODIFY),
  `.claude-plugin/plugin.json`, `README.md` (MODIFY, Versionsbump)
- **Estimated Changes:** ~90-120 LoC in `secret_egress_guard.py`, ~10 LoC config, ~200-260 LoC
  neue Testdatei (Subprozess-Integrationstests wie beim Rest der Datei üblich)
- **Bewusst NICHT im Scope** (siehe Known Limitations für die Begründung je Punkt):
  - Inhaltsprüfung von Prozess-Ausgaben (`PostToolUse`, kann nicht blockieren)
  - Tool-spezifische Ausgabe-Flags (`curl -o`, `wget -O`, `scp`, `rsync`, `dd of=`,
    Cloud-CLI-Uploads) — im Issue selbst als `--output` erwähnt, hier zurückgestellt
  - Nicht-Bash-Tools (Write/Edit mit Pfad außerhalb des Projekts) — anderer Mechanismus
    (`worktree_write_guard.py` deckt einen Teilaspekt bereits ab), anderes Issue
  - Erkennung von Datei-Schreiben ohne Shell-Redirect-Syntax (z. B.
    `python3 -c "open('/tmp/x','w').write(...)"`) — dieselbe Grenze, die das Issue selbst für
    seinen eigenen Vorschlag benennt

## Implementation Details

### 1. Schreibziele aus dem Bash-Kommando extrahieren

```python
def _shell_write_targets(command: str) -> list[str]:
    """Ziel-Pfade von '>', '>>' und 'tee' in einem Bash-Kommando.

    Tokenisierung identisch zu bash_gate.py::_has_real_redirect() (shlex mit
    Fallback auf den Roh-Scan bei verschachtelter Shell/eval oder Parse-Fehler)
    — hier um die Ziel-STRINGS statt eine reine Bool-Erkennung erweitert.
    Bei sh -c/eval-Fallback wird nur der rohe '>'-Scan geliefert (kein
    'tee'-Ziel aus dem Rohtext extrahierbar) — sicherheitshalber konservativ:
    ein Redirect-Fund im Rohtext reicht bereits, um zu blocken (siehe
    find_unsafe_redirects()).
    """
    if re.search(r"\b(?:ba|z|da|k)?sh\s+-c\b|\beval\b", command):
        return [m.group(1) for m in re.finditer(r"(?<![\d-])>{1,2}\s*(\S+)", command)
                if m.group(1) != "/dev/null" and not re.match(r"^&\d+$", m.group(1))]
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return [m.group(1) for m in re.finditer(r"(?<![\d-])>{1,2}\s*(\S+)", command)
                if m.group(1) != "/dev/null" and not re.match(r"^&\d+$", m.group(1))]

    targets = []
    for i, tok in enumerate(tokens):
        m = re.match(r"^\d*>{1,2}(.*)$", tok)
        if m:
            target = m.group(1) or (tokens[i + 1] if i + 1 < len(tokens) else "")
            if target and target != "/dev/null" and not re.match(r"^&\d+$", target):
                targets.append(target)
        elif tok == "tee" or tok.endswith("/tee"):
            for nxt in tokens[i + 1:]:
                if nxt in ("-a", "--append"):
                    continue
                if nxt.startswith("-"):
                    break  # andere Flag (-i, --output-error, ...) — kein Ziel-Token
                targets.append(nxt)
                break
    return targets
```

### 2. Sicherheitszone prüfen

```python
def _is_outside_safe_zone(target: str, root: Path, cfg: dict) -> bool:
    """True, wenn `target` außerhalb Projekt UND außerhalb aller konfigurierten
    Ausnahme-Verzeichnisse liegt. Relative Ziele werden wie in
    _targets_env_file() gegen Path.cwd() aufgeloest (dieselbe Annahme, die der
    Rest dieser Datei bereits trifft: die Hook-Subprocess-CWD entspricht der
    Ausfuehrungs-CWD des Bash-Tools)."""
    try:
        p = Path(target).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        resolved = str(p.resolve())
    except (OSError, ValueError):
        return False  # nicht als Pfad interpretierbar -> fail-open, wie der Rest der Datei
    if resolved.startswith(str(root.resolve()) + os.sep) or resolved == str(root.resolve()):
        return False
    for pattern in cfg["extra_allowed_write_dirs"]:
        if re.match(pattern, resolved):
            return False
    return True
```

### 3. Einstiegspunkt, parallel zu `find_leaks()`

```python
def find_unsafe_redirects(tool_name: str, tool_input: dict, cfg: dict, root: Path) -> list[str]:
    """Schreibziele außerhalb der Sicherheitszone, nur für Bash-Kommandos."""
    if not cfg["redirect_guard_enabled"] or tool_name != "Bash":
        return []
    command = tool_input.get("command", "")
    if not command:
        return []
    targets = _shell_write_targets(command)
    return [t for t in targets if _is_outside_safe_zone(t, root, cfg)]
```

### 4. `_get_config()` erweitert

```python
"redirect_guard_enabled": bool(cfg.get("redirect_guard_enabled", True)),
"extra_allowed_write_dirs": list(cfg.get("extra_allowed_write_dirs", [])),
```

### 5. `main()` — zweiter Check, NUR wenn der erste nichts findet

```python
hits = find_leaks(tool_name, tool_input, cfg, root)
if hits:
    ... # unveraendert, wie bisher: unbedingter Block, kein Override
    sys.exit(2)

unsafe = find_unsafe_redirects(tool_name, tool_input, cfg, root)
if unsafe and not has_valid_token():
    # neue Meldung, exit 2, override-faehig (siehe Scope-Begruendung)
    ...
    sys.exit(2)
sys.exit(0)
```

Die bestehende Literal-Wert-Prüfung wird durch diese Änderung nicht berührt — sie läuft
weiterhin zuerst, unverändert, ohne Override. Der neue Check greift nur, wenn sie nichts
gefunden hat.

### 6. `config.yaml` — zwei neue Felder

```yaml
secret_egress_guard:
  enabled: true
  min_length: 8
  ignore_keys: []
  extra_key_patterns: []
  scan_all_keys: false
  # Issue #97: blockt Bash-Umleitungen (>, >>, tee) auf Ziele ausserhalb des
  # Projekts. Eigener Kill-Switch, unabhaengig von 'enabled' oben -- die
  # bestehende Literal-Wert-Pruefung bleibt aktiv, auch wenn dieser Teil
  # abgeschaltet wird. Uebersteuerbar per 'override' (Override-Token), anders
  # als die Literal-Wert-Pruefung.
  redirect_guard_enabled: true
  # Regex-Muster (voller aufgeloester Pfad) fuer legitime Schreibziele
  # ausserhalb des Projekts, z.B. ein Sitzungs-Scratchpad-Verzeichnis. Leer
  # per Default -- es gibt keine plattformuebergreifend verlaessliche
  # Laufzeit-Signatur fuer "das Scratchpad" (kein CLAUDE_*-Env-Var liefert
  # diesen Pfad an Hooks). Projekte mit einer bekannten Konvention (z.B.
  # Claude-Code-Remote-Umgebungen: "^/tmp/claude-\\d+/") tragen sie hier ein.
  extra_allowed_write_dirs: []
```

## Expected Behavior

- **Input:** Ein `PreToolUse`-Aufruf für das `Bash`-Tool, dessen `command`-Feld einen echten
  Shell-Redirect (`>`, `>>`) oder eine `tee`-Umleitung auf ein Ziel außerhalb des
  Projektverzeichnisses und außerhalb jedes in `extra_allowed_write_dirs` konfigurierten Musters
  enthält.
- **Output:** Exit 2, Meldung nennt das unsichere Ziel und den Weg zur Konfiguration
  (`extra_allowed_write_dirs`) sowie den Override-Weg ("override" tippen). Ein Gate-Event wird
  geloggt (`hook="secret_egress_guard"`, `reason` nennt das Ziel — anders als beim
  Literal-Wert-Fund enthält diese Meldung KEIN Geheimnis, der Pfad selbst ist unkritisch).
- **Side effects:** Keine Aenderung am bestehenden Verhalten fuer: Nicht-Bash-Tools, Bash-Befehle
  ohne Schreibziel außerhalb der Zone, jeden Fall, in dem die bestehende Literal-Wert-Pruefung
  bereits greift (die läuft weiterhin zuerst und exklusiv).

## Known Limitations

- **Keine Inhaltspruefung.** Dieser Fix verhindert nicht jedes denkbare Laufzeit-Leck, nur den
  konkret gemessenen Weg (Shell-Redirect auf ein Ziel ausserhalb der Zone). Ein Wert, der auf
  einem anderen Weg nach aussen dringt (siehe naechste Punkte), bleibt unsichtbar — exakt die
  Grenze, die das Issue selbst fuer seinen eigenen Vorschlag benennt.
- **Tool-spezifische Ausgabe-Flags nicht abgedeckt** (`curl -o`, `wget -O`, `scp`, `rsync`,
  `dd of=`, Cloud-CLI-Uploads). Das Issue nennt `--output` als dritten Fall neben `>`/`tee`. Eine
  generische Erkennung muesste pro Tool wissen, welche Flag-Namen ein Schreibziel markieren --
  ohne gemessene Faelle waere jede Liste geraten. Bewusst zurueckgestellt: das
  Gate-Event-Log aus #181 macht ab jetzt messbar, ob dieser Weg in der Praxis vorkommt --
  Erweiterung erst auf Basis echter Daten, nicht auf Verdacht (dieselbe Haltung, mit der #181
  selbst begruendet wurde).
- **Kein plattform-/hosting-uebergreifendes Signal fuer "das Scratchpad".** Untersucht: es
  existiert kein `CLAUDE_*`-Environment-Var, das einer PreToolUse-Hook-Subprocess den
  Scratchpad-Pfad der aktuellen Session mitteilt (geprüft gegen die tatsaechliche
  Env-Variablen-Liste dieser Session). Der Default-Scope ist deshalb bewusst streng
  (nur Projektverzeichnis sicher) mit einer konfigurierbaren Erweiterung
  (`extra_allowed_write_dirs`) statt eines geratenen, moeglicherweise falschen Defaults.
  Konsequenz: ein Redirect ins Scratchpad wird ohne Projekt-spezifische Config-Erweiterung
  blockiert (Fehlalarm mit Override-Ausweg), bis ein Projekt sein eigenes Muster eintraegt.
- **Relative Ziele werden gegen `Path.cwd()` der Hook-Subprocess aufgeloest**, nicht gegen eine
  explizite CWD des Bash-Tool-Aufrufs (der Tool-Input traegt keine). Dieselbe Annahme trifft
  bereits `_targets_env_file()` in derselben Datei -- kein neues Risiko, nur fortgefuehrt.
- **`sh -c`/`eval`-Fallback liefert keine `tee`-Ziele**, nur den rohen `>`-Scan (siehe
  Docstring von `_shell_write_targets()`). Sicherheitshalber genuegt ein Redirect-Fund im
  Rohtext bereits zum Block -- ein verschachteltes `tee` ohne begleitenden `>`/`>>` in
  derselben verschachtelten Shell wuerde in diesem Randfall nicht separat erkannt. Seltener,
  zusammengesetzter Fall (verschachtelte Shell UND ausschliesslich `tee` ohne Redirect-Zeichen);
  nicht Teil der gemessenen 75 Faelle.
- **Override hebt die neue Pruefung fuer die volle Stunde des Tokens auf**, nicht nur fuer den
  einen Aufruf. Konsistent mit dem bestehenden Override-Mechanismus im Rest des Frameworks,
  aber bewusst grosszuegiger als ein einmaliger Bypass.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Der im Issue gemessene Fall (`uv run pytest > /tmp/pytest_full.log`) wird von einem
      Integrationstest gegen den echten Hook nachgestellt und blockiert
- [ ] Die bestehende Literal-Wert-Pruefung (find_leaks) verhaelt sich in JEDEM bestehenden Test
      exakt wie vor dieser Aenderung (Regressionslauf gruen, insbesondere
      `tests/test_egress_guard.py` und `tests/test_config_yaml_secrets_pattern_drift_145.py`)
- [ ] `config.yaml` und der Code-Default fuer die zwei neuen Felder sind identisch (kein neuer
      Drift der Klasse #145/#146)
- [ ] `CHANGELOG.md`, `.claude-plugin/plugin.json`, `README.md` sind aktualisiert (MINOR-Bump,
      siehe ADR)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen)

## Acceptance Criteria

- **AC-1:** Given ein Bash-Kommando `uv run pytest > /tmp/pytest_full.log` (der im Issue
  gemessene Fall) / When `secret_egress_guard.py` es prueft / Then Exit 2, Meldung nennt
  `/tmp/pytest_full.log` als unsicheres Ziel.
  - Test: `test_measured_incident_pytest_redirect_to_tmp_is_blocked`
- **AC-2:** Given ein Bash-Kommando, das per `>` oder `>>` in eine Datei INNERHALB des
  Projektverzeichnisses schreibt / When geprueft / Then Exit 0, kein Block.
  - Test: `test_redirect_inside_project_is_allowed`
- **AC-3:** Given `config.yaml::secret_egress_guard.extra_allowed_write_dirs` enthaelt ein
  Muster, das das Redirect-Ziel matcht / When geprueft / Then Exit 0, kein Block.
  - Test: `test_redirect_matching_extra_allowed_dir_is_allowed`
- **AC-4:** Given ein Bash-Kommando mit `| tee /tmp/x.log` (Ziel ausserhalb der Zone) / When
  geprueft / Then Exit 2.
  - Test: `test_tee_redirect_outside_project_is_blocked`
- **AC-5:** Given ein gueltiger Override-Token (`override_token.has_valid_token()` == True) UND
  ein Redirect ausserhalb der Zone / When geprueft / Then Exit 0 — der NEUE Check ist
  uebersteuerbar.
  - Test: `test_valid_override_token_allows_redirect_outside_zone`
- **AC-6:** Given ein Bash-Kommando, das GLEICHZEITIG einen ausgeschriebenen Secret-Wert im
  Input UND einen Redirect ausserhalb der Zone enthaelt, OHNE Override-Token / When geprueft /
  Then Exit 2 mit der Literal-Wert-Meldung (unveraendertes Verhalten hat Vorrang) — nicht mit
  der neuen Redirect-Meldung.
  - Test: `test_literal_secret_hit_takes_precedence_over_redirect_check`
- **AC-7:** Given ein Nicht-Bash-Tool (z. B. `Write`) mit einem `file_path` ausserhalb des
  Projekts / When geprueft / Then Exit 0 — dieser Check gilt ausschliesslich fuer das
  `Bash`-Tool (Scope-Grenze, siehe Known Limitations).
  - Test: `test_non_bash_tool_is_not_checked_by_redirect_guard`
- **AC-8:** Given `secret_egress_guard.redirect_guard_enabled: false` in der Config / When ein
  Redirect ausserhalb der Zone geprueft wird / Then Exit 0 — eigener Kill-Switch, unabhaengig
  von `enabled` (Gesamt-Guard bleibt aktiv fuer die Literal-Wert-Pruefung).
  - Test: `test_redirect_guard_disabled_still_checks_literal_leaks`
- **AC-9:** Given ein Redirect-Ziel `2>&1` (FD-Duplizierung) oder `/dev/null` / When geprueft /
  Then Exit 0 — keine Regression gegenueber der bestehenden `_has_real_redirect()`-Ausnahme in
  `bash_gate.py`, die dieselben Faelle kennt.
  - Test: `test_fd_duplication_and_devnull_are_not_flagged_as_targets`
- **AC-10:** Given ein `>` als Teil eines quoted Freitexts (`gh pr create --body "... a > b
  ..."`), kein echter Redirect / When geprueft / Then Exit 0 — dieselbe shlex-Absicherung wie in
  `bash_gate.py`, hier fuer denselben False-Positive-Typ wiederverwendet.
  - Test: `test_arrow_inside_quoted_text_is_not_flagged`

## Test Plan

`tests/test_secret_egress_redirect_guard_97.py`, Subprozess-Integrationstests gegen den echten
Hook (Stilvorlage: `tests/test_config_yaml_secrets_pattern_drift_145.py` — echte `config.yaml`
in ein `tmp_path`-Projekt kopiert, damit Config-Anteil und Code-Anteil gemeinsam getestet
werden):

- Je ein Test pro AC-1 bis AC-10 oben (AC-7 zusaetzlich verschaerft: eine Write-Content, die
  zufaellig wie ein Redirect AUSSIEHT, darf nicht als einer gewertet werden — der Check liest
  ausschliesslich das `command`-Feld eines Bash-Aufrufs, kein rekursiver String-Scan)
- Zusaetzliche Unit-Tests direkt gegen `_shell_write_targets()` und `_is_outside_safe_zone()`
  fuer die Randfaelle aus den Known Limitations (sh -c-Fallback, relative Pfade)
- `TestConfigYamlMatchesCodeDefaults` — config.yaml und Code-Default duerfen fuer die zwei
  neuen Felder nicht auseinanderlaufen (dieselbe Drift-Klasse wie #145/#146)

Regressions-Referenz (muss unveraendert gruen bleiben):
- `pytest tests/test_egress_guard.py`
- `pytest tests/test_config_yaml_secrets_pattern_drift_145.py`
- `pytest tests/test_gate_event_log_181.py` (secret_egress_guard ist dort mitgetestet)

### Nachweis

- Ausgangsstand (Branch von origin/main nach #181): 1068 passed, 4 skipped
- GREEN: 1097 passed, 4 skipped (29 neue in `tests/test_secret_egress_redirect_guard_97.py`,
  keine bestehenden veraendert)

**Gegenprobe (Mutation).** Sechs gezielte Verfaelschungen, jede wurde rot: `_shell_write_targets()`
liefert immer `[]` (8 Tests rot) · `_is_outside_safe_zone()` liefert immer `False` (4 Tests rot) ·
Override-Pruefung aus `main()` entfernt (1 Test rot) · `redirect_guard_enabled` im Code auf `True`
festgenagelt, Config-Wert ignoriert (1 Test rot) · `config.yaml` von beiden neuen Feldern
abweichend gesetzt (2 Tests rot) · Bash-only-Beschraenkung aus `find_unsafe_redirects()` entfernt
(1 Test rot — deckte einen echten Praezisierungsbedarf auf: die urspruengliche AC-7-Testfassung
haette diese Mutation NICHT gefangen, da das Beispiel keinen redirect-aehnlichen Text enthielt;
Test verschaerft, bevor er in diese Spec aufgenommen wurde). Arbeitsbaum nach jeder Mutation
nachweislich sauber wiederhergestellt (`diff` gegen Schnappschuss vor der ersten Mutation).

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Neue Faehigkeit (ein bisher nicht existierender Blockade-Grund fuer eine bisher
  nicht gepruefte Angriffsflaeche), kein Bugfix eines bestehenden Verhaltens — MINOR-Bump nach
  Repo-Konvention (siehe CHANGELOG-Muster: 3.21.0 CI-Spec-Gate, 3.29.0 Gate-Event-Log, beides
  MINOR fuer neue Faehigkeiten). Exakte Zielversion wird beim Umsetzen dieser Spec gegen den dann
  aktuellen `main`-Stand bestimmt (dieselbe Vorsicht, die sich in dieser Session mehrfach als
  noetig erwiesen hat: Versionsnummern verschieben sich durch parallele Sessions).

  Zwei bewusste Architektur-Entscheidungen, die eine eigene ADR-Zeile verdienen:
  1. **Parallele Kopie statt Import** von `bash_gate.py`s Redirect-Parsing: passt zum
     bestehenden Repo-Muster (secrets_guard.py/bash_gate.py sind bereits parallel, mit
     Kommentar-Verweis, kein gemeinsames Modul) — jeder Guard bleibt in sich geschlossen und
     unabhaengig lauffaehig, kein Kopplungsrisiko zwischen zwei Kern-Hooks.
  2. **Neuer Check ist uebersteuerbar, die bestehende Literal-Wert-Pruefung bleibt es nicht** —
     unterschiedliches Fehlerprofil (syntaktische Heuristik mit erwarteten Fehlalarmen vs.
     bestaetigter Literal-Treffer ohne legitimen Anwendungsfall).

## Changelog

- 2026-09-22: Initial spec created
