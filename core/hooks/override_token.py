#!/usr/bin/env python3
"""
Override Token — Shared Multi-Workflow Token Management

Supports multiple concurrent override tokens (one per workflow).
All hooks import from here instead of duplicating token logic.

Token file format (v2 — multi-workflow):
{
  "version": 2,
  "tokens": {
    "bug-114": {"created": "...", "granted_by": "user_prompt"},
    "feature-x": {"created": "...", "granted_by": "user_prompt"}
  }
}
"""

from hook_utils import setup_path, find_project_root
setup_path()

import json
from datetime import datetime, timedelta
from pathlib import Path

TOKEN_TTL_HOURS = 1


def _get_token_file() -> Path:
    return find_project_root() / ".claude" / "user_override_token.json"


def _load_tokens() -> dict[str, dict]:
    """Load all tokens, handling both v1 and v2 format."""
    if not _get_token_file().exists():
        return {}
    try:
        data = json.loads(_get_token_file().read_text())
    except (json.JSONDecodeError, OSError):
        return {}

    if data.get("version") == 2:
        return data.get("tokens", {})

    # v1 format — migrate on read
    workflow = data.get("workflow")
    if workflow:
        return {
            workflow: {
                "created": data.get("created", ""),
                "granted_by": data.get("granted_by", "unknown"),
            }
        }
    return {}


def _save_tokens(tokens: dict[str, dict]) -> None:
    token_file = _get_token_file()
    token_file.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 2, "tokens": tokens}
    with open(token_file, "w") as f:
        json.dump(data, f, indent=2)


def _is_expired(created_str: str) -> bool:
    if not created_str:
        return False
    try:
        created_dt = datetime.fromisoformat(created_str)
        return (datetime.now() - created_dt) > timedelta(hours=TOKEN_TTL_HOURS)
    except (ValueError, TypeError):
        return False


def has_valid_token(workflow_name: str = None) -> bool:
    """Check if a valid override token exists.

    Args:
        workflow_name: Check for a specific workflow. If None, checks if ANY
                       valid token exists.
    """
    tokens = _load_tokens()
    if not tokens:
        return False

    if workflow_name:
        entry = tokens.get(workflow_name)
        if not entry:
            return False
        return not _is_expired(entry.get("created", ""))

    return any(
        not _is_expired(entry.get("created", ""))
        for entry in tokens.values()
    )


def create_token(workflow_name: str) -> None:
    """Create or update an override token for a workflow."""
    tokens = _load_tokens()
    # Prune expired tokens
    tokens = {
        name: entry
        for name, entry in tokens.items()
        if not _is_expired(entry.get("created", ""))
    }
    tokens[workflow_name] = {
        "created": datetime.now().isoformat(),
        "granted_by": "user_prompt",
    }
    _save_tokens(tokens)


def remove_token(workflow_name: str) -> None:
    tokens = _load_tokens()
    if workflow_name in tokens:
        del tokens[workflow_name]
        _save_tokens(tokens)


def remove_all_tokens() -> None:
    token_file = _get_token_file()
    if token_file.exists():
        try:
            token_file.unlink()
        except OSError:
            pass
