"""#81: /70-deploy liest den Deploy-Ablauf des Projekts statt Plattform-Beispiele zu zeigen.

Der Ablauf steht unter `deploy:` in der Projekt-Config (command/verify/rollback,
optional autonomous). `workflow.py deploy-config` gibt ihn rein lesend aus; fehlt
command oder verify, meldet es DEPLOY_CONFIGURED=no und /70-deploy fragt den PO.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"


def _project(tmp_path: Path, deploy_yaml: str) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "config.yaml").write_text(deploy_yaml)
    return tmp_path


def _deploy_config(project: Path) -> str:
    env = {k: v for k, v in os.environ.items() if k not in ("OPENSPEC_FRAMEWORK",)}
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
    r = subprocess.run([sys.executable, str(HOOKS_DIR / "workflow.py"), "deploy-config"],
                       capture_output=True, text=True, env=env, cwd=str(project))
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_missing_block_is_not_configured(tmp_path):
    out = _deploy_config(_project(tmp_path, "project:\n  name: x\n"))
    assert out.splitlines()[0] == "DEPLOY_CONFIGURED=no"
    assert "command: (nicht gesetzt)" in out


def test_template_defaults_are_not_configured(tmp_path):
    yaml = 'deploy:\n  command: ""\n  verify: ""\n  rollback: ""\n  autonomous: false\n'
    assert _deploy_config(_project(tmp_path, yaml)).startswith("DEPLOY_CONFIGURED=no")


def test_command_without_verify_is_not_configured(tmp_path):
    out = _deploy_config(_project(tmp_path, 'deploy:\n  command: "./deploy.sh"\n'))
    assert out.startswith("DEPLOY_CONFIGURED=no")


def test_full_block_is_listed_in_order(tmp_path):
    yaml = ("deploy:\n  command:\n    - git push origin main\n    - ./scripts/deploy.sh\n"
            '  verify: "./scripts/verify-live.sh /"\n  rollback: "git revert HEAD"\n'
            "  autonomous: true\n")
    out = _deploy_config(_project(tmp_path, yaml)).splitlines()
    assert out[0] == "DEPLOY_CONFIGURED=yes"
    assert out[1:3] == ["command: git push origin main", "command: ./scripts/deploy.sh"]
    assert "verify: ./scripts/verify-live.sh /" in out
    assert "rollback: git revert HEAD" in out
    assert "autonomous: true" in out


def test_framework_template_ships_empty_block():
    import yaml
    cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())
    assert set(cfg["deploy"]) == {"command", "verify", "rollback", "autonomous"}
    assert cfg["deploy"]["autonomous"] is False


@pytest.mark.parametrize("path", [
    REPO_ROOT / "core" / "commands" / "70-deploy.md",
    REPO_ROOT / "skills" / "70-deploy" / "SKILL.md",
])
def test_command_has_no_platform_examples_and_reads_config(path):
    text = path.read_text()
    for word in ("vercel", "heroku", "gcloud", "aws ecs", "checkout production",
                 "CUSTOMIZE THIS FILE", "This is a template"):
        assert word.lower() not in text.lower(), (path, word)
    assert "deploy-config" in text
    assert "DEPLOY_CONFIGURED=no" in text


def test_deploy_config_call_passes_bash_gate(tmp_path):
    project = _project(tmp_path, "project:\n  name: x\n")
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_TOOL_INPUT", "OPENSPEC_FRAMEWORK")}
    env["CLAUDE_PROJECT_DIR"] = str(project)
    r = subprocess.run([sys.executable, str(HOOKS_DIR / "bash_gate.py")],
                       input=json.dumps({"tool_input": {"command":
                                         "python3 .claude/hooks/workflow.py deploy-config"}}),
                       capture_output=True, text=True, env=env, cwd=str(project))
    assert r.returncode == 0, r.stderr
