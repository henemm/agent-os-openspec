"""Spec-Ampel: automatische Spec-Freigabe im Auto-Modus (Issue #470) — Tests zu AC-1 bis AC-22.

Spec: docs/specs/feat-470-spec-ampel.md

Festgelegte Vertraege (die Spec nennt sie nur sinngemaess):
- `workflow.autonomy_mode()` liest nur die wirksame Config-Datei
  (`config_loader.find_config_file(find_project_root())`), nie `settings.local.json`.
- `workflow.parse_ampel(text) -> "green" | "red"`, wirft nie.
- `workflow.py set-briefing` speichert `po_briefing["ampel"]` und
  `po_briefing["briefing_sha256"]` (SHA-256 der Briefing-Datei auf Platte NACH dem Stempeln).
- `workflow.py auto-approve`: stdout enthaelt eine Zeile `AUTO_APPROVE=done|human` und
  eine Zeile `REASON=...`, Exit immer 0; bei `human` bleibt die State-Datei byte-identisch.
- Freigabe schreibt `phase_transitions` (from/to/trigger="auto") und genau einen
  `approvals`-Eintrag (gate=spec, by=auto, mode=auto, evidence mit
  briefing/briefing_sha256/spec_sha256/ampel).
- `next_step`: Auto-Freigabe-Schritt beginnt mit "Auto-" und lautet exakt
  "Auto-Freigabe der Spec (workflow.py auto-approve)".
- `status_note` enthaelt im Auto-Fall den Schritt, aber das Zeichen "❗" gar nicht
  (die sonst allgemeine ❗Du-Anweisung entfaellt in dem Fall komplett).
- `herdr_bridge.build_report`: tokens.next == "auto" beim Auto-Schritt.

Fehlende Funktionen erscheinen pro Test als FAIL (Imports erst im Testkoerper).
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
LISTENER_PY = HOOKS_DIR / "phase_listener.py"
FOOTER_GATE_PY = HOOKS_DIR / "footer_gate.py"

WF = "feat-470-demo"
REL_SPEC = "docs/specs/demo.md"
REL_BRIEFING = "docs/briefings/demo.md"
AUTO_STEP = "Auto-Freigabe der Spec (workflow.py auto-approve)"
HUMAN_STEP = "Freigabe der Spec (Stichwort: approved)"

SPEC_OK = (
    "# Demo Spec\n\n"
    "## Purpose\n\nEin Feature, das etwas tut.\n\n"
    "## Definition of Done\n\n- Fertig, wenn X sichtbar ist.\n\n"
    "## Acceptance Criteria\n\n"
    "- **AC-1:** Given ein Nutzer / When er klickt / Then passiert etwas Sichtbares.\n\n"
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** keine\n"
    "- **Rationale:** Kleine Aenderung, keine Weichenstellung.\n"
)

SPEC_ADR_MISSING = SPEC_OK.replace(
    "- **ADR-Nr.:** keine\n- **Rationale:** Kleine Aenderung, keine Weichenstellung.\n",
    "- **ADR-Nr.:** \n",
)

BRIEFING_BASE = (
    "# PO-Briefing: demo\n\n"
    "- **Spec:** docs/specs/demo.md\n\n"
    "## Was gebaut wird\n\n"
    "Nutzer koennen kuenftig mit einem Klick etwas ausloesen, das heute fehlt.\n\n"
    "## Definition of Done\n\n"
    "Fertig ist es, wenn der Klick sichtbar etwas ausloest und das automatisch geprueft wird.\n\n"
    "## Wie geprueft wird\n\n"
    "Ein automatischer Test klickt stellvertretend und prueft das sichtbare Ergebnis.\n\n"
    "## Kritische Anmerkungen\n\n"
    "- Keine offene Entscheidung fuer den PO.\n"
)


def _briefing(ampel_value: "str | None" = "gruen") -> str:
    if ampel_value is None:
        return BRIEFING_BASE
    return BRIEFING_BASE + f"\n## Ampel\n\nAmpel: {ampel_value}\n"


# --- Helpers ---------------------------------------------------------------

def _env(proj: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    return env


def _cli(args, proj: Path, active: str = WF):
    env = _env(proj)
    if active:
        env["OPENSPEC_ACTIVE_WORKFLOW"] = active
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args],
                          capture_output=True, text=True, env=env,
                          cwd=str(proj), timeout=60)


def _wf_path(proj: Path) -> Path:
    return proj / ".claude" / "workflows" / f"{WF}.json"


def _state(proj: Path) -> dict:
    return json.loads(_wf_path(proj).read_text())


def _write_state(proj: Path, **fields) -> None:
    data = _state(proj)
    data.update(fields)
    _wf_path(proj).write_text(json.dumps(data))


def _project(tmp_path: Path, *, mode: str = "auto", ampel: "str | None" = "gruen",
             spec: str = SPEC_OK, register: bool = True,
             workflow_type: str = "feature") -> Path:
    """Temp-Projekt: Config, Spec, Briefing, Workflow in phase3_spec, ggf. set-briefing."""
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    (proj / "openspec.yaml").write_text(f"autonomy:\n  mode: {mode}\n")
    (proj / REL_SPEC).parent.mkdir(parents=True)
    (proj / REL_SPEC).write_text(spec)
    (proj / REL_BRIEFING).parent.mkdir(parents=True)
    (proj / REL_BRIEFING).write_text(_briefing(ampel))
    _wf_path(proj).write_text(json.dumps({
        "name": WF, "workflow_type": workflow_type, "current_phase": "phase3_spec",
        "context_file": "docs/context.md", "spec_file": REL_SPEC,
        "spec_approved": False, "phase_transitions": [], "phase_log": [],
        "approvals": [],
    }))
    (proj / ".claude" / "active_workflow").write_text(WF)
    if register:
        res = _cli(["set-briefing", REL_BRIEFING], proj)
        assert res.returncode == 0, f"set-briefing: {res.stdout!r} {res.stderr!r}"
    return proj


def _auto_approve(proj: Path):
    res = _cli(["auto-approve"], proj)
    assert res.returncode == 0, (
        f"auto-approve muss immer Exit 0 liefern: rc={res.returncode} "
        f"stdout={res.stdout!r} stderr={res.stderr!r}"
    )
    m = re.search(r"^AUTO_APPROVE=(\w+)\s*$", res.stdout, re.M)
    assert m, f"Zeile AUTO_APPROVE=... fehlt: stdout={res.stdout!r} stderr={res.stderr!r}"
    assert re.search(r"^REASON=.+$", res.stdout, re.M), res.stdout
    return m.group(1), res


def _assert_human_unchanged(proj: Path) -> None:
    before = _wf_path(proj).read_bytes()
    verdict, res = _auto_approve(proj)
    assert verdict == "human", res.stdout
    assert _wf_path(proj).read_bytes() == before, "State darf bei human nicht veraendert werden"


@pytest.fixture
def inproc(tmp_path, monkeypatch):
    """In-Process-Zugriff auf workflow/config_loader mit frischen Caches."""
    proj = tmp_path / "ip"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude").mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
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

    reset()

    class Ctx:
        pass

    ctx = Ctx()
    ctx.root = proj
    ctx.workflow = workflow
    ctx.reset = reset
    yield ctx
    reset()


# --- AC-1 -------------------------------------------------------------------

def test_autonomy_mode_ignores_settings_local(inproc):
    """AC-1: `auto` nur aus der wirksamen Config; settings.local.json wirkt nicht."""
    wf, root = inproc.workflow, inproc.root
    local = json.dumps({"autonomy": {"mode": "auto"}})

    # a) settings.local.json = auto, wirksame Config ohne autonomy -> manual
    (root / "openspec.yaml").write_text("project:\n  name: x\n")
    (root / ".claude" / "settings.local.json").write_text(local)
    (root / "settings.local.json").write_text(local)
    inproc.reset()
    assert wf.autonomy_mode() == "manual"

    # b) wirksame Config = auto -> auto (kein Dauer-manual)
    (root / "openspec.yaml").write_text("autonomy:\n  mode: auto\n")
    inproc.reset()
    assert wf.autonomy_mode() == "auto"

    # c) kaputte wirksame Config -> manual, ohne Ausnahme
    (root / "openspec.yaml").write_text("autonomy: [unclosed\n  mode: : auto\n\t- x")
    inproc.reset()
    assert wf.autonomy_mode() == "manual"

    # d) fehlende wirksame Config (nur local = auto) -> manual
    (root / "openspec.yaml").unlink()
    inproc.reset()
    assert wf.autonomy_mode() == "manual"


# --- AC-2 -------------------------------------------------------------------

def test_parse_ampel_green_variants():
    """AC-2: gruen / grün / green (case-insensitiv, getrimmt) -> "green"."""
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    for value in ("gruen", "grün", "green", "GRUEN", "Green", "  gruen  "):
        text = _briefing(value)
        assert workflow.parse_ampel(text) == "green", value
    assert workflow.parse_ampel("## Ampel\n\nAmpel: grün\n") == "green"


# --- AC-3 -------------------------------------------------------------------

def test_parse_ampel_everything_else_is_red():
    """AC-3: rot, fehlend, doppelt, mehrzeilig, unklar -> "red"; wirft nie."""
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    cases = {
        "rot": _briefing("rot"),
        "red": _briefing("red"),
        "kein_abschnitt": BRIEFING_BASE,
        "doppelte_zeile": BRIEFING_BASE + "\n## Ampel\n\nAmpel: gruen\nAmpel: gruen\n",
        "zwei_abschnitte": (BRIEFING_BASE + "\n## Ampel\n\nAmpel: gruen\n"
                            "\n## Ampel\n\nAmpel: gruen\n"),
        "mehrere_zeilen": BRIEFING_BASE + "\n## Ampel\n\nAmpel: gruen\nAlles bestens.\n",
        "unklar": _briefing("vielleicht gruen"),
        "gruenlich": _briefing("gruenlich"),
        "leer": _briefing(""),
        "nur_ueberschrift": BRIEFING_BASE + "\n## Ampel\n",
        "zeile_ausserhalb": BRIEFING_BASE + "\nAmpel: gruen\n",
        "leerer_text": "",
    }
    for label, text in cases.items():
        assert workflow.parse_ampel(text) == "red", label
    for junk in (None, 5, b"x", ["Ampel: gruen"]):
        try:
            assert workflow.parse_ampel(junk) == "red", repr(junk)
        except AssertionError:
            raise
        except Exception as exc:  # pragma: no cover
            pytest.fail(f"parse_ampel darf nie werfen: {junk!r} -> {exc!r}")


# --- AC-4 -------------------------------------------------------------------

def test_set_briefing_stores_ampel_and_hash(tmp_path):
    """AC-4: set-briefing speichert ampel + briefing_sha256 (Hash der Datei auf Platte)."""
    proj = _project(tmp_path / "g", ampel="gruen")
    entry = _state(proj)["po_briefing"]
    assert entry.get("ampel") == "green", entry
    on_disk = (proj / REL_BRIEFING).read_text()
    assert entry.get("briefing_sha256") == hashlib.sha256(on_disk.encode("utf-8")).hexdigest()

    red = _project(tmp_path / "r", ampel="rot")
    entry = _state(red)["po_briefing"]
    assert entry.get("ampel") == "red", entry
    on_disk = (red / REL_BRIEFING).read_text()
    assert entry.get("briefing_sha256") == hashlib.sha256(on_disk.encode("utf-8")).hexdigest()


# --- AC-5 -------------------------------------------------------------------

def test_auto_approve_happy_path_sets_state(tmp_path):
    """AC-5: auto + phase3_spec + ADR ok + aktuell + gruen -> done, phase4_approved."""
    proj = _project(tmp_path)
    verdict, res = _auto_approve(proj)
    assert verdict == "done", res.stdout
    data = _state(proj)
    assert data["current_phase"] == "phase4_approved"
    assert data["spec_approved"] is True
    hits = [t for t in data["phase_transitions"]
            if t.get("from") == "phase3_spec" and t.get("to") == "phase4_approved"]
    assert len(hits) == 1 and hits[0].get("trigger") == "auto", data["phase_transitions"]


# --- AC-6 -------------------------------------------------------------------

def test_auto_approve_records_approval_with_evidence(tmp_path):
    """AC-6: genau ein approvals-Eintrag mit gate/by/mode und Evidence."""
    proj = _project(tmp_path)
    verdict, res = _auto_approve(proj)
    assert verdict == "done", res.stdout
    data = _state(proj)
    approvals = data["approvals"]
    assert len(approvals) == 1, approvals
    entry = approvals[0]
    assert (entry["gate"], entry["by"], entry["mode"]) == ("spec", "auto", "auto"), entry
    ev = entry["evidence"]
    assert isinstance(ev, dict), entry
    for key in ("briefing", "briefing_sha256", "spec_sha256", "ampel"):
        assert ev.get(key), (key, ev)
    assert ev["ampel"] == "green"
    assert ev["briefing"] == REL_BRIEFING
    assert ev["briefing_sha256"] == data["po_briefing"]["briefing_sha256"]


# --- AC-7 -------------------------------------------------------------------

def test_auto_approve_manual_mode_is_human(tmp_path):
    """AC-7: manual -> human, Exit 0, State byte-identisch."""
    proj = _project(tmp_path, mode="manual")
    _assert_human_unchanged(proj)


# --- AC-8 -------------------------------------------------------------------

def test_auto_approve_red_or_missing_ampel_is_human(tmp_path):
    """AC-8: rote Ampel bzw. fehlender Abschnitt -> human, State unveraendert."""
    _assert_human_unchanged(_project(tmp_path / "rot", ampel="rot"))
    _assert_human_unchanged(_project(tmp_path / "fehlt", ampel=None))


# --- AC-9 -------------------------------------------------------------------

def test_auto_approve_briefing_changed_after_registration_is_human(tmp_path):
    """AC-9: Briefing nach set-briefing geaendert (rot -> gruen gedreht) -> human."""
    proj = _project(tmp_path / "flip", ampel="rot")
    path = proj / REL_BRIEFING
    path.write_text(path.read_text().replace("Ampel: rot", "Ampel: gruen"))
    assert "Ampel: gruen" in path.read_text()
    _assert_human_unchanged(proj)

    # Auch eine sonstige Aenderung an einem registriert-gruenen Briefing zaehlt.
    proj2 = _project(tmp_path / "edit", ampel="gruen")
    path2 = proj2 / REL_BRIEFING
    path2.write_text(path2.read_text() + "\nNachtrag nach der Registrierung.\n")
    _assert_human_unchanged(proj2)


# --- AC-10 ------------------------------------------------------------------

def test_auto_approve_spec_changed_after_briefing_is_human(tmp_path):
    """AC-10: Spec nach set-briefing geaendert -> human."""
    proj = _project(tmp_path)
    spec = proj / REL_SPEC
    spec.write_text(spec.read_text().replace("etwas tut.", "etwas ganz anderes tut."))
    _assert_human_unchanged(proj)


# --- AC-11 ------------------------------------------------------------------

def test_auto_approve_adr_missing_is_human(tmp_path):
    """AC-11: ADR-Sektion nicht ausgefuellt -> human."""
    proj = _project(tmp_path, spec=SPEC_ADR_MISSING)
    _assert_human_unchanged(proj)


# --- AC-12 ------------------------------------------------------------------

def test_auto_approve_wrong_phase_is_human(tmp_path):
    """AC-12: nicht phase3_spec -> human."""
    proj = _project(tmp_path)
    _write_state(proj, current_phase="phase2_analyse")
    _assert_human_unchanged(proj)


# --- AC-13 ------------------------------------------------------------------

def test_auto_approve_is_idempotent(tmp_path):
    """AC-13: zweiter Lauf -> human, weiterhin genau ein approvals-Eintrag."""
    proj = _project(tmp_path)
    verdict, res = _auto_approve(proj)
    assert verdict == "done", res.stdout
    assert len(_state(proj)["approvals"]) == 1
    before = _wf_path(proj).read_bytes()
    verdict2, res2 = _auto_approve(proj)
    assert verdict2 == "human", res2.stdout
    assert len(_state(proj)["approvals"]) == 1
    assert _wf_path(proj).read_bytes() == before

    # Auch eine bereits (per Listener) freigegebene Spec in phase3_spec: human.
    proj2 = _project(tmp_path / "pre")
    _write_state(proj2, spec_approved=True)
    _assert_human_unchanged(proj2)


# --- AC-14 ------------------------------------------------------------------

def test_fast_track_requires_briefing_in_auto_mode(inproc):
    """AC-14: Fast Track ohne Briefing -> im Auto-Modus Fehler, im manual-Modus None."""
    wf, root = inproc.workflow, inproc.root
    (root / REL_SPEC).parent.mkdir(parents=True)
    (root / REL_SPEC).write_text(SPEC_OK)
    cfg = "po_briefing_gate:\n  skip_fast_track: true\n"
    data = {"name": WF, "workflow_type": "feature-fast", "current_phase": "phase3_spec",
            "spec_file": REL_SPEC, "spec_approved": False}

    (root / "openspec.yaml").write_text(cfg + "autonomy:\n  mode: manual\n")
    inproc.reset()
    assert wf._check_po_briefing(dict(data)) is None  # Ausnahme bleibt im manual-Modus

    (root / "openspec.yaml").write_text(cfg + "autonomy:\n  mode: auto\n")
    inproc.reset()
    err = wf._check_po_briefing(dict(data))
    assert err and "Briefing" in err, err


# --- AC-15 ------------------------------------------------------------------

def test_next_step_auto_only_with_green_ampel(inproc):
    """AC-15: Auto-Schritt nur bei auto + phase3_spec + Spec + gruener Ampel."""
    wf, root = inproc.workflow, inproc.root

    def data(ampel):
        d = {"name": WF, "workflow_type": "feature", "current_phase": "phase3_spec",
             "spec_file": REL_SPEC}
        if ampel is not None:
            d["po_briefing"] = {"file": REL_BRIEFING, "ampel": ampel}
        return d

    def set_mode(mode):
        (root / "openspec.yaml").write_text(f"autonomy:\n  mode: {mode}\n")
        inproc.reset()

    set_mode("auto")
    assert wf.next_step(data("green")) == AUTO_STEP
    assert wf.next_step(data("red")) == HUMAN_STEP
    assert wf.next_step(data(None)) == HUMAN_STEP
    no_spec = data("green")
    del no_spec["spec_file"]
    assert wf.next_step(no_spec) != AUTO_STEP

    note = wf.status_note(data("green"))
    assert note and AUTO_STEP in note, note
    assert "❗" not in note, "Auto-Fall: keine ❗Du-Pflicht fuer diesen Schritt"

    # Gegenprobe: ausserhalb des Auto-Falls bleibt die ❗Du-Anweisung erhalten.
    red_note = wf.status_note(data("red"))
    assert red_note and HUMAN_STEP in red_note and "❗" in red_note

    set_mode("manual")
    assert wf.next_step(data("green")) == HUMAN_STEP
    manual_note = wf.status_note(data("green"))
    assert manual_note and HUMAN_STEP in manual_note and "❗" in manual_note


# --- AC-16 ------------------------------------------------------------------

def test_footer_gate_exit_zero_on_auto_step(tmp_path):
    """AC-16: Auto-Schritt ist Freitext -> expected_footer_command reicht ihn durch,
    footer_gate endet mit Exit 0 bei beliebiger Fusszeile."""
    proj = _project(tmp_path)  # auto + gruen registriert, phase3_spec
    env = _env(proj)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF

    probe = subprocess.run(
        [sys.executable, "-c",
         "import sys, json; sys.path.insert(0, sys.argv[1]); import workflow; "
         "d = json.load(open(sys.argv[2])); print(workflow.expected_footer_command(d))",
         str(HOOKS_DIR), str(_wf_path(proj))],
        capture_output=True, text=True, env=env, cwd=str(proj), timeout=60)
    assert probe.stdout.strip() == AUTO_STEP, (probe.stdout, probe.stderr)

    footers = [
        "❗ Du: `/40-tdd-red #470` — falscher Befehl",
        "❗ Du: `approved` — Freigabe",
        "ℹ️ Nichts zu tun: Auto-Freigabe laeuft",
        "Keine Fusszeile.",
    ]
    for footer in footers:
        payload = {"session_id": "s470", "hook_event_name": "Stop", "cwd": str(proj),
                   "prompt_id": "11111111-2222-3333-4444-555555555555",
                   "last_assistant_message": f"Spec geschrieben.\n\n{footer}\n⚙ /30-write-spec"}
        res = subprocess.run([sys.executable, str(FOOTER_GATE_PY)], input=json.dumps(payload),
                             capture_output=True, text=True, env=env, cwd=str(proj),
                             timeout=60)
        assert res.returncode == 0, (footer, res.stderr)


# --- AC-17 ------------------------------------------------------------------

def test_herdr_report_next_auto(inproc):
    """AC-17: Auto-Schritt -> tokens.next == "auto"; Freigabe-Schritt -> "approved"."""
    import herdr_bridge  # noqa: PLC0415
    root = inproc.root

    def report(ampel):
        d = {"name": "feat-470-demo", "current_phase": "phase3_spec",
             "spec_file": REL_SPEC}
        if ampel:
            d["po_briefing"] = {"file": REL_BRIEFING, "ampel": ampel}
        return herdr_bridge.build_report(d)

    (root / "openspec.yaml").write_text("autonomy:\n  mode: auto\n")
    inproc.reset()
    assert report("green")["tokens"]["next"] == "auto"
    assert report("red")["tokens"]["next"] == "approved"
    assert report(None)["tokens"]["next"] == "approved"

    (root / "openspec.yaml").write_text("autonomy:\n  mode: manual\n")
    inproc.reset()
    assert report("green")["tokens"]["next"] == "approved"


# --- AC-18 ------------------------------------------------------------------

def test_po_briefer_defines_ampel_section():
    """AC-18: po-briefer.md definiert `## Ampel` samt Regeln."""
    text = (REPO_ROOT / "core" / "agents" / "po-briefer.md").read_text()
    low = text.lower()
    assert re.search(r"^#{2,3} Ampel\s*$", text, re.M), "Abschnitt `## Ampel` fehlt"
    assert "Ampel: gruen" in text and "Ampel: rot" in text
    for needle in ("abweichung", "scope", "offene entscheidung", "vag", "im zweifel rot"):
        assert needle in low, needle
    assert re.search(r"acceptance criterion|\bAC\b", text), "Regel 'AC ohne Test' fehlt"
    assert "ohne test" in low or "kein test" in low or "ohne einen test" in low


# --- AC-19 ------------------------------------------------------------------

def test_commands_branch_on_auto_approve_and_skills_in_sync():
    """AC-19: Commands verzweigen auf AUTO_APPROVE; generierte Skills synchron."""
    write_spec = (REPO_ROOT / "core" / "commands" / "30-write-spec.md").read_text()
    for needle in ("auto-approve", "AUTO_APPROVE=done", "AUTO_APPROVE=human"):
        assert needle in write_spec, needle
    intake = (REPO_ROOT / "core" / "commands" / "00-intake.md").read_text()
    idx = intake.find("Auto-Modus")
    assert idx >= 0, "00-intake.md erwaehnt den Auto-Modus nicht"
    assert "Briefing" in intake[idx: idx + 600], "Auto-Modus im Fast Track verlangt Briefing"
    for skill in ("30-write-spec", "00-intake"):
        skill_text = (REPO_ROOT / "skills" / skill / "SKILL.md").read_text()
        assert "AUTO_APPROVE" in skill_text or skill == "00-intake", skill
        if skill == "00-intake":
            assert "Auto-Modus" in skill_text
    res = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"),
                          "--check"], capture_output=True, text=True, cwd=str(REPO_ROOT),
                         timeout=60)
    assert res.returncode == 0, res.stderr


# --- AC-20 ------------------------------------------------------------------

def test_check_briefing_content_accepts_ampel_section():
    """AC-20: zusaetzlicher Abschnitt `## Ampel` kippt check_briefing_content nicht."""
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    assert workflow.check_briefing_content(BRIEFING_BASE) is None
    assert workflow.check_briefing_content(_briefing("gruen")) is None
    assert workflow.check_briefing_content(_briefing("rot")) is None
    # Verknuepfung zur neuen Funktion: dasselbe Briefing ist als gruen lesbar.
    assert workflow.parse_ampel(_briefing("gruen")) == "green"


# --- AC-21 ------------------------------------------------------------------

def _run_listener(proj: Path, prompt: str):
    return subprocess.run([sys.executable, str(LISTENER_PY)],
                          input=json.dumps({"prompt": prompt}), capture_output=True,
                          text=True, env={**_env(proj), "OPENSPEC_ACTIVE_WORKFLOW": WF},
                          cwd=str(proj), timeout=60)


def test_listener_approved_still_works_in_auto_mode_with_red_ampel(tmp_path):
    """AC-21: `approved` gibt auch im Auto-Modus bei roter Ampel frei (trigger approval)."""
    proj = _project(tmp_path, ampel="rot")
    assert _state(proj)["po_briefing"].get("ampel") == "red"
    res = _run_listener(proj, "approved")
    assert res.returncode == 0, res.stderr
    data = _state(proj)
    assert data["current_phase"] == "phase4_approved", (data, res.stdout, res.stderr)
    assert data["spec_approved"] is True
    hits = [t for t in data["phase_transitions"]
            if t.get("from") == "phase3_spec" and t.get("to") == "phase4_approved"]
    assert len(hits) == 1 and hits[0].get("trigger") == "approval", data["phase_transitions"]


# --- AC-22 ------------------------------------------------------------------

def test_listener_and_auto_paths_set_same_state_fields(tmp_path):
    """AC-22: Listener- und Auto-Freigabe setzen dieselben State-Felder."""
    via_listener = _project(tmp_path / "l")
    via_auto = _project(tmp_path / "a")

    res = _run_listener(via_listener, "approved")
    assert res.returncode == 0, res.stderr
    verdict, out = _auto_approve(via_auto)
    assert verdict == "done", out.stdout

    def shape(proj):
        d = _state(proj)
        return {
            "spec_approved": d.get("spec_approved"),
            "current_phase": d.get("current_phase"),
            "transitions": [(t.get("from"), t.get("to")) for t in d["phase_transitions"]],
            "log_phases": [e.get("phase") for e in d.get("phase_log", [])],
        }

    listener_state, auto_state = _state(via_listener), _state(via_auto)
    assert shape(via_listener) == shape(via_auto)
    assert shape(via_auto)["spec_approved"] is True
    assert shape(via_auto)["current_phase"] == "phase4_approved"
    assert listener_state["phase_transitions"][-1]["trigger"] == "approval"
    assert auto_state["phase_transitions"][-1]["trigger"] == "auto"
    assert not listener_state.get("approvals")
    assert len(auto_state["approvals"]) == 1
