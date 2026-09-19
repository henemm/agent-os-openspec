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

## GitHub Issue

- **Issue:** #N (link to tracking issue)

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

## Scope

- **Affected Files:** `path/to/file_1`, `path/to/file_2`
- **Estimated Changes:** ~N LoC

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

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] [beobachtbares Ergebnis, an dem der PO „fertig" erkennt — kein „Code gemerged"]
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given <precondition> / When <action> / Then <observable outcome>
  - Test: *(populated after TDD RED phase)*

- **AC-2:** Given <precondition> / When <action> / Then <observable outcome>
  - Test: *(populated after TDD RED phase)*

## Test Plan

Automated tests (linked to AC above):
- `pytest tests/test_entity.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** [ADR-NNNN oder "keine"]
- **Rationale:** [kurz: warum diese Entscheidung bzw. warum keine nötig ist]

## Changelog

- YYYY-MM-DD: Initial spec created
