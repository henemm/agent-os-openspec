"""Repo-eigene Alias-Dateien und Doku-Formulierungen (Issue #147, Haelfte 1).

Zwei Luecken, die vor dieser Spec ungeprueft blieben:

(a) `tests/test_setup_alias_sync_150.py::test_generated_aliases_match_alias_sync_exactly`
    (Z. 51-64) vergleicht `setup.generate_command_aliases()` nur gegen FRISCH
    ERZEUGTE Dateien in `tmp_path` — nie gegen die tatsaechlich in diesem
    Repository liegenden `.claude/commands/*.md`. `scripts/release_check.py`
    (`check_skills_sync`, Z. 190-203) prueft ebenfalls nur `skills/` gegen
    `core/commands/`, nie die Alias-Kopien. In genau dieser Luecke sind die
    Vollkopien fuer `50-implement`/`60-validate` unbemerkt verrottet: Beide
    tragen noch den Versions-Marker `3.30.0`, waehrend die zugehoerigen
    Skills laengst bei `3.32.0` stehen — gemessen am 2026-09-27 vor dieser
    Spec. `alias_sync.find_stale_aliases()` ist bereits fuer genau den Fall
    gebaut, dass ein Skill von gesperrt auf entsperrt wechselt (Docstring
    dort), wird aber nirgends gegen die echten Repo-Dateien aufgerufen.

(b) AC-9: Nach dem Flag-Flip fuer `50-implement`/`60-validate`
    (`disable-model-invocation: false`) beschreiben drei Doku-Dateien den
    PO-Tastendruck falsch — sie nennen `/50-implement` bzw. `/60-validate`
    noch als etwas, das der Product Owner selbst eintippt oder als manuellen
    Testauftrag, obwohl die Entscheidung laut ADR-0147 bereits mit `approved`
    bzw. `go` gefallen ist.

Zusaetzlich AC-1 (Frontmatter-Flag-Flip): thematisch naheliegend hier statt
in einer eigenen Datei, weil AC-1 dieselbe Zwei-Skills-Aufzaehlung wie (a)
betrifft und `find_stale_aliases()` in (a) erst dann sinnvoll leer werden
kann, wenn der Flag-Flip vollzogen ist.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))

import alias_sync  # noqa: E402

SKILLS_DIR = REPO_ROOT / "skills"
COMMANDS_DIR = REPO_ROOT / ".claude" / "commands"

FLIPPED_SKILLS = ["50-implement", "60-validate"]


# --- AC-1: Flag-Flip in den beiden betroffenen Skills --------------------------

@pytest.mark.parametrize("name", FLIPPED_SKILLS)
def test_skill_allows_model_invocation_after_flip(name):
    skill_text = (SKILLS_DIR / name / "SKILL.md").read_text()
    assert "disable-model-invocation: false" in skill_text, (
        f"skills/{name}/SKILL.md sperrt weiterhin den Skill-Tool-Selbstaufruf "
        f"(disable-model-invocation fehlt oder ist noch 'true') — AC-1 verlangt "
        f"'false'."
    )
    assert "disable-model-invocation: true" not in skill_text, (
        f"skills/{name}/SKILL.md enthaelt noch 'disable-model-invocation: true' — "
        f"AC-1 verlangt, dass dieser Wert vollstaendig durch 'false' ersetzt wurde."
    )


# --- AC-7: repo-eigene Alias-Dateien entsprechen ihrem Soll --------------------

def test_no_stale_aliases_in_this_repository():
    """`find_stale_aliases` gegen die ECHTEN Dateien dieses Repos, nicht gegen
    `tmp_path`. Vor dieser Spec liefert der Aufruf gemessen (2026-09-27):
    ['50-implement', '60-validate', '70-deploy', '80-workflow',
    '81-add-artifact', '99-reset'] — alle sechs Vollkopien tragen den
    Versions-Marker 3.30.0, die zugehoerigen Skills 3.32.0.
    """
    stale = alias_sync.find_stale_aliases(SKILLS_DIR, COMMANDS_DIR, loaded_version=None)
    assert stale == [], (
        "Repo-eigene Alias-Dateien unter .claude/commands/ weichen vom Soll "
        f"(alias_sync.alias_content) ab: {stale}. Reparatur laut Spec-Reihenfolge: "
        "1) Flag-Flip + Chaining in core/commands/, 2) python3 scripts/sync_skills.py, "
        "3) Versionsbump, 4) python3 scripts/sync_skills.py erneut, "
        "5) python3 setup.py . --refresh-aliases."
    )


# --- AC-9: verbotene Doku-Formulierungen sind entfernt -------------------------
#
# README.md gehoert laut AC-9 ebenfalls zum Scope, enthaelt aber (Stand
# 2026-09-27, vor dieser Spec) keine der drei verbotenen Formulierungen — die
# Datei ist rein englischsprachig und beschreibt /50-implement und
# /60-validate nirgends als PO-Tastendruck oder manuellen Testauftrag. Ein
# "Formulierung nicht vorhanden"-Test waere dort schon jetzt und dauerhaft
# trivial gruen und bewiese nichts (siehe Bericht an den Orchestrator). Die
# geplante Aenderung an README.md laut Scope-Tabelle der Spec ist eine
# ERGAENZUNG (Hinweis auf automatisches Chaining am Diagramm/der Tabelle),
# fuer die die Spec keinen konkreten Wortlaut vorgibt — dafuer gibt es daher
# hier bewusst keinen Test.

def test_workflow_guide_no_longer_tells_po_to_type_50_implement():
    content = (REPO_ROOT / "docs" / "WORKFLOW_GUIDE.md").read_text()
    assert "User tippt /50-implement" not in content, (
        "docs/WORKFLOW_GUIDE.md beschreibt /50-implement noch als Tastendruck des "
        "PO (Fundstelle nahe Z. 386) — nach dem Flag-Flip ruft Claude den Skill "
        "selbst auf."
    )


def test_workflow_guide_no_longer_calls_validation_manual():
    content = (REPO_ROOT / "docs" / "WORKFLOW_GUIDE.md").read_text()
    assert "Manuelle Validierung" not in content, (
        "docs/WORKFLOW_GUIDE.md nennt /60-validate noch 'Manuelle Validierung' "
        "(Fundstelle nahe Z. 469) — die Phase besteht aus vier automatischen "
        "Pruefagenten, nicht aus einem manuellen Testauftrag an den PO."
    )
    assert "Manuelle Tests, Integration-Tests, UI-Checks" not in content, (
        "docs/WORKFLOW_GUIDE.md beschreibt Phase 7 noch als manuellen Testauftrag "
        "('Manuelle Tests, Integration-Tests, UI-Checks', Fundstelle nahe Z. 155)."
    )


def test_intake_no_longer_calls_validation_manual():
    content = (REPO_ROOT / "core" / "commands" / "00-intake.md").read_text()
    assert "Manuelle Validierung" not in content, (
        "core/commands/00-intake.md nennt die Validierungsphase noch 'Manuelle "
        "Validierung' (Fundstelle Z. 114) — sie ist automatisiert (vier "
        "Pruefagenten + docs-updater), kein manueller PO-Testauftrag."
    )
