"""Ruecksprung verwirft die alte Freigabe-Grundlage; endstate bevorzugt den
aktiven Workflow (Issues #647, #648, Schnitt 2 von Epic #649).

Spec: docs/specs/fix-647-648-ruecksprung.md (AC-1 bis AC-8; AC-9 = Regressionslauf).

Szenarien:
- #647: `phase4_approved` -> `phase3_spec`
- #648: `phase6_implement` -> `phase2_analyse` (danach wieder `phase3_spec`)

Hermetisch nach Vorlage tests/test_rueckspruung_405.py: CLAUDE_PROJECT_DIR=tmp_path,
`.git` als Ordner (kein Worktree), echte Subprozess-Aufrufe von workflow.py, echte
State-Dateien. Reine Funktionen (`next_step`, `expected_footer_command`,
`_auto_approval_pending`, `_apply_spec_approval`) laufen In-Process mit
CLAUDE_PROJECT_DIR per monkeypatch und frischen Caches (wie tests/test_spec_ampel_470.py).
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"

WF = "fix-647-ruecksprung-demo"
ISSUE = "647"
REL_SPEC = "docs/specs/fix-647-demo.md"
REL_BRIEFING = "docs/briefings/fix-647-demo.md"
REL_CONTEXT = "docs/context/fix-647-demo.md"

APPROVAL_STEP = "Freigabe der Spec (Stichwort: approved)"
AUTO_STEP = "Auto-Freigabe der Spec (workflow.py auto-approve)"
WRITE_SPEC = "/30-write-spec"

AUTO_CFG = "autonomy:\n  mode: auto\n"
KILL_SWITCH_CFG = "po_briefing_gate:\n  enabled: false\n"

SPEC_BODY = (
    "# Spec fix-647\n\n"
    "## Purpose\n\nRuecksprung verwirft das alte PO-Briefing.\n\n"
    "## Scope\n\n- Eine Datei im Modul.\n\n"
    "## Definition of Done\n\n- Fertig, wenn nach dem Ruecksprung die Spec dran ist.\n\n"
    "## Acceptance Criteria\n\n"
    "- **AC-1:** Given ein Ruecksprung / When next_step / Then /30-write-spec.\n\n"
    "## Test Plan\n\n- pytest tests/test_ruecksprung_briefing_647.py\n\n"
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** keine\n"
    "- **Rationale:** Bestehendes Muster, keine neue Architektur.\n"
)

BRIEFING = (
    "# PO-Briefing: fix-647\n\n"
    "## Was gebaut wird\n\n"
    "Nach einem Ruecksprung gilt das alte Briefing nicht mehr, die Spec wird neu geschrieben.\n\n"
    "## Definition of Done\n\n"
    "Fertig ist es, wenn nach dem Ruecksprung wieder die Spec als naechster Schritt dasteht.\n\n"
    "## Wie geprüft wird\n\n"
    "Automatische Tests springen zurueck und lesen den naechsten Schritt aus dem State.\n\n"
    "## Kritische Anmerkungen\n\n"
    "- Keine offene Entscheidung fuer den PO.\n\n"
    "## Ampel\n\n"
    "Ampel: gruen\n"
)


# --- Helpers ---------------------------------------------------------------

def _env(proj: Path, active: "str | None" = WF) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    if active:
        env["OPENSPEC_ACTIVE_WORKFLOW"] = active
    return env


def _cli(proj: Path, *args: str, active: "str | None" = WF) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args],
                          capture_output=True, text=True, env=_env(proj, active),
                          cwd=str(proj), timeout=60)


def _write(proj: Path, rel: str, content: str) -> None:
    path = proj / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _wf_path(proj: Path, name: str = WF) -> Path:
    return proj / ".claude" / "workflows" / f"{name}.json"


def _state(proj: Path, name: str = WF) -> dict:
    return json.loads(_wf_path(proj, name).read_text())


def _write_state(proj: Path, **fields) -> None:
    data = _state(proj)
    data.update(fields)
    _wf_path(proj).write_text(json.dumps(data))


def _base_project(proj: Path, config: "str | None" = None) -> Path:
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_archive").mkdir()
    (proj / "_home").mkdir()
    if config is not None:
        (proj / "openspec.yaml").write_text(config)
    return proj


def _phase_flags(phase: str) -> dict:
    """Flags, die ein Workflow in `phase` laut normalem Ablauf traegt."""
    order = ("phase3_spec", "phase4_approved", "phase5_tdd_red",
             "phase6_implement", "phase6b_adversary", "phase7_validate")
    idx = order.index(phase)
    return {
        "current_phase": phase,
        "spec_approved": idx >= 1,
        "red_test_done": idx >= 2,
        "green_approved": idx >= 4,
    }


def _make_project(proj: Path, phase: str, *, briefing: bool = True,
                  config: "str | None" = None,
                  workflow_type: str = "feature") -> Path:
    """Projekt mit Workflow in phase3_spec; Briefing ggf. ueber den echten
    `set-briefing` registriert, danach Phase/Flags wie im normalen Ablauf."""
    _base_project(proj, config)
    _write(proj, REL_CONTEXT, "# Kontext\n")
    _write(proj, REL_SPEC, SPEC_BODY)
    _write(proj, REL_BRIEFING, BRIEFING)
    _wf_path(proj).write_text(json.dumps({
        "name": WF, "workflow_type": workflow_type, "current_phase": "phase3_spec",
        "context_file": REL_CONTEXT, "spec_file": REL_SPEC,
        "spec_approved": False, "phase_transitions": [], "phase_log": [],
        "test_artifacts": [], "approvals": [],
    }))
    (proj / ".claude" / "active_workflow").write_text(WF)
    if briefing:
        reg = _cli(proj, "set-briefing", REL_BRIEFING)
        assert reg.returncode == 0, f"Testaufbau: set-briefing scheiterte: {reg.stderr}"
    _write_state(proj, **_phase_flags(phase))
    return proj


def _jump(proj: Path, target: str) -> None:
    res = _cli(proj, "phase", target)
    assert res.returncode == 0, f"phase {target} scheiterte: {res.stderr}"
    assert _state(proj)["current_phase"] == target


def _auto_approve(proj: Path) -> str:
    res = _cli(proj, "auto-approve")
    assert res.returncode == 0, (res.stdout, res.stderr)
    m = re.search(r"^AUTO_APPROVE=(\w+)\s*$", res.stdout, re.M)
    assert m, f"AUTO_APPROVE-Zeile fehlt: {res.stdout!r} {res.stderr!r}"
    return m.group(1), res.stdout


def _kv(stdout: str, key: str) -> "str | None":
    for line in stdout.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


@pytest.fixture
def inproc(monkeypatch):
    """In-Process-Zugriff auf workflow.py mit frischen Caches (wie #470)."""
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    import config_loader  # noqa: PLC0415
    import hook_utils  # noqa: PLC0415
    import workflow  # noqa: PLC0415

    def reset():
        for mod in (config_loader, hook_utils):
            for obj in vars(mod).values():
                clear = getattr(obj, "cache_clear", None)
                if callable(clear):
                    clear()

    def use(proj: Path):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
        monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
        # Modus nur aus der Projekt-Config, nie aus der Umgebung des Testlaufs
        monkeypatch.delenv("OPENSPEC_AUTONOMY", raising=False)
        reset()
        return workflow

    monkeypatch.delenv("OPENSPEC_AUTONOMY", raising=False)
    reset()
    yield use
    reset()


# --- AC-1 ------------------------------------------------------------------

def test_backstep_moves_briefing_to_history(tmp_path):
    """AC-1: Ruecksprung vor phase4_approved verschiebt `po_briefing` nach
    `po_briefing_history` (entry, reason "backstep <von>-><nach>", at)."""
    cases = [
        ("phase4_approved", "phase3_spec"),     # #647
        ("phase6_implement", "phase2_analyse"),  # #648
        ("phase3_spec", "phase2_analyse"),       # in phase3_spec nach set-briefing
    ]
    for i, (start, target) in enumerate(cases):
        proj = _make_project(tmp_path / f"case{i}", start)
        old = _state(proj).get("po_briefing")
        assert isinstance(old, dict), "Testaufbau: kein registriertes Briefing"

        _jump(proj, target)

        data = _state(proj)
        assert "po_briefing" not in data, (
            f"{start}->{target}: altes Briefing steht nach dem Ruecksprung noch im State: "
            f"{data.get('po_briefing')!r}"
        )
        hist = data.get("po_briefing_history")
        assert isinstance(hist, list) and hist, (
            f"{start}->{target}: po_briefing_history fehlt oder leer: {hist!r}"
        )
        last = hist[-1]
        assert last.get("entry") == old, (start, target, last)
        assert last.get("reason") == f"backstep {start}->{target}", (start, target, last)
        assert last.get("at"), (start, target, last)


# --- AC-2 ------------------------------------------------------------------

def test_history_keeps_at_most_five(tmp_path):
    """AC-2: Historie mit 5 Eintraegen + weiterer Ruecksprung -> genau 5, der
    neue zuletzt, der aelteste entfallen."""
    proj = _make_project(tmp_path / "proj", "phase4_approved")
    previous = [
        {"entry": {"file": f"docs/briefings/alt-{i}.md"},
         "reason": f"backstep phase4_approved->phase3_spec #{i}",
         "at": f"2026-11-0{i + 1}T10:00:00"}
        for i in range(5)
    ]
    _write_state(proj, po_briefing_history=previous)
    current = _state(proj)["po_briefing"]

    _jump(proj, "phase3_spec")

    hist = _state(proj).get("po_briefing_history")
    assert isinstance(hist, list), hist
    assert len(hist) == 5, f"Historie soll genau 5 Eintraege haben, hat {len(hist)}: {hist!r}"
    assert hist[-1].get("entry") == current, f"neuer Eintrag nicht zuletzt: {hist[-1]!r}"
    assert hist[-1].get("reason") == "backstep phase4_approved->phase3_spec", hist[-1]
    assert hist[:4] == previous[1:], (
        f"aeltester Eintrag soll entfallen, Rest in Reihenfolge bleiben: {hist[:4]!r}"
    )


# --- AC-3 ------------------------------------------------------------------

def test_next_step_after_backstep_is_write_spec(tmp_path, inproc):
    """AC-3: phase3_spec + spec_file + spec_rework -> `/30-write-spec` bzw.
    Fusszeile `/30-write-spec #647`; ohne Flag der Freigabe-Schritt."""
    # Manueller Modus
    manual = _make_project(tmp_path / "manual", "phase3_spec")
    wf = inproc(manual)
    base = {"name": WF, "workflow_type": "feature", "current_phase": "phase3_spec",
            "spec_file": REL_SPEC}
    assert wf.next_step(dict(base)) == APPROVAL_STEP
    rework = dict(base, spec_rework=True)
    assert wf.next_step(rework) == WRITE_SPEC, (
        f"spec_rework gesetzt, next_step meldet {wf.next_step(rework)!r}"
    )
    assert wf.expected_footer_command(rework) == f"{WRITE_SPEC} #{ISSUE}"

    # Auto-Modus mit gruener, registrierter Ampel
    auto = _make_project(tmp_path / "auto", "phase3_spec", config=AUTO_CFG)
    wf = inproc(auto)
    entry = _state(auto)["po_briefing"]
    green = dict(base, po_briefing=entry)
    assert wf.next_step(dict(green)) == AUTO_STEP, "Testaufbau: Auto-Schritt erwartet"
    assert wf.next_step(dict(green, spec_rework=True)) == WRITE_SPEC

    # Echter Ruecksprung #647: der State danach fuehrt zu /30-write-spec
    real = _make_project(tmp_path / "real", "phase4_approved")
    wf = inproc(real)
    _jump(real, "phase3_spec")
    data = _state(real)
    assert wf.next_step(data) == WRITE_SPEC, (
        f"nach Ruecksprung phase4_approved->phase3_spec: {wf.next_step(data)!r}"
    )
    assert wf.expected_footer_command(data) == f"{WRITE_SPEC} #{ISSUE}"


# --- AC-4 ------------------------------------------------------------------

def test_auto_approve_after_backstep_stays_human(tmp_path, inproc):
    """AC-4: Auto-Modus, Spec und Briefing unveraendert, Ruecksprung ->
    `auto-approve` liefert human, Spec bleibt unfreigegeben,
    `_auto_approval_pending` ist False."""
    # #647: auto-freigegeben, dann zurueck auf phase3_spec
    proj = _make_project(tmp_path / "p647", "phase3_spec", config=AUTO_CFG)
    verdict, out = _auto_approve(proj)
    assert verdict == "done", f"Testaufbau: erste Auto-Freigabe scheiterte: {out!r}"
    assert _state(proj)["current_phase"] == "phase4_approved"
    spec_before = (proj / REL_SPEC).read_bytes()
    briefing_before = (proj / REL_BRIEFING).read_bytes()

    _jump(proj, "phase3_spec")
    verdict, out = _auto_approve(proj)

    assert (proj / REL_SPEC).read_bytes() == spec_before
    assert (proj / REL_BRIEFING).read_bytes() == briefing_before
    data = _state(proj)
    assert verdict == "human", (
        f"#647: auto-approve gibt die widerlegte, unveraenderte Spec erneut frei: {out!r}"
    )
    assert data.get("spec_approved") is False, data.get("spec_approved")
    assert data["current_phase"] == "phase3_spec"
    wf = inproc(proj)
    assert wf._auto_approval_pending(data) is False

    # #648: aus phase6_implement zurueck auf phase2_analyse, dann wieder phase3_spec
    proj2 = _make_project(tmp_path / "p648", "phase3_spec", config=AUTO_CFG)
    verdict, out = _auto_approve(proj2)
    assert verdict == "done", f"Testaufbau: {out!r}"
    _write_state(proj2, **_phase_flags("phase6_implement"))
    _jump(proj2, "phase2_analyse")
    _jump(proj2, "phase3_spec")
    verdict, out = _auto_approve(proj2)
    assert verdict == "human", f"#648: auto-approve nach Ruecksprung: {out!r}"
    data2 = _state(proj2)
    assert data2.get("spec_approved") is False
    wf = inproc(proj2)
    assert wf._auto_approval_pending(data2) is False


# --- AC-5 ------------------------------------------------------------------

def test_set_briefing_and_approval_clear_rework(tmp_path, inproc):
    """AC-5: `set-briefing` und `_apply_spec_approval` loeschen `spec_rework`;
    danach meldet next_step wieder den Freigabe-Schritt."""
    proj = _make_project(tmp_path / "proj", "phase3_spec", briefing=False)
    _write_state(proj, spec_rework=True)

    reg = _cli(proj, "set-briefing", REL_BRIEFING)
    assert reg.returncode == 0, reg.stderr

    data = _state(proj)
    assert not data.get("spec_rework"), (
        f"set-briefing hat spec_rework nicht geloescht: {data.get('spec_rework')!r}"
    )
    wf = inproc(proj)
    assert wf.next_step(data) == APPROVAL_STEP

    approval = {"name": WF, "workflow_type": "feature", "current_phase": "phase3_spec",
                "spec_file": REL_SPEC, "spec_approved": False, "spec_rework": True,
                "phase_transitions": [], "phase_log": []}
    wf._apply_spec_approval(approval, "approval")
    assert approval["current_phase"] == "phase4_approved"
    assert not approval.get("spec_rework"), (
        f"_apply_spec_approval hat spec_rework nicht geloescht: {approval.get('spec_rework')!r}"
    )


def _run_listener(proj: Path, prompt: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HOOKS_DIR / "phase_listener.py")],
                          input=json.dumps({"prompt": prompt}), capture_output=True,
                          text=True, env=_env(proj), cwd=str(proj), timeout=60)


def test_listener_approval_clears_rework(tmp_path, inproc):
    """AC-5 (F001): Die Freigabe ueber den echten phase_listener (record_transition
    nach phase4_approved) loescht `spec_rework`; ein folgender Ruecksprung ohne
    Briefing meldet den Freigabe-Schritt, nicht /30-write-spec.

    Kill-Switch aus: der Listener gibt ohne neues Briefing frei, das Flag aus dem
    ersten Ruecksprung (mit Briefing) steht also noch, wenn die Freigabe wirkt."""
    proj = _make_project(tmp_path / "proj", "phase4_approved", config=KILL_SWITCH_CFG)
    _jump(proj, "phase3_spec")
    assert _state(proj).get("spec_rework") is True, "Testaufbau: Flag nach Ruecksprung erwartet"

    approval = _run_listener(proj, "approved")
    assert approval.returncode == 0, approval.stderr
    data = _state(proj)
    assert data["current_phase"] == "phase4_approved", (
        f"Freigabe wirkte nicht: {data['current_phase']} {approval.stdout.strip()[:300]!r}"
    )
    assert "spec_rework" not in data, (
        f"Freigabe ueber phase_listener hat spec_rework nicht geloescht: "
        f"{data.get('spec_rework')!r}"
    )

    _jump(proj, "phase3_spec")
    data = _state(proj)
    assert "spec_rework" not in data, data.get("spec_rework")
    wf = inproc(proj)
    assert wf.next_step(data) == APPROVAL_STEP, (
        f"Ruecksprung ohne Briefing nach Listener-Freigabe: {wf.next_step(data)!r}"
    )


# --- AC-6 ------------------------------------------------------------------

def test_no_rework_without_briefing_and_no_change_on_forward(tmp_path, inproc):
    """AC-6: Ruecksprung ohne Briefing (Fast Track, Kill-Switch), Vorwaertswechsel
    und Ruecksprung auf ein Ziel ab phase4_approved setzen kein `spec_rework` und
    lassen `po_briefing` unveraendert.

    Die Negativ-Faelle sind heute schon korrekt; die Gegenprobe am Ende (Ruecksprung
    MIT Briefing setzt das Flag) zeigt, dass sie nicht trivial gruen sind, und ist
    der Teil, der vor der Umsetzung rot ist.
    """
    # Fast Track ohne Briefing: phase4_approved -> phase3_spec
    ff = _make_project(tmp_path / "ff", "phase4_approved", briefing=False,
                       workflow_type="feature-fast")
    _jump(ff, "phase3_spec")
    data = _state(ff)
    assert "spec_rework" not in data, data.get("spec_rework")
    assert "po_briefing" not in data
    assert not data.get("po_briefing_history")
    wf = inproc(ff)
    assert wf.next_step(data) == APPROVAL_STEP, "Fast Track behaelt den Freigabe-Schritt"

    # Kill-Switch ohne Briefing: phase6_implement -> phase2_analyse
    ks = _make_project(tmp_path / "ks", "phase6_implement", briefing=False,
                       config=KILL_SWITCH_CFG)
    _jump(ks, "phase2_analyse")
    data = _state(ks)
    assert "spec_rework" not in data, data.get("spec_rework")
    assert not data.get("po_briefing_history")

    # Vorwaertswechsel mit Briefing: phase5_tdd_red -> phase6_implement
    fw = _make_project(tmp_path / "fw", "phase5_tdd_red")
    before = _state(fw)["po_briefing"]
    _jump(fw, "phase6_implement")
    data = _state(fw)
    assert data.get("po_briefing") == before
    assert "spec_rework" not in data
    assert not data.get("po_briefing_history")

    # Ruecksprung auf ein Ziel ab phase4_approved: phase6_implement -> phase4_approved
    p4 = _make_project(tmp_path / "p4", "phase6_implement")
    before = _state(p4)["po_briefing"]
    _jump(p4, "phase4_approved")
    data = _state(p4)
    assert data.get("po_briefing") == before
    assert "spec_rework" not in data
    assert not data.get("po_briefing_history")

    # Gegenprobe: Ruecksprung MIT Briefing vor phase4_approved setzt das Flag
    gp = _make_project(tmp_path / "gp", "phase4_approved")
    _jump(gp, "phase3_spec")
    assert _state(gp).get("spec_rework") is True, (
        "Gegenprobe: Ruecksprung mit Briefing setzt spec_rework nicht: "
        f"{_state(gp).get('spec_rework')!r}"
    )


# --- AC-7 ------------------------------------------------------------------

def test_set_field_blocks_new_fields(tmp_path):
    """AC-7: `set-field po_briefing_history|spec_rework` -> Exit 1, Meldung
    "per set-field gesperrt" mit Hinweis auf den zustaendigen Befehl, State unveraendert."""
    proj = _make_project(tmp_path / "proj", "phase3_spec")
    for key, value in (("po_briefing_history", "[]"), ("spec_rework", "false")):
        before = _wf_path(proj).read_bytes()
        res = _cli(proj, "set-field", key, value)
        assert res.returncode == 1, (
            f"set-field {key} nicht gesperrt (Exit {res.returncode}): "
            f"{res.stdout.strip()!r} {res.stderr.strip()!r}"
        )
        assert "per set-field gesperrt" in res.stderr, res.stderr
        assert "workflow.py phase" in res.stderr or "set-briefing" in res.stderr, (
            f"Hinweis auf den zustaendigen Befehl fehlt: {res.stderr!r}"
        )
        assert _wf_path(proj).read_bytes() == before, f"State nach set-field {key} veraendert"


# --- AC-8 ------------------------------------------------------------------

def _wf_data(name: str, phase: str) -> dict:
    return {"name": name, "workflow_type": "feature", "current_phase": phase,
            "phase_transitions": [], "phase_log": []}


def _put_wf(proj: Path, name: str, phase: str, mtime: "float | None" = None,
            archived: bool = False) -> Path:
    folder = proj / ".claude" / "workflows"
    if archived:
        folder = folder / "_archive"
    path = folder / f"{name}.json"
    path.write_text(json.dumps(_wf_data(name, phase)))
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_endstate_prefers_active_workflow(tmp_path):
    """AC-8: Rangfolge exakter Name, aktiver Workflow, nicht phase8_complete,
    juengster nach mtime; ohne aktiven Workflow kein Abbruch; Archiv wie bisher."""
    now = time.time()

    # Vorgaenger (phase8_complete, alphabetisch zuerst) + aktiver Workflow
    proj = _base_project(tmp_path / "active")
    _put_wf(proj, "fix-647-alt", "phase8_complete", mtime=now)
    _put_wf(proj, "fix-647-neu", "phase6_implement", mtime=now - 100)
    (proj / ".claude" / "active_workflow").write_text("fix-647-neu")

    res = _cli(proj, "endstate", "647", active="fix-647-neu")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "ENDSTATE") == "you", (
        f"endstate 647 nennt nicht den aktiven Workflow (phase6 -> you): {res.stdout!r}"
    )
    res = _cli(proj, "deploy-status", "running", "647", active="fix-647-neu")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "fix-647-neu" in res.stdout, res.stdout
    assert "deploy_status" not in _state(proj, "fix-647-alt")

    # Exakter Name schlaegt den aktiven Workflow
    res = _cli(proj, "endstate", "fix-647-alt", active="fix-647-neu")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "ENDSTATE") == "done", res.stdout

    # Ohne aktiven Workflow: kein Abbruch, nicht abgeschlossener Treffer gewinnt
    # (auch wenn der abgeschlossene juenger ist)
    noact = _base_project(tmp_path / "noactive")
    _put_wf(noact, "fix-647-alt", "phase8_complete", mtime=now)
    _put_wf(noact, "fix-647-neu", "phase6_implement", mtime=now - 100)
    res = _cli(noact, "deploy-status", "running", "647", active=None)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "fix-647-neu" in res.stdout, (
        f"ohne aktiven Workflow soll der nicht abgeschlossene Treffer gelten: {res.stdout!r}"
    )

    # Mehrere nicht abgeschlossene, kein aktiver: juengster nach mtime
    young = _base_project(tmp_path / "young")
    _put_wf(young, "fix-647-a", "phase6_implement", mtime=now - 100)
    _put_wf(young, "fix-647-b", "phase5_tdd_red", mtime=now)
    res = _cli(young, "deploy-status", "running", "647", active=None)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "fix-647-b" in res.stdout, (
        f"juengster Treffer nach mtime erwartet: {res.stdout!r}"
    )

    # Archiv wie bisher
    arch = _base_project(tmp_path / "archive")
    _put_wf(arch, "fix-647-x", "phase8_complete", archived=True)
    res = _cli(arch, "deploy-status", "done", "647", active=None)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "fix-647-x" in res.stdout, res.stdout


def _deploy_marked(proj: Path, *names: str) -> "list[str]":
    """Namen der Workflows, die nach deploy-status ein `deploy_status` tragen."""
    return [n for n in names if "deploy_status" in _state(proj, n)]


def test_endstate_active_beats_younger_open_hit(tmp_path):
    """AC-8 (F002a): aktiver, offener, AELTERER Workflow neben einem JUENGEREN
    fremden offenen Treffer gleicher Nummer -> der aktive gewinnt."""
    now = time.time()
    proj = _base_project(tmp_path / "proj")
    _put_wf(proj, "fix-647-neu", "phase6_implement", mtime=now - 100)
    _put_wf(proj, "fix-647-zweit", "phase5_tdd_red", mtime=now)
    (proj / ".claude" / "active_workflow").write_text("fix-647-neu")

    res = _cli(proj, "deploy-status", "running", "647", active="fix-647-neu")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _deploy_marked(proj, "fix-647-neu", "fix-647-zweit") == ["fix-647-neu"], (
        f"aktiver Workflow soll vor dem juengeren fremden Treffer gewinnen: {res.stdout!r}"
    )


def test_endstate_exact_name_beats_active(tmp_path):
    """AC-8 (F002b): exakter Name (ref == Dateiname) neben einem aktiven anderen
    Treffer -> der exakte Name gewinnt, auch wenn er aelter ist."""
    now = time.time()
    proj = _base_project(tmp_path / "proj")
    _put_wf(proj, "647", "phase5_tdd_red", mtime=now - 100)
    _put_wf(proj, "fix-647-neu", "phase6_implement", mtime=now)
    (proj / ".claude" / "active_workflow").write_text("fix-647-neu")

    res = _cli(proj, "deploy-status", "running", "647", active="fix-647-neu")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _deploy_marked(proj, "647", "fix-647-neu") == ["647"], (
        f"exakter Name soll vor dem aktiven Workflow gewinnen: {res.stdout!r}"
    )
