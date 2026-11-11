"""Tests fuer Issue #522: Gates in Cloud-Sitzungen fuer Plugin-Konsumenten.

Spec: docs/specs/feat-522-cloud-plugin-gates.md (AC-1 bis AC-21).

Aufbau (Spec, "Testaufbau"): echte Dateien in tmp_path, echte Subprozesse, kein
Mock der Shell oder von git. Als Framework-Quelle dient ein lokales Git-Repo mit
annotiertem Tag `agent-os-openspec--v9.9.9`, erreichbar per
`AGENT_OS_CLOUD_REPO=file://...`; der Cache liegt per `AGENT_OS_CLOUD_CACHE` im
tmp_path, HOME zeigt auf ein Wegwerf-Verzeichnis (kein Zugriff auf ~/.cache,
kein Netz).

Der Baustein `core/cloud_bootstrap.py` wird pro Test in das Fake-Projekt nach
`.claude/cloud_bootstrap.py` kopiert und von dort gestartet, wie im Konsumenten.

Die `setup.py`-Tests laufen gegen eine Kopie des Frameworks (ohne `.git`, Version
in `.claude-plugin/plugin.json` auf 9.9.9 gesetzt): Die lokale Tag-Aufloesung
(`git -C <framework> rev-parse`) findet dort nichts, die Pin-Aufloesung geht
deterministisch an `git ls-remote` gegen `AGENT_OS_CLOUD_REPO` (Annahme: setup.py
nutzt fuer die URL dieselbe Variable wie der Baustein).
"""

import importlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
BOOT_SRC = REPO_ROOT / "core" / "cloud_bootstrap.py"
ARTIFACT = REPO_ROOT / "docs" / "artifacts" / "feat-522-cloud-plugin-gates" / "cloud-session-events.json"

FW_VERSION = "9.9.9"
TAG = f"agent-os-openspec--v{FW_VERSION}"
RETRY = "python3 .claude/cloud_bootstrap.py --retry"
PO_EXIT = "PO: `override` tippen (gilt 1 h für diese Sitzung)"
ORIG_RE = re.compile(r"^\$\{CLAUDE_PLUGIN_ROOT\}/core/hooks/(\S+\.py)(.*)$")
CONSUMER_PREFIX = '[ "$CLAUDE_CODE_REMOTE" != "true" ] || python3 -I "${CLAUDE_PROJECT_DIR}/.claude/cloud_bootstrap.py" '
# Alt-Form vor Adversary F008 (ohne `-I`): `--update` muss sie erkennen und ersetzen.
OLD_CONSUMER_PREFIX = '[ "$CLAUDE_CODE_REMOTE" != "true" ] || python3 "${CLAUDE_PROJECT_DIR}/.claude/cloud_bootstrap.py" '

WRITE_TOOLS = ["Edit", "Write", "MultiEdit", "NotebookEdit", "WebFetch", "Agent",
               "mcp__github__issue_write"]
READ_TOOLS = ["Read", "Grep", "Glob"]

TOOL_INPUTS = {
    "Edit": {"file_path": "src/a.py", "old_string": "a", "new_string": "b"},
    "Write": {"file_path": "src/a.py", "content": "x"},
    "MultiEdit": {"file_path": "src/a.py", "edits": [{"old_string": "a", "new_string": "b"}]},
    "NotebookEdit": {"notebook_path": "n.ipynb", "new_source": "x"},
    "WebFetch": {"url": "https://example.invalid", "prompt": "x"},
    "Agent": {"description": "x", "prompt": "x"},
    "mcp__github__issue_write": {"title": "x"},
    "Read": {"file_path": "README.md"},
    "Grep": {"pattern": "x"},
    "Glob": {"pattern": "*.py"},
}

# Hook-Skript im Fake-Framework: schreibt stdin, CLAUDE_PLUGIN_ROOT und Marker in die
# Datei aus `probe_out` (stdin-JSON), Exit-Code aus `probe_exit` (stdin-JSON).
PROBE = r'''import json, os, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except Exception:
    data = {}
out = data.get("probe_out") if isinstance(data, dict) else None
if out:
    with open(out, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"marker": "probe-ran", "stdin": raw,
                             "root": os.environ.get("CLAUDE_PLUGIN_ROOT"),
                             "argv": sys.argv[1:]}) + "\n")
print("PROBE-STDOUT")
print("PROBE-STDERR", file=sys.stderr)
sys.exit(int(data.get("probe_exit", 0)) if isinstance(data, dict) else 0)
'''
BANNER = 'import sys\nsys.stdin.read()\nprint("BANNER-FROM-CACHE")\n'


# ------------------------------------------------------------------ Umgebung
def _clean_env() -> dict:
    drop = ("CLAUDE_", "GIT_", "AGENT_OS_", "OPENSPEC_")
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    return env


def _git(args, cwd) -> str:
    r = subprocess.run(["git", "-c", "user.email=t@t.invalid", "-c", "user.name=Test",
                        "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
                       cwd=str(cwd), capture_output=True, text=True, env=_clean_env())
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout.strip()


def _make_framework_repo(path: Path, tag: str = TAG) -> "tuple[str, str]":
    """Fake-Framework-Repo mit annotiertem Tag; liefert (Commit-SHA, Tag-Objekt-SHA)."""
    hooks = path / "core" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "probe.py").write_text(PROBE, encoding="utf-8")
    (hooks / "phase_listener.py").write_text(PROBE, encoding="utf-8")
    (hooks / "session_banner.py").write_text(BANNER, encoding="utf-8")
    (path / ".claude-plugin").mkdir()
    (path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "agent-os-openspec", "version": FW_VERSION}), encoding="utf-8")
    _git(["init", "-q", "-b", "main"], path)
    _git(["add", "-A"], path)
    _git(["commit", "-q", "-m", "release"], path)
    _git(["tag", "-a", tag, "-m", f"release {tag}"], path)
    commit = _git(["rev-parse", f"{tag}^{{commit}}"], path)
    tag_obj = _git(["rev-parse", tag], path)
    assert commit != tag_obj, "Tag muss annotiert sein"
    return commit, tag_obj


class Ctx:
    """Fake-Framework + Konsumenten-Projekt + Cache-Basis fuer den Baustein."""

    def __init__(self, tmp_path: Path):
        self.tmp = tmp_path
        self.repo = tmp_path / "framework"
        self.sha, self.tag_obj = _make_framework_repo(self.repo)
        self.url = self.repo.as_uri()
        self.bad_url = (tmp_path / "gibt-es-nicht").as_uri()
        self.proj = tmp_path / "proj mit Leerzeichen"
        (self.proj / ".claude").mkdir(parents=True)
        self.base = tmp_path / "cache-base"
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.out = tmp_path / "probe_out.jsonl"
        self.boot = self.proj / ".claude" / "cloud_bootstrap.py"

    @property
    def cache(self) -> Path:
        return self.base / TAG

    def pin(self, ref=TAG, sha=None, present=True):
        data = {"framework_version": None, "plugin_mode": True}
        if present:
            data.update(cloud_ref=ref, cloud_sha=sha or self.sha)
        (self.proj / ".claude" / "framework_version.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8")

    def install(self):
        assert BOOT_SRC.exists(), "core/cloud_bootstrap.py fehlt (Baustein #522 nicht implementiert)"
        shutil.copy(BOOT_SRC, self.boot)

    def env(self, url=None, **extra) -> dict:
        env = _clean_env()
        env.update(CLAUDE_PROJECT_DIR=str(self.proj), CLAUDE_CODE_REMOTE="true",
                   AGENT_OS_CLOUD_CACHE=str(self.base), AGENT_OS_CLOUD_REPO=url or self.url,
                   HOME=str(self.home), GIT_CEILING_DIRECTORIES=str(self.tmp))
        env.update(extra)
        return env

    def run(self, *args, payload="", url=None, **extra):
        return subprocess.run([sys.executable, str(self.boot), *args], input=payload,
                              cwd=str(self.proj), env=self.env(url, **extra),
                              capture_output=True, text=True, timeout=60)

    def probe_records(self) -> list:
        if not self.out.exists():
            return []
        return [json.loads(line) for line in self.out.read_text(encoding="utf-8").splitlines()
                if line.strip()]


def _ctx(tmp_path, pin=True, **pin_kw) -> Ctx:
    ctx = Ctx(tmp_path)
    ctx.pin(present=pin, **pin_kw)
    ctx.install()
    return ctx


def _ev(event, tool=None, session="sessA", tool_input=None, **extra) -> str:
    data = {"hook_event_name": event, "session_id": session, "cwd": "/x"}
    if tool is not None:
        data["tool_name"] = tool
        data["tool_input"] = tool_input if tool_input is not None else TOOL_INPUTS.get(tool, {})
    data.update(extra)
    return json.dumps(data, ensure_ascii=False)


def _bash_ev(cmd, session="sessA") -> str:
    return _ev("PreToolUse", "Bash", session=session, tool_input={"command": cmd})


def _subdirs(path: Path) -> list:
    return sorted(p.name for p in path.iterdir() if p.is_dir()) if path.exists() else []


def _paths(*roots) -> set:
    return {str(p) for r in roots if r.exists() for p in r.rglob("*")}


def _events_log(ctx) -> list:
    path = ctx.proj / ".claude" / "gate-events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _clone_count(trace_dir: Path) -> int:
    count = 0
    for f in trace_dir.iterdir():
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("event") == "cmd_name" and ev.get("name") == "clone":
                count += 1
    return count


def _load_sync():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    sys.modules.pop("sync_cloud_hooks", None)
    return importlib.import_module("sync_cloud_hooks")


def _expected_consumer(hooks_json: dict) -> dict:
    """Erwarteter Konsumenten-Block, unabhaengig von der Implementierung berechnet."""
    out = {}
    for event, groups in hooks_json["hooks"].items():
        out_groups = []
        for g in groups:
            ng = {k: v for k, v in g.items() if k != "hooks"}
            ng["hooks"] = []
            for h in g["hooks"]:
                m = ORIG_RE.match(h["command"])
                assert m, h["command"]
                nh = {k: v for k, v in h.items() if k not in ("command", "timeout")}
                nh["command"] = CONSUMER_PREFIX + m.group(1) + m.group(2)
                if "timeout" in h:
                    nh["timeout"] = h["timeout"] + 25
                ng["hooks"].append(nh)
            out_groups.append(ng)
        out[event] = out_groups
    return out


def _assert_consumer_entries(settings_hooks: dict, hooks_json: dict):
    expected = _expected_consumer(hooks_json)
    total = 0
    for event, groups in expected.items():
        for g in groups:
            for h in g["hooks"]:
                total += 1
                hits = [x for sg in settings_hooks.get(event, [])
                        if sg.get("matcher") == g.get("matcher")
                        for x in sg.get("hooks", []) if x == h]
                assert len(hits) == 1, f"{event}/{g.get('matcher')!r}: {h['command']} {len(hits)}x"
    found = [x for groups in settings_hooks.values() for sg in groups
             for x in sg.get("hooks", []) if "cloud_bootstrap.py" in x.get("command", "")]
    assert len(found) == total, f"{len(found)} Baustein-Eintraege statt {total}"


# ------------------------------------------------------------------ AC-1
def test_bootstrap_fetches_tag_and_forwards_stdin_and_exit_code(tmp_path):
    ctx = _ctx(tmp_path)
    payload = _ev("PreToolUse", "Edit", probe_out=str(ctx.out), probe_exit=2, x="ü")
    r = ctx.run("probe.py", payload=payload)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "PROBE-STDOUT" in r.stdout
    assert "PROBE-STDERR" in r.stderr
    recs = ctx.probe_records()
    assert len(recs) == 1, recs
    assert recs[0]["marker"] == "probe-ran"
    assert recs[0]["stdin"] == payload
    assert Path(recs[0]["root"]).resolve() == ctx.cache.resolve()
    assert (ctx.cache / ".ok").exists()
    assert _git(["rev-parse", "HEAD"], ctx.cache) == ctx.sha
    assert not (ctx.home / ".cache").exists(), "~/.cache darf im Test nicht beruehrt werden"


# ------------------------------------------------------------------ AC-2
def test_command_runs_only_in_cloud(tmp_path):
    mod = _load_sync()
    ctx = Ctx(tmp_path)
    ctx.pin()
    cmd = mod.consumer_command("${CLAUDE_PLUGIN_ROOT}/core/hooks/probe.py")
    assert cmd == CONSUMER_PREFIX + "probe.py"
    payload = _ev("PreToolUse", "Edit", probe_out=str(ctx.out), probe_exit=2)

    # Stolperdraht statt Baustein: wird er lokal gestartet, entsteht der Marker.
    trip = tmp_path / "tripwire"
    ctx.boot.write_text(f"open({str(trip)!r}, 'w').write('x')\nraise SystemExit(3)\n",
                        encoding="utf-8")

    def run(remote):
        env = ctx.env()
        env.pop("CLAUDE_CODE_REMOTE", None)
        if remote is not None:
            env["CLAUDE_CODE_REMOTE"] = remote
        return subprocess.run(["bash", "-c", cmd], input=payload, env=env, cwd=str(ctx.proj),
                              capture_output=True, text=True, timeout=60)

    for remote in (None, "false"):
        r = run(remote)
        assert r.returncode == 0, (remote, r.stderr)
        assert not trip.exists(), f"Baustein lokal gestartet (CLAUDE_CODE_REMOTE={remote})"
        assert not ctx.base.exists(), "Cache lokal beruehrt"
        assert not ctx.out.exists()

    ctx.install()
    r = run("true")
    assert r.returncode == 2, r.stdout + r.stderr
    recs = ctx.probe_records()
    assert len(recs) == 1 and recs[0]["stdin"] == payload


# ------------------------------------------------------------------ AC-3
def test_sha_mismatch_fails_closed_and_leaves_no_cache(tmp_path):
    ctx = _ctx(tmp_path, sha="0123456789abcdef0123456789abcdef01234567")
    r = ctx.run("probe.py", payload=_ev("PreToolUse", "Edit", probe_out=str(ctx.out)))
    assert r.returncode == 2, r.stdout + r.stderr
    assert "sha" in r.stderr.lower(), r.stderr
    assert not ctx.cache.exists()
    assert _subdirs(ctx.base) == [], f"Reste im Cache: {_subdirs(ctx.base)}"
    assert not list(ctx.base.rglob(".ok")) if ctx.base.exists() else True
    assert not ctx.out.exists(), "probe.py darf bei SHA-Abweichung nicht starten"


# ------------------------------------------------------------------ AC-1/AC-3: Cache-Unversehrtheit (Adversary F003)
def test_tampered_cache_is_not_executed(tmp_path):
    ctx = _ctx(tmp_path)
    evil = tmp_path / "evil-ran"
    evil_src = f"open({str(evil)!r}, 'w').write('x')\nraise SystemExit(0)\n"
    payload = _ev("PreToolUse", "Edit", probe_out=str(ctx.out), probe_exit=2)
    probe = ctx.cache / "core" / "hooks" / "probe.py"

    def assert_original_ran(r, runs):
        assert r.returncode == 2, r.stdout + r.stderr
        assert not evil.exists(), "manipulierte Fassung wurde ausgefuehrt"
        assert len(ctx.probe_records()) == runs
        assert not os.path.islink(ctx.cache)
        assert probe.read_text(encoding="utf-8") == PROBE

    assert_original_ran(ctx.run("probe.py", payload=payload), 1)

    # 1. Skript im Cache umgeschrieben, `.ok` unveraendert -> neu geholt, Original laeuft
    probe.write_text(evil_src, encoding="utf-8")
    assert_original_ran(ctx.run("probe.py", payload=payload), 2)

    # 2. assume-unchanged versteckt die Aenderung vor `git status` -> trotzdem erkannt
    _git(["update-index", "--assume-unchanged", "core/hooks/probe.py"], ctx.cache)
    probe.write_text(evil_src, encoding="utf-8")
    assert_original_ran(ctx.run("probe.py", payload=payload), 3)

    # 3. Untergeschobene ignorierte Datei (Bytecode) -> neu geholt
    pyc = ctx.cache / "core" / "hooks" / "__pycache__" / "probe.cpython-39.pyc"
    pyc.parent.mkdir()
    pyc.write_bytes(b"x" * 64)
    assert_original_ran(ctx.run("probe.py", payload=payload), 4)
    assert not pyc.exists()

    # 4. Cache-Ordner ist ein Symlink auf eine manipulierte Kopie mit passendem `.ok`
    fake = tmp_path / "fake-cache"
    shutil.copytree(str(ctx.cache), str(fake), symlinks=True)
    (fake / "core" / "hooks" / "probe.py").write_text(evil_src, encoding="utf-8")
    shutil.rmtree(str(ctx.cache))
    os.symlink(str(fake), str(ctx.cache))
    assert_original_ran(ctx.run("probe.py", payload=payload), 5)

    # 5. Skript im Cache ist ein Symlink -> nicht ausgefuehrt
    evil_file = tmp_path / "evil.py"
    evil_file.write_text(evil_src, encoding="utf-8")
    probe.unlink()
    os.symlink(str(evil_file), str(probe))
    assert_original_ran(ctx.run("probe.py", payload=payload), 6)

    # 6. Clean-Filter in der Cache-Config tarnt die Aenderung vor `git status` (F007):
    #    trotzdem erkannt, und der Filter-Befehl selbst laeuft nie. Gleiche Groesse wie
    #    das Original, damit `git status` den Inhalt durch den Filter neu hasht.
    filter_ran = tmp_path / "filter-ran"
    padded = evil_src + "#" * (len(PROBE.encode()) - len(evil_src.encode()) - 1) + "\n"
    assert len(padded.encode()) == len(PROBE.encode())
    probe.write_text(padded, encoding="utf-8")
    clean = f"sh -c 'touch {filter_ran}; git show HEAD:core/hooks/probe.py'"
    _git(["config", "filter.f.clean", clean], ctx.cache)
    _git(["config", "filter.f.smudge", "cat"], ctx.cache)
    (ctx.cache / ".git" / "info").mkdir(exist_ok=True)
    (ctx.cache / ".git" / "info" / "attributes").write_text(
        "core/hooks/probe.py filter=f\n", encoding="utf-8")
    assert_original_ran(ctx.run("probe.py", payload=payload), 7)
    assert not filter_ran.exists(), "Filter-Befehl aus der Cache-Config wurde ausgefuehrt"

    # 7. Zusaetzliche .py in core/hooks (kapert `import json` des Skripts) -> neu geholt
    shadow = ctx.cache / "core" / "hooks" / "json.py"
    shadow.write_text(evil_src, encoding="utf-8")
    assert_original_ran(ctx.run("probe.py", payload=payload), 8)
    assert not shadow.exists()

    # 8. Manipuliert und Quelle unerreichbar -> fail-closed (Exit 2), nichts ausgefuehrt
    probe.write_text(evil_src, encoding="utf-8")
    r = ctx.run("probe.py", payload=payload, url=ctx.bad_url)
    assert r.returncode == 2, r.stdout + r.stderr
    assert RETRY in r.stderr, r.stderr
    assert not evil.exists(), "manipulierte Fassung wurde ausgefuehrt"
    assert len(ctx.probe_records()) == 8


# ------------------------------------------------------------------ Adversary F008: Modul-Kaperung
def _hijack_run(ctx, cmd, **extra):
    payload = _ev("PreToolUse", "Edit", probe_out=str(ctx.out), probe_exit=2)
    return subprocess.run(["bash", "-c", cmd], input=payload, env=ctx.env(**extra),
                          cwd=str(ctx.proj), capture_output=True, text=True, timeout=60)


def _assert_not_hijacked(ctx, r, evil):
    assert r.returncode == 2, r.stdout + r.stderr
    assert not evil.exists(), "Stdlib-Modul wurde gekapert (Code vor der Cache-Pruefung)"
    recs = ctx.probe_records()
    assert len(recs) == 1 and recs[0]["marker"] == "probe-ran", recs


def _evil_module(path: Path, evil: Path) -> None:
    path.write_text(f"open({str(evil)!r}, 'w').write('x')\nraise SystemExit(0)\n",
                    encoding="utf-8")


def test_generated_command_ignores_shadow_module_in_claude_dir(tmp_path):
    ctx = _ctx(tmp_path)
    evil = tmp_path / "evil-ran"
    _evil_module(ctx.proj / ".claude" / "json.py", evil)
    cmd = _load_sync().consumer_command("${CLAUDE_PLUGIN_ROOT}/core/hooks/probe.py")
    assert " -I " in cmd, cmd
    _assert_not_hijacked(ctx, _hijack_run(ctx, cmd), evil)


def test_generated_command_ignores_pythonpath_shadow_module(tmp_path):
    ctx = _ctx(tmp_path)
    evil = tmp_path / "evil-ran"
    shadow_dir = tmp_path / "shadow"
    shadow_dir.mkdir()
    _evil_module(shadow_dir / "json.py", evil)
    cmd = _load_sync().consumer_command("${CLAUDE_PLUGIN_ROOT}/core/hooks/probe.py")
    _assert_not_hijacked(ctx, _hijack_run(ctx, cmd, PYTHONPATH=str(shadow_dir)), evil)


@pytest.mark.parametrize("module", ["json", "__future__", "subprocess"])
def test_old_command_without_isolation_ignores_shadow_module(tmp_path, module):
    ctx = _ctx(tmp_path)
    evil = tmp_path / "evil-ran"
    _evil_module(ctx.proj / ".claude" / f"{module}.py", evil)
    cmd = OLD_CONSUMER_PREFIX + "probe.py"
    _assert_not_hijacked(ctx, _hijack_run(ctx, cmd), evil)


# ------------------------------------------------------------------ AC-4
@pytest.mark.parametrize("case", ["bad-url", "missing-tag", "missing-pin", "missing-script"])
def test_fetch_failure_blocks_write_tools(tmp_path, case):
    if case == "missing-tag":
        ctx = _ctx(tmp_path, ref="agent-os-openspec--v0.0.0")
    elif case == "missing-pin":
        ctx = _ctx(tmp_path, pin=False)
    else:
        ctx = _ctx(tmp_path)
    url = ctx.bad_url if case == "bad-url" else None
    script = "nope.py" if case == "missing-script" else "edit_gate.py"

    for tool in WRITE_TOOLS:
        r = ctx.run(script, payload=_ev("PreToolUse", tool), url=url)
        assert r.returncode == 2, f"{case}/{tool}: rc={r.returncode} {r.stderr!r}"
        assert RETRY in r.stderr, f"{case}/{tool}: Abhilfe fehlt: {r.stderr!r}"
        assert "github.com" in r.stderr, f"{case}/{tool}: github.com fehlt"
        assert "override" in r.stderr, f"{case}/{tool}: PO-Ausweg fehlt"
    for tool in READ_TOOLS:
        r = ctx.run(script, payload=_ev("PreToolUse", tool), url=url)
        assert r.returncode == 0, f"{case}/{tool}: rc={r.returncode} {r.stderr!r}"


# ------------------------------------------------------------------ AC-5
def test_bash_whitelist_and_retry_when_fetch_failed(tmp_path):
    ctx = _ctx(tmp_path)
    allowed = [RETRY, "git status", "ls -la", "grep foo src", "git diff --stat", "git log -p -1"]
    denied = ["echo x > f", "ls; rm f", "cat a | sh", "git log $(id)", "touch f",
              # Adversary F001: Optionen erlaubter Befehle, die Programme starten oder schreiben
              "rg --hostname-bin=/bin/true --hyperlink-format=file://{host}{path} . f",
              "rg foo src", "rg --pre=/bin/cat foo",
              "git diff --ext-diff", "git show --ext-diff HEAD", "git log -p --ext-diff",
              "git diff --textconv", "git show --textconv HEAD:a",
              "git log --show-signature", "git diff --output=/tmp/x", "git show --output /tmp/x"]
    for cmd in allowed:
        r = ctx.run("bash_gate.py", payload=_bash_ev(cmd), url=ctx.bad_url)
        assert r.returncode == 0, f"{cmd!r}: rc={r.returncode} {r.stderr!r}"
    for cmd in denied:
        r = ctx.run("bash_gate.py", payload=_bash_ev(cmd), url=ctx.bad_url)
        assert r.returncode == 2, f"{cmd!r}: rc={r.returncode} {r.stderr!r}"


# ------------------------------------------------------------------ AC-6
def test_non_write_events_never_blocked(tmp_path):
    ctx = _ctx(tmp_path)
    cases = [
        ("footer_gate.py", [], _ev("Stop")),
        ("post_bash.py", [], _ev("PostToolUse", "Bash", tool_input={"command": "ls"},
                                 tool_response={"stdout": ""})),
        ("session_singleton_guard.py", ["cleanup"], _ev("SessionEnd", reason="exit")),
        ("phase_listener.py", [], _ev("UserPromptSubmit", prompt="hallo")),
        ("secrets_guard.py", [], _ev("PreToolUse", "Read")),
        ("session_singleton_guard.py", ["guard"], _ev("PreToolUse", "Grep")),
        ("footer_gate.py", [], "{kaputt"),
        ("footer_gate.py", [], ""),
    ]
    for script, args, payload in cases:
        r = ctx.run(script, *args, payload=payload, url=ctx.bad_url)
        assert r.returncode == 0, f"{script} {payload[:40]!r}: rc={r.returncode} {r.stderr!r}"


# ------------------------------------------------------------------ AC-7
def test_session_start_warns_on_failure_and_forwards_on_success(tmp_path):
    ctx = _ctx(tmp_path)
    payload = _ev("SessionStart", source="startup")
    r = ctx.run("session_banner.py", payload=payload, url=ctx.bad_url)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    hso = data["hookSpecificOutput"]
    assert hso.get("hookEventName") == "SessionStart"
    ctx_text = hso["additionalContext"]
    assert "gates" in ctx_text.lower(), ctx_text
    assert RETRY in ctx_text, ctx_text
    assert "BANNER-FROM-CACHE" not in r.stdout

    r = ctx.run("session_banner.py", payload=payload)
    assert r.returncode == 0, r.stderr
    assert "BANNER-FROM-CACHE" in r.stdout
    assert "additionalContext" not in r.stdout
    assert "cloud_bootstrap.py --retry" not in r.stdout + r.stderr


# ------------------------------------------------------------------ AC-8
def test_concurrent_calls_fetch_once_and_leave_valid_cache(tmp_path):
    ctx = _ctx(tmp_path)
    trace = tmp_path / "trace2"
    trace.mkdir()
    env = ctx.env(GIT_TRACE2_EVENT=str(trace))
    payload = _ev("PreToolUse", "Edit", probe_out=str(ctx.out), probe_exit=0)
    procs = [subprocess.Popen([sys.executable, str(ctx.boot), "probe.py"], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              cwd=str(ctx.proj), env=env) for _ in range(6)]
    results = [p.communicate(payload, timeout=60) + (p.returncode,) for p in procs]
    for out, err, rc in results:
        assert rc == 0, err
        assert "PROBE-STDOUT" in out
    assert len(ctx.probe_records()) == 6
    assert _clone_count(trace) == 1, f"{_clone_count(trace)} Klon-Vorgaenge statt 1"
    assert (ctx.cache / ".ok").exists()
    assert _subdirs(ctx.base) == [TAG], f"Reste im Cache: {_subdirs(ctx.base)}"


# ------------------------------------------------------------------ AC-9
def test_cache_reuse_and_retry_and_current_pointer(tmp_path):
    ctx = _ctx(tmp_path)
    payload = _ev("PreToolUse", "Edit", probe_out=str(ctx.out), probe_exit=0)
    assert ctx.run("probe.py", payload=payload).returncode == 0
    assert (ctx.cache / ".ok").exists()
    pointer = ctx.base / "current"
    assert pointer.exists(), "Zeiger <base>/current fehlt"
    assert Path(pointer.read_text(encoding="utf-8").strip()).resolve() == ctx.cache.resolve()

    trace = tmp_path / "trace2"
    trace.mkdir()
    r = ctx.run("probe.py", payload=payload, url=ctx.bad_url, GIT_TRACE2_EVENT=str(trace))
    assert r.returncode == 0, r.stderr
    assert len(ctx.probe_records()) == 2
    assert _clone_count(trace) == 0, "gueltiger Cache darf keinen Abruf ausloesen"

    sentinel = ctx.cache / "sentinel.txt"
    sentinel.write_text("alt", encoding="utf-8")
    r = ctx.run("--retry")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not sentinel.exists(), "--retry muss den Cache verwerfen und neu holen"
    assert (ctx.cache / ".ok").exists()

    r = ctx.run("--retry", url=ctx.bad_url)
    assert r.returncode == 1, r.stdout + r.stderr


# ------------------------------------------------------------------ setup.py-Aufbau
_FW_PARTS = ["setup.py", "config.yaml", ".claude-plugin", "core", "hooks", "scripts", "skills",
             "templates", "modules"]


@pytest.fixture(scope="module")
def fw_copy(tmp_path_factory) -> Path:
    """Framework-Kopie ohne .git, Version 9.9.9 — Pin-Aufloesung nur ueber ls-remote."""
    dst = tmp_path_factory.mktemp("fwcopy") / "agent-os-openspec"
    dst.mkdir()
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for part in _FW_PARTS:
        src = REPO_ROOT / part
        if src.is_dir():
            shutil.copytree(src, dst / part, ignore=ignore)
        elif src.exists():
            shutil.copy2(src, dst / part)
    pj = dst / ".claude-plugin" / "plugin.json"
    data = json.loads(pj.read_text(encoding="utf-8"))
    data["version"] = FW_VERSION
    pj.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return dst


def _remote(tmp_path, tag=TAG) -> "tuple[str, str, str]":
    repo = tmp_path / "remote"
    commit, tag_obj = _make_framework_repo(repo, tag)
    return repo.as_uri(), commit, tag_obj


def _setup(fw: Path, proj: Path, *args, url: str, tmp_path: Path):
    home = tmp_path / "setup-home"
    home.mkdir(exist_ok=True)
    env = _clean_env()
    env.update(AGENT_OS_CLOUD_REPO=url, HOME=str(home), GIT_CEILING_DIRECTORIES=str(fw.parent))
    return subprocess.run([sys.executable, str(fw / "setup.py"), str(proj), *args],
                          cwd=str(fw), env=env, capture_output=True, text=True, timeout=60)


def _plugin_project(tmp_path, name="consumer", settings=None, **fv_extra) -> Path:
    proj = tmp_path / name
    (proj / ".claude").mkdir(parents=True)
    fv = {"framework_version": None, "version_source": "plugin", "note": "x",
          "installed": "2026-01-01T00:00:00", "installed_modules": [], "plugin_mode": True}
    fv.update(fv_extra)
    (proj / ".claude" / "framework_version.json").write_text(json.dumps(fv, indent=2),
                                                             encoding="utf-8")
    if settings is not None:
        (proj / ".claude" / "settings.json").write_text(json.dumps(settings, indent=2) + "\n",
                                                        encoding="utf-8")
    return proj


def _snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _fw_hooks(fw: Path) -> dict:
    return json.loads((fw / "hooks" / "hooks.json").read_text(encoding="utf-8"))


OWN_HOOKS = {
    "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 own_guard.py"}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "python3 own_stop.py", "timeout": 3}]}],
}
OWN_KEYS = {
    "enabledPlugins": {"agent-os-openspec@henemm-private": True},
    "extraKnownMarketplaces": {"henemm-private": {"source": {"source": "github",
                                                             "repo": "henemm/agent-os-openspec"}}},
    "permissions": {"allow": ["Bash(ls:*)"], "deny": ["Read(.env)"]},
    "env": {"PROJ_VAR": "ä"},
}


# ------------------------------------------------------------------ AC-10
def test_cloud_gates_merges_and_is_idempotent(tmp_path, fw_copy):
    url, commit, _ = _remote(tmp_path)
    proj = _plugin_project(tmp_path, settings={**OWN_KEYS, "hooks": json.loads(json.dumps(OWN_HOOKS))})
    r = _setup(fw_copy, proj, "--cloud-gates", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr

    boot = proj / ".claude" / "cloud_bootstrap.py"
    assert boot.exists()
    assert boot.read_bytes() == (fw_copy / "core" / "cloud_bootstrap.py").read_bytes()

    settings = json.loads((proj / ".claude" / "settings.json").read_text(encoding="utf-8"))
    for key, value in OWN_KEYS.items():
        assert settings[key] == value, key
    for event, groups in OWN_HOOKS.items():
        for g in groups:
            for h in g["hooks"]:
                assert any(h in sg.get("hooks", []) for sg in settings["hooks"].get(event, [])
                           if sg.get("matcher") == g.get("matcher")), f"eigener Hook fehlt: {h}"
    _assert_consumer_entries(settings["hooks"], _fw_hooks(fw_copy))

    fv = json.loads((proj / ".claude" / "framework_version.json").read_text(encoding="utf-8"))
    assert fv["plugin_mode"] is True
    assert fv["cloud_ref"] == TAG and fv["cloud_sha"] == commit

    before = _snapshot(proj)
    r = _setup(fw_copy, proj, "--cloud-gates", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _snapshot(proj) == before, "zweiter Lauf hat Dateien geaendert"


# ------------------------------------------------------------------ AC-11
def test_cloud_gates_creates_missing_settings_and_rejects_copy_mode(tmp_path, fw_copy):
    url, commit, _ = _remote(tmp_path)
    proj = _plugin_project(tmp_path)
    r = _setup(fw_copy, proj, "--cloud-gates", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    settings = json.loads((proj / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings["hooks"] == _expected_consumer(_fw_hooks(fw_copy))
    fv = json.loads((proj / ".claude" / "framework_version.json").read_text(encoding="utf-8"))
    assert fv["cloud_ref"] == TAG
    assert re.fullmatch(r"[0-9a-f]{40}", fv["cloud_sha"]), fv["cloud_sha"]
    assert fv["plugin_mode"] is True

    copy_proj = tmp_path / "copymode"
    (copy_proj / ".claude" / "hooks").mkdir(parents=True)
    (copy_proj / ".claude" / "framework_version.json").write_text(
        json.dumps({"framework_version": "4.9.0", "installed_modules": []}), encoding="utf-8")
    before = _snapshot(copy_proj)
    r = _setup(fw_copy, copy_proj, "--cloud-gates", url=url, tmp_path=tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "plugin" in (r.stdout + r.stderr).lower(), "Hinweis auf Plugin-Modus fehlt"
    assert _snapshot(copy_proj) == before


# ------------------------------------------------------------------ AC-12
def test_consumer_hooks_mirror_hooks_json_completely(tmp_path):
    mod = _load_sync()
    src = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    out = mod.consumer_hooks(src)
    assert list(out) == list(src["hooks"])
    for event, groups in src["hooks"].items():
        assert len(out[event]) == len(groups), event
        for g_src, g_out in zip(groups, out[event]):
            assert g_out.get("matcher") == g_src.get("matcher")
            assert len(g_out["hooks"]) == len(g_src["hooks"])
            for h_src, h_out in zip(g_src["hooks"], g_out["hooks"]):
                m = ORIG_RE.match(h_src["command"])
                assert m, h_src["command"]
                assert h_out["type"] == h_src["type"]
                assert h_out["command"] == CONSUMER_PREFIX + m.group(1) + m.group(2)
                assert h_out.get("timeout") == h_src["timeout"] + 25
    assert out == _expected_consumer(src)

    mini = {"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/core/hooks/footer_gate.py"}]}]}}
    assert "timeout" not in mod.consumer_hooks(mini)["Stop"][0]["hooks"][0]

    bad = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python3 x.py"}]}]}}
    with pytest.raises(ValueError):
        mod.consumer_hooks(bad)

    settings_path = REPO_ROOT / ".claude" / "settings.json"
    before = settings_path.read_bytes()
    r = subprocess.run([sys.executable, str(SCRIPTS / "sync_cloud_hooks.py"), "--consumer"],
                       cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == out
    assert settings_path.read_bytes() == before

    r = subprocess.run([sys.executable, str(SCRIPTS / "sync_cloud_hooks.py"), "--check"],
                       cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


# ------------------------------------------------------------------ AC-13
def test_pin_resolution_falls_back_to_ls_remote(tmp_path, fw_copy):
    assert subprocess.run(["git", "-C", str(fw_copy), "rev-parse", f"{TAG}^{{commit}}"],
                          capture_output=True, env=_clean_env() | {
                              "GIT_CEILING_DIRECTORIES": str(fw_copy.parent)}).returncode != 0, \
        "Tag darf im Framework-Checkout nicht lokal aufloesbar sein"
    url, commit, tag_obj = _remote(tmp_path)
    proj = _plugin_project(tmp_path)
    r = _setup(fw_copy, proj, "--cloud-gates", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    fv = json.loads((proj / ".claude" / "framework_version.json").read_text(encoding="utf-8"))
    assert fv["cloud_sha"] == commit, "Commit-SHA des Tags erwartet"
    assert fv["cloud_sha"] != tag_obj, "Tag-Objekt statt Commit gepinnt"


# ------------------------------------------------------------------ AC-21
def test_unresolvable_pin_writes_nothing(tmp_path, fw_copy):
    url, _, _ = _remote(tmp_path, tag="agent-os-openspec--v1.0.0")
    proj = _plugin_project(tmp_path, settings={**OWN_KEYS, "hooks": OWN_HOOKS})
    before = _snapshot(proj)
    r = _setup(fw_copy, proj, "--cloud-gates", url=url, tmp_path=tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert FW_VERSION in r.stdout + r.stderr, "Meldung soll den nicht aufloesbaren Tag nennen"
    assert _snapshot(proj) == before, "bei nicht aufloesbarem Pin darf nichts geschrieben werden"


# ------------------------------------------------------------------ AC-14
def test_update_in_plugin_mode_keeps_and_refreshes_pin(tmp_path, fw_copy):
    url, commit, _ = _remote(tmp_path)
    stale = {"PreToolUse": [{"matcher": "Edit|Write|MultiEdit", "hooks": [
        {"type": "command", "command": OLD_CONSUMER_PREFIX + "edit_gate.py", "timeout": 1}]}]}
    hooks = json.loads(json.dumps(OWN_HOOKS))
    hooks["PreToolUse"] += stale["PreToolUse"]
    proj = _plugin_project(tmp_path, settings={**OWN_KEYS, "hooks": hooks},
                           cloud_ref="agent-os-openspec--v0.0.1", cloud_sha="a" * 40)
    (proj / ".claude" / "cloud_bootstrap.py").write_text("# veralteter Baustein\n", encoding="utf-8")

    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    fv = json.loads((proj / ".claude" / "framework_version.json").read_text(encoding="utf-8"))
    assert fv.get("plugin_mode") is True
    assert fv.get("cloud_ref") == TAG, fv
    assert fv.get("cloud_sha") == commit, fv
    assert (proj / ".claude" / "cloud_bootstrap.py").read_bytes() == \
        (fw_copy / "core" / "cloud_bootstrap.py").read_bytes()
    settings = json.loads((proj / ".claude" / "settings.json").read_text(encoding="utf-8"))
    _assert_consumer_entries(settings["hooks"], _fw_hooks(fw_copy))
    for key, value in OWN_KEYS.items():
        assert settings[key] == value, key

    # Ohne Pin: --update schreibt weder Baustein noch Eintraege noch Pin.
    plain = _plugin_project(tmp_path, name="ohne-pin")
    r = _setup(fw_copy, plain, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (plain / ".claude" / "cloud_bootstrap.py").exists()
    assert not (plain / ".claude" / "settings.json").exists()
    fv = json.loads((plain / ".claude" / "framework_version.json").read_text(encoding="utf-8"))
    assert "cloud_ref" not in fv and "cloud_sha" not in fv
    assert fv.get("plugin_mode") is True


# ------------------------------------------------------------------ AC-15
GATE_WF = "wf-522"
PROTECTED = [".claude/cloud_bootstrap.py", ".claude/framework_version.json"]


def _gate_sandbox(tmp_path) -> Path:
    root = (tmp_path / "sb").resolve()
    (root / ".git").mkdir(parents=True)
    wf_dir = root / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / f"{GATE_WF}.json").write_text(json.dumps({
        "name": GATE_WF, "current_phase": "phase6_implement", "workflow_type": "feature",
        "red_test_done": True, "spec_approved": True, "affected_files": []}), encoding="utf-8")
    (root / ".claude" / "active_workflow").write_text(GATE_WF + "\n", encoding="utf-8")
    (root / ".claude" / "cloud_bootstrap.py").write_text("a = 1\n", encoding="utf-8")
    (root / ".claude" / "framework_version.json").write_text('{"a": 1}\n', encoding="utf-8")
    return root


def _gate(root, script, payload):
    env = _clean_env()
    env.update(CLAUDE_PROJECT_DIR=str(root), HOME=str(root.parent / "gate-home"))
    (root.parent / "gate-home" / ".claude").mkdir(parents=True, exist_ok=True)
    return subprocess.run([sys.executable, str(HOOKS_DIR / script)], input=json.dumps(payload),
                          cwd=str(root), env=env, capture_output=True, text=True, timeout=60)


def _token(root, present=True):
    path = root / ".claude" / "user_override_token.json"
    if not present:
        path.unlink(missing_ok=True)
        return
    entry = {"created": datetime.now().isoformat(), "granted_by": "user_prompt"}
    path.write_text(json.dumps({"version": 2, "tokens": {GATE_WF: entry, "__infra__": entry}}),
                    encoding="utf-8")


def _edit(root, tool, path, content="b = 2\n"):
    tin = {"file_path": path, "content": content} if tool == "Write" else {
        "file_path": path, "old_string": "a", "new_string": "b"}
    return _gate(root, "edit_gate.py", {"tool_name": tool, "tool_input": tin})


def _bash(root, cmd):
    return _gate(root, "bash_gate.py", {"tool_name": "Bash", "tool_input": {"command": cmd}})


def test_gates_protect_bootstrap_and_pin_files(tmp_path):
    root = _gate_sandbox(tmp_path)

    # edit_gate: ohne Override geblockt (Orchestrator-Domaene), mit Override frei
    for rel in PROTECTED:
        for tool in ("Write", "Edit"):
            for path in (rel, str(root / rel)):
                _token(root, present=False)
                r = _edit(root, tool, path)
                assert r.returncode == 2 and "Orchestrator" in r.stderr, \
                    f"edit_gate {tool} {path}: rc={r.returncode} {r.stderr.strip()[:200]!r}"
                _token(root)
                r = _edit(root, tool, path)
                assert r.returncode == 0, \
                    f"edit_gate {tool} {path} mit Override: rc={r.returncode} {r.stderr[:200]!r}"

    # #543 unveraendert: nur enabledPlugins in settings.json aendern bleibt ohne Override frei
    _token(root, present=False)
    settings = root / ".claude" / "settings.json"
    base = {"hooks": OWN_HOOKS, "permissions": OWN_KEYS["permissions"]}
    settings.write_text(json.dumps(base, indent=2), encoding="utf-8")
    r = _edit(root, "Write", str(settings),
              json.dumps({**base, "enabledPlugins": OWN_KEYS["enabledPlugins"]}, indent=2))
    assert r.returncode == 0, f"#543-Ausnahme gebrochen: {r.stderr[:200]!r}"

    # bash_gate: echte Schreibziele geblockt, Lesen und Retry frei, mit Override frei
    forms = ["echo x > {t}", "echo x >> {t}", "echo x | tee {t}", "sed -i s/a/b/ {t}",
             "cp /tmp/a {t}", "mv /tmp/a {t}"]
    for rel in PROTECTED:
        for form in forms:
            cmd = form.format(t=rel)
            _token(root, present=False)
            r = _bash(root, cmd)
            assert r.returncode == 2 and "override" in r.stderr.lower(), \
                f"bash_gate {cmd!r}: rc={r.returncode} {r.stderr.strip()[:200]!r}"
        _token(root)
        r = _bash(root, f"echo x > {rel}")
        assert r.returncode == 0, f"bash_gate mit Override {rel}: {r.stderr[:200]!r}"
        _token(root, present=False)
        r = _bash(root, f"cat {rel}")
        assert r.returncode == 0, f"Lesen {rel} geblockt: {r.stderr[:200]!r}"
    _token(root, present=False)
    r = _bash(root, RETRY)
    assert r.returncode == 0, f"Retry-Aufruf geblockt: {r.stderr[:200]!r}"


# ------------------------------------------------------------------ AC-16
def _walk(obj):
    yield obj
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def test_cloud_session_proof_artifact_present():
    assert ARTIFACT.exists(), f"Nachweis-Artefakt fehlt: {ARTIFACT.relative_to(REPO_ROOT)}"
    text = ARTIFACT.read_text(encoding="utf-8")
    data = json.loads(text)
    assert re.search(r"session_[0-9A-Za-z]{8,}", text), "Sitzungs-ID fehlt im Export"
    nodes = list(_walk(data))
    edits = [n for n in nodes if isinstance(n, dict) and n.get("type") == "tool_use"
             and n.get("name") == "Edit" and n.get("id")]
    assert edits, "kein Edit-Werkzeugaufruf im Export"
    edit_ids = {e["id"] for e in edits}
    results = [n for n in nodes if isinstance(n, dict) and n.get("type") == "tool_result"
               and n.get("tool_use_id") in edit_ids]
    assert results, "kein Ergebnis zum Edit-Aufruf im Export"
    assert any("BLOCKED" in json.dumps(r.get("content"), ensure_ascii=False) for r in results), \
        "Ergebnis zum Edit-Aufruf enthaelt keine edit_gate-Blockmeldung (BLOCKED)"


# ------------------------------------------------------------------ AC-17
def test_readme_and_changelog_document_cloud_gates():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(r"^(#+) .*Cloud sessions.*$", readme, re.M | re.I)
    assert m, "README: Abschnitt Cloud sessions fehlt"
    level = len(m.group(1))
    rest = readme[m.end():]
    end = re.search(rf"^#{{1,{level}}} ", rest, re.M)
    section = rest[:end.start()] if end else rest
    for needle in ("--cloud-gates", "cloud_bootstrap.py", "--retry", "github.com"):
        assert needle in section, f"README-Abschnitt nennt {needle!r} nicht"
    for line in section.splitlines():
        if "#522" in line:
            assert not re.search(r"follow-up|yet|offen|open|folge", line, re.I), \
                f"README verweist noch auf #522 als offen: {line.strip()[:120]!r}"

    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # Ab [Unreleased] abwaerts: nach einem Release steht der Eintrag im Versionsabschnitt.
    start = changelog.index("## [Unreleased]")
    assert any("#522" in line and ("--cloud-gates" in line or "cloud_bootstrap" in line)
               for line in changelog[start:].splitlines()), "CHANGELOG ohne Eintrag zu #522"


# ------------------------------------------------------------------ AC-18 bis AC-20
def _override_file(ctx, session) -> Path:
    return ctx.base / f"override-{session}.json"


def _set_override(ctx, session="sessA", prompt="override"):
    return ctx.run("phase_listener.py", payload=_ev("UserPromptSubmit", prompt=prompt,
                                                     session=session), url=ctx.bad_url)


def _backdate(path: Path, hours=2):
    """Ausnahmedatei um `hours` zurueckdatieren — Inhalt (Epoch/ISO) und mtime."""
    shift = timedelta(hours=hours)

    def fix(v):
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)) and v > 1_000_000_000:
            return v - shift.total_seconds()
        if isinstance(v, str):
            try:
                return (datetime.fromisoformat(v) - shift).isoformat()
            except ValueError:
                return v
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        if isinstance(v, list):
            return [fix(x) for x in v]
        return v

    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(fix(data)), encoding="utf-8")
    old = path.stat().st_mtime - shift.total_seconds()
    os.utime(path, (old, old))


def test_override_prompt_sets_session_exception_and_logs(tmp_path):
    ctx = _ctx(tmp_path)
    assert _events_log(ctx) == []
    r = _set_override(ctx, prompt="  Override ")
    assert r.returncode == 0, r.stderr
    assert "Ausnahme gesetzt" in r.stdout, r.stdout
    ofile = _override_file(ctx, "sessA")
    assert ofile.exists(), "Ausnahmedatei fehlt"
    odata = json.loads(ofile.read_text(encoding="utf-8"))
    assert any(isinstance(v, (int, float, str)) and not isinstance(v, bool)
               for v in odata.values()), "Zeitstempel fehlt"
    log = _events_log(ctx)
    assert len(log) == 1, log
    assert log[0]["hook"] == "cloud_bootstrap"
    assert log[0]["reason"] == "override: gates not loaded"
    assert log[0].get("session_id") == "sessA"
    assert log[0].get("ts"), "Zeitstempel fehlt in gate-events.jsonl"

    r = ctx.run("edit_gate.py", payload=_ev("PreToolUse", "Edit", session="sessB"), url=ctx.bad_url)
    assert r.returncode == 2
    assert PO_EXIT in r.stderr, r.stderr


def test_exception_allows_writes_only_for_same_session_within_one_hour(tmp_path):
    ctx = _ctx(tmp_path)
    assert _set_override(ctx).returncode == 0
    ofile = _override_file(ctx, "sessA")
    assert ofile.exists(), "Ausnahmedatei fehlt"
    before_paths = _paths(ctx.base, ctx.proj)
    before_override = ofile.read_bytes()
    before_log = len(_events_log(ctx))

    calls = [("edit_gate.py", _ev("PreToolUse", t, session="sessA"))
             for t in ("Edit", "Write", "MultiEdit", "WebFetch")]
    calls.append(("bash_gate.py", _bash_ev("echo x > f", session="sessA")))
    for script, payload in calls:
        r = ctx.run(script, payload=payload, url=ctx.bad_url)
        assert r.returncode == 0, f"{payload[:80]}: rc={r.returncode} {r.stderr!r}"
    assert _paths(ctx.base, ctx.proj) == before_paths, "Durchlass hat Dateien angelegt"
    assert ofile.read_bytes() == before_override
    assert len(_events_log(ctx)) == before_log, "Durchlass hat protokolliert"

    for script, payload in [("edit_gate.py", _ev("PreToolUse", "Edit", session="sessB")),
                            ("bash_gate.py", _bash_ev("echo x > f", session="sessB"))]:
        r = ctx.run(script, payload=payload, url=ctx.bad_url)
        assert r.returncode == 2 and PO_EXIT in r.stderr, f"fremde Sitzung: {r.stderr!r}"

    _backdate(ofile)
    r = ctx.run("edit_gate.py", payload=_ev("PreToolUse", "Edit", session="sessA"), url=ctx.bad_url)
    assert r.returncode == 2 and PO_EXIT in r.stderr, f"abgelaufene Ausnahme: {r.stderr!r}"


def test_override_never_set_when_cache_loadable_or_prompt_not_exact(tmp_path):
    ctx = _ctx(tmp_path)

    # (a) ladbarer Cache: phase_listener.py aus dem Cache mit durchgereichtem stdin
    payload = _ev("UserPromptSubmit", prompt="override", probe_out=str(ctx.out), probe_exit=0)
    r = ctx.run("phase_listener.py", payload=payload)
    assert r.returncode == 0, r.stderr
    recs = ctx.probe_records()
    assert len(recs) == 1 and recs[0]["stdin"] == payload, "phase_listener.py nicht aus dem Cache"
    assert Path(recs[0]["root"]).resolve() == ctx.cache.resolve()
    assert "Ausnahme gesetzt" not in r.stdout
    assert not list(ctx.base.glob("override-*")), "Ausnahme trotz ladbarem Cache"
    assert _events_log(ctx) == []
    # Schreibende Werkzeuge entscheidet das echte Gate (hier: probe.py aus dem Cache)
    r = ctx.run("probe.py", payload=_ev("PreToolUse", "Edit", probe_out=str(ctx.out), probe_exit=2))
    assert r.returncode == 2 and len(ctx.probe_records()) == 2

    # (b) Prompt nicht exakt `override`, (c) ungueltige session_id — bei fehlgeschlagenem Abruf
    shutil.rmtree(ctx.base)
    for prompt, session in [("bitte override setzen", "sessA"), ("override", "../x"),
                            ("override", "")]:
        r = _set_override(ctx, session=session, prompt=prompt)
        assert r.returncode == 0, r.stderr
        assert "Ausnahme gesetzt" not in r.stdout, (prompt, session)
        leaked = list(ctx.base.glob("override*")) + list(ctx.tmp.glob("override*")) \
            + list(ctx.base.parent.glob("x.json"))
        assert not leaked, f"Ausnahmedatei angelegt fuer {prompt!r}/{session!r}: {leaked}"
        assert _events_log(ctx) == [], (prompt, session)
    r = ctx.run("edit_gate.py", payload=_ev("PreToolUse", "Edit", session="../x"), url=ctx.bad_url)
    assert r.returncode == 2
