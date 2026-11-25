"""Auto-/clear-Grenze beim Phasenwechsel selbst vermerken (Issue #497).

Spec: docs/specs/fix-497-autoclear-grenze-beim-phasenwechsel.md (AC-1 bis AC-7;
AC-8 = E2E-Skript, AC-9 = Regressionslauf).

Seit #495 entsteht der Grenz-Vermerk `auto_clear_boundary` nur durch einen
zusaetzlichen `workflow.py autoclear`-Aufruf. Kuenftig schreibt ihn der
erzwungene Phasenwechsel (`record_transition`) selbst — fuer genau fuenf
Grenzen, nur bei aktivem Auto-/clear (Herdr-Pane + Opt-in), fail-open.

Muster: tests/test_autoclear_boundary_495.py; Stub- und Hook-Helfer aus
tests/test_herdr_auto_clear_467.py. Alle Phasenwechsel laufen als Subprozess
(`workflow.py phase`, `workflow.py auto-approve`, `phase_listener.py`).

Abgeloest durch #662 (docs/specs/feat-662-kette-flach.md): Kein Phasenwechsel
schreibt mehr einen Vermerk. `test_phase_command_records_boundary_per_table` und
`test_approval_paths_record_boundary` sind entfallen, ersetzt durch
tests/test_auto_chain_flat_662.py::test_phase_change_writes_no_boundary (AC-4);
die uebrigen Tests pruefen das neue Verhalten bzw. den Leser `_boundary_fresh`
(Runner-Interna bis #663).
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_herdr_auto_clear_467 import (  # noqa: E402
    AUTO_ON,
    FOOTER_GATE,
    HOOKS_DIR,
    _du,
    _make_stub,
    _message,
)

WORKFLOW = HOOKS_DIR / "workflow.py"

WF = "fix-497-demo"
ISSUE = "#497"
PANE = "pane-497"

# Phasen-Tests: Briefing-Gate aus, damit Grenzen hinter der Freigabe ohne
# echtes Briefing erreichbar sind (Gegenstand ist der Vermerk, nicht das Gate).
CFG_ON = AUTO_ON + "po_briefing_gate:\n  enabled: false\n"
CFG_OPT_OUT = "herdr:\n  enabled: true\npo_briefing_gate:\n  enabled: false\n"

# Zustand, der alle Vorbedingungen bis vor phase8 erfuellt (ohne spec_file:
# sonst waere der Folgebefehl in phase3_spec das Freigabewort statt eines Befehls).
_PRE_APPROVAL = {"context_file": "docs/context.md"}
_POST_APPROVAL = {"context_file": "docs/context.md", "spec_file": "docs/specs/missing.md",
                  "spec_approved": True, "red_test_done": True}

# (von, nach, Zusatzfelder, erwarteter Folgebefehl ohne #N)
BOUNDARIES = [
    ("phase1_context", "phase2_analyse", _PRE_APPROVAL, "/20-analyse"),
    ("phase2_analyse", "phase3_spec", _PRE_APPROVAL, "/30-write-spec"),
    ("phase5_tdd_red", "phase6_implement", _POST_APPROVAL, "/50-implement"),
    # Phase 7 verlangt seit fix-schritte-ueberspringen den Adversary-Nachweis;
    # _case legt dafuer einen gestempelten Dialog an (_adversary_evidence).
    ("phase6b_adversary", "phase7_validate", _POST_APPROVAL, "/60-validate"),
]


# --- Helfer -----------------------------------------------------------------

def _project(root: Path, phase: str, config: "str | None" = CFG_ON, **fields) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    data = {"name": WF, "workflow_type": "feature", "current_phase": phase,
            "phase_transitions": [], "phase_log": [], "approvals": []}
    data.update(fields)
    (proj / ".claude" / "workflows" / f"{WF}.json").write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(WF)
    if config is not None:
        (proj / "openspec.yaml").write_text(config)
    return proj


def _env(proj: Path, root: Path, *, herdr: bool = True, **extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    if herdr:
        stub = _make_stub(root)
        env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": PANE,
                    "HERDR_BIN_PATH": str(stub), "STUB_LOG": str(root / "stub.log")})
    env.update(extra)
    return env


def _case(tmp_path: Path, label: str, phase: str, *, config: "str | None" = CFG_ON,
          herdr: bool = True, **fields):
    root = tmp_path / label
    root.mkdir(parents=True)
    proj = _project(root, phase, config=config, **fields)
    env = _env(proj, root, herdr=herdr)
    if phase == "phase6b_adversary":
        # Seit fix-schritte-ueberspringen verlangt der Wechsel nach Phase 7 den
        # Adversary-Nachweis; fuer Rueckspruenge ist er unschaedlich.
        _adversary_evidence(proj, env)
    return proj, env, root


def _wf(proj: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(WORKFLOW), *args], capture_output=True,
                          text=True, env=env, cwd=str(proj), timeout=60)


def _state(proj: Path) -> dict:
    return json.loads((proj / ".claude" / "workflows" / f"{WF}.json").read_text())


def _adversary_evidence(proj: Path, env: dict) -> None:
    """Gestempelter, registrierter Dialog + VERIFIED: seit fix-schritte-ueberspringen
    Voraussetzung fuer den Wechsel nach phase7_validate (Vorbild: test_adversary_evidence_gate_253)."""
    (proj / "src").mkdir(exist_ok=True)
    (proj / "src" / "checked_module.py").write_text("VALUE = 1\n")
    rel = f"docs/artifacts/{WF}/adversary-dialog.md"
    art = proj / rel
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(
        f"# Adversary Dialog — {WF}\n\n## Checkliste\n"
        "- [x] AC-1: Vermerk entsteht — Beweis: Testlauf\n"
        "  Code reference: src/checked_module.py:1\n\n## Dialog\n\n"
        "### Runde 1\n**Adversary:** A1\n**Implementierer:** B1\n\n"
        "### Runde 2\n**Adversary:** A2\n**Implementierer:** B2\n\nVERDICT: VERIFIED\n")
    stamp = subprocess.run([sys.executable, str(WORKFLOW.parent / "adversary_dialog.py"),
                            "stamp", str(art)], capture_output=True, text=True, env=env,
                           cwd=str(proj), timeout=60)
    assert stamp.returncode == 0, stamp.stdout + stamp.stderr
    data = _state(proj)
    data["adversary_verdict"] = "VERIFIED:Tests PASSED: 5 passed"
    data["test_artifacts"] = [{"type": "adversary_dialog", "path": rel,
                               "description": "dialog", "phase": "phase6b_adversary",
                               "created": "2026-11-06T10:00:00"}]
    (proj / ".claude" / "workflows" / f"{WF}.json").write_text(json.dumps(data))


# --- AC-3 (heute schon gruen: es gibt noch gar keinen Vermerk-Pfad) -----------

def test_non_boundaries_record_nothing(tmp_path):
    fast = dict(_POST_APPROVAL, workflow_type="feature-fast")
    cases = [
        ("phase4_approved", "phase5_tdd_red", _POST_APPROVAL),
        ("phase6_implement", "phase6b_adversary", _POST_APPROVAL),
        ("phase6b_adversary", "phase6_implement", _POST_APPROVAL),  # BROKEN-Fix-Schleife
        ("phase3_spec", "phase2_analyse", _PRE_APPROVAL),          # Ruecksprung
        ("phase7_validate", "phase3_spec", _POST_APPROVAL),         # Ruecksprung
        ("phase7_validate", "phase8_complete", fast),
    ]
    for src, dst, fields in cases:
        proj, env, root = _case(tmp_path, f"{src}-{dst}", src, **fields)
        res = _wf(proj, env, "phase", dst)
        assert res.returncode == 0, (src, dst, res.stdout, res.stderr)
        data = _state(proj)
        assert data["current_phase"] == dst, (src, dst, data["current_phase"])
        assert "auto_clear_boundary" not in data, (src, dst, data["auto_clear_boundary"])


# --- AC-4 (heute schon gruen) ----------------------------------------------

def test_auto_clear_off_records_nothing_output_unchanged(tmp_path):
    for src, dst, fields, _step in BOUNDARIES:
        # Referenz: ausserhalb von Herdr = Verhalten ohne Feature
        base_proj, base_env, _ = _case(tmp_path, f"base-{src}-{dst}", src,
                                       herdr=False, **fields)
        base = _wf(base_proj, base_env, "phase", dst)
        assert base.returncode == 0, base.stderr
        assert base.stdout == f"Set phase to: {dst}\n", base.stdout

        for label, kwargs in [("no-pane", {"herdr": False}),
                              ("opt-out", {"config": CFG_OPT_OUT})]:
            proj, env, _ = _case(tmp_path, f"{label}-{src}-{dst}", src, **kwargs, **fields)
            res = _wf(proj, env, "phase", dst)
            assert res.returncode == base.returncode == 0, (label, res.stderr)
            assert res.stdout == base.stdout, (label, res.stdout)
            assert res.stderr == base.stderr, (label, res.stderr)
            data = _state(proj)
            assert data["current_phase"] == dst
            assert "auto_clear_boundary" not in data, (label, src, dst)


# --- AC-5 -------------------------------------------------------------------

_WRAPPER = r"""
import sys
sys.path.insert(0, {hooks!r})
mode = sys.argv.pop(1)
marker = sys.argv.pop(1)
if mode == "no-bridge":
    class _Block:
        def find_spec(self, name, path=None, target=None):
            if name == "herdr_bridge":
                raise ImportError("herdr_bridge blockiert (Test #497)")
            return None
    sys.meta_path.insert(0, _Block())
import workflow
if mode == "raise":
    import inspect
    def _boom(data):
        # nur Aufrufe aus dem Phasenwechsel zaehlen (nicht Sidebar-Report o. ae.)
        if any(f.function == "record_transition" for f in inspect.stack()):
            open(marker, "a").write("called\n")
        raise RuntimeError("expected_footer_command kaputt (Test #497)")
    workflow.expected_footer_command = _boom
sys.argv[0] = "workflow.py"
workflow.main()
"""


def _run_wrapped(proj: Path, env: dict, root: Path, mode: str, *args: str):
    wrapper = root / "wrapper.py"
    wrapper.write_text(_WRAPPER.format(hooks=str(HOOKS_DIR)))
    marker = root / "called.txt"
    res = subprocess.run([sys.executable, str(wrapper), mode, str(marker), *args],
                         capture_output=True, text=True, env=env, cwd=str(proj), timeout=60)
    return res, marker


def test_boundary_error_never_aborts_transition(tmp_path):
    # (a) expected_footer_command wirft im Vermerk-Pfad
    proj, env, root = _case(tmp_path, "raise", "phase1_context", **_PRE_APPROVAL)
    res, marker = _run_wrapped(proj, env, root, "raise", "phase", "phase2_analyse")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "Traceback" not in res.stderr, res.stderr
    assert res.stdout == "Set phase to: phase2_analyse\n", res.stdout
    data = _state(proj)
    assert data["current_phase"] == "phase2_analyse"
    assert data["phase_transitions"][-1]["to"] == "phase2_analyse", data["phase_transitions"]
    assert "auto_clear_boundary" not in data, data["auto_clear_boundary"]
    # #662: der Vermerk-Pfad ist stillgelegt; er fragt den Folgebefehl gar nicht mehr ab
    assert not marker.exists(), (
        "Grenz-Phasenwechsel fragt expected_footer_command fuer einen Vermerk ab, "
        "obwohl Auto-/clear stillgelegt ist")

    # (b) herdr_bridge nicht importierbar (heute schon gruen)
    proj, env, root = _case(tmp_path, "no-bridge", "phase1_context", **_PRE_APPROVAL)
    res, _ = _run_wrapped(proj, env, root, "no-bridge", "phase", "phase2_analyse")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "Traceback" not in res.stderr, res.stderr
    assert res.stdout == "Set phase to: phase2_analyse\n", res.stdout
    data = _state(proj)
    assert data["current_phase"] == "phase2_analyse"
    assert data["phase_transitions"][-1]["to"] == "phase2_analyse"
    assert "auto_clear_boundary" not in data


# --- AC-6 -------------------------------------------------------------------

def test_footer_gate_stop_hook_active_discards_boundary(tmp_path):
    boundary = {"phase": "phase2_analyse", "command": f"/20-analyse {ISSUE}",
                "at": datetime.now().astimezone().isoformat()}
    wrong = _message("Kontext gesichert.", du=_du(f"/30-write-spec {ISSUE}"))

    def run(label: str, **fields):
        proj, env, root = _case(tmp_path, label, "phase2_analyse", **_PRE_APPROVAL, **fields)
        payload = {"session_id": "sess-497", "hook_event_name": "Stop", "cwd": str(proj),
                   "last_assistant_message": wrong, "stop_hook_active": True,
                   "prompt_id": "11111111-2222-3333-4444-555555555496"}
        res = subprocess.run([sys.executable, str(FOOTER_GATE)], input=json.dumps(payload),
                             capture_output=True, text=True, env=env, cwd=str(proj),
                             timeout=30)
        return proj, res

    _, base = run("baseline")
    proj, res = run("with-boundary", auto_clear_boundary=boundary)
    assert res.returncode == 0 == base.returncode, res.stderr
    assert res.stdout == base.stdout, res.stdout
    data = _state(proj)
    assert "auto_clear_boundary" not in data, (
        f"Vermerk bleibt nach zweimal falscher Fusszeile (stop_hook_active) stehen: "
        f"{data.get('auto_clear_boundary')}")


# --- AC-7 -------------------------------------------------------------------

def _has_tz(value: str) -> bool:
    return datetime.fromisoformat(value).tzinfo is not None


def test_timestamp_has_timezone_reader_accepts_both_no_writer(tmp_path):
    # Leser (heute schon gruen): tz-aware und naive, frisch und veraltet
    sys.path.insert(0, str(HOOKS_DIR))
    import herdr_bridge  # noqa: PLC0415
    now_aware = datetime.now().astimezone()
    now_naive = datetime.now()
    old = timedelta(minutes=20)
    cases = {
        "aware-fresh": (now_aware.isoformat(), True),
        "aware-utc-fresh": (datetime.now(timezone.utc).isoformat(), True),
        "aware-old": ((now_aware - old).isoformat(), False),
        "naive-fresh": (now_naive.isoformat(), True),
        "naive-old": ((now_naive - old).isoformat(), False),
    }
    for label, (at, fresh) in cases.items():
        assert herdr_bridge._boundary_fresh({"at": at}) is fresh, (label, at)

    # Zeitstempel-Helfer der (bis #663 stehenden) Schreiber: mit Zeitzone, frisch
    import workflow  # noqa: PLC0415
    at = workflow._boundary_timestamp()
    assert _has_tz(at), at
    assert herdr_bridge._boundary_fresh({"at": at}) is True, at

    # #662: weder Phasenwechsel noch `workflow.py autoclear` schreiben einen Vermerk
    proj, env, _ = _case(tmp_path, "phase", "phase1_context", **_PRE_APPROVAL)
    assert _wf(proj, env, "phase", "phase2_analyse").returncode == 0
    assert "auto_clear_boundary" not in _state(proj), _state(proj)
    proj, env, _ = _case(tmp_path, "autoclear", "phase2_analyse", **_PRE_APPROVAL)
    res = _wf(proj, env, "autoclear")
    assert res.stdout.strip() == "AUTO_CLEAR=off", (res.stdout, res.stderr)
    assert "auto_clear_boundary" not in _state(proj), _state(proj)
