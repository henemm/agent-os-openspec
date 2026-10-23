"""TDD RED — #453: Restlücken der Beleg-Schreibsperre 1d schließen.

Spec: docs/specs/fix-453-proof-lock-gaps.md (AC-1 … AC-18). Die Fälle sind die Probe-Matrix aus
docs/context/fix-453-proof-lock-gaps.md ("Ist-Stand per Probe"): Fälschungs-Angriff → Exit 2 mit
Beleg-Meldung, Negativkontrolle → Exit 0. Echtes `bash_gate.py` als Subprozess in einer
Wegwerf-Sandbox (tmp_path, cwd dort); Helfer aus #447/#448. Dateien für Glob-, chmod- und
Rekursiv-Kopie-Fälle werden real angelegt; Spec-Pfade unter `/tmp/...` werden auf Unterordner von
tmp_path abgebildet (außerhalb der Sandbox, wie `/tmp`). Kein Mocking (Ausnahme AC-18: erzwungene
Ausnahme per sitecustomize, Muster aus #448 AC-19).

Abkürzungen wie in der Spec: P = ART/simulator-run.txt, ART = docs/artifacts/wf-447,
RUN = ART/simulator-run.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_evidence_gate_447 import (  # noqa: E402
    ART, PROOF, RUN, _bash_gate, _env, _run, _sandbox, _write,
)

P = PROOF
LOCK_MSG = "Simulator-Beleg"  # Kern der 1d-Meldung (#447)
REPO = Path(__file__).resolve().parent.parent
BASE_COMMIT = "b599ee3"


# ------------------------------------------------------------------ Aufbau
def _root(tmp_path) -> Path:
    """Sandbox mit erzwungenem Workflow; Beleg, Beleg-Ordner, Nachbardatei, fremder WF-Ordner."""
    root = _sandbox(tmp_path)
    _write(root, PROOF, "beleg\n")
    (root / RUN).mkdir(parents=True, exist_ok=True)
    _write(root, f"{ART}/shot.png", "png\n")
    (root / "docs/artifacts/other-wf").mkdir(parents=True, exist_ok=True)
    return root


def _ext(tmp_path) -> Path:
    """Ordner außerhalb der Sandbox — Ersatz für die `/tmp/...`-Pfade der Spec."""
    ext = (tmp_path / "ext").resolve()
    ext.mkdir(parents=True, exist_ok=True)
    return ext


def _blocked(r, cmd):
    assert r.returncode == 2 and LOCK_MSG in r.stderr, (
        f"Angriff kommt durch: {cmd!r}: rc={r.returncode} stderr={r.stderr.strip()[:200]!r}")


def _free(r, cmd):
    assert r.returncode == 0, (
        f"Fehlalarm: {cmd!r}: rc={r.returncode} stderr={r.stderr.strip()[:200]!r}")


def _check(r, cmd, rc):
    (_blocked if rc == 2 else _free)(r, cmd)


def _ids(cases):
    return [c[0] for c in cases]


# ------------------------------------------------------------------ AC-1 Interpreter-Optionen (F001)
INTERP_OPTS = [
    ("python3-W", f"python3 -W ignore -c \"open('{P}','w')\"", 2),
    ("python3-X", f"python3 -X utf8 -c \"open('{P}','w').write('x')\"", 2),
    ("node-r", f"node -r foo -e \"require('fs').writeFileSync('{P}','x')\"", 2),
    ("node-eval", f"node --eval \"require('fs').writeFileSync('{P}','x')\"", 2),
    ("node-p", f"node -p \"require('fs').writeFileSync('{P}','x')\"", 2),
    ("python3-m-module-free", f"python3 -m modul {P}", 0),
]


@pytest.mark.parametrize("name,cmd,rc", INTERP_OPTS, ids=_ids(INTERP_OPTS))
def test_interpreter_options_with_value_blocked(tmp_path, name, cmd, rc):
    _check(_bash_gate(_root(tmp_path), cmd), cmd, rc)


# ------------------------------------------------------------------ AC-2 neue Präfixe (F002)
NEW_PREFIXES = [
    ("doas", f"doas tee {P}"),
    ("busybox", f"busybox tee {P}"),
    ("flock-cmd", f"flock /tmp/l tee {P}"),
    ("flock-c", f"flock /tmp/l -c 'echo x > {P}'"),
    ("ionice", f"ionice -c 3 tee {P}"),
    ("setsid", f"setsid tee {P}"),
    ("taskset", f"taskset 1 tee {P}"),
    ("chronic", f"chronic tee {P}"),
    ("xargs", f"echo x | xargs tee {P}"),
]


@pytest.mark.parametrize("name,cmd", NEW_PREFIXES, ids=_ids(NEW_PREFIXES))
def test_new_command_prefixes_blocked(tmp_path, name, cmd):
    _blocked(_bash_gate(_root(tmp_path), cmd), cmd)


# ------------------------------------------------------------------ AC-3 Glob und Brace (F003a)
GLOB_BRACE = [
    ("glob-question", f"tee {ART}/simulator-run.t?t", 2),
    ("brace-list", f"tee {ART}/simulator-run.{{txt,x}}", 2),
    # Glob ohne Treffer auf dem Dateisystem bleibt literal und trifft den Beleg nicht
    ("glob-no-hit-free", f"tee {ART}/simulator-run.q?q", 0),
]


@pytest.mark.parametrize("name,cmd,rc", GLOB_BRACE, ids=_ids(GLOB_BRACE))
def test_glob_and_brace_targets_blocked(tmp_path, name, cmd, rc):
    root = _root(tmp_path)
    assert (root / P).is_file()  # der Glob `?` muss eine vorhandene Datei treffen
    _check(_bash_gate(root, cmd), cmd, rc)


# ------------------------------------------------------------------ AC-4 cp -t (F003b)
CP_TARGET = [
    ("cp-vt", "cp -vt {art} {ext}/simulator-run.txt", 2),
    ("cp-t-attached", "cp -t{art} {ext}/simulator-run.txt", 2),
    ("cp-target-directory", "cp --target-directory {art} {ext}/simulator-run.txt", 2),
    ("cp-t-elsewhere-free", "cp -t {ext}/out {ext}/simulator-run.txt", 0),
]


@pytest.mark.parametrize("name,cmd,rc", CP_TARGET, ids=_ids(CP_TARGET))
def test_cp_target_directory_blocked(tmp_path, name, cmd, rc):
    root, ext = _root(tmp_path), _ext(tmp_path)
    _write(ext, "simulator-run.txt", "fake\n")
    (ext / "out").mkdir()
    cmd = cmd.format(art=ART, ext=ext)
    _check(_bash_gate(root, cmd), cmd, rc)


# ------------------------------------------------------------------ AC-5 curl -oDATEI (F003c)
CURL_ATTACHED = [
    ("curl-o-attached", f"curl -o{P} https://x", 2),
    ("curl-bundle-sSo", f"curl -sSo{P} https://x", 2),
    ("curl-o-attached-elsewhere-free", "curl -o/tmp/x https://x", 0),
]


@pytest.mark.parametrize("name,cmd,rc", CURL_ATTACHED, ids=_ids(CURL_ATTACHED))
def test_curl_attached_output_value_blocked(tmp_path, name, cmd, rc):
    _check(_bash_gate(_root(tmp_path), cmd), cmd, rc)


# ------------------------------------------------------------------ AC-6 git mv (F003d)
GIT_MV = [
    ("git-mv-art-source", f"git mv {ART} t", 2),
    ("git-mv-art-target", f"git mv fake-dir {ART}", 2),
    ("git-mv-unrelated-free", "git mv a.txt b.txt", 0),
]


@pytest.mark.parametrize("name,cmd,rc", GIT_MV, ids=_ids(GIT_MV))
def test_git_mv_ancestor_blocked(tmp_path, name, cmd, rc):
    _check(_bash_gate(_root(tmp_path), cmd), cmd, rc)


# ------------------------------------------------------------------ AC-7 cp -r in den Bereich (F003e)
RECURSIVE = [
    # Quelle `X` (Basisname wf-447) mit simulator-run.txt -> docs/artifacts/wf-447/simulator-run.txt
    ("cp-r-dir-into-artifacts", "cp -r {ext}/wf-447 docs/artifacts/", 2),
    # Quelle `X/.` mit simulator-run.txt -> ART/simulator-run.txt
    ("cp-r-dot-into-art", "cp -r {ext}/fake/. " + ART + "/", 2),
    # Quelle ohne simulator-run-Eintrag bleibt frei
    ("cp-r-screenshots-free", "cp -r screenshots/ " + ART + "/", 0),
]


@pytest.mark.parametrize("name,cmd,rc", RECURSIVE, ids=_ids(RECURSIVE))
def test_recursive_copy_into_area_blocked_only_with_proof_entry(tmp_path, name, cmd, rc):
    root, ext = _root(tmp_path), _ext(tmp_path)
    _write(ext, "wf-447/simulator-run.txt", "fake\n")
    _write(ext, "fake/simulator-run.txt", "fake\n")
    _write(root, "screenshots/a.png", "png\n")
    _write(root, "screenshots/b.png", "png\n")
    cmd = cmd.format(ext=ext)
    _check(_bash_gate(root, cmd), cmd, rc)


# ------------------------------------------------------------------ AC-8 shred/chmod/chown (F003f)
EXACT_DESTROY = [
    ("shred-u-proof", f"shred -u {P}", 2),
    ("chmod-000-proof", f"chmod 000 {P}", 2),
    ("chown-root-proof", f"chown root {P}", 2),
    ("shred-u-sibling-free", f"shred -u {ART}/shot.png", 0),
    ("chmod-644-sibling-free", f"chmod 644 {ART}/shot.png", 0),
]


@pytest.mark.parametrize("name,cmd,rc", EXACT_DESTROY, ids=_ids(EXACT_DESTROY))
def test_shred_chmod_chown_on_exact_proof_blocked(tmp_path, name, cmd, rc):
    _check(_bash_gate(_root(tmp_path), cmd), cmd, rc)


# ------------------------------------------------------------------ AC-9 Präfix-Umgebung (F005)
CHILD_ENV = [
    ("assign-sh-c", f"X={P} sh -c 'tee $X <<< x'"),
    ("assign-python-environ", f"X={P} python3 -c \"import os; open(os.environ['X'],'w')\""),
]


@pytest.mark.parametrize("name,cmd", CHILD_ENV, ids=_ids(CHILD_ENV))
def test_prefix_assignment_into_child_environment_blocked(tmp_path, name, cmd):
    _blocked(_bash_gate(_root(tmp_path), cmd), cmd)


# ------------------------------------------------------------------ AC-10 Shell-Aufrufe (F006)
SHELL_CALLS = [
    ("python-os-system", f"python3 -c \"import os; os.system('echo x > {P}')\""),
    ("python-subprocess-list", f"python3 -c \"import subprocess; subprocess.run(['tee','{P}'])\""),
    ("node-execSync", f"node -e \"require('child_process').execSync('cp /tmp/a {P}')\""),
    ("perl-system", f"perl -e 'system(\"cp /tmp/a {P}\")'"),
]


@pytest.mark.parametrize("name,cmd", SHELL_CALLS, ids=_ids(SHELL_CALLS))
def test_inline_shell_calls_blocked(tmp_path, name, cmd):
    _blocked(_bash_gate(_root(tmp_path), cmd), cmd)


# ------------------------------------------------------------------ AC-11 tar packen (F007)
TAR_CREATE = [
    ("tar-cf", f"tar -cf {P} {ART}/shot.png", 2),
    ("tar-czf-oldstyle", f"tar czf {P} {ART}/shot.png", 2),
    ("tar-cvf", f"tar -cvf {P} {ART}/shot.png", 2),
    ("tar-file-eq-c", f"tar --file={P} -c {ART}/shot.png", 2),
    ("tar-xf-proof-free", f"tar -xf {P} -C /tmp/out", 0),
    ("tar-cf-elsewhere-free", f"tar -cf /tmp/a.tar {ART}", 0),
]


@pytest.mark.parametrize("name,cmd,rc", TAR_CREATE, ids=_ids(TAR_CREATE))
def test_tar_create_with_proof_archive_blocked(tmp_path, name, cmd, rc):
    _check(_bash_gate(_root(tmp_path), cmd), cmd, rc)


# ------------------------------------------------------------------ AC-12 lesen + woanders schreiben (F004)
READ_ELSEWHERE = [
    ("read-proof-write-elsewhere-free",
     f"python3 -c \"d=open('{P}').read(); open('/tmp/out','w').write(d)\"", 0),
    ("same-statement-write-blocked", f"python3 -c \"open('{P}','w')\"", 2),
]


@pytest.mark.parametrize("name,cmd,rc", READ_ELSEWHERE, ids=_ids(READ_ELSEWHERE))
def test_inline_read_proof_write_elsewhere_free(tmp_path, name, cmd, rc):
    _check(_bash_gate(_root(tmp_path), cmd), cmd, rc)


# ------------------------------------------------------------------ AC-13 einstufige Variablen
VAR_TRACKING = [
    ("python-str-var", f"python3 -c \"p='{P}'; open(p,'w')\""),
    ("python-path-var",
     f"python3 -c \"from pathlib import Path; p=Path('{P}'); p.write_text('x')\""),
]


@pytest.mark.parametrize("name,cmd", VAR_TRACKING, ids=_ids(VAR_TRACKING))
def test_inline_single_level_variable_tracking_blocked(tmp_path, name, cmd):
    _blocked(_bash_gate(_root(tmp_path), cmd), cmd)


# ------------------------------------------------------------------ AC-14 Pflicht-FREE-Liste
FREE_LIST = [
    ("cat-proof", f"cat {P}"),
    ("tar-cf-from-art", f"tar -cf /tmp/a.tar {ART}"),
    ("rm-rf-other-wf", "rm -rf docs/artifacts/other-wf"),
    ("mkdir-p-art", f"mkdir -p {ART}"),
    ("rm-f-sibling", f"rm -f {ART}/shot.png"),
    ("grep-tee-proof", f"grep tee {P}"),
    ("git-add-proof", f"git add {P}"),
    ("ls-la-art", f"ls -la {ART}"),
    ("python-print-read", f"python3 -c \"print(open('{P}').read())\""),
    ("echo-proof", f"echo {P}"),
    ("git-log-proof", f"git log -- {P}"),
    ("tar-xf-elsewhere", "tar -xf /tmp/a.tar -C /tmp/out"),
    ("assign-tee-same-command", f"X={P} tee $X <<< x"),
]


@pytest.mark.parametrize("name,cmd", FREE_LIST, ids=_ids(FREE_LIST))
def test_mandatory_free_list(tmp_path, name, cmd):
    _free(_bash_gate(_root(tmp_path), cmd), cmd)


# ------------------------------------------------------------------ AC-15 Zerstörer bleiben frei
DESTROYERS = [
    ("rm-rf-art", f"rm -rf {ART}"),
    ("rm-rf-artifacts", "rm -rf docs/artifacts"),
    ("git-rm-r-art", f"git rm -r {ART}"),
    ("mkdir-p-run-sub", f"mkdir -p {RUN}/x"),
]


@pytest.mark.parametrize("name,cmd", DESTROYERS, ids=_ids(DESTROYERS))
def test_destroyers_remain_free(tmp_path, name, cmd):
    _free(_bash_gate(_root(tmp_path), cmd), cmd)


# ------------------------------------------------------------------ AC-16 ruby -E
RUBY_E = [
    ("ruby-E-encoding-free", f"ruby -E utf-8 skript.rb {P}", 0),
    ("ruby-e-code-blocked", f"ruby -e \"File.write('{P}','x')\"", 2),
]


@pytest.mark.parametrize("name,cmd,rc", RUBY_E, ids=_ids(RUBY_E))
def test_ruby_encoding_option_not_code(tmp_path, name, cmd, rc):
    _check(_bash_gate(_root(tmp_path), cmd), cmd, rc)


# ------------------------------------------------------------------ AC-17 geteilte Bausteine
def _segment(source: str, name: str) -> str:
    """Quelltext des Top-Level-Knotens `name` (Funktion oder Zuweisung) per ast."""
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node)
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            return ast.get_source_segment(source, node)
    raise AssertionError(f"{name} nicht gefunden")


@pytest.mark.parametrize("part", ["_CONFIG_WRITERS", "_copy_targets", "hook_utils"])
def test_shared_pieces_unchanged_and_existing_suites_green(part):
    """Statische Prüfung gegen den Stand vor #453 (Commit b599ee3).

    Die vier Regressionssuiten (tests/test_proof_lock_448.py, tests/test_evidence_gate_447.py,
    tests/test_bash_gate_config_lock_418.py, tests/test_bash_gate_main_write_417.py) laufen
    separat (Test Plan), nicht als Subprozess dieses Tests — zu teuer.
    """
    if part == "hook_utils":
        r = subprocess.run(["git", "diff", "--quiet", BASE_COMMIT, "--",
                            "core/hooks/hook_utils.py"], cwd=str(REPO), capture_output=True,
                           text=True, env=_env())
        assert r.returncode == 0, f"core/hooks/hook_utils.py verändert: {r.stderr.strip()}"
        return
    old = subprocess.run(["git", "show", f"{BASE_COMMIT}:core/hooks/bash_gate.py"],
                         cwd=str(REPO), capture_output=True, text=True, env=_env())
    assert old.returncode == 0, old.stderr
    new = (REPO / "core/hooks/bash_gate.py").read_text()
    assert _segment(new, part) == _segment(old.stdout, part), f"{part} verändert gegenüber {BASE_COMMIT}"


# ------------------------------------------------------------------ AC-18 fail-open
_RAISE_GLOB = (
    "import glob\n"
    "def _boom(*a, **k):\n    raise OSError('erzwungen (#453 AC-18)')\n"
    "glob.glob = _boom\nglob.iglob = _boom\n")
FAIL_OPEN = [
    ("broken-quote-dq", f'echo "x > {P}', None),
    ("broken-quote-sq-tail", f"echo x > {P} 'oops", None),
    ("glob-raises-harmless", f"ls {ART}/shot.p?g", _RAISE_GLOB),
    ("glob-raises-glob-target", f"tee {ART}/simulator-run.t?t", _RAISE_GLOB),
]


@pytest.mark.parametrize("name,cmd,sitecustomize", FAIL_OPEN, ids=_ids(FAIL_OPEN))
def test_fail_open_on_exception_preserved(tmp_path, name, cmd, sitecustomize):
    root = _root(tmp_path)
    if sitecustomize is None:
        r = _bash_gate(root, cmd)
    else:
        sc = tmp_path / "sitecustomize_dir"
        _write(sc, "sitecustomize.py", sitecustomize)
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
        r = _run("bash_gate.py", [], root, env=_env(root, PYTHONPATH=str(sc)), stdin=payload)
    _free(r, f"[{name}] {cmd}")
