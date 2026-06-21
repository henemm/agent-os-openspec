# Spec: Workflow Retro Commands

## What
Add `retro-list` and `retro [<name>]` commands to `workflow.py` plus a `/90-retro` slash command, so users can analyze completed workflows from the archive.

## Acceptance Criteria
- AC-1: `workflow.py retro-list` prints all archived workflows with name, type, date, total duration, and outcome
- AC-2: `workflow.py retro <name>` prints a structured retro report for the named archived workflow
- AC-3: `workflow.py retro` (no args) analyzes the most recently archived workflow
- AC-4: Retro report shows phase timeline with durations, quality signals (TDD, adversary, fix-loops), and optimization hints
- AC-5: `/90-retro` slash command guides user through list → pick → analyze flow
- AC-6: `80-workflow.md` and CHANGELOG updated

## Out of Scope
- Token/cost tracking (no API data available)
- Cross-workflow comparison stats
