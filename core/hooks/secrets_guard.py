#!/usr/bin/env python3
"""
Secrets Guard — PreToolUse Bash + Read

Blockiert Zugriffe auf sensible Dateien (.env, Credentials, Private Keys).

Staging-Modus erlaubt .env-Zugriff während der Entwicklung:
  touch .claude/staging   oder   OPENSPEC_ENV=staging

Immer blockiert (auch im Staging): credentials.json, Service-Accounts, .pem/.key

Konfigurierbar via openspec.yaml:
  secrets_guard:
    enabled: true
    sensitive_patterns: [...]
    always_blocked: [...]

Exit-Codes: 0 = erlaubt, 2 = blockiert
"""

import json
import os
import re
import sys
from pathlib import Path


def _setup():
    hooks_dir = str(Path(__file__).parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)


_setup()

from hook_utils import find_project_root  # noqa: E402

try:
    from config_loader import load_config
except ImportError:
    def load_config():
        return {}

# Standardmuster für sensible Dateien
_DEFAULT_SENSITIVE = [
    r"\.env",
    r"credentials\.json",
    r"service[_-]?account.*\.json",
    r"private[_.]key",
    r"[_.]secret\.",
    r"\.pem$",
    r"\.key$",
]

# Immer blockiert — auch im Staging-Modus
_DEFAULT_ALWAYS_BLOCKED = [
    r"credentials\.json",
    r"service[_-]?account.*\.json",
    r"private[_.]key",
    r"[_.]secret\.",
    r"\.pem$",
    r"\.key$",
]

# Shell-Befehle die Dateiinhalt ausgeben (nicht grep -l)
_DANGEROUS_CMD_RE = re.compile(
    r"\b(cat|head|tail|less|more)\b"
    r"|sed\s+.*-n.*p"
    r"|awk\s+.*print"
    r"|grep\b(?!.*\s-l)"
)


def _get_config() -> dict:
    cfg = load_config().get("secrets_guard", {})
    return {
        "enabled": cfg.get("enabled", True),
        "sensitive_patterns": cfg.get("sensitive_patterns", _DEFAULT_SENSITIVE),
        "always_blocked": cfg.get("always_blocked", _DEFAULT_ALWAYS_BLOCKED),
    }


def _is_staging() -> bool:
    if (find_project_root() / ".claude" / "staging").exists():
        return True
    return os.environ.get("OPENSPEC_ENV", "").lower() in ("staging", "development", "dev")


def _matches(text: str, patterns: list) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _read_payload() -> tuple[str, dict]:
    """Gibt (tool_name, tool_input) zurück."""
    ti_env = os.environ.get("CLAUDE_TOOL_INPUT", "")
    tn_env = os.environ.get("CLAUDE_TOOL_NAME", "")
    if ti_env and tn_env:
        try:
            return tn_env, json.loads(ti_env)
        except json.JSONDecodeError:
            return tn_env, {}
    try:
        data = json.load(sys.stdin)
        return data.get("tool_name", ""), data.get("tool_input", {})
    except Exception:
        return "", {}


def main() -> None:
    cfg = _get_config()
    if not cfg["enabled"]:
        sys.exit(0)

    tool_name, tool_input = _read_payload()
    sensitive = cfg["sensitive_patterns"]
    always = cfg["always_blocked"]
    staging = _is_staging()

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if _matches(cmd, sensitive) and _DANGEROUS_CMD_RE.search(cmd):
            if _matches(cmd, always):
                print(
                    "BLOCKED [secrets_guard]: Befehl würde geschützte Credentials/Keys ausgeben.\n"
                    "  Diese Dateien sind immer geschützt (auch im Staging-Modus).\n"
                    "  Tipp: 'grep -l' zeigt Dateipfade ohne Inhalt.",
                    file=sys.stderr,
                )
                sys.exit(2)
            if not staging:
                print(
                    "BLOCKED [secrets_guard]: Befehl würde sensible Datei ausgeben.\n"
                    "  Für .env-Zugriff im Staging: touch .claude/staging\n"
                    "  Oder: export OPENSPEC_ENV=staging",
                    file=sys.stderr,
                )
                sys.exit(2)

    elif tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        if _matches(file_path, sensitive):
            if _matches(file_path, always):
                print(
                    f"BLOCKED [secrets_guard]: {Path(file_path).name} enthält Credentials/Keys.\n"
                    "  Diese Datei ist immer geschützt.",
                    file=sys.stderr,
                )
                sys.exit(2)
            if not staging:
                print(
                    f"BLOCKED [secrets_guard]: Sensible Datei: {Path(file_path).name}\n"
                    "  Für .env-Zugriff im Staging: touch .claude/staging",
                    file=sys.stderr,
                )
                sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
