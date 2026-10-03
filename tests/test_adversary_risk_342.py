"""TDD RED — Issue #342: Gegenpruefung nach Risiko staffeln.

Belegt AC-1 ... AC-9 aus docs/specs/feat-342-gegenpruefung-nach-risiko.md.

Hohes Risiko (Hook-/Gate-Code, Guards, Freigabe-Logik, Gate-Konfiguration):
unveraendert mindestens 2 Dialog-Runden. Niedriges Risiko (ausschliesslich
Anweisungstext, Doku, Tests): mindestens 1 Runde. Das Risiko kommt mechanisch
aus der Dateiliste, fail-closed: im Zweifel hoch.

## Hermetik

Die Einstufung haengt an git-Zustand und Config. Jeder Fall baut deshalb ein
EIGENES Wegwerf-Git-Repo in tmp_path mit eigener `config.yaml`, definierter
Dateiliste und definiertem Basis-Stand (Zweig `base` per `base_branch`, oder
ein Bare-`origin` mit gesetztem `origin/HEAD`) — nie der echte Checkout.
Der Produktivcode laeuft als Subprozess (`python -c` bzw. das Hook-Skript) mit
cwd und CLAUDE_PROJECT_DIR im Wegwerf-Repo: `config_loader.load_config()` ist
`lru_cache`-d, ein In-Process-Test mit mehreren Config-Staenden waere
reihenfolgeabhaengig (Begruendung wie tests/test_observable_surface_260.py).

## Rot-Strategie

Die neuen Namen (`adversary_risk_report`, `required_rounds`, `min_rounds=`,
CLI `risk`, Config-Block) werden erst INNERHALB der Tests angesprochen, nie
beim Import/Sammeln. Jeder Test scheitert so einzeln und aus dem richtigen
Grund: das Feature fehlt.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"

WF = "wf-342"
DIALOG = f"docs/artifacts/{WF}/adversary-dialog.md"
EXAMINED = "docs/notes.md"  # im Basis-Stand vorhanden, im Dialog per 'Code reference:' zitiert
VERIFIED = "VERIFIED:Tests PASSED: 5 passed"

_SCRUBBED = {"CLAUDE_TOOL_INPUT", "CLAUDE_TOOL_NAME", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT",
             "CLAUDE_CODE_SESSION_ID", "OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK",
             "PYTHONPATH"}

# Die Risikostufen heissen in der Spec „hoch"/„niedrig"; die Schreibweise der
# Rueckgabe ist dort nicht festgelegt, deshalb werden beide Sprachen akzeptiert.
HIGH_WORDS = ("hoch", "high")
LOW_WORDS = ("niedrig", "low")

# Startwerte aus der Spec (Implementation Details 1): je ein Beispielpfad pro Muster.
HIGH_SAMPLES = [
    "core/hooks/some_gate.py",
    "hooks/hooks.json",
    "core/agents/some-agent.md",
    "scripts/tool.py",
    "modules/ios/config.yaml",
    "setup.py",
    "config.yaml",
    ".github/workflows/spec-gate.yml",
    ".claude-plugin/plugin.json",
    ".env.local",
    "src/secret_store.py",
]
LOW_SAMPLES = [
    "docs/a.md",
    "tests/test_a.py",
    "tests/helper.txt",
    "pkg/test_b.py",
    "core/commands/10-context.md",
    "skills/10-context/SKILL.md",
    "CHANGELOG.md",
    "README.md",
    "CLAUDE.md",
    "sub/CLAUDE.md",
    ".gitignore",
]


# --------------------------------------------------------------------------
# Hermetische Umgebung und Subprozess-Helfer
# --------------------------------------------------------------------------

def _env(project_dir=None, **extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _SCRUBBED and not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return {**env, **extra}


def _git(args: list, cwd: Path) -> str:
    r = subprocess.run(["git", "-c", "user.email=t@t.invalid", "-c", "user.name=Test",
                        "-c", "commit.gpgsign=false", *args],
                       cwd=str(cwd), capture_output=True, text=True, env=_env())
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout.strip()


def _script(name: str, args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HOOKS_DIR / name), *args], capture_output=True,
                          text=True, cwd=str(cwd), env=_env(cwd), stdin=subprocess.DEVNULL,
                          timeout=60)


def _py(cwd: Path, code: str) -> subprocess.CompletedProcess:
    """`python -c` im Wegwerf-Repo; HOOKS_DIR vorn im Suchpfad."""
    prelude = f"import sys, json; sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
    return subprocess.run([sys.executable, "-c", prelude + code], capture_output=True, text=True,
                          cwd=str(cwd), env=_env(cwd), stdin=subprocess.DEVNULL, timeout=60)


def _py_json(cwd: Path, code: str):
    """Fuehrt `code` aus und liest die letzte stdout-Zeile als JSON. Ein Absturz
    (z. B. AttributeError: Funktion fehlt) wird zum sprechenden Testfehler."""
    r = _py(cwd, code)
    assert r.returncode == 0, (
        f"Aufruf scheiterte (rc={r.returncode}) — Feature fehlt?\n"
        f"stdout={r.stdout!r}\nstderr={r.stderr[-600:]!r}")
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert lines, f"keine Ausgabe, stderr={r.stderr!r}"
    return json.loads(lines[-1])


# --------------------------------------------------------------------------
# Wegwerf-Repo bauen
# --------------------------------------------------------------------------

def _write(root: Path, rel: str, text: "str | None" = None) -> Path:
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {rel}\nVALUE = 1\n" if text is None else text, encoding="utf-8")
    return path


def _config(body: str) -> str:
    return "adversary_risk:\n" + body


STD_BODY = "  enabled: true\n  base_branch: base\n"


def _make_repo(tmp_path: Path, name: str = "proj", config_text: "str | None" = None,
               origin: bool = False) -> Path:
    """Wegwerf-Repo; Basis-Commit enthaelt config.yaml, README/CHANGELOG/CLAUDE.md,
    docs/notes.md und .gitignore, damit sie nicht selbst als Aenderung zaehlen.

    Zweig `base` zeigt auf den Basis-Commit. Mit origin=True gibt es zusaetzlich
    einen Bare-`origin` mit gesetztem `origin/HEAD` (Basis-Stand ohne `base_branch`).
    """
    root = tmp_path / name
    root.mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], root)
    _write(root, "config.yaml", _config(STD_BODY) if config_text is None else config_text)
    _write(root, ".gitignore", ".claude/\n")
    _write(root, "README.md", "# Wegwerf\n")
    _write(root, "CHANGELOG.md", "# Changelog\n")
    _write(root, "CLAUDE.md", "# Projekt\n")
    _write(root, EXAMINED, "NOTE = 1\n")
    _git(["add", "-A"], root)
    _git(["commit", "-q", "-m", "base"], root)
    _git(["branch", "base"], root)
    if origin:
        bare = tmp_path / f"{name}-origin.git"
        _git(["init", "-q", "--bare", "-b", "main", str(bare)], tmp_path)
        _git(["remote", "add", "origin", str(bare)], root)
        _git(["push", "-q", "origin", "main"], root)
        _git(["remote", "set-head", "origin", "main"], root)
    _write(root, ".claude/active_workflow", WF)  # ignoriert; nur fuer `stamp`
    return root


def _change(root: Path, *rels: str, commit: bool = True) -> None:
    """Dateien aendern/anlegen (bestehende bekommen eine Zeile angehaengt)."""
    for rel in rels:
        target = root / rel
        if target.exists():
            target.write_text(target.read_text(encoding="utf-8") + "# geaendert\n", encoding="utf-8")
        else:
            _write(root, rel)
    if commit:
        _git(["add", "-A"], root)
        _git(["commit", "-q", "-m", "change"], root)


# --------------------------------------------------------------------------
# Risiko-Report und Rundenzahl (Subprozess)
# --------------------------------------------------------------------------

def _report(repo: Path) -> dict:
    return _py_json(repo, "import hook_utils\n"
                          "print(json.dumps(hook_utils.adversary_risk_report(), default=str))")


def _rounds(repo: Path):
    return _py_json(repo, "import adversary_dialog\n"
                          "print(json.dumps(adversary_dialog.required_rounds()))")


def _is_high(risk) -> bool:
    return str(risk).lower() in HIGH_WORDS


def _is_low(risk) -> bool:
    return str(risk).lower() in LOW_WORDS


def _file_count(report: dict) -> int:
    files = report.get("files")
    return len(files) if isinstance(files, (list, tuple)) else int(files)


def _assert_report_shape(report: dict) -> None:
    for key in ("risk", "reason", "files", "root", "min_rounds"):
        assert key in report, f"Rueckgabe muss `{key}` enthalten — war {sorted(report)}"
    assert isinstance(report["reason"], str) and report["reason"].strip(), (
        f"`reason` muss ein nichtleerer Text sein — war {report['reason']!r}")


def _assert_high(report: dict, context: str = "") -> None:
    _assert_report_shape(report)
    assert _is_high(report["risk"]), f"{context} muss hohes Risiko sein — war {report!r}"
    assert report["min_rounds"] == 2, f"{context} verlangt 2 Runden — war {report!r}"


def _assert_low(report: dict, context: str = "") -> None:
    _assert_report_shape(report)
    assert _is_low(report["risk"]), f"{context} muss niedriges Risiko sein — war {report!r}"
    assert report["min_rounds"] == 1, f"{context} verlangt nur 1 Runde — war {report!r}"


# --------------------------------------------------------------------------
# Dialog-Artefakt (Muster: test_adversary_evidence_gate_253.py / ..._coverage_gate_259.py)
# --------------------------------------------------------------------------

def _dialog_text(rounds: int, verdict: str = "VERIFIED") -> str:
    body = (
        f"# Adversary Dialog — {WF}\nSpec: docs/specs/s.md\n\n"
        "## Checkliste\n"
        "- [x] AC-1: Staffelung greift — Beweis: Testlauf\n"
        f"  Code reference: {EXAMINED}:1\n\n"
        "## Dialog\n\n"
    )
    for i in range(1, rounds + 1):
        body += f"### Runde {i}\n**Adversary:** Angriff {i}\n**Implementierer:** Beweis {i}\n\n"
    return body + f"VERDICT: {verdict}\n"


def _make_dialog(root: Path, rounds: int) -> Path:
    """Dialog-Artefakt mit `rounds` Runden, per `adversary_dialog.py stamp` gestempelt."""
    art = _write(root, DIALOG, _dialog_text(rounds))
    r = _script("adversary_dialog.py", ["stamp", str(art)], root)
    assert r.returncode == 0, f"stamp scheiterte: {r.stdout}{r.stderr}"
    return art


def _evidence(root: Path):
    """`check_dialog_evidence(wf)` im Wegwerf-Repo → None (akzeptiert) oder Grund-Text."""
    wf = {"name": WF, "adversary_verdict": VERIFIED,
          "test_artifacts": [{"type": "adversary_dialog", "path": DIALOG, "description": "fixture",
                              "phase": "phase6b_adversary", "created": "2026-10-03T10:00:00"}]}
    return _py_json(root, "import adversary_dialog\n"
                          f"wf = json.loads({json.dumps(json.dumps(wf))})\n"
                          "print(json.dumps(adversary_dialog.check_dialog_evidence(wf)))")


# --------------------------------------------------------------------------
# AC-1: Config-Block und Modul-Konstanten
# --------------------------------------------------------------------------

def test_config_block_and_defaults(tmp_path):
    """AC-1: `config.yaml` enthaelt `adversary_risk`; fehlt der Block, gelten dieselben Werte.

    GIVEN: die mitgelieferte config.yaml / ein Repo ohne `adversary_risk`-Block.
    WHEN:  geladen bzw. das Risiko ermittelt wird.
    THEN:  Block mit enabled, high_risk_patterns, low_risk_patterns und
           low_risk_min_rounds: 1 — und ohne Block derselbe Befund wie mit den Startwerten.
    """
    import yaml  # PyYAML ist Abhaengigkeit des Frameworks (config_loader)
    cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text(encoding="utf-8"))
    block = cfg.get("adversary_risk")
    assert isinstance(block, dict), "config.yaml braucht einen Block `adversary_risk`"
    assert block.get("enabled") is True, f"enabled muss true sein — war {block.get('enabled')!r}"
    assert block.get("low_risk_min_rounds") == 1, (
        f"low_risk_min_rounds muss 1 sein — war {block.get('low_risk_min_rounds')!r}")
    assert "base_branch" in block, "`base_branch` fehlt im Block (leer = aus origin/HEAD)"
    for key in ("high_risk_patterns", "low_risk_patterns"):
        value = block.get(key)
        assert isinstance(value, list) and value and all(isinstance(p, str) for p in value), (
            f"`{key}` muss eine nichtleere Liste von Mustern sein — war {value!r}")

    high = [re.compile(p) for p in block["high_risk_patterns"]]
    low = [re.compile(p) for p in block["low_risk_patterns"]]
    for path in HIGH_SAMPLES:
        assert any(rx.search(path) for rx in high), f"Startwert fehlt: {path} muss hoch sein"
    for path in LOW_SAMPLES:
        assert any(rx.search(path) for rx in low), f"Startwert fehlt: {path} muss niedrig sein"

    # Fehlt der Block, gelten dieselben Werte als Modul-Konstanten. Basis-Stand
    # kommt hier aus origin/HEAD, damit auch `base_branch` ohne Block leer sein darf.
    low_repo = _make_repo(tmp_path, "low", config_text="platzhalter: 1\n", origin=True)
    _change(low_repo, "docs/a.md", "tests/test_a.py", "CHANGELOG.md")
    _assert_low(_report(low_repo), "Ohne Block: reine Doku/Tests")
    assert _rounds(low_repo) == 1

    high_repo = _make_repo(tmp_path, "high", config_text="platzhalter: 1\n", origin=True)
    _change(high_repo, "docs/a.md", "core/hooks/x.py")
    _assert_high(_report(high_repo), "Ohne Block: Hook-Datei")
    assert _rounds(high_repo) == 2


# --------------------------------------------------------------------------
# AC-2: ein Hochrisiko-Treffer genuegt
# --------------------------------------------------------------------------

def test_one_high_risk_file_makes_it_high(tmp_path):
    """AC-2: Datei unter core/hooks/ — auch zusammen mit Doku — heisst hoch, 2 Runden."""
    repo = _make_repo(tmp_path)
    _change(repo, "docs/a.md", "tests/test_a.py", "core/hooks/guard.py")

    report = _report(repo)

    _assert_high(report, "Hook-Datei neben Doku und Tests")
    assert "core/hooks/guard.py" in report["reason"], (
        f"Begruendung soll die ausloesende Datei nennen — war {report['reason']!r}")
    assert _file_count(report) == 3, f"3 geaenderte Dateien erwartet — war {report!r}"


@pytest.mark.parametrize("rel", HIGH_SAMPLES)
def test_each_high_risk_pattern_alone_makes_it_high(tmp_path, rel):
    """AC-2 (streng): jedes Startmuster der Hochrisiko-Liste greift schon fuer sich allein."""
    repo = _make_repo(tmp_path)
    _change(repo, rel)

    _assert_high(_report(repo), rel)


def test_high_pattern_beats_low_pattern(tmp_path):
    """AC-2 (streng): `secret` im Pfad macht auch eine Doku-/Test-Datei hoch."""
    repo = _make_repo(tmp_path)
    _change(repo, "docs/secret-notes.md", "tests/test_secrets.py")

    _assert_high(_report(repo), "Hochrisiko-Muster schlaegt Niedrigrisiko-Muster")


# --------------------------------------------------------------------------
# AC-3: nur Text, Doku und Tests ist niedrig
# --------------------------------------------------------------------------

def test_only_text_docs_and_tests_is_low(tmp_path):
    """AC-3: jede Datei in der Niedrigrisiko-Liste → niedrig, 1 Runde (alle Muster zusammen)."""
    repo = _make_repo(tmp_path)
    _change(repo, *LOW_SAMPLES)

    report = _report(repo)

    _assert_low(report, "Reine Doku/Text/Tests")
    assert _file_count(report) == len(LOW_SAMPLES), (
        f"{len(LOW_SAMPLES)} geaenderte Dateien erwartet — war {report!r}")


@pytest.mark.parametrize("rel", LOW_SAMPLES)
def test_each_low_risk_pattern_alone_is_low(tmp_path, rel):
    """AC-3 (mild): jedes Niedrigrisiko-Muster traegt schon fuer sich allein."""
    repo = _make_repo(tmp_path)
    _change(repo, rel)

    _assert_low(_report(repo), rel)


def test_staged_and_untracked_files_count_for_low(tmp_path):
    """AC-3: gestagte und unversionierte Dateien gehoeren zur Liste (nicht nur Commits)."""
    repo = _make_repo(tmp_path)
    _change(repo, "docs/committed.md")
    _change(repo, "docs/staged.md", commit=False)
    _git(["add", "docs/staged.md"], repo)
    _change(repo, "docs/untracked.md", commit=False)

    report = _report(repo)

    _assert_low(report, "committet + gestagt + unversioniert")
    assert _file_count(report) == 3, f"alle drei Dateien muessen zaehlen — war {report!r}"

    # Spiegelprobe: eine unversionierte Hook-Datei kippt das Urteil.
    _change(repo, "core/hooks/untracked_guard.py", commit=False)
    _assert_high(_report(repo), "unversionierte Hook-Datei")


# --------------------------------------------------------------------------
# AC-4: im Zweifel hoch — jeder Fall einzeln
# --------------------------------------------------------------------------

DOUBT_CASES = [
    pytest.param("invalid-config",
                 _config(STD_BODY + "  high_risk_patterns: 'nicht-eine-liste'\n"),
                 ["docs/a.md"], ("config-invalid", "ungültig", "ungueltig", "invalid"),
                 id="invalid-config-wrong-shape"),
    pytest.param("invalid-regex",
                 _config(STD_BODY + "  low_risk_patterns: ['(unclosed']\n"),
                 ["docs/a.md"], ("config-invalid", "ungültig", "ungueltig", "invalid"),
                 id="invalid-config-broken-regex"),
    pytest.param("disabled", _config("  enabled: false\n  base_branch: base\n"),
                 ["docs/a.md"], ("disabled", "abgeschaltet"), id="disabled"),
    pytest.param("no-base", _config("  enabled: true\n"),
                 ["docs/a.md"], ("no-base", "basis"), id="no-base"),
    pytest.param("git-error", _config("  enabled: true\n  base_branch: gibt-es-nicht-4711\n"),
                 ["docs/a.md"], ("git-error", "git"), id="git-error"),
    pytest.param("empty", None, [], ("empty-list", "leer"), id="empty-list"),
    pytest.param("unknown", None, ["docs/a.md", "data/export.csv"], ("data/export.csv",),
                 id="unknown-file"),
]


@pytest.mark.parametrize("case,config_text,changed,reason_tokens", DOUBT_CASES)
def test_every_doubt_means_high(tmp_path, case, config_text, changed, reason_tokens):
    """AC-4: jeder Zweifelsfall liefert hohes Risiko, 2 Runden und einen Grund.

    Die Aenderung ist in allen Faellen sonst harmlos (nur Doku), damit nur der
    Zweifel selbst das Urteil `hoch` erklaeren kann.
    """
    repo = _make_repo(tmp_path, config_text=config_text)
    if changed:
        _change(repo, *changed)
    if case == "no-base":
        _git(["checkout", "-q", "--detach", "HEAD"], repo)

    report = _report(repo)

    _assert_high(report, f"Zweifelsfall {case}")
    reason = report["reason"].lower()
    assert any(tok.lower() in reason for tok in reason_tokens), (
        f"Grund fuer {case} soll einen von {reason_tokens} nennen — war {report['reason']!r}")
    if case == "empty":
        assert _file_count(report) == 0, f"leere Liste → files 0 — war {report!r}"


def test_report_reads_only_and_writes_nothing(tmp_path):
    """AC-4/Spec: `adversary_risk_report()` liest nur — der Git-Stand bleibt unveraendert."""
    repo = _make_repo(tmp_path)
    _change(repo, "docs/a.md", "core/hooks/x.py", commit=False)
    before = _git(["status", "--porcelain"], repo)
    head = _git(["rev-parse", "HEAD"], repo)

    _assert_high(_report(repo), "Hook-Datei")

    assert _git(["status", "--porcelain"], repo) == before
    assert _git(["rev-parse", "HEAD"], repo) == head


# --------------------------------------------------------------------------
# AC-5: eine Runde besteht nur bei niedrigem Risiko
# --------------------------------------------------------------------------

def test_one_round_passes_only_when_risk_is_low(tmp_path):
    """AC-5: DASSELBE Ein-Runden-Artefakt — niedrig akzeptiert, hoch lehnt wegen der Rundenzahl ab.

    Kontrollen: ein Zwei-Runden-Artefakt besteht auch bei hohem Risiko; ein
    Artefakt ohne jede Runde besteht auch bei niedrigem Risiko NICHT (keine
    Pruefung entfaellt vollstaendig).
    """
    low = _make_repo(tmp_path, "low")
    _change(low, "docs/a.md", commit=False)
    low_art = _make_dialog(low, rounds=1)
    _assert_low(_report(low), "Fixture niedrig")

    high = _make_repo(tmp_path, "high")
    _change(high, "docs/a.md", "core/hooks/guard.py", commit=False)
    high_art = _make_dialog(high, rounds=1)
    _assert_high(_report(high), "Fixture hoch")

    assert low_art.read_text(encoding="utf-8") == high_art.read_text(encoding="utf-8"), (
        "Fixture-Kontrolle: in beiden Repos muss exakt dasselbe Artefakt liegen")

    assert _evidence(low) is None, (
        "Niedriges Risiko: ein gueltiges Ein-Runden-Artefakt muss genuegen")
    reason = _evidence(high)
    assert isinstance(reason, str) and "runde" in reason.lower(), (
        f"Hohes Risiko: dasselbe Artefakt muss wegen der Rundenzahl abgelehnt werden — war {reason!r}")

    # Kontrolle hoch: zwei Runden genuegen weiterhin.
    _make_dialog(high, rounds=2)
    assert _evidence(high) is None, "Hohes Risiko: zwei Runden muessen weiter genuegen"

    # Kontrolle niedrig: null Runden genuegen nie.
    _make_dialog(low, rounds=0)
    zero = _evidence(low)
    assert isinstance(zero, str) and "runde" in zero.lower(), (
        f"Auch bei niedrigem Risiko ist mindestens eine Runde Pflicht — war {zero!r}")


# --------------------------------------------------------------------------
# AC-6: ohne Parameter bleibt es bei zwei Runden, unabhaengig vom Checkout
# --------------------------------------------------------------------------

def test_validate_without_parameter_keeps_two_rounds(tmp_path):
    """AC-6: `validate_dialog_artifact`/`_ex` ohne Parameter lehnen ein Ein-Runden-Artefakt ab —
    selbst in einem Checkout, der als niedriges Risiko eingestuft waere.

    Rot heute, weil `min_rounds` als Parameter fehlt: ohne ihn waere die
    Unabhaengigkeit vom Checkout nicht belegbar.
    """
    repo = _make_repo(tmp_path)
    _change(repo, "docs/a.md", commit=False)  # Checkout waere niedrig
    art = _make_dialog(repo, rounds=1)
    _assert_low(_report(repo), "Fixture niedrig")

    out = _py_json(repo, (
        "import inspect, adversary_dialog as ad\n"
        f"p = {str(art)!r}\n"
        "sig = inspect.signature(ad.validate_dialog_artifact_ex)\n"
        "ok2, msg2 = ad.validate_dialog_artifact(p)\n"
        "ex = ad.validate_dialog_artifact_ex(p)\n"
        "print(json.dumps({\n"
        "  'has_param': 'min_rounds' in sig.parameters,\n"
        "  'plain': [ok2, msg2], 'ex': [ex[0], ex[1]],\n"
        "  'min1': list(ad.validate_dialog_artifact_ex(p, min_rounds=1))[:2],\n"
        "  'min2': list(ad.validate_dialog_artifact_ex(p, min_rounds=2))[:2],\n"
        "  'MIN_ROUNDS': ad.MIN_ROUNDS}))\n"))

    assert out["MIN_ROUNDS"] == 2
    assert out["has_param"], "validate_dialog_artifact_ex braucht den Parameter `min_rounds`"
    assert out["plain"][0] is False, f"ohne Parameter muessen 2 Runden gelten — war {out['plain']}"
    assert "runde" in out["plain"][1].lower(), f"Grund nennt Runden — war {out['plain'][1]!r}"
    assert out["ex"][0] is False, f"_ex ohne Parameter muss ablehnen — war {out['ex']}"
    assert out["min1"][0] is True, f"min_rounds=1 akzeptiert Ein-Runden-Artefakt — war {out['min1']}"
    assert out["min2"][0] is False, f"min_rounds=2 lehnt es ab — war {out['min2']}"


# --------------------------------------------------------------------------
# AC-7: ungueltige Werte und Kill-Switch fallen auf zwei zurueck
# --------------------------------------------------------------------------

ROUND_CASES = [
    # (Config-Zusatz, enabled, geaenderte Dateien, erwartete Rundenzahl)
    pytest.param("  low_risk_min_rounds: 1\n", True, ["docs/a.md"], 1, id="valid-1-low"),
    pytest.param("  low_risk_min_rounds: 2\n", True, ["docs/a.md"], 2, id="valid-2-low"),
    pytest.param("  low_risk_min_rounds: zwei\n", True, ["docs/a.md"], 2, id="text"),
    pytest.param("  low_risk_min_rounds: 0\n", True, ["docs/a.md"], 2, id="zero"),
    pytest.param("  low_risk_min_rounds: -1\n", True, ["docs/a.md"], 2, id="negative"),
    pytest.param("  low_risk_min_rounds: 3\n", True, ["docs/a.md"], 2, id="greater-than-2"),
    pytest.param("  low_risk_min_rounds: 1\n", False, ["docs/a.md"], 2, id="kill-switch"),
    pytest.param("  low_risk_min_rounds: 1\n", True, ["docs/a.md", "core/hooks/x.py"], 2,
                 id="high-risk-ignores-low-setting"),
]


@pytest.mark.parametrize("extra,enabled,changed,expected", ROUND_CASES)
def test_invalid_values_and_kill_switch_fall_back_to_two(tmp_path, extra, enabled, changed,
                                                         expected):
    """AC-7: `required_rounds()` liefert 1 nur bei niedrigem Risiko UND gueltigem Wert.

    Text, 0, negativ, groesser als 2 und `enabled: false` fallen auf MIN_ROUNDS (2) zurueck.
    Die zwei `valid-*`-Faelle sind die Gegenprobe, dass die Funktion nicht pauschal 2 liefert.
    """
    body = f"  enabled: {'true' if enabled else 'false'}\n  base_branch: base\n{extra}"
    repo = _make_repo(tmp_path, config_text=_config(body))
    _change(repo, *changed)

    assert _rounds(repo) == expected


# --------------------------------------------------------------------------
# AC-8: CLI `adversary_dialog.py risk`
# --------------------------------------------------------------------------

@pytest.mark.parametrize("level,changed,rounds", [
    pytest.param("low", ["docs/a.md", "tests/test_a.py", "CHANGELOG.md"], 1, id="low"),
    pytest.param("high", ["docs/a.md", "tests/test_a.py", "core/hooks/guard.py"], 2, id="high"),
])
def test_risk_cli_reports_level_and_rounds(tmp_path, level, changed, rounds):
    """AC-8: `adversary_dialog.py risk` nennt Stufe, Begruendung, Dateianzahl und Rundenzahl; rc 0."""
    repo = _make_repo(tmp_path)
    _change(repo, *changed)
    report = _report(repo)  # Soll-Werte aus derselben Quelle, im selben Repo

    proc = _script("adversary_dialog.py", ["risk"], repo)

    assert proc.returncode == 0, (
        f"`risk` ist Auskunft, kein Gate: rc muss 0 sein — rc={proc.returncode}, "
        f"stdout={proc.stdout!r}, stderr={proc.stderr!r}")
    out = proc.stdout
    lowered = out.lower()
    words, other = (LOW_WORDS, HIGH_WORDS) if level == "low" else (HIGH_WORDS, LOW_WORDS)
    assert any(w in lowered for w in words), f"Stufe ({words}) fehlt in der Ausgabe: {out!r}"
    assert not any(re.search(rf"\b{w}\b", lowered) for w in other), (
        f"Ausgabe nennt die falsche Stufe ({other}): {out!r}")
    assert report["reason"] in out, (
        f"Begruendung {report['reason']!r} fehlt in der Ausgabe: {out!r}")
    assert any(re.search(r"datei|file", ln.lower()) and re.search(r"\b3\b", ln)
               for ln in out.splitlines()), f"Dateianzahl 3 fehlt in der Ausgabe: {out!r}"
    assert any(re.search(r"runde|round", ln.lower()) and re.search(rf"\b{rounds}\b", ln)
               for ln in out.splitlines()), f"Rundenzahl {rounds} fehlt in der Ausgabe: {out!r}"


# --------------------------------------------------------------------------
# AC-9: Texte und generierte Skills
# --------------------------------------------------------------------------

TEXT_FILES = [
    "core/commands/00-intake.md",
    "core/commands/50-implement.md",
    "core/agents/implementation-validator.md",
    "CLAUDE.md",
]
HIGH_CLAIM = re.compile(r"(?i)(mindestens|minimum|at least)\s+(2|zwei|two)\b")
LOW_CLAIM = re.compile(r"(?i)\b(1|eine|one)\s+(runde|round|dialog-runde|dialog round)\b")
ROUNDS_WORD = re.compile(r"(?i)\b(runden?|dialog-runden?|rounds?)\b")
RISK_WORD = re.compile(r"(?i)risiko|risk")


def test_texts_describe_risk_staging_and_skills_in_sync():
    """AC-9: alle vier Texte nennen „mindestens 2" bei hohem und „1 Runde" bei niedrigem Risiko,
    verweisen auf `adversary_dialog.py risk`, behaupten keine feste Rundenzahl fuer alle;
    `sync_skills.py --check` meldet keinen Drift.
    """
    problems = []
    for rel in TEXT_FILES:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        if not HIGH_CLAIM.search(text):
            problems.append(f"{rel}: nennt „mindestens 2 Runden“ (hohes Risiko) nicht")
        if not LOW_CLAIM.search(text):
            problems.append(f"{rel}: nennt „1 Runde“ (niedriges Risiko) nicht")
        if "adversary_dialog.py risk" not in text:
            problems.append(f"{rel}: verweist nicht auf `adversary_dialog.py risk`")
        # Keine feste Rundenzahl fuer alle: jede Zeile mit „mindestens 2 … Runden“ muss
        # das Risiko nennen, sonst gilt sie pauschal.
        for no, line in enumerate(text.splitlines(), 1):
            if HIGH_CLAIM.search(line) and ROUNDS_WORD.search(line) and not RISK_WORD.search(line):
                problems.append(f"{rel}:{no}: pauschale Rundenzahl ohne Risiko-Bezug: {line.strip()!r}")
    assert not problems, "Textvertrag verletzt:\n  " + "\n  ".join(problems)

    proc = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"), "--check"],
                          capture_output=True, text=True, cwd=str(REPO_ROOT), env=_env(),
                          stdin=subprocess.DEVNULL, timeout=120)
    assert proc.returncode == 0, (
        f"sync_skills.py --check meldet Drift: {proc.stdout}{proc.stderr}")
