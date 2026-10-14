"""Prüfung an der Quelle für die übrigen Zustandsdateien — #422.

Spec: docs/specs/fix-422-state-files-source-check.md

Befund: #416 prüft nur `.claude/workflows/<wf>.json`. Override-Token,
Freigabevermerk, Stop-Lock, Pending-Lock, Footer-State, Session-Locks und
`active_workflow` werden weiter über einen Verweis (harter Link, Symlink auf
die Datei, Symlink auf einen Ordner der Kette oder `.claude` selbst) gelesen
und geschrieben. Ein gefälschter Token gibt frei, ein gefälschter Vermerk
löst die Review-Sperre, ein Verweis hebt die Stop-Sperre auf.

Teil A (hier): Leserkern `read_state_text` (AC-1, AC-2), freigebende und
sperrende Dateien in den Gates (AC-3 bis AC-6), Unlink-Pfade (AC-14).
Teil B (unten, separat ergänzt): AC-7 bis AC-13, AC-15 bis AC-18.

Richtungen (`RICHTUNGEN` aus dem #416-Test): Für Dateien direkt unter
`.claude/` gibt es keinen Zwischenordner; „symlink_dir" bedeutet dort, dass
der Elternordner — also `.claude` selbst — ein Symlink ist. In beiden
Ordner-Richtungen liegt damit auch der Workflow-State hinter dem Verweis,
und #416 greift zuerst (edit_gate blockt, post_implementation_gate und
phase_listener laufen fail-open mit Warnung). Die Tests werten das als
„keine Freigabe", solange der Edit insgesamt blockiert bleibt.

Import-Strategie: neue APIs per getattr, damit jeder Test einzeln RED wird
statt eines Sammelfehlers bei der Collection.
"""

import importlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
for _p in (str(HOOKS_DIR), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hook_utils  # noqa: E402
from test_state_reader_source_416 import RICHTUNGEN  # noqa: E402

WF = "sandboxwf"
WF_CREATED = "2026-01-01T00:00:00"
FAKE_STATE = {
    "name": WF,
    "current_phase": "phase3_spec",
    "workflow_type": "feature",
    "created": WF_CREATED,
}
# Richtungen, in denen nur die Datei selbst ein Verweis ist (Workflow-State sauber)
DATEI_RICHTUNGEN = ("hard", "symlink_file")


def _require_api(*names):
    """Neue hook_utils-API holen; fehlt sie, klarer Fehlschlag statt AttributeError."""
    found = []
    for name in names:
        obj = getattr(hook_utils, name, None)
        if obj is None:
            pytest.fail(f"hook_utils.{name} fehlt (#422)")
        found.append(obj)
    return found[0] if len(found) == 1 else tuple(found)


# --------------------------------------------------------------------- #
# Sandbox (Muster aus tests/test_state_reader_source_416.py)
# --------------------------------------------------------------------- #

def _sandbox(tmp_path: Path, state: "dict | None" = None, git: bool = False) -> Path:
    """Wegwerf-Projekt (Haupt-Repo, kein Worktree) mit aktivem Workflow WF.

    Workflow-State und `active_workflow` sind normale eigene Dateien.
    """
    root = tmp_path.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if git:
        subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
    else:
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


def _claude_nach_aussen(root: Path) -> Path:
    """`.claude` nach docs/claude_real verschieben, `.claude` als Symlink darauf."""
    claude = root / ".claude"
    if claude.is_symlink():
        return Path(os.path.realpath(claude))
    real = root / "docs" / "claude_real"
    shutil.move(str(claude), str(real))
    os.symlink(real, claude)
    return real


def _verweis(root: Path, relpfad: str, richtung: str, inhalt: str) -> Path:
    """Legt `.claude/<relpfad>` als Verweis auf eine FREMDE Datei mit `inhalt` an.

    Liefert die fremde Zieldatei (außerhalb von `.claude`) für Byte-Vergleiche.

      - "hard":           fremde Datei docs/fremd_<name>, `.claude/<relpfad>`
                          ist ein zweiter Name (st_nlink == 2).
      - "symlink_file":   `.claude/<relpfad>` ist ein Symlink auf die fremde
                          Datei. `inhalt=None` → hängender Symlink.
      - "symlink_dir":    der Elternordner von `<relpfad>` ist ein Symlink auf
                          einen fremden Ordner; liegt die Datei direkt unter
                          `.claude`, ist das `.claude` selbst.
      - "claude_symlink": `.claude` ist ein Symlink auf docs/claude_real.
    """
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    pfad = root / ".claude" / relpfad
    name = Path(relpfad).name
    if richtung == "hard":
        target = docs / f"fremd_{name}"
        target.write_text(inhalt)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        os.link(target, pfad)
        assert os.stat(pfad).st_nlink == 2
        return target
    if richtung == "symlink_file":
        target = docs / f"fremd_{name}"
        if inhalt is not None:
            target.write_text(inhalt)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, pfad)
        return target
    if richtung == "symlink_dir" and Path(relpfad).parent != Path("."):
        eltern = pfad.parent
        real_dir = docs / f"{eltern.name}_real"
        if eltern.exists():
            shutil.move(str(eltern), str(real_dir))
        else:
            real_dir.mkdir(parents=True)
        os.symlink(real_dir, eltern)
        target = real_dir / name
        target.write_text(inhalt)
        return target
    if richtung in ("symlink_dir", "claude_symlink"):
        real = _claude_nach_aussen(root)
        target = real / relpfad
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(inhalt)
        return target
    raise ValueError(f"unbekannte Richtung: {richtung}")


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


def _run_py(root: Path, code: str) -> subprocess.CompletedProcess:
    """Python-Schnipsel mit core/hooks auf sys.path in der Sandbox ausführen."""
    prog = f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r})\n" + code
    return subprocess.run(
        [sys.executable, "-c", prog], capture_output=True, text=True,
        env=_hook_env(root), cwd=str(root), timeout=60,
    )


def _edit_payload(file_path) -> dict:
    return {"tool_name": "Edit", "tool_input": {
        "file_path": str(file_path), "old_string": "a", "new_string": "b"}}


def _bash_payload(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _out(r: subprocess.CompletedProcess, root: Path) -> str:
    """stdout+stderr, Sandbox-Pfad neutralisiert."""
    return (r.stdout + r.stderr).replace(str(root), "<root>")


def _token_json() -> str:
    return json.dumps({"version": 2, "tokens": {WF: {
        "created": datetime.now().isoformat(), "granted_by": "user_prompt"}}})


def _lock_json(created: float) -> str:
    return json.dumps({"workflow": WF, "workflow_created": WF_CREATED,
                       "created": created, "created_iso": "x"})


def _lock_rel() -> str:
    return f"pending_validation_{WF}.json"


def _marker_rel() -> str:
    return f"user_approved_validation_{WF}"


# --------------------------------------------------------------------- #
# AC-1, AC-2: Leserkern
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_kern_wirft_unsafe_state_error_je_richtung(tmp_path, richtung):
    """AC-1: read_state_text wirft UnsafeStateError; read_state_json unverändert."""
    read_state_text, err = _require_api("read_state_text", "UnsafeStateError")
    root = _sandbox(tmp_path)
    _verweis(root, _marker_rel(), richtung, "123.0")
    pfad = root / ".claude" / _marker_rel()

    with pytest.raises(err) as info:
        read_state_text(pfad, root)
    assert str(pfad.name) in str(info.value), (
        f"{richtung}: Meldung nennt den Pfad nicht: {info.value}")

    if richtung in DATEI_RICHTUNGEN:
        # #416-Leser: der saubere Workflow-State wird unverändert gelesen
        assert hook_utils.read_state_json(_state_path(root), root) == FAKE_STATE


def test_normalfall_fehlend_kaputt_und_wurzel_hinter_symlink_wie_heute(tmp_path):
    """AC-2: normale Datei → Inhalt, fehlend → FileNotFoundError, kaputt wie heute,
    Wurzel hinter Symlink-Elternordner kein Fehlalarm."""
    read_state_text, err = _require_api("read_state_text", "UnsafeStateError")
    root = _sandbox(tmp_path / "proj")
    marker = root / ".claude" / _marker_rel()
    marker.write_text("1234.5")
    assert read_state_text(marker, root).strip() == "1234.5"

    with pytest.raises(FileNotFoundError):
        read_state_text(root / ".claude" / "fehlt", root)

    kaputt = root / ".claude" / f"pending_validation_{WF}.json"
    kaputt.write_text("{kein json")
    assert read_state_text(kaputt, root) == "{kein json"
    with pytest.raises(json.JSONDecodeError):
        hook_utils.read_state_json(kaputt, root)

    # Wurzel liegt hinter einem Symlink-Elternordner (z. B. /tmp → /private/tmp)
    link = tmp_path.resolve() / "link"
    os.symlink(tmp_path.resolve(), link)
    via_link = link / "proj"
    assert read_state_text(via_link / ".claude" / _marker_rel(), via_link) \
        .strip() == "1234.5"
    assert hook_utils.read_state_json(
        via_link / ".claude" / "workflows" / f"{WF}.json", via_link) == FAKE_STATE


# --------------------------------------------------------------------- #
# AC-3: Override-Token als Verweis
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_override_token_verweis_gibt_nichts_frei(tmp_path, richtung):
    """AC-3: has_valid_token False, edit_gate blockt den Code-Edit (Exit 2)."""
    root = _sandbox(tmp_path)  # phase3_spec: ohne Token kein Code-Edit
    _verweis(root, "user_override_token.json", richtung, _token_json())

    fehler = []
    r = _run_py(root, "import override_token\n"
                      f"print(override_token.has_valid_token({WF!r}), "
                      "override_token.has_valid_token())")
    if r.returncode != 0:
        fehler.append(f"has_valid_token: rc={r.returncode}: {_out(r, root)[-400:]!r}")
    elif r.stdout.strip() != "False False":
        fehler.append(f"has_valid_token liefert {r.stdout.strip()!r} "
                      "(erwartet 'False False')")

    r = _run_hook("edit_gate.py", root, _edit_payload(root / "src" / "x.py"))
    if r.returncode != 2:
        fehler.append(f"edit_gate src/x.py: rc={r.returncode} (erwartet 2): "
                      f"{_out(r, root)[:300]!r}")
    assert not fehler, f"{richtung}: {fehler}"


# --------------------------------------------------------------------- #
# AC-4: Freigabevermerk als Verweis
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_freigabevermerk_verweis_gilt_als_nicht_vorhanden(tmp_path, richtung):
    """AC-4: Lock normal (Batch-Fenster abgelaufen), Vermerk als Verweis mit
    passendem `created` → Exit 2, Lock bleibt."""
    state = dict(FAKE_STATE, current_phase="phase6_implement", red_test_done=True)
    root = _sandbox(tmp_path, state=state)
    created = time.time() - 10 * 3600
    lock = root / ".claude" / _lock_rel()
    lock.write_text(_lock_json(created))
    _verweis(root, _marker_rel(), richtung, str(created))

    fehler = []
    r = _run_hook("post_implementation_gate.py", root,
                  _edit_payload(root / "src" / "x.py"))
    out = _out(r, root)
    if richtung in DATEI_RICHTUNGEN:
        if r.returncode != 2:
            fehler.append(f"post_implementation_gate: rc={r.returncode} "
                          f"(erwartet 2): {out[:300]!r}")
    else:
        # .claude hinter Verweis: #416 greift zuerst (fail-open mit Warnung),
        # edit_gate muss den Edit dann blocken.
        if r.returncode not in (0, 2):
            fehler.append(f"post_implementation_gate: rc={r.returncode}: {out[:300]!r}")
        r2 = _run_hook("edit_gate.py", root, _edit_payload(root / "src" / "x.py"))
        if r2.returncode != 2:
            fehler.append(f"edit_gate: rc={r2.returncode} (erwartet 2)")
    if not os.path.lexists(root / ".claude" / _lock_rel()):
        fehler.append("Pending-Lock wurde gelöscht (Vermerk als Freigabe gewertet)")
    assert not fehler, f"{richtung}: {fehler}"


# --------------------------------------------------------------------- #
# AC-5: Stop-Lock als Verweis
# --------------------------------------------------------------------- #

def _stop_varianten(richtung: str):
    v = [("enabled_true", json.dumps({"enabled": True})),
         ("enabled_false", json.dumps({"enabled": False}))]
    if richtung == "symlink_file":
        v.append(("haengend", None))
    return v


@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_stop_lock_verweis_sperrt_edit_und_bash_gate(tmp_path, richtung):
    """AC-5: edit_gate und bash_gate Exit 2 mit Verweis-Meldung; gemeinsame
    Funktion hook_utils.is_stop_locked, Kopien in den Gates entfernt."""
    fehler = []
    for variante, inhalt in _stop_varianten(richtung):
        state = dict(FAKE_STATE, current_phase="phase6_implement", red_test_done=True)
        root = _sandbox(tmp_path / variante, state=state, git=True)
        _verweis(root, "stop_lock.json", richtung, inhalt)
        for hook, payload in (
                ("edit_gate.py", _edit_payload(root / "src" / "x.py")),
                ("bash_gate.py", _bash_payload("ls"))):
            r = _run_hook(hook, root, payload)
            out = _out(r, root)
            if r.returncode != 2:
                fehler.append(f"{variante} {hook}: rc={r.returncode} (erwartet 2)")
            if "stop_lock" not in out or "verweis" not in out.lower():
                fehler.append(f"{variante} {hook}: Meldung nennt den Stop-Lock-"
                              f"Verweis nicht: {out[:300]!r}")

    if getattr(hook_utils, "is_stop_locked", None) is None:
        fehler.append("hook_utils.is_stop_locked fehlt")
    for gate in ("edit_gate.py", "bash_gate.py"):
        if "def _is_stop_locked" in (HOOKS_DIR / gate).read_text():
            fehler.append(f"{gate} definiert _is_stop_locked noch selbst")
    assert not fehler, f"{richtung}: {fehler}"


# --------------------------------------------------------------------- #
# AC-6: Pending-Lock als Verweis
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_pending_lock_verweis_blockt_explizit_nie_exit_1(tmp_path, richtung):
    """AC-6: Lock-Verweis mit `created` in der Zukunft → Exit 2 (nie 0/1),
    phase_listener schreibt bei 'go' keinen Freigabevermerk."""
    state = dict(FAKE_STATE, current_phase="phase6_implement", red_test_done=True)
    root = _sandbox(tmp_path, state=state)
    _verweis(root, _lock_rel(), richtung, _lock_json(time.time() + 3600))

    fehler = []
    r = _run_hook("post_implementation_gate.py", root,
                  _edit_payload(root / "src" / "x.py"))
    out = _out(r, root)
    if r.returncode == 1:
        fehler.append(f"post_implementation_gate: Exit 1 (unbehandelte Ausnahme): "
                      f"{out[-300:]!r}")
    if richtung in DATEI_RICHTUNGEN:
        if r.returncode != 2:
            fehler.append(f"post_implementation_gate: rc={r.returncode} "
                          f"(erwartet 2): {out[:300]!r}")
    else:
        # .claude hinter Verweis: #416 fail-open, edit_gate blockt
        r2 = _run_hook("edit_gate.py", root, _edit_payload(root / "src" / "x.py"))
        if r2.returncode != 2:
            fehler.append(f"edit_gate: rc={r2.returncode} (erwartet 2)")

    r = _run_hook("phase_listener.py", root,
                  {"hook_event_name": "UserPromptSubmit", "prompt": "go"})
    if r.returncode == 1:
        fehler.append(f"phase_listener: Exit 1: {_out(r, root)[-300:]!r}")
    if os.path.lexists(root / ".claude" / _marker_rel()):
        fehler.append("phase_listener hat einen Freigabevermerk aus dem "
                      "Lock-Verweis geschrieben")
    assert not fehler, f"{richtung}: {fehler}"


# --------------------------------------------------------------------- #
# AC-14: Unlink-Pfade löschen nur den Verweis
# (nur Datei-Richtungen: bei einem Ordner-Symlink IST der Eintrag im
#  Zielordner die Datei — dort gibt es keinen „Verweis" zum Entfernen)
# --------------------------------------------------------------------- #

def _bytes(paths):
    return {p: p.read_bytes() for p in paths}


@pytest.mark.parametrize("richtung", DATEI_RICHTUNGEN)
def test_clear_lock_loescht_nur_den_verweis(tmp_path, richtung):
    root = _sandbox(tmp_path)
    t_lock = _verweis(root, _lock_rel(), richtung, _lock_json(1.0))
    t_mark = _verweis(root, _marker_rel(), richtung, "1.0")
    vorher = _bytes([t_lock, t_mark])

    pig = importlib.import_module("post_implementation_gate")
    pig._clear_lock(root / ".claude" / _lock_rel(), root / ".claude" / _marker_rel())

    assert not os.path.lexists(root / ".claude" / _lock_rel())
    assert not os.path.lexists(root / ".claude" / _marker_rel())
    assert _bytes([t_lock, t_mark]) == vorher


@pytest.mark.parametrize("richtung", DATEI_RICHTUNGEN)
def test_reap_dead_loescht_nur_den_verweis(tmp_path, richtung):
    root = _sandbox(tmp_path)
    data = {"session_id": "tot", "pid": None, "last_seen": 0}
    target = _verweis(root, "session-locks/tot.json", richtung, json.dumps(data))
    vorher = target.read_bytes()
    pfad = root / ".claude" / "session-locks" / "tot.json"

    ssg = importlib.import_module("session_singleton_guard")
    alive = ssg._reap_dead({"tot": (pfad, data)}, time.time())

    assert alive == {}
    assert not os.path.lexists(pfad)
    assert target.read_bytes() == vorher


@pytest.mark.parametrize("richtung", DATEI_RICHTUNGEN)
def test_remove_all_tokens_loescht_nur_den_verweis(tmp_path, monkeypatch, richtung):
    root = _sandbox(tmp_path)
    target = _verweis(root, "user_override_token.json", richtung, _token_json())
    vorher = target.read_bytes()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))

    ot = importlib.import_module("override_token")
    ot.remove_all_tokens()

    assert not os.path.lexists(root / ".claude" / "user_override_token.json")
    assert target.read_bytes() == vorher


# --------------------------------------------------------------------- #
# Teil B — Helfer
# --------------------------------------------------------------------- #

def _run_ssg(root: Path, mode: str, payload: "dict | None" = None,
             extra_env: "dict | None" = None) -> subprocess.CompletedProcess:
    """session_singleton_guard als Subprozess (Hook-Modus bzw. CLI `claim`)."""
    env = _hook_env(root)
    env.update(extra_env or {})
    argv = [sys.executable, str(HOOKS_DIR / "session_singleton_guard.py"), mode]
    if mode == "claim":
        argv += ["--issue", "422"]
    return subprocess.run(
        argv, input=json.dumps(payload or {}), capture_output=True, text=True,
        env=env, cwd=str(root), timeout=60,
    )


def _ssg_payload(root: Path, sid: str = "eigen") -> dict:
    return {"session_id": sid, "cwd": str(root), "tool_name": "Read",
            "tool_input": {"file_path": str(root / "README.md")}}


def _session_entry(sid: str, last_seen: float) -> str:
    return json.dumps({"session_id": sid, "pid": None, "cwd": "/fremd",
                       "started_at": last_seen - 10, "last_seen": last_seen})


def _footer_payload(prompt_id: str = "p-422") -> dict:
    # Workflow steht in phase3_spec → erwartet `/30-write-spec`, Fußzeile falsch.
    return {"hook_event_name": "Stop", "prompt_id": prompt_id,
            "last_assistant_message": "Erledigt.\n\n❗ Du: `/99-reset`"}


def _footer_state_json(prompt_id: str = "p-422") -> str:
    return json.dumps({"last_turn_id": prompt_id,
                       "last_block_at": datetime.now().isoformat()})


def _ist_normale_datei(p: Path) -> bool:
    st = os.lstat(p)
    return stat.S_ISREG(st.st_mode) and st.st_nlink == 1


def _ohne_vorhandene(root: Path, relpfad: str) -> None:
    """Datei der Sandbox entfernen, damit `_verweis` sie neu anlegen kann."""
    p = root / ".claude" / relpfad
    if os.path.lexists(p) and not (root / ".claude").is_symlink():
        p.unlink()


def _kein_traceback(r: subprocess.CompletedProcess) -> bool:
    return "Traceback" not in (r.stdout + r.stderr)


def _sessions_json(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py"), "sessions", "--json"],
        capture_output=True, text=True, env=_hook_env(root), cwd=str(root),
        timeout=60)


# --------------------------------------------------------------------- #
# AC-7: Footer-State als Verweis
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_footer_state_verweis_wie_leer_mit_log(tmp_path, richtung):
    """AC-7: abschaltender Inhalt im Verweis → Gate prüft (blockt), Log, nie Exit 1."""
    root = _sandbox(tmp_path)
    target = _verweis(root, "footer_gate_state.json", richtung, _footer_state_json())
    vorher = target.read_bytes()

    r = _run_hook("footer_gate.py", root, _footer_payload())
    out = _out(r, root)
    fehler = []
    if r.returncode == 1 or not _kein_traceback(r):
        fehler.append(f"Exit 1/Traceback: {out[-400:]!r}")
    if richtung in DATEI_RICHTUNGEN:
        # Workflow-State sauber: der Verweis darf das Gate nicht abschalten.
        if r.returncode != 2:
            fehler.append(f"rc={r.returncode} (erwartet 2, Gate prüft): {out[:300]!r}")
        if "footer_gate_state" not in out:
            fehler.append(f"kein Log zum Fund: {out[:300]!r}")
    elif r.returncode not in (0, 2):
        # .claude hinter Verweis: #416 greift zuerst (fail-open).
        fehler.append(f"rc={r.returncode}: {out[:300]!r}")
    if target.read_bytes() != vorher:
        fehler.append("Verweisziel wurde beschrieben")
    assert not fehler, f"{richtung}: {fehler}"


# --------------------------------------------------------------------- #
# AC-8: Session-Locks mit Verweis-Eintrag
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_session_locks_verweis_eintrag_wird_uebersprungen(tmp_path, richtung):
    """AC-8: _read_entries und `workflow.py sessions --json` zeigen nur den
    normalen Eintrag. Ist der Ordner selbst der Verweis, gilt jeder Eintrag
    darin als Verweis."""
    root = _sandbox(tmp_path)
    locks = root / ".claude" / "session-locks"
    locks.mkdir(parents=True)
    (locks / "normal.json").write_text(_session_entry("normal", time.time()))
    _verweis(root, "session-locks/fremd.json", richtung,
             _session_entry("fremd", time.time()))
    erwartet = ["normal"] if richtung in DATEI_RICHTUNGEN else []

    fehler = []
    r = _run_py(root, "import json, session_singleton_guard as s\n"
                      "print(json.dumps(sorted(s._read_entries(s._locks_dir()))))")
    if r.returncode != 0:
        fehler.append(f"_read_entries: rc={r.returncode}: {_out(r, root)[-300:]!r}")
    elif json.loads(r.stdout.strip().splitlines()[-1]) != erwartet:
        fehler.append(f"_read_entries zeigt {r.stdout.strip()!r}, erwartet {erwartet}")

    r = _sessions_json(root)
    if r.returncode != 0:
        fehler.append(f"sessions: rc={r.returncode}: {_out(r, root)[-300:]!r}")
    else:
        sids = sorted(e.get("session_id") for e in json.loads(r.stdout))
        if sids != erwartet:
            fehler.append(f"sessions --json zeigt {sids}, erwartet {erwartet}")
    assert not fehler, f"{richtung}: {fehler}"


# --------------------------------------------------------------------- #
# AC-9: Session-Guard schreibt nie durch einen Verweis
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_session_guard_schreibt_nie_durch_verweis(tmp_path, richtung):
    """AC-9: eigener Lock bzw. active_workflow als Verweis → Heartbeat,
    Register und Claim lassen das Ziel byte-gleich, Exit 0."""
    fehler = []
    # last_seen vor 5 min: lebendig (< 900 s), Heartbeat fällig (>= 60 s)
    lock_inhalt = _session_entry("eigen", time.time() - 300)
    for datei, inhalt in (("session-locks/eigen.json", lock_inhalt),
                          ("active_workflow", "fremdwf\n")):
        for mode in ("guard", "register", "claim"):
            root = _sandbox(tmp_path / Path(datei).stem / mode)
            _ohne_vorhandene(root, datei)
            target = _verweis(root, datei, richtung, inhalt)
            vorher = target.read_bytes()
            r = _run_ssg(root, mode, _ssg_payload(root),
                         {"CLAUDE_CODE_SESSION_ID": "eigen"})
            if r.returncode != 0 or not _kein_traceback(r):
                fehler.append(f"{datei} {mode}: rc={r.returncode}: "
                              f"{_out(r, root)[-300:]!r}")
            if target.read_bytes() != vorher:
                fehler.append(f"{datei} {mode}: Verweisziel wurde beschrieben")
    assert not fehler, f"{richtung}: {fehler}"


# --------------------------------------------------------------------- #
# AC-10: active_workflow als Verweis → Fallback settings.local.json
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_active_workflow_verweis_wie_nicht_vorhanden_mit_fallback(tmp_path, richtung):
    root = _sandbox(tmp_path)
    for name in ("fremdwf", "eigenwf"):
        (root / ".claude" / "workflows" / f"{name}.json").write_text(
            json.dumps(dict(FAKE_STATE, name=name)))
    (root / ".claude" / "settings.local.json").write_text(
        json.dumps({"env": {"OPENSPEC_ACTIVE_WORKFLOW": "eigenwf"}}))
    _ohne_vorhandene(root, "active_workflow")
    _verweis(root, "active_workflow", richtung, "fremdwf\n")

    r = _run_py(root, "import hook_utils\n"
                      "print(*hook_utils.resolve_active_workflow())")
    out = _out(r, root)
    assert r.returncode == 0, f"{richtung}: rc={r.returncode}: {out[-400:]!r}"
    name_quelle = r.stdout.strip().splitlines()[-1].split()
    assert name_quelle[0] == "eigenwf", (
        f"{richtung}: Name {name_quelle!r} (erwartet Fallback 'eigenwf')")
    assert "active_workflow" in r.stderr, (
        f"{richtung}: kein Log zum Fund: {r.stderr[:300]!r}")


# --------------------------------------------------------------------- #
# AC-11: Schreiber verändern ein Verweisziel nie
# --------------------------------------------------------------------- #

def _schreib_aufruf(code: str) -> str:
    """Fund (UnsafeStateError) beim Schreiben ist erlaubt, alles andere nicht."""
    eingerueckt = "\n".join("    " + z for z in code.splitlines())
    return ("try:\n" + eingerueckt + "\nexcept Exception as e:\n"
            "    if type(e).__name__ != 'UnsafeStateError':\n        raise\n"
            "    print('FUND', e)\n")


SCHREIBER = {
    "override_token._save_tokens": (
        "user_override_token.json",
        "import override_token\n"
        f"override_token._save_tokens({{{WF!r}: {{'created': 'x', 'granted_by': 't'}}}})"),
    "phase_listener._set_stop_lock": (
        "stop_lock.json",
        "import phase_listener\nphase_listener._set_stop_lock(True)"),
    "token_fallback": (
        "user_override_token.json",
        "sys.modules['override_token'] = None\n"
        f"import phase_listener\nphase_listener._create_override_token({WF!r})"),
    "post_implementation_gate._write_lock": (
        _lock_rel(),
        "import post_implementation_gate as p\n"
        "from hook_utils import find_project_root\n"
        f"p._write_lock(find_project_root() / '.claude' / {_lock_rel()!r}, "
        f"{WF!r}, {WF_CREATED!r})"),
    "footer_gate._remember": (
        "footer_gate_state.json",
        "import footer_gate\nfooter_gate._remember('t-422')"),
}


@pytest.mark.parametrize("richtung", RICHTUNGEN)
@pytest.mark.parametrize("schreiber", list(SCHREIBER) + ["freigabevermerk"])
def test_schreiber_veraendern_verweisziel_nie(tmp_path, schreiber, richtung):
    """AC-11: Verweisziel byte-gleich; bei Datei-Verweis steht danach eine
    normale Datei, bei Fund in der Ordnerkette wird nicht geschrieben."""
    if schreiber == "freigabevermerk":
        state = dict(FAKE_STATE, current_phase="phase6_implement", red_test_done=True)
        root = _sandbox(tmp_path, state=state)
        (root / ".claude" / _lock_rel()).write_text(_lock_json(time.time() - 60))
        relpfad = _marker_rel()
        target = _verweis(root, relpfad, richtung, "fremd")
        vorher = target.read_bytes()
        r = _run_hook("phase_listener.py", root,
                      {"hook_event_name": "UserPromptSubmit", "prompt": "go"})
        assert r.returncode != 1 and _kein_traceback(r), _out(r, root)[-400:]
    else:
        relpfad, code = SCHREIBER[schreiber]
        root = _sandbox(tmp_path)
        target = _verweis(root, relpfad, richtung, "fremd")
        vorher = target.read_bytes()
        r = _run_py(root, _schreib_aufruf(code))
        assert r.returncode == 0, f"{schreiber}/{richtung}: {_out(r, root)[-400:]!r}"

    assert target.read_bytes() == vorher, (
        f"{schreiber}/{richtung}: Verweisziel wurde verändert")
    pfad = root / ".claude" / relpfad
    if richtung in DATEI_RICHTUNGEN and os.path.lexists(pfad):
        assert _ist_normale_datei(pfad), (
            f"{schreiber}/{richtung}: am Ziel steht keine normale Datei")


# --------------------------------------------------------------------- #
# AC-12, AC-13: atomarer Schreiber mit und ohne root
# --------------------------------------------------------------------- #

def test_atomarer_schreiber_prueft_ordnerkette(tmp_path):
    """AC-12: `.claude` bzw. `session-locks` als Symlink → UnsafeStateError,
    kein tempfile und keine Datei im Verweisziel-Ordner."""
    atomic_write_text, err = _require_api("atomic_write_text", "UnsafeStateError")
    fehler = []
    for fall, relpfad in (("claude", "stop_lock.json"),
                          ("session_locks", "session-locks/eigen.json")):
        for schreiber in ("json", "text"):
            root = _sandbox(tmp_path / fall / schreiber)
            if fall == "claude":
                real_dir = _claude_nach_aussen(root)
            else:
                real_dir = root / "docs" / "locks_real"
                real_dir.mkdir()
                os.symlink(real_dir, root / ".claude" / "session-locks")
            vorher = sorted(os.listdir(real_dir))
            pfad = root / ".claude" / relpfad
            try:
                if schreiber == "json":
                    hook_utils.atomic_write_json(pfad, {"enabled": False}, root=root)
                else:
                    atomic_write_text(pfad, "x", root=root)
                fehler.append(f"{fall}/{schreiber}: keine UnsafeStateError")
            except err:
                pass
            except Exception as exc:  # noqa: BLE001
                fehler.append(f"{fall}/{schreiber}: {type(exc).__name__}: {exc}")
            nachher = sorted(os.listdir(real_dir))
            if nachher != vorher:
                fehler.append(f"{fall}/{schreiber}: im Verweisziel-Ordner neu: "
                              f"{sorted(set(nachher) - set(vorher))}")
    assert not fehler, fehler


def test_schreiber_ohne_root_behalten_altes_verhalten(tmp_path):
    """AC-13: ohne root kein Walk — tempfile im Elternordner, os.replace."""
    root = _sandbox(tmp_path)
    # Symlink am Ziel wird durch eine normale Datei ersetzt, Ziel bleibt
    target = _verweis(root, "user_override_token.json", "symlink_file", "fremd")
    pfad = root / ".claude" / "user_override_token.json"
    hook_utils.atomic_write_json(pfad, {"a": 1})
    assert target.read_text() == "fremd"
    assert _ist_normale_datei(pfad)
    assert json.loads(pfad.read_text()) == {"a": 1}
    # Elternordner hinter Symlink: ohne root wird dort geschrieben (kein Walk)
    real_dir = _claude_nach_aussen(root)
    hook_utils.atomic_write_json(root / ".claude" / "neu.json", {"b": 2})
    assert json.loads((real_dir / "neu.json").read_text()) == {"b": 2}
    assert not [n for n in os.listdir(real_dir) if n.endswith(".tmp")]


# --------------------------------------------------------------------- #
# AC-15: footer_gate und session_singleton_guard werfen nie nach außen
# --------------------------------------------------------------------- #

def _fund_faelle(richtung: str):
    """(relpfad, inhalt) je Fund-Pfad; symlink_file zusätzlich hängend."""
    faelle = [("footer_gate_state.json", _footer_state_json()),
              ("session-locks/eigen.json", _session_entry("eigen", time.time() - 300)),
              ("session-locks/fremd.json", _session_entry("fremd", time.time())),
              ("active_workflow", WF + "\n")]
    if richtung == "symlink_file":
        faelle += [("footer_gate_state.json", None),
                   ("session-locks/eigen.json", None),
                   ("active_workflow", None)]
    return faelle


@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_footer_gate_und_session_guard_werfen_nie_nach_aussen(tmp_path, richtung):
    fehler = []
    for i, (relpfad, inhalt) in enumerate(_fund_faelle(richtung)):
        root = _sandbox(tmp_path / str(i))
        _ohne_vorhandene(root, relpfad)
        _verweis(root, relpfad, richtung, inhalt)
        art = "haengend" if inhalt is None else "inhalt"
        laeufe = [("footer_gate", _run_hook("footer_gate.py", root, _footer_payload()))]
        for mode in ("register", "guard", "cleanup", "claim"):
            laeufe.append((f"ssg {mode}", _run_ssg(
                root, mode, _ssg_payload(root), {"CLAUDE_CODE_SESSION_ID": "eigen"})))
        for name, r in laeufe:
            if r.returncode == 1 or not _kein_traceback(r):
                fehler.append(f"{relpfad}/{art} {name}: rc={r.returncode}: "
                              f"{_out(r, root)[-200:]!r}")
            elif name.startswith("ssg") and r.returncode != 0:
                fehler.append(f"{relpfad}/{art} {name}: rc={r.returncode} (erwartet 0)")
    assert not fehler, f"{richtung}: {fehler}"


# --------------------------------------------------------------------- #
# AC-16: normale Dateien — Verhalten unverändert
# --------------------------------------------------------------------- #

def test_normale_dateien_verhalten_unveraendert(tmp_path):
    fehler = []

    # 1. Override-Token gewährt Freigabe
    root = _sandbox(tmp_path / "token")
    (root / ".claude" / "user_override_token.json").write_text(_token_json())
    r = _run_py(root, f"import override_token\n"
                      f"print(override_token.has_valid_token({WF!r}))")
    if r.stdout.strip() != "True":
        fehler.append(f"Token: {_out(r, root)[-200:]!r}")

    # 2. Stop-Lock enabled:true sperrt
    state6 = dict(FAKE_STATE, current_phase="phase6_implement", red_test_done=True)
    root = _sandbox(tmp_path / "stop", state=state6, git=True)
    (root / ".claude" / "stop_lock.json").write_text(json.dumps({"enabled": True}))
    for hook, payload in (("edit_gate.py", _edit_payload(root / "src" / "x.py")),
                          ("bash_gate.py", _bash_payload("ls"))):
        r = _run_hook(hook, root, payload)
        if r.returncode != 2:
            fehler.append(f"Stop-Lock {hook}: rc={r.returncode}")

    # 3. Pending-Lock + passender Vermerk lösen die Sperre
    root = _sandbox(tmp_path / "pending", state=state6)
    created = time.time() - 10 * 3600
    (root / ".claude" / _lock_rel()).write_text(_lock_json(created))
    (root / ".claude" / _marker_rel()).write_text(str(created))
    r = _run_hook("post_implementation_gate.py", root,
                  _edit_payload(root / "src" / "x.py"))
    if r.returncode != 0:
        fehler.append(f"Pending-Lock+Vermerk: rc={r.returncode}: {_out(r, root)[:200]!r}")

    # 4. Footer-State schaltet das Gate ab (gleicher Turn); ohne State prüft es
    root = _sandbox(tmp_path / "footer")
    (root / ".claude" / "footer_gate_state.json").write_text(_footer_state_json())
    r = _run_hook("footer_gate.py", root, _footer_payload())
    if r.returncode != 0:
        fehler.append(f"Footer-State: rc={r.returncode}")
    root = _sandbox(tmp_path / "footer_leer")
    r = _run_hook("footer_gate.py", root, _footer_payload())
    if r.returncode != 2:
        fehler.append(f"Footer ohne State: rc={r.returncode} (Gate prüft nicht)")

    # 5. Session-Locks erscheinen in der Anzeige
    root = _sandbox(tmp_path / "sessions")
    (root / ".claude" / "session-locks").mkdir()
    (root / ".claude" / "session-locks" / "normal.json").write_text(
        _session_entry("normal", time.time()))
    r = _sessions_json(root)
    if r.returncode != 0 or [e.get("session_id")
                             for e in json.loads(r.stdout)] != ["normal"]:
        fehler.append(f"sessions: {_out(r, root)[-200:]!r}")

    # 6. active_workflow wählt den Namen
    root = _sandbox(tmp_path / "active")
    (root / ".claude" / "settings.local.json").write_text(
        json.dumps({"env": {"OPENSPEC_ACTIVE_WORKFLOW": "anderer"}}))
    r = _run_py(root, "import hook_utils\nprint(*hook_utils.resolve_active_workflow())")
    if r.stdout.strip() != f"{WF} file":
        fehler.append(f"active_workflow: {_out(r, root)[-200:]!r}")

    # 7. Geschriebene Dateien sind normale Dateien (S_ISREG, st_nlink == 1)
    root = _sandbox(tmp_path / "schreiber")
    for name, (relpfad, code) in SCHREIBER.items():
        pfad = root / ".claude" / relpfad
        pfad.write_text("alt")
        r = _run_py(root, code)
        if r.returncode != 0:
            fehler.append(f"{name}: rc={r.returncode}: {_out(r, root)[-200:]!r}")
        elif not _ist_normale_datei(pfad) or pfad.read_text() == "alt":
            fehler.append(f"{name}: keine frisch geschriebene normale Datei")
    r = _run_ssg(root, "register", _ssg_payload(root))
    eigen = root / ".claude" / "session-locks" / "eigen.json"
    if r.returncode != 0 or not eigen.exists() or not _ist_normale_datei(eigen):
        fehler.append(f"register: rc={r.returncode}, Lock fehlt/nicht normal")
    assert not fehler, fehler


# --------------------------------------------------------------------- #
# AC-18: Doku
# --------------------------------------------------------------------- #

def _version(text: str) -> str:
    m = re.search(r"\*\*Version\*\*:\s*(\S+)", text)
    return m.group(1) if m else ""


def _changelog_entry_422(changelog: str) -> str:
    # Release-stabil: nicht an [Unreleased] gebunden — beim Release wandert der
    # Eintrag in den Versionsabschnitt (wie tests/test_always_allowed_worktree_409.py).
    lines = changelog.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("- **#422")), None)
    assert start is not None, "Kein Eintrag zu #422 im CHANGELOG"
    entry = [lines[start]]
    for line in lines[start + 1:]:
        if line.startswith("- ") or line.startswith("#"):
            break
        entry.append(line)
    return "\n".join(entry)


def test_changelog_und_claude_md_nennen_limitations_und_funktionen():
    block = _changelog_entry_422((REPO_ROOT / "CHANGELOG.md").read_text())
    fehler = []
    for muss in ("#422", "settings.local.json"):
        if muss not in block:
            fehler.append(f"CHANGELOG-Eintrag #422 nennt {muss!r} nicht")
    klein = block.lower()
    for muss in ("link anlegen", "direktes schreiben ohne link"):
        if muss not in klein:
            fehler.append(f"CHANGELOG-Eintrag #422 nennt Known Limitation {muss!r} nicht")

    claude_md = (REPO_ROOT / "CLAUDE.md").read_text()
    zeilen = [z for z in claude_md.splitlines() if "core/hooks/hook_utils.py" in z]
    for fn in ("read_state_text", "atomic_write_text", "is_stop_locked"):
        if not any(fn in z for z in zeilen):
            fehler.append(f"CLAUDE.md: hook_utils-Zeile nennt {fn} nicht")

    # Release-stabil: CLAUDE.md-Version gegen plugin.json statt gegen origin/main.
    plugin = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    if _version(claude_md) != plugin.get("version"):
        fehler.append(f"CLAUDE.md-Version {_version(claude_md)} != "
                      f"plugin.json-Version {plugin.get('version')}")
    assert not fehler, fehler
