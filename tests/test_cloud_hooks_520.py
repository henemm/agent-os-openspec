"""Tests fuer Issue #520: Gates in Cloud-Sitzungen (Spec fix-520-cloud-hooks).

Echte Dateien in tmp_path, echte bash-/Python-Subprozesse, kein Mock der Shell.
`scripts/sync_cloud_hooks.py` wird lazy geladen, damit ein fehlendes Modul pro
Test als FAIL erscheint und nicht die ganze Datei beim Sammeln abbricht.

Erwartete Release-Check-Funktion: `release_check.check_cloud_hooks(root=None)`
-> `tuple[bool, str]`; `root` ist eine Repo-Wurzel mit `hooks/hooks.json` und
`.claude/settings.json` (Default: REPO_ROOT). FAIL-Meldung nennt
`sync_cloud_hooks.py`.
"""

import importlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
GUARD = REPO_ROOT / "core" / "hooks" / "session_singleton_guard.py"
PREFIX = '[ "$CLAUDE_CODE_REMOTE" != "true" ] || CLAUDE_PLUGIN_ROOT="${CLAUDE_PROJECT_DIR}" python3 "${CLAUDE_PROJECT_DIR}/core/hooks/'
ORIG_RE = re.compile(r"^\$\{CLAUDE_PLUGIN_ROOT\}/core/hooks/(\S+\.py)(.*)$")


def _load(name="sync_cloud_hooks"):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def _hooks_json(root=REPO_ROOT):
    return json.loads((root / "hooks" / "hooks.json").read_text(encoding="utf-8"))


def _make_root(tmp_path, settings=None):
    """Mini-Repo mit hooks.json (Kopie) und optionaler settings.json."""
    root = tmp_path / "repo"
    (root / "hooks").mkdir(parents=True)
    (root / ".claude").mkdir()
    shutil.copy(REPO_ROOT / "hooks" / "hooks.json", root / "hooks" / "hooks.json")
    if settings is not None:
        (root / ".claude" / "settings.json").write_text(
            json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return root


def _run_script(root, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / "sync_cloud_hooks.py"),
                           "--root", str(root), *args],
                          capture_output=True, text=True)


def test_cloud_hooks_mirror_plugin_hooks():
    mod = _load()
    src = _hooks_json()["hooks"]
    out = mod.cloud_hooks(_hooks_json())
    assert list(out) == list(src)
    for event, groups in src.items():
        assert len(out[event]) == len(groups)
        for g_src, g_out in zip(groups, out[event]):
            assert g_out.get("matcher") == g_src.get("matcher")
            assert len(g_out["hooks"]) == len(g_src["hooks"])
            for h_src, h_out in zip(g_src["hooks"], g_out["hooks"]):
                m = ORIG_RE.match(h_src["command"])
                assert m, h_src["command"]
                assert h_out["type"] == h_src["type"]
                assert h_out.get("timeout") == h_src.get("timeout")
                assert h_out["command"] == f'{PREFIX}{m.group(1)}"{m.group(2)}'


def test_committed_settings_are_in_sync():
    mod = _load()
    r = subprocess.run([sys.executable, str(SCRIPTS / "sync_cloud_hooks.py"), "--check"],
                       cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings["hooks"] == mod.cloud_hooks(_hooks_json())


def test_check_detects_drift(tmp_path):
    _load()
    expected = _load().cloud_hooks(_hooks_json())
    # (a) Eintrag fehlt
    missing = json.loads(json.dumps(expected))
    missing["PreToolUse"][0]["hooks"].pop()
    # (b) Timeout weicht ab
    timeout = json.loads(json.dumps(expected))
    timeout["PreToolUse"][0]["hooks"][0]["timeout"] += 99
    for i, hooks in enumerate((missing, timeout)):
        root = _make_root(tmp_path / str(i), {"permissions": {"allow": ["x"]}, "hooks": hooks})
        path = root / ".claude" / "settings.json"
        before = path.read_bytes()
        r = _run_script(root, "--check")
        assert r.returncode == 1, r.stdout + r.stderr
        assert "Cloud-Hooks nicht synchron" in (r.stdout + r.stderr)
        assert path.read_bytes() == before


def test_sync_keeps_other_keys_and_is_idempotent(tmp_path):
    mod = _load()
    settings = {"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"Stop": []}, "env": {"A": "ä"}}
    root = _make_root(tmp_path, settings)
    path = root / ".claude" / "settings.json"
    assert _run_script(root).returncode == 0
    first = path.read_bytes()
    data = json.loads(first)
    assert data["permissions"] == settings["permissions"]
    assert data["env"] == settings["env"]
    assert data["hooks"] == mod.cloud_hooks(_hooks_json(root))
    assert first.endswith(b"\n")
    assert _run_script(root).returncode == 0
    assert path.read_bytes() == first


def test_command_runs_only_in_cloud_and_propagates_exit(tmp_path):
    mod = _load()
    proj = tmp_path / "proj mit Leerzeichen"
    (proj / "core" / "hooks").mkdir(parents=True)
    out = tmp_path / "probe_out.json"
    (proj / "core" / "hooks" / "probe.py").write_text(
        "import sys, os, json\n"
        f"open({str(out)!r}, 'w').write(json.dumps({{'marker': 'ran', "
        "'stdin': sys.stdin.read(), 'root': os.environ.get('CLAUDE_PLUGIN_ROOT')}))\n"
        "sys.exit(2)\n", encoding="utf-8")
    mini = {"hooks": {"PreToolUse": [{"matcher": "", "hooks": [
        {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/core/hooks/probe.py", "timeout": 5}]}]}}
    cmd = mod.cloud_hooks(mini)["PreToolUse"][0]["hooks"][0]["command"]
    payload = '{"tool_name": "Bash", "x": "ü"}'

    def run(remote):
        env = {k: v for k, v in os.environ.items()
               if k not in ("CLAUDE_CODE_REMOTE", "CLAUDE_PLUGIN_ROOT")}
        env["CLAUDE_PROJECT_DIR"] = str(proj)
        if remote is not None:
            env["CLAUDE_CODE_REMOTE"] = remote
        return subprocess.run(["bash", "-c", cmd], input=payload, env=env,
                              capture_output=True, text=True)

    for remote in (None, "false"):
        assert run(remote).returncode == 0
        assert not out.exists()
    r = run("true")
    assert r.returncode == 2, r.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["marker"] == "ran"
    assert data["stdin"] == payload
    assert data["root"] == str(proj)


def test_guard_skips_worktree_rule_only_in_cloud(tmp_path):
    repo = tmp_path / "myproject"
    (repo / ".git").mkdir(parents=True)
    home = tmp_path / "home"
    (home / ".claude" / "sessions").mkdir(parents=True)
    payload = json.dumps({"session_id": "sess-520", "cwd": str(repo),
                          "tool_name": "Bash", "tool_input": {"command": "echo hi"}})

    def run(remote):
        env = {k: v for k, v in os.environ.items()
               if k not in ("CLAUDE_CODE_REMOTE", "OPENSPEC_ACTIVE_WORKFLOW")}
        env.update(HOME=str(home), CLAUDE_PROJECT_DIR=str(repo))
        env.pop("USERPROFILE", None)
        if remote is not None:
            env["CLAUDE_CODE_REMOTE"] = remote
        return subprocess.run([sys.executable, str(GUARD), "guard"], input=payload,
                              cwd=str(repo), env=env, capture_output=True, text=True)

    # (b)/(c) Regressionsschutz: ausser exakt "true" bleibt die Pflicht bestehen
    for remote in (None, "1"):
        r = run(remote)
        assert r.returncode == 2, r.stderr
        assert "BLOCKIERT" in r.stderr and "Worktree" in r.stderr
    # (a) Cloud: keine Worktree-Pflicht
    a = run("true")
    assert a.returncode == 0, a.stderr
    assert "BLOCKIERT" not in a.stderr + a.stdout


def test_release_check_reports_cloud_hook_drift(tmp_path):
    """Erwartet `release_check.check_cloud_hooks(root=None) -> (ok, msg)`."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    release_check = importlib.import_module("release_check")
    ok, msg = release_check.check_cloud_hooks(REPO_ROOT)
    assert ok, msg
    expected = _load().cloud_hooks(_hooks_json())
    expected["PreToolUse"][0]["hooks"].pop()
    root = _make_root(tmp_path, {"hooks": expected})
    ok, msg = release_check.check_cloud_hooks(root)
    assert not ok
    assert "sync_cloud_hooks.py" in msg


def test_readme_documents_cloud_sessions():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert re.search(r"^#+ .*Cloud sessions", text, re.M | re.I)
    assert "CLAUDE_CODE_REMOTE" in text
    assert "sync_cloud_hooks.py" in text


def test_changelog_mentions_520():
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    idx = text.index("## [Unreleased]")
    assert "#520" in text[idx:]
