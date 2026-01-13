#!/usr/bin/env python3
"""
OpenSpec Framework - Domain Pattern Guard

Enforces Single Source of Truth architectural patterns.
Blocks code that violates domain-specific constraints.

Use Cases:
- Weather calculations must use WeatherService
- Payment processing must use PaymentGateway
- Auth logic must use AuthService
- Logging must use Logger, not console

Configuration (in config.yaml):
  domain_guards:
    weather_service:
      description: "Weather calculations must use WeatherMetricsService"
      source_of_truth: "src/services/weather_metrics.py"
      allowed_files:
        - "weather_metrics.py"
        - "test_weather_*.py"
      violations:
        - pattern: "cloud_pct\\s*[<>=]"
          message: "Direct cloud percentage comparison"
          fix: "Use WeatherMetricsService.calculate_sunny_hours()"
        - pattern: "def\\s+calculate_sunny_hours"
          message: "Local sunny hours function"
          fix: "Use WeatherMetricsService.calculate_sunny_hours()"

Exit Codes:
- 0: Allowed
- 2: Blocked (violation detected)
"""

import json
import os
import re
import sys
from pathlib import Path

# Try to import config loader
try:
    from config_loader import load_config, get_project_root
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from config_loader import load_config, get_project_root
    except ImportError:
        def load_config():
            return {}
        def get_project_root():
            return Path.cwd()


def get_domain_guards() -> dict:
    """Get domain guard configurations."""
    config = load_config()
    return config.get("domain_guards", {})


def is_allowed_file(file_path: str, guard_config: dict) -> bool:
    """Check if file is allowed to contain the pattern."""
    file_name = Path(file_path).name
    allowed_files = guard_config.get("allowed_files", [])

    for allowed in allowed_files:
        # Support glob-like patterns
        if "*" in allowed:
            pattern = allowed.replace("*", ".*")
            if re.match(pattern, file_name):
                return True
        elif allowed == file_name:
            return True

    return False


def check_for_violations(content: str, guard_config: dict) -> list[tuple[str, str]]:
    """
    Check content for pattern violations.

    Returns list of (message, fix) tuples.
    """
    violations = []
    violation_patterns = guard_config.get("violations", [])

    for line in content.split("\n"):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue

        for v in violation_patterns:
            pattern = v.get("pattern", "")
            message = v.get("message", "Pattern violation")
            fix = v.get("fix", "See documentation")

            if pattern and re.search(pattern, line, re.IGNORECASE):
                violations.append((message, fix))
                break  # One violation per line

    return violations


def main():
    # Get tool input
    tool_input_str = os.environ.get("CLAUDE_TOOL_INPUT", "")

    if not tool_input_str:
        try:
            data = json.load(sys.stdin)
            tool_input_str = json.dumps(data.get("tool_input", {}))
            tool_name = data.get("tool_name", "")
        except (json.JSONDecodeError, Exception):
            sys.exit(0)
    else:
        tool_name = os.environ.get("CLAUDE_TOOL_NAME", "")

    try:
        tool_input = json.loads(tool_input_str) if isinstance(tool_input_str, str) else tool_input_str
    except json.JSONDecodeError:
        sys.exit(0)

    # Only check Edit and Write
    if tool_name not in ("Edit", "Write", ""):
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    # Get content being written
    content = tool_input.get("content", "") or tool_input.get("new_string", "")
    if not content:
        sys.exit(0)

    # Get domain guards
    guards = get_domain_guards()
    if not guards:
        sys.exit(0)

    # Check each guard
    all_violations = []

    for guard_name, guard_config in guards.items():
        # Skip if file is allowed for this guard
        if is_allowed_file(file_path, guard_config):
            continue

        # Check for violations
        violations = check_for_violations(content, guard_config)

        if violations:
            all_violations.append((guard_name, guard_config, violations))

    if not all_violations:
        sys.exit(0)

    # Format error message
    print("=" * 70, file=sys.stderr)
    print("BLOCKED - Architecture Violation Detected!", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    for guard_name, guard_config, violations in all_violations:
        description = guard_config.get("description", guard_name)
        source = guard_config.get("source_of_truth", "See documentation")

        print(file=sys.stderr)
        print(f"Domain: {description}", file=sys.stderr)
        print(f"Source of Truth: {source}", file=sys.stderr)
        print(file=sys.stderr)
        print("VIOLATIONS:", file=sys.stderr)
        print("-" * 40, file=sys.stderr)

        # Deduplicate
        seen = set()
        for message, fix in violations:
            if message not in seen:
                seen.add(message)
                print(f"  - {message}", file=sys.stderr)
                print(f"    FIX: {fix}", file=sys.stderr)
                print(file=sys.stderr)

    print("=" * 70, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
