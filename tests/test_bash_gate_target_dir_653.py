"""bash_gate: Zielordner-Flag (-t / --target-directory) in allen Schreibweisen — #653.

Spec: docs/specs/fix-653-target-dir-flag.md (AC-1 bis AC-10; AC-11 ist der Lauf
der bestehenden Regressionsdateien, hier keine eigene Testfunktion).
Echtes Gate als Subprozess (Helfer aus #410/#417), Abweichungen je Funktion gesammelt.
`main` ist der Haupt-Ordner, `wt` der eigene Worktree (cwd), `wt/sub` ein
echter Unterordner im eigenen Worktree.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bash_gate_state_integrity_410 import (  # noqa: E402
    OVERRIDE_HINT, PLUGIN_CONFIG, _assert_blocked, _expect, _git,
    _override_token, _sandbox_ohne_workflow, _worktree_sandbox,
)

CFG = "openspec.yaml"
CONFIG_MSG = "wirksame Gate-Config"


def _fail(ac: str, wrong) -> None:
    assert not wrong, f"{ac}: {len(wrong)} Abweichungen:\n" + "\n".join(wrong)


def _wt(tmp_path: Path, name: str = "main"):
    """Haupt-Ordner + eigener Worktree mit Datei `f` und Unterordner `sub`."""
    main, wt = _worktree_sandbox(tmp_path / name, CFG)
    (main / "a.txt").write_text("a\n")
    (wt / "f").write_text("f\n")
    (wt / "sub").mkdir()
    # Aufbau-Sanity: exakte Form blockt schon heute; ein Aufbaufehler ist kein RED.
    _fail("Sanity (Aufbau 1c)",
          _expect([f"cp -t {main} f"], wt, 2, OVERRIDE_HINT, cwd=wt))
    return main, wt


def _main_blocked(ac: str, cases_for, tmp_path: Path) -> None:
    """Jede Form einmal mit absolutem und einmal mit relativem Haupt-Ordner."""
    main, wt = _wt(tmp_path)
    cases = cases_for(str(main)) + cases_for("../../..")
    _fail(ac, _expect(cases, wt, 2, OVERRIDE_HINT, cwd=wt))


def test_cp_varianten_in_hauptordner_blocken(tmp_path):
    """AC-1: cp --target-directory H x, --target-dir=H, -vt H -> Exit 2 + 'override'."""
    _main_blocked("AC-1", lambda h: [
        f"cp --target-directory {h} f",
        f"cp --target-dir={h} f",
        f"cp -vt {h} f",
    ], tmp_path)


def test_cp_angehaengter_wert_blockt(tmp_path):
    """AC-2: cp -tH x (Wert direkt angehaengt) -> Exit 2."""
    _main_blocked("AC-2", lambda h: [f"cp -t{h} f"], tmp_path)


def test_ln_varianten_in_hauptordner_blocken(tmp_path):
    """AC-3: ln -sft H x, ln --target-directory H x -> Exit 2."""
    _main_blocked("AC-3", lambda h: [
        f"ln -sft {h} f",
        f"ln --target-directory {h} f",
    ], tmp_path)


def test_install_varianten_in_hauptordner_blocken(tmp_path):
    """AC-4: install -Dt H x, install -m 644 --target-directory=H x -> Exit 2."""
    _main_blocked("AC-4", lambda h: [
        f"install -Dt {h} f",
        f"install -m 644 --target-directory={h} f",
    ], tmp_path)


def test_mv_varianten_in_hauptordner_blocken(tmp_path):
    """AC-5: mv -tH x, mv --target-dir=H x, mv -vt H x -> Exit 2."""
    _main_blocked("AC-5", lambda h: [
        f"mv -t{h} f",
        f"mv --target-dir={h} f",
        f"mv -vt {h} f",
    ], tmp_path)


def _cfg_root(tmp_path: Path) -> Path:
    """Sandbox ohne Workflow, wirksame Config im Stamm, Namensvetter in docs/."""
    root = _sandbox_ohne_workflow(tmp_path)
    (root / CFG).write_text(PLUGIN_CONFIG)
    (root / "docs").mkdir()
    (root / "docs" / CFG).write_text(PLUGIN_CONFIG)
    # Aufbau-Sanity: exakte Form blockt schon heute (418 AC-3).
    _assert_blocked([f"cp docs/{CFG} -t ."], root, "Sanity (Aufbau 1b)", CONFIG_MSG)
    return root


def test_config_als_ziel_ueber_alle_schreibweisen_blockt_1b(tmp_path):
    """AC-6: Zielordner D = Ordner der wirksamen Config, Quelle heisst openspec.yaml."""
    root = _cfg_root(tmp_path)
    src = f"docs/{CFG}"
    cases = []
    for d in (".", str(root)):
        cases += [
            f"cp --target-directory {d} {src}",
            f"cp --target-dir={d} {src}",
            f"cp -vt {d} {src}",
            f"cp -t{d} {src}",
            f"ln -sft {d} {src}",
            f"install -Dt {d} {src}",
            f"install -m 644 --target-directory={d} {src}",
            f"mv -vt {d} {src}",
        ]
    _fail("AC-6", _expect(cases, root, 2, CONFIG_MSG))


def test_zielordner_im_eigenen_worktree_bleibt_frei(tmp_path):
    """AC-7: dieselben Formen mit Zielordner im eigenen Worktree -> Exit 0."""
    _main, wt = _wt(tmp_path)
    cases = []
    for d in ("sub", str(wt / "sub")):
        cases += [
            f"cp --target-directory {d} f", f"cp --target-dir={d} f",
            f"cp -vt {d} f", f"cp -t{d} f",
            f"ln -sft {d} f", f"ln --target-directory {d} f",
            f"install -Dt {d} f", f"install -m 644 --target-directory={d} f",
            f"mv -t{d} f", f"mv --target-dir={d} f", f"mv -vt {d} f",
        ]
    _fail("AC-7", _expect(cases, wt, 0, cwd=wt))


def test_wert_von_S_suffix_und_m_ist_kein_zielordner(tmp_path):
    """AC-8: Werte von -S/--suffix/-m sehen wie Haupt-Ordner-Pfade aus, Ziel ist y."""
    main, wt = _wt(tmp_path)
    _fail("AC-8", _expect([
        "cp -S .t f y", "cp --suffix .t f y", "install -m 644 f y",
        f"cp -S {main} f y", f"cp --suffix {main} f y",
        f"cp --suffix={main} f y", f"install -m {main} f y",
        "cp -S ../../.. f y", "install -m ../../.. f sub/y",
    ], wt, 0, cwd=wt))


def test_permutation_doppelstrich_und_mehrere_zielordner(tmp_path):
    """AC-9: Flag hinter den Quellen, `--`, zwei Zielordner -> Exit 2."""
    main, wt = _wt(tmp_path)
    _fail("AC-9", _expect([
        f"cp f -t {main}", f"cp -t {main} -- f",
        f"cp -t sub -t {main} f",
        f"cp f -vt {main}", f"cp f --target-dir={main}",
        f"cp -vt {main} -- f", f"cp --target-dir=sub -t{main} f",
        f"mv f -vt {main}",
    ], wt, 2, OVERRIDE_HINT, cwd=wt))


def test_fremder_worktree_override_und_fail_open_unveraendert(tmp_path):
    """AC-10: fremder Worktree gesperrt; Haupt-Ordner-Sitzung, Override, Fail-open frei."""
    main, wt = _wt(tmp_path)
    other = main / ".claude" / "worktrees" / "other"
    _git(main, "worktree", "add", "-q", "-b", "other", str(other))
    wrong = _expect([f"cp -t {other} f", f"cp --target-directory={other} f",
                     "cp -t ../other f"], wt, 2, OVERRIDE_HINT, cwd=wt)

    # Fail-open: Variable, Glob, offene Quote, Backtick -> Exit 0.
    wrong += _expect([
        "cp -vt $X f", "cp --target-dir=$DEST f", "cp -t $X f",
        f"cp -t {main}/* f", f"cp -t '{main} f", "cp -t `pwd` f",
    ], wt, 0, cwd=wt)

    # Sitzung im Haupt-Ordner selbst: Zielordner-Flag in den Haupt-Ordner frei.
    (main / "d").mkdir()
    (main / "d" / "x").write_text("x\n")
    wrong += _expect([f"cp -t {main} d/x", f"cp -vt {main} d/x",
                      f"cp --target-dir={main} d/x"], main, 0, cwd=main)

    # Override: Vorbedingung ohne Token Exit 2, mit Token Exit 0.
    wrong += _expect([f"cp -t {main} f"], wt, 2, OVERRIDE_HINT, cwd=wt)
    _override_token(main)
    wrong += _expect([f"cp -t {main} f", f"cp -vt {main} f",
                      f"mv --target-dir={main} f"], wt, 0, cwd=wt)
    _fail("AC-10", wrong)
