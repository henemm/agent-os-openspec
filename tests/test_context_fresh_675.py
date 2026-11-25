"""`workflow.py context` misst frische Sitzungen selbst (Issue #675).

Spec: docs/specs/fix-675-context-fresh.md (AC-1 bis AC-7).

Fehlt die Messdatei der laufenden Sitzung, liest `context` das Transcript
`<CLAUDE_CONFIG_DIR oder ~/.claude>/projects/<slug>/<sid>.jsonl` mit derselben
Rechnung wie `post_bash.py`. Isolation: tmp-Projekt mit kopierten Hooks, eigenes
HOME, Sitzungs-Id und Config-Ordner je Szenario explizit.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "core" / "hooks"
sys.path.insert(0, str(HOOKS))

import hook_utils  # noqa: E402

BUDGET = "context_budget:\n  enabled: true\n  clear_threshold_tokens: 100000\n"


def _project(root: Path) -> Path:
    hooks = root / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    for f in HOOKS.glob("*.py"):
        shutil.copy(f, hooks / f.name)
    (root / ".claude" / "config.yaml").write_text(BUDGET)
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    return root


def _env(root: Path, session: "str | None" = "sid-675",
         config_dir: "Path | None" = None) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("OPENSPEC_", "HERDR_"))
           and k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_CODE_SESSION_ID",
                         "CLAUDE_PLUGIN_ROOT", "CLAUDE_CONFIG_DIR")}
    env["CLAUDE_PROJECT_DIR"] = str(root)
    home = root / "_home"
    home.mkdir(exist_ok=True)
    env["HOME"] = str(home)
    env["OPENSPEC_AUTONOMY"] = "manual"
    if session is not None:
        env["CLAUDE_CODE_SESSION_ID"] = session
    if config_dir is not None:
        env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    return env


def _transcript(base: Path, session: str, usage: dict, slug: str = "-tmp-proj") -> Path:
    path = base / "projects" / slug / f"{session}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"type": "user", "message": {"content": "hi"}},
        {"type": "assistant", "message": {"usage": {"input_tokens": 1,
                                                    "cache_read_input_tokens": 10}}},
        {"type": "assistant", "isSidechain": True,
         "message": {"usage": {"input_tokens": 999_999}}},
        {"type": "assistant", "message": {"usage": usage}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def _write_usage(root: Path, tokens: int, session: str) -> Path:
    path = root / ".claude" / "context_usage" / f"{session}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"session_id": session, "tokens": tokens,
                                "baseline_tokens": 20_000,
                                "at": "2026-11-25T10:00:00", "announced_bucket": 0}))
    return path


def _context(root: Path, env: dict) -> "list[str]":
    res = subprocess.run([sys.executable, str(root / ".claude" / "hooks" / "workflow.py"),
                          "context"], cwd=root, env=env, capture_output=True, text=True,
                         timeout=60)
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr
    return res.stdout.splitlines()


def _kv(lines, key):
    return next((l[len(key) + 1:] for l in lines if l.startswith(key + "=")), None)


USAGE = {"input_tokens": 5, "cache_creation_input_tokens": 1_000,
         "cache_read_input_tokens": 95_000}   # Summe 96.005


def test_ac1_fresh_session_reads_own_transcript(tmp_path):
    root = _project(tmp_path / "p")
    env = _env(root)
    _transcript(Path(env["HOME"]) / ".claude", "sid-675", USAGE)
    lines = _context(root, env)
    assert _kv(lines, "CONTEXT_TOKENS") == "96005"
    assert lines[-1].startswith("CONTEXT_STOP=")


def test_ac2_own_usage_file_wins_over_transcript(tmp_path):
    root = _project(tmp_path / "p")
    env = _env(root)
    _transcript(Path(env["HOME"]) / ".claude", "sid-675", USAGE)
    _write_usage(root, 42_000, "sid-675")
    assert _kv(_context(root, env), "CONTEXT_TOKENS") == "42000"


def test_ac3_foreign_newer_usage_does_not_shadow_own_transcript(tmp_path):
    root = _project(tmp_path / "p")
    env = _env(root)
    _transcript(Path(env["HOME"]) / ".claude", "sid-675", USAGE)
    _write_usage(root, 180_000, "other-session")
    assert _kv(_context(root, env), "CONTEXT_TOKENS") == "96005"


def test_ac4_nothing_found_unknown(tmp_path):
    root = _project(tmp_path / "p")
    assert _kv(_context(root, _env(root)), "CONTEXT_TOKENS") == "unknown"


def test_ac4_no_transcript_keeps_newest_fallback(tmp_path):
    root = _project(tmp_path / "p")
    _write_usage(root, 77_000, "other-session")
    assert _kv(_context(root, _env(root)), "CONTEXT_TOKENS") == "77000"


def test_ac5_claude_config_dir_used(tmp_path):
    root = _project(tmp_path / "p")
    cfg = tmp_path / "cfg"
    env = _env(root, config_dir=cfg)
    _transcript(cfg, "sid-675", USAGE)
    # Gegenprobe: gleicher Sitzungs-Id unter HOME mit anderem Wert wird ignoriert
    _transcript(Path(env["HOME"]) / ".claude", "sid-675", {"input_tokens": 3})
    assert _kv(_context(root, env), "CONTEXT_TOKENS") == "96005"


def test_ac6_invalid_session_id_no_access(tmp_path, monkeypatch):
    home = tmp_path / "h"
    (home / ".claude" / "projects" / "x").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    for bad in ("../x", "a/b", "", "x" * 200):
        assert hook_utils.session_transcript_path(bad) is None
    root = _project(tmp_path / "p")
    lines = _context(root, _env(root, session="../evil"))
    assert _kv(lines, "CONTEXT_TOKENS") == "unknown"


def test_ac6_helper_picks_newest_and_respects_env(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    old = _transcript(cfg, "s9", USAGE, slug="a")
    new = _transcript(cfg, "s9", USAGE, slug="b")
    t = time.time()
    os.utime(old, (t - 100, t - 100))
    os.utime(new, (t, t))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s9")
    assert hook_utils.session_transcript_path() == new
    assert hook_utils.session_transcript_path("s9") == new


def test_ac7_context_writes_nothing(tmp_path):
    root = _project(tmp_path / "p")
    env = _env(root)
    _transcript(Path(env["HOME"]) / ".claude", "sid-675", USAGE)
    _context(root, env)
    assert not (root / ".claude" / "context_usage").exists()
