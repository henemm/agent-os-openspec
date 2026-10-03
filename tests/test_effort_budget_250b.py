"""RED-Tests fuer Issue #250, Teil B: Aufwandsbremse.

Spec: docs/specs/feat-250-teil-b-aufwandsbremse.md (AC-1 bis AC-9).

Ueberschreitet ein Workflow sein Stufen-Budget (Fix-Loops, Phasen-Wiedereintritte),
wird der PO gefragt statt still weitergearbeitet. Es wird nie ein Phasenwechsel
verweigert. Die 15-Minuten-Bremse des post_implementation_gate wird stufenabhaengig,
und der Abschluss erfasst die tatsaechliche Aenderungsgroesse (`loc_delta_final`).

Alle Tests sind hermetisch: eigenes tmp-Projekt, Subprozesse, eigene config.yaml.

Zur Zaehlweise (AC-6): "Wiedereintritt" = Betreten einer Phase nach dem ersten Mal
(Eintraege in `phase_transitions` mit `to == Phase`, minus 1). "Ueberschritten" heisst
strikt groesser als die Grenze. Bei Grenze 2 meldet daher erst das vierte Betreten
(3 Wiedereintritte); das dritte Betreten (2 Wiedereintritte) liegt genau auf der Grenze.
"""

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"

WF = "wf-250b"
WF_CREATED = "2026-10-03T10:00:00.000000"

BUDGET_CONFIG = textwrap.dedent("""\
    effort_budget:
      enabled: true
      feature-fast: {max_fix_loops: 1, max_phase_reentries: 1, batch_window_min: 30}
      feature:      {max_fix_loops: 2, max_phase_reentries: 2, batch_window_min: 15}
    """)

KILL_SWITCH_CONFIG = BUDGET_CONFIG.replace("enabled: true", "enabled: false")


# --- Hilfen ---------------------------------------------------------------


def _env(project: Path) -> dict:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    return env


def _project(tmp_path: Path, config: "str | None", workflow: dict) -> Path:
    """Main-Repo (.git als DIR) mit optionaler config.yaml und aktivem Workflow."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "name": WF,
        "workflow_type": "feature",
        "current_phase": "phase6b_adversary",
        "created": WF_CREATED,
        "phase_transitions": [],
        "phase_log": [],
        "fix_loop_iterations": 0,
        "test_artifacts": [],
    }
    base.update(workflow)
    (wf_dir / f"{WF}.json").write_text(json.dumps(base))
    if config is not None:
        (tmp_path / "config.yaml").write_text(config)
    return tmp_path


def _py(project: Path, code: str) -> subprocess.CompletedProcess:
    """Python-Schnipsel mit den Hooks im Importpfad, im Kontext des tmp-Projekts."""
    prelude = f"import sys, json; sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
    return subprocess.run(
        [sys.executable, "-c", prelude + textwrap.dedent(code)],
        capture_output=True, text=True, env=_env(project), cwd=str(project),
    )


def _cli(project: Path, args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py")] + args,
        capture_output=True, text=True, env=_env(project), cwd=str(project),
    )


def _state(project: Path) -> dict:
    return json.loads((project / ".claude" / "workflows" / f"{WF}.json").read_text())


def _gate_events(project: Path) -> list:
    path = project / ".claude" / "gate-events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _budget_events_of(project: Path, hook: str = "effort_budget") -> list:
    return [e for e in _gate_events(project) if e.get("hook") == hook]


# --- AC-1: Konfiguration --------------------------------------------------


def test_config_block_and_stage_lookup(tmp_path):
    """AC-1: config.yaml hat den Block; get_effort_budget liefert die Werte je Stufe."""
    block = yaml.safe_load((REPO_ROOT / "config.yaml").read_text()).get("effort_budget")
    assert isinstance(block, dict), "config.yaml enthaelt keinen Block `effort_budget`"
    assert "enabled" in block
    for stage in ("feature-fast", "feature"):
        for key in ("max_fix_loops", "max_phase_reentries", "batch_window_min"):
            assert key in block[stage], f"effort_budget.{stage}.{key} fehlt"

    project = _project(tmp_path, BUDGET_CONFIG, {})
    result = _py(project, """
        import config_loader
        out = {s: config_loader.get_effort_budget(s)
               for s in ("feature-fast", "feature", "bug", "express")}
        print(json.dumps(out))
    """)
    assert result.returncode == 0, result.stderr
    got = json.loads(result.stdout)
    assert got["feature-fast"] == {"max_fix_loops": 1, "max_phase_reentries": 1, "batch_window_min": 30}
    assert got["feature"] == {"max_fix_loops": 2, "max_phase_reentries": 2, "batch_window_min": 15}
    # Altbestand-Typen fallen auf `feature`
    assert got["bug"] == got["feature"]
    assert got["express"] == got["feature"]


# --- AC-2: Eintrag und Gate-Event-Log ------------------------------------


def test_exceeding_fix_loops_is_recorded_and_logged(tmp_path):
    """AC-2: 2 Fix-Loops bei Grenze 1 -> budget_events und Gate-Event-Log."""
    project = _project(tmp_path, BUDGET_CONFIG, {})
    result = _py(project, """
        import workflow
        data = {"workflow_type": "feature-fast", "current_phase": "phase6b_adversary",
                "fix_loop_iterations": 2, "phase_transitions": [], "phase_log": []}
        returned = workflow.record_transition(data, "phase6_implement")
        print(json.dumps({"returned": returned, "events": data.get("budget_events")}))
    """)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    metrics = [(e["metric"], e["value"], e["limit"]) for e in out["returned"]]
    assert ("fix_loops", 2, 1) in metrics
    assert out["events"], "budget_events fehlt im State"

    events = _budget_events_of(project)
    assert events, "kein Gate-Event mit hook=effort_budget"
    assert "fix_loops" in events[0]["reason"] or "Fix" in events[0]["reason"]


# --- AC-3: Ausgabe von `workflow.py phase` --------------------------------


def test_phase_command_prints_question_to_po(tmp_path):
    """AC-3: Die Ausgabe enthaelt RUECKFRAGE AN DEN PO mit Stufe, Metrik, Stand, Grenze."""
    # Grenze (feature) 2; der Wechsel zurueck nach phase6 hebt den Zaehler auf 3.
    project = _project(tmp_path, BUDGET_CONFIG, {"fix_loop_iterations": 2})
    result = _cli(project, ["phase", "phase6_implement"])
    assert result.returncode == 0, result.stderr
    out = result.stdout + result.stderr
    assert "RÜCKFRAGE AN DEN PO:" in out
    assert "feature" in out
    assert "fix_loops" in out
    assert "3" in out and "2" in out
    assert _state(project)["current_phase"] == "phase6_implement"


# --- AC-4: milder Fall ----------------------------------------------------


def test_within_budget_stays_silent(tmp_path):
    """AC-4: Innerhalb des Budgets weder Eintrag noch Rueckfrage."""
    # Gegenprobe: dieselbe Config meldet bei Ueberschreitung (sonst waere Stille wertlos)
    (tmp_path / "over").mkdir()
    over = _project(tmp_path / "over", BUDGET_CONFIG, {"fix_loop_iterations": 2})
    over_run = _cli(over, ["phase", "phase6_implement"])
    assert "RÜCKFRAGE AN DEN PO:" in over_run.stdout + over_run.stderr

    project = _project(tmp_path, BUDGET_CONFIG, {"fix_loop_iterations": 0})
    result = _cli(project, ["phase", "phase6_implement"])
    assert result.returncode == 0, result.stderr
    assert "RÜCKFRAGE" not in result.stdout + result.stderr
    assert not _state(project).get("budget_events")
    assert _budget_events_of(project) == []


# --- AC-5: nie blockieren -------------------------------------------------


def test_budget_never_blocks_a_transition(tmp_path):
    """AC-5: Trotz ueberschrittenem Budget gelingen die Wechsel nach Adversary und Validate."""
    project = _project(tmp_path, BUDGET_CONFIG, {
        "current_phase": "phase6_implement",
        "fix_loop_iterations": 9,
        "context_file": "docs/context/x.md",
        "spec_file": "docs/specs/nicht-vorhanden.md",
        "spec_approved": True,
        "red_test_done": True,
    })
    first = _cli(project, ["phase", "phase6b_adversary"])
    assert first.returncode == 0, first.stdout + first.stderr
    # Gegenprobe: das Budget IST ueberschritten und wird gemeldet — der Wechsel gelingt trotzdem
    assert "RÜCKFRAGE AN DEN PO:" in first.stdout + first.stderr
    assert _state(project)["current_phase"] == "phase6b_adversary"
    second = _cli(project, ["phase", "phase7_validate"])
    assert second.returncode == 0, second.stdout + second.stderr
    assert _state(project)["current_phase"] == "phase7_validate"
    assert "BLOCKED" not in first.stderr + second.stderr


# --- AC-6: Wiedereintritte ------------------------------------------------


def test_reentries_counted_and_not_repeated(tmp_path):
    """AC-6: phase_reentries wird gemeldet, ein gleicher Stand nicht erneut."""
    project = _project(tmp_path, BUDGET_CONFIG, {})
    result = _py(project, """
        import workflow
        def entry(frm, to):
            return {"from": frm, "to": to, "at": "2026-10-03T10:00:00", "trigger": "command"}
        # zweimal betreten (1 Wiedereintritt), jetzt das dritte Mal -> 2 = genau auf der Grenze
        data = {"workflow_type": "feature", "current_phase": "phase6b_adversary",
                "fix_loop_iterations": 0, "phase_log": [],
                "phase_transitions": [entry("phase5_tdd_red", "phase6_implement"),
                                      entry("phase6b_adversary", "phase6_implement")]}
        at_limit = workflow.record_transition(data, "phase6_implement")
        data["current_phase"] = "phase6_implement"
        # viertes Betreten -> 3 Wiedereintritte, Grenze 2 -> gemeldet
        data["current_phase"] = "phase6b_adversary"
        over = workflow.record_transition(data, "phase6_implement")
        data["current_phase"] = "phase6_implement"
        # derselbe Stand bei einem Wechsel, der phase6 nicht betritt -> nicht erneut
        again = workflow.record_transition(data, "phase6b_adversary")
        print(json.dumps({"at_limit": at_limit, "over": over, "again": again}))
    """)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["at_limit"] == [], "genau auf der Grenze ist noch keine Ueberschreitung"
    assert [(e["metric"], e["value"], e["limit"]) for e in out["over"]] == [("phase_reentries", 3, 2)]
    assert out["again"] == [], "derselbe Stand darf nicht erneut gemeldet werden"


# --- AC-7: Kill-Switch ----------------------------------------------------


def test_kill_switch_restores_old_behaviour(tmp_path):
    """AC-7: enabled=false -> keine Meldung, Fenster fuer alle Stufen 15 Minuten."""
    # Gegenprobe: derselbe Stand mit eingeschaltetem Budget meldet
    (tmp_path / "on").mkdir()
    on = _project(tmp_path / "on", BUDGET_CONFIG, {"fix_loop_iterations": 9})
    on_run = _cli(on, ["phase", "phase6_implement"])
    assert "RÜCKFRAGE AN DEN PO:" in on_run.stdout + on_run.stderr

    project = _project(tmp_path, KILL_SWITCH_CONFIG, {"fix_loop_iterations": 9})
    result = _cli(project, ["phase", "phase6_implement"])
    assert result.returncode == 0, result.stderr
    assert "RÜCKFRAGE" not in result.stdout + result.stderr
    assert not _state(project).get("budget_events")
    assert _budget_events_of(project) == []

    # Fenster: feature-fast haette 30 min, mit Kill-Switch gelten 15 min -> 20 min alter Lock blockt
    gate_project = _gate_project(tmp_path / "gate", KILL_SWITCH_CONFIG, "feature-fast", age_min=20)
    assert _run_gate(gate_project).returncode == 2


# --- AC-8: Batch-Fenster je Stufe ----------------------------------------


def _gate_project(root: Path, config: "str | None", wf_type: str, age_min: float) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    project = _project(root, config, {
        "workflow_type": wf_type, "current_phase": "phase6_implement",
    })
    (project / ".claude" / f"pending_validation_{WF}.json").write_text(json.dumps({
        "workflow": WF, "workflow_created": WF_CREATED,
        "created": time.time() - age_min * 60, "created_iso": "irrelevant",
    }))
    return project


def _run_gate(project: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "post_implementation_gate.py")],
        input=json.dumps({"tool_input": {"file_path": "src/foo.py"}}),
        capture_output=True, text=True, env=_env(project), cwd=str(project),
    )


def test_batch_window_depends_on_stage(tmp_path):
    """AC-8: 20 Minuten alter Lock: feature-fast (30 min) erlaubt, feature (15 min) blockiert."""
    fast = _gate_project(tmp_path / "fast", BUDGET_CONFIG, "feature-fast", age_min=20)
    full = _gate_project(tmp_path / "full", BUDGET_CONFIG, "feature", age_min=20)
    assert _run_gate(fast).returncode == 0
    assert _run_gate(full).returncode == 2
    # ohne Config bleibt das bisherige Verhalten (15 min) auch fuer feature-fast
    bare = _gate_project(tmp_path / "bare", None, "feature-fast", age_min=20)
    assert _run_gate(bare).returncode == 2


# --- AC-9: Abschluss-LoC --------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.email=t@example.org", "-c", "user.name=T", *args],
        cwd=str(cwd), capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _complete(project: Path) -> subprocess.CompletedProcess:
    """`finish`; neutralisiert Adversary-Nachweis und Phasen-Vorbedingungen (hier nicht Gegenstand der Pruefung; geprueft wird die LoC-Messung beim Abschluss)."""
    return _py(project, """
        import adversary_dialog as ad
        ad.check_dialog_evidence = lambda *a, **k: None
        ad.coverage_gate_enabled = lambda: False
        import workflow
        workflow._validate_transition = lambda *a, **k: None
        sys.argv = ["workflow.py", "finish"]
        workflow.main()
    """)


def test_final_loc_survives_commit_and_never_blocks_complete(tmp_path):
    """AC-9: Nach einem Commit steht die echte Groesse im Archiv; ein Messfehler blockiert nicht."""
    project = tmp_path / "good"
    project.mkdir()
    _git(project, "init", "-q")
    (project / "README.md").write_text("start\n")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "base")
    base = _git(project, "rev-parse", "HEAD")

    (project / "src").mkdir()
    (project / "tests").mkdir()
    (project / "src" / "neu.py").write_text("".join(f"x{i} = {i}\n" for i in range(10)))
    (project / "tests" / "test_neu.py").write_text("".join(f"t{i} = {i}\n" for i in range(4)))
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "change")

    _project(project, BUDGET_CONFIG, {
        "current_phase": "phase7_validate",
        "base_commit": base,
        "loc_delta_current": "+0",
        "fix_loop_iterations": 5,
        "adversary_verdict": "VERIFIED",
    })
    log = _cli(project, ["write-log"])
    assert log.returncode == 0, log.stderr
    log_text = next((project / ".claude" / "workflows" / "_log").glob("*.yaml")).read_text()
    assert "scope_loc_delta: +10" in log_text, log_text
    assert "effort_budget_exceeded:" in log_text, log_text

    done = _complete(project)
    assert done.returncode == 0, done.stdout + done.stderr
    archived = json.loads(
        (project / ".claude" / "workflows" / "_archive" / f"{WF}.json").read_text()
    )
    assert archived["loc_delta_final"] == 10
    assert archived["loc_delta_test_final"] == 4

    # Messung schlaegt fehl (unbekannter base_commit) -> Abschluss gelingt trotzdem
    broken = tmp_path / "broken"
    broken.mkdir()
    _git(broken, "init", "-q")
    (broken / "a.txt").write_text("a\n")
    _git(broken, "add", "-A")
    _git(broken, "commit", "-q", "-m", "base")
    _project(broken, BUDGET_CONFIG, {
        "current_phase": "phase7_validate",
        "base_commit": "0" * 40,
        "adversary_verdict": "VERIFIED",
    })
    assert _cli(broken, ["write-log"]).returncode == 0
    done_broken = _complete(broken)
    assert done_broken.returncode == 0, done_broken.stdout + done_broken.stderr
    archived_broken = json.loads(
        (broken / ".claude" / "workflows" / "_archive" / f"{WF}.json").read_text()
    )
    assert "loc_delta_final" not in archived_broken


# ===========================================================================
# Issue #341: Randfaelle der Abschluss-Zeilenzaehlung und der Rueckfrage
# Spec: docs/specs/feat-341-aufwandsbremse-randfaelle.md (AC-1 bis AC-7)
# ===========================================================================


def _lines(prefix: str, n: int) -> str:
    return "".join(f"{prefix}{i} = {i}\n" for i in range(n))


def _repo(root: Path) -> str:
    """Echtes Git-Repo auf Zweig main mit einem Basis-Commit; liefert dessen SHA."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "core.quotePath", "true")  # Git-Standard, explizit gegen globale Abweichung
    (root / "README.md").write_text("start\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return _git(root, "rev-parse", "HEAD")


def _measure(project: Path, data: dict):
    """`workflow._final_loc(data)` im Kontext des Repos; Ergebnis als Liste oder None."""
    _project(project, None, {})
    result = _py(project, f"""
        import workflow
        res = workflow._final_loc({data!r})
        print(json.dumps(list(res) if res is not None else None))
    """)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


# --- AC-1: Rebase ----------------------------------------------------------


def test_final_loc_ignores_main_lines_after_rebase(tmp_path):
    """AC-1: Nach Rebase auf main zaehlen nur die 10 eigenen Zeilen, nicht die 100 aus main."""
    repo = tmp_path / "repo"
    base = _repo(repo)

    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "src").mkdir()
    (repo / "src" / "feature.py").write_text(_lines("f", 10))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feature")

    _git(repo, "checkout", "-q", "main")
    (repo / "lib").mkdir()
    (repo / "lib" / "main_work.py").write_text(_lines("m", 100))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main work")

    _git(repo, "checkout", "-q", "feature")
    _git(repo, "rebase", "-q", "main")
    _git(repo, "update-ref", "refs/remotes/origin/main", "main")
    # Gegenprobe: der alte base_commit ist nach dem Rebase weiterhin Vorfahre von HEAD
    subprocess.run(["git", "merge-base", "--is-ancestor", base, "HEAD"], cwd=str(repo), check=True)

    assert _measure(repo, {"base_commit": base}) == [10, 0]


# --- AC-2: Umbenennung -----------------------------------------------------


def test_final_loc_follows_rename_to_new_path(tmp_path):
    """AC-2: core/hooks/old.py -> tests/test_new.py mit 5 geaenderten Zeilen ergibt (0, 5)."""
    repo = tmp_path / "repo"
    _repo(repo)
    (repo / "core" / "hooks").mkdir(parents=True)
    original = [f"value_{i} = {i}  # unveraenderte Zeile\n" for i in range(30)]
    (repo / "core" / "hooks" / "old.py").write_text("".join(original))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "old file")
    base = _git(repo, "rev-parse", "HEAD")

    (repo / "tests").mkdir()
    _git(repo, "mv", "core/hooks/old.py", "tests/test_new.py")
    changed = list(original)
    for i in range(5):
        changed[i] = f"value_{i} = {i * 100}  # geaendert\n"
    (repo / "tests" / "test_new.py").write_text("".join(changed))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "rename")
    # Gegenprobe: Git erkennt die Umbenennung (sonst prueft der Test den Fall nicht)
    status = _git(repo, "diff", "--name-status", "-M", base, "HEAD")
    assert status.startswith("R"), status

    assert _measure(repo, {"base_commit": base}) == [0, 5]


# --- AC-3: Umlaut-Pfad -----------------------------------------------------


def test_final_loc_matches_umlaut_path_as_test(tmp_path):
    """AC-3: tests/Prüfung_test.py mit 7 Zeilen zaehlt als Test (0, 7), nicht als Code."""
    repo = tmp_path / "repo"
    base = _repo(repo)
    (repo / "tests").mkdir()
    (repo / "tests" / "Prüfung_test.py").write_text(_lines("p", 7))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "umlaut")
    # Gegenprobe: ohne -z quotet Git diesen Pfad (Ausgangslage des Fehlers)
    assert '"tests/Pr\\303\\274fung_test.py"' in _git(repo, "diff", base, "--numstat")

    assert _measure(repo, {"base_commit": base}) == [0, 7]


# --- AC-4 / AC-5: Rueckfrage bei der Freigabe ------------------------------


APPROVAL_CONFIG = BUDGET_CONFIG + "po_briefing_gate: {enabled: false}\n"


def _spec_phase_project(root: Path, prior_approvals: int) -> Path:
    """phase3_spec ohne spec_file (ADR-/Briefing-Gate greifen nicht), mit frueheren Freigaben."""
    root.mkdir(parents=True, exist_ok=True)
    transitions = [
        {"from": "phase3_spec", "to": "phase4_approved", "at": "2026-10-03T10:00:00", "trigger": "approval"}
        for _ in range(prior_approvals)
    ]
    return _project(root, APPROVAL_CONFIG, {
        "workflow_type": "feature",
        "current_phase": "phase3_spec",
        "spec_approved": False,
        "phase_transitions": transitions,
    })


def _listener(project: Path, wrapper: "str | None" = None) -> subprocess.CompletedProcess:
    """Echter Listener per Subprozess, stdin `{"prompt": "approved"}`."""
    if wrapper is None:
        cmd = [sys.executable, str(HOOKS_DIR / "phase_listener.py")]
    else:
        prelude = f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
        cmd = [sys.executable, "-c", prelude + textwrap.dedent(wrapper)]
    return subprocess.run(
        cmd, input=json.dumps({"prompt": "approved"}),
        capture_output=True, text=True, env=_env(project), cwd=str(project),
    )


def _additional_context(stdout: str) -> str:
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            out = json.loads(line)
            return (out.get("hookSpecificOutput") or {}).get("additionalContext") or ""
    return ""


def _assert_approved(project: Path, run: subprocess.CompletedProcess) -> None:
    state = _state(project)
    assert state.get("spec_approved") is True, f"{state}\nstdout={run.stdout!r}\nstderr={run.stderr!r}"
    assert state.get("current_phase") == "phase4_approved", state


def test_approval_prints_budget_question(tmp_path):
    """AC-4: Freigabe, deren Betreten von phase4_approved das Budget reisst -> Rueckfrage im Kontext."""
    # 3 fruehere + diese Freigabe = 4 Betreten -> phase_reentries 3 > Grenze 2
    project = _spec_phase_project(tmp_path, prior_approvals=3)
    run = _listener(project)
    assert run.returncode == 0, run.stderr
    _assert_approved(project, run)
    # Gegenprobe: das Budget IST ueberschritten und protokolliert
    assert [(e["metric"], e["value"]) for e in _state(project).get("budget_events", [])] == [
        ("phase_reentries", 3)
    ]
    context = _additional_context(run.stdout)
    assert "RÜCKFRAGE AN DEN PO" in context, f"stdout={run.stdout!r}"


def test_approval_within_budget_silent_and_never_blocked(tmp_path):
    """AC-5: Innerhalb Budget still; wirft die Rueckfragen-Ausgabe, gilt die Freigabe trotzdem."""
    # (a) innerhalb des Budgets: erste Freigabe
    quiet = _spec_phase_project(tmp_path / "quiet", prior_approvals=0)
    run = _listener(quiet)
    assert run.returncode == 0, run.stderr
    _assert_approved(quiet, run)
    assert "RÜCKFRAGE AN DEN PO" not in run.stdout + run.stderr
    assert not _state(quiet).get("budget_events")

    # (b) Ueberschreitung, aber die Formatierung der Rueckfrage wirft
    broken = _spec_phase_project(tmp_path / "broken", prior_approvals=3)
    run = _listener(broken, wrapper="""
        import workflow
        if not hasattr(workflow, "format_budget_question"):
            raise SystemExit("workflow.format_budget_question fehlt")
        def _boom(*args, **kwargs):
            raise RuntimeError("Ausgabe der Rueckfrage kaputt")
        workflow.format_budget_question = _boom
        import phase_listener
        phase_listener.main()
    """)
    _assert_approved(broken, run)
    assert run.returncode == 0, run.stderr


# --- AC-7: Messfehler ------------------------------------------------------


def test_final_loc_error_still_returns_none(tmp_path):
    """AC-7: Unbekannter base_commit bzw. nicht aufloesbare Basis -> None; Abschluss gelingt."""
    repo = tmp_path / "repo"
    _repo(repo)  # kein origin/main
    (repo / "src").mkdir()
    (repo / "src" / "x.py").write_text(_lines("x", 3))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "change")

    assert _measure(repo, {"base_commit": "0" * 40}) is None
    assert _measure(repo, {}) is None

    _project(repo, BUDGET_CONFIG, {
        "current_phase": "phase7_validate",
        "base_commit": "0" * 40,
        "adversary_verdict": "VERIFIED",
    })
    assert _cli(repo, ["write-log"]).returncode == 0
    done = _complete(repo)
    assert done.returncode == 0, done.stdout + done.stderr
    archived = json.loads((repo / ".claude" / "workflows" / "_archive" / f"{WF}.json").read_text())
    assert "loc_delta_final" not in archived
