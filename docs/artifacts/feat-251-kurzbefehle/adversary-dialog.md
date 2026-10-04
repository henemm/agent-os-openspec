# Adversary Dialog — feat-251-kurzbefehle
Spec: docs/specs/feat-251-kurzbefehle.md
Datum: 2026-10-04 09:20

## Checkliste
- [x] **Input:** `alias_content(name, skill_text)`; Textdateien in `<scope>/.claude/commands/`; Aufrufe
- [x] **Output:** Generierte Dateien haben ein parsbares Frontmatter mit echter `description`, der Marker steht in der
- [x] **Side effects:** `--remove-aliases` ist eine löschende Operation, begrenzt auf markierte Dateien in
- [x] **AC-1:** Given eine mit `alias_content` erzeugte Weiterleitung / When ihr Frontmatter geparst wird / Then beginnt die Datei mit `---`, `description` ist der echte Text `Kurz-Alias für /agent-os-openspec:<name>` und die erste Zeile nach dem Frontmatter ist der Marker
- [x] **AC-2:** Given eine mit `alias_content` erzeugte Vollkopie (`disable-model-invocation: true`) / When ihr Frontmatter geparst wird / Then ist `description` die echte Beschreibung aus dem `SKILL.md`, der Marker steht direkt nach dem Frontmatter, und der Rest des Skill-Inhalts ist unverändert
- [x] **AC-3:** Given eine Datei mit dem alten Marker in Zeile 1 / When `is_alias_file` und `find_stale_aliases` laufen / Then gilt sie als generiert und wird als veraltet gemeldet
- [x] **AC-4:** Given eine Datei mit altem Marker im Projekt / When `setup.py --refresh-aliases` läuft / Then hat sie danach den Inhalt von `alias_content` (neue Position) und ist nicht mehr veraltet
- [x] **AC-5:** Given eine unmarkierte projekteigene Datei, auch mit Marker-Text mitten im Inhalt / When `is_alias_file`, `--refresh-aliases` und `--remove-aliases` laufen / Then ist `is_alias_file` falsch und die Datei bleibt byte-gleich unverändert
- [x] **AC-6:** Given ein Bereich mit markierten und unmarkierten Dateien / When `setup.py <pfad> --remove-aliases` läuft / Then sind alle markierten Dateien gelöscht und die Ausgabe nennt gelöschte (`Removed:`) und behaltene (`Kept:`) Dateien namentlich
- [x] **AC-7:** Given ein Bereich ohne markierte Dateien oder ohne `.claude/commands/` / When `--remove-aliases` läuft / Then ist es ein No-op: nichts wird gelöscht, die Ausgabe meldet `0 removed`, Exit-Code 0
- [x] **AC-8:** Given `--remove-aliases --global` und ein gesetztes Home-Verzeichnis (Test-Home) / When es läuft / Then wirkt es auf `<home>/.claude/commands/` und nicht auf den Projektordner
- [x] **AC-9:** Given `migrate_to_plugin.py` und ein Projekt mit projekteigenen Befehlen / When die Migration läuft / Then werden projekteigene Befehle weiterhin nicht gelöscht (bestehende Tests bleiben grün)
- [x] **AC-10:** Given die 15 versionierten Kopien in `.claude/commands/` / When `find_stale_aliases` und die Marker-Position geprüft werden / Then ist die Liste der veralteten leer und jede Kopie trägt den Marker in der neuen Position (zusätzlich bleibt `tests/test_repo_own_aliases_147.py` grün)

## Dialog

### Runde 1
**Adversary:** Breiter Angriff auf Erkennung, Erzeugung und Entfernen.

Testlauf: Vollsuite 1866 passed, 0 failed, 23 skipped (122 s). Die zwei neuen Testdateien `tests/test_alias_marker_position_251.py` und `tests/test_alias_remove_251.py` sind enthalten.

Probe 1, `is_alias_file` (Python-Aufruf gegen `core/hooks/alias_sync.py`):

| Fall | Ergebnis |
|---|---|
| Frontmatter ohne schließendes `---`, Marker in Zeile 3 | False |
| Fremdtext zwischen Frontmatter und Marker | False |
| Marker im Codeblock im Body | False |
| Leere Datei | False |
| Datei nur `---` | False |
| Frontmatter mit Leerzeile vor dem Marker | False |
| Marker mitten in einer Textzeile nach dem Frontmatter | False |
| Marker erst in Zeile 2 ohne Frontmatter (`intro\n<marker>`) | False |
| Schließendes `---` mit Trailing-Spaces | False |
| Altformat: Marker in Zeile 1 | True |
| Neuformat, CRLF-Zeilenenden | True (`splitlines` entfernt `\r`) |
| Marker in Zeile 1, danach ungeschlossener Frontmatter | True (korrekt, Altposition) |

Die Strenge ist spezifikationsgemäß. Kein Fall außerhalb von Zeile 1 und der Zeile direkt nach dem geschlossenen Frontmatter wird erkannt.

Probe 2, `alias_content`:
- Eine SKILL.md ohne Frontmatter (nur `disable-model-invocation: true` im Body) bekommt den Marker vorn (Rückfall auf die Altposition). `is_alias_file` ist True, also konsistent und kein Einfrieren.
- Ein Skill mit Frontmatter und ohne Zeilenumbruch nach dem schließenden `---` bekommt den Marker angehängt. `is_alias_file` ist True.
- Ein Skill mit CRLF fällt wegen `lines[0] != "---"` auf die Altposition zurück. Das ist erkannt, aber nicht neu positioniert (siehe F003). Die Skills im Repo enthalten kein einziges `\r`, in der Praxis ist das also nicht betroffen.

Probe 3, Idempotenz und Altformat-Anhebung. Zwei Altformat-Dateien (`10-context`, `70-deploy`) sowie eine projekteigene Datei `own.md` mit Marker mitten im Text lagen in einem Wegwerf-Projekt.
- Vorher: `find_stale_aliases` liefert `['10-context', '70-deploy']`.
- `refresh_command_aliases` meldet `2 refreshed, 0 removed, none created`. Danach ist die Liste der veralteten leer.
- Zweiter Lauf: `0 refreshed`, alle Dateien byte-identisch zum Stand nach dem ersten Lauf. `own.md` ist byte-gleich zum Ausgangszustand.
- `find_stale_aliases(skills, <repo>/.claude/commands)` liefert `[]`.

Probe 4, Entfernen (Aufruf von `setup.remove_command_aliases` im Wegwerf-Ordner mit Symlink, Verzeichnis, Fremdtypen und Sonderzeichen):
- Ein Symlink `link.md` auf eine Datei mit Marker außerhalb des Bereichs wird entfernt, das Ziel `outside.md` bleibt bestehen. `Path.unlink` löscht nur den Link.
- Ein hängender Symlink bleibt als `Kept`, weil `is_file()` False ist.
- Das Verzeichnis `sub.md/` wird nicht gelöscht, aber als `Kept: sub.md` gemeldet (kosmetisch, siehe F002).
- `notmd.txt` mit Marker bleibt unberührt, weil nur `*.md` erfasst wird.
- `mine.md` (Marker im Text, Zeile 2) bleibt `Kept`.
- Der Dateiname `sp ä$.md` wird korrekt gelöscht und gemeldet.
- Eine binäre Datei `bin.md` (`\xff\xfe\x00...`) führt zu `UnicodeDecodeError`, und der Lauf bricht komplett ab. Da `find_aliases` zuerst alles liest und danach löscht, wird in diesem Fall nichts gelöscht. Das ist kein Datenverlust, aber ein Traceback statt einer Fehlermeldung (F001).

Probe 5, CLI per `subprocess` mit Test-HOME im Scratchpad:
- `<projekt> --remove-aliases --global` hat nur `<home>/.claude/commands/g.md` entfernt. Der Projektordner blieb unverändert (`p.md` und `own.md` vorhanden). Exit 0.
- `--remove-aliases --refresh-aliases` gemeinsam: Es läuft nur das Entfernen, `p.md` ist weg, `own.md` bleibt, und es wird nichts angelegt. Das Entfernen hat Vorrang.
- Wiederholter Lauf: `0 removed, 1 kept`, Exit 0.
- Bereich ohne `.claude/commands/`: `Command aliases: 0 removed, 0 kept.`, Exit 0, es wird kein Ordner angelegt.
- Nicht existierender Projektpfad: `ERROR: Project path does not exist`, Exit 1. Das ist das bestehende Verhalten der Hauptfunktion.

Rückwärtskompatibilität: `migrate_to_plugin.py` ist unverändert (nicht im Diff). Es erkennt den Marker per Teilstring (`migrate_to_plugin.py:460`, `:510`: `"openspec-alias:" in content` führt zu `continue`). Eine projekteigene Datei mit Marker im Text wird deshalb nicht angefasst, vor wie nach der Änderung. Die Spec nennt genau diese Grenze in "Weitere Grenzen". `session_banner` importiert `find_stale_aliases` aus `alias_sync`, und Altformat gilt dort als veraltet.

Testumstellung in `tests/test_setup_command_aliases.py`: Die Hilfsfunktionen `_first_line_after_frontmatter` und `_full_copy` sind unabhängig von `alias_sync`. Sie verwenden die eigene `MARKER`-Konstante der Testdatei und eigenes Parsing. Die Aussagekraft ist nicht geschwächt, sondern strenger: die Datei muss mit `---` beginnen (Assert), und die Vollkopie wird byte-genau verglichen. Der Altmarker-Fall steht in den Tests der Spec (AC-3).

Spec-Treue: Die Ausgabestrings stimmen (`Removed:`, `Kept:`, `Command aliases: N removed, M kept.`). Der CHANGELOG-Eintrag steht nur unter `[Unreleased]`, es gibt keinen Versions-Bump. Handgeschrieben geändert sind nur `alias_sync.py`, `setup.py`, `CHANGELOG.md` und `tests/test_setup_command_aliases.py`, dazu 15 regenerierte Kopien. Das passt zum Umfang.

Befunde:
```
Finding:
  ID: F001
  Severity: MEDIUM
  Category: edge_case
  Code reference: core/hooks/alias_sync.py:94
  Description: find_aliases liest jede *.md per read_text() ohne Fehlerbehandlung; remove_command_aliases (setup.py:1123) fängt keine Ausnahme.
  Spec requirement: AC-6 — --remove-aliases löscht alle markierten Dateien eines Bereichs.
  Conflict: Eine einzige nicht UTF-8-lesbare .md in .claude/commands/ führt zu UnicodeDecodeError-Traceback, und es wird gar nichts entfernt (nichts gelöscht, kein Datenverlust, aber das Werkzeug ist für den Bereich unbenutzbar). migrate_to_plugin.py überspringt solche Dateien ausdrücklich.
  Remediation: In find_aliases per try/except (UnicodeDecodeError, OSError) unlesbare Dateien überspringen und in remove_command_aliases als Kept melden.

Finding:
  ID: F002
  Severity: LOW
  Category: edge_case
  Code reference: setup.py:1123
  Description: Die Kept-Liste nutzt commands_dir.glob("*.md") ohne is_file-Filter und meldet damit Verzeichnisse namens x.md und hängende Symlinks als Kept. Außerdem wird --global ohne --remove-aliases (setup.py:1268) stillschweigend ignoriert.
  Spec requirement: AC-6 — Ausgabe nennt behaltene Dateien namentlich.
  Conflict: Kosmetisch, ohne Datenfolgen; --global wirkt nur bei --remove-aliases, wie die Hilfe sagt.
  Remediation: Filter p.is_file() in der Kept-Liste; optional Warnung bei --global ohne --remove-aliases.

Finding:
  ID: F003
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/alias_sync.py:43
  Description: _frontmatter_close verlangt lines[0] == "---" exakt; eine SKILL.md mit CRLF oder Trailing-Spaces nach --- oder ohne Frontmatter bekommt den Marker in der Altposition (alias_content, Zeile 53).
  Spec requirement: AC-2 — Marker direkt nach dem Frontmatter.
  Conflict: Nur theoretisch; alle Skills im Repo sind LF mit Frontmatter, die Datei bleibt erkannt und wird nicht dauerhaft als veraltet gemeldet.
  Remediation: Optional tolerante Zeilenprüfung (rstrip).
```

Bewertung: Alle angegriffenen Punkte hielten stand. F001 ist ein Absturz bei einem seltenen Eingabezustand, ohne Datenverlust.

**Implementierer:** (nicht beteiligt, Kontextisolation: der Adversary hat die Belege selbst erbracht)

### Runde 2
**Adversary:** Tiefer auf das, was Runde 1 offen ließ.

1. Marker-Position im Repo (AC-10): `.claude/commands/50-implement.md` und `60-validate.md` beginnen mit `---`, dann `description: Kurz-Alias für /agent-os-openspec:<name>` und `---`, danach in Zeile 4 `<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->`. `find_stale_aliases(skills, <repo>/.claude/commands) == []`. Vollsuite grün, darunter `tests/test_repo_own_aliases_147.py`.
2. Spec-Strenge von `is_alias_file`: In `core/hooks/alias_sync.py:76` wird nur Zeile 1 oder die Zeile unmittelbar nach dem ersten geschlossenen `---` geprüft. Die Fälle "Marker mitten im Inhalt" (AC-5) und "Marker im Codeblock" sind False (Probe 1). `--refresh-aliases` und `--remove-aliases` fassen `own.md` nicht an, byte-gleich nach beiden Läufen.
3. Löschrisiko: `Path.unlink()` auf einem Symlink löscht nur den Link. Das Ziel außerhalb des Bereichs überlebt. Es werden nur direkte Kinder von `<scope>/.claude/commands/` per `glob("*.md")` angefasst, keine Rekursion.
4. Abbruchsicherheit: `find_aliases` baut die komplette Liste, bevor `remove_command_aliases` löscht. Ein Lesefehler (F001) führt daher nicht zu halbgelöschten Zuständen.
5. Kein Zugriff aufs echte HOME: Für `--global` wurde ein Test-Home im Scratchpad genutzt. `setup.py:1268` löst `Path.home()` auf, Probe 5 bestätigt, dass nur das Test-Home berührt wurde.
6. Idempotenz und Migrationsweg: Zweiter Refresh ist ein No-op (Probe 3). Altformat wird erkannt, als veraltet gemeldet und angehoben (`setup.py:1092`).
7. Frühe Einigung hinterfragt: Es wurde versucht, die Position zu brechen (CRLF, ohne Frontmatter, ungeschlossen, Leerzeile, Marker im Body). Das einzige Ergebnis ist F003 für einen aktuell nicht auftretenden Fall.

Fazit: Keine weiteren Befunde. F001 bis F003 bleiben als nicht blockierend offen.

**Implementierer:** (nicht beteiligt, Kontextisolation)

## Bestätigungen

Confirmation:
  AC: AC-1
  Code reference: core/hooks/alias_sync.py:53
  Evidence: Die Weiterleitung beginnt mit `---`, dann `description: Kurz-Alias für /agent-os-openspec:{name}`, `---`, dann der Marker. Bestätigt an `.claude/commands/50-implement.md` Zeilen 1-4.
  Status: CONFIRMED

Confirmation:
  AC: AC-2
  Code reference: core/hooks/alias_sync.py:53
  Evidence: Die Vollkopie fügt den Marker direkt hinter das Frontmatter ein, der Rest bleibt byte-gleich; `tests/test_setup_command_aliases.py` vergleicht per `_full_copy` exakt. `.claude/commands/60-validate.md` zeigt die echte Beschreibung.
  Status: CONFIRMED

Confirmation:
  AC: AC-3
  Code reference: core/hooks/alias_sync.py:76
  Evidence: `lines[0].startswith(_MARKER_PREFIX)` erkennt die Altposition; Probe "stale before ['10-context','70-deploy']".
  Status: CONFIRMED

Confirmation:
  AC: AC-4
  Code reference: setup.py:1092
  Evidence: `refresh_command_aliases` meldet `2 refreshed`, danach `find_stale_aliases == []`; zweiter Lauf ändert nichts.
  Status: CONFIRMED

Confirmation:
  AC: AC-5
  Code reference: core/hooks/alias_sync.py:76
  Evidence: Marker im Text, im Codeblock, hinter Fremdtext: False; `own.md` bleibt nach Refresh und Remove byte-gleich.
  Status: CONFIRMED

Confirmation:
  AC: AC-6
  Code reference: setup.py:1123
  Evidence: Ausgabe `Removed: ok.md`, `Kept: mine.md`, `Command aliases: 3 removed, 3 kept.`; nur markierte Dateien werden gelöscht.
  Status: CONFIRMED

Confirmation:
  AC: AC-7
  Code reference: core/hooks/alias_sync.py:94
  Evidence: `find_aliases` liefert bei fehlendem Ordner `[]`. Leerer Bereich: `Command aliases: 0 removed, 0 kept.`, Exit 0, kein Ordner angelegt.
  Status: CONFIRMED

Confirmation:
  AC: AC-8
  Code reference: setup.py:1268
  Evidence: `scope = Path.home() if args.global_scope else project_path`. Mit Test-HOME wurde nur `<home>/.claude/commands/g.md` gelöscht, der Projektordner blieb unberührt.
  Status: CONFIRMED

Confirmation:
  AC: AC-9
  Code reference: setup.py:1123
  Evidence: `migrate_to_plugin.py` unverändert und überspringt jede Datei mit `openspec-alias:` (Zeilen 460, 510); Vollsuite grün, einschließlich `test_migrate_to_plugin_keeps_project_commands_with_new_marker_files`.
  Status: CONFIRMED

Confirmation:
  AC: AC-10
  Code reference: core/hooks/alias_sync.py:43
  Evidence: `find_stale_aliases(skills, <repo>/.claude/commands)` ergibt `[]`; Marker in Zeile 4 der Kopien, `test_repo_own_aliases_147.py` grün.
  Status: CONFIRMED

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

═══════════════════════════════════════
VERDICT: VERIFIED
═══════════════════════════════════════
Die Implementierung hat den Angriff überstanden. Es gibt keinen CRITICAL- oder HIGH-Befund. Offen sind F001 (MEDIUM, ein Absturz bei nicht UTF-8-lesbarer .md ohne Datenverlust) sowie F002 und F003 (LOW, kosmetisch).
Tests: 1866 passed, 0 failed, 23 übersprungen
Edge cases: Alle geprüft; keine Spec-Verletzung, keine Löschung außerhalb markierter Dateien
Regressions: Keine gefunden (migrate_to_plugin unverändert, 15 Kopien nicht veraltet)
Checklist: 13/13 Punkte bewiesen (Input, Output, Side effects, AC-1 bis AC-10)

## Geprüfte Dateien

- sha256:605e8e6e207a40c45d000e91a80c1b3826ed0f981a1c9549150e3abf8b1aa53b  core/hooks/alias_sync.py
- sha256:1fc7d854c6cd0a109f5bc0052ff9bc80ed32f97addcc3835e6bac3a64aea29c6  setup.py
