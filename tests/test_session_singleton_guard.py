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
# Test 15 — fehlende Lock-Datei (AC-11, Regressionsschutz)
# ---------------------------------------------------------------------------

def test_guard_without_lock_file_creates_nothing(tmp_path, monkeypatch):
    """Test 15 (AC-11): Der guard legt niemals Eintraege an."""
    locks, _ = _heartbeat_env(monkeypatch, tmp_path)
    lock = locks / "sess-abc.json"
    assert not lock.exists()

    assert _run_guard(_make_guard_payload("Read", WORKTREE_CWD)) == 0
    assert not lock.exists(), "guard hat einen Registereintrag angelegt"

    assert _run_guard(_make_guard_payload("Edit", WORKTREE_CWD)) == 0
    assert not lock.exists(), "guard hat einen Registereintrag angelegt"

    assert _run_guard(_make_guard_payload("Edit", MAIN_CWD)) == 2
    assert not lock.exists(), "guard hat einen Registereintrag angelegt"
    assert list(locks.glob("*.json")) == []


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
