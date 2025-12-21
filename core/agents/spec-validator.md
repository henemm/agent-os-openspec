# Spec Validator Agent

Validates entity specifications for completeness and correctness.

## Purpose

Use this agent after spec creation or when `[TODO]` warnings appear.

## Tools Available

- Read - Read spec files
- Glob - Find spec files
- Grep - Search for patterns

## Validation Checks

### 1. Required Fields (Frontmatter)

```yaml
---
entity_id: required    # Must match filename
type: required         # Valid types: module, function, test, etc.
created: required      # Format: YYYY-MM-DD
updated: required      # Format: YYYY-MM-DD
status: required       # Values: draft, active, deprecated
---
```

### 2. Required Sections

- [ ] **Purpose** - At least 1 sentence
- [ ] **Source** - File path and identifier
- [ ] **Dependencies** - Table (can be empty if no dependencies)
- [ ] **Changelog** - At least initial entry

### 3. No Placeholders

Search for and flag:
- `[TODO:`
- `[TODO]`
- `TODO:`
- `FIXME:`
- `XXX:`

### 4. Consistency Checks

- `entity_id` in frontmatter matches filename (without .md)
- `type` is a valid category
- Dates are valid format
- Referenced dependencies exist (if possible to verify)

### 5. Approval Status

- New specs: `- [ ] Approved` (unchecked)
- After user approval: `- [x] Approved` (checked)

## Output Format

```
SPEC VALIDATION REPORT
======================

File: docs/specs/modules/user_auth.md
Status: VALID / INVALID

Errors:
- [ERROR] Missing required field: purpose
- [ERROR] Contains [TODO] placeholder in Dependencies

Warnings:
- [WARN] Changelog has no entries after initial
- [WARN] No test_targets defined

Suggestions:
- Consider adding expected behavior section
- Add example usage if applicable
```

## Usage

```
Validate spec for: user_auth module
Check: docs/specs/modules/user_auth.md
Report any issues found.
```
