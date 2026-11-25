"""Frischer Kontext je Aufgabe eines Auftrags (Issue #667, Epic #649).

Spec: docs/specs/feat-667-fresh-session.md (AC-1 bis AC-10).

Vertraege aus der Spec (Implementation Details), die diese Tests festlegen:
- `workflow.py handoff [--start] [--mark <weg>]`: `KEY=value`-Zeilen in der Reihenfolge
  `HANDOFF=none|cloud|herdr|inline`, `NEXT=<M>|none`, bei cloud `REPO_URL=<https ohne .git>|none`,
  bei `--start` `STARTED=yes|no|already` (+ `REASON=` bei no); nur bei HANDOFF != none folgt
  der Startauftrag zwischen `PROMPT_BEGIN` und `PROMPT_END`. Exit immer 0, ausser `--mark`
  mit ungueltigem Weg (Usage auf stderr, Exit 1, keine Schreibung).
- Wegwahl: Kill-Switch / kein autarker Auftrag / Autonomie != auto / kein naechstes Issue
  -> none; `CLAUDE_CODE_REMOTE=true` -> cloud; Herdr-Pane + `claude` im PATH -> herdr;
  sonst inline.
- Vermerk im Auftrag: Feld `handoff = {"issue": M, "mode": weg, "at": ISO}`;
  `hook_utils._normalize_auftrag` behaelt es nur gueltig.
- `herdr_bridge.start_session(prompt, cwd)`: `pane split <eigenes Pane> --direction right
  --cwd <root> --no-focus`, dann `pane run <neues Pane> "exec claude <shlex-quoted prompt>"`.

Umgebung: Diese Tests laufen u. a. in der Cloud (`CLAUDE_CODE_REMOTE=true`,
`OPENSPEC_AUTONOMY=auto`) und auf Rechnern mit echtem `claude` im PATH. Jeder Test setzt
deshalb `CLAUDE_CODE_REMOTE`, `HERDR_*`, `OPENSPEC_*` und `PATH` (ohne Ordner mit einem echten
`claude`, ggf. mit Fake-`claude`) ausdruecklich. Kein Netz: `herdr` ist ein Fake-Binary, das
jeden Aufruf protokolliert. workflow.py laeuft als Subprozess aus einer Kopie der Hooks im
tmp-Projekt (`.claude/hooks` bzw. `core/hooks`), damit der Hook-Pfad im Startauftrag pruefbar ist.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
COMMANDS_DIR = REPO_ROOT / "core" / "commands"
SKILLS_DIR = REPO_ROOT / "skills"

WF = "feat-547-x"
PANE = "pane-667"
NEW_PANE = "pane-new"
KILL_CFG = "auftrag:\n  enabled: false\n"
WAIT_548 = "⏳ Läuft noch: Claude startet #548 aus deinem Auftrag. Du musst nichts tun, ich melde mich."
YOU_548 = "❗ Du: /00-intake #548 — nächstes Issue aus deinem Auftrag"

FAKE_HERDR = """#!{py}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_HERDR_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
if args[:2] == ["pane", "split"]:
    out = os.environ.get("FAKE_SPLIT_OUT") or json.dumps(
        {{"result": {{"pane": {{"pane_id": "{new}"}}}}}})
    print(out)
    sys.exit(int(os.environ.get("FAKE_SPLIT_EXIT", "0")))
if args[:2] == ["pane", "run"]:
    sys.exit(int(os.environ.get("FAKE_RUN_EXIT", "0")))
sys.exit(0)
"""


# --- Helpers ---------------------------------------------------------------

def _hu():
    sys.path.insert(0, str(HOOKS_DIR))
    import hook_utils  # noqa: PLC0415
    return hook_utils


def _clean_path() -> str:
    """PATH ohne Ordner, die ein echtes `claude` enthalten."""
    keep = []
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if d and not os.access(os.path.join(d, "claude"), os.X_OK):
            keep.append(d)
    return os.pathsep.join(keep)


def _git(proj: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(HOME=str(proj / "_home"), GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", *args], cwd=str(proj), env=env, check=True,
                   capture_output=True, timeout=60)


def _project(root: Path, issues=((547, "open"), (548, "open"), (549, "open")),
             autark: bool = True, note: str = "", spur: str = "",
             config: "str | None" = None, remote: "str | None" = None,
             layout: str = "consumer", auftrag: bool = True,
             phase: str = "phase8_complete") -> Path:
    """tmp-Projekt: echtes git-Repo, Hook-Kopie, aktiver Workflow #547, Auftrag ohne Kennung."""
    proj = root / "proj"
    proj.mkdir(parents=True)
    (proj / "_home").mkdir()
    _git(proj, "init", "-q", ".")
    if remote:
        _git(proj, "remote", "add", "origin", remote)
    hooks = proj / (".claude/hooks" if layout == "consumer" else "core/hooks")
    hooks.mkdir(parents=True)
    for f in HOOKS_DIR.glob("*.py"):
        shutil.copy(f, hooks / f.name)
    wf_dir = proj / ".claude" / "workflows"
    (wf_dir / "_log").mkdir(parents=True)
    (wf_dir / "_archive").mkdir()
    (wf_dir / f"{WF}.json").write_text(json.dumps({
        "name": WF, "workflow_type": "feature", "current_phase": phase,
        "phase_transitions": [], "phase_log": []}))
    (proj / ".claude" / "active_workflow").write_text(WF)
    if config is not None:
        (proj / ".claude" / "config.yaml").write_text(config)
    if auftrag:
        data = {"issues": [{"n": n, "status": s} for n, s in issues],
                "autark": autark, "note": note,
                "created": "2026-11-25T10:00:00Z", "updated": "2026-11-25T10:00:00Z"}
        if spur:
            data["spur"] = spur
        _auftrag_file(proj).write_text(json.dumps(data))
    return proj


def _auftrag_file(proj: Path) -> Path:
    return proj / ".claude" / "auftrag.json"


def _auftrag(proj: Path) -> dict:
    return json.loads(_auftrag_file(proj).read_text())


def _fake_claude(root: Path) -> Path:
    bindir = root / "fakebin"
    bindir.mkdir(exist_ok=True)
    exe = bindir / "claude"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    return bindir


def _fake_herdr(root: Path) -> Path:
    exe = root / "herdr-fake"
    exe.write_text(FAKE_HERDR.format(py=sys.executable, new=NEW_PANE))
    exe.chmod(0o755)
    return exe


def _env(proj: Path, *, remote: bool = False, autonomy: str = "auto",
         claude: bool = False, herdr: "Path | None" = None, **extra: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("OPENSPEC_", "HERDR_", "STUB_", "FAKE_", "GIT_"))
           and k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PLUGIN_ROOT",
                         "CLAUDE_CODE_REMOTE", "CLAUDE_PID")}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["OPENSPEC_AUTONOMY"] = autonomy
    path = _clean_path()
    if claude:
        path = str(_fake_claude(proj.parent)) + os.pathsep + path
    env["PATH"] = path
    if remote:
        env["CLAUDE_CODE_REMOTE"] = "true"
    if herdr is not None:
        env.update(HERDR_ENV="1", HERDR_PANE_ID=PANE, HERDR_BIN_PATH=str(herdr),
                   FAKE_HERDR_LOG=str(proj.parent / "herdr.log"))
    env.update(extra)
    return env


def _handoff(proj: Path, *args: str, env: dict, layout: str = "consumer"):
    hooks = proj / (".claude/hooks" if layout == "consumer" else "core/hooks")
    return subprocess.run([sys.executable, str(hooks / "workflow.py"), "handoff", *args],
                          capture_output=True, text=True, env=env, cwd=str(proj),
                          timeout=60)


def _parse(stdout: str) -> "tuple[list[str], str | None]":
    """(KEY=value-Zeilen vor PROMPT_BEGIN, Startauftrag oder None)."""
    lines = stdout.splitlines()
    if "PROMPT_BEGIN" not in lines:
        return [l for l in lines if l.strip()], None
    b = lines.index("PROMPT_BEGIN")
    assert "PROMPT_END" in lines[b:], stdout
    e = b + lines[b:].index("PROMPT_END")
    return [l for l in lines[:b] if l.strip()], "\n".join(lines[b + 1:e]).strip()


def _kv(lines: list, key: str) -> "str | None":
    for line in lines:
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


def _calls(proj: Path) -> list:
    log = proj.parent / "herdr.log"
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]


def _of(calls: list, kind: str) -> list:
    return [c for c in calls if " ".join(c[:2]) == kind]


def _assert_iso(value) -> None:
    assert isinstance(value, str) and value, value
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def _queue_add_tokens(prompt: str) -> list:
    m = re.search(r"python3 (\S*workflow\.py queue add[^`\n]*)", prompt)
    assert m, f"`python3 …workflow.py queue add …` fehlt im Startauftrag:\n{prompt}"
    return shlex.split(m.group(1))


# --- AC-1 -------------------------------------------------------------------

def test_handoff_none_cases(tmp_path):
    """AC-1: Kill-Switch, kein Auftrag, nicht autark, manual, kein naechstes Issue -> none."""
    cases = {
        "kill": dict(config=KILL_CFG),
        "noauftrag": dict(auftrag=False),
        "notautark": dict(autark=False),
        "manual": dict(),
        "nonext_own_open": dict(issues=((547, "open"), (548, "done"))),
        "nonext_all_done": dict(issues=((547, "done"), (548, "done"))),
    }
    for label, kw in cases.items():
        proj = _project(tmp_path / label, **kw)
        herdr = _fake_herdr(tmp_path / label)
        env = _env(proj, remote=True, claude=True, herdr=herdr,
                   autonomy="manual" if label == "manual" else "auto")
        before = _auftrag_file(proj).read_bytes() if _auftrag_file(proj).exists() else None
        res = _handoff(proj, env=env)
        assert res.returncode == 0, (label, res.stdout, res.stderr)
        lines, prompt = _parse(res.stdout)
        assert _kv(lines, "HANDOFF") == "none", (label, res.stdout, res.stderr)
        assert prompt is None and "PROMPT_BEGIN" not in res.stdout, (label, res.stdout)
        if label.startswith("nonext"):
            assert _kv(lines, "NEXT") == "none", (label, res.stdout)
        after = _auftrag_file(proj).read_bytes() if _auftrag_file(proj).exists() else None
        assert after == before, (label, "handoff ohne Aktion darf nichts schreiben")
        calls = _calls(proj)
        assert _of(calls, "pane split") == [] and _of(calls, "pane run") == [], (label, calls)


# --- AC-2 -------------------------------------------------------------------

def test_handoff_cloud_with_repo_url(tmp_path):
    """AC-2: Cloud-Env + autarker Auftrag -> cloud, NEXT, REPO_URL ohne .git, Startauftrag."""
    proj = _project(tmp_path / "https", remote="https://github.com/acme/demo.git")
    res = _handoff(proj, env=_env(proj, remote=True))
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, prompt = _parse(res.stdout)
    assert lines[:3] == ["HANDOFF=cloud", "NEXT=548", "REPO_URL=https://github.com/acme/demo"], \
        res.stdout
    assert prompt and "#548" in prompt, res.stdout

    for label, remote in (("none", None), ("ssh", "git@github.com:acme/demo.git")):
        proj = _project(tmp_path / label, remote=remote)
        res = _handoff(proj, env=_env(proj, remote=True))
        assert res.returncode == 0, (label, res.stdout, res.stderr)
        lines, prompt = _parse(res.stdout)
        assert _kv(lines, "HANDOFF") == "cloud", (label, res.stdout)
        assert _kv(lines, "NEXT") == "548", (label, res.stdout)
        assert _kv(lines, "REPO_URL") == "none", (label, res.stdout)
        assert prompt, (label, res.stdout)


# --- AC-3 -------------------------------------------------------------------

def test_handoff_route_herdr_and_inline(tmp_path):
    """AC-3: Herdr-Pane + claude im PATH -> herdr; ohne Pane oder ohne claude -> inline."""
    proj = _project(tmp_path / "herdr")
    herdr = _fake_herdr(tmp_path / "herdr")
    res = _handoff(proj, env=_env(proj, claude=True, herdr=herdr))
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, prompt = _parse(res.stdout)
    assert _kv(lines, "HANDOFF") == "herdr", res.stdout
    assert _kv(lines, "NEXT") == "548", res.stdout
    assert _kv(lines, "REPO_URL") is None and _kv(lines, "STARTED") is None, res.stdout
    assert prompt, res.stdout
    assert _of(_calls(proj), "pane split") == [] and _of(_calls(proj), "pane run") == [], \
        "ohne --start startet handoff nichts"

    variants = {
        "nopane": dict(claude=True, herdr=None),
        "noclaude": dict(claude=False, herdr=_fake_herdr(tmp_path / "herdr")),
    }
    for label, kw in variants.items():
        proj = _project(tmp_path / label)
        res = _handoff(proj, env=_env(proj, **kw))
        assert res.returncode == 0, (label, res.stdout, res.stderr)
        lines, prompt = _parse(res.stdout)
        assert _kv(lines, "HANDOFF") == "inline", (label, res.stdout)
        assert _kv(lines, "NEXT") == "548", (label, res.stdout)
        assert prompt, (label, res.stdout)


# --- AC-4 -------------------------------------------------------------------

def test_prompt_content_numbers_note_spur(tmp_path):
    """AC-4: Startauftrag mit Issue, 00-intake, queue add (Reihenfolge, note, spur), Regeln."""
    note = 'Sag "hallo" zu Henning; danach $HOME nicht anfassen'
    proj = _project(tmp_path / "full", issues=((547, "open"), (551, "open"), (548, "open"),
                                               (549, "done")),
                    note=note, spur="kontext")
    res = _handoff(proj, env=_env(proj, remote=True))
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, prompt = _parse(res.stdout)
    assert _kv(lines, "NEXT") == "551", res.stdout
    assert prompt, res.stdout

    assert "#551" in prompt, prompt
    assert "00-intake" in prompt and "skills/00-intake/SKILL.md" in prompt, prompt
    tokens = _queue_add_tokens(prompt)
    assert tokens[:5] == [".claude/hooks/workflow.py", "queue", "add", "551", "548"], tokens
    assert "547" not in tokens and "549" not in tokens, tokens
    assert "--autark" in tokens, tokens
    assert "--note" in tokens and tokens[tokens.index("--note") + 1] == note, tokens
    assert "--spur" in tokens and tokens[tokens.index("--spur") + 1] == "kontext", tokens
    assert "PO-Punkten" in prompt and "AskUserQuestion" in prompt, prompt
    assert "/clear" in prompt, prompt
    assert "frisch" in prompt and "#667" in prompt, prompt
    assert "CONTEXT_TOKENS" in prompt and "workflow.py context" in prompt, prompt
    assert ".claude/hooks/workflow.py context" in prompt, prompt

    # Ohne note/spur: keine --note/--spur; Framework-Repo-Layout: core/hooks
    proj = _project(tmp_path / "plain", layout="framework")
    res = _handoff(proj, env=_env(proj, remote=True), layout="framework")
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, prompt = _parse(res.stdout)
    assert prompt, res.stdout
    tokens = _queue_add_tokens(prompt)
    assert tokens[:5] == ["core/hooks/workflow.py", "queue", "add", "548", "549"], tokens
    assert "--autark" in tokens, tokens
    assert "--note" not in tokens and "--spur" not in tokens, tokens
    assert "core/hooks/workflow.py context" in prompt, prompt


# --- AC-5 -------------------------------------------------------------------

def test_herdr_start_with_fake_binary(tmp_path):
    """AC-5: --start im herdr-Weg: pane split + pane run mit exec claude, STARTED=yes, Vermerk."""
    proj = _project(tmp_path / "p")
    herdr = _fake_herdr(tmp_path / "p")
    res = _handoff(proj, "--start", env=_env(proj, claude=True, herdr=herdr))
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, prompt = _parse(res.stdout)
    assert _kv(lines, "HANDOFF") == "herdr", res.stdout
    assert _kv(lines, "STARTED") == "yes", (res.stdout, res.stderr)
    assert prompt, res.stdout

    calls = _calls(proj)
    splits, runs = _of(calls, "pane split"), _of(calls, "pane run")
    assert len(splits) == 1 and len(runs) == 1, calls
    split = splits[0]
    assert split[:3] == ["pane", "split", PANE], split
    assert split[split.index("--direction") + 1] == "right", split
    assert os.path.realpath(split[split.index("--cwd") + 1]) == os.path.realpath(proj), split
    assert "--no-focus" in split, split
    assert calls.index(split) < calls.index(runs[0]), calls
    run = runs[0]
    assert run[:3] == ["pane", "run", NEW_PANE], run
    assert all(c[2] != PANE for c in runs), "nie im eigenen Pane starten"
    assert run[3].startswith("exec claude "), run
    assert shlex.split(run[3]) == ["exec", "claude", prompt], run

    mark = _auftrag(proj).get("handoff")
    assert isinstance(mark, dict), _auftrag(proj)
    assert mark.get("issue") == 548 and mark.get("mode") == "herdr", mark
    _assert_iso(mark.get("at"))


# --- AC-6 -------------------------------------------------------------------

def test_start_idempotent_already(tmp_path):
    """AC-6: Vermerk fuer dieselbe Nummer vorhanden -> STARTED=already, kein neuer Start."""
    proj = _project(tmp_path / "p")
    herdr = _fake_herdr(tmp_path / "p")
    env = _env(proj, claude=True, herdr=herdr)
    first = _handoff(proj, "--start", env=env)
    assert first.returncode == 0, (first.stdout, first.stderr)
    assert _kv(_parse(first.stdout)[0], "STARTED") == "yes", first.stdout
    n_split = len(_of(_calls(proj), "pane split"))
    n_run = len(_of(_calls(proj), "pane run"))

    again = _handoff(proj, "--start", env=env)
    assert again.returncode == 0, (again.stdout, again.stderr)
    assert _kv(_parse(again.stdout)[0], "STARTED") == "already", again.stdout
    assert len(_of(_calls(proj), "pane split")) == n_split, _calls(proj)
    assert len(_of(_calls(proj), "pane run")) == n_run, _calls(proj)

    # Vorab per --mark vermerkter Start zaehlt ebenso
    proj2 = _project(tmp_path / "q")
    herdr2 = _fake_herdr(tmp_path / "q")
    env2 = _env(proj2, claude=True, herdr=herdr2)
    mark = _handoff(proj2, "--mark", "herdr", env=env2)
    assert mark.returncode == 0, (mark.stdout, mark.stderr)
    res = _handoff(proj2, "--start", env=env2)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(_parse(res.stdout)[0], "STARTED") == "already", res.stdout
    assert _of(_calls(proj2), "pane split") == [] and _of(_calls(proj2), "pane run") == []


# --- AC-7 -------------------------------------------------------------------

def test_herdr_failure_started_no(tmp_path):
    """AC-7: split/run scheitert, eigenes Pane als Antwort oder Binary fehlt -> STARTED=no."""
    cases = {
        "split_fail": dict(FAKE_SPLIT_EXIT="1"),
        "split_garbage": dict(FAKE_SPLIT_OUT="kein json"),
        "split_own_pane": dict(FAKE_SPLIT_OUT=json.dumps(
            {"result": {"pane": {"pane_id": PANE}}})),
        "run_fail": dict(FAKE_RUN_EXIT="1"),
        "no_binary": dict(HERDR_BIN_PATH="/nonexistent/herdr-667"),
    }
    for label, extra in cases.items():
        proj = _project(tmp_path / label)
        herdr = _fake_herdr(tmp_path / label)
        env = _env(proj, claude=True, herdr=herdr, **extra)
        before = _auftrag_file(proj).read_bytes()
        res = _handoff(proj, "--start", env=env)
        assert res.returncode == 0, (label, res.stdout, res.stderr)
        lines, _ = _parse(res.stdout)
        assert _kv(lines, "STARTED") == "no", (label, res.stdout, res.stderr)
        reason = _kv(lines, "REASON")
        assert reason and reason.strip(), (label, res.stdout)
        assert _auftrag_file(proj).read_bytes() == before, (label, "kein handoff-Vermerk")
        assert "handoff" not in _auftrag(proj), label
        assert all(c[2] != PANE for c in _of(_calls(proj), "pane run")), (label, _calls(proj))


# --- AC-8 -------------------------------------------------------------------

def test_mark_validation_and_normalize(tmp_path):
    """AC-8: --mark cloud/herdr vermerkt; ungueltiger Weg -> Exit 1, Usage, keine Schreibung."""
    for mode in ("cloud", "herdr"):
        proj = _project(tmp_path / mode)
        res = _handoff(proj, "--mark", mode, env=_env(proj, remote=True))
        assert res.returncode == 0, (mode, res.stdout, res.stderr)
        mark = _auftrag(proj).get("handoff")
        assert isinstance(mark, dict), (mode, _auftrag(proj))
        assert mark.get("issue") == 548 and mark.get("mode") == mode, (mode, mark)
        _assert_iso(mark.get("at"))

    for bad in ("inline", "none", "x"):
        proj = _project(tmp_path / f"bad-{bad}")
        before = _auftrag_file(proj).read_bytes()
        res = _handoff(proj, "--mark", bad, env=_env(proj, remote=True))
        assert res.returncode == 1, (bad, res.returncode, res.stdout, res.stderr)
        assert "usage" in res.stderr.lower(), (bad, res.stderr)
        assert _auftrag_file(proj).read_bytes() == before, bad

    hu = _hu()
    base = {"issues": [{"n": 548, "status": "open"}], "autark": True, "note": "",
            "created": "c", "updated": "u"}
    good = hu._normalize_auftrag(dict(base, handoff={
        "issue": 548, "mode": "cloud", "at": "2026-11-25T10:00:00Z"}))
    assert good and isinstance(good.get("handoff"), dict), good
    assert good["handoff"]["issue"] == 548 and good["handoff"]["mode"] == "cloud", good
    assert hu._normalize_auftrag(dict(base, handoff={
        "issue": 549, "mode": "herdr", "at": "2026-11-25T10:00:00Z"}))["handoff"]["mode"] == "herdr"
    for bad in ({"issue": "548", "mode": "cloud", "at": "x"},
                {"issue": True, "mode": "cloud", "at": "x"},
                {"issue": 0, "mode": "cloud", "at": "x"},
                {"issue": -3, "mode": "herdr", "at": "x"},
                {"issue": 548, "mode": "inline", "at": "x"},
                {"issue": 548, "mode": "x", "at": "x"},
                {"issue": 548},
                "cloud", 548, None):
        got = hu._normalize_auftrag(dict(base, handoff=bad))
        assert got is not None and "handoff" not in got, (bad, got)
    assert "handoff" not in hu._normalize_auftrag(base)


# --- AC-9 -------------------------------------------------------------------

def _chain_section(text: str) -> str:
    start = text.find("Kette bei offenem Auftrag")
    assert start >= 0, "Abschnitt „Kette bei offenem Auftrag“ fehlt"
    rest = text[start:]
    end = rest.find("\n\nVorschlag (#589)")
    return rest if end < 0 else rest[:end]


def test_command_texts_mention_handoff():
    """AC-9: 60-validate/70-deploy nennen handoff, create_session, --mark cloud, --start."""
    for name in ("60-validate", "70-deploy"):
        for path in (COMMANDS_DIR / f"{name}.md", SKILLS_DIR / name / "SKILL.md"):
            section = _chain_section(path.read_text(encoding="utf-8"))
            for needle in ("workflow.py handoff", "create_session", "handoff --mark cloud",
                           "handoff --start", "/00-intake #M", "inline"):
                assert needle in section, (str(path), needle)

    wf_cmd = (COMMANDS_DIR / "80-workflow.md").read_text(encoding="utf-8")
    assert "handoff" in wf_cmd, "80-workflow.md dokumentiert `handoff` nicht"
    assert "--mark" in wf_cmd and "--start" in wf_cmd, "80-workflow.md: Optionen fehlen"

    res = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"),
                          "--check"], capture_output=True, text=True, cwd=str(REPO_ROOT),
                         timeout=60)
    assert res.returncode == 0, (res.stdout, res.stderr)


# --- AC-10 ------------------------------------------------------------------

def test_endstate_unchanged(tmp_path):
    """AC-10: endstate-Zeile „aus deinem Auftrag“ unveraendert, footer_gate bewertet wie bisher."""
    for label, autark, kind, line in (("autark", True, "waiting", WAIT_548),
                                      ("manual", False, "you", YOU_548)):
        proj = _project(tmp_path / label, issues=((547, "done"), (548, "open")), autark=autark)
        herdr = _fake_herdr(tmp_path / label)
        env = _env(proj, remote=True, claude=True, herdr=herdr)
        res = subprocess.run([sys.executable, str(proj / ".claude" / "hooks" / "workflow.py"),
                              "endstate"], capture_output=True, text=True, env=env,
                             cwd=str(proj), timeout=60)
        assert res.returncode == 0, (label, res.stdout, res.stderr)
        lines = res.stdout.splitlines()
        assert _kv(lines, "ENDSTATE") == kind, (label, res.stdout)
        assert _kv(lines, "FOOTER") == line, (label, res.stdout)

        payload = json.dumps({"session_id": "sess-667", "hook_event_name": "Stop",
                              "cwd": str(proj), "prompt_id": f"p-{label}",
                              "last_assistant_message": f"Fertig.\n\n{line}\n⚙ /60-validate"})
        gate = subprocess.run([sys.executable, str(proj / ".claude" / "hooks" / "footer_gate.py")],
                              input=payload, capture_output=True, text=True,
                              env=dict(env, OPENSPEC_ACTIVE_WORKFLOW=WF), cwd=str(proj),
                              timeout=60)
        assert gate.returncode == 0, (label, gate.stderr)
        calls = _calls(proj)
        assert _of(calls, "pane split") == [] and _of(calls, "pane run") == [], (label, calls)
