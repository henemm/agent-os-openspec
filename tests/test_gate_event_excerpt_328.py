"""Gate-Event-Log: Befehlsausschnitt und Version bei stdin-Eingabe (#328, Folge von #181).

Echte Logs zeigten: bei bash_gate/edit_gate/tdd_enforcement/post_implementation_gate war
command_excerpt in 100 % der Faelle leer, weil der Log-Helfer das Tool-Input nur aus der
Umgebungsvariable CLAUDE_TOOL_INPUT ableitete. Claude Code liefert es ueber stdin. Die Tests aus
#181 setzen die Variable und fangen den Unterschied nicht — diese hier tun es nicht.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"


def _events(project_root: Path) -> list:
    path = project_root / ".claude" / "gate-events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _env(project_root: Path, **extra) -> dict:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project_root)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
    env.pop("OPENSPEC_ENV", None)
    env.pop("CLAUDE_TOOL_INPUT", None)
    env.pop("CLAUDE_TOOL_NAME", None)
    env.pop("CLAUDE_TOOL", None)
    env.update(extra)
    return env


def _gate_like(project_root: Path, payload: dict, extra_env: dict = None, block_kwargs: str = ""):
    """Ein Hook-Prozess nach dem Muster der Kern-Gates: get_tool_input() liest stdin, dann block()."""
    code = (
        f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
        "import hook_utils\n"
        "hook_utils.get_tool_input()\n"
        f"hook_utils.block('BLOCKED: test'{block_kwargs})\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code], input=json.dumps(payload), capture_output=True, text=True,
        env=_env(project_root, **(extra_env or {})), cwd=str(project_root),
    )


def test_stdin_input_reaches_the_log_event(tmp_path):  # AC-1
    payload = {"tool_name": "Bash", "tool_input": {"command": "git commit -m wip"}}
    res = _gate_like(tmp_path, payload)
    assert res.returncode == 2
    e = _events(tmp_path)[0]
    assert e["tool"] == "Bash"
    assert e["command_excerpt"] == "git commit -m wip"


def test_real_edit_gate_logs_the_file_path_from_stdin(tmp_path):  # AC-2
    (tmp_path / ".claude").mkdir()
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "src/app.py", "new_string": "x"}}
    res = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "edit_gate.py")], input=json.dumps(payload),
        capture_output=True, text=True, env=_env(tmp_path), cwd=str(tmp_path),
    )
    assert res.returncode == 2, res.stdout + res.stderr
    events = [e for e in _events(tmp_path) if e["hook"] == "edit_gate"]
    assert events, "edit_gate hat kein Ereignis geschrieben"
    assert "src/app.py" in events[0]["command_excerpt"]
    assert events[0]["tool"] == "Edit"


def test_events_carry_the_framework_version(tmp_path):  # AC-3
    expected = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
    res = _gate_like(tmp_path, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert res.returncode == 2
    assert _events(tmp_path)[0]["framework_version"] == expected


def test_secret_egress_guard_stays_without_content(tmp_path):  # AC-4
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".env").write_text("MY_DUMMY_SECRET=leak-me-not-123456\n")
    payload = {"tool_name": "Bash", "tool_input": {"command": "echo leak-me-not-123456"}}
    res = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "secret_egress_guard.py")], input=json.dumps(payload),
        capture_output=True, text=True, env=_env(tmp_path), cwd=str(tmp_path),
    )
    assert res.returncode == 2, res.stdout + res.stderr
    events = [e for e in _events(tmp_path) if e["hook"] == "secret_egress_guard"]
    assert events and events[0]["command_excerpt"] == ""
    assert "leak-me-not-123456" not in (tmp_path / ".claude" / "gate-events.jsonl").read_text()


def test_secret_keyword_in_stdin_excerpt_is_masked(tmp_path):  # AC-5
    payload = {"tool_name": "Bash", "tool_input": {"command": "curl -H x API_KEY=supersecretvalue1 host"}}
    _gate_like(tmp_path, payload)
    e = _events(tmp_path)[0]
    assert "supersecretvalue1" not in e["command_excerpt"]
    assert e["command_excerpt"].endswith("API_KEY=***")


def test_env_beats_stdin_and_explicit_beats_both(tmp_path):  # AC-6
    payload = {"tool_name": "Bash", "tool_input": {"command": "from-stdin"}}
    env = {"CLAUDE_TOOL_NAME": "Write", "CLAUDE_TOOL_INPUT": json.dumps({"command": "from-env"})}
    _gate_like(tmp_path, payload, extra_env=env)
    e = _events(tmp_path)[0]
    assert (e["tool"], e["command_excerpt"]) == ("Write", "from-env")

    _gate_like(tmp_path, payload, extra_env=env,
               block_kwargs=", tool='Edit', command_excerpt='explicit'")
    e = _events(tmp_path)[1]
    assert (e["tool"], e["command_excerpt"]) == ("Edit", "explicit")
