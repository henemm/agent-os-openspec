"""Plan-Pane-Lebenszyklus (Issue #496).

Spec: docs/specs/fix-496-plan-pane-lebenszyklus.md (AC-1 bis AC-11; AC-12 ist
der Regressionslauf, AC-13 das E2E-Skript scripts/e2e_plan_pane.sh).

Aufbau je Fall (Muster tests/test_herdr_plan_pane_476.py,
tests/test_herdr_plan_pane_reuse_493.py): isoliertes Projekt (`.git`-Ordner,
`config.yaml` mit `herdr.enabled: true`, optional aktiver Workflow) und ein
Stub-Herdr (`HERDR_BIN_PATH`), der eine JSON-Welt aus einer Fixture-Datei
(`STUB_WORLD`) beantwortet und veraendert:

- jeder Aufruf wird NUL-getrennt in STUB_LOG protokolliert (vor allem anderen);
- `pane list [--workspace W]` -> `{"result":{"panes":[...]}}`; OHNE
  `--workspace` liefert der Stub ALLE Workspaces (wie echtes Herdr, Vorfall);
  STUB_LIST_MODE=fail -> Exit 1, =garbage -> kaputtes JSON;
- `pane get P` -> `{"result":{"pane":{...}}}` bzw. Exit 1 `pane_not_found`;
  mit STUB_GET_SEQ (Komma-Liste ok|noagent|missing, letzter Wert wiederholt
  sich) je Aufruf der naechste Wert;
- `pane close P` -> entfernt P aus der Welt (STUB_CLOSE_EXIT != 0: Fehler);
- `pane split S ...` -> neues Pane `pane-new-<n>` im Workspace von S;
- `pane rename P L`, `pane report-metadata P --token k=v ...` (Tokens werden
  gemischt), `pane run P CMD`;
- STUB_SLEEP=<s>: jeder Aufruf haengt so lange (nach dem Protokollieren).
- `pane process-info --pane P` -> `foreground_processes` mit den PIDs aus
  `fg_pids` des Panes, sonst STUB_FG_PID (#496 R2 F001); STUB_PROCINFO_MODE=fail
  -> Exit 1, =garbage -> kaputtes JSON;
- STUB_RENAME_EXIT / STUB_META_EXIT != 0: `pane rename` bzw.
  `pane report-metadata` scheitern; STUB_SPLIT_ID: `pane split` antwortet mit
  genau dieser pane_id und legt kein Pane an (#496 R2 F002/F003).

Die Runner-/SessionEnd-Aufrufe laufen mit CLAUDE_PID=STUB_FG_PID (eigene Session
ist Vordergrundprozess ihres Panes); ein verschachteltes Kind hat eine andere PID.
"""

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
BRIDGE = HOOKS_DIR / "herdr_bridge.py"
SESSION_BANNER = HOOKS_DIR / "session_banner.py"
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"

ME = "pane-claude-496"          # eigenes Claude-Pane
OTHER = "pane-claude-other"     # fremdes, lebendes Claude-Pane (selber Workspace)
SHELL = "pane-shell"            # Pane ohne agent == "claude"
GONE = "pane-gone"              # Owner, der nicht (mehr) in der Liste steht
WS = "ws-1"                     # eigener Workspace
WS2 = "ws-2"                    # fremder Workspace
WF = "fix-496-demo"
LABEL = "Workflow"
OLD_VERSION = "0.0.0-alt"
PARENT_PID = "4242"             # Claude-Prozess, der Vordergrund von ME ist
CHILD_PID = "5151"              # verschachteltes `claude -p` mit geerbter HERDR-Env


def _version() -> str:
    return json.loads(PLUGIN_JSON.read_text())["version"]


STUB_SOURCE = r'''
import json, os, sys, time
args = sys.argv[1:]
log = os.environ.get("STUB_LOG")
if log:
    with open(log, "ab") as fh:
        fh.write(b"".join(a.encode("utf-8", "replace") + b"\0" for a in args) + b"\n")
sleep = float(os.environ.get("STUB_SLEEP") or 0)
if sleep:
    time.sleep(sleep)
world_path = os.environ.get("STUB_WORLD", "")

def load():
    try:
        with open(world_path) as fh:
            return json.load(fh)
    except Exception:
        return {"panes": []}

def save(world):
    tmp = world_path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(world, fh)
    os.replace(tmp, world_path)

def opt(name):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            return args[i + 1]
    return None

kind = " ".join(args[:2])
world = load()
panes = world.setdefault("panes", [])

def find(pid):
    for p in panes:
        if p.get("pane_id") == pid:
            return p
    return None

def not_found(pid):
    sys.stderr.write(json.dumps({"error": {"code": "pane_not_found", "pane": pid}}) + "\n")
    sys.exit(1)

if kind == "pane list":
    mode = os.environ.get("STUB_LIST_MODE", "")
    if mode == "fail":
        sys.stderr.write("stub: list failed\n")
        sys.exit(1)
    if mode == "garbage":
        print("{kaputt")
        sys.exit(0)
    ws = opt("--workspace")
    out = [p for p in panes if ws is None or p.get("workspace_id") == ws]
    print(json.dumps({"result": {"panes": out}}))
    sys.exit(0)

if kind == "pane get":
    target = args[2] if len(args) > 2 else ""
    seq = os.environ.get("STUB_GET_SEQ", "")
    if seq:
        items = [s.strip() for s in seq.split(",") if s.strip()]
        cpath = os.environ["STUB_GET_COUNT"]
        try:
            n = int(open(cpath).read())
        except Exception:
            n = 0
        with open(cpath, "w") as fh:
            fh.write(str(n + 1))
        item = items[n] if n < len(items) else items[-1]
        if item == "missing":
            not_found(target)
        agent = "claude" if item == "ok" else None
        print(json.dumps({"result": {"pane": {"pane_id": target, "workspace_id": "ws-1",
                                              "agent": agent, "agent_status": "idle"}}}))
        sys.exit(0)
    p = find(target)
    if p is None:
        not_found(target)
    print(json.dumps({"result": {"pane": p}}))
    sys.exit(0)

if kind == "pane close":
    code = int(os.environ.get("STUB_CLOSE_EXIT") or 0)
    if code:
        sys.stderr.write("stub: close failed\n")
        sys.exit(code)
    target = args[2] if len(args) > 2 else ""
    if find(target) is None:
        not_found(target)
    world["panes"] = [p for p in panes if p.get("pane_id") != target]
    save(world)
    print(json.dumps({"result": {}}))
    sys.exit(0)

if kind == "pane process-info":
    mode = os.environ.get("STUB_PROCINFO_MODE", "")
    if mode == "fail":
        sys.stderr.write("stub: process-info failed\n")
        sys.exit(1)
    if mode == "garbage":
        print("{kaputt")
        sys.exit(0)
    target = opt("--pane") or ""
    p = find(target)
    if p is None:
        not_found(target)
    fg = p.get("fg_pids")
    if fg is None:
        fg = [int(os.environ.get("STUB_FG_PID") or 0)]
    print(json.dumps({"result": {"process_info": {
        "pane_id": target, "foreground_processes": [{"pid": x, "name": "claude"} for x in fg]}}}))
    sys.exit(0)

if kind == "pane split" and os.environ.get("STUB_SPLIT_ID"):
    print(json.dumps({"result": {"pane": {"pane_id": os.environ["STUB_SPLIT_ID"]}}}))
    sys.exit(0)

if kind == "pane split":
    src = find(args[2]) if len(args) > 2 else None
    cpath = os.environ["STUB_COUNT"]
    try:
        n = int(open(cpath).read())
    except Exception:
        n = 0
    n += 1
    with open(cpath, "w") as fh:
        fh.write(str(n))
    new = {"pane_id": "pane-new-%d" % n,
           "workspace_id": (src or {}).get("workspace_id") or os.environ.get("HERDR_WORKSPACE_ID", ""),
           "label": "", "cwd": opt("--cwd") or "", "agent_status": "unknown"}
    panes.append(new)
    save(world)
    print(json.dumps({"result": {"pane": {"pane_id": new["pane_id"]}}}))
    sys.exit(0)

if kind == "pane rename" and int(os.environ.get("STUB_RENAME_EXIT") or 0):
    sys.stderr.write("stub: rename failed\n")
    sys.exit(int(os.environ["STUB_RENAME_EXIT"]))

if kind == "pane report-metadata" and int(os.environ.get("STUB_META_EXIT") or 0):
    sys.stderr.write("stub: report-metadata failed\n")
    sys.exit(int(os.environ["STUB_META_EXIT"]))

if kind == "pane rename":
    p = find(args[2]) if len(args) > 2 else None
    if p is None:
        not_found(args[2] if len(args) > 2 else "")
    p["label"] = args[3] if len(args) > 3 else ""
    save(world)
    sys.exit(0)

if kind == "pane report-metadata":
    p = find(args[2]) if len(args) > 2 else None
    if p is None:
        not_found(args[2] if len(args) > 2 else "")
    tokens = dict(p.get("tokens") or {})
    for i, a in enumerate(args):
        if a == "--token" and i + 1 < len(args) and "=" in args[i + 1]:
            k, v = args[i + 1].split("=", 1)
            tokens[k] = v
    p["tokens"] = tokens
    save(world)
    sys.exit(0)

sys.exit(0)
'''


# --- Helpers ---------------------------------------------------------------

def claude_pane(pid: str = ME, ws: str = WS, cwd: str = "/x") -> dict:
    return {"pane_id": pid, "workspace_id": ws, "label": "claude", "cwd": cwd,
            "agent": "claude", "agent_status": "idle"}


def shell_pane(pid: str = SHELL, ws: str = WS) -> dict:
    return {"pane_id": pid, "workspace_id": ws, "label": "zsh", "cwd": "/x",
            "agent_status": "unknown"}


def plan_pane(pid: str, cwd: str, ws: str = WS, **tokens) -> dict:
    p = {"pane_id": pid, "workspace_id": ws, "label": LABEL, "cwd": cwd,
         "agent_status": "unknown"}
    if tokens:
        p["tokens"] = dict(tokens)
    return p


class Case:
    """Isoliertes Projekt + Stub-Herdr mit JSON-Welt."""

    def __init__(self, tmp_path: Path, label: str, workflow: bool = True):
        self.root = tmp_path / label
        self.root.mkdir()
        self.proj = self.root / "proj"
        (self.proj / ".git").mkdir(parents=True)
        (self.proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
        (self.proj / "_home").mkdir()
        (self.proj / "config.yaml").write_text("herdr:\n  enabled: true\n")
        if workflow:
            self.set_workflow(WF)
        self.world = self.root / "world.json"
        self.log = self.root / "stub.log"
        self.count = self.root / "stub.count"
        self.get_count = self.root / "stub.getcount"
        self.stub = self.root / "herdr-stub"
        self.stub.write_text(f"#!{sys.executable}\n" + STUB_SOURCE)
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.write_world([])

    @property
    def cwd(self) -> str:
        return str(self.proj)

    def set_workflow(self, name: str) -> None:
        data = {"name": name, "workflow_type": "bugfix",
                "current_phase": "phase5_tdd_red", "phase_transitions": [],
                "phase_log": []}
        (self.proj / ".claude" / "workflows" / f"{name}.json").write_text(json.dumps(data))
        (self.proj / ".claude" / "active_workflow").write_text(name)

    # -- Welt --------------------------------------------------------------
    def write_world(self, panes: list) -> None:
        self.world.write_text(json.dumps({"panes": panes}))

    def panes(self) -> dict:
        return {p["pane_id"]: p for p in json.loads(self.world.read_text())["panes"]}

    # -- Umgebung ----------------------------------------------------------
    def env(self, **extra) -> dict:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_", "GH_"))}
        env.update({
            "CLAUDE_PROJECT_DIR": self.cwd,
            "HOME": str(self.proj / "_home"),
            "HERDR_ENV": "1",
            "HERDR_PANE_ID": ME,
            "HERDR_WORKSPACE_ID": WS,
            "HERDR_BIN_PATH": str(self.stub),
            "STUB_LOG": str(self.log),
            "STUB_WORLD": str(self.world),
            "STUB_COUNT": str(self.count),
            "STUB_GET_COUNT": str(self.get_count),
            "CLAUDE_PID": PARENT_PID,       # eigene Session = Vordergrund ihres Panes
            "STUB_FG_PID": PARENT_PID,
        })
        for k, v in extra.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v
        return env

    # -- Aufrufe -----------------------------------------------------------
    def runner(self, **extra):
        """SessionStart-Runner synchron (wie ihn open_plan_pane detached startet)."""
        return subprocess.run(
            [sys.executable, str(BRIDGE), "plan-pane", "--pane", ME,
             "--cwd", self.cwd, "--ratio", "0.75", "--delay", "0"],
            capture_output=True, text=True, env=self.env(**extra),
            cwd=self.cwd, timeout=60)

    def session_end(self, reason: str, **extra):
        payload = {"session_id": "sess-496", "hook_event_name": "SessionEnd",
                   "cwd": self.cwd, "reason": reason}
        return subprocess.run(
            [sys.executable, str(BRIDGE), "plan-pane-close"],
            input=json.dumps(payload), capture_output=True, text=True,
            env=self.env(**extra), cwd=self.cwd, timeout=60)

    def calls(self) -> list:
        if not self.log.exists():
            return []
        out = []
        for line in self.log.read_bytes().decode("utf-8", "replace").split("\n"):
            if line:
                parts = line.split("\0")
                out.append(parts[:-1] if line.endswith("\0") else parts)
        return out

    def of(self, kind: str) -> list:
        return [c for c in self.calls() if " ".join(c[:2]) == kind]

    def closed(self) -> list:
        return [c[2] for c in self.of("pane close") if len(c) > 2]

    def touching(self, pane_id: str) -> list:
        """Alle veraendernden Aufrufe auf `pane_id`."""
        kinds = ("pane close", "pane report-metadata", "pane rename", "pane run")
        return [c for c in self.calls()
                if " ".join(c[:2]) in kinds and len(c) > 2 and c[2] == pane_id]


def _tokens(call: list) -> dict:
    out = {}
    for i, a in enumerate(call):
        if a == "--token" and i + 1 < len(call) and "=" in call[i + 1]:
            k, v = call[i + 1].split("=", 1)
            out[k] = v
    return out


def _flag(call: list, flag: str):
    for i, a in enumerate(call):
        if a == flag and i + 1 < len(call):
            return call[i + 1]
    return None


# --- AC-1 -------------------------------------------------------------------

def test_sweep_closes_each_stale_rule(tmp_path):
    v = _version()
    support = lambda c: [claude_pane(cwd=c.cwd), shell_pane()]  # noqa: E731
    rules = (
        ("deleted-cwd", True,
         lambda c: [plan_pane("pp-x", f"{c.cwd} (deleted)", owner=ME, workflow=WF, version=v)]),
        ("ohne-owner", True,
         lambda c: [plan_pane("pp-x", c.cwd)]),
        ("toter-owner", True,
         lambda c: [plan_pane("pp-x", c.cwd, owner=GONE, workflow=WF, version=v)]),
        ("owner-ohne-claude", True,
         lambda c: [plan_pane("pp-x", c.cwd, owner=SHELL, workflow=WF, version=v)]),
        ("eigen-ohne-workflow", False,
         lambda c: [plan_pane("pp-x", c.cwd, owner=ME, workflow=WF, version=v)]),
        ("eigen-alte-version", True,
         lambda c: [plan_pane("pp-x", c.cwd, owner=ME, workflow=WF, version=OLD_VERSION)]),
    )
    for label, with_wf, make in rules:
        c = Case(tmp_path, label, workflow=with_wf)
        c.write_world(support(c) + make(c))
        res = c.runner()
        assert res.returncode == 0, (label, res.stderr)
        assert c.closed() == ["pp-x"], f"{label}: erwartet pane close pp-x, gesehen {c.calls()}"
        assert "pp-x" not in c.panes(), (label, c.panes())
        assert {ME, SHELL} <= set(c.panes()), f"{label}: Nicht-Plan-Pane geschlossen"

    # Duplikat: zwei gueltige eigene Panes -> genau eines wird geschlossen, keins neu
    c = Case(tmp_path, "duplikat")
    c.write_world(support(c) + [
        plan_pane("pp-a", c.cwd, owner=ME, workflow=WF, version=v),
        plan_pane("pp-b", c.cwd, owner=ME, workflow=WF, version=v)])
    res = c.runner()
    assert res.returncode == 0, res.stderr
    closed = c.closed()
    assert len(closed) == 1 and closed[0] in ("pp-a", "pp-b"), (
        f"Duplikat: erwartet genau ein pane close, gesehen {c.calls()}")
    assert c.of("pane split") == [], f"Duplikat: trotz behaltenem Pane gesplittet: {c.calls()}"


# --- AC-2 -------------------------------------------------------------------

def test_sweep_never_closes_foreign_living_owner(tmp_path):
    c = Case(tmp_path, "foreign")
    foreign = plan_pane("pp-foreign", c.cwd, owner=OTHER, workflow="anderer-wf",
                        version=OLD_VERSION)
    c.write_world([claude_pane(cwd=c.cwd), claude_pane(OTHER, cwd=c.cwd), foreign,
                   plan_pane("pp-stale", c.cwd)])  # Kontrolle: Altlast ohne Owner
    res = c.runner()
    assert res.returncode == 0, res.stderr
    assert "pp-stale" in c.closed(), f"Kontrolle: Sweep lief nicht: {c.calls()}"
    assert c.touching("pp-foreign") == [], (
        f"Pane eines fremden lebenden Owners angefasst: {c.touching('pp-foreign')}")
    assert c.panes().get("pp-foreign") == foreign, c.panes().get("pp-foreign")
    assert OTHER in c.panes(), "fremdes Claude-Pane geschlossen"


# --- AC-3 -------------------------------------------------------------------

def test_sweep_is_workspace_scoped(tmp_path):
    c = Case(tmp_path, "scoped")
    c.write_world([
        claude_pane(cwd=c.cwd),
        plan_pane("pp-stale-own-ws", c.cwd),                       # Kontrolle
        claude_pane("pane-claude-ws2", ws=WS2, cwd=c.cwd),
        plan_pane("pp-ws2-noowner", c.cwd, ws=WS2),
        plan_pane("pp-ws2-deleted", f"{c.cwd} (deleted)", ws=WS2, owner=GONE),
        plan_pane("pp-ws2-me", c.cwd, ws=WS2, owner=ME, workflow=WF, version=OLD_VERSION),
    ])
    res = c.runner()
    assert res.returncode == 0, res.stderr
    lists = c.of("pane list")
    assert lists, f"kein pane list (Sweep fehlt): {c.calls()}"
    for call in lists:
        assert _flag(call, "--workspace") == WS, f"pane list ohne/anderen --workspace: {call}"
    assert "pp-stale-own-ws" in c.closed(), f"Kontrolle: Sweep lief nicht: {c.calls()}"
    ws2 = {"pane-claude-ws2", "pp-ws2-noowner", "pp-ws2-deleted", "pp-ws2-me"}
    assert not ws2 & set(c.closed()), f"Pane eines anderen Workspace geschlossen: {c.closed()}"
    assert ws2 <= set(c.panes()), c.panes()

    # Ohne HERDR_WORKSPACE_ID: gar nichts schliessen
    c = Case(tmp_path, "no-ws")
    c.write_world([claude_pane(cwd=c.cwd), plan_pane("pp-stale", c.cwd),
                   plan_pane("pp-ws2", c.cwd, ws=WS2)])
    res = c.runner(HERDR_WORKSPACE_ID=None)
    assert res.returncode == 0, res.stderr
    assert c.of("pane close") == [], f"ohne HERDR_WORKSPACE_ID geschlossen: {c.calls()}"
    for call in c.of("pane list"):
        assert _flag(call, "--workspace"), f"pane list ohne --workspace: {call}"


# --- AC-4 -------------------------------------------------------------------

def test_open_sets_tokens_and_reuses_with_token_refresh(tmp_path):
    v = _version()
    c = Case(tmp_path, "open")
    c.write_world([claude_pane(cwd=c.cwd)])
    res = c.runner()
    assert res.returncode == 0, res.stderr
    splits = c.of("pane split")
    assert len(splits) == 1, c.calls()
    assert splits[0][2] == ME and _flag(splits[0], "--direction") == "right", splits[0]
    renames = c.of("pane rename")
    assert renames and renames[0][2:4] == ["pane-new-1", LABEL], renames
    metas = c.of("pane report-metadata")
    assert metas, f"kein pane report-metadata: {c.calls()}"
    meta = metas[0]
    assert meta[2] == "pane-new-1", f"Pane-ID nicht vor den Optionen: {meta}"
    assert _flag(meta, "--source") == "user:openspec", meta
    assert _tokens(meta) == {"owner": ME, "workflow": WF, "version": v}, meta
    runs = c.of("pane run")
    assert runs and runs[0][2] == "pane-new-1", c.calls()
    tokens = shlex.split(runs[0][-1])
    assert tokens[-4:] == ["plan", "--watch", "--target", ME], tokens
    plans = [p for p in c.panes().values() if p.get("label") == LABEL]
    assert len(plans) == 1, plans
    assert plans[0].get("tokens") == {"owner": ME, "workflow": WF, "version": v}, plans

    # Behaltenes eigenes Pane mit altem workflow-Token: nur Token nachziehen
    c = Case(tmp_path, "refresh")
    c.write_world([claude_pane(cwd=c.cwd),
                   plan_pane("pp-own", c.cwd, owner=ME, workflow="alter-wf", version=v)])
    res = c.runner()
    assert res.returncode == 0, res.stderr
    assert c.of("pane split") == [], f"trotz behaltenem Pane gesplittet: {c.calls()}"
    assert c.of("pane close") == [], c.calls()
    metas = [m for m in c.of("pane report-metadata") if m[2] == "pp-own"]
    assert metas, f"workflow-Token nicht nachgezogen: {c.calls()}"
    assert any(_tokens(m).get("workflow") == WF for m in metas), metas
    assert c.panes()["pp-own"]["tokens"] == {"owner": ME, "workflow": WF, "version": v}


# --- AC-5 -------------------------------------------------------------------

def test_session_end_closes_only_own_pane(tmp_path):
    v = _version()
    for reason in ("prompt_input_exit", "other"):
        c = Case(tmp_path, reason)
        c.write_world([
            claude_pane(cwd=c.cwd), claude_pane(OTHER, cwd=c.cwd),
            plan_pane("pp-own", c.cwd, owner=ME, workflow=WF, version=v),
            plan_pane("pp-foreign", c.cwd, owner=OTHER, workflow=WF, version=v),
            plan_pane("pp-stale", c.cwd),
            plan_pane("pp-own-ws2", c.cwd, ws=WS2, owner=ME, workflow=WF, version=v),
        ])
        res = c.session_end(reason)
        assert res.returncode == 0, (reason, res.stderr)
        assert c.closed() == ["pp-own"], f"{reason}: erwartet nur pp-own, gesehen {c.calls()}"
        for call in c.of("pane list"):
            assert _flag(call, "--workspace") == WS, (reason, call)
        assert {"pp-foreign", "pp-stale", "pp-own-ws2", ME, OTHER} <= set(c.panes())


# --- AC-6 -------------------------------------------------------------------

def test_session_end_clear_keeps_pane(tmp_path):
    v = _version()
    c = Case(tmp_path, "clear")
    own = plan_pane("pp-own", c.cwd, owner=ME, workflow=WF, version=v)
    c.write_world([claude_pane(cwd=c.cwd), own])
    res = c.session_end("clear")
    assert res.returncode == 0, res.stderr
    assert c.of("pane close") == [], f"SessionEnd clear schloss: {c.calls()}"
    # folgender SessionStart (source=clear) behaelt dasselbe Pane
    res = c.runner()
    assert res.returncode == 0, res.stderr
    assert c.of("pane close") == [], f"SessionStart clear schloss: {c.calls()}"
    assert c.of("pane split") == [], f"SessionStart clear oeffnete zweites Pane: {c.calls()}"
    plans = [p["pane_id"] for p in c.panes().values() if p.get("label") == LABEL]
    assert plans == ["pp-own"], plans


# --- AC-7 -------------------------------------------------------------------

def _watch(c: Case, rounds: int, **extra):
    env = c.env(OPENSPEC_PLAN_WATCH_ROUNDS=str(rounds),
                OPENSPEC_PLAN_WATCH_INTERVAL="0", PYTHONUNBUFFERED="1", **extra)
    return subprocess.run(
        [sys.executable, str(WORKFLOW_PY), "plan", "--watch", "--target", ME],
        capture_output=True, text=True, env=env, cwd=c.cwd, timeout=60)


def test_watcher_exits_after_three_dead_owner_rounds(tmp_path):
    for label, seq in (("missing", "missing"), ("noagent", "noagent")):
        c = Case(tmp_path, f"dead-{label}")
        res = _watch(c, 20, STUB_GET_SEQ=seq)
        assert res.returncode == 0, (label, res.stderr)
        gets = [g for g in c.of("pane get") if g[2:3] == [ME]]
        assert len(gets) == 3, (
            f"{label}: Watcher sollte nach 3 toten Runden enden, pane get auf Owner: {len(gets)}")

    # Gesunde Zwischenrunde setzt den Zaehler zurueck -> alle Runden laufen
    c = Case(tmp_path, "reset")
    res = _watch(c, 6, STUB_GET_SEQ="missing,missing,ok,missing,missing,ok")
    assert res.returncode == 0, res.stderr
    gets = [g for g in c.of("pane get") if g[2:3] == [ME]]
    assert len(gets) == 6, f"Zaehler-Reset: erwartet 6 Runden mit pane get, gesehen {len(gets)}"

    # Ohne Binary: weiterlaufen
    c = Case(tmp_path, "nobin")
    env = c.env(OPENSPEC_PLAN_WATCH_ROUNDS="0", OPENSPEC_PLAN_WATCH_INTERVAL="0.05",
                HERDR_BIN_PATH=str(c.root / "gibt-es-nicht"))
    proc = subprocess.Popen(
        [sys.executable, str(WORKFLOW_PY), "plan", "--watch", "--target", ME],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=c.cwd)
    try:
        time.sleep(1.5)
        assert proc.poll() is None, "Watcher ohne Herdr-Binary hat sich beendet"
    finally:
        proc.kill()
        proc.wait(timeout=10)


# --- AC-8 -------------------------------------------------------------------

def test_watcher_exits_when_workflow_py_missing(tmp_path):
    c = Case(tmp_path, "nowfpy")
    hooks = c.root / "hooks"
    shutil.copytree(HOOKS_DIR, hooks, ignore=shutil.ignore_patterns("__pycache__"))
    env = c.env(OPENSPEC_PLAN_WATCH_ROUNDS="0", OPENSPEC_PLAN_WATCH_INTERVAL="0.05",
                STUB_GET_SEQ="ok", PYTHONUNBUFFERED="1")
    proc = subprocess.Popen(
        [sys.executable, str(hooks / "workflow.py"), "plan", "--watch", "--target", ME],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=c.cwd)
    try:
        time.sleep(1.0)
        assert proc.poll() is None, "Watcher endete schon vor dem Entfernen von workflow.py"
        (hooks / "workflow.py").unlink()
        deadline = time.monotonic() + 8
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert proc.poll() is not None, "Watcher laeuft trotz fehlender workflow.py weiter"
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)


# --- AC-9 -------------------------------------------------------------------

def test_fail_open_everywhere(tmp_path):
    def world(c: Case) -> None:
        c.write_world([claude_pane(cwd=c.cwd),
                       plan_pane("pp-own", c.cwd, owner=ME, workflow=WF, version=OLD_VERSION),
                       plan_pane("pp-stale", c.cwd)])

    scenarios = (
        ("herdr-fehlt", {"HERDR_BIN_PATH": "/gibt/es/nicht/herdr"}),
        ("env-fehlt", {"HERDR_ENV": None, "HERDR_PANE_ID": None, "HERDR_WORKSPACE_ID": None}),
        ("list-fehler", {"STUB_LIST_MODE": "fail"}),
        ("list-kaputt", {"STUB_LIST_MODE": "garbage"}),
        ("close-fehler", {"STUB_CLOSE_EXIT": "1"}),
    )
    for label, extra in scenarios:
        for mode in ("sweep", "session-end"):
            c = Case(tmp_path, f"{label}-{mode}")
            world(c)
            before = c.panes()
            res = c.runner(**extra) if mode == "sweep" else c.session_end("other", **extra)
            tag = f"{label}/{mode}"
            assert res.returncode == 0, (tag, res.returncode)
            assert res.stdout == "", (tag, res.stdout)
            assert res.stderr == "", (tag, res.stderr)
            gone = set(before) - set(c.panes())
            assert not gone, f"{tag}: Panes geschlossen: {sorted(gone)}"
            if label == "close-fehler":
                # Kontrolle: der Pfad lief wirklich bis zum pane close
                assert c.of("pane close"), f"{tag}: kein pane close versucht: {c.calls()}"
            elif label in ("list-fehler", "list-kaputt"):
                assert c.of("pane list"), f"{tag}: kein pane list versucht: {c.calls()}"
                assert c.of("pane close") == [], (tag, c.calls())


# --- AC-10 ------------------------------------------------------------------

def test_session_start_not_delayed_and_close_is_lightweight(tmp_path):
    # Banner kehrt trotz haengendem Herdr sofort zurueck; Runner laeuft auch ohne Workflow
    c = Case(tmp_path, "banner", workflow=False)
    c.write_world([claude_pane(cwd=c.cwd), plan_pane("pp-stale", c.cwd)])
    env = c.env(STUB_SLEEP="4")
    t0 = time.monotonic()
    res = subprocess.run([sys.executable, str(SESSION_BANNER)],
                         input=json.dumps({"source": "startup", "cwd": c.cwd}),
                         capture_output=True, text=True, env=env, cwd=c.cwd, timeout=60)
    elapsed = time.monotonic() - t0
    assert res.returncode == 0, res.stderr
    assert elapsed < 3.0, f"session_banner wartete auf Herdr: {elapsed:.2f}s"
    deadline = time.monotonic() + 8
    while not c.of("pane list") and time.monotonic() < deadline:
        time.sleep(0.05)
    assert c.of("pane list"), (
        f"SessionStart ohne Workflow stiess keinen Sweep an: {c.calls()}")

    # plan-pane-close: endet bei haengendem Herdr unter der Hook-Kappung
    c = Case(tmp_path, "close-hang")
    c.write_world([claude_pane(cwd=c.cwd),
                   plan_pane("pp-own", c.cwd, owner=ME, workflow=WF, version=_version())])
    t0 = time.monotonic()
    res = c.session_end("other", STUB_SLEEP="30")
    elapsed = time.monotonic() - t0
    assert res.returncode == 0, res.stderr
    assert res.stdout == "" and res.stderr == "", (res.stdout, res.stderr)
    assert c.of("pane list"), f"plan-pane-close rief Herdr gar nicht auf: {c.calls()}"
    assert elapsed < 1.25, f"plan-pane-close zu langsam bei haengendem Herdr: {elapsed:.2f}s"

    # plan-pane-close importiert weder config_loader noch workflow
    c = Case(tmp_path, "close-imports")
    c.write_world([claude_pane(cwd=c.cwd),
                   plan_pane("pp-own", c.cwd, owner=ME, workflow=WF, version=_version())])
    mods = c.root / "modules.json"
    probe = (
        "import json, runpy, sys\n"
        f"sys.argv = [{str(BRIDGE)!r}, 'plan-pane-close']\n"
        "try:\n"
        f"    runpy.run_path({str(BRIDGE)!r}, run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
        f"open({str(mods)!r}, 'w').write(json.dumps(sorted(sys.modules)))\n"
    )
    payload = json.dumps({"hook_event_name": "SessionEnd", "reason": "other", "cwd": c.cwd})
    res = subprocess.run([sys.executable, "-c", probe], input=payload, capture_output=True,
                         text=True, env=c.env(), cwd=c.cwd, timeout=60)
    assert res.returncode == 0, res.stderr
    assert c.closed() == ["pp-own"], f"Kontrolle: plan-pane-close schloss nicht: {c.calls()}"
    loaded = set(json.loads(mods.read_text()))
    assert "config_loader" not in loaded, "plan-pane-close importiert config_loader"
    assert "workflow" not in loaded, "plan-pane-close importiert workflow"


# --- AC-11 ------------------------------------------------------------------

def test_hooks_json_registers_session_end_close_first():
    hooks = json.loads(HOOKS_JSON.read_text())["hooks"]
    groups = hooks.get("SessionEnd")
    assert isinstance(groups, list) and groups, hooks.get("SessionEnd")
    entries = groups[0].get("hooks") or []
    assert entries, groups
    first = entries[0]
    command = first.get("command", "")
    assert command.split() == [
        "${CLAUDE_PLUGIN_ROOT}/core/hooks/herdr_bridge.py", "plan-pane-close"] or (
        "${CLAUDE_PLUGIN_ROOT}/core/hooks/herdr_bridge.py" in command
        and command.rstrip().endswith("plan-pane-close")), (
        f"erster SessionEnd-Eintrag ist nicht plan-pane-close: {first}")
    timeout = first.get("timeout")
    assert isinstance(timeout, (int, float)) and 0 < timeout <= 2, first


# --- Adversary-Runde 1 (F001-F004) ------------------------------------------

def test_sweep_never_touches_agent_panes(tmp_path):
    """F001: Ein Pane mit gesetztem `agent` ist nie ein Plan-Pane — egal welches Label."""
    c = Case(tmp_path, "agent-label")
    other = claude_pane(OTHER, cwd=c.cwd)
    other["label"] = LABEL                                  # Nutzer nannte es "Workflow"
    other["tokens"] = {"workflow": "anderer-wf", "phase": "phase6_implement"}
    codex = {"pane_id": "pane-codex", "workspace_id": WS, "label": LABEL,
             "cwd": f"{c.cwd} (deleted)", "agent": "codex", "agent_status": "working"}
    c.write_world([claude_pane(cwd=c.cwd), other, codex,
                   plan_pane("pp-stale", c.cwd)])           # Kontrolle: echte Altlast
    res = c.runner()
    assert res.returncode == 0, res.stderr
    assert "pp-stale" in c.closed(), f"Kontrolle: Sweep lief nicht: {c.calls()}"
    assert c.touching(OTHER) == [], f"Claude-Pane mit Label Workflow angefasst: {c.calls()}"
    assert c.touching("pane-codex") == [], f"Agent-Pane angefasst: {c.calls()}"
    assert {OTHER, "pane-codex"} <= set(c.panes()), c.panes()

    # SessionEnd fasst ebenfalls kein Agent-Pane an, selbst mit owner == ich
    c = Case(tmp_path, "agent-label-end")
    odd = claude_pane(OTHER, cwd=c.cwd)
    odd["label"] = LABEL
    odd["tokens"] = {"owner": ME}
    c.write_world([claude_pane(cwd=c.cwd), odd])
    res = c.session_end("other")
    assert res.returncode == 0, res.stderr
    assert c.of("pane close") == [], f"SessionEnd schloss ein Agent-Pane: {c.calls()}"


LOCKED_STUB = r'''
import fcntl, os, sys, time
delay = float(os.environ.get("STUB_CALL_DELAY") or 0)
if delay:
    time.sleep(delay)          # ausserhalb der Sperre: Aufrufe zweier Runner verzahnen sich
fd = os.open(os.environ["STUB_WORLD"] + ".lock", os.O_CREAT | os.O_RDWR, 0o644)
fcntl.flock(fd, fcntl.LOCK_EX)  # jeder Aufruf atomar auf der Welt
exec(compile(open(os.environ["STUB_INNER"]).read(), "stub", "exec"))
'''


def test_concurrent_spawn_sets_owner_before_label(tmp_path):
    """F002: owner-Token VOR dem Label; gleichzeitige Runner behalten je ein Pane."""
    c = Case(tmp_path, "order")
    c.write_world([claude_pane(cwd=c.cwd)])
    res = c.runner()
    assert res.returncode == 0, res.stderr
    seq = [" ".join(x[:2]) for x in c.calls()
           if " ".join(x[:2]) in ("pane rename", "pane report-metadata")
           and x[2:3] == ["pane-new-1"]]
    assert "pane rename" in seq and "pane report-metadata" in seq, c.calls()
    assert seq.index("pane report-metadata") < seq.index("pane rename"), (
        f"Label vor owner-Token gesetzt: {seq}")

    # Zwei Sessions im selben Workspace starten (fast) gleichzeitig
    offsets = [round(0.05 * i, 2) for i in range(20)]
    cases = []
    for off in offsets:
        cc = Case(tmp_path, f"race-{off}")
        inner = cc.root / "stub-inner.py"
        inner.write_text(STUB_SOURCE)
        cc.stub.write_text(f"#!{sys.executable}\n" + LOCKED_STUB)
        cc.write_world([claude_pane(cwd=cc.cwd), claude_pane(OTHER, cwd=cc.cwd)])
        cases.append((off, cc, inner))

    def start(cc, inner, pane):
        env = cc.env(HERDR_PANE_ID=pane, STUB_INNER=str(inner), STUB_CALL_DELAY="0.15")
        return subprocess.Popen(
            [sys.executable, str(BRIDGE), "plan-pane", "--pane", pane, "--cwd", cc.cwd,
             "--ratio", "0.75", "--delay", "0"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=cc.cwd)

    procs = []
    t0 = time.monotonic()
    for off, cc, inner in cases:
        procs.append(start(cc, inner, ME))
    for off, cc, inner in sorted(cases, key=lambda x: x[0]):
        wait = off - (time.monotonic() - t0)
        if wait > 0:
            time.sleep(wait)
        procs.append(start(cc, inner, OTHER))
    for p in procs:
        p.wait(timeout=60)
    bad = []
    for off, cc, inner in cases:
        owners = sorted(str(_tokens_of(p).get("owner")) for p in cc.panes().values()
                        if p.get("label") == LABEL)
        if owners != sorted([ME, OTHER]) or cc.closed():
            bad.append((off, owners, cc.closed()))
    assert not bad, f"gleichzeitiger Start: Session ohne eigenes Plan-Pane: {bad}"


def _tokens_of(pane: dict) -> dict:
    t = pane.get("tokens")
    return t if isinstance(t, dict) else {}


def test_sweep_skips_when_self_not_listed(tmp_path):
    """F003: steht das eigene Pane nicht in `pane list --workspace W`, wird nichts geschlossen."""
    c = Case(tmp_path, "self-missing")
    c.write_world([claude_pane(OTHER, cwd=c.cwd),
                   plan_pane("pp-stale", c.cwd),
                   plan_pane("pp-dead", f"{c.cwd} (deleted)", owner=GONE)])
    res = c.runner()
    assert res.returncode == 0, res.stderr
    assert c.of("pane list"), f"kein pane list: {c.calls()}"
    assert c.of("pane close") == [], f"Sweep ohne eigenes Pane in der Liste: {c.calls()}"
    assert c.of("pane split") == [], f"Pane geoeffnet ohne eigenes Pane: {c.calls()}"


def test_legacy_pane_of_living_owner_kept(tmp_path):
    """F004: ownerloses Plan-Pane aus der #493-ID-Datei eines LEBENDEN Claude-Panes bleibt."""
    c = Case(tmp_path, "legacy")
    (c.proj / ".claude" / "herdr_plan_pane.json").write_text(json.dumps({"panes": {
        OTHER: {"pane_id": "pp-legacy", "cwd": c.cwd},
        GONE: {"pane_id": "pp-legacy-dead", "cwd": c.cwd}}}))
    legacy = plan_pane("pp-legacy", c.cwd)
    c.write_world([claude_pane(cwd=c.cwd), claude_pane(OTHER, cwd=c.cwd), legacy,
                   plan_pane("pp-legacy-dead", c.cwd)])
    res = c.runner()
    assert res.returncode == 0, res.stderr
    assert "pp-legacy-dead" in c.closed(), f"Kontrolle: toter Altbestand blieb: {c.calls()}"
    assert c.touching("pp-legacy") == [], f"Altbestand einer lebenden Session angefasst: {c.calls()}"
    assert c.panes().get("pp-legacy") == legacy, c.panes().get("pp-legacy")


# --- Adversary-Runde 2 (F001-F003) ------------------------------------------

def _ids_file(c: Case) -> Path:
    return c.proj / ".claude" / "herdr_plan_pane.json"


def test_nested_child_session_leaves_panes_alone(tmp_path):
    """F001: ein Kind-Claude (CLAUDE_PID nicht Vordergrund von $HERDR_PANE_ID) fasst nichts an."""
    v = _version()
    kinds = ("pane close", "pane report-metadata", "pane rename", "pane run", "pane split")

    def world(c: Case) -> dict:
        parent = plan_pane("pp-parent", c.cwd, owner=ME, workflow=WF, version=v)
        c.write_world([claude_pane(cwd=c.cwd), parent, plan_pane("pp-stale", c.cwd)])
        _ids_file(c).write_text(json.dumps({"panes": {ME: {"pane_id": "pp-parent",
                                                             "cwd": "/eltern"}}}))
        return parent

    # SessionStart des Kindes: ohne aktiven Workflow, mit anderem Workflow, mit demselben
    for label, wf in (("start-ohne-wf", None), ("start-anderer-wf", "kind-wf"),
                      ("start-gleicher-wf", WF)):
        c = Case(tmp_path, label, workflow=False)
        if wf:
            c.set_workflow(wf)
        parent = world(c)
        ids = _ids_file(c).read_text()
        res = c.runner(CLAUDE_PID=CHILD_PID)
        assert res.returncode == 0, (label, res.stderr)
        changed = [x for x in c.calls() if " ".join(x[:2]) in kinds]
        assert changed == [], f"{label}: Kind-Session veraenderte Panes: {changed}"
        assert c.panes().get("pp-parent") == parent, (label, c.panes().get("pp-parent"))
        assert _ids_file(c).read_text() == ids, f"{label}: cwd-Cache der Eltern umgeschrieben"

    # SessionEnd des Kindes (reason other / prompt_input_exit)
    for reason in ("other", "prompt_input_exit"):
        c = Case(tmp_path, f"end-{reason}")
        parent = world(c)
        res = c.session_end(reason, CLAUDE_PID=CHILD_PID)
        assert res.returncode == 0, (reason, res.stderr)
        assert c.of("pane close") == [], f"SessionEnd des Kindes schloss: {c.calls()}"
        assert c.panes().get("pp-parent") == parent

    # Ohne CLAUDE_PID oder ohne verwertbares process-info: im Zweifel nichts tun
    for label, extra in (("ohne-claude-pid", {"CLAUDE_PID": None}),
                         ("procinfo-fehler", {"STUB_PROCINFO_MODE": "fail"}),
                         ("procinfo-kaputt", {"STUB_PROCINFO_MODE": "garbage"})):
        for mode in ("start", "end"):
            c = Case(tmp_path, f"{label}-{mode}", workflow=False)
            world(c)
            res = c.runner(**extra) if mode == "start" else c.session_end("other", **extra)
            assert res.returncode == 0 and res.stdout == "" and res.stderr == "", (label, res)
            changed = [x for x in c.calls() if " ".join(x[:2]) in kinds]
            assert changed == [], f"{label}/{mode}: im Zweifel trotzdem gehandelt: {changed}"

    # Kontrolle: dieselbe Welt mit der Eltern-PID -> Sweep bzw. SessionEnd greifen
    c = Case(tmp_path, "kontrolle-start", workflow=False)
    world(c)
    c.runner()
    assert "pp-parent" in c.closed(), f"Kontrolle Start: {c.calls()}"
    c = Case(tmp_path, "kontrolle-end")
    world(c)
    c.session_end("other")
    assert c.closed() == ["pp-parent"], f"Kontrolle Ende: {c.calls()}"


def test_rename_failure_closes_fresh_pane(tmp_path):
    """F002: scheitert `rename` nach `report-metadata`, wird das neue Pane geschlossen."""
    c = Case(tmp_path, "rename-fail")
    c.write_world([claude_pane(cwd=c.cwd)])
    res = c.runner(STUB_RENAME_EXIT="1")
    assert res.returncode == 0, res.stderr
    assert c.of("pane split"), f"Kontrolle: kein split: {c.calls()}"
    assert c.closed() == ["pane-new-1"], f"neues Pane ohne Label blieb: {c.calls()}"
    assert c.of("pane run") == [], f"Watcher trotz Rename-Fehler gestartet: {c.calls()}"
    assert set(c.panes()) == {ME}, c.panes()

    # Eigene Panes OHNE Label, aber mit allen drei Tokens: Sweep erkennt sie als eigene
    v = _version()
    c = Case(tmp_path, "unlabelled")
    own = lambda pid: dict(plan_pane(pid, c.cwd, owner=ME, workflow=WF, version=v),  # noqa: E731
                           label="")
    partial = dict(plan_pane("pp-partial", c.cwd, owner=ME, workflow=WF), label="")
    foreign = dict(plan_pane("pp-foreign", c.cwd, owner=OTHER, workflow=WF, version=v),
                   label="")
    c.write_world([claude_pane(cwd=c.cwd), claude_pane(OTHER, cwd=c.cwd),
                   own("pp-u1"), own("pp-u2"), own("pp-u3"), partial, foreign])
    res = c.runner()
    assert res.returncode == 0, res.stderr
    left = {"pp-u1", "pp-u2", "pp-u3"} & set(c.panes())
    assert len(left) == 1, f"eigene Duplikate ohne Label nicht erkannt: {c.calls()}"
    assert c.of("pane split") == [], f"trotz eigenem Pane neu geoeffnet: {c.calls()}"
    assert c.touching("pp-partial") == [] and c.touching("pp-foreign") == [], c.calls()
    res = c.session_end("other")
    assert res.returncode == 0, res.stderr
    assert not ({"pp-u1", "pp-u2", "pp-u3"} & set(c.panes())), (
        f"SessionEnd liess eigenes Pane ohne Label stehen: {c.panes()}")
    assert {"pp-partial", "pp-foreign", ME, OTHER} <= set(c.panes()), c.panes()


def test_abort_never_closes_owner_pane(tmp_path):
    """F003: liefert `pane split` die eigene Pane-ID, wird sie nie angefasst."""
    for label, extra in (("meta-fail", {"STUB_META_EXIT": "1"}),
                         ("rename-fail", {"STUB_RENAME_EXIT": "1"}),
                         ("ok", {})):
        c = Case(tmp_path, f"self-{label}")
        c.write_world([claude_pane(cwd=c.cwd)])
        res = c.runner(STUB_SPLIT_ID=ME, **extra)
        assert res.returncode == 0, (label, res.stderr)
        assert c.of("pane split"), f"{label}: Kontrolle: kein split: {c.calls()}"
        assert c.touching(ME) == [], f"{label}: eigenes Claude-Pane angefasst: {c.touching(ME)}"
        assert ME in c.panes(), label
