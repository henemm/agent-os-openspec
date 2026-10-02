"""bash_gate: Erkennungsluecken schliessen — Teil A von #299 (#296, #298, #304, #284).

Spec: docs/specs/fix-299-bash-gate-erkennung.md (AC-1 bis AC-20).

Alle Wirkungstests rufen `core/hooks/bash_gate.py` DIESES Arbeitsbaums als
echten Subprozess auf (Hook-JSON per Env, wie tests/test_git_invocation_detection.py),
gegen eine Wegwerf-Sandbox in tmp_path. Keine Mocks der Erkennung.

Beide Fehlerrichtungen:
  * Unter-Blockieren: Commit-Schreibweisen bzw. Schreibzugriffe auf den
    Workflow-State, die heute durchrutschen (Exit 0), muessen blocken (Exit 2).
  * Ueber-Blockieren: harmlose Befehle bleiben erlaubt (Exit 0).

#284 (AC-17 bis AC-19) laeuft gegen ein echtes Origin-Repo (bare) samt Klon mit
Rueckstand und vorgemerkter Datei; der in der Gate-Meldung genannte Befehl wird
wirklich ausgefuehrt.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
BASH_GATE = HOOKS_DIR / "bash_gate.py"
sys.path.insert(0, str(HOOKS_DIR))

import hook_utils  # noqa: E402

WF = "sandboxwf"
WF_PATH = f".claude/workflows/{WF}.json"


# --------------------------------------------------------------------- #
# Sandbox + Gate-Aufruf
# --------------------------------------------------------------------- #

def _write_workflow(root: Path, workflow_type: str = "feature", phase: str = "phase6_implement") -> None:
    claude = root / ".claude"
    (claude / "workflows").mkdir(parents=True, exist_ok=True)
    (claude / "active_workflow").write_text(WF + "\n")
    (claude / "workflows" / f"{WF}.json").write_text(json.dumps({
        "name": WF,
        "current_phase": phase,
        "workflow_type": workflow_type,
    }))


def _sandbox(tmp_path: Path, workflow_type: str = "feature") -> Path:
    """Projekt-Sandbox mit aktivem Workflow in phase6_implement ohne Verdict."""
    (tmp_path / ".git").mkdir()  # kein Worktree -> Haupt-Repo-Aufloesung
    _write_workflow(tmp_path, workflow_type=workflow_type)
    return tmp_path


def _sandbox_ohne_workflow(tmp_path: Path) -> Path:
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    return tmp_path


def _gate(command: str, project_dir: Path, cwd: "Path | None" = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for var in ("OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK"):
        env.pop(var, None)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    env["CLAUDE_TOOL_INPUT"] = json.dumps({"command": command})
    return subprocess.run(
        [sys.executable, str(BASH_GATE)],
        cwd=str(cwd or project_dir), env=env, capture_output=True, text=True, timeout=60,
    )


def _expect(cases, project_dir: Path, rc: int, needle: "str | None" = None):
    """Alle Faelle pruefen, Abweichungen SAMMELN (nicht beim ersten abbrechen)."""
    wrong = []
    for cmd in cases:
        proc = _gate(cmd, project_dir)
        if proc.returncode != rc or (needle and needle not in proc.stderr):
            wrong.append(f"  {cmd!r}: rc={proc.returncode} (soll {rc}), "
                         f"stderr={proc.stderr.strip()[:160]!r}")
    return wrong


def _assert_blocked_as_commit(cases, tmp_path: Path, issue: str):
    wrong = _expect(cases, _sandbox(tmp_path), 2, "Adversary verdict")
    assert not wrong, (
        f"{issue}: Commit-Schreibweise umgeht das Commit-Gate "
        f"({len(wrong)}/{len(cases)}):\n" + "\n".join(wrong)
    )


def _assert_allowed(cases, project_dir: Path, issue: str):
    wrong = _expect(cases, project_dir, 0)
    assert not wrong, (
        f"{issue}: harmloser Befehl wird ueber-blockiert "
        f"({len(wrong)}/{len(cases)}):\n" + "\n".join(wrong)
    )


# --------------------------------------------------------------------- #
# AC-1 Kontrolle
# --------------------------------------------------------------------- #

def test_kontrolle_normale_commit_formen_bleiben_blockiert(tmp_path):
    """AC-1: die bisher schon erkannten Formen bleiben blockiert."""
    _assert_blocked_as_commit(
        ["git commit -m x", "git -C . commit -m x", 'bash -c "git commit -m x"'],
        tmp_path, "AC-1 Kontrolle",
    )


# --------------------------------------------------------------------- #
# AC-2 bis AC-7: Whitelist (#296 + Nebenbefund „irgendein Segment“)
# --------------------------------------------------------------------- #

def test_whitelist_commit_mit_geschuetztem_pfad_wird_blockiert(tmp_path):
    """AC-2 (#296): Whitelist-Treffer darf Schritt 5 nicht ueberspringen."""
    _assert_blocked_as_commit([f"git commit -m x -- {WF_PATH}"], tmp_path, "AC-2 #296")


def test_whitelist_add_geschuetzt_und_commit_wird_blockiert(tmp_path):
    """AC-3 (#296)."""
    _assert_blocked_as_commit(
        ["git add .claude/settings.json && git commit -m x"], tmp_path, "AC-3 #296",
    )


def _assert_state_write_blocked(command: str, tmp_path: Path, ac: str):
    sandbox = _sandbox(tmp_path)
    before = (sandbox / WF_PATH).read_text()
    proc = _gate(command, sandbox)
    assert proc.returncode == 2 and "Direct state file manipulation" in proc.stderr, (
        f"{ac}: Schreibzugriff auf den Workflow-State neben einem Whitelist-Befehl "
        f"wird durchgelassen: cmd={command!r} rc={proc.returncode} stderr={proc.stderr!r}"
    )
    assert (sandbox / WF_PATH).read_text() == before  # Gate fuehrt nichts aus


def test_whitelist_gilt_nicht_fuer_beliebiges_segment_status_sed(tmp_path):
    """AC-4: `git status` macht das `sed -i`-Segment nicht zur Whitelist."""
    _assert_state_write_blocked(f"git status && sed -i 's/a/b/' {WF_PATH}", tmp_path, "AC-4")


def test_whitelist_gilt_nicht_fuer_beliebiges_segment_add_sed(tmp_path):
    """AC-5."""
    _assert_state_write_blocked(f"git add x && sed -i 's/a/b/' {WF_PATH}", tmp_path, "AC-5")


def test_reine_whitelist_befehle_ohne_commit_bleiben_erlaubt(tmp_path):
    """AC-6: reine Whitelist-Befehle werden nicht ueber-blockiert."""
    _assert_allowed(
        ["python3 .claude/hooks/workflow.py status", "git status", "git add x",
         "git status && git add x"],
        _sandbox(tmp_path), "AC-6",
    )


def test_whitelist_mit_geschuetztem_pfad_ohne_schreibzugriff_bleibt_erlaubt(tmp_path):
    """AC-7: Nennen ohne Schreiben blockt nicht (3b nur bei Schreibzugriff)."""
    _assert_allowed(
        ["python3 .claude/hooks/workflow.py status", f"git add {WF_PATH}"],
        _sandbox(tmp_path), "AC-7",
    )


def test_geschuetzter_pfad_im_whitelist_segment_zaehlt_nicht_fuer_3b(tmp_path):
    """AC-21: geschuetzter Pfad nur im whitelisted Segment -> kein 3b-Block;
    nennt ein NICHT-whitelisted Segment den State -> Block."""
    sandbox = _sandbox(tmp_path)
    hooks = sandbox / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "workflow.py").write_text("# sandbox\n")
    _assert_allowed(
        ["python3 .claude/hooks/workflow.py status 2>&1 | tee out.log",
         "python3 .claude/hooks/workflow.py status > /tmp/s.txt && cat /tmp/s.txt"],
        sandbox, "AC-21 erlaubt",
    )
    wrong = _expect([f"python3 .claude/hooks/workflow.py status && echo x > {WF_PATH}"],
                    sandbox, 2, "Direct state file manipulation")
    assert not wrong, "AC-21: State-Schreibzugriff durchgelassen:\n" + "\n".join(wrong)


# --------------------------------------------------------------------- #
# AC-8 bis AC-10: verschachtelte Shells (#298)
# --------------------------------------------------------------------- #

def test_nested_shell_optionsbuendel_mit_c_wird_als_commit_erkannt(tmp_path):
    """AC-8 (#298)."""
    _assert_blocked_as_commit(
        ['bash -lc "git commit -m x"', 'sh -ec "git commit -m x"',
         'bash --login -c "git commit -m x"'],
        tmp_path, "AC-8 #298",
    )


def test_nested_shell_optionen_mit_wert_und_noprofile_werden_uebersprungen(tmp_path):
    """AC-9 (#298): Wert von -o/-O/--rcfile/--init-file ist kein Kommando."""
    _assert_blocked_as_commit(
        ['bash -o pipefail -c "git commit -m x"', 'bash -O extglob -c "git commit -m x"',
         'bash --rcfile f -c "git commit -m x"', 'bash --init-file f -c "git commit -m x"',
         'bash --noprofile --norc -c "git commit -m x"'],
        tmp_path, "AC-9 #298",
    )


def test_nested_shell_ohne_commit_im_inneren_bleibt_erlaubt(tmp_path):
    """AC-10: kein Commit im Inneren -> keine Ueber-Erkennung."""
    _assert_allowed(
        ['bash -c "git status"', 'bash -lc "echo hallo"', 'bash --login -c "ls"'],
        _sandbox(tmp_path), "AC-10",
    )


# --------------------------------------------------------------------- #
# AC-11 bis AC-15: Umleitungen und Vor-Optionen (#304)
# --------------------------------------------------------------------- #

def test_umleitung_vor_unterbefehl_wird_uebersprungen(tmp_path):
    """AC-11 (#304)."""
    _assert_blocked_as_commit(
        ["git >/dev/null commit -m x", "git >>log commit -m x",
         "git &>/dev/null commit -m x"],
        tmp_path, "AC-11 #304",
    )


def test_attr_source_option_mit_wert_wird_uebersprungen(tmp_path):
    """AC-12 (#304)."""
    _assert_blocked_as_commit(["git --attr-source HEAD commit -m x"], tmp_path, "AC-12 #304")


def test_und_umleitung_ist_kein_trenner_commit_erkannt(tmp_path):
    """AC-13: `2>&1` ist kein Befehlstrenner."""
    _assert_blocked_as_commit(["git 2>&1 commit -m x"], tmp_path, "AC-13")


def test_git_status_mit_umleitung_ist_rein_git_und_trenner_bleiben():
    """AC-14: Unit-Pruefung von hook_utils.is_pure_git_command."""
    soll = {
        "git status 2>&1": True,
        "git status &>/dev/null": True,
        "git log >> out.txt": True,
        "git status 2>&1 && touch x": False,
        "git status & touch x": False,
        "git status | cat": False,
        "git status && touch x": False,
    }
    wrong = [f"  is_pure_git_command({c!r}) = {hook_utils.is_pure_git_command(c)} (soll {s})"
             for c, s in soll.items() if hook_utils.is_pure_git_command(c) is not s]
    assert not wrong, "AC-14: Umleitung/Trenner falsch eingeordnet:\n" + "\n".join(wrong)


def test_umleitung_nach_unterbefehl_und_exec_path_ohne_wert(tmp_path):
    """AC-15: Umleitung hinter commit (Kontrolle) und `--exec-path` ohne Wert."""
    _assert_blocked_as_commit(
        ["git commit -m x 2>&1", "git --exec-path commit -m x"], tmp_path, "AC-15",
    )


# --------------------------------------------------------------------- #
# AC-16: kein Ueber-Blockieren, wenn alle Gates erfuellt sind
# --------------------------------------------------------------------- #

ERWEITERTE_COMMITS = [
    "git >/dev/null commit -m x",
    "git 2>&1 commit -m x",
    'bash -lc "git commit -m x"',
    "git --attr-source HEAD commit -m x",
]


def test_erweiterte_schreibweisen_mit_gueltigem_nachweis_nicht_ueberblockiert(tmp_path):
    """AC-16: ohne Workflow und mit Workflow ohne Verdict-Pflicht (bug) -> Exit 0."""
    ohne = tmp_path / "ohne_workflow"
    ohne.mkdir()
    _assert_allowed(ERWEITERTE_COMMITS, _sandbox_ohne_workflow(ohne), "AC-16 ohne Workflow")
    bug = tmp_path / "bug_workflow"
    bug.mkdir()
    _assert_allowed(ERWEITERTE_COMMITS, _sandbox(bug, workflow_type="bug"),
                    "AC-16 Workflow ohne Verdict-Pflicht")


# --------------------------------------------------------------------- #
# AC-17 bis AC-19: Rebase-Pflicht mit echtem Origin (#284)
# --------------------------------------------------------------------- #

def _git(args, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=60)
    if check:
        assert proc.returncode == 0, f"git {args} in {cwd}: {proc.stderr}"
    return proc


def _configure(repo: Path) -> None:
    _git(["config", "user.email", "test@example.invalid"], repo)
    _git(["config", "user.name", "Test"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)


def _origin_mit_klon(tmp_path: Path, rueckstand: bool = True) -> Path:
    """Bare-Origin, Klon mit vorgemerkter Datei; Origin optional einen Commit weiter."""
    origin = tmp_path / "origin.git"
    _git(["init", "--bare", "-b", "main", str(origin)], tmp_path)
    seed = tmp_path / "seed"
    _git(["clone", str(origin), str(seed)], tmp_path)
    _configure(seed)
    (seed / "a.txt").write_text("a\n")
    _git(["add", "a.txt"], seed)
    _git(["commit", "-m", "init"], seed)
    _git(["push", "origin", "HEAD:main"], seed)

    clone = tmp_path / "clone"
    _git(["clone", str(origin), str(clone)], tmp_path)
    _configure(clone)
    (clone / ".git" / "info" / "exclude").write_text(".claude/\n")
    _write_workflow(clone, workflow_type="bug")  # 5c laesst bug durch -> 5b isoliert
    (clone / "sub").mkdir()
    (clone / "sub" / "keep.txt").write_text("k\n")
    _git(["add", "sub/keep.txt"], clone)
    _git(["commit", "-m", "sub"], clone)
    _git(["push", "origin", "HEAD:main"], clone)

    if rueckstand:
        (seed / "b.txt").write_text("b\n")
        _git(["pull", "--ff-only", "origin", "main"], seed)
        _git(["add", "b.txt"], seed)
        _git(["commit", "-m", "upstream"], seed)
        _git(["push", "origin", "HEAD:main"], seed)

    (clone / "staged.txt").write_text("vorgemerkt\n")
    _git(["add", "staged.txt"], clone)
    return clone


def _staged(repo: Path) -> list:
    return _git(["diff", "--cached", "--name-only"], repo).stdout.split()


def _behind(repo: Path) -> int:
    return int(_git(["rev-list", "--count", "HEAD..origin/main"], repo).stdout.strip())


def test_rebase_pflicht_meldung_nennt_autostash(tmp_path):
    """AC-17 (#284)."""
    clone = _origin_mit_klon(tmp_path)
    proc = _gate("git commit -m x", clone)
    assert proc.returncode == 2 and "hinter origin/main" in proc.stderr, (
        f"Vorbedingung: 5b muss den Rueckstand blocken. rc={proc.returncode} "
        f"stderr={proc.stderr!r}"
    )
    assert "git rebase --autostash origin/main" in proc.stderr, (
        "AC-17 #284: Rebase-Rat scheitert bei vorgemerkten Dateien, `--autostash` "
        f"fehlt in der Meldung: {proc.stderr!r}"
    )


def test_autostash_rat_gelingt_bei_vorgemerkter_datei_und_erhaelt_vormerkung(tmp_path):
    """AC-18 (#284): den in der Meldung genannten Befehl wirklich ausfuehren."""
    clone = _origin_mit_klon(tmp_path)
    _git(["fetch", "origin"], clone)
    vorher = _staged(clone)
    assert vorher == ["staged.txt"]

    # Kontrolle gegen eine nur behauptete Wirkung: der alte Rat scheitert.
    alt = _git(["rebase", "origin/main"], clone, check=False)
    assert alt.returncode != 0 and "index contains uncommitted changes" in (alt.stderr + alt.stdout), (
        f"Kontrolle: `git rebase origin/main` haette scheitern muessen: {alt.stderr!r}"
    )
    assert _staged(clone) == vorher

    gate = _gate("git commit -m x", clone)
    assert gate.returncode == 2, gate.stderr
    m = re.search(r"git fetch origin && git rebase[^\n]*", gate.stderr)
    assert m, f"Meldung nennt keinen Rebase-Befehl: {gate.stderr!r}"
    rat = m.group(0).strip()
    assert "--autostash" in rat, f"AC-18 #284: genannter Rat ohne --autostash: {rat!r}"

    lauf = subprocess.run(["bash", "-c", rat], cwd=str(clone), capture_output=True,
                          text=True, timeout=60)
    assert lauf.returncode == 0, f"Rat {rat!r} scheitert: {lauf.stderr!r}"
    assert _behind(clone) == 0, "Branch steht nach dem Rat weiter hinter origin/main"
    assert _staged(clone) == vorher, f"Vormerkung verloren: {_staged(clone)} statt {vorher}"


def test_rebase_pflicht_misst_im_arbeitsbaum_und_blockiert_nicht_ohne_rueckstand(tmp_path):
    """AC-19: Aufruf aus Unterverzeichnis blockt weiter; ohne Rueckstand kein 5b-Block."""
    mit = tmp_path / "mit"
    mit.mkdir()
    clone = _origin_mit_klon(mit)
    proc = _gate("git commit -m x", clone, cwd=clone / "sub")
    assert proc.returncode == 2 and "hinter origin/main" in proc.stderr, (
        f"AC-19: Rueckstand aus Unterverzeichnis nicht erkannt: rc={proc.returncode} "
        f"stderr={proc.stderr!r}"
    )

    ohne = tmp_path / "ohne"
    ohne.mkdir()
    clone2 = _origin_mit_klon(ohne, rueckstand=False)
    for cwd in (clone2, clone2 / "sub"):
        proc = _gate("git commit -m x", clone2, cwd=cwd)
        assert proc.returncode == 0 and "hinter origin/main" not in proc.stderr, (
            f"AC-19: 5b blockt ohne Rueckstand (cwd={cwd}): rc={proc.returncode} "
            f"stderr={proc.stderr!r}"
        )


# --------------------------------------------------------------------- #
# AC-20: Regressionsschutz
# --------------------------------------------------------------------- #

REGRESSION = [
    "tests/test_git_invocation_detection.py",
    "tests/test_bash_gate_false_positives.py",
    "tests/test_bash_gate_freetext_fixes_64_75.py",
    "tests/test_bash_gate_worktree_commit_155.py",
]


def test_bestehende_bash_gate_und_git_erkennungs_tests_bleiben_gruen():
    """AC-20."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *REGRESSION],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, (
        "AC-20: Regression in bestehenden Tests:\n" + proc.stdout[-3000:] + proc.stderr[-1000:]
    )
