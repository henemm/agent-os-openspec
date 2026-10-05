"""Issue #279, Befund 1: Copy-Modus registriert dieselben Hooks wie das Plugin.

Vorher fuehrte setup.py eine eigene Liste mit 4 Kern-Hooks; Worktree-Pflicht,
Secrets-Guard, Egress-Guard, Edit-Verify, Footer-Gate und die Events
SessionStart/SessionEnd fehlten still. Jetzt ist hooks/hooks.json die einzige
Quelle — ein neuer Eintrag dort erscheint ohne weitere Aenderung im Copy-Modus.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"


def _signature(hooks: dict) -> set:
    """(Event, Matcher, Hook-Datei, Argumente) — unabhaengig von der Pfad-Schreibweise."""
    out = set()
    for event, groups in hooks.items():
        for group in groups:
            for hook in group["hooks"]:
                m = re.search(r'(?:core|\.claude)/hooks/(\S+?\.py)"?(.*)$', hook["command"])
                assert m, hook["command"]
                out.add((event, group.get("matcher"), m.group(1), m.group(2).strip()))
    return out


def _install(project: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(REPO_ROOT / "setup.py"), str(project), *extra],
                          capture_output=True, text=True, timeout=120)


def _settings(project: Path) -> dict:
    return json.loads((project / ".claude" / "settings.json").read_text())


@pytest.fixture
def copy_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    r = _install(project)
    assert r.returncode == 0, r.stdout + r.stderr
    return project


def test_copy_mode_registers_every_plugin_hook(copy_project):
    plugin = _signature(json.loads(HOOKS_JSON.read_text())["hooks"])
    assert _signature(_settings(copy_project)["hooks"]) == plugin


def test_copy_mode_has_session_events_and_guards(copy_project):
    sig = _signature(_settings(copy_project)["hooks"])
    files = {s[2] for s in sig}
    for name in ("session_singleton_guard.py", "worktree_write_guard.py", "secrets_guard.py",
                 "secret_egress_guard.py", "edit_verify.py", "footer_gate.py"):
        assert name in files, name
    events = {s[0] for s in sig}
    assert {"SessionStart", "SessionEnd", "Stop"} <= events


def test_commands_point_to_copied_files(copy_project):
    for event, groups in _settings(copy_project)["hooks"].items():
        for group in groups:
            for hook in group["hooks"]:
                cmd = hook["command"]
                assert cmd.startswith('python3 "${CLAUDE_PROJECT_DIR}/.claude/hooks/'), cmd
                name = re.search(r'hooks/(\S+?\.py)', cmd).group(1)
                assert (copy_project / ".claude" / "hooks" / name).exists(), cmd


def test_module_hooks_join_matching_groups(tmp_path):
    project = tmp_path / "ios"
    project.mkdir()
    r = _install(project, "--module", "ios-swiftui")
    assert r.returncode == 0, r.stdout + r.stderr
    sig = _signature(_settings(project)["hooks"])
    assert ("PreToolUse", "Edit|Write|MultiEdit", "ui_test_preflight.py", "") in sig
    assert ("PreToolUse", "Bash", "test_lock_guard.py", "") in sig
    assert ("PostToolUse", "Bash", "on_ui_test_failure.py", "") in sig


def test_update_adds_missing_hooks_and_keeps_own(copy_project):
    """Altprojekt mit 4 Hooks (Stand vor #279) plus eigenem Hook: --update ergaenzt."""
    path = copy_project / ".claude" / "settings.json"
    old = {
        "permissions": {"allow": ["Bash(make:*)"]},
        "hooks": {
            "PreToolUse": [
                {"matcher": "Edit|Write", "hooks": [
                    {"type": "command", "command": "python3 .claude/hooks/edit_gate.py"}]},
                {"matcher": "Bash", "hooks": [
                    {"type": "command", "command": "python3 .claude/hooks/bash_gate.py"},
                    {"type": "command", "command": "./scripts/own_hook.sh"}]},
            ],
            "UserPromptSubmit": [{"hooks": [
                {"type": "command", "command": "python3 .claude/hooks/phase_listener.py"}]}],
        },
    }
    path.write_text(json.dumps(old))

    r = _install(copy_project, "--update")
    assert r.returncode == 0, r.stdout + r.stderr
    new = _settings(copy_project)
    assert new["permissions"] == old["permissions"]
    commands = [h["command"] for gs in new["hooks"].values() for g in gs for h in g["hooks"]]
    assert "./scripts/own_hook.sh" in commands
    assert commands.count("python3 .claude/hooks/bash_gate.py") == 1
    assert not any('hooks/bash_gate.py"' in c for c in commands), "Duplikat"
    files = {re.search(r'hooks/(\S+?\.py)', c).group(1) for c in commands if ".py" in c}
    plugin_files = {s[2] for s in _signature(json.loads(HOOKS_JSON.read_text())["hooks"])}
    assert plugin_files <= files

    _install(copy_project, "--update")
    assert _settings(copy_project) == new, "zweites Update aendert nichts"


# --- Pruefrunde 1 (F5, F6) ---

@pytest.mark.parametrize("content", ['{"hooks": null}', '{"hooks": []}', '[]',
                                     '{"hooks": {"PreToolUse": {}}}',
                                     '{"hooks": {"PreToolUse": ["x"]}}',
                                     '{"hooks": {"PreToolUse": [{"hooks": ["x"]}]}}'])
def test_update_survives_odd_settings(copy_project, content):
    path = copy_project / ".claude" / "settings.json"
    path.write_text(content)
    r = _install(copy_project, "--update")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "WARNING: Hook-Registrierung nicht abgeglichen" in r.stdout
    assert path.read_text() == content, "unerwartete Struktur bleibt unangetastet"


def test_update_registers_per_matcher_and_widens_legacy_edit_group(copy_project):
    path = copy_project / ".claude" / "settings.json"
    path.write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Edit|Write", "hooks": [
            {"type": "command", "command": "python3 .claude/hooks/edit_gate.py"}]},
        {"matcher": "Bash", "hooks": [
            {"type": "command", "command": "python3 .claude/hooks/secrets_guard.py"}]},
    ]}}))
    assert _install(copy_project, "--update").returncode == 0
    groups = {g.get("matcher"): g for g in _settings(copy_project)["hooks"]["PreToolUse"]}
    assert "Edit|Write" not in groups, "Alt-Gruppe auf MultiEdit angehoben"
    edit_cmds = [h["command"] for h in groups["Edit|Write|MultiEdit"]["hooks"]]
    assert sum("edit_gate.py" in c for c in edit_cmds) == 1
    assert any("secrets_guard.py" in h["command"] for h in groups["Read"]["hooks"])


@pytest.mark.parametrize("legacy_hooks", [
    ["python3 .claude/hooks/edit_gate.py"],                     # rein, neben neuer Gruppe
    ["python3 .claude/hooks/edit_gate.py", "./my-lint.sh"],     # gemischt
])
def test_no_double_registration_with_legacy_edit_group(copy_project, legacy_hooks):
    """Pruefrunde 2: Alt-Gruppe `Edit|Write` neben bzw. statt der neuen Gruppe."""
    path = copy_project / ".claude" / "settings.json"
    path.write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": c}
                                           for c in legacy_hooks]},
        {"matcher": "Edit|Write|MultiEdit", "hooks": [
            {"type": "command", "command": "python3 .claude/hooks/tdd_enforcement.py"}]},
    ]}}))
    assert _install(copy_project, "--update").returncode == 0
    groups = _settings(copy_project)["hooks"]["PreToolUse"]
    edit_like = [h["command"] for g in groups if g.get("matcher") in ("Edit|Write",
                 "Edit|Write|MultiEdit") for h in g["hooks"]]
    for name in ("edit_gate.py", "tdd_enforcement.py", "worktree_write_guard.py"):
        assert sum(name in c for c in edit_like) == 1, (name, edit_like)
    assert sum(g.get("matcher") == "Edit|Write|MultiEdit" for g in groups) == 1
