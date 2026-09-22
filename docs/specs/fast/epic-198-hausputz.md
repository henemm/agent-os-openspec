# Fast Track: Hausputz — sechs bestätigte Kleinfehler (Epic #198, 3.28.0)

## Problem

Sechs Befunde, die einzeln zu klein waren, um je vorgezogen zu werden, und zusammen einen
Vormittag kosten. Gemeinsames Merkmal: jeder machte etwas Grundlegendes unzuverlässig.

Der teuerste ist #154. `modules/ios-swiftui/hooks/test_lock_guard.py` rief seinen Modul-Guard
beim *Import* auf (`sys.exit(0)` auf Modulebene). Der pytest-Collector fängt `SystemExit` beim
Einsammeln nicht ab, und die Datei heißt `test_*`, wird also eingesammelt. Ein nacktes
`python3 -m pytest` — der naheliegende Aufruf — endete deshalb mit INTERNALERROR, bevor ein
einziger Test lief. Ein abbrechender Sammellauf verdeckt echte Fehlschläge; wer ihn sieht, hält
ihn für ein Setup-Problem und nicht für ein Ergebnis.

Der folgenreichste ist #159. `setup.py::update_project` schrieb `framework_version.json` blind neu
und verlor dabei `plugin_mode`, `version_source` und `note`. Ein einziges `--update` stufte ein
Plugin-Modus-Projekt still auf Copy-Modus zurück und stellte die Falschauskunft wieder her, die
3.26.0 (PR #158) gerade beseitigt hatte.

Herkunft der Einstufung: Backlog-Triage vom 2026-09-21, PO-Freigabe für Epic #198 am selben Tag.

## Scope

- `modules/ios-swiftui/hooks/test_lock_guard.py`: Modul-Guard als `module_active()` in `main()`
  statt `sys.exit(0)` auf Modulebene (#154, Teil 1 von #70)
- `scripts/release_check.py`: `README`-Konstante, `readme_version()`, `check_readme_version()`,
  neue Zeile „README" in der Prüfliste von `main()` (#195)
- `README.md`: Versionszeile auf den tatsächlichen Stand (#195)
- `.gitignore`: `.worktrees/` (#70)
- `setup.py`: `GITIGNORE_RUNTIME_ENTRIES` + `ensure_gitignore_entries()`, aufgerufen von beiden
  Installationswegen und von `--update` (#78)
- `setup.py`: `update_project` liest den bestehenden Zustand und erhält den Plugin-Modus (#159)
- `setup.py`: Alias-Logik aus `core/hooks/alias_sync.py` importiert statt dupliziert;
  `copy_command_text()` ersetzt `{{OPENSPEC_VERSION}}` im Kopiermodus; `should_update_command()`
  vergleicht gegen den ersetzten Text (#150)
- Version 3.28.0, `skills/` neu erzeugt, CHANGELOG
- **Nicht enthalten:** Der Kopiermodus registriert weiterhin keine SessionStart-Hooks
  (dritter Punkt aus #150) — eigener Zuschnitt, bleibt im Issue offen.

## Definition of Done

`python3 -m pytest` läuft ohne Zusatzpfad und ohne `--ignore` sauber durch. `release_check.py`
verweigert ein Release, dessen README eine andere Version nennt als `plugin.json`. Ein
`setup.py --update` auf ein Plugin-Modus-Projekt lässt es im Plugin-Modus. Ein frisch
installiertes Projekt hat die Laufzeit-Dateien des Frameworks in seiner `.gitignore`. Alias-Inhalt
und Versions-Platzhalter haben je genau eine Quelle.

## Acceptance Criteria

- **AC-1:** Given das Hook-Script `test_lock_guard.py`, When es importiert wird, Then wirft der Import kein `SystemExit`, und ein `pytest --collect-only` über das ganze Repo endet mit Rückgabewert 0 ohne INTERNALERROR.
- **AC-2:** Given dasselbe Script als Hook ausgeführt, When `OPENSPEC_ENABLED_MODULES` das Modul nicht enthält, Then beendet es sich mit 0 — die Guard-Wirkung bleibt unverändert erhalten.
- **AC-3:** Given ein README, dessen Versionszeile von `plugin.json` abweicht, When `release_check.py` läuft, Then meldet die Zeile „README" FAIL und nennt beide Zahlen; bei Gleichstand meldet sie OK.
- **AC-4:** Given ein Projekt im Plugin-Modus, When `setup.py --update` darauf läuft, Then bleibt `plugin_mode: true` erhalten, `framework_version` bleibt `null`, und `version_source` sowie `note` überleben auch wiederholte Updates.
- **AC-5:** Given ein Projekt im Copy-Modus, When `setup.py --update` darauf läuft, Then wird weiterhin die Framework-Version gestempelt — der Fix für den einen Modus darf den anderen nicht zerbrechen.
- **AC-6:** Given ein Projekt mit vorhandener `.gitignore`, When `ensure_gitignore_entries()` läuft, Then stehen alle Laufzeit-Einträge darin, vorhandener Inhalt bleibt unverändert, und ein zweiter Aufruf ändert nichts mehr.
- **AC-7:** Given die erzeugten Alias-Dateien aus `setup.py`, When sie mit `alias_sync.alias_content()` verglichen werden, Then sind sie zeichengleich, und `setup.py` enthält keine eigene Auswertung von `disable-model-invocation` mehr.
- **AC-8:** Given der Kopiermodus kopiert `30-write-spec.md`, When die Zieldatei gelesen wird, Then enthält sie die Versionsnummer statt `{{OPENSPEC_VERSION}}`, während die Quelldatei den Platzhalter behält.

## Test Plan

Fünf neue Testdateien, 40 Tests, benannt nach den Issue-Nummern:

- `tests/test_module_hook_import_154.py` — Import ohne Nebenwirkung, nackter Sammellauf, Guard-Wirkung in drei Varianten (AC-1, AC-2)
- `tests/test_readme_version_195.py` — Extraktion, Abgleich, Repo-Zustand, Prüfliste (AC-3)
- `tests/test_setup_update_preserves_plugin_mode_159.py` — Plugin-Modus, Copy-Modus, fehlende und unlesbare Datei (AC-4, AC-5)
- `tests/test_gitignore_runtime_state_70_78.py` — Repo-`.gitignore`, Eintragsliste, Idempotenz, fehlender Zeilenumbruch, beide Installationswege (AC-6)
- `tests/test_setup_alias_sync_150.py` — Zeichengleichheit mit `alias_sync`, unveränderte Überschreibregeln, Platzhalter-Ersetzung (AC-7, AC-8)

Nachweis:

- Ausgangsstand: 976 passed, 4 skipped
- RED vor der Umsetzung: 26 der 40 neuen Tests rot; die 14 grünen sichern unverändertes Verhalten
- GREEN: 1016 passed, 4 skipped — sowohl mit `pytest tests/` als auch mit nacktem `pytest`
- `sync_skills.py --check`: 16 Skills synchron

**Gegenprobe (Mutation):** Jeder der fünf Fixes wurde einzeln verfälscht und der zugehörige Test
erneut ausgeführt. Vier wurden sofort rot. Die fünfte Mutation (README-Zeile aus der Prüfliste
entfernen) **überlebte** — die Prüfung `"README" in stdout` war vakuös wahr, weil `README.md` als
geänderte Datei ohnehin in der Arbeitsbaum-Zeile steht. Der Test wurde an die Zeilenform der
Prüfliste gebunden (`^\s*(OK|FAIL)\s+README\s`) und die Mutation wiederholt: jetzt rot. Der Befund
ist im Test dokumentiert, damit er nicht zurückfällt.
