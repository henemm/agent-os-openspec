#!/usr/bin/env python3
"""
OpenSpec Framework - Output Format Validator

Validates output artifacts (emails, HTML, JSON, etc.) against spec requirements.
Must be run before declaring E2E tests as passed.

Usage:
    python3 core/tools/output_validator.py --spec email_v1     # Validate against spec
    python3 core/tools/output_validator.py --spec html_report  # Different spec
    python3 core/tools/output_validator.py --file /path/to/output.html
    python3 core/tools/output_validator.py --list-specs        # Show available specs

Configuration (in config.yaml):
  output_specs:
    email_v1:
      description: "Standard email format"
      type: "html"
      fetch_method: "imap"  # or "file", "http"
      validations:
        - type: "structure"
          rules:
            - pattern: "<table.*?</table>"
              count: 2
              message: "Must have exactly 2 tables"
        - type: "required_sections"
          sections:
            - "Summary"
            - "Details"
            - "Recommendation"
        - type: "format"
          rules:
            - field: "score"
              pattern: "\\d+/100"
              message: "Score must be N/100 format"

Exit Codes:
    0 = All validations passed
    1 = Validation failed
    2 = Technical error
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def find_project_root() -> Path:
    """Find project root by looking for .git or .claude."""
    current = Path(__file__).parent
    while current != current.parent:
        if (current / ".git").exists():
            return current
        if (current / ".claude").exists():
            return current
        current = current.parent
    return Path.cwd()


PROJECT_ROOT = find_project_root()


def load_config() -> dict:
    """Load project configuration."""
    config_paths = [
        PROJECT_ROOT / "config.yaml",
        PROJECT_ROOT / ".claude" / "config.yaml",
        PROJECT_ROOT / "openspec.yaml",
    ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                import yaml
                with open(config_path) as f:
                    return yaml.safe_load(f) or {}
            except ImportError:
                # Fallback to basic parsing if yaml not available
                pass

    return {}


def get_output_specs() -> dict:
    """Get output spec configurations."""
    config = load_config()
    return config.get("output_specs", {})


def fetch_content_file(file_path: str) -> str:
    """Fetch content from a local file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    return path.read_text()


def fetch_content_imap(imap_config: dict) -> str:
    """Fetch latest email content via IMAP."""
    import imaplib
    import email as email_lib

    host = imap_config.get("host", "imap.gmail.com")
    user = imap_config.get("user")
    password = imap_config.get("password")
    folder = imap_config.get("folder", "INBOX")

    if not user or not password:
        # Try to load from environment or settings
        import os
        user = user or os.environ.get("IMAP_USER")
        password = password or os.environ.get("IMAP_PASSWORD")

    if not user or not password:
        raise ValueError("IMAP credentials not configured")

    imap = imaplib.IMAP4_SSL(host)
    imap.login(user, password)
    imap.select(folder)

    _, data = imap.search(None, 'ALL')
    all_ids = data[0].split()
    if not all_ids:
        raise ValueError("No emails found")

    _, msg_data = imap.fetch(all_ids[-1], '(RFC822)')
    msg = email_lib.message_from_bytes(msg_data[0][1])

    body = ''
    for part in msg.walk():
        if part.get_content_type() == 'text/html':
            body = part.get_payload(decode=True).decode('utf-8')
            break

    imap.close()
    imap.logout()

    return body


def fetch_content_http(url: str) -> str:
    """Fetch content from HTTP endpoint."""
    import urllib.request
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.read().decode('utf-8')


def fetch_content(spec_config: dict, file_override: str = None) -> str:
    """Fetch content based on spec configuration."""
    if file_override:
        return fetch_content_file(file_override)

    method = spec_config.get("fetch_method", "file")

    if method == "imap":
        return fetch_content_imap(spec_config.get("imap", {}))
    elif method == "http":
        return fetch_content_http(spec_config.get("url", ""))
    elif method == "file":
        return fetch_content_file(spec_config.get("file_path", ""))
    else:
        raise ValueError(f"Unknown fetch method: {method}")


def validate_structure(content: str, rules: list) -> list[str]:
    """Validate content structure against rules."""
    errors = []

    for rule in rules:
        pattern = rule.get("pattern", "")
        expected_count = rule.get("count")
        min_count = rule.get("min", 0)
        max_count = rule.get("max", float('inf'))
        message = rule.get("message", f"Pattern validation failed: {pattern}")

        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
        actual_count = len(matches)

        if expected_count is not None and actual_count != expected_count:
            errors.append(f"STRUCTURE: {message} (found {actual_count}, expected {expected_count})")
        elif actual_count < min_count:
            errors.append(f"STRUCTURE: {message} (found {actual_count}, min {min_count})")
        elif actual_count > max_count:
            errors.append(f"STRUCTURE: {message} (found {actual_count}, max {max_count})")

    return errors


def validate_required_sections(content: str, sections: list) -> list[str]:
    """Validate that required sections are present."""
    errors = []

    for section in sections:
        if isinstance(section, dict):
            keywords = section.get("keywords", [])
            name = section.get("name", str(keywords))
        else:
            keywords = [section]
            name = section

        found = any(kw.lower() in content.lower() for kw in keywords)
        if not found:
            errors.append(f"SECTION: Required section '{name}' not found")

    return errors


def validate_format(content: str, rules: list) -> list[str]:
    """Validate specific field formats."""
    errors = []

    for rule in rules:
        field = rule.get("field", "")
        pattern = rule.get("pattern", "")
        message = rule.get("message", f"Format validation failed for {field}")
        required = rule.get("required", True)

        # Try to find the field value
        field_pattern = rf'{field}[:\s]*([^<\n]+)'
        match = re.search(field_pattern, content, re.IGNORECASE)

        if match:
            value = match.group(1).strip()
            if pattern and not re.match(pattern, value):
                errors.append(f"FORMAT: {message} (value: '{value}')")
        elif required:
            errors.append(f"FORMAT: Required field '{field}' not found")

    return errors


def validate_plausibility(content: str, rules: list) -> list[str]:
    """Validate data plausibility (cross-checks, ranges, etc.)."""
    errors = []

    for rule in rules:
        rule_type = rule.get("type", "")

        if rule_type == "range":
            field = rule.get("field", "")
            min_val = rule.get("min")
            max_val = rule.get("max")

            # Extract numeric values for field
            pattern = rf'{field}[:\s]*(\d+)'
            matches = re.findall(pattern, content, re.IGNORECASE)

            for match in matches:
                value = int(match)
                if min_val is not None and value < min_val:
                    errors.append(f"PLAUSIBILITY: {field} value {value} below minimum {min_val}")
                if max_val is not None and value > max_val:
                    errors.append(f"PLAUSIBILITY: {field} value {value} above maximum {max_val}")

        elif rule_type == "consistency":
            field1 = rule.get("field1", "")
            field2 = rule.get("field2", "")
            relation = rule.get("relation", "")
            message = rule.get("message", f"Consistency check failed: {field1} vs {field2}")

            # This is placeholder - real implementation would extract and compare values
            # Specific projects can implement custom validators

    return errors


def run_validation(spec_name: str, file_override: str = None) -> tuple[bool, list[str]]:
    """Run all validations for a spec."""
    specs = get_output_specs()

    if spec_name not in specs:
        return False, [f"Unknown spec: {spec_name}. Available: {list(specs.keys())}"]

    spec_config = specs[spec_name]

    try:
        content = fetch_content(spec_config, file_override)
    except Exception as e:
        return False, [f"ERROR: Failed to fetch content: {e}"]

    all_errors = []

    # Run configured validations
    for validation in spec_config.get("validations", []):
        val_type = validation.get("type", "")

        if val_type == "structure":
            all_errors.extend(validate_structure(content, validation.get("rules", [])))
        elif val_type == "required_sections":
            all_errors.extend(validate_required_sections(content, validation.get("sections", [])))
        elif val_type == "format":
            all_errors.extend(validate_format(content, validation.get("rules", [])))
        elif val_type == "plausibility":
            all_errors.extend(validate_plausibility(content, validation.get("rules", [])))

    return len(all_errors) == 0, all_errors


def list_specs():
    """List available output specs."""
    specs = get_output_specs()

    if not specs:
        print("No output specs configured.")
        print("\nAdd specs to config.yaml under 'output_specs'")
        return

    print("Available Output Specs:")
    print("=" * 50)

    for name, config in specs.items():
        description = config.get("description", "No description")
        output_type = config.get("type", "unknown")
        fetch_method = config.get("fetch_method", "file")
        print(f"\n  {name}")
        print(f"    Description: {description}")
        print(f"    Type: {output_type}")
        print(f"    Fetch: {fetch_method}")


def main():
    parser = argparse.ArgumentParser(description="Output Format Validator")
    parser.add_argument("--spec", help="Spec name to validate against")
    parser.add_argument("--file", help="Override: validate this file instead of fetching")
    parser.add_argument("--list-specs", action="store_true", help="List available specs")
    args = parser.parse_args()

    if args.list_specs:
        list_specs()
        return

    if not args.spec:
        print("Error: --spec required (or use --list-specs)")
        sys.exit(2)

    print("=" * 70)
    print(f"OUTPUT VALIDATOR - Spec: {args.spec}")
    print("=" * 70)
    print()

    success, errors = run_validation(args.spec, args.file)

    if success:
        print("VALIDATION SUCCESSFUL")
        print()
        print("  All spec requirements met.")
        print("  You may now declare the E2E test as passed.")
        sys.exit(0)
    else:
        print("VALIDATION FAILED")
        print()
        for error in errors:
            print(f"  - {error}")
        print()
        print("=" * 70)
        print("DO NOT declare E2E test as passed!")
        print("Fix the errors and run validation again.")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()
