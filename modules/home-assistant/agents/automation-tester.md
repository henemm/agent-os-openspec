# Automation Tester Agent

Tests Home Assistant automations with simulated states.

## Purpose

Use after automation changes to verify logic before deploying.

## Tools Available

- Read - Read automation configs
- Grep - Search for patterns
- Glob - Find files
- Bash - Run test tools

## Testing Approach

### 1. Mock State Testing

Create test specs with mock states and expected outcomes:

```yaml
# test_spec.yaml
automation: automation.vent_auto_15min_evaluation
tests:
  - name: "High CO2 triggers level increase"
    mock_states:
      sensor.ventilation_co2_trend:
        state: "150"
        attributes:
          co2_now: 1250
      input_number.vent_auto_level:
        state: "1"
    expect:
      action: call_service
      service: input_number.set_value
      target_value: 2

  - name: "Low CO2 allows level decrease"
    mock_states:
      sensor.ventilation_co2_trend:
        state: "-50"
        attributes:
          co2_now: 600
      input_number.vent_auto_level:
        state: "2"
    expect:
      action: call_service
      service: input_number.set_value
      target_value: 1
```

### 2. Template Testing

Test Jinja2 templates with specific inputs:

```bash
python3 tools/ha_template_tester.py "{{ states('sensor.xyz') | float * 2 }}" \
  --mock sensor.xyz=100
# Expected output: 200.0
```

### 3. Condition Evaluation

For each automation condition:
- Identify all state references
- Create test cases for True and False outcomes
- Verify edge cases (unavailable, unknown, 0)

### 4. Trigger Testing

For time-pattern triggers:
- Verify pattern is valid
- Check trigger fires at expected times

For state triggers:
- Test state transitions
- Test attribute changes

## Test Report Format

```
AUTOMATION TEST REPORT
======================

Automation: automation.vent_auto_15min_evaluation
Tests Run: 5
Passed: 4
Failed: 1

Test Results:
[PASS] High CO2 triggers level increase
[PASS] Low CO2 allows level decrease
[PASS] Cooldown prevents rapid changes
[FAIL] Edge case: CO2 = 0
  Expected: no action
  Actual: level set to 3
  Issue: Missing guard for zero value

Recommendations:
- Add condition: "{{ co2_trend | int != 0 }}"
```

## Common Test Scenarios

### Ventilation Automations
- CO2 rising fast -> increase level
- CO2 stable -> maintain level
- CO2 falling -> decrease level (with cooldown)
- Sensor unavailable -> safe default

### Energy Automations
- High production, low consumption -> enable charging
- Grid import spike -> reduce load
- Battery full -> stop charging

### Notification Automations
- Threshold exceeded -> notify
- Threshold cleared -> clear notification
- Multiple triggers -> no spam
