# Context: fix-399-start-wartung

## Request Summary
Der Start-Hinweis (`session_banner.py`, SessionStart) zeigt dem PO Shell-Befehle zum Abtippen
(`setup.py … --refresh-aliases`, `session_singleton_guard.py sync-main`). Ziel (#399): sichere
Wartung erledigt der Start selbst; was nicht geht, geht als Hinweis an Claude, nie an den PO.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/session_banner.py` (390 Z.) | Erzeugt alle drei Meldungen: `stale_alias_lines` (Z. 137), `removed_alias_lines` (Z. 166), `behind_lines` (Z. 312). Ausgabe nur als `systemMessage` (Z. 382) |
| `core/hooks/alias_sync.py` | `find_stale_aliases`, `find_removed_aliases`, `alias_content` — dieselbe Logik, die `setup.py` zum Schreiben nutzt |
| `setup.py:1278` `refresh_command_aliases` | Referenz-Ablauf: veraltete markierte Kopien überschreiben, markierte Aliase entfernter Befehle löschen, nie neu anlegen. Liest `FRAMEWORK_ROOT/skills` + `FRAMEWORK_VERSION` |
| `core/hooks/session_singleton_guard.py:822` `_do_sync_main` | Referenz-Ablauf Nachziehen: Abbruch bei Worktree-cwd, fehlendem Upstream, geänderten versionierten Dateien, abweichender Historie; sonst `fetch` + `merge --ff-only`. Ruft `sys.exit` — als Funktion nicht direkt aus dem Banner nutzbar |
| `hooks/hooks.json` | SessionStart: `session_singleton_guard.py register` → `session_banner.py`, beide `timeout: 5` |
| `tests/test_session_banner.py` (19 Tests) | Hermetisch: Fake-Plugin, Fake-HOME, Banner als Subprozess. Mehrere Tests prüfen heute den Text des Reparatur-Befehls (`--refresh-aliases`, Pfad der installierten Fassung, #163) — die werden sich ändern |
| `tests/test_banner_behind_origin_185.py` (9 Tests) | Echte Git-Repos (origin/clone/worktree) in tmp_path; `test_behind_shows_count_and_sync_main` prüft heute den `sync-main`-Text |
| `tests/test_sync_main_169.py` | Abbruchgründe von `sync-main` |
| `README.md:58`, `CLAUDE.md:313` | Doku zu `--refresh-aliases` / `sync-main` (CLI bleibt bestehen) |

## Existing Patterns
- Banner ist fail-open: jede Exception → Exit 0, keine Ausgabe. Gesamtbudget 4 s für den Git-Teil (Hook-Timeout 5 s), `_git()` mit eigener Prozessgruppe, kein Credential-Dialog (#371, #382).
- Der Fetch des Banners holt den Remote-Stand bereits — ein anschließendes `merge --ff-only` braucht kein zweites Netz.
- #163: Kopien mit neuerem Versions-Marker als die geladene Fassung bleiben unberührt (`find_stale_aliases(loaded_version=…)`), also kann ein Auffrischen mit den Skills der geladenen Fassung nie herabstufen.
- #87/#205: nur `--refresh`-Semantik (nie neu anlegen) ist im Scope `~` sicher.

## Dependencies
- Upstream: `alias_sync`, `config_loader` (`session_banner.behind_check`), `hook_utils.framework_disabled`, git.
- Downstream: jede Sitzung jedes Konsumenten-Projekts (Plugin-Modus). Copy-Modus-Projekte nutzen `.claude/settings.json`.

## Recherche (Claude-Code-Doku, https://code.claude.com/docs/en/hooks)
- SessionStart kennt `systemMessage` (für den Nutzer sichtbar) und `hookSpecificOutput.additionalContext` (nur in Claudes Kontext, als System-Hinweis vor dem ersten Prompt). Beides lässt sich in einer JSON-Ausgabe kombinieren; `hookEventName: "SessionStart"` ist Pflicht.
- SessionStart läuft auch bei `/clear`, `--resume`, `--continue` (Payload-Feld `source`) im Hintergrund; Claudes erste Antwort wartet auf den Hook.

## Existing Specs
- `docs/specs/fast/fix-205-alias-refresh.md` — `--refresh-aliases` eingeführt
- `docs/specs/fast/feat-169-main-sync.md` — `sync-main`
- `docs/specs/feat-251-kurzbefehle.md`, `docs/specs/feat-333-bug-typ-entfernen.md` — Aliase entfernter Befehle

## Risks & Considerations
- **Schreiben beim Start:** Der Banner war bisher rein lesend. Neu schreibt er in `~/.claude/commands` und ins Projekt — nur markierte Alias-Dateien. Unlesbare/fremde Dateien bleiben stehen (#353).
- **Nachziehen im Haupt-Ordner:** gleiche Abbruchregeln wie `sync-main` (keine geänderten versionierten Dateien, nur fast-forward). Parallele Sitzung im Haupt-Ordner → git `index.lock`-Konflikt ist ein Abbruch, kein Schaden.
- **Worktree-Sitzung:** `sync-main` verweigert Worktree-cwd; die Sitzung kann den Haupt-Ordner auch über Tools nicht anfassen (#169). Offene Frage für die Analyse: Hinweis an Claude, still, oder Nachziehen per `git -C <haupt>` aus dem Hook.
- **Zeitbudget:** 5-s-Hook-Timeout; Fetch-Budget heute 3 s. Merge muss in den Rest passen.
- **Tests, die den Befehlstext prüfen,** werden bewusst umgeschrieben (Text darf keine `python3`-Zeile mehr enthalten).
- **Herabstufen:** geladene Fassung älter als installierte (#163) → nur Kopien ohne neueren Marker werden aufgefrischt.

## Analysis

### Type
Bug (Verstoß gegen „PO bekommt nie einen Shell-Befehl“, nachgestellt 2026-10-08 mit Plugin 3.39.0 — siehe Issue)

### Zusätzliche Befunde (2026-10-08)
- **Projekt-Kurzbefehle sind versioniert:** In diesem Repo liegen 15 markierte Aliase unter `.claude/commands/` in git. Ein Auffrischen beim Start würde ungefragt Diffs erzeugen und — im Haupt-Ordner — den Ordner „dirty“ machen, was dann das Nachziehen blockiert. → Projekt-Scope wird beim Start NICHT geschrieben.
- **Worktrees verzweigen von origin/HEAD** (Claude-Code-Default `worktree.baseRef: "fresh"`, Rückfall auf lokales HEAD nur ohne Remote/Fetch; Quelle: https://code.claude.com/docs/en/worktrees). Ein veralteter Haupt-Ordner schadet der Worktree-Arbeit also nicht; relevant ist er nur für das Lesen im Haupt-Ordner vor `EnterWorktree`. → Aus Worktree-Sitzungen kein Fetch, keine Meldung.
- **Sitzungen starten im Haupt-Ordner** (Guard erzwingt danach `EnterWorktree`) — der Normalfall für das Nachziehen ist also gegeben.
- `_kill_group` schickt SIGKILL — für einen Merge ungeeignet (`index.lock`-Rest). Merge braucht eigenen Abbruchpfad mit SIGTERM.
- SessionStart-Payload-Feld `source` (`startup`/`resume`/`clear`/`compact`): bei `compact` nichts tun.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/alias_sync.py` | MODIFY | Neue Funktion `refresh_aliases(skills_dir, commands_dir, loaded_version) -> (refreshed, removed)` — Kernlogik aus `setup.py` |
| `setup.py` | MODIFY | `refresh_command_aliases` delegiert an `alias_sync.refresh_aliases` (Ausgabe bleibt) |
| `core/hooks/session_banner.py` | MODIFY | Scope `~` automatisch auffrischen; Projekt-Scope → Hinweis an Claude; Haupt-Ordner nachziehen (nur Haupt-Ordner-cwd); Ausgabe aufgeteilt in `systemMessage` (Klartext, keine Befehle) + `additionalContext` (Claude) |
| `hooks/hooks.json` | MODIFY | Banner-Timeout 5 → 10 s |
| `tests/test_session_banner.py` | MODIFY | Befehlstext-Assertions → Auffrisch-Wirkung, keine `python3` im sichtbaren Text |
| `tests/test_banner_behind_origin_185.py` | MODIFY | Nachgezogen (sauber), Abbruch (lokale Änderungen) → nur Claude-Kontext, Worktree → still |
| `CHANGELOG.md` | MODIFY | [Unreleased] |

### Scope Assessment
- Files: 7 (davon 2 Tests, 1 Changelog)
- Estimated LoC: Produktivcode ca. +160/−60, Tests ca. +100/−20
- Risk Level: MEDIUM — der Start-Hinweis schreibt erstmals (Kurzbefehle in `~`, Merge im Haupt-Ordner); läuft in jeder Sitzung jedes Projekts.
- Limit: Dateizahl über 4–5, Produktivcode unter 250 LoC. Ein Workflow (gleiches Ziel, vgl. Memory „Bündel über Limit: ein Ticket“).

### Technical Approach
1. `alias_sync.refresh_aliases` extrahieren, `setup.py` darauf umstellen (eine Quelle, keine Drift).
2. Banner: Scope `~` mit Skills der GELADENEN Fassung auffrischen (`find_stale_aliases(loaded_version=…)` verhindert Herabstufen, #163); entfernte Aliase löschen; alles in try/except. Nutzer sieht „Kurzbefehle aktualisiert (N)“.
3. Projekt-Scope veraltet → nur `additionalContext`: „Kurzbefehle im Projekt veraltet: … — im Worktree mit `setup.py <projekt> --refresh-aliases` auffrischen und mitcommitten.“
4. Haupt-Ordner: nur wenn Hook-cwd == Haupt-Ordner (erste Zeile `worktree list`). Nach dem bestehenden Fetch prüfen: Upstream vorhanden, kein laufender Merge/Rebase, `status --porcelain --untracked-files=no` leer, HEAD Vorfahre von `@{u}`. Dann `merge --ff-only --quiet` mit eigenem Budget, Abbruch per SIGTERM, nie SIGKILL. Erfolg → „Projektstand aktualisiert (N Änderungen)“; Abbruch → nur `additionalContext` mit Grund und Auftrag, dem PO in Klartext zu sagen, was los ist.
5. Worktree-cwd → kein Fetch, keine Meldung. `source == compact` → nur Versionszeile.
6. Ausgabe: `{"systemMessage": …, "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": …}}`. Sichtbarer Text ohne Shell-Befehl und ohne Git-Vokabular.
7. Hook-Timeout 10 s; Gesamtbudget im Skript entsprechend (Fetch bleibt 3 s).

### Alternative (nicht gewählt)
Hook merged nicht selbst, gibt nur `additionalContext` aus; Claude ruft `sync-main` über die vorhandene Guard-Ausnahme auf. Vorteil: kein längerer Timeout, kein Merge im Hook. Nachteil: hängt davon ab, dass Claude den Hinweis befolgt — genau das Liegenbleiben, das #399 abstellen will. Zweite Alternative: nur Formulierung ändern (im Issue bereits als schwächer verworfen).

### Dependencies
`alias_sync` (Hook + setup.py), `config_loader` (`session_banner.behind_check` bleibt Kill-Switch), `hook_utils.framework_disabled`, git. CLI `sync-main` und `--refresh-aliases` bleiben unverändert bestehen.

### Open Questions
- keine PO-Fragen offen; Timeout 10 s und Projekt-Scope-Verzicht sind technische Entscheidungen (s. o.)
