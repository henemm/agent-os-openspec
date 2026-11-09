"""Auftragsliste auf der Platte: Mehr-Issue-Auftrag ueberlebt `/clear` (Issue #551).

Spec: docs/specs/feat-551-auftragsliste.md (AC-1 bis AC-9).

Vertraege aus der Spec (Implementation Details), die diese Tests festlegen:
- Datei `<Haupt-Repo>/.claude/auftrag.json` (`find_project_root()`), gitignoriert,
  Form `{"issues": [{"n": int, "status": "open"|"done"}], "autark": bool, "note": str,
  "created": str, "updated": str}`; geschrieben per `atomic_write_text(path, text, root=)`.
- CLI `workflow.py queue [list|add <N..> [--autark] [--note T]|done <N>|clear]`:
  Ausgabe `QUEUE=<offen,kommagetrennt|none>`, `AUTARK=on|off`, `NEXT=<N|none>` und bei
  offenem Auftrag `PROMPT=/00-intake #<NEXT>` (autark ergaenzt um
  ` (autark: Auftrag aus .claude/auftrag.json weiter abarbeiten, kein Halt für /clear)`).
  Kill-Switch `auftrag.enabled: false` -> genau `QUEUE=disabled`, Exit 0, keine Schreibung.
- `end_state(..., queue_next=None, autark=False)`; feste Zeilen fuer ⏳ und ❗ (AC-4).
- `context` -> `CONTEXT_CUT=off` + `CONTEXT_REASON=AUTARK`; `autoclear` -> `AUTO_CLEAR=off`;
  `hook_utils.context_cut_note(tokens, threshold, autark=False)`.
- `hook_utils.auftrag_settings(config) -> {"enabled": bool}` (nur Literal `false` schaltet ab).

workflow.py/hook_utils werden erst im Testkoerper importiert, CLI und Hooks laufen als
Subprozess (frischer Config-Cache je Aufruf): fehlende Funktionen erscheinen als
Test-FAIL, nicht als Collection-Error.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
BANNER_PY = HOOKS_DIR / "session_banner.py"
COMMANDS_DIR = REPO_ROOT / "core" / "commands"
SKILLS_DIR = REPO_ROOT / "skills"

sys.path.insert(0, str(Path(__file__).resolve().parent))

AUTARK_SUFFIX = " (autark: Auftrag aus .claude/auftrag.json weiter abarbeiten, kein Halt für /clear)"
WAIT_548 = "⏳ Läuft noch: Claude startet #548 aus deinem Auftrag. Du musst nichts tun, ich melde mich."
YOU_548 = "❗ Du: /00-intake #548 — nächstes Issue aus deinem Auftrag"
KILL_CFG = "auftrag:\n  enabled: false\n"
CONTEXT_CFG = "context_budget:\n  enabled: true\n  clear_threshold_tokens: 100000\n"
WF547 = "feat-547-x"


# --- Helpers ---------------------------------------------------------------

def _wf():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _hu():
    sys.path.insert(0, str(HOOKS_DIR))
    import hook_utils  # noqa: PLC0415
    return hook_utils


def _env(proj: "Path | None" = None, **extra: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("OPENSPEC_", "HERDR_", "STUB_"))
           and k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PLUGIN_ROOT")}
    if proj is not None:
        env["CLAUDE_PROJECT_DIR"] = str(proj)
        home = proj / "_home"
        home.mkdir(exist_ok=True)
        env["HOME"] = str(home)
    env.update(extra)
    return env


def _cli(proj: Path, *args: str, env: "dict | None" = None, cwd: "Path | None" = None):
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args], capture_output=True,
                          text=True, env=env if env is not None else _env(proj),
                          cwd=str(cwd or proj), timeout=60)


def _kv(stdout: str, key: str) -> "str | None":
    for line in stdout.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


def _plain_project(root: Path, config: "str | None" = None) -> Path:
    """Main-Repo (.git als Verzeichnis), ohne Workflow."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    (root / ".claude" / "workflows").mkdir(parents=True, exist_ok=True)
    if config is not None:
        (root / ".claude" / "config.yaml").write_text(config)
    return root


def _auftrag_path(root: Path) -> Path:
    return root / ".claude" / "auftrag.json"


def _write_auftrag(root: Path, issues, autark: bool = False, note: str = "") -> Path:
    path = _auftrag_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "issues": [{"n": n, "status": s} for n, s in issues],
        "autark": autark, "note": note,
        "created": "2026-11-09T10:00:00Z", "updated": "2026-11-09T10:00:00Z",
    }))
    return path


def _read_auftrag(root: Path) -> dict:
    return json.loads(_auftrag_path(root).read_text())


def _status_of(root: Path) -> dict:
    return {e["n"]: e["status"] for e in _read_auftrag(root)["issues"]}


def _data(name: str = WF547, phase: str = "phase8_complete", **fields) -> dict:
    data = {"name": name, "workflow_type": "feature", "current_phase": phase,
            "phase_transitions": [], "phase_log": []}
    data.update(fields)
    return data


def _active_project(root: Path, data: dict, config: "str | None" = None) -> Path:
    proj = _plain_project(root, config)
    wf_dir = proj / ".claude" / "workflows"
    (wf_dir / "_log").mkdir(exist_ok=True)
    (wf_dir / "_archive").mkdir(exist_ok=True)
    (wf_dir / f"{data['name']}.json").write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(data["name"])
    return proj


def _completable(root: Path, name: str = WF547, config: "str | None" = None) -> Path:
    """Wie tests/test_workflow_finish_alias.py: Fast Track mit erfuellten Vorbedingungen."""
    root.mkdir(parents=True, exist_ok=True)
    spec = root / "docs" / "specs" / "x.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("## Architektur-Entscheidung (ADR)\n\n- **ADR-Nr.:** keine\n")
    wf_dir = root / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / f"{name}.json").write_text(json.dumps({
        "name": name, "workflow_type": "feature-fast", "spec_file": "docs/specs/x.md",
        "spec_approved": True, "current_phase": "phase8_complete",
        "context_file": "docs/context/x.md", "affected_files": [], "test_artifacts": [],
        "adversary_verdict": None,
    }))
    (wf_dir / "_log").mkdir(exist_ok=True)
    (wf_dir / "_log" / f"20261109100000_{name}.yaml").write_text("outcome: success\n")
    (root / ".claude" / "active_workflow").write_text(name)
    if config is not None:
        (root / ".claude" / "config.yaml").write_text(config)
    return root


def _complete(proj: Path, name: str = WF547):
    return _cli(proj, "complete", env=_env(proj, OPENSPEC_ACTIVE_WORKFLOW=name))


# Kontext-Messung (Muster tests/test_kontext_haushalt.py): Hooks in .claude/hooks kopieren

def _ctx_project(root: Path, config: str = CONTEXT_CFG) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    hooks = root / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    for f in HOOKS_DIR.glob("*.py"):
        shutil.copy(f, hooks / f.name)
    (root / ".claude" / "config.yaml").write_text(config)
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    return root


def _ctx_run(root: Path, script: str, *args: str, stdin: "str | None" = None, **extra):
    env = _env(**extra)
    return subprocess.run([sys.executable, str(root / ".claude" / "hooks" / script), *args],
                          cwd=root, env=env, capture_output=True, text=True,
                          input=stdin, timeout=60)


def _transcript(path: Path, tokens: int) -> Path:
    rows = [{"type": "user", "message": {}},
            {"type": "assistant", "message": {"usage": {
                "input_tokens": 40, "cache_creation_input_tokens": 2000,
                "cache_read_input_tokens": tokens - 2040, "output_tokens": 5}}}]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def _post_bash_run(root: Path, tokens: int, session: str) -> subprocess.CompletedProcess:
    tr = _transcript(root / "t.jsonl", tokens)
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"},
                          "tool_response": {"stdout": "", "stderr": ""},
                          "session_id": session, "transcript_path": str(tr)})
    res = _ctx_run(root, "post_bash.py", stdin=payload)
    assert res.returncode == 0, res.stderr
    return res


def _post_bash_note(root: Path, tokens: int = 122_040, session: str = "s1") -> str:
    # #557: der erste Messwert einer Sitzung ist der Grundkontext (Baseline). Ein
    # kleiner Erstwert (20k) laesst die wirksame Schwelle bei 100k, wie vor #557.
    if not (root / ".claude" / "context_usage" / f"{session}.json").exists():
        assert _post_bash_run(root, 20_000, session).stdout.strip() == ""
    res = _post_bash_run(root, tokens, session)
    assert res.stdout.strip(), f"kein Kontext-Hinweis, stderr={res.stderr!r}"
    return json.loads(res.stdout)["hookSpecificOutput"]["additionalContext"]


def _context_lines(root: Path, session: str = "s1") -> list:
    res = _ctx_run(root, "workflow.py", "context", CLAUDE_CODE_SESSION_ID=session)
    assert res.returncode == 0, res.stderr
    return res.stdout.splitlines()


# Auto-/clear im Herdr-Pane (Muster tests/test_autoclear_boundary_495.py)

def _autoclear_case(root: Path, extra_config: str = ""):
    from test_herdr_auto_clear_467 import AUTO_ON, _hook_case  # noqa: PLC0415
    root.mkdir(parents=True, exist_ok=True)
    proj, _log, _stub, env = _hook_case(root, config=AUTO_ON + extra_config)
    return proj, env


def _run_autoclear(proj: Path, env: dict):
    return subprocess.run([sys.executable, str(WORKFLOW_PY), "autoclear"],
                          capture_output=True, text=True, env=env, cwd=str(proj),
                          timeout=30)


def _autoclear_state(proj: Path) -> dict:
    from test_herdr_auto_clear_467 import WF  # noqa: PLC0415
    return json.loads((proj / ".claude" / "workflows" / f"{WF}.json").read_text())


# status_note / Banner: frischer Prozess je Aufruf (Config-Cache)

def _status_note(proj: Path, data: dict) -> "str | None":
    code = ("import json, sys\n"
            f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            "import workflow\n"
            "print(json.dumps(workflow.status_note(json.loads(sys.stdin.read()))))\n")
    res = subprocess.run([sys.executable, "-c", code], input=json.dumps(data),
                         capture_output=True, text=True, env=_env(proj),
                         cwd=str(proj), timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


def _plugin(root: Path) -> Path:
    plugin = root / "plugin"
    (plugin / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "agent-os-openspec", "version": "9.9.9"}))
    (plugin / "skills").mkdir(exist_ok=True)
    return plugin


def _banner(proj: Path, plugin: Path, source: str) -> dict:
    env = _env(proj, CLAUDE_PLUGIN_ROOT=str(plugin))
    res = subprocess.run([sys.executable, str(BANNER_PY)],
                         input=json.dumps({"source": source, "cwd": str(proj)}),
                         capture_output=True, text=True, env=env, cwd=str(proj),
                         timeout=60)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip(), f"keine Banner-Ausgabe, stderr={res.stderr!r}"
    return json.loads(res.stdout)


def _banner_context(out: dict) -> str:
    return (out.get("hookSpecificOutput") or {}).get("additionalContext") or ""


# --- AC-1 -------------------------------------------------------------------

def test_queue_add_list_done_clear(tmp_path):
    proj = _plain_project(tmp_path / "p")
    path = _auftrag_path(proj)

    res = _cli(proj, "queue", "add", "547", "548", "--autark", "--note", "komplett autark")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "QUEUE") == "547,548", res.stdout
    assert _kv(res.stdout, "AUTARK") == "on", res.stdout
    assert _kv(res.stdout, "NEXT") == "547", res.stdout
    assert _kv(res.stdout, "PROMPT") == "/00-intake #547" + AUTARK_SUFFIX, res.stdout
    assert path.is_file(), "queue add legt .claude/auftrag.json an"
    data = _read_auftrag(proj)
    assert data["autark"] is True, data
    assert data["note"] == "komplett autark", data
    assert [(e["n"], e["status"]) for e in data["issues"]] == [(547, "open"), (548, "open")]

    # Lesend: `queue` und `queue list` liefern dieselbe Ausgabe, schreiben nichts
    before = path.read_bytes()
    for args in (("queue",), ("queue", "list")):
        lst = _cli(proj, *args)
        assert lst.returncode == 0, (args, lst.stderr)
        assert lst.stdout == res.stdout, (args, lst.stdout, res.stdout)
    assert path.read_bytes() == before

    # done
    done = _cli(proj, "queue", "done", "547")
    assert done.returncode == 0, (done.stdout, done.stderr)
    assert _kv(done.stdout, "QUEUE") == "548", done.stdout
    assert _kv(done.stdout, "NEXT") == "548", done.stdout
    assert _kv(done.stdout, "AUTARK") == "on", done.stdout
    assert _kv(done.stdout, "PROMPT") == "/00-intake #548" + AUTARK_SUFFIX, done.stdout
    assert _status_of(proj) == {547: "done", 548: "open"}

    # done mit unbekannter Nummer: stderr, Exit 1
    bad = _cli(proj, "queue", "done", "999")
    assert bad.returncode == 1, (bad.stdout, bad.stderr)
    assert bad.stderr.strip(), "Meldung auf stderr erwartet"

    # add ohne --autark nimmt autark nicht zurueck; Doppelte ignoriert; erledigte wieder offen
    add2 = _cli(proj, "queue", "add", "548", "549")
    assert add2.returncode == 0, (add2.stdout, add2.stderr)
    assert _kv(add2.stdout, "QUEUE") == "548,549", add2.stdout
    assert _kv(add2.stdout, "AUTARK") == "on", add2.stdout
    assert [e["n"] for e in _read_auftrag(proj)["issues"]] == [547, 548, 549]
    add3 = _cli(proj, "queue", "add", "547")
    assert add3.returncode == 0, (add3.stdout, add3.stderr)
    assert _kv(add3.stdout, "QUEUE") == "547,548,549", add3.stdout
    assert _status_of(proj) == {547: "open", 548: "open", 549: "open"}
    assert [e["n"] for e in _read_auftrag(proj)["issues"]] == [547, 548, 549]

    # clear: Datei weg, leere Ausgabe ohne PROMPT; idempotent
    for _ in range(2):
        clr = _cli(proj, "queue", "clear")
        assert clr.returncode == 0, (clr.stdout, clr.stderr)
        assert not path.exists()
        assert _kv(clr.stdout, "QUEUE") == "none", clr.stdout
        assert _kv(clr.stdout, "AUTARK") == "off", clr.stdout
        assert _kv(clr.stdout, "NEXT") == "none", clr.stdout
        assert _kv(clr.stdout, "PROMPT") is None, clr.stdout

    # nicht autark: PROMPT ohne Zusatz
    plain = _cli(proj, "queue", "add", "560")
    assert plain.returncode == 0, (plain.stdout, plain.stderr)
    assert _kv(plain.stdout, "AUTARK") == "off", plain.stdout
    assert _kv(plain.stdout, "PROMPT") == "/00-intake #560", plain.stdout
    _cli(proj, "queue", "clear")

    # Ungueltige Nummern oder keine Nummer: Exit 1, Usage auf stderr, nichts geschrieben
    for args in (("abc",), ("0",), ("-5",), ("12a",), ()):
        inv = _cli(proj, "queue", "add", *args)
        assert inv.returncode == 1, (args, inv.stdout, inv.stderr)
        assert "usage" in inv.stderr.lower(), (args, inv.stderr)
        assert not path.exists(), args

    # Kaputte Datei: lesend wie "kein Auftrag", `add` ersetzt sie
    path.write_text("{kaputt")
    lst = _cli(proj, "queue")
    assert lst.returncode == 0, (lst.stdout, lst.stderr)
    assert _kv(lst.stdout, "QUEUE") == "none", lst.stdout
    rep = _cli(proj, "queue", "add", "550")
    assert rep.returncode == 0, (rep.stdout, rep.stderr)
    assert _kv(rep.stdout, "QUEUE") == "550", rep.stdout
    assert _status_of(proj) == {550: "open"}

    # `queue` steht in COMMANDS, `batch` findet es
    bat = _cli(proj, "batch", "queue", "add", "551", "--", "queue")
    assert bat.returncode == 0, (bat.stdout, bat.stderr)
    assert "QUEUE=550,551" in bat.stdout.splitlines(), bat.stdout


# --- AC-2 -------------------------------------------------------------------

def _git(cwd: Path, *args: str):
    return subprocess.run(["git", "-c", "user.email=t@t.invalid", "-c", "user.name=T",
                           "-c", "commit.gpgsign=false", *args], cwd=cwd, check=True,
                          capture_output=True, text=True)


def test_auftrag_file_in_main_repo_atomic_and_gitignored(tmp_path):
    # .gitignore des Frameworks
    lines = [ln.strip() for ln in (REPO_ROOT / ".gitignore").read_text().splitlines()]
    assert ".claude/auftrag.json" in lines, "Eintrag .claude/auftrag.json fehlt in .gitignore"

    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main", ".")
    (main / "f.txt").write_text("x\n")
    _git(main, "add", ".")
    _git(main, "commit", "-q", "-m", "init")
    wt = tmp_path / "wt"
    _git(main, "worktree", "add", "-q", "-b", "wt-551", str(wt))
    sub = wt / "sub" / "dir"
    sub.mkdir(parents=True)
    (wt / "_home").mkdir()

    # (a) aus einem Worktree-Unterordner, ohne CLAUDE_PROJECT_DIR
    env = _env(HOME=str(wt / "_home"))
    res = _cli(wt, "queue", "add", "547", env=env, cwd=sub)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "QUEUE") == "547", res.stdout
    assert _auftrag_path(main).is_file(), "Datei muss im Haupt-Repo liegen"
    assert not _auftrag_path(wt).exists(), "Datei darf nicht im Worktree liegen"
    assert not (sub / ".claude" / "auftrag.json").exists()

    # (b) aus dem Worktree mit CLAUDE_PROJECT_DIR=Worktree
    res = _cli(wt, "queue", "add", "548", env=_env(wt), cwd=wt)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert not _auftrag_path(wt).exists()

    # (c) aus dem Haupt-Repo: dieselbe Datei
    res = _cli(main, "queue", "add", "549", env=_env(main), cwd=main)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "QUEUE") == "547,548,549", res.stdout

    data = _read_auftrag(main)
    for key in ("issues", "autark", "created", "updated"):
        assert key in data, (key, data)
    assert data["autark"] is False, data
    assert [(e["n"], e["status"]) for e in data["issues"]] == \
        [(547, "open"), (548, "open"), (549, "open")]
    assert isinstance(data["created"], str) and data["created"], data
    assert isinstance(data["updated"], str) and data["updated"], data
    leftovers = [p.name for p in (main / ".claude").iterdir()
                 if p.name.endswith(".tmp") or (p.name.startswith(".") and p.is_file())]
    assert leftovers == [], f"Temp-Reste: {leftovers}"

    # Geschrieben ueber hook_utils.atomic_write_text mit root=
    proj = _plain_project(tmp_path / "spy")
    code = ("import json, sys\n"
            f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            "import hook_utils\n"
            "calls = []\n"
            "orig = hook_utils.atomic_write_text\n"
            "def spy(path, text, root=None):\n"
            "    calls.append([str(path), None if root is None else str(root)])\n"
            "    return orig(path, text, root=root)\n"
            "hook_utils.atomic_write_text = spy\n"
            "import workflow\n"
            "sys.argv = ['workflow.py', 'queue', 'add', '547']\n"
            "try:\n"
            "    workflow.main()\n"
            "except SystemExit:\n"
            "    pass\n"
            "print('SPY=' + json.dumps(calls))\n")
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=_env(proj), cwd=str(proj), timeout=60)
    assert res.returncode == 0, res.stderr
    calls = json.loads(_kv(res.stdout, "SPY") or "[]")
    hits = [c for c in calls if c[0].endswith("auftrag.json")]
    assert hits, f"auftrag.json nicht ueber atomic_write_text geschrieben: {calls}"
    assert all(c[1] is not None and Path(c[1]).resolve() == proj.resolve() for c in hits), hits

    # Verweis an der Zielstelle: das Ziel ausserhalb bleibt unangetastet
    proj2 = _plain_project(tmp_path / "link")
    outside = tmp_path / "outside.json"
    outside.write_text("ORIGINAL")
    _auftrag_path(proj2).symlink_to(outside)
    _cli(proj2, "queue", "add", "547")
    assert outside.read_text() == "ORIGINAL"


# --- AC-3 -------------------------------------------------------------------

def test_complete_marks_issue_done_fail_open(tmp_path):
    # Auftrag mit 547 und 548: complete fuer feat-547-x hakt 547 ab
    proj = _completable(tmp_path / "with")
    _write_auftrag(proj, [(547, "open"), (548, "open")], autark=True)
    res = _complete(proj)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert (proj / ".claude" / "workflows" / "_archive" / f"{WF547}.json").is_file()
    assert _status_of(proj) == {547: "done", 548: "open"}
    assert _read_auftrag(proj)["autark"] is True

    # Ohne Auftragsdatei: unveraendert, keine Datei angelegt
    proj = _completable(tmp_path / "without")
    base = _complete(proj)
    assert base.returncode == 0, (base.stdout, base.stderr)
    assert not _auftrag_path(proj).exists()
    assert "Traceback" not in base.stderr, base.stderr

    # Kaputtes JSON: Exit 0, Datei byte-gleich, Ausgabe wie ohne Auftrag
    proj = _completable(tmp_path / "broken")
    _auftrag_path(proj).write_text("{kaputt")
    res = _complete(proj)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _auftrag_path(proj).read_text() == "{kaputt"
    assert res.stdout == base.stdout, (res.stdout, base.stdout)
    assert "Traceback" not in res.stderr, res.stderr

    # Workflow ohne Issue-Nummer: Auftrag unangetastet
    proj = _completable(tmp_path / "noissue", name="demo-auftrag")
    path = _write_auftrag(proj, [(547, "open"), (548, "open")])
    before = path.read_bytes()
    res = _complete(proj, name="demo-auftrag")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert path.read_bytes() == before


# --- AC-4 -------------------------------------------------------------------

def test_end_state_with_queue_and_plan_matches_endstate(tmp_path):
    wf = _wf()
    data = _data()
    for archived in (False, True):
        es = wf.end_state(data, archived=archived)
        assert es["kind"] == "done" and es["line"].startswith("✅ Erledigt"), es
        es = wf.end_state(data, archived=archived, queue_next=None, autark=True)
        assert es["kind"] == "done" and es["line"].startswith("✅ Erledigt"), es

        es = wf.end_state(data, archived=archived, queue_next=548, autark=True)
        assert es["kind"] == "waiting", es
        assert es["line"] == WAIT_548, es

        es = wf.end_state(data, archived=archived, queue_next=548, autark=False)
        assert es["kind"] == "you", es
        assert es["line"] == YOU_548, es
        assert es["cmd"] == "/00-intake #548", es

    # Unveraendert: Phasen vor 8, waiting_on-Vorrang, Deploy-Faelle
    for extra in ({"phase": "phase6_implement"}, {"waiting_on": "CI von PR 12"},
                  {"phase": "phase6_implement", "waiting_on": "CI von PR 12"}):
        d = _data(**extra)
        assert wf.end_state(d, queue_next=548, autark=True) == wf.end_state(d), extra
        assert wf.end_state(d, queue_next=548, autark=False) == wf.end_state(d), extra
    for fields, autonomous in (({}, False), ({}, True), ({"deploy_status": "running"}, False),
                               ({"deploy_status": "failed"}, True)):
        d = _data(**fields)
        ref = wf.end_state(d, deploy="configured", autonomous=autonomous)
        for autark in (True, False):
            got = wf.end_state(d, deploy="configured", autonomous=autonomous,
                               queue_next=548, autark=autark)
            assert got == ref, (fields, autonomous, autark, got, ref)

    # CLI: endstate und Plan-Schlusszeile identisch
    cases = [
        ("none", None, "done", None),
        ("empty", ([(547, "done"), (548, "done")], True), "done", None),
        ("autark", ([(547, "open"), (548, "open")], True), "waiting", WAIT_548),
        ("manual", ([(547, "done"), (548, "open")], False), "you", YOU_548),
    ]
    for label, auftrag, kind, line in cases:
        proj = _active_project(tmp_path / label, _data())
        if auftrag is not None:
            _write_auftrag(proj, auftrag[0], autark=auftrag[1])
        es = _cli(proj, "endstate")
        assert es.returncode == 0, (label, es.stdout, es.stderr)
        assert _kv(es.stdout, "ENDSTATE") == kind, (label, es.stdout)
        footer = _kv(es.stdout, "FOOTER")
        assert footer, (label, es.stdout)
        if line is None:
            assert footer.startswith("✅ Erledigt"), (label, footer)
        else:
            assert footer == line, (label, footer)
        plan = _cli(proj, "plan")
        assert plan.returncode == 0, (label, plan.stdout, plan.stderr)
        assert plan.stdout.rstrip("\n").splitlines()[-1] == footer, (label, plan.stdout)

    # Archivierter Workflow, abgefragt per #547
    proj = _plain_project(tmp_path / "archived")
    (proj / ".claude" / "workflows" / "_archive").mkdir()
    (proj / ".claude" / "workflows" / "_archive" / f"{WF547}.json").write_text(
        json.dumps(_data()))
    _write_auftrag(proj, [(547, "done"), (548, "open")], autark=True)
    es = _cli(proj, "endstate", "#547")
    assert es.returncode == 0, (es.stdout, es.stderr)
    assert _kv(es.stdout, "ENDSTATE") == "waiting", es.stdout
    assert _kv(es.stdout, "FOOTER") == WAIT_548, es.stdout


# --- AC-5 -------------------------------------------------------------------

def test_autark_keeps_chain_going(tmp_path):
    hu = _hu()
    note = hu.context_cut_note(168_464, 100_000, autark=True)
    assert note.startswith("KONTEXT-SCHWELLE"), note
    assert "~168.464 Token" in note and "Schwelle 100.000" in note, note
    for forbidden in ("beende den Turn", "Turn beenden", "NICHT selbst aufrufen"):
        assert forbidden not in note, (forbidden, note)
    assert "/compact" in note, note
    assert "autark" in note.lower(), note
    assert "Explore-Teilagent" in note and "Zeilenbereich" in note and "batch" in note, note

    # post_bash reicht die autarke Lage durch; context meldet off + AUTARK
    root = _ctx_project(tmp_path / "ctx")
    _write_auftrag(root, [(547, "open"), (548, "open")], autark=True)
    hint = _post_bash_note(root)
    assert hint.startswith("KONTEXT-SCHWELLE") and "~122.040" in hint, hint
    assert "beende den Turn" not in hint and "NICHT selbst aufrufen" not in hint, hint
    assert "/compact" in hint, hint
    lines = _context_lines(root)
    assert "CONTEXT_TOKENS=122040" in lines, lines
    assert "CONTEXT_CUT=off" in lines, lines
    assert "CONTEXT_REASON=AUTARK" in lines, lines
    assert "CONTEXT_CUT=on" not in lines and len(lines) == 3, lines

    # autoclear im Herdr-Pane mit Auto-/clear: off, kein Grenz-Vermerk
    proj, env = _autoclear_case(tmp_path / "ac")
    _write_auftrag(proj, [(547, "open"), (548, "open")], autark=True)
    res = _run_autoclear(proj, env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "AUTO_CLEAR=off", res.stdout
    assert "auto_clear_boundary" not in _autoclear_state(proj)


# --- AC-6 -------------------------------------------------------------------

def test_without_autark_queue_behaviour_unchanged(tmp_path):
    hu = _hu()
    base = hu.context_cut_note(168_464, 100_000)
    assert "beende den Turn" in base and "NICHT selbst aufrufen" in base, base
    assert hu.context_cut_note(168_464, 100_000, autark=False) == base

    variants = {
        "none": None,
        "manual": ([(547, "open"), (548, "open")], False),
        "alldone": ([(547, "done"), (548, "done")], True),
    }
    for label, auftrag in variants.items():
        root = _ctx_project(tmp_path / f"ctx-{label}")
        if auftrag is not None:
            _write_auftrag(root, auftrag[0], autark=auftrag[1])
        hint = _post_bash_note(root)
        assert "beende den Turn" in hint, (label, hint)
        lines = _context_lines(root)
        assert lines == ["CONTEXT_TOKENS=122040", "CONTEXT_CUT=on",
                         "CONTEXT_THRESHOLD=100000"], (label, lines)

        proj, env = _autoclear_case(tmp_path / f"ac-{label}")
        if auftrag is not None:
            _write_auftrag(proj, auftrag[0], autark=auftrag[1])
        res = _run_autoclear(proj, env)
        assert res.returncode == 0, (label, res.stderr)
        assert res.stdout.strip() == "AUTO_CLEAR=on", (label, res.stdout)
        assert isinstance(_autoclear_state(proj).get("auto_clear_boundary"), dict), label


# --- AC-7 -------------------------------------------------------------------

def test_status_note_and_banner_mention_open_queue(tmp_path):
    data = _data(phase="phase7_validate")
    plugin = _plugin(tmp_path)

    # Ohne Auftrag: Referenz
    ref = _plain_project(tmp_path / "ref")
    ref_note = _status_note(ref, data)
    assert ref_note and "auftrag.json" not in ref_note, ref_note
    ref_banner = {src: _banner(ref, plugin, src) for src in ("startup", "clear", "compact")}
    for src, out in ref_banner.items():
        assert "auftrag.json" not in _banner_context(out), (src, out)
        assert "#548" not in _banner_context(out), (src, out)

    for autark in (True, False):
        proj = _plain_project(tmp_path / f"q-{autark}")
        _write_auftrag(proj, [(547, "done"), (548, "open"), (549, "open")], autark=autark,
                       note="Setze 547, 548 und 549 um")
        note = _status_note(proj, data)
        assert note, "status_note liefert einen Vermerk"
        assert note.startswith(ref_note.split("\n", 1)[0]), (ref_note, note)
        texts = {"status_note": note}
        for src in ("startup", "clear", "compact"):
            out = _banner(proj, plugin, src)
            assert out.get("systemMessage") == ref_banner[src].get("systemMessage"), (src, out)
            texts[f"banner:{src}"] = _banner_context(out)
        for where, text in texts.items():
            assert "#548" in text, (autark, where, text)
            assert "/00-intake #548" in text, (autark, where, text)
            if autark:
                assert "autark" in text.lower(), (where, text)
            else:
                assert "kein Halt für /clear" not in text, (where, text)


# --- AC-8 -------------------------------------------------------------------

def _paragraph_with(text: str, needle: str) -> str:
    for para in text.split("\n\n"):
        if needle in para:
            return para
    return ""


def test_command_texts_and_skills_in_sync():
    intake = (COMMANDS_DIR / "00-intake.md").read_text(encoding="utf-8")
    assert "workflow.py queue add" in intake, "00-intake.md: Anweisung `workflow.py queue add` fehlt"
    assert "--autark" in intake, "00-intake.md: `--autark` fehlt"
    skill = (SKILLS_DIR / "00-intake" / "SKILL.md").read_text(encoding="utf-8")
    assert "workflow.py queue add" in skill, "skills/00-intake/SKILL.md nicht synchron"

    for name in ("60-validate", "70-deploy"):
        text = (COMMANDS_DIR / f"{name}.md").read_text(encoding="utf-8")
        assert "workflow.py queue" in text, name
        para = _paragraph_with(text, "/00-intake #M")
        assert para, f"{name}.md: Kette `/00-intake #M` fehlt"
        assert "ENDSTATE=waiting" in para, (name, para)
        skill = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
        assert "/00-intake #M" in skill, f"skills/{name}/SKILL.md nicht synchron"

    res = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"),
                          "--check"], capture_output=True, text=True, cwd=str(REPO_ROOT),
                         timeout=60)
    assert res.returncode == 0, (res.stdout, res.stderr)


# --- AC-9 -------------------------------------------------------------------

def test_kill_switch_disables_everything(tmp_path):
    hu = _hu()
    assert hu.auftrag_settings({}) == {"enabled": True}
    assert hu.auftrag_settings({"auftrag": {"enabled": False}}) == {"enabled": False}
    assert hu.auftrag_settings({"auftrag": {"enabled": "no"}}) == {"enabled": True}
    assert hu.auftrag_settings({"auftrag": "kaputt"}) == {"enabled": True}

    queue_items = [(547, "open"), (548, "open")]

    # queue: QUEUE=disabled, Exit 0, keine Schreibung
    proj = _plain_project(tmp_path / "q", KILL_CFG)
    path = _write_auftrag(proj, queue_items, autark=True)
    before = path.read_bytes()
    for args in (("queue",), ("queue", "list"), ("queue", "add", "549"),
                 ("queue", "done", "547"), ("queue", "clear")):
        res = _cli(proj, *args)
        assert res.returncode == 0, (args, res.stdout, res.stderr)
        assert res.stdout.strip() == "QUEUE=disabled", (args, res.stdout)
        assert path.exists() and path.read_bytes() == before, args
    empty = _plain_project(tmp_path / "q-empty", KILL_CFG)
    res = _cli(empty, "queue", "add", "549")
    assert res.returncode == 0 and res.stdout.strip() == "QUEUE=disabled", res.stdout
    assert not _auftrag_path(empty).exists()

    # complete: Auftrag bleibt unangetastet
    proj = _completable(tmp_path / "complete", config=KILL_CFG)
    path = _write_auftrag(proj, queue_items, autark=True)
    before = path.read_bytes()
    res = _complete(proj)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert path.read_bytes() == before

    # endstate / plan: ✅ wie ohne Auftrag
    proj = _active_project(tmp_path / "endstate", _data(), config=KILL_CFG)
    _write_auftrag(proj, queue_items, autark=True)
    es = _cli(proj, "endstate")
    assert es.returncode == 0, (es.stdout, es.stderr)
    assert _kv(es.stdout, "ENDSTATE") == "done", es.stdout
    assert (_kv(es.stdout, "FOOTER") or "").startswith("✅ Erledigt"), es.stdout

    # context / post_bash: CONTEXT_CUT=on ohne CONTEXT_REASON, bisheriger Hinweis
    root = _ctx_project(tmp_path / "ctx", CONTEXT_CFG + KILL_CFG)
    _write_auftrag(root, queue_items, autark=True)
    hint = _post_bash_note(root)
    assert "beende den Turn" in hint, hint
    assert _context_lines(root) == ["CONTEXT_TOKENS=122040", "CONTEXT_CUT=on",
                                    "CONTEXT_THRESHOLD=100000"]

    # autoclear: on wie ohne Auftrag
    proj, env = _autoclear_case(tmp_path / "ac", extra_config=KILL_CFG)
    _write_auftrag(proj, queue_items, autark=True)
    res = _run_autoclear(proj, env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "AUTO_CLEAR=on", res.stdout

    # status_note und Banner: kein Auftragssatz
    data = _data(phase="phase7_validate")
    plugin = _plugin(tmp_path)
    ref = _plain_project(tmp_path / "ref", KILL_CFG)
    proj = _plain_project(tmp_path / "note", KILL_CFG)
    _write_auftrag(proj, [(547, "done"), (548, "open")], autark=True)
    assert _status_note(proj, data) == _status_note(ref, data)
    for src in ("startup", "clear", "compact"):
        ctx = _banner_context(_banner(proj, plugin, src))
        assert "auftrag.json" not in ctx and "#548" not in ctx, (src, ctx)
