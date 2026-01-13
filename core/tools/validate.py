#!/usr/bin/env python3
"""
OpenSpec Framework - Pre-Test Validation Tool

Claude MUST run this before asking the user to test!

Usage:
    python3 .claude/tools/validate.py          # Run all checks
    python3 .claude/tools/validate.py --quick  # Quick syntax check only
    python3 .claude/tools/validate.py --clear  # Clear after successful test
    python3 .claude/tools/validate.py --status # Show current status

Checks:
1. Syntax check on all changed files
2. Import check on changed modules (Python)
3. Optional: Server startup check

Configuration (in config.yaml):
  validation:
    checks:
      - syntax
      - imports
      - server_startup  # optional
    source_dir: "src"
    import_command: "python3 -c"  # or "uv run python -c"
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def find_project_root() -> Path:
    """Find project root by looking for .git."""
    current = Path(__file__).parent
    while current != current.parent:
        if (current / ".git").exists():
            return current
        if (current / ".claude").exists():
            return current
        current = current.parent
    return Path.cwd()


PROJECT_ROOT = find_project_root()
STATE_FILE = PROJECT_ROOT / ".claude" / "validation_state.json"


def load_state() -> dict:
    """Load validation state."""
    if not STATE_FILE.exists():
        return {"files_changed": [], "last_validation": None}
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return {"files_changed": [], "last_validation": None}


def save_state(state: dict):
    """Save validation state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def check_syntax(file_path: Path) -> tuple[bool, str]:
    """Check Python syntax."""
    if not file_path.suffix == ".py":
        return True, "Skipped (not Python)"

    result = subprocess.run(
        ["python3", "-m", "py_compile", str(file_path)],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT
    )
    if result.returncode != 0:
        return False, result.stderr.strip()
    return True, "OK"


def check_import(module_path: str, source_dir: str = "src") -> tuple[bool, str]:
    """Check if module can be imported."""
    if not module_path.endswith(".py"):
        return True, "Skipped (not Python)"

    # Convert file path to module path
    module = module_path.replace("/", ".").replace(".py", "")

    # Try import
    result = subprocess.run(
        ["python3", "-c", f"import {module}"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT / source_dir if (PROJECT_ROOT / source_dir).exists() else PROJECT_ROOT,
        timeout=10
    )
    if result.returncode != 0:
        error = result.stderr[:200] if result.stderr else "Import failed"
        return False, error
    return True, "OK"


def run_validation(quick: bool = False, source_dir: str = "src") -> bool:
    """Run all validation checks."""
    state = load_state()
    files_changed = state.get("files_changed", [])

    if not files_changed:
        print("No changes to validate")
        return True

    print(f"Validating {len(files_changed)} changed file(s):\n")

    all_ok = True

    for rel_path in files_changed:
        print(f"  {rel_path}")

        # Find full path
        full_path = PROJECT_ROOT / source_dir / rel_path
        if not full_path.exists():
            full_path = PROJECT_ROOT / rel_path
        if not full_path.exists():
            print(f"    Warning: File not found")
            continue

        # Syntax check
        ok, msg = check_syntax(full_path)
        if ok:
            print(f"    Syntax: OK")
        else:
            print(f"    Syntax ERROR: {msg}")
            all_ok = False
            continue

        # Import check (unless quick mode)
        if not quick and full_path.suffix == ".py":
            ok, msg = check_import(rel_path, source_dir)
            if ok:
                print(f"    Import: OK")
            else:
                print(f"    Import ERROR: {msg}")
                all_ok = False

    print()

    if all_ok:
        print("=" * 50)
        print("VALIDATION SUCCESSFUL")
        print("  You may now ask the user to test.")
        print("=" * 50)

        # Record successful validation
        state["last_validation"] = datetime.now().isoformat()
        state["validated_files"] = files_changed.copy()
        save_state(state)
    else:
        print("=" * 50)
        print("VALIDATION FAILED")
        print("  Fix errors before asking user to test!")
        print("=" * 50)

    return all_ok


def clear_state():
    """Clear changed files after successful user test."""
    state = load_state()
    state["files_changed"] = []
    state["last_validation"] = datetime.now().isoformat()
    save_state(state)
    print("Validation state cleared")


def show_status():
    """Show current validation status."""
    state = load_state()
    files = state.get("files_changed", [])
    last_val = state.get("last_validation", "never")

    print(f"Changed files: {len(files)}")
    for f in files:
        print(f"  - {f}")
    print(f"Last validation: {last_val}")


def main():
    parser = argparse.ArgumentParser(description="Pre-Test Validation Tool")
    parser.add_argument("--quick", action="store_true", help="Quick syntax check only")
    parser.add_argument("--clear", action="store_true", help="Clear state after successful test")
    parser.add_argument("--status", action="store_true", help="Show current status")
    parser.add_argument("--source-dir", default="src", help="Source directory (default: src)")
    args = parser.parse_args()

    if args.clear:
        clear_state()
        return

    if args.status:
        show_status()
        return

    success = run_validation(quick=args.quick, source_dir=args.source_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
