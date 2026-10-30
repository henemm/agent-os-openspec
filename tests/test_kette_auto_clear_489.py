"""Kette beendet den Turn an Phasengrenzen bei aktivem Auto-/clear (Issue #489).

Spec: docs/specs/fix-489-kette-auto-clear.md (AC-1 bis AC-3).
"""

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / "core" / "hooks" / "workflow.py"
SYNC = REPO_ROOT / "scripts" / "sync_skills.py"

STUB = "#!/bin/bash\nexit 0\n"
CHAIN = ["10-context", "20-analyse", "30-write-spec", "40-tdd-red", "50-implement"]


def _env(tmp_path: Path, herdr: bool, switch: "str | None") -> dict:
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True, exist_ok=True)
    (proj / ".claude").mkdir(exist_ok=True)
    (proj / "_home").mkdir(exist_ok=True)
    (proj / "config.yaml").write_text("herdr:\n  enabled: true\n")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    if herdr:
        stub = tmp_path / "herdr-stub"
        stub.write_text(STUB)
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": "pane-489",
                    "HERDR_BIN_PATH": str(stub)})
    if switch is not None:
        env["OPENSPEC_HERDR_AUTO_CLEAR"] = switch
    return env


def _run(tmp_path: Path, herdr: bool, switch: "str | None"):
    env = _env(tmp_path, herdr, switch)
    return subprocess.run([sys.executable, str(WORKFLOW), "autoclear"],
                          capture_output=True, text=True, env=env,
                          cwd=env["CLAUDE_PROJECT_DIR"], timeout=30)


def test_autoclear_cli(tmp_path):
    res = _run(tmp_path, True, "1")
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "AUTO_CLEAR=on", res.stdout
    for herdr, switch in [(False, "1"), (True, None), (True, "0")]:
        res = _run(tmp_path, herdr, switch)
        assert res.returncode == 0, res.stderr
        assert res.stdout.strip() == "AUTO_CLEAR=off", (herdr, switch, res.stdout)


def _texts(name: str):
    return [REPO_ROOT / "core" / "commands" / f"{name}.md",
            REPO_ROOT / "skills" / name / "SKILL.md"]


@pytest.mark.parametrize("name", CHAIN)
def test_chain_commands_check_autoclear(name):
    for path in _texts(name):
        text = path.read_text(encoding="utf-8")
        # 30-write-spec hat zwei Selbstaufruf-Stellen (Auto-Freigabe, After Approval)
        expected = 2 if name == "30-write-spec" else 1
        # Quelle: `workflow.py autoclear`; generierte Skills schreiben `$WF autoclear`
        calls = len(re.findall(r"(?:workflow\.py|\$WF) autoclear", text))
        assert calls >= expected, path
        assert text.count("AUTO_CLEAR=on") >= expected, path
        assert "NICHT selbst" in text, path
        assert "❗Du-Zeile" in text, path


def test_skills_in_sync():
    res = subprocess.run([sys.executable, str(SYNC), "--check"], capture_output=True,
                         text=True, cwd=str(REPO_ROOT), timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr
