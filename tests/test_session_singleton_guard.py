"""Tests for session_singleton_guard._is_alive — shell-PID regression.

Core bug: os.getppid() in a hook returns the transient shell subprocess PID,
not Claude's PID. The shell exits immediately after the hook completes, so the
stored PID is dead on the very next guard call. Without the last_seen fallback,
every live session's lock file would be reaped on first PreToolUse.
"""

import json
import sys
import time
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import session_singleton_guard as ssg


@pytest.fixture(autouse=True)
def _isolate_lock_dir(tmp_path, monkeypatch):
    """Kein Test dieses Moduls schreibt je ins echte .claude/session-locks/.

    Seit dem Re-Register-Sicherheitsnetz (fix-120-121, A2) legt der guard bei
    fehlender Lock-Datei einen Eintrag an, statt still auszusteigen. Ohne diesen
    Default wuerden die Bestandstests aus 3.4.10 (die `_locks_dir` nie patchen
    mussten, weil der guard frueher nichts schrieb) Phantom-Sessions in das
    PRODUKTIVE Register des Hauptrepos schreiben — sichtbar in `workflow.py
    sessions` jeder Server-Session. Tests mit eigenem Lock-Verzeichnis
    (_heartbeat_env, _hermetic_guard) ueberschreiben diesen Default regulaer.
    """
    monkeypatch.setattr(ssg, "_locks_dir", lambda: tmp_path / "autouse-locks")


# ---------------------------------------------------------------------------
# _is_alive — shell-PID fallback
# ---------------------------------------------------------------------------

def test_is_alive_live_pid():
    """Entry with a live PID is alive."""
    entry = {"pid": 1, "last_seen": time.time() - 9999}  # pid 1 (init) is always alive
    assert ssg._is_alive(entry, time.time()) is True


def test_is_alive_dead_pid_recent_last_seen():
    """Entry with dead PID but fresh last_seen is considered alive.

    This is the shell-PID bug: the hook stores the transient shell PID which
    dies immediately. The session should survive via last_seen.
    """
    entry = {"pid": 999999999, "last_seen": time.time() - 10}  # dead PID, fresh timestamp
    assert ssg._is_alive(entry, time.time()) is True


def test_is_alive_dead_pid_stale_last_seen():
    """Entry with dead PID AND stale last_seen is dead (genuinely crashed session)."""
    entry = {"pid": 999999999, "last_seen": time.time() - 9999}  # dead, stale
    assert ssg._is_alive(entry, time.time()) is False


def test_is_alive_no_pid_recent_last_seen():
    """Entry without PID falls back to last_seen only."""
    entry = {"last_seen": time.time() - 10}
    assert ssg._is_alive(entry, time.time()) is True


def test_is_alive_no_pid_stale_last_seen():
    """Entry without PID and stale last_seen is dead."""
    entry = {"last_seen": time.time() - 9999}
    assert ssg._is_alive(entry, time.time()) is False


# ---------------------------------------------------------------------------
# _reap_dead — lock file survives despite dead shell PID
# ---------------------------------------------------------------------------

def test_reap_dead_keeps_entry_with_dead_pid_fresh_last_seen(tmp_path):
    """Lock file is NOT deleted when PID is dead but last_seen is fresh.

    Regression test for the shell-PID bug: without the last_seen fallback,
    _reap_dead would delete every live session's lock file on first guard call.
    """
    locks = tmp_path / ".claude" / "session-locks"
    locks.mkdir(parents=True)

    lock_file = locks / "session-abc.json"
    entry = {"session_id": "abc", "pid": 999999999, "last_seen": time.time() - 10}
    lock_file.write_text(json.dumps(entry))

    entries = ssg._read_entries(locks)
    alive = ssg._reap_dead(entries, time.time())

    assert "abc" in alive, "Live session reaped despite fresh last_seen"
    assert lock_file.exists(), "Lock file deleted despite fresh last_seen"


def test_reap_dead_removes_entry_with_dead_pid_stale_last_seen(tmp_path):
    """Lock file IS deleted when PID is dead AND last_seen is stale (genuine crash)."""
    locks = tmp_path / ".claude" / "session-locks"
    locks.mkdir(parents=True)

    lock_file = locks / "session-xyz.json"
    entry = {"session_id": "xyz", "pid": 999999999, "last_seen": time.time() - 9999}
    lock_file.write_text(json.dumps(entry))

    entries = ssg._read_entries(locks)
    alive = ssg._reap_dead(entries, time.time())

    assert "xyz" not in alive, "Crashed session not reaped"
    assert not lock_file.exists(), "Lock file of crashed session not deleted"


# ---------------------------------------------------------------------------
# _do_guard — worktree-mandatory logic (3.4.10)
# ---------------------------------------------------------------------------

def _make_guard_payload(tool_name: str, cwd: str, session_id: str = "sess-abc") -> dict:
    return {
        "session_id": session_id,
        "cwd": cwd,
        "tool_name": tool_name,
        "tool_input": {},
    }


MAIN_CWD = "/home/user/myproject"
WORKTREE_CWD = "/home/user/myproject/.claude/worktrees/my-feature"


def _run_guard(payload: dict) -> int:
    """Run _do_guard and return the exit code (0 = allow, 2 = block)."""
    import io
    import contextlib
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            ssg._do_guard(payload)
        return 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0


def test_guard_read_tool_always_allowed_in_main_repo():
    """Read tool is never blocked, even in main repo (non-blocking tool)."""
    payload = _make_guard_payload("Read", MAIN_CWD)
    assert _run_guard(payload) == 0


def test_guard_grep_always_allowed_in_main_repo():
    """Grep is non-blocking — never blocked."""
    payload = _make_guard_payload("Grep", MAIN_CWD)
    assert _run_guard(payload) == 0


def test_guard_toolsearch_always_allowed_in_main_repo():
    """ToolSearch (schema loader) must never be blocked — EnterWorktree depends on it."""
    payload = _make_guard_payload("ToolSearch", MAIN_CWD)
    assert _run_guard(payload) == 0


def _hermetic_guard(monkeypatch, tmp_path):
    """Isolate _do_guard from live project state (#49).

    _do_guard reads the real project's override token and locks dir. A real
    override token in the project root would make these block tests see 'allow'.
    Pin both to hermetic values so the test proves guard logic, not environment.
    """
    monkeypatch.setattr(ssg, "_has_override_token", lambda: False)
    locks = tmp_path / ".claude" / "session-locks"
    monkeypatch.setattr(ssg, "_locks_dir", lambda: locks)


def test_guard_edit_blocked_in_main_repo(tmp_path, monkeypatch):
    """Edit is a blocking tool — blocked in main repo."""
    _hermetic_guard(monkeypatch, tmp_path)
    payload = _make_guard_payload("Edit", MAIN_CWD)
    assert _run_guard(payload) == 2


def test_guard_write_blocked_in_main_repo(tmp_path, monkeypatch):
    """Write is a blocking tool — blocked in main repo."""
    _hermetic_guard(monkeypatch, tmp_path)
    payload = _make_guard_payload("Write", MAIN_CWD)
    assert _run_guard(payload) == 2


def test_guard_bash_blocked_in_main_repo(tmp_path, monkeypatch):
    """Bash is a blocking tool — blocked in main repo."""
    _hermetic_guard(monkeypatch, tmp_path)
    payload = _make_guard_payload("Bash", MAIN_CWD)
    assert _run_guard(payload) == 2


def test_guard_edit_allowed_in_worktree():
    """Edit is allowed inside a worktree path."""
    payload = _make_guard_payload("Edit", WORKTREE_CWD)
    assert _run_guard(payload) == 0


def test_guard_bash_allowed_in_worktree():
    """Bash is allowed inside a worktree path."""
    payload = _make_guard_payload("Bash", WORKTREE_CWD)
    assert _run_guard(payload) == 0


def test_guard_enter_worktree_always_allowed_in_main_repo():
    """EnterWorktree is the rescue command — must never be blocked."""
    payload = _make_guard_payload("EnterWorktree", MAIN_CWD)
    assert _run_guard(payload) == 0


def test_guard_missing_session_id_allows():
    """Missing session_id → fail-safe allow."""
    payload = {"session_id": "", "cwd": MAIN_CWD, "tool_name": "Edit", "tool_input": {}}
    assert _run_guard(payload) == 0


def test_guard_missing_cwd_allows():
    """Missing cwd → fail-safe allow."""
    payload = {"session_id": "sess-abc", "cwd": "", "tool_name": "Edit", "tool_input": {}}
    assert _run_guard(payload) == 0


def test_guard_override_token_bypasses_block(tmp_path, monkeypatch):
    """Valid override token bypasses the main-repo block."""
    monkeypatch.setattr(ssg, "_has_override_token", lambda: True)
    payload = _make_guard_payload("Edit", MAIN_CWD)
    assert _run_guard(payload) == 0


# ===========================================================================
# Issue #106 — Session-Register: agent_name, cwd/branch/worktree, issue/phase,
# Dauerlaeufer-Fix (Spec: docs/specs/feat-106-session-register.md)
#
# Alle Tests unterhalb dieser Linie sind NEU (TDD RED). Die 19 Bestandstests
# oberhalb bleiben unveraendert (AC-14).
#
# Hermetik-Regeln fuer diese Testgruppe:
#   * Lock-Verzeichnis IMMER per monkeypatch auf tmp_path (nie das echte
#     .claude/session-locks/ dieses Repos beschreiben).
#   * Harness-Register IMMER ueber HOME=tmp_path/home isoliert. Der Lookup
#     muss das Home-Verzeichnis zur Aufrufzeit aufloesen (Path.home() /
#     os.path.expanduser), nicht beim Import cachen — sonst schreibt der
#     Testlauf in ~/.claude/sessions/ echter Server-Sessions.
# ===========================================================================

import hook_utils


def _patch_project_root(monkeypatch, root: Path) -> None:
    """find_project_root auf tmp_path pinnen — an beiden moeglichen Bindungen.

    Die Implementierung darf hook_utils.find_project_root sowohl lokal in der
    Funktion importieren (heutiges Muster in _locks_dir) als auch modulweit
    binden; beide Varianten werden hier abgedeckt.
    """
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: root)
    monkeypatch.setattr(ssg, "find_project_root", lambda: root, raising=False)


def _patch_active_workflow(monkeypatch, name: str, source: str = "file") -> None:
    """resolve_active_workflow pinnen — an beiden moeglichen Bindungen."""
    monkeypatch.setattr(hook_utils, "resolve_active_workflow", lambda: (name, source))
    monkeypatch.setattr(ssg, "resolve_active_workflow", lambda: (name, source), raising=False)


def _isolate_harness_home(monkeypatch, tmp_path: Path) -> Path:
    """Legt ein leeres Harness-Sessions-Verzeichnis unter tmp_path an.

    Gibt das Verzeichnis zurueck (Tests legen dort ihre Fixture-Dateien ab).
    """
    home = tmp_path / "home"
    sessions = home / ".claude" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("USERPROFILE", raising=False)
    return sessions


def _heartbeat_env(monkeypatch, tmp_path: Path, workflow=("", "none")):
    """Vollstaendig hermetische Umgebung fuer Heartbeat-Tests.

    Returns (locks_dir, harness_sessions_dir).
    """
    monkeypatch.setattr(ssg, "_has_override_token", lambda: False)
    locks = tmp_path / ".claude" / "session-locks"
    locks.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ssg, "_locks_dir", lambda: locks)
    _patch_project_root(monkeypatch, tmp_path)
    _patch_active_workflow(monkeypatch, workflow[0], workflow[1])
    sessions = _isolate_harness_home(monkeypatch, tmp_path)
    return locks, sessions


def _write_lock(locks: Path, session_id: str = "sess-abc", **fields) -> Path:
    """Schreibt einen Registereintrag. Bestandsfelder als Default, per
    kwargs ueberschreibbar; optionale Felder nur wenn explizit uebergeben."""
    now = time.time()
    entry = {
        "session_id": session_id,
        "cwd": MAIN_CWD,
        "pid": 999999999,          # tote Shell-PID, wie im Realbetrieb
        "started_at": now,
        "last_seen": now,
    }
    entry.update(fields)
    path = locks / f"{ssg._safe_sid(session_id)}.json"
    path.write_text(json.dumps(entry))
    return path


def _write_workflow_state(root: Path, name: str, phase: str) -> Path:
    wf_dir = root / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    path = wf_dir / f"{name}.json"
    path.write_text(json.dumps({"name": name, "current_phase": phase}))
    return path


# ---------------------------------------------------------------------------
# Test 1/2/5 — Heartbeat laeuft VOR Worktree- und Tool-Filter-Ausstieg
# ---------------------------------------------------------------------------

def test_heartbeat_updates_last_seen_in_worktree(tmp_path, monkeypatch):
    """Test 1 (AC-2/AC-4): Heartbeat feuert auch in einer Worktree-Session.

    Ist-Zustand: der Worktree-Ausstieg (sys.exit(0)) greift vor dem
    Heartbeat-Block — last_seen bleibt unveraendert.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    old = time.time() - 120
    lock = _write_lock(locks, last_seen=old, started_at=old,
                       agent_name="agent-os-openspec-9a")

    before = time.time()
    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert entry["last_seen"] >= before, (
        "last_seen nicht aktualisiert — Heartbeat steht noch hinter dem "
        "Worktree-Ausstieg"
    )


def test_heartbeat_fires_for_non_blocking_tool(tmp_path, monkeypatch):
    """Test 2 (AC-5): Auch lesende Tools (Read) muessen den Heartbeat ausloesen."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    old = time.time() - 120
    lock = _write_lock(locks, last_seen=old, started_at=old,
                       agent_name="agent-os-openspec-9a")

    before = time.time()
    assert _run_guard(_make_guard_payload("Read", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert entry["last_seen"] >= before, (
        "last_seen nicht aktualisiert — Heartbeat steht noch hinter dem "
        "Tool-Filter-Ausstieg"
    )


def test_long_running_session_survives_reap(tmp_path, monkeypatch):
    """Test 5 (AC-4, Kernbeweis): Dauerlaeufer wird nicht mehr weggeraeumt.

    started_at aelter als _STALE_SECONDS, PID tot, last_seen initial stale.
    Ein zwischenzeitlicher guard-Aufruf muss last_seen auffrischen, sodass
    _reap_dead den Eintrag stehen laesst.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    stale = time.time() - (ssg._STALE_SECONDS + 600)
    lock = _write_lock(locks, session_id="sess-long", started_at=stale,
                       last_seen=stale, pid=999999999)

    assert _run_guard(_make_guard_payload("Read", WORKTREE_CWD, "sess-long")) == 0

    alive = ssg._reap_dead(ssg._read_entries(locks), time.time())
    assert "sess-long" in alive, "Dauerlaeufer-Session faelschlich als tot erkannt"
    assert lock.exists(), "Lock-Datei einer aktiven Dauerlaeufer-Session geloescht"


# ---------------------------------------------------------------------------
# Test 3 — Throttle
# ---------------------------------------------------------------------------

def test_heartbeat_throttled_within_60s(tmp_path, monkeypatch):
    """Test 3 (AC-6): Innerhalb des Throttle-Fensters wird nicht geschrieben.

    Das Fensteralter wird bewusst aus `_HEARTBEAT_THROTTLE_SECONDS` abgeleitet
    statt hart auf 10s gesetzt: sonst waere der Test schon gegen den Ist-Code
    gruen (dort schreibt der guard in einer Worktree-Session ueberhaupt nie)
    und wuerde die neue Throttle-Mechanik gar nicht pruefen.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    assert ssg._HEARTBEAT_THROTTLE_SECONDS == 60, "Default-Throttle laut Spec: 60s"
    now = time.time()
    age = ssg._HEARTBEAT_THROTTLE_SECONDS / 6.0     # deutlich innerhalb des Fensters
    lock = _write_lock(locks, last_seen=now - age, started_at=now - age,
                       agent_name="agent-os-openspec-9a")
    content_before = lock.read_text()
    mtime_before = lock.stat().st_mtime_ns

    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    assert lock.read_text() == content_before, "Eintrag im Throttle-Fenster veraendert"
    assert lock.stat().st_mtime_ns == mtime_before, (
        "Lock-Datei im Throttle-Fenster neu geschrieben (unnoetige I/O im Hot-Path)"
    )


# ---------------------------------------------------------------------------
# Test 4 — cwd/worktree werden nachgefuehrt
# ---------------------------------------------------------------------------

def test_heartbeat_updates_cwd_and_worktree(tmp_path, monkeypatch):
    """Test 4 (AC-2): cwd wird auf den aktuellen Worktree-Pfad nachgezogen."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    old = time.time() - 120
    lock = _write_lock(locks, cwd=MAIN_CWD, last_seen=old, started_at=old,
                       agent_name="agent-os-openspec-9a")

    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert entry["cwd"] == WORKTREE_CWD, "cwd eingefroren auf dem Hauptverzeichnis"
    assert entry["worktree"] == "my-feature"


# ---------------------------------------------------------------------------
# Test 6/13/14 — workflow / issue / phase
# ---------------------------------------------------------------------------

def test_heartbeat_updates_issue_and_phase(tmp_path, monkeypatch):
    """Test 6 (AC-3): workflow, issue und phase landen im Eintrag."""
    locks, _ = _heartbeat_env(
        monkeypatch, tmp_path, workflow=("feat-106-session-register", "file")
    )
    _write_workflow_state(tmp_path, "feat-106-session-register", "phase3_spec")
    old = time.time() - 120
    lock = _write_lock(locks, last_seen=old, started_at=old,
                       agent_name="agent-os-openspec-9a")

    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert entry["workflow"] == "feat-106-session-register"
    assert entry["issue"] == "106"
    assert entry["phase"] == "phase3_spec"


def test_workflow_name_without_digits_has_no_issue(tmp_path, monkeypatch):
    """Test 13 (AC-9): Workflow-Name ohne Ziffer → workflow ja, issue nein."""
    assert ssg._extract_issue_number("retro-cleanup") is None
    assert ssg._extract_issue_number("feat-106-session-register") == "106"

    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("retro-cleanup", "file"))
    _write_workflow_state(tmp_path, "retro-cleanup", "phase2_analyse")
    old = time.time() - 120
    lock = _write_lock(locks, last_seen=old, started_at=old,
                       agent_name="agent-os-openspec-9a")

    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert entry["workflow"] == "retro-cleanup"
    assert "issue" not in entry, "Ziffernlose Workflow-Namen duerfen kein issue setzen"


def test_no_active_workflow_leaves_fields_absent(tmp_path, monkeypatch):
    """Test 14 (AC-10): Kein aktiver Workflow → keine der drei Felder, kein Crash."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("", "none"))
    old = time.time() - 120
    lock = _write_lock(locks, last_seen=old, started_at=old,
                       agent_name="agent-os-openspec-9a")

    before = time.time()
    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert entry["last_seen"] >= before, "Heartbeat lief nicht"
    assert "workflow" not in entry
    assert "phase" not in entry
    assert "issue" not in entry


# ---------------------------------------------------------------------------
# Test 7/12 — _do_register mit Harness-Lookup
# ---------------------------------------------------------------------------

def _run_register(payload: dict) -> int:
    try:
        ssg._do_register(payload)
        return 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0


def test_register_writes_agent_name_from_harness(tmp_path, monkeypatch):
    """Test 7 (AC-1, Kernbeweis): agent_name kommt exakt aus dem Harness-Eintrag."""
    locks, sessions = _heartbeat_env(monkeypatch, tmp_path)
    (sessions / "12345.json").write_text(json.dumps({
        "sessionId": "sess-abc",
        "name": "agent-os-openspec-9a",
        "nameSource": "derived",
    }))

    assert _run_register({"session_id": "sess-abc", "cwd": WORKTREE_CWD}) == 0

    entry = json.loads((locks / "sess-abc.json").read_text())
    assert entry["agent_name"] == "agent-os-openspec-9a"


def test_register_survives_exploding_harness_lookup(tmp_path, monkeypatch):
    """Test 12 (AC-8): Wirft der Harness-Lookup, bleibt register vollstaendig intakt."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)

    def boom(session_id):
        raise RuntimeError("harness format changed")

    monkeypatch.setattr(ssg, "_harness_agent_name", boom)

    assert _run_register({"session_id": "sess-abc", "cwd": WORKTREE_CWD}) == 0

    entry = json.loads((locks / "sess-abc.json").read_text())
    assert entry["session_id"] == "sess-abc"
    assert entry["cwd"] == WORKTREE_CWD
    assert isinstance(entry["pid"], int)
    assert isinstance(entry["started_at"], (int, float))
    assert isinstance(entry["last_seen"], (int, float))
    assert "agent_name" not in entry


# ---------------------------------------------------------------------------
# Test 8-11 — _harness_agent_name Fail-Safe-Varianten (AC-7)
# ---------------------------------------------------------------------------

def test_harness_lookup_missing_directory(tmp_path, monkeypatch):
    """Test 8: Sessions-Verzeichnis fehlt → None, keine Exception."""
    home = tmp_path / "empty-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("USERPROFILE", raising=False)

    assert ssg._harness_agent_name("sess-abc") is None


def test_harness_lookup_broken_json_continues_scan(tmp_path, monkeypatch):
    """Test 9: Kaputte JSON-Datei → None; der Scan bricht nicht ab."""
    sessions = _isolate_harness_home(monkeypatch, tmp_path)
    (sessions / "broken.json").write_text("{ this is not json")

    assert ssg._harness_agent_name("sess-abc") is None

    (sessions / "good.json").write_text(json.dumps({
        "sessionId": "sess-abc", "name": "agent-os-openspec-9a"
    }))
    assert ssg._harness_agent_name("sess-abc") == "agent-os-openspec-9a", (
        "Scan bricht bei der kaputten Datei ab statt weiterzusuchen"
    )


def test_harness_lookup_missing_name_field(tmp_path, monkeypatch):
    """Test 10: Treffer ohne name-Feld → None."""
    sessions = _isolate_harness_home(monkeypatch, tmp_path)
    (sessions / "noname.json").write_text(json.dumps({"sessionId": "sess-abc"}))

    assert ssg._harness_agent_name("sess-abc") is None


def test_harness_lookup_no_match(tmp_path, monkeypatch):
    """Test 11: Keine Datei matcht die session_id → None."""
    sessions = _isolate_harness_home(monkeypatch, tmp_path)
    (sessions / "a.json").write_text(json.dumps({"sessionId": "other-1", "name": "x"}))
    (sessions / "b.json").write_text(json.dumps({"sessionId": "other-2", "name": "y"}))

    assert ssg._harness_agent_name("sess-abc") is None


# ---------------------------------------------------------------------------
# Test 15 — fehlende Lock-Datei: Re-Register statt Nichts-Tun
#
# UMGESCHRIEBEN durch fix-120-121-session-register (AC-38). Vormals
# `test_guard_without_lock_file_creates_nothing` mit der Erwartung "der guard
# legt NIEMALS Eintraege an" (feat-106 AC-11). Diese Erwartung ist durch A2
# bewusst ueberholt: eine lebende Session, deren Lock-Datei verloren ging,
# muss ueber den Heartbeat zurueck ins Register finden — sonst ist sie fuer
# jede andere Session unsichtbar. Siehe docs/specs/feat-106-session-register.md
# AC-11 (dort als ueberholt markiert).
# ---------------------------------------------------------------------------

def test_guard_without_lock_file_reregisters(tmp_path, monkeypatch):
    """Test 15 (AC-14/AC-38): fehlende Lock-Datei → guard legt sie neu an."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    lock = locks / "sess-abc.json"
    assert not lock.exists()

    assert _run_guard(_make_guard_payload("Read", WORKTREE_CWD)) == 0
    assert lock.exists(), "guard hat die fehlende Lock-Datei nicht neu angelegt"

    entry = json.loads(lock.read_text())
    assert entry["session_id"] == "sess-abc"
    assert entry["reregistered"] is True, (
        "Re-Register nicht als solcher gekennzeichnet — ein zurueckgesetztes "
        "started_at saehe sonst wie ein echter Sessionstart aus"
    )

    # Auch der Block-Pfad (Haupt-Repo) darf den Eintrag nicht verhindern:
    # der Heartbeat laeuft vor allen Ausstiegspfaden.
    lock.unlink()
    assert _run_guard(_make_guard_payload("Edit", MAIN_CWD)) == 2
    assert lock.exists(), "Re-Register unterbleibt auf dem Block-Pfad"


# ---------------------------------------------------------------------------
# Test 17/18/18b — lazy agent_name-Nachfuehrung + Hot-Path-Schutz
# ---------------------------------------------------------------------------

def test_guard_backfills_agent_name_despite_throttle(tmp_path, monkeypatch):
    """Test 17 (AC-15, Richtung 1): fehlendes agent_name wird lazy nachgezogen —
    unabhaengig vom 60s-Throttle, aber innerhalb des 60s-Zeitdeckels (AC-16)."""
    locks, sessions = _heartbeat_env(monkeypatch, tmp_path)
    now = time.time()
    lock = _write_lock(locks, last_seen=now - 5, started_at=now - 5)  # kein agent_name
    (sessions / "12345.json").write_text(json.dumps({
        "sessionId": "sess-abc", "name": "agent-os-openspec-9a"
    }))

    assert _run_guard(_make_guard_payload("Read", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert entry["agent_name"] == "agent-os-openspec-9a"


def test_guard_skips_harness_scan_when_agent_name_present(tmp_path, monkeypatch):
    """Test 18 (AC-15, Richtung 2): gesetztes agent_name → kein Verzeichnis-Scan."""
    locks, sessions = _heartbeat_env(monkeypatch, tmp_path)
    (sessions / "12345.json").write_text(json.dumps({
        "sessionId": "sess-abc", "name": "agent-os-openspec-9a"
    }))
    calls = []

    def spy(session_id):
        calls.append(session_id)
        return "should-not-be-used"

    monkeypatch.setattr(ssg, "_harness_agent_name", spy)

    now = time.time()
    _write_lock(locks, last_seen=now - 120, started_at=now - 120,
                agent_name="agent-os-openspec-9a")

    assert _run_guard(_make_guard_payload("Read", WORKTREE_CWD)) == 0
    assert calls == [], "Harness-Scan trotz gesetztem agent_name (Hot-Path-Leck)"


def test_guard_skips_harness_scan_after_first_minute(tmp_path, monkeypatch):
    """Test 18b (AC-16): Zeitdeckel — nach 60s Session-Laufzeit kein Scan mehr,
    auch wenn agent_name fehlt und eine passende Harness-Datei existiert."""
    locks, sessions = _heartbeat_env(monkeypatch, tmp_path)
    (sessions / "12345.json").write_text(json.dumps({
        "sessionId": "sess-abc", "name": "agent-os-openspec-9a"
    }))
    calls = []

    def spy(session_id):
        calls.append(session_id)
        return "agent-os-openspec-9a"

    monkeypatch.setattr(ssg, "_harness_agent_name", spy)

    now = time.time()
    lock = _write_lock(locks, last_seen=now - 120, started_at=now - 120)  # kein agent_name

    before = time.time()
    assert _run_guard(_make_guard_payload("Read", WORKTREE_CWD)) == 0
    assert calls == [], "Zeitdeckel greift nicht — Dauer-Scan im Hot-Path"

    entry = json.loads(lock.read_text())
    assert entry["last_seen"] >= before, "Heartbeat lief nicht"
    assert "agent_name" not in entry


# ===========================================================================
# fix-120-121-session-register — Block A: Liveness + Re-Register (#120)
#
# Hermetik-Regeln wie oben: Lock-Verzeichnis immer auf tmp_path, HOME immer
# isoliert. Zusaetzlich neu: os.kill wird in diesen Tests gemockt — kein Test
# darf ein Signal an einen echten fremden Prozess senden.
# ===========================================================================

import os


class _KillSpy:
    """Ersatz fuer os.kill: zeichnet Aufrufe auf und spielt ein Ergebnis vor."""

    def __init__(self, raises: "BaseException | None" = None):
        self.calls: list = []
        self._raises = raises

    def __call__(self, pid, sig):
        self.calls.append((pid, sig))
        if self._raises is not None:
            raise self._raises
        return None


# ---------------------------------------------------------------------------
# A1 — _pid_alive nutzt os.kill statt /proc  (AC-1 … AC-3, AC-5)
# ---------------------------------------------------------------------------

def test_pid_alive_true_for_running_process(monkeypatch):
    """AC-1: os.kill(pid, 0) ohne Exception → Prozess lebt.

    Bewusst eine PID ohne /proc-Eintrag: der Bestandscode (Path('/proc/<pid>')
    .exists()) liefert hier False, os.kill sagt "lebt". Der Test faellt also
    genau dann, wenn noch die /proc-Pruefung greift.
    """
    spy = _KillSpy()
    monkeypatch.setattr(os, "kill", spy)

    assert ssg._pid_alive(999999999) is True
    assert spy.calls == [(999999999, 0)], "os.kill(pid, 0) wurde nicht konsultiert"


def test_pid_alive_false_on_process_lookup_error(monkeypatch):
    """AC-2: ProcessLookupError → Prozess existiert nicht → False.

    Bewusst die eigene, real existierende PID: der Bestandscode findet
    /proc/<eigene pid> und liefert True. Nur wer os.kill befragt, sieht hier
    das ProcessLookupError.
    """
    spy = _KillSpy(raises=ProcessLookupError())
    monkeypatch.setattr(os, "kill", spy)

    assert ssg._pid_alive(os.getpid()) is False
    assert spy.calls, "os.kill(pid, 0) wurde nicht konsultiert"


def test_pid_alive_true_on_permission_error(monkeypatch):
    """AC-3: PermissionError → Prozess existiert (fremder User) → True."""
    spy = _KillSpy(raises=PermissionError())
    monkeypatch.setattr(os, "kill", spy)

    assert ssg._pid_alive(999999999) is True, (
        "PermissionError bedeutet 'Prozess existiert, gehoert jemand anderem' — "
        "kein Tot-Signal"
    )


def test_pid_alive_false_on_unexpected_exception(monkeypatch):
    """AC-5: jede andere Exception → False (fail-safe wie im Bestand)."""
    spy = _KillSpy(raises=RuntimeError("boom"))
    monkeypatch.setattr(os, "kill", spy)

    assert ssg._pid_alive(os.getpid()) is False


# ---------------------------------------------------------------------------
# A1 — Prozessgruppen-Schutz (M2, AC-4)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_pid", [0, -5, -1, "1234", None, True])
def test_is_alive_never_signals_invalid_pid(monkeypatch, bad_pid):
    """AC-4: pid <= 0, kein int oder bool → _pid_alive wird gar nicht erst
    aufgerufen, es wird auf last_seen zurueckgefallen.

    os.kill(0, 0) adressiert die GESAMTE Prozessgruppe des Aufrufers,
    negative Werte eine fremde Prozessgruppe. Beides muss ausgeschlossen sein,
    bevor os.kill ueberhaupt erreicht wird — die Validierung gehoert nach
    _is_alive (Aufrufer-Verantwortung), nicht in _pid_alive.
    """
    calls = []
    monkeypatch.setattr(ssg, "_pid_alive", lambda pid: calls.append(pid) or True)

    now = time.time()
    entry = {"pid": bad_pid, "last_seen": now - 9999}

    assert ssg._is_alive(entry, now) is False, "stale last_seen muss entscheiden"
    assert calls == [], f"_pid_alive mit unzulaessiger PID {bad_pid!r} aufgerufen"


def test_is_alive_invalid_pid_still_honours_fresh_last_seen(monkeypatch):
    """AC-4 (Gegenprobe): unzulaessige PID + frisches last_seen → lebt."""
    monkeypatch.setattr(ssg, "_pid_alive", lambda pid: pytest.fail(
        "_pid_alive darf bei pid=0 nicht aufgerufen werden"))

    now = time.time()
    assert ssg._is_alive({"pid": 0, "last_seen": now - 10}, now) is True


# ---------------------------------------------------------------------------
# A1 — stabile PID-Quelle CLAUDE_PID  (AC-6, AC-7)
# ---------------------------------------------------------------------------

def _register_payload(session_id: str = "sess-abc", cwd: str = WORKTREE_CWD) -> dict:
    return {"session_id": session_id, "cwd": cwd}


def test_register_uses_claude_pid_when_plausible(tmp_path, monkeypatch):
    """AC-6: CLAUDE_PID gesetzt und plausibel → landet als pid im Eintrag.

    os.getppid() ist die transiente Hook-Shell und stirbt sofort nach dem
    Hook — das ist die Wurzel von #120. CLAUDE_PID ist die stabile Quelle.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    monkeypatch.setenv("CLAUDE_PID", "424242")

    assert _run_register(_register_payload()) == 0

    entry = json.loads((locks / "sess-abc.json").read_text())
    assert entry["pid"] == 424242, "CLAUDE_PID nicht als PID-Quelle genutzt"


@pytest.mark.parametrize("raw", ["", "0", "-5", "abc", "12.5", "  "])
def test_register_falls_back_to_getppid_for_implausible_claude_pid(
    tmp_path, monkeypatch, raw
):
    """AC-7 / EB-2: unplausibler CLAUDE_PID → unveraendert os.getppid()."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    monkeypatch.setenv("CLAUDE_PID", raw)

    assert _run_register(_register_payload()) == 0

    entry = json.loads((locks / "sess-abc.json").read_text())
    assert entry["pid"] == os.getppid(), f"CLAUDE_PID={raw!r} nicht verworfen"


def test_register_falls_back_to_getppid_without_claude_pid(tmp_path, monkeypatch):
    """AC-7 / EB-1: CLAUDE_PID fehlt komplett → Bestandsverhalten."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    monkeypatch.delenv("CLAUDE_PID", raising=False)

    assert _run_register(_register_payload()) == 0

    entry = json.loads((locks / "sess-abc.json").read_text())
    assert entry["pid"] == os.getppid()


# ---------------------------------------------------------------------------
# A1 — boot_id: Schutz gegen PID-Recycling  (AC-8 … AC-12)
# ---------------------------------------------------------------------------

def test_register_stores_boot_id_when_readable(tmp_path, monkeypatch):
    """AC-8: lesbare boot_id → Feld landet im Eintrag."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    monkeypatch.setattr(ssg, "_read_boot_id", lambda: "boot-aaaa")

    assert _run_register(_register_payload()) == 0

    entry = json.loads((locks / "sess-abc.json").read_text())
    assert entry["boot_id"] == "boot-aaaa"


def test_register_omits_boot_id_when_unreadable(tmp_path, monkeypatch):
    """AC-9 / EB-3: boot_id nicht lesbar → Feld fehlt, kein Fehler."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    monkeypatch.setattr(ssg, "_read_boot_id", lambda: None)

    assert _run_register(_register_payload()) == 0

    entry = json.loads((locks / "sess-abc.json").read_text())
    assert "boot_id" not in entry, "None darf nicht als Wert gespeichert werden"


def test_read_boot_id_survives_missing_file(monkeypatch):
    """AC-9 / EB-3: _read_boot_id ist vollstaendig fail-safe (macOS/Windows)."""
    def explode(*_a, **_kw):
        raise OSError("no /proc on this platform")

    monkeypatch.setattr(Path, "read_text", explode)
    assert ssg._read_boot_id() is None


def test_is_alive_distrusts_pid_after_reboot(monkeypatch):
    """AC-10 / EB-4: gespeicherte boot_id != aktuelle → PID-Pruefung verworfen.

    Nach einem Reboot kann die gespeicherte PID von einem voellig fremden
    Prozess recycelt worden sein. Eine 'lebende' PID beweist dann nichts —
    allein last_seen entscheidet.
    """
    monkeypatch.setattr(ssg, "_read_boot_id", lambda: "boot-neu")
    monkeypatch.setattr(ssg, "_pid_alive", lambda pid: True)

    now = time.time()
    entry = {"pid": 4242, "boot_id": "boot-alt", "last_seen": now - 9999}

    assert ssg._is_alive(entry, now) is False, (
        "PID-Recycling nach Reboot nicht erkannt — tote Session wird als "
        "lebend gefuehrt"
    )


def test_is_alive_after_reboot_still_honours_fresh_last_seen(monkeypatch):
    """AC-10 (Gegenprobe): abweichende boot_id + frisches last_seen → lebt."""
    monkeypatch.setattr(ssg, "_read_boot_id", lambda: "boot-neu")
    monkeypatch.setattr(ssg, "_pid_alive", lambda pid: False)

    now = time.time()
    entry = {"pid": 4242, "boot_id": "boot-alt", "last_seen": now - 10}

    assert ssg._is_alive(entry, now) is True


def test_is_alive_without_stored_boot_id_trusts_pid(monkeypatch):
    """AC-11: Bestands-Lock-Datei ohne boot_id → kein Misstrauen.

    Rueckwaertskompatibilitaet: Eintraege, die vor diesem Fix geschrieben
    wurden, haben kein boot_id-Feld und muessen unveraendert weiterlaufen.
    """
    monkeypatch.setattr(ssg, "_read_boot_id", lambda: "boot-neu")
    monkeypatch.setattr(ssg, "_pid_alive", lambda pid: True)

    now = time.time()
    entry = {"pid": 4242, "last_seen": now - 9999}  # stale, aber PID lebt

    assert ssg._is_alive(entry, now) is True


def test_is_alive_without_current_boot_id_trusts_pid(monkeypatch):
    """AC-12 / EB-3: aktuelle boot_id nicht lesbar → kein Vergleich moeglich,
    kein Misstrauen (Plattform ohne /proc)."""
    monkeypatch.setattr(ssg, "_read_boot_id", lambda: None)
    monkeypatch.setattr(ssg, "_pid_alive", lambda pid: True)

    now = time.time()
    entry = {"pid": 4242, "boot_id": "boot-alt", "last_seen": now - 9999}

    assert ssg._is_alive(entry, now) is True


def test_is_alive_same_boot_id_trusts_pid(monkeypatch):
    """AC-11 (Normalfall): identische boot_id → PID-Pruefung greift regulaer."""
    monkeypatch.setattr(ssg, "_read_boot_id", lambda: "boot-gleich")
    monkeypatch.setattr(ssg, "_pid_alive", lambda pid: True)

    now = time.time()
    entry = {"pid": 4242, "boot_id": "boot-gleich", "last_seen": now - 9999}

    assert ssg._is_alive(entry, now) is True


# ---------------------------------------------------------------------------
# A1 — echte Leichen werden weiterhin gereapt  (AC-13)
# ---------------------------------------------------------------------------

def test_reap_still_removes_genuinely_dead_foreign_session(tmp_path, monkeypatch):
    """AC-13: A1 darf keine tote Session kuenstlich am Leben halten.

    Fremder Eintrag mit wirklich toter PID UND stale last_seen → wird beim
    naechsten guard-Aufruf einer anderen Session regulaer entfernt.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    monkeypatch.setattr(ssg, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(ssg, "_read_boot_id", lambda: None)

    stale = time.time() - 9999
    foreign = _write_lock(locks, session_id="sess-tot",
                          started_at=stale, last_seen=stale)
    assert foreign.exists()

    assert _run_register(_register_payload("sess-abc")) == 0

    assert not foreign.exists(), (
        "Wirklich tote Fremdsession nicht gereapt — A1 haelt Leichen am Leben"
    )


# ---------------------------------------------------------------------------
# A2 — Re-Register-Sicherheitsnetz im Heartbeat  (AC-14 … AC-17)
# ---------------------------------------------------------------------------

def _count_lock_writes(monkeypatch, locks: Path) -> list:
    """Zaehlt write_text-Aufrufe unterhalb von `locks`. Gibt die Liste der
    geschriebenen Pfade zurueck (Laenge == Anzahl Schreibvorgaenge)."""
    written: list = []
    original = Path.write_text

    def spy(self, *args, **kwargs):
        try:
            if locks in self.parents:
                written.append(self)
        except Exception:
            pass
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", spy)
    return written


def test_heartbeat_recreates_missing_lock_file(tmp_path, monkeypatch):
    """AC-14: eigene Lock-Datei extern geloescht → Heartbeat legt sie neu an.

    Wurzel von #120: bisher stieg _heartbeat bei fehlender Datei mit `return`
    aus — eine einmal gereapte Session kam nie zurueck ins Register.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path,
                              workflow=("fix-120-121-session-register", "file"))
    lock = locks / "sess-abc.json"
    assert not lock.exists()

    before = time.time()
    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    assert lock.exists(), "Heartbeat hat die fehlende Lock-Datei nicht neu angelegt"
    entry = json.loads(lock.read_text())
    assert entry["session_id"] == "sess-abc"
    assert entry["cwd"] == WORKTREE_CWD
    assert entry["reregistered"] is True
    assert entry["started_at"] >= before, (
        "started_at ist nach einem Reap nicht rekonstruierbar und muss auf "
        "'jetzt' gesetzt werden"
    )
    assert entry["last_seen"] >= before
    # Kontextfelder werden auch im Re-Register-Zweig angereichert.
    assert entry["worktree"] == "my-feature"
    assert entry["workflow"] == "fix-120-121-session-register"


def test_heartbeat_reregister_writes_exactly_once(tmp_path, monkeypatch):
    """AC-15: der Re-Register-Zweig loest genau EINEN Schreibvorgang aus.

    PreToolUse-Hot-Path: ein zweiter Write durch den nachgelagerten
    Throttle-Zweig im selben Aufruf waere verdoppelte I/O.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    written = _count_lock_writes(monkeypatch, locks)

    assert _run_guard(_make_guard_payload("Read", WORKTREE_CWD)) == 0

    assert len(written) == 1, (
        f"{len(written)} Schreibvorgaenge im Re-Register-Zweig statt genau 1"
    )


def test_heartbeat_throttle_survives_reregister_branch(tmp_path, monkeypatch):
    """AC-16: vorhandene, frische Lock-Datei → kein Write (Throttle unangetastet).

    Der neue Re-Register-Zweig darf den 60s-Throttle nicht aushebeln; er greift
    ausschliesslich, wenn die Datei FEHLT.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    now = time.time()
    _write_lock(locks, last_seen=now - 5, started_at=now - 5,
                agent_name="agent-os-openspec-9a")
    written = _count_lock_writes(monkeypatch, locks)

    assert _run_guard(_make_guard_payload("Read", WORKTREE_CWD)) == 0
    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    assert written == [], (
        "Schreibvorgang trotz frischem last_seen — Throttle ausgehebelt"
    )


def test_build_entry_is_the_single_source_for_both_paths(tmp_path, monkeypatch):
    """AC-17: register und Re-Register erzeugen denselben Eintragstyp.

    Beide Wege muessen ueber _build_entry() laufen, sonst driften die
    Pflichtfelder zwischen zwei Entstehungswegen auseinander.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    calls: list = []
    original = ssg._build_entry

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(ssg, "_build_entry", spy)

    assert _run_register(_register_payload("sess-reg")) == 0
    registered = json.loads((locks / "sess-reg.json").read_text())

    assert _run_guard(_make_guard_payload("Read", WORKTREE_CWD, "sess-hb")) == 0
    reregistered = json.loads((locks / "sess-hb.json").read_text())

    assert len(calls) == 2, "_build_entry nicht von beiden Aufrufstellen genutzt"

    required = {"session_id", "cwd", "pid", "started_at", "last_seen"}
    assert required <= set(registered), f"register: fehlend {required - set(registered)}"
    assert required <= set(reregistered), (
        f"re-register: fehlend {required - set(reregistered)}"
    )
    assert registered.get("reregistered") is None, (
        "echter Sessionstart darf nicht als reregistered markiert werden"
    )
    assert reregistered.get("reregistered") is True


# ===========================================================================
# fix-120-121-session-register — Block B: Issue-Claim (#121)
#
# /00-intake #N kennt die Issue-Nummer ab Sekunde eins. Bisher wird sie
# stattdessen aus dem Workflow-Namen erraten (erste Ziffernfolge) — bei
# mehreren Issues pro Workflow oder Namen ohne fuehrende Nummer liefert das
# falsche oder gar keine Werte.
# ===========================================================================

import shutil
import subprocess

import config_loader


def _run_claim(argv: list) -> int:
    """Fuehrt _do_claim aus und liefert den Exit-Code."""
    try:
        ssg._do_claim(argv)
        return 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0


def _no_tmux(monkeypatch) -> None:
    """tmux-Nebenwirkung fuer Claim-Tests abschalten, die sie nicht pruefen."""
    monkeypatch.delenv("TMUX", raising=False)


# ---------------------------------------------------------------------------
# B1 — Eingabevalidierung  (AC-23, AC-24)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["120", "120,121", "1,2,3", "42"])
def test_validate_issue_arg_accepts_digits_and_commas(raw):
    """AC-23: nur Ziffern und Kommas → unveraendert uebernommen."""
    assert ssg._validate_issue_arg(raw) == raw


@pytest.mark.parametrize("raw", [
    "120; rm -rf /", "abc", "12.3", "", "  ", "#120", "120 121",
    "$(id)", "120|cat", "-1",
])
def test_validate_issue_arg_rejects_everything_else(raw):
    """AC-24 / EB-7: alles andere → None (Ablehnung).

    Der Wert landet spaeter in einem tmux-Kommando — Shell-Metazeichen und
    Leerzeichen duerfen hier nicht durchkommen.
    """
    assert ssg._validate_issue_arg(raw) is None


def test_claim_rejects_invalid_issue_without_touching_files(
    tmp_path, monkeypatch, capsys
):
    """AC-24 / EB-7: ungueltiger Wert → Meldung, kein Write, Exit 0."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    _no_tmux(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-abc")
    lock = _write_lock(locks)
    before = lock.read_text()

    assert _run_claim(["--issue", "120; rm -rf /"]) == 0

    assert lock.read_text() == before, "Eintrag trotz ungueltigem --issue veraendert"
    assert capsys.readouterr().out.strip(), "keine verstaendliche Meldung ausgegeben"


def test_claim_without_issue_argument_is_a_noop(tmp_path, monkeypatch, capsys):
    """AC-24: fehlendes --issue → Meldung, kein Write, Exit 0."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    _no_tmux(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-abc")
    lock = _write_lock(locks)
    before = lock.read_text()

    assert _run_claim([]) == 0

    assert lock.read_text() == before
    assert capsys.readouterr().out.strip()


# ---------------------------------------------------------------------------
# B1 — Zielfindung und Schreiben  (AC-19 … AC-22)
# ---------------------------------------------------------------------------

def test_claim_writes_fields_for_session_from_env(tmp_path, monkeypatch):
    """AC-19: CLAUDE_CODE_SESSION_ID trifft einen Eintrag → Claim-Felder gesetzt.

    Der Live-Befund dieses Workflows: zwei Issues (#120 UND #121), aber das
    Register zeigte per Regex nur '120'. Genau das behebt der Claim.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path,
                              workflow=("fix-120-121-session-register", "file"))
    _no_tmux(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-abc")
    lock = _write_lock(locks, issue="120")

    assert _run_claim(["--issue", "120,121"]) == 0

    entry = json.loads(lock.read_text())
    assert entry["issue"] == "120,121", "Claim hat den Regex-Wert nicht ersetzt"
    assert entry["issue_source"] == "claim"
    assert entry["issue_claim_workflow"] == "fix-120-121-session-register"


def test_claim_records_empty_workflow_when_none_active(tmp_path, monkeypatch):
    """AC-19: kein aktiver Workflow → issue_claim_workflow == ''.

    Der Claim laeuft im /00-intake, also typischerweise VOR dem Workflow-Start.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("", "none"))
    _no_tmux(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-abc")
    lock = _write_lock(locks)

    assert _run_claim(["--issue", "42"]) == 0

    entry = json.loads(lock.read_text())
    assert entry["issue"] == "42"
    assert entry["issue_claim_workflow"] == ""


def test_claim_falls_back_to_unique_cwd_match(tmp_path, monkeypatch):
    """AC-20: ohne Env-Var, aber genau EIN Eintrag mit passendem cwd."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("", "none"))
    _no_tmux(monkeypatch)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.chdir(tmp_path)

    mine = _write_lock(locks, session_id="sess-mine", cwd=str(tmp_path))
    other = _write_lock(locks, session_id="sess-other", cwd="/somewhere/else")

    assert _run_claim(["--issue", "42"]) == 0

    assert json.loads(mine.read_text())["issue"] == "42"
    assert "issue" not in json.loads(other.read_text()), "fremder Eintrag angefasst"


@pytest.mark.parametrize("cwd_matches", [0, 2])
def test_claim_without_unique_target_changes_nothing(
    tmp_path, monkeypatch, capsys, cwd_matches
):
    """AC-21 / EB-8: kein Env-Treffer und 0 oder >=2 cwd-Kandidaten → No-Op."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("", "none"))
    _no_tmux(monkeypatch)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.chdir(tmp_path)

    if cwd_matches == 0:
        _write_lock(locks, session_id="sess-a", cwd="/elsewhere/a")
        _write_lock(locks, session_id="sess-b", cwd="/elsewhere/b")
    else:
        _write_lock(locks, session_id="sess-a", cwd=str(tmp_path))
        _write_lock(locks, session_id="sess-b", cwd=str(tmp_path))

    snapshot = {p.name: p.read_text() for p in locks.glob("*.json")}

    assert _run_claim(["--issue", "42"]) == 0

    assert {p.name: p.read_text() for p in locks.glob("*.json")} == snapshot, (
        f"Eintrag veraendert, obwohl {cwd_matches} cwd-Kandidaten kein "
        "eindeutiges Ziel ergeben"
    )
    assert capsys.readouterr().out.strip(), "keine verstaendliche Meldung ausgegeben"


def test_claim_creates_entry_when_session_has_no_lock_file(tmp_path, monkeypatch):
    """AC-22: Env-Var gesetzt, aber noch kein Eintrag → ueber _build_entry anlegen.

    Nutzt denselben A2-Helper — kein dritter Entstehungsweg fuer Eintraege.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("", "none"))
    _no_tmux(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-neu")
    monkeypatch.chdir(tmp_path)

    calls: list = []
    original = ssg._build_entry
    monkeypatch.setattr(
        ssg, "_build_entry",
        lambda *a, **kw: (calls.append((a, kw)), original(*a, **kw))[1],
    )

    assert _run_claim(["--issue", "42"]) == 0

    lock = locks / "sess-neu.json"
    assert lock.exists(), "kein Eintrag fuer die claimende Session angelegt"
    assert calls, "_build_entry nicht genutzt — dritter Entstehungsweg"

    entry = json.loads(lock.read_text())
    assert entry["session_id"] == "sess-neu"
    assert entry["issue"] == "42"
    assert entry["issue_source"] == "claim"
    assert entry["reregistered"] is True


# ---------------------------------------------------------------------------
# B1 — stdout-Disziplin  (AC-25)
# ---------------------------------------------------------------------------

def test_hook_modes_stay_silent_while_claim_speaks(tmp_path, monkeypatch, capsys):
    """AC-25: register/guard/cleanup schweigen auf stdout, claim nicht.

    Die drei Hook-Modi laufen im PreToolUse/SessionStart-Kontext — jede
    stdout-Ausgabe landet dort im Transcript. `claim` ist dagegen ein direkter
    CLI-Aufruf, bei dem Rueckmeldung gewollt ist.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("", "none"))
    _no_tmux(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-abc")

    assert _run_register(_register_payload("sess-abc")) == 0
    assert _run_guard(_make_guard_payload("Read", WORKTREE_CWD)) == 0
    assert capsys.readouterr().out == "", "Hook-Modus schreibt auf stdout"

    assert _run_claim(["--issue", "42"]) == 0
    assert capsys.readouterr().out.strip(), "claim gibt keine Rueckmeldung"

    ssg_cleanup = {"session_id": "sess-abc"}
    try:
        ssg._do_cleanup(ssg_cleanup)
    except SystemExit:
        pass
    assert capsys.readouterr().out == "", "cleanup schreibt auf stdout"


# ---------------------------------------------------------------------------
# B2 — Claim-Invalidierung  (AC-26 … AC-29, AC-39, AC-40)
#
# Alle Faelle laufen ueber _apply_context_fields, ausgeloest durch den
# Heartbeat. last_seen wird bewusst ausserhalb des 60s-Throttle-Fensters
# gesetzt, damit der Kontext-Zweig ueberhaupt greift.
# ---------------------------------------------------------------------------

def _claimed_lock(locks: Path, *, issue: str, claim_wf: str) -> Path:
    old = time.time() - 120
    return _write_lock(
        locks,
        last_seen=old,
        started_at=old,
        agent_name="agent-os-openspec-9a",
        issue=issue,
        issue_source="claim",
        issue_claim_workflow=claim_wf,
    )


def test_claim_survives_when_no_workflow_ever_active(tmp_path, monkeypatch):
    """AC-26 (Fall 1): claim_wf == '' und weiterhin kein Workflow → alles bleibt."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("", "none"))
    lock = _claimed_lock(locks, issue="120,121", claim_wf="")

    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert entry["issue"] == "120,121", "Claim ohne Anlass verworfen"
    assert entry["issue_source"] == "claim"
    assert entry["issue_claim_workflow"] == ""


def test_claim_adopted_by_matching_workflow(tmp_path, monkeypatch):
    """AC-27 (Fall 2a): erster Workflow passt zur geclaimten Liste → adoptiert."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path,
                              workflow=("fix-120-121-session-register", "file"))
    lock = _claimed_lock(locks, issue="120,121", claim_wf="")

    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert entry["issue"] == "120,121", "issue bei Adoption veraendert"
    assert entry["issue_source"] == "claim"
    assert entry["issue_claim_workflow"] == "fix-120-121-session-register", (
        "Adoption nicht vollzogen — der Claim bleibt sonst dauerhaft heimatlos"
    )


def test_claim_adopted_by_workflow_without_digits(tmp_path, monkeypatch):
    """AC-40 (Fall 2c): Workflow-Name ohne Ziffernfolge → adoptiert.

    Ein nummernloser Name widerspricht dem Claim nicht, und die
    Regex-Ableitung haette hier ohnehin nichts anzubieten.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("retro-cleanup", "file"))
    lock = _claimed_lock(locks, issue="120,121", claim_wf="")

    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert entry["issue"] == "120,121"
    assert entry["issue_claim_workflow"] == "retro-cleanup"


def test_claim_expires_instead_of_being_adopted_by_foreign_workflow(
    tmp_path, monkeypatch
):
    """AC-39 (Fall 2b): erster Workflow gehoert zu einem FREMDEN Issue → verfaellt.

    Ohne diese Pruefung wuerde 'fix-500-xyz' den Claim auf '120' adoptieren.
    Danach stimmen claim_wf und aktueller Workflow ueberein — Fall 4 (Verfall
    bei Abweichung) kann nie mehr greifen und der falsche Wert ist dauerhaft
    eingefroren. Genau das Szenario, gegen das B2 gebaut ist.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("fix-500-xyz", "file"))
    lock = _claimed_lock(locks, issue="120", claim_wf="")

    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert entry["issue"] == "500", (
        "Claim von fremdem Workflow adoptiert statt verfallen — der falsche "
        "Wert waere ab jetzt dauerhaft eingefroren"
    )
    assert "issue_source" not in entry
    assert "issue_claim_workflow" not in entry


def test_claim_holds_while_workflow_unchanged(tmp_path, monkeypatch):
    """AC-28 (Fall 3): claim_wf == aktueller Workflow → Claim gilt weiter.

    Ohne diese Regel wuerde die Regex-Ableitung den Claim bei jedem Heartbeat
    ueberschreiben — '120,121' wuerde zu '120'.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path,
                              workflow=("fix-120-121-session-register", "file"))
    lock = _claimed_lock(locks, issue="120,121",
                         claim_wf="fix-120-121-session-register")

    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert entry["issue"] == "120,121", "Claim vom Regex ueberschrieben"
    assert entry["issue_source"] == "claim"
    assert entry["issue_claim_workflow"] == "fix-120-121-session-register"


def test_claim_expires_on_workflow_switch(tmp_path, monkeypatch):
    """AC-29 (Fall 4): Themenwechsel → Claim verfaellt, Regex uebernimmt."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("fix-500-xyz", "file"))
    lock = _claimed_lock(locks, issue="120,121",
                         claim_wf="fix-120-121-session-register")

    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert entry["issue"] == "500", "Regex-Ableitung nach Claim-Verfall nicht aktiv"
    assert "issue_source" not in entry, "abgelaufener Claim-Marker nicht entfernt"
    assert "issue_claim_workflow" not in entry


def test_claim_expires_to_nothing_when_new_workflow_has_no_digits(
    tmp_path, monkeypatch
):
    """AC-29 (Fall 4, Randfall): neuer Workflow ohne Ziffer → issue faellt weg."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("retro-cleanup", "file"))
    lock = _claimed_lock(locks, issue="120,121",
                         claim_wf="fix-120-121-session-register")

    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert "issue" not in entry
    assert "issue_source" not in entry
    assert "issue_claim_workflow" not in entry


def test_regex_derivation_unchanged_without_claim(tmp_path, monkeypatch):
    """EB-Rueckwaertskompatibilitaet: kein issue_source → Bestandsverhalten.

    Lock-Dateien aus der Zeit vor diesem Fix kennen weder issue_source noch
    issue_claim_workflow und muessen unveraendert weiterlaufen.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path,
                              workflow=("feat-106-session-register", "file"))
    old = time.time() - 120
    lock = _write_lock(locks, last_seen=old, started_at=old,
                       agent_name="agent-os-openspec-9a", issue="999")

    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0

    entry = json.loads(lock.read_text())
    assert entry["issue"] == "106", "Regex-Ableitung ohne Claim veraendert"


# ---------------------------------------------------------------------------
# B3 — tmux-Fenstername  (AC-30 … AC-33)
# ---------------------------------------------------------------------------

class _RunSpy:
    def __init__(self, result=None, raises=None):
        self.calls: list = []
        self._result = result
        self._raises = raises

    def __call__(self, cmd, *args, **kwargs):
        self.calls.append((cmd, kwargs))
        if self._raises is not None:
            raise self._raises
        return self._result


class _Completed:
    def __init__(self, returncode=0):
        self.returncode = returncode


def _tmux_env(monkeypatch, *, in_tmux=True, which="/usr/bin/tmux",
              rename_enabled=True):
    monkeypatch.setattr(shutil, "which", lambda name: which)
    if in_tmux:
        monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1234,0")
    else:
        monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(
        config_loader, "load_config",
        lambda: {"session_register": {"tmux_rename": rename_enabled}},
    )


def test_tmux_window_renamed_on_successful_claim(tmp_path, monkeypatch):
    """AC-30: $TMUX gesetzt, tmux vorhanden, Config nicht abgeschaltet → rename."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("", "none"))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-abc")
    _write_lock(locks)
    _tmux_env(monkeypatch)
    spy = _RunSpy(result=_Completed(0))
    monkeypatch.setattr(subprocess, "run", spy)

    assert _run_claim(["--issue", "120,121"]) == 0

    assert spy.calls, "tmux rename-window nicht aufgerufen"
    cmd, kwargs = spy.calls[0]
    assert cmd == ["tmux", "rename-window", "#120,121"]
    assert kwargs.get("timeout"), "kein Timeout — haengendes tmux blockiert den Hook"


def test_tmux_not_called_outside_tmux(tmp_path, monkeypatch):
    """AC-31: kein $TMUX → tmux wird gar nicht erst aufgerufen."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("", "none"))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-abc")
    lock = _write_lock(locks)
    _tmux_env(monkeypatch, in_tmux=False)
    spy = _RunSpy(result=_Completed(0))
    monkeypatch.setattr(subprocess, "run", spy)

    assert _run_claim(["--issue", "42"]) == 0

    assert spy.calls == [], "tmux ausserhalb einer tmux-Session aufgerufen"
    assert json.loads(lock.read_text())["issue"] == "42", "Claim selbst uebersprungen"


def test_tmux_not_called_when_disabled_by_config(tmp_path, monkeypatch):
    """AC-33: session_register.tmux_rename == false → kein rename."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("", "none"))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-abc")
    lock = _write_lock(locks)
    _tmux_env(monkeypatch, rename_enabled=False)
    spy = _RunSpy(result=_Completed(0))
    monkeypatch.setattr(subprocess, "run", spy)

    assert _run_claim(["--issue", "42"]) == 0

    assert spy.calls == [], "tmux trotz tmux_rename=false aufgerufen"
    assert json.loads(lock.read_text())["issue"] == "42"


def test_tmux_rename_defaults_to_enabled_when_config_explodes(tmp_path, monkeypatch):
    """AC-30 / EB-Fail-Safe: Config-Ladefehler → Default true, kein Abbruch."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("", "none"))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-abc")
    _write_lock(locks)
    _tmux_env(monkeypatch)

    def explode():
        raise RuntimeError("config kaputt")

    monkeypatch.setattr(config_loader, "load_config", explode)
    spy = _RunSpy(result=_Completed(0))
    monkeypatch.setattr(subprocess, "run", spy)

    assert _run_claim(["--issue", "42"]) == 0
    assert spy.calls, "Config-Ladefehler hat das rename verhindert (Default ist true)"


@pytest.mark.parametrize("scenario", ["missing_binary", "timeout", "nonzero", "raises"])
def test_tmux_failures_never_escape(tmp_path, monkeypatch, scenario):
    """AC-32: tmux fehlt / haengt / scheitert → still ignoriert, Claim steht.

    Der Claim ist die eigentliche Aufgabe; das Fensterumbenennen ist Kosmetik
    und darf sie unter keinen Umstaenden mitreissen.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("", "none"))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-abc")
    lock = _write_lock(locks)

    if scenario == "missing_binary":
        _tmux_env(monkeypatch, which=None)
        spy = _RunSpy(result=_Completed(0))
    else:
        _tmux_env(monkeypatch)
        if scenario == "timeout":
            spy = _RunSpy(raises=subprocess.TimeoutExpired(cmd="tmux", timeout=2))
        elif scenario == "nonzero":
            spy = _RunSpy(result=_Completed(1))
        else:
            spy = _RunSpy(raises=OSError("exec format error"))

    monkeypatch.setattr(subprocess, "run", spy)

    assert _run_claim(["--issue", "42"]) == 0, f"{scenario} hat _do_claim abgebrochen"
    assert json.loads(lock.read_text())["issue"] == "42", (
        f"{scenario} hat den Claim verhindert"
    )

    if scenario == "missing_binary":
        assert spy.calls == [], "subprocess.run trotz fehlendem tmux-Binary"


def test_maybe_rename_tmux_window_swallows_everything(monkeypatch):
    """AC-32: die Helferfunktion selbst laesst nie eine Exception nach aussen."""
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1234,0")

    def explode(*_a, **_kw):
        raise RuntimeError("alles kaputt")

    monkeypatch.setattr(shutil, "which", explode)
    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(config_loader, "load_config", explode)

    assert ssg._maybe_rename_tmux_window("42") is None


# ---------------------------------------------------------------------------
# B1 — main() kennt den vierten Modus
# ---------------------------------------------------------------------------

def test_main_dispatches_claim_mode(monkeypatch):
    """AC-19: `session_singleton_guard.py claim --issue N` erreicht _do_claim."""
    seen: list = []
    monkeypatch.setattr(ssg, "_do_claim", lambda argv: seen.append(argv))
    monkeypatch.setattr(ssg, "_read_payload", lambda: {})
    monkeypatch.setattr(sys, "argv",
                        ["session_singleton_guard.py", "claim", "--issue", "120,121"])

    ssg.main()

    assert seen == [["--issue", "120,121"]], (
        "claim-Modus nicht in main() verdrahtet"
    )


# ===========================================================================
# Adversary-Findings F002 / F003 / F005 — Hot-Path-Kosten und Robustheit
# ===========================================================================

# ---------------------------------------------------------------------------
# F002 — Re-Register darf den Harness-Scan nicht bei jedem Aufruf ausloesen
# ---------------------------------------------------------------------------

def _count_harness_scans(monkeypatch) -> list:
    """Zaehlt _harness_agent_name-Aufrufe (Glob + JSON-Parse pro Aufruf)."""
    scans: list = []
    monkeypatch.setattr(ssg, "_harness_agent_name",
                        lambda session_id: scans.append(session_id))
    return scans


def test_reregister_never_scans_harness_when_lock_file_stays_missing(
    tmp_path, monkeypatch
):
    """F002: dauerhaft fehlende Lock-Datei -> KEIN Harness-Scan, nie.

    Der Re-Register-Zweig laeuft in diesem Zustand bei jedem Guard-Aufruf.
    Wuerde er _harness_agent_name() rufen, liefe der Verzeichnis-Scan ueber
    ~/.claude/sessions/ endlos mit: der 60s-Zeitdeckel bremst ihn hier NICHT,
    weil started_at beim Re-Register jedes Mal auf now zurueckgesetzt wird —
    die Session sieht dauerhaft "juenger als 60s" aus.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    scans = _count_harness_scans(monkeypatch)
    lock = locks / "sess-abc.json"

    for _ in range(5):
        assert _run_guard(_make_guard_payload("Read", WORKTREE_CWD)) == 0
        assert lock.exists(), "Re-Register hat die Datei nicht angelegt"
        lock.unlink()                      # Datei verschwindet wieder

    assert scans == [], (
        f"{len(scans)} Harness-Verzeichnis-Scans im Re-Register-Zweig — "
        "unbegrenzte I/O im PreToolUse-Hot-Path"
    )


def test_healthy_session_still_writes_once_per_throttle_window(
    tmp_path, monkeypatch
):
    """F002 (Gegenprobe): bleibt die Datei liegen, greift der Throttle regulaer.

    Beweist, dass die Hot-Path-Kosten NUR im Ausnahmefall anfallen — genau die
    Zusage aus der A3-Begruendung gegenueber feat-106:75-87.
    """
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    written = _count_lock_writes(monkeypatch, locks)

    for _ in range(5):
        assert _run_guard(_make_guard_payload("Read", WORKTREE_CWD)) == 0

    assert len(written) == 1, (
        f"{len(written)} Schreibvorgaenge statt 1 — der erste Aufruf legt die "
        "Datei an, die restlichen vier fallen in das 60s-Throttle-Fenster"
    )


def test_reregister_short_circuits_on_unwritable_lock_dir(tmp_path, monkeypatch):
    """F002: nicht beschreibbares Lock-Verzeichnis -> gar kein Versuch.

    Ohne Vorabtest liefe pro Guard-Aufruf ein kompletter Bau- und
    Schreibversuch samt Exception-Pfad. Diese Pruefung wirkt — anders als
    prozesslokaler Zustand — auch ueber Prozessgrenzen hinweg, denn jeder
    Hook-Aufruf ist ein eigener Prozess.
    """
    if os.geteuid() == 0:
        pytest.skip("root ignoriert Verzeichnisrechte")

    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    scans = _count_harness_scans(monkeypatch)
    written = _count_lock_writes(monkeypatch, locks)

    locks.chmod(0o500)
    try:
        for _ in range(5):
            assert _run_guard(_make_guard_payload("Read", WORKTREE_CWD)) == 0
    finally:
        locks.chmod(0o700)

    assert written == [], "Schreibversuch trotz unbeschreibbarem Verzeichnis"
    assert scans == [], "Harness-Scan trotz unbeschreibbarem Verzeichnis"


# ---------------------------------------------------------------------------
# F003 — claim-Schreibfehler darf nicht still bleiben
# ---------------------------------------------------------------------------

def test_claim_reports_write_failure_instead_of_staying_silent(
    tmp_path, monkeypatch, capsys
):
    """F003: schlaegt der Write fehl, sieht der Operator sonst nur Exit 0.

    Meldungen auf stdout sind laut B1 Teil des beobachtbaren Verhaltens von
    `claim` — ein stiller Fehlschlag widerspricht der eigenen Design-Praemisse.
    """
    if os.geteuid() == 0:
        pytest.skip("root ignoriert Dateirechte")

    locks, _ = _heartbeat_env(monkeypatch, tmp_path, workflow=("", "none"))
    _no_tmux(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-abc")
    lock = _write_lock(locks)
    before = lock.read_text()

    lock.chmod(0o400)                      # z.B. Rechtefehler / read-only Mount
    try:
        assert _run_claim(["--issue", "42"]) == 0, "Schreibfehler bricht claim ab"
        out = capsys.readouterr().out
    finally:
        lock.chmod(0o600)

    assert "Schreibfehler" in out, f"Fehlschlag bleibt still — stdout: {out!r}"
    assert "eingetragen" not in out, "Erfolgsmeldung trotz fehlgeschlagenem Write"
    assert lock.read_text() == before, "Eintrag trotz Schreibfehler veraendert"


# ---------------------------------------------------------------------------
# F005 — Laengendeckel auf --issue
# ---------------------------------------------------------------------------

def test_validate_issue_arg_accepts_value_at_length_limit():
    """F005: exakt 64 Zeichen sind noch gueltig (Grenze inklusive)."""
    value = "1" * 64
    assert len(value) == ssg._MAX_ISSUE_ARG_LEN
    assert ssg._validate_issue_arg(value) == value


def test_validate_issue_arg_rejects_overlong_value():
    """F005: laenger als 64 Zeichen -> abgelehnt wie jeder ungueltige Wert.

    Ohne Deckel landet ein beliebig langer Wert unveraendert in der Lock-JSON.
    """
    assert ssg._validate_issue_arg("1" * 65) is None
    assert ssg._validate_issue_arg("1" * 100000) is None


def test_claim_rejects_overlong_issue_without_touching_files(
    tmp_path, monkeypatch, capsys
):
    """F005: der Deckel greift auch im echten claim-Pfad."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    _no_tmux(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-abc")
    lock = _write_lock(locks)
    before = lock.read_text()

    assert _run_claim(["--issue", "1" * 65]) == 0

    assert lock.read_text() == before, "ueberlanger Wert ins Register geschrieben"
    assert capsys.readouterr().out.strip(), "keine verstaendliche Meldung"


# ---------------------------------------------------------------------------
# F007 — kein stiller Fehlschlag in der Pfadaufloesung von claim
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("broken", ["_locks_dir", "_find_claim_target"])
def test_claim_reports_internal_error_instead_of_silent_exit(
    tmp_path, monkeypatch, capsys, broken
):
    """F007: wirft irgendetwas VOR dem Write, sieht der Operator sonst nichts.

    Nur der Write war gekapselt (F003). Ein Fehler in _locks_dir() —
    z.B. weil find_project_root() wirft — liess claim wortlos mit 0 enden:
    exakt die stille Fehlschlagsklasse, gegen die F003 gebaut wurde.
    """
    _heartbeat_env(monkeypatch, tmp_path)
    _no_tmux(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-abc")

    def boom(*_a, **_kw):
        raise RuntimeError("find_project_root explodiert")

    monkeypatch.setattr(ssg, broken, boom)

    assert _run_claim(["--issue", "42"]) == 0, "claim endet nicht mit Exit 0"

    out = capsys.readouterr().out
    assert "interner Fehler" in out, f"stiller Fehlschlag — stdout: {out!r}"
    assert "RuntimeError" in out, "Fehlerart nicht benannt"


def test_claim_wrapper_lets_systemexit_through(tmp_path, monkeypatch):
    """F007: ein SystemExit aus der Logik darf nicht als 'interner Fehler'
    fehlgedeutet werden — der Wrapper reicht ihn unveraendert durch."""
    _heartbeat_env(monkeypatch, tmp_path)
    monkeypatch.setattr(ssg, "_claim_impl",
                        lambda argv: (_ for _ in ()).throw(SystemExit(3)))

    with pytest.raises(SystemExit) as excinfo:
        ssg._do_claim(["--issue", "42"])

    assert excinfo.value.code == 3, "SystemExit vom Wrapper verschluckt"
