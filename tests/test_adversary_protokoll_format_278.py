"""TDD RED — Issue #278: Adversary-Protokollformat dokumentieren, Kennzahlen tatsächlich schreiben.

AC-1 … AC-9 (docs/specs/fix-278-adversary-protokoll-format.md). Die CLI-Tests laufen über die
echten Hook-Skripte (`core/hooks/adversary_dialog.py`, `core/hooks/workflow.py`) in Wegwerf-
Repos unter `tmp_path` — Muster 1:1 aus tests/test_adversary_coverage_gate_259.py (Hermetik
#265): cwd/CLAUDE_PROJECT_DIR im tmp-Projekt, ohne Sitzungs-/GIT_*-Variablen und globale
Git-Config; den aktiven Workflow setzt nur `.claude/active_workflow` im tmp-Projekt (#58).

RED (neue Funktionalität, heute rot): AC-1, AC-2, AC-4, AC-5, AC-6, AC-9.
Regressionswächter (heute schon grün, bleiben grün): AC-3, AC-7, AC-8.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

WF = "wf-278"
DIALOG = f"docs/artifacts/{WF}/adversary-dialog.md"
MOD_A, MOD_B = "src_A/module_a.py", "src/module_b.py"
VERIFIED = "VERIFIED:Tests PASSED: 5 passed"
MIN_ROUNDS = 2  # Spiegel von adversary_dialog.MIN_ROUNDS; im Test zusätzlich gegengeprüft
_SCRUBBED = {"CLAUDE_TOOL_INPUT", "CLAUDE_TOOL_NAME", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT",
             "CLAUDE_CODE_SESSION_ID", "OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK",
             "PYTHONPATH"}


# --- Hermetische Helfer (Muster aus test_adversary_coverage_gate_259.py) -------------------

def _env(project_dir=None, **extra) -> dict:
    """Hermetisch: ohne Sitzungs- und GIT_*-Variablen, ohne globale/System-Git-Config."""
    env = {k: v for k, v in os.environ.items() if k not in _SCRUBBED and not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return {**env, **extra}


def _run(script, args: list, cwd: Path, env=None, check=False):
    """Hook-Skript aus core/hooks, cwd im tmp-Projekt."""
    r = subprocess.run([sys.executable, str(HOOKS_DIR / script), *args], capture_output=True,
                       text=True, cwd=str(cwd), env=env or _env(cwd), timeout=60,
                       stdin=subprocess.DEVNULL)
    assert not check or r.returncode == 0, f"{script} {args}: {r.stdout}{r.stderr}"
    return r


def _git(args: list, cwd: Path) -> str:
    r = subprocess.run(["git", "-c", "user.email=t@t.invalid", "-c", "user.name=Test",
                        "-c", "commit.gpgsign=false", *args],
                       cwd=str(cwd), capture_output=True, text=True, env=_env())
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout.strip()


def _sha(cwd: Path) -> str:
    return _git(["rev-parse", "HEAD"], cwd)


def _write(root: Path, rel: str, text: "str | None" = None) -> Path:
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {rel}\nVALUE = 1\n" if text is None else text)
    return path


def _make_repo(tmp_path: Path, name="proj") -> Path:
    """C0 = .gitignore (.claude/), README.md, MOD_A; aktiver Workflow WF per tmp-Datei."""
    proj = tmp_path / name
    proj.mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], proj)
    _write(proj, ".gitignore", ".claude/\n")
    _write(proj, "README.md")
    _write(proj, MOD_A)
    _git(["add", "-A"], proj)
    _git(["commit", "-q", "-m", "init"], proj)
    _write(proj, ".claude/active_workflow", WF)
    return proj


def _write_workflow(root: Path, *, phase="phase6b_adversary", verdict=VERIFIED, **extra) -> None:
    """State wie nach Phase 5 (Felder `adversary_findings_total`/`affected_files` nur via extra)."""
    data = {"name": WF, "workflow_type": "feature", "current_phase": phase,
            "context_file": "docs/context.md", "spec_file": "docs/specs/s.md",
            "spec_approved": True, "red_test_done": True, "adversary_verdict": verdict,
            "phase_transitions": [], "phase_log": [],
            "test_artifacts": [{"type": "test_output", "path": f"docs/artifacts/{WF}/red.txt",
                                "description": "fixture", "phase": "phase5_tdd_red",
                                "created": "2026-09-30T10:00:00"}], **extra}
    _write(root, f".claude/workflows/{WF}.json", json.dumps(data, indent=2))


def _state(root: Path) -> dict:
    return json.loads((root / ".claude" / "workflows" / f"{WF}.json").read_text())


def _dialog_text(cited, round_prefix="###", rounds=2, findings="", verdict="VERIFIED") -> str:
    """Vollständiges Protokoll: Checkliste abgehakt, `rounds` Runden mit `round_prefix`, Verdict."""
    refs = "".join(f"  Code reference: {c}:1\n" for c in cited)
    body = "".join(f"{round_prefix} Runde {i}\n**Adversary:** A{i}\n**Implementierer:** B{i}\n\n"
                   for i in range(1, rounds + 1))
    return ("# Adversary Dialog\n\n## Checkliste\n- [x] AC-1: deckt die Änderung ab — Beweis: Test\n"
            f"{refs}\n{findings}## Dialog\n\n{body}VERDICT: {verdict}\n")


def _write_log_file(root: Path) -> str:
    r = _run("workflow.py", ["write-log"], root, check=True)
    logs = sorted((root / ".claude" / "workflows" / "_log").glob(f"*_{WF}.yaml"))
    assert logs, f"write-log hat keine Log-Datei geschrieben: {r.stdout}{r.stderr}"
    return logs[-1].read_text()


def _doc_section(rel: str, start, end) -> str:
    """Abschnitt ab `start` bis zur nächsten `end`-Überschrift (Helfer aus dem #259-Test)."""
    text = (REPO_ROOT / rel).read_text()
    m = re.search(rf"{start}(.*?)(?={end}|\Z)", text, re.M | re.S) if start else None
    assert m or not start, f"{rel}: Abschnitt {start!r} fehlt"
    return m.group(1) if m else text


# --- AC-1 -----------------------------------------------------------------------------------

def test_scaffold_outputs_checklist_and_rounds(tmp_path):
    """AC-1 — RED: Subcommand `scaffold` existiert heute nicht ('Unknown command', Exit 1)."""
    import adversary_dialog
    assert adversary_dialog.MIN_ROUNDS == MIN_ROUNDS
    proj = _make_repo(tmp_path)
    spec = _write(proj, "docs/specs/s.md", (
        "# Spec\n\n## Expected Behavior\n\n- Punkt Alpha wird geliefert\n"
        "- Punkt Beta wird geliefert\n\n## Acceptance Criteria\n\n"
        "- **AC-1:** Given X / When Y / Then Z\n  - Test: `test_x`\n\n## Changelog\n\n- init\n"))
    r = _run("adversary_dialog.py", ["scaffold", WF, str(spec)], proj)
    assert r.returncode == 0, f"scaffold scheitert: {r.stdout}{r.stderr}"
    out = r.stdout
    assert re.search(r"(?m)^## Checkliste\s*$", out), out
    checklist = _doc_section_from(out, r"^## Checkliste\s*$", r"^## ")
    open_items = re.findall(r"(?m)^- \[ \] (.+)$", checklist)
    for needle in ("Punkt Alpha", "Punkt Beta", "AC-1"):
        assert any(needle in item for item in open_items), f"{needle} fehlt als - [ ]: {checklist}"
    assert not re.search(r"(?mi)^- \[x\]", checklist), "Gerüst darf nichts abgehakt haben"
    assert re.search(r"(?m)^## Dialog\s*$", out), out
    dialog = _doc_section_from(out, r"^## Dialog\s*$", r"^## ")
    heads = re.findall(r"(?m)^### Runde (\d+)\s*$", dialog)
    assert heads == [str(i) for i in range(1, MIN_ROUNDS + 1)], f"Rundenköpfe: {heads}\n{dialog}"
    assert re.search(r"(?m)^## Verdict\s*$", out), out


def _doc_section_from(text: str, start: str, end: str) -> str:
    m = re.search(rf"{start}(.*?)(?={end}|\Z)", text, re.M | re.S)
    assert m, f"Abschnitt {start!r} fehlt:\n{text}"
    return m.group(1)


# --- AC-2 / AC-3 ----------------------------------------------------------------------------

def _stamped_dialog(proj: Path, round_prefix: str) -> Path:
    art = _write(proj, DIALOG, _dialog_text([MOD_A], round_prefix=round_prefix))
    _run("adversary_dialog.py", ["stamp", str(art)], proj, check=True)
    return art


def test_h2_rounds_accepted_reproduces_2026_09_27_case(tmp_path):
    """AC-2 — RED: heute zählt die Regex nur `### Runde` → 0 Runden → Exit 1."""
    proj = _make_repo(tmp_path)
    art = _stamped_dialog(proj, "##")
    r = _run("adversary_dialog.py", ["validate", str(art)], proj)
    assert r.returncode == 0, f"H2-Runden abgewiesen: {r.stdout}{r.stderr}"


def test_h3_rounds_still_accepted_no_regression(tmp_path):
    """AC-3 — Regressionswächter (heute grün): bisheriges `### Runde N` bleibt gültig."""
    proj = _make_repo(tmp_path)
    art = _stamped_dialog(proj, "###")
    r = _run("adversary_dialog.py", ["validate", str(art)], proj)
    assert r.returncode == 0, f"H3-Runden abgewiesen: {r.stdout}{r.stderr}"


# --- AC-4 / AC-5 ----------------------------------------------------------------------------

FINDINGS = (
    "## Findings\n\n"
    "- ID: F001\n  Severity: HIGH\n  Code reference: src_A/module_a.py:1\n\n"
    "- ID: F002\n  Severity: LOW\n  Code reference: src_A/module_a.py:1\n\n"
    "Fix-Loop-Zitat (darf nicht mitzählen):\n\n"
    "```\n- ID: F001\n  Severity: HIGH\n- ID: F009\n  Severity: LOW\n```\n\n"
)


def test_stamp_writes_findings_total_excludes_fenced_duplicates(tmp_path):
    """AC-4 — RED: `stamp` schreibt `adversary_findings_total` heute nie in den State."""
    proj = _make_repo(tmp_path)
    _write_workflow(proj, verdict=None)
    assert "adversary_findings_total" not in _state(proj)
    art = _write(proj, DIALOG, _dialog_text([MOD_A], findings=FINDINGS))
    _run("adversary_dialog.py", ["stamp", str(art)], proj, check=True)
    state = _state(proj)
    assert state.get("adversary_findings_total") == 2, (
        f"adversary_findings_total = {state.get('adversary_findings_total', '<fehlt>')!r}, "
        "erwartet 2 (F001 + F002; F001/F009 im Codeblock zählen nicht)")


def _norm(paths, root: Path) -> set:
    return {os.path.realpath(p if os.path.isabs(p) else root / p) for p in paths}


def test_stamp_writes_affected_files_matches_required_files(tmp_path):
    """AC-5 — RED: `affected_files` bleibt heute nach `stamp` unberührt (fehlt/leer)."""
    proj = _make_repo(tmp_path)
    _write_workflow(proj, verdict=None, base_commit=_sha(proj))
    _write(proj, MOD_A, "# geändert\nVALUE = 2\n")
    _write(proj, MOD_B)
    _write(proj, "docs/notes.md", "Nicht-Code\n")
    req = _run("adversary_dialog.py", ["required-files"], proj)
    assert req.returncode == 0, f"required-files scheitert: {req.stdout}{req.stderr}"
    expected = _norm(req.stdout.split(), proj)
    assert expected == _norm([MOD_A, MOD_B], proj), f"Fixture-Kontrolle: {req.stdout}"
    art = _write(proj, DIALOG, _dialog_text([MOD_A, MOD_B]))
    _run("adversary_dialog.py", ["stamp", str(art)], proj, check=True)
    affected = _state(proj).get("affected_files")
    assert affected, f"affected_files nach stamp leer/fehlt: {affected!r}"
    assert _norm(affected, proj) == expected, f"affected_files {affected} != required-files"


# --- AC-6 / AC-7 ----------------------------------------------------------------------------

def test_write_log_unbekannt_when_metrics_never_persisted(tmp_path):
    """AC-6 — RED: heute schreibt write-log den stillen Default `0` statt `unbekannt`."""
    proj = _make_repo(tmp_path)
    _write_workflow(proj, phase="phase7_validate")
    assert "adversary_findings_total" not in _state(proj)
    log = _write_log_file(proj)
    assert re.search(r"(?m)^adversary_findings_total: unbekannt$", log), log
    assert re.search(r"(?m)^scope_files_changed: unbekannt$", log), log


def test_write_log_shows_real_zero_after_metrics_persisted(tmp_path):
    """AC-7 — Regressionswächter (heute grün): explizite 0 bleibt 0, nicht `unbekannt`."""
    proj = _make_repo(tmp_path)
    _write_workflow(proj, phase="phase7_validate", adversary_findings_total=0, affected_files=[])
    log = _write_log_file(proj)
    assert re.search(r"(?m)^adversary_findings_total: 0$", log), log
    assert not re.search(r"(?m)^adversary_findings_total: unbekannt$", log), log


# --- AC-8 -----------------------------------------------------------------------------------

def test_zero_rounds_stays_format_failure_not_content(tmp_path):
    """AC-8 — Regressionswächter (heute grün): 0 Runden bleibt `format`, nie `content` (#77/#253)."""
    from adversary_dialog import validate_dialog_artifact_ex
    art = _write(tmp_path, "dialog.md", _dialog_text([MOD_A], rounds=0))
    valid, msg, kind = validate_dialog_artifact_ex(str(art))
    assert valid is False, msg
    assert kind == "format", f"failure_kind={kind!r}: {msg}"


# --- AC-9 -----------------------------------------------------------------------------------

def test_docs_reference_scaffold_and_keep_required_files_mentions():
    """AC-9 — RED: `scaffold` kommt heute in keiner der beiden Anweisungen vor."""
    for rel in ("core/agents/implementation-validator.md", "core/commands/50-implement.md"):
        text = (REPO_ROOT / rel).read_text()
        assert re.search(r"adversary_dialog\.py scaffold\b", text), f"{rel}: scaffold fehlt"
    kept = [
        ("core/commands/50-implement.md", r"^#### 8c\.", r"^#{3,4} ", r"required-files"),
        ("core/agents/implementation-validator.md", r"^### Step 3\b", r"^#{2,3} ",
         r"required-files"),
        ("core/agents/implementation-validator.md", r"^## Step 6\b", r"^## ",
         r"required-files|gelistet|listed"),
    ]
    missing = [(rel, start) for rel, start, end, pat in kept
               if not re.search(pat, _doc_section(rel, start, end))]
    assert not missing, f"required-files-Erwähnung (#259) verloren: {missing}"
