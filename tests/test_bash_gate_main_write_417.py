"""bash_gate: Worktree-Sitzung schreibt per Bash nicht in den Haupt-Ordner — #417.

Spec: docs/specs/fix-417-bash-main-write.md (AC-1 bis AC-16; AC-17 ist der Lauf
der bestehenden Regressionsdateien, hier keine eigene Testfunktion).
Echtes Gate als Subprozess (Helfer aus #410), Abweichungen je Funktion gesammelt.
`main` ist der Haupt-Ordner, `wt` der eigene Worktree (cwd).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bash_gate_state_integrity_410 import (  # noqa: E402
    BASH_GATE, OVERRIDE_HINT, _expect, _git, _override_token,
    _sandbox_ohne_workflow, _worktree_sandbox,
)

CFG = "openspec.yaml"


def _fail(ac: str, wrong) -> None:
    assert not wrong, f"{ac}: {len(wrong)} Abweichungen:\n" + "\n".join(wrong)


def _gate_env(command: str, project_dir: Path, cwd: Path, extra_env=None):
    env = dict(os.environ)
    env.pop("OPENSPEC_ACTIVE_WORKFLOW", None)
    env.pop("OPENSPEC_FRAMEWORK", None)
    env.update(extra_env or {})
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    env["CLAUDE_TOOL_INPUT"] = json.dumps({"command": command})
    return subprocess.run([sys.executable, str(BASH_GATE)], cwd=str(cwd), env=env,
                          capture_output=True, text=True, timeout=60)


def _expect_env(cases, project_dir: Path, cwd: Path, rc: int, extra_env=None,
                needle=None):
    wrong = []
    for cmd in cases:
        proc = _gate_env(cmd, project_dir, cwd, extra_env)
        if proc.returncode != rc or (needle and needle not in proc.stderr):
            wrong.append(f"  {cmd!r}: rc={proc.returncode} (soll {rc}), "
                         f"stderr={proc.stderr.strip()[:160]!r}")
    return wrong


def _wt(tmp_path: Path, name: str = "main"):
    main, wt = _worktree_sandbox(tmp_path / name, CFG)
    (main / "a.txt").write_text("a\n")
    (wt / "f").write_text("f\n")
    return main, wt


def _blocked(ac: str, cases, tmp_path: Path, name: str = "main"):
    _main, wt = _wt(tmp_path, name)
    _fail(ac, _expect(cases, wt, 2, OVERRIDE_HINT, cwd=wt))


def test_umleitung_in_hauptordner_blockt(tmp_path):
    """AC-1: > und >> in eine Haupt-Ordner-Datei -> Exit 2 mit 'override'."""
    main, wt = _wt(tmp_path)
    _fail("AC-1", _expect([
        f"echo x > {main}/a.txt", f"echo x >> {main}/a.txt",
        f"echo x > {main}/neu.txt",
    ], wt, 2, OVERRIDE_HINT, cwd=wt))


def test_cp_und_mv_in_hauptordner_blocken(tmp_path):
    """AC-2: cp/mv mit Ziel im Haupt-Ordner -> Exit 2."""
    main, wt = _wt(tmp_path)
    _fail("AC-2", _expect([
        f"cp f {main}/a.txt", f"mv f {main}/a.txt", f"cp -t {main} f",
    ], wt, 2, OVERRIDE_HINT, cwd=wt))


def test_sed_inplace_mit_relativem_pfad_blockt(tmp_path):
    """AC-3: sed -i ../../../a.txt loest auf den Haupt-Ordner auf."""
    _blocked("AC-3", ["sed -i s/a/b/ ../../../a.txt",
                      "sed -i '' s/a/b/ ../../../a.txt"], tmp_path)


def test_tee_in_hauptordner_blockt(tmp_path):
    """AC-4: cat f | tee <haupt>/a.txt -> Exit 2."""
    main, wt = _wt(tmp_path)
    _fail("AC-4", _expect([f"cat f | tee {main}/a.txt",
                           f"cat f | tee -a {main}/a.txt"],
                          wt, 2, OVERRIDE_HINT, cwd=wt))


def test_ziel_ueber_cd_basis_blockt(tmp_path):
    """AC-5: cd ../../.. && echo x > a.txt -> Ziel liegt ueber die cd-Basis im Haupt-Ordner."""
    _blocked("AC-5", ["cd ../../.. && echo x > a.txt",
                      "cd ../../..; sed -i s/a/b/ a.txt"], tmp_path)


def test_tilde_pfad_blockt(tmp_path):
    """AC-6: ~ loest (HOME=Haupt-Ordner) auf den Haupt-Ordner auf."""
    main, wt = _wt(tmp_path)
    _fail("AC-6", _expect_env(["echo x > ~/a.txt", "cp f ~/a.txt"], wt, wt, 2,
                              {"HOME": str(main)}, OVERRIDE_HINT))


def test_pfad_mit_leerzeichen_blockt(tmp_path):
    """AC-7: Haupt-Ordner mit Leerzeichen im Pfad (Regex [^/]+)."""
    main, wt = _wt(tmp_path, "mein haupt ordner")
    _fail("AC-7", _expect([f"echo x > '{main}/a.txt'", "sed -i s/a/b/ ../../../a.txt"],
                          wt, 2, OVERRIDE_HINT, cwd=wt))


def test_fremder_worktree_blockt(tmp_path):
    """AC-8: Ziel in einem fremden Worktree im selben Haupt-Ordner -> Exit 2."""
    main, wt = _wt(tmp_path)
    other = main / ".claude" / "worktrees" / "other"
    _git(main, "worktree", "add", "-q", "-b", "other", str(other))
    _fail("AC-8", _expect([f"echo x > {other}/a.txt", f"cp f {other}/f",
                           "echo x > ../other/a.txt"],
                          wt, 2, OVERRIDE_HINT, cwd=wt))


def test_eigener_worktree_bleibt_frei(tmp_path):
    """AC-9: Schreiben in den eigenen Worktree (relativ/absolut) -> Exit 0."""
    main, wt = _wt(tmp_path)
    _fail("AC-9", _expect([
        "echo x > neu.txt", f"echo x > {wt}/neu.txt", "cp f g",
        f"cp f {wt}/g", "sed -i s/a/b/ f", "cat f | tee h",
    ], wt, 0, cwd=wt))


def test_lesen_aus_hauptordner_bleibt_frei(tmp_path):
    """AC-10: Haupt-Ordner nur als Lese-Quelle -> Exit 0."""
    main, wt = _wt(tmp_path)
    _fail("AC-10", _expect([
        f"cat {main}/a.txt", f"cp {main}/a.txt ./", f"cat {main}/a.txt > kopie",
        f"grep a {main}/a.txt", "cat ../../../a.txt > kopie",
    ], wt, 0, cwd=wt))


def test_workflow_py_und_git_commit_bleiben_frei(tmp_path):
    """AC-11: workflow.py-Aufruf und git sind keine Schreibziele.

    `git commit` selbst bleibt aussen vor: das Commit-Gate (Adversary-Verdict)
    blockt im Sandbox-Workflow aus anderem Grund.
    """
    main, wt = _wt(tmp_path)
    _fail("AC-11", _expect([
        f"python3 {main}/.claude/hooks/workflow.py status",
        "git add f", "git log -1", "git status", "gh pr view",
    ], wt, 0, cwd=wt))


def test_hauptordner_sitzung_unveraendert(tmp_path):
    """AC-12: cwd im Haupt-Ordner selbst -> Schreiben bleibt frei."""
    root = _sandbox_ohne_workflow(tmp_path / "plain")
    _fail("AC-12", _expect(["echo x > a.txt", f"cp a.txt {root}/b.txt",
                            "sed -i s/a/b/ a.txt"], root, 0))
    main, _wt_dir = _wt(tmp_path, "mit_wt")
    _fail("AC-12 Haupt-Ordner mit Worktree", _expect(
        [f"echo x > {main}/a.txt"], main, 0, cwd=main))


def test_nicht_aufloesbares_ziel_ist_fail_open(tmp_path):
    """AC-13: $VAR im Ziel / offene Quote -> kein Absturz, Exit 0."""
    main, wt = _wt(tmp_path)
    _fail("AC-13", _expect([
        "echo x > $TARGET/a.txt", "cp f $DEST", "cd $X && echo x > a.txt",
        f"echo 'x > {main}/a.txt",
    ], wt, 0, cwd=wt))


def test_override_token_laesst_durch(tmp_path):
    """AC-14: ohne Token Exit 2 (Vorbedingung), mit Token Exit 0."""
    main, wt = _wt(tmp_path)
    cases = [f"echo x > {main}/a.txt", f"cp f {main}/a.txt"]
    _fail("AC-14 ohne Token (Vorbedingung)",
          _expect(cases, wt, 2, OVERRIDE_HINT, cwd=wt))
    _override_token(main)
    _fail("AC-14 mit Token", _expect(cases, wt, 0, cwd=wt))


def test_block_ohne_workflow_und_bei_framework_disabled(tmp_path):
    """AC-15: Schutz, kein Workflow-Zwang: auch ohne Workflow / bei OPENSPEC_FRAMEWORK=off."""
    main, wt = _wt(tmp_path)
    cmd = [f"echo x > {main}/a.txt"]
    _fail("AC-15 framework off", _expect_env(cmd, wt, wt, 2,
                                             {"OPENSPEC_FRAMEWORK": "off"},
                                             OVERRIDE_HINT))
    (wt / ".claude" / "active_workflow").unlink()
    _fail("AC-15 ohne Workflow", _expect(cmd, wt, 2, OVERRIDE_HINT, cwd=wt))


def test_config_sperre_410_bleibt_mit_eigener_meldung(tmp_path):
    """AC-16: Config im Haupt-Ordner -> weiterhin Block mit der Config-Meldung aus 1b."""
    _main, wt = _wt(tmp_path)
    _fail("AC-16", _expect([f"sed -i s/a/b/ ../../../{CFG}"], wt, 2,
                           "wirksame Gate-Config", cwd=wt))
