---
entity_id: fix-566-plugin-update-sync
type: bugfix
created: 2026-11-10
updated: 2026-11-10
status: draft
version: "1.0"
workflow: fix-566-plugin-update-sync
issue: 566
tags: [setup, update, plugin-mode, shims, aliases, consumers]
---

# `--update` im Plugin-Modus spiegelt keine Hooks und Befehle mehr (Issue #566, Folge zu #562)

## Approval

- [ ] Approved

## Purpose

In Projekten im Plugin-Modus liefert das Plugin Hooks und Befehle selbst aus; das Projekt braucht nur zwei kleine Weiterleitungen (Shims) und markierte Kurzbefehle. `setup.py <projekt> --update` spiegelt aber ohne Cloud-Pin noch immer alle Framework-Hooks und -Befehle in `.claude/hooks` und `.claude/commands`: Shims und Kurzbefehle werden zu Vollkopien, echte lokale Kopien überschrieben, fehlende Dateien angelegt. Diese Änderung schaltet das Spiegeln im gesamten Plugin-Modus ab und erneuert dort nur noch veraltete Shims und markierte Kurzbefehle; projekteigene Dateien bleiben unberührt.

## Source

- **File:** `setup.py`
- **Identifier:** `update_project`, `refresh_pinned_rollout` (wird zu `refresh_plugin_rollout`), `apply_cloud_gates`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `migrate_to_plugin.refresh_shims` (#562) | function | erneuert nur vorhandene, markierte, veraltete Shims; legt nie etwas an |
| `alias_sync.refresh_aliases`, `alias_sync.alias_content` (#251/#399) | function | erneuert nur markierte, veraltete Kurzbefehle; einzige Quelle des Soll-Inhalts |
| `migrate_to_plugin._render_shim` | function | Soll-Inhalt der Shims, Vergleichsmaßstab in den Tests |
| `setup.refresh_cloud_gates` | function | Pin-Abruf und `.claude/cloud_bootstrap.py`; bleibt an den Pin gebunden |
| `.claude/framework_version.json` | config | trägt `plugin_mode`, `cloud_ref`, `cloud_sha` |
| `tests/test_cache_finder_562.py` (`fw_copy`, `_consumer`, `_setup`, `_snapshot`) | test helper | Bausteine für Plugin-Projekte mit und ohne Pin |
| `docs/specs/feat-562-cloud-cache-finder.md` | spec | benennt #566 als Folge; AC-15 daraus wird hier bewusst abgelöst |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| setup.py | MODIFY | `update_project`: neues Bool `plugin = bool(existing.get("plugin_mode"))`; `sync_dir` für `core/hooks` und `core/commands` nur bei `not plugin` (heute `not pinned`); im Plugin-Zweig immer `refresh_plugin_rollout`, `refresh_cloud_gates` nur mit Pin; `refresh_pinned_rollout` wird zu `refresh_plugin_rollout` (Name, Docstring, beide Aufrufer `apply_cloud_gates` und `update_project`); Ausgabepräfix ohne Pin `plugin refresh:`, mit Pin wie bisher `cloud refresh:` |
| tests/test_plugin_update_sync_566.py | CREATE | alle ACs von #566 |
| tests/test_cache_finder_562.py | MODIFY | `test_update_without_pin_is_unchanged` (AC-15 aus #562) wird neu gefasst |
| CHANGELOG.md | MODIFY | `[Unreleased]` → Fixed mit `#566` |

### Estimated Changes

- Files: 1 neu (Test), 1 produktiv geändert, 1 Test angepasst, CHANGELOG
- LoC: +~20/-~15 Produktion, +~110 Test
- Risk Level: MEDIUM (Update-Pfad aller Konsumenten-Projekte; Copy-Modus und gepinnter Zweig müssen unverändert bleiben)

## Implementation Details

**Ursache.** `update_project` klammert seit #562 nur den gepinnten Plugin-Zweig (`plugin_mode` und `cloud_ref`/`cloud_sha`) vom Spiegeln aus. Ohne Pin laufen `sync_dir` für `core/hooks` und `core/commands` weiter in vorhandene Ordner `.claude/hooks` und `.claude/commands`.

**Änderung in `update_project`.** `existing` (`framework_version.json`) wird bereits vor den Sync-Läufen gelesen. Neben `pinned` kommt `plugin = bool(existing.get("plugin_mode"))`. Die beiden `sync_dir`-Läufe für Hooks und Befehle laufen nur bei `not plugin`. Im Plugin-Zweig wird `refresh_plugin_rollout(project_path)` immer aufgerufen, mit und ohne Pin: Shims über `refresh_shims`, markierte Kurzbefehle über `refresh_aliases`. Beide legen nie etwas an, ersetzen nur markierte, veraltete Fassungen; Symlinks und nicht beschreibbare Dateien werden mit `Skipped:` gemeldet. Nur bei gesetztem Pin folgt zusätzlich `refresh_cloud_gates` wie bisher. Ohne Pin entsteht deshalb weder ein Pin noch `.claude/cloud_bootstrap.py`, und `plugin_mode` bleibt erhalten.

**Umbenennung.** `refresh_pinned_rollout` heißt künftig `refresh_plugin_rollout`, weil die Funktion nicht mehr an den Pin gebunden ist. Aufrufer: `apply_cloud_gates` (`--cloud-gates`) und `update_project`. Die Ausgabe trägt ohne Pin das Präfix `plugin refresh:`, damit die Meldung nicht „cloud“ behauptet; mit Pin bleibt `cloud refresh:` unverändert.

**Unverändert.** Copy-Modus (`plugin_mode` fehlt oder ist false): `sync_dir` mit Manifest, `.new`-Dateien und Backups wie bisher (#72). Gepinnter Plugin-Zweig: Verhalten aus #562 (AC-13, AC-14).

**Bewusst nicht im Scope.**

- `.claude/agents`: `.claude-plugin/plugin.json` liefert keine Agenten aus, Projekte brauchen die Kopien; das Spiegeln bleibt.
- `core/tools` nach `.claude/tools` und Modul-Dateien über `install_module` (Hooks, Standards, Tools, Workflows): projektseitig genutzte Inhalte, kein gemeldeter Schaden; ein eigener Befund wäre nötig.
- Löschen vorhandener Alt-Vollkopien in Plugin-Projekten: Datenverlust-Risiko, das Issue verlangt nur „nicht mehr spiegeln“. Vorhandene Vollkopien bleiben liegen und werden nicht mehr aktualisiert.

**Bewusste Ablösung von AC-15 aus #562.** AC-15 (`test_update_without_pin_is_unchanged`) hielt fest, dass ohne Pin das heutige Verhalten gilt, also Spiegeln inklusive Vollkopien. Der Test bestand nur, weil `sync_dir` Shims und Kurzbefehle zu Vollkopien machte, deren Inhalt vom Soll abwich. Das ist mit #566 unvereinbar (#562 hat #566 dafür ausdrücklich vorgesehen). Der Test wird nicht gelöscht, sondern neu gefasst: Ohne Pin werden vorhandene veraltete Shims und markierte Kurzbefehle jetzt erneuert, es wird nichts angelegt, es entsteht kein Pin.

**Tests.** Echte Dateien in `tmp_path`, Aufruf von `setup.py` per `subprocess`; Bausteine `fw_copy`, `_consumer`, `_setup`, `_snapshot` aus `tests/test_cache_finder_562.py` werden importiert oder wiederverwendet. Kein Mock von Shell oder git.

## Expected Behavior

- **Input:** `setup.py <projekt> --update` in einem Plugin-Modus-Projekt ohne Pin, mit vorhandenen Ordnern `.claude/hooks` und `.claude/commands`, die veraltete Shims, markierte Kurzbefehle, echte Kopien und eigene Dateien enthalten können; außerdem dasselbe in einem Copy-Modus-Projekt und in einem Projekt mit Pin.
- **Output:** Im Plugin-Modus entsteht keine neue Datei in `.claude/hooks` und `.claude/commands`; veraltete Shims und markierte Kurzbefehle sind auf den Soll-Inhalt erneuert und mit Pfad in der Ausgabe (`plugin refresh:`) gelistet; echte Kopien und eigene Dateien sind byte-gleich. Im Copy-Modus und mit Pin verhält sich `--update` wie bisher.
- **Side effects:** Erneuerte Dateien stehen im Projekt und müssen committet werden. Keine Backups unter `.claude/update-backups/` für Hooks und Befehle im Plugin-Modus, kein Pin, kein `cloud_bootstrap.py` ohne Pin.

## Known Limitations

- Vorhandene Alt-Vollkopien von Hooks und Befehlen in Plugin-Projekten werden nicht gelöscht und nicht mehr aktualisiert; sie veralten still, werden vom Plugin-Modus aber nicht benutzt (Registrierung über `${CLAUDE_PLUGIN_ROOT}`), außer `hook_utils.py` und `config_loader.py` als Import-Ziel projekteigener Hooks.
- `.claude/agents`, `core/tools` nach `.claude/tools` und Modul-Dateien werden im Plugin-Modus weiterhin gespiegelt (siehe Implementation Details, Begründung dort).
- Shims und markierte Kurzbefehle werden nie neu angelegt, nur erneuert; fehlende bleiben fehlend (Schutz vor Überschatten, #87/#163/#400).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test in `tests/test_plugin_update_sync_566.py` bzw. dem neu gefassten Test in `tests/test_cache_finder_562.py` belegt
- [ ] `setup.py <projekt> --update` in einem Plugin-Projekt ohne Pin legt keine Framework-Hooks und -Befehle mehr im Projekt ab, erneuert aber veraltete Shims und markierte Kurzbefehle und lässt eigene Dateien und echte Kopien unverändert (AC-1 bis AC-3)
- [ ] Ohne Pin entstehen weder ein Pin noch `.claude/cloud_bootstrap.py`; ein zweiter Lauf ändert kein Byte (AC-4, AC-5)
- [ ] Copy-Modus-Projekte und gepinnte Plugin-Projekte werden wie bisher aktualisiert (AC-6, AC-7)
- [ ] CHANGELOG `[Unreleased]` → Fixed nennt `#566`
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/` grün, insbesondere #72, #159, #522, #562)

## Acceptance Criteria

Testaufbau: echte Dateien in `tmp_path`, `subprocess.run` für `setup.py`, Bausteine aus `tests/test_cache_finder_562.py`.

- **AC-1:** Given ein Plugin-Modus-Projekt ohne Pin mit vorhandenen Ordnern `.claude/hooks` und `.claude/commands` / When `setup.py <projekt> --update` läuft / Then entsteht in beiden Ordnern keine neue Datei (Dateinamen-Menge vorher gleich nachher, `__pycache__` ignoriert)
  - Test: tests/test_plugin_update_sync_566.py::test_update_without_pin_creates_no_new_files

- **AC-2:** Given ein Plugin-Modus-Projekt ohne Pin mit veralteten Shims (Marker, alter Inhalt) und markierten veralteten Kurzbefehlen / When `--update` läuft / Then sind die Shims gleich `_render_shim` und die Kurzbefehle gleich `alias_content()`, und ihre Pfade stehen in der Ausgabe
  - Test: tests/test_plugin_update_sync_566.py::test_update_without_pin_refreshes_stale_shims_and_aliases

- **AC-3:** Given ein Plugin-Modus-Projekt ohne Pin mit echten Kopien von `hook_utils.py`/`config_loader.py` (erste Zeile ohne Marker) sowie eigenen Hooks und Befehlen / When `--update` läuft / Then sind diese Dateien byte-gleich, die Ausgabe enthält keine „UEBERSCHRIEBEN“-Meldung und es entsteht kein Ordner `.claude/update-backups/`
  - Test: tests/test_plugin_update_sync_566.py::test_update_without_pin_leaves_real_copies_and_own_files_untouched

- **AC-4:** Given ein Plugin-Modus-Projekt ohne Pin / When `--update` läuft / Then entsteht kein Pin (`cloud_ref` und `cloud_sha` bleiben ungesetzt), keine Datei `.claude/cloud_bootstrap.py`, und `plugin_mode` bleibt true
  - Test: tests/test_plugin_update_sync_566.py::test_update_without_pin_creates_no_pin_and_keeps_plugin_mode

- **AC-5:** Given ein Plugin-Modus-Projekt ohne Pin nach einem ersten `--update` / When ein zweiter `--update` läuft / Then ändert sich kein Byte im Projekt (Schnappschuss vorher gleich nachher)
  - Test: tests/test_plugin_update_sync_566.py::test_update_without_pin_is_idempotent

- **AC-6:** Given ein Copy-Modus-Projekt (`plugin_mode` fehlt) mit vorhandenen Ordnern `.claude/hooks` und `.claude/commands` / When `--update` läuft / Then spiegelt `update_project` die Framework-Hooks und -Befehle wie bisher dorthin (Regression)
  - Test: tests/test_plugin_update_sync_566.py::test_copy_mode_update_still_syncs_hooks_and_commands

- **AC-7:** Given ein Plugin-Modus-Projekt mit Pin / When `--update` läuft / Then bleibt das Verhalten aus #562 unverändert (veraltete Shims und Kurzbefehle erneuert, echte Kopien byte-gleich, nichts neu angelegt, Pin erhalten, Präfix `cloud refresh:`); die bestehenden Tests zu AC-13 und AC-14 aus #562 bleiben grün
  - Test: tests/test_plugin_update_sync_566.py::test_update_with_pin_behaves_as_in_562

- **AC-8:** Given ein Plugin-Modus-Projekt ohne Pin mit veralteten Shims und Kurzbefehlen (bewusste Neufassung von AC-15 aus #562) / When `--update` läuft / Then werden diese erneuert, es wird nichts angelegt, es entsteht kein Pin, und die Ausgabe trägt das Präfix `plugin refresh:`
  - Test: tests/test_cache_finder_562.py::test_update_without_pin_is_unchanged

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- Test: GIVEN Plugin-Projekt ohne Pin mit vorhandenen Ordnern WHEN `--update` THEN Dateinamen-Menge in `.claude/hooks` und `.claude/commands` unverändert (AC-1)
- Test: GIVEN veraltete Shims und markierte Kurzbefehle ohne Pin WHEN `--update` THEN Soll-Inhalt und Pfade in der Ausgabe (AC-2)
- Test: GIVEN echte Kopien und eigene Dateien ohne Pin WHEN `--update` THEN byte-gleich, keine Überschreib-Meldung, keine Backups (AC-3)
- Test: GIVEN Plugin-Projekt ohne Pin WHEN `--update` THEN weder Pin noch `cloud_bootstrap.py`, `plugin_mode` true (AC-4)
- Test: GIVEN zweiter Lauf WHEN `--update` THEN kein Byte geändert (AC-5)
- Test: GIVEN Copy-Modus-Projekt WHEN `--update` THEN Hooks und Befehle werden gespiegelt (AC-6)
- Test: GIVEN Projekt mit Pin WHEN `--update` THEN Verhalten wie in #562 (AC-7)
- Test: GIVEN Plugin-Projekt ohne Pin mit veralteten Shims WHEN `--update` THEN erneuert, `plugin refresh:` (AC-8)

Ausführung:

- Neue Datei: `pytest tests/test_plugin_update_sync_566.py`
- Neu gefasster Test: `pytest tests/test_cache_finder_562.py`
- Betroffene bestehende Tests: `pytest tests/test_setup_update_preserves_plugin_mode_159.py tests/test_setup_update_keeps_local_72.py tests/test_cloud_gates_522.py`
- TDD RED: Die neue Testdatei und der neu gefasste Test müssen vor der Implementierung fehlschlagen (ohne Pin werden heute Vollkopien angelegt)
- Regressionslauf: `pytest tests/` (lokal im venv mit `pytest` und `pyyaml`)

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Das Repo führt keine ADR-Sammlung (`docs/adr/` existiert nicht), und #522 sowie #562 haben bewusst keine ADR eingetragen. Diese Änderung setzt die Entscheidung aus #562 („im Plugin-Modus erneuern Shims und Kurzbefehle allein `refresh_shims` und `refresh_aliases`“) konsequent auf den ungepinnten Plugin-Modus fort. Weder ein neues Gate noch eine neue Regel entsteht, nur der Geltungsbereich eines bestehenden Zweigs wird vom Pin auf den Plugin-Modus erweitert; deshalb keine eigene ADR.

## Changelog

- 2026-11-10: Initial spec created
