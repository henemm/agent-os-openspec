#!/usr/bin/env python3
"""
OpenSpec Framework - Hook Utilities

Shared bootstrap module for all hooks. Handles:
- sys.path setup for same-directory imports
- Common input parsing (tool_input from env or stdin)
- Standardized exit helpers

Usage in any hook:
    from hook_utils import setup_path, get_tool_input, block, allow
    setup_path()
    from config_loader import load_config, find_project_root
"""

import json
import os
import re
import sys
from pathlib import Path


# AC-Bullet-Start: unindentierte '- ...AC-N...:'-Zeile. Deckt vier
# Label-Varianten ab:
#   '- **AC-1:** ...'            (Doppelpunkt innerhalb Bold)
#   '- **AC-1**: ...'            (Doppelpunkt ausserhalb Bold)
#   '- **AC-8 (praezisiert):** ' (Klammer-Zusatz + Doppelpunkt in Bold)
#   '- AC-1: ...'                (ganz ohne Bold)
_AC_BULLET_RE = re.compile(r"^-\s+\*{0,2}AC-\d+[^:*]*\*{0,2}\s*:")
# Split-Variante: trennt Label (inkl. Klammer-Zusatz) vom Beschreibungstext.
# Konsumiert Bold-Marker auf beiden Seiten des Doppelpunkts.
_AC_SPLIT_RE = re.compile(r"^-\s+\*{0,2}(AC-\d+[^:*]*?)\*{0,2}\s*:\s*\*{0,2}\s*(.*)$")


def extract_ac_entries(content: str) -> "list[tuple[str, str, str]]":
    """Section-gebunden AC-N-Bullets aus '## Acceptance Criteria' extrahieren.

    Liefert (label, description, raw) je Bullet, z.B.
    ("AC-1", "Given ... Then ...", "**AC-1:** Given ... Then ...").
    raw = Original-Bulletzeile (inkl. Soft-Wrap-Fortsetzungen) OHNE fuehrendes
    "- ", damit Konsumenten den unveraenderten Quelltext erhalten koennen.
    Soft-Wrap-Fortsetzungszeilen werden angehaengt, eingerueckte Sub-Bullets
    (z.B. '- Test:') verworfen. Nur Bullets INNERHALB der Section zaehlen --
    weder Fliesstext-Querverweise noch Tabellenzellen noch Vorkommen in
    anderen Sections.

    Section-gebundene State-Machine, 1:1 aus der bisherigen Inline-Logik in
    adversary_dialog.parse_spec_expected_behavior uebernommen; einziger
    Unterschied: Label, Beschreibungstext UND der Original-Rohtext werden
    getrennt zurueckgegeben statt als ein rekonstruierter String.
    """
    lines = content.splitlines()
    in_section = False
    ac_active = False
    entries: "list[list[str]]" = []  # [label, description, raw], mutable fuer Soft-Wrap

    for line in lines:
        stripped = line.strip()
        indented = line[:1].isspace()

        # Section-State pflegen (case-insensitive)
        if re.match(r"^##\s+Expected Behavior", stripped, re.IGNORECASE):
            in_section = False
            ac_active = False
            continue
        if re.match(r"^##\s+Acceptance Criteria", stripped, re.IGNORECASE):
            in_section = True
            ac_active = False
            continue
        # Jede andere H2-Section beendet die aktuelle Section
        if re.match(r"^##\s+", stripped):
            in_section = False
            ac_active = False
            continue

        if not in_section:
            continue

        # AC-Bullet nur INNERHALB der Acceptance-Criteria-Section (unindentiert)
        if not indented and _AC_BULLET_RE.match(stripped):
            raw = re.sub(r"^-\s+", "", stripped)  # Original-Bullet ohne "- "
            m = _AC_SPLIT_RE.match(stripped)
            if m:
                label = m.group(1).strip()
                desc = m.group(2).strip()
            else:  # Defensive: sollte nie eintreten (Split ist Superset)
                label = ""
                desc = raw
            entries.append([label, desc, raw])
            ac_active = True
            continue
        # Innerhalb eines offenen AC-Blocks: Sub-Bullet vs. Fortsetzung
        if ac_active and indented:
            if stripped.startswith("-"):
                # Eingerueckter Sub-Bullet (z.B. '- Test:') -> verwerfen
                continue
            if stripped:
                # Fortsetzungszeile (Soft-Wrap) -> an desc UND raw anhaengen
                entries[-1][1] = (entries[-1][1] + " " + stripped).strip()
                entries[-1][2] = (entries[-1][2] + " " + stripped).strip()
            continue
        # Unindentierte Nicht-AC-Zeile beendet einen offenen AC-Block
        if not indented and stripped:
            ac_active = False

    return [(label, desc, raw) for label, desc, raw in entries]


def setup_path():
    """Add the hooks directory to sys.path for same-directory imports.
    Call this BEFORE importing config_loader or other hook modules."""
    hooks_dir = str(Path(__file__).parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)


def get_tool_input() -> dict:
    """Parse tool input from CLAUDE_TOOL_INPUT env var or stdin.
    Returns parsed dict or empty dict on failure."""
    tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")

    if not tool_input:
        try:
            data = json.load(sys.stdin)
            return data.get("tool_input", {})
        except (json.JSONDecodeError, Exception):
            return {}

    try:
        return json.loads(tool_input) if isinstance(tool_input, str) else tool_input
    except json.JSONDecodeError:
        return {}


def get_user_message() -> str:
    """Parse user message from stdin (for UserPromptSubmit hooks).

    Claude Code sendet den Prompt-Text im Feld "prompt" (offizielle Hook-API).
    "user_message" wird als Fallback fuer aeltere Versionen/Wrapper beibehalten.
    Vor diesem Fix las der Hook ausschliesslich "user_message" und bekam daher
    IMMER einen leeren String — der gesamte phase_listener (override, go/approval,
    stop-lock, GREEN) war dadurch funktionslos.
    """
    try:
        data = json.load(sys.stdin)
        return data.get("prompt") or data.get("user_message", "")
    except (json.JSONDecodeError, Exception):
        return ""


def get_tool_result() -> dict:
    """Parse tool result from stdin (for PostToolUse hooks)."""
    try:
        data = json.load(sys.stdin)
        return data
    except (json.JSONDecodeError, Exception):
        return {}


def block(message: str):
    """Block the operation with an error message and exit."""
    print(message, file=sys.stderr)
    sys.exit(2)


def allow():
    """Allow the operation and exit."""
    sys.exit(0)


def get_file_path(tool_input: dict = None) -> str:
    """Extract file_path from tool input."""
    if tool_input is None:
        tool_input = get_tool_input()
    return tool_input.get("file_path", "")


def get_command(tool_input: dict = None) -> str:
    """Extract command from tool input (for Bash hooks)."""
    if tool_input is None:
        tool_input = get_tool_input()
    return tool_input.get("command", "")


def is_code_file(file_path: str) -> bool:
    """Check if a file is a code file based on extension."""
    code_extensions = [
        ".py", ".js", ".ts", ".tsx", ".jsx",
        ".swift", ".kt", ".java",
        ".go", ".rs", ".cpp", ".c", ".h",
        ".rb", ".php", ".cs",
    ]
    return any(file_path.endswith(ext) for ext in code_extensions)


def find_main_repo_from_worktree(start: Path) -> "Path | None":
    """If start is inside a git worktree, return the linked main repo root.

    Git worktrees place a .git FILE (not directory) pointing at the main repo:
      gitdir: <main>/.git/worktrees/<name>
    Returns None if start is not in a worktree.
    """
    current = start
    while current != current.parent:
        git_marker = current / ".git"
        if git_marker.is_file():
            try:
                content = git_marker.read_text(errors="ignore").strip()
            except OSError:
                return None
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("gitdir:"):
                    gitdir = Path(line[len("gitdir:"):].strip())
                    if not gitdir.is_absolute():
                        gitdir = (current / gitdir).resolve()
                    # Walk up until we find the .git directory itself
                    walker = gitdir
                    while walker.name != ".git" and walker != walker.parent:
                        walker = walker.parent
                    if walker.name == ".git":
                        return walker.parent
            return None
        if git_marker.is_dir():
            return None
        current = current.parent
    return None


def find_project_root() -> Path:
    """Find project root. Resolves git worktrees to the main repo root.

    Priority:
    1. CLAUDE_PROJECT_DIR env var (set by Claude Code) — resolved through worktree if needed
    2. Walk up from CWD looking for .git, resolving worktrees transparently
    """
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        p = Path(env_dir)
        main = find_main_repo_from_worktree(p)
        return main if main is not None else p
    cwd = Path.cwd()
    main = find_main_repo_from_worktree(cwd)
    if main is not None:
        return main
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").is_dir():
            return parent
    return cwd


def _workflow_file_exists(root: Path, name: str) -> bool:
    """Return True if workflows/<name>.json exists under the project root."""
    try:
        return (root / ".claude" / "workflows" / f"{name}.json").exists()
    except OSError:
        return False


def resolve_active_workflow() -> "tuple[str, str]":
    """Return (name, source). source ∈ {'file', 'settings', 'env', 'none'}.

    Single source of truth for active-workflow name resolution. Both
    workflow._read_active() and workflow.read_active_workflow_fast() delegate here
    instead of duplicating the priority chain — keep this function authoritative
    and change resolution behaviour ONLY here.

    Worktree-aware priority — prevents cross-session contamination:

    In a worktree session:
      1. Worktree-local active_workflow file ({worktree_root}/.claude/active_workflow)
         Written by workflow.py start/switch within THIS worktree. Never shared.
      2. Worktree-local settings.local.json env section (written live by workflow.py
         start/switch — not frozen, reflects the latest call in this session).
         Validated: skipped if workflows/<name>.json does not exist.
      3. OPENSPEC_ACTIVE_WORKFLOW env var (frozen at session start by Claude Code).
         Validated: skipped if it doesn't point to an existing workflow file.
         Prevents stale values (e.g. the worktree directory name injected at startup)
         from shadowing the correct settings value.
      (Shared {project_root}/.claude/active_workflow is SKIPPED — it might belong to
      a parallel session and would contaminate this session's context.)

    In a main repo session (not a worktree):
      1. Shared active_workflow file ({project_root}/.claude/active_workflow)
      2. {project_root}/.claude/settings.local.json env section
      3. OPENSPEC_ACTIVE_WORKFLOW env var (frozen at session start)
    """
    root = find_project_root()
    worktree_root = _find_worktree_root()

    if worktree_root is not None:
        # 1. Worktree-local active_workflow file (written by workflow.py start/switch)
        try:
            active_file = worktree_root / ".claude" / "active_workflow"
            if active_file.exists():
                name = active_file.read_text().strip()
                if name:
                    return name, "file"
        except OSError:
            pass
        # 2. Worktree-local settings.local.json (updated live, not frozen like env)
        try:
            settings_path = worktree_root / ".claude" / "settings.local.json"
            if settings_path.exists():
                settings = json.loads(settings_path.read_text())
                name = (settings.get("env") or {}).get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()
                if name and _workflow_file_exists(root, name):
                    return name, "settings"
        except (OSError, json.JSONDecodeError, KeyError):
            pass
        # 3. Env var (frozen at session start) — only trusted if it points to a real workflow
        name = os.environ.get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()
        if name and _workflow_file_exists(root, name):
            return name, "env"
        return "", "none"

    # Main repo session: existing priority chain
    try:
        active_file = root / ".claude" / "active_workflow"
        if active_file.exists():
            name = active_file.read_text().strip()
            if name:
                return name, "file"
    except OSError:
        pass
    try:
        settings_path = root / ".claude" / "settings.local.json"
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
            name = (settings.get("env") or {}).get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()
            if name:
                return name, "settings"
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    name = os.environ.get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()
    if name:
        return name, "env"
    return "", "none"


def _find_worktree_root() -> "Path | None":
    """If CWD is inside a git worktree, return the worktree root (dir with .git FILE).

    Returns None if in the main repo (where .git is a directory, not a file).
    Mirrors workflow._worktree_root_if_any() — kept local to avoid circular imports.
    """
    current = Path.cwd()
    while current != current.parent:
        git_marker = current / ".git"
        if git_marker.is_file():
            return current
        if git_marker.is_dir():
            return None
        current = current.parent
    return None


def get_active_workflow_name() -> str:
    """Unverändertes Verhalten — delegiert an resolve_active_workflow()."""
    return resolve_active_workflow()[0]


def gate_diagnostics(workflow: "dict | None" = None, **extra) -> str:
    """Bracketed diagnostics for block messages.

    Beispiel: '[wf=feature-login (env) | token=keins | phase=phase6_implement]'
    Fail-safe: jede Teilinfo, die nicht ermittelbar ist, wird zu '?' —
    der Builder wirft nie.
    """
    try:
        name, source = resolve_active_workflow()
    except Exception:
        name, source = "?", "?"
    parts = [f"wf={name or '—'} ({source})"]
    try:
        from override_token import has_valid_token
        parts.append("token=gültig" if has_valid_token(name or None) else "token=keins")
    except Exception:
        parts.append("token=?")
    try:
        if workflow:
            parts.append(f"phase={workflow.get('current_phase', '?')}")
    except Exception:
        parts.append("phase=?")
    try:
        for key, value in extra.items():
            parts.append(f"{key}={value}")
    except Exception:
        pass
    return "[" + " | ".join(parts) + "]"


def find_plugin_root() -> Path:
    """Plugin-Root: wo die Hook-Skripte liegen."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if env:
        return Path(env)
    # Fallback: hook_utils.py liegt in plugin_root/core/hooks/
    candidate = Path(__file__).parent.parent.parent
    if (candidate / ".claude-plugin" / "plugin.json").exists():
        return candidate
    return candidate


def is_module_enabled(module_id: str) -> bool:
    """Check if a plugin module is enabled via OPENSPEC_ENABLED_MODULES env var."""
    enabled = os.environ.get("OPENSPEC_ENABLED_MODULES", "")
    return module_id in [m.strip() for m in enabled.split(",") if m.strip()]


def is_test_file(file_path: str) -> bool:
    """Check if a file is a test file."""
    test_patterns = [
        "test_", "_test.", ".test.", "tests/", "spec/", "_spec.",
        "Test.", "Tests/", "UITests/",
    ]
    return any(pattern in file_path for pattern in test_patterns)
