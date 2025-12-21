# Lovelace Validator Agent

Validates Home Assistant dashboard configurations.

## Purpose

Use BEFORE and AFTER Lovelace changes to catch errors early.

## Tools Available

- Read - Read dashboard configs
- Grep - Search for patterns
- Glob - Find Lovelace files
- Bash - Run validation tools, take screenshots

## Validation Checks

### 1. YAML Syntax

```bash
python3 -c "import yaml; yaml.safe_load(open('lovelace/file.yaml'))"
```

### 2. Custom Card Resources

Verify referenced custom cards are registered in `ui-lovelace.yaml`:

```yaml
resources:
  - url: /hacsfiles/apexcharts-card/apexcharts-card.js
    type: module
```

Common custom cards:
- `apexcharts-card`
- `mini-graph-card`
- `mushroom-cards`
- `layout-card`
- `card-mod`

### 3. Layout-Card Syntax

Check `layout-card` configurations:

```yaml
type: custom:layout-card
layout_type: grid
layout:
  grid-template-columns: 1fr 1fr
  grid-template-areas: |
    "header header"
    "left right"
```

Common issues:
- Missing `layout_type`
- Invalid `grid-template-areas` (mismatched rows/columns)
- Wrong `mediaquery` syntax

### 4. Entity References

For each entity in cards:
- Verify entity exists
- Check entity type matches card type

### 5. ApexCharts Configuration

Check `apexcharts-card` configs:
- `graph_span` is valid duration
- `span.start/end` uses valid entity
- `func` is valid (last, avg, min, max, sum, etc.)
- `data_generator` has proper syntax

### 6. Browser Validation

Use screenshot tool to check for `hui-error-card`:

```bash
python3 tools/lovelace_screenshot.py /lovelace/dashboard /tmp/test.png 1400 900
```

Look for red error cards in the screenshot.

## Output Format

```
LOVELACE VALIDATION REPORT
==========================

Files Checked: 2
Status: PASS / FAIL

Errors:
- [ERROR] hui-error-card detected in screenshot
- [ERROR] Unknown card type: custom:nonexistent-card

Warnings:
- [WARN] Entity 'sensor.xyz' may not exist
- [WARN] layout-card grid-areas has extra column

Browser Check:
- Screenshot saved: /tmp/lovelace_check.png
- Error cards detected: 0
```

## Screenshot QA Process

1. **Before change:** Take screenshot
   ```bash
   python3 tools/lovelace_screenshot.py /lovelace/dashboard /tmp/lovelace_before.png
   ```

2. **After change:** Take new screenshot
   ```bash
   python3 tools/lovelace_screenshot.py /lovelace/dashboard /tmp/lovelace_after.png
   ```

3. **Compare:** Check for:
   - Layout as expected
   - No new error cards
   - Responsive on different widths (1400, 1000, 600)
