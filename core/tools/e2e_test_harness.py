#!/usr/bin/env python3
"""
OpenSpec Framework - E2E Test Harness

Runs real browser-based E2E tests using Playwright.
Captures screenshots as test artifacts for TDD validation.

Usage:
    # Basic text check
    python3 core/tools/e2e_test_harness.py --url /page --check "Expected Text"

    # With action before check
    python3 core/tools/e2e_test_harness.py --url /form --action click:#submit --check "Success"

    # RED phase (expect text NOT to exist yet)
    python3 core/tools/e2e_test_harness.py --url /page --check "New Feature" --expect-fail

    # Custom viewport and timeout
    python3 core/tools/e2e_test_harness.py --url /page --check "Text" --width 1920 --height 1080 --timeout 30

Configuration (in config.yaml):
  e2e_tests:
    base_url: "http://localhost:8080"
    default_timeout: 10
    screenshot_dir: ".claude/artifacts/screenshots"
    headless: true
    browser: "chromium"  # chromium, firefox, webkit

Exit Codes:
    0 = Test passed (or expected failure in RED phase)
    1 = Test failed
    2 = Technical error (Playwright not installed, server not reachable, etc.)
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path


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
                pass

    return {}


def get_e2e_config() -> dict:
    """Get E2E test configuration with defaults."""
    config = load_config()
    e2e_config = config.get("e2e_tests", {})

    return {
        "base_url": e2e_config.get("base_url", "http://localhost:8080"),
        "default_timeout": e2e_config.get("default_timeout", 10),
        "screenshot_dir": e2e_config.get("screenshot_dir", ".claude/artifacts/screenshots"),
        "headless": e2e_config.get("headless", True),
        "browser": e2e_config.get("browser", "chromium"),
    }


def ensure_screenshot_dir() -> Path:
    """Ensure screenshot directory exists."""
    config = get_e2e_config()
    screenshot_dir = PROJECT_ROOT / config["screenshot_dir"]
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    return screenshot_dir


def parse_action(action_str: str) -> tuple[str, str]:
    """
    Parse action string.

    Formats:
        click:#selector
        type:#selector:text
        wait:seconds
        press:Enter
        scroll:down
    """
    parts = action_str.split(":", 2)
    action_type = parts[0]
    target = parts[1] if len(parts) > 1 else ""
    value = parts[2] if len(parts) > 2 else ""

    return action_type, target, value


def execute_action(page, action_str: str) -> bool:
    """Execute a single action on the page."""
    parts = action_str.split(":", 2)
    action_type = parts[0]
    target = parts[1] if len(parts) > 1 else ""
    value = parts[2] if len(parts) > 2 else ""

    try:
        if action_type == "click":
            page.locator(target).click(timeout=5000)
        elif action_type == "type":
            page.locator(target).fill(value)
        elif action_type == "wait":
            time.sleep(float(target))
        elif action_type == "press":
            page.keyboard.press(target)
        elif action_type == "scroll":
            if target == "down":
                page.evaluate("window.scrollBy(0, 500)")
            elif target == "up":
                page.evaluate("window.scrollBy(0, -500)")
            elif target == "bottom":
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            elif target == "top":
                page.evaluate("window.scrollTo(0, 0)")
        elif action_type == "hover":
            page.locator(target).hover()
        elif action_type == "select":
            page.locator(target).select_option(value)
        else:
            print(f"  Warning: Unknown action type '{action_type}'")
            return False

        time.sleep(0.5)  # Brief pause after action
        return True

    except Exception as e:
        print(f"  Action failed: {action_type}:{target} - {e}")
        return False


def run_browser_test(
    url: str,
    check_text: str,
    actions: list[str] = None,
    width: int = 1400,
    height: int = 1000,
    timeout: int = None,
    wait_after_load: float = 2.0,
) -> tuple[bool, str, str]:
    """
    Run browser-based E2E test.

    Returns:
        (success, message, screenshot_path)
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "Playwright not installed. Run: pip install playwright && playwright install", None

    config = get_e2e_config()
    base_url = config["base_url"]
    timeout = timeout or config["default_timeout"]
    headless = config["headless"]
    browser_type = config["browser"]

    # Build full URL
    if url.startswith("http"):
        full_url = url
    else:
        full_url = f"{base_url}{url}"

    # Generate screenshot path
    screenshot_dir = ensure_screenshot_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_url = url.replace("/", "_").replace("?", "_").strip("_")
    screenshot_path = str(screenshot_dir / f"e2e_{safe_url}_{timestamp}.png")

    try:
        with sync_playwright() as p:
            # Launch browser
            if browser_type == "firefox":
                browser = p.firefox.launch(headless=headless)
            elif browser_type == "webkit":
                browser = p.webkit.launch(headless=headless)
            else:
                browser = p.chromium.launch(headless=headless)

            page = browser.new_page(viewport={'width': width, 'height': height})

            # Navigate
            try:
                page.goto(full_url, timeout=timeout * 1000)
            except Exception as e:
                return False, f"Failed to load {full_url}: {e}", None

            # Wait for page load
            time.sleep(wait_after_load)

            # Execute actions
            if actions:
                for action in actions:
                    print(f"  Executing: {action}")
                    if not execute_action(page, action):
                        page.screenshot(path=screenshot_path, full_page=True)
                        browser.close()
                        return False, f"Action failed: {action}", screenshot_path

            # Take screenshot
            page.screenshot(path=screenshot_path, full_page=True)

            # Check for text
            content = page.content()
            found = check_text.lower() in content.lower()

            browser.close()

            if found:
                return True, f"Text '{check_text}' found on page", screenshot_path
            else:
                return False, f"Text '{check_text}' NOT found on page", screenshot_path

    except Exception as e:
        return False, f"Browser test error: {e}", None


def main():
    parser = argparse.ArgumentParser(
        description="E2E Test Harness (Playwright)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic check
  %(prog)s --url /login --check "Sign In"

  # With actions
  %(prog)s --url /form --action "type:#email:test@example.com" --action "click:#submit" --check "Success"

  # RED phase (expect failure)
  %(prog)s --url /dashboard --check "New Widget" --expect-fail

Actions format:
  click:#selector       - Click element
  type:#selector:text   - Type text into input
  wait:seconds          - Wait N seconds
  press:Enter           - Press keyboard key
  scroll:down/up/top/bottom - Scroll page
  hover:#selector       - Hover over element
  select:#selector:value - Select dropdown option
"""
    )

    parser.add_argument("--url", required=True, help="URL path to test (relative to base_url)")
    parser.add_argument("--check", required=True, help="Text that must be present on page")
    parser.add_argument("--action", action="append", help="Action to perform (can be repeated)")
    parser.add_argument("--expect-fail", action="store_true", help="RED phase: expect text NOT to exist")
    parser.add_argument("--width", type=int, default=1400, help="Viewport width")
    parser.add_argument("--height", type=int, default=1000, help="Viewport height")
    parser.add_argument("--timeout", type=int, help="Page load timeout in seconds")
    parser.add_argument("--wait", type=float, default=2.0, help="Wait after page load (seconds)")

    args = parser.parse_args()

    print("=" * 60)
    print("E2E TEST HARNESS")
    print("=" * 60)
    print(f"  URL: {args.url}")
    print(f"  Check: '{args.check}'")
    print(f"  Phase: {'RED (expect fail)' if args.expect_fail else 'GREEN (expect pass)'}")
    if args.action:
        print(f"  Actions: {len(args.action)}")
    print()

    success, message, screenshot = run_browser_test(
        url=args.url,
        check_text=args.check,
        actions=args.action or [],
        width=args.width,
        height=args.height,
        timeout=args.timeout,
        wait_after_load=args.wait,
    )

    print(f"Result: {message}")
    if screenshot:
        print(f"Screenshot: {screenshot}")
    print()

    # RED/GREEN logic
    if args.expect_fail:
        if not success:
            print("=" * 60)
            print("RED PHASE OK")
            print("  Feature does not exist yet (expected)")
            print("  Now implement the feature to make the test pass.")
            print("=" * 60)
            sys.exit(0)
        else:
            print("=" * 60)
            print("RED PHASE FAILED")
            print("  Feature already exists!")
            print("  Either the test is wrong or feature was already implemented.")
            print("=" * 60)
            sys.exit(1)
    else:
        if success:
            print("=" * 60)
            print("GREEN PHASE OK")
            print("  Feature works as expected!")
            print("=" * 60)
            sys.exit(0)
        else:
            print("=" * 60)
            print("GREEN PHASE FAILED")
            print("  Feature not working. Fix the implementation.")
            print("=" * 60)
            sys.exit(1)


if __name__ == "__main__":
    main()
