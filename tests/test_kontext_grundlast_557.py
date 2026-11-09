"""Kontext-Schwelle relativ zum Grundkontext (Issue #557).

Spec: docs/specs/fix-557-kontext-grundlast.md (AC-1 bis AC-9).

In Cloud-Sitzungen liegt der Grundkontext direkt nach `/clear` schon bei ~100k Token;
die feste Schwelle (100k) stand dort dauerhaft auf `CONTEXT_CUT=on`. Neu:

- `record_context_usage` fuehrt `baseline_tokens` (erster Messwert; Reset auf den
  neuen Wert und `announced_bucket` = 0, wenn der Messwert mehr als 30 % unter dem
  vorigen liegt, Zeichen fuer `/clear`/`/compact`).
- `context_budget_settings` liefert zusaetzlich `growth` (`context_budget.growth_tokens`,
  int >= 1000, Default `CONTEXT_BUDGET_DEFAULT_GROWTH` = 75000 im Code).
- `effective_context_threshold(settings, baseline)` = `max(threshold, baseline + growth)`,
  Baseline None/kein int -> nur `threshold`.
- `post_bash.py` stuft relativ zur wirksamen Schwelle; `workflow.py context` meldet
  `CONTEXT_CUT` gegen die wirksame Schwelle und eine Zeile `CONTEXT_THRESHOLD=`.

Isolation: jedes Szenario laeuft in einem eigenen tmp-Projekt (`CLAUDE_PROJECT_DIR`,
eigenes HOME), damit eine echte `.claude/auftrag.json` im Entwickler-Checkout das
Ergebnis nicht auf AUTARK zieht.
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
sys.path.insert(0, str(HOOKS))

import hook_utils  # noqa: E402

CONFIG = "context_budget:\n  enabled: true\n  clear_threshold_tokens: 100000\n"
KILL_CONFIG = "context_budget:\n  enabled: false\n  clear_threshold_tokens: 100000\n"


# --- Helpers -----------------------------------------------------------------

def _project(root: Path, config: str = CONFIG) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    hooks = root / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    for f in HOOKS.glob("*.py"):
        shutil.copy(f, hooks / f.name)
    (root / ".claude" / "config.yaml").write_text(config)
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    return root


def _env(root: Path, **extra: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("OPENSPEC_", "HERDR_", "STUB_"))
           and k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PLUGIN_ROOT")}
    env["CLAUDE_PROJECT_DIR"] = str(root)
    home = root / "_home"
    home.mkdir(exist_ok=True)
    env["HOME"] = str(home)
    env.update(extra)
    return env


def _run(root: Path, script: str, *args: str, stdin: "str | None" = None,
         **extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(root / ".claude" / "hooks" / script), *args],
                          cwd=root, env=_env(root, **extra), capture_output=True, text=True,
                          input=stdin, timeout=60)


def _transcript(path: Path, tokens: int) -> Path:
    rows = [{"type": "user", "message": {}},
            {"type": "assistant", "message": {"usage": {
                "input_tokens": 40, "cache_creation_input_tokens": 2000,
                "cache_read_input_tokens": tokens - 2040, "output_tokens": 5}}}]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def _post_bash(root: Path, tokens: int, session: str = "s1") -> "str | None":
    """post_bash.py mit Transcript der Groesse `tokens`; Hinweistext oder None."""
    tr = _transcript(root / "t.jsonl", tokens)
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"},
                          "tool_response": {"stdout": "", "stderr": ""},
                          "session_id": session, "transcript_path": str(tr)})
    res = _run(root, "post_bash.py", stdin=payload)
    assert res.returncode == 0, res.stderr
    if not res.stdout.strip():
        return None
    return json.loads(res.stdout)["hookSpecificOutput"]["additionalContext"]


def _usage_path(root: Path, session: str = "s1") -> Path:
    return root / ".claude" / "context_usage" / f"{session}.json"


def _usage(root: Path, session: str = "s1") -> dict:
    return json.loads(_usage_path(root, session).read_text())


def _write_usage(root: Path, tokens: int, baseline: "int | None" = None,
                 announced_bucket: int = 0, session: str = "s1") -> Path:
    data = {"session_id": session, "tokens": tokens, "at": "2026-11-09T10:00:00",
            "announced_bucket": announced_bucket}
    if baseline is not None:
        data["baseline_tokens"] = baseline
    path = _usage_path(root, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def _context(root: Path, session: str = "s1") -> "list[str]":
    res = _run(root, "workflow.py", "context", CLAUDE_CODE_SESSION_ID=session)
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
        "issues": [{"n": 547, "status": "open"}], "autark": True, "note": "",
        "created": "2026-11-09T10:00:00Z", "updated": "2026-11-09T10:00:00Z",
    }))


# --- AC-1: erster Messwert setzt die Baseline ---------------------------------

def test_first_measurement_sets_baseline(tmp_path):
    root = _project(tmp_path / "p")
    assert not _usage_path(root).exists()
    _post_bash(root, 100_000)
    usage = _usage(root)
    assert usage["tokens"] == 100_000
    assert usage.get("baseline_tokens") == 100_000, usage
    # Wachstum und Rueckgang bis einschliesslich 70 % des vorigen Werts: Baseline bleibt
    for tokens in (150_000, 105_000, 120_000):  # 105.000 = genau 70 % von 150.000
        _post_bash(root, tokens)
        usage = _usage(root)
        assert usage["tokens"] == tokens
        assert usage.get("baseline_tokens") == 100_000, (tokens, usage)


# --- AC-2: Reset bei Abfall um mehr als 30 % -----------------------------------

def test_baseline_resets_on_drop_over_30_percent(tmp_path):
    # Abfall 180.000 -> 40.000 (/clear): Baseline = 40.000, announced_bucket = 0
    root = _project(tmp_path / "drop")
    _write_usage(root, 180_000, baseline=100_000, announced_bucket=1)
    assert _post_bash(root, 40_000) is None
    usage = _usage(root)
    assert usage["tokens"] == 40_000
    assert usage.get("baseline_tokens") == 40_000, usage
    assert usage["announced_bucket"] == 0, usage

    # Rueckgang um hoechstens 30 % (180.000 -> 130.000): Baseline bleibt
    root = _project(tmp_path / "keep")
    _write_usage(root, 180_000, baseline=100_000, announced_bucket=1)
    _post_bash(root, 130_000)
    usage = _usage(root)
    assert usage["tokens"] == 130_000
    assert usage.get("baseline_tokens") == 100_000, usage
    assert usage["announced_bucket"] == 1, usage  # ohne Reset kein Zuruecksetzen der Stufe


# --- AC-3: Formel der wirksamen Schwelle, Default und Override -------------------

def test_effective_threshold_formula_default_and_override():
    assert hook_utils.CONTEXT_BUDGET_DEFAULT_GROWTH == 75_000

    default = hook_utils.context_budget_settings({})
    assert default["threshold"] == 100_000
    assert default["growth"] == 75_000
    eff = hook_utils.effective_context_threshold
    assert eff(default, 100_000) == 175_000          # Cloud: Baseline + Wachstum
    assert eff(default, 25_000) == 100_000           # lokal: absolute Schwelle gewinnt
    assert eff(default, 25_001) == 100_001
    assert eff(default, None) == 100_000             # alte Messdatei ohne Baseline
    assert eff(default, "100000") == 100_000         # kein int -> nur absolute Schwelle

    custom = hook_utils.context_budget_settings({"context_budget": {"growth_tokens": 50_000}})
    assert custom["growth"] == 50_000
    assert eff(custom, 100_000) == 150_000
    both = hook_utils.context_budget_settings(
        {"context_budget": {"clear_threshold_tokens": 120_000, "growth_tokens": 1000}})
    assert both["threshold"] == 120_000 and both["growth"] == 1000
    assert eff(both, 10_000) == 120_000
    assert eff(both, 200_000) == 201_000

    for bad in ("75k", "50000", 999, 0, -5, 60000.0, True, None):
        s = hook_utils.context_budget_settings({"context_budget": {"growth_tokens": bad}})
        assert s["growth"] == 75_000, (bad, s)
        assert s["threshold"] == 100_000 and s["enabled"] is True


# --- AC-4: Cloud-Szenario mit 100k Grundkontext ---------------------------------

def test_cloud_scenario_cut_on_only_after_growth(tmp_path):
    root = _project(tmp_path / "p")
    _post_bash(root, 100_000)  # erster Messwert = Grundkontext
    for tokens, expected in ((100_000, "off"), (150_000, "off"), (174_999, "off"),
                             (175_000, "on"), (200_000, "on")):
        _post_bash(root, tokens)
        lines = _context(root)
        assert _kv(lines, "CONTEXT_TOKENS") == str(tokens), lines
        assert _kv(lines, "CONTEXT_CUT") == expected, (tokens, lines)
    assert _usage(root).get("baseline_tokens") == 100_000


# --- AC-5: lokales Szenario mit 25k Grundlast -------------------------------------

def test_local_scenario_threshold_stays_100k(tmp_path):
    root = _project(tmp_path / "p")
    _post_bash(root, 25_000)
    for tokens, expected in ((99_999, "off"), (100_000, "on")):
        _post_bash(root, tokens)
        lines = _context(root)
        assert _kv(lines, "CONTEXT_TOKENS") == str(tokens), lines
        assert _kv(lines, "CONTEXT_CUT") == expected, (tokens, lines)
        assert _kv(lines, "CONTEXT_THRESHOLD") == "100000", lines
    assert _usage(root).get("baseline_tokens") == 25_000


# --- AC-6: Zeile CONTEXT_THRESHOLD ------------------------------------------------

def test_context_prints_effective_threshold_line(tmp_path):
    root = _project(tmp_path / "cloud")
    _write_usage(root, 120_000, baseline=100_000)
    assert _context(root) == ["CONTEXT_TOKENS=120000", "CONTEXT_CUT=off",
                              "CONTEXT_THRESHOLD=175000"]

    root = _project(tmp_path / "local")
    _write_usage(root, 120_000, baseline=25_000)
    assert _context(root) == ["CONTEXT_TOKENS=120000", "CONTEXT_CUT=on",
                              "CONTEXT_THRESHOLD=100000"]


# --- AC-7: post_bash-Stufen relativ zur wirksamen Schwelle --------------------------

def test_post_bash_buckets_relative_to_effective_threshold(tmp_path):
    root = _project(tmp_path / "p")
    assert _post_bash(root, 100_000) is None   # Baseline 100.000 -> wirksam 175.000
    assert _usage(root).get("baseline_tokens") == 100_000
    assert _post_bash(root, 120_000) is None, "unter der wirksamen Schwelle kein Hinweis"

    note = _post_bash(root, 175_000)
    assert note is not None and note.startswith("KONTEXT-SCHWELLE"), note
    assert "~175.000" in note and "Schwelle 175.000" in note, note
    assert _usage(root)["announced_bucket"] == 1

    assert _post_bash(root, 180_000) is None, "gleiche Stufe: kein zweiter Hinweis"

    note = _post_bash(root, 225_000)  # +50k ueber der wirksamen Schwelle
    assert note is not None and "~225.000" in note and "Schwelle 175.000" in note, note
    usage = _usage(root)
    assert usage["announced_bucket"] == 2 and usage.get("baseline_tokens") == 100_000, usage


# --- AC-8: alte Messdatei ohne baseline_tokens ----------------------------------------

def test_old_usage_file_without_baseline_behaves_as_before(tmp_path):
    root = _project(tmp_path / "p")
    _write_usage(root, 99_999)  # alte Fassung: kein baseline_tokens
    assert _context(root) == ["CONTEXT_TOKENS=99999", "CONTEXT_CUT=off",
                              "CONTEXT_THRESHOLD=100000"]
    _write_usage(root, 100_000)
    assert _context(root) == ["CONTEXT_TOKENS=100000", "CONTEXT_CUT=on",
                              "CONTEXT_THRESHOLD=100000"]
    assert "baseline_tokens" not in _usage(root), "context liest nur, schreibt nicht"


# --- AC-9: Autark (#551) und Kill-Switch unveraendert ------------------------------------

def test_autark_and_kill_switch_unchanged(tmp_path):
    # Autark: context bleibt off + AUTARK, post_bash-Hinweis im Autark-Wortlaut
    root = _project(tmp_path / "autark")
    _write_autark_auftrag(root)
    assert _post_bash(root, 100_000) is None  # Baseline, unter der wirksamen Schwelle
    note = _post_bash(root, 200_000)
    assert note is not None and note.startswith("KONTEXT-SCHWELLE"), note
    assert "Schwelle 175.000" in note, note
    assert "Ein autarker Auftrag läuft" in note, note
    lines = _context(root)
    assert _kv(lines, "CONTEXT_TOKENS") == "200000", lines
    assert _kv(lines, "CONTEXT_CUT") == "off", lines
    assert _kv(lines, "CONTEXT_REASON") == "AUTARK", lines

    # Kill-Switch: post_bash ohne Hinweis und ohne Messdatei
    root = _project(tmp_path / "kill_post", KILL_CONFIG)
    assert _post_bash(root, 200_000) is None
    assert not (root / ".claude" / "context_usage").exists()

    # Kill-Switch: context off (auch mit vorhandener Messung ueber der wirksamen Schwelle)
    root = _project(tmp_path / "kill_ctx", KILL_CONFIG)
    _write_usage(root, 200_000, baseline=100_000)
    lines = _context(root)
    assert _kv(lines, "CONTEXT_CUT") == "off", lines
    assert _kv(lines, "CONTEXT_REASON") is None, lines
