"""Auto-/clear: richtige Befehlsform, /10-context mit context_file, robuster
Issue-Titel (Issues #499, #500, #492).

Spec: docs/specs/fix-499-befehlsform-context-titel.md (AC-1 bis AC-11; AC-12 =
E2E-Skript, AC-13 = Regressionslauf).

Stub-Herdr und Hook-Helfer aus tests/test_herdr_auto_clear_467.py, Stub-`gh`-Muster
aus tests/test_plan_issue_titel_490.py. Jeder Fall laeuft in einem isolierten
Projekt mit `HOME` auf einem Wegwerf-Verzeichnis, damit Aliase unter `~/.claude`
des echten Benutzers nie mitzaehlen.

Vertraege, die diese Tests festlegen (die Spec nennt sie nicht exakt):
- `herdr_bridge.resolve_command_form(command) -> str`: Projekt aus
  `find_project_root()`, Home aus `Path.home()` (Spec: Implementation Details).
- Der Fehlerfall "Home nicht ermittelbar" wird per `sitecustomize` simuliert, das
  `pathlib.Path.home` eine `RuntimeError` werfen laesst (wie Python ohne HOME/pwd).
- Die Cache-Sperre ist eine `fcntl.flock`-Sperre auf `<cache>.lock`
  (Muster `herdr_bridge._pp_flock`).
"""

import fcntl
import json
import os
import stat
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_herdr_auto_clear_467 import (  # noqa: E402
    AUTO_ON,
    BRIDGE,
    FOOTER_GATE,
    HOOKS_DIR,
    REPO_ROOT,
    _calls,
    _kind,
    _make_stub,
    _prompts,
)

WORKFLOW_PY = HOOKS_DIR / "workflow.py"
PANE = "pane-499"
WF = "fix-999-befehlsform"
PHASE = "phase2_analyse"
SHORT = "/20-analyse #999"
PLUGIN = "/agent-os-openspec:20-analyse #999"
RESET = "/99-reset #999"
AC_LOG = Path(".claude") / "herdr_auto_clear.log"
TITLE_LOG = Path(".claude") / "issue_titles.log"
PLAIN = "Phase sauber abgeschlossen, Stand committet."

# Stub-gh: antwortet auf `api repos/.../issues/N` UND `issue view N` (damit AC-9
# am Cache-Verlust scheitert, nicht an der Aufrufform). Titel: ${GH_TITLE} oder
# "Titel <N>". GH_WAIT_UNTIL (epoch) synchronisiert parallele Aufrufe.
GH_STUB = r"""#!/bin/bash
printf '%s\n' "$*" >> "$GH_LOG"
if [ -n "$GH_WAIT_UNTIL" ]; then
  while [ "$(date +%s%N)" -lt "$GH_WAIT_UNTIL" ]; do :; done
fi
if [ -n "$GH_SLEEP" ]; then sleep "$GH_SLEEP"; fi
num=""
for a in "$@"; do
  case "$a" in
    repos/*/issues/*) num="${a##*/}" ;;
    [0-9]*) [ -z "$num" ] && num="$a" ;;
  esac
done
if [ -n "${GH_TITLE+x}" ]; then
  printf '%s\n' "$GH_TITLE"
else
  printf 'Titel %s\n' "$num"
fi
exit "${GH_EXIT:-0}"
"""

SITECUSTOMIZE_NO_HOME = (
    "import pathlib\n"
    "def _no_home(cls=None):\n"
    "    raise RuntimeError('Could not determine home directory.')\n"
    "pathlib.Path.home = classmethod(_no_home)\n"
)


# --- Helfer: Projekt, Runner, Hook --------------------------------------------

def _project(root: Path, phase: str = PHASE, **fields) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    data = {"name": WF, "workflow_type": "bugfix", "current_phase": phase,
            "phase_transitions": [], "phase_log": []}
    data.update(fields)
    (proj / ".claude" / "workflows" / f"{WF}.json").write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(WF)
    (proj / "config.yaml").write_text(AUTO_ON)
    return proj


def _env(proj: Path, log: Path, stub: Path, **extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_", "GH_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": PANE,
                "HERDR_BIN_PATH": str(stub), "STUB_LOG": str(log)})
    env.update(extra)
    return env


def _case(tmp_path: Path, label: str, phase: str = PHASE, **fields):
    root = tmp_path / label
    root.mkdir(parents=True)
    proj = _project(root, phase=phase, **fields)
    log = root / "stub.log"
    stub = _make_stub(root)
    return proj, log, _env(proj, log, stub), root


def _run_runner(proj: Path, env: dict, command: str = SHORT, phase: str = PHASE):
    argv = [sys.executable, str(BRIDGE), "auto-clear",
            "--pane", PANE, "--workflow", WF, "--phase", phase, "--command", command,
            "--grace", "0", "--settle", "0", "--idle-timeout", "5", "--announce", "0"]
    return subprocess.run(argv, capture_output=True, text=True, env=env,
                          cwd=str(proj), timeout=60)


def _texts(log: Path) -> list:
    return [c[3] for c in _prompts(_calls(log)) if len(c) > 3]


def _ac_log(proj: Path) -> str:
    path = proj / AC_LOG
    return path.read_text() if path.exists() else ""


def _du(command: str) -> str:
    return f"❗ Du: `{command}` — der naechste Pflicht-Schritt"


def _message(du: str) -> str:
    return "\n\n".join(["Phase abgeschlossen.", PLAIN, du,
                        "⚙ /20-analyse · agent-os-openspec 4.4.7"])


def _run_hook(proj: Path, env: dict, message: str):
    payload = {"session_id": "sess-499", "hook_event_name": "Stop", "cwd": str(proj),
               "last_assistant_message": message,
               "prompt_id": "11111111-2222-3333-4444-555555555555"}
    return subprocess.run([sys.executable, str(FOOTER_GATE)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, cwd=str(proj),
                          timeout=30)


def _wait_for(predicate, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return predicate()


def _alias_paths(proj: Path) -> dict:
    home = proj / "_home"
    return {
        "projekt-commands": proj / ".claude" / "commands" / "20-analyse.md",
        "projekt-skills": proj / ".claude" / "skills" / "20-analyse" / "SKILL.md",
        "home-commands": home / ".claude" / "commands" / "20-analyse.md",
        "home-skills": home / ".claude" / "skills" / "20-analyse" / "SKILL.md",
    }


def _py(code: str, env: dict, cwd: Path, timeout: float = 30):
    full = f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r})\n{code}"
    return subprocess.run([sys.executable, "-c", full], capture_output=True, text=True,
                          env=env, cwd=str(cwd), timeout=timeout)


# --- Helfer: Issue-Titel ------------------------------------------------------

def _gh_case(tmp_path: Path, label: str, *, gh: bool = True, **extra):
    root = tmp_path / label
    root.mkdir(parents=True)
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    log = root / "gh.log"
    bindir = root / "bin"
    bindir.mkdir()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "GH_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    env["GH_LOG"] = str(log)
    if gh:
        stub = bindir / "gh"
        stub.write_text(GH_STUB)
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        env["PATH"] = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"
    else:
        (bindir / "python3").symlink_to(sys.executable)
        env["PATH"] = str(bindir)
    env.update(extra)
    return proj, log, env


def _cache(proj: Path) -> Path:
    return proj / ".claude" / "issue_titles.json"


def _gh_calls(log: Path) -> list:
    return [ln for ln in log.read_text().splitlines() if ln] if log.exists() else []


def _fetch(proj: Path, env: dict, issue: str = "999", timeout: float = 8):
    code = ("import workflow\n"
            f"print('RESULT=' + repr(workflow.fetch_issue_title({issue!r}, timeout={timeout})))")
    return _py(code, env, proj, timeout=timeout + 30)


def _result(res) -> str:
    lines = [ln for ln in res.stdout.splitlines() if ln.startswith("RESULT=")]
    assert lines, f"Keine Ergebniszeile: stdout={res.stdout!r} stderr={res.stderr!r}"
    return lines[-1][len("RESULT="):]


# --- AC-1 ---------------------------------------------------------------------

def test_alias_present_in_each_location_sends_short_form(tmp_path):
    seen = {}
    for label in ("projekt-commands", "projekt-skills", "home-commands", "home-skills"):
        proj, log, env, _ = _case(tmp_path, label)
        alias = _alias_paths(proj)[label]
        alias.parent.mkdir(parents=True, exist_ok=True)
        alias.write_text("---\ndescription: Kurz-Alias\n---\nAlias\n")
        res = _run_runner(proj, env)
        assert res.returncode == 0, (label, res.stderr)
        seen[label] = _texts(log)
    for label, texts in seen.items():
        assert texts == ["/clear", SHORT], (label, texts)
    # Gegenprobe: dieselbe Konstellation ohne jede Alias-Datei waehlt NICHT die Kurzform
    proj, log, env, _ = _case(tmp_path, "ohne-alias")
    res = _run_runner(proj, env)
    assert res.returncode == 0, res.stderr
    assert _texts(log) == ["/clear", PLUGIN], (
        f"Ohne Alias muss die Plugin-Form gesendet werden: {_texts(log)}; "
        f"Log: {_ac_log(proj)!r}")


# --- AC-2 ---------------------------------------------------------------------

def test_no_alias_sends_plugin_form_keeps_arguments(tmp_path):
    proj, log, env, _ = _case(tmp_path, "plugin")
    res = _run_runner(proj, env)
    assert res.returncode == 0, res.stderr
    assert _texts(log) == ["/clear", PLUGIN], (_texts(log), _ac_log(proj))

    # Reine Funktion: Argumente bleiben, qualifizierte Befehle unveraendert
    code = ("import herdr_bridge as h\n"
            "for c in ['/20-analyse #999', '/20-analyse', '/30-write-spec #12 extra',\n"
            "          '/agent-os-openspec:20-analyse #999', '/anderes-plugin:x #1']:\n"
            "    print(repr(c) + ' -> ' + repr(h.resolve_command_form(c)))\n")
    res = _py(code, env, proj)
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert "'/20-analyse #999' -> '/agent-os-openspec:20-analyse #999'" in out, out
    assert "'/20-analyse' -> '/agent-os-openspec:20-analyse'" in out, out
    assert ("'/30-write-spec #12 extra' -> '/agent-os-openspec:30-write-spec #12 extra'"
            in out), out
    assert ("'/agent-os-openspec:20-analyse #999' -> '/agent-os-openspec:20-analyse #999'"
            in out), out
    assert "'/anderes-plugin:x #1' -> '/anderes-plugin:x #1'" in out, out


# --- AC-3 ---------------------------------------------------------------------

def test_form_check_error_falls_back_to_plugin_form(tmp_path):
    proj, log, env, root = _case(tmp_path, "nohome")
    site = root / "site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(SITECUSTOMIZE_NO_HOME)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(site)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    # Plausibilitaet: im Subprozess wirft Path.home() tatsaechlich
    check = _py("import pathlib\ntry:\n    pathlib.Path.home()\n    print('HOME-OK')\n"
                "except RuntimeError:\n    print('HOME-ERR')\n", env, proj)
    assert check.stdout.strip() == "HOME-ERR", (check.stdout, check.stderr)
    res = _run_runner(proj, env)
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr
    assert _texts(log) == ["/clear", PLUGIN], (_texts(log), _ac_log(proj))
    assert "OK" in _ac_log(proj), _ac_log(proj)


# --- AC-4 ---------------------------------------------------------------------

def test_state_log_and_lock_keep_short_form(tmp_path):
    proj, log, env, _ = _case(tmp_path, "shortkeys")
    res = subprocess.run([sys.executable, str(WORKFLOW_PY), "autoclear"],
                         capture_output=True, text=True, env=env, cwd=str(proj),
                         timeout=30)
    assert res.returncode == 0, res.stderr
    state = json.loads((proj / ".claude" / "workflows" / f"{WF}.json").read_text())
    boundary = state.get("auto_clear_boundary")
    assert isinstance(boundary, dict), state
    assert boundary.get("command") == SHORT, boundary

    res = _run_hook(proj, env, _message(_du(SHORT)))
    assert res.returncode == 0, res.stderr
    assert _wait_for(lambda: ": OK" in _ac_log(proj) or "ABBRUCH" in _ac_log(proj)), (
        f"Runner endete nicht; Log: {_ac_log(proj)!r}; Calls: {_calls(log)}")
    # getippter Text: Plugin-Form (kein Alias im Projekt/Home)
    assert _texts(log) == ["/clear", PLUGIN], (_texts(log), _ac_log(proj))
    # Log-Tag und Once-Lock-Schluessel: Kurzform
    assert f"{WF}|{PHASE}|{SHORT}: OK" in _ac_log(proj), _ac_log(proj)
    assert PLUGIN not in _ac_log(proj), _ac_log(proj)
    lock = json.loads((proj / ".claude" / "herdr_auto_clear_state.json").read_text())
    assert list(lock) == [f"{WF}|{PHASE}|{SHORT}"], lock
    # Ankuendigung nennt weiter die Kurzform (gleiche Quelle wie die Fusszeile)
    notes = [c for c in _calls(log) if _kind(c) == "notification show"]
    assert notes and SHORT in " ".join(notes[0]), notes


# --- AC-5 ---------------------------------------------------------------------

def test_99_reset_is_never_typed_automatically(tmp_path):
    fields = {"no_build_reason": "PO: nichts bauen",
              "auto_clear_boundary": {"phase": PHASE, "command": RESET,
                                      "at": datetime.now().isoformat()}}
    # (a) Stop-Hook: kein Spawn, Skip-Grund im Log
    proj, log, env, _ = _case(tmp_path, "hook", **fields)
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    data = json.loads((proj / ".claude" / "workflows" / f"{WF}.json").read_text())
    assert workflow.expected_footer_command(data) == RESET
    res = _run_hook(proj, env, _message(_du(RESET)))
    assert res.returncode == 0, res.stderr
    time.sleep(1.5)
    assert _calls(log) == [], f"Stub unerwartet aufgerufen: {_calls(log)}"
    assert "skip: Workflow-Abschluss bleibt manuell" in _ac_log(proj), _ac_log(proj)

    # (b) Runner direkt (defensiv): weder /clear noch /99-reset
    proj, log, env, _ = _case(tmp_path, "runner", no_build_reason="PO: nichts bauen")
    res = _run_runner(proj, env, command=RESET)
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr
    assert _texts(log) == [], f"Runner tippte: {_texts(log)}"
    assert "ABBRUCH" in _ac_log(proj), _ac_log(proj)


# --- AC-6 ---------------------------------------------------------------------

def test_context_command_and_skill_set_context_file_before_phase():
    target = "set-field context_file docs/context/[workflow-name].md"
    phase = "phase phase2_analyse"
    src = (REPO_ROOT / "core" / "commands" / "10-context.md").read_text()
    assert f"workflow.py {target}" in src, "10-context.md nennt set-field context_file nicht"
    assert src.index(f"workflow.py {target}") < src.index(f"workflow.py {phase}"), (
        "set-field context_file muss vor dem Phasenwechsel nach phase2_analyse stehen")
    skill = (REPO_ROOT / "skills" / "10-context" / "SKILL.md").read_text()
    assert target in skill, "SKILL.md nennt set-field context_file nicht"
    assert skill.index(target) < skill.index(phase), skill
    res = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"),
                          "--check"], capture_output=True, text=True,
                         cwd=str(REPO_ROOT), timeout=60)
    assert res.returncode == 0, f"Skill-Drift: {res.stdout}{res.stderr}"


# --- AC-7 ---------------------------------------------------------------------

def _clean(text: str) -> bool:
    return not any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in text) and "\x1b" not in text


def test_short_title_strips_control_and_ansi():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    st = workflow.short_title
    dirty = "\x1b[31mRot\x07 Titel\nzeile"
    out = st(dirty)
    assert _clean(out), repr(out)
    assert "[31m" not in out, repr(out)
    assert out == "Rot Titel zeile", repr(out)
    out = st("\x1b[1;32mFett\x1b[0m\tund\x7f\r\nmehr\x1b]0;fenster\x07 Text")
    assert _clean(out), repr(out)
    assert "Fett" in out and "mehr" in out and "Text" in out, repr(out)
    assert "0;fenster" not in out, repr(out)
    # Normalfall unveraendert
    assert st("Plan-Pane zeigt Übergänge für Größe") == "Plan-Pane zeigt Übergänge für Größe"
    assert st("eins zwei drei vier fünf sechs sieben") == "eins zwei drei vier fünf sechs…"
    assert st("  a   b  ") == "a b"
    assert st(None) == ""


# --- AC-8 ---------------------------------------------------------------------

def test_cache_value_is_renormalized(tmp_path):
    proj, log, env = _gh_case(tmp_path, "cache", gh=False)
    code = ("import json, workflow\n"
            "d = workflow._with_issue_title({'name': 'fix-999-befehlsform'})\n"
            "print('RESULT=' + json.dumps(d.get('issue_title', '<kein>')))")
    _cache(proj).write_text(json.dumps({"999": "Zeile eins\nZeile\x07 zwei\x1b[31m"}))
    res = _py(code, env, proj)
    assert res.returncode == 0, res.stderr
    title = json.loads(_result(res))
    assert _clean(title), repr(title)
    assert title == "Zeile eins Zeile zwei", repr(title)

    _cache(proj).write_text(json.dumps({"999": "\x1b[0m\x07\n\t"}))
    res = _py(code, env, proj)
    assert res.returncode == 0, res.stderr
    assert json.loads(_result(res)) == "<kein>", res.stdout


# --- AC-9 ---------------------------------------------------------------------

def test_parallel_cache_writes_lose_no_entry(tmp_path):
    proj, log, env = _gh_case(tmp_path, "parallel")
    issues = [str(n) for n in range(101, 125)]
    _cache(proj).write_text(json.dumps({"7": "Alt"}))
    start_ns = time.time_ns() + 2_000_000_000  # alle gh-Stubs antworten gleichzeitig
    env["GH_WAIT_UNTIL"] = str(start_ns)
    procs = []
    for issue in issues:
        code = ("import sys; sys.path.insert(0, %r)\nimport workflow\n"
                "print('RESULT=' + repr(workflow.fetch_issue_title(%r, timeout=20)))"
                % (str(HOOKS_DIR), issue))
        procs.append(subprocess.Popen([sys.executable, "-c", code], env=env, cwd=str(proj),
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True))
    for p in procs:
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0, err
        assert "Traceback" not in err, err
    cache = json.loads(_cache(proj).read_text())
    missing = [i for i in issues if cache.get(i) != f"Titel {i}"]
    assert not missing, f"Eintraege verloren: {missing}; Cache: {cache}"
    assert cache.get("7") == "Alt", cache

    # Nicht erhaeltliche Sperre: nach kurzer Frist fail-open, keine Exception
    proj2, log2, env2 = _gh_case(tmp_path, "locked")
    lock_path = Path(str(_cache(proj2)) + ".lock")
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        t0 = time.monotonic()
        res = _fetch(proj2, env2, "999")
        elapsed = time.monotonic() - t0
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr
    assert _result(res) == repr("Titel 999"), res.stdout
    assert elapsed < 8.0, f"Gesperrter Cache blockierte {elapsed:.1f}s"


# --- AC-10 --------------------------------------------------------------------

def test_fetch_uses_rest_api_call(tmp_path):
    long_title = "Auto-/clear tippt Kurzbefehl ohne installierte Aliase im TUI"
    proj, log, env = _gh_case(tmp_path, "rest", GH_TITLE=long_title)
    res = _fetch(proj, env, "999")
    assert res.returncode == 0, res.stderr
    expected = "Auto-/clear tippt Kurzbefehl ohne installierte Aliase…"
    assert _result(res) == repr(expected), res.stdout
    calls = _gh_calls(log)
    assert calls == ["api repos/{owner}/{repo}/issues/999 --jq .title"], calls
    assert not any("issue view" in c for c in calls), calls
    assert json.loads(_cache(proj).read_text()) == {"999": expected}


# --- AC-11 --------------------------------------------------------------------

def _title_log(proj: Path) -> str:
    path = proj / TITLE_LOG
    return path.read_text() if path.is_file() else ""


@pytest.mark.parametrize("label,gh,extra,timeout", [
    ("exit1", True, {"GH_EXIT": "1", "GH_TITLE": "Titel"}, 8),
    ("leer", True, {"GH_TITLE": ""}, 8),
    ("timeout", True, {"GH_SLEEP": "5", "GH_TITLE": "Titel"}, 1),
    ("ohne-gh", False, {}, 8),
])
def test_fetch_failure_is_logged_fail_open(tmp_path, label, gh, extra, timeout):
    proj, log, env = _gh_case(tmp_path, label, gh=gh, **extra)
    res = _fetch(proj, env, "999", timeout=timeout)
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr
    assert _result(res) == "None", res.stdout
    assert not _cache(proj).exists() or "999" not in json.loads(_cache(proj).read_text())
    lines = [ln for ln in _title_log(proj).splitlines() if "999" in ln]
    assert lines, f"Kein Eintrag mit Issue-Nummer in {TITLE_LOG}: {_title_log(proj)!r}"
    line = lines[-1]
    assert len(line.replace("999", "").strip()) > 10, f"Zeile ohne Grund: {line!r}"
    assert _clean(line), repr(line)

    # Nicht schreibbares Log (Verzeichnis statt Datei): Ergebnis unveraendert
    proj2, log2, env2 = _gh_case(tmp_path, f"{label}-ro", gh=gh, **extra)
    (proj2 / TITLE_LOG).mkdir(parents=True)
    res = _fetch(proj2, env2, "999", timeout=timeout)
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr
    assert _result(res) == "None", res.stdout
