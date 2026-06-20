---
entity_id: bug_fix_fast_track
type: feature
created: 2026-06-20
updated: 2026-06-20
status: draft
version: "1.0"
tags: [workflow, bugs, token-efficiency]
test_targets:
  - core/hooks/edit_gate.py
  - core/hooks/workflow.py
  - core/commands/00-bug.md
---

# Bug-Fix Fast Track

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** (noch nicht erstellt)

## Purpose

Kleinen Bugs einen schlanken 3-Schritte-Weg geben, der den 8-Phasen-Workflow
auf das Wesentliche reduziert: verstehen → bestätigen → fixen. Die Phasen
Kontext-Sammlung, Spec-Schreiben, TDD-Red und Adversary-Validierung sind bei
trivialen Fixes (1-3 Dateien, bekannte Ursache) reiner Overhead.

## Abhängigkeiten

| Komponente | Typ | Abhängigkeit |
|-----------|-----|-------------|
| `workflow.py` | CLI | Neues Flag `--type bug` beim `start`-Subcommand |
| `edit_gate.py` | Hook | Liest `workflow_type` und überspringt TDD-Check wenn `bug` |
| `bash_gate.py` | Hook | Überspringt Adversary-Verdict-Check wenn `workflow_type == bug` |
| `config_loader.py` | Config | Neues Key `bug_fix.require_tdd` (bool, default `false`) |
| `00-bug.md` | Command | Erweiterung um Fast-Track-Pfad |

## Implementierungsdetails

### 1. Workflow-Typ `bug` im State

`workflow.py start <name> --type bug` schreibt ins JSON:

```json
{
  "name": "BUG-042",
  "workflow_type": "bug",
  "current_phase": "phase6_implement",
  ...
}
```

Der Workflow startet direkt bei `phase6_implement` — keine Phasen 1–5.

### 2. `edit_gate.py` — TDD-Check-Bypass

```python
wf = _read_active_workflow()
if wf and wf.get("workflow_type") == "bug":
    config = _load_config_values()
    if not config.get("bug_fix", {}).get("require_tdd", False):
        allow()  # TDD-Red-Artefakt-Check wird übersprungen
```

### 3. `bash_gate.py` — Adversary-Verdict-Bypass

Adversary-Verdict-Check (5c) wird übersprungen wenn `workflow_type == "bug"`.
Rebase-Check (5b) bleibt aktiv — auch Bugfixes dürfen nicht auf altem Commit landen.

### 4. `/00-bug.md` — Fast-Track-Pfad

Neuer Abschnitt am Ende:

```
## Fast Track (triviale Bugs — <3 Dateien, bekannte Ursache)

1. Bug kurz beschreiben (Symptom + Vermutete Ursache)
2. `workflow.py start BUG-<N> --type bug`
3. `export OPENSPEC_ACTIVE_WORKFLOW=BUG-<N>`
4. Fix direkt implementieren (kein Spec, kein TDD-Red erforderlich)
5. Manuell testen
6. `workflow.py complete`
```

### 5. `openspec.yaml` — Konfiguration

```yaml
bug_fix:
  require_tdd: false   # true → erzwingt TDD auch für Bug-Workflows
  max_files: 5         # Warnung wenn Fix mehr Dateien berührt (kein Block)
```

### 6. Optionaler Scope-Guard

Wenn der Fix mehr als `max_files` Dateien berührt, gibt `edit_gate.py` eine
Warnung aus (kein Block): "Bug-Fix berührt >5 Dateien — Feature-Workflow erwägen?"

## Expected Behavior

- **Input:** `workflow.py start BUG-042 --type bug`
- **Output:** Workflow-JSON mit `workflow_type: bug`, `current_phase: phase6_implement`
- **Edit-Gate:** Lässt Code-Edits durch ohne TDD-Artefakt-Check
- **Adversary-Gate:** Kein Verdict erforderlich vor `git commit`
- **Rebase-Gate:** Bleibt aktiv (unveränderter 5b-Check)

## Error Handling

- `workflow_type` unbekannt → `edit_gate.py` fällt auf Standard-Verhalten zurück (kein Block)
- `max_files`-Überschreitung → Warning auf stderr, kein Block
- `require_tdd: true` gesetzt → normaler TDD-Check greift auch bei Bug-Workflow

## Acceptance Criteria

- **AC-1:** Given `workflow.py start BUG-1 --type bug` / When Workflow gestartet / Then `workflow_type == "bug"` und `current_phase == "phase6_implement"` in JSON
- **AC-2:** Given aktiver Bug-Workflow + `require_tdd: false` / When Code-Edit in phase6 / Then kein Block durch TDD-Artefakt-Check
- **AC-3:** Given aktiver Bug-Workflow / When `git commit` / Then Adversary-Verdict-Check wird übersprungen, Rebase-Check bleibt aktiv
- **AC-4:** Given Bug-Workflow + Fix berührt >5 Dateien / When Code-Edit / Then Warning auf stderr (kein Block)
- **AC-5:** Given `require_tdd: true` in openspec.yaml / When Bug-Workflow + Code-Edit / Then normaler TDD-Check greift

## Test Plan

```bash
# AC-1
python3 core/hooks/workflow.py start BUG-TEST --type bug
cat .claude/workflows/BUG-TEST.json | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['workflow_type']=='bug'; assert d['current_phase']=='phase6_implement'"

# AC-2: edit_gate blockiert NICHT ohne TDD-Artefakt bei Bug-Workflow
OPENSPEC_ACTIVE_WORKFLOW=BUG-TEST python3 core/hooks/edit_gate.py
# → exit 0

# AC-3: bash_gate lässt commit durch ohne Adversary-Verdict
OPENSPEC_ACTIVE_WORKFLOW=BUG-TEST python3 core/hooks/bash_gate.py <<< '{"tool_input":{"command":"git commit -m test"}}'
# → exit 0 (nicht BLOCKED wegen fehlendem Verdict)
```

## Changelog

- 2026-06-20: Initial spec erstellt
