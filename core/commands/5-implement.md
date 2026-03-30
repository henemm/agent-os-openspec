# Phase 6: Implementation (TDD GREEN)

You are in **Phase 6 - Implementation / TDD GREEN Phase**.

## Purpose

Write the **minimal code** to make failing tests pass. No more, no less.

## Prerequisites

- Spec approved (`phase4_approved`)
- TDD RED complete (`phase5_tdd_red`)
- Test artifacts registered showing failures

Check status:
```bash
python3 .claude/hooks/workflow.py status
```

**If TDD RED artifacts are missing, the `tdd_enforcement` hook will BLOCK your edits!**

## Your Tasks

### Step 1: Verify RED Phase Complete

```bash
python3 .claude/hooks/workflow.py status
```

### Step 2: Kontext laden (Explore/Haiku)

Dispatche einen **Explore/Haiku Subagenten** um den Implementierungs-Kontext zu laden:

```
Task (Explore/haiku): "Lies folgende Dateien und fasse den relevanten Kontext
  zusammen:
  - Spec: [spec_file_path]
  - Betroffene Dateien: [affected_files]
  - Test-Dateien: [test_files]

  Fasse zusammen: Welche Interfaces existieren, welche Methoden muessen
  implementiert werden, welche Imports werden benoetigt."
```

### Step 3: Implementieren (Hauptkontext / Opus)

Die eigentliche Implementation passiert im **Hauptkontext** (Opus) fuer hoechste Qualitaet:

- Lies und befolge die approved Spec exakt
- Schreibe Code der die Tests gruen macht
- Halte dich an die Scoping-Limits

**TDD GREEN Rules:**
- Only write code that makes a test pass
- Don't add features not covered by tests
- Don't optimize prematurely
- Don't refactor yet

### Step 4: Parallele Side-Tasks

Dispatche parallel waehrend/nach der Implementation:

```
Task 1 (general-purpose/sonnet): "Fuehre die Tests aus:
  [test_command]
  Fasse Ergebnisse zusammen: passed/failed/errors."

Task 2 (general-purpose/haiku): "Pruefe ob Konfigurationsdateien
  aktualisiert werden muessen fuer [Feature].
  Check: package.json, config files, environment variables."
```

### Step 5: GREEN Artifacts erfassen

```bash
# Test output erfassen
[test_command] > docs/artifacts/[workflow]/test-green-output.txt 2>&1

python3 .claude/hooks/workflow.py add-artifact test_output \
    "docs/artifacts/[workflow]/test-green-output.txt" \
    "All tests PASSED" \
    phase6_implement
```

### Step 6: Update Workflow State

```bash
python3 .claude/hooks/workflow.py phase phase7_validate
```

## Implementation Constraints

Follow scoping limits:
- **Max 4-5 files** per change
- **Max +/-250 LoC** total
- **Functions <= 50 LoC**
- **No side effects** outside spec scope

## Next Step

After implementation:
> "Implementation complete. All [N] tests pass. Ready for `/validate`."

## Common Mistakes

- **Adding unrequested features** -> Scope creep
- **Skipping tests** -> Not TDD
- **Large functions** -> Hard to test/maintain
- **Not running tests** -> Might still be RED
