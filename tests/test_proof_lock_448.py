"""TDD RED — #448: Abdichtung der Beleg-Schreibsperre (Simulator-Beleg).

Spec: docs/specs/feat-448-proof-lock-bypass.md (AC-1 … AC-21; AC-17 ist der Regressionslauf von
tests/test_evidence_gate_447.py, hier keine eigene Funktion). Die Fälle sind die Probe-Matrix aus
docs/context/feat-448-proof-lock-bypass.md: Angriff → Exit 2 mit Beleg-Meldung, Negativkontrolle
→ Exit 0. Echte Gates als Subprozess in einer Wegwerf-Sandbox (tmp_path, cwd dort); Helfer aus
#447 (`_sandbox`, `_bash_gate`, `_edit_gate`) bzw. #410 (1b/1c-Sandboxen). Symlinks werden real
angelegt, `resolve()` wird nicht gemockt (Ausnahme AC-19: erzwungene Ausnahme per sitecustomize).
"""

import importlib
import json
import os
import shlex
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_evidence_gate_447 import (  # noqa: E402
    ART, PROOF, RUN, WF, _bash_gate, _edit_gate, _env, _run, _sandbox, _write,
)
from test_bash_gate_state_integrity_410 import (  # noqa: E402
    PLUGIN_CONFIG as _PLUGIN_CONFIG_410, _gate as _gate_410,
    _sandbox_ohne_workflow as _sandbox_ohne_workflow_410,
    _worktree_sandbox as _worktree_sandbox_410,
)

LOCK_MSG = "Simulator-Beleg"  # Kern der 1d-/Edit-Gate-Meldung (#447), bleibt laut Spec erhalten


# ------------------------------------------------------------------ Aufbau
def _root(tmp_path) -> Path:
    """Sandbox mit erzwungenem Workflow; Beleg-Ordner und Beleg existieren real."""
    root = _sandbox(tmp_path)
    _write(root, PROOF, "beleg\n")
    (root / RUN).mkdir(parents=True, exist_ok=True)
    return root


def _with_link(tmp_path) -> Path:
    """Wie `_root`, dazu ein echter Symlink `lnk -> docs/artifacts/<wf>`."""
    root = _root(tmp_path)
    os.symlink(root / ART, root / "lnk")
    assert (root / "lnk").is_symlink() and (root / "lnk" / "simulator-run.txt").is_file()
    return root


def _with_symlinked_artifacts(tmp_path) -> Path:
    """Konsumenten-Fall: `docs/artifacts` selbst ist ein Symlink auf einen Ordner außerhalb."""
    root = _sandbox(tmp_path)
    store = (tmp_path / "store").resolve()
    (store / WF).mkdir(parents=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    os.symlink(store, root / "docs" / "artifacts")
    return root


def _blocked(r, cmd):
    assert r.returncode == 2 and LOCK_MSG in r.stderr, (
        f"Angriff kommt durch: {cmd!r}: rc={r.returncode} stderr={r.stderr.strip()[:200]!r}")


def _free(r, cmd):
    assert r.returncode == 0, (
        f"Fehlalarm: {cmd!r}: rc={r.returncode} stderr={r.stderr.strip()[:200]!r}")


def _ids(cases):
    return [c[0] for c in cases]


# ------------------------------------------------------------------ AC-1 verschachtelte Shells, eval
NESTED = [
    ("bash-c", f"bash -c 'echo x > {PROOF}'"),
    ("sh-c", f'sh -c "echo x > {PROOF}"'),
    ("bash-lc", f"bash -lc 'echo x > {PROOF}'"),
    ("bash-ec-cp", f"bash -ec 'cp /tmp/a {PROOF}'"),
    ("sudo-bash-c", f"sudo bash -c 'echo x > {PROOF}'"),
    ("bin-sh-c", f"/bin/sh -c 'echo x > {PROOF}'"),
    ("zsh-c-tee", f"zsh -c 'echo x | tee {PROOF}'"),
    ("eval-single", f"eval 'echo x > {PROOF}'"),
    ("eval-double-cp", f'eval "cp /tmp/a {PROOF}"'),
    ("bash-c-cd-in-payload", f"bash -c 'cd {ART} && echo x > simulator-run.txt'"),
    ("cd-before-bash-c", f"cd docs/artifacts && bash -c 'echo x > {WF}/simulator-run.txt'"),
]


@pytest.mark.parametrize("name,cmd", NESTED, ids=_ids(NESTED))
def test_nested_shell_and_eval_blocked(tmp_path, name, cmd):
    _blocked(_bash_gate(_root(tmp_path), cmd), cmd)


# ------------------------------------------------------------------ AC-2 Variablen im selben Befehl
VARIABLES = [
    ("assign-dollar", f"X={PROOF}; echo x > $X"),
    ("export-quoted", f'export X={PROOF}; echo x > "$X"'),
    ("assign-braces", f"X={PROOF}; echo x > ${{X}}"),
    ("assign-and-tee", f'X={PROOF} && echo x | tee "$X"'),
    ("dir-var-cp", f"D={ART}; cp /tmp/a $D/simulator-run.txt"),
]


@pytest.mark.parametrize("name,cmd", VARIABLES, ids=_ids(VARIABLES))
def test_variable_in_same_command_blocked(tmp_path, name, cmd):
    _blocked(_bash_gate(_root(tmp_path), cmd), cmd)


# ------------------------------------------------------------------ AC-3 Inline-Interpreter
INTERPRETERS = [
    ("python3-c-open-w", f"python3 -c \"open('{PROOF}','w').write('x')\""),
    ("python3-c-write-text",
     f"python3 -c \"import pathlib; pathlib.Path('{PROOF}').write_text('x')\""),
    ("python3-c-shutil-copy", f"python3 -c \"import shutil; shutil.copy('/tmp/a','{PROOF}')\""),
    ("python3-heredoc", f"python3 - <<'EOF'\nopen('{PROOF}','w').write('x')\nEOF"),
    ("pipe-into-python3", f"echo \"open('{PROOF}','w').write('x')\" | python3"),
    ("node-e-writeFileSync", f"node -e \"require('fs').writeFileSync('{PROOF}','x')\""),
    ("perl-e-open", f"perl -e 'open(F,\">{PROOF}\")'"),
    ("ruby-e-file-open", f"ruby -e \"File.open('{PROOF}','w')\""),
    # heute schon 2 (Heredoc-Rumpf wird mitzerlegt) — muss es bleiben
    ("bash-heredoc-redirect", f"bash <<'EOF'\necho x > {PROOF}\nEOF"),
]


@pytest.mark.parametrize("name,cmd", INTERPRETERS, ids=_ids(INTERPRETERS))
def test_inline_interpreter_with_write_indicator_blocked(tmp_path, name, cmd):
    _blocked(_bash_gate(_root(tmp_path), cmd), cmd)


# ------------------------------------------------------------------ AC-4 Zusatz-Schreiber
WRITERS = [
    ("rsync", f"rsync -a /tmp/a {PROOF}"),
    ("curl-o", f"curl -o {PROOF} https://example.com/x"),
    ("curl-output", f"curl --output {PROOF} https://example.com/x"),
    ("wget-O", f"wget -O {PROOF} https://example.com/x"),
    ("wget-output-document", f"wget --output-document {PROOF} https://example.com/x"),
    ("patch-file", f"patch {PROOF} /tmp/p.diff"),
    ("patch-o", f"patch -o {PROOF} /tmp/a /tmp/p.diff"),
    ("ed", f"ed {PROOF}"),
    ("ex", f"ex {PROOF}"),
    ("tar-C-art", f"tar -xf /tmp/a.tar -C {ART}"),
    ("tar-C-run", f"tar -C {RUN} -xf /tmp/a.tar"),
    ("unzip-d-art", f"unzip /tmp/a.zip -d {ART}"),
    ("unzip-d-run", f"unzip /tmp/a.zip -d {RUN}"),
]


@pytest.mark.parametrize("name,cmd", WRITERS, ids=_ids(WRITERS))
def test_additional_writers_blocked(tmp_path, name, cmd):
    _blocked(_bash_gate(_root(tmp_path), cmd), cmd)


# ------------------------------------------------------------------ AC-5 Befehlspräfixe
# Ziel steht immer im Argument des Kommandoworts: `präfix … > PROOF` blockt schon heute.
PREFIXES = [
    ("timeout-tee", f"echo x | timeout 5 tee {PROOF}"),
    ("nohup-tee", f"echo x | nohup tee {PROOF}"),
    ("nice-n-tee", f"echo x | nice -n 5 tee {PROOF}"),
    ("nice-cp", f"nice cp /tmp/a {PROOF}"),
    ("stdbuf-tee", f"echo x | stdbuf -oL tee {PROOF}"),
    ("time-tee", f"echo x | time tee {PROOF}"),
    ("time-cp", f"time cp /tmp/a {PROOF}"),
    ("exec-tee", f"exec tee {PROOF} < /tmp/a"),
    ("timeout-cp", f"timeout 5 cp /tmp/a {PROOF}"),
]


@pytest.mark.parametrize("name,cmd", PREFIXES, ids=_ids(PREFIXES))
def test_command_prefixes_blocked(tmp_path, name, cmd):
    _blocked(_bash_gate(_root(tmp_path), cmd), cmd)


# ------------------------------------------------------------------ AC-6 Hardlink auf den Beleg
HARDLINKS = [
    ("cp-l", f"cp -l {PROOF} hl"),
    ("ln-hard", f"ln {PROOF} hl"),
]


@pytest.mark.parametrize("name,cmd", HARDLINKS, ids=_ids(HARDLINKS))
def test_hardlink_on_proof_blocked(tmp_path, name, cmd):
    _blocked(_bash_gate(_root(tmp_path), cmd), cmd)


# ------------------------------------------------------------------ AC-7 Vorfahr- und Link-Regel
ANCESTOR = [
    ("mv-art-source", f"mv {ART} bk"),
    ("mv-art-target", f"mv bk {ART}"),
    ("mv-artifacts-source", "mv docs/artifacts old"),
    ("mv-proof-source", f"mv {PROOF} old.txt"),
    ("ln-s-art", f"ln -s {ART} l2"),
    ("ln-s-artifacts", "ln -s docs/artifacts l3"),
    ("ln-s-proof", f"ln -s {PROOF} pl"),
    ("cp-s-proof", f"cp -s {PROOF} pl"),
    ("cp-al-art", f"cp -al {ART} bk"),
    ("rsync-art-source", f"rsync -a {ART}/ bk/"),
    ("rsync-art-target", f"rsync -a bk/ {ART}/"),
    ("ln-s-then-write", f"ln -s {ART} l2 && echo x > l2/simulator-run.txt"),
    ("mv-write-mv-back", f"mv {ART} t && echo x > t/simulator-run.txt && mv t {ART}"),
]


@pytest.mark.parametrize("name,cmd", ANCESTOR, ids=_ids(ANCESTOR))
def test_ancestor_and_link_rule_blocked(tmp_path, name, cmd):
    _blocked(_bash_gate(_root(tmp_path), cmd), cmd)


# ------------------------------------------------------------------ AC-8 Symlink im Bash-Gate
BASH_LINK = [
    ("redirect-via-link", "lnk", "echo x > lnk/simulator-run.txt", 2),
    ("cp-via-link", "lnk", "cp /tmp/a lnk/simulator-run.txt", 2),
    ("redirect-via-link-run-dir", "lnk", "echo x > lnk/simulator-run/summary.json", 2),
    ("abs-redirect-via-link", "lnk", "echo x > {root}/lnk/simulator-run.txt", 2),
    # Gegenprobe: der Link selbst ist kein Block-Grund, nur der Beleg dahinter
    ("sanity-link-sibling", "lnk", "echo x > lnk/other.txt", 0),
    # Regressionsgrenze (ADR 2): `docs/artifacts` selbst ein Symlink -> Schutz bleibt
    ("artifacts-dir-is-link", "artifacts-link", f"echo x > {PROOF}", 2),
]

_SETUPS = {"lnk": _with_link, "artifacts-link": _with_symlinked_artifacts}


@pytest.mark.parametrize("name,setup,cmd,rc", BASH_LINK, ids=_ids(BASH_LINK))
def test_bash_symlink_resolution_blocked(tmp_path, name, setup, cmd, rc):
    root = _SETUPS[setup](tmp_path)
    cmd = cmd.format(root=root)
    r = _bash_gate(root, cmd)
    (_blocked if rc == 2 else _free)(r, cmd)


# ------------------------------------------------------------------ AC-9 Symlink im Edit-Gate
EDIT_LINK = [
    ("write-rel", "lnk", "Write", "lnk/simulator-run.txt", 2),
    ("write-abs", "lnk", "Write", "{root}/lnk/simulator-run.txt", 2),
    ("edit-rel", "lnk", "Edit", "lnk/simulator-run.txt", 2),
    ("edit-abs", "lnk", "Edit", "{root}/lnk/simulator-run.txt", 2),
    ("write-rel-run-dir", "lnk", "Write", "lnk/simulator-run/summary.json", 2),
    ("sanity-write-link-sibling", "lnk", "Write", "lnk/other.txt", 0),
    # Regressionsgrenze (AC-9, ADR 2): normpath ODER resolved, nie nur resolved
    ("artifacts-dir-is-link-rel", "artifacts-link", "Write", PROOF, 2),
    ("artifacts-dir-is-link-abs", "artifacts-link", "Write", "{root}/" + PROOF, 2),
]


@pytest.mark.parametrize("name,setup,tool,path,rc", EDIT_LINK, ids=_ids(EDIT_LINK))
def test_edit_gate_symlink_resolution_blocked(tmp_path, name, setup, tool, path, rc):
    root = _SETUPS[setup](tmp_path)
    path = path.format(root=root)
    r = _edit_gate(root, tool, path)
    (_blocked if rc == 2 else _free)(r, f"{tool} {path}")


# ------------------------------------------------------------------ AC-10 … AC-16 Negativkontrollen
@pytest.mark.parametrize("cmd", [
    f"python3 -c \"print(open('{PROOF}').read())\"",
    f"python3 -c \"import pathlib; print(pathlib.Path('{PROOF}').read_text())\"",
], ids=["open-read", "read-text"])
def test_negative_python_read_free(tmp_path, cmd):
    _free(_bash_gate(_root(tmp_path), cmd), cmd)


@pytest.mark.parametrize("cmd", [
    f"bash -c 'cat {PROOF}'",
    f'sh -c "grep -c ergebnis {PROOF}"',
], ids=["bash-c-cat", "sh-c-grep"])
def test_negative_bash_c_cat_free(tmp_path, cmd):
    _free(_bash_gate(_root(tmp_path), cmd), cmd)


@pytest.mark.parametrize("cmd", [
    f"bash scripts/x.sh {PROOF}",
    f"sh scripts/x.sh {PROOF}",
    f"python3 scripts/x.py {PROOF}",
], ids=["bash-script", "sh-script", "python-script"])
def test_negative_script_with_proof_argument_free(tmp_path, cmd):
    _free(_bash_gate(_root(tmp_path), cmd), cmd)


@pytest.mark.parametrize("cmd", [
    f'echo "{PROOF}" > "$LOG"',
    f'echo "{PROOF}" > $LOG',
    f'echo "{PROOF}" | tee "$LOG"',
], ids=["quoted-var", "bare-var", "tee-var"])
def test_negative_echo_proof_text_to_variable_free(tmp_path, cmd):
    _free(_bash_gate(_root(tmp_path), cmd), cmd)


@pytest.mark.parametrize("cmd", [
    "curl -o /tmp/x https://example.com/x",
    "tar -xf /tmp/a.tar -C /tmp",
    "wget -O /tmp/x https://example.com/x",
    "unzip /tmp/a.zip -d /tmp/x",
    "rsync -a /tmp/a /tmp/b",
], ids=["curl-o-tmp", "tar-C-tmp", "wget-O-tmp", "unzip-d-tmp", "rsync-tmp"])
def test_negative_curl_tar_other_target_free(tmp_path, cmd):
    _free(_bash_gate(_root(tmp_path), cmd), cmd)


@pytest.mark.parametrize("cmd", [
    f"python3 scripts/sim_proof.py {WF} LooseEndsUITests {RUN}/run.xcresult "
    f"'** TEST SUCCEEDED **' 'scripts/sim.sh test-proof' 0",
    f"scripts/sim.sh test-proof {WF} LooseEndsUITests",
], ids=["sim_proof-py", "sim-sh"])
def test_negative_generator_call_free(tmp_path, cmd):
    _free(_bash_gate(_root(tmp_path), cmd), cmd)


DOC_SIBLING = [
    ("echo-mention-readme", "bash", f'echo "siehe {PROOF}" >> README.md'),
    ("echo-sibling", "bash", f"echo x > {ART}/other.txt"),
    ("cp-sibling", "bash", f"cp /tmp/a {ART}/other.txt"),
    ("write-sibling", "Write", f"{ART}/other.txt"),
]


@pytest.mark.parametrize("name,kind,arg", DOC_SIBLING, ids=_ids(DOC_SIBLING))
def test_negative_doc_mention_and_sibling_file_free(tmp_path, name, kind, arg):
    root = _root(tmp_path)
    r = _bash_gate(root, arg) if kind == "bash" else _edit_gate(root, kind, arg)
    _free(r, arg)


# ------------------------------------------------------------------ AC-18 1b/1c unverändert
# Snapshot der heutigen Tabelle (3.42.0); neue Schreiber gehören in eine eigene 1d-Tabelle (#452).
CONFIG_WRITERS_SNAPSHOT = {"cp", "install", "ln", "mv", "rm", "unlink", "tee", "truncate",
                           "touch", "sed", "perl", "git", "dd", "yq"}
CFG_418 = "openspec.yaml"
# Gemessen gegen 3.42.0: alle neuen Schreiber heute 0 in 1b/1c, die Sanity-Umleitung 2.
LOCK_1B = [(f"curl -o {CFG_418} https://e.x", 0), (f"curl --output {CFG_418} https://e.x", 0),
           (f"wget -O {CFG_418} https://e.x", 0), (f"rsync -a x {CFG_418}", 0),
           ("tar -xf a.tar -C .", 0), ("unzip a.zip -d .", 0), (f"patch {CFG_418} p.diff", 0),
           (f"patch -o {CFG_418} a p.diff", 0), (f"echo x > {CFG_418}", 2)]
LOCK_1C = [("curl -o {main}/a.txt https://e.x", 0), ("wget -O {main}/a.txt https://e.x", 0),
           ("rsync -a f {main}/a.txt", 0), ("tar -xf a.tar -C {main}", 0),
           ("unzip a.zip -d {main}", 0), ("patch {main}/a.txt p.diff", 0),
           ("echo x > {main}/a.txt", 2)]


@pytest.mark.parametrize("part", ["config_writers_snapshot", "lock_1b_config", "lock_1c_main"])
def test_config_and_main_repo_locks_unchanged(tmp_path, part):
    if part == "config_writers_snapshot":
        bash_gate = importlib.import_module("bash_gate")
        assert set(bash_gate._CONFIG_WRITERS) == CONFIG_WRITERS_SNAPSHOT, (
            f"_CONFIG_WRITERS verändert: {sorted(set(bash_gate._CONFIG_WRITERS) ^ CONFIG_WRITERS_SNAPSHOT)}")
        assert bash_gate._CONFIG_WRITERS["cp"] is bash_gate._copy_targets
        assert bash_gate._CONFIG_WRITERS["sed"] is bash_gate._sed_targets
        return
    if part == "lock_1b_config":
        root = _sandbox_ohne_workflow_410(tmp_path / "r")
        (root / CFG_418).write_text(_PLUGIN_CONFIG_410)
        runs = [(c, rc, _gate_410(c, root)) for c, rc in LOCK_1B]
    else:
        main, wt = _worktree_sandbox_410(tmp_path / "m", CFG_418)
        (main / "a.txt").write_text("a\n")
        (wt / "f").write_text("f\n")
        runs = [(c.format(main=main), rc, _gate_410(c.format(main=main), wt, wt))
                for c, rc in LOCK_1C]
    wrong = [f"{c!r}: rc={r.returncode} (soll {rc}) {r.stderr.strip()[:120]!r}"
             for c, rc, r in runs if r.returncode != rc]
    assert not wrong, f"{part} verhält sich anders als vor #448:\n" + "\n".join(wrong)


# ------------------------------------------------------------------ AC-19 fail-open
_RAISE_RESOLVE = (
    "import pathlib\n_orig = pathlib.Path.resolve\n"
    "def _boom(self, *a, **k):\n"
    "    if 'lnk' in str(self):\n        raise OSError('erzwungen (#448 AC-19)')\n"
    "    return _orig(self, *a, **k)\n"
    "pathlib.Path.resolve = _boom\n")
_RAISE_NORMPATH = (
    "import os.path, posixpath\n_orig = posixpath.normpath\n"
    "def _boom(p):\n"
    "    if 'simulator-run' in str(p):\n        raise ValueError('erzwungen (#448 AC-19)')\n"
    "    return _orig(p)\n"
    "posixpath.normpath = _boom\nos.path.normpath = _boom\n")
FAIL_OPEN = [
    ("broken-quote-dq", f'echo "x > {PROOF}', None),
    ("broken-quote-sq-tail", f"echo x > {PROOF} 'oops", None),
    ("resolve-raises", "echo x > lnk/simulator-run.txt", _RAISE_RESOLVE),
    ("normpath-raises", f"echo x > {PROOF}", _RAISE_NORMPATH),
]


@pytest.mark.parametrize("name,cmd,sitecustomize", FAIL_OPEN, ids=_ids(FAIL_OPEN))
def test_fail_open_on_exception(tmp_path, name, cmd, sitecustomize):
    root = _with_link(tmp_path)
    if sitecustomize is None:
        r = _bash_gate(root, cmd)
    else:
        sc = tmp_path / "sitecustomize_dir"
        _write(sc, "sitecustomize.py", sitecustomize)
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
        r = _run("bash_gate.py", [], root, env=_env(root, PYTHONPATH=str(sc)), stdin=payload)
    _free(r, f"[{name}] {cmd}")


# ------------------------------------------------------------------ AC-20 Tiefe / Parse-Fehler
def _nest(inner: str, depth: int) -> str:
    for _ in range(depth):
        inner = "bash -c " + shlex.quote(inner)
    return inner


DEPTH = [
    ("depth2-write", _nest(f"echo x > {PROOF}", 2), 2),
    ("depth3-write", _nest(f"echo x > {PROOF}", 3), 2),
    ("depth4-write", _nest(f"echo x > {PROOF}", 4), 2),
    ("depth5-tee", _nest(f"echo x | tee {PROOF}", 5), 2),
    ("depth4-cat-free", _nest(f"cat {PROOF}", 4), 0),
    ("depth5-cat-free", _nest(f"cat {PROOF}", 5), 0),
    ("payload-parse-error-write", f"bash -c 'echo \"x > {PROOF}'", 2),
    ("payload-parse-error-cat-free", f"bash -c 'cat \"{PROOF}'", 0),
]


@pytest.mark.parametrize("name,cmd,rc", DEPTH, ids=_ids(DEPTH))
def test_depth_and_parse_error_fallback(tmp_path, name, cmd, rc):
    r = _bash_gate(_root(tmp_path), cmd)
    (_blocked if rc == 2 else _free)(r, cmd)


# ------------------------------------------------------------------ AC-21 Meldung nennt Vorfahr-Regel
MESSAGE = [
    ("mv-art", f"mv {ART} bk"),
    ("ln-s-art", f"ln -s {ART} l2"),
    ("plain-redirect", f"echo x > {PROOF}"),  # Erkennung heute schon da, Meldung nicht
]


@pytest.mark.parametrize("name,cmd", MESSAGE, ids=_ids(MESSAGE))
def test_error_message_names_ancestor_rule(tmp_path, name, cmd):
    r = _bash_gate(_root(tmp_path), cmd)
    _blocked(r, cmd)
    low = r.stderr.lower()
    missing = [w for w in ("umbenennen", "verlinken", "docs/artifacts") if w not in low]
    assert not missing, f"Meldung nennt die Vorfahr-Regel nicht (fehlt: {missing}): {r.stderr!r}"
