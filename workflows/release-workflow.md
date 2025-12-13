# Release Workflow

## Overview

Steps to prepare and release a new version.

## Pre-Release Checklist

### 1. All Tests Passing

```bash
xcodebuild test -project {{PROJECT_FILE}} \
  -scheme "{{TEST_SCHEME}}" \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro'
```

All tests must pass.

### 2. Build Verification

```bash
xcodebuild -project {{PROJECT_FILE}} \
  -scheme "{{MAIN_SCHEME}}" \
  -configuration Release \
  -destination 'platform=iOS Simulator,name=iPhone 15 Pro' \
  build
```

No errors or warnings (except unavoidable system ones).

### 3. Documentation Review

- [ ] DOCS/ACTIVE-todos.md - No critical bugs open
- [ ] DOCS/ACTIVE-roadmap.md - Completed features marked
- [ ] CLAUDE.md - Version number updated

### 4. Localization Check

- [ ] All new strings in Localizable.xcstrings
- [ ] All language translations present
- [ ] No hardcoded strings in new code

## Version Bump

### Update Version Number

In Xcode project:
- `MARKETING_VERSION` (e.g., 1.0.1)
- `CURRENT_PROJECT_VERSION` (increment build number)

### Update CLAUDE.md

```markdown
**Current Version:** X.Y.Z
```

## Commit

```bash
git commit -m "chore: Bump version to X.Y.Z

Changes in this release:
- [Feature/Fix 1]
- [Feature/Fix 2]

🤖 Generated with Claude Code"
```

## Post-Release

### Tag Release

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

### Archive for App Store

In Xcode:
1. Product -> Archive
2. Distribute App -> App Store Connect
3. Upload

### Update Documentation

- [ ] Clear completed items from ACTIVE-todos.md
- [ ] Update ACTIVE-roadmap.md status
- [ ] Note release date
