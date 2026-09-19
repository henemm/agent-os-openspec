"""Tests für das CI-seitige Spec-Gate (`scripts/ci_spec_gate.py`).

Die lokalen Hooks sind Leitplanken, keine Mauern: Wer sie abschaltet, umschreibt
oder per Bash umgeht, kommt an ihnen vorbei — und `.claude/workflows/` ist
gitignored, der Workflow-State erreicht die CI also nie. Dieses Gate prüft
deshalb ausschliesslich **committete** Dateien und fängt genau das ab, was ein
deaktivierter lokaler Hook durchlässt:

  1. Code geändert, aber keine Spec im PR
  2. Spec unvollständig (Pflicht-Sektionen, AC-N, ADR, Platzhalter)
  3. PO-Briefing fehlt, ist unvollständig oder **veraltet** (Spec danach geändert)

Die Aktualitätsprüfung funktioniert in der CI nur, weil `set-briefing` den
Spec-Hash zusätzlich ins Briefing-Frontmatter schreibt — die Bindung reist mit
der Datei, nicht nur im ignorierten State.

Escape: Commit-Trailer `Spec-Gate: skip <Grund>` (sichtbar in der Historie,
im Gegensatz zu einem stillen Config-Flip). Kill-Switch:
config.yaml → ci_spec_gate.enabled: false.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "ci_spec_gate.py"

SPEC_REL = "docs/specs/m/feature.md"
BRIEFING_REL = "docs/briefings/feature.md"
CODE_REL = "core/hooks/some_hook.py"


SPEC_COMPLETE = """---
entity_id: feature
type: feature
status: draft
---

# Feature

## Purpose

Etwas Nützliches für Nutzer.

## Scope

- **Affected Files:** `core/hooks/some_hook.py`
- **Estimated Changes:** ~40 LoC

## Definition of Done

- [ ] Jede Acceptance Criterion ist durch einen automatischen Test belegt
- [ ] Der Nutzer sieht nach dem Klick sein Ergebnis

## Acceptance Criteria

- **AC-1:** Given ein angemeldeter Nutzer / When er auf Senden klickt / Then erscheint eine Bestätigung.

## Test Plan

- `pytest tests/test_feature.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Reine Ergänzung ohne Architektur-Relevanz.

## Changelog

- 2026-09-19: Initial
"""


def _briefing(spec_sha: str, spec_rel: str = SPEC_REL, body_ok: bool = True) -> str:
    tail = (
        "## Kritische Anmerkungen\n\n"
        "- Die Spec sagt nicht, was bei doppeltem Klick passiert.\n"
        if body_ok else ""
    )
    return (
        "---\n"
        f"spec_file: {spec_rel}\n"
        f"spec_sha256: {spec_sha}\n"
        "---\n\n"
        "# PO-Briefing: feature\n\n"
        "## Was gebaut wird\n\n"
        "Nutzer bekommen nach dem Senden eine sichtbare Bestätigung.\n\n"
        "## Definition of Done\n\n"
        "Fertig, wenn ein angemeldeter Nutzer nach dem Klick die Bestätigung sieht.\n\n"
        "## Wie geprüft wird\n\n"
        "Ein automatischer Test klickt stellvertretend und prüft die Bestätigung.\n\n"
        + tail
    )


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def _run(root: Path, changed: list[str], commit_message: str | None = None):
    args = [sys.executable, str(SCRIPT), "--root", str(root), "--changed-files", *changed]
    if commit_message is not None:
        args += ["--commit-message", commit_message]
    return subprocess.run(args, capture_output=True, text=True, env=dict(os.environ))


def _project(tmp_path: Path, *, spec: str | None = SPEC_COMPLETE,
             briefing: str | None = None) -> Path:
    _write(tmp_path, CODE_REL, "def f():\n    return 1\n")
    if spec is not None:
        _write(tmp_path, SPEC_REL, spec)
    if briefing is not None:
        _write(tmp_path, BRIEFING_REL, briefing)
    return tmp_path


# --- Pass-Fälle -------------------------------------------------------------

def test_1_docs_only_change_passes(tmp_path):
    """Test 1 — Nur Doku/Tests geändert → keine Spec nötig, Exit 0."""
    _write(tmp_path, "README.md", "# Readme\n")
    _write(tmp_path, "tests/test_x.py", "def test_x():\n    assert True\n")
    r = _run(tmp_path, ["README.md", "tests/test_x.py"])
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"


def test_2_complete_spec_and_current_briefing_passes(tmp_path):
    """Test 2 — Code + vollständige Spec + aktuelles Briefing → Exit 0."""
    root = _project(tmp_path, briefing=_briefing(_sha(SPEC_COMPLETE)))
    r = _run(root, [CODE_REL, SPEC_REL, BRIEFING_REL])
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"


# --- Block-Fälle ------------------------------------------------------------

def test_3_code_without_spec_blocks(tmp_path):
    """Test 3 — Code geändert, keine Spec im PR → Block."""
    _write(tmp_path, CODE_REL, "def f():\n    return 1\n")
    r = _run(tmp_path, [CODE_REL])
    assert r.returncode != 0, f"stdout={r.stdout!r}"
    assert "Spec" in r.stdout + r.stderr


def test_4_spec_without_definition_of_done_blocks(tmp_path):
    """Test 4 — Spec ohne '## Definition of Done' → Block."""
    spec = SPEC_COMPLETE.replace("## Definition of Done", "## Irgendwas Anderes", 1)
    root = _project(tmp_path, spec=spec, briefing=_briefing(_sha(spec)))
    r = _run(root, [CODE_REL, SPEC_REL, BRIEFING_REL])
    assert r.returncode != 0, f"stdout={r.stdout!r}"
    assert "Definition of Done" in r.stdout + r.stderr


def test_5_spec_without_ac_entries_blocks(tmp_path):
    """Test 5 — '## Acceptance Criteria' ohne AC-N-Einträge → Block."""
    spec = SPEC_COMPLETE.replace(
        "- **AC-1:** Given ein angemeldeter Nutzer / When er auf Senden klickt / Then erscheint eine Bestätigung.",
        "- Es soll halt funktionieren.",
        1,
    )
    root = _project(tmp_path, spec=spec, briefing=_briefing(_sha(spec)))
    r = _run(root, [CODE_REL, SPEC_REL, BRIEFING_REL])
    assert r.returncode != 0, f"stdout={r.stdout!r}"
    assert "AC" in r.stdout + r.stderr


def test_6_spec_with_unfilled_adr_blocks(tmp_path):
    """Test 6 — ADR-Sektion nur mit Platzhalter → Block (gleiche Regel wie lokal)."""
    spec = SPEC_COMPLETE.replace(
        "- **ADR-Nr.:** keine", '- **ADR-Nr.:** [ADR-NNNN oder "keine"]', 1
    )
    root = _project(tmp_path, spec=spec, briefing=_briefing(_sha(spec)))
    r = _run(root, [CODE_REL, SPEC_REL, BRIEFING_REL])
    assert r.returncode != 0, f"stdout={r.stdout!r}"
    assert "ADR" in r.stdout + r.stderr


def test_7_missing_briefing_blocks(tmp_path):
    """Test 7 — Spec vorhanden, kein PO-Briefing → Block."""
    root = _project(tmp_path)
    r = _run(root, [CODE_REL, SPEC_REL])
    assert r.returncode != 0, f"stdout={r.stdout!r}"
    assert "Briefing" in r.stdout + r.stderr


def test_8_stale_briefing_blocks(tmp_path):
    """Test 8 — Kern des Gates: Briefing-Hash != Hash der Spec im PR.

    Das ist der Fall, den ein abgeschalteter lokaler Hook durchlässt: Spec nach
    der Freigabe still umgeschrieben."""
    root = _project(tmp_path, briefing=_briefing(_sha("eine voellig andere spec")))
    r = _run(root, [CODE_REL, SPEC_REL, BRIEFING_REL])
    assert r.returncode != 0, f"stdout={r.stdout!r}"
    assert "veraltet" in (r.stdout + r.stderr).lower()


def test_9_incomplete_briefing_blocks(tmp_path):
    """Test 9 — Briefing ohne '## Kritische Anmerkungen' → Block."""
    spec_sha = _sha(SPEC_COMPLETE)
    root = _project(tmp_path, briefing=_briefing(spec_sha, body_ok=False))
    r = _run(root, [CODE_REL, SPEC_REL, BRIEFING_REL])
    assert r.returncode != 0, f"stdout={r.stdout!r}"
    assert "Kritische Anmerkungen" in r.stdout + r.stderr


def test_10_briefing_without_hash_blocks(tmp_path):
    """Test 10 — Briefing ohne `spec_sha256` im Frontmatter → Block.

    Sonst genügt eine von Hand geschriebene Datei, um das Gate zu passieren."""
    b = _briefing(_sha(SPEC_COMPLETE))
    b = "\n".join(l for l in b.splitlines() if not l.startswith("spec_sha256:")) + "\n"
    root = _project(tmp_path, briefing=b)
    r = _run(root, [CODE_REL, SPEC_REL, BRIEFING_REL])
    assert r.returncode != 0, f"stdout={r.stdout!r}"


# --- Escapes ----------------------------------------------------------------

def test_11_commit_trailer_skips_gate(tmp_path):
    """Test 11 — Commit-Trailer 'Spec-Gate: skip <Grund>' → Exit 0, Grund im Report."""
    _write(tmp_path, CODE_REL, "def f():\n    return 1\n")
    r = _run(
        tmp_path, [CODE_REL],
        commit_message="fix: Tippfehler\n\nSpec-Gate: skip Hotfix ohne Spec, Issue #999\n",
    )
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "skip" in r.stdout.lower()


def test_12_kill_switch_disables_gate(tmp_path):
    """Test 12 — config.yaml → ci_spec_gate.enabled: false → Exit 0."""
    _write(tmp_path, CODE_REL, "def f():\n    return 1\n")
    _write(tmp_path, "config.yaml", "ci_spec_gate:\n  enabled: false\n")
    r = _run(tmp_path, [CODE_REL])
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"


def test_13_fast_track_spec_needs_no_briefing(tmp_path):
    """Test 13 — Fast-Track-Spec (docs/specs/fast/) → kein Briefing verlangt.

    Deckungsgleich mit dem lokalen Gate (po_briefing_gate.skip_fast_track)."""
    fast_rel = "docs/specs/fast/quickfix.md"
    _write(tmp_path, CODE_REL, "def f():\n    return 1\n")
    _write(tmp_path, fast_rel, "# Quickfix\n\n## Purpose\n\nKleine Korrektur.\n")
    r = _run(tmp_path, [CODE_REL, fast_rel])
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
