"""bash_gate 1c: Symlink im eigenen Worktree ist kein Haupt-Ordner-Schreibzugriff — #435.

Spec: docs/specs/fix-435-symlink-parent.md (AC-1 bis AC-13; AC-14 ist der Lauf
der bestehenden Regressionsdateien, hier keine eigene Testfunktion).
Echtes Gate als Subprozess (Helfer aus #410/#417), Abweichungen je Funktion gesammelt.
`main` ist der Haupt-Ordner, `wt` der eigene Worktree (cwd). Die Links liegen nur
im Dateisystem (nicht im Git-Baum):

- `wt/libs -> ../../../libs` (Ordner-Link in den Haupt-Ordner, steht fuer `node_modules`)
- `wt/datalink -> ../../../data.txt` (Datei-Link in den Haupt-Ordner)

Der Ordner-Link heisst bewusst NICHT `node_modules`: Pruefung 4c (#293,
`dependency_dir_guard`) blockt `rm|unlink|mv node_modules` namensbasiert und
unabhaengig von 1c; hier wird nur 1c geprueft.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bash_gate_state_integrity_410 import (  # noqa: E402
    OVERRIDE_HINT, _gate, _git, _override_token, _sandbox_ohne_workflow,
)
from test_bash_gate_main_write_417 import CFG, _expect, _fail, _wt  # noqa: E402

L = "libs"  # Ordner-Link; nicht in dependency_dir_guard.dirs (#293)
MAIN_MSG = "in den Haupt-Ordner (Worktree-Pflicht)"  # 1c-Meldung


def _link_sandbox(tmp_path: Path, name: str = "main"):
    """Haupt-Ordner mit `libs/a` und `data.txt`, Worktree mit echten Links."""
    main, wt = _wt(tmp_path, name)
    (main / L).mkdir()
    (main / L / "a").write_text("a\n")
    (main / "data.txt").write_text("d\n")
    rel_main = os.path.relpath(main, wt)  # ../../..
    os.symlink(os.path.join(rel_main, L), wt / L)
    os.symlink(os.path.join(rel_main, "data.txt"), wt / "datalink")
    (wt / "sub").mkdir()
    (wt / "x").write_text("x\n")
    assert (wt / L).is_symlink() and (wt / L / "a").is_file(), "Aufbau: Ordner-Link"
    assert (wt / "datalink").is_symlink() and (wt / "datalink").is_file(), \
        "Aufbau: Datei-Link"
    return main, wt


def _expect_1c(cases, wt: Path):
    """Exit 2 mit 1c-Meldung UND Hinweis auf 'override' (beide Nadeln)."""
    wrong = []
    for cmd in cases:
        proc = _gate(cmd, wt, wt)
        if (proc.returncode != 2 or MAIN_MSG not in proc.stderr
                or OVERRIDE_HINT not in proc.stderr):
            wrong.append(f"  {cmd!r}: rc={proc.returncode} (soll 2 + 1c-Meldung), "
                         f"stderr={proc.stderr.strip()[:160]!r}")
    return wrong


def _frei(ac: str, cases, tmp_path: Path):
    _main, wt = _link_sandbox(tmp_path)
    _fail(ac, _expect(cases, wt, 0, cwd=wt))


# --------------------------------------------------------------------- #
# Fehlalarm weg: Befehle, die den Link SELBST bearbeiten (AC-1 bis AC-5)
# --------------------------------------------------------------------- #

def test_rm_und_unlink_auf_link_bleiben_frei(tmp_path):
    """AC-1: rm / rm -f / rm -rf / unlink auf den Link -> Exit 0."""
    _frei("AC-1", [f"rm {L}", f"rm -f {L}", f"rm -rf {L}", f"unlink {L}",
                   "rm datalink", "unlink datalink"], tmp_path)


def test_mv_von_und_mit_T_auf_link_bleibt_frei(tmp_path):
    """AC-2: mv L L.bak (Quelle) und mv -T x L (Ziel ersetzt den Link) -> Exit 0."""
    _frei("AC-2", [f"mv {L} {L}.bak", f"mv -T x {L}",
                   f"mv --no-target-directory x {L}"], tmp_path)


def test_touch_h_und_ln_sfn_auf_link_bleiben_frei(tmp_path):
    """AC-3: touch -h L, ln -sfn <ziel> L, ln -sfT <ziel> L -> Exit 0."""
    _frei("AC-3", [f"touch -h {L}", f"touch --no-dereference {L}",
                   f"ln -sfn ../../../{L} {L}", f"ln -sfT ../../../{L} {L}"],
          tmp_path)


def test_git_rm_checkout_restore_auf_link_bleiben_frei(tmp_path):
    """AC-4: git rm L, git checkout -- L, git restore L -> Exit 0."""
    _frei("AC-4", [f"git rm {L}", f"git checkout -- {L}", f"git restore {L}"],
          tmp_path)


def test_freie_befehle_nach_cd_in_unterordner_bleiben_frei(tmp_path):
    """AC-5: dieselben freien Befehle nach `cd sub` mit relativem Pfad -> Exit 0."""
    _frei("AC-5", [
        f"cd sub && rm ../{L}", f"cd sub && rm -rf ../{L}", f"cd sub && unlink ../{L}",
        f"cd sub && mv ../{L} ../{L}.bak", f"cd sub && touch -h ../{L}",
        f"cd sub && ln -sfn ../../../../{L} ../{L}", f"cd sub && git rm ../{L}",
    ], tmp_path)


# --------------------------------------------------------------------- #
# Schreiben DURCH den Link blockt weiter (AC-6 bis AC-10)
# --------------------------------------------------------------------- #

def test_umleitung_durch_link_blockt(tmp_path):
    """AC-6: > L/a und > L (L zeigt auf Datei) -> Exit 2 mit 1c-Meldung + 'override'."""
    _main, wt = _link_sandbox(tmp_path)
    _fail("AC-6", _expect_1c([f"echo x > {L}/a", f"echo x >> {L}/a",
                              "echo x > datalink", "echo x >> datalink"], wt))


def test_folgende_befehle_durch_link_blocken(tmp_path):
    """AC-7: cp x L, mv x L, ln -sf x L, touch L, tee L/a -> Exit 2."""
    _main, wt = _link_sandbox(tmp_path)
    _fail("AC-7", _expect([
        f"cp x {L}", f"mv x {L}", f"ln -sf x {L}", f"touch {L}",
        f"cat x | tee {L}/a", "cp x datalink", "touch datalink",
    ], wt, 2, OVERRIDE_HINT, cwd=wt))


def test_schraegstrich_punkt_und_unterpfad_blocken(tmp_path):
    """AC-8: rm -r L/, rm -rf L/., rm L/a -> Exit 2."""
    _main, wt = _link_sandbox(tmp_path)
    _fail("AC-8", _expect([f"rm -r {L}/", f"rm -rf {L}/.", f"rm {L}/a",
                           f"rm -rf {L}/..", f"unlink {L}/a"],
                          wt, 2, OVERRIDE_HINT, cwd=wt))


def test_link_rolle_plus_umleitungsziel_blockt(tmp_path):
    """AC-9: dasselbe Token ist Link-Rolle und Umleitungsziel -> Exit 2."""
    _main, wt = _link_sandbox(tmp_path)
    _fail("AC-9", _expect([f"rm {L} > {L}", "rm datalink > datalink",
                           "unlink datalink >> datalink"],
                          wt, 2, OVERRIDE_HINT, cwd=wt))


def test_link_im_hauptordner_blockt_bei_rm(tmp_path):
    """AC-10: Link liegt selbst im Haupt-Ordner -> rm/unlink darauf -> Exit 2."""
    main, wt = _link_sandbox(tmp_path)
    os.symlink(L, main / "hostlink")
    assert (main / "hostlink").is_symlink(), "Aufbau: Link im Haupt-Ordner"
    _fail("AC-10", _expect([f"rm {main}/hostlink", "rm ../../../hostlink",
                            f"unlink {main}/hostlink", f"rm -f {main}/hostlink"],
                           wt, 2, OVERRIDE_HINT, cwd=wt))


# --------------------------------------------------------------------- #
# Unveraendertes Verhalten (AC-11 bis AC-13)
# --------------------------------------------------------------------- #

def test_fremder_worktree_und_hauptordner_sitzung_unveraendert(tmp_path):
    """AC-11: fremder Worktree bleibt gesperrt, Haupt-Ordner-Sitzung bleibt frei."""
    main, wt = _link_sandbox(tmp_path)
    other = main / ".claude" / "worktrees" / "other"
    _git(main, "worktree", "add", "-q", "-b", "other", str(other))
    os.symlink(os.path.join(os.path.relpath(main, other), L), other / L)
    _fail("AC-11 fremder Worktree", _expect([
        f"echo x > {other}/a.txt", f"cp x {other}/f", "echo x > ../other/a.txt",
        f"rm {other}/{L}", f"rm ../other/{L}", f"unlink {other}/{L}",
    ], wt, 2, OVERRIDE_HINT, cwd=wt))

    root = _sandbox_ohne_workflow(tmp_path / "plain")
    (root / "ziel").mkdir()
    os.symlink("ziel", root / L)
    _fail("AC-11 Haupt-Ordner ohne Worktree", _expect(
        [f"rm {L}", f"echo x > {L}/a", f"touch {L}"], root, 0))
    _fail("AC-11 Haupt-Ordner mit Worktree", _expect(
        [f"rm {wt}/{L}", f"echo x > {main}/{L}/a", f"echo x > {main}/a.txt"],
        main, 0, cwd=main))


def test_fail_open_und_override_wirken_wie_bisher(tmp_path):
    """AC-12: $VAR / Glob / offene Quote -> fail-open (0); Override laesst Blocks durch."""
    main, wt = _link_sandbox(tmp_path)
    _fail("AC-12 fail-open", _expect([
        "echo x > $X/a", f"cp x $DEST/{L}", "rm $L", f"cp x {L}/*",
        f"rm -r {L[:2]}*/", f"echo 'x > {L}/a",
    ], wt, 0, cwd=wt))
    cases = [f"echo x > {L}/a", f"cp x {L}", f"touch {L}", f"rm -r {L}/"]
    _fail("AC-12 ohne Token (Vorbedingung)",
          _expect(cases, wt, 2, OVERRIDE_HINT, cwd=wt))
    _override_token(main)
    _fail("AC-12 mit Token", _expect(cases, wt, 0, cwd=wt))


def test_config_sperre_1b_bleibt_unveraendert(tmp_path):
    """AC-13: wirksame Config im Haupt-Ordner -> Block 1b mit eigener Config-Meldung."""
    _main, wt = _link_sandbox(tmp_path)
    _fail("AC-13", _expect([f"sed -i s/a/b/ ../../../{CFG}",
                            f"echo x > ../../../{CFG}", f"rm ../../../{CFG}"],
                           wt, 2, "wirksame Gate-Config", cwd=wt))
