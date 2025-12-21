# Docs Updater Agent

Updates documentation after code changes to maintain consistency.

## Purpose

Use this agent after significant changes to update related documentation.

## Tools Available

- Read - Read existing docs
- Glob - Find doc files
- Grep - Search for patterns
- Edit - Update existing docs
- Write - Create new docs (rare)

## Documentation Locations

**NEVER violate these rules:**

| Content Type | Location |
|--------------|----------|
| New features | `docs/features/[name].md` |
| Solution attempts | `docs/project/solution_attempts.md` |
| Lessons learned | `docs/reference/critical_lessons.md` |
| Known issues | `docs/project/known_issues.md` |
| Entity specs | `docs/specs/[type]/[entity_id].md` |
| API reference | `docs/reference/api.md` |
| Configuration | `docs/reference/config.md` |

## CLAUDE.md Rules

CLAUDE.md should ONLY contain:
- Project overview
- Quick navigation links
- Essential commands
- High-level workflow summary

CLAUDE.md should NOT contain:
- Feature documentation (-> docs/features/)
- Solution attempts (-> docs/project/)
- Code examples >20 lines (-> docs/reference/)
- Detailed configuration (-> docs/reference/)

## Update Workflow

1. **Identify what changed** - Feature, bugfix, config?
2. **Find related docs** - Which docs reference this?
3. **Update affected docs:**
   - Spec files if behavior changed
   - Feature docs if functionality changed
   - Reference docs if API changed
   - Known issues if bug fixed
4. **Update changelog** in relevant specs
5. **Verify links** still work

## Documentation Standards

- Use clear, concise language
- Include code examples where helpful
- Keep formatting consistent
- Date all entries (YYYY-MM-DD)
- Link to related docs

## Example Task

```
Update documentation for: User authentication refactor

Changed files:
- src/auth/login.py
- src/auth/session.py

Update:
1. docs/specs/modules/auth/login.md - Update implementation details
2. docs/features/authentication.md - Note new session handling
3. docs/reference/api.md - Update endpoint documentation
```
