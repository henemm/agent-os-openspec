"""TDD RED — #447: Evidence-Gate (Simulator-Beleg vor Phase 8, opt-in) + Schreibsperre.

Spec: docs/specs/feat-447-evidence-gate.md (AC-1 … AC-30). Unit-Ebene ruft
`evidence_gate.check_evidence` in-process in einem Wegwerf-Git-Repo (cwd/CLAUDE_PROJECT_DIR dort,
lru-Caches der Config geleert); Hook-Ebene läuft über die echten Skripte. `xcrun` ist das
Fake-Skript aus tests/fixtures/evidence_447/ vorn im PATH, gesteuert nur über FAKE_XCRUN_*.
Der Beleg entsteht über `format_proof` der unveränderten Kopie von loose-ends `sim_proof.py`.
`evidence_gate` wird erst nach dem Aufbau importiert: ein fehlendes Modul macht den Test rot,
nicht die Sammlung.
"""

import hashlib
import importlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
FIX = REPO_ROOT / "tests" / "fixtures" / "evidence_447"
sys.path.insert(0, str(HOOKS_DIR))

WF = "wf-447"
ART = f"docs/artifacts/{WF}"
PROOF, RUN = f"{ART}/simulator-run.txt", f"{ART}/simulator-run"
MOD_A, MOD_B = "src/module_a.py", "src/module_b.py"  # MOD_A in der Basis, MOD_B neu
VERIFIED = "VERIFIED:Tests PASSED: 5 passed"
ENTRY = "    - verifier: {v}\n      file: {f}\n"
GATE = "evidence_checks:\n  phase8_complete:\n" + ENTRY.format(v="xcresult_proof",
                                                                 f="simulator-run.txt")
COVERAGE_OFF = "adversary_coverage_gate:\n  enabled: false\n"
DIALOG_MSG = "Dialog-Nachweis"  # Kern der #253/#259-Meldung — darf bei Evidence-Gründen fehlen
OVERRIDE_MSG = "Evidence-Gate per override umgangen"
SUMMARY_TEXT = (FIX / "summary.json").read_text()
SUMMARY = json.loads(SUMMARY_TEXT)
_SCRUBBED = {"CLAUDE_TOOL_INPUT", "CLAUDE_TOOL_NAME", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT",
             "CLAUDE_CODE_SESSION_ID", "OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK",
             "PYTHONPATH"}


# ------------------------------------------------------------------ Aufbau
def _env(proj=None, **extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _SCRUBBED and not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    if proj is not None:
        env["CLAUDE_PROJECT_DIR"] = str(proj)
    return {**env, **extra}


def _run(script, args, cwd, env=None, stdin=None, check=False):
    io = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
    r = subprocess.run([sys.executable, str(HOOKS_DIR / script), *args], capture_output=True,
                       text=True, cwd=str(cwd), env=env or _env(cwd), timeout=60, **io)
    assert not check or r.returncode == 0, f"{script} {args}: {r.stdout}{r.stderr}"
    return r


def _git(args, cwd) -> str:
    r = subprocess.run(["git", "-c", "user.email=t@t.invalid", "-c", "user.name=Test",
                        "-c", "commit.gpgsign=false", *args], cwd=str(cwd), capture_output=True,
                       text=True, env=_env())
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout.strip()


def _write(root, rel, text=None) -> Path:
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {rel}\nVALUE = 1\n" if text is None else text)
    return path


def _sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sim_proof():
    spec = importlib.util.spec_from_file_location("sim_proof_447", FIX / "sim_proof.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_proof(root, wf=WF, files=(MOD_A, MOD_B), summary=None, bundle=True, **header) -> Path:
    """Beleg wie `sim_proof.main`: summary.json, run.xcresult, Kopf, Hash-Block (Obermenge MOD_A,
    `head:` ungleich HEAD). `header` überschreibt einzelne Kopfzeilen."""
    sp, rel = _sim_proof(), f"docs/artifacts/{wf}/simulator-run"
    sj = _write(root, f"{rel}/summary.json",
                SUMMARY_TEXT if summary is None else json.dumps(summary, separators=(",", ":")))
    if bundle:
        _write(root, f"{rel}/run.xcresult/Info.plist", "<plist/>\n")
    s = sp.parse_summary(SUMMARY if summary is None else summary, 0)
    hdr = {"erzeugt": "2026-10-22T10:00:00+0200", "befehl": "scripts/sim.sh test-proof",
           "workflow": wf, "head": "0" * 40, "basis": f"{'1' * 40} (merge-base origin/main HEAD)",
           "testklasse": "LooseEndsUITests", "ergebnis": s["ergebnis"],
           "xcodebuild": "** TEST SUCCEEDED **",
           "tests": f"{s['gesamt']} gesamt, {s['bestanden']} bestanden, "
                    f"{s['fehlgeschlagen']} fehlgeschlagen, {s['uebersprungen']} übersprungen",
           "start": f"{s['start']}  ende: {s['ende']}", "geraet": s["geraet"],
           "summary": f"{rel}/summary.json  sha256:{_sha256(sj)}",
           "xcresult": f"{rel}/run.xcresult  (gitignored)", "screenshots": f"{rel}/*.png (1 Stück)",
           **header}
    return _write(root, f"docs/artifacts/{wf}/simulator-run.txt",
                  sp.format_proof(hdr, [(_sha256(Path(root) / p), p) for p in files]))


def _make_dialog(root, cited=(MOD_A, MOD_B)) -> Path:
    refs = "".join(f"  Code reference: {c}:1\n" for c in cited)
    art = _write(root, f"{ART}/adversary-dialog.md", (
        "# Adversary Dialog\n\n## Checkliste\n- [x] AC-1: deckt die Änderung ab — Beweis: Test\n"
        f"{refs}\n## Dialog\n\n### Runde 1\n**Adversary:** A1\n**Implementierer:** B1\n\n"
        "### Runde 2\n**Adversary:** A2\n**Implementierer:** B2\n\nVERDICT: VERIFIED\n"))
    _run("adversary_dialog.py", ["stamp", str(art)], root, check=True)
    _run("adversary_dialog.py", ["validate", str(art)], root, check=True)
    return art


def _project(tmp_path, cfg=GATE, *, git=True, dialog=False, proof=True, phase="phase7_validate",
             wf_type="feature", token=None) -> Path:
    """Wegwerf-Projekt: MOD_A in der Basis, MOD_B neu (Gate-Menge = {MOD_B}); Config unter
    .claude/config.yaml; optional gestempelter Dialog (#253/#259 bestanden) und gültiger Beleg."""
    proj = (tmp_path / "proj").resolve()
    proj.mkdir(parents=True)
    extra = {}
    _write(proj, MOD_A)
    if git:
        _git(["init", "-q", "-b", "main"], proj)
        _write(proj, ".gitignore", ".claude/\n")
        _git(["add", "-A"], proj)
        _git(["commit", "-q", "-m", "init"], proj)
        extra["base_commit"] = _git(["rev-parse", "HEAD"], proj)
    _write(proj, MOD_B)
    _write(proj, ".claude/active_workflow", WF)
    _write(proj, f".claude/workflows/_log/2026-10-22_{WF}.yaml", f"workflow_id: {WF}\n")
    if cfg is not None:
        _write(proj, ".claude/config.yaml", cfg)
    if token:
        _write(proj, ".claude/user_override_token.json", json.dumps({"version": 2, "tokens": {
            token: {"created": datetime.now().isoformat(), "granted_by": "user_prompt"}}}))
    arts = [("test_output", f"{ART}/red.txt", "phase5_tdd_red")]
    if dialog:
        _make_dialog(proj)
        arts.append(("adversary_dialog", f"{ART}/adversary-dialog.md", "phase6b_adversary"))
    data = {"name": WF, "workflow_type": wf_type, "current_phase": phase,
            "context_file": "docs/context.md", "spec_file": "docs/specs/s.md",
            "spec_approved": True, "red_test_done": True, "adversary_verdict": VERIFIED,
            "phase_transitions": [], "phase_log": [], **extra,
            "test_artifacts": [{"type": t, "path": p, "description": "fixture", "phase": ph,
                                "created": "2026-10-22T10:00:00"} for t, p, ph in arts]}
    _write(proj, f".claude/workflows/{WF}.json", json.dumps(data, indent=2))
    if proof:
        _make_proof(proj)
    return proj


def _state(proj) -> dict:
    return json.loads((proj / ".claude" / "workflows" / f"{WF}.json").read_text())


def _xcrun_text(summary=None) -> str:
    """Semantisch gleich, aber bytegleich NIE: umsortiert, eingerückt, anderes finishTime."""
    d = dict(SUMMARY if summary is None else summary)
    d["finishTime"] = float(d.get("finishTime", 0)) + 0.25
    return json.dumps(dict(reversed(list(d.items()))), indent=2)


def _xc_env(tmp_path, summary=None, *, tool=True, **fake) -> dict:
    """PATH mit Fake-`xcrun` (tool=False: PATH ohne jedes xcrun) und FAKE_XCRUN_*-Steuerung."""
    path = [d for d in os.environ.get("PATH", "").split(os.pathsep)
            if d and not (Path(d) / "xcrun").exists()]
    out = {"FAKE_XCRUN_LOG": str(tmp_path / "xcrun.log")}
    if tool:
        bindir = tmp_path / "fakebin"
        bindir.mkdir(exist_ok=True)
        shutil.copy(FIX / "xcrun", bindir / "xcrun")
        (bindir / "xcrun").chmod(0o755)
        path.insert(0, str(bindir))
        out["FAKE_XCRUN_OUT"] = str(_write(tmp_path, "xcrun-out.json", _xcrun_text(summary)))
    out.update({f"FAKE_XCRUN_{k.upper()}": str(v) for k, v in fake.items()})
    return {"PATH": os.pathsep.join(path), **out}


def _xcrun_log(tmp_path) -> str:
    log = tmp_path / "xcrun.log"
    return log.read_text() if log.exists() else ""


def _clear_caches():
    import config_loader
    for fn in ("find_project_root", "load_config", "_worktree_secrets_section"):
        getattr(getattr(config_loader, fn, None), "cache_clear", lambda: None)()


@pytest.fixture(autouse=True)
def _cache_hygiene():
    _clear_caches()
    yield
    _clear_caches()


def _inproc(mp, proj, xc=None):
    """Unit-Ebene: Umgebung auf das Wegwerf-Projekt, DANN erst evidence_gate importieren."""
    for key in _SCRUBBED:
        mp.delenv(key, raising=False)
    mp.setenv("CLAUDE_PROJECT_DIR", str(proj))
    mp.chdir(proj)
    for key, val in (xc if xc is not None else _xc_env(proj.parent)).items():
        mp.setenv(key, val)
    _clear_caches()
    return importlib.import_module("evidence_gate")


def _check(mp, proj, data=None, xc=None, **kw):
    eg = _inproc(mp, proj, xc)
    return eg.check_evidence("phase8_complete", data or _state(proj), **kw)


def _wf(proj, *cmd, env=None, tmp_path=None):
    return _run("workflow.py", list(cmd), proj, env or _env(proj, **_xc_env(tmp_path or proj.parent)))


def _rejected_by_evidence(r, needle):
    assert r.returncode != 0, f"Übergang erlaubt: {r.stdout}{r.stderr}"
    assert re.search(needle, r.stderr), f"Grund nennt {needle!r} nicht: {r.stderr}"
    assert DIALOG_MSG not in r.stderr, f"am Dialog-Gate statt am Evidence-Gate: {r.stderr}"


# ------------------------------------------------------------------ AC-1 … AC-8: Config, Menge, Pfad
@pytest.mark.parametrize("cmd", [("phase", "phase8_complete"), ("complete",), ("finish",)],
                         ids=["phase", "complete", "finish"])
@pytest.mark.parametrize("cfg", [None, "evidence_checks: {}\n",
                                 "evidence_checks:\n  phase8_complete: []\n"],
                         ids=["missing", "empty", "empty-list"])
def test_ac1_without_config_identical(tmp_path, monkeypatch, cfg, cmd):
    proj = _project(tmp_path, cfg, dialog=True, proof=False)
    r = _wf(proj, *cmd)
    assert r.returncode == 0, f"ohne Gate-Config abgewiesen: {r.stderr}"
    assert _xcrun_log(tmp_path) == "", "xcrun ohne Gate-Config aufgerufen"
    eg = _inproc(monkeypatch, proj)
    calls = []

    def spy(*a, **k):
        calls.append(a[0] if a else k.get("args"))
        raise AssertionError("Subprozess (git/xcrun) im Evidence-Gate ohne Config")

    monkeypatch.setattr(subprocess, "Popen", spy)
    data = _state(proj) if (proj / ".claude/workflows" / f"{WF}.json").exists() else {"name": WF}
    assert eg.check_evidence("phase8_complete", data) is None
    assert calls == [], f"Subprozesse ohne Config: {calls}"


BROKEN = {"not-list": "  phase8_complete: simulator-run.txt\n",
          "entry-not-object": "  phase8_complete:\n    - xcresult_proof\n",
          "no-verifier": "  phase8_complete:\n    - file: simulator-run.txt\n",
          "no-file": "  phase8_complete:\n    - verifier: xcresult_proof\n",
          "file-slash": "  phase8_complete:\n" + ENTRY.format(v="xcresult_proof", f="sub/x.txt"),
          "file-dotdot": "  phase8_complete:\n" + ENTRY.format(v="xcresult_proof", f="'..'"),
          "file-dotdot-prefix": "  phase8_complete:\n"
                                + ENTRY.format(v="xcresult_proof", f="../simulator-run.txt")}


@pytest.mark.parametrize("body", BROKEN.values(), ids=BROKEN.keys())
def test_ac2_broken_config_rejected(tmp_path, monkeypatch, body):
    reason = _check(monkeypatch, _project(tmp_path, "evidence_checks:\n" + body))
    assert reason and re.search(r"(?i)config|evidence_checks", reason), reason


def test_ac3_unloadable_config_rejected(tmp_path, monkeypatch):
    import yaml
    cfg = GATE + "  phase8_complete: [unclosed\n: :\n"
    with pytest.raises(yaml.YAMLError):  # Vorbedingung: wirklich nicht ladbar (nicht AC-2)
        yaml.safe_load(cfg)
    reason = _check(monkeypatch, _project(tmp_path, cfg))
    assert reason and re.search(r"(?i)config", reason), reason


def test_ac4_unknown_verifier_rejected(tmp_path, monkeypatch):
    cfg = "evidence_checks:\n  phase8_complete:\n" + ENTRY.format(v="bogus_verifier",
                                                                  f="simulator-run.txt")
    reason = _check(monkeypatch, _project(tmp_path, cfg))
    assert reason and "bogus_verifier" in reason, reason


def test_ac5_empty_gate_set_and_exempt_paths(tmp_path, monkeypatch):
    proj = _project(tmp_path, GATE + "  exempt_paths:\n    - 'src/*'\n", proof=False)
    assert _check(monkeypatch, proj) is None, "exempt_paths leert die Gate-Menge nicht"
    _write(proj, ".claude/config.yaml", GATE)
    _clear_caches()
    reason = _check(monkeypatch, proj)
    assert reason and "simulator-run.txt" in reason, reason


@pytest.mark.parametrize("case", ["no-git-tree", "changeset-error"])
def test_ac6_no_git_tree_or_changeset_error_rejected(tmp_path, case):
    if case == "no-git-tree":  # Abdeckung (#259) entfällt ohne Git — das Evidence-Gate nicht
        proj = _project(tmp_path, git=False, dialog=True)
        env = _env(proj, GIT_CEILING_DIRECTORIES=str(tmp_path), **_xc_env(tmp_path))
    else:  # #259 abgeschaltet, `git diff` scheitert: nur das Evidence-Gate fragt die Menge ab
        proj = _project(tmp_path, GATE + COVERAGE_OFF, dialog=True)
        real = shutil.which("git")
        wrapper = _write(tmp_path, "gitbin/git", "#!/bin/sh\nfor a in \"$@\"; do case \"$a\" in "
                         "diff) echo 'fatal: simulierter diff-Fehler (#447)' >&2; exit 128;; "
                         f"esac; done\nexec \"{real}\" \"$@\"\n")
        wrapper.chmod(0o755)
        xc = _xc_env(tmp_path)
        env = _env(proj, **{**xc, "PATH": f"{wrapper.parent}{os.pathsep}{xc['PATH']}"})
    _rejected_by_evidence(_wf(proj, "phase", "phase8_complete", env=env),
                          r"(Ä|Ae)nderungsmenge|nicht ermittelbar|Git-Arbeitsbaum")


@pytest.mark.parametrize("name", ["../outside", "a/b"])
def test_ac7_workflow_name_with_slash_or_dotdot_rejected(tmp_path, monkeypatch, name):
    proj = _project(tmp_path)
    _make_proof(proj, wf=name)  # gültiger Beleg genau dort, wohin der Name zeigen würde
    assert _check(monkeypatch, proj, {**_state(proj), "name": name}) is not None


@pytest.mark.parametrize("case", ["regular", "file-link", "dir-link"])
def test_ac8_symlink_escape_rejected(tmp_path, monkeypatch, case):
    proj, outside = _project(tmp_path), tmp_path / "outside"
    outside.mkdir()
    src = {"file-link": PROOF, "dir-link": ART}.get(case)
    if src:
        shutil.move(str(proj / src), str(outside / "moved"))
        (proj / src).symlink_to(outside / "moved", target_is_directory=case == "dir-link")
    reason = _check(monkeypatch, proj)
    assert (reason is None) if case == "regular" else (reason is not None), reason


# ------------------------------------------------------------------ AC-9 … AC-22: Prüfkette
def test_ac9_proof_missing_rejected(tmp_path, monkeypatch):
    reason = _check(monkeypatch, _project(tmp_path, proof=False))
    assert reason and "simulator-run.txt" in reason and WF in reason, reason


@pytest.mark.parametrize("files", [(MOD_A,), ()], ids=["other-file-only", "no-code-files-line"])
def test_ac10_gate_file_missing_in_block_rejected(tmp_path, monkeypatch, files):
    proj = _project(tmp_path, proof=False)
    _make_proof(proj, files=files)
    reason = _check(monkeypatch, proj)
    assert reason and MOD_B in reason, reason


def test_ac11_stale_hash_rejected(tmp_path, monkeypatch):
    proj = _project(tmp_path)
    _write(proj, MOD_B, "VALUE = 2  # nach dem Lauf geändert\n")
    reason = _check(monkeypatch, proj)
    assert reason and MOD_B in reason, reason


@pytest.mark.parametrize("case", ["missing", "no-bundle-line", "checksum"])
def test_ac12_summary_json_missing_or_checksum_wrong_rejected(tmp_path, monkeypatch, case):
    proj = _project(tmp_path)
    if case == "no-bundle-line":  # Kopfzeile wie sim_proof.read_summary ohne Bündel
        text = (proj / PROOF).read_text()
        (proj / PROOF).write_text(re.sub(r"(?m)^summary: .*$",
                                         "summary: fehlt (kein Ergebnisbündel)", text))
    elif case == "missing":
        (proj / RUN / "summary.json").unlink()
    else:
        (proj / RUN / "summary.json").write_text(SUMMARY_TEXT + " ")
    reason = _check(monkeypatch, proj)
    assert reason and re.search(r"(?i)summary", reason), reason


def test_ac13_xcresult_missing_rejected(tmp_path, monkeypatch):
    proj = _project(tmp_path)
    shutil.rmtree(proj / RUN / "run.xcresult")
    reason = _check(monkeypatch, proj)
    assert reason and "xcresult" in reason, reason
    assert _xcrun_log(tmp_path) == "", "xcrun trotz fehlendem Bündel aufgerufen"


def test_ac14_xcresulttool_missing_rejected(tmp_path):
    proj = _project(tmp_path, dialog=True)
    r = _wf(proj, "phase", "phase8_complete", env=_env(proj, **_xc_env(tmp_path, tool=False)))
    _rejected_by_evidence(r, r"xcrun|xcresulttool")


def test_ac15_nonzero_exit_rejected(tmp_path):
    proj = _project(tmp_path, dialog=True)
    r = _wf(proj, "phase", "phase8_complete", env=_env(proj, **_xc_env(tmp_path, rc=37)))
    _rejected_by_evidence(r, r"\b37\b")


def test_ac16_invalid_json_rejected(tmp_path):
    proj = _project(tmp_path, dialog=True)
    env = _env(proj, **_xc_env(tmp_path, text="kein JSON {"))
    _rejected_by_evidence(_wf(proj, "phase", "phase8_complete", env=env), r"(?i)json|xcresult")


def test_ac17_timeout_rejected(tmp_path, monkeypatch):
    """Unit-Naht statt echtem Warten: die Spec legt keinen Timeout-Wert fest."""
    def runner(*a, **k):
        raise subprocess.TimeoutExpired(cmd=a[0] if a else k.get("args"), timeout=1)

    reason = _check(monkeypatch, _project(tmp_path), runner=runner)
    assert reason and re.search(r"(?i)timeout|zeitlimit", reason), reason


@pytest.mark.parametrize("field", ["result", "totalTestCount", "passedTests", "failedTests",
                                   "skippedTests"])
def test_ac18_semantic_mismatch_vs_summary_json_rejected(tmp_path, monkeypatch, field):
    proj = _project(tmp_path)
    derived = {**SUMMARY, field: "Failed" if field == "result" else SUMMARY[field] + 1}
    reason = _check(monkeypatch, proj, xc=_xc_env(tmp_path, derived))
    assert reason and field in reason, reason


@pytest.mark.parametrize("line,value", [
    ("ergebnis", "Failed"), ("tests", "3 gesamt, 2 bestanden, 1 fehlgeschlagen, 0 übersprungen")],
    ids=["ergebnis", "tests"])
def test_ac19_semantic_mismatch_vs_proof_lines_rejected(tmp_path, monkeypatch, line, value):
    proj = _project(tmp_path, proof=False)
    _make_proof(proj, **{line: value})
    reason = _check(monkeypatch, proj)
    assert reason and line in reason, reason


def test_ac20_result_not_passed_rejected(tmp_path, monkeypatch):
    failed = {**SUMMARY, "result": "Failed", "passedTests": 2, "failedTests": 1}
    proj = _project(tmp_path, proof=False)
    _make_proof(proj, summary=failed)
    reason = _check(monkeypatch, proj, xc=_xc_env(tmp_path, failed))
    assert reason and re.search(r"Passed|Failed|result", reason), reason


def test_ac21_zero_passed_tests_rejected(tmp_path, monkeypatch):
    skipped = {**SUMMARY, "totalTestCount": 1, "passedTests": 0, "failedTests": 0,
               "skippedTests": 1}
    proj = _project(tmp_path, proof=False)
    _make_proof(proj, summary=skipped)
    reason = _check(monkeypatch, proj, xc=_xc_env(tmp_path, skipped))
    assert reason and re.search(r"passedTests|bestanden", reason), reason


def test_ac22_green_case_real_format(tmp_path, monkeypatch):
    proj = _project(tmp_path, dialog=True)
    text = (proj / PROOF).read_text()
    assert text.startswith("# Simulator-Beleg\n") and f"  {MOD_A}\n" in text  # echtes Format
    assert _check(monkeypatch, proj) is None
    assert "xcresulttool get test-results summary" in _xcrun_log(tmp_path)
    r = _wf(proj, "phase", "phase8_complete", tmp_path=tmp_path)  # Ende-zu-Ende über den Hook
    assert r.returncode == 0 and _state(proj)["current_phase"] == "phase8_complete", r.stderr


# ------------------------------------------------------------------ AC-23 … AC-26: Wege, Ausweg, Naht
@pytest.mark.parametrize("phase,cmd", [
    ("phase7_validate", ("phase", "phase8_complete")), ("phase7_validate", ("complete",)),
    ("phase7_validate", ("finish",)), ("phase8_complete", ("complete",)),
    ("phase8_complete", ("finish",))],
    ids=["phase", "complete", "finish", "same-phase-complete", "same-phase-finish"])
def test_ac23_all_completion_paths_checked(tmp_path, phase, cmd):
    proj = _project(tmp_path, dialog=True, proof=False, phase=phase)
    _rejected_by_evidence(_wf(proj, *cmd), "simulator-run.txt")
    no_dialog = _project(tmp_path / "nd", proof=False, phase=phase)  # Dialog-Check zuerst
    r = _wf(no_dialog, *cmd, tmp_path=tmp_path / "nd")
    assert r.returncode != 0 and DIALOG_MSG in r.stderr, r.stderr
    assert "simulator-run" not in r.stderr, f"Evidence-Grund vor dem Dialog-Check: {r.stderr}"


def test_ac24_fast_track_gated_only_phase8_with_config(tmp_path):
    ff = {"proof": False, "phase": "phase6_implement", "wf_type": "feature-fast"}
    proj = _project(tmp_path, **ff)
    _rejected_by_evidence(_wf(proj, "phase", "phase8_complete"), "simulator-run.txt")
    assert _wf(proj, "phase", "phase7_validate").returncode == 0
    plain = _project(tmp_path / "nc", None, **ff)
    r = _wf(plain, "phase", "phase8_complete", tmp_path=tmp_path / "nc")
    assert r.returncode == 0, f"Fast Track ohne Config verändert: {r.stderr}"


@pytest.mark.parametrize("token,dialog,ok", [
    (WF, True, True), (WF, False, False), (None, True, False), ("wf-anderer", True, False)],
    ids=["own-token", "own-token-no-dialog", "no-token", "foreign-token"])
def test_ac25_override_opens_only_evidence_gate(tmp_path, token, dialog, ok):
    proj = _project(tmp_path, dialog=dialog, proof=False, token=token)
    r = _wf(proj, "phase", "phase8_complete")
    if ok:
        assert r.returncode == 0 and OVERRIDE_MSG in r.stderr, f"{r.returncode}: {r.stderr}"
    elif not dialog:
        assert r.returncode != 0 and DIALOG_MSG in r.stderr, r.stderr
    else:
        _rejected_by_evidence(r, "simulator-run.txt")


def test_ac26_runner_not_overridable_by_config_or_env(tmp_path, monkeypatch):
    marker = tmp_path / "evil-ran"
    evil = _write(tmp_path, "evil.sh", f"#!/bin/sh\ntouch '{marker}'\ncat '{tmp_path}/xcrun-out.json'\n")
    evil.chmod(0o755)
    proj = _project(tmp_path)
    for var in ("EVIDENCE_GATE_RUNNER", "OPENSPEC_EVIDENCE_RUNNER", "EVIDENCE_RUNNER",
                "XCRESULTTOOL", "XCRUN", "OPENSPEC_XCRUN"):
        monkeypatch.setenv(var, str(evil))
    assert _check(monkeypatch, proj) is None
    argv = _xcrun_log(tmp_path)
    assert re.search(r"^xcresulttool get test-results summary .*--path \S*run\.xcresult", argv,
                     re.M) and "--compact" in argv, argv
    _write(proj, ".claude/config.yaml", GATE + f"      runner: {evil}\n      command: {evil}\n")
    _clear_caches()
    _check(monkeypatch, proj)  # Abweisen oder Erlauben egal — nur das eigene Kommando zählt
    calls = []

    def rec(*a, **k):
        calls.append(list(a[0] if a else k.get("args")))
        return subprocess.CompletedProcess(calls[-1], 0, _xcrun_text(), "")

    _write(proj, ".claude/config.yaml", GATE)
    _clear_caches()
    assert _check(monkeypatch, proj, runner=rec) is None
    assert calls and Path(calls[0][0]).name == "xcrun" and calls[0][1:5] == [
        "xcresulttool", "get", "test-results", "summary"], calls
    assert not marker.exists(), "eingeschleuster Runner wurde ausgeführt"
    src = (HOOKS_DIR / "evidence_gate.py").read_text()
    assert not re.search(r"os\.environ|getenv", src), "evidence_gate liest Umgebungsvariablen"


# ------------------------------------------------------------------ AC-27 … AC-30: Schreibsperre, Template
def _sandbox(tmp_path, cfg=None, workflow=True) -> Path:
    root = (tmp_path / "sb").resolve()
    (root / ".git").mkdir(parents=True)
    _write(root, ".claude/workflows/x.keep", "")
    if workflow:
        _write(root, f".claude/workflows/{WF}.json", json.dumps({
            "name": WF, "current_phase": "phase6_implement", "workflow_type": "feature",
            "red_test_done": True, "spec_approved": True, "affected_files": []}))
        _write(root, ".claude/active_workflow", WF + "\n")
    if cfg:
        _write(root, ".claude/config.yaml", cfg)
    return root


def _edit_gate(root, tool, path, content="x"):
    tin = {"file_path": path, "content": content} if tool == "Write" else {
        "file_path": path, "old_string": "a", "new_string": content}
    return _run("edit_gate.py", [], root, stdin=json.dumps({"tool_name": tool, "tool_input": tin}))


def _bash_gate(root, command):
    return _run("bash_gate.py", [], root, stdin=json.dumps({"tool_name": "Bash",
                                                             "tool_input": {"command": command}}))


TARGETS = [PROOF, f"{RUN}/summary.json", f"{RUN}/run.xcresult/Info.plist"]


@pytest.mark.parametrize("cfg,workflow", [(None, True), (GATE, True), (None, False)],
                         ids=["no-config", "gate-on", "no-workflow"])
def test_ac27_edit_gate_blocks_proof_files(tmp_path, cfg, workflow):
    root = _sandbox(tmp_path, cfg, workflow)
    wrong = [f"{tool} {p}: rc={r.returncode} {r.stderr.strip()[:120]!r}"
             for tool in ("Write", "Edit") for rel in TARGETS for p in (rel, str(root / rel))
             if (r := _edit_gate(root, tool, p)).returncode != 2]
    assert not wrong, "Beleg-Datei per Write/Edit schreibbar:\n" + "\n".join(wrong)


def test_ac28_bash_gate_blocks_proof_writes(tmp_path):
    root = _sandbox(tmp_path)
    forms = ["echo x > {t}", "echo x >> {t}", "echo x | tee {t}", "cp /tmp/a {t}", "mv /tmp/a {t}",
             "sed -i s/a/b/ {t}", "rm {t}", "git status > {t}", "ls && echo x > {t}",
             "python3 .claude/hooks/workflow.py status > {t}"]
    wrong = [f"{cmd!r}: rc={r.returncode}" for t in TARGETS[:2] for f in forms
             if (r := _bash_gate(root, cmd := f.format(t=t))).returncode != 2]
    assert not wrong, "Bash-Schreibzugriff auf den Beleg rutscht durch:\n" + "\n".join(wrong)


def test_ac29_write_protection_is_narrow(tmp_path):
    """Regressionswächter (heute grün): enge Sperre; rote Gegenprobe sind AC-27/AC-28."""
    root = _sandbox(tmp_path)
    edits = [("Write", "docs/artifacts/x/other.txt", "x"),
             ("Write", "docs/notes.md", f"Der Beleg liegt unter {PROOF}.\n"),
             ("Edit", "docs/notes.md", f"siehe {RUN}/summary.json")]
    wrong = [f"{t} {p}: rc={r.returncode} {r.stderr.strip()[:120]!r}" for t, p, c in edits
             if (r := _edit_gate(root, t, p, c)).returncode != 0]
    cmds = ["echo x > docs/artifacts/x/other.txt", f'echo "Beleg: {PROOF}" >> docs/notes.md',
            f"cat {PROOF}", f"ls {RUN}/",
            f"grep -c ergebnis {PROOF}", f"scripts/sim.sh test-proof {WF} LooseEndsUITests",
            f"python3 scripts/sim_proof.py {WF} LooseEndsUITests {RUN}/run.xcresult "
            f"'** TEST SUCCEEDED **' 'scripts/sim.sh test-proof' 0"]
    wrong += [f"{c!r}: rc={r.returncode} {r.stderr.strip()[:120]!r}" for c in cmds
              if (r := _bash_gate(root, c)).returncode != 0]
    assert not wrong, "Sperre zu breit:\n" + "\n".join(wrong)


def test_ac30_config_template_documents_evidence_checks():
    import yaml
    text = (REPO_ROOT / "config.yaml").read_text()
    assert "evidence_checks" in text, "Abschnitt evidence_checks fehlt im Template"
    assert "exempt_paths" in text, "exempt_paths nicht dokumentiert"
    section = (yaml.safe_load(text) or {}).get("evidence_checks") or {}
    assert not section.get("phase8_complete"), f"Default nicht leer: {section}"
