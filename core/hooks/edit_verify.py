#!/usr/bin/env python3
"""
Edit Verify — PostToolUse Edit|Write|MultiEdit

Prüft nach jedem Edit/Write, dass der neue Inhalt tatsächlich auf Disk
gelandet ist. Gibt bei stiller Fehlfunktion eine Warnung aus.

#439: Ist die Datei die `spec_file` eines Workflows ab phase4_approved und
liegt die Änderung nachweislich auf Disk, hängt es einen Eintrag
{ts, tool, sections} an `spec_post_approval_edits` im Workflow-State an —
nur über die gehärtete State-API aus hook_utils (#416/#422).

Fail-open: Jede Exception → exit(0). Blockiert nie.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _verify(payload: dict) -> None:
    """Warnung, wenn der neue Inhalt nicht in der Datei steht."""
    tool_input = payload.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return
    file_path = tool_input.get("file_path")
    if not file_path or not isinstance(file_path, str):
        return
    key = "content" if payload.get("tool_name", "") == "Write" else "new_string"
    search_string = tool_input.get(key)
    if not search_string or not isinstance(search_string, str):
        return
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            file_content = fh.read()
    except (OSError, UnicodeDecodeError):
        return  # Binärdateien oder fehlende Rechte → kein Problem
    if search_string[:200] not in file_content:
        print(
            f"WARNUNG [edit_verify]: Inhalt nach Edit NICHT in {file_path} gefunden.\n"
            f"  Erwartet: {repr(search_string[:80])}",
            file=sys.stderr,
        )


def _approved_spec_workflow(hook_utils, root: Path, file_path: str):
    """(State-Pfad, State) des Workflows mit dieser spec_file ab phase4, sonst None."""
    from workflow import PHASES
    target = Path(file_path).resolve()
    roots = [root]
    wt = hook_utils.find_worktree_root()
    if wt is not None:
        roots.insert(0, Path(wt))
    for wf_file in sorted((root / ".claude" / "workflows").glob("*.json")):
        try:
            data = hook_utils.read_state_json(wf_file, root)
        except Exception:
            continue
        spec = data.get("spec_file") if isinstance(data, dict) else None
        phase = data.get("current_phase") if isinstance(data, dict) else None
        if not isinstance(spec, str) or phase not in PHASES:
            continue
        if PHASES.index(phase) < PHASES.index("phase4_approved"):
            continue
        if any((Path(r) / spec).resolve() == target for r in roots):
            return wf_file, data
    return None


def _trail_sections(hook_utils, tool: str, tool_input: dict, content: str):
    """Abschnitte der Änderung auf Disk; None = nicht nachweisbar gelandet."""
    if tool == "Write":
        new = tool_input.get("content")
        same = isinstance(new, str) and new.replace("\r\n", "\n") == content
        return ["*"] if same else None
    if tool == "MultiEdit":
        edits = tool_input.get("edits")
        news = [e.get("new_string") for e in edits if isinstance(e, dict)] \
            if isinstance(edits, list) else []
    else:
        news = [tool_input.get("new_string")]
    found = []
    for new in news:
        if isinstance(new, str) and new:
            for title in hook_utils.spec_sections_at(content, new):
                if title not in found:
                    found.append(title)
    return found or None


def _record_trail(payload: dict) -> None:
    """Spur-Eintrag für Änderungen an einer freigegebenen Spec (#439)."""
    import hook_utils
    hook_utils.adopt_payload_cwd(payload)
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return
    root = hook_utils.find_project_root()
    match = _approved_spec_workflow(hook_utils, root, file_path)
    if match is None:
        return
    wf_file, _ = match
    content = Path(file_path).read_text(encoding="utf-8")
    tool = str(payload.get("tool_name") or "Edit")
    sections = _trail_sections(hook_utils, tool, tool_input, content)
    if sections is None:
        return
    data = hook_utils.read_state_json(wf_file, root)  # frisch lesen, wirft bei Verweis
    edits = data.get("spec_post_approval_edits")
    if not isinstance(edits, list):
        edits = []
    edits.append({"ts": datetime.now().isoformat(timespec="seconds"),
                  "tool": tool, "sections": sections})
    data["spec_post_approval_edits"] = edits
    hook_utils.atomic_write_json(wf_file, data, root=root)


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)
    for step in (_verify, _record_trail):
        try:
            step(payload)
        except Exception:
            pass
    sys.exit(0)


if __name__ == "__main__":
    main()
