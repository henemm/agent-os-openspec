"""Tests fuer #333: Workflow-Typ `bug` und `/00-bug` entfernen.

Spec: docs/specs/feat-333-bug-typ-entfernen.md (AC-1 bis AC-5, AC-7, AC-8, AC-10).
Subprozess-Tests hermetisch (cwd/CLAUDE_PROJECT_DIR/HOME = tmp_path), Muster
test_workflow_finish_alias.py und test_session_banner.py.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import alias_sync  # noqa: E402


# --- Helpers ---------------------------------------------------------------

def _run_workflow(tmp_path: Path, args: list, wf_name: str = "legacy-bug"):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = wf_name
    env["HOME"] = str(tmp_path / "home")
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py")] + args,
        capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )


def _legacy_bug_state(name: str, phase: str = "phase8_complete") -> dict:
    return {
        "name": name,
        "workflow_type": "bug",
        "current_phase": phase,
        "context_file": "docs/context/x.md",
        "affected_files": [],
        "test_artifacts": [],
        "adversary_verdict": None,
    }


def _function_body(source: str, func_name: str) -> str:
    """Quelltext einer Top-Level-Funktion (bis zur naechsten Top-Level-Zeile)."""
    m = re.search(rf"^def {func_name}\(.*?(?=^\S)", source, re.S | re.M)
    return m.group(0) if m else ""


# --- AC-1 -------------------------------------------------------------------

def test_hooks_know_no_bug_type():
    """AC-1: Kein Hook vergleicht mehr gegen den Workflow-Typ "bug".

    Einzige Ausnahme: cmd_start in workflow.py darf "bug" erkennen, um es mit
    eigener Meldung abzulehnen (AC-2) — das ist kein Typ-Vergleich fuer
    Gate-Verhalten.
    """
    offenders = []
    for name in ("workflow.py", "edit_gate.py", "bash_gate.py", "adversary_dialog.py"):
        source = (HOOKS_DIR / name).read_text()
        if name == "workflow.py":
            body = _function_body(source, "cmd_start")
            assert body, "cmd_start nicht gefunden"
            source = source.replace(body, "")
        for lineno, line in enumerate(source.splitlines(), 1):
            if '"bug"' in line:
                offenders.append(f"{name}:{lineno}: {line.strip()}")
    assert not offenders, "Typ 'bug' noch im Hook-Quelltext:\n" + "\n".join(offenders)

    import adversary_dialog
    assert adversary_dialog._FAST_TRACK_TYPES == ("feature-fast",)


# --- AC-2 -------------------------------------------------------------------

def test_start_type_bug_is_rejected_with_pointer(tmp_path):
    """AC-2: start --type bug endet mit Exit 1 und eigener Meldung."""
    result = _run_workflow(tmp_path, ["start", "x", "--type", "bug"], wf_name="x")
    out = result.stdout + result.stderr
    assert result.returncode == 1, out
    assert "/00-intake" in out, out
    assert "feature-fast" in out, out
    assert "Unknown workflow type" not in out, out
    assert not (tmp_path / ".claude" / "workflows" / "x.json").exists()


# --- AC-3 -------------------------------------------------------------------

def test_legacy_bug_workflow_json_does_not_crash(tmp_path):
    """AC-3: Altbestand mit Typ bug laeuft durch status/switch/finish/retro
    ohne Traceback und wird wie `feature` behandelt (volle Gates)."""
    name = "legacy-bug"
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    # Laufender Alt-Workflow vor dem Abschluss: in phase8_complete wuerde
    # _validate_transition fuer JEDEN Typ nichts pruefen (Ziel == aktuelle Phase).
    (wf_dir / f"{name}.json").write_text(
        json.dumps(_legacy_bug_state(name, phase="phase7_validate"))
    )
    log_dir = wf_dir / "_log"
    log_dir.mkdir()
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    (log_dir / f"{ts}_{name}.yaml").write_text("outcome: success\n")
    # Archivierter Alt-Workflow fuer Retro
    archive = wf_dir / "_archive"
    archive.mkdir()
    (archive / "old-bug.json").write_text(json.dumps(_legacy_bug_state("old-bug")))

    for args in (["status"], ["switch", name], ["status"]):
        r = _run_workflow(tmp_path, args, wf_name=name)
        assert "Traceback" not in r.stderr, (args, r.stderr)
        assert r.returncode == 0, (args, r.stdout, r.stderr)

    r = _run_workflow(tmp_path, ["retro", "old-bug"], wf_name=name)
    assert "Traceback" not in r.stderr, r.stderr
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "fast-track" not in r.stdout, (
        "Retro behandelt Typ 'bug' noch als Fast-Track:\n" + r.stdout
    )

    r = _run_workflow(tmp_path, ["finish"], wf_name=name)
    assert "Traceback" not in r.stderr, r.stderr
    # Wie `feature`: ohne Spec-Freigabe/Verdict darf finish nicht archivieren.
    assert r.returncode != 0, (
        "finish hat den bug-Workflow ohne Vorbedingungen archiviert:\n"
        + r.stdout + r.stderr
    )
    assert "BLOCKED" in r.stderr, r.stderr
    assert not (archive / f"{name}.json").exists()
    assert (wf_dir / f"{name}.json").exists()


# --- AC-4 -------------------------------------------------------------------

def test_edit_gate_reads_fast_track_with_bug_fix_fallback():
    """AC-4: edit_gate liest fast_track.require_tdd, Rueckfall bug_fix.require_tdd."""
    source = (HOOKS_DIR / "edit_gate.py").read_text()
    idx = source.find("require_tdd")
    assert idx != -1, "require_tdd-Ermittlung fehlt in edit_gate.py"
    # Block um die require_tdd-Ermittlung
    block = source[max(0, idx - 600): idx + 600]
    assert '"fast_track"' in block, "edit_gate liest fast_track.require_tdd nicht"
    assert '"bug_fix"' in block, "Rueckfall auf bug_fix.require_tdd fehlt"
    assert block.index('"fast_track"') < block.index('"bug_fix"'), (
        "fast_track muss Vorrang vor dem bug_fix-Rueckfall haben"
    )


# --- AC-5 -------------------------------------------------------------------

def test_config_has_fast_track_and_no_bug_fix_max_files():
    """AC-5: config.yaml kennt fast_track.require_tdd, kein bug_fix, kein max_files."""
    text = (REPO_ROOT / "config.yaml").read_text()
    cfg = yaml.safe_load(text)
    assert "require_tdd" in (cfg.get("fast_track") or {}), "fast_track.require_tdd fehlt"
    assert "bug_fix" not in cfg, "Abschnitt bug_fix existiert noch"
    assert "max_files" not in text, "max_files steht noch in config.yaml"


# --- AC-7 -------------------------------------------------------------------

def _marked_alias(name: str) -> str:
    return f"{alias_sync.ALIAS_MARKER}\n# {name}\n\nAlter Alias.\n"


def test_find_removed_aliases_only_marked_listed_names(tmp_path):
    """AC-7: nur markierte Aliase gelisteter Namen werden gemeldet."""
    assert "00-bug" in alias_sync.REMOVED_SKILLS

    marked_dir = tmp_path / "a"
    marked_dir.mkdir()
    (marked_dir / "00-bug.md").write_text(_marked_alias("00-bug"))
    (marked_dir / "foo.md").write_text(_marked_alias("foo"))
    found = alias_sync.find_removed_aliases(marked_dir)
    assert [Path(p).name for p in found] == ["00-bug.md"]

    unmarked_dir = tmp_path / "b"
    unmarked_dir.mkdir()
    (unmarked_dir / "00-bug.md").write_text("# Eigener Befehl des Nutzers\n")
    assert list(alias_sync.find_removed_aliases(unmarked_dir)) == []

    assert list(alias_sync.find_removed_aliases(tmp_path / "fehlt")) == []


def _run_refresh(tmp_path: Path, project: Path):
    env = dict(os.environ)
    env["HOME"] = str(tmp_path / "home")
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "setup.py"), str(project), "--refresh-aliases"],
        capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )


def test_refresh_aliases_deletes_only_removed_marked_alias(tmp_path):
    """AC-7: --refresh-aliases loescht genau den markierten 00-bug-Alias."""
    (tmp_path / "home").mkdir()
    proj_a = tmp_path / "proj_a"
    cmds_a = proj_a / ".claude" / "commands"
    cmds_a.mkdir(parents=True)
    (cmds_a / "00-bug.md").write_text(_marked_alias("00-bug"))
    (cmds_a / "foo.md").write_text(_marked_alias("foo"))

    proj_b = tmp_path / "proj_b"
    cmds_b = proj_b / ".claude" / "commands"
    cmds_b.mkdir(parents=True)
    own = "# Eigener Befehl des Nutzers\n"
    (cmds_b / "00-bug.md").write_text(own)

    r = _run_refresh(tmp_path, proj_a)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (cmds_a / "00-bug.md").exists(), r.stdout
    assert (cmds_a / "foo.md").exists()
    assert "00-bug" in r.stdout, r.stdout

    r = _run_refresh(tmp_path, proj_b)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (cmds_b / "00-bug.md").read_text() == own


def test_banner_warns_about_removed_aliases(tmp_path):
    """AC-7: Banner meldet markierten 00-bug-Alias und nennt --refresh-aliases."""
    plugin = tmp_path / "plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "agent-os-openspec", "version": "9.9.9"})
    )
    (plugin / "skills").mkdir()
    home = tmp_path / "home"
    (home / ".claude" / "commands").mkdir(parents=True)
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    (project / ".claude" / "commands").mkdir(parents=True)
    (project / ".claude" / "commands" / "00-bug.md").write_text(_marked_alias("00-bug"))

    env = {k: v for k, v in os.environ.items()
           if k not in ("OPENSPEC_FRAMEWORK", "CLAUDE_PLUGIN_ROOT")}
    env.update({
        "HOME": str(home),
        "CLAUDE_PLUGIN_ROOT": str(plugin),
        "CLAUDE_PROJECT_DIR": str(project),
    })
    r = subprocess.run([sys.executable, str(HOOKS_DIR / "session_banner.py")],
                       input="", capture_output=True, text=True, env=env,
                       cwd=str(project))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip(), r.stderr
    msg = json.loads(r.stdout)["systemMessage"]
    warn = [line for line in msg.splitlines() if "00-bug" in line]
    assert warn, msg
    assert any("--refresh-aliases" in line for line in warn), msg


# --- AC-8 -------------------------------------------------------------------

def test_docs_have_no_bug_fast_track_left():
    """AC-8: Doku und setup.py kennen keinen Bug-Schnellweg mehr."""
    forbidden = ("--type bug", "bug_fix.require_tdd", "bug_fix.max_files",
                 "bug / feature-fast / feature", "/00-bug")
    hits = []
    for rel in ("README.md", "CLAUDE.md", "docs/WORKFLOW_GUIDE.md", "setup.py"):
        text = (REPO_ROOT / rel).read_text()
        for needle in forbidden:
            if needle in text:
                hits.append(f"{rel}: {needle!r}")
    guide = (REPO_ROOT / "docs" / "WORKFLOW_GUIDE.md").read_text()
    if re.search(r"^#+ .*Bug-Fix \(`--type bug`\)", guide, re.M):
        hits.append("docs/WORKFLOW_GUIDE.md: Abschnitt 'Bug-Fix (`--type bug`)'")
    readme = (REPO_ROOT / "README.md").read_text()
    if 'workflow.py start "bug-' in readme:
        hits.append("README.md: Bug-Beispiel beginnt mit workflow.py start")
    assert not hits, "\n".join(hits)


# --- AC-10 ------------------------------------------------------------------

def test_changelog_replaces_a1_sentence():
    """AC-10: Der CHANGELOG-Abschnitt mit dem Eintrag zur Entfernung beschreibt
    sie samt Rezept und Rueckfall (release-stabil: nicht an [Unreleased] gebunden)."""
    text = (REPO_ROOT / "CHANGELOG.md").read_text()
    marker = text.index("Workflow-Typ `bug` und `/00-bug` entfernt")
    start = text.rfind("\n## [", 0, marker) + 1
    nxt = text.find("\n## [", marker)
    section = text[start: nxt if nxt != -1 else len(text)]
    assert "set-field workflow_type feature-fast" in section
    assert "fast_track.require_tdd" in section
    assert "bis A2 weiter" not in section
