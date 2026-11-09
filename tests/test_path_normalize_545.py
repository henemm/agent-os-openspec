"""#545: Pfad-Normalisierung vor den Pfad-Sperren in edit_gate.py und bash_gate.py.

Spec: docs/specs/fix-545-path-normalize.md (AC-1 bis AC-11).

Hermetisch: Fake-HOME + Fake-Projekt in tmp_path, die Gates DIESES Arbeitsbaums
laufen als echter Subprozess (Muster aus test_edit_gate_orchestrator_files.py
und test_bash_gate_ln_state_407.py). Abweichungen werden je Test gesammelt,
damit ein Lauf alle offenen Schreibweisen zeigt.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
EDIT_GATE = HOOKS_DIR / "edit_gate.py"
BASH_GATE = HOOKS_DIR / "bash_gate.py"

HOOKS = {"PreToolUse": [{"matcher": "Bash", "hooks": [
    {"type": "command", "command": "python3 x.py"}]}]}
BASE = {"hooks": HOOKS, "permissions": {"allow": ["Bash(ls:*)"]}}
EVIL = json.dumps({"hooks": {}, "disableAllHooks": True})

# Unsaubere Schreibweisen eines Pfades unter <proj>/.claude/ — {p}=Projekt, {f}=Rest
UNCLEAN = [
    "{p}/.claude//{f}",
    "{p}/./.claude/./{f}",
    "{p}/.claude/../.claude/{f}",
]


# --------------------------------------------------------------------- #
# edit_gate
# --------------------------------------------------------------------- #

def _setup(tmp_path: Path):
    fake_home = tmp_path / "fakehome"
    (fake_home / ".claude").mkdir(parents=True)
    proj = tmp_path / "project"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows").mkdir(parents=True)
    (proj / ".claude" / "hooks").mkdir(parents=True)
    (proj / "tests").mkdir(parents=True)
    (proj / ".claude" / "settings.json").write_text(json.dumps(BASE, indent=2))
    env = {
        "HOME": str(fake_home),
        "CLAUDE_PROJECT_DIR": str(proj),
        "OPENSPEC_ACTIVE_WORKFLOW": "",
    }
    return proj, fake_home, env


def _edit(env: dict, proj: Path, file_path: str, content: str = "x",
          tool_name: str = "Write") -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": tool_name,
                          "tool_input": {"file_path": file_path, "content": content}})
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(EDIT_GATE)],
        input=payload, capture_output=True, text=True, env=full_env,
        cwd=str(proj), timeout=60,
    )


def _write_token(proj: Path, workflow_name: str = "fix-wf") -> None:
    (proj / ".claude" / "user_override_token.json").write_text(json.dumps({
        "version": 2,
        "tokens": {workflow_name: {
            "created": datetime.now().isoformat(),
            "granted_by": "user_prompt",
        }},
    }))


def _collect(env, proj, paths, rc: int, content: str = "x", needle: "str | None" = None):
    wrong = []
    for fp in paths:
        r = _edit(env, proj, fp, content)
        if r.returncode != rc or (needle and needle not in r.stderr):
            wrong.append(f"  {fp!r}: rc={r.returncode} (soll {rc}), "
                         f"stderr={r.stderr.strip()[:160]!r}")
    return wrong


# --- AC-1 ---

def test_settings_json_unclean_spellings_blocked(tmp_path):
    proj, _, env = _setup(tmp_path)
    paths = [t.format(p=proj, f="settings.json") for t in UNCLEAN]
    wrong = _collect(env, proj, paths, 2, content=EVIL)
    assert not wrong, "Hook-Änderung an settings.json kam durch:\n" + "\n".join(wrong)


# --- AC-2 ---

def test_local_settings_and_active_workflow_unclean_blocked(tmp_path):
    proj, _, env = _setup(tmp_path)
    (proj / ".claude" / "settings.local.json").write_text("{}")
    (proj / ".claude" / "active_workflow").write_text("wf\n")
    paths = [t.format(p=proj, f=name) for name in ("settings.local.json", "active_workflow")
             for t in UNCLEAN]
    wrong = _collect(env, proj, paths, 2, content=EVIL)
    assert not wrong, "Orchestrator-Datei kam durch:\n" + "\n".join(wrong)


# --- AC-3 ---

def test_workflow_state_unclean_blocked(tmp_path):
    proj, _, env = _setup(tmp_path)
    (proj / ".claude" / "workflows" / "x.json").write_text("{}")
    paths = [
        f"{proj}/.claude//workflows/x.json",
        f"{proj}/./.claude/./workflows/x.json",
        f"{proj}/.claude/workflows//x.json",
    ]
    wrong = _collect(env, proj, paths, 2, content='{"adversary_verdict": "VERIFIED"}')
    assert not wrong, "Workflow-State kam durch:\n" + "\n".join(wrong)


# --- AC-4 ---

def test_infra_unclean_blocked_without_override(tmp_path):
    proj, _, env = _setup(tmp_path)
    paths = [
        f"{proj}/.claude//hooks/x.py",
        f"{proj}/./.claude/./hooks/x.py",
        f"{proj}/.claude/../.claude/hooks/x.py",
    ]
    # Ohne Workflow blockt Schritt 6 ohnehin jeden Code-Edit — massgeblich ist,
    # dass Schritt 4 (Infrastruktur) die unsaubere Schreibweise selbst erkennt.
    wrong = _collect(env, proj, paths + [f"{proj}/.claude/hooks/x.py"], 2,
                     content="print(1)\n", needle="Infrastruktur-Datei")
    assert not wrong, "Infrastruktur-Sperre greift nicht:\n" + "\n".join(wrong)


# --- AC-5 ---

def test_dotdot_via_allowed_dir_not_allowed(tmp_path):
    proj, _, env = _setup(tmp_path)
    paths = [
        f"{proj}/tests/../.claude/hooks/x.py",
        f"{proj}/docs/../.claude/hooks/x.py",
    ]
    wrong = _collect(env, proj, paths, 2, content="print(1)\n")
    assert not wrong, "`..`-Umweg über always-allowed Ordner offen:\n" + "\n".join(wrong)


# --- AC-6 ---

def test_plugin_change_unclean_blocked_clean_allowed(tmp_path):
    proj, _, env = _setup(tmp_path)
    plugin_only = json.dumps({**BASE, "enabledPlugins": {"agent-os-openspec@m": True}})

    clean = _edit(env, proj, f"{proj}/.claude/settings.json", plugin_only)
    assert clean.returncode == 0, clean.stderr

    paths = [t.format(p=proj, f="settings.json") for t in UNCLEAN]
    wrong = _collect(env, proj, paths, 2, content=plugin_only, needle="nicht eindeutig")
    assert not wrong, "Unsaubere Plugin-Änderung nicht mit 'nicht eindeutig' geblockt:\n" \
        + "\n".join(wrong)


# --- AC-7 ---

def test_home_exception_and_override_unchanged(tmp_path):
    proj, fake_home, env = _setup(tmp_path)

    # Home-Pfade ausserhalb des Projekts: nie die Orchestrator-Sperre (#48)
    for fp in (f"{fake_home}/.claude/settings.json",
               f"{fake_home}/.claude//settings.json",
               "~/.claude/settings.json"):
        r = _edit(env, proj, fp, "{}")
        assert "Orchestrator" not in r.stderr, (fp, r.stderr)

    # Mit Override-Token: saubere Schreibweise einer Orchestrator-Datei erlaubt
    _write_token(proj)
    r = _edit(env, proj, f"{proj}/.claude/settings.local.json", "{}")
    assert r.returncode == 0, r.stderr


# --- AC-11 ---

def test_variant_failure_keeps_raw_check(tmp_path):
    proj, _, env = _setup(tmp_path)
    # Null-Byte: Path.resolve() wirft ValueError; der rohe Pfad enthält das Muster
    for fp in (f"{proj}/.claude/settings.json\x00x",
               f"{proj}/.claude//settings.json\x00x"):
        r = _edit(env, proj, fp, EVIL)
        assert "Traceback" not in r.stderr, r.stderr
        assert r.returncode == 2, (fp, r.returncode, r.stderr)


# --------------------------------------------------------------------- #
# bash_gate
# --------------------------------------------------------------------- #

WF = "sandboxwf"


def _bash_sandbox(tmp_path: Path) -> Path:
    proj = tmp_path / "bproj"
    (proj / ".git").mkdir(parents=True)
    claude = proj / ".claude"
    (claude / "workflows").mkdir(parents=True)
    (claude / "active_workflow").write_text(WF + "\n")
    (claude / "workflows" / f"{WF}.json").write_text(json.dumps({
        "name": WF, "current_phase": "phase6_implement", "workflow_type": "feature",
    }))
    (claude / "settings.json").write_text(json.dumps(BASE))
    return proj


def _bash(command: str, proj: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for var in ("OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK"):
        env.pop(var, None)
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["CLAUDE_TOOL_INPUT"] = json.dumps({"command": command})
    return subprocess.run(
        [sys.executable, str(BASH_GATE)],
        cwd=str(proj), env=env, capture_output=True, text=True, timeout=60,
    )


def _bash_collect(cases, proj: Path, rc: int):
    wrong = []
    for cmd in cases:
        r = _bash(cmd, proj)
        if r.returncode != rc:
            wrong.append(f"  {cmd!r}: rc={r.returncode} (soll {rc}), "
                         f"stderr={r.stderr.strip()[:160]!r}")
    return wrong


# --- AC-8 ---

def test_bash_redirect_settings_unclean_blocked(tmp_path):
    proj = _bash_sandbox(tmp_path)
    cases = [
        "echo x > .claude//settings.json",
        "echo x > ./.claude/./settings.json",
        "echo x > .claude/../.claude/settings.json",
        "echo x | tee .claude//settings.json",
        "cp /tmp/evil.json ./.claude/./settings.json",
    ]
    wrong = _bash_collect(cases, proj, 2)
    assert not wrong, "settings.json per Bash beschreibbar:\n" + "\n".join(wrong)


# --- AC-9 ---

def test_bash_redirect_workflow_state_unclean_blocked(tmp_path):
    proj = _bash_sandbox(tmp_path)
    cases = [
        "echo x > .claude//workflows/x.json",
        "echo x > ./.claude/./workflows/x.json",
        "git status > .claude//workflows/x.json",
    ]
    wrong = _bash_collect(cases, proj, 2)
    assert not wrong, "Workflow-State per Bash beschreibbar:\n" + "\n".join(wrong)


# --- AC-10 ---

def test_bash_cd_dot_segment_blocked(tmp_path):
    proj = _bash_sandbox(tmp_path)
    cases = [
        "cd .claude/./workflows && echo x > w.json",
        "cd ./.claude//workflows && echo x > w.json",
    ]
    wrong = _bash_collect(cases, proj, 2)
    assert not wrong, "cd-Umweg offen:\n" + "\n".join(wrong)


def test_bash_clean_reads_still_allowed(tmp_path):
    """Regression (#53/#64): lesender Zugriff in unsauberer Schreibweise bleibt erlaubt."""
    proj = _bash_sandbox(tmp_path)
    cases = [
        "cat .claude//settings.json",
        "ls ./.claude/./workflows",
        "echo hallo > docs/notiz.txt",
    ]
    wrong = _bash_collect(cases, proj, 0)
    assert not wrong, "False Positive:\n" + "\n".join(wrong)
