# Verify Active Code Location

> Before editing, confirm you're working on the ACTIVE code.

## The Problem

Codebases often have:
- Old/unused versions of files
- Duplicate implementations
- Dead code that looks active

Hours can be wasted debugging the wrong file.

## Mandatory Check

**BEFORE editing any file, verify:**

```bash
# 1. Is this file actually used?
grep -rn "MyFileName" --include="*.swift" --include="*.py" --include="*.ts" .

# 2. Are there duplicates?
grep -rn "class MyClass\|struct MyStruct\|function myFunc" .

# 3. Check imports/includes in main entry point
```

## Warning Signs

- File has "View" in name but there's also a "Tab" variant
- Changes have no visible effect
- Logs don't appear despite correct-looking code
- Multiple files with similar names

## Quick Checklist

| Check | Action |
|-------|--------|
| File is imported somewhere | `grep -rn "import MyFile"` |
| No duplicates exist | `grep -rn "class MyClass"` |
| Used in entry point | Check main/ContentView/App |

## Consequence

Wrong file = wasted hours, frustrated user, burned tokens.

---

*Lesson learned: Always trace back to entry point before editing.*
