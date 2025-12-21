---
entity_id: entity_name_here
type: module
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: draft
version: "1.0"
tags: []
test_targets: []
---

# Entity Name

## Approval

- [ ] Approved

## Purpose

[1-2 sentences: What does this entity do? Why does it exist?]

## Source

- **File:** `path/to/source/file`
- **Identifier:** `class ClassName` or `def function_name`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| dependency_1 | module | Used for X |
| dependency_2 | function | Provides Y |

## Implementation Details

```python
# Code snippet or pseudocode
def example():
    pass
```

## Expected Behavior

- **Input:** Description of expected inputs
- **Output:** Description of expected outputs
- **Side effects:** Any side effects (file writes, API calls, etc.)

## Error Handling

- What happens on invalid input?
- What happens if dependencies fail?
- Recovery strategies?

## Known Limitations

- Limitation 1
- Limitation 2

## Test Plan

Manual tests:
- [ ] Test case 1
- [ ] Test case 2

Automated tests:
- `pytest tests/test_entity.py`

## Changelog

- YYYY-MM-DD: Initial spec created
