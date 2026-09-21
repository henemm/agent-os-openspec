# Fast Track: Plugin-Shim überlebt Geschwister-Importe (3.26.4)

## Problem

Folgefund zu #165, gemessen beim Nachziehen der drei Bestandsprojekte am 2026-09-21.

Nach `migrate_to_plugin.py --apply` starben in `/Users/hem/Developer/gregor-zwanzig` drei
projekteigene Hooks (`workflow_gate.py`, `spec_enforcement.py`, `workflow_state_updater.py`) mit

```
ModuleNotFoundError: No module named 'hook_utils'
```

Dieselben Hooks liefen **vor** der Migration mit Exit 0 (an der Sicherungskopie nachgewiesen). Der
Defekt wurde also durch die Migration eingeführt, nicht durch sie aufgedeckt.

Ursache: Der Shim aus #33 ersetzt die lokale `config_loader.py` und lädt die Fassung des Plugins
per `importlib.util.spec_from_file_location`. Die Plugin-Fassung beginnt in Zeile 20 mit
`from hook_utils import find_main_repo_from_worktree` — ein Geschwister-Modul im selben Ordner. Bei
diesem Ladeweg steht dieser Ordner nicht in `sys.path`; der Import scheitert, und der Hook stirbt
beim Start, bevor eine einzige Prüfung läuft.

Betroffen ist jedes Projekt, dessen eigene Hooks `config_loader` importieren — also genau die
Bestandsprojekte, für die der Shim gebaut wurde.

Erschwerend: `_find_shim_candidates()` hielt jede Datei mit dem Marker in Zeile 1 für aktuell. Der
Marker ist in alter wie neuer Fassung derselbe, eine fehlerhafte Shim-Fassung wäre also in jedem
bereits migrierten Projekt liegengeblieben — auch nach dem Fix.

## Scope

- `migrate_to_plugin.SHIM_TEMPLATE`: Hook-Ordner des Plugins vor `exec_module` in `sys.path`
- `migrate_to_plugin._find_shim_candidates`: Inhaltsvergleich statt reiner Marker-Prüfung
- Nicht enthalten: ein Versions-Stempel im Shim. Der Inhaltsvergleich leistet dasselbe ohne
  zusätzliches Feld, das auseinanderlaufen kann.
- Nicht enthalten: Entfernen des Shim-Konzepts zugunsten fester Plugin-Pfade — siehe ADR.

## Definition of Done

Ein projekteigener Hook, der `config_loader` importiert, startet nach der Migration fehlerfrei,
auch wenn das Plugin-Modul selbst ein Geschwister-Modul importiert. Ein Shim älterer Fassung wird
beim nächsten Lauf erneuert statt für aktuell gehalten.

## Acceptance Criteria

- **AC-1:** Given ein Plugin-Modul, das ein Geschwister-Modul importiert, When ein projekteigener
  Hook `from config_loader import X` ausführt, Then lädt der Shim das Modul ohne
  `ModuleNotFoundError`, und der Wert aus dem Geschwister-Modul ist erreichbar.
- **AC-2:** Given derselbe Aufbau, When der Hook stattdessen `import config_loader` verwendet,
  Then funktioniert auch dieser Importstil weiterhin.
- **AC-3:** Given ein Shim älterer Fassung mit korrektem Marker, When das Werkzeug läuft, Then
  steht er auf der Erneuerungsliste und nicht auf der „schon migriert"-Liste.
- **AC-4:** Given ein Shim der heutigen Fassung, When das Werkzeug läuft, Then bleibt er
  unangetastet (Idempotenz).
- **AC-5:** Given keine Plugin-Installation, When der Shim geladen wird, Then meldet er weiterhin
  klar `plugin not installed` statt eines Folgefehlers.

## Test Plan

- `tests/test_plugin_shim_sibling_import_165.py`: 5 Tests (AC-1 bis AC-5). Hermetisch — eine
  vollständige Fake-Plugin-Installation auf `tmp_path` (eigene Registry, eigenes `HOME`), der
  gerenderte Shim läuft im Subprozess.
- RED vor dem Fix: AC-1 und AC-2 rot, mit exakt der gemeldeten Fehlermeldung
  `ModuleNotFoundError: No module named 'hook_utils'`. AC-5 blieb grün — das Bestandsverhalten
  wird nicht eingetauscht.
- Betriebsnachweis an den drei echten Projekten: alle registrierten Hook-Kommandos werden aus einem
  Unterordner gestartet. Vorher 24 unauffindbar, nach der Migration 3 Abstürze, nach diesem Fix 0.

## ADR

**Entscheidung:** Der Shim bleibt, bekommt aber den Hook-Ordner des Plugins in `sys.path`.

**Verworfene Alternative — Shim abschaffen, projekteigene Hooks auf feste Plugin-Pfade umschreiben:**
Das hieße, in fremden Projekten Importzeilen umzuschreiben, deren Inhalt das Framework nicht kennt.
Der Shim ist genau dafür da, diese Dateien nicht anzufassen. Die Kosten der Alternative (Eingriff in
projekteigenen Code) stehen in keinem Verhältnis zum Nutzen (eine Zeile `sys.path` gespart).

**Verworfene Alternative — Marker mit Versionsnummer statt Inhaltsvergleich:** ein zweites Feld,
das gepflegt werden muss und beim Vergessen genau den Fehler wieder ermöglicht, den es verhindern
soll. Der Inhaltsvergleich kann nicht vergessen werden.
