# Phase 3: Write Specification

You are in **Phase 3 - Specification Writing**.

## Prerequisites

- Analysis completed (`phase2_analyse`)
- Context document exists with affected files list

Check current workflow:
```bash
python3 .claude/hooks/workflow_state_multi.py status
```

## Your Tasks

### Step 1: Vorbereitung

Lies die Analyse-Ergebnisse aus `docs/context/[workflow-name].md` und das Template aus `docs/specs/_template.md`.

### Step 2: Spec erstellen (general-purpose/Sonnet)

Dispatche einen **general-purpose/Sonnet Subagenten** mit den spec-writer Instruktionen:

```
Task (general-purpose/sonnet): "Du bist der spec-writer Agent.

  Input:
  - feature_name: [Name]
  - analysis_summary: [Zusammenfassung aus Phase 2]
  - affected_files: [Liste aus Analyse]
  - dependencies: [Liste aus Analyse]
  - workflow_name: [Workflow-Name]

  Erstelle eine vollstaendige Spec in docs/specs/[category]/[entity].md
  nach dem spec-writer Workflow. Beachte alle Qualitaetsregeln."
```

### Step 3: Spec validieren (spec-validator/Haiku)

Dispatche den **spec-validator/Haiku** zur Validierung:

```
Task (general-purpose/haiku): "Du bist der spec-validator Agent.

  Validiere die Spec: docs/specs/[category]/[entity].md
  Pruefe alle Required Fields, Sections, Placeholders.
  Output: VALID oder INVALID mit Details."
```

**Bei INVALID:**
1. Behebe die gemeldeten Fehler in der Spec
2. Dispatche spec-validator erneut
3. Wiederhole bis VALID

### Step 4: Workflow State aktualisieren

```bash
# Update spec file path in workflow
python3 -c "
import sys; sys.path.insert(0, '.claude/hooks')
from workflow_state_multi import load_state, save_state
state = load_state()
active = state.get('active_workflow')
if active:
    state['workflows'][active]['spec_file'] = 'docs/specs/[category]/[entity].md'
    save_state(state)
"

# Advance to spec_written phase
python3 .claude/hooks/workflow_state_multi.py phase phase3_spec
```

## Next Step

Present the spec and request approval:

> "Spec erstellt und validiert: `docs/specs/[path]`
>
> Scope: [N] files, ~[N] LoC
> Test plan: [N] automated tests
> Validation: VALID
>
> Confirm with 'approved', 'freigabe', or 'lgtm' to proceed."

## After Approval

When user approves:
1. `workflow_state_updater` hook detects approval phrase
2. State advances to `phase4_approved`
3. Next: `/tdd-red` to write failing tests

**IMPORTANT:**
- Do NOT implement until approved
- Do NOT skip TDD RED phase after approval
