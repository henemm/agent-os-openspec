"""Kette beendet den Turn an Phasengrenzen bei aktivem Auto-/clear (Issue #489).

Spec: docs/specs/fix-489-kette-auto-clear.md (AC-1 bis AC-3).

Abgeloest durch #662 (docs/specs/feat-662-kette-flach.md): Auto-/clear ist
stillgelegt. `workflow.py autoclear` sagt immer `AUTO_CLEAR=off` (Kompatibilitaet
fuer gecachte Befehlstexte, faellt mit #663), die Befehle 10 bis 50 pruefen es nicht
mehr und setzen die Kette im Auto-Modus selbst fort.
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
    # #662: auch Herdr-Pane + Env-Schalter ergibt off (frueher on)
    for herdr, switch in [(True, "1"), (False, "1"), (True, None), (True, "0")]:
        res = _run(tmp_path, herdr, switch)
        assert res.returncode == 0, res.stderr
        assert res.stdout.strip() == "AUTO_CLEAR=off", (herdr, switch, res.stdout)


def _texts(name: str):
    return [REPO_ROOT / "core" / "commands" / f"{name}.md",
            REPO_ROOT / "skills" / name / "SKILL.md"]


@pytest.mark.parametrize("name", CHAIN)
def test_chain_commands_without_autoclear(name):
    """#662 ersetzt test_chain_commands_check_autoclear: keine `autoclear`-Pruefung mehr;
    der Halt an der Kontext-Schwelle (`NICHT selbst`, ❗Du-Zeile) bleibt."""
    for path in _texts(name):
        text = path.read_text(encoding="utf-8")
        # Quelle: `workflow.py autoclear`; generierte Skills schreiben `$WF autoclear`
        assert not re.findall(r"(?:workflow\.py|\$WF) autoclear", text), path
        assert "AUTO_CLEAR" not in text, path
        assert "NICHT selbst" in text, path
        assert "❗Du-Zeile" in text, path


def test_skills_in_sync():
    res = subprocess.run([sys.executable, str(SYNC), "--check"], capture_output=True,
                         text=True, cwd=str(REPO_ROOT), timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr
