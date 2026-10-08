---
entity_id: fix-399-start-wartung
type: bugfix
created: 2026-10-08
updated: 2026-10-08
status: draft
version: "1.0"
tags: [session-banner, alias-sync, sync-main, start-hinweis, kurzbefehle, fail-open]
test_targets: ["tests/test_session_banner.py", "tests/test_banner_behind_origin_185.py"]
workflow: fix-399-start-wartung
---

# Start-Hinweis erledigt die Wartung selbst (#399)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #399. Analyse und Befunde: `docs/context/fix-399-start-wartung.md`.

## Purpose

Der Start-Hinweis (`session_banner.py`, SessionStart) zeigt dem PO heute Shell-Befehle zum Abtippen (`setup.py ~ --refresh-aliases`, `session_singleton_guard.py sync-main`) und Git-Vokabular. Das verstößt gegen die Regel „der PO bekommt nie einen Shell-Befehl“. Künftig erledigt der Start die sichere Wartung selbst (Kurzbefehle in `~` auffrischen, Haupt-Ordner nachziehen) und meldet das in einer Klartext-Zeile; was nicht geht, geht als Hinweis an Claude (`additionalContext`), nie als Aufforderung an den PO.

## Source

- **File:** `core/hooks/session_banner.py` (Wartung, Ausgabeformat), `core/hooks/alias_sync.py` (neue Kernlogik), `setup.py` (`refresh_command_aliases`, delegiert), `hooks/hooks.json` (Timeout)
- **Identifier:** `alias_sync.refresh_aliases`, `session_banner.main`, `setup.refresh_command_aliases`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/alias_sync.py` | Modul | `find_stale_aliases`, `find_removed_aliases`, `alias_content`; erhält `refresh_aliases` |
| `setup.py` | Modul | ruft künftig `alias_sync.refresh_aliases`; Konsolenausgabe bleibt |
| `core/hooks/session_singleton_guard.py` | Modul | Referenzablauf `_do_sync_main` (Vorbedingungen); CLI `sync-main` bleibt unverändert |
| `core/hooks/config_loader.py` | Modul | Kill-Switch `session_banner.behind_check` bleibt |
| `core/hooks/hook_utils.py` | Modul | `framework_disabled`, fail-open-Bootstrap |
| `hooks/hooks.json` | Konfiguration | SessionStart-Timeout des Banners |
| git | Werkzeug | Fetch (bestehend), `merge --ff-only`, `status`, `worktree list` |
| Claude-Code-Hook-Doku (code.claude.com/docs/en/hooks) | Schnittstelle | SessionStart-Ausgabe `systemMessage` + `hookSpecificOutput.additionalContext`, Payload-Feld `source` |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/alias_sync.py` | MODIFY | Neue Funktion `refresh_aliases(skills_dir, commands_dir, loaded_version) -> (refreshed, removed)` (Kernlogik aus `setup.py`) |
| `setup.py` | MODIFY | `refresh_command_aliases` delegiert an `alias_sync.refresh_aliases`; Ausgabe unverändert |
| `core/hooks/session_banner.py` | MODIFY | `~` automatisch auffrischen; Projekt-Scope nur Hinweis an Claude; Haupt-Ordner nachziehen; Ausgabe als JSON mit `systemMessage` + `additionalContext` |
| `hooks/hooks.json` | MODIFY | Banner-Timeout 5 auf 10 s |
| `tests/test_session_banner.py` | MODIFY | Befehlstext-Assertions werden zu Wirkungs-Assertions; neue Tests für Auffrischen, Projekt-Scope, compact, fail-open, Timeout |
| `tests/test_banner_behind_origin_185.py` | MODIFY | Nachziehen sauber, Abbruch bei lokalen Änderungen, Worktree still |
| `CHANGELOG.md` | MODIFY | Eintrag nur unter `[Unreleased]`, kein Versions-Bump |

### Estimated Changes

- Files: 7 (davon 2 Tests, 1 Changelog). Das Limit von 4–5 Dateien wird überschritten, weil es ein gemeinsames Ziel ist („der PO sieht keinen Befehl mehr“); Aufteilung wäre künstlich (vgl. Memory „Bündel über Limit: ein Ticket“).
- LoC: Produktivcode ca. +160/−60, Tests ca. +100/−20. Spec/Kontext/Briefing zählen im LoC-Gate zusätzlich (#294).
- Risiko: MEDIUM — der Banner war bisher rein lesend und schreibt erstmals (Kurzbefehle in `~`, Merge im Haupt-Ordner); er läuft in jeder Sitzung jedes Projekts. `core/hooks/` ist Infrastruktur, Gegenprüfung mit hohem Risiko.

## Implementation Details

**1. Gemeinsame Kernlogik.** `alias_sync.refresh_aliases(skills_dir, commands_dir, loaded_version)` überschreibt veraltete markierte Kopien mit dem Inhalt aus den Skills und löscht markierte Aliase entfernter Befehle; es liefert `(refreshed, removed)` als Namenslisten. Es legt nie neu an (#87/#205) und fasst fremde, unlesbare oder unmarkierte Dateien nicht an (#353). `setup.py refresh_command_aliases` delegiert und gibt dieselben Konsolenzeilen aus wie bisher.

**2. Kurzbefehle in `~`.** Der Banner ruft `refresh_aliases` mit den Skills der GELADENEN Fassung und deren Version auf. #163: `find_stale_aliases(loaded_version=…)` nimmt nur Kopien ohne neueren Versions-Marker als die geladene Fassung, damit wird nie herabgestuft. Änderung vorhanden: sichtbare Zeile „Kurzbefehle aktualisiert (N)“. Alles in try/except.

**3. Projekt-Scope wird beim Start nicht geschrieben.** Die Kurzbefehle unter `<projekt>/.claude/commands` sind versioniert; ein Schreiben würde den Haupt-Ordner ungefragt ändern und das Nachziehen blockieren. Ist dort eine Kopie veraltet, geht nur ein Hinweis in `additionalContext`: Kurzbefehle im Projekt veraltet, im Arbeitsordner auffrischen (`setup.py … --refresh-aliases`) und mitliefern. Dieser Text steht nur im Claude-Kontext, nie in `systemMessage`.

**4. Haupt-Ordner nachziehen.** Nur wenn Hook-cwd == Haupt-Ordner (erste Zeile von `git worktree list`). Nach dem bestehenden Fetch (Budget bleibt 3 s) gelten die Vorbedingungen von `sync-main`: Upstream vorhanden, kein laufender Merge/Rebase, `status --porcelain --untracked-files=no` leer, HEAD ist Vorfahre von `@{u}`. Dann `merge --ff-only --quiet` mit eigenem Zeitbudget; Abbruch per SIGTERM, nie SIGKILL (`_kill_group` ist wegen `index.lock`-Resten ungeeignet). Erfolg: sichtbare Zeile „Projektstand aktualisiert (N Änderungen)“. Abbruch (eine Vorbedingung verletzt, Merge-Fehler, Zeitüberschreitung): nur `additionalContext` mit Grund und Auftrag an Claude, dem PO in Klartext zu erklären, was los ist.

**5. Worktree und compact.** Worktree-cwd: kein Fetch, keine Meldung zum Haupt-Ordner (Worktrees verzweigen von origin/HEAD, ein veralteter Haupt-Ordner schadet dort nicht). Payload `source == "compact"`: nur Versionszeile, keine Wartung.

**6. Ausgabeformat.** JSON `{"systemMessage": …, "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": …}}`; `additionalContext` nur, wenn es etwas für Claude gibt. Sichtbarer Text enthält kein `python3`, keine Shell-Befehle und kein Git-Vokabular (commit, merge, branch, fetch, origin, worktree, …).

**7. Robustheit.** fail-open bleibt: jede Exception führt zu Exit 0. Hook-Timeout in `hooks/hooks.json` 5 auf 10 s, Fetch-Budget bleibt 3 s, Gesamtbudget im Skript entsprechend. Kill-Switch `session_banner.behind_check` bleibt. CLI `sync-main` und `--refresh-aliases` bleiben bestehen.

**Ohne Modell geht es?** Ja — Dateivergleich, Versionsmarker und Git-Zustandsprüfung, die Regel ist der Weg.

**Alternativen:**

- **A (gewählt): Hook zieht selbst nach und frischt `~` auf.** Erledigt die Wartung deterministisch beim Start, ohne dass etwas liegen bleibt.
- **B (nicht gewählt): Hook merged nicht selbst, gibt nur `additionalContext` aus; Claude ruft `sync-main` über die vorhandene Guard-Ausnahme auf.** Vorteil: kein längerer Timeout, kein Merge im Hook. Nachteil: hängt davon ab, dass Claude den Hinweis befolgt — genau das Liegenbleiben, das #399 abstellen will.
- **C (nicht gewählt): nur Formulierung ändern.** Im Issue bereits als schwächer verworfen; der Befehl bliebe beim PO.
- **D (nicht gewählt): auch Projekt-Kurzbefehle beim Start auffrischen.** Würde versionierte Dateien im Haupt-Ordner ändern und das Nachziehen selbst blockieren.

## Expected Behavior

- **Input:** SessionStart-Payload (mit `source`), cwd = Haupt-Ordner oder Worktree, Kurzbefehle in `~` und im Projekt, Remote-Stand.
- **Output:** JSON mit `systemMessage` (Klartext, höchstens Versionszeile, „Kurzbefehle aktualisiert (N)“, „Projektstand aktualisiert (N Änderungen)“) und optional `additionalContext` (Hinweise und Aufträge an Claude).
- **Side effects:** Markierte veraltete Alias-Dateien in `~/.claude/commands` werden überschrieben, markierte Aliase entfernter Befehle gelöscht; im Haupt-Ordner wird fast-forward nachgezogen. Keine neuen Dateien in `~`, keine Schreibzugriffe im Projekt-Scope.

## Known Limitations

- Projekt-Kurzbefehle werden beim Start nie geschrieben; die Auffrischung bleibt Aufgabe von Claude im Arbeitsordner.
- Eine parallele Sitzung im Haupt-Ordner kann einen `index.lock`-Konflikt auslösen; das ist ein Abbruch mit Hinweis an Claude, kein Schaden.
- Der Start kann bis zu 10 s dauern (Fetch 3 s plus Merge-Budget); Claudes erste Antwort wartet auf den Hook.
- **Verteilung:** wirkt in Konsumenten-Projekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Nach dem Start mit einer veralteten Kurzbefehl-Kopie in `~` ist die Kopie aktuell, und der sichtbare Text enthält keine `python3`-Zeile
- [ ] Ein hinter dem Remote liegender, sauberer Haupt-Ordner ist nach dem Start nachgezogen; mit lokalen Änderungen bleibt er unverändert und nur Claude erhält den Hinweis
- [ ] Der Start bleibt fail-open und schnell (Timeout 10 s, Fetch 3 s)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given eine veraltete markierte Kopie eines Kurzbefehls in `~/.claude/commands` / When der Banner beim Start läuft / Then entspricht der Inhalt der Kopie der geladenen Fassung, die sichtbare Ausgabe enthält „Kurzbefehle aktualisiert“ und kein „python3“
  - Test: `tests/test_session_banner.py::test_start_frischt_veraltete_kopie_in_home_auf`
- **AC-2:** Given eine Kopie in `~` mit neuerem Versions-Marker als die geladene Fassung (#163) / When der Banner läuft / Then bleibt die Datei byte-identisch und es erscheint keine Aktualisierungszeile
  - Test: `tests/test_session_banner.py::test_start_stuft_kopie_mit_neuerem_marker_nicht_herab`
- **AC-3:** Given ein markierter Alias eines entfernten Befehls und eine unmarkierte Datei gleichen Namens in verschiedenen Ordnern unter `~` / When der Banner läuft / Then wird der markierte Alias gelöscht, die unmarkierte Datei bleibt bestehen
  - Test: `tests/test_session_banner.py::test_start_loescht_markierten_alias_entfernter_befehle_nicht_fremde_datei`
- **AC-4:** Given eine veraltete Kopie im Projekt-Scope (`<projekt>/.claude/commands`) / When der Banner läuft / Then ist die Datei unverändert, und der Hinweis steht nur in `additionalContext`, nicht in `systemMessage`
  - Test: `tests/test_session_banner.py::test_projekt_kopie_wird_nicht_geschrieben_nur_claude_hinweis`
- **AC-5:** Given ein Haupt-Ordner hinter dem Remote, sauber, cwd = Haupt-Ordner / When der Banner läuft / Then ist HEAD danach gleich dem Remote-Stand, und die sichtbare Zeile „Projektstand aktualisiert“ enthält kein Git-Vokabular und keinen Befehl
  - Test: `tests/test_banner_behind_origin_185.py::test_behind_sauber_wird_nachgezogen_ohne_git_vokabular`
- **AC-6:** Given ein Haupt-Ordner hinter dem Remote mit geänderter versionierter Datei / When der Banner läuft / Then bleibt HEAD unverändert, der Hinweis mit Grund und Auftrag steht nur in `additionalContext`, und `systemMessage` enthält keinen Befehl
  - Test: `tests/test_banner_behind_origin_185.py::test_behind_mit_lokalen_aenderungen_nur_claude_hinweis`
- **AC-7:** Given cwd = Worktree, Haupt-Ordner hinter dem Remote / When der Banner läuft / Then wird nicht nachgezogen (Haupt-Ordner-HEAD unverändert) und es erscheint keine Meldung zum Haupt-Ordner
  - Test: `tests/test_banner_behind_origin_185.py::test_worktree_cwd_zieht_nicht_nach_und_schweigt`
- **AC-8:** Given Payload mit `source == "compact"` und veralteter Kopie in `~` / When der Banner läuft / Then wird nichts aufgefrischt und nichts nachgezogen; ausgegeben wird nur die Versionszeile
  - Test: `tests/test_session_banner.py::test_source_compact_fuehrt_keine_wartung_aus`
- **AC-9:** Given der bestehende Testbestand zu `setup.py --refresh-aliases` / When die Regressionstests laufen / Then bleiben sie grün (Konsolenausgabe von `setup.py` unverändert)
  - Test: `tests/test_setup_command_aliases.py`, `tests/test_bug_typ_entfernt_333.py` (unverändert, Lauf grün)
- **AC-10:** Given eine Exception in der Wartung (z. B. nicht lesbares Skills-Verzeichnis oder schreibgeschütztes `~`) / When der Banner läuft / Then endet er mit Exit 0 und gibt keinen Traceback auf stdout aus (fail-open)
  - Test: `tests/test_session_banner.py::test_exception_in_wartung_bleibt_fail_open`
- **AC-11:** Given `hooks/hooks.json` / When der SessionStart-Eintrag für `session_banner.py` gelesen wird / Then ist sein `timeout` 10
  - Test: `tests/test_session_banner.py::test_hooks_json_banner_timeout_ist_10`

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_session_banner.py` (AC-1 bis AC-4, AC-8, AC-10, AC-11; hermetisch mit Fake-Plugin und Fake-HOME, Banner als Subprozess; bestehende Tests, die den Befehlstext prüfen, werden auf Wirkung umgestellt)
- `pytest tests/test_banner_behind_origin_185.py` (AC-5 bis AC-7; echte Git-Repos in tmp_path: Remote, Klon, Worktree)
- GIVEN eine veraltete Kopie in `~` WHEN der Banner startet THEN ist sie aktuell und der sichtbare Text frei von `python3` (AC-1)
- GIVEN ein Haupt-Ordner mit lokalen Änderungen hinter dem Remote WHEN der Banner startet THEN bleibt HEAD stehen und nur Claude erhält den Grund (AC-6)
- RED-Nachweis: Vor der Implementierung schlagen AC-1, AC-3 bis AC-8, AC-10 (soweit Wirkung geprüft) und AC-11 fehl; AC-2 ist bereits grün, weil der Banner heute nichts schreibt.
- Regressionslauf (AC-9): `tests/test_setup_command_aliases.py`, `tests/test_bug_typ_entfernt_333.py`, `tests/test_sync_main_169.py`, danach die Vollsuite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Erweiterung der bestehenden Verantwortung des Start-Hinweises (Zustand prüfen und melden) um das Beheben ungefährlicher Fälle, mit denselben Regeln wie die vorhandenen CLI-Werkzeuge (`--refresh-aliases`, `sync-main`); keine neue Architektur, keine neue Abhängigkeit. Dass der Hook erstmals beim Start schreibt, ist auf markierte Alias-Dateien in `~` und einen fast-forward im sauberen Haupt-Ordner begrenzt; das Projekt-Scope bleibt bewusst unberührt. Alternativen (nur Hinweis an Claude, nur Formulierung ändern, Projekt-Scope mitschreiben) sind unter Implementation Details bewertet und verworfen; keine frühere ADR wird gekippt.

## Changelog

- 2026-10-08: Initial spec created (#399)
