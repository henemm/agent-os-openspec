"""Uebergabe an frische Sitzung idempotent (Issue #668, Epic #649).

Spec: docs/specs/fix-668-handoff-idempotent.md (AC-1 bis AC-6).
Helfer aus tests/test_handoff_667.py (tmp-Projekt, Fake-Herdr, explizites Env).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_handoff_667 import (  # noqa: E402
    COMMANDS_DIR, HOOKS_DIR, REPO_ROOT, SKILLS_DIR, _auftrag, _auftrag_file, _calls, _env,
    _fake_herdr, _handoff, _kv, _of, _parse, _project,
)

REMOTE = "https://github.com/acme/demo.git"

# Fake-Herdr, das bei `pane run` die Auftragsdatei loescht (Vermerk scheitert danach)
FAKE_HERDR_DELETE = """#!{py}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_HERDR_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
if args[:2] == ["pane", "split"]:
    print(json.dumps({{"result": {{"pane": {{"pane_id": "pane-new"}}}}}}))
    sys.exit(0)
if args[:2] == ["pane", "run"]:
    os.remove(os.environ["FAKE_DELETE"])
    sys.exit(0)
sys.exit(0)
"""


def _lines(res) -> list:
    assert res.returncode == 0, (res.stdout, res.stderr)
    return _parse(res.stdout)[0]


# --- AC-1 -------------------------------------------------------------------

def test_handoff_done_after_mark_cloud(tmp_path):
    """AC-1: nach --mark cloud meldet handoff HANDOFF_DONE=cloud (nach REPO_URL)."""
    proj = _project(tmp_path / "p", remote=REMOTE)
    env = _env(proj, remote=True)
    before = _lines(_handoff(proj, env=env))
    assert _kv(before, "HANDOFF_DONE") is None, before

    _lines(_handoff(proj, "--mark", "cloud", env=env))
    after = _lines(_handoff(proj, env=env))
    assert after[:4] == ["HANDOFF=cloud", "NEXT=548",
                         "REPO_URL=https://github.com/acme/demo", "HANDOFF_DONE=cloud"], after

    # Vermerk fuer eine andere Nummer zaehlt nicht
    proj2 = _project(tmp_path / "q", remote=REMOTE)
    data = _auftrag(proj2)
    data["handoff"] = {"issue": 549, "mode": "cloud", "at": "2026-11-25T10:00:00Z"}
    _auftrag_file(proj2).write_text(json.dumps(data))
    other = _lines(_handoff(proj2, env=_env(proj2, remote=True)))
    assert _kv(other, "HANDOFF_DONE") is None, other


# --- AC-2 -------------------------------------------------------------------

def test_handoff_done_after_herdr_start(tmp_path):
    """AC-2: nach erfolgreichem --start meldet handoff HANDOFF_DONE=herdr."""
    proj = _project(tmp_path / "p")
    env = _env(proj, claude=True, herdr=_fake_herdr(tmp_path / "p"))
    assert _kv(_lines(_handoff(proj, "--start", env=env)), "STARTED") == "yes"
    again = _lines(_handoff(proj, env=env))
    assert _kv(again, "HANDOFF") == "herdr", again
    assert _kv(again, "HANDOFF_DONE") == "herdr", again


# --- AC-3 -------------------------------------------------------------------

def test_marked_line(tmp_path):
    """AC-3: --mark meldet MARKED=yes (Weg cloud) bzw. MARKED=no (Weg none)."""
    proj = _project(tmp_path / "p")
    yes = _lines(_handoff(proj, "--mark", "cloud", env=_env(proj, remote=True)))
    assert _kv(yes, "MARKED") == "yes", yes

    proj2 = _project(tmp_path / "q")
    before = _auftrag_file(proj2).read_bytes()
    no = _lines(_handoff(proj2, "--mark", "cloud",
                         env=_env(proj2, remote=True, autonomy="manual")))
    assert _kv(no, "HANDOFF") == "none" and _kv(no, "MARKED") == "no", no
    assert _auftrag_file(proj2).read_bytes() == before


# --- AC-4 -------------------------------------------------------------------

def test_mark_rereads_under_lock(tmp_path, monkeypatch):
    """AC-4: _handoff_mark liest unter Sperre neu und erhaelt externe Aenderungen."""
    import fcntl
    proj = _project(tmp_path / "p")
    for key in ("CLAUDE_CODE_SESSION_ID", "HERDR_ENV", "HERDR_PANE_ID", "HERDR_WORKSPACE_ID",
                "OPENSPEC_ACTIVE_WORKFLOW"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.setenv("HOME", str(proj / "_home"))
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415

    path = _auftrag_file(proj)
    # extern geaendert, nachdem handoff gelesen haette: 548 abgehakt
    data = _auftrag(proj)
    data["issues"][1]["status"] = "done"
    path.write_text(json.dumps(data))

    held = []
    real_write = workflow.write_auftrag

    def spy_write(root, auftrag):
        fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held.append(False)
            fcntl.flock(fd, fcntl.LOCK_UN)
        except BlockingIOError:
            held.append(True)
        finally:
            os.close(fd)
        return real_write(root, auftrag)

    monkeypatch.setattr(workflow, "write_auftrag", spy_write)
    workflow._handoff_mark(proj, 548, "cloud")

    out = _auftrag(proj)
    assert [e["status"] for e in out["issues"]] == ["open", "done", "open"], out
    assert out["handoff"]["issue"] == 548 and out["handoff"]["mode"] == "cloud", out
    assert held == [True], held


# --- AC-5 -------------------------------------------------------------------

def test_start_yes_when_mark_fails(tmp_path):
    """AC-5: Start erfolgreich, Vermerk scheitert -> STARTED=yes + WARN, kein REASON."""
    proj = _project(tmp_path / "p")
    exe = tmp_path / "p" / "herdr-del"
    exe.write_text(FAKE_HERDR_DELETE.format(py=sys.executable))
    exe.chmod(0o755)
    env = _env(proj, claude=True, herdr=exe, FAKE_DELETE=str(_auftrag_file(proj)))
    lines = _lines(_handoff(proj, "--start", env=env))
    assert len(_of(_calls(proj), "pane run")) == 1, _calls(proj)
    assert _kv(lines, "STARTED") == "yes", lines
    assert _kv(lines, "REASON") is None, lines
    warn = _kv(lines, "WARN")
    assert warn and "Vermerk" in warn, lines


# --- AC-6 -------------------------------------------------------------------

def test_command_texts_handoff_done():
    """AC-6: Befehlstexte nennen HANDOFF_DONE, 80-workflow dokumentiert die Zeilen."""
    for name in ("60-validate", "70-deploy"):
        for path in (COMMANDS_DIR / f"{name}.md", SKILLS_DIR / name / "SKILL.md"):
            text = path.read_text()
            assert "HANDOFF_DONE=" in text, path
            idx = text.index("HANDOFF_DONE=")
            window = text[idx:idx + 400]
            assert "keine weitere Sitzung" in window, (path, window)
    wf_cmd = (COMMANDS_DIR / "80-workflow.md").read_text()
    for needle in ("HANDOFF_DONE", "MARKED", "WARN"):
        assert needle in wf_cmd, needle
    res = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"),
                          "--check"], capture_output=True, text=True, cwd=str(REPO_ROOT))
    assert res.returncode == 0, (res.stdout, res.stderr)
