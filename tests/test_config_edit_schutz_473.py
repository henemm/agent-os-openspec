"""edit_gate/bash_gate: Schutz der wirksamen Gate-Config ueber Edit/Write/MultiEdit
und das Anlegen vorrangiger Config-Dateien — Issue #473.

Spec: docs/specs/feat-473-config-edit-schutz.md (AC-1 bis AC-16).
Muster wie #410/#418/#439: `core/hooks/edit_gate.py` bzw. `bash_gate.py` DIESES
Arbeitsbaums laeuft als echter Subprozess gegen eine Wegwerf-Sandbox in
tmp_path (PreToolUse-JSON auf stdin). Abweichungen werden je Test gesammelt.

Importfehler des neuen Helfers (`protected_config_paths`) sind Test-FAIL, kein
Collection-Fehler: der Import passiert erst im Testkoerper.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bash_gate_state_integrity_410 import (  # noqa: E402
    OVERRIDE_HINT, PLUGIN_CONFIG, _expect, _sandbox_ohne_workflow,
    _worktree_sandbox,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
EDIT_GATE = HOOKS_DIR / "edit_gate.py"

APP_CONFIG = "port: 8080\nname: app\n"                 # kein Plugin-Block (#372)
AUTONOMY_AUTO = "autonomy:\n  mode: auto\n"            # Plugin-Block
CONFIG_MSG = "Gate-Config"                             # Marker der Config-Meldung
WF = "tokenwf"

_SCRUBBED = {"CLAUDE_TOOL_INPUT", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT",
             "PYTHONPATH"}


# --------------------------------------------------------------------- #
# Sandbox + Gate-Aufruf
# --------------------------------------------------------------------- #

def _env(proj: Path, home: Path, extra: "dict | None" = None) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in _SCRUBBED and not k.startswith("OPENSPEC_")
           and not k.startswith("GIT_")}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(home)
    env.update(extra or {})
    return env


def _proj(tmp_path: Path, files: "dict | None" = None):
    """Sandbox ohne Workflow: tmp/project (.git, .claude, docs) + tmp/home."""
    proj = (tmp_path / "project")
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude").mkdir()
    (proj / "docs").mkdir()
    proj = proj.resolve()
    home = (tmp_path / "home").resolve()
    (home / ".claude").mkdir(parents=True)
    for rel, text in (files or {}).items():
        p = proj / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return proj, home


def _token(proj: Path, key: str = "__infra__") -> None:
    (proj / ".claude" / "user_override_token.json").write_text(json.dumps({
        "version": 2,
        "tokens": {key: {"created": datetime.now().isoformat(),
                         "granted_by": "user_prompt"}},
    }))


def _gate(proj: Path, home: Path, tool: str, tool_input: dict,
          cwd: "Path | None" = None, extra_env: "dict | None" = None,
          script: "Path | None" = None):
    payload = json.dumps({"tool_name": tool, "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, str(script or EDIT_GATE)], input=payload,
        capture_output=True, text=True, env=_env(proj, home, extra_env),
        cwd=str(cwd or proj), timeout=60,
    )


def _write(path, content="x: 1\n") -> "tuple[str, dict]":
    return "Write", {"file_path": str(path), "content": content}


def _edit(path, old, new) -> "tuple[str, dict]":
    return "Edit", {"file_path": str(path), "old_string": old, "new_string": new}


def _multi(path, *pairs) -> "tuple[str, dict]":
    return "MultiEdit", {"file_path": str(path),
                         "edits": [{"old_string": o, "new_string": n}
                                   for o, n in pairs]}


def _check(label, call, proj, home, rc, needle=None, forbid=None, **kw) -> list:
    """Einen Gate-Aufruf pruefen; liefert Liste mit 0 oder 1 Abweichung."""
    tool, tin = call
    proc = _gate(proj, home, tool, tin, **kw)
    bad = proc.returncode != rc
    bad = bad or (needle is not None and needle not in proc.stderr)
    bad = bad or (forbid is not None and forbid in proc.stderr)
    if not bad:
        return []
    return [f"  {label} [{tool}]: rc={proc.returncode} (soll {rc}), "
            f"stderr={proc.stderr.strip()[:160]!r}"]


def _fail(ac: str, wrong: list) -> None:
    assert not wrong, f"{ac}: {len(wrong)} Abweichungen:\n" + "\n".join(wrong)


def _config_loader():
    """Import des Helfers erst im Test: Fehler = FAIL, nicht Collection-Error."""
    try:
        sys.path.insert(0, str(HOOKS_DIR))
        import config_loader
        return config_loader
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"config_loader nicht importierbar: {exc!r}")


def _pcp(root: Path, *args):
    cl = _config_loader()
    fn = getattr(cl, "protected_config_paths", None)
    if fn is None:
        pytest.fail("config_loader.protected_config_paths fehlt (Spec #473)")
    return fn(root, *args)


# --------------------------------------------------------------------- #
# AC-1
# --------------------------------------------------------------------- #

def test_edit_write_multiedit_on_effective_config_blocked(tmp_path):
    """AC-1: Write/Edit/MultiEdit auf die wirksame Config -> Exit 2 + 'override'."""
    wrong = []
    for i, (rel, text) in enumerate([
        ("openspec.yaml", PLUGIN_CONFIG),
        (".claude/openspec.yaml", PLUGIN_CONFIG),
        ("config.yaml", PLUGIN_CONFIG),  # Root-config.yaml MIT Plugin-Block
    ]):
        proj, home = _proj(tmp_path / f"s{i}", {rel: text})
        target = proj / rel
        for call in (
            _write(target, AUTONOMY_AUTO),
            _edit(target, "enabled: true", "enabled: false"),
            _multi(target, ("enabled: true", "enabled: false")),
        ):
            wrong += _check(rel, call, proj, home, 2, OVERRIDE_HINT)
    _fail("AC-1", wrong)


# --------------------------------------------------------------------- #
# AC-2
# --------------------------------------------------------------------- #

def test_create_higher_priority_blocked_lower_priority_free(tmp_path):
    """AC-2: vorrangige Datei anlegen blockt, nachrangige (wirkungslose) bleibt frei."""
    proj, home = _proj(tmp_path, {".claude/openspec.yaml": PLUGIN_CONFIG})
    wrong = _check("openspec.yaml (vorrangig, neu)",
                   _write(proj / "openspec.yaml", AUTONOMY_AUTO),
                   proj, home, 2, OVERRIDE_HINT)
    for rel in (".openspec.yaml", ".claude/.openspec.yaml"):
        wrong += _check(f"{rel} (nachrangig)", _write(proj / rel, AUTONOMY_AUTO),
                        proj, home, 0, forbid=CONFIG_MSG)
    _fail("AC-2", wrong)


# --------------------------------------------------------------------- #
# AC-3
# --------------------------------------------------------------------- #

def test_no_effective_config_creation_of_any_candidate_blocked(tmp_path):
    """AC-3: ohne wirksame Config blockt jeder Kandidat; Root-config.yaml nur mit Plugin-Block."""
    proj, home = _proj(tmp_path)
    wrong = []
    for rel in ("openspec.yaml", ".claude/openspec.yaml", ".claude/config.yaml",
                ".openspec.yaml", ".claude/.openspec.yaml"):
        wrong += _check(rel, _write(proj / rel, PLUGIN_CONFIG), proj, home, 2,
                        OVERRIDE_HINT)
    wrong += _check("config.yaml ohne Plugin-Block",
                    _write(proj / "config.yaml", APP_CONFIG), proj, home, 0,
                    forbid=CONFIG_MSG)
    wrong += _check("config.yaml mit Plugin-Block",
                    _write(proj / "config.yaml", AUTONOMY_AUTO), proj, home, 2,
                    OVERRIDE_HINT)
    _fail("AC-3", wrong)


# --------------------------------------------------------------------- #
# AC-4 / AC-5
# --------------------------------------------------------------------- #

def _app_config_proj(tmp_path):
    return _proj(tmp_path, {".claude/openspec.yaml": PLUGIN_CONFIG,
                            "config.yaml": APP_CONFIG})


def test_app_config_edit_without_plugin_block_free(tmp_path):
    """AC-4: Edit/MultiEdit auf App-config.yaml ohne Plugin-Block -> Exit 0 (#372)."""
    proj, home = _app_config_proj(tmp_path)
    target = proj / "config.yaml"
    wrong = []
    for call in (
        _edit(target, "port: 8080", "port: 9090"),
        _multi(target, ("port: 8080", "port: 9090"), ("name: app", "name: app2")),
        _write(target, "port: 1\nname: other\n"),
    ):
        wrong += _check("App-config.yaml", call, proj, home, 0, forbid=CONFIG_MSG)
    _fail("AC-4", wrong)


def test_app_config_edit_inserting_plugin_block_blocked(tmp_path):
    """AC-5: Plugin-Block in die App-config.yaml einfuegen -> Exit 2 + 'override'."""
    proj, home = _app_config_proj(tmp_path)
    target = proj / "config.yaml"
    wrong = []
    for call in (
        _write(target, APP_CONFIG + AUTONOMY_AUTO),
        _edit(target, "name: app", "name: app\nautonomy:\n  mode: auto"),
        _edit(target, "port: 8080", "framework:\n  enabled: false\nport: 8080"),
        _multi(target, ("port: 8080", "port: 9090"),
               ("name: app", "name: app\nframework:\n  enabled: false")),
    ):
        wrong += _check("App-config.yaml + Plugin-Block", call, proj, home, 2,
                        OVERRIDE_HINT)
    _fail("AC-5", wrong)


def _blowup_multi(target: Path, n: int) -> "tuple[str, dict]":
    """n Loesch-Edits (leerer new_string, eindeutig, ohne \\n) + Plugin-Block."""
    edits = [{"old_string": f"tok{i:03d}x", "new_string": ""} for i in range(n)]
    edits.append({"old_string": "port: 1", "new_string": "port: 1\nautonomy: 1"})
    return "MultiEdit", {"file_path": str(target), "edits": edits}


def test_app_config_multiedit_variant_blowup_blocked_fast(tmp_path):
    """AC-5 / F001: MultiEdit mit 24+ Loesch-Edits laesst die Variantenmenge nicht
    exponentiell wachsen (Hook-Timeout 10 s = Durchlass) — Exit 2 in < 2 s."""
    import time
    wrong = []
    # gleichfoermig (Adversary atk5: Varianten fallen per Dedup zusammen) und
    # unterscheidbar (jede Kombination eigene Fassung: Deckel greift, Exit 2 fail-closed)
    for label, line in (("atk5", "tok{i:03d}x\n"), ("distinct", "tok{i:03d}x\nl{i:03d}\n")):
        app = "port: 1\n" + "".join(line.format(i=i) for i in range(30))
        proj, home = _proj(tmp_path / label, {".claude/openspec.yaml": PLUGIN_CONFIG,
                                              "config.yaml": app})
        for n in (12, 24, 30):  # 12: Varianten-Deckel; 24/30: Mengengrenze (> 20 Edits)
            start = time.monotonic()
            wrong += _check(f"Varianten-Explosion {label} n={n}",
                            _blowup_multi(proj / "config.yaml", n),
                            proj, home, 2, OVERRIDE_HINT)
            took = time.monotonic() - start
            if took >= 2.0:
                wrong.append(f"  {label} n={n}: {took:.1f} s (soll < 2 s)")
    # Deckel ohne Plugin-Block (19 Edits, unter der Mengengrenze): fail-closed
    # mit verstaendlichem Grund
    tool, tin = _blowup_multi(proj / "config.yaml", 24)
    proc = _gate(proj, home, tool, dict(tin, edits=tin["edits"][:19]))
    if proc.returncode != 2 or "mögliche Fassungen" not in proc.stderr \
            or "override" not in proc.stderr:
        wrong.append(f"  Deckel ohne Plugin-Block: rc={proc.returncode}, "
                     f"stderr={proc.stderr.strip()[:200]!r}")
    # Mit Override-Token frei (gleicher Ausweg wie jeder Config-Treffer)
    _token(proj)
    wrong += _check("Varianten-Explosion + Token", _blowup_multi(proj / "config.yaml", 24),
                    proj, home, 0)
    _fail("F001", wrong)


def _big_app_multi(target: Path, n_del: int = 60, k: int = 100) -> "tuple[str, dict]":
    """Adversary-Runde 2 (f3/f4): Loesch-Edits + viele replace_all-Durchlaeufe
    auf einer grossen App-config.yaml + Plugin-Block am Ende."""
    edits = [{"old_string": f"tk{i:03d}q", "new_string": ""} for i in range(n_del)]
    edits += [{"old_string": "a", "new_string": "a", "replace_all": True}] * k
    edits.append({"old_string": "port: 1", "new_string": "port: 1\nautonomy: 1"})
    return "MultiEdit", {"file_path": str(target), "edits": edits}


def test_app_config_size_and_edit_count_limits_fail_closed(tmp_path):
    """F001 Runde 2: grosse App-config (1-2 MB) / > 20 Edits / Write > 256 KiB
    werden nicht simuliert, sondern fail-closed geblockt (Exit 2 in < 2 s);
    20 harmlose Edits bleiben frei; Override-Token gibt frei."""
    import time
    wrong = []
    for size in (1_000_000, 2_000_000):
        app = "port: 1\n" + "".join(f"tk{i:03d}q\n" for i in range(60)) + "a" * size + "\n"
        proj, home = _proj(tmp_path / f"big{size}", {".claude/openspec.yaml": PLUGIN_CONFIG,
                                                     "config.yaml": app})
        start = time.monotonic()
        wrong += _check(f"f3/f4 {size} B, 161 Edits", _big_app_multi(proj / "config.yaml"),
                        proj, home, 2, "256 KiB")
        took = time.monotonic() - start
        if took >= 2.0:
            wrong.append(f"  f3/f4 {size} B: {took:.1f} s (soll < 2 s)")
        # auch ein einzelner harmloser Edit: Datei zu gross → nicht pruefbar
        wrong += _check(f"Edit auf {size} B", _edit(proj / "config.yaml", "port: 1", "port: 2"),
                        proj, home, 2, OVERRIDE_HINT)

    lines = "port: 1\n" + "".join(f"key{i:02d}: v\n" for i in range(25))
    proj, home = _proj(tmp_path / "count", {".claude/openspec.yaml": PLUGIN_CONFIG,
                                            "config.yaml": lines})
    target = proj / "config.yaml"
    pairs21 = [(f"key{i:02d}: v", f"key{i:02d}: w") for i in range(21)]
    wrong += _check("21 harmlose Edits (Mengengrenze)", _multi(target, *pairs21),
                    proj, home, 2, "mehr als 20 Edits")
    wrong += _check("20 harmlose Edits", _multi(target, *pairs21[:20]),
                    proj, home, 0, forbid=CONFIG_MSG)

    big_write = "port: 1\n" + "# x\n" * (70 * 1024)  # ~280 KiB, ohne Plugin-Block
    wrong += _check("Write > 256 KiB", _write(target, big_write), proj, home, 2, "256 KiB")
    wrong += _check("Write klein", _write(target, "port: 2\n"), proj, home, 0,
                    forbid=CONFIG_MSG)
    # Grenzen gelten nur fuer die App-config.yaml, nicht fuer beliebige Dateien
    wrong += _check("Write > 256 KiB andere Datei", _write(proj / "docs" / "big.md", big_write),
                    proj, home, 0, forbid=CONFIG_MSG)

    _token(proj)
    wrong += _check("21 Edits + Token", _multi(target, *pairs21), proj, home, 0)
    wrong += _check("Write > 256 KiB + Token", _write(target, big_write), proj, home, 0)
    _fail("F001 Runde 2", wrong)


def test_sim_deadline_fail_closed(tmp_path):
    """F001 Runde 2: abgelaufene Deadline → `_SpecSimTimeout` (Unterklasse von
    `_SpecSimError`, im Spec-Freeze Block) und im Config-Schritt ein Treffer."""
    proj, home = _proj(tmp_path, {".claude/openspec.yaml": PLUGIN_CONFIG,
                                  "config.yaml": APP_CONFIG})
    code = (
        "import sys, time; sys.path.insert(0, %r)\n"
        "import edit_gate as g\n"
        "assert issubclass(g._SpecSimTimeout, g._SpecSimError)\n"
        "try:\n"
        "    g._spec_edit_variants(['a b'], {'old_string': 'b', 'new_string': 'c'},\n"
        "                          time.monotonic() - 1)\n"
        "    print('NO-TIMEOUT')\n"
        "except g._SpecSimTimeout:\n"
        "    print('TIMEOUT')\n"
        "g._SIM_BUDGET_S = -1.0\n"
        "hit = g._config_edit_hit(%r, {'file_path': %r, 'old_string': 'port: 8080',\n"
        "                               'new_string': 'port: 9090'})\n"
        "print('HIT', hit)\n"
    ) % (str(HOOKS_DIR), str(proj / "config.yaml"), str(proj / "config.yaml"))
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env=_env(proj, home), cwd=str(proj), timeout=60)
    assert proc.returncode == 0, proc.stderr[-1500:]
    out = proc.stdout.splitlines()
    assert out[0] == "TIMEOUT", proc.stdout
    assert out[1].startswith("HIT Zeitbudget"), proc.stdout


def test_spec_edit_variants_capped_and_deduplicated(tmp_path):
    """F001 (#439-Pfad): `_spec_edit_variants` dedupliziert und wirft ueber dem
    Deckel `_SpecVariantOverflow` (Unterklasse von `_SpecSimError` → Spec-Freeze
    blockt fail-closed statt in den Timeout zu laufen)."""
    proj, home = _proj(tmp_path)
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import edit_gate as g\n"
        "assert issubclass(g._SpecVariantOverflow, g._SpecSimError)\n"
        "text = ''.join(f'tok{i:03d}x\\nline{i:03d}\\n' for i in range(40))\n"
        "v = [text]\n"
        "try:\n"
        "    for i in range(40):\n"
        "        v = g._spec_edit_variants(v, {'old_string': f'tok{i:03d}x', 'new_string': ''})\n"
        "        assert len(v) <= g._SPEC_VARIANT_CAP, len(v)\n"
        "        assert len(v) == len(set(v))\n"
        "    print('NO-OVERFLOW')\n"
        "except g._SpecVariantOverflow:\n"
        "    print('OVERFLOW', i)\n"
        "w = g._spec_edit_variants(['a b a'], {'old_string': 'b', 'new_string': 'c'})\n"
        "assert w == ['a c a'], w\n"
    ) % str(HOOKS_DIR)
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env=_env(proj, home), cwd=str(proj), timeout=60)
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert proc.stdout.startswith("OVERFLOW"), proc.stdout


# --------------------------------------------------------------------- #
# AC-6
# --------------------------------------------------------------------- #

def test_path_tricks_relative_dotdot_symlink_hardlink_blocked(tmp_path):
    """AC-6: relativ, '..', Symlink, Symlink-Ordner, Hardlink -> Exit 2."""
    proj, home = _proj(tmp_path / "a", {"openspec.yaml": PLUGIN_CONFIG})
    (proj / "link.yaml").symlink_to(proj / "openspec.yaml")
    os.link(proj / "openspec.yaml", proj / "hard.yaml")
    wrong = []
    for label, path in (
        ("relativ", "openspec.yaml"),
        ("dotdot", str(proj / "docs" / ".." / "openspec.yaml")),
        ("symlink", str(proj / "link.yaml")),
        ("hardlink", str(proj / "hard.yaml")),
    ):
        wrong += _check(label, _write(path, AUTONOMY_AUTO), proj, home, 2,
                        OVERRIDE_HINT)
    # relativer Pfad, cwd = Projekt, Edit
    wrong += _check("relativ Edit", _edit("openspec.yaml", "enabled: true",
                                          "enabled: false"),
                    proj, home, 2, OVERRIDE_HINT, cwd=proj)

    # Symlink-Ordner auf .claude, wirksame Datei dort
    proj2, home2 = _proj(tmp_path / "b", {".claude/openspec.yaml": PLUGIN_CONFIG})
    (proj2 / "cfgdir").symlink_to(proj2 / ".claude", target_is_directory=True)
    wrong += _check("symlink-ordner",
                    _write(proj2 / "cfgdir" / "openspec.yaml", AUTONOMY_AUTO),
                    proj2, home2, 2, OVERRIDE_HINT)
    _fail("AC-6", wrong)


# --------------------------------------------------------------------- #
# AC-7
# --------------------------------------------------------------------- #

def test_worktree_copy_free_main_repo_blocked(tmp_path):
    """AC-7: Worktree-Kopie frei, dieselbe Datei im Haupt-Ordner Exit 2."""
    main, wt = _worktree_sandbox(tmp_path / "wtmain", "openspec.yaml")
    home = (tmp_path / "home").resolve()
    (home / ".claude").mkdir(parents=True)
    wrong = []
    wrong += _check("Worktree-Kopie Write", _write(wt / "openspec.yaml", AUTONOMY_AUTO),
                    wt, home, 0, forbid=CONFIG_MSG, cwd=wt)
    wrong += _check("Worktree-Kopie Edit",
                    _edit(wt / "openspec.yaml", "enabled: true", "enabled: false"),
                    wt, home, 0, forbid=CONFIG_MSG, cwd=wt)
    wrong += _check("Haupt-Ordner Write", _write(main / "openspec.yaml", AUTONOMY_AUTO),
                    wt, home, 2, OVERRIDE_HINT, cwd=wt)
    wrong += _check("Haupt-Ordner Edit",
                    _edit(main / "openspec.yaml", "enabled: true", "enabled: false"),
                    wt, home, 2, OVERRIDE_HINT, cwd=wt)
    _fail("AC-7", wrong)


# --------------------------------------------------------------------- #
# AC-8
# --------------------------------------------------------------------- #

def test_outside_project_unchanged(tmp_path):
    """AC-8: Ziele ausserhalb des Projekts: Exit 0, keine Config-Meldung."""
    proj, home = _proj(tmp_path / "p", {"openspec.yaml": PLUGIN_CONFIG})
    outside = (tmp_path / "elsewhere")
    outside.mkdir()
    wrong = []
    for label, path in (("tmp-fremd", outside / "openspec.yaml"),
                        ("~/.claude", home / ".claude" / "openspec.yaml")):
        wrong += _check(label, _write(path, AUTONOMY_AUTO), proj, home, 0,
                        forbid=CONFIG_MSG)
    _fail("AC-8", wrong)


# --------------------------------------------------------------------- #
# AC-9
# --------------------------------------------------------------------- #

def test_override_token_allows_config_edit(tmp_path):
    """AC-9: gueltiger Token -> Exit 0 (Vorbedingung: ohne Token Exit 2)."""
    proj, home = _proj(tmp_path, {".claude/openspec.yaml": PLUGIN_CONFIG})
    calls = [
        _write(proj / ".claude" / "openspec.yaml", AUTONOMY_AUTO),
        _edit(proj / ".claude" / "openspec.yaml", "enabled: true", "enabled: false"),
        _write(proj / "openspec.yaml", AUTONOMY_AUTO),  # vorrangig anlegen
    ]
    wrong = []
    for call in calls:  # ohne Token blockt es (Vorbedingung)
        wrong += _check("ohne Token", call, proj, home, 2, OVERRIDE_HINT)
    _token(proj)
    for call in calls:
        wrong += _check("mit Token", call, proj, home, 0)
    _fail("AC-9", wrong)


# --------------------------------------------------------------------- #
# AC-10
# --------------------------------------------------------------------- #

def test_framework_disabled_still_protects_config(tmp_path):
    """AC-10: framework_disabled() hebt den Config-Schutz nicht auf."""
    disabled_cfg = "framework:\n  enabled: false\n"
    wrong = []
    # (a) Config-Weg: framework.enabled: false in der wirksamen Config
    proj, home = _proj(tmp_path / "a", {".claude/openspec.yaml": disabled_cfg,
                                        "docs/notes.txt": "n\n"})
    cfg = proj / ".claude" / "openspec.yaml"
    wrong += _check("cfg: Write Config", _write(cfg, AUTONOMY_AUTO), proj, home, 2,
                    OVERRIDE_HINT)
    wrong += _check("cfg: Edit Config",
                    _edit(cfg, "enabled: false", "enabled: true"), proj, home, 2,
                    OVERRIDE_HINT)
    wrong += _check("cfg: andere Datei", _write(proj / "docs" / "notes.txt", "m\n"),
                    proj, home, 0)
    _token(proj)
    wrong += _check("cfg: mit Token", _write(cfg, AUTONOMY_AUTO), proj, home, 0)
    # (b) Env-Weg: OPENSPEC_FRAMEWORK=off
    proj2, home2 = _proj(tmp_path / "b", {"openspec.yaml": PLUGIN_CONFIG})
    off = {"OPENSPEC_FRAMEWORK": "off"}
    wrong += _check("env: Write Config", _write(proj2 / "openspec.yaml", AUTONOMY_AUTO),
                    proj2, home2, 2, OVERRIDE_HINT, extra_env=off)
    wrong += _check("env: andere Datei", _write(proj2 / "docs" / "n.txt", "m\n"),
                    proj2, home2, 0, extra_env=off)
    _token(proj2)
    wrong += _check("env: mit Token", _write(proj2 / "openspec.yaml", AUTONOMY_AUTO),
                    proj2, home2, 0, extra_env=off)
    _fail("AC-10", wrong)


# --------------------------------------------------------------------- #
# AC-11
# --------------------------------------------------------------------- #

def test_bash_creating_higher_priority_config_blocked(tmp_path):
    """AC-11: bash_gate blockt das Anlegen einer vorrangigen Config, nachrangige frei."""
    wrong = []
    # wirksam: .claude/openspec.yaml -> openspec.yaml ist vorrangig
    a = _sandbox_ohne_workflow(tmp_path / "a")
    (a / ".claude" / "openspec.yaml").write_text(PLUGIN_CONFIG)
    wrong += _expect(["echo x > openspec.yaml", "echo x > .claude/openspec.yaml"],
                     a, 2, OVERRIDE_HINT)
    wrong += _expect(["echo x > .openspec.yaml"], a, 0)  # nachrangig, wirkungslos
    # keine wirksame Config -> jeder Kandidat blockt
    b = _sandbox_ohne_workflow(tmp_path / "b")
    wrong += _expect(["echo x > .claude/openspec.yaml", "echo x > openspec.yaml",
                      "echo x > .claude/config.yaml"], b, 2, OVERRIDE_HINT)
    # wirksam: openspec.yaml -> .openspec.yaml nachrangig
    c = _sandbox_ohne_workflow(tmp_path / "c")
    (c / "openspec.yaml").write_text(PLUGIN_CONFIG)
    wrong += _expect(["echo x > .openspec.yaml"], c, 0)
    _fail("AC-11", wrong)


def test_bash_moving_or_removing_config_dir_blocked(tmp_path):
    """F002: `mv`/`rm -rf`/`git rm` auf einen Ordner, der die wirksame Config
    enthaelt, macht sie unwirksam -> Exit 2. Ordner ohne geschuetzte Datei,
    Verschieben IN den Ordner und die Projektwurzel selbst bleiben frei."""
    wrong = []
    a = _sandbox_ohne_workflow(tmp_path / "a")
    (a / ".claude" / "openspec.yaml").write_text(PLUGIN_CONFIG)
    (a / "sub").mkdir()
    (a / "other").mkdir()
    (a / ".claude" / "cache").mkdir()
    wrong += _expect([
        "mv .claude .claude_off", "rm -rf .claude", "rm -rf .claude/",
        "rm -r ./.claude", "mv -t /tmp .claude", "cd sub && rm -rf ../.claude",
        f"rm -rf {a}/.claude", "git rm -r .claude", "git mv .claude x",
    ], a, 2, OVERRIDE_HINT)
    wrong += _expect([
        "rm -rf other", "mv other other2", "rm -rf .claude/cache",
        "mv sub .claude", "touch .claude", "rm -rf /tmp/nonexistent-473/.claude",
    ], a, 0)
    # Wirksame Config im Root: `.claude` enthaelt keine geschuetzte Datei -> frei
    b = _sandbox_ohne_workflow(tmp_path / "b")
    (b / "openspec.yaml").write_text(PLUGIN_CONFIG)
    wrong += _expect(["rm -rf .claude", "mv .claude .claude_off"], b, 0)
    _fail("F002", wrong)


# --------------------------------------------------------------------- #
# AC-12 / AC-16 (Regressionslaeufe)
# --------------------------------------------------------------------- #

def _pytest(*args) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in _SCRUBBED and not k.startswith("OPENSPEC_")}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=900,
    )


def test_existing_bash_config_lock_suites_still_green():
    """AC-12: #418- und #410-Suiten bleiben gruen."""
    proc = _pytest("tests/test_bash_gate_config_lock_418.py",
                   "tests/test_bash_gate_state_integrity_410.py")
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-500:]


# --------------------------------------------------------------------- #
# AC-13
# --------------------------------------------------------------------- #

def test_settings_local_json_stays_free(tmp_path):
    """AC-13: settings.local.json ist kein Config-Kandidat (kein Treffer des Config-Schritts)."""
    proj, home = _proj(tmp_path, {"openspec.yaml": PLUGIN_CONFIG})
    target = proj / ".claude" / "settings.local.json"
    # 1) Helfer: settings.local.json nie in der Pfadmenge
    paths = [Path(p) for p in _pcp(proj, "{}")]
    assert target not in paths, f"settings.local.json in protected_config_paths: {paths}"
    # 2) Gate: nie die Config-Meldung (Orchestrator-Schritt 1b blockt ohne Token weiter)
    wrong = []
    for call in (_write(target, "{}"), _edit(target, "a", "b")):
        proc = _gate(proj, home, *call)
        if CONFIG_MSG in proc.stderr:
            wrong.append(f"  {call[0]}: Config-Meldung ohne Treffer: {proc.stderr[:160]!r}")
    # mit Token: Exit 0 durch alle Schritte
    _token(proj)
    wrong += _check("mit Token", _write(target, "{}"), proj, home, 0, forbid=CONFIG_MSG)
    _fail("AC-13", wrong)


# --------------------------------------------------------------------- #
# AC-14
# --------------------------------------------------------------------- #

_WRAPPER = '''\
import runpy, sys
sys.path.insert(0, {hooks!r})
import config_loader
def boom(*a, **k):
    raise RuntimeError("boom (Test #473)")
for name in ("find_config_file", "_find_config_file", "protected_config_paths"):
    setattr(config_loader, name, boom)
sys.argv = [{gate!r}]
runpy.run_path({gate!r}, run_name="__main__")
'''


def test_path_resolution_error_fails_open(tmp_path):
    """AC-14: wirft die Pfadermittlung, ueberspringt das Gate den Config-Schritt."""
    proj, home = _proj(tmp_path, {"openspec.yaml": PLUGIN_CONFIG,
                                  "docs/notes.txt": "n\n"})
    wrapper = tmp_path / "wrap_gate.py"
    wrapper.write_text(_WRAPPER.format(hooks=str(HOOKS_DIR), gate=str(EDIT_GATE)))
    wrong = []
    for label, call in (
        ("beliebige Datei", _write(proj / "docs" / "notes.txt", "m\n")),
        ("Config-Datei (kein Totalblock)", _write(proj / "openspec.yaml", "a: 1\n")),
    ):
        wrong += _check(label, call, proj, home, 0, forbid="boom", script=wrapper)
    # Helfer selbst wirft nie (kaputte Eingaben -> leere Liste)
    for bad_root in (None, 12345, tmp_path / "gibt-es-nicht" / "x"):
        try:
            res = _pcp(bad_root, "x")
        except pytest.fail.Exception:
            raise
        except Exception as exc:
            wrong.append(f"  protected_config_paths({bad_root!r}) wirft {exc!r}")
        else:
            if not isinstance(res, list):
                wrong.append(f"  protected_config_paths({bad_root!r}) -> {res!r}")
    _fail("AC-14", wrong)


# --------------------------------------------------------------------- #
# AC-15
# --------------------------------------------------------------------- #

def test_protected_config_paths_set(tmp_path):
    """AC-15: protected_config_paths liefert genau die beschriebene Menge in Suchreihenfolge."""
    wrong = []

    def check(label, root, expected, new_content=None, as_set=False):
        got = [Path(p) for p in _pcp(root, new_content)]
        exp = [root / e for e in expected]
        if (set(got) != set(exp)) if as_set else (got != exp):
            wrong.append(f"  {label}: {[str(g.relative_to(root)) for g in got]} "
                         f"!= {expected}")

    # (a) keine wirksame Config: alle Kandidaten, Root-config.yaml nur mit Plugin-Inhalt
    none = _proj(tmp_path / "a")[0]
    five = ["openspec.yaml", ".claude/openspec.yaml", ".claude/config.yaml",
            ".openspec.yaml", ".claude/.openspec.yaml"]
    six = ["openspec.yaml", ".claude/openspec.yaml", "config.yaml",
           ".claude/config.yaml", ".openspec.yaml", ".claude/.openspec.yaml"]
    check("a: None", none, five)
    check("a: App-Inhalt", none, five, APP_CONFIG)
    check("a: Plugin-Inhalt", none, six, AUTONOMY_AUTO)
    # (b) wirksame .claude/openspec.yaml: davor openspec.yaml, danach nichts
    b = _proj(tmp_path / "b", {".claude/openspec.yaml": PLUGIN_CONFIG})[0]
    check("b", b, ["openspec.yaml", ".claude/openspec.yaml"])
    # (c) wirksame openspec.yaml im Root: nur sie selbst
    c = _proj(tmp_path / "c", {"openspec.yaml": PLUGIN_CONFIG})[0]
    check("c", c, ["openspec.yaml"])
    # (d) Root-config.yaml mit Plugin-Block ist wirksam: davor-Kandidaten + sie
    d = _proj(tmp_path / "d", {"config.yaml": PLUGIN_CONFIG})[0]
    check("d", d, ["openspec.yaml", ".claude/openspec.yaml", "config.yaml"])
    # (e) App-config.yaml neben wirksamer .claude/openspec.yaml (#372)
    e = _proj(tmp_path / "e", {".claude/openspec.yaml": PLUGIN_CONFIG,
                               "config.yaml": APP_CONFIG})[0]
    base = ["openspec.yaml", ".claude/openspec.yaml"]
    check("e: None", e, base)
    check("e: App-Inhalt", e, base, APP_CONFIG)
    # Plugin-Inhalt macht die App-Config schutzwuerdig (AC-5), Reihenfolge offen
    check("e: Plugin-Inhalt", e, base + ["config.yaml"], AUTONOMY_AUTO, as_set=True)
    # (f) nachrangige Kandidaten fehlen: wirksame .openspec.yaml ... nur Vorrangige
    f = _proj(tmp_path / "f", {".openspec.yaml": PLUGIN_CONFIG})[0]
    check("f", f, ["openspec.yaml", ".claude/openspec.yaml", ".claude/config.yaml",
                   ".openspec.yaml"])
    _fail("AC-15", wrong)


def test_existing_edit_gate_suites_still_green():
    """AC-16: bestehende edit_gate-Tests bleiben gruen (Gesamtlauf: pytest tests/)."""
    proc = _pytest("tests/", "-k", "edit_gate",
                   "--ignore=tests/test_config_edit_schutz_473.py")
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-500:]
