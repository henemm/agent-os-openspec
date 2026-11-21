"""edit_gate: Anzeige-Abschnitte der wirksamen Config ohne Override aendern;
Planungshinweis fuer autarke Auftraege — Issue #622.

Spec: docs/specs/feat-622-config-additiv.md (AC-1 bis AC-9 + Unit-Test fuer
`config_loader.display_only_change`).

Muster wie #473 (tests/test_config_edit_schutz_473.py): `core/hooks/edit_gate.py`
bzw. `bash_gate.py` DIESES Arbeitsbaums laeuft als echter Subprozess gegen eine
Wegwerf-Sandbox in tmp_path (PreToolUse-JSON auf stdin). Abweichungen werden je
Test gesammelt, nicht beim ersten Fehler abgebrochen.

Wirksame Config im Sandbox-Projekt ist eine Root-`config.yaml` mit Plugin-Block
(`adversary_coverage_gate`, `qa_gate`), so wie #473 sie anlegt.

Festgelegte Schnittstelle:
  config_loader.DISPLAY_ONLY_CONFIG_KEYS == ("next_suggestion", "time_estimate")
  config_loader.display_only_change(old_text: str, new_text: str) -> bool

Importfehler des neuen Helfers sind Test-FAIL, kein Collection-Fehler: der
Import passiert erst im Testkoerper.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bash_gate_state_integrity_410 import (  # noqa: E402
    OVERRIDE_HINT, PLUGIN_CONFIG, _expect, _sandbox_ohne_workflow,
)
from test_config_edit_schutz_473 import (  # noqa: E402
    APP_CONFIG, CONFIG_MSG, HOOKS_DIR, REPO_ROOT, _check, _edit, _fail, _multi, _proj, _token, _write,
)

# --------------------------------------------------------------------- #
# Config-Fassungen
# --------------------------------------------------------------------- #

GATES = (
    "# Plugin-Config (Test #622)\n"
    "adversary_coverage_gate:\n"
    "  enabled: true\n"
    "qa_gate:\n"
    "  enabled: true\n"
)
NEXT_BLOCK = (
    "next_suggestion:\n"
    "  enabled: true\n"
    "  timeout_s: 8\n"
)
TIME_BLOCK = (
    "time_estimate:\n"
    "  enabled: true\n"
    "  min_samples: 3\n"
    "  quantiles: [0.25, 0.75]\n"
)
BASE = GATES                                   # ohne Anzeige-Abschnitte
FULL = GATES + NEXT_BLOCK + TIME_BLOCK          # mit beiden Anzeige-Abschnitten


def _cl():
    """Import erst im Test: Fehler = FAIL, nicht Collection-Error."""
    try:
        sys.path.insert(0, str(HOOKS_DIR))
        import config_loader
        return config_loader
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"config_loader nicht importierbar: {exc!r}")


def _doc(cl):
    fn = getattr(cl, "display_only_change", None)
    if fn is None:
        pytest.fail("config_loader.display_only_change fehlt (Spec #622)")
    return fn


# --------------------------------------------------------------------- #
# Unit: config_loader.display_only_change / DISPLAY_ONLY_CONFIG_KEYS
# --------------------------------------------------------------------- #

def test_display_only_change_pur_und_fail_closed():
    """Unit: `display_only_change` ist pur und gibt bei jedem Fehler False zurueck.

    True: gleiche Fassung (keine Aenderung zaehlt als „nur Anzeige“), nur
    Kommentare/Formatierung anders, Anzeige-Abschnitt hinzu/geaendert/entfernt.
    False: Gate-Wert geaendert, Gate-Abschnitt entfernt, neuer Nicht-Anzeige-
    Schluessel, doppelter Schluessel (top-level und verschachtelt), unlesbares
    YAML, Nicht-Mapping, None/Nicht-String. Wirft nie.
    """
    cl = _cl()
    keys = getattr(cl, "DISPLAY_ONLY_CONFIG_KEYS", None)
    assert keys == ("next_suggestion", "time_estimate"), \
        f"DISPLAY_ONLY_CONFIG_KEYS = {keys!r}"
    assert isinstance(keys, tuple), f"DISPLAY_ONLY_CONFIG_KEYS kein Tupel: {type(keys)}"
    doc = _doc(cl)

    true_cases = {
        "gleiche Fassung": (FULL, FULL),
        "nur Kommentar/Formatierung": (
            FULL, "# anderer Kommentar\n" + FULL.replace("enabled: true\n", "enabled: true   # x\n")),
        "Flow-Stil statt Block-Stil": (
            BASE, "adversary_coverage_gate: {enabled: true}\nqa_gate: {enabled: true}\n"),
        "time_estimate hinzu": (BASE, BASE + TIME_BLOCK),
        "next_suggestion hinzu": (BASE, BASE + NEXT_BLOCK),
        "beide hinzu": (BASE, FULL),
        "time_estimate geaendert": (FULL, FULL.replace("min_samples: 3", "min_samples: 7")),
        "next_suggestion geaendert": (FULL, FULL.replace("timeout_s: 8", "timeout_s: 12")),
        "time_estimate entfernt": (FULL, GATES + NEXT_BLOCK),
        "beide entfernt": (FULL, BASE),
        "Anzeige-Abschnitt auf null": (FULL, GATES + NEXT_BLOCK + "time_estimate:\n"),
    }
    false_cases = {
        "Gate-Wert geaendert": (
            FULL, FULL.replace("adversary_coverage_gate:\n  enabled: true",
                               "adversary_coverage_gate:\n  enabled: false")),
        "Gate-Wert + Anzeige geaendert": (
            FULL, FULL.replace("qa_gate:\n  enabled: true", "qa_gate:\n  enabled: false")
                      .replace("min_samples: 3", "min_samples: 4")),
        "Gate-Abschnitt entfernt": (
            FULL, "qa_gate:\n  enabled: true\n" + NEXT_BLOCK + TIME_BLOCK),
        "neuer Gate-Abschnitt": (
            "qa_gate:\n  enabled: true\n",
            "qa_gate:\n  enabled: true\nadversary_coverage_gate: {enabled: false}\n"),
        "neuer fremder Schluessel": (BASE, BASE + "foo: 1\n" + TIME_BLOCK),
        "Typ eines Gate-Werts geaendert": (
            BASE, BASE.replace("qa_gate:\n  enabled: true", 'qa_gate:\n  enabled: "true"')),
        "doppelter Gate-Schluessel (letzter gleich)": (
            BASE, "qa_gate:\n  enabled: false\n" + BASE + TIME_BLOCK),
        "doppelter Anzeige-Schluessel": (BASE, BASE + TIME_BLOCK + TIME_BLOCK),
        "doppelter verschachtelter Schluessel": (
            BASE, BASE + "time_estimate:\n  enabled: true\n  enabled: false\n"),
        "doppelter Schluessel in alter Fassung": (
            BASE + "qa_gate:\n  enabled: true\n", BASE + "qa_gate:\n  enabled: true\n" + TIME_BLOCK),
        "neue Fassung unlesbar": (BASE, BASE + "time_estimate: [unclosed\n"),
        "alte Fassung unlesbar": ("qa_gate: [x\n", BASE),
        "neue Fassung Liste": (BASE, "- qa_gate\n- time_estimate\n"),
        "neue Fassung Skalar": (BASE, "nur ein text\n"),
        "neue Fassung leer": (BASE, ""),
        "alte Fassung leer": ("", TIME_BLOCK),
        "Tab-Einrueckung (YAML-Fehler)": (BASE, BASE + "time_estimate:\n\tenabled: true\n"),
    }
    weird = [(None, FULL), (FULL, None), (None, None), (1, FULL), (FULL, b"x: 1\n"),
             (FULL, ["x"])]

    wrong = []
    for label, (old, new) in true_cases.items():
        try:
            got = doc(old, new)
        except Exception as exc:
            wrong.append(f"  {label}: wirft {exc!r} (soll True)")
            continue
        if got is not True:
            wrong.append(f"  {label}: {got!r} (soll True)")
    for label, (old, new) in false_cases.items():
        try:
            got = doc(old, new)
        except Exception as exc:
            wrong.append(f"  {label}: wirft {exc!r} (soll False)")
            continue
        if got is not False:
            wrong.append(f"  {label}: {got!r} (soll False)")
    for old, new in weird:
        try:
            got = doc(old, new)
        except Exception as exc:
            wrong.append(f"  ({old!r}, {new!r}): wirft {exc!r} (soll False)")
            continue
        if got is not False:
            wrong.append(f"  ({old!r}, {new!r}): {got!r} (soll False)")
    # pur: Eingaben bleiben unveraendert, gleiche Eingabe -> gleiches Ergebnis
    a, b = BASE, BASE + TIME_BLOCK
    if doc(a, b) != doc(a, b) or a != BASE or b != BASE + TIME_BLOCK:
        wrong.append("  nicht deterministisch/pur")
    _fail("Unit display_only_change", wrong)


# --------------------------------------------------------------------- #
# AC-1
# --------------------------------------------------------------------- #

def test_write_neuer_anzeige_abschnitt_erlaubt(tmp_path):
    """AC-1: Write fuegt `time_estimate` (bzw. `next_suggestion`) zur wirksamen
    Config hinzu, alle anderen Schluessel gleich -> Exit 0 ohne Token, keine
    Config-Meldung. Geprueft fuer Root-`config.yaml` und Root-`openspec.yaml`."""
    wrong = []
    for i, rel in enumerate(("config.yaml", "openspec.yaml")):
        for j, (label, content) in enumerate((
            ("time_estimate hinzu", BASE + TIME_BLOCK),
            ("next_suggestion hinzu", BASE + NEXT_BLOCK),
            ("time_estimate hinzu, Kommentar anders", "# neu\n" + BASE + TIME_BLOCK),
        )):
            proj, home = _proj(tmp_path / f"s{i}{j}", {rel: BASE})
            wrong += _check(f"{rel}: {label}", _write(proj / rel, content),
                            proj, home, 0, forbid=CONFIG_MSG)
    _fail("AC-1", wrong)


# --------------------------------------------------------------------- #
# AC-2
# --------------------------------------------------------------------- #

def test_edit_und_multiedit_aendern_entfernen_anzeige_abschnitt_erlaubt(tmp_path):
    """AC-2: Edit aendert einen Wert in `time_estimate`/`next_suggestion`,
    MultiEdit entfernt einen der Abschnitte -> Exit 0 ohne Token."""
    wrong = []
    cases = (
        ("Edit time_estimate", _edit, ("min_samples: 3", "min_samples: 5")),
        ("Edit next_suggestion", _edit, ("timeout_s: 8", "timeout_s: 12")),
        ("MultiEdit entfernt time_estimate", _multi, ((TIME_BLOCK, ""),)),
        ("MultiEdit entfernt next_suggestion", _multi, ((NEXT_BLOCK, ""),)),
        ("MultiEdit aendert beide",
         _multi, (("min_samples: 3", "min_samples: 4"), ("timeout_s: 8", "timeout_s: 9"))),
    )
    for i, (label, fn, args) in enumerate(cases):
        proj, home = _proj(tmp_path / f"s{i}", {"config.yaml": FULL})
        target = proj / "config.yaml"
        call = fn(target, *args)
        wrong += _check(label, call, proj, home, 0, forbid=CONFIG_MSG)
    _fail("AC-2", wrong)


# --------------------------------------------------------------------- #
# AC-3
# --------------------------------------------------------------------- #

def test_gate_schluessel_aendern_blockiert(tmp_path):
    """AC-3: Edit aendert einen bestehenden Gate-Schluessel -> Exit 2 + 'override'
    (auch zusammen mit einer Anzeige-Aenderung im selben MultiEdit)."""
    proj, home = _proj(tmp_path, {"config.yaml": FULL})
    target = proj / "config.yaml"
    wrong = []
    for label, call in (
        ("Edit adversary_coverage_gate.enabled",
         _edit(target, "adversary_coverage_gate:\n  enabled: true",
               "adversary_coverage_gate:\n  enabled: false")),
        ("Edit qa_gate.enabled",
         _edit(target, "qa_gate:\n  enabled: true", "qa_gate:\n  enabled: false")),
        ("MultiEdit Anzeige + Gate",
         _multi(target, ("min_samples: 3", "min_samples: 4"),
                ("qa_gate:\n  enabled: true", "qa_gate:\n  enabled: false"))),
    ):
        wrong += _check(label, call, proj, home, 2, OVERRIDE_HINT)
    _fail("AC-3", wrong)


# --------------------------------------------------------------------- #
# AC-4
# --------------------------------------------------------------------- #

def test_gate_schluessel_entfernen_oder_neu_einfuegen_blockiert(tmp_path):
    """AC-4: Write entfernt einen Gate-Abschnitt oder fuegt einen neuen Abschnitt
    ausserhalb der Anzeige-Liste ein -> Exit 2 + 'override'."""
    wrong = []
    proj, home = _proj(tmp_path / "a", {"config.yaml": FULL})
    target = proj / "config.yaml"
    for label, content in (
        ("Gate-Abschnitt entfernt", "qa_gate:\n  enabled: true\n" + NEXT_BLOCK + TIME_BLOCK),
        ("neuer Gate-Abschnitt adr_gate", FULL + "adr_gate:\n  enabled: false\n"),
        ("fremder neuer Schluessel", FULL + "foo: 1\n"),
    ):
        wrong += _check(label, _write(target, content), proj, home, 2, OVERRIDE_HINT)
    # adversary_coverage_gate fehlt bisher und wird eingeschmuggelt
    proj2, home2 = _proj(tmp_path / "b", {"config.yaml": "qa_gate:\n  enabled: true\n"})
    wrong += _check("adversary_coverage_gate: {enabled: false} eingefuegt",
                    _write(proj2 / "config.yaml",
                           "qa_gate:\n  enabled: true\n"
                           "adversary_coverage_gate: {enabled: false}\n" + TIME_BLOCK),
                    proj2, home2, 2, OVERRIDE_HINT)
    wrong += _check("Edit fuegt Gate-Abschnitt ein",
                    _edit(proj2 / "config.yaml", "qa_gate:\n  enabled: true",
                          "qa_gate:\n  enabled: true\nadversary_coverage_gate: {enabled: false}"),
                    proj2, home2, 2, OVERRIDE_HINT)
    _fail("AC-4", wrong)


# --------------------------------------------------------------------- #
# AC-5
# --------------------------------------------------------------------- #

def test_doppelte_schluessel_und_unlesbares_yaml_blockiert(tmp_path):
    """AC-5: Anzeige-Aenderung, aber doppelter Schluessel (top-level oder
    verschachtelt) oder unlesbares YAML/Nicht-Mapping -> Exit 2 (fail-closed).

    Der Fall 'doppelter Gate-Schluessel, letzter Wert gleich' ist der eigentliche
    Angriff: ein lascher Loader (letzter gewinnt) saehe keine Aenderung."""
    proj, home = _proj(tmp_path, {"config.yaml": BASE})
    target = proj / "config.yaml"
    wrong = []
    for label, content in (
        ("doppelter Gate-Schluessel", "qa_gate:\n  enabled: false\n" + BASE + TIME_BLOCK),
        ("doppelter Anzeige-Schluessel", BASE + TIME_BLOCK + TIME_BLOCK),
        ("doppelter verschachtelter Schluessel",
         BASE + "time_estimate:\n  enabled: true\n  enabled: false\n"),
        ("unlesbares YAML", BASE + "time_estimate: [unclosed\n"),
        ("Tab-Einrueckung", BASE + "time_estimate:\n\tenabled: true\n"),
    ):
        wrong += _check(label, _write(target, content), proj, home, 2, OVERRIDE_HINT)
    wrong += _check("Edit erzeugt doppelten Schluessel",
                    _edit(target, "# Plugin-Config (Test #622)",
                          "qa_gate:\n  enabled: false\ntime_estimate:\n  enabled: true"),
                    proj, home, 2, OVERRIDE_HINT)
    _fail("AC-5", wrong)


# --------------------------------------------------------------------- #
# AC-6
# --------------------------------------------------------------------- #

def test_app_config_ohne_plugin_block_und_anlegen_vorrangiger_config_blockiert(tmp_path):
    """AC-6: App-`config.yaml` ohne Plugin-Block (nicht wirksam) bekommt einen
    Anzeige-Abschnitt, oder eine vorrangige Config wird neu angelegt (mit oder
    ohne bestehende wirksame Config) -> Exit 2 + 'override'."""
    wrong = []
    # (a) App-config.yaml neben wirksamer .claude/openspec.yaml
    proj, home = _proj(tmp_path / "a", {".claude/openspec.yaml": PLUGIN_CONFIG,
                                        "config.yaml": APP_CONFIG})
    app = proj / "config.yaml"
    wrong += _check("App-config Write + time_estimate",
                    _write(app, APP_CONFIG + TIME_BLOCK), proj, home, 2, OVERRIDE_HINT)
    wrong += _check("App-config Edit + next_suggestion",
                    _edit(app, "name: app", "name: app\nnext_suggestion:\n  enabled: true"),
                    proj, home, 2, OVERRIDE_HINT)
    # (b) vorrangige openspec.yaml anlegen, wirksam ist .claude/openspec.yaml
    proj2, home2 = _proj(tmp_path / "b", {".claude/openspec.yaml": PLUGIN_CONFIG + TIME_BLOCK})
    wrong += _check("vorrangige openspec.yaml anlegen",
                    _write(proj2 / "openspec.yaml", PLUGIN_CONFIG + TIME_BLOCK),
                    proj2, home2, 2, OVERRIDE_HINT)
    # (c) keine wirksame Config: jede neue Config mit Anzeige-Abschnitt blockt
    proj3, home3 = _proj(tmp_path / "c")
    for rel in ("openspec.yaml", ".claude/openspec.yaml", "config.yaml"):
        wrong += _check(f"ohne wirksame Config: {rel} anlegen",
                        _write(proj3 / rel, TIME_BLOCK), proj3, home3, 2, OVERRIDE_HINT)
    _fail("AC-6", wrong)


# --------------------------------------------------------------------- #
# AC-7
# --------------------------------------------------------------------- #

def test_bash_schreibzugriff_bleibt_blockiert(tmp_path):
    """AC-7: Bash-Schreibumleitung, die nur einen Anzeige-Abschnitt anhaengt,
    blockt `bash_gate.py` weiterhin ohne Token (Inhalt nicht pruefbar)."""
    wrong = []
    a = _sandbox_ohne_workflow(tmp_path / "a")
    (a / "config.yaml").write_text(BASE)
    wrong += _expect([
        "printf 'time_estimate:\\n  enabled: true\\n' >> config.yaml",
        "echo 'next_suggestion: {enabled: true}' >> config.yaml",
    ], a, 2, OVERRIDE_HINT)
    b = _sandbox_ohne_workflow(tmp_path / "b")
    (b / "openspec.yaml").write_text(BASE)
    wrong += _expect(["echo 'time_estimate: {enabled: true}' >> openspec.yaml"],
                     b, 2, OVERRIDE_HINT)
    _fail("AC-7", wrong)


# --------------------------------------------------------------------- #
# AC-8
# --------------------------------------------------------------------- #

def test_override_wirkt_weiter(tmp_path):
    """AC-8: gueltiger Override-Token -> Gate-Schluessel-Aenderung Exit 0
    (Vorbedingung: ohne Token Exit 2)."""
    proj, home = _proj(tmp_path, {"config.yaml": FULL})
    target = proj / "config.yaml"
    calls = [
        _edit(target, "adversary_coverage_gate:\n  enabled: true",
              "adversary_coverage_gate:\n  enabled: false"),
        _write(target, "qa_gate:\n  enabled: false\n"),
    ]
    wrong = []
    for call in calls:
        wrong += _check("ohne Token", call, proj, home, 2, OVERRIDE_HINT)
    _token(proj)
    for call in calls:
        wrong += _check("mit Token", call, proj, home, 0)
    _fail("AC-8", wrong)


# --------------------------------------------------------------------- #
# AC-9
# --------------------------------------------------------------------- #

PLAN_FILES = (
    "core/commands/00-intake.md",
    "core/commands/30-write-spec.md",
    "skills/00-intake/SKILL.md",
    "skills/30-write-spec/SKILL.md",
)
# Alle Begriffe muessen (case-insensitive) in EINEM Absatz stehen.
PLAN_TERMS = ("autark", "override", "gate-config", "next_suggestion", "time_estimate")


def _paragraphs(text: str) -> list:
    """Absatz = Block zwischen Leerzeilen (Zeilen nur aus Leerraum zaehlen leer)."""
    return [p for p in re.split(r"\n[ \t]*\n", text) if p.strip()]


def test_planungshinweis_in_befehlstexten_und_skills_ohne_drift():
    """AC-9: Planungshinweis fuer autarke Auftraege in 00-intake und 30-write-spec
    (Quelle `core/commands/` und Generat `skills/`), `sync_skills.py --check` Exit 0.

    Pruefregel: In jeder der vier Dateien gibt es mindestens EINEN Absatz (Block
    zwischen Leerzeilen), der alle Begriffe aus PLAN_TERMS enthaelt, ohne
    Gross-/Kleinschreibung: „autark“ (auch „autarken“/„autarker“), „override“,
    „Gate-Config“, `next_suggestion` und `time_estimate`. Das entspricht dem
    Spec-Wortlaut (autarker Auftrag, keine Override-Schritte, Gate-Config-
    Aenderungen vermeiden, Anzeige-Abschnitte ausgenommen). Nur „autark“ +
    „override“ reicht bewusst nicht: 00-intake hat schon heute einen Absatz
    mit „autarker Auftrag … Override“ (Pflichtstopps), der den Hinweis nicht
    enthaelt.
    """
    wrong = []
    for rel in PLAN_FILES:
        path = REPO_ROOT / rel
        if not path.is_file():
            wrong.append(f"  {rel}: fehlt")
            continue
        paras = _paragraphs(path.read_text(encoding="utf-8"))
        if not any(all(t in p.lower() for t in PLAN_TERMS) for p in paras):
            wrong.append(f"  {rel}: kein Absatz mit allen Begriffen {PLAN_TERMS}")
    proc = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"),
                           "--check"], cwd=str(REPO_ROOT), capture_output=True,
                          text=True, timeout=120)
    if proc.returncode != 0:
        wrong.append(f"  sync_skills.py --check: rc={proc.returncode}, "
                     f"{(proc.stdout + proc.stderr).strip()[-300:]!r}")
    _fail("AC-9", wrong)
