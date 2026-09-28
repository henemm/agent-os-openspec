"""Beobachtbare Oberflaeche erkennen — Vertrag von `has_observable_surface()`
und des CLI-Unterbefehls `workflow.py observable-surface` (Issue #260).

Die Pruefung entscheidet, ob die Schlussfrage „Soll ich den Code committen?"
in `/60-validate` entfaellt. Sie ist bewusst fail-closed: nur ein positiver
Nachweis, dass JEDE geaenderte Datei nachweislich keine Oberflaeche beruehrt,
fuehrt zu `no`. Jede Unsicherheit — kaputte Config, kein Basis-Stand,
`git`-Fehler, leere Dateiliste, unbekannte Endung — liefert `yes`.

## Warum Subprozess + eigenes Wegwerf-Repo pro Testfall

`config_loader.load_config()` und `config_loader.find_project_root()` tragen
`@lru_cache(maxsize=1)`; `hook_utils.find_project_root()` liest die Wurzel
ebenfalls aus dem Prozesszustand (CWD / `CLAUDE_PROJECT_DIR`). Ein
In-Process-Test mit mehreren Konfigurationsstaenden in derselben
Python-Session wuerde ab dem zweiten Fall den zwischengespeicherten Stand des
ersten Falls wiederverwenden — die Tests waeren reihenfolgeabhaengig und
teilweise wirkungslos. Dieselbe Begruendung und derselbe Ansatz stehen im
Docstring von `tests/test_loc_gate_config_source_153.py` (Issue #153).

## Warum `base_branch` statt `origin/HEAD`

Der Basis-Stand wird in den Wegwerf-Repos deterministisch ueber
`observable_surface.base_branch` gesetzt. Ein Wegwerf-Repo hat kein `origin`,
und `git symbolic-ref --short refs/remotes/origin/HEAD` waere dort von der
Umgebung abhaengig. Genau ein Test (AC-3) laesst diesen Weg absichtlich
weg, um den `no-base`-Fall zu erreichen.

`OPENSPEC_ACTIVE_WORKFLOW` wird im Subprozess-Env bewusst NICHT gesetzt: die
Auskunft ist ein Read-only-Report und darf keinen aktiven Workflow brauchen.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PY = REPO_ROOT / "core" / "hooks" / "workflow.py"
VALIDATE_MD = REPO_ROOT / "core" / "commands" / "60-validate.md"

# Die fuenf Zeilen der CLI-Auskunft, in verbindlicher Reihenfolge (AC-13).
EXPECTED_KEYS = ["OBSERVABLE_SURFACE", "REASON", "FILES", "ROOT", "CONFIG"]


# --------------------------------------------------------------------------
# Helfer: Wegwerf-Repo bauen
# --------------------------------------------------------------------------

def _git(args, cwd: Path, check: bool = True):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), check=check,
        capture_output=True, text=True,
    )


def _touch(repo: Path, rel: str, text: str = "x\n") -> None:
    """Datei anlegen/ueberschreiben, Elternverzeichnisse inklusive."""
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _config_yaml(body: str) -> str:
    """`observable_surface`-Block fuer die Wegwerf-`config.yaml`."""
    return "observable_surface:\n" + body


def _make_repo(root: Path, config_body: str) -> Path:
    """Wegwerf-Git-Repo mit eigener Projektwurzel.

    Eigene Projektwurzel heisst fuer `config_loader.find_project_root()`:
    eine Datei aus `CONFIG_NAMES` (hier `config.yaml`) ODER ein `.git`-
    VERZEICHNIS im selben Ordner — `git init` liefert beides. Der Basis-Commit
    enthaelt die `config.yaml` bereits, damit sie nicht selbst als geaenderte
    Datei in der Messung auftaucht.

    Legt zusaetzlich den Zweig `base` auf dem Basis-Commit an; Tests, die einen
    Basis-Stand brauchen, zeigen mit `base_branch: base` darauf.
    """
    root.mkdir(parents=True, exist_ok=True)
    _git(["init", "-b", "main"], root)
    _git(["config", "user.email", "test@example.invalid"], root)
    _git(["config", "user.name", "Test"], root)
    _git(["config", "commit.gpgsign", "false"], root)

    (root / "config.yaml").write_text(_config_yaml(config_body), encoding="utf-8")
    _touch(root, "README.md", "# Wegwerf\n")
    _git(["add", "-A"], root)
    _git(["commit", "-m", "base"], root)
    _git(["branch", "base"], root)
    return root


def _commit(repo: Path, message: str = "change") -> None:
    _git(["add", "-A"], repo)
    _git(["commit", "-m", message], repo)


# --------------------------------------------------------------------------
# Helfer: CLI aufrufen und stdout parsen
# --------------------------------------------------------------------------

def _run_cli(repo: Path):
    """`workflow.py observable-surface` als Subprozess mit `cwd=repo`."""
    env = dict(os.environ)
    for var in ("CLAUDE_PROJECT_DIR", "CLAUDE_TOOL_INPUT",
                "OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK"):
        env.pop(var, None)
    return subprocess.run(
        [sys.executable, str(WORKFLOW_PY), "observable-surface"],
        cwd=str(repo), capture_output=True, text=True, timeout=120, env=env,
    )


def _parse(proc) -> dict:
    """Die `KEY=value`-Zeilen aus stdout als Dict. Fehlt eine, fehlt sie."""
    out = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            if key in EXPECTED_KEYS and key not in out:
                out[key] = value
    return out


def _surface(repo: Path):
    """(surface, reason, felder, proc) — mit sprechender Meldung bei Ausfall."""
    proc = _run_cli(repo)
    fields = _parse(proc)
    assert proc.returncode == 0, (
        "Der Unterbefehl `observable-surface` muss immer mit Code 0 enden "
        f"(Auskunft, kein Gate) — rc={proc.returncode}, "
        f"stdout={proc.stdout!r}, stderr={proc.stderr!r}"
    )
    assert "OBSERVABLE_SURFACE" in fields, (
        "stdout muss eine Zeile `OBSERVABLE_SURFACE=yes|no` enthalten — "
        f"stdout={proc.stdout!r}, stderr={proc.stderr!r}"
    )
    assert "REASON" in fields, (
        f"stdout muss eine Zeile `REASON=` enthalten — stdout={proc.stdout!r}"
    )
    return fields["OBSERVABLE_SURFACE"], fields["REASON"], fields, proc


# --------------------------------------------------------------------------
# AC-1 .. AC-13: Vertrag von has_observable_surface() ueber die CLI
# --------------------------------------------------------------------------

def test_ac1_config_invalid_keeps_the_question(tmp_path):
    """AC-1: fehlerhaft geformter Config-Block ist streng.

    GIVEN: ein Wegwerf-Git-Repo, dessen `observable_surface.surface_patterns`
           eine Zeichenkette statt einer Liste ist.
    WHEN:  `workflow.py observable-surface` dort laeuft.
    THEN:  Ergebnis `yes` mit Begruendung `config-invalid` — Schritt 1 des
           Vertrags, noch vor jeder `git`-Abfrage.
    """
    repo = _make_repo(tmp_path / "repo",
                      "  enabled: true\n"
                      "  base_branch: base\n"
                      "  surface_patterns: 'nicht-eine-liste'\n")

    surface, reason, _fields, proc = _surface(repo)

    assert surface == "yes", (
        "Ein unbrauchbar geformter Config-Block muss streng sein "
        f"(yes) — war {surface!r}, stdout={proc.stdout!r}"
    )
    assert "config-invalid" in reason, (
        f"Begruendung muss `config-invalid` nennen — war {reason!r}"
    )


def test_ac2_disabled_keeps_the_question(tmp_path):
    """AC-2: abgeschaltete Pruefung ist streng.

    GIVEN: ein Wegwerf-Git-Repo mit `observable_surface.enabled: false` und
           einer geaenderten Datei, die klar keine Oberflaeche hat.
    WHEN:  `workflow.py observable-surface` dort laeuft.
    THEN:  Ergebnis `yes` mit Begruendung `disabled` — unabhaengig vom Inhalt
           der geaenderten Dateien.
    """
    repo = _make_repo(tmp_path / "repo",
                      "  enabled: false\n"
                      "  base_branch: base\n")
    _touch(repo, "core/hooks/irgendwas.py", "X = 1\n")
    _commit(repo)

    surface, reason, _fields, proc = _surface(repo)

    assert surface == "yes", (
        "Bei `enabled: false` darf die Frage nie entfallen — "
        f"war {surface!r}, stdout={proc.stdout!r}"
    )
    assert "disabled" in reason, (
        f"Begruendung muss `disabled` nennen — war {reason!r}"
    )


def test_ac3_no_base_keeps_the_question(tmp_path):
    """AC-3: kein aufloesbarer Basis-Stand ist streng.

    GIVEN: ein Wegwerf-Git-Repo ohne `origin`-Remote, ohne `base_branch` in der
           Config und mit detached HEAD.
    WHEN:  `workflow.py observable-surface` dort laeuft.
    THEN:  Ergebnis `yes` mit Begruendung `no-base` — es gibt keinen literalen
           Rueckfallwert wie `origin/main`.
    """
    repo = _make_repo(tmp_path / "repo", "  enabled: true\n")
    _touch(repo, "core/hooks/irgendwas.py", "X = 1\n")
    _commit(repo)
    _git(["checkout", "--detach", "HEAD"], repo)

    surface, reason, _fields, proc = _surface(repo)

    assert surface == "yes", (
        "Ohne aufloesbaren Basis-Stand muss die Frage bleiben — "
        f"war {surface!r}, stdout={proc.stdout!r}"
    )
    assert "no-base" in reason, (
        f"Begruendung muss `no-base` nennen — war {reason!r}"
    )


def test_ac4_git_error_keeps_the_question(tmp_path):
    """AC-4: ein fehlgeschlagener `git`-Aufruf ist streng.

    GIVEN: ein Wegwerf-Git-Repo, dessen `base_branch` auf eine nicht
           existierende Referenz zeigt, sodass `git merge-base` mit einem
           Rueckgabecode != 0 endet.
    WHEN:  `workflow.py observable-surface` dort laeuft.
    THEN:  Ergebnis `yes` mit Begruendung `git-error`.
    """
    repo = _make_repo(tmp_path / "repo",
                      "  enabled: true\n"
                      "  base_branch: gibt-es-nicht-4711\n")
    _touch(repo, "core/hooks/irgendwas.py", "X = 1\n")
    _commit(repo)

    surface, reason, _fields, proc = _surface(repo)

    assert surface == "yes", (
        "Ein git-Fehler muss streng sein — "
        f"war {surface!r}, stdout={proc.stdout!r}"
    )
    assert "git-error" in reason, (
        f"Begruendung muss `git-error` nennen — war {reason!r}"
    )


def test_ac5_empty_list_keeps_the_question(tmp_path):
    """AC-5: leere Dateiliste ist streng — VOR dem Non-Surface-Fall.

    GIVEN: ein Wegwerf-Git-Repo, das gegenueber dem Basis-Stand keine einzige
           geaenderte, gestagete oder unversionierte Datei hat.
    WHEN:  `workflow.py observable-surface` dort laeuft.
    THEN:  Ergebnis `yes` mit Begruendung `empty-list` und `FILES=0`. Ginge die
           leere Liste stattdessen durch Schritt 8, lieferte `all([])` in Python
           `True` und damit faelschlich `no`.
    """
    repo = _make_repo(tmp_path / "repo",
                      "  enabled: true\n"
                      "  base_branch: base\n")

    surface, reason, fields, proc = _surface(repo)

    assert surface == "yes", (
        "Eine leere Dateiliste darf nie als `keine Oberflaeche` durchgehen "
        f"(all([]) is True) — war {surface!r}, stdout={proc.stdout!r}"
    )
    assert "empty-list" in reason, (
        f"Begruendung muss `empty-list` nennen — war {reason!r}"
    )
    assert fields.get("FILES") == "0", (
        f"FILES muss 0 sein — war {fields.get('FILES')!r}"
    )


def test_ac6_surface_match_keeps_the_question(tmp_path):
    """AC-6: ein einziger Surface-Treffer genuegt.

    GIVEN: ein Wegwerf-Git-Repo mit genau einer geaenderten Datei, die
           `surface_patterns` trifft (`core/commands/foo.md`), neben mehreren
           Dateien, die `non_surface_patterns` treffen.
    WHEN:  `workflow.py observable-surface` dort laeuft.
    THEN:  Ergebnis `yes`, und die Begruendung nennt die Datei plus
           `trifft surface`.
    """
    repo = _make_repo(tmp_path / "repo",
                      "  enabled: true\n"
                      "  base_branch: base\n")
    _touch(repo, "core/commands/foo.md", "# Befehl\n")
    _touch(repo, "core/hooks/a.py", "A = 1\n")
    _touch(repo, "tests/test_a.py", "def test_a():\n    pass\n")
    _commit(repo)

    surface, reason, fields, proc = _surface(repo)

    assert surface == "yes", (
        "Eine Datei unter core/commands/ ist Oberflaeche (PO-Entscheidung E1) — "
        f"war {surface!r}, stdout={proc.stdout!r}"
    )
    assert "trifft surface" in reason, (
        f"Begruendung muss `trifft surface` nennen — war {reason!r}"
    )
    assert "core/commands/foo.md" in reason, (
        f"Begruendung muss die ausloesende Datei nennen — war {reason!r}"
    )
    assert fields.get("FILES") == "3", (
        f"Alle drei geaenderten Dateien muessen gezaehlt sein — war {fields.get('FILES')!r}"
    )


def test_ac7_all_non_surface_drops_the_question(tmp_path):
    """AC-7: reine Hook-/Test-Aenderung — die Frage entfaellt.

    GIVEN: ein Wegwerf-Git-Repo, in dem ausschliesslich Dateien unter
           `core/hooks/` und `tests/` geaendert sind.
    WHEN:  `workflow.py observable-surface` dort laeuft.
    THEN:  Ergebnis `no` mit Begruendung „alle 2 Dateien ohne Oberflaeche".
           Das ist der EINZIGE Weg zu `no`.
    """
    repo = _make_repo(tmp_path / "repo",
                      "  enabled: true\n"
                      "  base_branch: base\n")
    _touch(repo, "core/hooks/a.py", "A = 1\n")
    _touch(repo, "tests/test_b.py", "def test_b():\n    pass\n")
    _commit(repo)

    surface, reason, fields, proc = _surface(repo)

    assert surface == "no", (
        "Nur Hooks und Tests geaendert: die Schlussfrage muss entfallen — "
        f"war {surface!r}, stdout={proc.stdout!r}"
    )
    assert "ohne Oberfl" in reason, (
        f"Begruendung muss `ohne Oberflaeche` nennen — war {reason!r}"
    )
    assert "2" in reason, (
        f"Begruendung muss die Anzahl der Dateien nennen — war {reason!r}"
    )
    assert fields.get("FILES") == "2", (
        f"FILES muss 2 sein — war {fields.get('FILES')!r}"
    )


def test_ac8_unknown_extension_keeps_the_question(tmp_path):
    """AC-8: unbekannte Endung ist streng.

    GIVEN: ein Wegwerf-Git-Repo mit einer geaenderten `data/export.csv`, die
           weder `surface_patterns` noch `non_surface_patterns` trifft.
    WHEN:  `workflow.py observable-surface` dort laeuft.
    THEN:  Ergebnis `yes`, Begruendung nennt die Datei und `unbekannt`. Diese
           Regel traegt die gesamte Sicherheit des Verfahrens und darf von
           keinem Refactoring stillschweigend umgedreht werden.
    """
    repo = _make_repo(tmp_path / "repo",
                      "  enabled: true\n"
                      "  base_branch: base\n")
    _touch(repo, "data/export.csv", "a,b\n1,2\n")
    _touch(repo, "core/hooks/a.py", "A = 1\n")
    _commit(repo)

    surface, reason, _fields, proc = _surface(repo)

    assert surface == "yes", (
        "Eine Datei, die keine der beiden Listen trifft, muss streng sein — "
        f"war {surface!r}, stdout={proc.stdout!r}"
    )
    assert "unbekannt" in reason, (
        f"Begruendung muss `unbekannt` nennen — war {reason!r}"
    )
    assert "data/export.csv" in reason, (
        f"Begruendung muss die ausloesende Datei nennen — war {reason!r}"
    )


def test_ac9_lovelace_dashboard_keeps_the_question(tmp_path):
    """AC-9: Home-Assistant-Dashboard ist Oberflaeche.

    GIVEN: ein Wegwerf-Git-Repo mit geaenderter `lovelace/dashboard.yaml`.
    WHEN:  `workflow.py observable-surface` dort laeuft.
    THEN:  Ergebnis `yes` — ein Dashboard sieht der PO unmittelbar.
    """
    repo = _make_repo(tmp_path / "repo",
                      "  enabled: true\n"
                      "  base_branch: base\n")
    _touch(repo, "lovelace/dashboard.yaml", "views: []\n")
    _commit(repo)

    surface, reason, _fields, proc = _surface(repo)

    assert surface == "yes", (
        "lovelace/*.yaml ist beobachtbare Oberflaeche — "
        f"war {surface!r} (reason={reason!r}), stdout={proc.stdout!r}"
    )
    assert "lovelace/dashboard.yaml" in reason, (
        f"Begruendung muss die ausloesende Datei nennen — war {reason!r}"
    )


def test_ac10_strings_xcstrings_keep_the_question(tmp_path):
    """AC-10: iOS-Lokalisierung ist sichtbarer Text.

    GIVEN: zwei getrennte Wegwerf-Git-Repos — eines mit geaenderter
           `Localizable.strings`, eines mit geaenderter `de.xcstrings`.
    WHEN:  `workflow.py observable-surface` in beiden laeuft.
    THEN:  Beide liefern `yes`.
    """
    for name, rel in (("strings", "Resources/Localizable.strings"),
                      ("xcstrings", "Resources/de.xcstrings")):
        repo = _make_repo(tmp_path / name,
                          "  enabled: true\n"
                          "  base_branch: base\n")
        _touch(repo, rel, '"key" = "Wert";\n')
        _commit(repo)

        surface, reason, _fields, proc = _surface(repo)

        assert surface == "yes", (
            f"{rel} enthaelt sichtbaren Text und ist Oberflaeche — "
            f"war {surface!r} (reason={reason!r}), stdout={proc.stdout!r}"
        )
        assert rel in reason, (
            f"Begruendung muss {rel} nennen — war {reason!r}"
        )


def test_ac11_commands_md_keeps_the_question(tmp_path):
    """AC-11: Befehlstexte gelten als Oberflaeche, nicht als Doku.

    GIVEN: ein Wegwerf-Git-Repo mit geaenderter `core/commands/60-validate.md`.
    WHEN:  `workflow.py observable-surface` dort laeuft.
    THEN:  Ergebnis `yes` — PO-Entscheidung E1: was der PO beim Tippen eines
           Slash-Befehls liest, kann er beurteilen.
    """
    repo = _make_repo(tmp_path / "repo",
                      "  enabled: true\n"
                      "  base_branch: base\n")
    _touch(repo, "core/commands/60-validate.md", "# Validate\n")
    _commit(repo)

    surface, reason, _fields, proc = _surface(repo)

    assert surface == "yes", (
        "core/commands/*.md ist Oberflaeche (E1), keine unsichtbare Doku — "
        f"war {surface!r} (reason={reason!r}), stdout={proc.stdout!r}"
    )
    assert "core/commands/60-validate.md" in reason, (
        f"Begruendung muss die ausloesende Datei nennen — war {reason!r}"
    )


def test_ac12_untracked_file_enters_the_list(tmp_path):
    """AC-12: eine neu angelegte, noch nicht hinzugefuegte Datei zaehlt mit.

    GIVEN: ein Wegwerf-Git-Repo mit genau einer neuen, unversionierten Datei
           `core/commands/neu.md` — `git ls-files --others --exclude-standard`
           liefert sie, kein einziger `git diff` tut das.
    WHEN:  `workflow.py observable-surface` dort laeuft.
    THEN:  Sie ist Teil der geprueften Liste (`FILES=1`) und fuehrt zu `yes`.
           Fehlt Quelle 4, erschiene der Fall faelschlich als `empty-list`.
    """
    repo = _make_repo(tmp_path / "repo",
                      "  enabled: true\n"
                      "  base_branch: base\n")
    _touch(repo, "core/commands/neu.md", "# Neuer Befehl\n")

    surface, reason, fields, proc = _surface(repo)

    assert fields.get("FILES") == "1", (
        "Die unversionierte Datei muss in der geprueften Liste stehen "
        "(git ls-files --others --exclude-standard) — "
        f"FILES war {fields.get('FILES')!r}, reason={reason!r}, "
        f"stdout={proc.stdout!r}"
    )
    assert surface == "yes", (
        f"Sie trifft surface_patterns — war {surface!r} (reason={reason!r})"
    )
    assert "core/commands/neu.md" in reason, (
        f"Begruendung muss die neue Datei nennen — war {reason!r}"
    )


def test_ac13_cli_output_format(tmp_path):
    """AC-13: die CLI-Auskunft hat ein festes Format.

    GIVEN: ein beliebiges Wegwerf-Git-Repo (hier: sauberer Baum).
    WHEN:  `python3 core/hooks/workflow.py observable-surface` dort laeuft.
    THEN:  stdout enthaelt genau die fuenf Zeilen `OBSERVABLE_SURFACE=`,
           `REASON=`, `FILES=`, `ROOT=`, `CONFIG=` in dieser Reihenfolge, der
           Rueckgabecode ist 0. `ROOT=` nennt die Messwurzel, `CONFIG=` die
           Config-Quelle — beide Zeilen verhindern die Wiederholung von #153.
    """
    repo = _make_repo(tmp_path / "repo",
                      "  enabled: true\n"
                      "  base_branch: base\n")
    _touch(repo, "core/hooks/a.py", "A = 1\n")
    _commit(repo)

    proc = _run_cli(repo)

    assert proc.returncode == 0, (
        "Auskunft, kein Gate: Rueckgabecode muss immer 0 sein — "
        f"rc={proc.returncode}, stderr={proc.stderr!r}"
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == 5, (
        f"Genau fuenf Zeilen erwartet, waren {len(lines)}: {proc.stdout!r}"
    )
    keys = [ln.split("=", 1)[0] for ln in lines]
    assert keys == EXPECTED_KEYS, (
        f"Reihenfolge der Schluessel muss {EXPECTED_KEYS} sein — war {keys}"
    )
    values = dict(ln.split("=", 1) for ln in lines)
    assert values["OBSERVABLE_SURFACE"] in ("yes", "no"), (
        f"Nur `yes` oder `no` erlaubt — war {values['OBSERVABLE_SURFACE']!r}"
    )
    assert values["FILES"].isdigit(), (
        f"FILES muss eine Anzahl sein — war {values['FILES']!r}"
    )
    assert Path(values["ROOT"]).resolve() == repo.resolve(), (
        "ROOT muss die Messwurzel (der tatsaechliche Arbeitsbaum) sein — "
        f"war {values['ROOT']!r}, erwartet {str(repo.resolve())!r}"
    )
    assert "config.yaml" in values["CONFIG"], (
        "CONFIG muss die tatsaechlich benutzte Config-Quelle nennen "
        f"(config_source_note) — war {values['CONFIG']!r}"
    )


# --------------------------------------------------------------------------
# AC-14: Textvertrag in core/commands/60-validate.md
# --------------------------------------------------------------------------

def _fenced_blocks(text: str):
    """Alle fenced Codebloecke als (sprache, inhalt, startindex)."""
    out = []
    for m in re.finditer(r"^```([A-Za-z0-9_+-]*)\n(.*?)^```", text,
                         re.DOTALL | re.MULTILINE):
        out.append((m.group(1).lower(), m.group(2), m.start()))
    return out


def test_ac14_validate_asks_without_no_line():
    """AC-14: fehlt `OBSERVABLE_SURFACE=no`, wird gefragt.

    GIVEN: `core/commands/60-validate.md` nach der Umsetzung.
    WHEN:  der Befehlstext gelesen wird.
    THEN:  (a) ein fenced bash-Block ruft `workflow.py observable-surface` VOR
           der Zusammenfassung auf, (b) der Text legt ausdruecklich fest, dass
           ohne die Zeile `OBSERVABLE_SURFACE=no` die Schlussfrage „Soll ich
           den Code committen?" gestellt wird, (c) alle vier Kombinationen aus
           Oberflaeche (yes/no) und dokumentierter Autonomie (ja/nein) stehen
           im Text.
    """
    text = VALIDATE_MD.read_text(encoding="utf-8")

    summary_idx = text.find("### Zusammenfassung an den User")
    assert summary_idx != -1, (
        "Ankerpunkt `### Zusammenfassung an den User` fehlt in "
        f"{VALIDATE_MD} — der Test kann `vor der Zusammenfassung` nicht pruefen"
    )

    # (a) Pflicht-Aufruf als fenced bash-Block vor der Zusammenfassung
    calls = [
        start for lang, body, start in _fenced_blocks(text)
        if lang == "bash" and "workflow.py observable-surface" in body
    ]
    assert calls, (
        "Es muss einen fenced ```bash-Block mit dem Aufruf "
        "`workflow.py observable-surface` geben — keiner gefunden in "
        f"{VALIDATE_MD}"
    )
    assert min(calls) < summary_idx, (
        "Der Aufruf muss VOR der Zusammenfassung stehen — fruehester Block bei "
        f"Zeichen {min(calls)}, Zusammenfassung bei {summary_idx}"
    )

    # (b) Fehlende `OBSERVABLE_SURFACE=no`-Zeile => Schlussfrage bleibt
    assert "OBSERVABLE_SURFACE=no" in text, (
        "Der Text muss die Zeichenkette `OBSERVABLE_SURFACE=no` benennen, "
        "an der die Abstufung haengt"
    )
    assert "Soll ich den Code committen?" in text, (
        "Die Schlussfrage muss weiterhin woertlich im Befehlstext stehen"
    )
    mentions = [p for p in text.split("\n\n") if "OBSERVABLE_SURFACE=no" in p]
    assert any("fehlt" in p.lower() for p in mentions), (
        "Der Text muss ausdruecklich regeln, dass bei FEHLENDER Zeile "
        "`OBSERVABLE_SURFACE=no` (auch bei Absturz oder ausgebliebenem Aufruf) "
        "die Schlussfrage gestellt wird — kein Absatz nennt beides. "
        f"Gefundene Absaetze: {mentions!r}"
    )

    # (c) Alle vier Kombinationen Oberflaeche x Autonomie
    pairs = set()
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip().strip("`*").strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        surface = cells[0].strip("`").lower()
        autonomy = cells[1].strip("`").lower()
        if surface in ("yes", "no") and autonomy in ("ja", "nein"):
            pairs.add((surface, autonomy))

    expected_pairs = {("yes", "nein"), ("yes", "ja"), ("no", "nein"), ("no", "ja")}
    assert pairs == expected_pairs, (
        "Alle vier Kombinationen Oberflaeche x Autonomie muessen im Befehlstext "
        f"stehen — gefunden: {sorted(pairs)}, erwartet: {sorted(expected_pairs)}"
    )
