---
entity_id: entity_name
type: module
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: draft
version: "1.0"
tags: []
---

# Entity Name

## Approval

- [ ] Approved

## Purpose

[1-2 sentences: What does this entity do? Why does it exist?]

## Source

- **File:** `path/to/file`
- **Identifier:** `class/function name`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| | | |

## Scope

- **Affected Files:** `path/to/file_1`, `path/to/file_2`
- **Estimated Changes:** ~N LoC

## Implementation Details

```
[Code or logic description]
```

## Expected Behavior

- **Input:** [description]
- **Output:** [description]
- **Side effects:** [if any]

## Known Limitations

- [Any limitations]

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] [beobachtbares Ergebnis, an dem der PO „fertig" erkennt — kein „Code gemerged"]
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given <Vorbedingung> / When <Aktion> / Then <beobachtbares Ergebnis>
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_entity.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** [ADR-NNNN oder "keine"]
- **Rationale:** [kurz: warum diese Entscheidung bzw. warum keine nötig ist]

## Changelog

- YYYY-MM-DD: Initial spec created
