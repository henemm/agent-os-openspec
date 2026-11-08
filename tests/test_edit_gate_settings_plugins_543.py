"""Tests fuer #543 — enge Ausnahme der Orchestrator-Sperre: Plugin-Einrichtung
in der projektlokalen `.claude/settings.json` (nur `enabledPlugins` und
`extraKnownMarketplaces`).

Hermetisch: Fake-HOME + Fake-Projekt im tmp_path, Subprozess mit cwd=Projekt
(Muster aus test_edit_gate_orchestrator_files.py), Payload mit tool_name.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"

PLUGINS = {"agent-os-openspec@henemm-private": True}
MARKETS = {
    "henemm-private": {
        "source": {"source": "github", "repo": "henemm/agent-os-openspec"}
    }
}
HOOKS = {
    "PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 x.py"}]}
    ]
}
PERMS = {"allow": ["Bash(ls:*)"], "deny": ["Read(.env)"]}
BASE = {"hooks": HOOKS, "permissions": PERMS}


def _run(env: dict, tool_name: str, tool_input: dict, cwd: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "edit_gate.py")],
        input=payload, capture_output=True, text=True, env=full_env, cwd=cwd,
    )


def _setup(tmp_path: Path):
    fake_home = tmp_path / "fakehome"
    (fake_home / ".claude").mkdir(parents=True)
    proj = tmp_path / "project"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude").mkdir(parents=True)
    env = {
        "HOME": str(fake_home),
        "CLAUDE_PROJECT_DIR": str(proj),
        "OPENSPEC_ACTIVE_WORKFLOW": "",
    }
    return proj, env


def _write_token(proj: Path, workflow_name: str = "fix-wf") -> Path:
    token_file = proj / ".claude" / "user_override_token.json"
    token_file.write_text(json.dumps({
        "version": 2,
        "tokens": {workflow_name: {
            "created": datetime.now().isoformat(),
            "granted_by": "user_prompt",
        }},
    }))
    return token_file


def _settings(proj: Path, data=None, raw: str = None) -> Path:
    p = proj / ".claude" / "settings.json"
    p.write_text(raw if raw is not None else json.dumps(data, indent=2))
    return p


def _write(env, proj, path: Path, content: str):
    return _run(env, "Write", {"file_path": str(path), "content": content}, str(proj))


# --- AC-1 ---

def test_create_with_plugin_keys_only_allowed(tmp_path):
    proj, env = _setup(tmp_path)
    target = proj / ".claude" / "settings.json"
    assert not target.exists()
    content = json.dumps({"enabledPlugins": PLUGINS, "extraKnownMarketplaces": MARKETS})
    r = _write(env, proj, target, content)
    assert r.returncode == 0, r.stderr


# --- AC-2 ---

def test_existing_file_plugin_change_allowed(tmp_path):
    proj, env = _setup(tmp_path)
    cwd = str(proj)

    # (a) Write ergaenzt beide Schluessel, Rest identisch (auch umsortiert / anderer Einzug)
    path = _settings(proj, BASE)
    new = dict(BASE)
    new["enabledPlugins"] = PLUGINS
    new["extraKnownMarketplaces"] = MARKETS
    r = _write(env, proj, path, json.dumps(new, indent=2))
    assert r.returncode == 0, "Write indent2: " + r.stderr

    reordered = {
        "extraKnownMarketplaces": MARKETS,
        "permissions": PERMS,
        "enabledPlugins": PLUGINS,
        "hooks": HOOKS,
    }
    r = _write(env, proj, path, json.dumps(reordered, indent=4))
    assert r.returncode == 0, "Write reordered/indent4: " + r.stderr

    r = _write(env, proj, path, json.dumps(reordered))
    assert r.returncode == 0, "Write compact: " + r.stderr

    # (b) Edit fuegt enabledPlugins-Eintrag ein
    path = _settings(proj, {"enabledPlugins": {"a@b": True}, **BASE})
    assert '"a@b": true' in path.read_text()
    r = _run(env, "Edit", {
        "file_path": str(path),
        "old_string": '"a@b": true',
        "new_string": '"a@b": true,\n    "c@d": true',
    }, cwd)
    assert r.returncode == 0, "Edit: " + r.stderr

    # (c) MultiEdit in zwei Schritten
    r = _run(env, "MultiEdit", {
        "file_path": str(path),
        "edits": [
            {"old_string": '"a@b": true', "new_string": '"a@b": true,\n    "c@d": true'},
            {"old_string": '"c@d": true', "new_string": '"c@d": true,\n    "e@f": false'},
        ],
    }, cwd)
    assert r.returncode == 0, "MultiEdit: " + r.stderr

    # (d) bestehenden enabledPlugins-Wert true -> false
    r = _run(env, "Edit", {
        "file_path": str(path),
        "old_string": '"a@b": true',
        "new_string": '"a@b": false',
    }, cwd)
    assert r.returncode == 0, "true->false: " + r.stderr

    # (e) enabledPlugins komplett entfernen
    r = _write(env, proj, path, json.dumps(dict(BASE), indent=2))
    assert r.returncode == 0, "remove enabledPlugins: " + r.stderr


# --- AC-3 ---

def _case_hook():
    d = json.loads(json.dumps(BASE))
    d["hooks"]["PostToolUse"] = [{"matcher": "*", "hooks": [{"type": "command", "command": "evil"}]}]
    return d


def _case_perm_allow():
    d = json.loads(json.dumps(BASE))
    d["permissions"]["allow"].append("Bash(rm:*)")
    return d


def _case_env():
    d = json.loads(json.dumps(BASE))
    d["env"] = {"FOO": "bar"}
    return d


def _case_disable_hooks():
    d = json.loads(json.dumps(BASE))
    d["disableAllHooks"] = True
    return d


def _case_change_perm():
    d = json.loads(json.dumps(BASE))
    d["permissions"]["deny"] = ["Read(.secret)"]
    return d


@pytest.mark.parametrize("make", [
    _case_hook, _case_perm_allow, _case_env, _case_disable_hooks, _case_change_perm,
], ids=["add-hook", "add-permission", "add-env", "disableAllHooks", "change-permission"])
def test_other_key_change_blocked(tmp_path, make):
    proj, env = _setup(tmp_path)
    path = _settings(proj, BASE)
    new = make()
    new["enabledPlugins"] = PLUGINS  # Plugin-Schluessel dabei aendert nichts am Block
    r = _write(env, proj, path, json.dumps(new, indent=2))
    assert r.returncode == 2, r.stderr


# --- AC-4 ---

def test_other_key_removed_or_new_file_extra_key_blocked(tmp_path):
    proj, env = _setup(tmp_path)
    path = _settings(proj, {**BASE, "enabledPlugins": PLUGINS})

    # permissions entfernt
    r = _write(env, proj, path, json.dumps({"hooks": HOOKS, "enabledPlugins": PLUGINS}))
    assert r.returncode == 2, "remove permissions: " + r.stderr

    # neue Datei mit enabledPlugins + hooks
    path.unlink()
    r = _write(env, proj, path, json.dumps({"enabledPlugins": PLUGINS, "hooks": HOOKS}))
    assert r.returncode == 2, "new file extra key: " + r.stderr

    # Edit auf nicht existierende settings.json
    assert not path.exists()
    r = _run(env, "Edit", {
        "file_path": str(path), "old_string": "{}", "new_string": '{"enabledPlugins": {}}',
    }, str(proj))
    assert r.returncode == 2, "Edit on missing file: " + r.stderr


# --- AC-5 ---

_DUP_NEW = '{"hooks": {"PreToolUse": []}, "hooks": {}, "enabledPlugins": {}}'


@pytest.mark.parametrize("existing,new", [
    ({}, "{not json"),
    ({}, "[]"),
    ({}, '"x"'),
    ({}, '{"enabledPlugins": []}'),
    ({}, '{"enabledPlugins": {"a@b": "yes"}}'),
    ({}, '{"extraKnownMarketplaces": {"m": "github"}}'),
    ({}, '{"extraKnownMarketplaces": []}'),
    ({"hooks": {}}, _DUP_NEW),
    ({"disableAllHooks": False}, '{"disableAllHooks": 0}'),
], ids=["broken-json", "array", "string", "plugins-list", "plugin-value-text",
        "market-value-text", "markets-list", "duplicate-key", "type-swap"])
def test_malformed_or_non_object_blocked(tmp_path, existing, new):
    proj, env = _setup(tmp_path)
    path = _settings(proj, existing)
    r = _write(env, proj, path, new)
    assert r.returncode == 2, r.stderr


def test_malformed_or_non_object_blocked_existing_broken(tmp_path):
    proj, env = _setup(tmp_path)
    path = _settings(proj, raw="{broken json")
    r = _write(env, proj, path, json.dumps({"enabledPlugins": PLUGINS}))
    assert r.returncode == 2, r.stderr


# --- AC-6 ---

def test_block_message_names_exception(tmp_path):
    proj, env = _setup(tmp_path)
    path = _settings(proj, BASE)
    r = _write(env, proj, path, json.dumps(_case_hook()))
    assert r.returncode == 2
    assert "enabledPlugins" in r.stderr, r.stderr
    assert "extraKnownMarketplaces" in r.stderr, r.stderr


# --- AC-7 ---

def test_override_path_unchanged(tmp_path):
    proj, env = _setup(tmp_path)
    path = _settings(proj, BASE)
    token_file = _write_token(proj)

    # Hook-Aenderung mit gueltigem Token -> frei (#48)
    r = _write(env, proj, path, json.dumps(_case_hook()))
    assert r.returncode == 0, r.stderr

    # Plugin-Aenderung mit Token -> frei, Token bleibt erhalten
    before = token_file.read_text()
    new = dict(BASE)
    new["enabledPlugins"] = PLUGINS
    r = _write(env, proj, path, json.dumps(new))
    assert r.returncode == 0, r.stderr
    assert token_file.exists()
    assert token_file.read_text() == before
    assert "fix-wf" in json.loads(token_file.read_text())["tokens"]


# --- AC-8 ---

def test_exception_limited_to_settings_json(tmp_path):
    proj, env = _setup(tmp_path)

    local = proj / ".claude" / "settings.local.json"
    r = _write(env, proj, local, json.dumps({"enabledPlugins": PLUGINS}))
    assert r.returncode == 2, "settings.local.json: " + r.stderr

    other = proj / "other.json"
    other.write_text("{}")
    link = proj / ".claude" / "settings.json"
    link.symlink_to(other)
    r = _write(env, proj, link, json.dumps({"enabledPlugins": PLUGINS}))
    assert r.returncode == 2, "symlink: " + r.stderr
