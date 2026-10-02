"""TDD RED — Issue #281: Commit-Gate löst git-Aliase auf (docs/specs/fix-281-…-commit-gate.md).

AC-1 … AC-17. E2E über das echte core/hooks/bash_gate.py in hermetischen echten Repos (cwd und
CLAUDE_PROJECT_DIR im tmp-Projekt, HOME/GIT_CONFIG_GLOBAL im tmp-Baum, GIT_CONFIG_NOSYSTEM=1, ohne
GIT_*-/Sitzungsvariablen). Gesperrter Zustand: `feature` in phase6_implement ohne Verdict, gestagte
Änderung — die Vorlage prüft einmal, dass ein wörtliches `git commit -m x` darin heute blockt.
`unit-`-Fälle (Regel-Matrizen des Test Plans) rufen den Resolver mit Runner-Recorder statt git;
git_alias wird erst im Test importiert. Wächter (heute grün) sind markiert.
"""

import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import types
from collections.abc import Mapping
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import hook_utils  # noqa: E402  (bestehendes Modul; git_alias erst im Test)

WF = "wf-281"
MOD_B, MOD_C, NEW = "src/b.py", "src/c.py", "NEU.py"
DIALOG = f"docs/artifacts/{WF}/adversary-dialog.md"
MARKER = ".claude/user_approved_validation_x"
CI, ST = (("ci", "commit"),), (("st", "status"),)
# Meldungskerne: 5c, 3a und #259 unverändert, die neuen Zeilen aus Spec Abschnitt 12
BLOCK_5C = "Adversary verdict missing or not VERIFIED"
EVIDENCE = "ohne gültigen Dialog-Nachweis"
MARKER_MSG = "Freigabe-/Erfolgs-Marker"
VIA_ALIAS = "Commit erkannt über Alias: "
UNRESOLVED = "Unterbefehl nicht auflösbar ("
WAY_OUT = "Ausweg: Unterbefehl ausschreiben"
_SCRUBBED = {"CLAUDE_TOOL_INPUT", "CLAUDE_TOOL_NAME", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT",
             "CLAUDE_CODE_SESSION_ID", "OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK",
             "PYTHONPATH", "XDG_CONFIG_HOME"}


# --- Hermetik, Repos, Hook-Aufruf ------------------------------------------------------------
def _env(base: Path, proj=None, **extra) -> dict:
    """Ohne Sitzungs- und GIT_*-Variablen; HOME im tmp-Baum, keine System-/globale Git-Config."""
    home = Path(base) / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in _SCRUBBED and not k.startswith("GIT_")}
    env.update(HOME=str(home), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0")
    if proj is not None:
        env["CLAUDE_PROJECT_DIR"] = str(proj)
    return {**env, **extra}


def _write(root, rel: str, text: str) -> Path:
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _git(args: list, cwd: Path, env: dict) -> None:
    """Nur für den Fixture-Aufbau (echtes git, hermetische Umgebung)."""
    r = subprocess.run(["git", "-c", "user.email=t@t.invalid", "-c", "user.name=Test",
                        "-c", "commit.gpgsign=false", *args], cwd=str(cwd), env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"git {args}: {r.stderr}"


def _cfg(section: str, entries: dict) -> str:
    """Git-Config-Abschnitt; Werte gequotet (führendes `-` oder `!`, Zeilenumbruch)."""
    quoted = {k: v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
              for k, v in entries.items()}
    return f"[{section}]\n" + "".join(f'\t{k} = "{v}"\n' for k, v in quoted.items())


def _config(repo: Path, section: str = "alias", **entries) -> None:
    """Lokale Konfiguration (.git/config) ergänzen — ohne den Optionsparser von `git config`."""
    with open(Path(repo) / ".git" / "config", "a") as f:
        f.write(_cfg(section, entries))


def _gate(proj: Path, command: str, env: dict, hooks: Path = HOOKS_DIR):
    """Echtes bash_gate.py als Subprozess, Hook-JSON auf stdin, cwd im tmp-Projekt."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run([sys.executable, str(hooks / "bash_gate.py")], input=payload,
                          capture_output=True, text=True, cwd=str(proj), env=env, timeout=60)


def _expect(r, rc: int, texts=(), gate: "str | None" = BLOCK_5C) -> None:
    """Exit-Code und stderr-Kerne; bei Exit 2 zusätzlich die Block-Meldung (Grund des Blocks)."""
    assert r.returncode == rc, f"Exit {r.returncode} statt {rc}; stderr: {r.stderr[-1200:]!r}"
    missing = [t for t in (*texts, *([gate] if rc == 2 and gate else [])) if t not in r.stderr]
    assert not missing, f"stderr ohne {missing}: {r.stderr[-1200:]!r}"


def _base_repo(root: Path, env: dict) -> Path:
    """Echtes Repo: MOD_C committet, MOD_B gestagt; aktiver Workflow nur per tmp-Datei."""
    proj = root / "A"
    _git(["init", "-q", "-b", "main", str(proj)], root, env)
    _write(proj, ".gitignore", ".claude/\n")
    _write(proj, MOD_C, "C = 1\n")
    _git(["add", "-A"], proj, env)
    _git(["commit", "-q", "-m", "init"], proj, env)
    _write(proj, MOD_B, "B = 1\n")
    _git(["add", MOD_B], proj, env)
    _write(proj, ".claude/active_workflow", WF)
    return proj


def _state(proj: Path, **fields) -> None:
    data = {"name": WF, "workflow_type": "feature", "spec_approved": True, "red_test_done": True,
            "phase_transitions": [], "test_artifacts": [], **fields}
    _write(proj, f".claude/workflows/{WF}.json", json.dumps(data, indent=2))


@pytest.fixture(scope="session")
def locked_tpl(tmp_path_factory):
    """Gesperrter Zustand. Fixture-Kontrolle: das wörtliche `git commit -m x` blockt heute (5c)."""
    root = tmp_path_factory.mktemp("locked")
    proj = _base_repo(root, _env(root))
    _state(proj, current_phase="phase6_implement")
    r = _gate(proj, "git commit -m x", _env(root, proj))
    assert r.returncode == 2 and BLOCK_5C in r.stderr, f"Fixture kaputt: {r.stderr}"
    return proj


@pytest.fixture(scope="session")
def verified_tpl(tmp_path_factory):
    """AC-12: Phase 7, VERIFIED, gestempelter Dialog zitiert und hasht nur MOD_B; MOD_C getrackt
    geändert (nicht gestagt), NEU.py untrackt. Kontrolle: die wörtlichen Formen wirken heute."""
    root = tmp_path_factory.mktemp("verified")
    proj = _base_repo(root, _env(root))
    env = _env(root, proj)
    _write(proj, MOD_C, "C = 2  # geändert, nicht gestagt\n")
    _write(proj, NEW, "N = 1\n")
    art = _write(proj, DIALOG, (
        "# Adversary Dialog\n\n## Checkliste\n- [x] AC-1: belegt — Beweis: Test\n"
        f"  Code reference: {MOD_B}:1\n\n## Dialog\n\n### Runde 1\n**Adversary:** A1\n"
        "**Implementierer:** B1\n\n### Runde 2\n**Adversary:** A2\n**Implementierer:** B2\n\n"
        "VERDICT: VERIFIED\n"))
    for sub in ("stamp", "validate"):
        r = subprocess.run([sys.executable, str(HOOKS_DIR / "adversary_dialog.py"), sub, str(art)],
                           cwd=str(proj), env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, f"{sub}: {r.stdout}{r.stderr}"
    _state(proj, current_phase="phase7_validate", adversary_verdict="VERIFIED:Tests PASSED: 5",
           test_artifacts=[{"type": "adversary_dialog", "path": DIALOG, "description": "fixture",
                            "phase": "phase6b_adversary", "created": "2026-09-30T10:00:00"}])
    for command, rc, text in (("git commit -m x", 0, ""), ("git commit -a -m x", 2, MOD_C),
                              (f"git add {NEW} && git commit -m x", 2, NEW)):
        r = _gate(proj, command, env)
        assert r.returncode == rc and text in r.stderr, f"Fixture kaputt ({command}): {r.stderr}"
    return proj


def _copy(request, tmp_path: Path, tpl: str = "locked_tpl", workflow: bool = True):
    """Eigene Kopie der Vorlage je Test; workflow=False entfernt den aktiven Workflow."""
    proj = tmp_path / "A"
    shutil.copytree(request.getfixturevalue(tpl), proj, symlinks=True)
    if not workflow:
        (proj / ".claude" / "active_workflow").unlink()
    return proj, _env(tmp_path, proj)


def _case(command: str, rc: int, *texts, **opts) -> tuple:
    return ("e2e", command, rc, texts, opts)


def _e(id_: str, command: str, rc: int, *texts, **opts):
    """E2E-Fall: Befehl ({t} = tmp_path), Exit-Code, stderr-Kerne; opts: gate, workflow, src."""
    return pytest.param(_case(command, rc, *texts, **opts), id=id_)


def _setup(request, tmp_path: Path, case: tuple, tpl: str = "locked_tpl", **aliases):
    proj, env = _copy(request, tmp_path, tpl, case[4].get("workflow", True))
    if aliases:
        _config(proj, **aliases)
    return proj, env, case[1].replace("{t}", str(tmp_path))


def _check(proj: Path, env: dict, command: str, case: tuple):
    r = _gate(proj, command, env)
    _expect(r, case[2], case[3], case[4].get("gate", BLOCK_5C))
    return r


def _e2e(request, tmp_path: Path, case: tuple, tpl: str = "locked_tpl", **aliases):
    proj, env, command = _setup(request, tmp_path, case, tpl, **aliases)
    return proj, _check(proj, env, command, case)


def _wrapper(tmp_path: Path, proj: Path, env: dict, fail: bool = False) -> Path:
    """Wrapper vorn im PATH: loggt `config … --get-regexp` (fail: rc 128), sonst echtes git."""
    real, log = shutil.which("git"), tmp_path / "lookups.log"
    then = "exit 128" if fail else f'exec "{real}" "$@"'
    wrapper = _write(tmp_path, "bin/git", '#!/bin/sh\ncase " $* " in *" config "*" --get-regexp "*)'
                     f'\n  echo "$*" >> "{log}"; {then} ;;\nesac\nexec "{real}" "$@"\n')
    wrapper.chmod(0o755)
    env["PATH"] = f"{wrapper.parent}{os.pathsep}{env['PATH']}"
    probe = subprocess.run(["git", "config", "-z", "--get-regexp", r"^alias\."], cwd=str(proj),
                           env=env, capture_output=True)
    assert _lookups(log) == 1 and (probe.returncode == 128) == fail, "Wrapper greift nicht"
    log.write_text("")
    return log


def _lookups(log: Path) -> int:
    return len(log.read_text().splitlines()) if log.exists() else 0


# --- Unit: Resolver mit Runner-Recorder ------------------------------------------------------
def _git_alias():
    """Import erst im Test: fehlt das Modul, scheitert nur dieser Fall (ModuleNotFoundError)."""
    return importlib.import_module("git_alias")


def _environ(t: Path, **extra) -> dict:
    return {"HOME": str(t / "home"), "PATH": "/usr/bin:/bin", **extra}


def _resolve(command: str, aliases, t: Path, environ, rc: int = 0, exc=None):
    """Resolver mit Runner run(argv, cwd, env) -> (rc, stdout); liefert (Sicht, Aufrufe)."""
    calls, table = [], "".join(f"alias.{k}\n{v}\0" for k, v in aliases).encode()

    def run(argv, cwd, env):
        calls.append(types.SimpleNamespace(argv=list(argv), cwd=cwd, env=env))
        if exc is not None:
            raise exc
        return rc, table

    return _git_alias().resolve_git_aliases(command, cwd=str(t), environ=environ, run=run), calls


def _verdict(view) -> str:
    """'offen' (unresolved) | 'commit' (wie `committing` in main()) | 'frei'."""
    if view.unresolved:
        return "offen"
    commit = (any(hook_utils._git_subcommand_after(list(t), 1) == "commit" for t in view.expansions)
              or any(hook_utils.is_git_subcommand(b, "commit") for b in view.shell_bodies))
    return "commit" if commit else "frei"


def _query_dir(call) -> Path:
    """Wo die Abfrage wirkt: Runner-cwd plus nachgespielte `-C`-Kette vor `config`."""
    d, argv, i = Path(call.cwd), call.argv, 1
    while i < len(argv) and argv[i] != "config":
        if argv[i] == "-C":
            d = d / argv[i + 1]
        i += 2 if argv[i] in hook_utils._GIT_OPTS_WITH_VALUE else 1
    return d.resolve()


def _has_seq(seq, part) -> bool:
    return any(list(seq[i:i + len(part)]) == list(part) for i in range(len(seq)))


def _u(id_: str, command: str, aliases, verdict: str, calls=None, **checks):
    """unit-Fall: Befehl + Alias-Tabelle ({t} = tmp_path) → Urteil, Zahl der Abfragen; checks:
    argv, dir, env (None = fehlt), environ, rc, exc, expansion, bodies, resolution, subs, argv0."""
    return pytest.param(("unit", command, tuple(aliases), verdict, calls, checks), id="unit-" + id_)


def _unit(case: tuple, t: Path) -> bool:
    """Führt einen unit-Fall aus (True); False heißt: E2E-Fall."""
    if case[0] != "unit":
        return False
    _, command, aliases, verdict, n_calls, ck = case
    sub = lambda s: s.replace("{t}", str(t))  # noqa: E731
    for rel in ("have.cfg", "B/g.cfg", "B/sub/.keep", "home/B/.keep"):  # Dateien und Verzeichnisse
        _write(t, rel, "[user]\n\tname = x\n")
    environ = _environ(t, **{k: sub(v) for k, v in ck.get("environ", {}).items()})
    view, calls = _resolve(sub(command), [(k, sub(v)) for k, v in aliases], t, environ,
                           ck.get("rc", 0), ck.get("exc"))
    assert _verdict(view) == verdict, f"{command!r}: {view}"
    assert n_calls is None or len(calls) == n_calls, f"{command!r}: {len(calls)} Abfragen {calls}"
    if "argv" in ck:
        assert any(_has_seq(c.argv, ck["argv"]) for c in calls), calls
    if "dir" in ck:
        assert _query_dir(calls[-1]) == (t / ck["dir"]).resolve(), calls
    if ck.get("argv0"):
        assert calls and all(c.argv[0] == "git" for c in calls), calls
    for key, want in ck.get("env", {}).items():
        got = [c.env.get(key) for c in calls]
        assert calls and all(g == (want and sub(want)) for g in got), (key, got)
    if "expansion" in ck:
        assert ck["expansion"] in [list(x) for x in view.expansions], view.expansions
    if "bodies" in ck:
        assert view.shell_bodies and ck["bodies"] in (True, list(view.shell_bodies)), view
    if "resolution" in ck:
        assert any(ck["resolution"] in r for r in view.resolutions), view.resolutions
    if "subs" in ck:
        assert set(ck["subs"]) <= set(view.unresolved_subs), view.unresolved_subs
    return True


# --- AC-1 … AC-8: Erkennung im gesperrten Zustand --------------------------------------------
def test_ac1_local_alias_commit_blocks(request, tmp_path):
    """Given gesperrt und lokales `alias.ci=commit` / When `git ci -m x` (Reproduktion #281) /
    Then Exit 2 mit der 5c-Meldung und der Auflösung `git ci → git commit`."""
    case = _case("git ci -m x", 2, VIA_ALIAS + "git ci → git commit")
    _e2e(request, tmp_path, case, ci="commit")


AC2 = [
    _e("a-global-env", "git ci -m x", 2, src="global"),
    _e("b-include-path", "git ci -m x", 2, src="include"),
    _e("c-inline", "git -c alias.ci=commit ci -m x", 2),
    _e("d-config-count", "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit "
       "git ci -m x", 2),
    _e("e-config-env", "ZZ=commit git --config-env=alias.ci=ZZ ci -m x", 2),
    _e("f-env-global-file", "env GIT_CONFIG_GLOBAL={t}/g.cfg git ci -m x", 2),
    _e("g-git-config-ignored", "git ci -m x", 2, src="git-config"),
    _e("h-cmdline-overrides-local", "git -c alias.dup=commit dup -m x", 2, src="dup"),
    _u("last-listed-wins", "git dup -m x", [("dup", "log"), ("dup", "commit")], "commit", 1),
    _u("c-replayed", "git -c alias.ci=commit ci -m x", CI, "commit", 1,
       argv=("-c", "alias.ci=commit")),
    _u("config-env-from-prefix", "ZZ=commit git --config-env=alias.ci=ZZ ci -m x", CI, "commit",
       1, argv=("-c", "alias.ci=commit")),
    _u("config-env-from-hook-env", "git --config-env=alias.ci=ZZ ci -m x", CI, "commit", 1,
       argv=("-c", "alias.ci=commit"), environ={"ZZ": "commit"}),
    _u("config-env-unset", "git --config-env=alias.ci=NOPE ci -m x", CI, "offen"),
    _u("allowlisted-prefix-overlay", "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci "
       "GIT_CONFIG_VALUE_0=commit git ci -m x", CI, "commit", 1, env={"GIT_CONFIG_COUNT": "1",
       "GIT_CONFIG_KEY_0": "alias.ci", "GIT_CONFIG_VALUE_0": "commit"}),
    _u("env-wrapper-overlay", "env GIT_CONFIG_GLOBAL={t}/have.cfg git ci -m x", CI, "commit", 1,
       env={"GIT_CONFIG_GLOBAL": "{t}/have.cfg"}),
    _e("adv-F005", "export GIT_TERMINAL_PROMPT=commit; "
       "git --config-env=alias.ci=GIT_TERMINAL_PROMPT ci -m x", 2),
    _u("adv-F005", "read ZZ; git --config-env=alias.ci=ZZ ci -m x", CI, "offen", environ={"ZZ": "c"}),
    _e("adv-F020", 'export GIT_TERMINAL_P""ROMPT=commit; git --config-env=alias.ci=GIT_TERMINAL_PROMPT ci -m x', 2),
    _e("adv-F020-declare", 'declare -x "GIT_TERMINAL_P""ROMPT"=commit; '
       "git --config-env=alias.ci=GIT_TERMINAL_PROMPT ci -m x", 2),
]


@pytest.mark.parametrize("case", AC2)
def test_ac2_alias_sources_block(case, request, tmp_path):
    """Given gesperrt, Alias auf commit aus Quelle a–h / When `git ci -m x` (h: `git -c
    alias.dup=commit dup -m x` bei lokalem alias.dup=log) / Then Exit 2 je Quelle.
    unit-*: Vorrang (zuletzt gelisteter Wert), Nachspielen von -c/--config-env, Env-Overlay."""
    if _unit(case, tmp_path):
        return
    proj, env, command = _setup(request, tmp_path, case)
    alias_file = _write(tmp_path, "g.cfg", _cfg("alias", {"ci": "commit"}))
    src = case[4].get("src")
    if src == "global":
        env["GIT_CONFIG_GLOBAL"] = str(alias_file)
    elif src == "include":
        _config(proj, "include", path=str(alias_file))
    elif src == "git-config":  # (g): die Abfrage ignoriert GIT_CONFIG wie `git ci`
        env["GIT_CONFIG"] = str(_write(tmp_path, "empty.cfg", "[user]\n\tname = x\n"))
        _config(proj, ci="commit")
    elif src == "dup":
        _config(proj, dup="log")
    _check(proj, env, command, case)


AC3 = [
    _e("C-option", "git -C {t}/B ci -m x", 2),
    _e("cd", "cd {t}/B && git ci -m x", 2),
    _e("nested-shell", 'bash -c "cd {t}/B && git ci -m x"', 2),
    _e("cd-unknown-dir", 'cd "$X" && git ci -m x', 2, UNRESOLVED),
    _u("C-replayed", "git -C B ci -m x", CI, "commit", 1, dir="B"),
    _u("cd-literal", "cd B && git ci -m x", CI, "commit", 1, dir="B"),
    _u("cd-chain", "cd B && cd sub && git ci -m x", CI, "commit", 1, dir="B/sub"),
    _u("pushd-literal", "pushd B && git ci -m x", CI, "commit", 1, dir="B"),
    _u("cd-tilde", "cd ~/B && git ci -m x", CI, "commit", 1, dir="home/B"),
    _u("nested-shell", 'bash -c "cd B && git ci -m x"', CI, "commit", 1, dir="B"),
    _u("nested-cd-stays-inside", 'bash -c "cd B"; git ci -m x', CI, "commit", 1, dir="."),
    _u("cd-dash", "cd - && git ci -m x", CI, "offen"),
    _u("cd-without-arg", "cd && git ci -m x", CI, "offen"),
    _u("cd-variable", 'cd "$X" && git ci -m x', CI, "offen"),
    _u("cd-option", "cd -P B && git ci -m x", CI, "offen"),
    _u("popd", "popd; git ci -m x", CI, "offen"),
    _u("cd-after-control-word", "if true; then cd B; fi; git ci -m x", CI, "offen"),
    _u("cd-and-subshell", "(cd B) && git ci -m x", CI, "offen"),
    _u("cd-and-background", "cd B & git ci -m x", CI, "offen"),
    _u("unknown-dir-builtin-unaffected", "cd - && git status", CI, "frei", 0),
    _u("C-shell-syntax", 'git -C "$R" ci -m x', CI, "offen"),
    _u("c-value-shell-syntax", 'git -c "alias.ci=$V" ci -m x', CI, "offen"),
    _u("sudo", "sudo git ci -m x", CI, "offen"),
    _u("env-with-option", "env -i git ci -m x", CI, "offen"),
    _u("xargs-allowlisted-assignment", "HOME={t}/h xargs git ci -m x", CI, "offen"),
    _u("body-relative-cd", "git sb", [("sb", "!cd sub && git ci"), ("ci", "commit")], "offen"),
    _u("body-absolute-cd", "git sa", [("sa", "!cd {t}/B && git ci"), ("ci", "commit")],
       "commit", dir="B"),
    _e("adv-F002", "builtin cd {t}/B && git ci -m x", 2),
    _e("adv-F002-eval", 'eval "cd {t}/B" && git ci -m x', 2),
    _e("adv-F009", "/usr/bin/env -C {t}/B git ci -m x", 2),
    _e("adv-F009-execdir", "find {t}/B -name f -execdir git ci -m x \\;", 2),
    _e("adv-F009-execdir-dot", "find . -execdir git ci -m x \\;", 2),
    *[_u("adv-F002-" + c.split()[0], c, CI, "offen") for c in ('eval "cd B" && git ci', "builtin cd B; git ci",
      "command cd B; git ci", "X=1 cd B; git ci", "time cd B; git ci", "for i in 1; do git ci; cd B; done",
      "export CDPATH=/x; cd B; git ci")],
    *[_u("adv-F009-" + i, c, t, v) for i, c, t, v in (  # Stellung: A offen, B Kontext bleibt, C nur ein Alias
        ("timeout", "timeout 5 git ci", CI, "commit"), ("xargs", "xargs git ci", CI, "commit"),
        ("nice", "nice -n 1 git ci", CI, "commit"), ("xargs-no-alias", "xargs git st", (), "frei"),
        ("xargs-sh", "xargs sh -c 'git ci'", CI, "commit"), ("execdir", "find . -execdir git ci ;", CI, "offen"),
        ("execdir-sh", "find . -execdir sh -c 'git ci' ;", CI, "offen"), ("sudo-u", "sudo -u x git ci", CI, "offen"),
        ("mention-alias", "grep -rn git ci", CI, "commit"), ("mention", "echo git is $X `great`", CI, "frei"),
        ("mention-sh", "echo sh -c 'git $X'", CI, "frei"), ("mention-loop", "echo git l1", [("l1", "l2"), ("l2", "l1")],
                                                            "offen"),  # Alias-Erwaehnung = echter Aufruf
        ("mention-taint", "echo git ci; git config alias.q x", CI, "offen"))],
    _u("adv-C-plausible", "grep -rn git core/", CI, "frei", 0),  # kein moeglicher Alias-Name: keine Abfrage
    _u("adv-C-plausible-name", "echo git is great", ST, "frei", 1),
    _e("adv-F009-timeout-C", "timeout 5 git -C {t}/B ci -m x", 2),
    *[_u(f"adv-F021-{i}", c + "; cd B && git ci", CI, "offen") for i, c in enumerate(
        ('export CD""PATH=/x', "export CD\\PATH=/x"))],
    *[_u(f"adv-F018-{i}", c + " git ci", CI, "commit", 1) for i, c in enumerate((
        "timeout -s KILL 5", "flock /tmp/lockx", "stdbuf -o L", "nice -n +5", ">/dev/null", "2>/dev/null",
        "xargs -I {} -P 2", "ionice -c 2 -n 7"))],
    _u("adv-F011", "timeout 5 git `echo ci` -m x", CI, "offen", 0),
    _u("adv-F009-control-word", "if git ci -m x; then :; fi", CI, "commit", 1),
]


@pytest.mark.parametrize("case", AC3)
def test_ac3_context_replay_other_repo(case, request, tmp_path):
    """Given gesperrtes Repo A, `alias.ci=commit` nur in Repo B / When (cwd A) `git -C B ci`,
    `cd B && git ci`, `bash -c "cd B && git ci"`, `cd "$X" && git ci` / Then Exit 2 in allen vier.
    unit-*: -C/cd-Modell, unbekanntes Verzeichnis, env-Optionen/sudo, Zuweisungen, cd im Rumpf."""
    if _unit(case, tmp_path):
        return
    proj, env, command = _setup(request, tmp_path, case)
    repo_b = tmp_path / "B"
    _git(["init", "-q", "-b", "main", str(repo_b)], tmp_path, env)
    _config(repo_b, ci="commit")
    _check(proj, env, command, case)


AC4 = [
    _e("upper-case-alias", "git CI -m x", 2),
    _e("upper-case-builtin-name", "git STATUS -m x", 2),
    _u("alias-name-case-insensitive", "git CI -m x", CI, "commit", 1),
    _u("builtin-name-exact", "git STATUS -m x", [("status", "commit")], "commit", 1),
    _u("builtin-shadows-alias", "git status", [("status", "commit")], "frei", 0),
    _u("chain-ends-at-builtin", "git x", [("x", "status"), ("status", "commit")], "frei", 1),
    _e("adv-F001", 'g""it ci -m x', 2),
    *[_u(f"adv-F001-{i}", c + " ci -m x", CI, "commit", 1)
      for i, c in enumerate(('g""it', "g\\it", "gi''t", '"g""it"', "gi\\\nt"))],
    _e("adv-F024-bash-heredoc", "bash <<'EOF'\ngit ci -m x\nEOF", 2),
    _e("adv-F024-sh-heredoc", "sh <<'EOF'\ngit ci -m x\nEOF", 2),
]


@pytest.mark.parametrize("case", AC4)
def test_ac4_alias_names_case_insensitive(case, request, tmp_path):
    """Given gesperrt, ci=commit, status=commit / When `git CI -m x` bzw. `git STATUS -m x` / Then
    Exit 2: Alias-Namen case-insensitiv, Builtins exakt. unit-*: Schatten-Regel, auch in Ketten."""
    if not _unit(case, tmp_path):
        _e2e(request, tmp_path, case, ci="commit", status="commit")


AC5 = [
    _e("a-chain", "git c2 -m x", 2, "git c2 → git ci → git commit"),
    _e("b-option-in-value", "git cx -m x", 2),
    _e("c-loop", "git l1", 2, UNRESOLVED, WAY_OUT, loop=True),
    _u("chain", "git c2 -m x", [("c2", "ci"), ("ci", "commit")], "commit", 1,
       expansion=["git", "commit", "-m", "x"], resolution="git c2 → git ci → git commit"),
    _u("option-in-value", "git cx -m x", [("cx", "-c user.name=zz commit")], "commit", 1,
       expansion=["git", "-c", "user.name=zz", "commit", "-m", "x"]),
    _u("loop", "git l1", [("l1", "l2"), ("l2", "l1")], "offen", subs=["l1"]),
    _u("loop-case-folded", "git a", [("a", "A")], "offen"),
    _u("short-chain", "git a0", [("a0", "a1"), ("a1", "a2"), ("a2", "commit")], "commit", 1),
    _u("over-8-steps", "git a0", [(f"a{i}", f"a{i + 1}") for i in range(11)] + [("a11", "commit")],
       "offen"),
    _u("empty-value", "git e", [("e", "")], "offen"),
    _u("unparsable-value", "git u", [("u", "commit 'x")], "offen"),
    _u("c-alias-in-value", "git cc", [("cc", "-c alias.y=commit y")], "offen"),
    _u("c-include-in-value", "git ci2", [("ci2", "-c Include.path=/x commit")], "offen"),
    _u("config-env-alias-in-value", "git ce", [("ce", "--config-env=alias.y=V y")], "offen"),
    _u("external-name-ends-chain", "git ext", [("ext", "frobnicate --x")], "frei", 1),
    _u("adv-F003", "git ci -m x", [("ci", '"com\\mit"')], "offen"),
]


@pytest.mark.parametrize("case", AC5)
def test_ac5_chains_option_values_and_loops(case, request, tmp_path):
    """Given gesperrt / When (a) Kette c2 → ci → commit, (b) `cx = -c user.name=zz commit`,
    (c) Schleife l1 ↔ l2 / Then Exit 2 in allen drei; bei (c) nennt stderr Grund und Ausweg.
    unit-*: Kette, Besucht-Menge, Obergrenze 8, leere/unzerlegbare Werte, -c/--config-env."""
    if _unit(case, tmp_path):
        return
    _, r = _e2e(request, tmp_path, case, c2="ci", ci="commit", cx="-c user.name=zz commit",
                l1="l2", l2="l1")
    if case[4].get("loop"):
        m = re.search(r"nicht auflösbar \((.+)\): git l1\b", r.stderr)
        assert m and re.search(r"(?i)schleife", m.group(1)), f"Grund fehlt: {r.stderr!r}"


AC6 = [
    _e("commit-in-body", "git sh1 -m x", 2, "git sh1 → !git commit"),
    _e("marker-in-body", "git mk", 2, gate=MARKER_MSG),
    _e("harmless-body", "git hi", 0),  # Wächter (heute grün)
    _u("body-text", "git sh1 -m 'a b'", [("sh1", "!git commit")], "commit", 1,
       bodies=["git commit -m 'a b'"]),
    _u("z-newline-in-value", "git ml -m x", [("ml", "!echo a\ngit commit")], "commit", 1),
    _u("alias-in-body", "git sh2 -m x", [("sh2", "!git ci"), ("ci", "commit")], "commit", 1,
       expansion=["git", "commit", "-m", "x"]),
    _u("harmless-body", "git hi", [("hi", "!echo hi")], "frei", 1, bodies=True),
    _e("adv-F007", "git dc -m x", 2, "git dc → !git-commit"),
    *[_u(f"adv-F007-{i}", "git dc", [("dc", b)], "commit", 1) for i, b in enumerate((
        "!exec git-commit", '!f() { git-commit "$@"; }; f', "!$(git --exec-path)/git-commit", '!"git-commit"'))],
    _e("adv-F019", "git d2 -m x", 2),
    _e("adv-F019-sh-c", "git d3 -m x", 2),
    _e("adv-F019-exec-path", "git d4 -m x", 2),
    _e("adv-F019-ls-free", "git d5", 0),
    *[_u(f"adv-F019-{i}", "git dc", [("dc", b)], "commit", 1) for i, b in enumerate((
        "!git\\-commit", '!git-com""mit', "!g\\it-commit", "!'git'-commit", "!git-'commit'",
        "!sh -c 'git-commit \"$@\"' --", "!bash -c 'git-commit \"$@\"' --", '!sh -c "git-commit \\"\\$@\\"" --',
        '!"$(git --exec-path)/git-commit" "$@"'))],
    _u("adv-F019-ls", "git dc", [("dc", "!ls git-hooks")], "frei", 1),
]


@pytest.mark.parametrize("case", AC6)
def test_ac6_shell_aliases(case, request, tmp_path):
    """Given gesperrt, sh1 = !git commit, mk = !touch <Marker>, hi = !echo hi / When `git sh1
    -m x`, `git mk`, `git hi` / Then Exit 2; Exit 2 mit 3a-Meldung, ohne Marker-Datei; Exit 0
    (Wächter). unit-*: Rumpf-Aufbau, -z mit Zeilenumbruch, Alias im Rumpf."""
    if _unit(case, tmp_path):
        return
    proj, _ = _e2e(request, tmp_path, case, sh1="!git commit", mk=f"!touch {MARKER}", hi="!echo hi",
                   dc="!git-commit", d2='!git-com""mit', d3="!sh -c 'git-commit \"$@\"' --",
                   d4='!"$(git --exec-path)/git-commit" "$@"', d5="!ls git-hooks")
    assert not (proj / MARKER).exists(), "Freigabe-Marker entstanden"


AC7 = [
    _e("a-alias-set-in-same-call", "git config alias.ci commit && git ci -m x", 2, UNRESOLVED),
    _e("b-export-global", "export GIT_CONFIG_GLOBAL={t}/g.cfg; git ci -m x", 2, UNRESOLVED),
    _e("c-unrelated-config", "git config user.name y && git st", 0),  # Wächter (heute grün)
    _e("d-named-file-missing", "printf '[alias]\\n\\tci = commit\\n' > {t}/f && "
       "GIT_CONFIG_GLOBAL={t}/f git ci -m x", 2, UNRESOLVED),
    _u("a-config-alias", "git config alias.st commit && git st", ST, "offen"),
    _u("a-config-include", "git config Include.path /x; git st", ST, "offen"),
    _u("a-clone-alias", "git clone -c alias.st=commit r d && git st", ST, "offen"),
    _u("a-unrelated", "git config user.name y && git st", ST, "frei", 1),
    _u("a-earlier-calls-too", "git st; git config alias.st commit", ST, "offen", 1),  # F004: jede Stelle
    _u("b-gitconfig", "echo x >> ~/.gitconfig; git st", ST, "offen"),
    _u("b-dot-git-config", "cp x .git/config && git st", ST, "offen"),
    _u("b-config-worktree", "cp x config.worktree && git st", ST, "offen"),
    _u("b-config-variable-target", 'printf x > "$GIT_CONFIG_GLOBAL" && git st', ST, "offen"),
    _u("c-export", "export HOME={t}/h; git st", ST, "offen"),
    _u("c-plain-assignment", "GIT_DIR={t}/B/.git; git st", ST, "offen"),
    _u("c-unset", "unset GIT_CONFIG_GLOBAL; git st", ST, "offen"),
    _u("c-immediate-prefix-ok", "HOME={t}/home git st", ST, "frei", 1),
    _u("src-missing", "GIT_CONFIG_GLOBAL={t}/missing.cfg git st", ST, "offen", 0),
    _u("src-exists", "GIT_CONFIG_GLOBAL={t}/have.cfg git st", ST, "frei", 1),
    _u("src-named-again", "GIT_CONFIG_GLOBAL={t}/have.cfg git st && cat have.cfg", ST, "offen", 0),
    _u("src-hook-env-exempt", "git st", ST, "frei", 1,
       environ={"GIT_CONFIG_GLOBAL": "{t}/missing.cfg"}),
    _u("src-relative-to-cd", "cd B && GIT_CONFIG_GLOBAL=g.cfg git st", ST, "frei", 1),
    _u("src-relative-to-C", "GIT_CONFIG_GLOBAL=g.cfg git -C B st", ST, "frei", 1),
    _u("src-relative-missing", "GIT_CONFIG_GLOBAL=g.cfg git st", ST, "offen", 0),
    _u("src-include-c", "git -c include.path={t}/missing.cfg st", ST, "offen", 0),
    _u("src-includeif-exists", "git -c includeIf.onbranch:main.path={t}/have.cfg st", ST,
       "frei", 1),
    _u("src-config-env-include", "P={t}/missing.cfg git --config-env=include.path=P st", ST,
       "offen", 0),
    _u("src-key-value-n", "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=include.path "
       "GIT_CONFIG_VALUE_0={t}/missing.cfg git st", ST, "offen", 0),
    _u("src-parameters-include", "GIT_CONFIG_PARAMETERS=\"'include.path'='/x'\" git st", ST,
       "offen", 0),
    _u("src-nested-shell", "bash -c 'GIT_CONFIG_GLOBAL={t}/missing.cfg git st'", ST, "offen"),
    _e("adv-F004", "git ci -m x $(git config alias.ci commit)", 2, UNRESOLVED),
    _e("adv-C-taint", "git config alias.ci commit; strace git ci -m x", 2, UNRESOLVED),
    _e("adv-C-prefix-source", "GIT_CONFIG_GLOBAL={t}/g.cfg strace git ci -m x", 2, UNRESOLVED),
    _e("adv-C-export-source", "export GIT_CONFIG_GLOBAL={t}/g.cfg; strace git ci -m x", 2, UNRESOLVED),
    _e("adv-C-open-dir", 'cd "$X" && strace git ci -m x', 2, UNRESOLVED),
    _e("adv-C-config-env", "V=commit strace git --config-env=alias.ci=V ci -m x", 2, UNRESOLVED),
    _e("adv-C-include", "printf '[alias]\\n\\tci = commit\\n' > {t}/inc && strace git -c include.path={t}/inc ci -m x",
       2, UNRESOLVED),
    _e("adv-F022-tem", "git init -q --tem={t}/tpl {t}/C && git ci -m x", 2, UNRESOLVED),
    _e("adv-F022-ed", "git config --ed && git ci -m x", 2, UNRESOLVED),
    _u("adv-F022-t", "git init --t=/x d; git st", ST, "offen"),  # git nimmt auch --t= (eindeutiges Praefix)
    _e("adv-F023-key", "K=alias.ci; git config $K commit && git ci -m x", 2, UNRESOLVED),
    _e("adv-F023-name", "PFX=GIT_CONFIG_GL; export ${PFX}OBAL={t}/g.cfg; git ci -m x", 2, UNRESOLVED),
    _u("adv-F023-declare", "declare -x ${P}OBAL=/x; git st", ST, "offen"),
    _u("adv-F023-value-ok", 'git config user.name "$N" && git st', ST, "frei", 1),
    _e("adv-F004-trap", "trap 'git ci -m x' EXIT; git config alias.ci commit", 2, UNRESOLVED),
    *[_u(f"adv-F004-{i}", c, ST, "offen") for i, c in enumerate((
        'git st -m "x$(git config alias.st commit)"', 'X="$(git config alias.st x)" git st',
        "for i in 1 2; do git st; git config alias.st commit; done", "trap 'git st' EXIT; git config alias.st c",
        "f() { git st; }; git config alias.st commit; f", "for i in 1 2; do git st; cd B; done",
        "read HOME; git st", "for HOME in x; do git st; done", "printf -v HOME x; git st"))],
    *[_u(f"adv-F017-{i}", c + "; git st", ST, "offen") for i, c in enumerate(("git config -e", "git init "
      "--template=/t d", "git clone --template=/t r d", "git submodule add --template=/t r"))],
]


@pytest.mark.parametrize("case", AC7)
def test_ac7_same_call_changes_taint(case, request, tmp_path):
    """Given gesperrt, alias.st=status / When (a) `git config alias.ci commit && git ci`, (b)
    `export GIT_CONFIG_GLOBAL=<datei mit ci=commit>; git ci`, (c) `git config user.name y &&
    git st`, (d) `printf … > f && GIT_CONFIG_GLOBAL=f git ci` (f fehlt) / Then Exit 2 „nicht
    auflösbar“ für a, b, d; Exit 0 für c (Wächter). unit-*: Taint (a)–(c), benannte Quellen."""
    if _unit(case, tmp_path):
        return
    _write(tmp_path, "g.cfg", _cfg("alias", {"ci": "commit"}))
    _e2e(request, tmp_path, case, st="status")


@pytest.mark.parametrize("command", ["git st", "git lg", "git status",
                                     pytest.param("grep -rn git core/", id="adv-fp-grep"),
                                     pytest.param("echo git is great", id="adv-fp-echo"),
                                     pytest.param('grep -n "git" "$f"', id="adv-fp-var"),
                                     pytest.param('find . -type f -exec grep -l "git" {} \\;', id="adv-fp-find-exec"),
                                     pytest.param("timeout 60 grep -rn git *.py", id="adv-fp-timeout-glob"),
                                     pytest.param("xargs -I{} grep git {}", id="adv-fp-xargs-I"),
                                     pytest.param("find . -execdir grep -l git {} \\;", id="adv-fp-find-execdir"),
                                     pytest.param('cd "$D" && grep -rn git .', id="adv-fp-cd-var"),
                                     pytest.param("git config user.name y && grep -rn git core/", id="adv-fp-config"),
                                     pytest.param("gh pr create --title t --body \"$(cat <<'EOF'\n- Fix git alias "
                                                  "bypass (it's #281)\nEOF\n)\"", id="adv-F024-pr"),
                                     pytest.param("cat > docs/n.md <<'EOF'\nDon't run git hooks manually.\nEOF",
                                                  id="adv-F024-doc"),
                                     pytest.param('cd "$D" && grep git README.md', id="adv-F018-dotted-file")])
def test_ac8_harmless_aliases_pass(command, request, tmp_path):
    """adv-fp-*: git als Argument (grep, echo; auch hinter find -exec, timeout, xargs) ist nur eine Erwähnung ohne
    möglichen Alias-Namen bzw. ohne Alias (F009) — Exit 0 auch im gesperrten Zustand.
    Wächter (heute grün): Given gesperrt, st=status, lg=log --graph --oneline, status=commit /
    When `git st`, `git lg`, `git status` / Then Exit 0 (Alias auf Builtin-Namen wirkungslos)."""
    _e2e(request, tmp_path, _case(command, 0), st="status", lg="log --graph --oneline",
         status="commit")


# --- AC-9 … AC-11: Kosten, Fehlerrichtung, keine Nebenwirkung der Abfrage --------------------
def test_ac9_builtins_cost_no_lookup(request, tmp_path):
    """Given Wrapper, der jede `config … --get-regexp`-Abfrage protokolliert, kein Workflow / When
    `git status`, `git add f`, `git diff`, `git commit -m x`, dann `git st && git lg` / Then null
    Abfragen für die Builtins (Wächter-Teil), genau eine für `git st && git lg` (Cache)."""
    proj, env = _copy(request, tmp_path, workflow=False)
    _config(proj, st="status", lg="log --graph --oneline")
    log = _wrapper(tmp_path, proj, env)
    for command in ("git status", "git add f", "git diff", "git commit -m x"):
        _expect(_gate(proj, command, env), 0)
        assert _lookups(log) == 0, f"Builtin `{command}` hat {_lookups(log)} Abfrage(n) ausgelöst"
    _expect(_gate(proj, "git st && git lg", env), 0)
    assert _lookups(log) == 1, f"{_lookups(log)} statt genau 1 Abfrage für `git st && git lg`"


def test_ac9_cache_and_budget(tmp_path):
    """Given Runner-Recorder / When `git st && git lg` bzw. `git -C a st; …; git -C d st` / Then
    genau eine Abfrage `config -z --get-regexp`, bzw. drei und der vierte Kontext `unresolved`."""
    for d in "abcd":
        (tmp_path / d).mkdir()
    table = ST + (("lg", "log --graph --oneline"),)
    view, calls = _resolve("git st && git lg", table, tmp_path, _environ(tmp_path))
    assert len(calls) == 1 and _verdict(view) == "frei", (calls, view)
    assert _has_seq(calls[0].argv, ("config", "-z", "--get-regexp")), calls[0].argv
    view, calls = _resolve("git -C a st; git -C b st; git -C c st; git -C d st", ST, tmp_path,
                           _environ(tmp_path))
    assert len(calls) == 3, calls
    assert view.unresolved and "st" in view.unresolved_subs, view
    assert any("Budget" in reason for reason in view.unresolved), view.unresolved


AC10 = [
    _e("st-locked", "git st", 2, UNRESOLVED, WAY_OUT),
    _e("status-locked", "git status", 0),  # Wächter (heute grün)
    _e("st-without-workflow", "git st", 0, workflow=False),  # Wächter (heute grün)
    _u("rc-128", "git st", ST, "offen", 1, rc=128),
    _u("rc-1-no-alias", "git st", (), "frei", 1, rc=1),
    _u("oserror", "git st", ST, "offen", exc=OSError("git fehlt")),
    _u("timeout", "git st", ST, "offen", exc=subprocess.TimeoutExpired(["git"], 2)),
]


@pytest.mark.parametrize("case", AC10)
def test_ac10_lookup_failure_checks_only_with_workflow(case, request, tmp_path):
    """Given Wrapper: `config … --get-regexp` endet mit rc 128 / When `git st`, `git status`
    (gesperrt), `git st` ohne Workflow / Then Exit 2 „nicht auflösbar“ + Ausweg; Exit 0 ohne
    Abfrage; Exit 0 (beide Wächter). unit-*: rc 128, rc 1 (kein Treffer), OSError, Timeout."""
    if _unit(case, tmp_path):
        return
    proj, env, command = _setup(request, tmp_path, case)
    log = _wrapper(tmp_path, proj, env, fail=True)
    _check(proj, env, command, case)
    assert command != "git status" or _lookups(log) == 0, "Builtin hat eine Abfrage ausgelöst"


AC11 = [
    _e("git-trace-prefix", "GIT_TRACE={t}/trace.out git -c alias.ci=commit ci -m x", 2),
    _e("dot-slash-git", "./git ci -m x", 2),
    _u("argv0-is-git", "./git ci -m x", CI, "commit", 1, argv0=True),
    _u("trace-and-git-config-removed", "GIT_TRACE2_EVENT={t}/t4 git -c alias.ci=commit ci -m x",
       CI, "commit", 1, environ={"GIT_TRACE": "{t}/t1", "GIT_TRACE2": "{t}/t2",
                                 "GIT_TRACE_PACKET": "{t}/t3", "GIT_CONFIG": "{t}/have.cfg"},
       env={"GIT_TRACE": None, "GIT_TRACE2": "0", "GIT_TRACE_PACKET": None,  # F012: trace2 aus, nie Hook-Ziel
            "GIT_TRACE2_EVENT": "0", "GIT_CONFIG": None}),
    _u("foreign-prefixes-dropped", "LD_PRELOAD=/x.so GIT_EXEC_PATH=/y PAGER=evil PATH=/evil "
       "git ci -m x", CI, "commit", 1,
       env={"LD_PRELOAD": None, "GIT_EXEC_PATH": None, "PAGER": None, "PATH": "/usr/bin:/bin"}),
    _u("adv-F012", "git st", ST, "frei", 1, env=dict.fromkeys(("GIT_TRACE2", "GIT_TRACE2_EVENT",
                                                                "GIT_TRACE2_PERF"), "0")),
]


@pytest.mark.parametrize("case", AC11)
def test_ac11_lookup_never_runs_foreign_code(case, request, tmp_path):
    """Given alias.ci=commit, ausführbares ./git mit Sentinel / When `GIT_TRACE=<pfad> git -c
    alias.ci=commit ci -m x` bzw. `./git ci -m x` / Then Exit 2, keine Trace-Datei, kein Sentinel.
    unit-*: argv[0] = git; Runner-Env ohne GIT_TRACE*, GIT_CONFIG, nicht freigegebene Präfixe."""
    if _unit(case, tmp_path):
        return
    proj, env, command = _setup(request, tmp_path, case, ci="commit")
    fake = _write(proj, "git", f'#!/bin/sh\ntouch "{tmp_path}/sentinel"\n'
                               f'exec "{shutil.which("git")}" "$@"\n')
    fake.chmod(0o755)
    _check(proj, env, command, case)
    assert not (tmp_path / "trace.out").exists(), "Trace-Datei durch die Abfrage angelegt"
    assert not (tmp_path / "sentinel").exists(), "./git aus dem Befehlstext wurde ausgeführt"


# --- AC-12 … AC-17: Commit-Menge, Whitelist, Ausfall, Unzerlegbares, Doku, Drift -------------
def _f(id_: str, command: str, aliases, expected: tuple):
    """unit-form-Fall: `_commit_form(command, view)`; ohne Aliase nur der wörtliche Text."""
    return pytest.param(("form", command, tuple(aliases), expected), id="unit-form-" + id_)


AC12 = [
    _e("ci-index-form", "git ci -m x", 0),  # Wächter (heute grün): MOD_C gehört nicht dazu
    _e("cam-worktree-form", "git cam msg", 2, MOD_C, gate=EVIDENCE),
    _e("add-alias", f"git a {NEW} && git ci -m x", 2, NEW, gate=EVIDENCE),
    _e("stage-alias", f"git s {NEW} && git ci -m x", 2, NEW, gate=EVIDENCE),
    _f("stage-literal", f"git stage {NEW} && git commit -m x", (), (False, False, True, False)),
    _f("cam-expansion", "git cam msg", [("cam", "commit -a -m")], (True, False, False, False)),
    _f("stage-expansion", f"git s {NEW} && git ci -m x", [("s", "stage"), ("ci", "commit")],
       (False, False, True, False)),
    _f("stage-in-body", "git sb", [("sb", f"!git stage {NEW} && git commit -m x")],
       (False, False, True, False)),
    _f("unresolved-largest-set", "git l1", [("l1", "l2"), ("l2", "l1")], (True, True, True, True)),
    _e("adv-F010", "git b1 && git commit -m y", 2, MOD_C, gate=EVIDENCE),
    _f("adv-F007-stage", "git sb", [("sb", f"!git-stage {NEW} && git-commit -m x")],
       (False, False, True, False)),
    _e("adv-F024-phase7", "cd {t}/A && git commit -m \"$(cat <<'EOF'\nfix: tidy up the git hooks\nEOF\n)\"", 0),
    _e("adv-F024-phase7-apostrophe", "git commit -m \"$(cat <<'EOF'\nfix: don't resolve git aliases twice\nEOF\n)\"",
       0),
]


@pytest.mark.parametrize("case", AC12)
def test_ac12_commit_set_follows_alias_arguments(case, request, tmp_path):
    """Given Phase 7, VERIFIED, Dialog nur über B (gestagt); C getrackt geändert; NEU.py untrackt
    / When `git ci -m x`, `git cam msg` (commit -a -m), `git a|s NEU.py && git ci` (add|stage) /
    Then Exit 0 (Wächter), Exit 2 mit C, Exit 2 mit NEU.py. unit-form-*: `_commit_form` faltet
    Expansionen und Rümpfe; `stage` zählt wie `add`, auch im wörtlichen Befehlstext."""
    if case[0] == "form":
        import bash_gate
        _, command, aliases, expected = case
        if aliases:
            view = _resolve(command, aliases, tmp_path, _environ(tmp_path))[0]
            got = bash_gate._commit_form(command, view)
        else:
            got = bash_gate._commit_form(command)
        assert got == expected, f"{command!r}: {got} statt {expected}"
        return
    _e2e(request, tmp_path, case, "verified_tpl", ci="commit", cam="commit -a -m", a="add",
         s="stage", b1="!git commit -a -m $'it\\'s'")


def test_ac13_whitelist_ignores_aliases(tmp_path, monkeypatch):
    """Given alias.ci=commit, Resolver gepatcht auf eine werfende Funktion / When
    `_is_whitelisted("git ci -m x")` / Then False ohne Fehler, der Resolver wird nie gerufen."""
    ga = _git_alias()
    import bash_gate
    repo = tmp_path / "r"
    _git(["init", "-q", "-b", "main", str(repo)], tmp_path, _env(tmp_path))
    _config(repo, ci="commit")
    monkeypatch.chdir(repo)
    calls = []

    def boom(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("Resolver aus der Whitelist gerufen")

    monkeypatch.setattr(ga, "resolve_git_aliases", boom)
    monkeypatch.setattr(bash_gate, "_load_config_values", lambda: {})  # ohne Projekt-Whitelist
    assert bash_gate._is_whitelisted("git ci -m x") is False
    assert bash_gate._is_whitelisted("git commit -m x") is True  # Kontrolle: Whitelist wirkt
    assert not calls, calls


class _BrokenEnviron(Mapping):
    """environ, das bei jedem Zugriff wirft — weder OSError noch TimeoutExpired (AC-14 (a))."""
    def _boom(self, *_):
        raise RuntimeError("environ kaputt (Test)")
    __getitem__ = __iter__ = __len__ = _boom


@pytest.mark.parametrize("case", ["a-runner-raises-non-builtin", "a-environ-raises-non-builtin",
                                  "a-raises-builtin-only", "b-hook-copy-without-module"])
def test_ac14_resolver_failure_modes(case, request, tmp_path):
    """Given (a) interne Ausnahme im Resolver (Runner/environ werfen RuntimeError), (b) Hook-Kopie
    ohne git_alias.py / When (a) `git st` bzw. `git status`, (b) `git st` gesperrt / Then (a)
    `unresolved` bei Nicht-Builtin, sonst leere Sicht; (b) Exit 0 plus stderr-Hinweis git_alias."""
    if case.startswith("a-"):
        command = "git status" if "builtin-only" in case else "git st"
        environ = _environ(tmp_path) if "runner" in case else _BrokenEnviron()
        exc = None if "environ" in case else RuntimeError("Runner kaputt (Test)")
        view, _calls = _resolve(command, ST, tmp_path, environ, exc=exc)
        empty = not any((view.expansions, view.shell_bodies, view.unresolved,
                         view.unresolved_subs, view.resolutions))
        assert view.unresolved if command == "git st" else empty, f"{command}: {view}"
        return
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    for src in HOOKS_DIR.glob("*.py"):
        if src.name != "git_alias.py":
            shutil.copy2(src, hooks / src.name)
    proj, env = _copy(request, tmp_path)
    r = _gate(proj, "git st", env, hooks)
    _expect(r, 0)
    assert "git_alias" in r.stderr, f"kein stderr-Hinweis auf das fehlende git_alias: {r.stderr!r}"


AC15 = [
    _e("alias-unparsable", "git ci -m $'it\\'s'", 2, UNRESOLVED),
    _e("builtin-unparsable", "git status $'it\\'s'", 0),  # Wächter (heute grün)
    _e("runtime-subcommand", "CMD=commit; git $CMD -m x", 2, UNRESOLVED),
    _u("dollar", "git $CMD -m x", CI, "offen", 0),
    _u("command-substitution", "git $(echo commit) -m x", CI, "offen", 0),
    _u("glob-star", "git com* -m x", CI, "offen", 0),
    _u("glob-question", "git c?mmit -m x", CI, "offen", 0),
    _u("glob-bracket", "git c[o]mmit -m x", CI, "offen", 0),
    _u("brace", "git {ci,commit} -m x", CI, "offen", 0),
    _u("backtick-separator", "git -C . `echo ci` -m x", CI, "offen", 0),
    _u("in-alias-value", "git dyn", [("dyn", "$X -m y")], "offen"),
    _u("in-shell-body", "git sd", [("sd", "!git $CMD")], "offen"),
    _u("unparsable-non-builtin", "git ci -m $'it\\'s'", CI, "offen", 0),
    _u("unparsable-builtin", "git status $'it\\'s'", CI, "frei", 0),
    _e("adv-F006", "echo $'it\\'s';git ci -m x", 2, UNRESOLVED),
    _e("adv-F013", "git -c help.autocorrect=immediate comit -m x", 2, UNRESOLVED),
    _e("adv-F013-off", "git -c help.autocorrect=never comit -m x", 0),
    _e("adv-F018-timeout-s", "timeout -s KILL 5 git $(echo ci) -m x", 2, UNRESOLVED),
    _e("adv-F018-redirect", "2>/dev/null git $(echo ci) -m x", 2, UNRESOLVED),
    _e("adv-F018-flock-dotted", "flock /tmp/lockx git -c alias.a.b=commit a.b -m x", 2),
    _e("adv-F018-nice-sign", "nice -n +5 git -c alias.a.b=commit a.b -m x", 2),
    _e("adv-F018-mywrap-autocorrect", "mywrap git -c help.autocorrect=immediate comit -m x", 2, UNRESOLVED),
    *[_u(f"adv-F006-{i}", c, CI, "offen", 0) for i, c in enumerate(("echo $'it\\'s'&&git ci -m x",
      "(git ci -m x); echo $'it\\'s'", "git status $'it\\'s';git ci -m x"))],
]


@pytest.mark.parametrize("case", AC15)
def test_ac15_undeterminable_subcommand_is_checked(case, request, tmp_path):
    """Given gesperrt / When `git ci -m $'it\\'s'` (shlex-unzerlegbar), `git status $'it\\'s'`,
    `CMD=commit; git $CMD -m x` / Then Exit 2, Exit 0 (Wächter), Exit 2. unit-*: Shell-Syntax im
    Unterbefehl, Alias-Wert und Rumpf; unzerlegbarer Gesamtbefehl — jeweils ohne Abfrage."""
    if not _unit(case, tmp_path):
        _e2e(request, tmp_path, case)


@pytest.mark.parametrize("command,aliases,big", [
    pytest.param("git commit -m x # " + "git " * 50000, ST, True, id="adv-F008"),  # Polster: Erwähnungen `git git`
    pytest.param("git st; " * 20000, ST, True, id="adv-F008-work-limit"),
    pytest.param("grep " + "git core/ " * 25000, ST, False, id="adv-F008-mentions"),
    pytest.param("git a", [("a", "!" + "; ".join(["git a"] * 2000))], True, id="adv-F014")])
def test_ac9_work_limit_is_linear(command, aliases, big, tmp_path):
    """Adversary F008/F014: Laufzeit linear (< 3 s); > 64 Nicht-Builtin-Aufrufe/Rümpfe → sofort `unresolved`
    („zu groß“); Erwähnungen ohne möglichen Alias-Namen (F009) machen nie `unresolved`."""
    start = time.monotonic()
    view = _resolve(command, aliases, tmp_path, _environ(tmp_path))[0]
    assert time.monotonic() - start < 3, "Resolver zu langsam"
    assert big == any("zu groß" in r for r in view.unresolved) and (big or not view.unresolved), view.unresolved


def _section(rel: str, start: str, end: str) -> str:
    m = re.search(rf"{start}(.*?)(?={end}|\Z)", (REPO_ROOT / rel).read_text(), re.M | re.S)
    assert m, f"{rel}: Abschnitt {start!r} fehlt"
    return m.group(1)


def _lines_with(text: str, *anchors: str) -> list:
    return [line for line in text.splitlines() if all(a in line for a in anchors)]


@pytest.mark.parametrize("doc", ["workflow-guide", "claude-md", "readme", "changelog"])
def test_ac16_docs_mention_alias_resolution(doc):
    """Given die Doku-Stellen aus Spec Abschnitt 16 / Then die Anker: Fast-Path-Zeile mit `Alias`;
    CLAUDE.md (Baum, „Wichtige Dateien“) je `git_alias.py` + `KEIN Hook`; README `git_alias.py` +
    `NOT a hook`; CHANGELOG [Unreleased] mit `#281`, `Alias`, `nicht auflösbar`, `stage`."""
    if doc == "workflow-guide":
        guide = _section("docs/WORKFLOW_GUIDE.md", r"^### `bash_gate\.py`", r"^### ")
        fast = _lines_with(guide, "Fast Path")
        assert fast and any("Alias" in line for line in fast), f"Fast-Path-Zeile: {fast}"
    elif doc == "claude-md":
        for start in (r"^## Architektur\b", r"^## Wichtige Dateien\b"):
            section = _section("CLAUDE.md", start, r"^## ")
            assert _lines_with(section, "git_alias.py", "KEIN Hook"), f"CLAUDE.md {start}"
    elif doc == "readme":
        readme = (REPO_ROOT / "README.md").read_text()
        assert _lines_with(readme, "git_alias.py", "NOT a hook"), "README: Baum-Zeile fehlt"
    else:
        unreleased = _section("CHANGELOG.md", r"^## \[Unreleased\]", r"^## \[")
        missing = [a for a in ("#281", "Alias", "nicht auflösbar", "stage") if a not in unreleased]
        assert not missing, f"CHANGELOG [Unreleased] ohne {missing}"


def test_ac17_builtin_list_within_installed_git(tmp_path):
    """Given git ab 2.43 (sonst übersprungen) / When GIT_BUILTINS mit `git --list-cmds=builtins`
    verglichen wird / Then ist GIT_BUILTINS (frozenset) Teilmenge der installierten Builtins."""
    git = shutil.which("git")
    if not git:
        pytest.skip("git nicht installiert")
    env = _env(tmp_path)
    version = subprocess.run([git, "--version"], capture_output=True, text=True, env=env).stdout
    m = re.search(r"(\d+)\.(\d+)", version)
    if not m or (int(m.group(1)), int(m.group(2))) < (2, 43):
        pytest.skip(f"git älter als 2.43: {version.strip()}")
    installed = set(subprocess.run([git, "--list-cmds=builtins"], capture_output=True, text=True,
                                   env=env).stdout.split())
    builtins = _git_alias().GIT_BUILTINS
    assert isinstance(builtins, frozenset), type(builtins)
    assert {"add", "commit", "config", "diff", "log", "stage", "status"} <= builtins
    assert builtins <= installed, sorted(builtins - installed)
