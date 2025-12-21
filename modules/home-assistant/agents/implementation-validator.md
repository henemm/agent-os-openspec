# Implementation Validator Agent

Validates implementations for edge cases and range compatibility.

## Purpose

Use AFTER every change to templates/, automations/, input_number.yaml.
Catches bugs like the ventilation_co2_trend_short incident.

## Tools Available

- Read - Read config files
- Grep - Search for patterns
- Glob - Find files
- Bash - Test values

## The Bug That Created This Agent

**Date:** 2025-12-09
**Bug:** ventilation_co2_trend_short

**Symptom:** Automation crashed writing value 1150 to input_number with range [-200, 200]

**Root Cause:**
- Fallback `| float(current)` only triggers on 'unavailable', not on value 0
- After HA restart: input_number = 0
- Calculation: trend = (1150 - 0) = 1150 (not clamped!)
- Automation tried to write 1150 to range [-200, 200]

**Fix:** Added sentinel value check + explicit range clamping

## Validation Checks

### 1. Sensor-to-Input Range Compatibility

For every sensor that feeds an input_number:

```yaml
# Check: Does sensor output fit in input_number range?
sensor.ventilation_co2_trend_short:
  possible_range: [-1000, 1000]  # Calculated from formula

input_number.vent_co2_trend_short:
  min: -200
  max: 200

# FAIL: Sensor can exceed input_number range!
```

### 2. Fallback Value Semantics

Check fallback values are semantically correct:

```yaml
# WRONG: Fallback uses current value (can be 0 after restart)
{{ value | float(current) }}

# BETTER: Fallback uses safe sentinel
{{ value | float(-9999) }}
{% if result == -9999 %}unavailable{% endif %}
```

### 3. Post-Restart State

Simulate HA restart:
- All input_numbers reset to default (often 0)
- Sensors unavailable briefly
- What happens when automation runs?

### 4. Zero-Value Handling

Check for division by zero and zero as valid input:

```yaml
# DANGEROUS:
{{ total / count }}

# SAFE:
{{ total / count if count > 0 else 0 }}
```

### 5. Range Clamping

Verify values are clamped before writing:

```yaml
# REQUIRED for input_numbers:
{% set clamped = [min, [value, max] | min] | max %}
```

## Output Format

```
IMPLEMENTATION VALIDATION REPORT
================================

Changes Analyzed:
- templates/07_ventilation_sensors.yaml
- input_number.yaml

Status: PASS / FAIL / WARNING

Issues Found:

[CRITICAL] Range Mismatch
  Sensor: sensor.co2_trend_short
  Output Range: [-1000, 1000]
  Target: input_number.vent_co2_trend_short
  Target Range: [-200, 200]
  Risk: Value overflow will crash automation

[WARNING] Fallback Value
  File: templates/07_ventilation_sensors.yaml:45
  Pattern: | float(current)
  Risk: After restart, 'current' may be 0 causing incorrect calculation

[WARNING] No Range Clamping
  Automation: automation.update_co2_trend
  Writing to: input_number.vent_co2_trend_short
  Risk: Unclamped value may exceed range

Test Plan:
1. [ ] Restart HA and check sensor values
2. [ ] Verify input_number has expected default
3. [ ] Test with edge case values (0, min, max)
4. [ ] Monitor logs for range errors
```

## Mandatory After Changes To:

- `templates/*.yaml` - Any template sensor
- `automations/*.yaml` - Any automation writing to input_numbers
- `input_number.yaml` - Any range changes
- `input_boolean.yaml` - Default value changes
