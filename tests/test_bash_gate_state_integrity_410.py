"""bash_gate: Restluecken in Pruefung 3b und Schutz der wirksamen Config — #410.

Spec: docs/specs/fix-410-state-integrity-gaps.md (AC-1 bis AC-13; AC-14 ist
der Lauf der bestehenden Regressionsdateien, hier keine eigene Testfunktion).

Muster wie #407 (tests/test_bash_gate_ln_state_407.py): `core/hooks/bash_gate.py`
DIESES Arbeitsbaums laeuft als echter Subprozess gegen eine Wegwerf-Sandbox in
tmp_path. Beide Fehlerrichtungen; Abweichungen werden je Test gesammelt statt
beim ersten Fehler abzubrechen.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASH_GATE = REPO_ROOT / "core" / "hooks" / "bash_gate.py"

WF = "sandboxwf"
STATE_MSG = "Direct state file manipulation"
OVERRIDE_HINT = "override"
SANITY_STATE = "cp docs/a.json .claude/workflows/b.json"
PLUGIN_CONFIG = "qa_gate:\n  enabled: true\n"  # Plugin-Block (#372)
APP_CONFIG = "port: 8080\nname: app\n"           # kein Plugin-Block


# --------------------------------------------------------------------- #
# Sandbox + Gate-Aufruf (Muster aus tests/test_bash_gate_ln_state_407.py)
# --------------------------------------------------------------------- #

def _workflow_json(claude: Path) -> None:
    (claude / "workflows").mkdir(parents=True, exist_ok=True)
    (claude / "workflows" / f"{WF}.json").write_text(json.dumps({
        "name": WF,
        "current_phase": "phase6_implement",
        "workflow_type": "feature",
    }))


def _sandbox(tmp_path: Path) -> Path:
    """Projekt-Sandbox mit aktivem Workflow in phase6_implement."""
    root = tmp_path.resolve()
    (root / ".git").mkdir(parents=True)  # kein Worktree -> Haupt-Repo-Aufloesung
    claude = root / ".claude"
    _workflow_json(claude)
    (claude / "active_workflow").write_text(WF + "\n")
    return root


def _sandbox_ohne_workflow(tmp_path: Path) -> Path:
    root = tmp_path.resolve()
    (root / ".claude").mkdir(parents=True)
    (root / ".git").mkdir(parents=True)
    return root


def _gate(command: str, project_dir: Path, cwd: "Path | None" = None):
    env = dict(os.environ)
    for var in ("OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK"):
        env.pop(var, None)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    env["CLAUDE_TOOL_INPUT"] = json.dumps({"command": command})
    return subprocess.run(
        [sys.executable, str(BASH_GATE)],
        cwd=str(cwd or project_dir), env=env, capture_output=True, text=True,
        timeout=60,
    )


def _expect(cases, project_dir: Path, rc: int, needle: "str | None" = None,
            cwd: "Path | None" = None):
    """Alle Faelle pruefen, Abweichungen SAMMELN (nicht beim ersten abbrechen)."""
    wrong = []
    for cmd in cases:
        proc = _gate(cmd, project_dir, cwd)
        if proc.returncode != rc or (needle and needle not in proc.stderr):
            wrong.append(f"  {cmd!r}: rc={proc.returncode} (soll {rc}), "
                         f"stderr={proc.stderr.strip()[:160]!r}")
    return wrong


def _assert_blocked(cases, project_dir: Path, ac: str, needle: str = STATE_MSG,
                    cwd: "Path | None" = None):
    wrong = _expect(cases, project_dir, 2, needle, cwd)
    assert not wrong, (
        f"{ac}: Schreibweise rutscht durch ({len(wrong)}/{len(cases)}):\n"
        + "\n".join(wrong)
    )


def _assert_allowed(cases, project_dir: Path, ac: str, cwd: "Path | None" = None):
    wrong = _expect(cases, project_dir, 0, None, cwd)
    assert not wrong, (
        f"{ac}: harmloser Befehl wird ueber-blockiert "
        f"({len(wrong)}/{len(cases)}):\n" + "\n".join(wrong)
    )


def _assert_sandbox_lebt(project_dir: Path, ac: str):
    """Aufbau-Sanity: das Gate sieht den Workflow und blockt State weiter."""
    _assert_blocked([SANITY_STATE], project_dir, f"{ac} Sanity (Aufbau)")


def _override_token(root: Path) -> None:
    """Gueltiger Override-Token im Format von override_token.py (v2)."""
    (root / ".claude" / "user_override_token.json").write_text(json.dumps({
        "version": 2,
        "tokens": {WF: {"created": datetime.now().isoformat(),
                        "granted_by": "user_prompt"}},
    }))


# --------------------------------------------------------------------- #
# Befehlslisten
# --------------------------------------------------------------------- #

GLOB_SCHREIBEN = [
    "cp .claude/workflows/fix* docs/x/",
    "ln .claude/workflows/fix* docs/x/",
    "mv .claude/workflows/fix* docs/x/",
]
ORDNER_PUNKT = [
    "cp -r docs/w/. .claude/workflows/.",
    "rsync -a docs/w/ .claude/workflows/.",
    "rsync -a docs/w/ .claude/workflows/..",
    "ln -s .claude/workflows/.. docs/c",
]
ORDNER_DOPPELSLASH = ["ln -s .claude//workflows d"]
ORDNER_NACH_CD = [
    "cd .claude && ln -s workflows ../w",
    "pushd .claude; ln -s workflows ../w",
]


def _config_writes(name: str, root: Path):
    return [
        f"echo x > {name}",
        f"sed -i s/a/b/ {name}",
        f"echo x > {root}/{name}",
        f"sed -i s/a/b/ {root}/{name}",
    ]


# --------------------------------------------------------------------- #
# Teil 1: Glob (AC-1 bis AC-3)
# --------------------------------------------------------------------- #

def test_glob_ohne_json_blockt(tmp_path):
    """AC-1."""
    _assert_blocked(GLOB_SCHREIBEN, _sandbox(tmp_path), "AC-1 Glob ohne .json")


def test_glob_lesen_bleibt_frei_und_sanity_blockt(tmp_path):
    """AC-2: Lesen frei, Sanity-State-Write blockt weiter."""
    sandbox = _sandbox(tmp_path)
    _assert_allowed([
        "ls .claude/workflows/fix*",
        "cat .claude/workflows/x.json",
    ], sandbox, "AC-2 Lesen")
    _assert_sandbox_lebt(sandbox, "AC-2")


def test_glob_mit_umleitung_ist_dokumentierter_fehlalarm(tmp_path):
    """AC-3: Glob plus Umleitung blockt (hinnehmbar, Ausweg workflow.py status)."""
    _assert_blocked(["cat .claude/workflows/fix* > docs/x"], _sandbox(tmp_path),
                    "AC-3 Glob + Umleitung")


# --------------------------------------------------------------------- #
# Teil 2: wirksame Config (AC-4 bis AC-7)
# --------------------------------------------------------------------- #

def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c",
         "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        cwd=str(cwd), check=True, capture_output=True, text=True, timeout=60,
    )


def _worktree_sandbox(base: Path, config_name: str):
    """Hauptordner (git init, Plugin-Config) plus echter Worktree.

    Worktree unter `.claude/worktrees/wt` mit eigenem active_workflow; die
    Workflow-JSON liegt im Hauptordner. Liefert (main, wt).
    """
    main = base.resolve()
    main.mkdir(parents=True)
    _git(main, "init", "-q")
    (main / config_name).write_text(PLUGIN_CONFIG)
    _git(main, "add", config_name)
    _git(main, "commit", "-q", "-m", "init")
    _workflow_json(main / ".claude")
    wt = main / ".claude" / "worktrees" / "wt"
    _git(main, "worktree", "add", "-q", "-b", "wt", str(wt))
    (wt / ".claude").mkdir(parents=True, exist_ok=True)
    (wt / ".claude" / "active_workflow").write_text(WF + "\n")
    assert (wt / config_name).is_file(), "Aufbau: Worktree-Kopie fehlt"
    _assert_blocked([SANITY_STATE], wt, "Sanity (Aufbau Worktree)", cwd=wt)
    return main, wt


def test_wirksame_config_schreiben_blockt(tmp_path):
    """AC-4: openspec.yaml und Plugin-config.yaml; relativ, absolut, ../../,
    dazu der Kernfall: eine Worktree-Sitzung schreibt die wirksame Config im
    Hauptordner. Abweichungen der GANZEN Funktion werden gesammelt; die
    Aufbau-Sanity bricht dagegen sofort ab (Aufbaufehler ist kein RED).
    """
    wrong = []
    a = _sandbox(tmp_path / "a")
    (a / "openspec.yaml").write_text(PLUGIN_CONFIG)
    _assert_sandbox_lebt(a, "AC-4 openspec.yaml")
    wrong += _expect(_config_writes("openspec.yaml", a), a, 2, OVERRIDE_HINT)

    b = _sandbox(tmp_path / "b")
    (b / "config.yaml").write_text(PLUGIN_CONFIG)
    sub = b / "docs" / "sub"
    sub.mkdir(parents=True)
    _assert_sandbox_lebt(b, "AC-4 config.yaml")
    wrong += _expect(_config_writes("config.yaml", b), b, 2, OVERRIDE_HINT)
    wrong += _expect([
        "echo x > ../../config.yaml",
        "sed -i s/a/b/ ../../config.yaml",
    ], b, 2, OVERRIDE_HINT, cwd=sub)

    main, wt = _worktree_sandbox(tmp_path / "wtmain", "openspec.yaml")
    wrong += _expect([
        f"sed -i s/a/b/ {main}/openspec.yaml",
        f"echo x > {main}/openspec.yaml",
        "sed -i s/a/b/ ../../../openspec.yaml",
    ], wt, 2, OVERRIDE_HINT, cwd=wt)

    assert not wrong, (
        "AC-4: Schreibzugriff auf die wirksame Config rutscht durch "
        f"({len(wrong)} Faelle):\n" + "\n".join(wrong)
    )


def test_config_schutz_ohne_aktiven_workflow(tmp_path):
    """AC-5: Config-Schutz gilt auch ohne aktiven Workflow."""
    root = _sandbox_ohne_workflow(tmp_path)
    (root / "openspec.yaml").write_text(PLUGIN_CONFIG)
    _assert_blocked(_config_writes("openspec.yaml", root), root,
                    "AC-5 ohne Workflow", OVERRIDE_HINT)


def test_override_gibt_config_frei_aber_nicht_state(tmp_path):
    """AC-6: Token gibt die Config frei, State bleibt gesperrt.

    Vorher ohne Token geprueft, damit der Test belegt, dass GERADE der Token
    die Sperre hebt (ein Gate, das die Config nie sperrt, faellt hier durch).
    """
    root = _sandbox(tmp_path)
    (root / "openspec.yaml").write_text(PLUGIN_CONFIG)
    writes = _config_writes("openspec.yaml", root)
    _assert_blocked(writes, root, "AC-6 ohne Token (Vorbedingung)", OVERRIDE_HINT)
    _override_token(root)
    _assert_allowed(writes, root, "AC-6 mit Token")
    _assert_blocked([SANITY_STATE], root, "AC-6 State trotz Token")


def test_worktree_kopie_lesen_und_app_config_bleiben_frei(tmp_path):
    """AC-7: Worktree-Kopie, Lesen der wirksamen Datei, App-config.yaml."""
    main, wt = _worktree_sandbox(tmp_path / "main", "config.yaml")
    _assert_allowed([
        "sed -i s/a/b/ config.yaml",
        "cat config.yaml",
        f"grep enabled {main}/config.yaml",
    ], wt, "AC-7 Worktree", cwd=wt)

    app = _sandbox(tmp_path / "app")
    (app / "config.yaml").write_text(APP_CONFIG)
    (app / ".claude" / "openspec.yaml").write_text(PLUGIN_CONFIG)
    _assert_allowed([
        "echo x > config.yaml",
        "sed -i s/a/b/ config.yaml",
        f"sed -i s/a/b/ {app}/config.yaml",
    ], app, "AC-7 App-config.yaml")


# --------------------------------------------------------------------- #
# Ordner-Token (AC-8 bis AC-10)
# --------------------------------------------------------------------- #

def test_ordner_token_mit_punkt_und_punktpunkt_blockt(tmp_path):
    """AC-8 (F001)."""
    _assert_blocked(ORDNER_PUNKT, _sandbox(tmp_path), "AC-8 /. und /..")


def test_doppelter_slash_im_ordner_token_blockt(tmp_path):
    """AC-9 (F002)."""
    _assert_blocked(ORDNER_DOPPELSLASH, _sandbox(tmp_path), "AC-9 //")


def test_ordner_verweis_nach_cd_blockt(tmp_path):
    """AC-10 (F003)."""
    _assert_blocked(ORDNER_NACH_CD, _sandbox(tmp_path), "AC-10 cd-Kontext")


# --------------------------------------------------------------------- #
# Gegenproben (AC-11 bis AC-13)
# --------------------------------------------------------------------- #

def test_cd_kontext_gegenproben_bleiben_frei(tmp_path):
    """AC-11."""
    _assert_allowed([
        "cd .claude && ls workflows",
        "cd .claude/worktrees/x && cp a b",
        "ls .claude && rm docs/x",
        "python3 .claude/hooks/workflow.py status",
    ], _sandbox(tmp_path), "AC-11 Gegenproben")


def test_freitext_mit_glob_bleibt_frei(tmp_path):
    """AC-12: Inhalte von -m/--body zaehlen nicht.

    `git tag -m` statt `git commit -m`: ein Commit blockt in der Sandbox
    unabhaengig von 3b am Commit-Gate (kein Adversary-Verdict); dieselbe
    Freitext-Ausnahme gilt fuer beide (wie #407 AC-8).
    """
    _assert_allowed([
        'git tag -a v1 -m "cp .claude/workflows/fix* docs/x"',
        'gh issue comment 1 --body "cp .claude/workflows/fix* docs/x"',
    ], _sandbox(tmp_path), "AC-12 Freitext")


def test_state_befehle_ohne_workflow_unveraendert(tmp_path):
    """AC-13: State-Befehle aus AC-1/8/9/10 ohne Workflow bleiben Exit 0."""
    _assert_allowed(
        GLOB_SCHREIBEN + ORDNER_PUNKT + ORDNER_DOPPELSLASH + ORDNER_NACH_CD,
        _sandbox_ohne_workflow(tmp_path), "AC-13 ohne Workflow",
    )
