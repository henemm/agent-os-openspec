"""Kontext-Haushalt: Messung der Kontextgroesse, `workflow.py context`, `workflow.py batch`,
`ship.py` und die Regeln in den Phasen-Befehlen.

Hintergrund (Token-Analyse): 70-75 % des Wiederlesens entstehen in Schritten mit ueber
100k Token Kontext; ein Schritt mit 200k kostet etwa das Fuenffache eines Schritts
mit 40k. Die Schwelle fuer den Schnitt liegt deshalb bei 100k, nicht bei 200k.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "core" / "hooks"
COMMANDS = REPO / "core" / "commands"
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(SCRIPTS))

import hook_utils  # noqa: E402
import ship  # noqa: E402

CONFIG = "context_budget:\n  enabled: true\n  clear_threshold_tokens: 100000\n"


def _project(tmp_path: Path, config: str = CONFIG) -> Path:
    hooks = tmp_path / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    for f in HOOKS.glob("*.py"):
        shutil.copy(f, hooks / f.name)
    (tmp_path / ".claude" / "config.yaml").write_text(config)
    subprocess.run(["git", "init", "-q", "."], cwd=tmp_path, check=True)
    return tmp_path


def _env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("OPENSPEC_", "HERDR_")) and k != "CLAUDE_CODE_SESSION_ID"}
    env.update(extra)
    return env


def _run(root: Path, script: str, *args: str, env: "dict | None" = None,
         stdin: "str | None" = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(root / ".claude" / "hooks" / script), *args],
                          cwd=root, env=env or _env(), capture_output=True, text=True,
                          input=stdin, timeout=60)


def _transcript(path: Path, tokens: int, trailing_sidechain: bool = True) -> Path:
    rows = [{"type": "user", "message": {}},
            {"type": "assistant", "message": {"usage": {
                "input_tokens": 40, "cache_creation_input_tokens": 2000,
                "cache_read_input_tokens": tokens - 2040, "output_tokens": 5}}}]
    if trailing_sidechain:
        rows.append({"type": "assistant", "isSidechain": True,
                     "message": {"usage": {"input_tokens": 5, "cache_read_input_tokens": 999_999}}})
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def _payload(transcript: Path, session: str = "s1") -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"},
                       "tool_response": {"stdout": "", "stderr": ""},
                       "session_id": session, "transcript_path": str(transcript)})


# --- Messung -----------------------------------------------------------------

def test_transcript_tokens_sum_last_main_assistant(tmp_path):
    tr = _transcript(tmp_path / "t.jsonl", 122_040)
    assert hook_utils.context_tokens_from_transcript(tr) == 122_040


def test_transcript_tokens_read_from_tail(tmp_path):
    tr = tmp_path / "t.jsonl"
    filler = json.dumps({"type": "user", "message": {"content": "x" * 2000}}) + "\n"
    tr.write_text(filler * 400)  # > 512 KiB vor der letzten Antwort
    with open(tr, "a") as fh:
        fh.write(json.dumps({"type": "assistant", "message": {"usage": {
            "input_tokens": 10, "cache_read_input_tokens": 50_000}}}) + "\n")
    assert hook_utils.context_tokens_from_transcript(tr) == 50_010


def test_transcript_tokens_none_without_usage(tmp_path):
    tr = tmp_path / "t.jsonl"
    tr.write_text(json.dumps({"type": "assistant", "message": {}}) + "\nnot json\n")
    assert hook_utils.context_tokens_from_transcript(tr) is None
    assert hook_utils.context_tokens_from_transcript(tmp_path / "missing.jsonl") is None


@pytest.mark.parametrize("tokens,bucket", [(99_999, 0), (100_000, 1), (149_999, 1), (150_000, 2), (210_000, 3)])
def test_context_bucket(tokens, bucket):
    assert hook_utils.context_bucket(tokens, 100_000) == bucket


def test_settings_default_literal_false_and_bad_threshold():
    assert hook_utils.context_budget_settings({}) == {"enabled": True, "threshold": 100_000}
    assert hook_utils.context_budget_settings({"context_budget": {"enabled": False}})["enabled"] is False
    assert hook_utils.context_budget_settings({"context_budget": {"enabled": "no"}})["enabled"] is True
    assert hook_utils.context_budget_settings({"context_budget": {"clear_threshold_tokens": 120_000}})["threshold"] == 120_000
    assert hook_utils.context_budget_settings({"context_budget": {"clear_threshold_tokens": "1e5"}})["threshold"] == 100_000
    assert hook_utils.context_budget_settings({"context_budget": {"clear_threshold_tokens": 10}})["threshold"] == 100_000


def test_cut_note_keeps_sentence_commas_and_formats_numbers():
    note = hook_utils.context_cut_note(168_464, 100_000)
    assert "~168.464 Token" in note and "Schwelle 100.000" in note
    assert "Spec fertig, PR angelegt" in note
    assert "Explore-Teilagenten" in note and "workflow.py batch" in note


# --- post_bash: Hinweis einmal je Stufe, Messung je Sitzung -------------------

def test_post_bash_announces_once_per_bucket(tmp_path):
    root = _project(tmp_path)
    tr = _transcript(root / "t.jsonl", 122_040)
    first = _run(root, "post_bash.py", stdin=_payload(tr))
    assert first.returncode == 0, first.stderr
    out = json.loads(first.stdout)
    note = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert note.startswith("KONTEXT-SCHWELLE") and "~122.040" in note
    second = _run(root, "post_bash.py", stdin=_payload(tr))
    assert second.returncode == 0 and second.stdout.strip() == ""
    usage = json.loads((root / ".claude" / "context_usage" / "s1.json").read_text())
    assert usage["tokens"] == 122_040 and usage["announced_bucket"] == 1
    # naechste Stufe (+50k) -> erneuter Hinweis
    _transcript(tr, 175_000)
    third = _run(root, "post_bash.py", stdin=_payload(tr))
    assert "KONTEXT-SCHWELLE" in third.stdout
    usage = json.loads((root / ".claude" / "context_usage" / "s1.json").read_text())
    assert usage["tokens"] == 175_000 and usage["announced_bucket"] == 2


def test_post_bash_below_threshold_records_silently(tmp_path):
    root = _project(tmp_path)
    tr = _transcript(root / "t.jsonl", 40_000)
    res = _run(root, "post_bash.py", stdin=_payload(tr))
    assert res.returncode == 0 and res.stdout.strip() == ""
    usage = json.loads((root / ".claude" / "context_usage" / "s1.json").read_text())
    assert usage["tokens"] == 40_000 and usage["announced_bucket"] == 0


def test_post_bash_disabled_by_literal_false(tmp_path):
    root = _project(tmp_path, "context_budget:\n  enabled: false\n")
    tr = _transcript(root / "t.jsonl", 122_040)
    res = _run(root, "post_bash.py", stdin=_payload(tr))
    assert res.returncode == 0 and res.stdout.strip() == ""
    assert not (root / ".claude" / "context_usage").exists()


def test_post_bash_other_session_not_confused_by_newest_file(tmp_path):
    root = _project(tmp_path)
    tr = _transcript(root / "t.jsonl", 122_040)
    _run(root, "post_bash.py", stdin=_payload(tr, "s1"))
    res = _run(root, "post_bash.py", stdin=_payload(tr, "s2"))
    assert "KONTEXT-SCHWELLE" in res.stdout  # eigene Sitzung, eigener erster Hinweis


# --- workflow.py context -------------------------------------------------------

def test_workflow_context_unknown_without_measurement(tmp_path):
    root = _project(tmp_path)
    res = _run(root, "workflow.py", "context")
    assert res.returncode == 0
    assert res.stdout.splitlines() == ["CONTEXT_TOKENS=unknown", "CONTEXT_CUT=off"]


def test_workflow_context_on_for_session_and_newest_fallback(tmp_path):
    root = _project(tmp_path)
    tr = _transcript(root / "t.jsonl", 122_040)
    _run(root, "post_bash.py", stdin=_payload(tr, "s1"))
    res = _run(root, "workflow.py", "context", env=_env(CLAUDE_CODE_SESSION_ID="s1"))
    assert res.stdout.splitlines() == ["CONTEXT_TOKENS=122040", "CONTEXT_CUT=on"]
    res = _run(root, "workflow.py", "context")  # ohne Sitzungs-Id: juengste Messung
    assert res.stdout.splitlines() == ["CONTEXT_TOKENS=122040", "CONTEXT_CUT=on"]


def test_workflow_context_off_below_threshold_from_config(tmp_path):
    root = _project(tmp_path, "context_budget:\n  clear_threshold_tokens: 200000\n")
    tr = _transcript(root / "t.jsonl", 122_040)
    _run(root, "post_bash.py", stdin=_payload(tr, "s1"))
    res = _run(root, "workflow.py", "context", env=_env(CLAUDE_CODE_SESSION_ID="s1"))
    assert res.stdout.splitlines() == ["CONTEXT_TOKENS=122040", "CONTEXT_CUT=off"]


# --- workflow.py batch ---------------------------------------------------------

def _started(tmp_path: Path) -> "tuple[Path, dict]":
    root = _project(tmp_path)
    res = _run(root, "workflow.py", "start", "demo-wf")
    assert res.returncode == 0, res.stderr
    return root, _env(OPENSPEC_ACTIVE_WORKFLOW="demo-wf")


def test_batch_runs_steps_in_order(tmp_path):
    root, env = _started(tmp_path)
    res = _run(root, "workflow.py", "batch", "status", "--", "phase", "phase1_context",
               "--", "autonomy", "--", "context", env=env)
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    heads = [l for l in lines if l.startswith("# batch ")]
    assert heads == ["# batch 1/4: status", "# batch 2/4: phase phase1_context",
                     "# batch 3/4: autonomy", "# batch 4/4: context"]
    assert "AUTONOMY=manual" in lines and "CONTEXT_CUT=off" in lines
    state = json.loads((root / ".claude" / "workflows" / "demo-wf.json").read_text())
    assert state["current_phase"] == "phase1_context"


def test_batch_stops_at_first_failure_with_its_exit_code(tmp_path):
    root, env = _started(tmp_path)
    res = _run(root, "workflow.py", "batch", "autonomy", "--", "phase", "phase9_bogus",
               "--", "status", env=env)
    assert res.returncode == 1
    assert "# batch 3/3" not in res.stdout
    assert "Schritt 2/3 `phase` endete mit Exit 1; 1 Schritt(e) nicht ausgefuehrt" in res.stderr


def test_batch_rejects_unknown_nested_and_empty(tmp_path):
    root, env = _started(tmp_path)
    res = _run(root, "workflow.py", "batch", "autonomy", "--", "nope", env=env)
    assert res.returncode == 1 and "unbekannter Befehl 'nope'" in res.stderr
    res = _run(root, "workflow.py", "batch", "batch", "status", env=env)
    assert res.returncode == 1 and "unbekannter Befehl 'batch'" in res.stderr
    res = _run(root, "workflow.py", "batch", env=env)
    assert res.returncode == 1 and "Usage: workflow.py batch" in res.stderr


# --- ship.py -----------------------------------------------------------------

def test_ship_classify_rollup():
    assert ship.classify([]) == ("none", [])
    assert ship.classify([{"__typename": "CheckRun", "name": "tests", "status": "IN_PROGRESS"}]) == ("pending", [])
    assert ship.classify([
        {"__typename": "CheckRun", "name": "tests", "status": "COMPLETED", "conclusion": "FAILURE"},
        {"__typename": "StatusContext", "context": "lint", "state": "SUCCESS"},
    ]) == ("red", ["tests"])
    assert ship.classify([
        {"__typename": "CheckRun", "name": "a", "status": "COMPLETED", "conclusion": "SKIPPED"},
        {"__typename": "StatusContext", "context": "b", "state": "SUCCESS"},
    ]) == ("green", [])
    assert ship.classify([{"__typename": "StatusContext", "context": "b", "state": "PENDING"}]) == ("pending", [])
    assert ship.classify([{"__typename": "StatusContext", "context": "b", "state": "ERROR"}]) == ("red", ["b"])


def _git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("x\n")
    subprocess.run(["git", "-c", "user.email=t@t.invalid", "-c", "user.name=T", "-c", "commit.gpgsign=false",
                    "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t.invalid", "-c", "user.name=T", "-c", "commit.gpgsign=false",
                    "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def _ship(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / "ship.py"), *args], cwd=root,
                          env=_env(), capture_output=True, text=True, timeout=60)


def test_ship_refuses_default_branch_without_branch_flag(tmp_path):
    root = _git_repo(tmp_path)
    res = _ship(root, "--dry-run")
    assert res.returncode == 2 and "Default-Branch" in res.stderr and "--branch" in res.stderr


def test_ship_dry_run_on_feature_branch_prints_plan(tmp_path):
    root = _git_repo(tmp_path)
    subprocess.run(["git", "switch", "-q", "-c", "feat-1"], cwd=root, check=True)
    res = _ship(root, "--dry-run", "--merge", "squash")
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "BRANCH=feat-1"
    assert "git push -u origin feat-1" in res.stderr and "gh pr merge --squash" in res.stderr


def test_ship_dry_run_with_branch_flag_from_default(tmp_path):
    root = _git_repo(tmp_path)
    subprocess.run(["git", "switch", "-q", "-c", "feat-1"], cwd=root, check=True)
    subprocess.run(["git", "switch", "-q", "main"], cwd=root, check=True)
    res = _ship(root, "--dry-run", "--branch", "feat-1")  # Name belegt -> Suffix -2
    assert res.returncode == 0, res.stderr
    assert "BRANCH=feat-1-2" in res.stdout
    assert subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root,
                          capture_output=True, text=True).stdout.strip() == "main"  # dry-run wechselt nicht


# --- Befehle, Config, Doku -------------------------------------------------------

@pytest.mark.parametrize("name,follow", [("10-context.md", "20-analyse"), ("20-analyse.md", "30-write-spec"),
                                         ("30-write-spec.md", "40-tdd-red"), ("40-tdd-red.md", "50-implement"),
                                         ("50-implement.md", "60-validate")])
def test_phase_commands_stop_chain_at_context_cut(name, follow):
    text = (COMMANDS / name).read_text()
    para = next(p for p in text.split("\n\n") if "CONTEXT_CUT=on" in p)
    assert "workflow.py context" in para
    assert f"`{follow}` NICHT selbst aufrufen" in para
    assert f"❗Du-Zeile `/{follow} #<N>`" in para
    assert "Default 100.000 Token" in para


def test_lookup_rule_in_context_and_implement():
    for name in ("10-context.md", "50-implement.md"):
        text = (COMMANDS / name).read_text()
        assert "Explore-Teilagenten" in text and "Zeilenbereich" in text and "workflow.py batch" in text


def test_validate_offers_ship_script():
    text = (COMMANDS / "60-validate.md").read_text()
    assert "ship.py" in text and "--merge squash" in text and "FAILED_CHECKS=" in text


def test_config_yaml_has_context_budget_section():
    import yaml
    cfg = yaml.safe_load((REPO / "config.yaml").read_text())
    assert cfg["context_budget"] == {"enabled": True, "clear_threshold_tokens": 100000}


def test_orchestration_template_has_lookup_agent():
    text = (REPO / "templates" / "agent_orchestration.md").read_text()
    assert "### Nachschlage-Agent (1x Explore/Haiku)" in text


def test_gitignore_covers_context_usage():
    assert ".claude/context_usage/" in (REPO / ".gitignore").read_text()
