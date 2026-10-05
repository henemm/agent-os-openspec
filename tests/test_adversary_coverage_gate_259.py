"""TDD RED — Issue #259: Adversary-Dialog-Nachweis an die tatsächliche Änderungsmenge binden.

AC-1 … AC-14 (docs/specs/fix-259-adversary-diff-binding.md) laufen Ende-zu-Ende über die echten
Hook-Skripte in Wegwerf-Repos (echte Commits, Bare-Repo als `origin`, `git worktree add`); AC-10
in-process, AC-15 als Pfad-Tabelle gegen edit_gate.py, AC-16 als Doku-Prüfung. Hermetik (#265):
cwd/CLAUDE_PROJECT_DIR im tmp-Projekt, ohne Sitzungs-/GIT_*-Variablen und globale Git-Config;
den aktiven Workflow setzt nur `.claude/active_workflow` im tmp-Projekt. Neues Verhalten wird
erst im Test angesprochen. Regressionswächter (heute grün) nennen ihre rote Gegenprobe.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import types
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

WF = "wf-259"
DIALOG = f"docs/artifacts/{WF}/adversary-dialog.md"  # Standardpfad dieses Workflows
FOREIGN = "docs/artifacts/wf-A/adversary-dialog.md"  # Protokoll von Workflow A (F001)
GENERIC = "docs/artifacts/adversary-dialog.md"  # F004: 'docs/artifacts/<leer>/…'
MOD_A, MOD_B, MOD_C = "src_A/module_a.py", "src/module_b.py", "src/module_c.py"
COVERED = {"cited": (MOD_A, MOD_B), "rel": DIALOG}  # eigenes Protokoll zitiert alles
VERIFIED = "VERIFIED:Tests PASSED: 5 passed"
CFG_OFF = "adversary_coverage_gate:\n  enabled: false\n"
# Meldungs-Kerne aus dem Spec-Abschnitt "Error Handling"
UNCOVERED, PARTIAL = "nicht zitiert", "teilweise gestagt"
GIT_ERROR, DEGRADED = "nicht ermittelbar", "nur HEAD"
OUTSIDE_RE = re.compile(r"au(ß|ss)erhalb")  # F002
NON_CODE = ("docs/helper.py", "tests/test_mod.py", "scripts/tool.py", "src/notes.md",
            "src/data.json", "src/conf.yaml")
CHANGE_SET = r"#259|required-files|(Ä|Ae)nderungsmenge|Abdeckungspr(ü|ue)fung"  # AC-16
GREEN_OUTPUT = ("============================= test session starts ==============================\n"
                "collected 5 items\n\ntests/test_gate.py .....\n\n"
                "============================= 5 passed in 0.12s ==============================\n")
_SCRUBBED = {"CLAUDE_TOOL_INPUT", "CLAUDE_TOOL_NAME", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT",
             "CLAUDE_CODE_SESSION_ID", "OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK",
             "PYTHONPATH"}


def _env(project_dir=None, **extra) -> dict:
    """Hermetisch: ohne Sitzungs- und GIT_*-Variablen, ohne globale/System-Git-Config."""
    env = {k: v for k, v in os.environ.items() if k not in _SCRUBBED and not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return {**env, **extra}


def _run(script, args: list, cwd: Path, env=None, stdin=None, check=False):
    """Hook-Skript aus core/hooks (bei script=None: `python -c …`), cwd im tmp-Projekt."""
    io = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
    head = [str(HOOKS_DIR / script)] if script else []
    r = subprocess.run([sys.executable, *head, *args], capture_output=True, text=True,
                       cwd=str(cwd), env=env or _env(cwd), timeout=60, **io)
    assert not check or r.returncode == 0, f"{script} {args}: {r.stdout}{r.stderr}"
    return r


def _git(args: list, cwd: Path) -> str:
    r = subprocess.run(["git", "-c", "user.email=t@t.invalid", "-c", "user.name=Test",
                        "-c", "commit.gpgsign=false", *args],
                       cwd=str(cwd), capture_output=True, text=True, env=_env())
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout.strip()


def _sha(cwd: Path) -> str:
    return _git(["rev-parse", "HEAD"], cwd)


def _write(root: Path, rel: str, text: "str | None" = None) -> Path:
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {rel}\nVALUE = 1\n" if text is None else text)
    return path


def _new(root: Path, *rels: str, stage=False, commit=None):
    """Dateien mit Standardinhalt anlegen; optional stagen bzw. committen (Rückgabe: SHA)."""
    for rel in rels:
        _write(root, rel)
    if stage or commit:
        _git(["add", "--", *rels], root)
    if commit:
        _git(["commit", "-q", "-m", commit], root)
        return _sha(root)


def _make_repo(tmp_path: Path, name="proj", *, origin=False, commit=True) -> Path:
    """C0 = .gitignore (.claude/), README.md, MOD_A; aktiver Workflow WF per tmp-Datei."""
    proj = tmp_path / name
    proj.mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], proj)
    _write(proj, ".gitignore", ".claude/\n")
    _new(proj, "README.md", MOD_A)
    if commit:
        _git(["add", "-A"], proj)
        _git(["commit", "-q", "-m", "init"], proj)
    if origin:
        bare = tmp_path / f"{name}-origin.git"
        _git(["init", "-q", "--bare", "-b", "main", str(bare)], tmp_path)
        _git(["remote", "add", "origin", str(bare)], proj)
        _git(["push", "-q", "origin", "main"], proj)  # legt origin/main an
    _write(proj, ".claude/active_workflow", WF)
    return proj


def _make_worktree(tmp_path: Path) -> "tuple[Path, Path]":
    """Hauptrepo + echter `git worktree` außerhalb davon; aktiver Workflow worktree-lokal."""
    main, wt = _make_repo(tmp_path, "main"), tmp_path / "worktrees" / "feat-259"
    _git(["worktree", "add", "-q", "-b", "feat-259", str(wt)], main)
    _write(wt, ".claude/active_workflow", WF)
    return main, wt


def _write_workflow(root: Path, *, phase="phase7_validate", verdict=VERIFIED, wf_type="feature",
                    artifacts=(), name=WF, **extra) -> None:
    """State wie nach Phase 5; `artifacts` = registrierte Dialog-Pfade; name=None → Feld fehlt."""
    arts = [("test_output", f"docs/artifacts/{WF}/red.txt", "phase5_tdd_red")]
    arts += [("adversary_dialog", str(a), "phase6b_adversary") for a in artifacts]
    data = {"workflow_type": wf_type, "current_phase": phase, "context_file": "docs/context.md",
            "spec_file": "docs/specs/s.md", "spec_approved": True, "red_test_done": True,
            "adversary_verdict": verdict, "phase_transitions": [], "phase_log": [],
            "test_artifacts": [{"type": t, "path": p, "description": "fixture", "phase": ph,
                                "created": "2026-09-28T10:00:00"} for t, p, ph in arts], **extra}
    if name is not None:
        data["name"] = name
    _write(root, f".claude/workflows/{WF}.json", json.dumps(data, indent=2))


def _state(root: Path) -> dict:
    return json.loads((root / ".claude" / "workflows" / f"{WF}.json").read_text())


def _make_dialog(root: Path, cited, rel: str = DIALOG, verdict: str = "VERIFIED") -> Path:
    """Protokoll (Checkliste, 2 Runden, Verdict), per `stamp` gehasht — heute schon gültig."""
    refs = "".join(f"  Code reference: {c}:1\n" for c in cited)
    art = _write(root, rel, (
        "# Adversary Dialog\n\n## Checkliste\n- [x] AC-1: deckt die Änderung ab — Beweis: Test\n"
        f"{refs}\n## Dialog\n\n### Runde 1\n**Adversary:** A1\n**Implementierer:** B1\n\n"
        f"### Runde 2\n**Adversary:** A2\n**Implementierer:** B2\n\nVERDICT: {verdict}\n"))
    _run("adversary_dialog.py", ["stamp", str(art)], root, check=True)
    _run("adversary_dialog.py", ["validate", str(art)], root, check=True)  # Fixture-Kontrolle
    return art


def _write_override_token(root: Path) -> None:
    _write(root, ".claude/user_override_token.json", json.dumps({"version": 2, "tokens": {
        WF: {"created": datetime.now().isoformat(), "granted_by": "user_prompt"}}}))


def _failing_git_env(tmp_path: Path, proj: Path, fail="diff",
                     msg="simulierter diff-Fehler (Test-Wrapper #259)") -> dict:
    """AC-8: `git`-Wrapper vorn im PATH — der Unterbefehl `fail` scheitert (Standard: nur `git
    diff`; `*`: jeder, F102), alles andere läuft echt."""
    real = shutil.which("git")
    assert real, "git nicht im PATH"
    wrapper = _write(tmp_path, "fakebin/git", f"""#!/bin/sh
skip=0; sub=""
for a in "$@"; do
  if [ "$skip" = 1 ]; then skip=0; continue; fi
  case "$a" in -C|-c|--git-dir|--work-tree) skip=1 ;; -*) ;; *) sub="$a"; break ;; esac
done
case "$sub" in {fail}) echo "fatal: {msg}" >&2; exit 128 ;; esac
exec "{real}" "$@"
""")
    wrapper.chmod(0o755)
    return _env(proj, PATH=f"{wrapper.parent}{os.pathsep}{os.environ.get('PATH', '')}")


def _plain_project(tmp_path: Path, dot_git=False) -> "tuple[Path, dict]":
    """Kein Git-Arbeitsbaum (evtl. leeres .git); MOD_B geändert, der Dialog zitiert nur MOD_A."""
    proj = tmp_path / "proj"
    _write(proj, ".claude/active_workflow", WF)
    if dot_git:
        (proj / ".git").mkdir()
    env = _env(proj, GIT_CEILING_DIRECTORIES=str(tmp_path))  # git sucht nicht oberhalb
    assert subprocess.run(["git", "rev-parse", "--git-dir"], cwd=proj, env=env,
                          capture_output=True).returncode != 0, "unerwartet ein Git-Repo"
    _new(proj, MOD_A, MOD_B)
    _make_dialog(proj, [MOD_A])
    _write_workflow(proj, artifacts=[DIALOG])
    return proj, env


def _gate(cwd: Path, gate="commit", env=None, command="git commit -m wip",
          cmd=("phase", "phase8_complete")):
    """Commit-Gate (bash_gate.py mit Hook-JSON) bzw. Phase-8-Übergang (workflow.py)."""
    if gate == "commit":
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        return _run("bash_gate.py", [], cwd, env, stdin=payload)
    return _run("workflow.py", list(cmd), cwd, env)


def _blocked(r, gate: str) -> bool:
    return r.returncode == 2 if gate == "commit" else r.returncode != 0


def _staged_b(tmp_path: Path, cited=(MOD_A,), rel=FOREIGN, **wf) -> Path:
    """F001 (#259): fremdes Protokoll (nur MOD_A), MOD_B gestagt; **COVERED: alles zitiert."""
    proj = _make_repo(tmp_path)
    _new(proj, MOD_B, stage=True)
    _make_dialog(proj, cited, rel)
    _write_workflow(proj, artifacts=[rel], base_commit=_sha(proj), **wf)
    return proj


def _partial_repo(tmp_path: Path) -> Path:
    """MOD_B gestagt, danach im Arbeitsbaum weiter geändert; der Dialog hasht den Arbeitsbaum."""
    proj = _make_repo(tmp_path)
    _write(proj, MOD_B, "B = 1\n")
    _git(["add", MOD_B], proj)
    _write(proj, MOD_B, "B = 2  # nach dem Stagen geändert\n")
    _make_dialog(proj, [MOD_B])
    _write_workflow(proj, phase="phase6_implement", artifacts=[DIALOG])
    return proj


def test_ac1_foreign_dialog_does_not_cover_staged_file(tmp_path):
    r = _gate(_staged_b(tmp_path, phase="phase6_implement"))
    assert r.returncode == 2, f"F001-Commit erlaubt (rc={r.returncode}): {r.stderr}"
    assert MOD_B in r.stderr and UNCOVERED in r.stderr, r.stderr


@pytest.mark.parametrize("cmd", [("phase", "phase8_complete"), ("complete",), ("finish",)],
                         ids=["phase", "complete", "finish"])
def test_ac2_phase8_blocks_uncovered_change(tmp_path, cmd):
    proj = _staged_b(tmp_path)
    _write(proj, f".claude/workflows/_log/2026-09-28_{WF}.yaml", f"workflow_id: {WF}\n")
    r = _gate(proj, "phase8", cmd=cmd)
    assert r.returncode != 0, f"F001: Phase 8 per '{cmd[0]}' erreicht: {r.stdout}{r.stderr}"
    assert MOD_B in r.stderr, f"stderr nennt {MOD_B} nicht: {r.stderr}"
    assert _state(proj)["current_phase"] == "phase7_validate"


def test_ac3_fully_cited_dialog_still_opens_commit_and_phase8(tmp_path):
    """Wächter (heute grün); rote Gegenprobe: ..._documented_path_with_required_files."""
    proj = _staged_b(tmp_path, **COVERED)
    assert _gate(proj).returncode == 0
    p = _gate(proj, "phase8")
    assert p.returncode == 0 and _state(proj)["current_phase"] == "phase8_complete", p.stderr


def test_ac3_documented_path_with_required_files(tmp_path):
    """DoD: required-files → Dialog → stamp → add-artifact → qa_gate → Commit und Phase 8."""
    proj = _make_repo(tmp_path)
    _write_workflow(proj, phase="phase6b_adversary", verdict=None, base_commit=_sha(proj))
    _new(proj, MOD_B, "docs/notes.md", "tests/test_b.py", stage=True)
    req = _run("adversary_dialog.py", ["required-files"], proj)
    assert req.returncode == 0, f"required-files fehlt/scheitert: {req.stdout}{req.stderr}"
    assert req.stdout.split() == [MOD_B], req.stdout
    art = _make_dialog(proj, req.stdout.split())
    _run("workflow.py", ["add-artifact", "adversary_dialog", DIALOG, "Adversary Dialog Protokoll",
                         "phase6b_adversary"], proj, check=True)
    out = _write(proj, f"docs/artifacts/{WF}/test-green-output.txt", GREEN_OUTPUT)
    _run("qa_gate.py", [str(out), "--checklist", str(art)], proj, check=True)
    assert _gate(proj).returncode == 0
    for target in ("phase7_validate", "phase8_complete"):
        p = _gate(proj, "phase8", cmd=("phase", target))
        assert p.returncode == 0, p.stderr


@pytest.mark.parametrize("cited", [False, True], ids=["uncited", "cited"])
@pytest.mark.parametrize("setup,command", [
    ("index", "git commit -m wip"), ("tracked", "git commit -am wip"),
    ("tracked", f"git commit -m wip {MOD_B}"), ("tracked", "git commit -m wip"),
    ("amend", "git commit --amend -m wip"), ("untracked", f"git add {MOD_B} && git commit -m wip"),
    ("boomerang", 'git commit -m "fix --amend text"'),  # F101: --amend nur im Nachrichtentext
    ("boomerang", "git commit --amend -m wip"),  # F101-Gegenprobe: echtes --amend, Vereinigung
    # Die Menge wird nie kleiner als der Index (Vereinigung statt Ersetzung):
    ("staged-reverted", "git add other.md && git commit -m msg"),
    ("staged-reverted", "git commit -i other.py -m msg"),  # --include: Index plus Pfad
    ("index-at-head", "git commit --amend -m wip"),  # Index = HEAD, Arbeitsbaum = HEAD~1-Stand
], ids=["index", "all-am", "pathspec", "empty-index", "amend", "add-and-commit",
        "amend-in-message", "amend-boomerang", "add-staged-reverted", "include-staged-reverted",
        "amend-index-at-head"])
def test_ac4_commit_set_covers_every_commit_form(tmp_path, setup, command, cited):
    """'cited' je Form = Regressionswächter (heute grün), 'uncited' = rote Gegenprobe."""
    proj = _make_repo(tmp_path)
    if setup in ("tracked", "amend", "boomerang", "index-at-head"):  # MOD_B steckt im HEAD-Commit
        _new(proj, MOD_B, commit="B")
    if setup == "tracked":
        _write(proj, MOD_B, "B = 2  # geändert, nicht gestagt\n")
    elif setup in ("boomerang", "index-at-head"):  # HEAD ändert MOD_B, zurück auf HEAD~1-Stand
        v1 = (proj / MOD_B).read_text()
        _write(proj, MOD_B, "B = 2\n")
        _git(["commit", "-q", "-am", "B2"], proj)
        _write(proj, MOD_B, v1)
        if setup == "boomerang":  # F101: gestagt zurück
            _git(["add", MOD_B], proj)
        else:  # nur eine andere Datei gestagt, MOD_B bleibt im Index auf dem HEAD-Stand
            _new(proj, "other.md", stage=True)
    elif setup == "staged-reverted":  # MOD_B gestagt geändert, Arbeitsbaum ungestagt = HEAD
        _new(proj, MOD_B, "other.py", commit="B")
        v1 = (proj / MOD_B).read_text()
        _write(proj, MOD_B, "B = 2\n")
        _git(["add", MOD_B], proj)
        _write(proj, MOD_B, v1)
        _new(proj, "other.md")
    elif setup in ("index", "untracked"):
        _new(proj, MOD_B, stage=setup == "index")
    _make_dialog(proj, [MOD_A, MOD_B] if cited else [MOD_A])
    _write_workflow(proj, phase="phase6_implement", artifacts=[DIALOG])
    r = _gate(proj, command=command)
    if cited:
        assert r.returncode == 0, r.stderr
    else:
        assert r.returncode == 2, f"'{command}': nicht zitierte Code-Datei übersehen: {r.stderr}"
        assert MOD_B in r.stderr and UNCOVERED in r.stderr, r.stderr


@pytest.mark.parametrize("command,expected_rc", [
    ('git commit -m "fix --amend text"', 0), ("git commit -m --amend", 0),
    ("git commit --amend -m wip", 2), ("git commit --amen -m wip", 2),
    ('bash -c "git commit --amend -m wip"', 2),
], ids=["message-text", "message-value", "option", "abbreviated", "not-decomposable"])
def test_ac4_amend_only_as_real_commit_option(tmp_path, command, expected_rc):
    """F101 (b): MOD_B steckt nur im HEAD-Commit und zählt allein bei echtem `--amend`-Token
    (auch als von git akzeptierte Abkürzung) bzw. bei nicht zerlegbarem Aufruf."""
    proj = _make_repo(tmp_path)
    _new(proj, MOD_B, commit="B")
    _new(proj, MOD_C, stage=True)
    _make_dialog(proj, [MOD_A, MOD_C])
    _write_workflow(proj, phase="phase6_implement", artifacts=[DIALOG])
    r = _gate(proj, command=command)
    assert r.returncode == expected_rc, f"'{command}' (rc={r.returncode}): {r.stderr}"
    assert expected_rc == 0 or MOD_B in r.stderr, r.stderr


@pytest.mark.parametrize("gate", ["commit", "phase8"])
@pytest.mark.parametrize("cite_new", [False, True], ids=["new-path-uncited", "new-path-cited"])
def test_ac5_rename_delete_and_non_code(tmp_path, gate, cite_new):
    """'new-path-cited' = Wächter (heute grün); 'new-path-uncited' = rote Gegenprobe."""
    proj = _make_repo(tmp_path)
    base = _new(proj, "src/old_name.py", "src/to_delete.py", commit="vor dem Start")
    _git(["rm", "-q", "src/to_delete.py"], proj)
    _git(["mv", "src/old_name.py", "src/new_name.py"], proj)
    _new(proj, MOD_B, *NON_CODE, stage=True)
    _make_dialog(proj, [MOD_B, "src/new_name.py"] if cite_new else [MOD_B])
    _write_workflow(proj, artifacts=[DIALOG], base_commit=base)
    r = _gate(proj, gate)
    if cite_new:
        assert r.returncode == 0, r.stderr
        return
    assert _blocked(r, gate), f"umbenannte Datei nicht unter neuem Pfad erfasst: {r.stderr}"
    assert "src/new_name.py" in r.stderr, r.stderr
    for absent in ("old_name", "to_delete", *NON_CODE):
        assert absent not in r.stderr, f"{absent} fälschlich gezählt: {r.stderr}"


@pytest.mark.parametrize("extensions,changed,blocks", [
    ([".py", ".sql"], "db/schema.sql", True),  # erweitert: .sql zählt (heute rot)
    ([".ts"], MOD_B, False),  # eingeschränkt: .py zählt nicht (Wächter, heute grün)
], ids=["extended", "restricted"])
def test_ac5_strict_code_gate_extension_list_applies(tmp_path, extensions, changed, blocks):
    proj = _make_repo(tmp_path)
    _write(proj, "config.yaml", json.dumps({"strict_code_gate": {"code_extensions": extensions}}))
    _new(proj, changed, stage=True)
    _make_dialog(proj, [MOD_A])
    _write_workflow(proj, artifacts=[DIALOG])
    r = _gate(proj)
    assert r.returncode == (2 if blocks else 0), f"strict_code_gate {extensions}: {r.stderr}"
    assert not blocks or changed in r.stderr, r.stderr


@pytest.mark.parametrize("command,expected_rc", [("git commit -m wip", 2),
                                                 ("git commit -am wip", 0)], ids=["index", "all"])
def test_ac6_partially_staged_file_blocks_index_commit(tmp_path, command, expected_rc):
    """'all' = Regressionswächter (heute grün): -a committet den geprüften Arbeitsbaum."""
    r = _gate(_partial_repo(tmp_path), command=command)
    assert r.returncode == expected_rc, f"'{command}' (rc={r.returncode}): {r.stderr}"
    assert expected_rc == 0 or (PARTIAL in r.stderr and MOD_B in r.stderr), r.stderr


@pytest.mark.parametrize("setup", ["feature", "feature-fast", "no-head", "worktree",
                                   "git-failure"],
                         ids=["a-feature", "a-feature-fast", "a-no-head", "g-worktree",
                              "a-git-failure"])
def test_ac7_start_records_base_commit(tmp_path, setup):
    env = None
    if setup == "worktree":  # (g): Basis ist HEAD des Worktrees, nicht des Hauptrepos
        state_root, cwd = _make_worktree(tmp_path)
        expected = _new(cwd, MOD_B, commit="nur im Worktree")
        assert expected != _sha(state_root)
    else:
        state_root = cwd = _make_repo(tmp_path, commit=setup != "no-head")
        expected = None if setup in ("no-head", "git-failure") else _sha(cwd)
    if setup == "git-failure":  # F102: start scheitert nie an git, base_commit = null
        env = _failing_git_env(tmp_path, cwd, "*", NO_REPO_MSG)
    wf_type = setup if setup == "feature-fast" else "feature"
    r = _run("workflow.py", ["start", WF, "--type", wf_type], cwd, env)
    assert r.returncode == 0, r.stderr
    state = _state(state_root)
    assert "base_commit" in state and state["base_commit"] == expected, state


def _rebased_repo(tmp_path: Path) -> "tuple[Path, str]":
    """(b): S = C0, eigener Commit MOD_B, MOD_C neu; upstream_mod.py per Rebase hereingezogen."""
    proj = _make_repo(tmp_path, origin=True)
    start = _sha(proj)
    _git(["checkout", "-q", "-b", "feat"], proj)
    _new(proj, MOD_B, commit="eigene Änderung")
    _new(proj, MOD_C)
    up = tmp_path / "upstream"
    _git(["clone", "-q", str(tmp_path / "proj-origin.git"), str(up)], tmp_path)
    _new(up, "src/upstream_mod.py", commit="upstream")
    _git(["push", "-q", "origin", "main"], up)
    _git(["fetch", "-q", "origin"], proj)
    _git(["rebase", "-q", "origin/main"], proj)
    return proj, start


def _scenario(tmp_path: Path, name: str):
    """AC-7 (b)–(g) → (cwd, State-Root, Felder, eigene Dateien, Ziele, Fremdes, Hinweis)."""
    if name == "b-rebase":
        proj, start = _rebased_repo(tmp_path)
        return proj, proj, {"base_commit": start}, [MOD_B, MOD_C], [MOD_B], ["upstream_mod"], None
    if name == "e-no-head":  # Index UND Unversioniertes zählen
        proj = _make_repo(tmp_path, commit=False)
        _new(proj, "src/staged_mod.py", stage=True)
        _new(proj, "src/untracked_mod.py")
        both = ["src/staged_mod.py", "src/untracked_mod.py"]
        return proj, proj, {"base_commit": None}, both, both, [], None
    if name == "g-worktree":
        main, wt = _make_worktree(tmp_path)
        wf = {"base_commit": _sha(wt)}
        _new(wt, MOD_B, stage=True)
        _new(main, "src/main_only.py")  # Änderung im Hauptrepo — gehört nicht zur Sitzung
        return wt, main, wf, [MOD_B], [MOD_B], ["main_only"], None
    proj = _make_repo(tmp_path, origin=name == "c-second-workflow")
    if name == "c-second-workflow":  # erster Workflow auf demselben Branch, nicht gemergt
        _git(["checkout", "-q", "-b", "feat"], proj)
    earlier = {"c-second-workflow": "src/first_wf.py", "d-no-origin": "src/old_work.py",
               "f-degraded": "src/committed_mod.py"}[name]
    start = _new(proj, earlier, commit=f"{earlier} committet")
    if name == "f-degraded":  # alter Workflow: kein base_commit, kein origin/main
        _new(proj, MOD_B)
        return proj, proj, {}, [MOD_B], [MOD_B], [earlier], DEGRADED
    _new(proj, MOD_B, commit="eigene Änderung seit dem Start")
    return proj, proj, {"base_commit": start}, [MOD_B], [MOD_B], [earlier], None


@pytest.mark.parametrize("cite_all", [False, True], ids=["own-uncited", "foreign-not-counted"])
@pytest.mark.parametrize("scenario", ["b-rebase", "c-second-workflow", "d-no-origin",
                                      "e-no-head", "f-degraded", "g-worktree"])
def test_ac7_phase8_base_selection(tmp_path, scenario, cite_all):
    """'foreign-not-counted' = Regressionswächter (heute grün): Upstream-, Vor-Start-,
    Fremd-Workflow- und Hauptrepo-Dateien zählen nicht. 'own-uncited' = rote Gegenprobe: die
    nicht zitierte eigene Datei (seit der Basis committet bzw. im Index) blockt."""
    cwd, state_root, wf, own, targets, absent, note = _scenario(tmp_path, scenario)
    _make_dialog(cwd, [MOD_A, *(f for f in own if cite_all or f not in targets)])
    _write_workflow(state_root, artifacts=[DIALOG], **wf)
    r = _gate(cwd, "phase8")
    if cite_all:
        assert r.returncode == 0, f"({scenario}) {r.stderr}"
        return
    assert r.returncode != 0, f"({scenario}) Phase 8 trotz nicht zitierter {targets}: {r.stdout}"
    for f in targets:
        assert f in r.stderr, f"({scenario}) {f} fehlt in der Meldung: {r.stderr}"
    for f in absent:
        assert f not in r.stderr, f"({scenario}) {f} gehört nicht zur Änderung: {r.stderr}"
    assert note is None or note in r.stderr, f"({scenario}) Hinweis '{note}' fehlt: {r.stderr}"


NO_REPO_MSG = "not a git repository (or any of the parent directories): .git"  # F102: gefälscht
AC8_FAILURES = [pytest.param("diff", "simulierter diff-Fehler (Test-Wrapper #259)", "diff",
                             id="diff-fails"),
                pytest.param("*", "simulierter Totalausfall (Test-Wrapper #259)", "rev-parse",
                             id="all-fail"),  # F102
                pytest.param("*", NO_REPO_MSG, "rev-parse", id="forged-no-repo")]  # F102


@pytest.mark.parametrize("fail,msg,failed", AC8_FAILURES)
@pytest.mark.parametrize("gate", ["commit", "phase8"])
def test_ac8_git_failure_in_valid_worktree_blocks(tmp_path, gate, fail, msg, failed):
    proj = _staged_b(tmp_path, **COVERED)
    env = _failing_git_env(tmp_path, proj, fail, msg)
    probe = [subprocess.run(["git", *c], cwd=proj, env=env, capture_output=True).returncode
             for c in (["diff"], ["rev-parse", "HEAD"])]
    assert probe[0] != 0 and (probe[1] != 0) == (fail == "*"), f"Wrapper wirkt anders: {probe}"
    r = _gate(proj, gate, env)
    assert _blocked(r, gate), f"gescheiterter git-Aufruf ignoriert (rc={r.returncode}): {r.stderr}"
    assert GIT_ERROR in r.stderr and failed in r.stderr, r.stderr


@pytest.mark.parametrize("layout,is_repo", [
    ("dot-git-dir", True), ("worktree-file", True), ("relative-gitdir", True), ("git-dir-env", True),
    ("nothing", False), ("empty-dot-git", False), ("dangling-gitdir", False)])
def test_ac8_repo_marker_decides_not_git_output(tmp_path, monkeypatch, layout, is_repo):
    """F102: scheitert JEDER git-Aufruf (Meldung gefälscht), entscheidet der Dateisystem-Befund
    oberhalb von `root`: gültiger Marker (.git/HEAD, `gitdir:`-Datei, GIT_DIR) → ChangeSetError,
    sonst None."""
    import adversary_dialog as ad
    root, store = tmp_path / "root", tmp_path / "store" / "gitdir"
    (root / "pkg").mkdir(parents=True)
    _write(store, "HEAD", "ref: refs/heads/main\n")
    dot = root / ".git"
    if layout == "dot-git-dir":
        _write(dot, "HEAD", "ref: refs/heads/main\n")
    elif layout == "empty-dot-git":
        dot.mkdir()
    elif layout != "nothing" and layout != "git-dir-env":
        target = {"worktree-file": store, "relative-gitdir": "../store/gitdir",
                  "dangling-gitdir": tmp_path / "missing"}[layout]
        dot.write_text(f"gitdir: {target}\n")
    monkeypatch.setenv("PATH", _failing_git_env(tmp_path, root, "*", NO_REPO_MSG)["PATH"])
    monkeypatch.delenv("GIT_DIR", raising=False)
    if layout == "git-dir-env":
        monkeypatch.setenv("GIT_DIR", str(store))
    if is_repo:
        with pytest.raises(ad.ChangeSetError, match="nicht ermittelbar.*rev-parse"):
            ad.git_toplevel(root / "pkg")
    else:
        assert ad.git_toplevel(root / "pkg") is None


@pytest.mark.parametrize("dot_git", [False, True], ids=["no-repo", "empty-dot-git"])
@pytest.mark.parametrize("gate", ["commit", "phase8"])
def test_ac8_without_git_worktree_coverage_is_skipped(tmp_path, gate, dot_git):
    """Wächter (heute grün); rote Gegenprobe: ..._git_failure_in_valid_worktree_blocks."""
    proj, env = _plain_project(tmp_path, dot_git)
    r = _gate(proj, gate, env)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("gate", ["commit", "phase8"])
@pytest.mark.parametrize("kind", ["absolute", "symlink"])
def test_ac9_artifact_outside_project_is_rejected(tmp_path, kind, gate):
    proj = _make_repo(tmp_path)
    _new(proj, MOD_B, stage=True)
    outside = _make_dialog(proj, [MOD_A, MOD_B], rel=str(tmp_path / "outside" / "dialog.md"))
    registered = str(outside)
    if kind == "symlink":
        (proj / DIALOG).parent.mkdir(parents=True)
        (proj / DIALOG).symlink_to(outside)
        registered = DIALOG
    _write_workflow(proj, base_commit=_sha(proj))
    _run("workflow.py", ["add-artifact", "adversary_dialog", registered, "Dialog",
                         "phase6b_adversary"], proj, check=True)  # keine Frühwarnung hier
    r = _gate(proj, gate)
    assert _blocked(r, gate), f"Artefakt außerhalb akzeptiert ({kind}): {r.stderr}"
    assert OUTSIDE_RE.search(r.stderr), r.stderr


@pytest.mark.parametrize("gate", ["commit", "phase8"])
def test_ac9_artifact_inside_worktree_is_accepted(tmp_path, gate):
    """Wächter (heute grün; Worktree liegt außerhalb des Hauptrepos). Gegenprobe: …_rejected."""
    main, wt = _make_worktree(tmp_path)
    _new(wt, MOD_B, stage=True)
    art = _make_dialog(wt, [MOD_A, MOD_B])
    _write_workflow(main, base_commit=_sha(wt))
    _run("workflow.py", ["add-artifact", "adversary_dialog", str(art), "Dialog",
                         "phase6b_adversary"], wt, check=True)
    r = _gate(wt, gate)
    assert r.returncode == 0, r.stderr


@pytest.fixture
def inproc(tmp_path, monkeypatch):
    """In-process: cwd und CLAUDE_PROJECT_DIR im tmp-Projekt, Sitzungs-Variablen entfernt."""
    proj = _make_repo(tmp_path)
    for key in _SCRUBBED:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.chdir(proj)
    return proj


def _patch_message(monkeypatch, message: str, *modules) -> None:
    """validate_dialog_artifact_ex meldet `message`; Gültigkeit und Fehlerart bleiben echt."""
    import adversary_dialog
    original = adversary_dialog.validate_dialog_artifact_ex

    def fake(path):
        valid, _msg, kind = original(path)
        return valid, message, kind

    for module in (adversary_dialog, *modules):
        monkeypatch.setattr(module, "validate_dialog_artifact_ex", fake, raising=False)


AC10 = [pytest.param("AMBIGUOUS", "Dialog valid: 1 Punkte bewiesen, 2 Runden.", "AMBIGUOUS",
                     id="ambiguous-artifact-plain-message"),
        pytest.param("VERIFIED", "Dialog valid (AMBIGUOUS erwähnt): 1 Punkte, 2 Runden.",
                     "VERIFIED", id="verified-artifact-ambiguous-word")]


@pytest.mark.parametrize("art_verdict,message,parsed", AC10)
def test_ac10_check_dialog_evidence_uses_parsed_verdict(inproc, monkeypatch, art_verdict,
                                                        message, parsed):
    import adversary_dialog
    _make_dialog(inproc, [MOD_A], verdict=art_verdict)
    _patch_message(monkeypatch, message)
    reason = adversary_dialog.check_dialog_evidence({"name": WF, "adversary_verdict": VERIFIED,
                                                     "test_artifacts": [{"type": "adversary_dialog",
                                                                         "path": DIALOG}]})
    if parsed == "AMBIGUOUS":
        assert reason is not None and "Widerspruch" in reason, f"AMBIGUOUS übersehen: {reason!r}"
    else:
        assert reason is None, f"Wort im Meldungstext statt Verdict entschied: {reason!r}"


@pytest.mark.parametrize("art_verdict,message,parsed", AC10)
def test_ac10_qa_gate_checklist_uses_parsed_verdict(inproc, monkeypatch, art_verdict, message,
                                                    parsed):
    """In-process statt Subprozess: der Checklist-Zweig lässt sich nur über eine veränderte
    Meldung von validate_dialog_artifact_ex prüfen, und ein Monkeypatch wirkt nur im selben
    Prozess. Persistenz (_set_verdict) und Statusabfrage (subprocess) sind abgefangen — der
    Test startet keinen Subprozess, der echten Workflow-State treffen könnte (#265)."""
    import qa_gate
    art = _make_dialog(inproc, [MOD_A], verdict=art_verdict)
    out = _write(inproc, f"docs/artifacts/{WF}/test-green-output.txt", GREEN_OUTPUT)
    _patch_message(monkeypatch, message, qa_gate)
    persisted = []
    monkeypatch.setattr(qa_gate, "_set_verdict", persisted.append)
    monkeypatch.setattr(qa_gate, "subprocess", types.SimpleNamespace(
        run=lambda *a, **k: subprocess.CompletedProcess(a[0], 0, f"Workflow: {WF}\n", "")))
    monkeypatch.setattr(sys, "argv", ["qa_gate.py", str(out), "--checklist", str(art)])
    with pytest.raises(SystemExit) as exc:
        qa_gate.main()
    assert exc.value.code == 0 and len(persisted) == 1, persisted
    assert persisted[0].startswith(f"{parsed}:"), persisted


@pytest.mark.parametrize("text,expected", [
    pytest.param("VERDICT: VERIFIED\n", "VERIFIED", id="line-form"),
    pytest.param("VERDICT: HOLDS\n", "VERIFIED", id="holds-synonym"),
    pytest.param("## Verdict\n**AMBIGUOUS**\n", "AMBIGUOUS", id="bold-form"),
    pytest.param("### VERDICT: BROKEN — F001 offen\n", "BROKEN", id="heading-form"),
    pytest.param("VERDICT: BROKEN\n\n### Runde 3\nVERDICT: VERIFIED\n", "VERIFIED", id="last-wins"),
    pytest.param("```\nVERDICT: VERIFIED\n```\nVERDICT: BROKEN\n", "BROKEN", id="fenced-ignored"),
    pytest.param("kein Urteil\n", None, id="no-verdict"),
    pytest.param(None, None, id="missing-file"),
])
def test_ac10_dialog_verdict_parses_structured_value(tmp_path, text, expected):
    from adversary_dialog import dialog_verdict
    art = tmp_path / "dialog.md"
    if text is not None:
        art.write_text("# Dialog\n\n" + text)
    assert dialog_verdict(str(art)) == expected


@pytest.mark.parametrize("generic_file", [True, False], ids=["generic-file", "no-file"])
@pytest.mark.parametrize("name", ["", None], ids=["empty-name", "missing-name"])
def test_ac11_no_default_path_without_workflow_name(inproc, name, generic_file):
    import adversary_dialog
    if generic_file:
        _make_dialog(inproc, [MOD_A], rel=GENERIC)
    wf = {"adversary_verdict": VERIFIED, "test_artifacts": []}
    wf.update({} if name is None else {"name": name})  # "" = leer, None = Feld fehlt
    reason = adversary_dialog.check_dialog_evidence(wf)
    assert reason is not None, f"{GENERIC} als Standardpfad akzeptiert"
    assert "<workflow>" not in reason, reason
    assert "Standardpfad" in reason and re.search(r"(?i)\bnamen?\b", reason), reason


@pytest.mark.parametrize("gate", ["commit", "phase8"])
def test_ac11_nameless_workflow_generic_file_blocks(tmp_path, gate):
    proj = _make_repo(tmp_path)
    _make_dialog(proj, [MOD_A], rel=GENERIC)
    _write_workflow(proj, name="")
    r = _gate(proj, gate)
    assert _blocked(r, gate), f"generischer Pfad öffnet das Gate (rc={r.returncode}): {r.stderr}"
    assert "Standardpfad" in r.stderr, r.stderr


@pytest.mark.parametrize("cfg,expected", [
    pytest.param(None, True, id="no-config"),
    pytest.param(CFG_OFF, False, id="enabled-false"),
    pytest.param("adversary_coverage_gate:\n  enabled: true\n", True, id="enabled-true"),
    pytest.param("adversary_coverage_gate:\n  enabeld: false\n", True, id="typo"),
    pytest.param("adversary_coverage_gate: [kaputt\n", True, id="broken-yaml"),
])
def test_ac12_coverage_gate_enabled_only_explicit_false(tmp_path, cfg, expected):
    proj = _make_repo(tmp_path)
    if cfg is not None:
        _write(proj, "config.yaml", cfg)
    r = _run(None, ["-c", "from adversary_dialog import coverage_gate_enabled as f; print(f())"],
             proj, _env(proj, PYTHONPATH=str(HOOKS_DIR)))
    assert r.returncode == 0 and r.stdout.strip() == str(expected), r.stdout + r.stderr


@pytest.mark.parametrize("case,expected_rc,text", [
    ("f001-commit", 0, None), ("f001-phase8", 0, None), ("partial-staging", 0, None),
    ("hash-253", 2, "Prüfling seit dem Dialog geändert"),
    ("f002-outside", 2, OUTSIDE_RE), ("f004-nameless", 2, "Standardpfad"),
], ids=["f001-commit", "f001-phase8", "partial-staging", "hash-253", "f002-outside", "f004-nameless"])
def test_ac12_kill_switch_only_covers_new_coverage(tmp_path, case, expected_rc, text):
    """Wächter (heute grün): f001-*, partial-staging, hash-253; rote Gegenprobe: f002, f004."""
    if case == "partial-staging":
        proj = _partial_repo(tmp_path)
    elif case.startswith(("f001", "hash")):
        proj = _staged_b(tmp_path)
    else:
        proj = _make_repo(tmp_path)
        rel = str(tmp_path / "outside" / "dialog.md") if case == "f002-outside" else GENERIC
        _make_dialog(proj, [MOD_A], rel=rel)
        _write_workflow(proj, **({"artifacts": [rel]} if case == "f002-outside" else {"name": ""}))
    _write(proj, "config.yaml", CFG_OFF)
    if case == "hash-253":
        _write(proj, MOD_A, "A = 2  # nach dem Dialog geändert\n")
    r = _gate(proj, "phase8" if case == "f001-phase8" else "commit")
    assert r.returncode == expected_rc, f"({case}) rc={r.returncode}: {r.stderr}"
    assert text is None or re.search(text, r.stderr), r.stderr


@pytest.mark.parametrize("block,relief", [
    ("coverage", "token"), ("partial", "token"), ("git-error", "token"),
    ("coverage", "feature-fast"),
    ("coverage", "phase5_tdd_red"), ("coverage", "phase8_complete"),
])
def test_ac13_commit_block_lifted_by_token_fast_track_or_phase(tmp_path, block, relief):
    """Erst die rote Gegenprobe (Block), dann hebt Token/Fast-Track/Phase ihn wieder auf."""
    env = None
    if block == "partial":
        proj = _partial_repo(tmp_path)
    elif block == "coverage":
        proj = _staged_b(tmp_path, phase="phase6_implement")
    else:
        proj = _staged_b(tmp_path, phase="phase6_implement", **COVERED)
        env = _failing_git_env(tmp_path, proj)
    before = _gate(proj, env=env)
    assert before.returncode == 2, f"({block}) kein Block für '{relief}': {before.stderr}"
    if relief == "token":
        _write_override_token(proj)
    else:
        key = "workflow_type" if relief == "feature-fast" else "current_phase"
        _write(proj, f".claude/workflows/{WF}.json", json.dumps({**_state(proj), key: relief}))
    after = _gate(proj, env=env)
    assert after.returncode == 0, f"({block}/{relief}) {after.stderr}"


def test_ac13_phase8_has_no_override_path(tmp_path):
    proj = _staged_b(tmp_path)
    _write_override_token(proj)
    r = _gate(proj, "phase8")
    assert r.returncode != 0 and MOD_B in r.stderr, f"Token öffnet Phase 8: {r.stdout}{r.stderr}"


def test_ac14_required_files_lists_exactly_the_phase8_set(tmp_path):
    proj, start = _rebased_repo(tmp_path)
    _write(proj, "docs/notes.md", "Nicht-Code\n")
    _write_workflow(proj, base_commit=start)
    r = _run("adversary_dialog.py", ["required-files"], proj)
    assert r.returncode == 0, f"required-files fehlt/scheitert: {r.stdout}{r.stderr}"
    listed = r.stdout.split()
    assert sorted(listed) == [MOD_B, MOD_C], r.stdout  # ohne Upstream-Datei, ohne Nicht-Code
    assert re.search(r"(?i)basis|base", r.stderr), f"Basis-Information fehlt auf stderr: {r.stderr}"
    _make_dialog(proj, listed)  # genau diese Liste zitiert → Phase 8 öffnet
    _write_workflow(proj, artifacts=[DIALOG], base_commit=start)
    p = _gate(proj, "phase8")
    assert p.returncode == 0, p.stderr


def test_ac14_required_files_reports_degraded_base_on_stderr(tmp_path):
    cwd, state_root, *_ = _scenario(tmp_path, "f-degraded")
    _write_workflow(state_root)
    r = _run("adversary_dialog.py", ["required-files"], cwd)
    assert r.returncode == 0 and r.stdout.split() == [MOD_B], f"{r.stdout}{r.stderr}"
    assert DEGRADED in r.stderr and DEGRADED not in r.stdout, r.stderr


def test_ac14_required_files_absolute_outside_hash_root(tmp_path):
    """Monorepo: CLAUDE_PROJECT_DIR zeigt auf einen Unterordner des Git-Toplevels."""
    mono = tmp_path / "mono"
    app = mono / "app"
    app.mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], mono)
    _write(mono, ".gitignore", ".claude/\n")
    start = _new(mono, "app/README.md", commit="init")
    _write(app, ".claude/active_workflow", WF)
    _new(app, MOD_B)
    shared = _write(mono, "lib/shared.py")
    _write_workflow(app, base_commit=start)
    r = _run("adversary_dialog.py", ["required-files"], app)
    assert r.returncode == 0, f"required-files fehlt/scheitert: {r.stdout}{r.stderr}"
    lines = {os.path.realpath(x) if os.path.isabs(x) else x for x in r.stdout.split()}
    assert lines == {MOD_B, os.path.realpath(shared)}, r.stdout


@pytest.mark.parametrize("case", ["no-repo", "no-workflow", "git-error", "git-total-failure"])
def test_ac14_required_files_exit_codes(tmp_path, case):
    if case == "no-repo":  # Exit 0, keine stdout-Zeilen, erklärender Hinweis auf stderr
        proj, env = _plain_project(tmp_path)
        r = _run("adversary_dialog.py", ["required-files"], proj, env)
        ok = r.returncode == 0 and not r.stdout.strip() and r.stderr.strip()
    elif case == "no-workflow":  # Exit 1
        proj = _make_repo(tmp_path)
        (proj / ".claude" / "active_workflow").unlink()
        r = _run("adversary_dialog.py", ["required-files"], proj)
        ok = r.returncode == 1 and re.search(r"(?i)workflow", r.stderr)
    else:  # Git-Fehler → Exit 1, der Befehl wird genannt (F102: auch bei Totalausfall)
        proj, total = _staged_b(tmp_path, **COVERED), case == "git-total-failure"
        env = _failing_git_env(tmp_path, proj, *(("*", NO_REPO_MSG) if total else ()))
        r = _run("adversary_dialog.py", ["required-files"], proj, env)
        failed = "rev-parse" if total else "diff"
        ok = r.returncode == 1 and not r.stdout.strip() and failed in r.stderr
    assert ok, f"({case}) rc={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r}"


PATH_TABLE = [  # (Pfad, strict_code_gate-Überschreibung, Code?)
    ("src/app.py", {}, True),  # Code-Endung
    ("lib/View.SWIFT", {}, True),  # Endung wird kleingeschrieben verglichen
    ("src/test/helper.py", {}, False),  # freigestellter Ordner als Pfad-Komponente
    ("src/latest/helper.py", {}, True),  # 'test' nur als Teilstring → keine Komponente
    ("docs/gen.py", {}, False),
    ("src/README_tools.py", {}, False),  # freigestelltes Muster
    ("src/changelog_writer.py", {}, False),  # Muster ohne Groß-/Kleinschreibung
    ("config/app.yaml", {}, False),
    ("src/style.css", {}, False),  # Nicht-Code-Endung
    ("db/schema.sql", {"code_extensions": [".sql"]}, True),  # Override erweitert …
    ("src/app.py", {"code_extensions": [".sql"]}, False),  # … und ersetzt die Liste
    ("legacy/old.py", {"always_allowed_dirs": ["legacy/"]}, False),
    ("tests/helper.py", {"always_allowed_dirs": ["legacy/"]}, True),  # Defaults ersetzt
    # #335: Testdatei-Namensmuster (Go/JS/TS) gelten zusaetzlich zur Projekt-Liste
    ("tests/test_x.py", {"always_allowed_dirs": ["legacy/"]}, True),
    ("src/app.test.ts", {"always_allowed_patterns": [r"\.md$"]}, False),
    ("pkg/notified_test.go", {}, False),
    ("pkg/test_helpers.go", {}, True),
    ("src/gen_api.py", {"always_allowed_patterns": [r"gen_\w+\.py$"]}, False),
]


def _edit_gate_says_code(tmp_path: Path, path: str, override: dict) -> bool:
    """Live-Orakel: ohne Workflow blockt edit_gate.py genau die Code-Dateien (Schritt 2/2b/3)."""
    proj = tmp_path / "eg"
    (proj / ".git").mkdir(parents=True)
    _write(proj, "config.yaml", json.dumps({"strict_code_gate": override}) if override else "{}\n")
    payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": path, "content": "x"}})
    r = _run("edit_gate.py", [], proj, stdin=payload)
    assert r.returncode == 0 or "No active workflow" in r.stderr, r.stderr
    return r.returncode == 2


@pytest.mark.parametrize("path,override,is_code", PATH_TABLE)
def test_ac15_is_gated_code_path_matches_edit_gate(tmp_path, path, override, is_code):
    assert _edit_gate_says_code(tmp_path, path, override) is is_code, "Tabelle ≠ edit_gate"
    from hook_utils import is_gated_code_path
    assert is_gated_code_path(path, config={"strict_code_gate": override}) is is_code


def test_ac15_edit_gate_constants_keep_names_and_values():
    """Regressionswächter (heute grün); rote Gegenprobe: ..._constants_have_single_source."""
    import edit_gate
    assert set(edit_gate.CODE_EXTENSIONS) == set(
        ".swift .kt .java .py .js .ts .tsx .jsx .go .rs .cpp .c .h .hpp .rb .php .cs".split())
    assert list(edit_gate.ALWAYS_ALLOWED_DIRS) == (
        "Tests/ UITests/ Test/ test/ __tests__/ tests/ spec/ docs/ .claude/commands/ scripts/ "
        "tools/").split()
    assert list(edit_gate.ALWAYS_ALLOWED_PATTERNS) == (
        r"\.md$ \.txt$ \.json$ \.yaml$ \.yml$ \.toml$ \.gitignore$ README CHANGELOG LICENSE"
    ).split()


def test_ac15_constants_have_single_source_in_hook_utils():
    import edit_gate
    import hook_utils
    for name in ("CODE_EXTENSIONS", "ALWAYS_ALLOWED_DIRS", "ALWAYS_ALLOWED_PATTERNS"):
        assert getattr(hook_utils, name, None) is getattr(edit_gate, name), (
            f"edit_gate.{name} stammt nicht aus hook_utils")


def _doc_section(rel: str, start, end) -> str:
    text = (REPO_ROOT / rel).read_text()
    m = re.search(rf"{start}(.*?)(?={end}|\Z)", text, re.M | re.S) if start else None
    assert m or not start, f"{rel}: Abschnitt {start!r} fehlt"
    return m.group(1) if m else text


@pytest.mark.parametrize("rel,start,end,patterns", [
    ("core/commands/50-implement.md", r"^#### 8c\.", r"^#{3,4} ", [r"required-files"]),
    ("core/agents/implementation-validator.md", r"^### Step 3\b", r"^#{2,3} ", [r"required-files"]),
    ("core/agents/implementation-validator.md", r"^## Step 6\b", r"^## ",
     [r"required-files|gelistet|listed"]),
    ("core/commands/60-validate.md", r"^\*\*Step 2b", r"^#{2,3} ",
     [r"BROKEN", r"phase6_implement|/50-implement|Phase 6"]),
    ("CLAUDE.md", r"^### Hooks\s*$", r"^#{2,3} ", [CHANGE_SET]),
    ("CLAUDE.md", r"^## Adversary-Limit", r"^## ", [r"#259|60-validate|(?i:auto-?fix)"]),
    ("docs/WORKFLOW_GUIDE.md", None, None, [CHANGE_SET]),
], ids=["50-implement-8c", "validator-step3", "validator-step6", "60-validate-2b",
        "claude-md-hooks", "claude-md-adversary-limit", "workflow-guide"])
def test_ac16_docs_describe_coverage_gate(rel, start, end, patterns):
    missing = [p for p in patterns if not re.search(p, _doc_section(rel, start, end))]
    assert not missing, f"{rel} [{start}]: {missing} fehlt"


def test_ac16_changelog_has_migration_note_for_259():
    sections = re.split(r"(?m)^## \[", (REPO_ROOT / "CHANGELOG.md").read_text())
    hits = [s for s in sections if "#259" in s and re.search(r"required-files|base_commit", s)
            and re.search(r"(?i)migration|laufende[nr]? workflows?", s)]
    assert hits, "CHANGELOG: kein #259-Eintrag mit Migrationshinweis (required-files/base_commit)"
