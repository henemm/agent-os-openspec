"""Tests für spec: Resolve Execution Context Consolidation.

Deckt Test-Plan-Punkte 1-4 und 9 aus
docs/specs/resolve-execution-context-consolidation.md ab.

Kernaussage: `workflow.py` löst den aktiven Workflow-Namen NICHT mehr über eigene
duplizierte Logik auf, sondern delegiert an `hook_utils.resolve_active_workflow()`.
Dadurch verschwindet der Live-Bug (Issue #13): worktree-lokale
`.claude/active_workflow`-Datei zeigt auf Workflow A, aber die (veraltete)
`OPENSPEC_ACTIVE_WORKFLOW`-Env-Var zeigt auf Workflow B → früher FATAL, jetzt
wird Workflow A verwendet.

Diese Tests laufen in-process und mocken die Auflösungs-Kontext-Funktionen
(`find_project_root`, `_find_worktree_root`, `_worktree_root_if_any`), damit sie
hermetisch vom echten Worktree-Zustand der Testsession sind.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import hook_utils  # noqa: E402
import workflow as wf_module  # noqa: E402


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _write_workflow(root: Path, name: str) -> None:
    """Lege eine gültige workflows/<name>.json unter root/.claude/ ab."""
    wf_dir = root / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / f"{name}.json").write_text(
        json.dumps(
            {
                "name": name,
                "workflow_type": "feature",
                "current_phase": "phase1_context",
            }
        )
    )


def _bind_context(monkeypatch, tmp_path: Path, worktree: "Path | None") -> None:
    """Verankere alle Auflösungs-Kontext-Funktionen deterministisch auf tmp_path.

    Patcht sowohl die von workflow.py als auch die von hook_utils genutzten
    Kontext-Funktionen, damit die Tests unabhängig davon grün/rot sind, ob
    workflow.py die alte (duplizierte) oder die neue (delegierende) Logik hat.
    """
    monkeypatch.setattr(wf_module, "find_project_root", lambda: tmp_path)
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: tmp_path)
    monkeypatch.setattr(hook_utils, "_find_worktree_root", lambda: worktree)
    monkeypatch.setattr(wf_module, "_worktree_root_if_any", lambda: worktree)


# --------------------------------------------------------------------------
# Test 1: Live-Bug-Regression (Issue #13)
# --------------------------------------------------------------------------

def test_1_file_beats_stale_env_no_fatal(monkeypatch, tmp_path):
    """Worktree-Datei zeigt auf A, Env (veraltet) auf B → A wird verwendet, kein FATAL.

    Reproduziert den Live-Bug: der alte `_read_active()`-FATAL-Pfad liest die
    Env-Var zuerst, findet keine passende workflows/B.json und ruft sys.exit(1).
    Nach der Konsolidierung gewinnt die worktree-lokale active_workflow-Datei
    (Workflow A).
    """
    _write_workflow(tmp_path, "workflow-a")  # existiert
    # Workflow B (aus Env) existiert bewusst NICHT
    (tmp_path / ".claude" / "active_workflow").write_text("workflow-a")
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "workflow-b")
    _bind_context(monkeypatch, tmp_path, worktree=tmp_path)

    data, name = wf_module._read_active()

    assert name == "workflow-a"
    assert data.get("name") == "workflow-a"


def test_1b_fast_file_beats_stale_env(monkeypatch, tmp_path):
    """read_active_workflow_fast() löst im selben Live-Bug-Szenario Workflow A auf."""
    _write_workflow(tmp_path, "workflow-a")
    (tmp_path / ".claude" / "active_workflow").write_text("workflow-a")
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "workflow-b")
    _bind_context(monkeypatch, tmp_path, worktree=tmp_path)

    result = wf_module.read_active_workflow_fast()

    assert result is not None
    name, data = result
    assert name == "workflow-a"


# --------------------------------------------------------------------------
# Test 2: Env als dritte Priorität (kein Worktree)
# --------------------------------------------------------------------------

def test_2_env_resolves_when_no_worktree_no_file(monkeypatch, tmp_path):
    """Kein Worktree, keine Datei/Settings, gültige Env-Var → Auflösung aus Env."""
    _write_workflow(tmp_path, "workflow-env")
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "workflow-env")
    _bind_context(monkeypatch, tmp_path, worktree=None)

    data, name = wf_module._read_active()

    assert name == "workflow-env"
    assert data.get("name") == "workflow-env"


def test_2b_fast_env_resolves_when_no_worktree(monkeypatch, tmp_path):
    """read_active_workflow_fast() löst ebenfalls aus der Env-Var auf (kein Worktree)."""
    _write_workflow(tmp_path, "workflow-env")
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "workflow-env")
    _bind_context(monkeypatch, tmp_path, worktree=None)

    result = wf_module.read_active_workflow_fast()

    assert result is not None
    name, _data = result
    assert name == "workflow-env"


# --------------------------------------------------------------------------
# Test 3: Kein Workflow auflösbar → FATAL + sys.exit(1)
# --------------------------------------------------------------------------

def test_3_no_workflow_resolvable_exits(monkeypatch, tmp_path):
    """Weder Datei noch Env noch Settings → 'No active workflow' + sys.exit(1)."""
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
    _bind_context(monkeypatch, tmp_path, worktree=None)

    with pytest.raises(SystemExit) as exc:
        wf_module._read_active()

    assert exc.value.code == 1


# --------------------------------------------------------------------------
# Test 4: read_active_workflow_fast() non-fatal → None
# --------------------------------------------------------------------------

def test_4_fast_returns_none_when_unresolvable(monkeypatch, tmp_path):
    """Kein Workflow auflösbar → None, ohne sys.exit()."""
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
    _bind_context(monkeypatch, tmp_path, worktree=None)

    # Darf keinen SystemExit auslösen
    result = wf_module.read_active_workflow_fast()

    assert result is None


# --------------------------------------------------------------------------
# Test 9: Regressionsfreiheit — Konsumenten-Signatur bleibt stabil (AC-6)
# --------------------------------------------------------------------------

def test_9_fast_signature_is_tuple_or_none(monkeypatch, tmp_path):
    """read_active_workflow_fast() liefert (name: str, data: dict) oder None — nie sys.exit.

    Absichert die von tdd_enforcement.py und post_implementation_gate.py erwartete
    Rückgabe-Signatur (AC-6): kein Verhaltensbruch bei den Konsumenten.
    """
    _write_workflow(tmp_path, "workflow-sig")
    (tmp_path / ".claude" / "active_workflow").write_text("workflow-sig")
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "workflow-sig")
    _bind_context(monkeypatch, tmp_path, worktree=tmp_path)

    result = wf_module.read_active_workflow_fast()

    assert result is not None
    assert isinstance(result, tuple) and len(result) == 2
    name, data = result
    assert isinstance(name, str)
    assert isinstance(data, dict)


# --------------------------------------------------------------------------
# Fix #58: Worktree ignoriert die eingefrorene OPENSPEC_ACTIVE_WORKFLOW-Env-Var
#
# Kernaussage: In einer Worktree-Session ist die bei Session-Start eingefrorene
# Env-Var KEINE gültige Auflösungsquelle mehr. Da alle Workflow-JSONs im geteilten
# Hauptrepo liegen, würde ein fremder Workflow-Name aus einer parallelen Session
# sonst die schwache "Datei existiert irgendwo"-Prüfung bestehen und die eigene
# Session kapern (Issue #58). Worktree-lokale Quellen (Datei > settings) bleiben
# maßgeblich; der Main-Repo-Zweig bleibt unverändert (Env dort weiterhin Prio 3).
# --------------------------------------------------------------------------

def test_5_worktree_ignores_foreign_env(monkeypatch, tmp_path):
    """AC-1/EB-1: Worktree, Env→fremder existierender Workflow, keine Datei/Settings → none."""
    _write_workflow(tmp_path, "foreign-wf")  # existiert im geteilten Hauptrepo
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "foreign-wf")
    _bind_context(monkeypatch, tmp_path, worktree=tmp_path)

    name, source = hook_utils.resolve_active_workflow()

    assert (name, source) == ("", "none")


def test_5b_worktree_foreign_env_fast_none(monkeypatch, tmp_path):
    """AC-1/EB-5: read_active_workflow_fast() liefert None statt der fremden Env-Identität."""
    _write_workflow(tmp_path, "foreign-wf")
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "foreign-wf")
    _bind_context(monkeypatch, tmp_path, worktree=tmp_path)

    assert wf_module.read_active_workflow_fast() is None


def test_5c_worktree_foreign_env_read_active_exits(monkeypatch, tmp_path):
    """EB-5: _read_active() beendet mit sys.exit(1), da im Worktree nichts Eigenes auflösbar."""
    _write_workflow(tmp_path, "foreign-wf")
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "foreign-wf")
    _bind_context(monkeypatch, tmp_path, worktree=tmp_path)

    with pytest.raises(SystemExit) as exc:
        wf_module._read_active()

    assert exc.value.code == 1


def test_6_worktree_file_beats_env(monkeypatch, tmp_path):
    """AC-2/EB-2: Worktree-Datei (A) gewinnt gegen existierende Env (B)."""
    _write_workflow(tmp_path, "workflow-a")
    _write_workflow(tmp_path, "workflow-b")
    (tmp_path / ".claude" / "active_workflow").write_text("workflow-a")
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "workflow-b")
    _bind_context(monkeypatch, tmp_path, worktree=tmp_path)

    name, source = hook_utils.resolve_active_workflow()

    assert (name, source) == ("workflow-a", "file")


def test_7_worktree_settings_beats_env(monkeypatch, tmp_path):
    """AC-3/EB-3: Worktree-settings.local.json (C) gewinnt gegen existierende Env (B)."""
    _write_workflow(tmp_path, "workflow-c")
    _write_workflow(tmp_path, "workflow-b")
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "settings.local.json").write_text(
        json.dumps({"env": {"OPENSPEC_ACTIVE_WORKFLOW": "workflow-c"}})
    )
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "workflow-b")
    _bind_context(monkeypatch, tmp_path, worktree=tmp_path)

    name, source = hook_utils.resolve_active_workflow()

    assert (name, source) == ("workflow-c", "settings")


def test_8_mainrepo_env_still_resolves(monkeypatch, tmp_path):
    """AC-4/EB-4: Main-Repo (kein Worktree) — Env bleibt gültige Prio-3-Quelle (Regression)."""
    _write_workflow(tmp_path, "workflow-env")
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "workflow-env")
    _bind_context(monkeypatch, tmp_path, worktree=None)

    name, source = hook_utils.resolve_active_workflow()

    assert (name, source) == ("workflow-env", "env")


# --------------------------------------------------------------------------
# Fix #144: workflow.py löst Spec-/Briefing-Pfade in Worktree-Sessions falsch
# auf (docs/specs/fix-144-briefing-worktree-path.md)
#
# Kernaussage: `_check_adr`, `_read_spec_content`, `_check_po_briefing` und
# `cmd_set_briefing` lösen die Pfade versionierter Repo-Dateien (Spec,
# Briefing) bisher IMMER über `find_project_root()` auf — richtig für
# geteilten Workflow-State, aber falsch für Dateien, die nur im Arbeitsbaum
# der Worktree-Session committet sind. Anders als beim bestehenden
# `_bind_context`-Helper oben (der beide Rollen auf denselben tmp_path legt)
# braucht dieser Fix zwei UNTERSCHIEDLICHE Verzeichnisse, um "Datei existiert
# nur im Worktree, nicht im Hauptrepo" hermetisch zu simulieren.
# --------------------------------------------------------------------------

_SPEC_ADR_FILLED_KEINE = (
    "# Spec Test\n\n"
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** keine\n"
    "- **Rationale:** Kein neues Architekturmuster, siehe Spec-Text.\n"
)

_SPEC_ADR_UNFILLED = (
    "# Spec Test\n\n"
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:**\n"
    "- **Rationale:**\n"
)

_BRIEFING_COMPLETE = (
    "# PO-Briefing Test\n\n"
    "## Was gebaut wird\n\n"
    "Eine kleine Testaenderung die ausreichend Text fuer den Gate-Check enthaelt.\n\n"
    "## Definition of Done\n\n"
    "Alle Acceptance Criteria sind durch automatisierte Tests belegt und gruen.\n\n"
    "## Wie geprüft wird\n\n"
    "Automatisierte Tests decken das Verhalten vollstaendig ab und laufen lokal.\n\n"
    "## Kritische Anmerkungen\n\n"
    "Es sind keine bekannten Risiken oder offenen Fragen zu dieser Aenderung vorhanden.\n"
)


def _write_file(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _bind_split_context(monkeypatch, worktree: "Path | None", main_root: Path) -> None:
    """Wie `_bind_context`, aber Worktree- und Hauptrepo-Root sind zwei
    UNTERSCHIEDLICHE Verzeichnisse (statt beide auf demselben `tmp_path`) —
    einzige Möglichkeit, "Datei existiert nur im Worktree, nicht im
    Hauptrepo" hermetisch zu simulieren (Spec fix-144, Test Plan)."""
    monkeypatch.setattr(wf_module, "find_project_root", lambda: main_root)
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: main_root)
    monkeypatch.setattr(hook_utils, "_find_worktree_root", lambda: worktree)
    monkeypatch.setattr(wf_module, "_worktree_root_if_any", lambda: worktree)


def _setup_worktree_briefing_scenario(monkeypatch, tmp_path: Path, wf_name: str) -> dict:
    """Gemeinsames Setup für AC-1/AC-5/AC-6: Spec+Briefing existieren NUR im
    simulierten Worktree; der geteilte Workflow-State liegt im simulierten
    Hauptrepo (unverändert über find_project_root()). Gibt die für die
    jeweiligen Assertions nötigen Pfade zurück."""
    worktree_root = tmp_path / "worktree"
    main_root = tmp_path / "main"
    worktree_root.mkdir()
    main_root.mkdir()
    _bind_split_context(monkeypatch, worktree_root, main_root)

    _write_workflow(main_root, wf_name)
    (worktree_root / ".claude").mkdir(parents=True, exist_ok=True)
    (worktree_root / ".claude" / "active_workflow").write_text(wf_name)

    wf_file = main_root / ".claude" / "workflows" / f"{wf_name}.json"
    data = json.loads(wf_file.read_text())
    data["spec_file"] = "docs/specs/x.md"
    wf_file.write_text(json.dumps(data))

    _write_file(worktree_root, "docs/specs/x.md", _SPEC_ADR_FILLED_KEINE)
    _write_file(worktree_root, "docs/briefings/x.md", _BRIEFING_COMPLETE)

    # Hermetischer Beweis: NICHT im simulierten Hauptrepo vorhanden.
    assert not (main_root / "docs" / "specs" / "x.md").exists()
    assert not (main_root / "docs" / "briefings" / "x.md").exists()

    return {
        "worktree_root": worktree_root,
        "main_root": main_root,
        "wf_file": wf_file,
        "briefing_rel": "docs/briefings/x.md",
        "spec_rel": "docs/specs/x.md",
    }


def test_ac1_set_briefing_succeeds_with_worktree_only_files(monkeypatch, tmp_path):
    """AC-1: set-briefing gelingt, wenn Spec+Briefing nur im Worktree existieren.

    Vor dem Fix: `cmd_set_briefing` löst den Root ausschließlich über
    `find_project_root()` (= simuliertes Hauptrepo) auf, findet die Briefing-
    Datei dort nicht und bricht mit `sys.exit(1)` ab ("nicht lesbar").
    """
    ctx = _setup_worktree_briefing_scenario(monkeypatch, tmp_path, "wf-ac1")

    wf_module.cmd_set_briefing([ctx["briefing_rel"]])

    saved = json.loads(ctx["wf_file"].read_text())
    entry = saved.get("po_briefing")
    assert isinstance(entry, dict), saved
    assert entry.get("file") == ctx["briefing_rel"], entry
    assert entry.get("spec_sha256"), entry


def test_ac2_check_po_briefing_reads_worktree_only_file(monkeypatch, tmp_path):
    """AC-2: `_check_po_briefing()` liest die Briefing-Datei erfolgreich, wenn
    sie nur im Worktree existiert (Spec liegt zur Isolation identisch in
    beiden Roots — der Test soll ausschließlich das Lesen von
    `po_briefing.file` prüfen, nicht das der Spec)."""
    worktree_root = tmp_path / "worktree"
    main_root = tmp_path / "main"
    worktree_root.mkdir()
    main_root.mkdir()
    _bind_split_context(monkeypatch, worktree_root, main_root)

    _write_file(main_root, "docs/specs/x.md", _SPEC_ADR_FILLED_KEINE)
    _write_file(worktree_root, "docs/specs/x.md", _SPEC_ADR_FILLED_KEINE)
    _write_file(worktree_root, "docs/briefings/x.md", _BRIEFING_COMPLETE)
    assert not (main_root / "docs" / "briefings" / "x.md").exists()

    data = {
        "spec_file": "docs/specs/x.md",
        "workflow_type": "feature",
        "po_briefing": {"file": "docs/briefings/x.md"},
    }

    result = wf_module._check_po_briefing(data)

    assert result is None, f"Erwartet: kein Block, aber: {result!r}"


def test_ac3_check_adr_reads_and_blocks_worktree_only_spec(monkeypatch, tmp_path):
    """AC-3: `_check_adr()` liest die Spec erfolgreich, wenn sie nur im
    Worktree existiert, UND blockiert korrekt bei fehlender/nicht
    ausgefüllter ADR-Sektion — Beweis der Reaktivierung, nicht nur eines
    gelungenen Lesezugriffs."""
    worktree_root = tmp_path / "worktree"
    main_root = tmp_path / "main"
    worktree_root.mkdir()
    main_root.mkdir()
    _bind_split_context(monkeypatch, worktree_root, main_root)

    _write_file(worktree_root, "docs/specs/x.md", _SPEC_ADR_UNFILLED)
    assert not (main_root / "docs" / "specs" / "x.md").exists()

    result = wf_module._check_adr({"spec_file": "docs/specs/x.md"})

    assert result is not None, (
        "Erwartet: Block wegen unausgefülltem ADR-Feld — None bedeutet, die "
        "Spec wurde gar nicht gelesen (lenientes Grandfathering greift "
        "fälschlich)."
    )
    assert "ADR-Feld" in result, result


def test_ac4_no_worktree_regression_uses_project_root_only(monkeypatch, tmp_path):
    """AC-4: Ohne Worktree bleibt die Auflösung für alle vier betroffenen
    Stellen unverändert ausschließlich über `find_project_root()`
    (Regressionsfreiheit für Nicht-Worktree-Sessions)."""
    main_root = tmp_path
    _bind_split_context(monkeypatch, worktree=None, main_root=main_root)

    _write_workflow(main_root, "wf-ac4")
    (main_root / ".claude" / "active_workflow").write_text("wf-ac4")

    wf_file = main_root / ".claude" / "workflows" / "wf-ac4.json"
    data = json.loads(wf_file.read_text())
    data["spec_file"] = "docs/specs/x.md"
    wf_file.write_text(json.dumps(data))

    _write_file(main_root, "docs/specs/x.md", _SPEC_ADR_FILLED_KEINE)
    _write_file(main_root, "docs/briefings/x.md", _BRIEFING_COMPLETE)

    assert wf_module._read_spec_content({"spec_file": "docs/specs/x.md"}) == _SPEC_ADR_FILLED_KEINE
    assert wf_module._check_adr({"spec_file": "docs/specs/x.md"}) is None

    po_data = {
        "spec_file": "docs/specs/x.md",
        "workflow_type": "feature",
        "po_briefing": {"file": "docs/briefings/x.md"},
    }
    assert wf_module._check_po_briefing(po_data) is None

    wf_module.cmd_set_briefing(["docs/briefings/x.md"])
    saved = json.loads(wf_file.read_text())
    assert saved["po_briefing"]["file"] == "docs/briefings/x.md"


def test_ac4b_worktree_but_file_only_in_main_repo_falls_back(monkeypatch, tmp_path):
    """Implementation Details (Spec fix-144): `_worktree_first_root` fällt auf
    `find_project_root()` zurück, wenn `rel` im Worktree NICHT existiert — die
    `(wt / rel).exists()`-Bedingung (Vorbild `edit_gate.py:254`). Kein eigenes
    AC, sondern eine Pin-Ergänzung zu AC-4: ohne diesen Test würde auch eine
    Implementierung OHNE Existenzprüfung (die den Worktree-Root immer
    bevorzugt, sobald überhaupt ein Worktree vorliegt) die restliche Suite
    grün machen, obwohl sie die falsche Datei läse, sobald sie existierte."""
    worktree_root = tmp_path / "worktree"
    main_root = tmp_path / "main"
    worktree_root.mkdir()
    main_root.mkdir()
    _bind_split_context(monkeypatch, worktree_root, main_root)

    _write_file(main_root, "docs/specs/x.md", _SPEC_ADR_UNFILLED)
    _write_file(main_root, "docs/briefings/x.md", _BRIEFING_COMPLETE)
    assert not (worktree_root / "docs" / "specs" / "x.md").exists()

    assert wf_module._read_spec_content({"spec_file": "docs/specs/x.md"}) == _SPEC_ADR_UNFILLED

    # Positives Signal (Block wegen unausgefülltem ADR-Feld), nicht das
    # mehrdeutige None, das auch ein gescheiterter Lesezugriff liefern würde.
    adr = wf_module._check_adr({"spec_file": "docs/specs/x.md"})
    assert adr is not None and "ADR-Feld" in adr, adr

    assert wf_module._check_po_briefing({
        "spec_file": "docs/specs/x.md",
        "workflow_type": "feature",
        "po_briefing": {"file": "docs/briefings/x.md"},
    }) is None


def test_ac5_set_briefing_stores_worktree_relative_path(monkeypatch, tmp_path):
    """AC-5: Der gespeicherte `po_briefing.file`-Pfad ist worktree-relativ,
    NICHT mit Worktree-Präfix (z.B. NICHT `.claude/worktrees/<name>/...`)."""
    ctx = _setup_worktree_briefing_scenario(monkeypatch, tmp_path, "wf-ac5")

    wf_module.cmd_set_briefing([ctx["briefing_rel"]])

    saved = json.loads(ctx["wf_file"].read_text())
    stored_path = saved["po_briefing"]["file"]
    assert stored_path == "docs/briefings/x.md", stored_path
    assert not stored_path.startswith(str(ctx["worktree_root"])), stored_path
    assert ".claude/worktrees" not in stored_path, stored_path


def test_ac6_parse_briefing_frontmatter_matches_worktree_relative_spec(monkeypatch, tmp_path):
    """AC-6: Die im Worktree gestempelte Briefing-Datei ergibt beim Parsen mit
    `parse_briefing_frontmatter()` (derselben Funktion, die
    `scripts/ci_spec_gate.py::_find_briefing` serverseitig nutzt) exakt den
    erwarteten worktree-relativen `spec_file`-Pfad."""
    ctx = _setup_worktree_briefing_scenario(monkeypatch, tmp_path, "wf-ac6")

    wf_module.cmd_set_briefing([ctx["briefing_rel"]])

    stamped = (ctx["worktree_root"] / ctx["briefing_rel"]).read_text()
    front = wf_module.parse_briefing_frontmatter(stamped)

    assert front.get("spec_file") == ctx["spec_rel"], front
