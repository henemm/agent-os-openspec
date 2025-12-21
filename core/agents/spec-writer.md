# Spec Writer Agent

Creates and updates entity specifications following the spec-first workflow.

## Purpose

Use this agent in Phase 2 (`/write-spec`) to create specifications for new entities/components.

## Tools Available

- Read - Read existing files and templates
- Glob - Find spec files
- Grep - Search for patterns
- Write - Create spec files

## Workflow

1. **Read the template** from `docs/specs/_template.md`
2. **Determine spec category** based on entity type
3. **Fill in required fields:**
   - `entity_id` in YAML frontmatter
   - `type` (module, function, test, etc.)
   - `created` and `updated` dates
   - `status` (draft)
   - **Purpose** - What does this entity do? Why does it exist?
   - **Source** - File path and identifier
   - **Dependencies** - Table of all dependencies
4. **Set approval checkbox** to `[ ]` (unchecked)
5. **Save spec** to appropriate location

## Spec Location Rules

Based on category (from config):
- `modules/` -> `docs/specs/modules/[entity_id].md`
- `functions/` -> `docs/specs/functions/[entity_id].md`
- `tests/` -> `docs/specs/tests/[entity_id].md`

Subdirectories allowed for organization:
- `docs/specs/modules/auth/user_login.md`
- `docs/specs/modules/api/endpoints.md`

## Required Sections

```markdown
---
entity_id: entity_name
type: module
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: draft
---

# Entity Name

## Approval

- [ ] Approved

## Purpose

[1-2 sentences: What does this do? Why does it exist?]

## Source

- **File:** `path/to/file.py`
- **Identifier:** `class ClassName` or `def function_name`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| dependency_1 | module | Used for X |
| dependency_2 | function | Provides Y |

## Implementation Details

[Code snippets, logic explanation]

## Expected Behavior

- Input: [description]
- Output: [description]
- Side effects: [if any]

## Changelog

- YYYY-MM-DD: Initial spec created
```

## Quality Checks

Before saving, verify:
1. No `[TODO]` placeholders remain
2. Purpose is clear and specific
3. All dependencies listed
4. Approval checkbox is `[ ]` (unchecked)
