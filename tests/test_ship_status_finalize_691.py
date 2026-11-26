"""`ship-status done|skipped` schliesst einen Workflow in Phase 8 ab (Issue #691).

Spec: docs/specs/fix-691-auto-abhaken.md (AC-1 bis AC-10).

Vertraege aus der Spec (Implementation Details), die diese Tests festlegen:
- Bei `done`/`skipped` und Ziel in `.claude/workflows/` mit `current_phase ==
  phase8_complete`: Execution-Log schreiben, falls kein `_log/*_<name>.yaml` existiert;
  archivieren wie `complete` (Archivdatei, Arbeitsdatei weg); Aktiv-Zeiger nur loeschen,
  wenn das Ziel der aktive Workflow der Sitzung ist; danach `auftrag_mark_done`;
  zusaetzliche Ausgabezeile `ARCHIVED=<name>`.
- Ziel schon im Archiv: nur abhaken (idempotent, kein zweites Archivieren).
- Ziel nicht in Phase 8: nur Status wie bisher.
- Fehler im Abschluss aendern weder `SHIP_STATUS=<status>` noch den Exit-Code.
- `complete` bleibt im sichtbaren Verhalten gleich; `running`/`failed` schliessen nichts ab.

Alle Aufrufe laufen als Subprozess gegen `core/hooks/workflow.py` dieses Checkouts mit
`cwd=tmp_path` (Muster tests/test_auftrag_551.py). Ohne Sitzungskennung (die Env wird
bereinigt) liegt der Auftrag projektweit in `<proj>/.claude/auftrag.json`.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
COMMAND_MD = REPO_ROOT / "core" / "commands" / "60-validate.md"
SKILL_MD = REPO_ROOT / "skills" / "60-validate" / "SKILL.md"
SYNC_PY = REPO_ROOT / "scripts" / "sync_skills.py"

WF = "feat-547-x"
OTHER = "feat-600-andere"


# --- Helpers ---------------------------------------------------------------

def _env(proj: Path, **extra: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("OPENSPEC_", "HERDR_", "STUB_"))
           and k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PLUGIN_ROOT")}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    home = proj / "_home"
    home.mkdir(exist_ok=True)
    env["HOME"] = str(home)
    env.update(extra)
    return env


def _cli(proj: Path, *args: str, active: "str | None" = WF):
    extra = {"OPENSPEC_ACTIVE_WORKFLOW": active} if active else {}
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args], capture_output=True,
                          text=True, env=_env(proj, **extra), cwd=str(proj), timeout=60)


def _lines(stdout: str) -> "list[str]":
    return [line.strip() for line in stdout.splitlines()]


def _has_ship_line(stdout: str, value: str) -> bool:
    return any(line.startswith(f"SHIP_STATUS={value}") for line in _lines(stdout))


def _archived_lines(stdout: str) -> "list[str]":
    return [line for line in _lines(stdout) if line.startswith("ARCHIVED=")]


def _wf_dir(proj: Path) -> Path:
    return proj / ".claude" / "workflows"


def _wf_file(proj: Path, name: str = WF) -> Path:
    return _wf_dir(proj) / f"{name}.json"


def _archive_file(proj: Path, name: str = WF) -> Path:
    return _wf_dir(proj) / "_archive" / f"{name}.json"


def _logs(proj: Path, name: str = WF) -> "list[Path]":
    return sorted((_wf_dir(proj) / "_log").glob(f"*_{name}.yaml"))


def _active_pointer(proj: Path) -> "str | None":
    f = proj / ".claude" / "active_workflow"
    return f.read_text().strip() if f.exists() else None


def _data(name: str = WF, phase: str = "phase8_complete", **fields) -> dict:
    data = {"name": name, "workflow_type": "feature", "current_phase": phase,
            "phase_transitions": [], "phase_log": [], "ship_status": "open"}
    data.update(fields)
    return data


def _project(root: Path) -> Path:
    """Main-Repo (.git als Verzeichnis) mit leerem Workflow-, Log- und Archivordner."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    (_wf_dir(root) / "_log").mkdir(parents=True, exist_ok=True)
    (_wf_dir(root) / "_archive").mkdir(parents=True, exist_ok=True)
    return root


def _active_project(root: Path, data: "dict | None" = None) -> Path:
    data = data or _data()
    proj = _project(root)
    _wf_file(proj, data["name"]).write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(data["name"])
    return proj


def _completable(root: Path, name: str = WF, with_log: bool = True) -> Path:
    """Wie tests/test_auftrag_551.py: Fast Track mit erfuellten Vorbedingungen."""
    proj = _project(root)
    spec = proj / "docs" / "specs" / "x.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("## Architektur-Entscheidung (ADR)\n\n- **ADR-Nr.:** keine\n")
    _wf_file(proj, name).write_text(json.dumps({
        "name": name, "workflow_type": "feature-fast", "spec_file": "docs/specs/x.md",
        "spec_approved": True, "current_phase": "phase8_complete",
        "context_file": "docs/context/x.md", "affected_files": [], "test_artifacts": [],
        "adversary_verdict": None,
    }))
    if with_log:
        (_wf_dir(proj) / "_log" / f"20261109100000_{name}.yaml").write_text("outcome: success\n")
    (proj / ".claude" / "active_workflow").write_text(name)
    return proj


def _auftrag_path(proj: Path) -> Path:
    return proj / ".claude" / "auftrag.json"


def _write_auftrag(proj: Path, issues) -> Path:
    path = _auftrag_path(proj)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "issues": [{"n": n, "status": s} for n, s in issues],
        "autark": False, "note": "",
        "created": "2026-11-09T10:00:00Z", "updated": "2026-11-09T10:00:00Z",
    }))
    return path


def _status_of(proj: Path) -> dict:
    return {e["n"]: e["status"] for e in json.loads(_auftrag_path(proj).read_text())["issues"]}


# --- AC-1 ------------------------------------------------------------------

def test_done_in_phase8_archives_and_marks_done(tmp_path):
    proj = _active_project(tmp_path / "p")
    _write_auftrag(proj, [(547, "open"), (548, "open")])

    res = _cli(proj, "ship-status", "done", "--note", "PR 1 gemergt")

    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _archive_file(proj).is_file(), "Workflow nicht archiviert"
    assert not _wf_file(proj).exists(), "Arbeitsdatei liegt noch in .claude/workflows/"
    archived = json.loads(_archive_file(proj).read_text())
    assert archived.get("ship_status") == "done"
    assert _status_of(proj) == {547: "done", 548: "open"}, "Issue im Auftrag nicht abgehakt"
    assert _active_pointer(proj) != WF, "Aktiv-Zeiger zeigt noch auf den archivierten Workflow"


# --- AC-2 ------------------------------------------------------------------

def test_log_written_if_missing_and_kept_if_present(tmp_path):
    # Ohne Log: danach existiert genau eins
    proj = _active_project(tmp_path / "missing")
    assert _logs(proj) == []
    res = _cli(proj, "ship-status", "done")
    assert res.returncode == 0, (res.stdout, res.stderr)
    logs = _logs(proj)
    assert len(logs) == 1, f"Execution-Log fehlt nach ship-status done: {logs}"
    assert f"workflow_id: {WF}" in logs[0].read_text()

    # Mit Log: unveraendert, kein zweites
    proj = _active_project(tmp_path / "present")
    existing = _wf_dir(proj) / "_log" / f"20261109100000_{WF}.yaml"
    existing.write_text("outcome: success\n")
    res = _cli(proj, "ship-status", "done")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _archive_file(proj).is_file(), "Workflow nicht archiviert"
    assert _logs(proj) == [existing], "vorhandenes Log ergaenzt statt beibehalten"
    assert existing.read_text() == "outcome: success\n", "vorhandenes Log ueberschrieben"


# --- AC-3 ------------------------------------------------------------------

def test_output_lines_and_exit_code(tmp_path):
    for value in ("done", "skipped"):
        proj = _active_project(tmp_path / value)
        res = _cli(proj, "ship-status", value)
        assert res.returncode == 0, (value, res.stdout, res.stderr)
        assert _has_ship_line(res.stdout, value), (value, res.stdout)
        assert _archived_lines(res.stdout) == [f"ARCHIVED={WF}"], (value, res.stdout)
        assert _archive_file(proj).is_file(), value


# --- AC-4 ------------------------------------------------------------------

def test_done_before_phase8_only_sets_status(tmp_path):
    proj = _active_project(tmp_path / "p", _data(phase="phase6_implement"))
    path = _write_auftrag(proj, [(547, "open")])
    before = path.read_bytes()

    res = _cli(proj, "ship-status", "done")

    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _has_ship_line(res.stdout, "done"), res.stdout
    assert _archived_lines(res.stdout) == [], res.stdout
    assert _wf_file(proj).is_file(), "Workflow vor Phase 8 entfernt"
    assert not _archive_file(proj).exists(), "Workflow vor Phase 8 archiviert"
    data = json.loads(_wf_file(proj).read_text())
    assert data["ship_status"] == "done"
    assert data["current_phase"] == "phase6_implement"
    assert path.read_bytes() == before, "Auftrag vor Phase 8 geaendert"
    assert _logs(proj) == [], "Log vor Phase 8 geschrieben"
    assert _active_pointer(proj) == WF


# --- AC-5 ------------------------------------------------------------------

def test_archived_target_idempotent_marking(tmp_path):
    # a) per complete archiviert und abgehakt -> ship-status done (Archiv-Fallback)
    proj = _completable(tmp_path / "finished")
    _write_auftrag(proj, [(547, "open"), (548, "open")])
    res = _cli(proj, "complete")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _status_of(proj) == {547: "done", 548: "open"}
    archive_before = sorted(p.name for p in (_wf_dir(proj) / "_archive").iterdir())

    res = _cli(proj, "ship-status", "done", "--note", "PR 1 gemergt", active=None)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "Traceback" not in res.stderr, res.stderr
    assert _has_ship_line(res.stdout, "done"), res.stdout
    assert _archived_lines(res.stdout) == [], "zweites Archivieren gemeldet"
    assert sorted(p.name for p in (_wf_dir(proj) / "_archive").iterdir()) == archive_before
    assert not _wf_file(proj).exists(), "Arbeitsdatei wieder angelegt"
    assert _status_of(proj) == {547: "done", 548: "open"}
    assert json.loads(_archive_file(proj).read_text())["ship_status"] == "done"

    # b) archiviert, Issue noch open -> ship-status done <nr> hakt nachtraeglich ab
    proj = _project(tmp_path / "late")
    _archive_file(proj).write_text(json.dumps(_data()))
    _write_auftrag(proj, [(547, "open"), (548, "open")])
    res = _cli(proj, "ship-status", "done", "547", active=None)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _has_ship_line(res.stdout, "done"), res.stdout
    assert _archived_lines(res.stdout) == [], res.stdout
    assert not _wf_file(proj).exists()
    assert [p.name for p in (_wf_dir(proj) / "_archive").iterdir()] == [f"{WF}.json"]
    assert _status_of(proj) == {547: "done", 548: "open"}, \
        "archiviertes Ziel: offenes Issue nicht nachtraeglich abgehakt"


# --- AC-6 ------------------------------------------------------------------

def test_foreign_target_keeps_active_pointer(tmp_path):
    proj = _active_project(tmp_path / "p", _data(name=OTHER, phase="phase6_implement"))
    _wf_file(proj, WF).write_text(json.dumps(_data()))
    _write_auftrag(proj, [(547, "open"), (600, "open")])

    res = _cli(proj, "ship-status", "done", "547", active=OTHER)

    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _archive_file(proj).is_file(), "fremdes Ziel B nicht archiviert"
    assert not _wf_file(proj).exists(), "Arbeitsdatei von B liegt noch da"
    assert _archived_lines(res.stdout) == [f"ARCHIVED={WF}"], res.stdout
    assert _active_pointer(proj) == OTHER, "Aktiv-Zeiger von A geloescht"
    assert _wf_file(proj, OTHER).is_file(), "Workflow A angetastet"
    assert json.loads(_wf_file(proj, OTHER).read_text())["current_phase"] == "phase6_implement"
    assert _status_of(proj) == {547: "done", 600: "open"}


# --- AC-7 ------------------------------------------------------------------

def test_running_and_failed_do_not_finalize(tmp_path):
    for value in ("running", "failed"):
        proj = _active_project(tmp_path / value)
        path = _write_auftrag(proj, [(547, "open")])
        before = path.read_bytes()
        res = _cli(proj, "ship-status", value)
        assert res.returncode == 0, (value, res.stdout, res.stderr)
        assert _has_ship_line(res.stdout, value), (value, res.stdout)
        assert _archived_lines(res.stdout) == [], (value, res.stdout)
        assert _wf_file(proj).is_file(), value
        assert not _archive_file(proj).exists(), value
        assert json.loads(_wf_file(proj).read_text())["ship_status"] == value
        assert path.read_bytes() == before, value
        assert _active_pointer(proj) == WF, value


# --- AC-8 ------------------------------------------------------------------

def test_failure_in_finalize_is_fail_open(tmp_path):
    # a) kaputte Auftragsdatei: Ausgabe/Exit unveraendert, Archivierung trotzdem,
    #    Datei byte-gleich
    proj = _active_project(tmp_path / "broken-auftrag")
    _auftrag_path(proj).write_text("{kaputt")
    res = _cli(proj, "ship-status", "done")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "Traceback" not in res.stderr, res.stderr
    assert _has_ship_line(res.stdout, "done"), res.stdout
    assert _auftrag_path(proj).read_text() == "{kaputt"
    assert _archive_file(proj).is_file(), "Auftragsfehler verhinderte die Archivierung"
    assert _archived_lines(res.stdout) == [f"ARCHIVED={WF}"], res.stdout

    # b) Archiv nicht anlegbar (Datei statt Ordner): Exit 0, SHIP_STATUS=done,
    #    Arbeitsdatei bleibt mit gesetztem Status, kein ARCHIVED
    proj = _project(tmp_path / "broken-archive")
    (_wf_dir(proj) / "_archive").rmdir()
    (_wf_dir(proj) / "_archive").write_text("kein Ordner")
    _wf_file(proj).write_text(json.dumps(_data()))
    (proj / ".claude" / "active_workflow").write_text(WF)
    _write_auftrag(proj, [(547, "open")])
    res = _cli(proj, "ship-status", "done")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "Traceback" not in res.stderr, res.stderr
    assert _has_ship_line(res.stdout, "done"), res.stdout
    assert _archived_lines(res.stdout) == [], res.stdout
    assert _wf_file(proj).is_file(), "Arbeitsdatei bei Archivfehler verloren"
    assert json.loads(_wf_file(proj).read_text())["ship_status"] == "done"


# --- AC-9 ------------------------------------------------------------------

def test_complete_behaviour_unchanged(tmp_path):
    # Log-Pflicht bleibt
    proj = _completable(tmp_path / "nolog", with_log=False)
    _write_auftrag(proj, [(547, "open")])
    res = _cli(proj, "complete")
    assert res.returncode == 1, (res.stdout, res.stderr)
    assert "No execution log" in res.stderr, res.stderr
    assert _wf_file(proj).is_file()
    assert _status_of(proj) == {547: "open"}

    # Archiv, Abhaken, Aktiv-Zeiger geloescht, Ausgabe wie bisher
    proj = _completable(tmp_path / "ok")
    _write_auftrag(proj, [(547, "open"), (548, "open")])
    res = _cli(proj, "complete")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert f"Workflow {WF} completed and archived." in res.stdout, res.stdout
    assert _archive_file(proj).is_file()
    assert not _wf_file(proj).exists()
    assert _status_of(proj) == {547: "done", 548: "open"}
    assert _active_pointer(proj) is None
    archived = json.loads(_archive_file(proj).read_text())
    assert archived["current_phase"] == "phase8_complete"
    assert archived["ship_status"] == "open"


# --- AC-10 -----------------------------------------------------------------

def _step4(text: str) -> str:
    start = text.index("### Step 4")
    rest = text[start + len("### Step 4"):]
    ends = [i for i in (rest.find("\n## "), rest.find("\n### ")) if i != -1]
    return rest[:min(ends)] if ends else rest


def test_validate_doc_mentions_finalize_and_skill_in_sync():
    for path in (COMMAND_MD, SKILL_MD):
        step = _step4(path.read_text())
        low = step.lower()
        assert "ship-status done" in step, (path, "ship-status done fehlt in Step 4")
        assert "archiv" in low, (path, "Step 4 sagt nicht, dass ship-status done archiviert")
        assert "auftrag" in low, (path, "Step 4 sagt nicht, dass im Auftrag abgehakt wird")

    spec = importlib.util.spec_from_file_location("sync_skills_691", SYNC_PY)
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    expected = sync.expected_skills()
    assert SKILL_MD in expected, list(expected)
    assert SKILL_MD.read_text() == expected[SKILL_MD], \
        "skills/60-validate/SKILL.md weicht vom Generat ab (sync_skills.py laufen lassen)"
