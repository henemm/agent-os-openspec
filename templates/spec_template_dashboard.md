---
entity_id: dashboard_change_name
type: dashboard
dashboard: /lovelace/dashboard-name
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: draft
test_targets:
  - url: /lovelace/dashboard-name
    width: 1400
    expected: "Desktop layout correct"
  - url: /lovelace/dashboard-name
    width: 768
    expected: "Tablet layout correct"
  - url: /lovelace/dashboard-name
    width: 375
    expected: "Mobile layout correct"
affected_files:
  - lovelace/dashboard.yaml
---

# Dashboard Change: [Title]

## Approval

- [ ] Approved

## Problem

| Aspect | Current | Expected |
|--------|---------|----------|
| Layout | [describe current] | [describe expected] |
| Behavior | [describe current] | [describe expected] |

## Current Configuration

```yaml
# Current problematic configuration
type: grid
cards:
  - type: entity
    entity: sensor.example
```

## New Configuration

```yaml
# Proposed fix
type: custom:layout-card
layout_type: grid
layout:
  grid-template-columns: 1fr 1fr
cards:
  - type: entity
    entity: sensor.example
```

## Test Plan

### Automated Tests (Required)

For each entry in `test_targets`:
```bash
python3 tools/lovelace_screenshot.py "<url>" /tmp/test.png <width> 900
python3 tools/mark_test_complete.py "<url>" <width>
```

### Manual Verification

- [ ] Desktop (1400px): Layout as expected
- [ ] Tablet (768px): Responsive adjustments work
- [ ] Mobile (375px): Stacked layout readable
- [ ] No hui-error-card visible
- [ ] All data loads correctly

## Screenshots

### Before
[Link to before screenshot or "pending"]

### After
[Link to after screenshot or "pending"]

## Rollback

If issues occur:
```bash
git checkout HEAD~1 -- lovelace/dashboard.yaml
docker restart homeassistant
```

## Changelog

- YYYY-MM-DD: Initial spec created
