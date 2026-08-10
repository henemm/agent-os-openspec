"""Regressionstest fuer Issue #90 (Freigabe-Stichwort wird still verworfen,
wenn die Phase nicht passt; Blockade-Meldung nennt ein fest verdrahtetes,
projektfremdes Wort).

Beobachtet in `gregor_zwanzig` mit Plugin 3.10.2: Der PO antwortete `Go` — im
Projekt an erster Stelle als `approval_phrase` konfiguriert. `phase_listener`
erkannte den Treffer korrekt, verwarf ihn aber, weil der Workflow noch in
`phase1_context` stand. Es gab keinen `else`-Zweig: kein Zustandswechsel, keine
Ausgabe. Der spaetere Phasenwechsel meldete dann `Spec not approved — user must
say 'approved'` — eine falsche Ursache (es GAB eine Freigabe) und ein Stichwort,
das in diesem Projekt gar nicht konfiguriert ist.

Die Kette endet verlaesslich im Anti-Pattern `set-field spec_approved true`:
Ein Gate, dessen einziger sauberer Weg unsichtbar scheitert, erzieht zum Umgehen.

Abgedeckt sind alle drei belegten Teilfehler plus der Nebenbefund:
- die stille Verwerfung (Freigabe UND GREEN — dieselbe Luecke zweimal)
- die hartkodierte Blockade-Meldung
- `green_phrases` war als einziges Phrasen-Set nicht konfigurierbar
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def _make_project(tmp_path: Path, phase: str, *, spec_approved: bool = False,
                  config_yaml: "str | None" = None) -> tuple[Path, str]:
    """Main-Repo (.git als DIR → kein Worktree) mit aktivem Workflow."""
    (tmp_path / ".git").mkdir()
    wf_name = "wf-90"
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / f"{wf_name}.json").write_text(json.dumps({
        "name": wf_name,
        "workflow_type": "feature",
        "current_phase": phase,
        "spec_approved": spec_approved,
    }))
    if config_yaml is not None:
        (tmp_path / "openspec.yaml").write_text(config_yaml)
    return tmp_path, wf_name


def _run_listener(project: Path, wf_name: str, prompt: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"prompt": prompt})
    full_env = dict(os.environ)
    full_env.update({
        "CLAUDE_PROJECT_DIR": str(project),
        "OPENSPEC_ACTIVE_WORKFLOW": wf_name,
    })
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "phase_listener.py")],
        input=payload, capture_output=True, text=True, env=full_env, cwd=str(project),
    )


def _wf_state(project: Path, wf_name: str) -> dict:
    return json.loads((project / ".claude" / "workflows" / f"{wf_name}.json").read_text())


# Projekt-Konfiguration wie im Fundprojekt: "go" ist hier eine FREIGABE-Phrase,
# nicht (nur) das GREEN-Wort der Framework-Defaults.
GREGOR_CONFIG = """
workflow:
  approval_phrases:
    - "go"
    - "approved"
    - "validated"
"""


class TestApprovalInWrongPhaseIsNotSilent:
    def test_approval_in_wrong_phase_warns_and_names_both_phases(self, tmp_path):
        """Kern-Regression: `Go` in phase1_context. Der Zustand darf sich nicht
        aendern (das war schon richtig) — aber es muss sichtbar werden, sonst
        laeuft der Bedienende in die falsche Blockade-Meldung."""
        project, wf = _make_project(tmp_path, "phase1_context", config_yaml=GREGOR_CONFIG)
        res = _run_listener(project, wf, "Go")

        assert res.returncode == 0
        assert _wf_state(project, wf).get("spec_approved") is False, (
            "Eine Freigabe in der falschen Phase darf weiterhin nicht greifen"
        )
        err = res.stderr
        assert "phase1_context" in err, (
            f"Die tatsaechliche Phase muss genannt werden — stderr war: {err!r}"
        )
        assert "phase3_spec" in err, (
            f"Die wirksame Phase muss genannt werden — stderr war: {err!r}"
        )
        assert "Freigabe" in err, f"Der Anlass muss benannt sein — stderr war: {err!r}"

    def test_approval_in_correct_phase_still_works(self, tmp_path):
        """Regressionswaechter: der Normalfall bleibt unveraendert."""
        project, wf = _make_project(tmp_path, "phase3_spec", config_yaml=GREGOR_CONFIG)
        res = _run_listener(project, wf, "Go")

        assert res.returncode == 0
        state = _wf_state(project, wf)
        assert state.get("spec_approved") is True
        assert state.get("current_phase") == "phase4_approved"

    def test_already_approved_is_reported_not_silent(self, tmp_path):
        """Zweite stille Bedingung derselben Zeile: `spec_approved` ist bereits
        True. Auch das darf nicht wortlos verpuffen."""
        project, wf = _make_project(tmp_path, "phase3_spec", spec_approved=True,
                                    config_yaml=GREGOR_CONFIG)
        res = _run_listener(project, wf, "Go")

        assert res.returncode == 0
        assert res.stderr.strip(), "Doppelte Freigabe darf nicht wortlos verpuffen"
        assert "freigegeben" in res.stderr.lower()


class TestGreenInWrongPhaseIsNotSilent:
    def test_green_in_wrong_phase_warns(self, tmp_path):
        """Dieselbe Luecke steht ein zweites Mal im GREEN-Zweig: passt die Phase
        nicht, passiert nichts und niemand erfaehrt davon."""
        project, wf = _make_project(tmp_path, "phase3_spec")
        res = _run_listener(project, wf, "green ok")

        assert res.returncode == 0
        assert _wf_state(project, wf).get("green_approved") is not True
        err = res.stderr
        assert "GREEN" in err, f"Der Anlass muss benannt sein — stderr war: {err!r}"
        assert "phase3_spec" in err, f"Die aktuelle Phase muss genannt sein: {err!r}"
        assert "phase6_implement" in err, f"Die wirksame Phase muss genannt sein: {err!r}"

    def test_green_in_correct_phase_still_works(self, tmp_path):
        project, wf = _make_project(tmp_path, "phase6_implement")
        res = _run_listener(project, wf, "green ok")

        assert res.returncode == 0
        assert _wf_state(project, wf).get("green_approved") is True


class TestOverlappingPhraseDoesNotWarnSpuriously:
    def test_word_serving_both_sets_warns_only_when_nothing_took_effect(self, tmp_path):
        """Heikler Fall des Fundprojekts: `go` ist dort FREIGABE-Phrase und im
        Framework-Default gleichzeitig GREEN-Phrase. Steht der Workflow in
        phase6_implement, ist `go` als GREEN voll wirksam — dann darf die
        Freigabe-Warnung NICHT erscheinen, sonst erzeugt der Fix fuer eine stille
        Verwerfung eine laute Falschmeldung."""
        project, wf = _make_project(tmp_path, "phase6_implement", config_yaml=GREGOR_CONFIG)
        res = _run_listener(project, wf, "go")

        assert res.returncode == 0
        assert _wf_state(project, wf).get("green_approved") is True, (
            "GREEN muss regulaer greifen"
        )
        assert "Freigabe-Stichwort erkannt" not in res.stderr, (
            f"Keine Warnung, wenn dieselbe Nachricht regulaer gewirkt hat: {res.stderr!r}"
        )


class TestGreenPhrasesConfigurable:
    def test_project_can_configure_green_phrases(self, tmp_path):
        """Nebenbefund: `approval`, `stop`, `continue` und `override` waren
        konfigurierbar, `green_phrases` als einziges Set nicht."""
        config = """
workflow:
  green_phrases:
    - "alles gruen"
"""
        project, wf = _make_project(tmp_path, "phase6_implement", config_yaml=config)
        res = _run_listener(project, wf, "alles gruen")

        assert res.returncode == 0
        assert _wf_state(project, wf).get("green_approved") is True, (
            f"Konfiguriertes GREEN-Wort muss greifen — stderr: {res.stderr!r}"
        )


class TestBlockMessageUsesConfiguredPhrases:
    def _validate(self, tmp_path, monkeypatch, phrases: list, workflow_type="feature"):
        import config_loader
        import workflow as wf_module

        monkeypatch.setattr(config_loader, "get_approval_phrases", lambda: list(phrases))
        data = {
            "name": "wf-90",
            "workflow_type": workflow_type,
            "current_phase": "phase3_spec",
            "context_file": "docs/context.md",
            "spec_file": "docs/specs/x.md",
            "spec_approved": False,
        }
        return wf_module._validate_transition(data, "phase4_approved")

    def test_message_names_configured_phrases_not_hardcoded_approved(
        self, tmp_path, monkeypatch
    ):
        """Die Meldung nannte `'approved'` fest verdrahtet — im Fundprojekt ein
        Wort, das dort gar nicht das vereinbarte ist."""
        err = self._validate(tmp_path, monkeypatch, ["go", "validated"])

        assert err is not None
        assert "go" in err, f"Das konfigurierte Wort muss genannt werden: {err!r}"
        assert "validated" in err, f"Alle konfigurierten Woerter: {err!r}"
        assert "'approved'" not in err, (
            f"Das hartkodierte Wort darf nicht mehr als DAS Stichwort erscheinen: {err!r}"
        )

    def test_message_mentions_phase_requirement(self, tmp_path, monkeypatch):
        """Die eigentliche Falle war die Phasenbindung — sie gehoert in die
        Meldung, sonst bleibt die Ursache unauffindbar."""
        err = self._validate(tmp_path, monkeypatch, ["go"])

        assert err is not None and "phase3_spec" in err, (
            f"Die Phasenbindung muss in der Meldung stehen: {err!r}"
        )

    def test_feature_fast_track_message_also_configured(self, tmp_path, monkeypatch):
        """Dieselbe hartkodierte Meldung stand an zwei Stellen (Fast-Track-Zweig)."""
        err = self._validate(tmp_path, monkeypatch, ["go"], workflow_type="feature-fast")

        assert err is not None
        assert "go" in err, f"Auch der Fast-Track-Zweig muss die Config nutzen: {err!r}"
