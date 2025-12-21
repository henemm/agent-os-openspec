#!/usr/bin/env python3
"""
OpenSpec Framework - Spec Enforcement Hook

Enforces Spec-First development:
1. Every entity/component needs a spec before implementation
2. Specs must be complete (no [TODO] placeholders)
3. Specs must be approved (checkbox checked)

Exit Codes:
- 0: Allowed
- 2: Blocked (stderr shown to Claude)
"""

import json
import os
import sys
import re
from pathlib import Path

try:
    from config_loader import (
        load_config, get_project_root, get_specs_config, get_protected_paths
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from config_loader import (
        load_config, get_project_root, get_specs_config, get_protected_paths
    )


def get_spec_type_for_path(file_path: str) -> str | None:
    """Determine spec type based on file path."""
    protected = get_protected_paths()

    for item in protected:
        if isinstance(item, dict):
            pattern = item.get("pattern", "")
            spec_type = item.get("spec_type", "")
            if pattern and re.search(pattern, file_path):
                return spec_type

    return None


def extract_entities(content: str, spec_type: str) -> list[str]:
    """Extract entity names from content based on spec type."""
    specs_config = get_specs_config()
    categories = specs_config.get("categories", {})

    if spec_type not in categories:
        return []

    pattern = categories[spec_type].get("pattern", "")
    if not pattern:
        return []

    matches = re.findall(pattern, content, re.MULTILINE)
    return [normalize_entity_id(m) for m in matches if m]


def normalize_entity_id(name: str) -> str:
    """Convert entity name to entity ID (lowercase, underscores)."""
    entity_id = name.lower().strip()
    entity_id = re.sub(r'[^a-z0-9_]', '_', entity_id)
    entity_id = re.sub(r'_+', '_', entity_id)
    entity_id = entity_id.strip('_')
    return entity_id


def find_spec_file(entity_id: str, spec_type: str) -> Path | None:
    """Search for spec file in specs directory."""
    specs_config = get_specs_config()
    base_path = get_project_root() / specs_config.get("base_path", "docs/specs")

    categories = specs_config.get("categories", {})
    category_path = categories.get(spec_type, {}).get("path", spec_type)

    spec_dir = base_path / category_path
    target_file = f"{entity_id}.md"

    # Direct path
    direct_path = spec_dir / target_file
    if direct_path.exists():
        return direct_path

    # Search in subdirectories
    if spec_dir.exists():
        for path in spec_dir.rglob("*.md"):
            if path.name.lower() == target_file.lower():
                return path

    # Search in grouped specs (entity mentioned in content)
    if spec_dir.exists():
        for path in spec_dir.rglob("*.md"):
            try:
                content = path.read_text()
                if entity_id in content.lower():
                    return path
            except Exception:
                pass

    return None


def check_spec_complete(spec_path: Path) -> tuple[bool, str]:
    """Check if spec is complete (no TODO placeholders)."""
    try:
        content = spec_path.read_text()

        # Critical TODO patterns
        todo_patterns = [
            "[TODO:",
            "[TODO]",
            "TODO:",
        ]

        for pattern in todo_patterns:
            if pattern in content:
                return False, f"Spec contains '{pattern}' placeholder"

        return True, ""
    except Exception as e:
        return False, f"Error reading spec: {e}"


def check_spec_approved(spec_path: Path) -> tuple[bool, str]:
    """Check if spec is approved (checkbox checked)."""
    try:
        content = spec_path.read_text()

        # Look for unchecked approval checkbox
        not_approved_pattern = r'-\s*\[\s*\]\s*Approved'
        if re.search(not_approved_pattern, content, re.IGNORECASE):
            return False, "Spec approval checkbox is not checked"

        return True, ""
    except Exception as e:
        return False, f"Error reading spec: {e}"


def load_legacy_entities() -> set:
    """Load list of legacy entities that don't need specs."""
    legacy_file = get_project_root() / ".claude" / "hooks" / "legacy_entities.txt"

    if not legacy_file.exists():
        return set()

    try:
        content = legacy_file.read_text()
        return set(
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.startswith('#')
        )
    except Exception:
        return set()


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = data.get('tool_input', {})
    file_path = tool_input.get('file_path', '')
    content = tool_input.get('content', '') or tool_input.get('new_string', '')

    if not file_path or not content:
        sys.exit(0)

    # Determine spec type for this file
    spec_type = get_spec_type_for_path(file_path)
    if not spec_type:
        sys.exit(0)  # Not a protected path

    # Extract entities from content
    entities = extract_entities(content, spec_type)
    if not entities:
        sys.exit(0)  # No entities found

    # Load legacy entities
    legacy_entities = load_legacy_entities()

    # Check each entity
    missing_specs = []
    incomplete_specs = []
    not_approved = []

    for entity_id in set(entities):
        # Skip legacy entities
        if entity_id in legacy_entities:
            continue

        spec_path = find_spec_file(entity_id, spec_type)

        if not spec_path:
            missing_specs.append(entity_id)
            continue

        # Check completeness
        complete, msg = check_spec_complete(spec_path)
        if not complete:
            incomplete_specs.append((entity_id, msg))
            continue

        # Check approval
        approved, msg = check_spec_approved(spec_path)
        if not approved:
            not_approved.append((entity_id, msg))

    # Report errors
    errors = []

    if missing_specs:
        errors.append("MISSING SPECS:")
        for entity in missing_specs[:5]:
            errors.append(f"  - {entity}")
        if len(missing_specs) > 5:
            errors.append(f"  ... and {len(missing_specs) - 5} more")
        errors.append("")
        errors.append("Create specs first! Template: docs/specs/_template.md")

    if incomplete_specs:
        errors.append("INCOMPLETE SPECS (contain [TODO]):")
        for entity, msg in incomplete_specs[:3]:
            errors.append(f"  - {entity}: {msg}")
        errors.append("")
        errors.append("Complete the specs before implementing!")

    if not_approved:
        errors.append("SPECS NOT APPROVED:")
        for entity, msg in not_approved[:3]:
            errors.append(f"  - {entity}: {msg}")
        errors.append("")
        errors.append("User must approve specs: set '- [x] Approved'")

    if errors:
        print("=" * 60, file=sys.stderr)
        print("BLOCKED - Spec requirements not met!", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
