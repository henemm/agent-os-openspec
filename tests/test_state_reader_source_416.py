"""Prüfung an der Quelle: Workflow-State nur aus echter eigener Datei — #416.

Spec: docs/specs/fix-416-state-reader-source-check.md

Befund: Jeder Leser von `.claude/workflows/<wf>.json` glaubt heute dem Inhalt,
egal ob die Datei ein harter Verweis (zweiter Name, `st_nlink == 2`), ein
Symlink auf eine fremde Datei ist, oder ob ein Ordner der Kette (`.claude`,
`.claude/workflows`) ein Symlink ist. Ein gefälschtes
`adversary_verdict: VERIFIED` öffnet so jedes Gate.

Teil A (hier): der sichere Leser `hook_utils.read_state_json` und
`UnsafeStateError` (AC-1 bis AC-8), die `workflow.py`-CLI samt
`read_active_workflow_fast` (AC-12), `session_singleton_guard` (AC-14) und die
Nachführung der #410-Spec (AC-17).

Teil B (unten, separat ergänzt): die Hook-Leser als echte Subprozesse.

Import-Strategie: `read_state_json`/`UnsafeStateError` existieren vor der
Implementierung nicht. Sie werden per getattr geholt, damit jeder Test einzeln
RED wird statt eines Sammelfehlers bei der Collection.
"""

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

import hook_utils  # noqa: E402

WF = "sandboxwf"
FAKE_STATE = {
    "name": WF,
    "current_phase": "phase7_validate",
    "adversary_verdict": "VERIFIED",
    "workflow_type": "feature",
}
RICHTUNGEN = ["hard", "symlink_file", "symlink_dir", "claude_symlink"]


def _read_state_json():
    return getattr(hook_utils, "read_state_json", None)


def _unsafe_error():
    return getattr(hook_utils, "UnsafeStateError", None)


def _require_api():
    fn, err = _read_state_json(), _unsafe_error()
    assert fn is not None, "hook_utils.read_state_json fehlt"
    assert err is not None, "hook_utils.UnsafeStateError fehlt"
    return fn, err


# --------------------------------------------------------------------- #
# Sandbox (Muster aus tests/test_bash_gate_state_integrity_410.py)
# --------------------------------------------------------------------- #

def _sandbox(tmp_path: Path, state: "dict | None" = None) -> Path:
    """Wegwerf-Projekt (Haupt-Repo, kein Worktree) mit aktivem Workflow WF.

    Die State-Datei ist zunächst eine normale eigene Datei
    (S_ISREG, st_nlink == 1). `_mache_unsicher` ersetzt sie danach.
    """
    root = tmp_path.resolve()
    (root / ".git").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    claude = root / ".claude"
    (claude / "workflows").mkdir(parents=True)
    (claude / "workflows" / f"{WF}.json").write_text(
        json.dumps(state if state is not None else FAKE_STATE))
    (claude / "active_workflow").write_text(WF + "\n")
    return root


def _state_path(root: Path) -> Path:
    return root / ".claude" / "workflows" / f"{WF}.json"


def _mache_unsicher(root: Path, richtung: str) -> Path:
    """Macht den State von WF in `root` unsicher; liefert die Zieldatei.

    Die Zieldatei ist die Datei mit dem echten Inhalt hinter dem Verweis —
    Tests prüfen an ihr, dass nichts zurückgeschrieben/kopiert wird.

    Richtungen (wiederverwendbar für Teil B):
      - "hard":           zweiter Name docs/zweitname.json per os.link,
                          State-Datei hat danach st_nlink == 2.
      - "symlink_file":   echte Datei nach docs/state_real.json verschoben,
                          an der State-Stelle ein Symlink darauf.
      - "symlink_dir":    Ordner .claude/workflows nach docs/workflows_real
                          verschoben, .claude/workflows ist ein Symlink darauf.
      - "claude_symlink": Ordner .claude nach docs/claude_real verschoben,
                          .claude selbst ist ein Symlink darauf.
    Der Pfad `root/.claude/workflows/<WF>.json` bleibt in allen Fällen lesbar.
    """
    state = _state_path(root)
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    if richtung == "hard":
        target = docs / "zweitname.json"
        os.link(state, target)
        assert os.stat(state).st_nlink == 2
        return target
    if richtung == "symlink_file":
        target = docs / "state_real.json"
        shutil.move(str(state), str(target))
        os.symlink(target, state)
        return target
    if richtung == "symlink_dir":
        real_dir = docs / "workflows_real"
        shutil.move(str(root / ".claude" / "workflows"), str(real_dir))
        os.symlink(real_dir, root / ".claude" / "workflows")
        return real_dir / f"{WF}.json"
    if richtung == "claude_symlink":
        real_claude = docs / "claude_real"
        shutil.move(str(root / ".claude"), str(real_claude))
        os.symlink(real_claude, root / ".claude")
        return real_claude / "workflows" / f"{WF}.json"
    raise ValueError(f"unbekannte Richtung: {richtung}")


def _run_workflow(root: Path, args: list):
    """workflow.py dieses Arbeitsbaums als Subprozess (Muster #82)."""
    env = dict(os.environ)
    env.pop("OPENSPEC_FRAMEWORK", None)
    env["CLAUDE_PROJECT_DIR"] = str(root)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py")] + args,
        capture_output=True, text=True, env=env, cwd=str(root), timeout=60,
    )


def _in_sandbox(monkeypatch, root: Path) -> None:
    """In-Process-Import mit Sandbox als Projektwurzel (find_project_root)."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
    monkeypatch.delenv("OPENSPEC_FRAMEWORK", raising=False)
    monkeypatch.chdir(root)


# --------------------------------------------------------------------- #
# AC-1 bis AC-4: read_state_json lehnt jede Richtung ab
# --------------------------------------------------------------------- #

def test_read_state_json_hartlink_wird_abgelehnt(tmp_path):
    fn, err = _require_api()
    root = _sandbox(tmp_path)
    _mache_unsicher(root, "hard")
    with pytest.raises(err) as exc:
        fn(_state_path(root), root)
    msg = str(exc.value)
    assert f"{WF}.json" in msg, msg
    assert "2" in msg, f"Linkzahl fehlt: {msg}"
    assert "hart" in msg.lower() or "link" in msg.lower(), msg


def test_read_state_json_symlink_auf_datei_wird_abgelehnt(tmp_path):
    fn, err = _require_api()
    root = _sandbox(tmp_path)
    _mache_unsicher(root, "symlink_file")
    with pytest.raises(err) as exc:
        fn(_state_path(root), root)
    msg = str(exc.value)
    assert f"{WF}.json" in msg, msg
    assert "symbol" in msg.lower() or "verweis" in msg.lower(), msg


def test_read_state_json_symlink_auf_ordner_wird_abgelehnt(tmp_path):
    fn, err = _require_api()
    root = _sandbox(tmp_path)
    _mache_unsicher(root, "symlink_dir")
    with pytest.raises(err) as exc:
        fn(_state_path(root), root)
    msg = str(exc.value)
    assert "workflows" in msg or f"{WF}.json" in msg, msg


def test_read_state_json_claude_als_symlink_wird_abgelehnt(tmp_path):
    fn, err = _require_api()
    root = _sandbox(tmp_path)
    _mache_unsicher(root, "claude_symlink")
    with pytest.raises(err) as exc:
        fn(_state_path(root), root)
    msg = str(exc.value)
    assert ".claude" in msg or f"{WF}.json" in msg, msg


# --------------------------------------------------------------------- #
# AC-5, AC-6: Normalfall ohne Fehlalarm
# --------------------------------------------------------------------- #

def test_normalfall_fehlende_datei_und_kaputtes_json_wie_heute(tmp_path):
    fn, err = _require_api()
    root = _sandbox(tmp_path)
    path = _state_path(root)

    assert fn(path, root) == json.loads(path.read_text())

    fehlt = root / ".claude" / "workflows" / "gibtsnicht.json"
    with pytest.raises(FileNotFoundError):
        fn(fehlt, root)

    kaputt = root / ".claude" / "workflows" / "kaputt.json"
    kaputt.write_text("{nicht json")
    with pytest.raises(json.JSONDecodeError):
        fn(kaputt, root)
    # kein UnsafeStateError in keinem der Fälle: oben jeweils exakt erwartet,
    # zusätzlich sicherstellen, dass JSONDecodeError nicht von err abgeleitet ist
    assert not issubclass(json.JSONDecodeError, err)
    assert not issubclass(FileNotFoundError, err)


def test_wurzel_hinter_symlink_kein_fehlalarm(tmp_path):
    fn, _err = _require_api()
    real_proj = tmp_path / "real" / "proj"
    claude = real_proj / ".claude" / "workflows"
    claude.mkdir(parents=True)
    (real_proj / ".git").mkdir()
    (claude / f"{WF}.json").write_text(json.dumps(FAKE_STATE))
    link = tmp_path / "link"
    os.symlink(tmp_path / "real", link)

    root = link / "proj"  # bewusst NICHT aufgelöst
    path = root / ".claude" / "workflows" / f"{WF}.json"
    assert fn(path, root) == FAKE_STATE


# --------------------------------------------------------------------- #
# AC-7, AC-8: Fehlerklasse und Meldung
# --------------------------------------------------------------------- #

def test_unsafe_state_error_erbt_nicht_von_oserror_valueerror():
    err = _unsafe_error()
    assert err is not None, "hook_utils.UnsafeStateError fehlt"
    assert issubclass(err, Exception)
    assert not issubclass(err, OSError)
    assert not issubclass(err, ValueError)


@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_meldung_nennt_pfad_grund_bereinigung_und_repariert_nicht(
        tmp_path, richtung):
    fn, err = _require_api()
    root = _sandbox(tmp_path)
    target = _mache_unsicher(root, richtung)
    vorher_bytes = target.read_bytes()
    wf_dir = target.parent
    vorher_dateien = sorted(p.name for p in wf_dir.iterdir())
    vorher_docs = sorted(str(p) for p in (root / "docs").rglob("*"))

    with pytest.raises(err) as exc:
        fn(_state_path(root), root)
    msg = str(exc.value)
    low = msg.lower()

    fehler = []
    if not (f"{WF}.json" in msg or ".claude" in msg):
        fehler.append("Pfad fehlt")
    if not any(w in low for w in ("verweis", "symbol", "hart", "link")):
        fehler.append("Grund fehlt")
    if "workflow" not in low or not any(
            w in low for w in ("entfernen", "neu starten", "frisch")):
        fehler.append("Bereinigungsweg fehlt")
    if target.read_bytes() != vorher_bytes:
        fehler.append("Zieldatei verändert")
    if sorted(p.name for p in wf_dir.iterdir()) != vorher_dateien:
        fehler.append("neue Datei im Ordner")
    if sorted(str(p) for p in (root / "docs").rglob("*")) != vorher_docs:
        fehler.append("neue Datei unter docs/")
    assert not fehler, f"{richtung}: {fehler} — Meldung: {msg}"


# --------------------------------------------------------------------- #
# AC-12: workflow.py-CLI und read_active_workflow_fast
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_workflow_cli_exit_1_mit_meldung(tmp_path, monkeypatch, richtung):
    root = _sandbox(tmp_path)
    _mache_unsicher(root, richtung)

    fehler = []
    for args in (["status"], ["list"]):
        r = _run_workflow(root, args)
        out = (r.stdout + r.stderr)
        if r.returncode != 1:
            fehler.append(f"{args}: rc={r.returncode} (erwartet 1)")
        if "verweis" not in out.lower():
            fehler.append(f"{args}: kein Hinweis auf Verweis")
        if "Traceback" in r.stderr:
            fehler.append(f"{args}: Traceback statt Meldung")

    _in_sandbox(monkeypatch, root)
    workflow = importlib.import_module("workflow")
    err = _unsafe_error()
    try:
        found = workflow.read_active_workflow_fast()
    except Exception as exc:  # noqa: BLE001
        if err is None or not isinstance(exc, err):
            fehler.append(f"read_active_workflow_fast: {type(exc).__name__}")
    else:
        if found is not None and found[1].get("adversary_verdict") == "VERIFIED":
            fehler.append("read_active_workflow_fast liefert gefälschtes VERIFIED")

    assert not fehler, f"{richtung}: {fehler}"


# --------------------------------------------------------------------- #
# AC-14: session_singleton_guard liefert None
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_session_singleton_guard_liefert_none(tmp_path, monkeypatch, richtung):
    root = _sandbox(tmp_path)
    _mache_unsicher(root, richtung)
    _in_sandbox(monkeypatch, root)
    guard = importlib.import_module("session_singleton_guard")
    assert guard._read_workflow_phase(WF) is None


# --------------------------------------------------------------------- #
# AC-17: F004 in der #410-Spec verweist auf #416 und gilt als aufgelöst
# --------------------------------------------------------------------- #

def test_f004_in_fix_410_spec_verweist_auf_416():
    spec = REPO_ROOT / "docs" / "specs" / "fix-410-state-integrity-gaps.md"
    zeilen = [z for z in spec.read_text().splitlines() if "F004" in z]
    assert zeilen, "F004 nicht in der #410-Spec gefunden"
    treffer = [z for z in zeilen
               if ("#416" in z or "fix-416" in z) and "gelöst" in z]
    assert treffer, (
        "F004 verweist nicht auf #416 als aufgelöst: " + " | ".join(zeilen))


# --- Teil B: Hook-Leser (AC-9 bis AC-11, AC-13, AC-15, AC-16) ---

def _hook_env(root: Path) -> dict:
    env = dict(os.environ)
    env.pop("OPENSPEC_FRAMEWORK", None)
    env["CLAUDE_PROJECT_DIR"] = str(root)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    return env


def _run_hook(script: str, root: Path, payload: dict) -> subprocess.CompletedProcess:
    """Hook dieses Arbeitsbaums als Subprozess, so wie Claude Code ihn startet."""
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / script)],
        input=json.dumps(payload), capture_output=True, text=True,
        env=_hook_env(root), cwd=str(root), timeout=60,
    )


def _edit_payload(file_path) -> dict:
    return {"tool_name": "Edit", "tool_input": {
        "file_path": str(file_path), "old_string": "a", "new_string": "b"}}


def _out(r: subprocess.CompletedProcess, root: Path) -> str:
    """stdout+stderr, Sandbox-Pfad neutralisiert (kein Zufallstreffer im Pfad)."""
    return (r.stdout + r.stderr).replace(str(root), "<root>")


def _fingerprint(root: Path, target: Path) -> dict:
    """Typ/Inode des State-Pfads, Bytes und Linkzahl der Datei hinter dem Verweis."""
    st = os.lstat(_state_path(root))
    return {
        "typ": st.st_mode & 0o170000,
        "ino": st.st_ino,
        "bytes": target.read_bytes(),
        "nlink_target": os.stat(target).st_nlink,
    }


@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_edit_gate_und_tdd_enforcement_blocken_code_edit_bei_unsicherem_state(
        tmp_path, richtung):
    """AC-9: Code-Edit -> Exit 2 mit Verweis-Meldung; Always-Allowed bleibt frei."""
    root = _sandbox(tmp_path)
    _mache_unsicher(root, richtung)

    fehler = []
    for hook in ("edit_gate.py", "tdd_enforcement.py"):
        r = _run_hook(hook, root, _edit_payload(root / "src" / "x.py"))
        out = _out(r, root)
        if r.returncode != 2:
            fehler.append(f"{hook} src/x.py: rc={r.returncode} (erwartet 2)")
        if "verweis" not in out.lower():
            fehler.append(f"{hook} src/x.py: keine Verweis-Meldung: {out[:300]!r}")
        r = _run_hook(hook, root, _edit_payload(root / "docs" / "a.md"))
        if r.returncode != 0:
            fehler.append(f"{hook} docs/a.md: rc={r.returncode} (erwartet 0): "
                          f"{_out(r, root)[:300]!r}")
    assert not fehler, f"{richtung}: {fehler}"


@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_bash_gate_verweigert_nur_state_abhaengige_freigaben(tmp_path, richtung):
    """AC-10: `git commit` -> Exit 2 mit Verweis-Meldung, `ls` -> Exit 0."""
    root = _sandbox(tmp_path)
    shutil.rmtree(root / ".git")
    subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
    _mache_unsicher(root, richtung)

    fehler = []
    r = _run_hook("bash_gate.py", root,
                  {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}})
    out = _out(r, root)
    if r.returncode != 2:
        fehler.append(f"git commit: rc={r.returncode} (erwartet 2)")
    if "verweis" not in out.lower():
        fehler.append(f"git commit: keine Verweis-Meldung: {out[:300]!r}")
    r = _run_hook("bash_gate.py", root,
                  {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    if r.returncode != 0:
        fehler.append(f"ls: rc={r.returncode} (erwartet 0): {_out(r, root)[:300]!r}")
    assert not fehler, f"{richtung}: {fehler}"


@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_phase_listener_footer_gate_post_implementation_gate_fail_open_mit_warnung(
        tmp_path, richtung):
    """AC-11: Exit 0 mit Warnung, nie Exit 2; phase_listener schreibt nichts."""
    state = dict(FAKE_STATE, current_phase="phase3_spec", adversary_verdict="")
    root = _sandbox(tmp_path, state=state)
    target = _mache_unsicher(root, richtung)
    vorher = target.read_bytes()

    fehler = []
    r = _run_hook("phase_listener.py", root,
                  {"hook_event_name": "UserPromptSubmit", "prompt": "approved"})
    if r.returncode != 0:
        fehler.append(f"phase_listener: rc={r.returncode} (erwartet 0)")
    if "verweis" not in _out(r, root).lower():
        fehler.append(f"phase_listener: keine Warnung: {_out(r, root)[:300]!r}")
    if target.read_bytes() != vorher:
        fehler.append("phase_listener: State hinter dem Verweis verändert")

    r = _run_hook("footer_gate.py", root, {
        "session_id": "sess-416", "hook_event_name": "Stop", "cwd": str(root),
        "prompt_id": "prompt-416",
        "last_assistant_message":
            "Fertig.\n\n❗ Du: `/60-validate` — der naechste Pflicht-Schritt\n"
            "⚙ /50-implement · agent-os-openspec",
    })
    if r.returncode != 0:
        fehler.append(f"footer_gate: rc={r.returncode} (erwartet 0)")
    if "verweis" not in _out(r, root).lower():
        fehler.append(f"footer_gate: keine Warnung: {_out(r, root)[:300]!r}")

    r = _run_hook("post_implementation_gate.py", root,
                  _edit_payload(root / "src" / "x.py"))
    if r.returncode != 0:
        fehler.append(f"post_implementation_gate: rc={r.returncode} (erwartet 0)")
    if "verweis" not in _out(r, root).lower():
        fehler.append(f"post_implementation_gate: keine Warnung: "
                      f"{_out(r, root)[:300]!r}")
    assert not fehler, f"{richtung}: {fehler}"


@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_adversary_dialog_gewaehrt_keine_freigabe_bei_unsicherem_state(
        tmp_path, monkeypatch, richtung):
    """AC-13: kein Fast-Track, required-files Exit 1, Metriken warnen ohne Schreiben."""
    root = _sandbox(tmp_path, state=dict(FAKE_STATE, workflow_type="feature-fast"))
    target = _mache_unsicher(root, richtung)
    vorher = target.read_bytes()
    _in_sandbox(monkeypatch, root)
    ad = importlib.import_module("adversary_dialog")

    fehler = []
    if ad._active_workflow_is_fast_track() is not False:
        fehler.append("Fast-Track gewährt Freigabe trotz Verweis")
    rc = ad._cmd_required_files()
    if rc != 1:
        fehler.append(f"required-files: rc={rc} (erwartet 1)")
    msg = ad._persist_adversary_metrics("")
    if "WARNUNG" not in msg:
        fehler.append(f"Metriken ohne Warnung: {msg!r}")
    if target.read_bytes() != vorher:
        fehler.append("Metriken: State hinter dem Verweis verändert")
    assert not fehler, f"{richtung}: {fehler}"


def _rmw_post_bash(root: Path, monkeypatch) -> None:
    """post_bash._record_test_run, ausgelöst über den echten Hook (Subprozess)."""
    _run_hook("post_bash.py", root, {
        "tool_name": "Bash", "hook_event_name": "PostToolUse",
        "tool_input": {"command": "python -m pytest -q"},
        "tool_response": {"stdout": "3 passed in 0.12s", "stderr": ""},
    })


def _rmw_e2e_scope(root: Path, monkeypatch) -> None:
    """bash_gate._write_e2e_scope direkt (modulweites `_root` auf die Sandbox)."""
    _in_sandbox(monkeypatch, root)
    bg = importlib.import_module("bash_gate")
    monkeypatch.setattr(bg, "_root", root)
    bg._write_e2e_scope({"name": WF}, "backend")


def _rmw_loc_delta(root: Path, monkeypatch) -> None:
    """edit_gate._check_loc_delta direkt; Grenzen hoch, damit der Schreibzweig läuft."""
    _in_sandbox(monkeypatch, root)
    eg = importlib.import_module("edit_gate")
    monkeypatch.setattr(eg, "_root", root)
    eg._check_loc_delta(
        {"scope_guard": {"max_loc_delta": 99999, "max_test_loc_delta": 99999}},
        {"name": WF})


@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_rmw_stellen_schreiben_bei_unsicherem_state_nicht_zurueck(
        tmp_path, monkeypatch, richtung):
    """AC-15: keine der drei Lesen-Ändern-Schreiben-Stellen schreibt zurück.

    Je Stelle eine frische Sandbox. post_bash läuft als Subprozess (der Hook
    liest die Payload von stdin), `_write_e2e_scope` und `_check_loc_delta`
    per Import, weil ihr Auslöser im Hook an weiteren Bedingungen hängt.
    Geprüft: Bytes der Datei hinter dem Verweis, Typ/Inode des State-Pfads
    (kein atomares „Waschen“ zur normalen Datei) und beim harten Verweis die
    Linkzahl 2.
    """
    fehler = []
    for name, stelle in (("post_bash", _rmw_post_bash),
                         ("bash_gate", _rmw_e2e_scope),
                         ("edit_gate", _rmw_loc_delta)):
        root = _sandbox(tmp_path / name)
        target = _mache_unsicher(root, richtung)
        vorher = _fingerprint(root, target)
        stelle(root, monkeypatch)
        nachher = _fingerprint(root, target)
        for key in vorher:
            if vorher[key] != nachher[key]:
                fehler.append(f"{name}: {key} verändert")
    assert not fehler, f"{richtung}: {fehler}"


def test_phase_listener_save_workflow_schreibt_atomar(tmp_path, monkeypatch):
    """AC-16: _save_workflow schreibt mit neuem Inode, nicht durch den Verweis."""
    root = _sandbox(tmp_path, state=dict(FAKE_STATE, adversary_verdict=""))
    state = _state_path(root)
    zweit = root / "docs" / "zweit.json"
    os.link(state, zweit)
    alt = zweit.read_bytes()
    ino_vorher = os.stat(state).st_ino

    _in_sandbox(monkeypatch, root)
    pl = importlib.import_module("phase_listener")
    monkeypatch.setattr(pl, "_root", root)
    pl._save_workflow(dict(FAKE_STATE, current_phase="phase4_approved"), state)

    fehler = []
    if zweit.read_bytes() != alt:
        fehler.append("Zweitname zeigt neuen Inhalt (durch den Verweis geschrieben)")
    if json.loads(state.read_text()).get("current_phase") != "phase4_approved":
        fehler.append("State-Pfad hat nicht den neuen Inhalt")
    if os.stat(state).st_ino == ino_vorher:
        fehler.append("kein neuer Inode")
    assert not fehler, fehler
