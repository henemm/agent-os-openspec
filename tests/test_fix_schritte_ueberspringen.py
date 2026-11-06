"""TDD RED — fix-schritte-ueberspringen: drei Lücken, durch die Claude Workflow-Schritte überspringt.

Belegt AC-1 … AC-15 aus `docs/specs/fix-schritte-ueberspringen.md`
(Kontext und Reproduktion: `docs/context/fix-schritte-ueberspringen.md`).

Teil A (AC-1 … AC-7): Kurz-Aliase mit `disable-model-invocation: false` sind
heute ein reiner Text-Redirect auf den Plugin-Skill. Ohne geladenes Plugin
(Cloud-Sitzung) kommt kein Befehlstext an. Künftig trägt der Redirect einen
einzeiligen Inline-Bash-Block (```!), der ohne Plugin die lokale SKILL.md
ausgibt oder hörbar mit `BEFEHLSTEXT FEHLT` stoppt.

Teil B (AC-8 … AC-13): `workflow.py phase phase7_validate` prüft Verdict und
Dialog-Nachweis heute erst ab `phase8_complete`. Künftig greift die Prüfung
schon beim Wechsel nach Phase 7; das Evidence-Gate (#447) bleibt an Phase 8.

Teil C (AC-14, AC-15): Die Blockmeldung von `footer_gate.py` nennt künftig
Workflow, Phase, Phasenbezeichnung und Grund; der Fail-open-Pfad bleibt.

Muster: echte Hooks als Subprozess gegen hermetische tmp_path-Projekte
(Vorbilder: test_spec_freeze_partial_hash_439.py, test_adversary_evidence_gate_253.py,
test_evidence_gate_447.py, test_footer_gate_234.py). Alias-Tests importieren
`alias_sync` direkt und führen den Inline-Befehl per Shell aus.

Fixture-Hygiene (wie test_red_marker_phase_gate_f004.py): Workflow-Typ
`feature`, Ziel strikt hinter der aktuellen Phase, alle vorgelagerten Gates
passiert (Spec-Datei fehlt auf der Platte → ADR-/Briefing-Gate lenient; Phase
> phase4 → Spec-Inhalts-Gate nicht fällig). Negativfälle prüfen immer die
Meldung, nicht nur den Exit-Code.

RED-Erwartung vor der Implementierung:
  * AC-1  rot: Frontmatter ohne `allowed-tools: Bash(python3 -c *)`
  * AC-2  rot: kein ```!-Block im Redirect
  * AC-3, AC-4, AC-5  rot: kein Inline-Befehl, der ausgeführt werden könnte
  * AC-6  rot: kein Erklärungssatz für die drei Fälle
  * AC-7  rot: committete Redirects sind noch der alte Zweizeiler (ohne Block)
  * AC-8  rot: Wechsel nach Phase 7 ohne Verdict geht durch (Exit 0)
  * AC-9  rot: Wechsel nach Phase 7 ohne Dialog-Nachweis geht durch (Exit 0)
  * AC-14 rot: Blockmeldung nennt weder Workflow noch Phase noch Grund
Schon grün (Regressionsschutz):
  * AC-10: gültiger Nachweis → Phase 7 erlaubt (heute grün, weil Phase 7 noch
    gar nicht geprüft wird — erlaubt; nach der Implementierung belegt der Test,
    dass das neue Gate den dokumentierten Weg nicht verbaut)
  * AC-11: BROKEN-Rücksprung bleibt frei, `fix_loop_iterations` +1
  * AC-12: Fast Track prüft beim Wechsel nach Phase 7 weiterhin kein Verdict
  * AC-13: Evidence-Gate bleibt an Phase 8 (Phase-7-Teil heute grün aus
    demselben Grund wie AC-10)
  * AC-15: Fail-open des Footer-Gates unverändert
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
SKILLS_DIR = REPO_ROOT / "skills"
COMMANDS_DIR = REPO_ROOT / ".claude" / "commands"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
FOOTER_GATE = HOOKS_DIR / "footer_gate.py"

sys.path.insert(0, str(HOOKS_DIR))
import alias_sync  # noqa: E402

WF = "fix-schritte-wf"
ART_DIR = f"docs/artifacts/{WF}"
DIALOG_REL = f"{ART_DIR}/adversary-dialog.md"
EXAMINED = "src/checked_module.py"
REDIRECT_SKILL = "50-implement"
REDIRECT_COUNT = 11  # Kontext: 11 Aliase mit disable-model-invocation: false

_SCRUBBED = {"CLAUDE_TOOL_INPUT", "CLAUDE_TOOL_NAME", "CLAUDE_PROJECT_DIR",
             "CLAUDE_PLUGIN_ROOT", "CLAUDE_CODE_SESSION_ID", "PYTHONPATH",
             "HERDR_ENV", "HERDR_PANE_ID"}


# =========================================================================
# Gemeinsame Helfer
# =========================================================================

def _base_env() -> dict:
    # GIT_* raus: ein geerbtes GIT_DIR würde Fixture-Befehle aufs echte Repo lenken.
    env = {k: v for k, v in os.environ.items()
           if k not in _SCRUBBED and not k.startswith("OPENSPEC_")
           and not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=os.devnull)
    return env


def _env(proj: Path, home: Path, name: "str | None" = WF) -> dict:
    env = _base_env()
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(home)
    if name:
        env["OPENSPEC_ACTIVE_WORKFLOW"] = name
    return env


def _git(args: list, cwd: Path) -> str:
    r = subprocess.run(
        ["git", "-c", "user.email=t@t.invalid", "-c", "user.name=Test",
         "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
        cwd=str(cwd), capture_output=True, text=True, env=_base_env(),
    )
    assert r.returncode == 0, f"Fixture: git {args} scheitert: {r.stderr}"
    return r.stdout.strip()


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _run_hook(script: str, args: list, proj: Path, home: Path,
              stdin: "str | None" = None) -> subprocess.CompletedProcess:
    io = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / script), *args], capture_output=True,
        text=True, cwd=str(proj), env=_env(proj, home), timeout=60, **io,
    )


# =========================================================================
# Teil A: Alias-Fallback
# =========================================================================

def _redirect_skills() -> "list[str]":
    return [n for n in alias_sync.skill_names(SKILLS_DIR)
            if not alias_sync.embeds_full_skill((SKILLS_DIR / n / "SKILL.md").read_text())]


def _skill_text(name: str = REDIRECT_SKILL) -> str:
    text = (SKILLS_DIR / name / "SKILL.md").read_text()
    assert "disable-model-invocation: false" in text, (
        f"Fixture-Fehler: skills/{name}/SKILL.md ist kein Redirect-Skill"
    )
    return text


def _redirect(name: str = REDIRECT_SKILL) -> str:
    return alias_sync.alias_content(name, _skill_text(name))


def _inline_block(text: str) -> "tuple[int, int, list[str]]":
    """(Start, Ende, nicht-leere Zeilen) des ```!-Blocks; Assertion, wenn er fehlt."""
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith("```!")), None)
    assert start is not None, (
        "Redirect enthält keinen Inline-Bash-Block (Fence-Zeile beginnt mit ```!).\n"
        f"Text:\n{text}"
    )
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == "```"), None)
    assert end is not None, f"Inline-Bash-Block ist nicht geschlossen.\nText:\n{text}"
    body = [line for line in lines[start + 1:end] if line.strip()]
    return start, end, body


def _inline_command(text: str) -> str:
    _, _, body = _inline_block(text)
    assert len(body) == 1, f"Inline-Block muss genau eine Befehlszeile haben: {body!r}"
    assert body[0].startswith("python3 -c "), f"Befehl beginnt nicht mit `python3 -c `: {body[0]!r}"
    return body[0]


def _alias_home(tmp_path: Path, plugin: bool) -> Path:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    if plugin:
        _write(home, ".claude/plugins/installed_plugins.json", json.dumps({
            "version": 2,
            "plugins": {"agent-os-openspec@agent-os-openspec": [
                {"scope": "user", "installPath": str(tmp_path / "plugin-cache"),
                 "version": "4.6.0"}]},
        }))
    return home


def _alias_project(tmp_path: Path, *, skill: bool, hooks: bool,
                   name: str = REDIRECT_SKILL, sub: str = "project") -> Path:
    proj = tmp_path / sub
    proj.mkdir(parents=True, exist_ok=True)
    if skill:
        _write(proj, f"skills/{name}/SKILL.md", _skill_text(name))
    if hooks:
        (proj / "core" / "hooks").mkdir(parents=True, exist_ok=True)
    return proj


def _run_inline(cmd: str, proj: Path, home: Path, cwd: "Path | None" = None):
    env = _base_env()
    env["HOME"] = str(home)
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          cwd=str(cwd or proj), env=env, timeout=60,
                          executable="/bin/bash")


@pytest.mark.parametrize("name", _redirect_skills())
def test_redirect_frontmatter_has_allowed_tools_and_marker(name):
    """AC-1 — GIVEN ein Skill mit `disable-model-invocation: false`
    WHEN `alias_content` den Redirect erzeugt
    THEN enthält das Frontmatter `description: Kurz-Alias für /agent-os-openspec:<name>`
    und `allowed-tools: Bash(python3 -c *)`, der Alias-Marker steht direkt nach dem
    Frontmatter, `is_alias_file` erkennt die Datei und `alias_version` liefert None."""
    text = _redirect(name)
    lines = text.split("\n")
    assert lines[0] == "---", f"Redirect beginnt nicht mit Frontmatter:\n{text}"
    close = next((i for i in range(1, len(lines)) if lines[i].rstrip() == "---"), None)
    assert close is not None, f"Frontmatter nicht geschlossen:\n{text}"
    front = lines[1:close]
    assert f"description: Kurz-Alias für /agent-os-openspec:{name}" in front, front
    assert "allowed-tools: Bash(python3 -c *)" in front, (
        f"Frontmatter ohne `allowed-tools: Bash(python3 -c *)`: {front!r}"
    )
    assert lines[close + 1] == alias_sync.ALIAS_MARKER, (
        f"Alias-Marker steht nicht direkt nach dem Frontmatter: {lines[close + 1]!r}"
    )
    assert alias_sync.is_alias_file(text)
    assert alias_sync.alias_version(text) is None


@pytest.mark.parametrize("name", _redirect_skills())
def test_redirect_inline_block_is_single_python_line(name):
    """AC-2 — GIVEN derselbe Redirect
    WHEN sein Text gelesen wird
    THEN enthält er die Zeile `/agent-os-openspec:<name> $ARGUMENTS` und einen
    Inline-Bash-Block (```!), dessen Befehl eine einzige Zeile ist, mit `python3 -c `
    beginnt und weder `&&` noch `;` noch `|` enthält."""
    text = _redirect(name)
    assert f"/agent-os-openspec:{name} $ARGUMENTS" in text.split("\n"), text
    cmd = _inline_command(text)
    for op in ("&&", ";", "|"):
        assert op not in cmd, f"Inline-Befehl enthält Shell-Operator {op!r}: {cmd!r}"


def test_inline_command_silent_when_plugin_installed(tmp_path):
    """AC-3 — GIVEN eine `~/.claude/plugins/installed_plugins.json` mit einem Schlüssel
    `agent-os-openspec@…` unter `plugins` (und zur Kontrolle eine lokale SKILL.md,
    die sonst ausgegeben würde)
    WHEN der Inline-Befehl ausgeführt wird
    THEN ist seine Ausgabe leer."""
    cmd = _inline_command(_redirect())
    home = _alias_home(tmp_path, plugin=True)
    proj = _alias_project(tmp_path, skill=True, hooks=True)
    r = _run_inline(cmd, proj, home)
    assert r.returncode == 0, f"Exit {r.returncode}: {r.stderr!r}"
    assert r.stdout.strip() == "", f"Mit Plugin muss die Ausgabe leer sein: {r.stdout!r}"
    assert r.stderr.strip() == "", f"Mit Plugin keine Fehlerausgabe: {r.stderr!r}"


def _assert_skill_output(out: str, skill_text: str) -> None:
    assert re.search(r"(?i)plugin.{0,80}nicht.{0,20}geladen", out), (
        f"Hinweis 'Plugin nicht geladen' fehlt:\n{out[:600]}"
    )
    # Die ⚙-Versionszeile darf nicht als `⚙ ` am Zeilenanfang erscheinen; verlangt
    # wird deshalb der SKILL-Text bis vor seine erste ⚙-Zeile (wörtlich).
    body = skill_text.split("\n⚙ ", 1)[0]
    assert len(body) > 200, "Fixture-Fehler: SKILL-Text zu kurz"
    pos = out.find(body)
    assert pos >= 0, f"SKILL.md-Text fehlt (wörtlich) in der Ausgabe:\n{out[:600]}"
    hint = re.search(r"(?i)plugin.{0,80}nicht.{0,20}geladen", out)
    assert hint.start() < pos, "Hinweis muss VOR dem SKILL.md-Text stehen"
    bad = [line for line in out.splitlines() if line.startswith("⚙ ")]
    assert not bad, f"Ausgabezeilen beginnen mit '⚙ ': {bad!r}"


def test_inline_command_prints_skill_text_without_plugin(tmp_path):
    """AC-4 — GIVEN kein installiertes Plugin und `<root>/skills/<name>/SKILL.md`
    (Root aus `CLAUDE_PROJECT_DIR`)
    WHEN der Inline-Befehl ausgeführt wird
    THEN steht zuerst ein Hinweis (Plugin nicht geladen, der folgende Text gilt),
    danach der vollständige SKILL.md-Text; mit `<root>/core/hooks` zusätzlich
    `export CLAUDE_PLUGIN_ROOT=<root>`; keine Ausgabezeile beginnt mit `⚙ `.
    Zwei Fälle: (a) cwd = Projekt, mit core/hooks → export-Zeile;
    (b) cwd = fremder leerer Ordner, ohne core/hooks → Root kommt allein aus der
    Umgebungsvariable, keine export-Zeile."""
    cmd = _inline_command(_redirect())
    skill_text = _skill_text()
    home = _alias_home(tmp_path, plugin=False)

    # (a) mit core/hooks
    proj = _alias_project(tmp_path, skill=True, hooks=True, sub="proj-a")
    r = _run_inline(cmd, proj, home)
    assert r.returncode == 0, f"Exit {r.returncode}: {r.stderr!r}"
    _assert_skill_output(r.stdout, skill_text)
    exports = {line.strip() for line in r.stdout.splitlines()}
    assert ({f"export CLAUDE_PLUGIN_ROOT={proj}",
             f"export CLAUDE_PLUGIN_ROOT={proj.resolve()}"} & exports), (
        f"Zeile `export CLAUDE_PLUGIN_ROOT={proj}` fehlt:\n{r.stdout[:600]}"
    )

    # (b) ohne core/hooks, cwd woanders
    proj_b = _alias_project(tmp_path, skill=True, hooks=False, sub="proj-b")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    r = _run_inline(cmd, proj_b, home, cwd=elsewhere)
    assert r.returncode == 0, f"Exit {r.returncode}: {r.stderr!r}"
    _assert_skill_output(r.stdout, skill_text)
    assert "export CLAUDE_PLUGIN_ROOT=" not in r.stdout, (
        "Ohne <root>/core/hooks darf keine export-Zeile erscheinen"
    )


def test_inline_command_stop_message_without_any_text(tmp_path):
    """AC-5 — GIVEN kein installiertes Plugin und keine lokale SKILL.md
    WHEN der Inline-Befehl ausgeführt wird
    THEN enthält die Ausgabe `BEFEHLSTEXT FEHLT` und die Anweisung, die Phase nicht
    zu beginnen und den PO zu informieren, und der Exit-Code ist 0."""
    cmd = _inline_command(_redirect())
    home = _alias_home(tmp_path, plugin=False)
    proj = _alias_project(tmp_path, skill=False, hooks=False)
    r = _run_inline(cmd, proj, home)
    assert r.returncode == 0, f"Exit-Code muss 0 sein, war {r.returncode}: {r.stderr!r}"
    out = r.stdout
    assert "BEFEHLSTEXT FEHLT" in out, out
    assert re.search(r"(?is)nicht.{0,40}beginn|beginn.{0,40}nicht", out), (
        f"Anweisung 'Phase nicht beginnen' fehlt: {out!r}"
    )
    assert re.search(r"\bPO\b", out), f"Anweisung 'PO informieren' fehlt: {out!r}"


def test_redirect_explains_fallback_cases():
    """AC-6 — GIVEN der Redirect-Text
    WHEN er gelesen wird (außerhalb des Inline-Blocks)
    THEN erklärt er drei Fälle (Plugin geladen: der Redirect gilt; Befehlstext unten:
    danach arbeiten; `BEFEHLSTEXT FEHLT`: nicht beginnen) und weist an, den Block per
    Bash auszuführen, falls er wörtlich statt seiner Ausgabe erscheint."""
    text = _redirect()
    start, end, _ = _inline_block(text)
    lines = text.split("\n")
    prose = "\n".join(lines[:start] + lines[end + 1:])
    assert re.search(r"(?is)plugin.{0,40}geladen", prose), f"Fall 'Plugin geladen' fehlt:\n{prose}"
    assert re.search(r"(?i)befehlstext", prose.replace("BEFEHLSTEXT FEHLT", "")), (
        f"Fall 'Befehlstext unten: danach arbeiten' fehlt:\n{prose}"
    )
    assert "BEFEHLSTEXT FEHLT" in prose, f"Fall 'BEFEHLSTEXT FEHLT' fehlt:\n{prose}"
    assert re.search(r"(?is)nicht.{0,40}beginn|beginn.{0,40}nicht", prose), (
        f"Anweisung 'nicht beginnen' fehlt:\n{prose}"
    )
    assert re.search(r"(?i)bash", prose) and re.search(r"(?i)w(ö|oe)rtlich", prose), (
        f"Hinweis 'wörtlich erschienen → per Bash ausführen' fehlt:\n{prose}"
    )


def test_repo_aliases_match_alias_content():
    """AC-7 — GIVEN die 11 committeten Redirects unter `.claude/commands/` dieses Repos
    WHEN sie mit `alias_content` verglichen werden
    THEN sind sie byte-gleich und tragen den neuen Inline-Block (sonst wäre der
    Vergleich vor der Implementierung trivial wahr)."""
    names = _redirect_skills()
    assert len(names) == REDIRECT_COUNT, f"Erwartet {REDIRECT_COUNT} Redirect-Skills: {names}"
    for name in names:
        path = COMMANDS_DIR / f"{name}.md"
        assert path.is_file(), f"Alias fehlt: {path}"
        actual = path.read_bytes()
        expected = alias_sync.alias_content(name, _skill_text(name)).encode()
        assert actual == expected, f"{path.name} weicht von alias_content ab"
        _inline_command(actual.decode())


# =========================================================================
# Teil B: Phase-7-Gate
# =========================================================================

def _red_artifact() -> dict:
    return {"type": "test_output", "path": f"{ART_DIR}/test-red-output.txt",
            "description": "red", "phase": "phase5_tdd_red",
            "created": "2026-11-06T09:00:00"}


def _gate_project(tmp_path: Path, *, phase: str = "phase6b_adversary",
                  wf_type: str = "feature", verdict=None, **extra) -> "tuple[Path, Path]":
    """Git-Projekt ohne Remote; alle vorgelagerten Gates passiert (Spec-Datei fehlt
    auf der Platte → ADR-/Briefing-Gate lenient; Phase > phase4 → Spec-Gate nicht fällig)."""
    proj = tmp_path / "proj"
    proj.mkdir()
    _git(["init", "-q"], proj)
    (proj / ".claude" / "workflows").mkdir(parents=True)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    _write(proj, f"{ART_DIR}/test-red-output.txt", "FAILED tests/x.py::test_a\n1 failed\n")
    data = {
        "name": WF, "workflow_type": wf_type, "current_phase": phase,
        "context_file": "docs/context.md", "spec_file": "docs/specs/s.md",
        "spec_approved": True, "red_test_done": True,
        "test_artifacts": [_red_artifact()], "adversary_verdict": verdict,
        "fix_loop_iterations": 0, "phase_transitions": [], "phase_log": [],
    }
    data.update(extra)
    _write(proj, f".claude/workflows/{WF}.json", json.dumps(data, indent=2))
    return proj, home


def _state(proj: Path) -> dict:
    return json.loads((proj / ".claude" / "workflows" / f"{WF}.json").read_text())


def _phase(proj: Path, home: Path, target: str) -> subprocess.CompletedProcess:
    return _run_hook("workflow.py", ["phase", target], proj, home)


def _dialog_text() -> str:
    return (
        f"# Adversary Dialog — {WF}\nSpec: docs/specs/s.md\n\n"
        "## Checkliste\n"
        "- [x] AC-1: Phase 7 verlangt den Nachweis — Beweis: Testlauf\n"
        f"  Code reference: {EXAMINED}:1\n"
        "- [x] AC-2: Phase 8 verlangt den Nachweis — Beweis: Testlauf\n"
        f"  Code reference: {EXAMINED}:1\n\n"
        "## Dialog\n\n"
        "### Runde 1\n**Adversary:** Angriff 1\n**Implementierer:** Beweis 1\n\n"
        "### Runde 2\n**Adversary:** Angriff 2\n**Implementierer:** Beweis 2\n\n"
        "VERDICT: VERIFIED\n"
    )


def _valid_evidence(proj: Path, home: Path, cited=(EXAMINED,)) -> None:
    """Dokumentierter Weg: stamp → add-artifact adversary_dialog → qa_gate --checklist."""
    for rel in cited:
        if not (proj / rel).exists():
            _write(proj, rel, "VALUE = 1\n")
    text = _dialog_text()
    if tuple(cited) != (EXAMINED,):
        refs = "".join(f"  Code reference: {c}:1\n" for c in cited)
        text = text.replace(f"  Code reference: {EXAMINED}:1\n", refs)
    art = _write(proj, DIALOG_REL, text)
    s = _run_hook("adversary_dialog.py", ["stamp", str(art)], proj, home)
    assert s.returncode == 0, f"Fixture: stamp scheitert: {s.stdout}{s.stderr}"
    a = _run_hook("workflow.py", ["add-artifact", "adversary_dialog", DIALOG_REL,
                                  "dialog", "phase6b_adversary"], proj, home)
    assert a.returncode == 0, f"Fixture: add-artifact scheitert: {a.stderr!r}"
    green = _write(proj, f"{ART_DIR}/test-green-output.txt", (
        "============================= test session starts ==============================\n"
        "collected 5 items\n\ntests/test_gate.py .....\n\n"
        "============================== 5 passed in 0.12s ===============================\n"))
    q = _run_hook("qa_gate.py", [str(green), "--checklist", str(art)], proj, home)
    assert q.returncode == 0, f"Fixture: qa_gate scheitert: {q.stdout}{q.stderr}"
    assert str(_state(proj).get("adversary_verdict", "")).startswith("VERIFIED"), (
        "Fixture: qa_gate hat kein VERIFIED gesetzt"
    )


def test_phase7_blocked_without_verdict(tmp_path):
    """AC-8 — GIVEN ein Workflow `feature` in `phase6b_adversary` mit RED-Artefakt,
    aber ohne `adversary_verdict`
    WHEN `workflow.py phase phase7_validate` läuft
    THEN Exit 1, stderr enthält `BLOCKED` und `Adversary verdict missing or not
    VERIFIED`, die Phase bleibt `phase6b_adversary`."""
    proj, home = _gate_project(tmp_path, verdict=None)
    r = _phase(proj, home, "phase7_validate")
    assert r.returncode == 1, (
        f"Wechsel nach Phase 7 ohne Verdict muss blocken, Exit {r.returncode}. "
        f"stdout={r.stdout!r} stderr={r.stderr!r}"
    )
    assert "BLOCKED" in r.stderr, r.stderr
    assert "Adversary verdict missing or not VERIFIED" in r.stderr, r.stderr
    assert _state(proj)["current_phase"] == "phase6b_adversary"


def test_phase7_blocked_without_dialog_evidence(tmp_path):
    """AC-9 — GIVEN derselbe Workflow mit `adversary_verdict: VERIFIED`, aber ohne
    registriertes und gestempeltes Dialog-Artefakt
    WHEN `workflow.py phase phase7_validate` läuft
    THEN Exit 1 und stderr enthält `Adversary verdict ohne gültigen Dialog-Nachweis`."""
    proj, home = _gate_project(tmp_path, verdict="VERIFIED:Tests PASSED: 5 passed")
    _write(proj, EXAMINED, "VALUE = 1\n")
    r = _phase(proj, home, "phase7_validate")
    assert r.returncode == 1, (
        f"Wechsel nach Phase 7 ohne Dialog-Nachweis muss blocken, Exit {r.returncode}. "
        f"stdout={r.stdout!r} stderr={r.stderr!r}"
    )
    assert "Adversary verdict ohne gültigen Dialog-Nachweis" in r.stderr, r.stderr
    assert _state(proj)["current_phase"] == "phase6b_adversary"


def test_phase7_allowed_with_valid_evidence(tmp_path):
    """AC-10 — GIVEN derselbe Workflow mit VERIFIED und einem gültigen, gestempelten
    (`adversary_dialog.py stamp`) und registrierten (`add-artifact adversary_dialog`)
    Dialog-Artefakt
    WHEN `workflow.py phase phase7_validate` läuft
    THEN Exit 0 und die Phase ist `phase7_validate`.
    (Heute schon grün, weil Phase 7 ungeprüft ist — Regressionsschutz.)"""
    proj, home = _gate_project(tmp_path)
    _valid_evidence(proj, home)
    r = _phase(proj, home, "phase7_validate")
    assert r.returncode == 0, f"Gültiger Nachweis muss Phase 7 öffnen: {r.stderr!r}"
    assert _state(proj)["current_phase"] == "phase7_validate"


def test_backstep_to_phase6_stays_free(tmp_path):
    """AC-11 — GIVEN ein Workflow in `phase6b_adversary` ohne Verdict (BROKEN-Pfad)
    WHEN `workflow.py phase phase6_implement` läuft
    THEN Exit 0 und `fix_loop_iterations` steigt um 1."""
    proj, home = _gate_project(tmp_path, verdict=None, fix_loop_iterations=1)
    r = _phase(proj, home, "phase6_implement")
    assert r.returncode == 0, f"BROKEN-Rücksprung muss frei bleiben: {r.stderr!r}"
    state = _state(proj)
    assert state["current_phase"] == "phase6_implement"
    assert state["fix_loop_iterations"] == 2, state.get("fix_loop_iterations")


def test_fast_track_phase7_unchanged(tmp_path):
    """AC-12 — GIVEN ein Workflow `feature-fast` in `phase6_implement` mit
    freigegebener Spec
    WHEN `workflow.py phase phase7_validate` läuft ohne Verdict
    THEN Exit 0."""
    proj, home = _gate_project(tmp_path, phase="phase6_implement",
                               wf_type="feature-fast", verdict=None)
    r = _phase(proj, home, "phase7_validate")
    assert r.returncode == 0, f"Fast Track darf in Phase 7 kein Verdict verlangen: {r.stderr!r}"
    assert _state(proj)["current_phase"] == "phase7_validate"


EVIDENCE_GATE_CFG = (
    "evidence_checks:\n  phase8_complete:\n"
    "    - verifier: xcresult_proof\n      file: simulator-run.txt\n"
)


def test_evidence_gate_stays_at_phase8(tmp_path):
    """AC-13 — GIVEN ein konfigurierter Evidence-Check (`evidence_checks` in
    config.yaml), ein gültiger Dialog-Nachweis und kein Beleg
    WHEN erst `phase phase7_validate` und danach `phase phase8_complete` läuft
    THEN Exit 0 beim Wechsel nach Phase 7 und Exit 1 beim Wechsel nach Phase 8
    (Grund: Evidence-Gate, nicht der Dialog-Nachweis).
    (Phase-7-Teil heute grün, weil Phase 7 ungeprüft ist — Regressionsschutz.)"""
    # Aufbau wie test_evidence_gate_447._project: MOD_A in der Basis, MOD_B neu.
    proj = (tmp_path / "proj").resolve()
    proj.mkdir()
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    mod_a, mod_b = "src/module_a.py", "src/module_b.py"
    _write(proj, mod_a, "VALUE = 1\n")
    _git(["init", "-q", "-b", "main"], proj)
    _write(proj, ".gitignore", ".claude/\n")
    _git(["add", "-A"], proj)
    _git(["commit", "-q", "-m", "init"], proj)
    base = _git(["rev-parse", "HEAD"], proj)
    _write(proj, mod_b, "VALUE = 2\n")
    _write(proj, ".claude/config.yaml", EVIDENCE_GATE_CFG)
    _write(proj, f".claude/workflows/_log/2026-11-06_{WF}.yaml", f"workflow_id: {WF}\n")
    _write(proj, f"{ART_DIR}/test-red-output.txt", "1 failed\n")
    data = {
        "name": WF, "workflow_type": "feature", "current_phase": "phase6b_adversary",
        "context_file": "docs/context.md", "spec_file": "docs/specs/s.md",
        "spec_approved": True, "red_test_done": True, "base_commit": base,
        "test_artifacts": [_red_artifact()], "adversary_verdict": None,
        "phase_transitions": [], "phase_log": [],
    }
    _write(proj, f".claude/workflows/{WF}.json", json.dumps(data, indent=2))
    _valid_evidence(proj, home, cited=(mod_a, mod_b))
    assert not (proj / ART_DIR / "simulator-run.txt").exists()

    p7 = _phase(proj, home, "phase7_validate")
    assert p7.returncode == 0, f"Phase 7 darf das Evidence-Gate nicht prüfen: {p7.stderr!r}"
    assert _state(proj)["current_phase"] == "phase7_validate"

    p8 = _phase(proj, home, "phase8_complete")
    assert p8.returncode == 1, (
        f"Phase 8 ohne Beleg muss blocken, Exit {p8.returncode}: {p8.stderr!r}"
    )
    assert "BLOCKED" in p8.stderr, p8.stderr
    assert "Dialog-Nachweis" not in p8.stderr, (
        f"Fixture-Fehler: Phase 8 scheitert am Dialog statt am Evidence-Gate: {p8.stderr!r}"
    )
    assert _state(proj)["current_phase"] == "phase7_validate"


# =========================================================================
# Teil C: Footer-Begründung
# =========================================================================

FOOTER_PROMPT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _footer_project(tmp_path: Path, *, state: "dict | None | str",
                    active: bool = True) -> Path:
    """Main-Repo (.git als Verzeichnis → kein Worktree). state=None: keine State-Datei;
    state=str: roher (kaputter) Inhalt."""
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    wf_dir = proj / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    if isinstance(state, dict):
        data = {"name": WF, "workflow_type": "feature"}
        data.update(state)
        (wf_dir / f"{WF}.json").write_text(json.dumps(data))
    elif isinstance(state, str):
        (wf_dir / f"{WF}.json").write_text(state)
    if active:
        (proj / ".claude" / "active_workflow").write_text(WF)
    return proj


def _footer_message(du_line: "str | None") -> str:
    msg = "Adversary-Runde läuft, der Dialog ist noch offen.\n\n"
    if du_line is not None:
        msg += du_line
    else:
        msg += "Ich warte auf den Adversary-Agenten."
    return msg


def _run_footer(proj: Path, message: str) -> subprocess.CompletedProcess:
    payload = json.dumps({
        "session_id": "sess-fix-schritte", "hook_event_name": "Stop",
        "cwd": str(proj), "prompt_id": FOOTER_PROMPT_ID,
        "last_assistant_message": message,
    })
    env = _base_env()
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    env["HOME"] = str(proj.parent / "home")
    return subprocess.run([sys.executable, str(FOOTER_GATE)], input=payload,
                          capture_output=True, text=True, env=env, cwd=str(proj),
                          timeout=60)


def test_footer_block_names_phase_and_reason(tmp_path):
    """AC-14 — GIVEN ein Workflow in `phase6b_adversary` und eine Antwort, die mit
    `❗ Du: /60-validate` endet
    WHEN der Stop-Hook `footer_gate.py` läuft
    THEN Exit 2 und stderr enthält `FUSSZEILE FALSCH`, den Workflow-Namen,
    `phase6b_adversary`, `Adversary Verification` und den Satz, dass diese Phase
    nur `/50-implement` verlässt."""
    proj = _footer_project(tmp_path, state={"current_phase": "phase6b_adversary"})
    r = _run_footer(proj, _footer_message("❗ Du: /60-validate"))
    assert r.returncode == 2, f"Exit 2 erwartet, war {r.returncode}: {r.stderr!r}"
    err = r.stderr
    assert "FUSSZEILE FALSCH" in err, err
    assert WF in err, f"Workflow-Name fehlt in der Meldung: {err!r}"
    assert "phase6b_adversary" in err, f"Phase fehlt in der Meldung: {err!r}"
    assert "Adversary Verification" in err, f"Phasenbezeichnung fehlt: {err!r}"
    assert re.search(r"(?s)nur\W{0,3}/50-implement.{0,40}verl(ä|ae)sst"
                     r"|verl(ä|ae)sst.{0,40}nur\W{0,3}/50-implement", err), (
        f"Grund 'diese Phase verlässt nur /50-implement' fehlt: {err!r}"
    )


@pytest.mark.parametrize("case", ["missing_state", "corrupt_state", "freetext_step",
                                  "no_du_line"])
def test_footer_fail_open_unchanged(tmp_path, case):
    """AC-15 — GIVEN ein fehlender oder unlesbarer Workflow-State, ein Freitext-Schritt
    (`phase3_spec` mit gesetztem `spec_file`) oder eine Antwort ohne ❗Du-Zeile
    WHEN der Stop-Hook läuft
    THEN Exit 0 und keine Meldung (stderr leer)."""
    du = "❗ Du: /60-validate"
    if case == "missing_state":
        proj, msg = _footer_project(tmp_path, state=None), _footer_message(du)
    elif case == "corrupt_state":
        proj = _footer_project(tmp_path, state='{"name": "x", "current_phase"')
        msg = _footer_message(du)
    elif case == "freetext_step":
        proj = _footer_project(tmp_path, state={"current_phase": "phase3_spec",
                                                "spec_file": "docs/specs/s.md"})
        msg = _footer_message(du)
    else:
        proj = _footer_project(tmp_path, state={"current_phase": "phase6b_adversary"})
        msg = _footer_message(None)
    r = _run_footer(proj, msg)
    assert r.returncode == 0, f"{case}: Exit 0 erwartet, war {r.returncode}: {r.stderr!r}"
    assert r.stderr == "", f"{case}: keine Meldung erwartet: {r.stderr!r}"
