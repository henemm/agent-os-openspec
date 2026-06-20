#!/usr/bin/env python3
"""
TDD Enforcement Hook — PreToolUse Edit|Write|MultiEdit

Validiert RED-Phase-Artefakte tiefgehend bevor Code-Edits in phase6+
erlaubt werden. Ergänzt edit_gate.py's einfache Boolean-Prüfung durch:

- Existenz der Artefakt-Datei auf Disk
- Mindestgröße (kein Platzhalter/leere Datei)
- Frische (<24h alt)
- Fehlerkeywords im Inhalt (echte Fehlermeldungen, nicht nur "failed")
- Keine Platzhalter-Patterns im Inhalt

Fail-safe: Bei Import-Fehlern oder Parse-Fehlern → exit(0), nie blockieren.
"""

import os
import re
import sys
import time
from pathlib import Path


def _setup():
    hooks_dir = str(Path(__file__).parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)


_setup()

from hook_utils import get_tool_input, find_project_root, block, allow, get_active_workflow_name  # noqa: E402

# Phasen in denen TDD-Enforcement gilt
TEST_REQUIRED_PHASES = {"phase6_implement", "phase6b_adversary"}

# Pfade die immer erlaubt sind (gespiegelt von edit_gate.py)
_ALWAYS_ALLOWED = re.compile(
    r"(\.claude[/\\]|[/\\]docs[/\\]|\.md$|\.gitignore|\.txt$|[/\\]specs[/\\]"
    r"|[/\\]\.claude[/\\])"
)

# Mindestgröße eines gültigen Artefakts in Bytes
_MIN_SIZE = 80

# Maximales Alter in Sekunden (24h)
_MAX_AGE_S = 86_400

# Keywords die echte Test-Fehler belegen
_FAILURE_RE = re.compile(
    r"\b(FAILED|ERROR|error|failed|FAIL|assert|AssertionError"
    r"|ImportError|ModuleNotFoundError|SyntaxError|TypeError"
    r"|AttributeError|NameError|NotImplementedError"
    r"|raise|Traceback|Exception|stderr)\b",
    re.MULTILINE,
)

# Platzhalter-Patterns die auf gefälschte Artefakte hinweisen
_PLACEHOLDER_RE = re.compile(
    r"(TODO|PLACEHOLDER|FIXME|<test_output>|<your output>"
    r"|insert output|copy output|example output)",
    re.IGNORECASE,
)


def _validate_artifact(art: dict, project_root: Path) -> "str | None":
    """Prüft ein einzelnes Artefakt. Gibt Fehlermeldung zurück oder None."""
    art_type = art.get("type", "")
    path_str = art.get("path", "")
    description = art.get("description", "").strip()

    if len(description) < 10:
        return f"Beschreibung zu kurz ({len(description)} Zeichen): '{description}'"

    if not path_str:
        return None  # Kein Dateipfad → kann nicht weiter prüfen

    artifact_path = (
        Path(path_str) if Path(path_str).is_absolute() else project_root / path_str
    )

    if not artifact_path.exists():
        return f"Artefakt-Datei nicht gefunden: {path_str}"

    size = artifact_path.stat().st_size
    if size < _MIN_SIZE:
        return f"Artefakt-Datei zu klein ({size} Bytes < {_MIN_SIZE}): {path_str}"

    age_s = time.time() - artifact_path.stat().st_mtime
    if age_s > _MAX_AGE_S:
        return (
            f"Artefakt-Datei zu alt ({age_s / 3600:.1f}h > 24h): {path_str}\n"
            f"  → Neue RED-Tests ausführen und frische Artefakte registrieren."
        )

    # Inhalt nur für test_output prüfen (nicht für Screenshots)
    if art_type == "test_output":
        try:
            content = artifact_path.read_text(errors="replace")
        except OSError:
            return f"Artefakt-Datei nicht lesbar: {path_str}"

        if _PLACEHOLDER_RE.search(content):
            return (
                f"Artefakt enthält Platzhalter-Text: {path_str}\n"
                f"  → Echte Testausgabe eintragen, kein Copy-Paste-Beispiel."
            )

        if not _FAILURE_RE.search(content):
            return (
                f"RED-Artefakt zeigt keine Fehler-Evidenz: {path_str}\n"
                f"  → Datei muss echte Fehlermeldungen enthalten (FAILED, ERROR, etc.).\n"
                f"  → Artefakt scheint zu zeigen, dass Tests bestanden — das ist kein RED."
            )

    return None


def main() -> None:
    try:
        tool_input = get_tool_input()
    except Exception:
        allow()

    file_path = tool_input.get("file_path", "")

    # Immer-Erlaubt-Pfade (Docs, Configs, Specs) — gleiche Logik wie edit_gate.py
    if _ALWAYS_ALLOWED.search(file_path):
        allow()

    # Workflow laden
    try:
        import workflow as _wf
        result = _wf.read_active_workflow_fast()
    except Exception:
        allow()

    if result is None:
        allow()

    wf_name, workflow = result
    current_phase = workflow.get("current_phase", "")

    if current_phase not in TEST_REQUIRED_PHASES:
        allow()

    project_root = find_project_root()

    red_artifacts = [
        a for a in workflow.get("test_artifacts", [])
        if a.get("phase") == "phase5_tdd_red"
    ]

    if not red_artifacts:
        # Kein Artefakt → erst hier blockieren wenn auch edit_gate's boolean-Flag fehlt
        # (edit_gate.py blockiert schon, aber zur Sicherheit auch hier)
        red_done = workflow.get("red_test_done", False) or workflow.get("ui_test_red_done", False)
        if not red_done:
            block(
                f"BLOCKED [tdd_enforcement]: Keine RED-Test-Artefakte für '{wf_name}'.\n"
                f"  Phase: {current_phase}\n"
                f"→ Zuerst /40-tdd-red ausführen und Artefakte registrieren:\n"
                f"  python3 .claude/hooks/workflow.py add-artifact test_output "
                f"'pfad/zum/output.txt' 'Tests fehlgeschlagen: ...' phase5_tdd_red"
            )
        allow()

    # Qualität der Artefakte prüfen
    errors = []
    for art in red_artifacts:
        err = _validate_artifact(art, project_root)
        if err:
            errors.append(f"  [{art.get('path', '?')}] {err}")

    if errors:
        block(
            f"BLOCKED [tdd_enforcement]: RED-Artefakte ungültig für '{wf_name}':\n"
            + "\n".join(errors)
            + "\n→ Echte fehlschlagende Tests ausführen und neue Artefakte registrieren."
        )

    allow()


if __name__ == "__main__":
    main()
