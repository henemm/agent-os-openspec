"""RED-Tests fuer Issue #250 Teil B: Aufwandsbremse (Budget je Stufe, Rueckfrage statt Blockade,
Abschluss-LoC).

Spec: docs/specs/feat-250-teil-b-aufwandsbremse.md (AC-1 bis AC-9).

Alle Tests laufen hermetisch in tmp_path (CLAUDE_PROJECT_DIR) und in Subprozessen: `load_config`
ist per lru_cache gepuffert, und die Hooks lesen ihre Config aus dem Projekt-Root. Auf die neuen
Namen (`get_effort_budget`, `effort_budget_exceeded`, `_batch_window_s`, `_final_loc`) wird erst
INNERHALB der Tests zugegriffen, damit jeder Test einzeln aus dem Grund "Feature fehlt" rot wird.
"""

import json
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"

WF_CREATED = "2026-10-03T10:00:00.000000"

BUDGET_YAML = textwrap.dedent("""\
    effort_budget:
      enabled: {enabled}
      feature-fast: {{max_fix_loops: 1, max_phase_reentries: 1, batch_window_min: 30}}
      feature:      {{max_fix_loops: 2, max_phase_reentries: 2, batch_window_min: 15}}
    """)


# --------------------------------------------------------------------------- Helfer

def _env(project: Path, wf_name: str = "wf-250b") -> dict:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = wf_name
    env.pop("CLAUDE_TOOL_INPUT", None)
    return env


def _make_project(tmp_path: Path, enabled: "bool | None" = True) -> Path:
    """Main-Repo-Attrappe (.git als DIR -> kein Worktree) mit config.yaml.

    `enabled=None` schreibt gar keine config.yaml (Verhalten ohne Config).
    """
    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "workflows").mkdir(parents=True, exist_ok=True)
    if enabled is not None:
        flag = "true" if enabled else "false"
        (tmp_path / "config.yaml").write_text(BUDGET_YAML.format(enabled=flag))
    return tmp_path


def _write_workflow(project: Path, wf_name: str = "wf-250b", **fields) -> Path:
    data = {
        "name": wf_name,
        "workflow_type": "feature-fast",
        "current_phase": "phase6_implement",
        "created": WF_CREATED,
        "spec_file": "docs/specs/wf-250b.md",
        "spec_approved": True,
        "context_file": "docs/context/wf-250b.md",
        "test_artifacts": [],
        "red_test_done": True,
        "phase_transitions": [],
        "phase_log": [],
        "fix_loop_iterations": 0,
    }
    data.update(fields)
    path = project / ".claude" / "workflows" / f"{wf_name}.json"
    path.write_text(json.dumps(data))
    return path


def _py(project: Path, code: str, wf_name: str = "wf-250b") -> dict:
    """Python-Schnipsel im Hook-Kontext ausfuehren; das Schnipsel druckt als LETZTE Zeile JSON."""
    prelude = f"import sys, json; sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
    res = subprocess.run(
        [sys.executable, "-c", prelude + textwrap.dedent(code)],
        capture_output=True, text=True, env=_env(project, wf_name), cwd=str(project),
    )
    assert res.returncode == 0, f"Schnipsel scheiterte:\n{res.stderr}"
    return json.loads(res.stdout.strip().splitlines()[-1])


def _run_workflow(project: Path, args: list, wf_name: str = "wf-250b") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py")] + args,
        capture_output=True, text=True, env=_env(project, wf_name), cwd=str(project),
    )


def _wf_state(project: Path, wf_name: str = "wf-250b") -> dict:
    return json.loads((project / ".claude" / "workflows" / f"{wf_name}.json").read_text())


def _gate_events(project: Path) -> list:
    path = project / ".claude" / "gate-events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _record(project: Path, target: str = "phase6b_adversary", **state) -> dict:
    """`record_transition` mit einem Workflow-Zustand aufrufen. Liefert Rueckgabe + Zustand."""
    base = {
        "name": "wf-250b", "workflow_type": "feature-fast", "current_phase": "phase6_implement",
        "created": WF_CREATED, "phase_transitions": [], "phase_log": [], "fix_loop_iterations": 0,
    }
    base.update(state)
    return _py(project, f"""
        import workflow
        data = json.loads({json.dumps(json.dumps(base))})
        ret = workflow.record_transition(data, {target!r})
        print(json.dumps({{"ret": ret, "events": data.get("budget_events")}}))
    """)


def _entries(n: int, phase: str = "phase6_implement") -> list:
    return [{"from": "x", "to": phase, "at": "2026-10-03T10:00:00", "trigger": "command"}
            for _ in range(n)]


def _read_log(project: Path, wf_name: str = "wf-250b") -> str:
    files = list((project / ".claude" / "workflows" / "_log").glob(f"*_{wf_name}.yaml"))
    assert len(files) == 1, f"erwartet genau eine Log-Datei, gefunden: {files}"
    return files[0].read_text()


def _run_gate(project: Path, wf_name: str = "wf-250b") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "post_implementation_gate.py")],
        input=json.dumps({"tool_input": {"file_path": "src/foo.py"}}),
        capture_output=True, text=True, env=_env(project, wf_name), cwd=str(project),
    )


def _write_lock(project: Path, age_min: float, wf_name: str = "wf-250b") -> None:
    (project / ".claude" / f"pending_validation_{wf_name}.json").write_text(json.dumps({
        "workflow": wf_name, "workflow_created": WF_CREATED,
        "created": time.time() - age_min * 60, "created_iso": "irrelevant",
    }))


# --------------------------------------------------------------------------- AC-1

def test_config_block_and_stage_lookup(tmp_path):  # AC-1
    import yaml
    cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())
    block = cfg.get("effort_budget")
    assert isinstance(block, dict), "config.yaml hat keinen Block `effort_budget`"
    assert "enabled" in block
    for stage in ("feature-fast", "feature"):
        for key in ("max_fix_loops", "max_phase_reentries", "batch_window_min"):
            assert key in block[stage], f"effort_budget.{stage}.{key} fehlt in config.yaml"

    # Lookup gegen genau diese Config (Projekt-Root = tmp mit Kopie der echten config.yaml)
    (tmp_path / ".git").mkdir()
    (tmp_path / "config.yaml").write_text((REPO_ROOT / "config.yaml").read_text())
    res = _py(tmp_path, """
        import config_loader
        out = {t: config_loader.get_effort_budget(t)
               for t in ("feature-fast", "feature", "bug", "express", "voellig-unbekannt")}
        print(json.dumps(out))
    """)
    assert res["feature-fast"] == {k: block["feature-fast"][k] for k in
                                   ("max_fix_loops", "max_phase_reentries", "batch_window_min")}
    assert res["feature"] == {k: block["feature"][k] for k in
                              ("max_fix_loops", "max_phase_reentries", "batch_window_min")}
    for legacy in ("bug", "express", "voellig-unbekannt"):
        assert res[legacy] == res["feature"], f"unbekannter Typ {legacy!r} faellt nicht auf `feature`"


# --------------------------------------------------------------------------- AC-2

def test_exceeding_fix_loops_is_recorded_and_logged(tmp_path):  # AC-2
    project = _make_project(tmp_path)
    res = _record(project, fix_loop_iterations=2)  # Grenze feature-fast: 1

    assert isinstance(res["ret"], list) and res["ret"], "record_transition meldet keine Ueberschreitung"
    hit = next((e for e in res["ret"] if str(e.get("metric", "")).startswith("fix_loop")), None)
    assert hit is not None, f"keine Fix-Loop-Metrik in {res['ret']}"
    assert hit["value"] == 2 and hit["limit"] == 1

    assert res["events"], "data['budget_events'] bleibt leer"
    assert any(str(e.get("metric", "")).startswith("fix_loop") for e in res["events"])

    events = [e for e in _gate_events(project) if e.get("hook") == "effort_budget"]
    assert events, "kein Gate-Event mit hook == 'effort_budget' im Log"


# --------------------------------------------------------------------------- AC-3

def test_phase_command_prints_question_to_po(tmp_path):  # AC-3
    project = _make_project(tmp_path)
    _write_workflow(project, fix_loop_iterations=2)

    res = _run_workflow(project, ["phase", "phase6b_adversary"])
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "RÜCKFRAGE AN DEN PO:" in out
    tail = out.split("RÜCKFRAGE AN DEN PO:", 1)[1]
    assert "feature-fast" in tail, "Stufe fehlt in der Rueckfrage"
    assert "fix_loop" in tail, "Metrik fehlt in der Rueckfrage"
    assert re.search(r"\b2\b", tail) and re.search(r"\b1\b", tail), "Stand/Grenze fehlen"


# --------------------------------------------------------------------------- AC-4

def test_within_budget_stays_silent(tmp_path):  # AC-4 (milder Fall)
    project = _make_project(tmp_path)
    # feature: Grenze 2/2 -> 1 Fix-Loop und 1 Wiedereintritt liegen klar im Budget
    res = _record(project, workflow_type="feature", fix_loop_iterations=1,
                  phase_transitions=_entries(2))
    assert res["ret"] == [], f"Rueckgabe im Budget muss eine leere Liste sein, ist {res['ret']!r}"
    assert not res["events"], "budget_events muss im Budget leer bleiben"
    assert not [e for e in _gate_events(project) if e.get("hook") == "effort_budget"]

    # Reine Funktion: strenger Fall (feature-fast, 2 > 1) liefert, milder Fall leer
    pure = _py(project, """
        import workflow
        budget = {"max_fix_loops": 1, "max_phase_reentries": 1, "batch_window_min": 30}
        quiet = workflow.effort_budget_exceeded(
            {"fix_loop_iterations": 0, "phase_transitions": []}, budget)
        loud = workflow.effort_budget_exceeded(
            {"fix_loop_iterations": 2, "phase_transitions": []}, budget)
        print(json.dumps({"quiet": quiet, "loud": loud}))
    """)
    assert pure["quiet"] == []
    assert pure["loud"] and pure["loud"][0]["limit"] == 1

    # Ueber die CLI: keine Rueckfrage
    _write_workflow(project, workflow_type="feature", fix_loop_iterations=1)
    cli = _run_workflow(project, ["phase", "phase6b_adversary"])
    assert cli.returncode == 0, cli.stderr
    assert "RÜCKFRAGE" not in cli.stdout + cli.stderr


# --------------------------------------------------------------------------- AC-5

def test_budget_never_blocks_a_transition(tmp_path):  # AC-5
    project = _make_project(tmp_path)
    _write_workflow(project, fix_loop_iterations=5,  # weit ueber der Grenze 1
                    phase_transitions=_entries(4) + _entries(4, "phase6b_adversary"))

    first = _run_workflow(project, ["phase", "phase6b_adversary"])
    assert first.returncode == 0, first.stdout + first.stderr
    assert _wf_state(project)["current_phase"] == "phase6b_adversary"
    assert "RÜCKFRAGE AN DEN PO:" in first.stdout + first.stderr, \
        "Ueberschreitung ohne Rueckfrage — der Test prueft sonst nichts"

    second = _run_workflow(project, ["phase", "phase7_validate"])
    assert second.returncode == 0, second.stdout + second.stderr
    assert _wf_state(project)["current_phase"] == "phase7_validate"


# --------------------------------------------------------------------------- AC-6

def test_reentries_counted_and_not_repeated(tmp_path):  # AC-6
    project = _make_project(tmp_path)
    res = _py(project, """
        import workflow
        data = {"name": "wf-250b", "workflow_type": "feature", "current_phase": "phase5_tdd_red",
                "created": "x", "phase_transitions": [], "phase_log": [],
                "fix_loop_iterations": 0}
        targets = ["phase6_implement", "phase6b_adversary", "phase6_implement",
                   "phase6b_adversary", "phase6_implement",   # 3. Betreten von phase6 (Grenze 2)
                   "phase6b_adversary", "phase7_validate"]
        returns = []
        for t in targets:
            returns.append(workflow.record_transition(data, t))
            data["current_phase"] = t
        print(json.dumps({"returns": returns}))
    """)
    returns = res["returns"]
    assert all(isinstance(r, list) for r in returns), f"record_transition gibt keine Liste: {returns}"

    # Die ersten vier Wechsel (hoechstens 1 Wiedereintritt je Phase) bleiben still
    assert returns[:4] == [[], [], [], []]

    # Das dritte Betreten von phase6_implement meldet phase_reentries mit Grenze 2
    third = returns[4]
    hit = next((e for e in third if e.get("metric") == "phase_reentries"), None)
    assert hit is not None, f"3. Betreten von phase6_implement meldet nichts: {third}"
    assert hit["limit"] == 2 and hit["value"] >= 2

    # Derselbe Stand wird bei spaeteren Wechseln nicht erneut gemeldet
    assert returns[5:] == [[], []], f"gleicher Stand erneut gemeldet: {returns[5:]}"


# --------------------------------------------------------------------------- AC-7

def test_kill_switch_restores_old_behaviour(tmp_path):  # AC-7
    project = _make_project(tmp_path, enabled=False)

    lookup = _py(project, """
        import config_loader
        print(json.dumps({"b": config_loader.get_effort_budget("feature-fast")}))
    """)
    assert lookup["b"] is None, "Kill-Switch aus, aber get_effort_budget liefert Werte"

    # Wechsel: weder Eintrag noch Rueckfrage
    res = _record(project, fix_loop_iterations=3, phase_transitions=_entries(5))
    assert res["ret"] == []
    assert not res["events"]
    _write_workflow(project, fix_loop_iterations=3)
    cli = _run_workflow(project, ["phase", "phase6b_adversary"])
    assert cli.returncode == 0, cli.stderr
    assert "RÜCKFRAGE" not in cli.stdout + cli.stderr

    # Fenster fuer alle Stufen 15 min
    win = _py(project, """
        import post_implementation_gate as g
        out = {s: g._batch_window_s({"workflow_type": s})
               for s in ("feature-fast", "feature", "bug")}
        print(json.dumps(out))
    """)
    assert win == {"feature-fast": 900, "feature": 900, "bug": 900}

    # und der Hook: ein 20 Minuten alter Lock blockiert auch feature-fast
    _write_workflow(project, current_phase="phase6_implement")
    _write_lock(project, age_min=20)
    gate = _run_gate(project)
    assert gate.returncode == 2, gate.stdout + gate.stderr


# --------------------------------------------------------------------------- AC-8

def test_batch_window_depends_on_stage(tmp_path):  # AC-8
    project = _make_project(tmp_path)

    # feature-fast: 20 Minuten alter Lock liegt im 30-Minuten-Fenster -> erlaubt
    _write_workflow(project, workflow_type="feature-fast", current_phase="phase6_implement")
    _write_lock(project, age_min=20)
    fast = _run_gate(project)
    assert fast.returncode == 0, f"feature-fast sollte erlaubt sein:\n{fast.stdout}{fast.stderr}"

    # feature: dasselbe Alter liegt ausserhalb des 15-Minuten-Fensters -> blockiert
    _write_workflow(project, workflow_type="feature", current_phase="phase6_implement")
    _write_lock(project, age_min=20)
    full = _run_gate(project)
    assert full.returncode == 2, f"feature sollte blockiert sein:\n{full.stdout}{full.stderr}"

    # Die Funktion selbst
    win = _py(project, """
        import post_implementation_gate as g
        print(json.dumps({s: g._batch_window_s({"workflow_type": s})
                          for s in ("feature-fast", "feature")}))
    """)
    assert win == {"feature-fast": 1800, "feature": 900}


# --------------------------------------------------------------------------- AC-9

def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)
    assert res.returncode == 0, f"git {' '.join(args)}: {res.stderr}"
    return res.stdout.strip()


def _git_project(tmp_path: Path, base_commit: "str | None" = None) -> "tuple[Path, str]":
    """Echtes Git-Repo mit base_commit, danach ein Commit (7 Produktiv- + 5 Testzeilen)."""
    project = tmp_path
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "t@example.com")
    _git(project, "config", "user.name", "T")
    (project / "README.txt").write_text("start\n")
    _git(project, "add", "README.txt")
    _git(project, "commit", "-q", "-m", "base")
    base = _git(project, "rev-parse", "HEAD")

    (project / "src").mkdir()
    (project / "tests").mkdir()
    (project / "src" / "app.py").write_text("".join(f"x{i} = {i}\n" for i in range(7)))
    (project / "tests" / "test_app.py").write_text("".join(f"def test_{i}(): pass\n" for i in range(5)))
    _git(project, "add", "src", "tests")
    _git(project, "commit", "-q", "-m", "change")

    (project / ".claude" / "workflows").mkdir(parents=True, exist_ok=True)
    _write_workflow(
        project, workflow_type="feature-fast", current_phase="phase7_validate",
        base_commit=base_commit or base, loc_delta_current="+0",
    )
    return project, base


def _as_int(value) -> int:
    return int(str(value).lstrip("+"))


def test_final_loc_survives_commit_and_never_blocks_complete(tmp_path):  # AC-9
    # --- Fall 1: gueltige Messung, die Aenderung ist bereits committet (loc_delta_current waere +0)
    ok_root = tmp_path / "ok"
    ok_root.mkdir()
    project, _base = _git_project(ok_root)

    fn = _py(project, """
        import workflow
        print(json.dumps({"has": hasattr(workflow, "_final_loc")}))
    """)
    assert fn["has"], "workflow._final_loc existiert nicht"

    wl = _run_workflow(project, ["write-log", "success"])
    assert wl.returncode == 0, wl.stdout + wl.stderr
    log = _read_log(project)
    assert re.search(r"^effort_budget_exceeded:\s*\d+\s*$", log, re.M), \
        f"effort_budget_exceeded fehlt im write-log:\n{log}"
    assert re.search(r"^scope_loc_delta:\s*\+?7\s*$", log, re.M), \
        f"scope_loc_delta nennt nicht die tatsaechlichen 7 Produktivzeilen:\n{log}"

    done = _run_workflow(project, ["complete"])
    assert done.returncode == 0, done.stdout + done.stderr
    archived = json.loads(
        (project / ".claude" / "workflows" / "_archive" / "wf-250b.json").read_text())
    assert _as_int(archived.get("loc_delta_final")) == 7, archived.get("loc_delta_final")
    assert _as_int(archived.get("loc_delta_test_final")) == 5, archived.get("loc_delta_test_final")

    # --- Fall 2: Messung schlaegt fehl (base_commit existiert nicht) -> Abschluss wird NICHT blockiert
    bad_root = tmp_path / "bad"
    bad_root.mkdir()
    project2, _ = _git_project(bad_root, base_commit="0" * 39 + "1")
    wl2 = _run_workflow(project2, ["write-log", "success"])
    assert wl2.returncode == 0, wl2.stdout + wl2.stderr
    assert re.search(r"^effort_budget_exceeded:", _read_log(project2), re.M)
    done2 = _run_workflow(project2, ["complete"])
    assert done2.returncode == 0, "fehlgeschlagene Messung blockiert den Abschluss"
    archived2 = json.loads(
        (project2 / ".claude" / "workflows" / "_archive" / "wf-250b.json").read_text())
    assert not archived2.get("loc_delta_final"), \
        "bei fehlgeschlagener Messung darf nichts gespeichert werden"
