"""/70-deploy bei deploy.autonomous fuer Claude aufrufbar (Issue #707).

Spec: docs/specs/feat-707-deploy-selbst.md (AC-1 bis AC-8).

Vertraege, die diese Tests festlegen (aus der Spec):
- Neuer PreToolUse-Hook `core/hooks/skill_gate.py` (Matcher `Skill`): Payload aus
  stdin-JSON, Env-Fallback `CLAUDE_TOOL_NAME`/`CLAUDE_TOOL_INPUT`; Skill-Name aus
  `tool_input["skill"]`, normalisiert ohne fuehrendes `/` und ohne
  `agent-os-openspec:`. `70-deploy` nur bei `workflow.deploy_autonomous() is True`
  (Exit 0), sonst Exit 2 mit deutscher Meldung (PO, `/70-deploy`). Alles andere Exit 0.
- `skills/70-deploy/SKILL.md`: `disable-model-invocation: false`; der Alias bleibt
  Vollkopie (feste Liste in `alias_sync`).
- `deploy_autonomous()`: in einer Worktree-Sitzung gilt der gemergte Stand
  (`git show <origin/HEAD-Ziel>:<relpfad>`), sofern die Config im Haupt-Ordner
  gegenueber dessen HEAD unveraendert ist; sonst wie bisher der Haupt-Ordner.

Die Hooks laufen als echte Subprozesse in temporaeren Projekten; die
Worktree-Tests bauen ein echtes Git-Setup (bare origin, Haupt-Klon, Worktree).
AC-8 sichert bestehendes Verhalten (#550) ab und besteht voraussichtlich schon
vor der Umsetzung, ebenso die Rueckfall-Faelle aus AC-6.
"""

import importlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
SKILL_GATE = HOOKS_DIR / "skill_gate.py"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
SCRIPTS = REPO_ROOT / "scripts"
SKILLS_DIR = REPO_ROOT / "skills"
COMMANDS_DIR = REPO_ROOT / "core" / "commands"
ALIAS_DIR = REPO_ROOT / ".claude" / "commands"

DEPLOY_BASE = "deploy:\n  command: \"echo deploy\"\n  verify: \"echo verify\"\n"
CFG_AUTO_TRUE = DEPLOY_BASE + "  autonomous: true\n"
CFG_AUTO_FALSE = DEPLOY_BASE + "  autonomous: false\n"
CFG_AUTO_STRING = DEPLOY_BASE + "  autonomous: \"true\"\n"
CFG_AUTO_MISSING = DEPLOY_BASE
CFG_INVALID = "deploy: [unclosed\n  autonomous: true\n  : : :\n"


# --- Helpers ---------------------------------------------------------------

def _clean_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("OPENSPEC_", "CLAUDE_TOOL_", "HERDR_", "STUB_"))
           and k not in ("CLAUDE_PROJECT_DIR",)}
    env.update(extra)
    return env


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = _clean_env(
        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
    )
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                          env=env, check=check, timeout=30)


def _sub(base: Path, name: str) -> Path:
    path = base / name
    path.mkdir()
    return path


def _project(tmp_path: Path, config: "str | None") -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    _git(proj, "init", "-q")
    (proj / "_home").mkdir()
    if config is not None:
        (proj / "openspec.yaml").write_text(config)
    return proj


def _run_gate(proj: Path, payload, *, stdin_raw: "str | None" = None,
              env_extra: "dict | None" = None) -> subprocess.CompletedProcess:
    env = _clean_env(CLAUDE_PROJECT_DIR=str(proj), HOME=str(proj / "_home"))
    if env_extra:
        env.update(env_extra)
    stdin = stdin_raw if stdin_raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(SKILL_GATE)], input=stdin,
                          capture_output=True, text=True, env=env, cwd=str(proj),
                          timeout=30)


def _skill_payload(name: str, args: str = "#42") -> dict:
    return {"tool_name": "Skill", "tool_input": {"skill": name, "args": args}}


def _alias_sync():
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    import alias_sync  # noqa: PLC0415
    return alias_sync


def _load_script(name: str):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def _hooks_json() -> dict:
    return json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))


def _skill_groups(pretool_groups: list) -> list:
    return [g for g in pretool_groups if g.get("matcher") == "Skill"]


def _group_mentions(group: dict, needle: str) -> bool:
    return any(needle in h.get("command", "") for h in group.get("hooks", []))


def _frontmatter(text: str) -> str:
    lines = text.split("\n")
    assert lines and lines[0].rstrip() == "---", text[:200]
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return "\n".join(lines[1:i])
    raise AssertionError("Frontmatter nicht geschlossen")


def _section(text: str, heading_re: str) -> str:
    """Abschnitt ab der passenden Ueberschrift bis zur naechsten gleich-/hoeherrangigen."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(#+)\s+(.*)$", line)
        if m and re.search(heading_re, m.group(2)):
            level = len(m.group(1))
            out = [line]
            for nxt in lines[i + 1:]:
                m2 = re.match(r"^(#+)\s+", nxt)
                if m2 and len(m2.group(1)) <= level:
                    break
                out.append(nxt)
            return "\n".join(out)
    return ""


# --- Worktree-Setup (AC-6) -------------------------------------------------

def _git_setup(tmp_path: Path, origin_cfg: str, main_cfg: str) -> "tuple[Path, Path, Path]":
    """bare origin + Haupt-Klon (Stand `main_cfg`, sauber) + Worktree.

    Danach liegt auf origin ein neuerer Commit mit `origin_cfg`; der Haupt-Klon hat
    ihn per `git fetch` gesehen, aber nicht gemergt (Haupt-Ordner ist hinterher).
    """
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))

    seed = tmp_path / "seed"
    _git(tmp_path, "clone", "-q", str(origin), str(seed))
    _git(seed, "checkout", "-q", "-b", "main")
    (seed / "openspec.yaml").write_text(main_cfg)
    _git(seed, "add", "openspec.yaml")
    _git(seed, "commit", "-q", "-m", "main cfg")
    _git(seed, "push", "-q", "origin", "main")

    main = tmp_path / "main"
    _git(tmp_path, "clone", "-q", str(origin), str(main))
    (main / "_home").mkdir()
    # .gitignore lokal ueber info/exclude, damit _home den Status nicht beeinflusst
    (main / ".git" / "info" / "exclude").write_text("_home/\n.claude/\n")
    _git(main, "remote", "set-head", "origin", "main")

    if origin_cfg != main_cfg:
        (seed / "openspec.yaml").write_text(origin_cfg)
        _git(seed, "commit", "-q", "-am", "origin cfg")
        _git(seed, "push", "-q", "origin", "main")
        _git(main, "fetch", "-q", "origin")
        # Haupt-Ordner bleibt bewusst hinterher
        assert (main / "openspec.yaml").read_text() == main_cfg

    wt = tmp_path / "wt"
    _git(main, "worktree", "add", "-q", "-b", "feature", str(wt))
    return origin, main, wt


def _deploy_autonomous_in(cwd: Path, home: Path, project_dir: "Path | None" = None) -> str:
    code = (f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r}); import workflow; "
            "print(workflow.deploy_autonomous())")
    env = _clean_env(HOME=str(home), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    res = subprocess.run([sys.executable, "-c", code], cwd=str(cwd), capture_output=True,
                         text=True, env=env, timeout=30)
    assert res.returncode == 0, (res.stdout, res.stderr)
    return res.stdout.strip().splitlines()[-1]


# --- AC-1 -------------------------------------------------------------------

@pytest.mark.parametrize("config,skill", [
    (CFG_AUTO_MISSING, "70-deploy"),
    (CFG_AUTO_FALSE, "70-deploy"),
    (CFG_AUTO_STRING, "70-deploy"),
    (CFG_INVALID, "70-deploy"),
    (None, "70-deploy"),
    (CFG_AUTO_FALSE, "agent-os-openspec:70-deploy"),
    (CFG_AUTO_FALSE, "/70-deploy"),
    (CFG_AUTO_MISSING, "/agent-os-openspec:70-deploy"),
], ids=["fehlt", "false", "string-true", "unlesbar", "keine-config",
        "plugin-praefix", "slash", "slash-plugin-praefix"])
def test_blocks_70_deploy_without_autonomous(tmp_path, config, skill):
    assert SKILL_GATE.exists(), "core/hooks/skill_gate.py fehlt"
    proj = _project(tmp_path, config)
    res = _run_gate(proj, _skill_payload(skill))
    assert res.returncode == 2, (res.returncode, res.stdout, res.stderr)
    assert "PO" in res.stderr, res.stderr
    assert "/70-deploy" in res.stderr, res.stderr


# --- AC-2 -------------------------------------------------------------------

@pytest.mark.parametrize("skill", ["70-deploy", "agent-os-openspec:70-deploy", "/70-deploy"])
def test_allows_70_deploy_with_autonomous_true(tmp_path, skill):
    assert SKILL_GATE.exists(), "core/hooks/skill_gate.py fehlt"
    proj = _project(tmp_path, CFG_AUTO_TRUE)
    res = _run_gate(proj, _skill_payload(skill))
    assert res.returncode == 0, (res.returncode, res.stdout, res.stderr)


# --- AC-3 -------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    _skill_payload("60-validate"),
    _skill_payload("agent-os-openspec:50-implement"),
    _skill_payload("/00-intake", "#1"),
    _skill_payload("70-deploy-extra"),
    {"tool_name": "Bash", "tool_input": {"command": "echo /70-deploy"}},
    {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}},
], ids=["60-validate", "plugin-50", "slash-00", "aehnlicher-name", "bash", "read"])
def test_other_skills_and_tools_always_allowed(tmp_path, payload):
    assert SKILL_GATE.exists(), "core/hooks/skill_gate.py fehlt"
    proj = _project(tmp_path, CFG_AUTO_FALSE)
    res = _run_gate(proj, payload)
    assert res.returncode == 0, (payload, res.returncode, res.stdout, res.stderr)


@pytest.mark.parametrize("stdin_raw", [
    "",
    "{not json",
    json.dumps({"tool_name": "Skill", "tool_input": "kaputt"}),
    json.dumps({"tool_name": "Skill", "tool_input": {"args": "#1"}}),
    json.dumps({"tool_name": "Skill", "tool_input": {"skill": None}}),
    json.dumps({"tool_name": "Bash"}),
    json.dumps([1, 2, 3]),
], ids=["leer", "kein-json", "input-string", "ohne-skill", "skill-none", "bash-ohne-input",
        "liste"])
def test_malformed_payload_non_deploy_allowed(tmp_path, stdin_raw):
    assert SKILL_GATE.exists(), "core/hooks/skill_gate.py fehlt"
    proj = _project(tmp_path, CFG_AUTO_FALSE)
    res = _run_gate(proj, None, stdin_raw=stdin_raw)
    assert res.returncode == 0, (stdin_raw, res.returncode, res.stdout, res.stderr)


def test_payload_env_fallback(tmp_path):
    assert SKILL_GATE.exists(), "core/hooks/skill_gate.py fehlt"
    proj = _project(tmp_path, CFG_AUTO_FALSE)
    deploy_env = {"CLAUDE_TOOL_NAME": "Skill",
                  "CLAUDE_TOOL_INPUT": json.dumps({"skill": "70-deploy", "args": "#42"})}
    res = _run_gate(proj, None, stdin_raw="", env_extra=deploy_env)
    assert res.returncode == 2, (res.returncode, res.stdout, res.stderr)
    assert "/70-deploy" in res.stderr, res.stderr

    other_env = {"CLAUDE_TOOL_NAME": "Skill",
                 "CLAUDE_TOOL_INPUT": json.dumps({"skill": "60-validate"})}
    res = _run_gate(proj, None, stdin_raw="", env_extra=other_env)
    assert res.returncode == 0, (res.returncode, res.stdout, res.stderr)

    proj_true = _project(_sub(tmp_path, "t"), CFG_AUTO_TRUE)
    res = _run_gate(proj_true, None, stdin_raw="", env_extra=deploy_env)
    assert res.returncode == 0, (res.returncode, res.stdout, res.stderr)


# --- AC-4 -------------------------------------------------------------------

def test_skill_flag_false_and_alias_full_copy():
    text = (SKILLS_DIR / "70-deploy" / "SKILL.md").read_text()
    fm = _frontmatter(text)
    assert re.search(r"^disable-model-invocation:\s*false\s*$", fm, re.M), fm
    assert not re.search(r"^disable-model-invocation:\s*true\s*$", fm, re.M), fm

    sync = _alias_sync()
    assert sync.embeds_full_skill(text) is True
    alias = sync.alias_content("70-deploy", text)
    assert sync.ALIAS_MARKER in alias
    # Vollkopie: ohne Marker-Zeile exakt der Skill-Text, kein Redirect
    assert alias.replace(sync.ALIAS_MARKER + "\n", "", 1) == text
    assert "/agent-os-openspec:70-deploy $ARGUMENTS" not in alias


def test_embeds_full_skill_other_skills_unchanged():
    sync = _alias_sync()
    full = set()
    for name in sync.skill_names(SKILLS_DIR):
        if name == "70-deploy":
            continue
        text = (SKILLS_DIR / name / "SKILL.md").read_text()
        expected = "disable-model-invocation: true" in text
        assert sync.embeds_full_skill(text) is expected, name
        if expected:
            full.add(name)
    assert full == {"80-workflow", "81-add-artifact", "99-reset"}, full

    # synthetische Faelle: Semantik ueber das Flag bleibt
    assert sync.embeds_full_skill("---\ndescription: x\ndisable-model-invocation: true\n---\n# X\n")
    assert not sync.embeds_full_skill(
        "---\ndescription: x\ndisable-model-invocation: false\n---\n# X\n")
    impl = (SKILLS_DIR / "50-implement" / "SKILL.md").read_text()
    assert sync.embeds_full_skill(impl) is False


def test_committed_alias_not_stale():
    sync = _alias_sync()
    text = (SKILLS_DIR / "70-deploy" / "SKILL.md").read_text()
    committed = (ALIAS_DIR / "70-deploy.md").read_text()
    assert committed == sync.alias_content("70-deploy", text)
    # die committete Vollkopie traegt den neuen Flag-Stand
    assert re.search(r"^disable-model-invocation:\s*false\s*$", _frontmatter(committed), re.M)
    assert sync.find_stale_aliases(SKILLS_DIR, ALIAS_DIR) == []


# --- AC-5 -------------------------------------------------------------------

def test_hooks_json_registers_skill_gate():
    pre = _hooks_json()["hooks"]["PreToolUse"]
    groups = _skill_groups(pre)
    assert len(groups) == 1, groups
    assert _group_mentions(groups[0], "skill_gate.py"), groups[0]
    cmds = [h["command"] for h in groups[0]["hooks"]]
    assert any(re.match(r"^\$\{CLAUDE_PLUGIN_ROOT\}/core/hooks/skill_gate\.py", c) for c in cmds), cmds


def test_cloud_hooks_in_sync():
    res = subprocess.run([sys.executable, str(SCRIPTS / "sync_cloud_hooks.py"), "--check"],
                         capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60)
    assert res.returncode == 0, (res.stdout, res.stderr)
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    groups = _skill_groups(settings["hooks"]["PreToolUse"])
    assert len(groups) == 1, groups
    assert _group_mentions(groups[0], "skill_gate.py"), groups[0]


def test_consumer_hooks_mirror():
    mod = _load_script("sync_cloud_hooks")
    block = mod.consumer_hooks(_hooks_json())
    groups = _skill_groups(block["PreToolUse"])
    assert len(groups) == 1, groups
    assert _group_mentions(groups[0], "skill_gate.py"), groups[0]


# --- AC-6 -------------------------------------------------------------------

def test_worktree_reads_origin_value(tmp_path):
    _, main, wt = _git_setup(tmp_path, origin_cfg=CFG_AUTO_TRUE, main_cfg=CFG_AUTO_FALSE)
    assert _deploy_autonomous_in(wt, main / "_home") == "True"
    assert _deploy_autonomous_in(wt, main / "_home", project_dir=wt) == "True"


def test_worktree_dirty_main_uses_main_value(tmp_path):
    _, main, wt = _git_setup(tmp_path, origin_cfg=CFG_AUTO_TRUE, main_cfg=CFG_AUTO_FALSE)
    # lokale, nicht committete Aenderung im Haupt-Ordner -> deren Wert gilt
    (main / "openspec.yaml").write_text(CFG_AUTO_MISSING + "  # lokal\n")
    assert _deploy_autonomous_in(wt, main / "_home", project_dir=wt) == "False"

    _, main2, wt2 = _git_setup(_sub(tmp_path, "b"), origin_cfg=CFG_AUTO_FALSE,
                               main_cfg=CFG_AUTO_FALSE)
    (main2 / "openspec.yaml").write_text(CFG_AUTO_TRUE)
    assert _deploy_autonomous_in(wt2, main2 / "_home", project_dir=wt2) == "True"


def test_worktree_no_origin_head_falls_back(tmp_path):
    _, main, wt = _git_setup(tmp_path, origin_cfg=CFG_AUTO_TRUE, main_cfg=CFG_AUTO_FALSE)
    _git(main, "remote", "set-head", "origin", "-d")
    assert _git(main, "symbolic-ref", "-q", "refs/remotes/origin/HEAD",
                check=False).returncode != 0
    assert _deploy_autonomous_in(wt, main / "_home", project_dir=wt) == "False"


def test_worktree_git_error_falls_back(tmp_path):
    _, main, wt = _git_setup(tmp_path, origin_cfg=CFG_AUTO_TRUE, main_cfg=CFG_AUTO_FALSE)
    # origin/HEAD zeigt auf einen nicht existierenden Zweig -> git show scheitert
    _git(main, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/gibtsnicht")
    assert _git(main, "show", "origin/HEAD:openspec.yaml", check=False).returncode != 0
    assert _deploy_autonomous_in(wt, main / "_home", project_dir=wt) == "False"


def test_non_worktree_unchanged(tmp_path):
    _, main, _ = _git_setup(tmp_path, origin_cfg=CFG_AUTO_TRUE, main_cfg=CFG_AUTO_FALSE)
    assert _deploy_autonomous_in(main, main / "_home") == "False"
    assert _deploy_autonomous_in(main, main / "_home", project_dir=main) == "False"

    _, main2, _ = _git_setup(_sub(tmp_path, "b"), origin_cfg=CFG_AUTO_FALSE,
                             main_cfg=CFG_AUTO_TRUE)
    assert _deploy_autonomous_in(main2, main2 / "_home", project_dir=main2) == "True"


def test_origin_revocation_wins(tmp_path):
    _, main, wt = _git_setup(tmp_path, origin_cfg=CFG_AUTO_FALSE, main_cfg=CFG_AUTO_TRUE)
    assert _deploy_autonomous_in(wt, main / "_home", project_dir=wt) == "False"


def _call_gate_inprocess(monkeypatch, proj: Path, payload: dict, autonomous: bool) -> int:
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    monkeypatch.setattr(workflow, "deploy_autonomous", lambda: autonomous)
    sys.modules.pop("skill_gate", None)
    spec = importlib.util.spec_from_file_location("skill_gate", SKILL_GATE)
    gate = importlib.util.module_from_spec(spec)
    sys.modules["skill_gate"] = gate
    spec.loader.exec_module(gate)
    if hasattr(gate, "deploy_autonomous"):
        monkeypatch.setattr(gate, "deploy_autonomous", lambda: autonomous)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    try:
        rc = gate.main()
    except SystemExit as exc:
        rc = exc.code
    finally:
        sys.modules.pop("skill_gate", None)
    return 0 if rc is None else int(rc)


def test_skill_gate_uses_deploy_autonomous(tmp_path, monkeypatch):
    assert SKILL_GATE.exists(), "core/hooks/skill_gate.py fehlt"
    assert "deploy_autonomous" in SKILL_GATE.read_text(encoding="utf-8")
    for key in ("CLAUDE_TOOL_NAME", "CLAUDE_TOOL_INPUT"):
        monkeypatch.delenv(key, raising=False)

    # Config sagt false, die Funktion sagt True -> erlaubt (Funktion ist die Quelle)
    proj_false = _project(_sub(tmp_path, "f"), CFG_AUTO_FALSE)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj_false))
    assert _call_gate_inprocess(monkeypatch, proj_false, _skill_payload("70-deploy"), True) == 0

    # Config sagt true, die Funktion sagt False -> blockiert
    proj_true = _project(_sub(tmp_path, "t"), CFG_AUTO_TRUE)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj_true))
    assert _call_gate_inprocess(monkeypatch, proj_true, _skill_payload("70-deploy"), False) == 2


# --- AC-7 -------------------------------------------------------------------

def test_70_deploy_step0_text():
    for path in (COMMANDS_DIR / "70-deploy.md", SKILLS_DIR / "70-deploy" / "SKILL.md"):
        text = path.read_text(encoding="utf-8")
        step0 = _section(text, r"^Step 0\b")
        assert step0, f"{path}: kein 'Step 0'-Abschnitt"
        assert "deploy-config" in step0, step0
        assert "autonomous" in step0, step0
        assert "❗ Du:" in step0, step0
        assert "/70-deploy #" in step0, step0
        assert "STOP" in step0, step0


def test_60_validate_self_call_text():
    for path in (COMMANDS_DIR / "60-validate.md", SKILLS_DIR / "60-validate" / "SKILL.md"):
        text = path.read_text(encoding="utf-8")
        sec = _section(text, r"Autonomen Weiterlauf prüfen")
        assert sec, f"{path}: Abschnitt 'Autonomen Weiterlauf prüfen' fehlt"
        assert "Skill" in sec, sec
        assert "70-deploy" in sec, sec
        assert re.search(r"70-deploy[`\s]*(mit\s*)?[`]?#", sec) or "#N" in sec, sec
        assert "❗ Du" in sec, sec


# --- AC-8 (Regression #550) --------------------------------------------------

WF_707 = "fix-707-endstate-demo"


def _wf_project(root: Path, config: str, data: dict) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    wf_dir = proj / ".claude" / "workflows"
    (wf_dir / "_log").mkdir(parents=True)
    (wf_dir / "_archive").mkdir()
    (proj / "_home").mkdir()
    (proj / "openspec.yaml").write_text(config)
    (wf_dir / f"{data['name']}.json").write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(data["name"])
    return proj


def _endstate(proj: Path) -> subprocess.CompletedProcess:
    env = _clean_env(CLAUDE_PROJECT_DIR=str(proj), HOME=str(proj / "_home"))
    return subprocess.run([sys.executable, str(WORKFLOW_PY), "endstate"], capture_output=True,
                          text=True, env=env, cwd=str(proj), timeout=30)


def _kv(stdout: str, key: str) -> "str | None":
    for line in stdout.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


def _wf_data(**fields) -> dict:
    data = {"name": WF_707, "workflow_type": "feature", "current_phase": "phase8_complete",
            "phase_transitions": [], "phase_log": []}
    data.update(fields)
    return data


def test_endstate_deployed_with_autonomous(tmp_path):
    proj = _wf_project(tmp_path, CFG_AUTO_TRUE, _wf_data(deploy_status="done"))
    res = _endstate(proj)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "ENDSTATE") == "done", res.stdout
    footer = _kv(res.stdout, "FOOTER") or ""
    assert footer.startswith("✅"), footer
    assert "fertig und deployt" in footer, footer
    assert "#707" in footer, footer


def test_endstate_you_without_autonomous(tmp_path):
    proj = _wf_project(tmp_path, CFG_AUTO_MISSING, _wf_data())
    res = _endstate(proj)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "ENDSTATE") == "you", res.stdout
    footer = _kv(res.stdout, "FOOTER") or ""
    assert "/70-deploy #707" in footer, footer
