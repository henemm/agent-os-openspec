#!/usr/bin/env python3
"""
OpenSpec Framework - Configuration Loader

Shared module for loading and accessing framework configuration.
All hooks import this to get consistent config access.

Supports:
- openspec.yaml / config.yaml - Main configuration
- settings.local.json - Local overrides (NOT in git, for credentials etc.)

Eine `config.yaml` direkt im Projekt-Root zaehlt nur als Plugin-Config, wenn sie
mindestens einen Plugin-Block enthaelt (`is_plugin_config()`, Issue #372) — sonst
ist es vermutlich die Config der App selbst und wird uebergangen.
`openspec.yaml`, `.openspec.yaml` und alles unter `.claude/` gelten ungeprueft.
"""

import os
import json
import re
import sys
from pathlib import Path
from functools import lru_cache

# Re-export for projects that imported from config_loader before Plugin migration
from hook_utils import find_main_repo_from_worktree  # noqa: F401

try:
    import yaml
except ImportError:
    print("WARNING: PyYAML not installed. Install with: pip install pyyaml", file=sys.stderr)
    yaml = None

# Config file search order
CONFIG_NAMES = ["openspec.yaml", "config.yaml", ".openspec.yaml"]

# Issue #372: Eine `config.yaml` im Projekt-Root kann der App gehoeren (Fundfall:
# Go-Dienst mit Bot-Token). Sie gilt nur dann als Plugin-Config, wenn sie einen
# dieser unverwechselbaren Plugin-Bloecke enthaelt.
PLUGIN_CONFIG_KEYS = frozenset({
    "framework", "workflow", "specs", "strict_code_gate", "secrets_guard",
    "secret_egress_guard", "credentials_guard", "dependency_dir_guard",
    "fast_track", "pre_commit", "stop_lock", "override_token", "tdd",
    "adversary_gate", "adversary_risk", "adversary_coverage_gate", "adr_gate",
    "po_briefing_gate", "ci_spec_gate", "session_banner", "effort_budget",
    "precondition_section_gate", "precondition_origins", "observable_surface",
    "scope_guard", "spec_validation", "bash_gate", "e2e_scope", "claude_md",
    "protected_paths", "always_allowed", "home_assistant", "ios_swiftui",
    "bug_fix", "e2e_tests", "output_specs",
})

# Namen, die auch eine App-Config plausibel verwendet — allein qualifizieren
# sie eine Datei NICHT als Plugin-Config (#372).
GENERIC_CONFIG_KEYS = frozenset({"project", "agents", "deploy", "modules", "hooks"})

# Obergrenze fuer die Plugin-Erkennung: groessere Dateien nur per Regex auf
# den ersten 256 KB, ohne YAML-Parse (#372).
_MAX_PROBE_BYTES = 256 * 1024

_TOP_LEVEL_KEY_RE = re.compile(r"^[\"']?([A-Za-z_][\w-]*)[\"']?\s*:", re.MULTILINE)


def is_plugin_config(path: Path) -> bool:
    """True, wenn `path` mindestens einen Plugin-Block auf oberster Ebene hat.

    Schluessel kommen aus PyYAML (deckt auch Flow-/JSON-Stil ab); ist YAML
    kaputt oder PyYAML fehlt, greift ein Regex auf Spalte-0-Schluessel.
    Wirft nie — unlesbar heisst False.
    """
    try:
        p = Path(path)
        if not p.is_file():  # FIFO/Geraet/Ordner: nicht lesen, sonst haengt der Hook
            return False
        with open(p, "r", errors="ignore") as fh:
            text = fh.read(_MAX_PROBE_BYTES + 1)
    except Exception:
        return False
    keys: "set[str] | None" = None
    if len(text) > _MAX_PROBE_BYTES:
        text = text[:_MAX_PROBE_BYTES]  # grosse Datei: kein YAML-Parse, nur Regex
    elif yaml is not None:
        try:
            data = yaml.safe_load(text)
            if isinstance(data, dict):
                keys = {str(k) for k in data}
        except Exception:
            keys = None
    if keys is None:
        keys = set(_TOP_LEVEL_KEY_RE.findall(text))
    return bool(keys & PLUGIN_CONFIG_KEYS)


def _is_root_app_config(root: Path, candidate: Path) -> bool:
    """True fuer eine `config.yaml` direkt im Root ohne Plugin-Block (#372)."""
    return candidate == root / "config.yaml" and not is_plugin_config(candidate)


# Local override file (should be in .gitignore)
LOCAL_OVERRIDE_NAMES = ["settings.local.json", ".settings.local.json"]


@lru_cache(maxsize=1)
def find_project_root() -> Path:
    """Find project root by looking for config file or .git directory.

    Worktree-transparent: if inside a git worktree (.git is a file, not a
    directory), resolves to the main repo root so that workflow state files
    are always written to the same location regardless of worktree context.
    """
    # CLAUDE_PROJECT_DIR hat höchste Priorität (gesetzt von Claude Code im Plugin-Modus)
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        p = Path(env_dir)
        main = find_main_repo_from_worktree(p)
        return main if main is not None else p

    current = Path.cwd()

    # Worktree-Erkennung: .git ist eine Datei → Haupt-Repo ableiten
    main = find_main_repo_from_worktree(current)
    if main is not None:
        return main

    while current != current.parent:
        # Check for config files
        for config_name in CONFIG_NAMES:
            candidate = current / config_name
            if candidate.exists() and not _is_root_app_config(current, candidate):
                return current
            if (current / ".claude" / config_name).exists():
                return current

        # Check for .git directory (file = worktree, already handled above)
        if (current / ".git").is_dir():
            return current

        current = current.parent

    return Path.cwd()


def _find_config_file(root: Path) -> "Path | None":
    """Erste Config-Datei unter `root` gemaess CONFIG_NAMES, oder None.

    Bewusst NICHT gecacht: `config_source_note()` fragt damit einen zweiten
    Baum ab, waehrend `load_config()` seinen eigenen behaelt.
    Eine Root-`config.yaml` ohne Plugin-Block wird uebergangen (#372).
    """
    for config_name in CONFIG_NAMES:
        candidate = root / config_name
        if candidate.exists() and not _is_root_app_config(root, candidate):
            return candidate
        candidate = root / ".claude" / config_name
        if candidate.exists():
            return candidate
    return None


# Oeffentlicher Name fuer Werkzeuge ausserhalb der Hooks (scripts/ci_spec_gate.py).
find_config_file = _find_config_file


def _skipped_app_config(root: Path) -> "Path | None":
    """Root-`config.yaml`, die als App-Config uebergangen wurde, sonst None (#372)."""
    try:
        candidate = root / "config.yaml"
        if candidate.exists() and _is_root_app_config(root, candidate):
            return candidate
    except Exception:
        pass
    return None


def skipped_app_config_note(root: "Path | None" = None) -> str:
    """Hinweis auf eine uebergangene Root-`config.yaml`, sonst "" (#372).

    Nur, wenn die Datei sonst tatsaechlich gewirkt haette — gewinnt ohnehin
    `openspec.yaml` (Root oder `.claude/`), ist ihr Uebergehen belanglos.
    Wirft nie.
    """
    try:
        root = root if root is not None else find_project_root()
        skipped = _skipped_app_config(root)
        if skipped is None:
            return ""
        effective = _find_config_file(root)
        if effective in (root / "openspec.yaml", root / ".claude" / "openspec.yaml"):
            return ""
        return (
            f"{skipped} übergangen — keine Plugin-Schlüssel (App-Config?). "
            "Plugin-Einstellungen gehören in openspec.yaml"
        )
    except Exception:
        return ""


def config_source_note() -> str:
    """Woher die Gate-Grenzen stammen — und ob der Arbeitsbaum etwas anderes sagt.

    Die Config wird bewusst aus dem HAUPTREPO gelesen, auch in Worktree-Sitzungen
    (`find_project_root()` loest dorthin auf). Gemessen wird dagegen im Worktree
    (`edit_gate._measurement_root()`, Issue #96). Diese Trennung ist gewollt: waere
    die Config worktree-first, koennte eine Sitzung ihr eigenes `max_loc_delta` im
    eigenen Branch anheben und weiterarbeiten — ohne Merge, ohne Review. Genau das
    Muster, das die Sperrmeldung des Gates verbietet.

    Der Preis ist Verwirrung: ein Eintrag, den man im Worktree vornimmt, wirkt
    nicht, und die Sperre sah bisher aus wie ein eigener Tippfehler (Issue #153).
    Diese Notiz macht die Quelle sichtbar. Wirft nie — eine Diagnose darf kein
    Gate zum Absturz bringen.
    """
    try:
        main_root = find_project_root()
        effective = _find_config_file(main_root)
        parts = [f"Grenzen aus: {effective or '<eingebaute Voreinstellung>'}"]
        skipped_note = skipped_app_config_note(main_root)
        if skipped_note:
            parts.append(skipped_note)

        from hook_utils import find_worktree_root
        worktree = find_worktree_root()
        if worktree is not None and worktree != main_root:
            local = _find_config_file(worktree)
            if local is not None:
                local_text = local.read_text()
                effective_text = effective.read_text() if effective else None
                if local_text != effective_text:
                    parts.append(
                        f"{local} weicht davon ab und ist NICHT wirksam — die Config "
                        "wird absichtlich aus dem Hauptrepo gelesen, damit eine Sitzung "
                        "ihre eigene Grenze nicht ohne Merge anhebt. Wirksam nach dem "
                        "Merge, vorher: 'override' oder loc_limit_override"
                    )
        return " | ".join(parts)
    except Exception:
        return ""


@lru_cache(maxsize=1)
def load_config() -> dict:
    """
    Load configuration from project root.

    Load order (later overrides earlier):
    1. Default config (built-in)
    2. openspec.yaml / config.yaml (project config)
    3. settings.local.json (local overrides, NOT in git)
    """
    root = find_project_root()
    config_path = _find_config_file(root)

    # Start with defaults
    config = get_default_config()

    # Merge main config if found
    if config_path and yaml is not None:
        try:
            with open(config_path, 'r') as f:
                file_config = yaml.safe_load(f) or {}
            config = deep_merge(config, file_config)
        except Exception as e:
            print(f"WARNING: Failed to load config {config_path}: {e}", file=sys.stderr)

    # Load local overrides (settings.local.json)
    local_config = load_local_overrides(root)
    if local_config:
        config = deep_merge(config, local_config)

    return config


def load_local_overrides(root: Path) -> dict | None:
    """
    Load local override settings.

    These are for:
    - API keys and credentials
    - Local paths
    - Developer-specific preferences

    Should be in .gitignore!
    """
    for override_name in LOCAL_OVERRIDE_NAMES:
        # Check in .claude/
        candidate = root / ".claude" / override_name
        if candidate.exists():
            try:
                with open(candidate, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, Exception):
                pass

        # Check in root
        candidate = root / override_name
        if candidate.exists():
            try:
                with open(candidate, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, Exception):
                pass

    return None


def get_default_config() -> dict:
    """Return default configuration."""
    return {
        "project": {
            "name": "Unnamed Project",
            "base_path": str(find_project_root()),
        },
        "workflow": {
            "phases": [
                "idle",
                "analyse_done",
                "spec_written",
                "spec_approved",
                "implemented",
                "validated"
            ],
            "approval_phrases": [
                "approved", "freigabe", "spec ok", "lgtm", "looks good"
            ],
        },
        "protected_paths": [],
        "always_allowed": [
            r"\.claude/",
            r"docs/",
            r"\.md$",
            r"\.gitignore",
        ],
        "specs": {
            "base_path": "docs/specs",
            "template_file": "docs/specs/_template.md",
            "categories": {},
        },
        "claude_md": {
            "max_lines": 600,
            "forbidden_patterns": [],
        },
        "modules": {
            "core": {
                "workflow_gate": True,
                "spec_enforcement": True,
                "claude_md_protection": True,
                "notification": True,
            },
            "generic": {
                "bug_fix_blocker": False,
                "test_before_commit": False,
                "scope_drift_guard": False,
            },
        },
        "hooks": {
            "timeout": 5,
        },
    }


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_project_root() -> Path:
    """Get the project root path."""
    config = load_config()
    return Path(config["project"].get("base_path", find_project_root()))


def get_workflow_phases() -> list:
    """Get configured workflow phases."""
    return load_config()["workflow"]["phases"]


def get_approval_phrases() -> list:
    """Get phrases that trigger spec approval."""
    return load_config()["workflow"]["approval_phrases"]


def get_protected_paths() -> list:
    """Get protected path patterns."""
    return load_config().get("protected_paths", [])


def get_always_allowed() -> list:
    """Get always-allowed path patterns."""
    return load_config().get("always_allowed", [])


def get_specs_config() -> dict:
    """Get specs configuration."""
    return load_config().get("specs", {})


def is_module_enabled(category: str, module: str) -> bool:
    """Check if a module is enabled."""
    modules = load_config().get("modules", {})
    return modules.get(category, {}).get(module, False)


def get_state_file_path() -> Path:
    """Get path to workflow state file."""
    return get_project_root() / ".claude" / "workflow_state.json"


def get_ac_format_required_since() -> "str | None":
    """Return ac_format_required_since date string from config, or None."""
    return load_config().get("spec_validation", {}).get("ac_format_required_since")


# Workflow documents the framework itself writes (/10-context, /30-write-spec,
# po-briefer). A framework convention, not a project decision — so they never
# count as production code, without any project config (Issue #294).
DEFAULT_LOC_EXCLUDE_PATTERNS = [
    r"^docs/(specs|context|briefings)/",
]


def with_default_loc_excludes(patterns: list, scope: "dict | None" = None) -> list:
    """Prepend DEFAULT_LOC_EXCLUDE_PATTERNS to project patterns (Issue #294).

    Additive: a project's own `loc_exclude_patterns` never drops the defaults.
    Opt-out only via `scope_guard.exclude_framework_docs: false`.
    """
    if isinstance(scope, dict) and scope.get("exclude_framework_docs") is False:
        return list(patterns)
    return DEFAULT_LOC_EXCLUDE_PATTERNS + [p for p in patterns
                                           if p not in DEFAULT_LOC_EXCLUDE_PATTERNS]


def get_scope_loc_config() -> tuple[int, list]:
    """Return (max_loc_delta, loc_exclude_patterns) from config.

    Defaults: (250, DEFAULT_LOC_EXCLUDE_PATTERNS) when scope_guard section is
    absent. Project patterns are added to the defaults, not replacing them.
    """
    cfg = load_config()
    scope = cfg.get("scope_guard", {})
    max_loc = int(scope.get("max_loc_delta", 250))
    excludes = with_default_loc_excludes(list(scope.get("loc_exclude_patterns", [])), scope)
    return max_loc, excludes


def get_effort_budget(workflow_type: str) -> "dict | None":
    """Return the effort budget of a stage (Issue #250, Teil B) or None.

    None when the block is absent or `enabled` is explicitly false. Unknown
    types (legacy `bug`, `express`) fall back to the values of `feature`.
    """
    block = load_config().get("effort_budget")
    if not isinstance(block, dict) or block.get("enabled") is False:
        return None
    stage = block.get(workflow_type)
    if not isinstance(stage, dict):
        stage = block.get("feature")
    return dict(stage) if isinstance(stage, dict) else None


# Built-in test path conventions (regex, matched via re.search on the path)
DEFAULT_TEST_PATH_PATTERNS = [
    r"(^|/)tests?/",
    r"(^|/)test_[^/]*\.py$",
    r"[^/]*_test\.py$",
    r"(^|/)__tests__/",
    r"[^/]*\.test\.[jt]sx?$",
    r"[^/]*\.spec\.[jt]sx?$",
    r"[^/]*_test\.go$",  # #335: Go-Tests liegen neben dem Code
]


def get_scope_test_loc_config() -> tuple[int, list]:
    """Return (max_test_loc_delta, test_path_patterns) from config.

    Defaults: (500, DEFAULT_TEST_PATH_PATTERNS) when the keys are absent —
    no project config change required (Issue #94, AC-6).
    """
    cfg = load_config()
    scope = cfg.get("scope_guard", {})
    max_test_loc = int(scope.get("max_test_loc_delta", 500))
    patterns = list(scope.get("test_path_patterns", DEFAULT_TEST_PATH_PATTERNS))
    return max_test_loc, patterns


if __name__ == "__main__":
    # Test: Print loaded config
    import json
    config = load_config()
    print(json.dumps(config, indent=2, default=str))
