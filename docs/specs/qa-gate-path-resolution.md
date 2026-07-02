---
entity_id: qa_gate_path_resolution
type: bugfix
created: 2026-07-02
updated: 2026-07-02
status: draft
version: "1.0"
tags: [bugfix, hooks, qa-gate, adversary-verdict, consumer-projects]
test_targets:
  - core/hooks/qa_gate.py
  - tests/test_qa_gate.py
---

# QA Gate Path Resolution

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** https://github.com/henemm/agent-os-openspec/issues/29

## Purpose

Behebt einen Bug in `core/hooks/qa_gate.py`, durch den `adversary_verdict` in
Consumer-Projekten (nach Installation via `setup.py`) niemals persistiert wird,
obwohl `qa_gate.py` fälschlich Erfolg meldet ("Commit is now allowed."). Der
Fix stellt sicher, dass `qa_gate.py` sein Geschwister-Skript `workflow.py`
robust relativ zum eigenen Dateipfad findet — unabhängig von
`CLAUDE_PLUGIN_ROOT`-Zustand oder Verzeichnis-Verschachtelung — und dass ein
fehlschlagender Subprocess-Aufruf laut fehlschlägt statt still verschluckt zu
werden.

## Dependencies

| Komponente | Typ | Abhängigkeit |
|-----------|-----|-------------|
| `core/hooks/workflow.py` | Geschwister-Skript | Wird von `qa_gate.py` per Subprocess aufgerufen, um `adversary_verdict` zu setzen (`set-field`) und den Workflow-Namen zu lesen (`status`) |
| `core/hooks/hook_utils.py` | Utility-Modul | Aktuell fälschlich für Geschwister-Skript-Auflösung genutzt (`find_plugin_root()`); nach dem Fix nur noch `setup_path()` benötigt |
| `core/hooks/bash_gate.py` | Downstream-Consumer | Prüft bei `git commit`, ob ein `VERIFIED`-Verdict im Workflow-State vorliegt — blockiert Commits dauerhaft, wenn `adversary_verdict` nie geschrieben wird |
| `setup.py` | Installations-Tool | Kopiert Hook-Dateien flach nach `.claude/hooks/` in Consumer-Projekten — genau dieses Layout muss `qa_gate.py` korrekt handhaben |

## Source

- **File:** `core/hooks/qa_gate.py`
- **Identifier:** `_set_verdict()`, `main()`

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/qa_gate.py` | MODIFY | 3× `workflow_py`-Pfadauflösung von `_plugin_root / "core" / "hooks" / "workflow.py"` auf `Path(__file__).parent / "workflow.py"` umstellen (Zeilen 47, 112, 138); Return-Code-Check in `_set_verdict()` und in der Status-Abfrage in `main()` ergänzen; toten Import (`find_project_root`, `find_plugin_root`) und ungenutzte Variablen (`_root`, `_plugin_root`) entfernen |
| `tests/test_qa_gate.py` | CREATE | Neuer Regressionstest: simuliert flaches Consumer-Layout via `tmp_path`, verifiziert Verdict-Persistierung (Erfolgsfall) und lautes Fehlschlagen (Fehlerfall) |

### Estimated Changes

- Files: 2
- LoC: ~+15/-8 (Fix in `qa_gate.py`) + ~+70 (neuer Test)

## Root Cause

`qa_gate.py` löst den Pfad zu seinem Geschwister-Skript `workflow.py` über
`find_plugin_root()` aus `hook_utils.py` auf statt relativ zum eigenen
Skriptpfad. `find_plugin_root()` geht bei fehlendem `CLAUDE_PLUGIN_ROOT` von
`Path(__file__).parent.parent.parent` **relativ zu `hook_utils.py`** aus und
setzt eine `core/hooks/`-Verschachtelung voraus. `setup.py` kopiert Hook-
Dateien aber **flach** nach `.claude/hooks/` in Consumer-Projekten — dort
zeigt `_plugin_root / "core" / "hooks" / "workflow.py"` ins Leere.

Der Bug tritt im Framework-Repo selbst NICHT auf, weil dort zufällig
`core/hooks/`-Nesting existiert (`hook_utils.py` liegt unter
`core/hooks/hook_utils.py`, `Path(__file__).parent.parent.parent` landet
zufällig beim Repo-Root, unter dem wiederum `core/hooks/workflow.py`
existiert). Er manifestiert sich ausschließlich in Consumer-Projekten nach
Installation.

**Symptom:** `qa_gate.py <test-output>` meldet Erfolg ("VERIFIED:...",
"Commit is now allowed."), aber `adversary_verdict` bleibt im Workflow-State
`null`, weil der `subprocess.run(...)`-Aufruf zu `workflow.py set-field` still
fehlschlägt (falscher Pfad → `FileNotFoundError` bzw. Non-Zero-Exit) und
`_set_verdict()` den Return-Code nicht prüft (`capture_output=True` ohne
Check). Downstream blockiert `bash_gate.py` Commits dauerhaft, weil nie ein
`VERIFIED`-Verdict im State landet (Fail-Closed, kein Security-Bypass, aber
ein blockierender Produktivitätsbug).

## Implementierungsdetails

### 1. Import bereinigen (Zeile 22, 33-34)

```python
# Vorher:
from hook_utils import setup_path, find_project_root, find_plugin_root
setup_path()
...
_root = find_project_root()
_plugin_root = find_plugin_root()

# Nachher:
from hook_utils import setup_path
setup_path()
# (keine _root/_plugin_root-Variablen mehr nötig — Path(__file__).parent
#  wird an jeder Verwendungsstelle direkt berechnet)
```

Toter Import (`find_project_root`, `find_plugin_root`) und ungenutzte
Modul-Variablen (`_root`, `_plugin_root`) werden vollständig entfernt — sie
werden nach dem Fix nirgends mehr in `qa_gate.py` benötigt.

### 2. Pfadauflösung an allen 3 Stellen (Zeilen 47, 112, 138)

```python
# Vorher (an jeder der 3 Stellen):
workflow_py = _plugin_root / "core" / "hooks" / "workflow.py"

# Nachher (an jeder der 3 Stellen):
workflow_py = Path(__file__).parent / "workflow.py"
```

Betroffen:
- `_set_verdict()` (Zeile 47) — setzt `adversary_verdict`
- `main()`, `--check`-Branch (Zeile 112) — zeigt Workflow-Status
- `main()`, Workflow-Namen-Ermittlung (Zeile 138) — liest `Workflow:`-Zeile aus `status`-Output

`Path(__file__).parent` ist robust, weil `workflow.py` in jeder bekannten
Installationsart (Framework-Repo `core/hooks/`, Consumer-Projekt
`.claude/hooks/`) garantiert als Geschwisterdatei im selben Verzeichnis wie
`qa_gate.py` liegt — unabhängig von `CLAUDE_PLUGIN_ROOT`-Zustand.

### 3. Return-Code-Check in `_set_verdict()` (nach Zeile 48-51)

```python
def _set_verdict(verdict: str) -> None:
    """Set adversary_verdict on active workflow via workflow.py CLI."""
    workflow_py = Path(__file__).parent / "workflow.py"
    result = subprocess.run(
        [sys.executable, str(workflow_py), "set-field", "adversary_verdict", verdict],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(
            f"ERROR: Failed to persist adversary_verdict via workflow.py: "
            f"{result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)
```

Ein fehlschlagender Subprocess-Aufruf darf nicht mehr still verschluckt
werden — `qa_gate.py` muss in diesem Fall mit Non-Zero-Exit abbrechen, statt
anschließend fälschlich "Commit is now allowed." auszugeben.

### 4. Return-Code-Check bei der Status-Abfrage in `main()` (Zeile 138-146)

```python
# Vorher:
workflow_py = _plugin_root / "core" / "hooks" / "workflow.py"
result = subprocess.run(
    [sys.executable, str(workflow_py), "status"],
    capture_output=True, text=True
)
wf_name = "unknown"
for line in result.stdout.splitlines():
    if line.startswith("Workflow:"):
        wf_name = line.split(":", 1)[1].strip()

# Nachher:
workflow_py = Path(__file__).parent / "workflow.py"
result = subprocess.run(
    [sys.executable, str(workflow_py), "status"],
    capture_output=True, text=True
)
if result.returncode != 0:
    print(
        f"ERROR: Could not read workflow status via workflow.py: "
        f"{result.stderr.strip()}",
        file=sys.stderr,
    )
    wf_name = "unknown-error"
else:
    wf_name = "unknown"
    for line in result.stdout.splitlines():
        if line.startswith("Workflow:"):
            wf_name = line.split(":", 1)[1].strip()
```

Diese Stelle wird bewusst NICHT mit `sys.exit(1)` versehen — sie dient nur der
Anzeige des Workflow-Namens im Log-Output, nicht dem Setzen des Verdicts. Ein
Fehlschlag hier soll sichtbar sein (`wf_name = "unknown-error"` +
stderr-Meldung), aber den weiteren Ablauf (Testvalidierung, Verdict-Setzen via
`_set_verdict()`, wo der eigentliche harte Check greift) nicht blockieren.

## Expected Behavior

- **Input:** `qa_gate.py <test-output-file>` in einem Consumer-Projekt, in
  dem `qa_gate.py` und `workflow.py` flach unter `.claude/hooks/` liegen
- **Output bei Erfolg:** Tests valide → `_set_verdict()` ruft `workflow.py
  set-field adversary_verdict VERIFIED:...` mit korrektem Pfad auf →
  Subprocess-Exit-Code 0 → State-JSON enthält
  `"adversary_verdict": "VERIFIED:..."` → `qa_gate.py` beendet mit Exit 0 und
  Meldung "Commit is now allowed."
- **Output bei Subprocess-Fehler:** `workflow.py` nicht auffindbar oder
  schlägt fehl → `_set_verdict()` gibt Fehlermeldung auf stderr aus und
  beendet `qa_gate.py` mit Exit 1 — KEINE fälschliche
  "Commit is now allowed."-Meldung mehr
- **Side effects:** `.claude/workflows/<name>.json` wird bei Erfolg um das
  Feld `adversary_verdict` ergänzt; bei Fehler bleibt der State unverändert
  und der Fehler ist über den Prozess-Exit-Code und stderr sichtbar

## Error Handling

- `workflow.py` existiert nicht am erwarteten Pfad (`Path(__file__).parent /
  "workflow.py"`) → `subprocess.run` liefert Non-Zero-Returncode oder wirft
  → `_set_verdict()` prüft `result.returncode != 0` und beendet mit
  `sys.exit(1)` + stderr-Meldung
- `workflow.py set-field` schlägt intern fehl (z.B. kein aktiver Workflow,
  ungültiger State) → gleiche Behandlung wie oben, Fehlertext aus
  `result.stderr` wird durchgereicht
- `workflow.py status` (Zeile 138, Namensermittlung) schlägt fehl → wird
  separat behandelt (`wf_name = "unknown-error"` + stderr-Warnung), blockiert
  aber NICHT den Gesamtablauf, da dies nur eine Anzeige-Hilfsfunktion ist
- Regressionsfall (kein Doppel-Exit): Wenn sowohl die Status-Abfrage als auch
  `_set_verdict()` fehlschlagen, terminiert der Prozess beim ersten harten
  Fehlschlag in `_set_verdict()` mit `sys.exit(1)` — es gibt keinen Fall, in
  dem trotz gescheitertem `_set_verdict()`-Aufruf noch "Commit is now
  allowed." ausgegeben wird

## Known Limitations

- Der Fix behandelt ausschließlich die Pfadauflösung und das
  Fehler-Silencing in `qa_gate.py`. Andere Hooks, die `find_plugin_root()`
  zur Root-Erkennung nutzen (nicht zur Geschwister-Skript-Auflösung), sind
  nicht betroffen und werden hier nicht angefasst.
- Historische Workflows, die vor diesem Fix fälschlich mit `adversary_verdict:
  null` "durchgerutscht" sind, werden durch diesen Fix nicht rückwirkend
  korrigiert — das ist Gegenstand des separat erwähnten Historien-Audits
  (siehe Memory `project_issue960_adversary_gate_bypass`), nicht dieses
  Bugfixes.

## Acceptance Criteria

- **AC-1:** Given `qa_gate.py` und `workflow.py` liegen flach im selben
  Verzeichnis eines simulierten Consumer-Projekts (kein `core/hooks/`-Nesting)
  / When `qa_gate.py` mit einer validen PASSED-Test-Output-Datei aufgerufen
  wird / Then `qa_gate.py` beendet mit Exit-Code 0 UND die Workflow-State-JSON
  enthält danach `"adversary_verdict"` beginnend mit `"VERIFIED:"`
- **AC-2:** Given `workflow.py` fehlt im Verzeichnis von `qa_gate.py` (Fake
  Consumer-Layout ohne Geschwister-Skript) / When `qa_gate.py` mit einer
  validen PASSED-Test-Output-Datei aufgerufen wird / Then `qa_gate.py` beendet
  mit Exit-Code ungleich 0 UND gibt eine Fehlermeldung auf stderr aus, statt
  "Commit is now allowed." zu melden
- **AC-3:** Given eine valide Test-Output-Datei und ein korrekt auffindbares
  `workflow.py` / When `_set_verdict()` intern den Subprocess-Aufruf zu
  `workflow.py set-field` durchführt / Then wird `Path(__file__).parent /
  "workflow.py"` als Pfad verwendet, nicht `find_plugin_root()`-basierte
  Pfade, unabhängig davon ob `CLAUDE_PLUGIN_ROOT` gesetzt ist
- **AC-4:** Given der Subprocess-Aufruf in `_set_verdict()` liefert einen
  Non-Zero-Returncode zurück (z.B. weil `workflow.py` intern fehlschlägt) /
  When `_set_verdict()` das Ergebnis auswertet / Then wird der Fehler laut
  auf stderr gemeldet und der Prozess beendet sich mit `sys.exit(1)`, statt
  den Fehler stillschweigend zu ignorieren
- **AC-5:** Given der aktuelle Code-Zustand nach dem Fix / When `qa_gate.py`
  statisch inspiziert wird / Then existieren keine Referenzen mehr auf
  `find_plugin_root`, `find_project_root`, `_root` oder `_plugin_root` in der
  Datei

## Test Plan

### Automated Tests (TDD RED)

- [ ] Test 1 (deckt AC-1 ab): GIVEN ein `tmp_path`-Fake-Projekt mit
      `.claude/workflows/<name>.json` (aktiver Workflow,
      `adversary_verdict: null`) und `qa_gate.py`/`workflow.py`/
      `hook_utils.py`/`config_loader.py`/`override_token.py` flach nach
      `tmp_path/fake_hooks/` kopiert (kein `core/hooks/`-Nesting) WHEN
      `qa_gate.py <passed-output>` per echtem `subprocess.run` mit
      `CLAUDE_PROJECT_DIR=tmp_path` und `OPENSPEC_ACTIVE_WORKFLOW=<name>`
      aufgerufen wird THEN `returncode == 0` und die State-JSON enthält
      `adversary_verdict` beginnend mit `"VERIFIED:"`
- [ ] Test 2 (deckt AC-2 ab): GIVEN dasselbe Fake-Projekt-Setup, aber
      `workflow.py` wird NICHT nach `fake_hooks/` kopiert WHEN `qa_gate.py
      <passed-output>` aufgerufen wird THEN `returncode != 0` und stderr
      enthält eine Fehlermeldung (kein "Commit is now allowed." in stdout)

### Test-Implementierung

Neue Datei `tests/test_qa_gate.py`, mock-freies Subprocess-Pattern analog zu
`tests/test_gate_coverage.py`:

```python
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
COPY_FILES = ["qa_gate.py", "workflow.py", "hook_utils.py",
              "config_loader.py", "override_token.py"]


def _setup_fake_project(tmp_path: Path, wf_name: str, skip_workflow_py: bool = False) -> Path:
    fake_hooks = tmp_path / "fake_hooks"
    fake_hooks.mkdir()
    for fname in COPY_FILES:
        if skip_workflow_py and fname == "workflow.py":
            continue
        shutil.copy(HOOKS_DIR / fname, fake_hooks / fname)
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / f"{wf_name}.json").write_text(json.dumps({
        "name": wf_name, "current_phase": "phase6_implement",
        "adversary_verdict": None,
    }))
    return fake_hooks


def _run_qa_gate(fake_hooks: Path, tmp_path: Path, wf_name: str, output_file: Path):
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "OPENSPEC_ACTIVE_WORKFLOW": wf_name,
           "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, str(fake_hooks / "qa_gate.py"), str(output_file)],
        capture_output=True, text=True, cwd=str(fake_hooks), env=env,
    )


def test_verdict_persisted_in_flat_consumer_layout(tmp_path):
    fake_hooks = _setup_fake_project(tmp_path, "wf1")
    output = tmp_path / "test-output.txt"
    output.write_text("test session starts\n5 passed in 1.2s\n" * 3)
    result = _run_qa_gate(fake_hooks, tmp_path, "wf1", output)
    assert result.returncode == 0
    state = json.loads((tmp_path / ".claude" / "workflows" / "wf1.json").read_text())
    assert state["adversary_verdict"] is not None
    assert state["adversary_verdict"].startswith("VERIFIED:")


def test_missing_workflow_py_fails_loudly(tmp_path):
    fake_hooks = _setup_fake_project(tmp_path, "wf2", skip_workflow_py=True)
    output = tmp_path / "test-output.txt"
    output.write_text("test session starts\n5 passed in 1.2s\n" * 3)
    result = _run_qa_gate(fake_hooks, tmp_path, "wf2", output)
    assert result.returncode != 0
    assert "Commit is now allowed." not in result.stdout
```

Ausführung:

```bash
python3 -m pytest tests/test_qa_gate.py -v
```

### Manuelle Verifikation (deckt AC-5 ab)

```bash
grep -nE "find_plugin_root|find_project_root|_plugin_root|_root\b" core/hooks/qa_gate.py
# → kein Treffer erwartet
```

## Changelog

- 2026-07-02: Initial spec erstellt für Issue #29
