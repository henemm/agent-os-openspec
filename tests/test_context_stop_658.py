"""Kontext-Halt nur dort, wo `/clear` automatisch kommt (Issue #658).

Spec: docs/specs/fix-658-context-stop-auto.md (AC-1 bis AC-9).

`CONTEXT_CUT` bleibt der Messfakt (Kontext >= wirksame Schwelle, #557). Neu ist die
Entscheidung `CONTEXT_STOP=on|off` als letzte Zeile von `workflow.py context`:
`on` genau dann, wenn CUT=on und Modus `manual` (#662: Herdr-Auto-/clear ist
stillgelegt und zaehlt nicht mehr). Im Auto-Modus steht bei CUT=on zusaetzlich
`CONTEXT_REASON=AUTO_NO_CLEAR` (nach `CONTEXT_THRESHOLD`), auch mit Herdr-Pane und
Auto-/clear-Schalter. Entscheidungs-Helfer: `hook_utils.context_stop_applies()`;
Fehler darin -> STOP folgt CUT.

#662 (docs/specs/feat-662-kette-flach.md): `test_auto_with_herdr_auto_clear_stop_on`
und `test_autoclear_output_unchanged` sind entfallen, ersetzt durch
tests/test_auto_chain_flat_662.py (AC-5 bzw. AC-2); AC-7 und AC-9 der #662-Spec
liegen hier (`test_helper_error_stop_follows_cut`, `test_post_bash_note_wording_per_variant`).
#663 (docs/specs/chore-663-rueckbau-autoclear.md, AC-9): `auto_clear_active` existiert
nicht mehr; der Herdr-Fall laeuft ohne ladbare Bridge und belegt, dass Config und Env
`OPENSPEC_HERDR_AUTO_CLEAR` `CONTEXT_STOP` nicht beeinflussen.

Isolation: jedes Szenario in einem eigenen tmp-Projekt (Hooks nach `.claude/hooks`
kopiert, eigenes HOME). Die Cloud-Umgebung setzt `OPENSPEC_AUTONOMY=auto`; die
Test-Env entfernt deshalb alle `OPENSPEC_*`/`HERDR_*` und setzt Autonomie und
Herdr je Szenario explizit.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "core" / "hooks"
COMMANDS = REPO / "core" / "commands"
SKILLS = REPO / "skills"
sys.path.insert(0, str(HOOKS))

import hook_utils  # noqa: E402

BUDGET = "context_budget:\n  enabled: true\n  clear_threshold_tokens: 100000\n"
HERDR_AUTO_CLEAR_ON = "herdr:\n  enabled: true\n  auto_clear:\n    enabled: true\n"
HERDR_AUTO_CLEAR_OFF = "herdr:\n  enabled: true\n  auto_clear:\n    enabled: false\n"
AUTONOMY_AUTO_CFG = "autonomy:\n  mode: auto\n"
AUTONOMY_MANUAL_CFG = "autonomy:\n  mode: manual\n"

OVER = 150_000    # ueber der wirksamen Schwelle 100.000 (Baseline 20.000)
UNDER = 50_000
BASELINE = 20_000
STUB = "#!/bin/sh\nexit 0\n"


# --- Helpers -----------------------------------------------------------------

def _project(root: Path, config: str = "") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    hooks = root / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    for f in HOOKS.glob("*.py"):
        shutil.copy(f, hooks / f.name)
    (root / ".claude" / "config.yaml").write_text(BUDGET + config)
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    return root


def _stub(root: Path) -> Path:
    stub = root / "_herdr-stub"
    stub.write_text(STUB)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def _env(root: Path, *, autonomy: "str | None" = None, herdr: bool = False,
         auto_clear_env: "str | None" = None, session: "str | None" = "s1") -> dict:
    """Saubere Env: kein geerbtes OPENSPEC_*/HERDR_*; Autonomie und Herdr explizit."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("OPENSPEC_", "HERDR_", "STUB_"))
           and k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PLUGIN_ROOT")}
    env["CLAUDE_PROJECT_DIR"] = str(root)
    home = root / "_home"
    home.mkdir(exist_ok=True)
    env["HOME"] = str(home)
    if autonomy is not None:
        env["OPENSPEC_AUTONOMY"] = autonomy
    if herdr:
        env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": "pane-658",
                    "HERDR_BIN_PATH": str(_stub(root))})
    if auto_clear_env is not None:
        env["OPENSPEC_HERDR_AUTO_CLEAR"] = auto_clear_env
    if session is not None:
        env["CLAUDE_CODE_SESSION_ID"] = session
    return env


def _run(root: Path, script: str, *args: str, env: dict,
         stdin: "str | None" = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(root / ".claude" / "hooks" / script), *args],
                          cwd=root, env=env, capture_output=True, text=True,
                          input=stdin, timeout=60)


def _write_usage(root: Path, tokens: int, session: str = "s1") -> None:
    path = root / ".claude" / "context_usage" / f"{session}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"session_id": session, "tokens": tokens,
                                "baseline_tokens": BASELINE,
                                "at": "2026-11-25T10:00:00", "announced_bucket": 0}))


def _context(root: Path, env: dict) -> "list[str]":
    res = _run(root, "workflow.py", "context", env=env)
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr
    return res.stdout.splitlines()


def _kv(lines: "list[str]", key: str) -> "str | None":
    for line in lines:
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


def _write_autark_auftrag(root: Path) -> None:
    path = root / ".claude" / "auftrag.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "issues": [{"n": 658, "status": "open"}], "autark": True, "note": "",
        "created": "2026-11-25T10:00:00Z", "updated": "2026-11-25T10:00:00Z",
    }))


def _transcript(path: Path, tokens: int) -> Path:
    rows = [{"type": "user", "message": {}},
            {"type": "assistant", "message": {"usage": {
                "input_tokens": 40, "cache_creation_input_tokens": 2000,
                "cache_read_input_tokens": tokens - 2040, "output_tokens": 5}}}]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def _post_bash_note(root: Path, env: dict, tokens: int = 122_040) -> str:
    """Erst Grundkontext 20k (Baseline, kein Hinweis), dann `tokens` -> Hinweistext."""
    def once(t: int) -> subprocess.CompletedProcess:
        tr = _transcript(root / "t.jsonl", t)
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"},
                              "tool_response": {"stdout": "", "stderr": ""},
                              "session_id": "s1", "transcript_path": str(tr)})
        res = _run(root, "post_bash.py", env=env, stdin=payload)
        assert res.returncode == 0, res.stderr
        return res

    assert once(BASELINE).stdout.strip() == ""
    res = once(tokens)
    assert res.stdout.strip(), f"kein Kontext-Hinweis, stderr={res.stderr!r}"
    return json.loads(res.stdout)["hookSpecificOutput"]["additionalContext"]


# --- AC-1: Auto-Modus ohne Herdr-Auto-Clear -> STOP off + Grund ----------------

def test_auto_without_herdr_stop_off_with_reason(tmp_path):
    expected = ["CONTEXT_TOKENS=150000", "CONTEXT_CUT=on", "CONTEXT_THRESHOLD=100000",
                "CONTEXT_REASON=AUTO_NO_CLEAR", "CONTEXT_HANDOFF=off", "CONTEXT_STOP=off"]
    cases = {
        # Cloud: Env-Schalter auto, kein Herdr
        "env-auto": ("", dict(autonomy="auto")),
        # Projekt-Config auto, kein Herdr
        "cfg-auto": (AUTONOMY_AUTO_CFG, dict()),
        # Herdr-Pane vorhanden, aber Auto-Clear aus
        "herdr-no-clear": (HERDR_AUTO_CLEAR_OFF, dict(autonomy="auto", herdr=True)),
        # Auto-Clear eingeschaltet, aber kein Herdr-Pane
        "clear-no-pane": (HERDR_AUTO_CLEAR_ON, dict(autonomy="auto")),
    }
    for label, (config, kw) in cases.items():
        root = _project(tmp_path / label, config)
        _write_usage(root, OVER)
        env = _env(root, **kw)
        # #696: mit Herdr-Pane und `claude` im PATH meldet context CONTEXT_HANDOFF=on
        handoff = ("on" if kw.get("herdr") and shutil.which("claude", path=env.get("PATH"))
                   and env.get("CLAUDE_CODE_REMOTE", "").lower() != "true" else "off")
        want = [f"CONTEXT_HANDOFF={handoff}" if l.startswith("CONTEXT_HANDOFF=") else l
                for l in expected]
        lines = _context(root, env)
        assert lines == want, (label, lines)


# --- AC-3: Modus manual -> STOP on (mit oder ohne Herdr) --------------------------

def test_manual_mode_stop_on(tmp_path):
    expected = ["CONTEXT_TOKENS=150000", "CONTEXT_CUT=on", "CONTEXT_THRESHOLD=100000",
                "CONTEXT_HANDOFF=off", "CONTEXT_STOP=on"]
    cases = {
        "no-env": ("", dict()),                                  # nichts gesetzt = manual
        "env-manual": ("", dict(autonomy="manual")),
        "cfg-manual-beats-env": (AUTONOMY_MANUAL_CFG, dict(autonomy="auto")),
        "manual-herdr-clear": (HERDR_AUTO_CLEAR_ON, dict(autonomy="manual", herdr=True)),
        "manual-herdr-no-clear": (HERDR_AUTO_CLEAR_OFF, dict(autonomy="manual", herdr=True)),
    }
    for label, (config, kw) in cases.items():
        root = _project(tmp_path / label, config)
        _write_usage(root, OVER)
        lines = _context(root, _env(root, **kw))
        assert lines[-1] == "CONTEXT_STOP=on", (label, lines)
        assert lines == expected, (label, lines)


# --- AC-4: unter der Schwelle -> CUT off, STOP off, kein Grund --------------------

def test_below_threshold_cut_and_stop_off(tmp_path):
    cases = {
        "auto": ("", dict(autonomy="auto")),
        "auto-herdr-clear": (HERDR_AUTO_CLEAR_ON, dict(autonomy="auto", herdr=True)),
        "manual": ("", dict(autonomy="manual")),
    }
    for label, (config, kw) in cases.items():
        root = _project(tmp_path / label, config)
        _write_usage(root, UNDER)
        lines = _context(root, _env(root, **kw))
        assert lines == ["CONTEXT_TOKENS=50000", "CONTEXT_CUT=off",
                         "CONTEXT_THRESHOLD=100000", "CONTEXT_HANDOFF=off",
                         "CONTEXT_STOP=off"], (label, lines)

        # ohne jede Messung: unknown, ebenfalls off
        bare = _project(tmp_path / f"{label}-unknown", config)
        lines = _context(bare, _env(bare, **kw))
        assert lines == ["CONTEXT_TOKENS=unknown", "CONTEXT_CUT=off",
                         "CONTEXT_THRESHOLD=100000", "CONTEXT_HANDOFF=off",
                         "CONTEXT_STOP=off"], (label, lines)


# --- AC-5: autarker Auftrag -> CUT off + AUTARK, STOP off --------------------------

def test_autark_stop_off(tmp_path):
    cases = {
        "auto": ("", dict(autonomy="auto")),
        "auto-herdr-clear": (HERDR_AUTO_CLEAR_ON, dict(autonomy="auto", herdr=True)),
    }
    for label, (config, kw) in cases.items():
        root = _project(tmp_path / label, config)
        _write_usage(root, OVER)
        _write_autark_auftrag(root)
        # ohne Sitzungskennung: Auftrag liegt besitzerlos in .claude/auftrag.json
        lines = _context(root, _env(root, session=None, **kw))
        assert lines == ["CONTEXT_TOKENS=150000", "CONTEXT_CUT=off",
                         "CONTEXT_REASON=AUTARK", "CONTEXT_HANDOFF=off",
                         "CONTEXT_STOP=off"], (label, lines)


# --- AC-6: Fehler im Entscheidungs-Helfer -> STOP folgt CUT ------------------------

WRAPPER = '''
import sys
sys.path.insert(0, sys.argv[1])
mode = sys.argv[2]
if mode == "herdr":
    # #663: Herdr ist kein Teil der Entscheidung; die Bridge ist hier gar nicht ladbar
    sys.modules["herdr_bridge"] = None
import hook_utils, workflow

def boom(*a, **k):
    raise RuntimeError("boom-658")

if mode == "helper":
    hook_utils.context_stop_applies = boom
    workflow.context_stop_applies = boom   # falls workflow den Namen direkt bindet
elif mode == "autonomy":
    workflow.autonomy_mode = boom
workflow.cmd_context([])
'''


def _context_patched(root: Path, mode: str, env: dict) -> "list[str]":
    script = root / "_wrap_658.py"
    script.write_text(WRAPPER)
    res = subprocess.run([sys.executable, str(script), str(root / ".claude" / "hooks"), mode],
                         cwd=root, env=env, capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr
    return res.stdout.splitlines()


def test_helper_error_stop_follows_cut(tmp_path):
    # Auto-Modus ohne Herdr: regulaer waere STOP=off; ein Fehler ergibt das alte Verhalten
    for mode in ("helper", "autonomy"):
        root = _project(tmp_path / f"over-{mode}")
        _write_usage(root, OVER)
        lines = _context_patched(root, mode, _env(root, autonomy="auto"))
        assert _kv(lines, "CONTEXT_CUT") == "on", (mode, lines)
        assert lines and lines[-1] == "CONTEXT_STOP=on", (mode, lines)
        assert "CONTEXT_REASON=AUTO_NO_CLEAR" not in lines, (mode, lines)

    # #662/#663: Herdr ist nicht Teil der Entscheidung. Auch ohne ladbare Bridge
    # bleibt es im Auto-Modus bei STOP=off mit Grund (kein Rueckfall auf Halt), trotz
    # Herdr-Pane, Config `herdr.auto_clear` und Env `OPENSPEC_HERDR_AUTO_CLEAR`.
    root = _project(tmp_path / "over-herdr", HERDR_AUTO_CLEAR_ON)
    _write_usage(root, OVER)
    lines = _context_patched(root, "herdr", _env(root, autonomy="auto", herdr=True,
                                                 auto_clear_env="1"))
    assert _kv(lines, "CONTEXT_CUT") == "on", lines
    assert "CONTEXT_REASON=AUTO_NO_CLEAR" in lines, lines
    assert lines and lines[-1] == "CONTEXT_STOP=off", lines

    # CUT off: STOP folgt CUT, also off
    root = _project(tmp_path / "under-helper")
    _write_usage(root, UNDER)
    lines = _context_patched(root, "helper", _env(root, autonomy="auto"))
    assert _kv(lines, "CONTEXT_CUT") == "off", lines
    assert lines and lines[-1] == "CONTEXT_STOP=off", lines


# --- AC-7: Hinweis-Wortlaut je Variante -------------------------------------------

def _assert_continue_wording(note: str, label: str) -> None:
    assert note.startswith("KONTEXT-SCHWELLE"), (label, note)
    assert re.search(r"weiterarbeiten|arbeite weiter", note), (label, note)
    assert "Teilagent" in note, (label, note)
    assert re.search(r"komprimier", note, re.IGNORECASE), (label, note)
    # #662: kein Herdr mehr im Hinweis (Auto-/clear stillgelegt), keine Halt-Aufforderung
    for forbidden in ("NICHT selbst aufrufen", "beende den Turn", "CONTEXT_STOP=on",
                      "CONTEXT_CUT=on", "Herdr"):
        assert forbidden not in note, (label, forbidden, note)


def _assert_stop_wording(note: str, label: str) -> None:
    assert note.startswith("KONTEXT-SCHWELLE"), (label, note)
    assert "CONTEXT_STOP=on" in note, (label, note)
    assert "CONTEXT_CUT=on" not in note, (label, note)
    assert "NICHT selbst aufrufen" in note, (label, note)


def test_post_bash_note_wording_per_variant(tmp_path):
    # direkt: dritte Variante per `stop=False`, Normalwortlaut nennt CONTEXT_STOP=on
    cont = hook_utils.context_cut_note(168_464, 100_000, stop=False)
    _assert_continue_wording(cont, "direkt stop=False")
    assert "~168.464 Token" in cont and "Schwelle 100.000" in cont, cont
    normal = hook_utils.context_cut_note(168_464, 100_000, stop=True)
    _assert_stop_wording(normal, "direkt stop=True")
    assert hook_utils.context_cut_note(168_464, 100_000) == normal

    # post_bash waehlt die Variante nach derselben Regel wie `workflow.py context`
    root = _project(tmp_path / "auto-no-herdr")
    _assert_continue_wording(_post_bash_note(root, _env(root, autonomy="auto")),
                             "auto ohne Herdr")

    root = _project(tmp_path / "manual")
    _assert_stop_wording(_post_bash_note(root, _env(root, autonomy="manual")), "manual")

    # #662: auch mit Herdr-Pane und Auto-/clear-Schalter weiterarbeiten (Config und Env)
    root = _project(tmp_path / "auto-herdr-clear", HERDR_AUTO_CLEAR_ON)
    _assert_continue_wording(_post_bash_note(root, _env(root, autonomy="auto", herdr=True)),
                             "auto mit Herdr-Auto-Clear")
    root = _project(tmp_path / "auto-herdr-env-clear", "herdr:\n  enabled: true\n")
    _assert_continue_wording(
        _post_bash_note(root, _env(root, autonomy="auto", herdr=True, auto_clear_env="1")),
        "auto mit Herdr-Env-Schalter")

    # Modus manual mit Herdr-Auto-/clear: Halt-Wortlaut wie ohne Herdr
    root = _project(tmp_path / "manual-herdr-clear", HERDR_AUTO_CLEAR_ON)
    _assert_stop_wording(_post_bash_note(root, _env(root, autonomy="manual", herdr=True)),
                         "manual mit Herdr-Auto-Clear")


# --- AC-8: Befehlstexte 10 bis 50 lesen CONTEXT_STOP --------------------------------

CHAIN = [("10-context", "20-analyse"), ("20-analyse", "30-write-spec"),
         ("30-write-spec", "40-tdd-red"), ("40-tdd-red", "50-implement"),
         ("50-implement", "60-validate")]


@pytest.mark.parametrize("name,follow", CHAIN)
def test_phase_commands_read_context_stop(name, follow):
    for path in (COMMANDS / f"{name}.md", SKILLS / name / "SKILL.md"):
        text = path.read_text(encoding="utf-8")
        paras = [p for p in text.split("\n\n")
                 if re.search(r"(?:workflow\.py|\$WF) context`", p) and "Kontext-Haushalt" in p]
        assert len(paras) == 1, (path, len(paras))
        para = paras[0]
        assert "CONTEXT_STOP=on" in para, (path, para)
        assert "CONTEXT_STOP=off" in para, (path, para)
        assert f"`{follow}` NICHT selbst aufrufen" in para, (path, para)
        assert f"❗Du-Zeile `/{follow} #<N>`" in para, (path, para)
        assert "Default 100.000 Token" in para, (path, para)
        # Halt-Ausloeser ist CONTEXT_STOP=on, nicht mehr CONTEXT_CUT=on
        assert "Bei `CONTEXT_CUT=on`" not in para, (path, para)
        assert para.index("CONTEXT_STOP=on") < para.index("NICHT selbst aufrufen"), (path, para)
