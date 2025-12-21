# Home Assistant Validator Agent

Validates Home Assistant configuration files for correctness.

## Purpose

Use this agent after EVERY implementation to catch config errors before restart.

## Tools Available

- Read - Read YAML configs
- Grep - Search for patterns
- Glob - Find config files
- Bash - Run validation commands

## Validation Checks

### 1. YAML Syntax

Check all modified YAML files for syntax errors:

```bash
python3 -c "import yaml; yaml.safe_load(open('file.yaml'))"
```

### 2. Entity References

For each `states('sensor.xyz')` or `entity_id: sensor.xyz`:
- Verify the entity exists (in config or HA)
- Check for typos in entity names

### 3. Template Sensor Configuration

Verify template sensors have:
- `name:` field (generates entity_id)
- `unique_id:` field (for entity registry)
- `state:` template
- Proper `availability:` if needed

**CRITICAL:** Entity ID is generated from `name:`, NOT from `unique_id`!

### 4. Automation Logic

Check automations for:
- Valid trigger configurations
- Proper condition syntax
- Action sequences make sense
- No circular dependencies

### 5. Jinja2 Templates

Common issues to flag:
- `max()` with single value (needs `| list`)
- Missing `| float(0)` for numeric operations
- `states()` returning 'unavailable'/'unknown' not handled
- Missing `namespace()` in for loops

### 6. Config Validation Command

Always run:
```bash
docker exec homeassistant python -m homeassistant --script check_config --config /config
```

## Output Format

```
HA CONFIG VALIDATION REPORT
===========================

Files Checked: 3
Status: PASS / FAIL

Errors:
- [ERROR] templates/sensors.yaml:45 - Invalid YAML syntax
- [ERROR] Entity 'sensor.xyz' referenced but not found

Warnings:
- [WARN] Automation 'xyz' has no conditions
- [WARN] Template uses 'max()' without list conversion

Config Check:
[Output from check_config command]
```

## Common Patterns

### Entity ID from Name
```yaml
# Wrong assumption:
- unique_id: sensor_xyz  # Does NOT set entity_id!

# Correct:
- name: "Sensor XYZ"     # Creates sensor.sensor_xyz
  unique_id: sensor_xyz   # For registry persistence
```

### Safe State Access
```yaml
# Risky:
{{ states('sensor.xyz') | float }}

# Safe:
{{ states('sensor.xyz') | float(0) }}

# Better:
{% if has_value('sensor.xyz') %}
  {{ states('sensor.xyz') | float }}
{% else %}
  0
{% endif %}
```
