# Kontext: fix-280-worktree-config-isolation

> Rekonstruiert am 2026-09-30 — die ursprüngliche Kontext-Datei dieses Workflows ist mit einem
> zwischenzeitlich entfernten Sitzungs-Worktree verlorengegangen (nie committet). Ironischerweise
> ist das derselbe Fehlerklasse-Nachbar, den dieser Vorgang selbst behebt (Zustand landet in einem
> Worktree statt im geteilten Ordner). Die Rekonstruktion stützt sich auf Issue #280 selbst (inkl.
> Scope-Kommentar) und auf erneutes Lesen des betroffenen Codes.

## Ursprüngliche Anfrage

Issue #280 (Sammel-Vorgang, fasst #241 und #265 zusammen): Hooks lösen ihre Umgebung zur Laufzeit
auf den echten Haupt-Ordner auf, auch wenn sie in einer Worktree-Sitzung laufen sollen. Zwei
Befunde:

- **Befund 1 (#241):** `config_loader.load_config()` liefert im Worktree die `config.yaml` des
  Haupt-Ordners statt der des eigenen Zweigs.
- **Befund 2 (#265):** Jeder vollständige Testlauf hängt reale Zeilen an das echte
  `.claude/gate-events.jsonl` des Repositories an — Test-Rauschen wird echten Sitzungen
  zugeschrieben, weil `log_gate_event()` mit `find_project_root()` immer den Haupt-Ordner trifft.

## Scope-Entscheidung (bereits getroffen, siehe Issue-Kommentar)

Dieser Vorgang (#280) ist auf **Befund 2 verengt**. Befund 1 bekommt einen eigenen, engeren
Vorgang (#292), weil ein pauschaler Fix dort die bewusste Design-Entscheidung aus #153 aushebeln
würde (Grenzwerte bleiben Haupt-Ordner-autoritativ). Diese Trennung ist bereits im Issue vermerkt
und nicht mehr offen.

## Root Cause (verifiziert durch erneutes Lesen von core/hooks/hook_utils.py, 2026-09-30)

`log_gate_event()` (`core/hooks/hook_utils.py:529-552`) löst die Log-Datei über
`root = find_project_root()` (Zeile 537) auf. `find_project_root()` ist *bewusst*
Worktree-transparent — sie löst jede Worktree-Sitzung auf den Haupt-Ordner auf, weil das für
geteilten Zustand (Workflow-JSONs) richtig ist. Für eine reine Beobachtungs-Funktion wie das
Gate-Event-Log ist das falsch: sie soll dorthin schreiben, wo die Sitzung tatsächlich arbeitet.

Es gibt bereits eine Gegenfunktion für genau diesen Zweck: `find_worktree_root()`
(`hook_utils.py:887-902`), eingeführt für Issue #96 (dasselbe Wurzel-Problem, andere Richtung:
LoC-Messung). Das etablierte Muster `root = find_worktree_root() or find_project_root()` wird
bereits an einer Stelle verwendet (`hook_utils.py:1149`, in der LoC-Messung selbst).

**Betroffene Testdateien (rufen den Guard in-process auf, nicht per Subprozess):**

- `tests/test_sync_main_169.py` — `_guard()` (Zeile 30) ruft `ssg._do_guard(payload)` direkt im
  pytest-Prozess auf. `Path.cwd()` ist dabei die reale Sitzung, in der `pytest` läuft — nicht
  `tmp_path`. Jede Blockade in diesen Tests schreibt daher ins echte Log.
- `tests/test_session_singleton_guard.py` — gleiches Muster.

`session_singleton_guard.py:668-669` importiert `log_gate_event` lokal
(`from hook_utils import log_gate_event`) und ruft es bei jeder Blockade auf. Das ist die einzige
Stelle in dieser Datei.

**Etabliertes Isolations-Muster** (`tests/test_gate_event_log_181.py`): Hook läuft dort als
Subprozess mit `env["CLAUDE_PROJECT_DIR"] = str(tmp_path)` — greift nicht 1:1 für die beiden
betroffenen Dateien, weil die dort in-process aufrufen. Isolation dort sinnvoll über
Monkeypatching der Root-Auflösung (`hook_utils.find_project_root` / `find_worktree_root`) auf
`tmp_path`, nicht über Subprozess-Umbau (der wäre ein deutlich größerer, ungeplanter Eingriff in
beide Testdateien).

## Vorschlag (aus Issue-Kommentar übernommen, technisch verifiziert)

1. `log_gate_event()` auf `root = find_worktree_root() or find_project_root()` umstellen.
2. Die beiden betroffenen Testdateien isolieren: Root-Auflösung in einer (ggf. erweiterten)
   `_isolate`-Fixture auf `tmp_path` monkeypatchen, damit keine Blockade in diesen Dateien mehr
   das echte `.claude/gate-events.jsonl` erreicht — unabhängig davon, aus welchem Ordner `pytest`
   gestartet wird.

## Definition of Done (aus Issue #280)

- [ ] Die vollständige Testsuite hängt **0 Zeilen** an das echte `.claude/gate-events.jsonl` an
- [ ] Eine echte Blockade landet weiterhin im Log (Gegenprobe — Regressionstest analog zu #96:
      Worktree anlegen, dort eine Blockade auslösen, prüfen dass sie im Worktree-Log landet und
      NICHT im Log des Haupt-Ordners)
- [ ] Stellen, die absichtlich den Haupt-Ordner brauchen (Zustandsablage), bleiben unverändert

## Betroffene Dateien

- `core/hooks/hook_utils.py` (log_gate_event, 1 Zeile)
- `tests/test_sync_main_169.py` (Isolations-Fixture)
- `tests/test_session_singleton_guard.py` (Isolations-Fixture)
- Neuer Regressionstest für die Worktree/Haupt-Ordner-Trennung des Gate-Event-Logs

## Risiko

Gering. `find_worktree_root()` existiert bereits und ist an anderer Stelle produktiv im Einsatz
(#96-Fix). Die Änderung an `log_gate_event()` betrifft nur den Schreibort einer
Beobachtungs-Funktion, die laut ihrem eigenen Kommentar "nie eine Ausnahme durchlassen" darf und
"nichts entscheidet" — kein Verhaltensrisiko für Gates selbst.
