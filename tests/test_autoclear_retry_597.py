"""Auto-/clear übersteht zurückgewiesene Antworten (Issue #597, AC-2 bis AC-10).

Spec: docs/specs/fix-597-autoclear-klartext.md (AC-1 im Vorlagen-Test
tests/test_vorlagen_klartext_597.py, AC-11 ist der Regressionslauf, AC-12 das
lokale E2E-Skript).

Regel: Jedes saubere Antwortende darf die Übergabe starten, ein späteres ersetzt
ein früheres, als erledigt gilt sie erst, wenn wirklich getippt wurde. Der
Grenz-Vermerk `auto_clear_boundary` ist das einzige Einmal-Token; der Runner
nimmt ihn atomar (`_Runner._take_boundary`, flock auf
`<root>/.claude/herdr_auto_clear.lock`) unmittelbar vor dem Tippen von `/clear`.
Kein Verbrauch beim Spawn, kein 600-s-Once-Lock, keine Sonderbehandlung von
`stop_hook_active`; neu `klartext_gate.pruefe(payload)` als Vorprüfung.

Vertrag, den diese Tests festlegen (aus der Spec):
- Runner-CLI zusätzlich `--boundary-at <at-Text>` (identisch mit `boundary["at"]`),
  argparse-Attribut `boundary_at`.
- Log-Texte: `skip: Klartext-Prüfung weist die Antwort zurück`, Abbruch
  `Grenze bereits vergeben`, bei liegen gebliebenem/zurückgelegtem Vermerk
  `; Grenze bleibt` in der ABBRUCH-Zeile.

Stub-Herdr (bash) protokolliert jeden Aufruf NUL-getrennt in STUB_LOG:
- `pane send-text <pane> <text>`: merkt den Text; `STUB_TEXT_EXIT` (nur für
  `/clear`) simuliert einen Herdr-Fehler; ist `$4 == STUB_AFTER_TEXT_ON`, läuft
  danach `STUB_AFTER_TEXT_HOOK` (Signal zwischen Text und Enter).
- `pane send-keys <pane> enter` nach `/clear`: schreibt wie der echte
  SessionStart(clear)-Hook `<proj>/.claude/herdr_signals/<pane>.session.json`
  (`STUB_SESSION_SOURCE`, `none` = kein Marker).
- `agent wait`/`agent prompt`: abgelehnt wie Herdr bei `blocked`; alles andere Exit 0.
"""

import fcntl
import json
import os
import shlex
import stat
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
BRIDGE = HOOKS_DIR / "herdr_bridge.py"
FOOTER_GATE = HOOKS_DIR / "footer_gate.py"
KLARTEXT_GATE = HOOKS_DIR / "klartext_gate.py"

PANE = "pane-597"
WF = "fix-597-autoclear-klartext"
PHASE = "phase6_implement"
CMD = "/50-implement #597"
RESET = "/99-reset #597"
FOLLOW_TEXT = "/agent-os-openspec:50-implement #597"

ENTER = ["pane", "send-keys", PANE, "enter"]
CTRL_U = ["pane", "send-keys", PANE, "ctrl+u"]
CLEAR = [["pane", "send-text", PANE, "/clear"], ENTER]
FOLLOW = [["pane", "send-text", PANE, FOLLOW_TEXT], ENTER]

SKIP_KLARTEXT = "skip: Klartext-Prüfung weist die Antwort zurück"
TAKEN = "Grenze bereits vergeben"
KEPT = "Grenze bleibt"
WORKING = "Claude arbeitet weiter"
TYPED_ON = "Nutzer hat weitergeschrieben"

CLEAN = "Phase abgeschlossen. Alles liegt gesichert auf der Platte."
GIT = "Phase abgeschlossen, alles committet und gepusht."
NEGATIVE = "⚠️ **`/clear` jetzt NICHT** — Hintergrund-Agent laeuft noch."

STUB_SCRIPT = r"""#!/bin/bash
{ for a in "$@"; do printf '%s\0' "$a"; done; printf '\n'; } >> "$STUB_LOG"
PENDING="$STUB_LOG.pending"
if [ "$1 $2" = "agent wait" ]; then
  printf '%s\n' 'timed out waiting for agent status' >&2
  exit 1
fi
if [ "$1 $2" = "agent prompt" ]; then
  printf '%s\n' '{"error":{"code":"agent_blocked","message":"agent is blocked"}}' >&2
  exit 1
fi
if [ "$1 $2" = "pane send-text" ]; then
  if [ -n "$STUB_TEXT_EXIT" ] && [ "$4" = "/clear" ]; then exit "$STUB_TEXT_EXIT"; fi
  printf '%s' "$4" > "$PENDING"
  if [ -n "$STUB_AFTER_TEXT_HOOK" ] && [ "$4" = "$STUB_AFTER_TEXT_ON" ]; then
    bash "$STUB_AFTER_TEXT_HOOK"
  fi
  exit 0
fi
if [ "$1 $2" = "pane send-keys" ]; then
  typed=""
  if [ -f "$PENDING" ]; then typed="$(cat "$PENDING")"; rm -f "$PENDING"; fi
  if [ "$4" = "enter" ] && [ "$typed" = "/clear" ] && [ "${STUB_SESSION_SOURCE:-clear}" != none ]; then
    python3 - "$CLAUDE_PROJECT_DIR/.claude/herdr_signals/$3.session.json" \
      "${STUB_SESSION_SOURCE:-clear}" <<'EOF'
import json, os, sys, time
path, source = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path + ".tmp", "w") as fh:
    json.dump({"source": source, "at": time.time()}, fh)
os.replace(path + ".tmp", path)
EOF
  fi
  exit 0
fi
exit 0
"""

# Signal zwischen Text und Enter: Marker schreiben, optional neueren Vermerk setzen
WRITER = r"""import json, os, sys, time
marker, fields = sys.argv[1], json.loads(sys.argv[2])
if marker != "-":
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    fields["at"] = time.time()
    with open(marker + ".tmp", "w") as fh:
        json.dump(fields, fh)
    os.replace(marker + ".tmp", marker)
if len(sys.argv) > 4:
    state, newer = sys.argv[3], json.loads(sys.argv[4])
    with open(state) as fh:
        data = json.load(fh)
    data["auto_clear_boundary"] = newer
    with open(state + ".tmp", "w") as fh:
        json.dump(data, fh)
    os.replace(state + ".tmp", state)
"""


def _config(grace: float) -> str:
    return ("herdr:\n  auto_clear:\n    enabled: true\n"
            f"    grace_s: {grace}\n    idle_timeout_s: 5\n    announce: true\n"
            "session_banner:\n  behind_check: false\n")


def _boundary(*, phase: str = PHASE, command: str = CMD, age_s: float = 0) -> dict:
    at = (datetime.now() - timedelta(seconds=age_s)).isoformat()
    return {"phase": phase, "command": command, "at": at}


_DEFAULT = object()


class Case:
    """Isoliertes Projekt mit Stub-Herdr, Workflow-State und optionalem Vermerk."""

    def __init__(self, tmp_path: Path, label: str, *, grace: float = 0,
                 boundary=_DEFAULT, phase: str = PHASE, **env_extra):
        self.root = tmp_path / label
        self.root.mkdir(parents=True)
        self.proj = self.root / "proj"
        (self.proj / ".git").mkdir(parents=True)
        (self.proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
        (self.proj / "_home").mkdir()
        self.boundary = _boundary(phase=phase) if boundary is _DEFAULT else boundary
        # `--boundary-at` des Runners: `at` des Vermerks (sonst ein frischer Zeitstempel)
        self.at = (self.boundary["at"] if isinstance(self.boundary, dict)
                   else datetime.now().isoformat())
        data = {"name": WF, "workflow_type": "feature", "current_phase": phase,
                "phase_transitions": [], "phase_log": []}
        if self.boundary is not None:
            data["auto_clear_boundary"] = self.boundary
        self.wf_file.write_text(json.dumps(data))
        (self.proj / ".claude" / "active_workflow").write_text(WF)
        (self.proj / "config.yaml").write_text(_config(grace))
        self.log = self.root / "stub.log"
        stub = self.root / "herdr-stub"
        stub.write_text(STUB_SCRIPT)
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_", "CLAUDE_"))}
        env.update({"CLAUDE_PROJECT_DIR": str(self.proj), "HOME": str(self.proj / "_home"),
                    "OPENSPEC_ACTIVE_WORKFLOW": WF, "HERDR_ENV": "1",
                    "HERDR_PANE_ID": PANE, "HERDR_BIN_PATH": str(stub),
                    "STUB_LOG": str(self.log)})
        env.update({k: str(v) for k, v in env_extra.items()})
        self.env = env

    # --- Zustand ---
    @property
    def wf_file(self) -> Path:
        return self.proj / ".claude" / "workflows" / f"{WF}.json"

    def state(self) -> dict:
        return json.loads(self.wf_file.read_text())

    def current_boundary(self):
        return self.state().get("auto_clear_boundary")

    def set_boundary(self, boundary) -> None:
        data = self.state()
        if boundary is None:
            data.pop("auto_clear_boundary", None)
        else:
            data["auto_clear_boundary"] = boundary
        self.wf_file.write_text(json.dumps(data))

    @property
    def lock_file(self) -> Path:
        return self.proj / ".claude" / "herdr_auto_clear.lock"

    @property
    def once_lock_file(self) -> Path:
        return self.proj / ".claude" / "herdr_auto_clear_state.json"

    def runner_log(self) -> str:
        path = self.proj / ".claude" / "herdr_auto_clear.log"
        return path.read_text() if path.exists() else ""

    def calls(self) -> list:
        if not self.log.exists():
            return []
        out = []
        for line in self.log.read_bytes().decode("utf-8", "replace").split("\n"):
            if line:
                out.append(line.split("\0")[:-1] if line.endswith("\0") else line.split("\0"))
        return out

    def typing(self) -> list:
        return [c for c in self.calls() if c[:2] in (["pane", "send-text"],
                                                     ["pane", "send-keys"])]

    def notifications(self) -> list:
        return [c for c in self.calls() if c[:2] == ["notification", "show"]]

    def marker(self, signal: str, pane: str = PANE) -> Path:
        return self.proj / ".claude" / "herdr_signals" / f"{pane}.{signal}.json"

    def write_marker(self, signal: str, **fields) -> None:
        path = self.marker(signal)
        path.parent.mkdir(parents=True, exist_ok=True)
        fields.setdefault("at", time.time())
        path.write_text(json.dumps(fields))

    # --- Prozesse ---
    def runner_argv(self, *, since=_DEFAULT, grace: float = 0, settle: float = 0,
                    idle_timeout: float = 5, announce: str = "0", boundary_at=_DEFAULT,
                    command: str = CMD, phase: str = PHASE) -> list:
        if boundary_at is _DEFAULT:
            boundary_at = self.at
        argv = [sys.executable, str(BRIDGE), "auto-clear", "--pane", PANE,
                "--workflow", WF, "--phase", phase, "--command", command,
                "--grace", str(grace), "--settle", str(settle),
                "--idle-timeout", str(idle_timeout), "--announce", announce,
                "--boundary-at", boundary_at]
        since = time.time() if since is _DEFAULT else since
        if since is not None:
            argv += ["--since", repr(float(since))]
        return argv

    def run_runner(self, timeout: float = 60, **kw) -> subprocess.CompletedProcess:
        return subprocess.run(self.runner_argv(**kw), capture_output=True, text=True,
                              env=self.env, cwd=str(self.proj), timeout=timeout)

    def start_runner(self, **kw) -> subprocess.Popen:
        return subprocess.Popen(self.runner_argv(**kw), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=self.env,
                                cwd=str(self.proj))

    def run_footer(self, message: str, **payload_extra) -> subprocess.CompletedProcess:
        payload = {"session_id": "sess-597", "hook_event_name": "Stop",
                   "cwd": str(self.proj), "last_assistant_message": message,
                   "prompt_id": "11111111-2222-3333-4444-555555555555"}
        payload.update(payload_extra)
        return subprocess.run([sys.executable, str(FOOTER_GATE)], input=json.dumps(payload),
                              capture_output=True, text=True, env=self.env,
                              cwd=str(self.proj), timeout=30)

    def py(self, code: str, *args, timeout: float = 30) -> subprocess.CompletedProcess:
        full = f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r})\n{code}"
        return subprocess.run([sys.executable, "-c", full, *args], capture_output=True,
                              text=True, env=self.env, cwd=str(self.proj), timeout=timeout)

    def after_text_hook(self, on_text: str, signal: str, newer_boundary=None,
                        **fields) -> None:
        """Nach `pane send-text <on_text>`: Signal `signal` schreiben (zwischen Text und Enter)."""
        writer = self.root / "writer.py"
        writer.write_text(WRITER)
        args = [sys.executable, str(writer), str(self.marker(signal)), json.dumps(fields)]
        if newer_boundary is not None:
            args += [str(self.wf_file), json.dumps(newer_boundary)]
        hook = self.root / "after_text.sh"
        hook.write_text(" ".join(shlex.quote(a) for a in args) + "\n")
        self.env["STUB_AFTER_TEXT_ON"] = on_text
        self.env["STUB_AFTER_TEXT_HOOK"] = str(hook)

    def phase_changer(self) -> Path:
        script = self.root / "change.sh"
        script.write_text(
            f"{shlex.quote(sys.executable)} - <<'EOF'\n"
            "import json\n"
            f"p = {str(self.wf_file)!r}\n"
            "d = json.load(open(p))\n"
            "d['current_phase'] = 'phase7_validate'\n"
            "json.dump(d, open(p, 'w'))\n"
            "EOF\n")
        return script


def _message(text: str = CLEAN, *blocks: str, command: str = CMD) -> str:
    return "\n\n".join([text, *blocks, f"❗ Du: `{command}` — der naechste Pflicht-Schritt",
                        "⚙ /50-implement · agent-os-openspec 4.12.0"])


def _wait_for(predicate, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _ends(case: Case) -> int:
    """Anzahl beendeter Runner (OK- oder ABBRUCH-Zeilen, ohne `skip:`)."""
    return sum(1 for ln in case.runner_log().splitlines()
               if ": OK" in ln or "ABBRUCH" in ln)


def _assert_no_calls(case: Case) -> None:
    time.sleep(0.8)
    assert case.calls() == [], f"Stub unerwartet aufgerufen: {case.calls()}"


def _finish(proc: subprocess.Popen, timeout: float = 60) -> None:
    _, err = proc.communicate(timeout=timeout)
    assert proc.returncode == 0, err
    assert "Traceback" not in (err or ""), err


# Skript: maybe_auto_clear mit abgefangenem Popen (Spawn-argv sichtbar, kein Runner)
SPAWN_PROBE = r"""
import json
import subprocess
calls = []
class _Popen:
    def __init__(self, argv, **kw):
        calls.append([str(a) for a in argv])
subprocess.Popen = _Popen
mode = sys.argv[1]
if mode == "pruefe-wirft":
    import klartext_gate
    def _boom(*a, **k):
        raise RuntimeError("kaputt")
    klartext_gate.pruefe = _boom
elif mode == "pruefe-fehlt":
    sys.modules["klartext_gate"] = None
import herdr_bridge
wf, message, n = sys.argv[2], sys.argv[3], int(sys.argv[4])
results = []
for _ in range(n):
    with open(wf) as fh:
        data = json.load(fh)
    data.setdefault("name", %(wf)r)
    payload = {"hook_event_name": "Stop", "last_assistant_message": message}
    results.append(herdr_bridge.maybe_auto_clear(payload, message, data))
print("RESULT=" + json.dumps({"results": results, "calls": calls}))
""" % {"wf": WF}


def _probe(case: Case, mode: str, message: str, n: int = 1) -> dict:
    res = case.py(SPAWN_PROBE, mode, str(case.wf_file), message, str(n))
    lines = [ln for ln in res.stdout.splitlines() if ln.startswith("RESULT=")]
    assert res.returncode == 0 and lines, f"Probe fehlgeschlagen: {res.stdout!r} {res.stderr!r}"
    return json.loads(lines[-1][len("RESULT="):])


# Skript: _Runner._take_boundary direkt (ein Prozess je Aufruf)
TAKE_PROBE = r"""
import argparse, json, time
cfg = json.loads(sys.argv[1])
if cfg.get("ohne_fcntl"):
    sys.modules["fcntl"] = None
import herdr_bridge
args = argparse.Namespace(pane=%(pane)r, workflow=%(wf)r, phase=cfg["phase"],
                          command=cfg["command"], grace=0.0, settle=0.0,
                          idle_timeout=5.0, announce="0", since=None,
                          boundary_at=cfg["boundary_at"])
runner = herdr_bridge._Runner(args)
start = cfg.get("start", 0)
while time.time() < start:
    time.sleep(0.001)
result = runner._take_boundary()
released = None
lock = cfg.get("lock")
if lock and not cfg.get("ohne_fcntl"):
    import fcntl, os
    if os.path.isfile(lock):
        with open(lock, "a+") as fh:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                released = True
            except OSError:
                released = False
print("RESULT=" + json.dumps({"taken": result, "released": released}))
""" % {"pane": PANE, "wf": WF}


def _take_cfg(case: Case, **over) -> dict:
    cfg = {"phase": PHASE, "command": CMD, "boundary_at": case.at,
           "lock": str(case.lock_file)}
    cfg.update(over)
    return cfg


def _take(case: Case, **over) -> dict:
    res = case.py(TAKE_PROBE, json.dumps(_take_cfg(case, **over)))
    lines = [ln for ln in res.stdout.splitlines() if ln.startswith("RESULT=")]
    assert res.returncode == 0 and lines, \
        f"_take_boundary-Aufruf fehlgeschlagen: {res.stdout!r} {res.stderr!r}"
    return json.loads(lines[-1][len("RESULT="):])


def _start_take(case: Case, **over) -> subprocess.Popen:
    full = (f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r})\n{TAKE_PROBE}")
    return subprocess.Popen([sys.executable, "-c", full, json.dumps(_take_cfg(case, **over))],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env=case.env, cwd=str(case.proj))


def _result_of(proc: subprocess.Popen, timeout: float = 30) -> dict:
    out, err = proc.communicate(timeout=timeout)
    lines = [ln for ln in out.splitlines() if ln.startswith("RESULT=")]
    assert proc.returncode == 0 and lines, f"_take_boundary-Prozess: {out!r} {err!r}"
    return json.loads(lines[-1][len("RESULT="):])


# --- AC-2 -------------------------------------------------------------------

def _transcript(tmp_path: Path, name: str, frage, antwort: str) -> str:
    path = tmp_path / f"{name}.jsonl"
    rows = []
    if frage is not None:
        rows.append({"type": "user", "message": {"role": "user", "content": frage}})
    rows.append({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": antwort}]}})
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8")
    return str(path)


def _run_main(tmp_path: Path, payload, env_extra: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("OPENSPEC_KLARTEXT", "CLAUDE_TOOL_NAME", "CLAUDE_TOOL_INPUT")}
    env.update(env_extra)
    return subprocess.run([sys.executable, str(KLARTEXT_GATE)], input=json.dumps(payload),
                          capture_output=True, text=True, cwd=str(tmp_path), env=env,
                          timeout=20)


def test_klartext_pruefe_matches_main_behaviour(tmp_path, monkeypatch):
    """AC-2: `klartext_gate.pruefe(payload)` liefert Treffer bzw. `[]`, wirft nie;
    `main` entscheidet identisch (Exit 2 mit derselben Meldung nur bei Treffern)."""
    sys.path.insert(0, str(HOOKS_DIR))
    try:
        import klartext_gate  # noqa: PLC0415
    finally:
        sys.path.remove(str(HOOKS_DIR))
    pruefe = getattr(klartext_gate, "pruefe", None)
    assert callable(pruefe), "klartext_gate.pruefe(payload) fehlt"

    anderswo = tmp_path / "anderswo"
    anderswo.mkdir()
    git_text = "Ich habe den Branch angelegt, committet und einen PR gemergt."
    git_hits = klartext_gate.treffer(git_text)
    assert git_hits, git_hits
    cases = [
        # (label, payload, env, erwartete Treffer)
        ("treffer", {"last_assistant_message": git_text, "cwd": str(anderswo)}, {}, git_hits),
        ("transkript", {"transcript_path": _transcript(tmp_path, "t1", "weiter",
                                                       "Der Merge ist durch.")},
         {}, ["Merge"]),
        ("transkript-fehlt", {"transcript_path": str(tmp_path / "fehlt.jsonl"),
                              "last_assistant_message": "Der Commit ist durch."},
         {}, ["Commit"]),
        ("transkript-ordner", {"transcript_path": str(anderswo),
                               "last_assistant_message": "Der Commit ist durch."},
         {}, ["Commit"]),
        ("aus-0", {"last_assistant_message": git_text}, {"OPENSPEC_KLARTEXT": "0"}, []),
        ("aus-off", {"last_assistant_message": git_text}, {"OPENSPEC_KLARTEXT": "off"}, []),
        ("aus-disabled", {"last_assistant_message": git_text},
         {"OPENSPEC_KLARTEXT": "Disabled"}, []),
        ("stop_hook_active", {"last_assistant_message": git_text, "stop_hook_active": True},
         {}, []),
        ("frage-mit-git", {"transcript_path": _transcript(
            tmp_path, "t2", "Ist der PR schon gemergt?", "Ja, der PR ist gemergt."),
            "last_assistant_message": "Ja, der PR ist gemergt."}, {}, []),
        ("ohne-text", {"cwd": str(anderswo)}, {}, []),
        ("leerer-text", {"last_assistant_message": ""}, {}, []),
        ("text-kein-str", {"last_assistant_message": 42, "transcript_path": 17}, {}, []),
        ("sauber", {"last_assistant_message": CLEAN}, {}, []),
        ("code-only", {"last_assistant_message": "Erledigt: `git commit` lief."}, {}, []),
    ]
    befunde = []
    for label, payload, env_extra, expected in cases:
        monkeypatch.delenv("OPENSPEC_KLARTEXT", raising=False)
        for key, val in env_extra.items():
            monkeypatch.setenv(key, val)
        cwd_before = os.getcwd()
        try:
            got = pruefe(payload)
        except Exception as exc:  # noqa: BLE001
            befunde.append(f"{label}: pruefe wirft {type(exc).__name__}: {exc}")
            continue
        if os.getcwd() != cwd_before:
            befunde.append(f"{label}: pruefe wechselte das Arbeitsverzeichnis")
            os.chdir(cwd_before)
        if got != expected:
            befunde.append(f"{label}: pruefe -> {got!r}, erwartet {expected!r}")
        res = _run_main(tmp_path, payload, env_extra)
        if bool(expected) != (res.returncode == 2) or res.returncode not in (0, 2):
            befunde.append(f"{label}: main Exit {res.returncode}, pruefe {got!r}")
        if expected:
            if "KLARTEXT-PRÜFUNG" not in res.stderr or \
                    "(" + ", ".join(expected) + ")" not in res.stderr:
                befunde.append(f"{label}: Meldung von main weicht ab: {res.stderr!r}")
        elif res.stderr.strip():
            befunde.append(f"{label}: main schreibt ohne Treffer auf stderr: {res.stderr!r}")
    monkeypatch.delenv("OPENSPEC_KLARTEXT", raising=False)

    # Payload kein dict: pruefe -> [], main Exit 0
    for payload in ("Commit", None, ["Commit"], 42):
        try:
            got = pruefe(payload)
        except Exception as exc:  # noqa: BLE001
            befunde.append(f"kein-dict {payload!r}: pruefe wirft {type(exc).__name__}")
            continue
        if got != []:
            befunde.append(f"kein-dict {payload!r}: pruefe -> {got!r}")
        res = _run_main(tmp_path, payload, {})
        if res.returncode != 0:
            befunde.append(f"kein-dict {payload!r}: main Exit {res.returncode}")
    assert not befunde, "\n".join(befunde)


# --- AC-3 -------------------------------------------------------------------

def test_stop_hook_active_stop_spawns_runner(tmp_path):
    """AC-3: Folge-Stop (`stop_hook_active: true`) mit passender Grenze und sauberer
    Antwort startet einen Runner; kein `skip: stop_hook_active`, der Vermerk bleibt
    bis zum Tippen liegen und ist erst danach verbraucht."""
    case = Case(tmp_path, "sha", grace=2)
    res = case.run_footer(_message(), stop_hook_active=True)
    assert res.returncode == 0, res.stderr
    assert _wait_for(lambda: case.notifications(), 3), \
        f"Kein Runner beim stop_hook_active-Stop; Log: {case.runner_log()!r}"
    assert "skip: stop_hook_active" not in case.runner_log(), case.runner_log()
    assert case.current_boundary() == case.boundary, \
        f"Vermerk schon vor dem Tippen verbraucht: {case.state()}"
    assert _wait_for(lambda: _ends(case) >= 1, 30), f"Runner endete nicht: {case.runner_log()!r}"
    assert ": OK" in case.runner_log(), case.runner_log()
    assert case.typing() == CLEAR + FOLLOW, case.calls()
    assert case.current_boundary() is None, f"Vermerk nach dem Tippen noch da: {case.state()}"


# --- AC-4 -------------------------------------------------------------------

def test_klartext_pre_check_skips_and_keeps_boundary(tmp_path):
    """AC-4: Würde `klartext_gate` die Antwort zurückweisen, startet `maybe_auto_clear`
    keinen Runner (`skip: Klartext-Prüfung weist die Antwort zurück`), der Vermerk
    bleibt unverändert; Negativ-Marker und veralteter Vermerk wie bisher (verbraucht);
    Fehler der Vorprüfung gelten als "keine Treffer" (fail-open)."""
    # (a) Git-Wort in der Antwort: kein Spawn, Vermerk unverändert
    case = Case(tmp_path, "git")
    res = case.run_footer(_message(GIT))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(case)
    assert SKIP_KLARTEXT in case.runner_log(), case.runner_log()
    assert case.current_boundary() == case.boundary, case.state()

    # (b) Klartext-Prüfung abgeschaltet: dieselbe Antwort startet den Runner
    case = Case(tmp_path, "git-aus", grace=5, OPENSPEC_KLARTEXT="0")
    res = case.run_footer(_message(GIT))
    assert res.returncode == 0, res.stderr
    assert _wait_for(lambda: case.notifications(), 3), \
        f"OPENSPEC_KLARTEXT=0: kein Runner; Log: {case.runner_log()!r}"
    assert SKIP_KLARTEXT not in case.runner_log(), case.runner_log()

    # (c) Negativ-Marker bzw. veralteter Vermerk: wie bisher verbraucht + Skip-Grund
    case = Case(tmp_path, "negativ")
    res = case.run_footer(_message(CLEAN, NEGATIVE))
    assert res.returncode == 0, res.stderr
    _assert_no_calls(case)
    assert "skip: Negativmarker" in case.runner_log(), case.runner_log()
    assert case.current_boundary() is None, case.state()
    case = Case(tmp_path, "veraltet", boundary=_boundary(age_s=20 * 60))
    res = case.run_footer(_message())
    assert res.returncode == 0, res.stderr
    _assert_no_calls(case)
    assert "skip: Grenze veraltet" in case.runner_log(), case.runner_log()
    assert case.current_boundary() is None, case.state()

    # (d) Vorprüfung wirft bzw. ist nicht importierbar: fail-open, Spawn wie ohne Treffer
    for mode in ("pruefe-wirft", "pruefe-fehlt"):
        case = Case(tmp_path, mode)
        out = _probe(case, mode, _message(GIT))
        assert out["results"] == [True], (mode, out, case.runner_log())
        assert len(out["calls"]) == 1, (mode, out)


# --- AC-5 -------------------------------------------------------------------

def test_spawn_keeps_boundary_and_has_no_once_lock(tmp_path):
    """AC-5: Spawn verbraucht den Vermerk nicht, es gibt keinen 600-s-Once-Lock
    (keine `herdr_auto_clear_state.json`, zwei Stops in Folge spawnen beide) und der
    Spawn übergibt `--boundary-at` mit dem `at` des Vermerks."""
    # (a) maybe_auto_clear direkt, Popen abgefangen: zwei Stops, zwei Spawns
    case = Case(tmp_path, "probe")
    out = _probe(case, "normal", _message(), n=2)
    assert out["results"] == [True, True], \
        f"Zweiter Stop nicht gespawnt (Once-Lock/Verbrauch?): {out}; Log: {case.runner_log()!r}"
    assert len(out["calls"]) == 2, out
    for argv in out["calls"]:
        assert "--boundary-at" in argv, argv
        assert argv[argv.index("--boundary-at") + 1] == case.boundary["at"], argv
    assert case.current_boundary() == case.boundary, \
        f"Vermerk beim Spawn verbraucht: {case.state()}"
    assert not case.once_lock_file.exists(), case.once_lock_file.read_text()

    # (b) echter Stop-Hook zweimal: zwei Runner, Vermerk liegt bis zum Tippen
    case = Case(tmp_path, "hook", grace=1)
    for _ in range(2):
        res = case.run_footer(_message())
        assert res.returncode == 0, res.stderr
    assert _wait_for(lambda: len(case.notifications()) >= 2, 3), \
        f"Zwei Stops, aber {len(case.notifications())} Runner; Log: {case.runner_log()!r}"
    assert case.current_boundary() == case.boundary, case.state()
    assert not case.once_lock_file.exists(), "Once-Lock-Datei angelegt"
    assert _wait_for(lambda: _ends(case) >= 2, 30), case.runner_log()


# --- AC-6 -------------------------------------------------------------------

def test_two_runners_only_one_takes_token(tmp_path):
    """AC-6: Zwei (bzw. viele) Runner für dieselbe Grenze: genau einer bekommt den
    Vermerk (atomar unter flock), der andere bricht mit "Grenze bereits vergeben" ab;
    getippt werden `/clear` und der Folgebefehl insgesamt genau einmal."""
    # (a) acht Prozesse rufen gleichzeitig _take_boundary
    case = Case(tmp_path, "race")
    before = case.state()
    start = time.time() + 2.0
    procs = [_start_take(case, start=start) for _ in range(8)]
    results = [_result_of(p)["taken"] for p in procs]
    assert results.count(True) == 1, f"Token mehrfach/nie vergeben: {results}"
    after = case.state()
    assert "auto_clear_boundary" not in after, after
    before.pop("auto_clear_boundary")
    assert after == before, (before, after)

    # (b) gehaltene Sperre: der Runner liest den State erst nach der Freigabe
    case = Case(tmp_path, "held")
    case.lock_file.parent.mkdir(parents=True, exist_ok=True)
    with open(case.lock_file, "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        proc = _start_take(case)
        time.sleep(1.5)
        # anderer Runner hat den Vermerk inzwischen genommen
        case.set_boundary(None)
        data = case.state()
        data["andere_aenderung"] = 1
        case.wf_file.write_text(json.dumps(data))
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    out = _result_of(proc)
    assert out["taken"] is False, f"_take_boundary ignorierte die Sperre: {out}"
    assert case.state() == data, f"State ueberschrieben: {case.state()}"

    # (c) zwei vollständige Runner gleichzeitig: genau ein /clear, ein Folgebefehl
    case = Case(tmp_path, "two")
    since = time.time()
    procs = [case.start_runner(since=since) for _ in range(2)]
    for p in procs:
        _finish(p)
    assert case.typing() == CLEAR + FOLLOW, \
        f"Log: {case.runner_log()!r} Aufrufe: {case.calls()}"
    log = case.runner_log()
    assert log.count(": OK") == 1, log
    assert TAKEN in log, log
    assert case.current_boundary() is None, case.state()


# --- AC-7 -------------------------------------------------------------------

def test_take_boundary_requires_exact_match_and_fails_safe(tmp_path):
    """AC-7: `_take_boundary` liefert nur bei exakt passendem Vermerk (phase, command,
    at) True; fehlt er, passt er nicht, ist der State unlesbar, schlägt die Sperre
    fehl oder fehlt `fcntl`: False, State unverändert, der Runner tippt nichts."""
    # Positiv-Kontrolle: passt -> True, nur das Feld entfernt, Sperre freigegeben
    case = Case(tmp_path, "passt")
    before = case.state()
    out = _take(case)
    assert out["taken"] is True, out
    before.pop("auto_clear_boundary")
    assert case.state() == before, case.state()
    assert case.lock_file.is_file(), "Sperrdatei .claude/herdr_auto_clear.lock fehlt"
    assert out["released"] is True, "Sperre nach _take_boundary nicht freigegeben"

    other_at = (datetime.now() + timedelta(minutes=1)).isoformat()
    negatives = {
        "fehlt": dict(boundary=None),
        "phase": dict(boundary=_boundary(phase="phase5_tdd_red")),
        "command": dict(boundary=_boundary(command="/40-tdd-red #597")),
        "at": dict(take={"boundary_at": other_at}),
        "kein-dict": dict(boundary="phase6_implement|/50-implement #597"),
        "state-kaputt": dict(raw="{kaputt"),
        "state-fehlt": dict(remove=True),
        "sperre-kaputt": dict(lock_dir=True),
        "ohne-fcntl": dict(take={"ohne_fcntl": True}),
    }
    befunde = []
    for label, spec in negatives.items():
        case = Case(tmp_path, label, boundary=spec.get("boundary", _DEFAULT))
        if "raw" in spec:
            case.wf_file.write_text(spec["raw"])
        if spec.get("remove"):
            case.wf_file.unlink()
        if spec.get("lock_dir"):
            case.lock_file.mkdir(parents=True)
        raw_before = case.wf_file.read_bytes() if case.wf_file.exists() else None
        res = case.py(TAKE_PROBE, json.dumps(_take_cfg(case, **spec.get("take", {}))))
        lines = [ln for ln in res.stdout.splitlines() if ln.startswith("RESULT=")]
        if res.returncode != 0 or not lines:
            befunde.append(f"{label}: Aufruf scheiterte: {res.stdout!r} {res.stderr[-400:]!r}")
            continue
        taken = json.loads(lines[-1][len("RESULT="):])["taken"]
        if taken is not False:
            befunde.append(f"{label}: _take_boundary -> {taken!r}, erwartet False")
        raw_after = case.wf_file.read_bytes() if case.wf_file.exists() else None
        if raw_after != raw_before:
            befunde.append(f"{label}: State veraendert: {raw_before!r} -> {raw_after!r}")
    assert not befunde, "\n".join(befunde)

    # Runner mit fremdem --boundary-at: nichts getippt, Abbruch, Vermerk bleibt
    case = Case(tmp_path, "runner-fremd")
    res = case.run_runner(boundary_at=other_at)
    assert res.returncode == 0, res.stderr
    assert case.typing() == [], case.calls()
    assert TAKEN in case.runner_log(), case.runner_log()
    assert case.current_boundary() == case.boundary, case.state()


# --- AC-8 -------------------------------------------------------------------

def test_newest_clean_stop_wins(tmp_path):
    """AC-8: Stop #1 startet Runner 1, ein fremder Hook blockt, Stop #2
    (`stop_hook_active`) startet Runner 2. Runner 1 sieht Stop #2, bricht ab und
    verwirft den Vermerk nicht ("Claude arbeitet weiter", "Grenze bleibt"); Runner 2
    nimmt ihn und tippt genau einmal `/clear` und den Folgebefehl; Log: erst ABBRUCH,
    dann OK."""
    case = Case(tmp_path, "newest", grace=2)
    res = case.run_footer(_message())
    assert res.returncode == 0, res.stderr
    assert _wait_for(lambda: case.notifications(), 3), \
        f"Stop #1 startete keinen Runner; Log: {case.runner_log()!r}"
    time.sleep(1.0)  # klartext_gate o. Ae. blockt Stop #1, Claude schreibt neu
    res = case.run_footer(_message(), stop_hook_active=True)
    assert res.returncode == 0, res.stderr
    assert _wait_for(lambda: "ABBRUCH" in case.runner_log(), 10), \
        f"Runner 1 brach nicht ab; Log: {case.runner_log()!r}"
    assert case.current_boundary() == case.boundary, \
        f"Runner 1 (bzw. Stop #2) verwarf den Vermerk: {case.state()}; Log: {case.runner_log()!r}"
    assert _wait_for(lambda: ": OK" in case.runner_log(), 30), \
        f"Runner 2 tippte nicht; Log: {case.runner_log()!r}; Aufrufe: {case.calls()}"
    assert len(case.notifications()) == 2, case.notifications()
    assert case.typing() == CLEAR + FOLLOW, case.calls()
    lines = case.runner_log().splitlines()
    abort = [i for i, ln in enumerate(lines) if "ABBRUCH" in ln]
    ok = [i for i, ln in enumerate(lines) if ": OK" in ln]
    assert abort and ok and abort[0] < ok[0], lines
    assert WORKING in lines[abort[0]] and KEPT in lines[abort[0]], lines[abort[0]]
    assert case.current_boundary() is None, case.state()


# --- AC-9 -------------------------------------------------------------------

def test_restore_boundary_on_continuation_between_text_and_enter(tmp_path):
    """AC-9: Runner hat den Vermerk genommen, zwischen `send-text /clear` und Enter
    kommt ein `activity`- bzw. `stop`-Signal: Zeile per `ctrl+u` gelöscht, Vermerk
    zurückgelegt — aber nur, wenn kein neuerer Vermerk im State steht."""
    # (a) activity zwischen Text und Enter: zurückgelegt
    case = Case(tmp_path, "activity")
    case.after_text_hook("/clear", "activity", kind="pretooluse")
    res = case.run_runner(since=time.time() - 0.5)
    assert res.returncode == 0, res.stderr
    assert case.typing() == [CLEAR[0], CTRL_U], \
        f"(a) Log: {case.runner_log()!r} Aufrufe: {case.calls()}"
    assert WORKING in case.runner_log() and KEPT in case.runner_log(), case.runner_log()
    assert case.current_boundary() == case.boundary, f"(a) nicht zurückgelegt: {case.state()}"

    # (b) stop zwischen Text und Enter, inzwischen neuerer Vermerk: nicht überschrieben
    case = Case(tmp_path, "stop-newer")
    newer = {"phase": PHASE, "command": CMD,
             "at": (datetime.now() + timedelta(seconds=30)).isoformat()}
    case.after_text_hook("/clear", "stop", newer_boundary=newer)
    res = case.run_runner(since=time.time() - 0.5)
    assert res.returncode == 0, res.stderr
    assert case.typing() == [CLEAR[0], CTRL_U], \
        f"(b) Log: {case.runner_log()!r} Aufrufe: {case.calls()}"
    assert WORKING in case.runner_log(), case.runner_log()
    assert case.current_boundary() == newer, f"(b) neuerer Vermerk überschrieben: {case.state()}"


# --- AC-10 ------------------------------------------------------------------

def test_discard_boundary_on_user_input_and_other_aborts(tmp_path):
    """AC-10: Abbruch vor dem Abschicken von `/clear` durch Nutzereingabe,
    Sitzungsende/Neustart, Phasenwechsel, Herdr-Fehler oder `/99-reset`: Vermerk
    verworfen (nur der eigene, ein neuerer bleibt), kein Neuversuch; nach
    abgeschicktem `/clear` bleibt er verbraucht; `ABBRUCH` im Log.

    Die Gesamt-Deadline (Budget >= 95 s) ist hier nicht in vertretbarer Zeit
    auslösbar; sie läuft über denselben Abbruchpfad wie die übrigen Gründe."""
    befunde = []

    def check(case: Case, label: str, *, typing, boundary=None, reason=None):
        if case.typing() != typing:
            befunde.append(f"{label}: getippt {case.typing()}, erwartet {typing}")
        if case.current_boundary() != boundary:
            befunde.append(f"{label}: Vermerk {case.current_boundary()!r}, erwartet {boundary!r}")
        log = case.runner_log()
        if "ABBRUCH" not in log or (reason and reason not in log):
            befunde.append(f"{label}: Log ohne ABBRUCH/{reason!r}: {log!r}")

    # (a) Nutzer schreibt in der Grace-Zeit
    case = Case(tmp_path, "input", grace=1)
    proc = case.start_runner(grace=1.5)
    time.sleep(0.5)
    case.write_marker("input")
    _finish(proc)
    check(case, "input", typing=[], reason=TYPED_ON)
    # kein Neuversuch: der nächste saubere Stop findet keinen Vermerk mehr
    n_calls = len(case.calls())
    res = case.run_footer(_message())
    assert res.returncode == 0, res.stderr
    time.sleep(0.8)
    if len(case.calls()) != n_calls:
        befunde.append(f"input: Neuversuch nach Abbruch: {case.calls()}")
    if not case.runner_log().rstrip().endswith("skip: keine Grenze vermerkt"):
        befunde.append(f"input: kein Skip 'keine Grenze vermerkt': {case.runner_log()!r}")

    # (b) Nutzereingabe, inzwischen neuerer Vermerk: der neuere bleibt
    case = Case(tmp_path, "input-newer")
    newer = {"phase": PHASE, "command": CMD,
             "at": (datetime.now() + timedelta(seconds=30)).isoformat()}
    proc = case.start_runner(grace=1.5)
    time.sleep(0.5)
    case.set_boundary(newer)
    case.write_marker("input")
    _finish(proc)
    check(case, "input-newer", typing=[], boundary=newer, reason=TYPED_ON)

    # (c) Sitzung beendet bzw. neu gestartet in der Grace-Zeit
    for label, signal, fields in (("session-end", "activity",
                                   {"kind": "session_end", "reason": "prompt_input_exit"}),
                                  ("restart", "session", {"source": "startup"})):
        case = Case(tmp_path, label)
        proc = case.start_runner(grace=1.5)
        time.sleep(0.5)
        case.write_marker(signal, **fields)
        _finish(proc)
        check(case, label, typing=[])

    # (d) Phase wechselt in der Grace-Zeit
    case = Case(tmp_path, "phase")
    proc = case.start_runner(grace=1.5)
    time.sleep(0.5)
    subprocess.run(["bash", str(case.phase_changer())], check=True, timeout=30)
    _finish(proc)
    check(case, "phase", typing=[], reason="vor /clear")

    # (e) Herdr-Fehler: Binary ungültig (vor dem Nehmen) bzw. send-text scheitert (danach)
    case = Case(tmp_path, "herdr-bin", HERDR_BIN_PATH=str(tmp_path / "gibt-es-nicht"))
    res = case.run_runner(announce="1")
    assert res.returncode == 0, res.stderr
    check(case, "herdr-bin", typing=[])
    case = Case(tmp_path, "herdr-text", STUB_TEXT_EXIT="1")
    res = case.run_runner()
    assert res.returncode == 0, res.stderr
    check(case, "herdr-text", typing=[CLEAR[0]])

    # (f) Nutzereingabe zwischen Text und Enter: Zeile gelöscht, Vermerk NICHT zurückgelegt
    case = Case(tmp_path, "input-between")
    case.after_text_hook("/clear", "input")
    res = case.run_runner(since=time.time() - 0.5)
    assert res.returncode == 0, res.stderr
    check(case, "input-between", typing=[CLEAR[0], CTRL_U], reason=TYPED_ON)

    # (g) /99-reset-Sperre
    case = Case(tmp_path, "reset", boundary=_boundary(command=RESET))
    res = case.run_runner(command=RESET)
    assert res.returncode == 0, res.stderr
    check(case, "reset", typing=[], reason="manuell")

    # (h) nach abgeschicktem /clear (kein SessionStart): bleibt verbraucht
    case = Case(tmp_path, "after-clear", STUB_SESSION_SOURCE="none")
    res = case.run_runner(idle_timeout=1)
    assert res.returncode == 0, res.stderr
    check(case, "after-clear", typing=CLEAR, reason="SessionStart")

    assert not befunde, "\n".join(befunde)
