"""Issue #357: Heredoc-Bodies werden nur entfernt, wenn sie zweifelsfrei Daten sind.

Vorher (Regex je Zeile) konnte ein falsch erkannter Oeffner — in Quotes, im
Kommentar, in Arithmetik, im Body eines Interpreter-Heredocs — die folgenden,
ECHTEN Befehle aus dem Scan von bash_gate, secrets_guard und (seit #276)
secret_egress_guard entfernen. Jeder Fall unten ist so gebaut, dass bash die
markierte Zeile tatsaechlich ausfuehrt. Fail-closed heisst: im Zweifel bleibt
der Befehl unveraendert.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

from hook_utils import strip_heredoc_bodies  # noqa: E402

REAL = "touch .claude/user_approved_x"  # die Zeile, die bash wirklich ausfuehrt

# Faelle, in denen REAL ausserhalb jedes echten Heredoc-Bodys steht.
ATTACKS = {
    "opener_in_double_quotes": f'echo "<<EOF"\n{REAL}\nEOF',
    "opener_in_comment": f"echo hi # <<EOF\n{REAL}\nEOF",
    "arithmetic_shift": f"n=1; echo $((1<<n))\n{REAL}\nn",
    "old_arithmetic": f"echo $[ 1 << y ]\n{REAL}\ny",
    "param_expansion": f"echo ${{x:-<<EOF}}\n{REAL}\nEOF",
    "backslash_quoted_marker": f"cat <<E\\OF\nbody\nEOF\n{REAL}\nE",
    "dash_marker_with_space": f"cat << -EOF\ndata\n-EOF\n{REAL}\nEOF",
    "hash_midword": f"echo a#b <<EOF\ncat <<X\nEOF\n{REAL}\nX",
    "cr_in_marker": f"cat <<EOF\r\ndata\nEOF\r\n{REAL}\nEOF",
    "opener_inside_interpreter_body": f'python3 - <<\'EOF\'\ns = "<<FOO"\nEOF\n{REAL}\nFOO',
    "quoted_marker_with_suffix": f"cat <<\"EOF\"x\nb\nEOF\n{REAL}\nEOFx",
    "multiline_double_quote": f'echo "start\ncat <<EOF\n"; {REAL}\nEOF',
    "single_quote_trick": f"echo '$(cat <<'EOF'\n'; {REAL}\nEOF",
    "backtick": f"echo `cat <<EOF`\n{REAL}\nEOF",
    "line_continuation": f"cat <<EOF \\\n> x\n{REAL}\nEOF",
    "double_bracket": f"[[ a << b ]]\n{REAL}\nb",
    "unclosed": f"cat <<EOF\n{REAL}",
    # Differenztest gegen bash, Klasse A: Parser lief aus dem Takt.
    "hash_after_subshell": f"(true)#<<E\n{REAL}\nE",
    "hash_after_case_pattern": f"case x in x)#<<E\n{REAL}\nE\nesac",
    "hash_after_escaped_space": f"echo \\ #<<E\ncat <<F\nE\n{REAL}\nF",
    "case_inside_subst": (f"echo \"$(case x in x) cat <<'E'\n\"\ncat <<'F'\nE\nesac)\"\n"
                          f"{REAL}\nF"),
    "terminator_with_paren_in_subst": f"echo \"$(cat <<'E'\ndata\nE)\"\n{REAL}\nE\n)\"",
    "pending_across_subst_newline": f"cat <<E; echo \"$(true\n{REAL}\nE\n)\"",
}

# Faelle, in denen REAL im Body steht, der aber AUSGEFUEHRT wird.
EXECUTED_BODIES = {
    "pipe_on_opener_line": f"cat <<'EOF' |\n{REAL}\nEOF\nbash",
    "pipe_to_interpreter_later": f"cat <<'EOF' > /dev/stdout\n{REAL}\nEOF\n| sh",
    "source_stdin": f"source /dev/stdin <<'EOF'\n{REAL}\nEOF",
    "dot_stdin": f". /dev/stdin <<'EOF'\n{REAL}\nEOF",
    "eval_cmdsubst": f"eval \"$(cat <<'EOF'\n{REAL}\nEOF\n)\"",
    "eval_later_line": f"x=\"$(cat <<'EOF'\n{REAL}\nEOF\n)\"\neval \"$x\"",
    "assignment_then_exec": f"x=$(cat <<'EOF'\n{REAL}\nEOF\n)\n$x",
    "subst_as_command_word": f"\"$(cat <<'EOF'\n{REAL}\nEOF\n)\"",
    "unquoted_marker_with_expansion": f"cat <<EOF > notes.md\n$({REAL})\nEOF",
    "xargs": f"cat <<'EOF' | xargs -I{{}} sh -c {{}}\n{REAL}\nEOF",
    "bash_interpreter": f"bash <<'EOF'\n{REAL}\nEOF",
    # Differenztest gegen bash (Pruefrunde zu #362), Klasse B: Konsumenten,
    # die eine Namens-Negativliste nicht kennt -> Positivliste noetig.
    "pipe_to_shell_var": f"cat <<'E' | $SHELL\n{REAL}\nE",
    "pipe_to_quoted_shell_var": f"cat <<'E' | \"$SHELL\"\n{REAL}\nE",
    "pipe_to_sed_e": f"cat <<'E' | sed e\n{REAL}\nE",
    "pipe_to_awk_system": f"cat <<'E' | awk '{{system($0)}}'\n{REAL}\nE",
    "pipe_to_escaped_name": f"cat <<'E' | s\\h\n{REAL}\nE",
    "pipe_to_split_name": f"cat <<'E' | bas''h\n{REAL}\nE",
    "pipe_to_composed_var": f"X=s; Y=h; cat <<'E' | $X$Y\n{REAL}\nE",
    "written_then_executed": f"cat > x <<'E'\n{REAL}\nE\nchmod +x x; ./x",
    "unknown_consumer": f"mystery-tool <<'E'\n{REAL}\nE",
    # Pruefrunde 2 (Code-Lesen): gelistete Konsumenten umdefiniert/umkonfiguriert.
    "function_shadows_cat": f"cat() {{ bash; }}; cat <<'E'\n{REAL}\nE",
    "function_keyword": f"function cat {{ bash; }}; cat <<'E'\n{REAL}\nE",
    "alias_cat": f"shopt -s expand_aliases; alias cat=bash\ncat <<'E'\n{REAL}\nE",
    "git_alias_shell": f"git -c alias.x='!sh' x <<'E'\n{REAL}\nE",
    "less_pager": f"less <<'E'\n{REAL}\nE",
}


@pytest.mark.parametrize("name", sorted(ATTACKS))
def test_misparsed_opener_never_hides_real_command(name):
    assert REAL in strip_heredoc_bodies(ATTACKS[name]), name


@pytest.mark.parametrize("name", sorted(EXECUTED_BODIES))
def test_executed_body_stays_in_scan(name):
    assert REAL in strip_heredoc_bodies(EXECUTED_BODIES[name]), name


# --- Gegenproben: echte Daten-Heredocs werden weiter entlastet ---

DATA = {
    "doc_file": ("cat <<'EOF' > docs/artifacts/protokoll.md\n"
                 "Zitat: .claude/hooks/edit_gate.py, echo x > /etc/boese.txt\nEOF"),
    "commit_message": ("git commit -m \"$(cat <<'EOF'\n"
                       "fix: Guard erkennt .env und user_approved_ Marker\nEOF\n)\""),
    "pr_body": ("gh pr create --title T --body \"$(cat <<'EOF'\n"
                "## Summary\nrm -rf node_modules war das Problem; cat .env\nEOF\n)\""),
    "commit_stdin": "git commit -F - <<'EOF'\nfeat: bash und python erwaehnt\nEOF",
    "dash_tabs": "cat <<-EOF\n\tinhalt .env erwaehnt\n\tEOF\necho done",
    "two_heredocs": ("cat <<'A' > a.md\n.env\nA\ncat <<'B' > b.md\nuser_approved_x\nB"),
}


@pytest.mark.parametrize("name", sorted(DATA))
def test_data_heredocs_still_stripped(name):
    out = strip_heredoc_bodies(DATA[name])
    assert out != DATA[name], name
    for word in (".env", "user_approved_", "/etc/boese.txt", "node_modules"):
        if word in DATA[name].split("\n", 1)[1]:
            assert word not in out, (name, word, out)


def test_opener_line_and_following_commands_survive():
    cmd = "cat <<'EOF' > docs/x.md\ntext\nEOF\necho fertig > docs/log.txt"
    out = strip_heredoc_bodies(cmd)
    assert "cat <<'EOF' > docs/x.md" in out and "echo fertig > docs/log.txt" in out
    assert "text" not in out


def test_interpreter_word_inside_body_does_not_disable_stripping():
    cmd = "git commit -F - <<'EOF'\nUmstellung von bash auf python3, eval entfernt\nEOF"
    assert "python3" not in strip_heredoc_bodies(cmd)


# --- Ende-zu-Ende: alle drei Guards ---

def _env(project: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDE_TOOL_INPUT", "CLAUDE_TOOL_NAME", "OPENSPEC_FRAMEWORK")}
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = "fix-42-x"
    return env


@pytest.fixture
def project(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    wf = tmp_path / ".claude" / "workflows"
    wf.mkdir(parents=True)
    (wf / "fix-42-x.json").write_text(json.dumps(
        {"name": "fix-42-x", "current_phase": "phase6_implement"}))
    return tmp_path


def _hook(project: Path, hook: str, command: str) -> subprocess.CompletedProcess:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    return subprocess.run([sys.executable, str(HOOKS_DIR / hook)], input=json.dumps(payload),
                          capture_output=True, text=True, env=_env(project), cwd=str(project))


@pytest.mark.parametrize("name", ["opener_in_double_quotes", "hash_midword",
                                  "opener_inside_interpreter_body", "multiline_double_quote",
                                  "single_quote_trick"])
def test_bash_gate_blocks_marker_write_after_misparsed_opener(project, name):
    r = _hook(project, "bash_gate.py", ATTACKS[name])
    assert r.returncode == 2 and "Marker" in r.stderr, (name, r.stderr)


@pytest.mark.parametrize("name", ["eval_later_line", "pipe_on_opener_line", "source_stdin"])
def test_bash_gate_blocks_marker_write_in_executed_body(project, name):
    r = _hook(project, "bash_gate.py", EXECUTED_BODIES[name])
    assert r.returncode == 2 and "Marker" in r.stderr, (name, r.stderr)


def test_secrets_guard_sees_env_read_after_misparsed_opener(project):
    (project / ".env").write_text("X=1\n")
    r = _hook(project, "secrets_guard.py", 'echo "<<EOF"\ncat .env\nEOF')
    assert r.returncode == 2, r.stderr


def test_egress_case_d_allowed_again(project):
    """#269: zitiertes '>' im Body einer Daten-Notiz ist kein Schreibziel."""
    cmd = "cat > notizen.md <<'MD'\nBeispiel: echo hallo > /etc/boese.txt\nMD"
    r = _hook(project, "secret_egress_guard.py", cmd)
    assert r.returncode == 0, r.stderr


def test_egress_real_write_after_misparsed_opener_blocked(project):
    r = _hook(project, "secret_egress_guard.py", 'echo "<<EOF"\necho x > /var/tmp/rv357\nEOF')
    assert r.returncode == 2, r.stderr
