"""TDD RED — Issue #286: Herkunft der Vorbedingungen als Pflichtsektion des Prüfprotokolls.

AC-1 … AC-12 (docs/specs/feat-286-herkunft-vorbedingungen.md). Muster: Hermetik und
Wegwerf-Repos aus tests/test_adversary_coverage_gate_259.py bzw. _278.py (#265) — cwd und
CLAUDE_PROJECT_DIR im tmp-Projekt, ohne Sitzungs-/GIT_*-Variablen und globale Git-Config; den
aktiven Workflow setzt nur `.claude/active_workflow` im tmp-Projekt (#58).

`validate_dialog_artifact_ex()` läuft je Fall in einem FRISCHEN Python-Prozess (`python -c`):
`config_loader.load_config()`/`find_project_root()` sind per lru_cache prozessweit gecacht, die
Projekt-`config.yaml` (hier `.claude/config.yaml`, gitignored) muss pro Test frisch gelesen
werden, und stderr (Warnzeile bei `mode: warn`) wird so ohne Monkeypatching sichtbar.

Die Vorbedingungs-Tabelle ist die ECHTE Ausgabe von `precondition_origins.py` (#285) über
`tests/fixtures/precondition_origins/swift/` — zwei Verdachtszeilen (`energyRaw`: 0,
`processedAt`: 1 Produktions-Schreibstelle) und eine unauffällige (`title`: 3).

Echtes RED (heute rot): AC-1, AC-3, AC-4 (×2, Warnzeile), AC-5 (×2), AC-8, AC-10,
AC-12/AC-12b (Teil „Sektion fehlt → blockt").
Regressionswächter (heute trivial grün, weil noch nichts prüft — müssen grün BLEIBEN):
AC-2, AC-6, AC-7, AC-9, AC-11.
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

WF = "wf-286"
DIALOG = f"docs/artifacts/{WF}/adversary-dialog.md"
MOD_A, MOD_B = "src_A/module_a.py", "src/module_b.py"
VERIFIED = "VERIFIED:Tests PASSED: 5 passed"
SECTION = "## Herkunft der Vorbedingungen"
GATE_KEY = "precondition_section_gate"
HINT_TEXT = "kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)"
SWIFT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "precondition_origins" / "swift"
SUSPECT_FIELDS = ("energyRaw", "processedAt")  # ≤1 Produktions-Schreibstelle
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


def _run(script, args: list, cwd: Path, env=None, stdin=None, check=False):
    """Hook-Skript aus core/hooks (bei script=None: `python -c …`), cwd im tmp-Projekt."""
    io = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
    head = [str(HOOKS_DIR / script)] if script else []
    r = subprocess.run([sys.executable, *head, *args], capture_output=True, text=True,
                       cwd=str(cwd), env=env or _env(cwd), timeout=60, **io)
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


def _write_workflow(root: Path, *, phase="phase6b_adversary", verdict=VERIFIED,
                    wf_type="feature", artifacts=(), **extra) -> None:
    """State wie nach Phase 5; `artifacts` = registrierte Dialog-Pfade (Muster #259)."""
    arts = [("test_output", f"docs/artifacts/{WF}/red.txt", "phase5_tdd_red")]
    arts += [("adversary_dialog", str(a), "phase6b_adversary") for a in artifacts]
    data = {"name": WF, "workflow_type": wf_type, "current_phase": phase,
            "context_file": "docs/context.md", "spec_file": "docs/specs/s.md",
            "spec_approved": True, "red_test_done": True, "adversary_verdict": verdict,
            "phase_transitions": [], "phase_log": [],
            "test_artifacts": [{"type": t, "path": p, "description": "fixture", "phase": ph,
                                "created": "2026-09-30T10:00:00"} for t, p, ph in arts],
            **extra}
    _write(root, f".claude/workflows/{WF}.json", json.dumps(data, indent=2))


def _state(root: Path) -> dict:
    return json.loads((root / ".claude" / "workflows" / f"{WF}.json").read_text())


def _write_gate_config(root: Path, *, enabled=True, mode="block", skip_fast_track=True) -> None:
    """Projekt-Config mit `precondition_section_gate` (in .claude/ → gitignored, nie gestagt)."""
    _write(root, ".claude/config.yaml", (
        f"{GATE_KEY}:\n  enabled: {str(enabled).lower()}\n  mode: {mode}\n"
        f"  skip_fast_track: {str(skip_fast_track).lower()}\n"))


# --- Vorbedingungs-Tabelle aus den #285-Fixtures --------------------------------------------

def _tool_table() -> str:
    """Echte Ausgabe von precondition_origins.py über das Swift-Fixture (#285)."""
    r = _run("precondition_origins.py", ["--lang", "swift", "--root", str(SWIFT_FIXTURE),
                                         "--config", str(REPO_ROOT / "config.yaml")], REPO_ROOT,
             env=_env())
    assert r.returncode == 0, f"precondition_origins.py scheitert: {r.stdout}{r.stderr}"
    table = r.stdout
    rows = {m.group(1): m.group(0) for m in re.finditer(r"(?m)^\| (\w+) \|.*\|$", table)}
    # Fixture-Kontrolle: zwei Verdachtszeilen (0 bzw. 1 Schreibstelle), eine unauffällige (3)
    assert "**0 — keine Schreibstelle im Produktivcode**" in rows.get("energyRaw", ""), table
    assert "| 1 — Sources/EnrichmentWriter.swift:" in rows.get("processedAt", ""), table
    assert "| 3 — " in rows.get("title", ""), table
    return table


def _filled_table(fill: dict) -> str:
    """Tabelle mit Prüfer-Prosa: fill = {feld: (bedingung, test)}; fehlt ein Feld → leer."""
    out = []
    for line in _tool_table().splitlines():
        m = re.match(r"^\| (\w+) \|", line)
        if m and m.group(1) in fill and line.endswith("|  |  |"):
            cond, test = fill[m.group(1)]
            line = line[: -len("|  |  |")] + f"| {cond} | {test} |"
        out.append(line)
    return "\n".join(out) + "\n"


COMPLETE_FILL = {
    "energyRaw": ("nie — kein Produktionsweg schreibt das Feld",
                  "keiner; Vorbedingung im Test künstlich, als Befund vermerkt"),
    "processedAt": ("nur wenn `task.needsEnrichment` wahr ist (EnrichmentWriter.swift:7)",
                    "`testEnrichmentSetsProcessedAt` löst genau diesen Zweig aus"),
}
# AC-3: processedAt hat die Bedingung, aber KEINEN Test für diesen Weg
INCOMPLETE_FILL = {**COMPLETE_FILL,
                   "processedAt": (COMPLETE_FILL["processedAt"][0], "")}


def _section(body: str) -> str:
    return f"{SECTION}\n\n{body}\n"


# --- Dialog-Artefakte -----------------------------------------------------------------------

def _dialog_text(cited=(MOD_A,), precondition: "str | None" = None, open_item=False) -> str:
    """Vollständiges Protokoll (Checkliste abgehakt, 2 Runden, Verdict); `precondition` =
    fertiger Sektionsblock oder None (Sektion fehlt). `open_item`: zusätzlich ein `- [ ]`."""
    refs = "".join(f"  Code reference: {c}:1\n" for c in cited)
    extra = "- [ ] AC-2: noch offen\n" if open_item else ""
    return ("# Adversary Dialog\n\n## Checkliste\n- [x] AC-1: deckt die Änderung ab — Beweis: Test\n"
            f"{refs}{extra}\n## Dialog\n\n"
            "### Runde 1\n**Adversary:** A1\n**Implementierer:** B1\n\n"
            "### Runde 2\n**Adversary:** A2\n**Implementierer:** B2\n\n"
            f"{precondition or ''}\n## Verdict\n\nVERDICT: VERIFIED\n")


def _stamped(proj: Path, text: str, rel: str = DIALOG) -> Path:
    """Artefakt schreiben und per echtem `stamp` mit dem Hash-Block versehen."""
    art = _write(proj, rel, text)
    _run("adversary_dialog.py", ["stamp", str(art)], proj, check=True)
    assert "## Geprüfte Dateien" in art.read_text(), "Fixture-Kontrolle: Hash-Block fehlt"
    return art


_VALIDATE_SNIPPET = (
    "import json, sys\n"
    f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
    "from adversary_dialog import validate_dialog_artifact_ex\n"
    "valid, msg, kind = validate_dialog_artifact_ex(sys.argv[1])\n"
    "print(json.dumps({'valid': valid, 'msg': msg, 'kind': kind}))\n"
)


def _validate(proj: Path, art: Path) -> "tuple[dict, str]":
    """validate_dialog_artifact_ex() in frischem Prozess → (Ergebnis, stderr)."""
    r = _run(None, ["-c", _VALIDATE_SNIPPET, str(art)], proj)
    assert r.returncode == 0, f"Validierungsprozess abgestürzt: {r.stdout}{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1]), r.stderr


def _case(tmp_path: Path, precondition, *, mode="block", enabled=True, wf_type="feature",
          open_item=False) -> "tuple[dict, str]":
    proj = _make_repo(tmp_path)
    _write_gate_config(proj, enabled=enabled, mode=mode)
    _write_workflow(proj, wf_type=wf_type, verdict=None)
    art = _stamped(proj, _dialog_text(precondition=precondition, open_item=open_item))
    return _validate(proj, art)


MISSING = None  # Sektion fehlt


# --- AC-1 -----------------------------------------------------------------------------------

def test_ac1_missing_section_is_format_failure(tmp_path):
    """AC-1 — ECHTES RED: heute valid=True, weil nichts die Sektion prüft."""
    res, err = _case(tmp_path, MISSING, mode="block")
    assert res["valid"] is False, f"VERIFIED trotz fehlender Sektion: {res} / {err}"
    assert res["kind"] == "format", res


SCAFFOLD_PLACEHOLDER = "<!-- vom Prüfer auszufüllen, siehe `precondition_origins.py` -->"


def test_ac1b_unfilled_scaffold_placeholder_is_format_failure_not_complete(tmp_path):
    """AC-1 — Überschrift vorhanden, darunter NUR der unveränderte Scaffold-Platzhalter
    (weder Tabelle noch Hinweistext) → wie fehlende Sektion: 'format', nicht vollständig."""
    from adversary_dialog import scaffold_dialog_artifact
    spec = _write(tmp_path, "docs/specs/s.md", (
        "# Spec\n\n## Acceptance Criteria\n\n- **AC-1:** Given X / When Y / Then Z\n"
        "  - Test: `test_x`\n\n## Changelog\n\n- init\n"))
    assert SCAFFOLD_PLACEHOLDER in scaffold_dialog_artifact(WF, str(spec)), \
        "Fixture-Kontrolle: Platzhalter weicht vom Scaffold ab"
    res, err = _case(tmp_path, _section(SCAFFOLD_PLACEHOLDER), mode="block")
    assert (res["valid"], res["kind"]) == (False, "format"), \
        f"unausgefüllte Sektion als vollständig akzeptiert: {res} / {err}"


# --- AC-2-----------------------------------------------------------------------------------

def test_ac2_complete_suspect_rows_pass(tmp_path):
    """AC-2 — Regressionswächter (heute trivial grün): vollständig ausgefüllte
    Verdachtszeilen (energyRaw, processedAt) dürfen unter `mode: block` NICHT blocken; die
    unauffällige Zeile `title` (3 Schreibstellen) bleibt bewusst leer."""
    res, err = _case(tmp_path, _section(_filled_table(COMPLETE_FILL)), mode="block")
    assert res["valid"] is True, f"vollständige Sektion abgewiesen: {res} / {err}"
    assert res["kind"] is None, res


# --- AC-3 -----------------------------------------------------------------------------------

def test_ac3_incomplete_suspect_row_is_content_failure(tmp_path):
    """AC-3 — ECHTES RED: processedAt (1 Schreibstelle) ohne 'Test für diesen Weg' → heute
    valid=True."""
    res, err = _case(tmp_path, _section(_filled_table(INCOMPLETE_FILL)), mode="block")
    assert res["valid"] is False, f"unvollständige Verdachtszeile akzeptiert: {res} / {err}"
    assert res["kind"] == "content", res


# --- AC-4 -----------------------------------------------------------------------------------

def test_ac4_warn_mode_missing_section_passes_with_stderr_warning(tmp_path):
    """AC-4 — ECHTES RED (Warnzeile-Teil): valid=True ist heute trivial erfüllt, die
    Warnzeile auf stderr mit dem Grund (Sektion fehlt) gibt es heute nicht."""
    res, err = _case(tmp_path, MISSING, mode="warn")
    assert res["valid"] is True, f"mode=warn darf nicht blocken: {res} / {err}"
    assert GATE_KEY in err, f"keine Warnzeile auf stderr: {err!r}"
    assert "Herkunft der Vorbedingungen" in err, f"Warnzeile nennt den Grund nicht: {err!r}"


def test_ac4_warn_mode_incomplete_row_passes_with_stderr_warning(tmp_path):
    """AC-4 — ECHTES RED (Warnzeile-Teil): Grund = die unvollständige Zeile (processedAt)."""
    res, err = _case(tmp_path, _section(_filled_table(INCOMPLETE_FILL)), mode="warn")
    assert res["valid"] is True, f"mode=warn darf nicht blocken: {res} / {err}"
    assert GATE_KEY in err, f"keine Warnzeile auf stderr: {err!r}"
    assert "processedAt" in err, f"Warnzeile nennt die unvollständige Zeile nicht: {err!r}"


# --- AC-5 -----------------------------------------------------------------------------------

def test_ac5_block_mode_missing_section_fails_format(tmp_path):
    """AC-5 — ECHTES RED: mode=block, Sektion fehlt → format (heute valid=True)."""
    res, err = _case(tmp_path, MISSING, mode="block")
    assert (res["valid"], res["kind"]) == (False, "format"), f"{res} / {err}"


def test_ac5_block_mode_incomplete_row_fails_content(tmp_path):
    """AC-5 — ECHTES RED: mode=block, Verdachtszeile unvollständig → content."""
    res, err = _case(tmp_path, _section(_filled_table(INCOMPLETE_FILL)), mode="block")
    assert (res["valid"], res["kind"]) == (False, "content"), f"{res} / {err}"


# --- AC-6 -----------------------------------------------------------------------------------

def test_ac6_disabled_gate_skips_check_no_warning_no_block(tmp_path):
    """AC-6 — Regressionswächter (heute trivial grün): enabled=false → weder Block noch
    Warnung, auch bei fehlender Sektion und mode=block."""
    res, err = _case(tmp_path, MISSING, mode="block", enabled=False)
    assert res["valid"] is True, f"deaktiviertes Gate blockt: {res} / {err}"
    assert GATE_KEY not in err and "Herkunft" not in err, f"Warnung trotz enabled=false: {err!r}"


# --- AC-7 -----------------------------------------------------------------------------------

def test_ac7_hint_text_without_default_lang_counts_as_complete(tmp_path):
    """AC-7 — Regressionswächter (heute trivial grün): Hinweistext statt Tabelle zählt als
    vollständig (0 Verdachtszeilen)."""
    res, err = _case(tmp_path, _section(HINT_TEXT), mode="block")
    assert res["valid"] is True, f"Hinweistext abgewiesen: {res} / {err}"


def test_ac7b_no_model_files_hint_counts_as_complete(tmp_path):
    """AC-7 / Known Limitations — ECHTE Ausgabe von precondition_origins.py über einen
    modellfreien Baum („Keine Modelldateien gefunden unter [...]") zählt unter mode=block als
    vollständig (0 Zeilen), nicht als fehlende Sektion."""
    empty_root = tmp_path / "no-models"
    empty_root.mkdir()
    r = _run("precondition_origins.py", ["--lang", "swift", "--root", str(empty_root),
                                         "--config", str(REPO_ROOT / "config.yaml")], REPO_ROOT,
             env=_env())
    assert r.returncode == 0, f"precondition_origins.py scheitert: {r.stdout}{r.stderr}"
    assert r.stdout.startswith("Keine Modelldateien gefunden unter"), \
        f"Fixture-Kontrolle: unerwartete Werkzeug-Ausgabe {r.stdout!r}"
    res, err = _case(tmp_path, _section(r.stdout.strip()), mode="block")
    assert (res["valid"], res["kind"]) == (True, None), \
        f"echte Leer-Ausgabe als fehlende Sektion gewertet: {res} / {err}"


# --- AC-8 -----------------------------------------------------------------------------------

def test_ac8_scaffold_renders_precondition_placeholder_section(tmp_path):
    """AC-8 — ECHTES RED: scaffold_dialog_artifact() kennt die Überschrift heute nicht."""
    from adversary_dialog import scaffold_dialog_artifact
    spec = _write(tmp_path, "docs/specs/s.md", (
        "# Spec\n\n## Acceptance Criteria\n\n- **AC-1:** Given X / When Y / Then Z\n"
        "  - Test: `test_x`\n\n## Changelog\n\n- init\n"))
    out = scaffold_dialog_artifact(WF, str(spec))
    heads = list(re.finditer(r"(?m)^## Herkunft der Vorbedingungen\s*$", out))
    assert len(heads) == 1, f"Überschrift fehlt/doppelt:\n{out}"
    pos = heads[0].start()
    rounds = [m.start() for m in re.finditer(r"(?m)^### Runde \d+\s*$", out)]
    verdict = re.search(r"(?m)^## Verdict\s*$", out)
    assert rounds and verdict, out
    assert max(rounds) < pos < verdict.start(), f"falsch positioniert:\n{out}"
    body = out[heads[0].end():verdict.start()]
    assert re.search(r"<!--.*precondition_origins\.py.*-->", body), f"Platzhalter fehlt:\n{out}"


# --- AC-9 -----------------------------------------------------------------------------------

def test_ac9_fast_track_workflow_skips_section_check(tmp_path):
    """AC-9 — Regressionswächter (heute trivial grün): feature-fast überspringt die
    Prüfung unter mode=block trotz fehlender Sektion."""
    for wf_type in ("feature-fast",):
        res, err = _case(tmp_path / wf_type, MISSING, mode="block", wf_type=wf_type)
        assert res["valid"] is True, f"Fast Track ({wf_type}) geblockt: {res} / {err}"


# --- AC-10 ----------------------------------------------------------------------------------

def _doc_section(rel: str, start: str, end: str) -> str:
    text = (REPO_ROOT / rel).read_text()
    m = re.search(rf"{start}(.*?)(?={end}|\Z)", text, re.M | re.S)
    assert m, f"{rel}: Abschnitt {start!r} fehlt"
    return m.group(1)


def test_ac10_docs_mention_precondition_section_duty():
    """AC-10 — ECHTES RED: keiner der beiden Anleitungstexte nennt die Pflicht heute."""
    step8a = _doc_section("core/commands/50-implement.md", r"^#### 8a\.", r"^#{3,4} ")
    assert "precondition_origins.py" in step8a, "50-implement.md Step 8a: Aufruf fehlt"
    assert "default_lang" in step8a, "50-implement.md Step 8a: Bedingung default_lang fehlt"
    validator = (REPO_ROOT / "core/agents/implementation-validator.md").read_text()
    assert SECTION in validator, "implementation-validator.md nennt die Sektion nicht wörtlich"
    for col in ("Bedingung davor", "Test für diesen Weg"):
        assert col in validator, f"implementation-validator.md: Spalte {col!r} fehlt"


# --- AC-11 ----------------------------------------------------------------------------------

def test_ac11_mixed_defect_content_wins_over_new_format_check(tmp_path):
    """AC-11 — Regressionswächter (heute grün, Status quo #77): offener Checklistenpunkt UND
    fehlende Sektion → 'content' vom Checklisten-Schritt, nicht 'format' vom neuen Schritt."""
    res, err = _case(tmp_path, MISSING, mode="block", open_item=True)
    assert (res["valid"], res["kind"]) == (False, "content"), f"{res} / {err}"


# --- AC-12 ----------------------------------------------------------------------------------

def _e2e_repo(tmp_path: Path, precondition) -> Path:
    """Muster #259 `_staged_b(**COVERED)`: MOD_B gestagt, Dialog zitiert MOD_A+MOD_B,
    gestempelt, registriert; Phase 7; Gate-Config mode=block."""
    proj = _make_repo(tmp_path)
    _write_gate_config(proj, mode="block")
    _write(proj, MOD_B)
    _git(["add", "--", MOD_B], proj)
    _stamped(proj, _dialog_text(cited=(MOD_A, MOD_B), precondition=precondition))
    _write_workflow(proj, phase="phase7_validate", artifacts=[DIALOG], base_commit=_sha(proj))
    return proj


def _commit_gate(proj: Path):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m wip"}})
    return _run("bash_gate.py", [], proj, stdin=payload)


def test_ac12_commit_gate_blocks_and_allows_via_inherited_check(tmp_path):
    """AC-12 — ECHTES RED (Teil 'Sektion fehlt → Exit 2'; heute Exit 0). Der Teil
    'vollständige Sektion → Exit 0' ist Regressionswächter."""
    proj = _e2e_repo(tmp_path, MISSING)
    r = _commit_gate(proj)
    assert r.returncode == 2, f"Commit trotz fehlender Sektion erlaubt (rc={r.returncode}): " \
                              f"{r.stdout}{r.stderr}"
    _stamped(proj, _dialog_text(cited=(MOD_A, MOD_B),
                                precondition=_section(_filled_table(COMPLETE_FILL))))
    ok = _commit_gate(proj)
    assert ok.returncode == 0, f"vollständige Sektion blockt Commit: {ok.stdout}{ok.stderr}"


def test_ac12b_phase8_transition_blocks_and_allows_via_inherited_check(tmp_path):
    """AC-12b — ECHTES RED (Teil 'Sektion fehlt → BLOCKED'; heute Phase 8 erreicht). Der
    Teil 'vollständige Sektion → phase8_complete' ist Regressionswächter."""
    proj = _e2e_repo(tmp_path, MISSING)
    r = _run("workflow.py", ["phase", "phase8_complete"], proj)
    assert r.returncode != 0, f"Phase 8 trotz fehlender Sektion: {r.stdout}{r.stderr}"
    assert "BLOCKED" in r.stdout + r.stderr, f"keine BLOCKED-Meldung: {r.stdout}{r.stderr}"
    assert _state(proj)["current_phase"] == "phase7_validate"
    _stamped(proj, _dialog_text(cited=(MOD_A, MOD_B),
                                precondition=_section(_filled_table(COMPLETE_FILL))))
    ok = _run("workflow.py", ["phase", "phase8_complete"], proj)
    assert ok.returncode == 0, f"vollständige Sektion blockt Phase 8: {ok.stdout}{ok.stderr}"
    assert _state(proj)["current_phase"] == "phase8_complete"
