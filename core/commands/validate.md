# Phase 4: Validation

You are starting the **Validation Phase**.

## Prerequisites:

Check `.claude/workflow_state.json`:
- `current_phase` must be `implemented`
- `implementation_done` must be `true`

## Validation Checklist:

- [ ] Code compiles/runs without errors
- [ ] All tests pass
- [ ] New functionality works as specified
- [ ] No regressions introduced
- [ ] Edge cases handled
- [ ] No errors in logs

## Use Validation Agents:

If configured, use domain-specific validation agents:
- `implementation-validator` - Check for edge cases
- `spec-validator` - Verify spec compliance

## Test Targets (if defined in spec):

If the spec has `test_targets` in frontmatter, test each one:

```bash
# Example: Run specific tests
pytest tests/test_feature.py -v

# Mark test as complete (if using test tracking)
python3 tools/mark_test_complete.py "test_name"
```

## Update Workflow State:

After successful validation:
```json
{
  "current_phase": "validated",
  "validation_done": true,
  "last_updated": "[ISO timestamp]"
}
```

## On Failure:

If validation fails:
1. Do NOT update state to validated
2. Go back to implementation and fix
3. Re-run `/validate`

## Next Step:

> "Validation successful. You can now commit the changes."

After commit, reset the workflow:
```json
{
  "current_phase": "idle",
  "feature_name": null,
  "spec_file": null,
  "spec_approved": false,
  "implementation_done": false,
  "validation_done": false,
  "phases_completed": []
}
```
