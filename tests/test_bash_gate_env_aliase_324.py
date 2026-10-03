"""bash_gate: Aliase ueber git-Umgebungsvariablen erkennen (#324, Rest aus #299 Teil C).

Wie Teil A/B: echter Gate-Subprozess dieses Arbeitsbaums, beide Fehlerrichtungen.
"""

import inspect
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "hooks"))

from test_bash_gate_erkennung_299 import (  # noqa: E402
    BASH_GATE, _assert_allowed, _assert_blocked_as_commit, _expect, _sandbox,
)

import hook_utils  # noqa: E402


def _gate_mit_env(command: str, project_dir: Path, extra_env: dict) -> subprocess.CompletedProcess:
    import json
    env = dict(os.environ)
    for var in ("OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK"):
        env.pop(var, None)
    env.update(extra_env)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    env["CLAUDE_TOOL_INPUT"] = json.dumps({"command": command})
    return subprocess.run(
        [sys.executable, str(BASH_GATE)],
        cwd=str(project_dir), env=env, capture_output=True, text=True, timeout=60,
    )


# --- AC-1 bis AC-4: die vier Faelle aus dem Issue ------------------------------

def test_var_praefix_count_key_value_blockt(tmp_path):
    _assert_blocked_as_commit([
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit git ci -m x",
        "env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit git ci -m x",
    ], tmp_path, "#324 AC-1")


def test_export_in_anderem_segment_blockt(tmp_path):
    _assert_blocked_as_commit([
        "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit; git ci -m x",
        "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit && git ci -m x",
    ], tmp_path, "#324 AC-2")


def test_git_config_parameters_blockt(tmp_path):
    _assert_blocked_as_commit([
        "GIT_CONFIG_PARAMETERS=\"'alias.ci=commit'\" git ci -m x",
    ], tmp_path, "#324 AC-3")


def test_config_env_mit_wert_aus_praefix_blockt(tmp_path):
    _assert_blocked_as_commit([
        "X=commit git --config-env=alias.ci=X ci -m x",
        "X=commit git --config-env alias.ci=X ci -m x",
    ], tmp_path, "#324 AC-4")


# --- AC-5: unaufloesbar => nur genau dieser Aliasname ---------------------------

def test_config_env_unaufloesbar_nur_fuer_diesen_namen(tmp_path):
    root = _sandbox(tmp_path)
    wrong = _expect(["git --config-env=alias.ci=NUR_IM_GATE_ENV ci -m x"], root, 2, "Adversary verdict")
    assert not wrong, "#324 AC-5 unaufloesbar:\n" + "\n".join(wrong)
    _assert_allowed(["git --config-env=alias.ci=NUR_IM_GATE_ENV status"], root, "#324 AC-5 anderer Name")
    proc = _gate_mit_env("git --config-env=alias.ci=NUR_IM_GATE_ENV ci -m x", root,
                         {"NUR_IM_GATE_ENV": "commit"})
    assert proc.returncode == 2, f"os.environ-Zweig: rc={proc.returncode} {proc.stderr[:160]!r}"


# --- AC-6 / AC-7: Kontrollfaelle -------------------------------------------------

def test_env_alias_auf_status_bleibt_frei(tmp_path):
    _assert_allowed([
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.st GIT_CONFIG_VALUE_0=status git st",
        "GIT_CONFIG_PARAMETERS=\"'alias.st=status'\" git st",
        "X=status git --config-env=alias.st=X st",
    ], _sandbox(tmp_path), "#324 AC-6")


def test_git_status_ohne_alias_unveraendert(tmp_path):
    _assert_allowed(["git status", "git log -3", "X=1 git status"], _sandbox(tmp_path), "#324 AC-7")


# --- AC-8: kaputte Eingaben -----------------------------------------------------

KAPUTT = [
    "GIT_CONFIG_COUNT=abc git status",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci git status",
    "GIT_CONFIG_PARAMETERS=\"'alias.ci=commit\" git status",
    "git --config-env=alias.ci git status",
]


def test_kaputte_eingaben_fail_open_ohne_exception(tmp_path):
    for cmd in KAPUTT:
        hook_utils.git_subcommands(cmd)
        hook_utils.git_head_subcommands(cmd)
        hook_utils.git_runs_foreign_code(cmd)
    _assert_allowed(KAPUTT, _sandbox(tmp_path), "#324 AC-8")


KAPUTT_COUNT = "GIT_CONFIG_COUNT=²"  # Nicht-ASCII-Ziffer: isdigit() ja, int() nein (F001)


def test_count_mit_nicht_ascii_ziffer_fail_open(tmp_path):
    for cmd in (f"{KAPUTT_COUNT} git status",
                f"{KAPUTT_COUNT} GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit git ci -m x"):
        hook_utils.git_subcommands(cmd)
        hook_utils.git_head_subcommands(cmd)
        hook_utils.git_runs_foreign_code(cmd)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _assert_allowed([f"{KAPUTT_COUNT} git status"], _sandbox(tmp_path / "a"), "#324 F001 status")
    _assert_blocked_as_commit([
        f"{KAPUTT_COUNT} git commit -m x",
        f"{KAPUTT_COUNT} GIT_CONFIG_PARAMETERS=\"'alias.ci=commit'\" git ci -m x",
    ], tmp_path / "b", "#324 F001 commit")


# --- AC-9: kein Zustand, Signaturen ---------------------------------------------

def test_kein_zustand_zwischen_aufrufen_und_signaturen_stabil():
    mit = "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.zz324 GIT_CONFIG_VALUE_0=commit git zz324 -m x"
    ohne = "git zz324 -m x"
    assert "commit" in hook_utils.git_subcommands(mit), "Env-Alias muss aufgeloest werden"
    assert "commit" not in hook_utils.git_subcommands(ohne), "Zustand leckt zwischen Aufrufen"
    assert str(inspect.signature(hook_utils.git_subcommands)) == '(command: str, depth: int = 0) -> \'list[str]\''
    assert str(inspect.signature(hook_utils.git_head_subcommands)) == "(command: str) -> 'list[str]'"
    assert str(inspect.signature(hook_utils.git_runs_foreign_code)) == "(command: str) -> bool"
    assert str(inspect.signature(hook_utils.is_git_subcommand)) == "(command: str, subcommand: str) -> bool"
    helper = getattr(hook_utils, "_command_env_aliases", None)
    assert helper is not None, "_command_env_aliases fehlt"
    assert len(inspect.getsource(helper).splitlines()) <= 50
