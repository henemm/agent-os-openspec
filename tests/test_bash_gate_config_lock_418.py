"""bash_gate: Config-Sperre trifft nur Schreibziele, Langformen und cd — #418.

Spec: docs/specs/fix-418-config-lock-precision.md (AC-1 bis AC-8; AC-9 ist der
Lauf der bestehenden Regressionsdateien, hier keine eigene Testfunktion).
Echtes Gate als Subprozess (Helfer aus #410), Abweichungen je Funktion gesammelt.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bash_gate_state_integrity_410 import (  # noqa: E402
    OVERRIDE_HINT, PLUGIN_CONFIG, SANITY_STATE, _assert_allowed,
    _assert_blocked, _expect, _override_token, _sandbox, _sandbox_ohne_workflow,
    _worktree_sandbox,
)

CFG = "openspec.yaml"
SANITY_CONFIG = f"echo x > {CFG}"


def _root(tmp_path: Path) -> Path:
    """Sandbox ohne Workflow, Config im Stamm, docs/ (mit Namensvetter), backup/."""
    root = _sandbox_ohne_workflow(tmp_path)
    (root / CFG).write_text(PLUGIN_CONFIG)
    (root / "docs").mkdir()
    (root / "docs" / CFG).write_text(PLUGIN_CONFIG)
    (root / "backup").mkdir()
    (root / "x").write_text("x\n")
    # Aufbau-Sanity: bricht sofort ab, ein Aufbaufehler ist kein RED.
    _assert_blocked([SANITY_CONFIG], root, "Sanity (Aufbau)", OVERRIDE_HINT)
    return root


def _fail(ac: str, wrong) -> None:
    assert not wrong, f"{ac}: {len(wrong)} Abweichungen:\n" + "\n".join(wrong)


def test_teil_a_lesende_befehle_bleiben_frei(tmp_path):
    """AC-1: Config nur Lese-Quelle -> Exit 0."""
    _fail("AC-1", _expect([
        f"git diff {CFG} > x.patch",
        f"grep a {CFG} > out.txt",
        f"cat {CFG} > copy",
        f"cp {CFG} backup.yaml",
        f"cp -t backup/ {CFG}",
        f"cat {CFG} | tee copy",
    ], _root(tmp_path), 0))


def test_teil_b_inplace_langformen_blocken(tmp_path):
    """AC-2: In-Place-Langformen -> Exit 2 mit 'override'."""
    _fail("AC-2", _expect([
        f"sed --in-place s/a/b/ {CFG}",
        f"sed -ni 's/a/b/p' {CFG}",
        f"sed -i '' s/a/b/ {CFG}",
        f"perl -pi -e 's/a/b/' {CFG}",
        f"perl -i.bak -pe 's/a/b/' {CFG}",
    ], _root(tmp_path), 2, OVERRIDE_HINT))


def test_teil_b_umleitung_git_und_kopierformen_blocken(tmp_path):
    """AC-3: weitere Schreibformen -> Exit 2."""
    _fail("AC-3", _expect([
        f"echo x >| {CFG}",
        f"echo x &> {CFG}",
        f"git checkout -- {CFG}",
        f"git restore {CFG}",
        f"ln -sf x {CFG}",
        f"install x {CFG}",
        f"dd if=x of={CFG}",
        f"yq -i .a=1 {CFG}",
        f"cp docs/{CFG} -t .",  # Ziel ./openspec.yaml = wirksame Config
    ], _root(tmp_path), 2, OVERRIDE_HINT))


def test_teil_c_cd_im_befehl_blockt(tmp_path):
    """AC-4: cd im Befehl wird nachgefuehrt, auch im Worktree."""
    wrong = _expect([
        f"cd docs && sed -i s/a/b/ ../{CFG}",
        f"cd docs; echo x > ../{CFG}",
        f"cd docs && popd && sed -i s/a/b/ {CFG}",
    ], _root(tmp_path / "root"), 2, OVERRIDE_HINT)
    _main, wt = _worktree_sandbox(tmp_path / "wtmain", CFG)
    wrong += _expect([f"cd ../../.. && sed -i s/a/b/ {CFG}"], wt, 2,
                     OVERRIDE_HINT, cwd=wt)
    _fail("AC-4", wrong)


def test_teil_c_spiegelbild_bleibt_frei(tmp_path):
    """AC-5: cd docs && sed -i ... openspec.yaml trifft docs/openspec.yaml."""
    _fail("AC-5", _expect([f"cd docs && sed -i s/a/b/ {CFG}"],
                          _root(tmp_path), 0))


def test_gegenprobe_echte_schreibzugriffe_blocken_weiter(tmp_path):
    """AC-6: bestehende Treffer bleiben (darf vor der Umsetzung gruen sein)."""
    _fail("AC-6", _expect([
        f"echo x > {CFG}", f"echo x >> {CFG}", f"sed -i s/a/b/ {CFG}",
        f"sed -i.bak s/a/b/ {CFG}", f"cp x {CFG}", f"mv x {CFG}",
        f"mv {CFG} old", f"cat x | tee {CFG}", f"truncate -s0 {CFG}",
        f"rm {CFG}", f"git rm {CFG}", f"git mv {CFG} x",
    ], _root(tmp_path), 2, OVERRIDE_HINT))


def test_worktree_kopie_frei_und_override_gibt_config_frei(tmp_path):
    """AC-7: Worktree-Kopie frei; Token hebt die Sperre (Vorbedingung ohne Token)."""
    _main, wt = _worktree_sandbox(tmp_path / "wtmain", CFG)
    _assert_allowed([f"sed -i s/a/b/ {CFG}"], wt, "AC-7 Worktree-Kopie", cwd=wt)

    root = _sandbox(tmp_path / "ovr")
    (root / CFG).write_text(PLUGIN_CONFIG)
    writes = [f"echo x > {CFG}", f"sed -i s/a/b/ {CFG}", f"rm {CFG}"]
    _assert_blocked(writes, root, "AC-7 ohne Token (Vorbedingung)", OVERRIDE_HINT)
    _override_token(root)
    _assert_allowed(writes, root, "AC-7 mit Token")
    _assert_blocked([SANITY_STATE], root, "AC-7 State trotz Token")


def test_fail_open_und_dokumentierte_grenzen(tmp_path):
    """AC-8: kein Absturz, heutiges Verhalten bleibt; Known Limitations Exit 0.

    Ist-Werte gegen das Gate vor #418 ermittelt (Stand 65a953d):
    - offene Quote: Exit 0 (nicht zerlegbar -> fail-open)
    - `cd $X && sed -i ...`: Exit 2 (heute gegen cwd aufgeloest; die Spec
      verlangt Pruefung gegen alte Basis UND cwd, also bleibt es bei 2)
    """
    root = _root(tmp_path)
    wrong = _expect([f"sed -i 's/a/b/ {CFG}"], root, 0)
    wrong += _expect([f"cd $X && sed -i s/a/b/ {CFG}"], root, 2, OVERRIDE_HINT)
    wrong += _expect([f"ex -s {CFG}", f"patch {CFG} x.diff", "git apply x.diff"],
                     root, 0)
    _fail("AC-8", wrong)
