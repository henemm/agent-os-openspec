#!/usr/bin/env python3
"""
Workflow v3 — Isolated State Manager

Each workflow gets its own JSON file in .claude/workflows/.
Active workflow tracked ONLY via OPENSPEC_ACTIVE_WORKFLOW env var.
The .active symlink fallback is intentionally disabled — using it causes
cross-session drift. Always set: export OPENSPEC_ACTIVE_WORKFLOW=<name>
Atomic writes via tempfile + rename (no file locks).

Usage:
    python3 workflow.py start <name> [--type feature|feature-fast] [--issue N] [--uebernehmen]
    python3 workflow.py switch <name>
    python3 workflow.py status
    python3 workflow.py phase <phase>
    python3 workflow.py phase-log
    python3 workflow.py set-field <key> <value>
    python3 workflow.py set-briefing <pfad-zum-po-briefing>
    python3 workflow.py auto-approve
    python3 workflow.py auto-green
    python3 workflow.py set-affected-files [--replace] <f1> <f2> ...
    python3 workflow.py add-artifact <type> <path> <desc> <phase>
    python3 workflow.py remove-artifact <path> [<phase>]
    python3 workflow.py mark-red <result>
    python3 workflow.py mark-ui-red <result>
    python3 workflow.py write-log [outcome]
    python3 workflow.py override-ambiguous <reason>
    python3 workflow.py finish
    python3 workflow.py abandon --reason "<warum kein Abschluss>"
    python3 workflow.py list
    python3 workflow.py deploy-status <running|done|failed> [<issue-nr|name>] [--note <Grund>]
    python3 workflow.py sessions [--json]
    python3 workflow.py claim status|nachholen [<name>] [--uebernehmen]
    python3 workflow.py observable-surface
    python3 workflow.py handoff [--start] [--mark cloud|herdr]
    python3 workflow.py handoff --same [--start]
"""

from hook_utils import setup_path, find_project_root
from hook_utils import UnsafeStateError, atomic_write_json, read_state_json
from hook_utils import issue_number_from_name, workflow_issue_number
from hook_utils import (auftrag_settings, auftrag_path, read_auftrag, write_auftrag,
                        auftrag_open_issues, auftrag_autark_open, auftrag_mark_done,
                        auftrag_note_text, auftrag_set_spur, normalize_spur,
                        auftrag_owner_key, auftrag_clear, orphan_auftrag,
                        auftrag_claim_orphans)
setup_path()

import hashlib as _hashlib
import json
import math
import os
import re as _re
import sys
import tempfile
import time
from datetime import datetime
from datetime import timedelta
from pathlib import Path

_NAME_RE = _re.compile(r'^[a-zA-Z0-9_-]{1,64}$')

# Platzhalter fuer fehlende optionale Felder in Tabellenausgaben.
SESSIONS_PLACEHOLDER = "–"


def _worktree_root_if_any() -> "Path | None":
    """If CWD is inside a git worktree, return the worktree root (dir with .git FILE).

    Used to keep workflow state worktree-local and prevent cross-session contamination.
    Returns None if in the main repo (where .git is a directory, not a file).
    """
    current = Path.cwd()
    while current != current.parent:
        git_marker = current / ".git"
        if git_marker.is_file():
            return current
        if git_marker.is_dir():
            return None
        current = current.parent
    return None


def _worktree_first_root(rel: str) -> Path:
    """Root für versionierte Repo-Inhalte (Spec/Briefing): Worktree vor Hauptrepo.

    Anders als find_project_root() (Quelle für geteilten Workflow-State) muss
    hier der tatsächliche Arbeitsbaum gewinnen, wenn die Datei dort existiert
    (Vorbild: edit_gate.py:254). Existiert `rel` in keinem Worktree, bleibt
    find_project_root() der Fallback (Hauptrepo-Sessions, Regressionsfreiheit).
    """
    wt = _worktree_root_if_any()
    if wt is not None and (wt / rel).exists():
        return wt
    return find_project_root()


def _worktree_first_path(rel: str) -> Path:
    return _worktree_first_root(rel) / rel


def _validate_name(name: str) -> None:
    """Reject names that would escape the workflows dir or corrupt glob patterns."""
    if not _NAME_RE.fullmatch(name):
        print(
            f"INVALID workflow name: {name!r}\n"
            "Allowed: letters, digits, hyphens, underscores (1–64 chars).\n"
            "Rejected: / .. * ? [ ] { }",
            file=sys.stderr,
        )
        sys.exit(1)

PHASES = [
    "phase0_idle",
    "phase1_context",
    "phase2_analyse",
    "phase3_spec",
    "phase4_approved",
    "phase5_tdd_red",
    "phase6_implement",
    "phase6b_adversary",
    "phase7_validate",
    "phase8_complete",
]

PHASE_NAMES = {
    "phase0_idle": "Idle",
    "phase1_context": "Context Generation",
    "phase2_analyse": "Analysis",
    "phase3_spec": "Specification Writing",
    "phase4_approved": "Spec Approved",
    "phase5_tdd_red": "TDD RED - Write Failing Tests",
    "phase6_implement": "Implementation (TDD GREEN)",
    "phase6b_adversary": "Adversary Verification",
    "phase7_validate": "Validation",
    "phase8_complete": "Complete",
}

# Phasennummer fuer die PO-Anzeige ("Phase 7 von 8"). Bewusst eine eigene
# Tabelle statt PHASES.index(): die Liste enthaelt phase0_idle UND
# phase6b_adversary — index() wuerde phase7_validate als "Phase 8 von 8"
# ausweisen, also ausgerechnet den Zustand, der 3.25.0 ausgeloest hat, als
# fertig darstellen.
PHASE_NUMBERS = {
    "phase0_idle": 0,
    "phase1_context": 1,
    "phase2_analyse": 2,
    "phase3_spec": 3,
    "phase4_approved": 4,
    "phase5_tdd_red": 5,
    "phase6_implement": 6,
    "phase6b_adversary": 6,
    "phase7_validate": 7,
    "phase8_complete": 8,
}

TOTAL_PHASES = 8

# Der Befehl, der die jeweilige Phase weitertreibt. Quelle ist nicht das
# Diagramm, sondern wer die Folgephase schreibt
# (`grep "workflow.py phase phase" core/commands/*.md`): 40-tdd-red setzt am
# Ende phase6_implement, 50-implement am Ende phase7_validate, 60-validate am
# Ende phase8_complete. Wer in Phase X steht, hat also den Befehl offen, der
# X verlaesst.
NEXT_STEP = {
    "phase0_idle": "/00-intake",
    "phase1_context": "/10-context",
    "phase2_analyse": "/20-analyse",
    "phase3_spec": "/30-write-spec",
    "phase4_approved": "/40-tdd-red",
    "phase5_tdd_red": "/40-tdd-red",
    "phase6_implement": "/50-implement",
    "phase6b_adversary": "/50-implement",
    "phase7_validate": "/60-validate",
    "phase8_complete": None,
}

STATUS_NOTE_PREFIX = "[agent-os-openspec]"

# Phasen, in denen `no-build` erlaubt ist und next_step() den Marker auswertet (#424).
_NO_BUILD_PHASES = ("phase1_context", "phase2_analyse")


# Freitext-Schritt (kein "/"), den Claude selbst ausfuehrt (#470). Beginnt mit
# "Auto-": daran erkennt herdr_bridge den Schritt (next=auto).
AUTO_APPROVAL_STEP = "Auto-Freigabe der Spec (workflow.py auto-approve)"
# Freitext-Schritt, wenn die Spec auf das Freigabe-Wort des PO wartet.
APPROVAL_STEP = "Freigabe der Spec (Stichwort: approved)"


def _auto_approval_pending(data: dict) -> bool:
    """Auto-Modus + registrierte gruene Ampel (#470). Wirft nie, im Zweifel False.

    Prueft zusaetzlich die Datei-Aktualitaet (F005): Hash der Briefing-Datei auf
    Platte gleich dem registrierten `briefing_sha256`, Ampel der Datei gruen und
    Pfad im Projekt. Sonst bleibt der normale `approved`-Schritt mit ❗ stehen —
    sonst stuende "Auto-Freigabe" da, waehrend `auto-approve` human liefert.
    """
    try:
        entry = data.get("po_briefing")
        if not (isinstance(entry, dict) and entry.get("ampel") == "green"):
            return False
        if autonomy_mode() != "auto":
            return False
        return _read_current_briefing(entry) is not None
    except Exception:
        return False


def _briefing_path_inside_project(rel: str) -> "Path | None":
    """Aufgeloester Briefing-Pfad, wenn er (nach Symlink-Aufloesung) im Projekt
    liegt, sonst None (#470 F003). Wirft nie."""
    try:
        root = _worktree_first_root(rel)
        path = (root / rel).resolve()
        if not path.is_relative_to(root.resolve()):
            return None
        return path
    except Exception:
        return None


# Obergrenze fuer ein Briefing, das gelesen wird (#470 F010). Ein echtes Briefing
# hat ≤ 150 Woerter; alles darueber ist kein Briefing und wird nicht eingelesen.
_BRIEFING_MAX_BYTES = 256 * 1024


def _read_briefing_file(path: Path) -> "str | None":
    """Briefing-Text nur aus einer regulaeren Datei ≤ 256 KiB, sonst None (F010).

    Oeffnet mit O_NONBLOCK (ein FIFO blockiert so nicht beim open) und prueft
    Typ und Groesse per fstat auf DEMSELBEN Deskriptor — kein Tausch zwischen
    Pruefung und Lesen. FIFO, Device, Ordner, zu gross, kein UTF-8 → None.
    Wirft nie.
    """
    try:
        import stat as _stat
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    except Exception:
        return None
    try:
        st = os.fstat(fd)
        if not _stat.S_ISREG(st.st_mode) or st.st_size > _BRIEFING_MAX_BYTES:
            return None
        chunks, total = [], 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > _BRIEFING_MAX_BYTES:
                return None
            chunks.append(chunk)
        text = b"".join(chunks).decode("utf-8")
        # Wie Path.read_text() (universal newlines): Hash muss zu set-briefing passen.
        return text.replace("\r\n", "\n").replace("\r", "\n")
    except Exception:
        return None
    finally:
        try:
            os.close(fd)
        except Exception:
            pass


def _read_current_briefing(entry: dict) -> "str | None":
    """Text des registrierten Briefings, wenn es im Projekt liegt, unveraendert ist
    (Hash wie bei `set-briefing`) und eine gruene Ampel traegt; sonst None.
    Ohne Seiteneffekt, wirft nie (#470 F005)."""
    try:
        if not (isinstance(entry, dict) and entry.get("file")
                and entry.get("briefing_sha256")):
            return None
        path = _briefing_path_inside_project(entry["file"])
        if path is None:
            return None
        briefing = _read_briefing_file(path)
        if briefing is None:
            return None
        if _hashlib.sha256(briefing.encode("utf-8")).hexdigest() != entry["briefing_sha256"]:
            return None
        if parse_ampel(briefing) != "green":
            return None
        return briefing
    except Exception:
        return None


def next_step(data: dict) -> "str | None":
    """Naechster Pflicht-Schritt fuer den Zustand, oder None (Phase 8 / unklar).

    Zwei Phasen sind nicht allein aus `current_phase` bestimmt:
    - phase3_spec deckt Spec schreiben UND auf Freigabe warten ab; liegt eine
      Spec-Datei vor, ist der offene Schritt das Freigabewort, kein Befehl.
    - phase5_tdd_red bleibt stehen, bis /40-tdd-red am Ende phase6_implement
      setzt; sind die RED-Tests laut State fertig, ist /50-implement faellig.

    Fast Track (#688): in phase4_approved folgt bei `workflow_type ==
    "feature-fast"` direkt /50-implement (kein RED-Schritt); `NEXT_STEP`
    bleibt fuer den vollen Prozess unveraendert.
    """
    if not isinstance(data, dict):
        return None
    phase = data.get("current_phase")
    if not isinstance(phase, str) or phase not in NEXT_STEP:
        return None
    if phase in _NO_BUILD_PHASES and data.get("no_build_reason"):
        return "/99-reset"  # PO-Entscheidung "nichts bauen" (#424)
    if phase == "phase3_spec" and data.get("spec_file") and not data.get("spec_rework"):
        # spec_rework: nach einem Ruecksprung ist die Spec neu zu schreiben (#647)
        if _auto_approval_pending(data):
            return AUTO_APPROVAL_STEP  # Ampel gruen im Auto-Modus (#470)
        return APPROVAL_STEP
    if phase == "phase5_tdd_red" and (
        data.get("red_test_done") or data.get("ui_test_red_done")
    ):
        return "/50-implement"
    if phase == "phase4_approved" and data.get("workflow_type") == "feature-fast":
        return "/50-implement"  # Fast Track ohne RED-Schritt (#688)
    return NEXT_STEP[phase]


def issue_number(workflow_name: str) -> "str | None":
    """Issue-Nummer aus dem Namen (#513) — Huelle um hook_utils.issue_number_from_name.

    Liegt der State vor, gilt workflow_issue_number(data) (Feld `issue_number`).
    """
    return issue_number_from_name(workflow_name)


def expected_footer_command(data: dict) -> "str | None":
    """Erwarteter Fusszeilen-Befehl — dieselbe Quelle wie status_note() (#234).

    Duenne Huelle um next_step() + workflow_issue_number(), damit footer_gate.py die
    Fusszeile gegen genau den Wert prueft, den status_note() ansagt. Keine
    eigene Logik: None und Freitext-Schritte werden unveraendert
    durchgereicht.
    """
    step = next_step(data)
    if not step or not step.startswith("/"):
        return step  # None oder Freitext-Schritt (z.B. "Freigabe der Spec ...")
    issue = workflow_issue_number(data)
    return f"{step} #{issue}" if issue else step


# Schrittliste fuer die Plan-Anzeige (#476). Eigene Tabelle statt PHASES.index():
# Anzeige-Nummern ("6b") und Labels gehoeren nicht in die Phasenlogik.
PLAN_STEPS = (
    ("1", "Kontext", "phase1_context"),
    ("2", "Analyse", "phase2_analyse"),
    ("3", "Spec", "phase3_spec"),
    ("4", "Freigabe", "phase4_approved"),
    ("5", "TDD-RED", "phase5_tdd_red"),
    ("6", "Implement", "phase6_implement"),
    ("6b", "Adversary", "phase6b_adversary"),
    ("7", "Validierung", "phase7_validate"),
    ("8", "Fertig", "phase8_complete"),
)
_FAST_PLAN_PHASES = ("phase3_spec", "phase4_approved", "phase6_implement",
                     "phase7_validate", "phase8_complete")
PLAN_STEPS_FAST = tuple(s for s in PLAN_STEPS if s[2] in _FAST_PLAN_PHASES)
PLAN_TITLE_MAX_LINES = 3   # #612: voller Issue-Titel im Plan-Kopf, umbrochen
PLAN_BRIEF_MAX_LINES = 5   # #612: je Absatz Problem/Ziel

# Auslieferung (#612): Commit, Push, PR, CI, Merge als eigener Schritt nach
# "8 Code fertig". `phase8_complete` setzt `ship_status: open`; `ship-status`
# (auch aus scripts/ship.py) fuehrt ihn weiter. Erst `done`/`skipped` macht ✅.
SHIP_STATUS_VALUES = ("running", "done", "failed", "skipped")
SHIP_PENDING_VALUES = ("open", "running", "failed")


def _plan_deploy_mode(deploy) -> str:
    """Deploy-Modus fuer Plan und Endzustand normalisieren (#510, #550).

    True/"configured" -> "configured"; alles andere (False, None, "off",
    "unconfigured") -> "off": ein Projekt ohne `deploy:`-Block gilt als ohne
    Deploy. Plan und `endstate` gehen beide hierueber, damit sie nie auseinanderlaufen.
    """
    if deploy is True or deploy == "configured":
        return "configured"
    return "off"


# Warum-Text der ❗-Zeile je Schritt (#550). Schluessel = Wert aus next_step();
# "/70-deploy" fuer den offenen Deploy, "" als Rueckfall fuer Unbekanntes.
NEXT_WHY = {
    "/00-intake": "die Aufgabe muss zuerst eingeordnet werden",
    "/10-context": "als Nächstes wird der Kontext gesammelt",
    "/20-analyse": "als Nächstes werden die Anforderungen analysiert",
    "/30-write-spec": "als Nächstes wird die Spec geschrieben",
    APPROVAL_STEP: "die Spec wartet auf deine Freigabe",
    "/40-tdd-red": "als Nächstes entstehen die fehlschlagenden Tests",
    "/50-implement": "als Nächstes wird umgesetzt",
    "/60-validate": "als Nächstes wird die Umsetzung geprüft",
    "/99-reset": "es wird nichts gebaut, der Workflow wird geschlossen",
    "/70-deploy": "der Code ist fertig, das Deploy steht noch aus",
    "": "der nächste Schritt liegt bei dir",
}

END_DONE = "✅ Erledigt: {}. Du kannst /clear ausführen und das nächste Issue starten."
# Mit Vorschlag (#589): dieselbe ✅-Zeile, Schluss nennt die naechste Aufgabe
END_DONE_SUGGEST = ("✅ Erledigt: {}. Du kannst /clear ausführen und mit /00-intake #{} "
                    "weitermachen ({}).")
END_WAITING = "⏳ Läuft noch: {}. Du musst nichts tun, ich melde mich."
END_YOU = "❗ Du: {} — {}"

# Fusszeilen-Regel fuer status_note (#550); gleicher Inhalt wie
# scripts/sync_skills.py::marker_block — beide nennen nur die drei Formen.
END_STATE_RULE = (
    "Wer am Zug ist, steht GENAU EINMAL in der Fußzeile: "
    "„✅ Erledigt: <was>. …“ (Workflow abgeschlossen), „⏳ Läuft noch: <worauf>. …“ "
    "(CI/Agent/Server; vorher `workflow.py waiting \"…\"`, danach "
    "`--clear`) oder „❗ Du: <Schritt> — <warum>“ (PO ist dran, auch beim Warten "
    "auf ihn). `workflow.py endstate` liefert sie als FOOTER."
)


def _one_line(value) -> str:
    """Freitext auf eine Zeile ohne Schlusspunkt bringen (fuer die Endzeilen)."""
    return " ".join(str(value).split()).rstrip(".")


def _end(kind: str, line: str, cmd: "str | None" = None) -> dict:
    return {"kind": kind, "line": line, "cmd": cmd}


def _suggest_parts(suggest, own) -> "tuple[int, str] | None":
    """(Nummer, Grund) eines gueltigen Vorschlags (#589), sonst None. Pure."""
    if not isinstance(suggest, dict):
        return None
    number = _queue_number(suggest.get("n"))
    reason = suggest.get("reason")
    if number is None or number == _queue_number(own) or not isinstance(reason, str):
        return None
    reason = " ".join(reason.split())
    return (number, reason) if reason else None


def _ship_pending(data: dict) -> bool:
    """Auslieferung (#612) noch nicht abgeschlossen: open/running/failed."""
    return data.get("ship_status") in SHIP_PENDING_VALUES


def _end_state_ship(data: dict, head: str, issue, auto_mode: bool) -> dict:
    """Endzustand, solange die Auslieferung (#612) offen, laufend oder gescheitert ist.

    `open` ist der Stand direkt nach `phase8_complete`: im Auto-Modus liefert Claude
    im selben Turn aus (⏳), sonst wartet der Commit auf das Wort des PO (❗).
    `running` ist immer ⏳ (Push, PR, CI, Merge laufen), `failed` immer ❗ mit dem
    Grund aus `ship_note` — nie ein Git-Auftrag an den PO.
    """
    status = data.get("ship_status")
    raw = data.get("ship_note")
    note = _one_line(raw) if isinstance(raw, str) else ""
    what = f"die Auslieferung von {head}"
    if status == "running":
        return _end("waiting", END_WAITING.format(f"{what} ({note})" if note else what))
    if status == "failed":
        cmd = f"/60-validate #{issue}" if issue else "/60-validate"
        why = f"Auslieferung fehlgeschlagen ({note}), bitte neu anstoßen" if note else \
            "Auslieferung fehlgeschlagen, bitte neu anstoßen"
        return _end("you", END_YOU.format(cmd, why), cmd)
    if auto_mode:
        return _end("waiting", END_WAITING.format(f"{what} (Commit, PR, CI, Merge)"))
    return _end("you", END_YOU.format(
        "Sichern freigeben",
        f"der Code von {head} ist fertig, Commit und Auslieferung stehen noch aus"))


def _end_state_final(data: dict, deploy, autonomous: bool, suggest=None,
                     auto_mode: bool = False) -> dict:
    """Endzustand fuer Phase 8 bzw. archiviert (#550, Tabelle der Spec).

    `suggest` (#589) aendert nur die ✅-Zeilen: Schluss nennt die naechste Aufgabe.
    Eine nicht abgeschlossene Auslieferung (#612, `ship_status`) kommt vor dem
    Deploy: erst gemergt, dann deployt, dann ✅.
    """
    issue = workflow_issue_number(data)
    head = f"#{issue}" if issue else (str(data.get("name") or "") or "der Workflow")
    parts = _suggest_parts(suggest, issue)

    def done(what: str) -> dict:
        if parts:
            return _end("done", END_DONE_SUGGEST.format(what, *parts))
        return _end("done", END_DONE.format(what))

    if data.get("status") == "abandoned":
        return done(f"{head} ist abgebrochen")
    if data.get("no_build_reason"):
        return done(f"{head} ist ohne Code-Änderung beendet")
    if _ship_pending(data):
        return _end_state_ship(data, head, issue, auto_mode)
    shipped = data.get("ship_status") == "done"
    if _plan_deploy_mode(deploy) != "configured":
        return done(f"{head} ist fertig und ausgeliefert" if shipped else f"{head} ist fertig")
    status = data.get("deploy_status")
    cmd = f"/70-deploy #{issue}" if issue else "/70-deploy"
    if status == "done":
        return done(f"{head} ist fertig und deployt")
    if status == "running":
        return _end("waiting", END_WAITING.format(f"das Deploy von {head}"))
    if status == "failed":
        raw = data.get("deploy_note")  # #555: nur ein String zaehlt, kein Repr
        note = _one_line(raw) if isinstance(raw, str) else ""
        why = f"Deploy fehlgeschlagen ({note}), bitte neu anstoßen" if note else \
            "Deploy fehlgeschlagen, bitte neu anstoßen"
        return _end("you", END_YOU.format(cmd, why), cmd)
    if autonomous:
        return _end("waiting", END_WAITING.format(f"Claude deployt {head}"))
    return _end("you", END_YOU.format(cmd, NEXT_WHY["/70-deploy"]), cmd)


def _auto_approved(data: dict) -> bool:
    """True, wenn die juengste Spec-Freigabe in `approvals` automatisch war (#688).

    Rein lesend, ohne Config-Zugriff, wirft nie: fehlt `approvals`, ist es keine
    Liste oder hat es keinen dict-Eintrag mit `gate == "spec"`, ist das Ergebnis False.

    Manuelle Freigaben schreiben keinen `approvals`-Eintrag. Deshalb entscheidet
    zuerst der juengste dict-Eintrag in `phase_transitions` mit
    `to == "phase4_approved"`: ist sein `trigger` nicht "auto" (z.B. "approval"
    vom Listener nach einem Ruecksprung), ist das Ergebnis False. Fehlt ein
    solcher Eintrag, bleibt die `approvals`-Logik massgeblich.
    """
    if not isinstance(data, dict):
        return False
    transitions = data.get("phase_transitions")
    if isinstance(transitions, list):
        for entry in reversed(transitions):
            if isinstance(entry, dict) and entry.get("to") == "phase4_approved":
                if entry.get("trigger") != "auto":
                    return False
                break
    approvals = data.get("approvals")
    if not isinstance(approvals, list):
        return False
    for entry in reversed(approvals):
        if isinstance(entry, dict) and entry.get("gate") == "spec":
            return entry.get("by") == "auto"
    return False


def _end_state_open(data: dict, self_driven: bool = False) -> dict:
    """Endzustand fuer Phasen vor 8: Schritt aus next_step(), Warum aus NEXT_WHY.

    `self_driven` (#555): Auto-Modus mit offenem autarkem Auftrag — einen
    Slash-Schritt fuehrt Claude selbst aus, also ⏳ statt einer erfundenen
    PO-Aufgabe. Freigabe-Woerter und Freitext-Schritte bleiben ❗.

    Nach einer Auto-Freigabe (#688, juengster Spec-Eintrag in `approvals` mit
    `by == "auto"`) gilt in phase4_approved dasselbe: Claude fuehrt den
    naechsten Slash-Schritt selbst aus, also ⏳ statt ❗.
    """
    step = next_step(data)
    if step == AUTO_APPROVAL_STEP:
        return _end("waiting", END_WAITING.format("Auto-Freigabe der Spec läuft"))
    why = NEXT_WHY.get(step or "", NEXT_WHY[""])
    if step and step.startswith("/"):
        cmd = expected_footer_command(data)
        if self_driven or (
            data.get("current_phase") == "phase4_approved" and _auto_approved(data)
        ):
            return _end("waiting", END_WAITING.format(f"Claude führt {cmd} selbst aus"), cmd)
        return _end("you", END_YOU.format(cmd, why), cmd)
    return _end("you", END_YOU.format(step or "/00-intake", why))


def _queue_number(value) -> "int | None":
    """Positive Issue-Nummer aus `queue_next` (int oder Ziffern-String), sonst None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and _re.fullmatch(r"[0-9]+", value) and int(value) > 0:
        return int(value)
    return None


def _end_state_queue(number: int, autark: bool) -> dict:
    """Workflow fertig, Auftrag hat ein naechstes Issue (#551): ⏳ autark, sonst ❗."""
    if autark:
        return _end("waiting", END_WAITING.format(f"Claude startet #{number} aus deinem Auftrag"))
    cmd = f"/00-intake #{number}"
    return _end("you", END_YOU.format(cmd, "nächstes Issue aus deinem Auftrag"), cmd)


def end_state(data, archived: bool = False, deploy="off",
              autonomous: bool = False, queue_next=None, autark: bool = False,
              self_driven: bool = False, suggest=None, auto_mode: bool = False) -> dict:
    """Genau einer von drei Endzustaenden (#550): done | waiting | you.

    Rueckgabe `{"kind", "line", "cmd"}`; `line` ist die ganze Zeile fuer
    Chat-Fusszeile, Plan-Schluss und Seitenleiste. Kein Config-Zugriff: Deploy-
    Modus und `autonomous` liefern die Aufrufer. Ein gesetztes `waiting_on`
    (CI, Hintergrund-Agent, Server) hat Vorrang — ausser vor einem
    fehlgeschlagenen Deploy, der eine Handlung verlangt. `queue_next`/`autark`
    (#551) aendern nur den Fall „Workflow fertig“ (Art done): naechstes Issue
    aus dem Auftrag statt ✅; die eigene Issue-Nummer zaehlt dabei nie (#555).
    `self_driven` (#555, aus `queue_end_args`) gilt nur fuer Phasen vor 8.
    `suggest` (#589, `next_suggestion.choose`) aendert nur die ✅-Zeile ohne
    naechstes Issue aus dem Auftrag: "mit /00-intake #M weitermachen (<Grund>)".
    `auto_mode` (#612, aus `queue_end_args`): Autonomie `auto` — eine offene
    Auslieferung ist dann ⏳ (Claude liefert selbst aus) statt ❗.
    """
    data = data if isinstance(data, dict) else {}
    final = archived or data.get("current_phase") == "phase8_complete"
    state = _end_state_final(data, deploy, autonomous, suggest, auto_mode is True) \
        if final else _end_state_open(data, self_driven is True)
    waiting = _one_line(data.get("waiting_on") or "")
    failed = state["kind"] == "you" and final and (
        data.get("deploy_status") == "failed" or data.get("ship_status") == "failed")
    number = _queue_number(queue_next)
    own = _queue_number(workflow_issue_number(data))
    if number is not None and number == own:
        number = None  # eigenes, fertiges Issue ist kein "naechstes" (#555)
    if final and state["kind"] == "done" and number is not None:
        state = _end_state_queue(number, autark is True)
    if waiting and not failed:
        return _end("waiting", END_WAITING.format(waiting))
    return state


def _wrap_plan_tail(line: str, width: int) -> "list[str]":
    """Schlusszeile umbrechen statt kappen (#550): Emoji+Art, dann der Rest."""
    if len(line) <= width:
        return [line]
    import textwrap
    head, sep, rest = line.partition(": ")
    if not sep:
        return textwrap.wrap(line, width) or [line[:width]]
    return [(head + ":")[:width]] + (textwrap.wrap(rest, width) or [])


def _suggest_claimed() -> list:
    """Rohe `issue`-Werte anderer Sitzungen aus dem Session-Register (#589).

    Die eigene Sitzung (`CLAUDE_CODE_SESSION_ID`) zaehlt nicht.
    """
    own = os.environ.get("CLAUDE_CODE_SESSION_ID") or None
    return [e.get("issue") for e in _read_session_entries()
            if e.get("issue") and (own is None or e.get("session_id") != own)]


def _auftrag_spur() -> "str | None":
    """Spur (#591) aus dem Auftrag oder None. Wirft nie."""
    try:
        auftrag = read_auftrag()
        return (auftrag or {}).get("spur") or None
    except Exception:
        return None


def cached_suggestion(data) -> "dict | None":
    """Vorschlag (#589) nur aus dem Cache, frisch gegen das Session-Register. Wirft nie.

    Kein Netz: die Rohdaten holt allein `workflow.py endstate`.
    """
    try:
        import next_suggestion
        cfg = next_suggestion.settings()
        done = _queue_number(workflow_issue_number(data))
        if not cfg["enabled"] or done is None:
            return None
        raw = next_suggestion.read_cache(find_project_root(), done, ttl_s=cfg["cache_ttl_s"])
        if raw is None:
            return None
        return next_suggestion.choose(raw, done, _suggest_claimed(), spur=_auftrag_spur())
    except Exception:
        return None


def _auto_mode_flag() -> bool:
    """Autonomie `auto` als Flag fuer `end_state` (#612); jede Ausnahme -> False."""
    try:
        return autonomy_mode() == "auto"
    except Exception:
        return False


def queue_end_args(data) -> dict:
    """`{"queue_next", "autark", "self_driven", "auto_mode", "suggest"}` fuer `end_state`. Wirft nie.

    Gemeinsame Quelle fuer `endstate`, Plan und Seitenleiste (#551, #555):
    `queue_next` ist die erste offene Nummer, die nicht die des geprueften
    Workflows ist; `self_driven` ist Autonomie `auto` UND ein offener autarker
    Auftrag. Ohne Auftrag, mit Kill-Switch oder bei Fehlern alles leer bzw.
    False. `suggest` (#589) kommt nur ohne `queue_next` und nur aus dem Cache.
    """
    empty = {"queue_next": None, "autark": False, "self_driven": False,
             "auto_mode": False}
    try:
        auto = _auto_mode_flag()
        auftrag = read_auftrag()
        if not auftrag:
            return {**empty, "auto_mode": auto, "suggest": cached_suggestion(data)}
        own = workflow_issue_number(data)
        own_n = int(own) if own else None
        open_issues = auftrag_open_issues(auftrag)
        nxt = next((n for n in open_issues if n != own_n), None)
        autark = auftrag["autark"] is True
        driven = bool(autark and open_issues) and autonomy_mode() == "auto"
        return {"queue_next": nxt, "autark": autark, "self_driven": driven,
                "auto_mode": auto,
                "suggest": None if nxt is not None else cached_suggestion(data)}
    except Exception:
        return empty


def render_plan(data, archived: bool = False, width: "int | None" = None,
                deploy=False, autonomous: bool = False,
                queue: "dict | None" = None, estimate: "dict | None" = None) -> str:
    """Workflow-Plan als Text (#476): ✔ erledigt, ▶ laeuft, ○ offen. Pure.

    `deploy` (#478, #510, #550): nur Modus "configured" (siehe
    `_plan_deploy_mode`) fuegt nach "8 Code fertig" einen Schritt Deploy an.
    Der Deploy-Zustand kommt aus `data["deploy_status"]` (running/done/failed).
    Schlusszeile ist immer `end_state(...)["line"]` — dieselbe Zeile wie
    `workflow.py endstate` im Chat. `queue` (#551) ist das Ergebnis von
    `queue_end_args(data)`; die Aufrufer lesen den Auftrag, damit dies rein bleibt.
    `estimate` (#620, aus `current_estimate`) haengt nach den Schritten den
    Zeit-Block an; ohne `estimate` bleibt die Ausgabe unveraendert.
    """
    if not isinstance(data, dict):
        lines, times, tail = ["Kein aktiver Workflow"], None, None
    else:
        lines = _plan_lines(data, archived, deploy, width)
        times = _plan_time_lines(data, estimate) if estimate is not None else []
        tail = end_state(data, archived=archived, deploy=deploy,
                         autonomous=autonomous, **(queue or {}))["line"]
    narrow = isinstance(width, int) and width > 0
    if narrow:  # #642: Zeit-Block umbrechen, alle anderen Zeilen wie bisher kappen
        lines = [line[:width] for line in lines]
        times = None if times is None else [
            part for line in times for part in _wrap_time_line(line, width)]
    if times is not None:
        lines += times + [""]
    if tail:
        lines += _wrap_plan_tail(tail, width) if narrow else [tail]
    return "\n".join(lines)


def _wrap_time_line(line: str, width: int) -> "list[str]":
    """Zeile des Zeit-Blocks bei `width` umbrechen statt kappen (#642);
    Folgezeilen mit TIME_INDENT eingerückt."""
    if len(line) <= width:
        return [line]
    if width <= len(TIME_INDENT):
        return [line[:width]]
    import textwrap
    return textwrap.wrap(line, width, subsequent_indent=TIME_INDENT) or [line[:width]]


def _plan_lines(data: dict, archived: bool, deploy,
                width: "int | None" = None) -> "list[str]":
    """Kopf und Schrittliste des Plans ohne Schlusszeile (#476, #490, #510, #612)."""
    fast = data.get("workflow_type") == "feature-fast"
    steps = PLAN_STEPS_FAST if fast else PLAN_STEPS
    phase = data.get("current_phase")
    done_all = archived or phase == "phase8_complete"
    no_build = bool(data.get("status") == "abandoned" or data.get("no_build_reason"))
    with_deploy = _plan_deploy_mode(deploy) == "configured" and not no_build
    # #612: Auslieferung als eigener Schritt. Vor Phase 8 immer (sie kommt noch),
    # ab Phase 8 nur mit Marker — archivierte Workflows aelterer Fassungen haben
    # keinen und bleiben wie bisher.
    with_ship = not no_build and ("ship_status" in data or not done_all)
    ship_final = not with_ship or data.get("ship_status") in ("done", "skipped")
    running = None
    if not done_all and phase in PHASES and phase != "phase0_idle":
        # Phase nicht in der Liste (Fast Track): letzter Schritt davor laeuft
        pos = PHASES.index(phase)
        for i, (_, _, step_phase) in enumerate(steps):
            if PHASES.index(step_phase) <= pos:
                running = i
    issue = workflow_issue_number(data)
    lines = [f"Workflow #{issue}" if issue else "Workflow", str(data.get("name") or "")]
    title = data.get("issue_title")
    if isinstance(title, str) and title.strip():
        lines += _wrap_text(title, width, PLAN_TITLE_MAX_LINES)  # #490/#612: Titel
    lines.append("")
    lines += _plan_brief_lines(data.get("issue_brief"), width)  # #612: Problem/Ziel
    for i, (nr, label, step_phase) in enumerate(steps):
        if (with_deploy or with_ship) and step_phase == "phase8_complete":
            label = "Code fertig"  # #510/#612: fertig ist erst nach Auslieferung/Deploy
        if done_all or (running is not None and i < running):
            lines.append(f"✔ {nr} {label}")
        elif i == running:
            lines.append(f"▶ {nr} {label}  (läuft)")
        else:
            lines.append(f"○ {nr} {label}")
    if with_ship:
        lines.append(_plan_ship_line(data.get("ship_status"), done_all))
    if with_deploy:
        lines.append(_plan_deploy_line(data.get("deploy_status"), done_all and ship_final))
    return lines


def _plan_ship_line(status, done_all: bool) -> str:
    """Zeile „Ausliefern“ des Plans (#612): Commit, Push, PR, CI, Merge."""
    if not done_all:
        return "○ Ausliefern"
    return {"done": "✔ Ausliefern", "running": "▶ Ausliefern  (läuft)",
            "failed": "✘ Ausliefern  (fehlgeschlagen)",
            "skipped": "○ Ausliefern  (entfällt)"}.get(status, "▶ Ausliefern  (offen)")


def _wrap_text(text: str, width: "int | None", max_lines: int) -> "list[str]":
    """Text auf `width` umbrechen, hoechstens `max_lines` Zeilen, Rest „…“ (#612).

    Ohne `width` eine einzige Zeile. Pure.
    """
    text = " ".join(str(text).split())
    if not text:
        return []
    if not (isinstance(width, int) and width > 0):
        return [text]
    import textwrap
    out = textwrap.wrap(text, width, break_long_words=True) or [text[:width]]
    if len(out) > max_lines:
        out = out[:max_lines]
        out[-1] = out[-1][: max(1, width - 1)].rstrip() + "…"
    return out


def _plan_brief_lines(brief, width: "int | None") -> "list[str]":
    """Kopfblock „Problem“/„Ziel“ aus der Issue-Kurzfassung (#612); leer ohne Inhalt."""
    if not isinstance(brief, dict):
        return []
    out: "list[str]" = []
    for key, label in (("problem", "Problem"), ("goal", "Ziel")):
        value = brief.get(key)
        if isinstance(value, str) and value.strip():
            out += _wrap_text(f"{label}: {value}", width, PLAN_BRIEF_MAX_LINES)
    return out + [""] if out else []


def _plan_deploy_line(status, done_all: bool) -> str:
    """Deploy-Zeile des Plans bei Modus "configured" (#510, #550)."""
    if not done_all:
        return "○ Deploy"
    return {"done": "✔ Deploy", "running": "▶ Deploy  (läuft)",
            "failed": "✘ Deploy  (fehlgeschlagen)"}.get(status, "▶ Deploy  (offen)")


# --- Zeitschätzung (#620) ----------------------------------------------------
# Erfahrungswerte aus dem Archiv (`phase_log`), reine Anzeige, fail-open.
# #642: `defaults` bleibt gültiger Schlüssel, wird aber nicht mehr angezeigt.
TIME_ESTIMATE_DEFAULTS = {"enabled": True, "min_samples": 3, "quantiles": [0.1, 0.9],
                          "defaults": {"feature": [60, 240], "feature-fast": [20, 60]},
                          "idle_gap_min": 15, "display_timezone": "Europe/Berlin"}
APPROVAL_PHASE = "phase4_approved"
PERCENT_MIN_SAMPLES = 10   # #642: Prozentangabe erst ab so vielen Vergleichs-Workflows
TIME_INDENT = "  "         # #642: Einzug Basiszeile und Umbruch, passt in 34 Zeichen
NO_DATA = "zu wenig Vergleichsdaten"


def _estimate_now() -> datetime:
    """Uhr der Zeitschätzung (#620); eigene Funktion, damit Tests sie ersetzen."""
    return datetime.now()


def _is_num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _score_stage(score) -> "str | None":
    """Score-Stufe aus `intake_score` (#620): "0", "1-3", "4-6", sonst None."""
    if not _is_num(score) or int(score) != score or not 0 <= score <= 6:
        return None
    return "0" if score == 0 else ("1-3" if score <= 3 else "4-6")


def _po_wait_span(data, now=None) -> "tuple[datetime, datetime] | None":
    """Wartezeit auf die Spec-Freigabe (#628): [po_briefing.created, Freigabe].

    Nur bei einem Übergang nach phase4_approved mit trigger "approval"; ohne
    Übergang mit `now` [Briefing, now], solange phase3_spec auf die menschliche
    Freigabe wartet; sonst (auto, kein Briefing, ungültige Zeitstempel) None.
    """
    try:
        brief = _parse_time(data["po_briefing"]["created"])
        for tr in data.get("phase_transitions") or []:
            if not isinstance(tr, dict) or tr.get("to") != "phase4_approved":
                continue
            try:
                at = _parse_time(tr.get("at"))
            except Exception:
                continue
            if at >= brief:
                return (brief, at) if tr.get("trigger") == "approval" else None
        if now is not None and data.get("current_phase") == "phase3_spec" \
                and awaiting_human_approval(data):
            return (brief, now)
    except Exception:
        pass
    return None


def _overlap_min(span, start: datetime, end: datetime) -> float:
    """Überschneidung der Spanne mit [start, end] in Minuten (nie negativ)."""
    if span is None:
        return 0.0
    return max(0.0, (min(span[1], end) - max(span[0], start)).total_seconds() / 60)


def po_wait_minutes(data, now: "datetime | None" = None) -> dict:
    """PO-Wartezeit je Phase (#628): Überschneidung der Wartespanne mit den
    `phase_log`-Segmenten; offene Segmente nur mit `now`. {} bei Fehler."""
    out: dict = {}
    try:
        span = _po_wait_span(data, now)
        if span is None:
            return {}
        for entry in data.get("phase_log") or []:
            try:
                end = entry.get("exited_at")
                end = _parse_time(end) if end is not None else now
                if end is None:
                    continue
                wait = _overlap_min(span, _parse_time(entry["entered_at"]), end)
            except Exception:
                continue
            if wait > 0:
                out[entry["phase"]] = out.get(entry["phase"], 0.0) + wait
    except Exception:
        return {}
    return out


def _activity_path(name) -> "Path | None":
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        return None
    return _workflows_dir() / "_activity" / f"{name}.json"


def load_activity(name) -> "dict | None":
    """Aktivitätsdatei des Workflows (#628) als `{last, phases}` mit nur
    gültigen Minuten; None, wenn fehlend oder kaputt. Wirft nie."""
    try:
        path = _activity_path(name)
        if path is None or path.is_symlink() or not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        phases = raw.get("phases") if isinstance(raw.get("phases"), dict) else {}
        return {"last": raw.get("last") if isinstance(raw.get("last"), str) else None,
                "phases": {k: float(v) for k, v in phases.items()
                           if isinstance(k, str) and _is_num(v) and 0 <= v < float("inf")}}
    except Exception:
        return None


def _idle_gap_min() -> float:
    """`time_estimate.idle_gap_min` (Zahl > 0), sonst Standard 15 (#628)."""
    try:
        from config_loader import load_config
        value = (load_config().get("time_estimate") or {}).get("idle_gap_min")
        if _is_num(value) and value > 0:
            return float(value)
    except Exception:
        pass
    return float(TIME_ESTIMATE_DEFAULTS["idle_gap_min"])


def note_activity(name, phase, now) -> None:
    """Aktivitätsschlag (#628): liegt `last` höchstens `idle_gap_min` zurück,
    zählt die Differenz für `phase`; sonst wird nur `last` gesetzt. Schreibt
    atomar `.claude/workflows/_activity/<name>.json`, nie das Workflow-JSON.
    Wirft nie."""
    try:
        path = _activity_path(name)
        if path is None or not isinstance(phase, str) or not isinstance(now, datetime):
            return
        now = _parse_time(now)
        current = load_activity(name) or {}
        phases = dict(current.get("phases") or {})
        try:
            gap = (now - _parse_time(current["last"])).total_seconds() / 60
        except Exception:
            gap = None
        if gap is not None and 0 < gap <= _idle_gap_min():
            phases[phase] = round(phases.get(phase, 0.0) + gap, 2)
        from hook_utils import atomic_write_text
        atomic_write_text(path, json.dumps(
            {"last": now.isoformat(timespec="seconds"), "phases": phases}, indent=2))
    except Exception:
        pass


def _activity_phases(name) -> dict:
    """Aktivminuten je Phase, {} ohne brauchbare Aktivitätsdatei."""
    return (load_activity(name) or {}).get("phases") or {}


def _archive_phase_entry(data) -> "dict | None":
    """Ein Archiv-Workflow als `{type, stage, phases, clean}`, oder None, wenn er nicht zählt.

    #628: Arbeitszeit. Aktivminuten aus der Aktivitätsdatei, sonst `phase_log`
    je Segment abzüglich PO-Wartezeit (nie unter 0). #642: `clean` nur mit
    lesbarer Aktivitätsdatei; nur solche Einträge bilden die Vergleichsgruppe.
    """
    if not isinstance(data, dict) or data.get("status") == "abandoned":
        return None
    phases: dict = dict(_activity_phases(data.get("name")))
    clean = bool(phases)
    log = data.get("phase_log")
    span = _po_wait_span(data) if not phases else None
    for entry in log if isinstance(log, list) and not phases else []:
        if not isinstance(entry, dict) or entry.get("exited_at") is None:
            continue
        dur, phase = entry.get("duration_min"), entry.get("phase")
        if _is_num(dur) and isinstance(phase, str):
            try:
                wait = _overlap_min(span, _parse_time(entry["entered_at"]),
                                    _parse_time(entry["exited_at"]))
            except Exception:
                wait = 0.0
            # Wiedereintritte summiert
            phases[phase] = phases.get(phase, 0.0) + max(0.0, float(dur) - wait)
    if not phases:
        return None
    return {"type": data.get("workflow_type") or "feature",
            "stage": _score_stage(data.get("intake_score")), "phases": phases, "clean": clean}


def load_archive_phase_durations(archive_dir=None) -> list:
    """Phasendauern der archivierten Workflows (#620). Kaputte Dateien werden übersprungen."""
    try:
        folder = Path(archive_dir) if archive_dir is not None else _archive_dir()
        files = sorted(folder.glob("*.json")) if folder.is_dir() else []
    except Exception:
        return []
    history = []
    for path in files:
        try:
            if path.is_symlink():
                continue
            entry = _archive_phase_entry(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        if entry:
            history.append(entry)
    return history


def _valid_estimate_config(raw) -> "dict | None":
    """Abschnitt `time_estimate` geprüft; None = aus (Kill-Switch oder ungültig)."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return None
    cfg = dict(TIME_ESTIMATE_DEFAULTS, **raw)
    defaults = cfg.get("defaults")
    if cfg.get("enabled") is False or not isinstance(defaults, dict):  # nur false = aus
        return None
    cfg["defaults"] = dict(TIME_ESTIMATE_DEFAULTS["defaults"], **defaults)
    if not isinstance(cfg.get("display_timezone"), str):  # #637: sonst Standard
        cfg["display_timezone"] = TIME_ESTIMATE_DEFAULTS["display_timezone"]
    q, n = cfg.get("quantiles"), cfg.get("min_samples")
    if not (isinstance(n, int) and not isinstance(n, bool) and n >= 1):
        return None
    if not (isinstance(q, (list, tuple)) and len(q) == 2 and all(_is_num(v) for v in q)
            and 0 <= q[0] <= q[1] <= 1):
        return None
    for pair in cfg["defaults"].values():
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2
                and all(_is_num(v) for v in pair) and 0 <= pair[0] <= pair[1]):
            return None
    return cfg


def time_estimate_config() -> "dict | None":
    """`time_estimate` aus der Projekt-Config (#620); None bei aus oder Fehler."""
    try:
        from config_loader import load_config
        return _valid_estimate_config(load_config().get("time_estimate"))
    except Exception:
        return None


def _parse_time(value) -> datetime:
    """ISO-Zeitstempel oder datetime als naive Ortszeit; wirft bei Ungültigem."""
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def _quantile(values: list, q: float) -> float:
    """Quantil sortierter Werte mit linearer Interpolation."""
    pos = (len(values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def _estimate_steps(data: dict) -> "tuple[list, int]":
    """Phasen des Plans und Index des laufenden Schritts (wie `_plan_lines`)."""
    steps = PLAN_STEPS_FAST if data.get("workflow_type") == "feature-fast" else PLAN_STEPS
    phases = [s[2] for s in steps]
    pos = PHASES.index(data.get("current_phase"))
    running = 0
    for i, step_phase in enumerate(phases):
        if PHASES.index(step_phase) <= pos:
            running = i
    return phases, running


def _minutes_in_phase(data: dict, phase: str, now: datetime,
                      activity: "dict | None" = None) -> float:
    """Arbeitsminuten der laufenden Phase (#628): aus der Aktivität, sonst
    offener `phase_log`-Eintrag abzüglich PO-Wartezeit, sonst 0."""
    if activity:
        return float(activity.get(phase, 0.0))
    for entry in reversed(data.get("phase_log") or []):
        if entry.get("phase") == phase and entry.get("exited_at") is None:
            entered = _parse_time(entry["entered_at"])
            wait = _overlap_min(_po_wait_span(data, now), entered, now)
            return max(0.0, (now - entered).total_seconds() / 60 - wait)
    return 0.0


def _estimate_group(data: dict, history: list, min_samples: int) -> list:
    """Vergleichsgruppe (#620): gleiche Score-Stufe, sonst gleicher Typ, sonst leer.

    #642: nur saubere Einträge (`clean is True`, mit Aktivitätsdatei).
    """
    wtype = data.get("workflow_type") or "feature"
    same = [h for h in history if isinstance(h, dict) and h.get("type") == wtype
            and h.get("clean") is True]
    stage = _score_stage(data.get("intake_score"))
    if stage is not None:
        staged = [h for h in same if h.get("stage") == stage]
        if len(staged) >= min_samples:
            return staged
    return same if len(same) >= min_samples else []


def _estimate_rests(data, history, config, now, activity: "dict | None" = None,
                    until: "str | None" = None) -> "tuple[list, list, list]":
    """Restarbeit je Vergleichs-Workflow (Minuten, sortiert), Gruppe und Planphasen.

    #642: leere Gruppe = keine Schätzung (keine Startwerte); `until` = letzte
    mitgezählte Planphase (einschließlich), z. B. phase3_spec bis zur Freigabe.
    """
    phases, running = _estimate_steps(data)
    current = phases[running]
    in_phase = _minutes_in_phase(data, current, now, activity) if current == data.get(
        "current_phase") else 0.0
    group = _estimate_group(data, history, config["min_samples"])
    later = phases[running + 1:(phases.index(until) + 1 if until in phases else None)]
    rests = []
    for item in group:
        dur = item["phases"]
        rests.append(max(0.0, float(dur.get(current, 0) or 0) - in_phase)
                     + sum(float(dur.get(p, 0) or 0) for p in later))
    return sorted(rests), group, phases


def _measured_hit_rate(group: list, phases: list, quantiles) -> "int | None":
    """Nachgemessene Trefferquote der Ende-Spanne in Prozent (#642), pure.

    Leave-one-out über die Restarbeit ab phase4_approved: je Workflow die Spanne
    (Quantile `quantiles`) aus den übrigen; Treffer, wenn seine Restarbeit
    darin lag. None unter zwei Workflows oder bei Fehler.
    """
    try:
        later = phases[phases.index(APPROVAL_PHASE):]
        rests = [sum(float(g["phases"].get(p, 0) or 0) for p in later) for g in group]
        if len(rests) < 2:
            return None
        hits = 0
        for i, rest in enumerate(rests):
            others = sorted(rests[:i] + rests[i + 1:])
            hits += _quantile(others, quantiles[0]) <= rest <= _quantile(others, quantiles[1])
        return round(100 * hits / len(rests))
    except Exception:
        return None


def _quarter_floor(value: datetime, zone=None) -> datetime:
    """Auf die Viertelstunde abrunden, in der Anzeigezone (#637, #642); naive Ortszeit."""
    dt = _display_time(value, zone)
    return _parse_time(dt.replace(minute=dt.minute // 15 * 15, second=0, microsecond=0))


def _quarter_ceil(value: datetime, zone=None) -> datetime:
    """Auf die Viertelstunde aufrunden (#642); nie früher als `value`."""
    low = _quarter_floor(value, zone)
    return low if low >= _parse_time(value) else low + timedelta(minutes=15)


def _before_approval(data: dict) -> bool:
    """Steht der Workflow vor phase4_approved (#642)? Wirft bei unbekannter Phase."""
    return PHASES.index(data.get("current_phase")) < PHASES.index(APPROVAL_PHASE)


def estimate_remaining(data, history, config, now,
                       activity: "dict | None" = None) -> "dict | None":
    """Restdauer-Schätzung (#620), pure. None bei ungültigen Eingaben (fail-open).

    #628: verstrichen = Arbeitszeit, aus `activity` (Aktivminuten je Phase),
    sonst Wanduhr abzüglich PO-Wartezeit. #642: ohne saubere Gruppe `n=0`,
    `source="none"`, keine Uhrzeiten; vor der Freigabe nur `approval` (Median
    bis einschließlich phase3_spec, nächste Viertelstunde); danach `end_low`
    ab- und `end_high` aufgerundet, ab PERCENT_MIN_SAMPLES mit `hit_rate`.
    """
    try:
        start = _parse_time(data["created"])
        if activity:
            elapsed = sum(float(v) for v in activity.values())
        else:
            elapsed = max(0.0, (now - start).total_seconds() / 60
                          - _overlap_min(_po_wait_span(data, now), start, now))
        est = {"n": 0, "source": "none", "start": start, "now": now, "elapsed_min": elapsed,
               "approval": None, "end_low": None, "end_high": None, "hit_rate": None}
        rests, group, phases = _estimate_rests(data, history, config, now, activity)
        if not group:
            return est
        zone = config.get("display_timezone")
        q_low, q_high = config["quantiles"]
        low, mid, high = (_quantile(rests, q) for q in (q_low, 0.5, q_high))
        est.update(n=len(group), source="archive", low_min=low, mid_min=mid, high_min=high,
                   total_low_min=elapsed + low, total_high_min=elapsed + high)
        if _before_approval(data):
            to_approval = _estimate_rests(data, history, config, now, activity,
                                          until="phase3_spec")[0]
            est["approval"] = _quarter_floor(
                now + timedelta(minutes=_quantile(to_approval, 0.5) + 7.5), zone)
        else:
            est["end_low"] = _quarter_floor(now + timedelta(minutes=low), zone)
            est["end_high"] = _quarter_ceil(now + timedelta(minutes=high), zone)
            if len(group) >= PERCENT_MIN_SAMPLES:
                est["hit_rate"] = _measured_hit_rate(group, phases, config["quantiles"])
    except Exception:
        return None
    return est


def _archive_cache_key():
    """(mtime, Dateizahl) des Archivordners; None, wenn nicht lesbar."""
    try:
        folder = _archive_dir()
        return folder.stat().st_mtime_ns, sum(1 for _ in folder.glob("*.json"))
    except Exception:
        return None


def current_estimate(data, archived: bool = False,
                     cache: "dict | None" = None) -> "dict | None":
    """Schätzung für Plan/CLI (#620); None bei Kill-Switch oder Fehler. Wirft nie.

    Abgeschlossene/archivierte Workflows bekommen `{"actual": True}` (Ist-Block).
    `cache` (plan --watch): Archiv nur neu laden, wenn sich mtime/Dateizahl ändern.
    `display_tz` (#637) trägt `time_estimate.display_timezone` zur Anzeige.
    """
    try:
        cfg = time_estimate_config()
        if cfg is None or not isinstance(data, dict):
            return None
        now = _estimate_now()
        zone = cfg.get("display_timezone")
        if archived or data.get("current_phase") == "phase8_complete":
            return {"actual": True, "now": now, "display_tz": zone}
        if cache is None:
            history = load_archive_phase_durations()
        else:
            key = _archive_cache_key()
            if "history" not in cache or cache.get("key") != key:
                cache["key"], cache["history"] = key, load_archive_phase_durations()
            history = cache["history"]
        est = estimate_remaining(data, history, cfg, now, _activity_phases(data.get("name")))
        if est is not None:
            est["display_tz"] = zone
        return est
    except Exception:
        return None


def format_duration(minutes) -> str:
    """Lesbare Dauer (#620): "45 min", "2 h", "1 h 10 min"."""
    total = int(round(float(minutes)))
    if total < 60:
        return f"{total} min"
    hours, rest = divmod(total, 60)
    return f"{hours} h" if rest == 0 else f"{hours} h {rest} min"


def _display_time(value, zone=None) -> datetime:
    """Zeit in der Anzeigezone (#637); naiv = Systemzeit des Prozesses.

    `zone` = IANA-Name aus `display_timezone`; None, `local`, ungültiger Name
    oder fehlende Zonendaten -> naive Systemzeit wie `_parse_time`. Wirft nur
    bei ungültigem `value` (wie `_parse_time`).
    """
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    target = None
    if isinstance(zone, str) and zone and zone != "local":
        try:
            from zoneinfo import ZoneInfo
            target = ZoneInfo(zone)
        except Exception:
            target = None
    if target is None:
        return _parse_time(dt)
    return (dt if dt.tzinfo else dt.astimezone()).astimezone(target)


def _format_clock(value, today, zone=None) -> str:
    """Uhrzeit HH:MM, an einem anderen Tag als `today` mit Datum DD.MM;
    in der Anzeigezone `zone` (#637), `today` muss dort bestimmt sein."""
    dt = _display_time(value, zone)
    return dt.strftime("%H:%M") if dt.date() == today else dt.strftime("%d.%m. %H:%M")


def _finished_span(data: dict) -> "tuple[datetime, datetime] | None":
    """Tatsächlicher Start und Ende eines fertigen Workflows, sonst None."""
    log = data.get("phase_log")
    last = log[-1] if isinstance(log, list) and log else {}
    end = (last.get("exited_at") if isinstance(last, dict) else None) \
        or data.get("last_updated")
    if not data.get("created") or not end:
        return None
    return _parse_time(data["created"]), _parse_time(end)


def _finished_work_min(data: dict, end: datetime, total: float) -> float:
    """Arbeitszeit eines fertigen Workflows (#628): Aktivminuten, sonst
    `phase_log` abzüglich PO-Wartezeit plus offenes letztes Segment bis `end`."""
    try:
        activity = _activity_phases(data.get("name"))
        if activity:
            return sum(activity.values())
        entry = _archive_phase_entry(data)
        if entry is None:
            return total
        work = sum(entry["phases"].values())
        last = (data.get("phase_log") or [{}])[-1]
        if isinstance(last, dict) and last.get("exited_at") is None and last.get("entered_at"):
            entered = _parse_time(last["entered_at"])
            work += max(0.0, (end - entered).total_seconds() / 60
                        - _overlap_min(_po_wait_span(data), entered, end))
        return work
    except Exception:
        return total


def _ship_start(data: dict) -> "datetime | None":
    """Beginn der Auslieferung (#645): `entered_at` des letzten
    `phase8_complete`-Eintrags im `phase_log`, sonst das Ende aus
    `_finished_span`; nie `ship_at` (wird bei jedem `running` überschrieben)."""
    log = data.get("phase_log")
    for entry in reversed(log if isinstance(log, list) else []):
        if isinstance(entry, dict) and entry.get("phase") == "phase8_complete" \
                and entry.get("entered_at"):
            return _parse_time(entry["entered_at"])
    span = _finished_span(data)
    return span[1] if span else None


def _shipped_at(data: dict) -> "datetime | None":
    """`ship_at` einer abgeschlossenen Auslieferung (#645), None wenn
    `ship_status` nicht done/skipped ist oder `ship_at` fehlt/unlesbar ist."""
    if data.get("ship_status") not in ("done", "skipped") or not data.get("ship_at"):
        return None
    try:
        return _parse_time(data["ship_at"])
    except Exception:
        return None


def _actual_time_lines(data: dict, now, today, zone) -> "list[str]":
    """Ist-Block des Plans (#620, #628); während der Auslieferung
    „Ausliefern  seit“ und „Ende  offen“, danach Ende = `ship_at` (#645)."""
    span = _finished_span(data)
    if span is None:
        return []
    start, end = span
    if data.get("ship_status") in SHIP_PENDING_VALUES:
        since = _ship_start(data)
        if since is None:
            return []
        running = max(0.0, (_parse_time(now) - since).total_seconds() / 60)
        return ["", f"Start  {_format_clock(start, today, zone)}",
                f"Ausliefern  seit {_format_clock(since, today, zone)} "
                f"({format_duration(running)})", "Ende  offen"]
    shipped = _shipped_at(data)
    if shipped is not None and shipped >= start:
        end = shipped
    total = max(0.0, (end - start).total_seconds() / 60)
    work = min(total, _finished_work_min(data, end, total))
    dur = format_duration(work)
    if round(work) != round(total):
        dur += f" (gesamt {format_duration(total)})"
    return ["", f"Start  {_format_clock(start, today, zone)}", f"Dauer  {dur}",
            f"Ende  {_format_clock(end, today, zone)}"]


def _plan_time_lines(data: dict, estimate) -> "list[str]":
    """Zeit-Block des Plans (#620): Prognose oder Ist-Werte; [] bei Fehler."""
    try:
        if not isinstance(estimate, dict) or data.get("status") == "abandoned":
            return []
        now = estimate.get("now") or _estimate_now()
        zone = estimate.get("display_tz")
        today = _display_time(now, zone).date()
        if estimate.get("actual"):
            return _actual_time_lines(data, now, today, zone)
        # #642: keine Dauer-Zeile; Freigabe vor phase4, danach Ende, Basis eigene Zeile
        if _before_approval(data) and awaiting_human_approval(data):
            middle = "Freigabe  wartet auf dich"
        elif estimate.get("n") and estimate.get("approval") is not None:
            middle = f"Freigabe  ca. {_format_clock(estimate['approval'], today, zone)}"
        elif estimate.get("n") and estimate.get("end_low") is not None:
            middle = f"Ende  ca. {_estimate_end_text(estimate, today, zone)}"
        else:
            middle = "Ende  offen"
        countdown = _countdown_text(estimate, data)
        return ["", f"Start  {_format_clock(estimate['start'], today, zone)}", middle,
                *([countdown] if countdown else []), TIME_INDENT + _estimate_basis(estimate)]
    except Exception:
        return []


def _countdown_text(estimate: dict, data: dict) -> "str | None":
    """Grober Countdown (#655) aus den angezeigten Zeitpunkten minus `now`:
    vor der Freigabe „Noch  ca. N Min bis Freigabe“, danach die Spanne
    „Noch  ca. L–H Min“ (ab 120 Min in halben Stunden); None = keine Zeile."""
    if not estimate.get("n") or (_before_approval(data) and awaiting_human_approval(data)):
        return None
    now = _parse_time(estimate.get("now") or _estimate_now())

    def minutes(key):
        return round((_parse_time(estimate[key]) - now).total_seconds() / 60, 6)

    if estimate.get("approval") is not None:
        left = minutes("approval")
        if left <= 0:
            return None
        return f"Noch  ca. {max(5, math.floor(left / 5 + 0.5) * 5)} Min bis Freigabe"
    if estimate.get("end_low") is None or estimate.get("end_high") is None:
        return None
    low, high = minutes("end_low"), minutes("end_high")
    if high <= 0:
        return None
    low5, high5 = math.floor(low / 5) * 5, math.ceil(high / 5) * 5
    if high5 >= 120:
        unit = "h"
        lo, hi = (f"{v:g}".replace(".", ",") for v in
                  (max(0.5, math.floor(low / 30) / 2), math.ceil(high / 30) / 2))
    else:
        unit, lo, hi = "Min", str(low5), str(high5)
    if low5 <= 0:
        return f"Noch  bis ca. {hi} {unit}"
    return f"Noch  ca. {hi if lo == hi else f'{lo}–{hi}'} {unit}"


def awaiting_human_approval(data) -> bool:
    """Wartet der Workflow auf eine menschliche Freigabe (#628)? Wirft nie.

    phase3_spec mit registriertem Briefing ohne greifende Auto-Freigabe
    („approved“), oder phase6_implement mit grünem Testlauf, ohne GREEN und
    im Modus manual („go“).
    """
    try:
        phase = data.get("current_phase")
        if phase == "phase3_spec":
            return bool(isinstance(data.get("po_briefing"), dict)
                        and data["po_briefing"] and not _auto_approval_pending(data))
        if phase == "phase6_implement":
            run = data.get("last_test_run")
            return bool(isinstance(run, dict) and run.get("result") == "passed"
                        and not data.get("green_approved") and autonomy_mode() != "auto")
    except Exception:
        pass
    return False


def _estimate_end_text(estimate: dict, today, zone=None) -> str:
    """Ende-Spanne „A–B“ (#642), bei A = B eine einzige Uhrzeit."""
    low = _format_clock(estimate["end_low"], today, zone)
    high = _format_clock(estimate["end_high"], today, zone)
    return low if low == high else f"{low}–{high}"


def _estimate_basis(estimate: dict) -> str:
    """Basiszeile (#642): „P % sicher, aus N Workflows“ (P nachgemessen, ab
    PERCENT_MIN_SAMPLES), sonst „aus N Workflows“, ohne Daten NO_DATA."""
    n = estimate.get("n") or 0
    if estimate.get("source") != "archive" or not n:
        return NO_DATA
    base = f"aus {n} Workflow{'' if n == 1 else 's'}"
    rate = estimate.get("hit_rate")
    return f"{rate} % sicher, {base}" if rate is not None and n >= PERCENT_MIN_SAMPLES else base


def status_note(data: dict) -> "str | None":
    """Statusvermerk fuer den UserPromptSubmit-Hook, oder None.

    None heisst: nichts anhaengen — kein Workflow, Phase 8, oder State
    unbrauchbar. Der Vermerk ist die einzige Stelle, die Claude auch in frei
    formulierten Nachrichten NACH dem Ende einer Phase (Loop-Aufwachen,
    Zwischenfragen) daran erinnert, dass ein Pflicht-Schritt offen ist.
    Ein offener Auftrag (#551) haengt seinen Satz an (fail-open).
    """
    note = _status_note_base(data)
    if note is None:
        return None
    try:
        extra = auftrag_note_text(read_auftrag())
    except Exception:
        extra = ""
    return f"{note}\n{extra}" if extra else note


def _status_note_base(data: dict) -> "str | None":
    """Statusvermerk ohne Auftragssatz (siehe `status_note`)."""
    if not isinstance(data, dict):
        return None
    name = data.get("name")
    if not isinstance(name, str) or not name:
        return None
    phase = data.get("current_phase")
    if not isinstance(phase, str) or phase not in PHASE_NUMBERS:
        return None
    if phase == "phase8_complete":
        return None
    step = next_step(data)
    if not step:
        return None
    if step.startswith("/"):
        issue = workflow_issue_number(data)
        if issue:
            step = f"{step} #{issue}"
    if step == AUTO_APPROVAL_STEP:
        # Auto-Fall (#470): der PO muss nichts tippen — keine Du-Pflicht.
        return (
            f"{STATUS_NOTE_PREFIX} AKTIVER WORKFLOW {name} · "
            f"Phase {PHASE_NUMBERS[phase]} von {TOTAL_PHASES} ({phase}) · "
            f"Nächster Pflicht-Schritt: {step}\n"
            "Den Schritt führst du selbst aus (Auto-Modus, Ampel grün), ohne Du-Zeile; "
            "Fußzeile: „⏳ Läuft noch: Auto-Freigabe der Spec läuft. Du musst nichts "
            "tun, ich melde mich.“ Meldet `workflow.py auto-approve` "
            "AUTO_APPROVE=human, entscheidet der PO per Freigabe-Stichwort.\n"
            "„fertig“/„abgeschlossen“/„erledigt“ gilt für den Workflow erst ab "
            "phase8_complete."
        )
    return (
        f"{STATUS_NOTE_PREFIX} AKTIVER WORKFLOW {name} · "
        f"Phase {PHASE_NUMBERS[phase]} von {TOTAL_PHASES} ({phase}) · "
        f"Nächster Pflicht-Schritt: {step}\n"
        "Den Schritt als Pflicht nennen, nie „bei Bedarf“/„optional“; /clear- oder "
        "Kosten-Empfehlung nie darüber.\n"
        f"{END_STATE_RULE}\n"
        "Nach eigenem `workflow.py phase` gilt der neue Stand (`workflow.py status`); "
        "Marker-Zeilen entfallen nie.\n"
        "Emoji-Zeilen nur wie vorgeschrieben, keine eigene „ℹ️ Status“-Zeile.\n"
        "Workflow „fertig“/„abgeschlossen“/„erledigt“ erst ab phase8_complete."
    )


# Phases where user keywords ("approved", "go", "deployed") are expected.
# Switching away from these without updating OPENSPEC_ACTIVE_WORKFLOW causes
# the next keyword to land on the wrong workflow.
KEYWORD_SENSITIVE_PHASES = {"phase3_spec", "phase6_implement", "phase7_validate"}

VALID_ARTIFACT_TYPES = [
    "screenshot", "email", "api_response", "log", "file", "test_output", "video", "audio",
    "adversary_dialog",
]


def _workflows_dir() -> Path:
    return find_project_root() / ".claude" / "workflows"


# ANSI-Escape-Sequenzen (#492): OSC bis BEL/ST, CSI, sonstige ESC-Zwei-Zeichen-Folgen
_ANSI_RE = _re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-Z\\-_]?")


def short_title(title, max_words: int = 6) -> str:
    """Issue-Titel auf die ersten `max_words` Woerter kuerzen (#490). Pure.

    Entfernt ANSI-Sequenzen und nicht druckbare Zeichen; Leerraum (Zeilenumbruch,
    Tab) zaehlt als Wortgrenze (#492).
    """
    if not isinstance(title, str):
        return ""
    text = _ANSI_RE.sub("", title)
    text = "".join(ch if ch.isprintable() else (" " if ch.isspace() else "")
                   for ch in text)
    words = text.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]) + "…"
    return " ".join(words)


def _issue_titles_file() -> Path:
    """Cache der Issue-Kurztitel (#490): .claude/issue_titles.json."""
    return _workflows_dir().parent / "issue_titles.json"


def _read_issue_titles() -> dict:
    """Cache lesen; fehlend/kaputt gilt als leer. Wirft nie."""
    try:
        data = json.loads(_issue_titles_file().read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def cached_issue_title(issue) -> "str | None":
    """Kurztitel aus dem Cache oder None (#490). Wirft nie."""
    try:
        value = _read_issue_titles().get(str(issue))
        return value if isinstance(value, str) and value else None
    except Exception:
        return None


ISSUE_TITLE_LOG_MAX_LINES = 200


def _log_issue_title_failure(issue, reason: str) -> None:
    """Fehlschlag nach `.claude/issue_titles.log` (rotierend, #492). Wirft nie."""
    try:
        from hook_utils import atomic_write_text, read_state_text
        path = _issue_titles_file().with_name("issue_titles.log")
        root = path.parent.parent
        try:
            old = read_state_text(path, root).splitlines()
        except Exception:
            old = []
        line = short_title(f"#{issue} {reason}", max_words=40)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        lines = old[-(ISSUE_TITLE_LOG_MAX_LINES - 1):] + [f"{stamp} {line}"]
        atomic_write_text(path, "\n".join(lines) + "\n", root=root)
    except Exception:
        pass


def _store_issue_title(issue, title: str) -> None:
    """Eintrag unter `<cache>.lock` per Lesen-Aendern-Schreiben setzen (#492).

    Sperre wie `herdr_bridge._pp_flock` (max ~2 s, danach ohne Sperre weiter).
    """
    path = _issue_titles_file()
    fd = None
    try:
        import herdr_bridge
        fd = herdr_bridge._pp_flock(path)
    except Exception:
        fd = None
    try:
        cache = _read_issue_titles()
        cache[str(issue)] = title
        atomic_write_json(path, cache)
    finally:
        if fd is not None:
            os.close(fd)  # gibt die Sperre frei


# --- Issue-Kurzfassung (#612): Problem/Ziel aus dem Issue-Text fuer den Plan-Kopf ----

ISSUE_TITLE_MAX_WORDS = 24  # voller Titel im Plan-Kopf (umbrochen), statt 6 Woerter
BRIEF_MAX_CHARS = 260       # je Absatz Problem/Ziel, dann „…“
BRIEF_PROBLEM_WORDS = (
    "problem", "defekt", "fehler", "beschreibung", "description", "summary",
    "zusammenfassung", "kontext", "context", "motivation", "hintergrund", "background",
    "ist-zustand", "ist zustand", "aktuell", "symptom", "situation", "ausgangslage",
    "current behavior", "current behaviour", "beobachtung", "observed", "warum", "why",
)
BRIEF_GOAL_WORDS = (
    "ziel", "goal", "soll", "erwartet", "expected", "lösung", "loesung", "solution",
    "vorschlag", "proposal", "wunsch", "nutzen", "outcome", "ergebnis", "akzeptanz",
    "acceptance", "definition of done", "anforderung", "requirement", "job to be done",
)
_BRIEF_MD_HEADING_RE = _re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_BRIEF_BOLD_HEADING_RE = _re.compile(r"^\s*\*\*([^*\n]{1,60}?)\s*[:：]?\s*\*\*\s*[:：]?\s*(.*)$")
_BRIEF_KEY_LINE_RE = _re.compile(r"^\s*([A-Za-zÄÖÜäöüß][\w /&-]{0,40}?)\s*[:：]\s+(.*)$")
_BRIEF_LIST_RE = _re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?(.*)$")


def _brief_words(heading: str) -> "str | None":
    """'problem' / 'goal' / None je nach Ueberschrift (Wortlisten, case-insensitiv)."""
    low = " ".join(heading.lower().split())
    if any(w in low for w in BRIEF_PROBLEM_WORDS):
        return "problem"
    if any(w in low for w in BRIEF_GOAL_WORDS):
        return "goal"
    return None


def _brief_inline(text: str) -> str:
    """Markdown-Inline-Syntax entfernen: Bilder, Links (Text bleibt), HTML, Code, Fett."""
    text = _re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = _re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = _re.sub(r"<[^>\n]+>", "", text)
    text = _re.sub(r"`([^`]*)`", r"\1", text)
    text = _re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = _re.sub(r"__(.+?)__", r"\1", text)
    text = _re.sub(r"(?<!\w)[*_]([^*_\n]+)[*_](?!\w)", r"\1", text)
    text = _re.sub(r"^\s*>\s?", "", text)
    return " ".join(text.split())


def _brief_clamp(text: str, limit: int = BRIEF_MAX_CHARS) -> str:
    """Text an einer Wortgrenze auf `limit` Zeichen kuerzen, Ende „…“."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:.-") + "…"


def _brief_join(lines: "list[str]") -> str:
    """Abschnittszeilen zu einem Absatz: Listenpunkte mit „; “, sonst Leerzeichen."""
    parts: "list[str]" = []
    items: "list[str]" = []
    for raw in lines:
        if raw.lstrip().startswith("|") or _re.fullmatch(r"\s*[-=*_]{3,}\s*", raw):
            continue  # Tabellen und Trennlinien
        m = _BRIEF_LIST_RE.match(raw)
        text = _brief_inline(m.group(1) if m else raw)
        if not text:
            continue
        if m:
            items.append(text)
        else:
            if items:
                parts.append("; ".join(items))
                items = []
            parts.append(text)
    if items:
        parts.append("; ".join(items))
    return " ".join(parts)


def extract_issue_brief(title, body) -> dict:
    """Kurzfassung `{"title", "problem", "goal"}` aus Issue-Titel und -Text (#612). Pure.

    Entfernt HTML-Kommentare und Code-Bloecke, zerlegt den Text an Markdown-
    Ueberschriften, fetten Zeilen (`**Problem:**`) und `Schluessel:`-Zeilen
    (hoechstens drei Woerter, Schluessel aus den Wortlisten). „Problem“ ist der
    erste Abschnitt mit einer Problem-Ueberschrift, „Ziel“ der erste mit einer
    Ziel-Ueberschrift; ohne Problem-Treffer gilt der Einstieg vor der ersten
    Ueberschrift, ohne jede Ueberschrift der ganze Text. Jeder Wert hoechstens
    `BRIEF_MAX_CHARS` Zeichen (dann „…“).
    """
    out = {"title": short_title(title, max_words=ISSUE_TITLE_MAX_WORDS),
           "problem": "", "goal": ""}
    if not isinstance(body, str) or not body.strip():
        return out
    text = _re.sub(r"<!--.*?-->", "", body, flags=_re.DOTALL)
    text = _re.sub(r"(```|~~~).*?(\1|\Z)", "", text, flags=_re.DOTALL)
    sections: "list[tuple[str, list[str]]]" = [("", [])]
    for line in text.splitlines():
        m = _BRIEF_MD_HEADING_RE.match(line)
        if m:
            sections.append((m.group(1), []))
            continue
        m = _BRIEF_BOLD_HEADING_RE.match(line)
        if m and _brief_words(m.group(1)) is not None:
            sections.append((m.group(1), [m.group(2)] if m.group(2).strip() else []))
            continue
        m = _BRIEF_KEY_LINE_RE.match(line)
        if m and len(m.group(1).split()) <= 3 and _brief_words(m.group(1)) is not None:
            sections.append((m.group(1), [m.group(2)]))
            continue
        sections[-1][1].append(line)
    for heading, lines in sections:
        kind = _brief_words(heading) if heading else None
        if kind and not out[kind]:
            out[kind] = _brief_clamp(_brief_join(lines))
    if not out["problem"]:
        lead = _brief_join(sections[0][1])
        if not lead and len(sections) == 1:
            lead = ""
        out["problem"] = _brief_clamp(lead)
    return out


def _issue_briefs_file() -> Path:
    """Cache der Issue-Kurzfassungen (#612): .claude/issue_briefs.json."""
    return _workflows_dir().parent / "issue_briefs.json"


def _read_issue_briefs() -> dict:
    """Cache lesen; fehlend/kaputt gilt als leer. Wirft nie."""
    try:
        data = json.loads(_issue_briefs_file().read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def cached_issue_brief(issue) -> "dict | None":
    """Kurzfassung aus dem Cache (dict mit title/problem/goal/source) oder None."""
    try:
        value = _read_issue_briefs().get(str(issue))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _store_issue_brief(issue, brief: dict, replace_manual: bool = False) -> None:
    """Eintrag unter `<cache>.lock` setzen (#612). Eine manuelle Fassung bleibt,
    nur ihr Titel wird nachgezogen — ausser `replace_manual`."""
    path = _issue_briefs_file()
    fd = None
    try:
        import herdr_bridge
        fd = herdr_bridge._pp_flock(path)
    except Exception:
        fd = None
    try:
        cache = _read_issue_briefs()
        old = cache.get(str(issue))
        if (isinstance(old, dict) and old.get("source") == "manual"
                and brief.get("source") != "manual" and not replace_manual):
            old["title"] = brief.get("title") or old.get("title", "")
            cache[str(issue)] = old
        else:
            cache[str(issue)] = brief
        atomic_write_json(path, cache)
    finally:
        if fd is not None:
            os.close(fd)


def fetch_issue_title(issue, timeout: float = 8, replace_manual: bool = False) -> "str | None":
    """Titel und Text per `gh api` (REST, JSON) holen, Kurzfassung bilden, cachen
    (#490/#492/#612). Eine reine Textantwort zaehlt als Titel ohne Text.

    Fail-open: None, wirft nie; Fehlschlaege landen in `.claude/issue_titles.log`.
    """
    try:
        import shutil
        import subprocess
        if not str(issue).isdigit():
            return None
        gh = shutil.which("gh")
        if not gh:
            _log_issue_title_failure(issue, "gh nicht gefunden")
            return None
        try:
            res = subprocess.run(
                [gh, "api", f"repos/{{owner}}/{{repo}}/issues/{issue}"],
                capture_output=True, text=True, timeout=timeout,
                cwd=str(find_project_root()), stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            _log_issue_title_failure(issue, f"gh api Zeitlimit {timeout:g}s")
            return None
        if res.returncode != 0:
            _log_issue_title_failure(
                issue, f"gh api Exit {res.returncode}: {(res.stderr or '').strip()[:200]}")
            return None
        raw_title, body = res.stdout, ""
        try:
            payload = json.loads(res.stdout)
            if isinstance(payload, dict):
                raw_title = str(payload.get("title") or "")
                body = payload.get("body") or ""
        except ValueError:
            pass  # Textantwort (alter Stub): nur Titel
        title = short_title(raw_title, max_words=ISSUE_TITLE_MAX_WORDS)
        if not title:
            _log_issue_title_failure(issue, "gh api lieferte leeren Titel")
            return None
        _store_issue_title(issue, title)
        brief = extract_issue_brief(title, body if isinstance(body, str) else "")
        brief["source"] = "issue"
        brief["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _store_issue_brief(issue, brief, replace_manual=replace_manual)
        return title
    except Exception as exc:
        _log_issue_title_failure(issue, f"Fehler {type(exc).__name__}")
        return None


def _spawn_issue_title_fetch(issue: str) -> None:
    """`workflow.py issue-title N` abgekoppelt anstossen (#490). Wirft nie."""
    try:
        import subprocess
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "issue-title", str(issue)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
            cwd=str(find_project_root()),
        )
    except Exception:
        pass


def _active_link() -> Path:
    return _workflows_dir() / ".active"


def _workflow_file(name: str) -> Path:
    return _workflows_dir() / f"{name}.json"


def _archive_dir() -> Path:
    return _workflows_dir() / "_archive"


# Compatibility aliases for project hooks that used the old project-local workflow.py API
_get_workflows_root = _workflows_dir


def _archive_file(name: str) -> Path:
    return _archive_dir() / f"{name}.json"


def _read_workflow_file(path: "Path") -> dict:
    return _read_workflow(path)


def _active_name() -> "str | None":
    """Return active workflow name from env var, or None (non-fatal).

    Compatibility alias: old project-local workflow.py returned None instead
    of calling sys.exit(1) when no workflow was active.
    """
    name = _active_name_from_env()
    return name if name else None


def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically via tempfile + rename (hook_utils.atomic_write_json)."""
    atomic_write_json(path, data)


def _read_workflow(path: Path) -> dict:
    """State nur aus echter eigener Datei lesen (#416, wirft UnsafeStateError)."""
    return read_state_json(path, find_project_root())


def _active_name_from_env() -> str:
    """Return workflow name from OPENSPEC_ACTIVE_WORKFLOW env var, or empty string."""
    return os.environ.get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()


def _read_active() -> tuple[dict, str]:
    """Read the active workflow. Returns (data, name).

    Workflow-name resolution is delegated to hook_utils.resolve_active_workflow()
    — the single source of truth with worktree-aware priority (worktree-local
    active_workflow file > worktree settings.local.json > OPENSPEC_ACTIVE_WORKFLOW
    env var, each validated where applicable). This fixes the live bug (Issue #13)
    where the old FATAL path read the env var first and crashed when a stale env
    value pointed at a non-existent workflow, even though the worktree-local file
    and settings.local.json correctly pointed at a valid workflow.

    The resolved name is validated against the concrete workflows/<name>.json.
    The .active symlink fallback is intentionally removed (causes cross-session drift).
    """
    from hook_utils import resolve_active_workflow

    name, source = resolve_active_workflow()

    if name:
        wf_file = _workflow_file(name)
        if wf_file.exists():
            data = _read_workflow(wf_file)
            return data, data.get("name", wf_file.stem)
        print(
            f"FATAL: Resolved active workflow '{name}' (source={source}) but no "
            f"matching workflow file exists.\n"
            f"  The name may come from the worktree active_workflow file, "
            f"settings.local.json, or the OPENSPEC_ACTIVE_WORKFLOW env var.\n"
            f"  Run: python3 .claude/hooks/workflow.py list",
            file=sys.stderr,
        )
        sys.exit(1)

    # Symlink fallback is DISABLED. If a stale .active symlink exists, tell the user
    # what to do instead of silently using it — but ONLY if the target still
    # exists as an active workflow. After complete/abandon is "no active
    # workflow" the WANTED state (Issue #82): no FATAL, and never suggest
    # re-activating the workflow that was just archived.
    link = _active_link()
    if link.is_symlink():
        target = Path(os.readlink(str(link)))
        name = target.stem
        if _workflow_file(name).exists():
            print(
                f"No active workflow set.\n"
                f"  A .active symlink points to '{name}', but symlink fallback is disabled.\n"
                f"  Run: python3 .claude/hooks/workflow.py switch {name}",
                file=sys.stderr,
            )
            sys.exit(1)

    print("No active workflow. Run: python3 .claude/hooks/workflow.py start <name>", file=sys.stderr)
    sys.exit(1)


def read_active_workflow_fast() -> "tuple[str, dict] | None":
    """Return (name, data) for the active workflow, or None if no workflow is active.

    Unlike _read_active(), this never calls sys.exit(). Intended for hooks that
    should silently skip when no workflow is running.

    Thin wrapper around hook_utils.resolve_active_workflow() (the single source of
    truth for worktree-aware name resolution) plus the workflows/<name>.json
    existence check. Return contract is unchanged: (name, data) or None.
    """
    from hook_utils import resolve_active_workflow

    name, _source = resolve_active_workflow()
    if name:
        wf_file = _workflow_file(name)
        if wf_file.exists():
            data = _read_workflow(wf_file)
            return data.get("name", wf_file.stem), data
    return None


def write_qa_run_stamp(stamp: dict) -> bool:
    """Schreibt `qa_run_stamp` in den aktiven Workflow (#345). False = kein Workflow.

    Nur fuer qa_gate.py per Import. Bewusst KEIN CLI-Unterbefehl: der Stempel
    soll belegen, dass das Gate selbst gemessen hat — ein Befehl, der beliebiges
    JSON annimmt, liesse ihn per Bash faelschen (Sperre via _SET_FIELD_PROTECTED).
    #404 F003: Einstiegspunkt muss qa_gate.py sein, sonst PermissionError.
    #404 F001: Ort statt Name — nur das qa_gate.py neben dieser Datei zaehlt.
    """
    main_file = getattr(sys.modules.get("__main__"), "__file__", "") or ""
    expected = Path(__file__).resolve().parent / "qa_gate.py"
    if not main_file or Path(main_file).resolve() != expected:
        raise PermissionError(
            "qa_run_stamp: nur qa_gate.py --run darf den Stempel schreiben (#404)")
    found = read_active_workflow_fast()
    if found is None:
        return False
    name, data = found
    data.setdefault("name", name)
    data["qa_run_stamp"] = dict(stamp)
    _save_active(data)
    return True


QA_RUN_HINT = "Weg: python3 .claude/hooks/qa_gate.py --run (Testbefehl aus qa_gate.test_command)"


def _qa_gate_section() -> dict:
    """`qa_gate`-Abschnitt der Config; wirft bei einem Ladefehler (Aufrufer: fail-closed)."""
    from config_loader import load_config
    section = load_config().get("qa_gate") or {}
    return section if isinstance(section, dict) else {}


def qa_require_run() -> bool:
    """Schalter `qa_gate.require_run` (#404): nur ein ausdrueckliches true schaltet ein."""
    return _qa_gate_section().get("require_run") is True


def qa_run_stamp_problem(data: dict) -> "str | None":
    """EINZIGE Pruefstelle fuer `qa_run_stamp` (#404): None = passt oder Schalter aus.

    Aufgerufen vom Commit-Gate (bash_gate.py) und von _validate_transition
    (phase8_complete, damit auch `complete`). Sonst ein Klartext-Grund.
    """
    try:
        section = _qa_gate_section()
    except Exception as exc:
        return f"qa_gate-Config nicht lesbar ({type(exc).__name__}: {exc}) — {QA_RUN_HINT}"
    if section.get("require_run") is not True:
        return None
    cmd = section.get("test_command")
    if not isinstance(cmd, str) or not cmd.strip():
        return ("qa_gate.require_run ist an, aber kein qa_gate.test_command konfiguriert — "
                "Testbefehl in config.yaml setzen oder qa_gate.require_run ausschalten")
    stamp = data.get("qa_run_stamp")
    if not isinstance(stamp, dict):
        return f"kein qa_run_stamp — der Testlauf durch das QA-Gate fehlt. {QA_RUN_HINT}"
    reason = _stamp_reason(stamp, cmd, data)
    return f"qa_run_stamp ungültig — {reason}. {QA_RUN_HINT}" if reason else None


def _stamp_reason(stamp: dict, cmd: str, data: dict) -> "str | None":
    """Erster Befund am Stempel (Quelle, Exit-Code, Ausgabe, Testbefehl, Code-Stand)."""
    if stamp.get("source") != "run":
        return "Stempel stammt nicht aus `--run` (Datei-Modus zählt nicht)"
    code = stamp.get("exit_code")
    if type(code) is not int or code != 0:
        return f"roter Lauf (exit_code {code!r})"
    out_reason = _stamp_output_reason(stamp)
    if out_reason:
        return out_reason
    if stamp.get("command_sha256") != _hashlib.sha256(cmd.encode()).hexdigest():
        return "Testbefehl seit dem Lauf geändert (command_sha256 passt nicht zu qa_gate.test_command)"
    return _stamp_code_reason(stamp, data)


def _stamp_output_reason(stamp: dict) -> "str | None":
    """Ausgabedatei: im Projekt, kein Symlink, Inhalt = output_sha256."""
    from hook_utils import find_worktree_root
    raw = stamp.get("output_path")
    if not isinstance(raw, str) or not raw:
        return "Ausgabedatei (output_path) fehlt im Stempel"
    path = Path(raw)
    root = os.path.realpath(find_worktree_root() or find_project_root())
    real = os.path.realpath(path)
    if not path.is_absolute() or os.path.commonpath([root, real]) != root:
        return f"Ausgabedatei {raw} liegt außerhalb des Projekts"
    if path.is_symlink() or not path.is_file():
        return f"Ausgabedatei {raw} fehlt oder ist ein Symlink"
    try:
        digest = _hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        return f"Ausgabedatei {raw} nicht lesbar ({exc})"
    if digest != stamp.get("output_sha256"):
        return f"Ausgabedatei {raw} nach dem Lauf verändert (output_sha256 passt nicht)"
    return None


def _stamp_code_reason(stamp: dict, data: dict) -> "str | None":
    """Code-Stand: code_sha256 = change_set_hash; ohne git Stempelzeit >= neueste mtime."""
    try:
        import adversary_dialog as ad
        current = ad.change_set_hash(data)
    except Exception as exc:  # ChangeSetError & Co.: fail-closed
        return f"Code-Stand nicht ermittelbar ({type(exc).__name__}: {exc})"
    if current is not None:
        if stamp.get("code_sha256") != current:
            return "Code seit dem Lauf geändert (code_sha256 passt nicht zum aktuellen Stand)"
        return None
    try:
        stamped = datetime.fromisoformat(str(stamp.get("timestamp"))).timestamp()
    except (TypeError, ValueError):
        return "Stempel ohne gültigen Zeitstempel (ohne git nötig für code_sha256-Ersatz)"
    if _newest_code_mtime() > stamped:
        return "Code seit dem Lauf geändert (ohne git: Code-Datei neuer als der Stempel, code_sha256 fehlt)"
    return None


def _newest_code_mtime() -> float:
    """Neueste mtime aller Code-Dateien im Projekt (Ersatz ohne git, #404)."""
    from config_loader import load_config
    from hook_utils import find_worktree_root, is_gated_code_path
    root = find_worktree_root() or find_project_root()
    config, newest = load_config(), 0.0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "node_modules"]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if is_gated_code_path(os.path.relpath(full, root), config):
                try:
                    newest = max(newest, os.stat(full).st_mtime)
                except OSError:
                    pass
    return newest


def _set_active(name: str) -> None:
    """Set .active symlink and persist OPENSPEC_ACTIVE_WORKFLOW in settings.local.json.

    Hook subprocesses inherit Claude Code's process environment, not individual Bash
    exports. Writing to settings.local.json ensures all hooks see the correct workflow.
    """
    link = _active_link()
    target = f"{name}.json"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    os.symlink(target, str(link))
    _persist_env(name)


def _persist_env(name: "str | None") -> None:
    """Write (or remove) OPENSPEC_ACTIVE_WORKFLOW to session-local storage.

    Worktree-aware: when called from a worktree session, writes ONLY to the worktree's
    own .claude/settings.local.json and active_workflow file. This prevents one session's
    workflow from contaminating new sessions that open in the main repo — each session
    starts with a clean slate and only inherits workflows from its own worktree.

    When called from the main repo (not a worktree), writes to the main repo's
    settings.local.json (backward compat for single-session projects).

    On completion (name=None) from a worktree: also clears the main repo's settings to
    avoid stale state if the main settings.local.json was set before isolation was in place.
    """
    project_root = find_project_root()
    worktree_root = _worktree_root_if_any()

    if worktree_root is not None:
        # Worktree session: write ONLY to this worktree's own .claude/
        targets = [worktree_root / ".claude" / "settings.local.json"]
        active_file = worktree_root / ".claude" / "active_workflow"

        if not name:
            # On complete: also clear the shared main repo locations so future
            # main-repo sessions start clean (handles pre-isolation contamination).
            _clear_shared_env(project_root)
    else:
        # Main repo: write to main locations (single-session backward compat)
        targets = [project_root / ".claude" / "settings.local.json"]
        active_file = project_root / ".claude" / "active_workflow"

    for settings_path in targets:
        try:
            settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
        except (json.JSONDecodeError, OSError):
            settings = {}

        env = settings.setdefault("env", {})
        if name:
            env["OPENSPEC_ACTIVE_WORKFLOW"] = name
        else:
            env.pop("OPENSPEC_ACTIVE_WORKFLOW", None)
            if not env:
                settings.pop("env", None)

        settings_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(settings_path, settings)

    if name:
        active_file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(active_file.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(name)
            os.rename(tmp, str(active_file))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    else:
        try:
            active_file.unlink(missing_ok=True)
        except OSError:
            pass


def _clear_shared_env(project_root: Path) -> None:
    """Remove OPENSPEC_ACTIVE_WORKFLOW from the main repo's shared locations.

    Called by _persist_env(None) from a worktree to ensure cleanup propagates
    to the main repo's settings.local.json (handles pre-isolation contamination).
    """
    settings_path = project_root / ".claude" / "settings.local.json"
    try:
        settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
        env = settings.get("env", {})
        if "OPENSPEC_ACTIVE_WORKFLOW" in env:
            env.pop("OPENSPEC_ACTIVE_WORKFLOW")
            if not env:
                settings.pop("env", None)
            _atomic_write(settings_path, settings)
    except (OSError, json.JSONDecodeError):
        pass
    active_file = project_root / ".claude" / "active_workflow"
    try:
        active_file.unlink(missing_ok=True)
    except OSError:
        pass


def _herdr(action: str, data: "dict | None" = None) -> None:
    """Herdr-Sidebar aktualisieren (#466) — display-only, fail-open, nie stdout."""
    try:
        import herdr_bridge
        if action == "clear":
            herdr_bridge.clear()
        else:
            herdr_bridge.report_workflow(data)
    except Exception:
        pass


def _save_active(data: dict) -> None:
    name = data["name"]
    data["last_updated"] = datetime.now().isoformat()
    _atomic_write(_workflow_file(name), data)
    _herdr("report", data)


def _new_workflow(name: str) -> dict:
    return {
        "name": name,
        "workflow_type": "feature",
        "current_phase": "phase1_context",
        "created": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
        "spec_file": None,
        "spec_approved": False,
        "context_file": None,
        "affected_files": [],
        "test_artifacts": [],
        "is_new_ui": False,
        "red_test_done": False,
        "ui_test_red_done": False,
        "green_approved": False,
        "adversary_verdict": None,
        "phase_transitions": [],
        "fix_loop_iterations": 0,
        "phase_log": [],
        "approvals": [],
    }


def trusted_config() -> "dict | None":
    """Die EINE Config-Quelle fuer Autonomie-Entscheidungen (#470, Ursachen-Fix F008).

    Wurzel = `hook_utils.find_project_root()` — dieselbe Funktion, mit der
    `bash_gate.py::_writes_effective_config` die wirksame Config schreibschuetzt
    und unter der der Workflow-State liegt. Datei =
    `config_loader.find_config_file(<diese Wurzel>)`. Gelesen wird NUR das YAML
    dieser Datei: keine Defaults, keine Local-Overrides (`settings.local.json`),
    kein `config_loader.find_project_root()` (das haelt bei einer Unterordner-
    Config an, F008). Fehlende Datei → {}. Jeder Fehler → None; Aufrufer sind
    fail-closed (manual bzw. human). Wirft nie.
    """
    try:
        import config_loader
        path = config_loader.find_config_file(find_project_root())
        if path is None:
            return {}
        if config_loader.yaml is None:
            return None
        loaded = config_loader.yaml.safe_load(Path(path).read_text())
        if loaded is None:
            return {}
        return loaded if isinstance(loaded, dict) else None
    except Exception:
        return None


def autonomy_mode() -> str:
    """Aktueller Autonomie-Modus: "auto" nur bei exakt `autonomy.mode: auto` (#469).

    Fail-closed: jeder andere Wert, falscher Typ und jede Ausnahme ergibt
    "manual". Kein Trimmen, kein Lowercase. Wirft nie. Gelesen wird seit #470
    nur ueber `trusted_config()` (zur Laufzeit aufgeloest), nie
    `settings.local.json` und nie eine Unterordner-Config.

    #481: Hat die Projekt-Config keinen `autonomy.mode`, entscheidet die
    benutzerweite Variable `OPENSPEC_AUTONOMY` (getrimmt, ohne Gross/Klein:
    nur "auto" schaltet an). Ein Projekteintrag hat immer Vorrang.
    """
    try:
        cfg = trusted_config()
        if not isinstance(cfg, dict):
            return "manual"
        section = cfg.get("autonomy")
        if isinstance(section, dict) and "mode" in section:
            return "auto" if section.get("mode") == "auto" else "manual"
        if os.environ.get("OPENSPEC_AUTONOMY", "").strip().lower() == "auto":
            return "auto"
    except Exception:
        pass
    return "manual"


def auto_ship_enabled() -> bool:
    """Liefert Claude im Auto-Modus selbst aus (PR → CI → Merge)? (#525).

    True nur bei `autonomy_mode() == "auto"` UND wenn `autonomy.ship` in
    `trusted_config()` nicht ausdruecklich `False` ist. Nur ein echtes `False`
    schaltet ab; fehlender Schluessel, andere Werte (auch String "false") und
    eine unlesbare Config lassen den Schalter im Auto-Modus an. Nie
    `settings.local.json`. Wirft nie.
    """
    try:
        if autonomy_mode() != "auto":
            return False
        cfg = trusted_config()
        section = cfg.get("autonomy") if isinstance(cfg, dict) else None
        return not (isinstance(section, dict) and section.get("ship") is False)
    except Exception:
        return False


def record_approval(data: dict, gate: str, by: str, reason: str,
                    evidence=None) -> dict:
    """Freigabe an `data["approvals"]` anhaengen und den Eintrag zurueckgeben (#469).

    Speichert nicht selbst — der Aufrufer ruft wie bisher `_save_active`.
    Aeltere States ohne `approvals` bekommen die Liste per setdefault.
    """
    entry = {
        "gate": gate,
        "by": by,
        "mode": autonomy_mode(),
        "at": datetime.now().isoformat(),
        "reason": reason,
        "evidence": evidence,
    }
    data.setdefault("approvals", []).append(entry)
    return entry


def _log_phase_transition(data: dict, new_phase: str) -> None:
    """Record phase transition timestamp in phase_log.

    Call BEFORE setting data['current_phase']. Closes the current log entry
    (sets exited_at + duration_min) and opens a new one for new_phase.
    """
    now = datetime.now().isoformat()
    log = data.setdefault("phase_log", [])
    if log:
        last = log[-1]
        if last.get("exited_at") is None:
            last["exited_at"] = now
            try:
                entered = datetime.fromisoformat(last["entered_at"])
                exited = datetime.fromisoformat(now)
                last["duration_min"] = round((exited - entered).total_seconds() / 60, 1)
            except (ValueError, KeyError):
                pass
    log.append({"phase": new_phase, "entered_at": now, "exited_at": None, "duration_min": None})


def effort_budget_exceeded(data: dict, budget: "dict | None") -> list:
    """Ueberschrittene Metriken des Stufen-Budgets (Issue #250, Teil B). Reine Funktion.

    `fix_loops` = `fix_loop_iterations`; `phase_reentries` = hoechster Wiedereintritts-
    zaehler je Phase (Eintraege in `phase_transitions` mit `to == Phase`, minus 1).
    Ueberschritten heisst strikt groesser als die Grenze.
    """
    if not budget:
        return []
    entries: dict = {}
    for t in data.get("phase_transitions", []) or []:
        to = t.get("to") if isinstance(t, dict) else None
        if to:
            entries[to] = entries.get(to, 0) + 1
    values = {
        "fix_loops": int(data.get("fix_loop_iterations", 0) or 0),
        "phase_reentries": max([n - 1 for n in entries.values()] or [0]),
    }
    exceeded = []
    for metric, key in (("fix_loops", "max_fix_loops"), ("phase_reentries", "max_phase_reentries")):
        limit = budget.get(key)
        if isinstance(limit, int) and values[metric] > limit:
            exceeded.append({"metric": metric, "value": values[metric], "limit": limit})
    return exceeded


def _record_budget_events(data: dict) -> list:
    """Neue Budget-Ueberschreitungen (je Metrik+Wert einmal) ablegen und protokollieren."""
    try:
        from config_loader import get_effort_budget
        stage = data.get("workflow_type") or "feature"
        exceeded = effort_budget_exceeded(data, get_effort_budget(stage))
    except Exception:
        return []  # Budget darf einen Phasenwechsel nie stoeren
    known = {(e.get("metric"), e.get("value")) for e in data.get("budget_events", [])}
    new = [e for e in exceeded if (e["metric"], e["value"]) not in known]
    for event in new:
        event["stage"] = stage
        event["at"] = datetime.now().isoformat()
        data.setdefault("budget_events", []).append(event)
        try:
            from hook_utils import log_gate_event
            log_gate_event(
                "effort_budget", "workflow",
                f"Stufe {stage}: {event['metric']} {event['value']} > Grenze {event['limit']}",
            )
        except Exception:
            pass
    return new


def record_transition(data: dict, target: str, trigger: str = "command") -> list:
    """Einen Phasenwechsel vollstaendig protokollieren: `phase_transitions` UND `phase_log`.

    Die EINZIGE Stelle, die einen Phasen-WECHSEL aufzeichnet — jeder Aufrufer muss sie
    benutzen (Issue #111). Ausnahme ist `cmd_start`: die Startphase wird nicht betreten,
    sie ist der Ausgangspunkt und hat kein `from`; dort ist der direkte
    `_log_phase_transition()`-Aufruf korrekt.

    Vorher haengte nur `cmd_phase` an `phase_transitions` an, waehrend der Freigabe-Pfad im
    `phase_listener` ausschliesslich `_log_phase_transition()` rief. `phase_transitions` war
    dadurch je nach Uebergangsart unterschiedlich vollstaendig.

    Aufruf BEVOR `data['current_phase']` gesetzt wird — die Ausgangsphase wird von hier
    gelesen. Setzt `current_phase` bewusst NICHT selbst, damit Aufrufer mit Zusatzlogik
    (Fix-Loop-Zaehler, Gate-Pruefungen) die Reihenfolge behalten.

    Gibt neue Ueberschreitungen des Stufen-Budgets zurueck (Issue #250, Teil B); der
    Wechsel wird dadurch nie verweigert.
    """
    data.setdefault("phase_transitions", []).append({
        "from": data.get("current_phase", "phase0_idle"),
        "to": target,
        "at": datetime.now().isoformat(),
        "trigger": trigger,
    })
    _log_phase_transition(data, target)
    data.pop("waiting_on", None)  # #550: kein veralteter Wartezustand nach dem Wechsel
    if target in PHASES and PHASES.index(target) >= PHASES.index("phase4_approved"):
        # #647: Freigabe auf jedem Weg (cmd_phase, phase_listener, Auto) beendet die
        # Nacharbeit; ein Ruecksprung setzt das Flag vorher und zielt unter phase4.
        data.pop("spec_rework", None)
    return _record_budget_events(data)


# --- ADR Reflection Gate ---

def _check_adr(data: dict, config: "dict | None" = None) -> "str | None":
    """Enforce a filled '## Architektur-Entscheidung (ADR)' section at spec approval.

    Returns an error message if the spec has an ADR section that is not filled
    (no ADR number and no justified 'keine'/'none'), otherwise None. Lenient by
    design: the hook must never break — missing config, missing/unreadable spec,
    or a missing ADR section all return None (grandfathering).
    """
    # 1. Kill-switch — only an explicit enabled: False disables the gate.
    #    `config` von aussen (auto-approve, #470 F001): nur die wirksame Config,
    #    nie settings.local.json. Ohne Angabe wie bisher load_config().
    try:
        if config is None:
            from config_loader import load_config
            config = load_config()
        adr_cfg = config.get("adr_gate", {}) if isinstance(config, dict) else {}
        if isinstance(adr_cfg, dict) and adr_cfg.get("enabled") is False:
            return None
    except Exception:
        pass  # Config load failure → feature stays ON (lenient)

    # 2. Spec path
    spec_file = data.get("spec_file")
    if not spec_file:
        return None
    spec_path = _worktree_first_path(spec_file)

    # 3. Read
    try:
        content = spec_path.read_text()
    except Exception:
        return None

    return check_adr_content(content)


def check_adr_content(content: str) -> "str | None":
    """Prüft den Spec-TEXT auf eine ausgefüllte ADR-Sektion. Meldung oder None.

    Aus `_check_adr` herausgelöst, damit das CI-Gate (scripts/ci_spec_gate.py)
    exakt dieselbe Regel anwendet wie der lokale Hook — eine Regel, zwei Aufrufer.
    Grandfathering (keine ADR-Sektion → None) bleibt Teil dieser Funktion.
    """
    # 4. Extract the ADR section body (case-insensitive heading match).
    #    Accept ## or ### headings; body reaches up to the next heading of ANY
    #    rank 1-3 (#, ## or ###) or end of file. The end-lookahead must stop at
    #    #-level H1 too, otherwise an unrelated '**ADR-Nr.:**' line under a later
    #    H1 heading (e.g. '# Anhang') leaks into the section and falsely passes
    #    the gate even though the real ADR section is empty (F003).
    match = _re.search(
        r"^#{2,3}\s*Architektur-Entscheidung\s*\(ADR\)\s*$(.*?)(?=^#{1,3}\s|\Z)",
        content,
        _re.IGNORECASE | _re.MULTILINE | _re.DOTALL,
    )
    if not match:
        return None  # Grandfathering: no ADR section → not blocked
    body = match.group(1)

    # 5. Extract ONLY the value of the '**ADR-Nr.:**' bullet line (tolerate small
    #    format variants: bullet/dash optional, colon inside or outside the **).
    #    Intra-line whitespace only ([ \t]*, never \s*): a \s* after the closing
    #    ** would eat the newline and capture the following Rationale line when the
    #    value is empty (F001).
    nr_match = _re.search(
        r"(?im)^[ \t]*[-*]?[ \t]*\*\*[ \t]*ADR-Nr\.?[ \t]*:?[ \t]*\*\*[ \t]*:?[ \t]*(.*)$",
        body,
    )
    if not nr_match:
        # Section present but without the canonical '**ADR-Nr.:**' field →
        # treat as not filled (the canonical template always emits this line).
        return (
            "Spec ohne ausgefülltes ADR-Feld — Sektion "
            "'## Architektur-Entscheidung (ADR)' braucht ADR-Nr. oder begründetes 'keine'."
        )
    value = nr_match.group(1)

    # 6. Strip bracket placeholders from the value, then apply the criterion ONLY
    #    to that value (never to the free-form Rationale prose).
    v = _re.sub(r"\[[^\]]*\]", "", value).lower()
    if _re.search(r"adr-\d+", v) or _re.search(r"\bkeine\b|\bnone\b", v):
        return None

    # 7. Not filled
    return (
        "Spec ohne ausgefülltes ADR-Feld — Sektion "
        "'## Architektur-Entscheidung (ADR)' braucht ADR-Nr. oder begründetes 'keine'."
    )


# --- PO-Briefing-Gate (unabhängiges Freigabe-Briefing vor Phase 4) ---------

# Pflicht-Abschnitte des Briefings. Die Freigabe-Frage "passt das so?" ist nur
# beantwortbar, wenn alle vier beantwortet sind — was gebaut wird, wann es
# fertig ist, wie das geprüft wird, und was daran fragwürdig ist.
# Je Eintrag: (kanonischer Name für Meldungen, Regex für die Überschrift).
# Umlaute bewusst tolerant ('geprüft'/'geprueft'): ein Gate, das an der
# Schreibweise eines Umlauts scheitert, blockt den Nutzer aus einem Grund, der
# mit der Sache nichts zu tun hat.
PO_BRIEFING_SECTIONS = (
    ("Was gebaut wird", r"Was\s+gebaut\s+wird"),
    ("Definition of Done", r"(?:Definition\s+of\s+Done|DoD)"),
    ("Wie geprüft wird", r"Wie\s+gepr(?:ü|ue)ft\s+wird"),
    ("Kritische Anmerkungen", r"Kritische\s+Anmerkungen"),
)

# Mindest-Textlänge je Abschnitt (Zeichen, ohne Rahmen). Ein Abschnitt darunter
# ist eine Überschrift ohne Aussage.
_PO_BRIEFING_MIN_BODY = 20

# Die EINE Platzhalter-Liste (#521) fuer Spec und Briefing; das CI-Gate nutzt
# sie ueber `check_spec_content`. Kleingeschrieben, Pruefung case-insensitive
# und rein textuell: auch zitierte Zeilen zaehlen.
PLACEHOLDER_MARKERS = ("[todo", "[tbd", "todo:", "fixme:", "xxx:", "<platzhalter")


def find_placeholder(content: str) -> "str | None":
    """Erster Marker aus PLACEHOLDER_MARKERS (Listen-Reihenfolge) im Text oder None."""
    lowered = content.lower()
    for marker in PLACEHOLDER_MARKERS:
        if marker in lowered:
            return marker
    return None

# Obergrenze für die Wortzahl (Pflicht-Abschnitte + Freigabe-Frage). Der
# po-briefer zielt auf ≤ 120 Wörter; 150 lässt Puffer, damit das Gate nicht an
# einem Wort zu viel scheitert. Konfigurierbar: po_briefing_gate.max_words.
_PO_BRIEFING_MAX_WORDS = 150

# Optionaler Abschnitt, der mitgezählt wird, wenn vorhanden. Fehlt er, zählt er
# 0 Wörter — Vollständigkeit prüfen die Pflicht-Abschnitte, nicht dieser.
_PO_BRIEFING_QUESTION = r"Freigabe-?\s*Frage"


def spec_sha256(content: str) -> str:
    """SHA-256 des Spec-Inhalts — bindet ein Briefing an genau diese Spec-Fassung."""
    return _hashlib.sha256(content.encode("utf-8")).hexdigest()


# Teil-Hash nur ueber den freigegebenen Teil (#439). Eine Quelle (hook_utils),
# hier re-exportiert: das CI-Gate ruft `workflow.frozen_spec_sha256` per
# getattr auf und faellt bei aelteren Kopien auf den Byte-Gesamt-Hash zurueck.
from hook_utils import frozen_spec_sha256  # noqa: E402,F401


def _read_spec_content(data: dict) -> "str | None":
    spec_file = data.get("spec_file")
    if not spec_file:
        return None
    try:
        return _worktree_first_path(spec_file).read_text()
    except Exception:
        return None


def _briefing_section_body(content: str, pattern: str) -> "str | None":
    """Rohtext eines Briefing-Abschnitts oder None, wenn die Überschrift fehlt.

    Überschrift ## oder ###, Zusatztext dahinter erlaubt ("## Definition of
    Done (DoD)"). Body reicht bis zur nächsten Überschrift Rang 1-3 oder EOF.
    """
    match = _re.search(
        r"^#{2,3}\s*" + pattern + r"[^\n]*$(.*?)(?=^#{1,3}\s|\Z)",
        content,
        _re.IGNORECASE | _re.MULTILINE | _re.DOTALL,
    )
    return match.group(1) if match else None


def count_briefing_words(content: str) -> int:
    """Wörter in den Pflicht-Abschnitten + Freigabe-Frage (falls vorhanden).

    Titel, Meta-Zeilen (Spec/Issue/Datum) und Frontmatter zählen nicht — der
    PO liest sie nicht als Inhalt. Als Wort gilt jedes Leerzeichen-getrennte
    Token mit mindestens einem Buchstaben oder einer Ziffer; Aufzählungszeichen
    und Gedankenstriche zählen also nicht.
    """
    patterns = [pattern for _, pattern in PO_BRIEFING_SECTIONS] + [_PO_BRIEFING_QUESTION]
    total = 0
    for pattern in patterns:
        body = _briefing_section_body(content, pattern)
        if body:
            total += sum(1 for tok in body.split() if _re.search(r"\w", tok))
    return total


def check_briefing_content(content: str, max_words: "int | None" = None) -> "str | None":
    """Prüft den Briefing-TEXT auf Vollständigkeit und Länge. Fehlermeldung oder None.

    Bewusst rein textuell und ohne Workflow-Bezug, damit `set-briefing` (bei der
    Registrierung) und das Gate (bei der Freigabe) exakt dasselbe prüfen.
    `max_words` kommt von konfigurationskundigen Aufrufern
    (po_briefing_gate.max_words); ohne Angabe gilt `_PO_BRIEFING_MAX_WORDS`.
    """
    marker = find_placeholder(content)
    if marker:
        return f"PO-Briefing enthält noch einen Platzhalter ('{marker}') — nicht fertig."

    for section, pattern in PO_BRIEFING_SECTIONS:
        raw = _briefing_section_body(content, pattern)
        if raw is None:
            return f"PO-Briefing ohne Abschnitt '## {section}'."
        body = _re.sub(r"[\s\-*>]+", " ", raw).strip()
        if len(body) < _PO_BRIEFING_MIN_BODY:
            return f"PO-Briefing: Abschnitt '## {section}' ist leer bzw. zu dünn."

    limit = _PO_BRIEFING_MAX_WORDS if max_words is None else max_words
    words = count_briefing_words(content)
    if words > limit:
        return (
            f"Briefing zu lang ({words} Wörter, max {limit}) — "
            "po-briefer erneut dispatchen."
        )

    return None


_AMPEL_GREEN = ("gruen", "grün", "green")

_FENCE_OPEN_RE = _re.compile(r"^[ \t>]*(`{3,}|~{3,})")
# Markdown-Markup am Zeilenanfang: Einrueckung, Zitat, Listenpraefix, Ueberschrift,
# Hervorhebung. Danach beginnt eine Ampel-Zeile mit "Ampel" (+ Markup) ":".
_AMPEL_MARKUP_PREFIX_RE = _re.compile(r"^(?:[ \t>#_*+-]|\d+[.)][ \t])*")
_AMPEL_LINE_RE = _re.compile(r"^Ampel[ \t*_]*:", _re.IGNORECASE)


def _strip_hidden_markdown(text: str) -> str:
    """Code-Fences (``` / ~~~) und HTML-Kommentare samt Inhalt entfernen (#470 F004).

    Auch ungeschlossen bis Dateiende: ein offener Fence/Kommentar verbirgt alles
    dahinter. Zeilenweise; Kommentare duerfen inline und mehrzeilig sein.
    """
    out = []
    fence = None          # (zeichen, laenge) des offenen Fence
    in_comment = False
    for line in text.splitlines():
        if fence is not None:
            m = _FENCE_OPEN_RE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                    and not line[m.end():].strip():
                fence = None
            continue
        kept = ""
        rest = line
        while rest:
            if in_comment:
                end = rest.find("-->")
                if end < 0:
                    rest = ""
                    break
                rest = rest[end + 3:]
                in_comment = False
                continue
            start = rest.find("<!--")
            if start < 0:
                kept += rest
                break
            kept += rest[:start]
            rest = rest[start + 4:]
            in_comment = True
        if not in_comment or kept.strip():
            m = _FENCE_OPEN_RE.match(kept)
            if m:
                fence = (m.group(1)[0], len(m.group(1)))
                continue
        out.append(kept)
    return "\n".join(out)


def _is_ampel_line(line: str) -> bool:
    """Zeile, die nach Entfernen von Markdown-Markup mit `Ampel:` beginnt (F004)."""
    stripped = _AMPEL_MARKUP_PREFIX_RE.sub("", line, count=1)
    return bool(_AMPEL_LINE_RE.match(stripped))


def parse_ampel(text) -> str:
    """Ampel des PO-Briefings: "green" oder "red" (#470). Wirft nie.

    Vorab werden Code-Fences und HTML-Kommentare entfernt (auch ungeschlossen):
    was gerendert nicht sichtbar ist, zaehlt nicht (F004).
    Gruen NUR, wenn es genau einen Abschnitt `## Ampel` gibt, dieser genau eine
    nicht-leere Zeile `Ampel: <wert>` enthaelt, im ganzen Text genau eine
    Ampel-Zeile steht (auch `**Ampel: x**`, `- Ampel: x`, `> Ampel: x` zaehlen)
    und `<wert>` (getrimmt, case-insensitiv) gruen/grün/green ist. Alles andere —
    rot, fehlend, doppelt, mehrzeilig, unklar — ist "red".
    """
    try:
        if not isinstance(text, str):
            return "red"
        import unicodedata
        text = _strip_hidden_markdown(unicodedata.normalize("NFC", text))
        heads = _re.findall(r"^#{2,3}[ \t]*Ampel\b[^\n]*$", text,
                            _re.IGNORECASE | _re.MULTILINE)
        if len(heads) != 1:
            return "red"
        if sum(1 for line in text.splitlines() if _is_ampel_line(line)) != 1:
            return "red"
        body = _briefing_section_body(text, r"Ampel\b")
        if body is None:
            return "red"
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if len(lines) != 1:
            return "red"
        match = _re.fullmatch(r"Ampel[ \t]*:(.*)", lines[0], _re.IGNORECASE)
        if not match:
            return "red"
        return "green" if match.group(1).strip().lower() in _AMPEL_GREEN else "red"
    except Exception:
        return "red"


def po_briefing_max_words(cfg: "dict | None" = None) -> int:
    """Konfigurierte Wortgrenze (po_briefing_gate.max_words) oder Default.

    Lenient: fehlende/kaputte Konfiguration oder ein unbrauchbarer Wert → Default.
    """
    if cfg is None:
        try:
            from config_loader import load_config
            config = load_config()
            cfg = config.get("po_briefing_gate", {}) if isinstance(config, dict) else {}
        except Exception:
            cfg = {}
    value = cfg.get("max_words") if isinstance(cfg, dict) else None
    if isinstance(value, bool):
        return _PO_BRIEFING_MAX_WORDS
    try:
        value = int(value)
    except (TypeError, ValueError):
        return _PO_BRIEFING_MAX_WORDS
    return value if value > 0 else _PO_BRIEFING_MAX_WORDS


def parse_briefing_frontmatter(content: str) -> dict:
    """Liest den YAML-Frontmatter-Block eines Briefings als flaches dict.

    Bewusst ein Mini-Parser statt PyYAML: Das CI-Gate soll ohne zusätzliche
    Abhängigkeit laufen, und der Block enthält nur `key: value`-Zeilen.
    """
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end < 0:
        return {}
    out = {}
    for line in content[3:end].splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


def stamp_briefing_frontmatter(content: str, spec_rel: str, sha: str,
                               frozen_sha: "str | None" = None) -> str:
    """Schreibe `spec_file`/`spec_sha256` (und ggf. `spec_frozen_sha256`, #439)
    in den Frontmatter des Briefings.

    Vorhandener Frontmatter wird ergänzt bzw. der alte Stempel ersetzt (nie
    gedoppelt); fehlt er, wird einer vorangestellt. Der übrige Inhalt bleibt
    unangetastet.
    """
    stamp = {"spec_file": spec_rel, "spec_sha256": sha}
    if frozen_sha:
        stamp["spec_frozen_sha256"] = frozen_sha
    replaced = set(stamp) | {"spec_frozen_sha256"}
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end >= 0:
            head = content[3:end]
            rest = content[end + 4:]
            kept = [
                line for line in head.splitlines()
                if line.partition(":")[0].strip() not in replaced
            ]
            lines = [l for l in kept if l.strip()] + [f"{k}: {v}" for k, v in stamp.items()]
            return "---\n" + "\n".join(lines) + "\n---" + rest
    front = "\n".join(f"{k}: {v}" for k, v in stamp.items())
    return f"---\n{front}\n---\n\n{content.lstrip()}"


def _check_po_briefing(data: dict, config: "dict | None" = None) -> "str | None":
    """Enforce an independent PO briefing at spec approval (Phase 3→4).

    Returns an error message if no current, complete briefing is registered,
    otherwise None. Lenient in the same spirit as `_check_adr`: missing config,
    missing/unreadable spec or a disabled gate all return None.
    """
    # 1. Kill-switch — only an explicit enabled: False disables the gate.
    #    `config` von aussen (auto-approve, #470 F002): nur die wirksame Config,
    #    nie settings.local.json. Ohne Angabe wie bisher load_config().
    cfg = {}
    try:
        if config is None:
            from config_loader import load_config
            config = load_config()
        if isinstance(config, dict):
            cfg = config.get("po_briefing_gate", {}) or {}
        if isinstance(cfg, dict) and cfg.get("enabled") is False:
            return None
    except Exception:
        cfg = {}  # Config load failure → feature stays ON (lenient)

    # 2. Fast-Track: per Default kein Briefing (dort gibt es weder spec-writer
    #    noch Validator-Agenten). Abschaltbar via skip_fast_track: false.
    #    Im Auto-Modus gilt die Ausnahme nicht: das Briefing traegt die Ampel,
    #    ohne Briefing keine Freigabe-Grundlage (#470).
    skip_fast = True
    if isinstance(cfg, dict) and cfg.get("skip_fast_track") is False:
        skip_fast = False
    if skip_fast and autonomy_mode() == "auto":
        skip_fast = False
    if skip_fast and data.get("workflow_type") == "feature-fast":
        return None

    # 3. Ohne Spec kein Briefing-Gate (ein anderes Gate greift dann zuerst).
    spec_content = _read_spec_content(data)
    if spec_content is None:
        return None

    hint = (
        " → po-briefer-Agent laufen lassen (/30-write-spec Step 3b), "
        "danach: workflow.py set-briefing <pfad>"
    )

    # 4. Registrierung im State
    entry = data.get("po_briefing")
    if not isinstance(entry, dict) or not entry.get("file"):
        return "Kein unabhängiges PO-Briefing registriert" + hint
    # F010: nur regulaere Datei ≤ 256 KiB (kein FIFO/Device — sonst haengt die Freigabe).
    try:
        briefing = _read_briefing_file(_worktree_first_path(entry["file"]))
    except Exception:
        briefing = None
    if briefing is None:
        return f"PO-Briefing '{entry['file']}' nicht lesbar oder nicht vorhanden" + hint

    # 5. Inhalt + Länge
    content_err = check_briefing_content(briefing, po_briefing_max_words(cfg))
    if content_err:
        return content_err + hint

    # 6. Aktualität: das Briefing muss zu DIESER Spec-Fassung gehören. Sonst
    #    gibt der PO ein Briefing frei, das eine zwischenzeitlich umgeschriebene
    #    Spec beschreibt — das Gate wäre eine Attrappe.
    #    #439: bevorzugt der Teil-Hash (nur der freigegebene Teil); fehlt er
    #    (Legacy-Briefing), gilt der Gesamt-Hash.
    frozen = entry.get("spec_frozen_sha256")
    if frozen:
        stale = frozen != frozen_spec_sha256(spec_content)
    else:
        stored = entry.get("spec_sha256")
        stale = bool(stored) and stored != spec_sha256(spec_content)
    if stale:
        return (
            "PO-Briefing ist veraltet — die Spec wurde nach dem Briefing geändert."
            + hint
        )

    return None


# --- Spec-Inhaltspruefung des CI-Gates, lokal bei der Freigabe (#521) -------

# Pflicht-Sektionen einer Spec: (Name fuer Meldungen, Regex fuer die Ueberschrift).
SPEC_REQUIRED_SECTIONS = (
    ("Scope", r"Scope"),
    ("Definition of Done", r"(?:Definition\s+of\s+Done|DoD)"),
    ("Acceptance Criteria", r"Acceptance\s+Criteria"),
    ("Test Plan", r"Test\s*Plan"),
)


def check_spec_content(content: str) -> "list[str]":
    """Prueft den Spec-TEXT wie das CI-Gate. Liste der Befunde (leer = in Ordnung).

    Eine Regel, zwei Aufrufer: `scripts/ci_spec_gate.py` setzt den Pfad davor,
    die Freigabe (`_check_spec_content`) verbindet die Befunde zu einer Meldung.
    """
    from hook_utils import extract_ac_entries

    findings = []
    for label, pattern in SPEC_REQUIRED_SECTIONS:
        if _briefing_section_body(content, pattern) is None:
            findings.append(f"Pflicht-Sektion '## {label}' fehlt.")

    marker = find_placeholder(content)
    if marker:
        findings.append(f"enthält noch einen Platzhalter ('{marker}').")

    if _briefing_section_body(content, r"Acceptance\s+Criteria") is not None:
        entries = extract_ac_entries(content)
        if not entries:
            findings.append(
                "'## Acceptance Criteria' ohne AC-N-Einträge "
                "(Format: '- **AC-1:** Given ... / When ... / Then ...')."
            )
        for label, desc, _raw in entries:
            if len(desc.strip()) < 30:
                findings.append(
                    f"{label} ist zu knapp ({len(desc.strip())} Zeichen, ≥ 30 nötig)."
                )

    adr_err = check_adr_content(content)
    if adr_err:
        findings.append(adr_err)
    return findings


def _ci_checked_spec_rel(spec_file: str) -> "str | None":
    """Relativer Spec-Pfad, wenn das CI-Gate diese Spec prueft, sonst None.

    Wie `ci_spec_gate._is_spec`/`_is_fast_spec`: unter docs/specs/, Endung .md,
    nicht _template.md, nicht docs/specs/fast/. Absolute Pfade zaehlen relativ
    zur Worktree- bzw. Projekt-Wurzel.
    """
    import posixpath
    raw = str(spec_file).replace("\\", "/")
    if Path(raw).is_absolute():
        rel = None
        for root in (_worktree_root_if_any(), find_project_root()):
            if root is None:
                continue
            for a, b in ((Path(raw), root), (Path(raw).resolve(), root.resolve())):
                try:
                    rel = a.relative_to(b).as_posix()
                    break
                except ValueError:
                    continue
            if rel is not None:
                break
        if rel is None:
            return None
    else:
        rel = raw
    rel = posixpath.normpath(rel)
    if (not rel.startswith("docs/specs/") or not rel.endswith(".md")
            or Path(rel).name == "_template.md" or rel.startswith("docs/specs/fast/")):
        return None
    return rel


def _check_spec_content(data: dict, config: "dict | None" = None) -> "str | None":
    """CI-Spec-Gate lokal bei der Freigabe (#521). Meldung oder None.

    Lenient wie `_check_adr`: Kill-Switch `ci_spec_gate.enabled: false`, eine
    Spec, die die CI nicht prueft, oder eine fehlende/unlesbare Spec ergeben
    None. Ein Config-Fehler laesst die Pruefung an. Den ADR-Befund meldet
    `_check_adr` schon, solange das ADR-Gate aktiv ist.
    """
    adr_gate_on = True
    try:
        if config is None:
            from config_loader import load_config
            config = load_config()
        if isinstance(config, dict):
            ci_cfg = config.get("ci_spec_gate", {})
            if isinstance(ci_cfg, dict) and ci_cfg.get("enabled") is False:
                return None
            adr_cfg = config.get("adr_gate", {})
            if isinstance(adr_cfg, dict) and adr_cfg.get("enabled") is False:
                adr_gate_on = False
    except Exception:
        pass  # Config load failure → Pruefung bleibt an (lenient)

    spec_file = data.get("spec_file")
    if not spec_file or _ci_checked_spec_rel(spec_file) is None:
        return None
    content = _read_spec_content(data)
    if content is None:
        return None

    findings = check_spec_content(content)
    if adr_gate_on:
        adr_err = check_adr_content(content)
        findings = [f for f in findings if f != adr_err]
    if not findings:
        return None
    return "Spec besteht das CI-Spec-Gate nicht: " + " | ".join(findings)


def _spec_gate_due(data: dict) -> bool:
    """Spec-Pruefung nur beim Ueberschreiten der Freigabe-Grenze (#521)."""
    current = data.get("current_phase", "phase0_idle")
    cur_idx = PHASES.index(current) if current in PHASES else 0
    return cur_idx < PHASES.index("phase4_approved")


# --- Phase Transition Validation ---

def _not_approved_msg() -> str:
    """Blockade-Meldung mit den TATSAECHLICH konfigurierten Freigabe-Phrasen.

    Die Meldung nannte fest verdrahtet 'approved' (Issue #90). `approval_phrases`
    ist über openspec.yaml konfigurierbar, und Projekte nutzen das — die Meldung
    nannte dort also ein Wort, das gar nicht das vereinbarte war, und verschwieg
    das vereinbarte. Zusammen mit der Phasenbindung, der eigentlichen Falle, ist
    der Nutzer sonst auf Raten angewiesen und greift zu
    `set-field spec_approved true` — genau dem Anti-Pattern, das das Gate
    verhindern soll.
    """
    base = "Spec not approved"
    try:
        from config_loader import get_approval_phrases
        phrases = [str(p).strip() for p in get_approval_phrases() if str(p).strip()]
    except Exception:
        phrases = []
    if phrases:
        base += " — user must say one of: " + ", ".join(phrases)
    else:
        base += " — user must say one of the configured approval phrases"
    return base + " (wirkt nur in phase3_spec)"



def _validate_transition(data: dict, target: str) -> str | None:
    """Validate phase transition prerequisites. Returns error message or None."""
    # Feature fast-track: only spec approval gate enforced
    if data.get("workflow_type") == "feature-fast":
        tgt_idx_ff = PHASES.index(target) if target in PHASES else -1
        if tgt_idx_ff < 0:
            return f"Unknown phase: {target}"
        if tgt_idx_ff >= PHASES.index("phase4_approved"):
            if not data.get("spec_file"):
                return "spec_file not set — run /30-write-spec first"
            if not data.get("spec_approved"):
                return _not_approved_msg()
            adr_err = _check_adr(data)
            if adr_err:
                return adr_err
            briefing_err = _check_po_briefing(data)
            if briefing_err:
                return briefing_err
            if _spec_gate_due(data):
                spec_err = _check_spec_content(data)
                if spec_err:
                    return spec_err
        # #447: sonst waere das Evidence-Gate per `start --type feature-fast` umgehbar.
        if target == "phase8_complete":
            return qa_run_stamp_problem(data) or _evidence_reason(target, data)  # #404
        return None

    current = data.get("current_phase", "phase0_idle")
    cur_idx = PHASES.index(current) if current in PHASES else 0
    tgt_idx = PHASES.index(target) if target in PHASES else -1

    if tgt_idx < 0:
        return f"Unknown phase: {target}"

    # Allow backward transitions (reset) and same-phase — ausser Phase 8: der
    # Abschluss (`complete`/`finish`) prueft immer voll, auch wenn der State schon
    # auf phase8_complete steht (#337: sonst archivierte er ohne jede Pruefung).
    if tgt_idx < cur_idx or (tgt_idx == cur_idx and target != "phase8_complete"):
        return None

    if tgt_idx >= PHASES.index("phase2_analyse"):
        if not data.get("context_file"):
            return "context_file not set — run /context first"

    if tgt_idx >= PHASES.index("phase4_approved"):
        if not data.get("spec_file"):
            return "spec_file not set — run /write-spec first"
        if not data.get("spec_approved"):
            return _not_approved_msg()
        adr_err = _check_adr(data)
        if adr_err:
            return adr_err
        briefing_err = _check_po_briefing(data)
        if briefing_err:
            return briefing_err
        if _spec_gate_due(data):
            spec_err = _check_spec_content(data)
            if spec_err:
                return spec_err

    if tgt_idx >= PHASES.index("phase6_implement"):
        red_artifacts = [a for a in data.get("test_artifacts", [])
                        if a.get("phase") == "phase5_tdd_red"]
        if (not red_artifacts and not data.get("red_test_done")
                and not data.get("ui_test_red_done")):
            return "No RED test artifacts — run /tdd-red first"

    # Phase 7 war der einzige Vorwaertswechsel ohne eigene Pruefung: Verdict und
    # Dialog-Nachweis griffen erst bei Phase 8, das Commit-Gate fing es spaet.
    # Deshalb gilt die Pruefung schon beim Wechsel nach phase7_validate.
    if tgt_idx >= PHASES.index("phase7_validate"):
        verdict = str(data.get("adversary_verdict", "") or "")
        if verdict.startswith("VERIFIED"):
            pass
        elif verdict.startswith("AMBIGUOUS") and data.get("adversary_ambiguous_override"):
            pass
        else:
            return "Adversary verdict missing or not VERIFIED"
        # #253: das Verdict zaehlt nur mit gueltigem, gestempeltem Dialog-Artefakt —
        # dieselbe Regel wie im Commit-Gate (bash_gate.py 5c), kein Override-Pfad.
        # #259: das Artefakt muss zudem jede seit der Basis geaenderte Code-Datei binden.
        try:
            import adversary_dialog as ad
            files, info = None, ""
            if ad.coverage_gate_enabled():
                try:
                    files, info = ad.phase8_code_files(data)
                except ad.ChangeSetError as exc:
                    return f"Adversary verdict ohne gültigen Dialog-Nachweis — {exc}"
            reason = ad.check_dialog_evidence(data, changed_files=files)
            if reason and info == ad.DEGRADED_BASE_NOTE:
                reason = f"{reason} ({info})"
        except Exception as exc:
            reason = f"Nachweis-Prüfung nicht verfügbar ({type(exc).__name__}: {exc})"
        if reason:
            return f"Adversary verdict ohne gültigen Dialog-Nachweis — {reason}"

    if tgt_idx >= PHASES.index("phase8_complete"):
        # #447: Evidence-Gate (opt-in) erst nach bestandenem Dialog-Check;
        # #404: davor der Lauf-Stempel (nur bei qa_gate.require_run: true).
        return qa_run_stamp_problem(data) or _evidence_reason(target, data)

    return None


def _evidence_reason(target: str, data: dict) -> "str | None":
    """Evidence-Gate (#447): ohne `evidence_checks` None; fail-closed bei Ladefehler."""
    try:
        import evidence_gate
        return evidence_gate.check_evidence(target, data)
    except Exception as exc:
        return f"Evidence-Gate nicht verfügbar ({type(exc).__name__}: {exc})"


def _start_base_commit() -> "str | None":
    """HEAD des Mess-Roots bei `start` (#259 §14): Worktree vor Hauptrepo; None ohne HEAD."""
    try:
        from adversary_dialog import git_toplevel, run_git
        top = git_toplevel(_worktree_root_if_any() or find_project_root())
        head = run_git(["rev-parse", "--verify", "-q", "HEAD"], top, probe=True) if top else None
    except Exception:
        return None
    return (head.strip() or None) if head else None


def _parse_numstat_z(output: str) -> "list[tuple[int, str]]":
    """`git diff --numstat -z` in (hinzugefuegt, pfad) zerlegen (#341).

    Eintrag `added\\tdeleted\\tpfad`; leeres drittes Feld = Umbenennung, die
    beiden folgenden NUL-Tokens sind Vorher/Nachher, der Nachher-Pfad zaehlt.
    Binaer (`-`) zaehlt 0.
    """
    tokens = output.split("\0")
    entries: "list[tuple[int, str]]" = []
    i = 0
    while i < len(tokens):
        parts = tokens[i].split("\t")
        i += 1
        if len(parts) < 3:
            continue
        path = parts[2]
        if not path:
            if i + 1 >= len(tokens):
                break
            path = tokens[i + 1]
            i += 2
        entries.append((int(parts[0]) if parts[0].isdigit() else 0, path))
    return entries


def _final_loc(data: dict) -> "tuple[int, int] | None":
    """Hinzugefuegte Zeilen seit der Phase-8-Basis als (prod, test) (#250 B, #341).

    Gleiche Ausschluesse und Testmuster wie edit_gate._check_loc_delta. Basis wie
    adversary_dialog._phase8_base (base_commit bzw. merge-base gegen origin/main,
    rebase-fest). None ohne aufloesbare Basis oder bei jedem Fehler.
    """
    try:
        import subprocess
        from adversary_dialog import _phase8_base, git_toplevel
        from config_loader import get_scope_loc_config, get_scope_test_loc_config
        top = git_toplevel(_worktree_root_if_any() or find_project_root())
        if not top:
            return None
        base, _ = _phase8_base(data, top)
        if not base or base == "HEAD":
            return None
        _, exclude_patterns = get_scope_loc_config()
        _, test_patterns = get_scope_test_loc_config()
        result = subprocess.run(
            ["git", "diff", str(base), "--numstat", "-z"],
            cwd=str(top), capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        prod_total = 0
        test_total = 0
        for added, file_name in _parse_numstat_z(result.stdout):
            if any(_re.search(p, file_name) for p in exclude_patterns):
                continue
            if any(_re.search(p, file_name) for p in test_patterns):
                test_total += added
            else:
                prod_total += added
        return (prod_total, test_total)
    except Exception:
        return None


# --- Commands ---

START_USAGE = ("Usage: workflow.py start <name> [--type feature|feature-fast] [--issue N] "
               "[--score 0-6] [--uebernehmen]")


def _stamp_intake_estimate(data: dict, score: int) -> None:
    """`intake_score` und `estimate_initial` stempeln (#620). Schätzung fail-open."""
    data["intake_score"] = score
    est = current_estimate(data)
    if est and not est.get("actual") and est.get("n"):  # #642: ohne Daten keine Zahl
        data["estimate_initial"] = {
            "low": round(est["total_low_min"], 1),
            "mid": round(est["elapsed_min"] + est["mid_min"], 1),
            "high": round(est["total_high_min"], 1), "n": est["n"],
            "source": est["source"], "at": est["now"].isoformat()}


# --- Registrierung je Issue (#461) -----------------------------------------
# Die Logik liegt in issue_claim.py; hier nur die Einhaengepunkte. Jeder Pfad ist
# fail-open bis auf den einen gewollten Abbruch: fremder gueltiger Eintrag beim Start.
CLAIM_CATCH_UP = (None, "pending")


def _claim_ctx(data: dict) -> "tuple[object, dict, str] | None":
    """(Modul, Einstellungen, Issue) wenn die Registrierung fuer `data` gilt, sonst None."""
    try:
        import issue_claim
        cfg = issue_claim.settings()
        if not cfg["enabled"]:
            return None
        issue = workflow_issue_number(data)
        return (issue_claim, cfg, issue) if issue else None
    except Exception:
        return None


def _claim_warn(issue, reason: str) -> None:
    print(f"⚠ WARNUNG: Registrierung an Issue #{issue} nicht moeglich ({reason}). "
          "Die Arbeit laeuft weiter; nachgeholt wird bei `switch`, `claim nachholen` "
          "oder dem naechsten Phasenwechsel.", file=sys.stderr)


def _claim_on_start(data: dict, take_over: bool) -> None:
    """Pflicht-Registrierung beim Start; Exit 1 ohne Workflow-Datei bei fremdem Eintrag."""
    try:
        import issue_claim
        if not issue_claim.settings()["enabled"]:
            return
    except Exception:
        return
    ctx = _claim_ctx(data)
    if ctx is None:
        print("Hinweis: kein Issue im Workflow-Namen, daher keine Registrierung am Issue.")
        return
    mod, cfg, issue = ctx
    res = mod.register(issue, data["name"], data.get("current_phase", ""),
                       take_over=take_over, cfg=cfg)
    if res["result"] == "conflict":
        print(mod.conflict_text(issue, res["winner"], data["name"]), file=sys.stderr)
        sys.exit(1)
    data["issue_claim"] = res["claim"]
    if res["result"] == "pending":
        _claim_warn(issue, res.get("error") or "unbekannt")
    else:
        claim = res["claim"]
        print(f"Registriert an Issue #{issue}: Ort {claim.get('place')}, "
              f"erreichbar ueber {claim.get('reach')}.")


def _claim_store(name: str, claim: dict) -> None:
    """Nur `issue_claim` im laufenden Workflow-State ersetzen (frisch gelesen)."""
    path = _workflow_file(name)
    if not path.exists():
        return
    data = _read_workflow(path)
    data["issue_claim"] = claim
    _atomic_write(path, data)


def _claim_refresh(mod, cfg, issue, name: str, claim: dict, phase: str, quiet: bool) -> None:
    """Phase nachtragen, aber nie einen fremd geaenderten Eintrag ueberschreiben (F003).
    Lesefehler: nichts patchen (fail-open)."""
    try:
        remote = mod.remote_status(claim, cfg=cfg)
        if remote and remote != mod.ACTIVE:
            _claim_store(name, {**claim, "status": remote})
            if remote == mod.TAKEN and not quiet:
                print(f"⚠ WARNUNG: Der Eintrag an Issue #{issue} wurde von einer anderen "
                      "Sitzung übernommen; diese Sitzung arbeitet dort nicht mehr "
                      "registriert.", file=sys.stderr)
            return
        mod.refresh(claim, name, phase, cfg=cfg)
    except Exception as exc:
        mod._log(f"refresh #{issue} {name}: {exc}")


def _claim_catch_up(name: str, take_over: bool = False, quiet: bool = False) -> int:
    """Registrierung nachholen bzw. Stand (Phase) nachtragen. Exit-Code zurueck."""
    try:
        data = _read_workflow(_workflow_file(name))
    except Exception:
        return 0
    ctx = _claim_ctx(data)
    if ctx is None:
        return 0
    mod, cfg, issue = ctx
    claim = data.get("issue_claim") if isinstance(data.get("issue_claim"), dict) else {}
    status = claim.get("status")
    phase = data.get("current_phase", "")
    if status == mod.ACTIVE and not take_over:
        _claim_refresh(mod, cfg, issue, name, claim, phase, quiet)
        return 0
    if status not in CLAIM_CATCH_UP and not take_over:
        if not quiet:
            print(f"Registrierung an Issue #{issue}: {status} (nichts nachzuholen).")
        return 0
    res = mod.register(issue, name, phase, take_over=take_over, existing=claim, cfg=cfg)
    _claim_store(name, res["claim"])
    if res["result"] == "conflict":
        text = mod.conflict_text(issue, res["winner"], name)
        print(text.replace(f"workflow.py start {name} --uebernehmen",
                           f"workflow.py claim nachholen {name} --uebernehmen"), file=sys.stderr)
        return 1
    if res["result"] == "pending":
        _claim_warn(issue, res.get("error") or "unbekannt")
    elif not quiet:
        print(f"Registriert an Issue #{issue} ({res['claim'].get('place')}).")
    return 0


def _spawn_claim_sync(name: str, data: dict) -> None:
    """Phasenwechsel: Stand abgekoppelt nachtragen (Muster #490), wartet nie."""
    try:
        if _claim_ctx(data) is None:
            return
        claim = data.get("issue_claim") if isinstance(data.get("issue_claim"), dict) else {}
        if claim.get("status") not in CLAIM_CATCH_UP + ("aktiv",):
            return
        import subprocess
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "claim", "nachholen", name, "--still"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
            cwd=str(find_project_root()),
        )
    except Exception:
        pass


def _claim_release(data: dict, name: str) -> None:
    """Eintrag am Issue freigeben (`ship-status done|skipped`, `abandon`). Fail-open."""
    ctx = _claim_ctx(data)
    claim = data.get("issue_claim")
    if ctx is None or not isinstance(claim, dict):
        return
    status = claim.get("status")  # F001: pending mit ID kann am Issue aktiv stehen
    if not (status == "aktiv" or (status == "pending" and claim.get("comment_id"))):
        return
    mod, cfg, issue = ctx
    new_claim, error = mod.release(claim, name, data.get("current_phase", ""), cfg=cfg)
    data["issue_claim"] = new_claim
    if error:
        print(f"⚠ WARNUNG: Eintrag an Issue #{issue} nicht freigegeben ({error}).",
              file=sys.stderr)


def cmd_claim(args: list[str]) -> None:
    """`claim status [<name>]` zeigt die Eintraege am Issue samt offenen Pull Requests;
    `claim nachholen [<name>] [--uebernehmen]` holt die Registrierung nach (#461)."""
    flags = {a for a in args if a.startswith("--")}
    rest = [a for a in args if not a.startswith("--")]
    if not rest or rest[0] not in ("status", "nachholen"):
        print("Usage: workflow.py claim status|nachholen [<name>] [--uebernehmen]",
              file=sys.stderr)
        sys.exit(1)
    if len(rest) > 1:
        _validate_name(rest[1])
        name = rest[1]
        data = _read_workflow(_workflow_file(name)) if _workflow_file(name).exists() else None
        if data is None:
            print(f"Workflow {name} not found.", file=sys.stderr)
            sys.exit(1)
    else:
        data, name = _read_active()
    if rest[0] == "nachholen":
        sys.exit(_claim_catch_up(name, "--uebernehmen" in flags, quiet="--still" in flags))
    ctx = _claim_ctx(data)
    if ctx is None:
        print("Keine Registrierung: abgeschaltet oder kein Issue im Workflow-Namen.")
        return
    mod, cfg, issue = ctx
    try:
        lines = mod.status_lines(issue, data.get("issue_claim"), cfg=cfg)
    except Exception as exc:
        print(f"⚠ WARNUNG: Eintraege an Issue #{issue} nicht lesbar ({exc}).", file=sys.stderr)
        sys.exit(1)
    print("\n".join(lines))


def cmd_start(args: list[str]) -> None:
    workflow_type = "feature"
    issue_arg = None
    score_arg = None
    take_over = "--uebernehmen" in args  # #461: fremden Eintrag am Issue uebernehmen
    args = [a for a in args if a != "--uebernehmen"]
    name_args = []
    i = 0
    while i < len(args):
        if args[i] == "--type" and i + 1 < len(args):
            workflow_type = args[i + 1]
            i += 2
        elif args[i] == "--issue" and i + 1 < len(args):
            issue_arg = args[i + 1]
            i += 2
        elif args[i] == "--score":
            score_arg = args[i + 1] if i + 1 < len(args) else ""
            i += 2
        else:
            name_args.append(args[i])
            i += 1
    if not name_args or (score_arg is not None and not _re.fullmatch(r"[0-6]", score_arg)):
        print(START_USAGE, file=sys.stderr)
        sys.exit(1)
    if issue_arg is not None:
        issue_arg = issue_arg[1:] if issue_arg.startswith("#") else issue_arg
        if not _re.fullmatch(r"[0-9]+", issue_arg):
            print(f"Ungueltige Issue-Nummer fuer --issue: {issue_arg!r} (nur Ziffern, "
                  "optional mit fuehrendem #).", file=sys.stderr)
            sys.exit(1)
    if workflow_type == "bug":
        print("Typ `bug` wurde entfernt (#333). Fehler laufen über /00-intake; "
              "Kleinkram über `--type feature-fast`.", file=sys.stderr)
        sys.exit(1)
    if workflow_type not in ("feature", "feature-fast"):
        print(f"Unknown workflow type: {workflow_type!r}. Valid: feature, feature-fast", file=sys.stderr)
        sys.exit(1)
    name = name_args[0]
    _validate_name(name)
    wf_file = _workflow_file(name)
    if wf_file.exists():
        print(f"Workflow {name} already exists. Use 'switch' to activate.", file=sys.stderr)
        sys.exit(1)
    data = _new_workflow(name)
    data["workflow_type"] = workflow_type
    try:  # #628: ein Neustart unter gleichem Namen erbt keine Aktivminuten
        _activity_path(name).unlink(missing_ok=True)
    except OSError:
        pass
    if issue_arg is not None:
        data["issue_number"] = issue_arg  # #513: echte Nummer statt Namensregel
    data["base_commit"] = _start_base_commit()  # #259: Basis-Kandidat fuer Phase 8
    if workflow_type == "feature-fast":
        # Fast-track for small features: skip context/analyse, start at spec
        data["current_phase"] = "phase3_spec"
        data["red_test_done"] = True  # inline TDD during implementation
        _log_phase_transition(data, "phase3_spec")
    else:
        _log_phase_transition(data, "phase1_context")
    if score_arg is not None:
        _stamp_intake_estimate(data, int(score_arg))  # #620
    _claim_on_start(data, take_over)  # #461: vor dem Schreiben, Abbruch bei fremdem Eintrag
    _atomic_write(wf_file, data)
    _set_active(name)
    _herdr("report", data)
    issue = workflow_issue_number(data)
    if issue and (cached_issue_title(issue) is None or cached_issue_brief(issue) is None):
        _spawn_issue_title_fetch(issue)  # #490/#612: abgekoppelt, wartet nicht
    if workflow_type == "feature-fast":
        type_note = " [FEATURE fast-track → phase3_spec]"
    else:
        type_note = ""
    print(f"Started workflow: {name}{type_note}")
    print(
        f"\nOPENSPEC_ACTIVE_WORKFLOW={name} written to all settings.local.json files.\n"
        f"Hooks read this directly — no session restart required.\n"
        f"Shell (for manual workflow.py calls in terminal):\n"
        f"  export OPENSPEC_ACTIVE_WORKFLOW={name}\n"
        f"Agent spawns:\n"
        f'  Agent(prompt="... ## Required\\nexport OPENSPEC_ACTIVE_WORKFLOW={name}\\n...")',
    )
    # #476: Plan-Pane rechts neben Claude — nur Spawn, fail-open, kein stdout
    try:
        import herdr_bridge
        herdr_bridge.open_plan_pane()
    except Exception:
        pass


def _plan_active() -> "tuple[str, dict] | None":
    """Aktiven Workflow fuer die Plan-Anzeige (#476) frisch aufloesen."""
    found = read_active_workflow_fast()
    if not found:
        return None
    name, data = found
    data = dict(data)
    data.setdefault("name", name)
    _with_issue_title(data)
    return name, data


def _with_issue_title(data: dict) -> dict:
    """`issue_title` aus dem Cache setzen, falls vorhanden (#490). Wirft nie.

    Der Cache-Wert wird erneut normalisiert (#492); leer = kein Titel.
    """
    try:
        issue = workflow_issue_number(data)
        title = short_title(cached_issue_title(issue),
                            max_words=ISSUE_TITLE_MAX_WORDS) if issue else None
        if title:
            data["issue_title"] = title
        brief = cached_issue_brief(issue) if issue else None
        if brief:  # #612: Problem/Ziel fuer den Plan-Kopf
            data["issue_brief"] = {"problem": str(brief.get("problem") or ""),
                                   "goal": str(brief.get("goal") or "")}
    except Exception:
        pass
    return data


def _plan_fetch_missing(data, tried: set) -> None:
    """Fehlenden Titel/Kurzfassung hoechstens einmal je Issue und Prozess holen (#490/#612)."""
    try:
        if not isinstance(data, dict):
            return
        issue = workflow_issue_number(data)
        if not issue or issue in tried:
            return
        tried.add(issue)
        if cached_issue_title(issue) is None or cached_issue_brief(issue) is None:
            fetch_issue_title(issue)
    except Exception:
        pass


def _plan_pane_file() -> "Path | None":
    """ID-Datei im Haupt-Repo, einmal beim Watcher-Start absolut ermittelt (#493 F001)."""
    try:
        from hook_utils import find_project_root
        return (find_project_root() / ".claude" / "herdr_plan_pane.json").resolve()
    except Exception:
        return None


def _plan_follow_target(target: "str | None", path: "Path | None") -> None:
    """`--target` (#493): in die eingetragene Basis des Claude-Panes wechseln. Wirft nie.

    #496: aus der ID-Datei wird nur noch das `cwd` gelesen (Cache), nie `pane_id`.

    `path` ist absolut: auch wenn das aktuelle cwd (alter Worktree) geloescht
    wurde, bleibt die ID-Datei lesbar; ein nicht ermittelbares cwd gilt als
    abweichend (F001).
    """
    if not target or path is None:
        return
    try:
        from hook_utils import read_state_json
        cwd = read_state_json(path, path.parent.parent)["panes"][target].get("cwd")
        if not (isinstance(cwd, str) and cwd and Path(cwd).is_dir()):
            return
        try:
            same = Path(cwd).resolve() == Path(os.getcwd()).resolve()
        except Exception:
            same = False
        if not same:
            os.chdir(cwd)
            if os.environ.get("CLAUDE_PROJECT_DIR"):
                os.environ["CLAUDE_PROJECT_DIR"] = cwd  # sonst zeigt er auf die alte Basis
    except Exception:
        pass


PLAN_OWNER_DEAD_ROUNDS = 3  # #496: so viele tote Owner-Runden in Folge -> Ende


def _plan_owner_state(target: "str | None") -> "bool | None":
    """#496: True = Owner lebt (agent claude), False = tot (Fehler/kein claude),
    None = unklar (kein Binary, Zeitlimit, unlesbare Antwort) — zaehlt nicht."""
    import subprocess
    if not target:
        return None
    binary = os.environ.get("HERDR_BIN_PATH", "")
    if not (os.path.isabs(binary) and os.path.isfile(binary) and os.access(binary, os.X_OK)):
        return None
    try:
        res = subprocess.run([binary, "pane", "get", target], stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=3)
    except Exception:
        return None
    if res.returncode != 0:
        return False
    try:
        pane = json.loads(res.stdout)["result"]["pane"]
    except Exception:
        return None
    return isinstance(pane, dict) and pane.get("agent") == "claude"


def _plan_watch_should_end(target, own_file: Path, misses: list) -> bool:
    """#496: Ende, wenn die eigene workflow.py fehlt oder der Owner 3x tot war."""
    if not own_file.exists():
        return True
    state = _plan_owner_state(target)
    if state is True:
        misses[0] = 0
    elif state is False:
        misses[0] += 1
    return misses[0] >= PLAN_OWNER_DEAD_ROUNDS


def _plan_watch(target: "str | None" = None) -> None:
    """`plan --watch` (#476): je Runde neu aufloesen, nur bei Aenderung neu zeichnen."""
    import shutil
    own_file = Path(os.path.abspath(__file__))  # vor jedem chdir (#493) festhalten
    misses = [0]
    try:
        rounds = int(os.environ.get("OPENSPEC_PLAN_WATCH_ROUNDS") or 0)
    except ValueError:
        rounds = 0
    try:
        interval = max(0.0, float(os.environ.get("OPENSPEC_PLAN_WATCH_INTERVAL") or 1.0))
    except ValueError:
        interval = 1.0
    last_name = None
    last_out = None
    done = 0
    tried: set = set()  # #490: Issue-Nummern, deren Titel schon geholt wurde
    est_cache: dict = {}  # #620: Archiv-Dauern, neu nur bei geaendertem Archivordner
    pane_file = _plan_pane_file() if target else None
    try:
        while True:
            data = None
            if _plan_watch_should_end(target, own_file, misses):
                break  # Herdr schliesst das Pane, wenn der exec-Prozess endet
            _plan_follow_target(target, pane_file)  # #493: vor dem Aufloesen
            try:
                width = shutil.get_terminal_size().columns
                deploy = deploy_mode()  # je Runde neu (#478, #510)
                auto = deploy_autonomous()  # #550: wie `endstate`
                found = _plan_active()
                if found:
                    last_name, data = found
                    out = render_plan(data, width=width, deploy=deploy, autonomous=auto,
                                      queue=queue_end_args(data),
                                      estimate=current_estimate(data, cache=est_cache))
                elif last_name and _archive_file(last_name).exists():
                    data = dict(_read_workflow(_archive_file(last_name)))
                    data.setdefault("name", last_name)
                    _with_issue_title(data)
                    out = render_plan(data, archived=True, width=width, deploy=deploy,
                                      autonomous=auto, queue=queue_end_args(data),
                                      estimate=current_estimate(data, archived=True))
                else:
                    out = render_plan(None, width=width)
                if out != last_out:
                    sys.stdout.write("\x1b[H\x1b[2J" + out + "\n")
                    sys.stdout.flush()
                    last_out = out
            except (Exception, SystemExit):
                pass  # letzte Ausgabe bleibt stehen
            _plan_fetch_missing(data, tried)  # nach dem Zeichnen (#490)
            done += 1
            if rounds and done >= rounds:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        pass


def cmd_plan(args: list[str]) -> None:
    """Workflow-Plan anzeigen (#476): einmal, `--watch` live, `--open` Herdr-Pane."""
    if "--open" in args:
        try:
            import herdr_bridge
            if herdr_bridge._pane() is None:
                print("Plan-Pane: kein Herdr-Pane (HERDR-Env fehlt oder herdr.enabled: false)")
            elif herdr_bridge.open_plan_pane(force=True):
                print("Plan-Pane: Oeffnen angestossen")
            else:
                print("Plan-Pane: Start des Runners fehlgeschlagen")
        except Exception as exc:
            print(f"Plan-Pane: nicht moeglich ({type(exc).__name__})")
        return
    if "--watch" in args:
        i = args.index("--target") if "--target" in args else -1
        _plan_watch(args[i + 1] if 0 <= i < len(args) - 1 else None)
        return
    try:
        found = _plan_active()
    except (Exception, SystemExit):
        found = None
    data = found[1] if found else None
    print(render_plan(data, deploy=deploy_mode(), autonomous=deploy_autonomous(),
                      queue=queue_end_args(data) if data is not None else None,
                      estimate=current_estimate(data) if data is not None else None))


def cmd_issue_title(args: list[str]) -> None:
    """`issue-title <N>` (#490): Titel (und Kurzfassung) holen und cachen; Exit immer 0."""
    title = fetch_issue_title(args[0]) if args else None
    if title:
        print(title)


def cmd_issue_brief(args: list[str]) -> None:
    """`issue-brief <N> [--problem T] [--ziel T] [--auto]` (#612); Exit immer 0.

    Ohne Optionen: Kurzfassung zeigen, bei Bedarf aus dem Issue holen.
    `--problem`/`--ziel`: handgeschriebene Fassung (`SOURCE=manual`), die ein
    erneutes Holen nicht ueberschreibt. `--auto`: manuelle Fassung verwerfen und
    wieder aus dem Issue lesen. Ausgabe ISSUE=, TITLE=, PROBLEM=, ZIEL=, SOURCE=.
    """
    if not args or not args[0].strip():
        print('Usage: workflow.py issue-brief <N> [--problem "<Text>"] [--ziel "<Text>"] [--auto]',
              file=sys.stderr)
        return
    issue = args[0].lstrip("#").strip()
    manual: dict = {}
    auto = "--auto" in args
    for flag, key in (("--problem", "problem"), ("--ziel", "goal")):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):
                manual[key] = " ".join(args[idx + 1].split())
    try:
        if auto:
            fetch_issue_title(issue, replace_manual=True)
        elif cached_issue_brief(issue) is None or cached_issue_title(issue) is None:
            fetch_issue_title(issue)
        if manual and not auto:
            entry = dict(cached_issue_brief(issue) or {})
            entry.setdefault("title", short_title(cached_issue_title(issue) or "",
                                                  max_words=ISSUE_TITLE_MAX_WORDS))
            entry.setdefault("problem", "")
            entry.setdefault("goal", "")
            entry.update(manual)
            entry["source"] = "manual"
            entry["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _store_issue_brief(issue, entry, replace_manual=True)
    except Exception:
        pass
    brief = cached_issue_brief(issue) or {}
    title = cached_issue_title(issue) or brief.get("title") or ""
    print(f"ISSUE={issue}")
    print(f"TITLE={short_title(title, max_words=ISSUE_TITLE_MAX_WORDS)}")
    print(f"PROBLEM={brief.get('problem') or ''}")
    print(f"ZIEL={brief.get('goal') or ''}")
    print(f"SOURCE={brief.get('source') or 'none'}" if brief else "SOURCE=none")


def cmd_switch(args: list[str]) -> None:
    if not args:
        print("Usage: workflow.py switch <name>", file=sys.stderr)
        sys.exit(1)
    name = args[0]
    _validate_name(name)
    wf_file = _workflow_file(name)
    if not wf_file.exists():
        print(f"Workflow {name} not found.", file=sys.stderr)
        sys.exit(1)

    # Warn if current active workflow is in a keyword-sensitive phase.
    # Switching here means the next "approved" / "go" will target the new workflow.
    try:
        current_data, current_name = _read_active()
        if current_name != name:
            cur_phase = current_data.get("current_phase", "")
            if cur_phase in KEYWORD_SENSITIVE_PHASES:
                print(
                    f"WARNING: Switching away from '{current_name}' which is in {cur_phase}.\n"
                    f"  User keywords ('approved', 'go') will now target '{name}'.\n"
                    f"  Switch back with: workflow.py switch {current_name}",
                    file=sys.stderr,
                )
    except SystemExit:
        pass  # no current active workflow — that's fine

    _set_active(name)
    try:  # #466: Sidebar zeigt den neuen aktiven Workflow
        _herdr("report", _read_workflow(wf_file))
    except Exception:
        pass
    try:  # #461: ausstehende Registrierung nachholen; ein aktiver Eintrag bleibt unberuehrt
        claim = _read_workflow(wf_file).get("issue_claim")
        if (claim.get("status") if isinstance(claim, dict) else None) in CLAIM_CATCH_UP:
            _claim_catch_up(name)
    except Exception:
        pass

    env_name = _active_name_from_env()
    if env_name and env_name != name:
        print(
            f"Switched to workflow: {name}\n"
            f"  settings.local.json updated — hooks will use '{name}' on next invocation.\n"
            f"WARNING: Shell still has OPENSPEC_ACTIVE_WORKFLOW={env_name!r}.\n"
            f"  Update shell: export OPENSPEC_ACTIVE_WORKFLOW={name}",
            file=sys.stderr,
        )
    print(f"Switched to workflow: {name}")


def cmd_status(args: list[str]) -> None:
    data, name = _read_active()
    phase = data.get("current_phase", "phase0_idle")
    phase_name = PHASE_NAMES.get(phase, phase)
    spec = data.get("spec_file") or "Not created"
    approved = "Yes" if data.get("spec_approved") else "No"
    green_ok = "Yes" if data.get("green_approved") else "No"
    artifacts = len(data.get("test_artifacts", []))
    fix_loops = data.get("fix_loop_iterations", 0)
    transitions = len(data.get("phase_transitions", []))
    loc_delta = data.get("loc_delta_current", "+0")
    log_dir = find_project_root() / ".claude" / "workflows" / "_log"
    log_written = log_dir.exists() and any(log_dir.glob(f"*_{name}.yaml"))
    from hook_utils import resolve_active_workflow
    _resolved_name, source = resolve_active_workflow()
    if source == "env":
        source_label = f"env:OPENSPEC_ACTIVE_WORKFLOW={name}"
    else:
        source_label = source  # 'file', 'settings', ...
    print(f"Workflow: {name}  [{source_label}]")
    print(f"Phase: {phase_name}")
    print(f"Spec: {spec}")
    print(f"Approved: {approved}")
    print(f"GREEN Approved: {green_ok}")
    print(f"Test Artifacts: {artifacts}")
    print(f"Fix-Loop Iterations: {fix_loops}")
    print(f"Phase Transitions: {transitions}")
    loc_override = data.get("loc_limit_override")
    if loc_override:
        print(f"LoC Delta: {loc_delta}/{loc_override} (override)")
    else:
        print(f"LoC Delta: {loc_delta}")
    print(f"Execution Log: {'Written' if log_written else 'Pending — run write-log before complete'}")
    approvals = data.get("approvals") or []
    if isinstance(approvals, list) and approvals:
        # Freigabe-Protokoll (#469); ohne Eintraege bleibt die Ausgabe wie bisher.
        print(f"Freigaben: {len(approvals)}")
        for e in approvals:
            if not isinstance(e, dict):
                continue
            print(f"  - {e.get('gate')} | by {e.get('by')} | {e.get('mode')} | {e.get('at')}")


def _reset_approvals_on_backstep(data: dict, current: str, target: str) -> None:
    """Rueckspruenge entwerten die Freigaben, die das Ziel noch nicht hat (#405).

    Ziel vor phase4_approved: spec_approved und green_approved zurueck;
    Ziel vor phase6_implement: nur green_approved. Vorwaertswechsel, gleiche
    Phase und Ziel ab phase6_implement aendern nichts.
    Ziel vor phase8_complete verwirft zudem den Deploy-Zustand (`deploy_status`,
    `deploy_at`, `deploy_note`), damit der Plan nach dem BROKEN-Pfad nicht den
    alten Stand zeigt (#561).
    """
    if current not in PHASES or target not in PHASES:
        return
    cur_idx, tgt_idx = PHASES.index(current), PHASES.index(target)
    if tgt_idx >= cur_idx:
        return
    if tgt_idx < PHASES.index("phase4_approved"):
        data["spec_approved"] = False
        _retire_briefing(data, current, target)
    if tgt_idx < PHASES.index("phase6_implement"):
        data["green_approved"] = False
    if tgt_idx < PHASES.index("phase8_complete"):
        for key in ("deploy_status", "deploy_at", "deploy_note",
                    "ship_status", "ship_at", "ship_note"):
            data.pop(key, None)


_BRIEFING_HISTORY_MAX = 5


def _retire_briefing(data: dict, current: str, target: str) -> None:
    """Ruecksprung vor phase4_approved verwirft das alte PO-Briefing (#647, #648).

    Es wandert nach `po_briefing_history` (hoechstens 5, aelteste fallen weg),
    `spec_rework` haelt fest, dass die Spec neu zu schreiben ist. Ohne Briefing
    (Fast Track, Kill-Switch) bleibt alles unveraendert.
    """
    if not isinstance(data.get("po_briefing"), dict):
        return
    entry = data.pop("po_briefing")
    from datetime import timezone
    history = data.get("po_briefing_history")
    history = list(history) if isinstance(history, list) else []
    history.append({
        "entry": entry,
        "reason": f"backstep {current}->{target}",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    data["po_briefing_history"] = history[-_BRIEFING_HISTORY_MAX:]
    data["spec_rework"] = True


def cmd_phase(args: list[str]) -> None:
    if not args:
        print("Usage: workflow.py phase <phase>", file=sys.stderr)
        sys.exit(1)
    trigger = "command"
    filtered = [a for a in args if not a.startswith("--trigger=")]
    for a in args:
        if a.startswith("--trigger="):
            trigger = a.split("=", 1)[1]
    target = filtered[0]
    data, name = _read_active()
    error = _validate_transition(data, target)
    if error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        sys.exit(1)
    current = data.get("current_phase", "phase0_idle")
    # Fix-loop counter: re-entering phase6_implement from phase6b_adversary.
    # Vor record_transition, damit die Budget-Pruefung den neuen Stand sieht (#250).
    if target == "phase6_implement" and current == "phase6b_adversary":
        data["fix_loop_iterations"] = data.get("fix_loop_iterations", 0) + 1
    _reset_approvals_on_backstep(data, current, target)
    exceeded = record_transition(data, target, trigger)
    data["current_phase"] = target
    if target == "phase8_complete":
        _mark_ship_open(data)  # #612: Code fertig, Auslieferung steht aus
    _save_active(data)
    _spawn_claim_sync(name, data)  # #461: Stand am Issue abgekoppelt nachtragen
    print(f"Set phase to: {target}")
    _print_budget_question(exceeded)


def format_budget_question(exceeded: list) -> str:
    """Rueckfrage-Text zu Budget-Ueberschreitungen; leer ohne Ereignisse (#250, #341)."""
    return "\n".join(
        f"RÜCKFRAGE AN DEN PO: Stufe {event.get('stage')}: {event['metric']} "
        f"steht bei {event['value']}, Grenze {event['limit']}.\n"
        f"  Lege dem PO jetzt den Stand vor und frage: weiter, kleiner schneiden "
        f"oder abbrechen?"
        for event in exceeded or []
    )


def _print_budget_question(exceeded: list) -> None:
    """Budget-Ueberschreitung als Anweisung an Claude ausgeben, keine Sperre (#250)."""
    text = format_budget_question(exceeded)
    if text:
        print(text)


# Schluessel, die ein Gate steuern und einen eigenen, geprueften Befehl haben.
# `set-field` wuerde sie ohne jede Pruefung setzen (#379).
_SET_FIELD_PROTECTED = {
    "current_phase": "workflow.py phase <phase>",
    "spec_approved": "Freigabe-Phrase des Users in phase3_spec",
    "red_test_done": "workflow.py mark-red <ergebnis>",
    "ui_test_red_done": "workflow.py mark-ui-red <ergebnis>",
    "test_artifacts": "workflow.py add-artifact ...",
    "po_briefing": "workflow.py set-briefing <pfad>",
    "adversary_ambiguous_override": "workflow.py override-ambiguous <grund>",
    "affected_files": "workflow.py set-affected-files ...",
    "phase_log": "wird von workflow.py phase gefuehrt",
    "status": "workflow.py finish / abandon",
    "name": "workflow.py start <name>",
    "base_commit": "wird von workflow.py start gesetzt (Basis der Phase-8-Abdeckung)",
    "qa_run_stamp": "wird von qa_gate.py gesetzt",
    "no_build_reason": "workflow.py no-build --reason \"<Begruendung>\"",
    "approvals": "wird nur von workflow.record_approval(...) gefuehrt (#469)",
    "po_briefing_history": "wird von workflow.py phase / set-briefing gefuehrt (#647)",
    "spec_rework": "wird von workflow.py phase / set-briefing gefuehrt (#647)",
}

# Nach der Freigabe nur noch mit Override-Token des Users per set-field (#379).
_SET_FIELD_FROZEN_AFTER_APPROVAL = {"spec_file"}


def _is_approved(data: dict) -> bool:
    """Freigabe erteilt? Nicht nur an current_phase gemessen: `phase` erlaubt
    Rueckspruenge, spec_approved bleibt dabei stehen (#379)."""
    if data.get("spec_approved"):
        return True
    phase = data.get("current_phase", "phase0_idle")
    idx = PHASES.index(phase) if phase in PHASES else len(PHASES)
    return idx >= PHASES.index("phase4_approved")


def _ever_approved(data: dict) -> bool:
    """Je eine Phase ab phase4_approved erreicht? Belege: `phase_transitions`
    (`from`/`to`) und `phase_log` — ueberdauern den Ruecksprung-Reset (#405)."""
    seen = set()
    for t in data.get("phase_transitions", []) or []:
        if isinstance(t, dict):
            seen.update((t.get("from"), t.get("to")))
    for e in data.get("phase_log", []) or []:
        if isinstance(e, dict):
            seen.add(e.get("phase"))
    gate = PHASES.index("phase4_approved")
    return any(p in PHASES and PHASES.index(p) >= gate for p in seen)


def _user_override(name: str) -> bool:
    try:
        from override_token import has_valid_token
        return bool(has_valid_token(name))
    except Exception:
        return False


def _check_set_field_type(data: dict, name: str, value: str) -> str | None:
    """`workflow_type` per set-field: Herabstufung auf feature-fast ab Phase 4
    nur mit Override-Token des Users (#379).

    Der feature-fast-Zweig von `_validate_transition` prueft beim Abschluss kein
    Adversary-Verdict — ein freigegebener `feature`-Workflow verloere durch die
    Umklassifizierung sonst jeden Pruefnachweis. Vor der Freigabe bleibt der
    Wechsel frei: dann greift das Freigabe-Gate noch. Ein Ruecksprung mit
    zurueckgesetzter Freigabe (#405) bleibt gesperrt. Rueckfall-Rezept fuer
    Alt-Workflows vom Typ `bug` (#333) bleibt ueber `override` moeglich.
    """
    if value not in ("feature", "feature-fast"):
        return f"Unbekannter workflow_type {value!r}. Gueltig: feature, feature-fast"
    if value != "feature-fast" or data.get("workflow_type") == "feature-fast":
        return None
    if not (_is_approved(data) or _ever_approved(data)) or _user_override(name):
        return None
    phase = data.get("current_phase", "phase0_idle")
    return (
        f"workflow_type -> feature-fast in {phase} entzieht den Workflow dem "
        "Adversary-Gate beim Abschluss. Nach der Freigabe nur mit Override: "
        "der User tippt \"override\" (gilt 1 h), dann erneut ausfuehren. "
        "Ohne Abschluss beenden: workflow.py abandon --reason \"...\""
    )


def cmd_set_field(args: list[str]) -> None:
    if len(args) < 2:
        print("Usage: workflow.py set-field <key> <value>", file=sys.stderr)
        sys.exit(1)
    key, value = args[0], " ".join(args[1:])
    if key in _SET_FIELD_PROTECTED:
        print(
            f"BLOCKED: `{key}` steuert ein Gate und ist per set-field gesperrt (#379). "
            f"Stattdessen: {_SET_FIELD_PROTECTED[key]}",
            file=sys.stderr,
        )
        sys.exit(1)
    if key == "workflow_type":
        data, name = _read_active()
        err = _check_set_field_type(data, name, value)
        if err:
            print(f"BLOCKED: {err}", file=sys.stderr)
            sys.exit(1)
    if key in _SET_FIELD_FROZEN_AFTER_APPROVAL:
        data, name = _read_active()
        if _is_approved(data) and not _user_override(name):
            print(
                f"BLOCKED: `{key}` ist nach der Freigabe eingefroren — sonst pruefen "
                "Spec-Freeze und Adversary-Checkliste eine nicht freigegebene Spec (#379). "
                "Nur mit Override: der User tippt \"override\" (gilt 1 h).",
                file=sys.stderr,
            )
            sys.exit(1)
    if value.lower() in ("true", "yes"):
        value = True
    elif value.lower() in ("false", "no"):
        value = False
    elif key == "adversary_findings_total" and value.isdigit():
        value = int(value)  # Kennzahl als Zahl, nicht als String (#278)
    data, name = _read_active()
    data[key] = value
    _save_active(data)
    print(f"Set {key} = {value} on workflow {name}")


def _post_approval_briefing_error(data: dict, rel: str, spec_content: str) -> "str | None":
    """Nach der Freigabe nur noch Stempel-Migration (#439), sonst Fehlertext.

    Vor `phase4_approved` → None (normales Registrieren). Ohne bisher
    registriertes Briefing (Fast Track, Gate aus) gibt es keinen Stempel zu
    schuetzen → None. Sonst erlaubt nur, wenn dasselbe Briefing registriert
    ist und sein gespeicherter Gesamt-Hash exakt zum aktuellen Spec-Inhalt
    passt — dann wird nur der Doppelstempel nachgetragen.
    """
    phase = data.get("current_phase", "phase0_idle")
    if phase not in PHASES or PHASES.index(phase) < PHASES.index("phase4_approved"):
        return None
    entry = data.get("po_briefing")
    if not (isinstance(entry, dict) and entry.get("file")):
        return None
    if (entry.get("file") == rel
            and entry.get("spec_sha256") == spec_sha256(spec_content)):
        return None
    return (
        f"Spec ist freigegeben (Phase {phase}) — set-briefing stempelt danach nur "
        "noch ein bereits registriertes Briefing um, dessen Gesamt-Hash exakt zur "
        "aktuellen Spec passt. Das ist hier nicht der Fall.\n"
        "→ Änderung am Freigegebenen: `workflow.py phase phase3_spec`, neues "
        "Briefing, neue Freigabe."
    )


def cmd_set_briefing(args: list[str]) -> None:
    """Registriere das unabhängige PO-Briefing für die anstehende Freigabe.

    Bindet es über den SHA-256 der Spec an genau die Fassung, die der Briefer
    gelesen hat. Prüft denselben Inhalts-Kontrakt wie das Gate — ein
    unvollständiges Briefing fällt hier auf, nicht erst beim `approved`.
    """
    if not args:
        print("Usage: workflow.py set-briefing <pfad-zum-po-briefing>", file=sys.stderr)
        sys.exit(1)
    rel = args[0]
    root = _worktree_first_root(rel)
    path = Path(rel)
    if path.is_absolute():
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            print(f"BLOCKED: Briefing liegt ausserhalb des Projekts: {rel}", file=sys.stderr)
            sys.exit(1)
    briefing_path = root / rel
    # #470 F003: auch relative `..`-Pfade und Symlinks auf Dateien ausserhalb
    # blocken — ein Briefing ausserhalb des Repos sehen weder CI noch Review.
    try:
        inside = briefing_path.resolve().is_relative_to(root.resolve())
    except Exception:
        inside = False
    if not inside:
        print(f"BLOCKED: Briefing liegt ausserhalb des Projekts: {rel}", file=sys.stderr)
        sys.exit(1)

    try:
        briefing = briefing_path.read_text()
    except Exception:
        print(f"BLOCKED: PO-Briefing nicht lesbar: {rel}", file=sys.stderr)
        sys.exit(1)

    content_err = check_briefing_content(briefing, po_briefing_max_words())
    if content_err:
        print(f"BLOCKED: {content_err}", file=sys.stderr)
        sys.exit(1)

    data, name = _read_active()
    spec_content = _read_spec_content(data)
    if spec_content is None:
        print(
            "BLOCKED: Keine lesbare Spec im Workflow (Feld 'spec_file') — "
            "das Briefing kann an keine Spec-Fassung gebunden werden.",
            file=sys.stderr,
        )
        sys.exit(1)

    migrate_err = _post_approval_briefing_error(data, rel, spec_content)
    if migrate_err:
        print(f"BLOCKED: {migrate_err}", file=sys.stderr)
        sys.exit(1)

    sha = spec_sha256(spec_content)
    frozen_sha = frozen_spec_sha256(spec_content)
    entry = {
        "file": rel,
        "spec_sha256": sha,
        "spec_frozen_sha256": frozen_sha,
        "created": datetime.now().isoformat(timespec="seconds"),
        # #470: Ampel + Hash der Briefing-Datei. Der Hash wird nach dem Stempeln
        # auf den gestempelten Text nachgezogen, damit auto-approve gegen die
        # Datei auf Platte vergleichen kann.
        "ampel": parse_ampel(briefing),
        "briefing_sha256": _hashlib.sha256(briefing.encode("utf-8")).hexdigest(),
    }
    data["po_briefing"] = entry
    data.pop("spec_rework", None)  # neues Briefing nach Ruecksprung (#647)

    # Bindung zusätzlich IN die Briefing-Datei stempeln. Der Workflow-State
    # liegt unter .claude/workflows/ und ist gitignored — er erreicht die CI
    # nie. Nur ein Stempel in der committeten Datei macht ein veraltetes
    # Briefing serverseitig erkennbar (scripts/ci_spec_gate.py).
    try:
        stamped = stamp_briefing_frontmatter(briefing, str(data.get("spec_file", "")),
                                             sha, frozen_sha)
        briefing_path.write_text(stamped)
        entry["briefing_sha256"] = _hashlib.sha256(stamped.encode("utf-8")).hexdigest()
    except Exception as exc:
        print(
            f"WARNUNG: Briefing registriert, aber Frontmatter-Stempel fehlgeschlagen ({exc}). "
            "Das CI-Gate kann die Aktualität dann nicht prüfen.",
            file=sys.stderr,
        )
    _save_active(data)

    print(f"PO-Briefing registriert für Workflow {name}: {rel}")


def cmd_set_affected_files(args: list[str]) -> None:
    replace = "--replace" in args
    files = [a for a in args if a != "--replace"]
    data, name = _read_active()
    if replace:
        data["affected_files"] = files
    else:
        existing = set(data.get("affected_files", []))
        existing.update(files)
        data["affected_files"] = sorted(existing)
    _save_active(data)
    print(f"Set affected_files on workflow {name}: {len(data['affected_files'])} files")


def cmd_add_artifact(args: list[str]) -> None:
    if len(args) < 4:
        print("Usage: workflow.py add-artifact <type> <path> <desc> <phase>", file=sys.stderr)
        sys.exit(1)
    art_type, art_path, desc, phase = args[0], args[1], args[2], args[3]
    if art_type not in VALID_ARTIFACT_TYPES:
        print(
            f"Invalid artifact type: '{art_type}'\n"
            f"Valid types: {', '.join(sorted(VALID_ARTIFACT_TYPES))}",
            file=sys.stderr,
        )
        sys.exit(1)
    data, _ = _read_active()
    data.setdefault("test_artifacts", []).append({
        "type": art_type,
        "path": art_path,
        "description": desc,
        "phase": phase,
        "created": datetime.now().isoformat(),
    })
    _save_active(data)
    print(f"Artifact added to {data['name']}: {art_type} ({desc})")


def cmd_remove_artifact(args: list[str]) -> None:
    """Falsch registriertes Artefakt per Pfad entfernen (#387).

    Ohne diesen Weg blockiert tdd_enforcement dauerhaft: add-artifact haengt nur
    an, und set-field darf test_artifacts nicht setzen.
    """
    if not args:
        print("Usage: workflow.py remove-artifact <path> [<phase>]", file=sys.stderr)
        sys.exit(1)
    art_path = args[0]
    phase = args[1] if len(args) > 1 else None
    data, _ = _read_active()
    arts = data.get("test_artifacts", [])
    keep = [
        a for a in arts
        if not (a.get("path") == art_path and (phase is None or a.get("phase") == phase))
    ]
    removed = len(arts) - len(keep)
    if not removed:
        print(f"Kein Artefakt mit Pfad '{art_path}' in {data['name']} gefunden.", file=sys.stderr)
        sys.exit(1)
    data["test_artifacts"] = keep
    _save_active(data)
    print(f"{removed} Artefakt(e) aus {data['name']} entfernt: {art_path}")


def cmd_mark_red(args: list[str]) -> None:
    result = " ".join(args) if args else "failed"
    data, name = _read_active()
    data["red_test_done"] = True
    data["red_test_result"] = result
    _save_active(data)
    print(f"RED unit test marked done: {result}")


def cmd_mark_ui_red(args: list[str]) -> None:
    result = " ".join(args) if args else "failed"
    data, name = _read_active()
    data["ui_test_red_done"] = True
    data["ui_test_red_result"] = result
    _save_active(data)
    print(f"RED UI test marked done: {result}")


def cmd_write_log(args: list[str]) -> None:
    data, name = _read_active()
    log_file = _write_execution_log(data, name, args[0] if args else "success")
    print(f"Execution log written: {log_file}")


def _write_execution_log(data: dict, name: str, outcome: str = "success") -> Path:
    """Execution-Log fuer `data`/`name` schreiben (aus `cmd_write_log`, #691)."""
    log_dir = find_project_root() / ".claude" / "workflows" / "_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"{date_str}_{name}.yaml"
    # `phase_log` ist die verlaessliche Quelle fuer besuchte Phasen (Issue #111):
    # Die Startphase eines Workflows taucht in `phase_transitions` nur als `from` auf,
    # nie als `to` — aus dem `to`-Feld gebaut galt `phase1_context` systematisch als
    # uebersprungen. `_log_phase_transition()` wird dagegen von jedem Codepfad gerufen.
    phases_visited = {
        e.get("phase") for e in data.get("phase_log", []) if isinstance(e, dict)
    }
    phases_visited.discard(None)
    phases_visited.add(data.get("current_phase", "phase0_idle"))
    phases_completed = [p for p in PHASES if p in phases_visited and p != "phase0_idle"]
    impl_idx = PHASES.index("phase6_implement")
    expected = PHASES[1:impl_idx + 1]
    phases_skipped = [p for p in expected if p not in phases_visited]
    # "nie gesetzt" != "explizit 0" (#278): beide Kennzahlen schreibt erst `stamp`.
    persisted = "adversary_findings_total" in data
    findings_total = data["adversary_findings_total"] if persisted else "unbekannt"
    files_changed = len(data.get("affected_files", [])) if persisted else "unbekannt"
    final = _final_loc(data)
    loc_delta = f"+{final[0]}" if final else data.get("loc_delta_current", "+0")
    lines = [
        f"workflow_id: {name}",
        f"project: {find_project_root().name}",
        f"completed_at: {datetime.now().isoformat()}",
        "phases_completed:",
    ] + [f"  - {p}" for p in phases_completed] + [
        "phases_skipped:",
    ] + [f"  - {p}" for p in phases_skipped] + [
        f"override_used: {bool(data.get('adversary_ambiguous_override'))}",
        f"tdd_red_confirmed: {bool(data.get('red_test_done') or data.get('ui_test_red_done'))}",
        f"adversary_verdict: {data.get('adversary_verdict') or 'none'}",
        f"adversary_findings_total: {findings_total}",
        f"adversary_fix_loop_iterations: {data.get('fix_loop_iterations', 0)}",
        f"scope_files_changed: {files_changed}",
        f"scope_loc_delta: {loc_delta}",
        f"effort_budget_exceeded: {len(data.get('budget_events', []))}",
        f"outcome: {outcome}",
    ]
    log_file.write_text("\n".join(lines) + "\n")
    return log_file


def cmd_override_ambiguous(args: list[str]) -> None:
    if not args:
        print("Usage: workflow.py override-ambiguous <reason>", file=sys.stderr)
        sys.exit(1)
    reason = " ".join(args)
    data, name = _read_active()
    data["adversary_ambiguous_override"] = {
        "reason": reason,
        "at": datetime.now().isoformat(),
    }
    _save_active(data)
    print(f"AMBIGUOUS override set for {name}: {reason}")


def cmd_complete(args: list[str]) -> None:
    data, name = _read_active()
    log_dir = find_project_root() / ".claude" / "workflows" / "_log"
    if not (log_dir.exists() and any(log_dir.glob(f"*_{name}.yaml"))):
        print(f"BLOCKED: No execution log for '{name}'. Run: workflow.py write-log [outcome]",
              file=sys.stderr)
        sys.exit(1)
    # Must run the same prerequisite/adversary-verdict check as an explicit
    # `phase phase8_complete` transition — this is the only completion path
    # actually used in practice (write-log → complete), so skipping this
    # check here silently defeats the adversary gate. See issue #960.
    error = _validate_transition(data, "phase8_complete")
    if error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        sys.exit(1)
    data["current_phase"] = "phase8_complete"
    data.pop("waiting_on", None)  # #550: Phasenwechsel leert den Wartezustand
    _mark_ship_open(data)  # #612
    try:  # #250 B: Messung blockiert den Abschluss nie
        final = _final_loc(data)
        if final is not None:
            data["loc_delta_final"], data["loc_delta_test_final"] = final
    except Exception:
        pass
    _finalize_archive(data, name)
    print(f"Workflow {name} completed and archived.")


def _auftrag_mark_issue(data: dict, name: str) -> None:
    """#551: Issue im Auftrag abhaken; aendert weder Ausgabe noch Exit."""
    try:
        issue = workflow_issue_number(data) or workflow_issue_number({"name": name})
        if issue:
            auftrag_mark_done(find_project_root(), issue)
    except Exception:
        pass


def _finalize_archive(data: dict, name: str, clear_active: bool = True) -> None:
    """Abschluss wie `complete` (#691): archivieren, Arbeitsdatei loeschen, Aktiv-Zeiger
    nur bei `clear_active` loeschen, dann Issue im Auftrag abhaken."""
    archive = _archive_dir()
    archive.mkdir(parents=True, exist_ok=True)
    _atomic_write(archive / f"{name}.json", data)
    wf_file = _workflow_file(name)
    if wf_file.exists():
        wf_file.unlink()
    if clear_active:
        link = _active_link()
        if link.is_symlink():
            link.unlink()
        _persist_env(None)
        _herdr("clear")
    _auftrag_mark_issue(data, name)


def cmd_abandon(args: list[str]) -> None:
    """Bricht den aktiven Workflow ehrlich ab — ohne Abschluss-Gates.

    Fuer Workflows OHNE Pruefgegenstand (reine Analyse-/Kontext-Arbeit, nie
    in phase6_implement): `complete` verlangt ein Adversary-Verdict, das es
    hier nie geben kann; der bisher einzige Ausweg war eine Typ-
    Umklassifizierung — genau das Gaming-Muster, das die Gates verhindern
    sollen (Issue #82). `abandon` archiviert stattdessen mit status
    'abandoned' + Pflicht-Begruendung: sichtbar bleibt, dass hier KEIN
    Nachweis gefuehrt wurde.
    """
    reason = ""
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "--reason" and i + 1 < len(args):
            reason = args[i + 1]
            i += 2
        else:
            rest.append(args[i])
            i += 1
    if not reason:
        reason = " ".join(rest).strip()
    if not reason:
        print("Usage: workflow.py abandon --reason \"<warum kein Abschluss>\"", file=sys.stderr)
        print("  Die Begruendung ist Pflicht — sie ersetzt den fehlenden Nachweis.", file=sys.stderr)
        sys.exit(1)

    data, name = _read_active()
    data["status"] = "abandoned"
    data["abandon_reason"] = reason
    data["abandoned_at"] = datetime.now().isoformat()
    _claim_release(data, name)  # #461: Abbruch gibt das Issue frei
    archive = _archive_dir()
    archive.mkdir(parents=True, exist_ok=True)
    _atomic_write(archive / f"{name}.json", data)
    wf_file = _workflow_file(name)
    if wf_file.exists():
        wf_file.unlink()
    link = _active_link()
    if link.is_symlink():
        link.unlink()
    _persist_env(None)
    _herdr("clear")
    print(f"Workflow {name} abgebrochen (abandoned) und archiviert — NICHT abgeschlossen.")
    print(f"  Grund: {reason}")


def cmd_no_build(args: list[str]) -> None:
    """Haelt die PO-Entscheidung "nichts bauen" fest (#424).

    Nur in phase1_context/phase2_analyse; danach nennt next_step() /99-reset,
    das den Workflow per `abandon` archiviert.
    """
    reason = ""
    if len(args) >= 2 and args[0] == "--reason":
        reason = args[1].strip()
    if not reason:
        print("Usage: workflow.py no-build --reason \"<warum nichts gebaut wird>\"", file=sys.stderr)
        print("  Die Begruendung ist Pflicht.", file=sys.stderr)
        sys.exit(1)
    data, name = _read_active()
    phase = data.get("current_phase")
    if phase not in _NO_BUILD_PHASES:
        print(
            f"BLOCKED: no-build nur in phase1_context/phase2_analyse erlaubt "
            f"(aktuell: {phase}). Spaeter gilt der normale Abschluss.",
            file=sys.stderr,
        )
        sys.exit(1)
    data["no_build_reason"] = reason
    _save_active(data)
    print(f"Workflow {name}: nichts bauen vermerkt. Naechster Schritt: /99-reset")
    print(f"  Grund: {reason}")


def cmd_phase_log(args: list[str]) -> None:
    data, name = _read_active()
    log = data.get("phase_log", [])
    if not log:
        print("Kein Phase-Log vorhanden (Workflow vor v3.2 gestartet oder noch keine Phase-Transitions).")
        return
    SEP = "─" * 52
    print(f"Workflow: {name}")
    print(SEP)
    print(f"  {'Phase':<26} {'Dauer':>9}  Status")
    total_min = 0.0
    longest_phase = None
    longest_dur = 0.0
    for entry in log:
        phase = entry.get("phase", "?")
        dur = entry.get("duration_min")
        exited = entry.get("exited_at")
        if exited is None:
            status = "[aktiv]"
            dur_str = "–"
        else:
            dur_val = dur if dur is not None else 0.0
            total_min += dur_val
            dur_str = f"{dur_val:.1f} min"
            status = "✓"
            if dur_val > longest_dur:
                longest_dur = dur_val
                longest_phase = phase
        print(f"  {phase:<26} {dur_str:>9}  {status}")
    print(SEP)
    print(f"  Gesamt (abgeschlossen): {total_min:.1f} min")
    if longest_phase:
        print(f"  Längste Phase: {longest_phase} ({longest_dur:.1f} min) ▲")


def cmd_list(args: list[str]) -> None:
    wf_dir = _workflows_dir()
    if not wf_dir.exists():
        print("No workflows.")
        return
    from hook_utils import resolve_active_workflow
    active_name, _source = resolve_active_workflow()
    for f in sorted(wf_dir.glob("*.json")):
        data = _read_workflow(f)
        name = data.get("name", f.stem)
        phase = data.get("current_phase", "?")
        marker = " *" if name == active_name else ""
        print(f"  {name}: {PHASE_NAMES.get(phase, phase)}{marker}")


def _deploy_steps(value) -> "list[str]":
    """`deploy.<feld>` als Liste von Befehlen (String oder Liste von Strings)."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _deploy_block() -> dict:
    """`deploy:`-Block der Projekt-Config, sonst {} (#81)."""
    try:
        from config_loader import load_config
        block = load_config().get("deploy") or {}
    except Exception:
        block = {}
    return block if isinstance(block, dict) else {}


def _deploy_config_steps(block: dict) -> "dict[str, list[str]]":
    """`deploy:`-Block als {command, verify, rollback} -> Befehlsliste (#81, #478)."""
    return {k: _deploy_steps(block.get(k)) for k in ("command", "verify", "rollback")}


def _deploy_is_configured(steps: dict) -> bool:
    """Deploy gilt als beschrieben, wenn `command` UND `verify` gesetzt sind."""
    return bool(steps.get("command") and steps.get("verify"))


def deploy_configured() -> bool:
    """Gleiche Regel wie `DEPLOY_CONFIGURED=yes` (#478); jede Ausnahme -> False."""
    try:
        return _deploy_is_configured(_deploy_config_steps(_deploy_block()))
    except Exception:
        return False


def deploy_mode() -> str:
    """Deploy-Modus fuer den Plan (#510): "configured" | "unconfigured" | "off".

    "off" nur bei explizit `deploy.enabled: false`; "configured" nach der Regel
    aus #478 (`command` UND `verify`); jede Ausnahme -> "unconfigured".
    """
    try:
        block = _deploy_block()
        if block.get("enabled") is False:
            return "off"
        if _deploy_is_configured(_deploy_config_steps(block)):
            return "configured"
    except Exception:
        pass
    return "unconfigured"


DEPLOY_STATUS_VALUES = ("running", "done", "failed")


def _mark_ship_open(data: dict) -> None:
    """Auslieferung als offen vermerken (#612), einmalig beim Erreichen von Phase 8.

    Ohne Build (`no_build_reason`) oder bei Abbruch gibt es nichts auszuliefern;
    ein schon gesetzter Marker (z. B. `done` vor einem erneuten `complete`) bleibt.
    """
    if data.get("no_build_reason") or data.get("status") == "abandoned":
        return
    if "ship_status" not in data:
        data["ship_status"] = "open"


def _ship_fallback_target() -> "tuple[Path, dict, str] | None":
    """Juengster archivierter Workflow mit nicht abgeschlossener Auslieferung (#612).

    `complete` archiviert den Workflow, bevor Push, PR und CI durch sind;
    `ship-status` ohne Nummer muss ihn trotzdem noch finden — auch nach einem
    `failed`, damit ein erneuter `ship.py`-Lauf den Stand weiterfuehrt (F001).
    """
    folder = _archive_dir()
    if not folder.is_dir():
        return None
    hits = []
    for f in folder.glob("*.json"):
        try:
            data = _read_workflow(f)
        except (Exception, SystemExit):
            continue
        if isinstance(data, dict) and data.get("ship_status") in SHIP_PENDING_VALUES:
            hits.append((f.stat().st_mtime, f, data))
    if not hits:
        return None
    _, path, data = max(hits, key=lambda t: t[0])
    return path, data, data.get("name") or path.stem


def cmd_ship_status(args: list[str]) -> None:
    """`ship-status <running|done|failed|skipped> [<issue-nr|name>] [--note <Text>]` (#612).

    Setzt `ship_status`/`ship_at` (und `ship_note`) im Workflow-State — ohne
    zweites Argument im aktiven Workflow, ersatzweise im juengsten archivierten
    mit offener Auslieferung, sonst im laufenden oder archivierten Treffer.
    Solange der Stand `open`/`running`/`failed` ist, zeigen Plan, Fusszeile und
    Seitenleiste ⏳ bzw. ❗ statt ✅. Rein informativ, keine Gate-Wirkung.
    `scripts/ship.py` ruft den Befehl selbst auf.
    """
    split = _split_note_arg(args)
    rest, note = split if split is not None else ([], None)
    if not rest or rest[0] not in SHIP_STATUS_VALUES:
        print("Usage: workflow.py ship-status <running|done|failed|skipped> [<issue-nr|name>]"
              " [--note <Text>]", file=sys.stderr)
        sys.exit(1)
    value = rest[0]
    is_active = False
    if len(rest) > 1:
        path, data, name = _status_target(rest[1])
        is_active = name == _active_name_quiet()
    else:
        try:
            data, name = _read_active()
            path = _workflow_file(name)
            is_active = True
        except SystemExit:
            found = _ship_fallback_target()
            if found is None:
                print("KEIN aktiver Workflow und kein archivierter mit offener Auslieferung"
                      " — Issue-Nummer oder Name angeben.", file=sys.stderr)
                sys.exit(1)
            path, data, name = found
    from datetime import timezone
    data["ship_status"] = value
    data["ship_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    note = " ".join((note or "").split())
    if note:
        data["ship_note"] = note
    else:
        data.pop("ship_note", None)
    if value in ("done", "skipped"):
        _claim_release(data, name)  # #461: Ende der Auslieferung gibt das Issue frei
    _atomic_write(path, data)
    try:  # Seitenleiste zeigt den neuen Stand, fail-open (wie `waiting`, #555)
        _herdr("report", {"name": name, **data})
    except Exception:
        pass
    print(f"SHIP_STATUS={value} ({name})")
    if value in ("done", "skipped"):
        _ship_finalize(path, data, name, is_active)


def _ship_finalize(path: Path, data: dict, name: str, is_active: bool) -> None:
    """#691: Auslieferung fertig -> Workflow in Phase 8 abschliessen, fail-open.

    Archiviertes Ziel: nur abhaken (idempotent). Laufendes Ziel in
    `phase8_complete`: Log falls fehlend, archivieren, abhaken, `ARCHIVED=<name>`.
    Sonst nichts. Fehler aendern weder Ausgabe noch Exit-Code."""
    try:
        if path.parent.resolve() == _archive_dir().resolve():
            _auftrag_mark_issue(data, name)
            return
        if data.get("current_phase") != "phase8_complete":
            return
        log_dir = find_project_root() / ".claude" / "workflows" / "_log"
        if not (log_dir.is_dir() and any(log_dir.glob(f"*_{name}.yaml"))):
            _write_execution_log(data, name)
        _finalize_archive(data, name, clear_active=is_active)
        print(f"ARCHIVED={name}")
    except (Exception, SystemExit):
        pass


def _deploy_status_target(ref: str) -> "Path | None":
    """Workflow-Datei zu Issue-Nummer oder Name (#510): erst laufend, dann Archiv."""
    ref = ref.lstrip("#")
    pat = _re.compile(rf"(^|[-_]){_re.escape(ref)}([-_]|$)") if ref.isdigit() else None

    def hits(folder: Path) -> "list[Path]":
        if not folder.is_dir():
            return []
        return [f for f in folder.glob("*.json")
                if f.stem == ref or (pat is not None and pat.search(f.stem))]

    running = sorted(hits(_workflows_dir()))
    if running:
        return _pick_running_target(running, ref)
    archived = hits(_archive_dir())
    if archived:
        return max(archived, key=lambda f: f.stat().st_mtime)  # juengster gewinnt
    return None


def _active_name_quiet() -> "str | None":
    """Name des aktiven Workflows oder None, ohne Abbruch und ohne Meldung."""
    import contextlib
    import io
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            return _read_active()[1]
    except (Exception, SystemExit):
        return None


def _pick_running_target(running: "list[Path]", ref: str) -> Path:
    """Rangfolge unter laufenden Treffern (#647/#648 Nebenbefund): exakter Name,
    aktiver Workflow, nicht phase8_complete, dann juengster nach mtime."""
    exact = [f for f in running if f.stem == ref]
    if exact:
        return exact[0]
    if len(running) == 1:
        return running[0]
    active = _active_name_quiet()
    for f in running:
        if active and f.stem == active:
            return f

    def open_(f: Path) -> bool:
        try:
            return read_state_json(f).get("current_phase") != "phase8_complete"
        except Exception:
            return False

    candidates = [f for f in running if open_(f)] or running
    return max(candidates, key=lambda f: f.stat().st_mtime)


def _split_note_arg(args: list[str]) -> "tuple[list[str], str | None] | None":
    """`--note <Grund>` aus den Argumenten loesen (#561): (Rest, Text oder None);
    `--note` ohne folgendes Argument -> None."""
    if "--note" not in args:
        return list(args), None
    idx = args.index("--note")
    if idx + 1 >= len(args):
        return None
    return args[:idx] + args[idx + 2:], args[idx + 1]


def cmd_deploy_status(args: list[str]) -> None:
    """`deploy-status <running|done|failed> [<issue-nr|name>] [--note <Grund>]` (#510).

    Setzt `deploy_status`/`deploy_at` im Workflow-State — ohne zweites Argument
    im aktiven Workflow, sonst im laufenden oder (juengsten) archivierten Treffer.
    `--note` schreibt `deploy_note` als Einzeiler; ohne `--note` (oder mit leerem
    Text) entfaellt eine alte Notiz (#561). Rein informativ, keine Gate-Wirkung.
    """
    split = _split_note_arg(args)
    rest, note = split if split is not None else ([], None)
    if not rest or rest[0] not in DEPLOY_STATUS_VALUES:
        print("Usage: workflow.py deploy-status <running|done|failed> [<issue-nr|name>]"
              " [--note <Grund>]", file=sys.stderr)
        sys.exit(1)
    value = rest[0]
    path, data, name = _status_target(rest[1] if len(rest) > 1 else None)
    from datetime import timezone
    data["deploy_status"] = value
    data["deploy_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    note = " ".join((note or "").split())
    if note:
        data["deploy_note"] = note
    else:
        data.pop("deploy_note", None)
    _atomic_write(path, data)
    print(f"DEPLOY_STATUS={value} ({name})")


def _status_target(ref: "str | None") -> "tuple[Path, dict, str]":
    """Ziel fuer deploy-status/waiting/endstate (#510, #550): ohne `ref` der aktive
    Workflow, sonst laufend oder (juengster) archivierter Treffer; kein Treffer -> Exit 1."""
    if ref is None:
        data, name = _read_active()
        return _workflow_file(name), data, name
    path = _deploy_status_target(ref)
    if path is None:
        print(f"KEIN Workflow fuer '{ref}' (laufend oder im Archiv).", file=sys.stderr)
        sys.exit(1)
    data = _read_workflow(path)
    return path, data, data.get("name") or path.stem


def deploy_autonomous() -> bool:
    """`deploy.autonomous: true` in der Projekt-Config (#550); jede Ausnahme -> False."""
    try:
        return _deploy_block().get("autonomous") is True
    except Exception:
        return False


def cmd_waiting(args: list[str]) -> None:
    """`waiting "<worauf>" [<issue-nr|name>]` / `waiting --clear [...]` (#550).

    Setzt bzw. loescht `waiting_on` (CI, Hintergrund-Agent, Server). Solange es
    gesetzt ist, liefert `end_state` den Zustand ⏳; jeder Phasenwechsel leert es.
    Rein informativ, keine Gate-Wirkung.
    """
    if not args or not args[0].strip():
        print('Usage: workflow.py waiting "<worauf>" | --clear [<issue-nr|name>]',
              file=sys.stderr)
        sys.exit(1)
    path, data, name = _status_target(args[1] if len(args) > 1 else None)
    if args[0] == "--clear":
        data.pop("waiting_on", None)
    else:
        data["waiting_on"] = _one_line(args[0])
    _atomic_write(path, data)
    try:  # #555: Seitenleiste zeigt den neuen Stand, fail-open
        _herdr("report", {"name": name, **data})
    except Exception:
        pass
    print(f"WAITING_ON={data.get('waiting_on', '')} ({name})")


def cmd_endstate(args: list[str]) -> None:
    """`endstate [#N|name]` (#550): Endzustand fuer Chat-Fusszeile, wie im Plan.

    Ohne Argument der aktive Workflow, sonst laufend oder archiviert (der
    Abschluss-Turn laeuft nach `complete`). Ausgabe `ENDSTATE=<kind>` und
    `FOOTER=<line>`; kein Treffer -> Meldung auf stderr, Exit 1. Nur hier holt
    der Vorschlag (#589) Netzdaten; steht er in der Zeile, folgen
    `SUGGEST_ISSUE=`, `SUGGEST_SOURCE=` und `SUGGEST_REASON=`.
    """
    path, data, name = _status_target(args[0] if args else None)
    data = dict(data)
    data.setdefault("name", name)
    kw = {"archived": path.parent == _archive_dir(), "deploy": deploy_mode(),
          "autonomous": deploy_autonomous()}
    queue = queue_end_args(data)
    plain = {**queue, "suggest": None}
    if queue.get("queue_next") is None and end_state(data, **kw, **plain)["kind"] == "done":
        if _refresh_suggestion(data, queue):
            queue = queue_end_args(data)
            plain = {**queue, "suggest": None}
    state = end_state(data, **kw, **queue)
    print(f"ENDSTATE={state['kind']}")
    print(f"FOOTER={state['line']}")
    if data.get("ship_status"):  # #612: nur mit Marker, sonst Ausgabe wie bisher
        print(f"SHIP_STATUS={data['ship_status']}")
    suggest = queue.get("suggest")
    if suggest and suggest.get("source") == "epic-leer" and state["kind"] == "done":
        # #610: Sitzungs-Epic ohne freies Kind — keine Nummer, kein Ersatzvorschlag
        print("SUGGEST_SOURCE=epic-leer")
        print(f"SUGGEST_EPIC={suggest.get('epic')}")
        print(f"SUGGEST_REASON={suggest['reason']}")
    elif suggest and state != end_state(data, **kw, **plain):
        print(f"SUGGEST_ISSUE={suggest['n']}")
        print(f"SUGGEST_SOURCE={suggest['source']}")
        print(f"SUGGEST_REASON={suggest['reason']}")


def _session_scope() -> "dict | None":
    """Sitzungs-Epic und belegte Issues aus herdr (#610); None ausserhalb. Wirft nie."""
    try:
        import herdr_bridge
        return herdr_bridge.session_scope()
    except Exception:
        return None


def _in_herdr_session() -> bool:
    """Aktive herdr-Sitzung mit Workspace (#610); jede Ausnahme -> False."""
    try:
        import herdr_bridge
        return bool(os.environ.get("HERDR_WORKSPACE_ID", "").strip()) \
            and herdr_bridge._pane() is not None
    except Exception:
        return False


def _refresh_suggestion(data: dict, queue: dict) -> bool:
    """Vorschlags-Rohdaten (#589) aus dem Cache, sonst per `gh api` holen und cachen.

    Autarker Auftrag ohne naechstes Issue und Quelle Epic/Meilenstein/Spur (#591):
    Nummer idempotent an den Auftrag haengen (Kette #551). True, wenn Rohdaten vorliegen.
    Fail-open, wirft nie; Kill-Switch `next_suggestion.enabled: false`.
    """
    try:
        import next_suggestion
        cfg = next_suggestion.settings()
        done = _queue_number(workflow_issue_number(data))
        if not cfg["enabled"] or done is None:
            return False
        root = find_project_root()
        raw = next_suggestion.read_cache(root, done, ttl_s=cfg["cache_ttl_s"])
        if raw is None:
            scope = _session_scope()
            if scope is None and _in_herdr_session():
                # Adversary F002: in herdr ohne lesbaren Workspace ist das Sitzungs-Epic
                # unbekannt — lieber kein Vorschlag als einer ausserhalb des Epics.
                return False
            raw = next_suggestion.fetch(root, done, timeout_s=cfg["timeout_s"], scope=scope)
            if raw is None:
                return False
            next_suggestion.write_cache(root, done, raw)
        suggest = next_suggestion.choose(raw, done, _suggest_claimed(), spur=_auftrag_spur())
        if suggest and queue.get("autark") is True \
                and suggest["source"] in ("epic", "milestone", "spur"):
            auftrag = read_auftrag(root)
            if auftrag and auftrag["autark"] is True \
                    and all(e["n"] != suggest["n"] for e in auftrag["issues"]):
                auftrag["issues"].append({"n": suggest["n"], "status": "open"})
                write_auftrag(root, auftrag)
        return True
    except Exception:
        return False


def cmd_deploy_config(args: list[str]) -> None:
    """Deploy-Ablauf des Projekts aus `deploy:` in der Projekt-Config (#81). Rein lesend.

    Ausgabe immer mit Rueckgabecode 0; `DEPLOY_CONFIGURED=yes` nur, wenn
    `command` UND `verify` gesetzt sind — ohne Nachpruefung gilt ein Deploy
    nicht als beschrieben. `/70-deploy` verzweigt auf dieser Zeile.
    """
    block = _deploy_block()
    steps = _deploy_config_steps(block)
    configured = _deploy_is_configured(steps)
    print(f"DEPLOY_CONFIGURED={'yes' if configured else 'no'}")
    for key in ("command", "verify", "rollback"):
        if steps[key]:
            for line in steps[key]:
                print(f"{key}: {line}")
        else:
            print(f"{key}: (nicht gesetzt)")
    print(f"autonomous: {'true' if block.get('autonomous') is True else 'false'}")
    if not configured:
        # #372: eine Root-config.yaml nur mit `deploy:` gilt als App-Config und
        # wird uebergangen — sonst traegt /70-deploy dort ein und dreht sich im Kreis.
        try:
            from config_loader import skipped_app_config_note
            note = skipped_app_config_note()
        except Exception:
            note = ""
        if note:
            print(f"HINWEIS: {note}")

def cmd_find(args: list[str]) -> None:
    """Laufende Workflows zu einer Issue-Nummer (Wiedereinstieg nach /clear, #276).

    Rein lesend. Ersetzt den frueheren Python-Heredoc in /50-implement Step 0,
    den bash_gate als Marker-Manipulation blockte (Feldname + State-Pfad).
    """
    if not args:
        print("Usage: workflow.py find <issue-nummer>", file=sys.stderr)
        sys.exit(1)
    issue = args[0].lstrip("#")
    pat = _re.compile(rf"(^|[-_]){_re.escape(issue)}([-_]|$)")
    wf_dir = _workflows_dir()
    hits = []
    for f in sorted(wf_dir.glob("*.json")) if wf_dir.exists() else []:
        if pat.search(f.stem):
            d = _read_workflow(f)
        else:
            # #513: Treffer auch ueber das State-Feld `issue_number`
            try:
                d = _read_workflow(f)
            except Exception:
                continue
            if workflow_issue_number(d) != issue:
                continue
        hits.append((f.stem, d.get("current_phase"), d.get("spec_file") or "Not created",
                     d.get("adversary_verdict"), d.get("affected_files") or []))
    if not hits:
        print(f"KEIN laufender Workflow fuer #{issue} "
              "(evtl. abgeschlossen -> .claude/workflows/_archive/).")
        return
    for name, ph, spec, verd, aff in hits:
        print(f"GEFUNDEN: {name} | Phase={ph} | Spec={spec} | Verdict={verd}")
        if aff:
            print(f"  affected_files: {', '.join(aff)}")
    print("\nNAME=" + hits[0][0])


def _approvals_fallback_data() -> dict:
    """Juengster archivierter Workflow mit `ship_status` done/skipped (#691 F001), sonst {}."""
    folder = _archive_dir()
    hits = []
    for f in (folder.glob("*.json") if folder.is_dir() else []):
        try:
            data = _read_workflow(f)
        except (Exception, SystemExit):
            continue
        if isinstance(data, dict) and data.get("ship_status") in ("done", "skipped"):
            hits.append((f.stat().st_mtime, data))
    return max(hits, key=lambda t: t[0])[1] if hits else {}


def cmd_approvals(args: list[str]) -> None:
    """`approvals [--auto] [<issue-nr|name>]`: Freigabe-Protokoll anzeigen (#472). Nur Anzeige.

    stdout: `APPROVALS=<n>`, danach je Eintrag `- <gate> | <by> | <at> | <reason>`.
    `--auto` zeigt nur automatische Freigaben (`by == "auto"`). Ziel: laufender
    oder archivierter Treffer; ohne Ziel der aktive Workflow, ersatzweise der
    juengste archivierte mit `ship_status` done/skipped (#691 F001: `ship-status
    done` archiviert vorher). Exit immer 0 — ohne Treffer `APPROVALS=0`.
    """
    import contextlib
    import io
    refs = [a for a in args if a != "--auto"]
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            if refs:
                data = _status_target(refs[0])[1]
            else:
                try:
                    data = _read_active()[0]
                except SystemExit:
                    data = _approvals_fallback_data()
        entries = data.get("approvals") or []
    except (SystemExit, Exception):
        entries = []
    if not isinstance(entries, list):
        entries = []
    rows = [e for e in entries if isinstance(e, dict)
            and ("--auto" not in args or e.get("by") == "auto")]
    print(f"APPROVALS={len(rows)}")
    for e in rows:
        print("- " + " | ".join(_flat_line(e.get(k) or "-")
                                for k in ("gate", "by", "at", "reason")))


def _retro_load_log(name: str) -> dict:
    """Load execution log YAML for a workflow by name. Returns {} if not found."""
    log_dir = find_project_root() / ".claude" / "workflows" / "_log"
    if not log_dir.exists():
        return {}
    matches = sorted(log_dir.glob(f"*_{name}.yaml"))
    if not matches:
        return {}
    lines = matches[-1].read_text().splitlines()
    result: dict = {}
    for line in lines:
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def cmd_retro_list(args: list[str]) -> None:
    """List all archived workflows with basic stats."""
    archive = _archive_dir()
    if not archive.exists() or not list(archive.glob("*.json")):
        print("Keine abgeschlossenen Workflows im Archiv.")
        return
    SEP = "─" * 68
    print(SEP)
    print(f"  {'Name':<28} {'Typ':<14} {'Datum':<12} {'Zeit':>7}  Ergebnis")
    print(SEP)
    files = sorted(archive.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files:
        data = _read_workflow(f)
        name = data.get("name", f.stem)
        wf_type = data.get("workflow_type", "feature")
        created = data.get("created", "")[:10]
        log = _retro_load_log(name)
        if data.get("status") == "abandoned":
            outcome = "abgebrochen"
        else:
            outcome = log.get("outcome", "–")
        total_min = sum(
            e.get("duration_min") or 0.0
            for e in data.get("phase_log", [])
            if e.get("exited_at") is not None
        )
        time_str = f"{total_min:.0f} min" if total_min > 0 else "–"
        print(f"  {name:<28} {wf_type:<14} {created:<12} {time_str:>7}  {outcome}")
    print(SEP)
    print(f"  {len(files)} Workflow(s) archiviert.")


def _retro_hints(data: dict, log: dict, total_min: float, longest_phase: str,
                 longest_dur: float, phases_skipped: list) -> list[str]:
    hints = []
    fix_loops = data.get("fix_loop_iterations", 0)
    if fix_loops > 0:
        hints.append(
            f"  ⚠  {fix_loops}x Fix-Loop in phase6b_adversary — deutet auf "
            "unvollstaendige Spec oder fehlende Edge Cases hin."
        )
    if longest_phase and total_min > 0 and longest_dur / total_min > 0.35:
        pct = round(longest_dur / total_min * 100)
        hints.append(
            f"  ⚠  {longest_phase} war mit {longest_dur:.1f} min die laengste "
            f"Phase ({pct}% der Gesamtzeit)."
        )
    if data.get("adversary_ambiguous_override"):
        reason = data["adversary_ambiguous_override"].get("reason", "–")
        hints.append(f"  ⚠  AMBIGUOUS-Override genutzt: \"{reason}\"")
    if phases_skipped:
        hints.append(f"  ℹ  Uebersprungene Phasen: {', '.join(phases_skipped)}")
    if not data.get("red_test_done") and not data.get("ui_test_red_done"):
        if data.get("workflow_type") != "feature-fast":
            hints.append("  ⚠  Kein TDD-RED-Artefakt registriert — "
                         "TDD-Disziplin nicht nachweisbar.")
    if not hints:
        hints.append("  ✓  Keine Optimierungshinweise — Workflow lief reibungslos.")
    return hints


def cmd_retro(args: list[str]) -> None:
    """Analyze an archived workflow. Uses most recent if no name given."""
    archive = _archive_dir()
    if not archive.exists():
        print("Kein Archiv gefunden — noch keine abgeschlossenen Workflows.")
        return

    if args:
        name = args[0]
        path = archive / f"{name}.json"
        if not path.exists():
            print(f"Workflow '{name}' nicht im Archiv gefunden.", file=sys.stderr)
            print("Verfuegbare Workflows: workflow.py retro-list", file=sys.stderr)
            sys.exit(1)
    else:
        files = sorted(archive.glob("*.json"), key=lambda f: f.stat().st_mtime)
        if not files:
            print("Kein abgeschlossener Workflow im Archiv.")
            return
        path = files[-1]
        name = path.stem

    data = _read_workflow(path)
    log = _retro_load_log(name)
    wf_type = data.get("workflow_type", "feature")
    created = data.get("created", "")[:10]

    SEP = "═" * 52
    sep = "─" * 52
    print(SEP)
    print(f"  RETRO: {name}")
    print(f"  Typ: {wf_type}  |  Gestartet: {created}")
    print(SEP)

    # Phase timeline
    phase_log = data.get("phase_log", [])
    total_min = 0.0
    longest_phase = None
    longest_dur = 0.0
    print()
    print("PHASEN-TIMELINE")
    print(sep)
    print(f"  {'Phase':<28} {'Dauer':>8}  Status")
    print(sep)
    for entry in phase_log:
        phase = entry.get("phase", "?")
        dur = entry.get("duration_min")
        exited = entry.get("exited_at")
        if exited is None:
            status = "[unterbrochen]"
            dur_str = "–"
        else:
            dur_val = dur if dur is not None else 0.0
            total_min += dur_val
            dur_str = f"{dur_val:.1f} min"
            status = "✓"
            if dur_val > longest_dur:
                longest_dur = dur_val
                longest_phase = phase
        print(f"  {phase:<28} {dur_str:>8}  {status}")
    print(sep)
    total_str = f"{total_min:.1f} min" if total_min > 0 else "–"
    print(f"  Gesamt: {total_str}", end="")
    if longest_phase:
        print(f"  |  Laengste Phase: {longest_phase} ({longest_dur:.1f} min) ▲")
    else:
        print()
    estimate_line = _retro_estimate_line(data)  # #620: Lernnachweis
    if estimate_line:
        print(estimate_line)

    # Quality signals
    verdict = data.get("adversary_verdict") or log.get("adversary_verdict") or "–"
    fix_loops = data.get("fix_loop_iterations", 0)
    findings = data.get("adversary_findings_total", 0)
    tdd_ok = data.get("red_test_done") or data.get("ui_test_red_done")
    override_used = bool(data.get("adversary_ambiguous_override"))
    affected = len(data.get("affected_files", []))
    loc_delta = data.get("loc_delta_current") or log.get("scope_loc_delta") or "–"
    outcome = log.get("outcome", "–")

    print()
    print("QUALITAETS-SIGNALE")
    print(sep)
    tdd_str = "✓ bestaetigt" if tdd_ok else ("– (fast-track)" if wf_type == "feature-fast" else "✗ fehlend")
    print(f"  TDD RED Artefakte:     {tdd_str}")
    print(f"  Adversary-Verdict:     {verdict}")
    print(f"  Fix-Loop-Iterationen:  {fix_loops}")
    print(f"  Adversary-Findings:    {findings}")
    print(f"  Override genutzt:      {'Ja' if override_used else 'Nein'}")
    print(f"  Scope:                 {affected} Datei(en), {loc_delta} LoC")
    print(f"  Ergebnis:              {outcome}")

    # Phases skipped
    phases_skipped_raw = log.get("phases_skipped", "")
    phases_skipped = [p.strip("- ") for p in phases_skipped_raw.split(",") if p.strip("- ")]

    # Optimization hints
    hints = _retro_hints(data, log, total_min, longest_phase, longest_dur, phases_skipped)
    print()
    print("OPTIMIERUNGS-HINWEISE")
    print(sep)
    for h in hints:
        print(h)
    print()


def cmd_cleanup_stale_locks(args: list[str]) -> None:
    """Remove pending_validation locks and approval markers of finished workflows.

    Ueber die Workflow-NAMEN, nicht ueber die Lock-Dateien: vorher iterierte
    das hier nur ueber `pending_validation_*.json` und loeschte den passenden
    Freigabe-Marker mit. Ein Freigabe-Marker OHNE gleichnamigen Lock war damit
    durch keinen Befehl erreichbar — im Framework-Repo selbst betraf das 6 von
    9 (Issue #135). Und liegenbleiben ist bei genau dieser Familie keine
    Kosmetik: das post_implementation_gate erkennt eine Freigabe allein an der
    Existenz einer nach dem Workflow benannten Datei (#134).
    """
    claude_dir = find_project_root() / ".claude"
    wf_dir = _workflows_dir()
    removed = []
    skipped = []

    names = {p.stem.replace("pending_validation_", "", 1)
             for p in claude_dir.glob("pending_validation_*.json")}
    names |= {p.name.replace("user_approved_validation_", "", 1)
              for p in claude_dir.glob("user_approved_validation_*")}

    for wf_name in sorted(n for n in names if n):
        # Active workflow still in progress?
        active_file = wf_dir / f"{wf_name}.json"
        if active_file.exists():
            try:
                data = _read_workflow(active_file)
                phase = data.get("current_phase", "")
                if phase == "phase6_implement":
                    skipped.append(f"  SKIPPED {wf_name} (aktiv in {phase})")
                    continue
            except UnsafeStateError as exc:
                # #416: unsicherer State → Sperren NICHT loeschen
                skipped.append(
                    f"  SKIPPED {wf_name} (unsicherer State: {exc.reason})")
                continue
            except Exception:
                pass
        # Archived or past phase6 → safe to remove
        for marker in (claude_dir / f"pending_validation_{wf_name}.json",
                       claude_dir / f"user_approved_validation_{wf_name}"):
            if marker.exists():
                marker.unlink(missing_ok=True)
                removed.append(f"  Removed: {marker.name}")
    if removed:
        print("\n".join(removed))
    if skipped:
        print("\n".join(skipped))
    if not removed and not skipped:
        print("Keine verwaisten Lock-Dateien gefunden.")


def _sessions_age(last_seen) -> str:
    """Alter von last_seen als kompakter Text."""
    if not isinstance(last_seen, (int, float)) or isinstance(last_seen, bool):
        return SESSIONS_PLACEHOLDER
    delta = max(0, int(time.time() - last_seen))
    if delta < 60:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta // 60}m"
    return f"{delta // 3600}h"


def _read_session_entries() -> list:
    """Registereintraege aus .claude/session-locks/*.json des eigenen Projekts.

    Nur eigene normale Dateien (#422): ein Verweis-Eintrag wird uebersprungen.
    """
    root = find_project_root()
    locks = root / ".claude" / "session-locks"
    entries: list = []
    if not locks.is_dir():
        return entries
    for f in sorted(locks.glob("*.json")):
        try:
            data = read_state_json(f, root)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("session_id"):
            entries.append(data)
    entries.sort(key=lambda e: e.get("started_at") or 0)
    return entries


def _flat_line(value) -> str:
    """Zeilenumbrueche platt machen, Schlusspunkt bleibt (#555: eigener Name statt
    zweiter `_one_line`, die die Endzeilen-Variante ueberschrieb)."""
    return " ".join(str(value).split())


def cmd_observable_surface(args: list[str]) -> None:
    """Auskunft, kein Gate: hat der Arbeitsstand eine beobachtbare Oberflaeche?

    Genau fuenf Zeilen auf stdout, Rueckgabecode IMMER 0 — `/60-validate` liest
    daraus nur, ob die Schlussfrage entfallen darf. Bewusst OHNE aktiven
    Workflow (kein `_read_active()`): gelesen wird der Arbeitsbaum, nicht der
    State. `ROOT=`/`CONFIG=` machen die Diskrepanz aus #153 sichtbar — Config
    aus dem Hauptrepo, Messung im Worktree.
    """
    try:
        from hook_utils import observable_surface_report
        report = observable_surface_report()
        surface = "no" if report.get("surface") is False else "yes"
        reason = _flat_line(report.get("reason") or "") or "unbekannt"
        files = int(report.get("files") or 0)
        root = _flat_line(report.get("root") or "")
    except Exception as exc:
        # Ein Absturz darf keine Rueckfrage unterdruecken: yes + sprechender Grund.
        surface, reason, files, root = "yes", f"internal-error {type(exc).__name__}", 0, ""
    try:
        from config_loader import config_source_note
        note = _flat_line(config_source_note() or "")
    except Exception:
        note = ""
    print(f"OBSERVABLE_SURFACE={surface}\nREASON={reason}\nFILES={files}\n"
          f"ROOT={root}\nCONFIG={note}")


def cmd_autonomy(args: list[str]) -> None:
    """Auskunft, kein Gate: genau eine Zeile `AUTONOMY=<mode>`, Exit immer 0 (#469).

    Bewusst ohne aktiven Workflow (kein `_read_active()`), Vorbild
    `cmd_observable_surface`.
    """
    try:
        mode = autonomy_mode()
    except Exception:
        mode = "manual"
    if mode not in ("auto", "manual"):
        mode = "manual"
    try:
        print(f"AUTONOMY={mode}")
    except Exception:
        pass


def cmd_auto_ship(args: list[str]) -> None:
    """Auskunft, kein Gate: genau eine Zeile `AUTO_SHIP=on|off`, Exit immer 0 (#525).

    Bewusst ohne aktiven Workflow, Vorbild `cmd_autonomy`.
    """
    try:
        state = "on" if auto_ship_enabled() else "off"
    except Exception:
        state = "off"
    try:
        print(f"AUTO_SHIP={state}")
    except Exception:
        pass


def cmd_autoclear(args: list[str]) -> None:
    """Kompatibilitaetszeile, kein Gate: genau `AUTO_CLEAR=off`, Exit immer 0.

    Das Herdr-Auto-`/clear` ist mit #663 entfernt: die Zeile bleibt nur fuer
    alte, aus dem Plugin-Cache gelieferte Befehlstexte (#489), die damit die
    Kette selbst fortsetzen.
    """
    try:
        print("AUTO_CLEAR=off")
    except Exception:
        pass


def _apply_spec_approval(data: dict, trigger: str) -> list:
    """Spec-Freigabe auf den State anwenden: Phase 3 → 4 (#470).

    Dieselben Felder wie der Listener-Pfad (`phase_listener.py`, Trigger
    "approval"): `spec_approved`, `phase_transitions`/`phase_log` ueber
    `record_transition`, `current_phase`. Speichert nicht selbst. Gibt neue
    Budget-Ueberschreitungen zurueck (wie `record_transition`).
    """
    data["spec_approved"] = True
    data.pop("spec_rework", None)  # #647
    exceeded = record_transition(data, "phase4_approved", trigger)
    data["current_phase"] = "phase4_approved"
    return exceeded


def _auto_approve_decision() -> "tuple[str, str, list]":
    """Pruefkette fuer `auto-approve` (#470): (verdict, reason, budget_exceeded).

    Erste Verfehlung ergibt "human" OHNE State-Aenderung. Nur bei "done" wird
    gespeichert. Gate-Einstellungen (ADR-/Briefing-Kill-Switch, max_words)
    kommen NUR aus `trusted_config()`, nie aus `settings.local.json` (F001/F002)
    oder einer Unterordner-Config (F008) — `config_loader.load_config` wird in
    der Entscheidung nicht aufgerufen (Architekturtest). Ausgenommen ist nur
    die Budget-Buchhaltung NACH der Entscheidung (`_apply_spec_approval` →
    `record_transition`), die das Verdict nicht beeinflusst.
    """
    config = trusted_config()
    if not isinstance(config, dict):
        return "human", "wirksame Config nicht lesbar", []
    if autonomy_mode() != "auto":
        return "human", "Modus manual", []
    try:
        data, _name = _read_active()
    except SystemExit:
        return "human", "kein aktiver Workflow", []
    if data.get("current_phase") != "phase3_spec":
        return "human", f"Phase {data.get('current_phase')} statt phase3_spec", []
    if not data.get("spec_file"):
        return "human", "keine Spec im Workflow", []
    if data.get("spec_approved"):
        return "human", "Spec bereits freigegeben", []
    spec_content = _read_spec_content(data)
    if spec_content is None:
        return "human", "Spec nicht lesbar", []
    adr_err = _check_adr(data, config)
    if adr_err:
        return "human", "ADR: " + adr_err, []
    briefing_err = _check_po_briefing(data, config)
    if briefing_err:
        return "human", "Briefing: " + briefing_err, []
    spec_err = _check_spec_content(data, config)
    if spec_err:
        return "human", "Spec: " + spec_err, []
    entry = data.get("po_briefing")
    if not (isinstance(entry, dict) and entry.get("file") and entry.get("briefing_sha256")):
        return "human", "kein Briefing mit Hash registriert", []
    # F002: Aktualitaet der Spec unabhaengig vom Briefing-Kill-Switch — der
    # gespeicherte Teil-Hash muss zum aktuellen gefrorenen Spec-Teil passen.
    frozen = entry.get("spec_frozen_sha256")
    if not frozen or frozen != frozen_spec_sha256(spec_content):
        return "human", "Spec nach set-briefing geaendert", []
    # F003: Briefing muss (nach Symlink-Aufloesung) im Projekt liegen.
    path = _briefing_path_inside_project(entry["file"])
    if path is None:
        return "human", "Briefing liegt ausserhalb des Projekts", []
    briefing = _read_briefing_file(path)  # F010: nur regulaere Datei ≤ 256 KiB
    if briefing is None:
        return "human", "Briefing nicht lesbar (keine regulaere Datei oder zu gross)", []
    briefing_sha = _hashlib.sha256(briefing.encode("utf-8")).hexdigest()
    if briefing_sha != entry["briefing_sha256"]:
        return "human", "Briefing nach set-briefing geaendert", []
    ampel = parse_ampel(briefing)
    if ampel != "green":
        return "human", "Ampel rot", []
    exceeded = _apply_spec_approval(data, "auto")
    record_approval(
        data, "spec", "auto", "Ampel gruen im PO-Briefing",
        evidence={
            "briefing": entry["file"],
            "briefing_sha256": briefing_sha,
            "spec_sha256": spec_sha256(spec_content),
            "ampel": ampel,
        },
    )
    _save_active(data)
    return ("done", f"Ampel gruen, Spec automatisch freigegeben ({entry['file']})",
            exceeded or [])


def _context_measurement(root) -> "tuple[int | None, int | None, bool]":
    """(tokens, baseline, own) fuer `cmd_context` (#675): 1. eigene Messdatei,
    2. eigenes Transcript (ohne Baseline), 3. juengste Messdatei. Liest nur.
    `own` (#696) ist True nur fuer 1. und 2., nie fuer den Rueckfall auf 3."""
    from hook_utils import (context_tokens_from_transcript, read_context_usage,
                            session_transcript_path)
    usage = read_context_usage(None, root, fallback_newest=False)
    if isinstance(usage, dict) and type(usage.get("tokens")) is int:
        return usage["tokens"], usage.get("baseline_tokens"), True
    path = session_transcript_path()
    tokens = context_tokens_from_transcript(path) if path is not None else None
    if type(tokens) is int:
        return tokens, None, True
    usage = read_context_usage(None, root)
    if isinstance(usage, dict) and type(usage.get("tokens")) is int:
        return usage["tokens"], usage.get("baseline_tokens"), False
    return None, None, False


def _same_handoff_possible() -> bool:
    """Weg herdr fuer `handoff --same` (#696): Autonomie auto, nicht Cloud, Herdr-Pane
    und `claude` im PATH. Wirft nie."""
    try:
        if autonomy_mode() != "auto":
            return False
        if os.environ.get("CLAUDE_CODE_REMOTE", "").strip().lower() == "true":
            return False
        import shutil
        import herdr_bridge
        return bool(herdr_bridge._pane() and shutil.which("claude"))
    except Exception:
        return False


def cmd_context(args: list[str]) -> None:
    """Auskunft, kein Gate: `CONTEXT_TOKENS=<n|unknown>`, `CONTEXT_CUT=on|off` und als
    letzte Zeile `CONTEXT_STOP=on|off`, Exit immer 0.

    Quelle ist die Messung von `post_bash.py` unter
    `.claude/context_usage/<session_id>.json` (Sitzung aus `CLAUDE_CODE_SESSION_ID`,
    sonst die juengste Messung). `on` nur bei eingeschaltetem `context_budget` und
    Messung >= wirksamer Schwelle `max(clear_threshold_tokens, baseline_tokens +
    growth_tokens)` (#557; ohne Baseline nur `clear_threshold_tokens`, Default
    100000); die Zeile `CONTEXT_THRESHOLD=` nennt sie. Bewusst ohne aktiven
    Workflow (Vorbild `autonomy`). `CONTEXT_CUT` ist der Messfakt, `CONTEXT_STOP`
    die Entscheidung (#658): `on` genau dann, wenn CUT=on und
    `hook_utils.context_stop_applies()` (Modus `manual`, #662).
    Nur bei `CONTEXT_STOP=on` rufen die Phasen-Befehle den Folge-Skill nicht mehr
    selbst auf, sondern beenden den Turn mit Checkpoint und Du-Zeile, damit
    `/clear` den Kontext schneidet. CUT=on ohne Halt (Auto-Modus) meldet
    zusaetzlich `CONTEXT_REASON=AUTO_NO_CLEAR`. Ein
    Fehler im Helfer ergibt STOP = CUT. Bei offenem autarkem Auftrag (#551) immer
    `CONTEXT_CUT=off` plus `CONTEXT_REASON=AUTARK` (ohne Schwellen-Zeile).
    Fehlt die eigene Messdatei, liest `context` das eigene Transcript, bevor es auf
    die juengste fremde Messung zurueckfaellt (#675, siehe `_context_measurement`).
    Vor `CONTEXT_STOP=` steht `CONTEXT_HANDOFF=on|off` (#696): `on` nur bei
    Messfakt CUT (vor dem AUTARK-Zwang), Messung der eigenen Sitzung und Weg
    herdr (`_same_handoff_possible`); dann uebergeben die Phasen-Befehle per
    `handoff --same --start` an eine frische Sitzung.
    """
    tokens, cut, autark, threshold, own = None, "off", False, None, False
    try:
        from hook_utils import context_budget_settings, effective_context_threshold
        settings = context_budget_settings()
        tokens, baseline, own = _context_measurement(find_project_root())
        threshold = effective_context_threshold(settings, baseline)
        if settings["enabled"] and tokens is not None and tokens >= threshold:
            cut = "on"
        autark = auftrag_autark_open()
    except Exception:
        cut = "off"
    handoff = "on" if cut == "on" and own and _same_handoff_possible() else "off"
    if autark:
        cut = "off"
    stop = cut
    if cut == "on":
        try:
            import hook_utils
            stop = "on" if hook_utils.context_stop_applies() else "off"
        except Exception:
            stop = cut  # #658: Fehler im Helfer -> bisheriges Verhalten
    try:
        print(f"CONTEXT_TOKENS={tokens if tokens is not None else 'unknown'}")
        print(f"CONTEXT_CUT={cut}")
        if autark:
            print("CONTEXT_REASON=AUTARK")
        elif threshold is not None:
            print(f"CONTEXT_THRESHOLD={threshold}")
        if cut == "on" and stop == "off":
            print("CONTEXT_REASON=AUTO_NO_CLEAR")
        print(f"CONTEXT_HANDOFF={handoff}")
        print(f"CONTEXT_STOP={stop}")
    except Exception:
        pass


def _estimate_kv_lines(est: dict, waiting: bool = False) -> "list[str]":
    """KEY=value-Zeilen von `workflow.py estimate` (#620); `waiting` (#628) gibt
    `ESTIMATE_WAITING=po` aus. #642: Minuten und Ende nur mit Ende-Spanne,
    `ESTIMATE_APPROVAL` vor der Freigabe, `LINE=` wie der Plan."""
    zone = est.get("display_tz")
    today = _display_time(est["now"], zone).date()
    iso = lambda key: _display_time(est[key], zone).isoformat(timespec="minutes")  # noqa: E731
    clock = lambda key: _format_clock(est[key], today, zone)  # noqa: E731
    span = est.get("n") and est.get("end_low") is not None and est.get("end_high") is not None
    approval = est.get("n") and est.get("approval") is not None
    basis = _estimate_basis(est)
    out = ["ESTIMATE=on"] + (["ESTIMATE_WAITING=po"] if waiting else [])
    if span:
        out += [f"ESTIMATE_LOW_MIN={round(est['total_low_min'])}",
                f"ESTIMATE_HIGH_MIN={round(est['total_high_min'])}"]
    out.append(f"ESTIMATE_START={iso('start')}")
    if approval:
        out.append(f"ESTIMATE_APPROVAL={iso('approval')}")
        when = "wartet auf dich" if waiting else f"ca. {clock('approval')}"
        line = f"Start {clock('start')}, Freigabe {when} ({basis})"
    elif span:
        out += [f"ESTIMATE_END_LOW={iso('end_low')}", f"ESTIMATE_END_HIGH={iso('end_high')}"]
        line = f"Ende ca. {_estimate_end_text(est, today, zone)} ({basis})"
    else:
        line = f"Noch keine Zeitschätzung: {NO_DATA}"
    return out + [f"ESTIMATE_BASIS={est.get('n') or 'none'}", f"LINE={line}"]


def cmd_estimate(args: list[str]) -> None:
    """Zeitschätzung des aktiven Workflows (#620), Auskunft, kein Gate, Exit immer 0.

    `ESTIMATE=on` mit Start, vor der Freigabe Freigabezeit, danach Ende-Spanne
    (#642), Basis (Zahl der Vergleichs-Workflows oder `none`) und `LINE=` fuer die
    Intake-Bewertung; bei `time_estimate.enabled: false` oder Fehler nur `ESTIMATE=off`.
    """
    lines = ["ESTIMATE=off"]
    try:
        found = read_active_workflow_fast()
        est = current_estimate(found[1]) if found else None
        if est and not est.get("actual"):
            lines = _estimate_kv_lines(est, awaiting_human_approval(found[1]))
    except (Exception, SystemExit):
        lines = ["ESTIMATE=off"]
    print("\n".join(lines))


def _retro_estimate_line(data: dict) -> "str | None":
    """Retro-Zeile „Schätzung vs. Ist“ (#620), nur mit `estimate_initial`."""
    init = data.get("estimate_initial")
    try:
        if not isinstance(init, dict):
            return None
        low, high = float(init["low"]), float(init["high"])
        span = _finished_span(data)
        actual = (span[1] - span[0]).total_seconds() / 60 if span else None
        if actual is None:
            return None
        verdict = "darunter" if actual < low else ("darüber" if actual > high else "innerhalb")
        return (f"  Schätzung vs. Ist: geschätzt {format_duration(low)}–"
                f"{format_duration(high)}, tatsächlich {format_duration(actual)} ({verdict})")
    except Exception:
        return None


QUEUE_USAGE = ('Usage: workflow.py queue [list | add <N...> [--autark] [--note "<text>"] '
               '[--spur <name>] | done <N> | clear | claim]')
SPUR_USAGE = ("Usage: workflow.py spur [<name> | --clear]  "
              "(Name aus a-z, 0-9, '-'; GitHub-Label spur:<name>)")
QUEUE_AUTARK_SUFFIX = (" (autark: Auftrag aus .claude/auftrag.json weiter abarbeiten, "
                       "kein Halt für /clear)")


def _queue_usage_exit() -> None:
    print(QUEUE_USAGE, file=sys.stderr)
    sys.exit(1)


def _queue_num(arg: str) -> "int | None":
    """Positive Ganzzahl aus reinen ASCII-Ziffern, sonst None."""
    if _re.fullmatch(r"[0-9]+", arg) and int(arg) > 0:
        return int(arg)
    return None


def _print_queue(auftrag) -> None:
    """Gemeinsame Ausgabe aller `queue`-Unterbefehle (#551)."""
    open_issues = auftrag_open_issues(auftrag)
    autark = bool(auftrag and auftrag.get("autark"))
    print(f"QUEUE={','.join(str(n) for n in open_issues) or 'none'}")
    print(f"AUTARK={'on' if autark else 'off'}")
    print(f"NEXT={open_issues[0] if open_issues else 'none'}")
    if open_issues:
        suffix = QUEUE_AUTARK_SUFFIX if autark else ""
        print(f"PROMPT=/00-intake #{open_issues[0]}{suffix}")
    print(f"SPUR={(auftrag or {}).get('spur') or 'none'}")
    # #613: nur mit Sitzungskennung (ohne bleibt die Ausgabe wie bisher): wem der
    # Auftrag gehoert; verwaiste Auftraege nur als Hinweis, nie als eigener
    key = auftrag_owner_key()
    if key:
        print(f"OWNER={key}")
        orphans = auftrag_open_issues(orphan_auftrag())
        if orphans:
            print(f"ALTAUFTRAG={','.join(str(n) for n in orphans)}")
            print("HINWEIS=Auftrag ohne laufende Sitzung (ältere Fassung oder beendete "
                  "Sitzung); gehört er dieser Sitzung, übernimmt ihn `workflow.py queue claim`.")


def _parse_queue_add(args: list[str]) -> "tuple[list[int], bool, str | None, str | None]":
    """(Nummern, --autark, --note, --spur) aus den `queue add`-Argumenten; Fehler → Usage."""
    numbers, autark, note, spur, i = [], False, None, None, 0
    while i < len(args):
        arg = args[i]
        if arg == "--autark":
            autark = True
        elif arg == "--note" and i + 1 < len(args):
            note, i = args[i + 1], i + 1
        elif arg == "--spur" and i + 1 < len(args):
            spur, i = normalize_spur(args[i + 1]), i + 1
            if spur is None:
                _queue_usage_exit()
        elif _queue_num(arg) is not None:
            numbers.append(_queue_num(arg))
        else:
            _queue_usage_exit()
        i += 1
    if not numbers:
        _queue_usage_exit()
    return numbers, autark, note, spur


def _queue_add(root: Path, args: list[str]) -> None:
    """Nummern anhaengen; Doppelte ignoriert, erledigte wieder `open` (#551)."""
    numbers, autark, note, spur = _parse_queue_add(args)
    auftrag = read_auftrag(root) or {"issues": [], "autark": False, "note": "",
                                     "spur": "", "created": "", "updated": ""}
    by_number = {e["n"]: e for e in auftrag["issues"]}
    for n in numbers:
        if n in by_number:
            by_number[n]["status"] = "open"
        else:
            by_number[n] = {"n": n, "status": "open"}
            auftrag["issues"].append(by_number[n])
    if autark:
        auftrag["autark"] = True
    if note is not None:
        auftrag["note"] = note
    if spur is not None:
        auftrag["spur"] = spur
    write_auftrag(root, auftrag)


def cmd_queue(args: list[str]) -> None:
    """`queue [list | add <N..> [--autark] [--note T] [--spur S] | done <N> | clear | claim]`.

    Auftragsliste (#551) der laufenden Sitzung (#613): `<Haupt-Repo>/.claude/auftrag/
    <key>.json`, ohne Sitzungskennung `<Haupt-Repo>/.claude/auftrag.json`; wirkt ohne
    aktiven Workflow. Ausgabe `QUEUE=`, `AUTARK=`, `NEXT=`, bei offenem Auftrag
    `PROMPT=/00-intake #<NEXT>`, `SPUR=<name>|none` (#591); mit Sitzungskennung
    zusaetzlich `OWNER=<key>` und bei verwaisten Auftraegen `ALTAUFTRAG=`/`HINWEIS=`;
    `claim` uebernimmt sie.
    Kill-Switch `auftrag.enabled: false`: genau `QUEUE=disabled`, Exit 0, keine Schreibung.
    """
    if not auftrag_settings()["enabled"]:
        print("QUEUE=disabled")
        return
    root = find_project_root()
    sub, rest = (args[0], args[1:]) if args else ("list", [])
    if sub == "add":
        _queue_add(root, rest)
    elif sub == "done":
        number = _queue_num(rest[0]) if len(rest) == 1 else None
        if number is None:
            _queue_usage_exit()
        if not auftrag_mark_done(root, number):
            print(f"queue done: #{number} steht nicht im Auftrag "
                  f"({auftrag_path(root)})", file=sys.stderr)
            sys.exit(1)
    elif sub == "clear":
        auftrag_clear(root)
    elif sub == "claim" and not rest:
        if not auftrag_claim_orphans(root):
            print("queue claim: kein Auftrag ohne laufende Sitzung zu übernehmen",
                  file=sys.stderr)
    elif sub != "list" or rest:
        _queue_usage_exit()
    _print_queue(read_auftrag(root))


HANDOFF_USAGE = ("Usage: workflow.py handoff [--start] [--mark cloud|herdr] | "
                 "handoff --same [--start]")
HANDOFF_MARK_MODES = ("cloud", "herdr")


def _handoff_parse(args: list[str]) -> "tuple[bool, str | None, bool]":
    """(--start, --mark-Weg, --same) aus den Argumenten; Fehler (auch `--same` mit
    `--mark`, #696) -> Usage auf stderr, Exit 1."""
    start, mark, same, i = False, None, False, 0
    while i < len(args):
        if args[i] == "--start":
            start = True
        elif args[i] == "--same":
            same = True
        elif args[i] == "--mark" and i + 1 < len(args) and args[i + 1] in HANDOFF_MARK_MODES:
            mark, i = args[i + 1], i + 1
        else:
            print(HANDOFF_USAGE, file=sys.stderr)
            sys.exit(1)
        i += 1
    if same and mark:
        print(HANDOFF_USAGE, file=sys.stderr)
        sys.exit(1)
    return start, mark, same


def _handoff_own_issue() -> "int | None":
    """Issue-Nummer des aktiven Workflows oder None (kein/archivierter Workflow). Wirft nie."""
    try:
        found = read_active_workflow_fast()
        if not found:
            return None
        own = workflow_issue_number(found[1] if isinstance(found[1], dict) else {})
        return int(own) if own else None
    except (Exception, SystemExit):
        return None


def _handoff_repo_url(root: Path) -> str:
    """https-URL von `origin` ohne `.git` und ohne Zugangsdaten, sonst "none". Wirft nie."""
    try:
        import subprocess
        res = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(root),
                             capture_output=True, text=True, timeout=10,
                             stdin=subprocess.DEVNULL)
        url = res.stdout.strip() if res.returncode == 0 else ""
        if not url.startswith("https://"):
            return "none"
        rest = url[len("https://"):]
        host, sep, path = rest.partition("/")
        host = host.rpartition("@")[2]
        url = f"https://{host}{sep}{path}".rstrip("/")
        if url.endswith(".git"):
            url = url[:-len(".git")]
        return url if host and not _re.search(r"\s", url) else "none"
    except Exception:
        return "none"


def _handoff_hooks_rel(root: Path) -> str:
    """Pfad des Hook-Ordners relativ zum Repo-Root (`.claude/hooks` bzw. `core/hooks`)."""
    hooks = Path(os.path.abspath(__file__)).parent
    bases = [root] + [p for p in hooks.parents if (p / ".git").exists()][:1]
    for base in bases:
        try:
            return hooks.relative_to(Path(os.path.abspath(base))).as_posix()
        except Exception:
            continue
    return str(hooks)


def _handoff_label(number: int) -> str:
    """Tab-Label `#M <Titel>` (#694) aus dem Titel-Cache; ohne Steuerzeichen, max. 40."""
    title = str((cached_issue_brief(number) or {}).get("title") or "")
    title = "".join(" " if c.isspace() else c for c in title)
    title = " ".join(_re.sub(r"[\x00-\x1f\x7f]", "", title).split())
    return f"#{number} {title}"[:40].strip()


HANDOFF_AUTARK_LINE = (
    "Autarker Auftrag: kein Halt für /clear; halte nur an PO-Punkten (Freigabe ohne "
    "Auto-Freigabe, AMBIGUOUS, Override, Produktfragen per AskUserQuestion).")


def _handoff_queue_add(open_rest: "list[int]", auftrag: dict, hooks: str) -> str:
    """`python3 <hooks>/workflow.py queue add <N...> --autark [--note ..] [--spur ..]` (#667)."""
    import shlex
    cmd = ["python3", f"{hooks}/workflow.py", "queue", "add",
           *[str(n) for n in open_rest], "--autark"]
    note = " ".join((auftrag.get("note") or "").split())
    if note:
        cmd += ["--note", note]
    if auftrag.get("spur"):
        cmd += ["--spur", auftrag["spur"]]
    return " ".join(shlex.quote(part) for part in cmd)


def handoff_prompt(number: int, open_rest: "list[int]", auftrag: dict, hooks: str,
                   prev: "int | None" = None) -> str:
    """Startauftrag der frischen Sitzung (#667), ohne Gespraechswissen lesbar."""
    queue_add = _handoff_queue_add(open_rest, auftrag, hooks)
    report = ([f"Nenne in deiner ersten Meldung in einem Satz das Ergebnis von #{prev} "
               "(Abschlusskommentar am Issue).", ""] if prev else [])
    return "\n".join(report + [
        f"Bitte Issue #{number} in diesem Repo bearbeiten: beginne mit dem Befehl 00-intake "
        f"für #{number} (Kurzbefehl `00-intake` mit Argument `#{number}`; fehlt das Plugin, "
        "liegt der Befehlstext unter skills/00-intake/SKILL.md bzw. im Konsumenten-Projekt "
        "der Redirect-Alias) und folge dem Workflow bis zur Auslieferung.",
        "",
        f"Lege zuerst den Auftrag neu an: `{queue_add}`",
        "",
        HANDOFF_AUTARK_LINE,
        "",
        "Diese Sitzung startet bewusst mit frischem Kontext (#667).",
        "",
        "Nenne beim Abschluss im Abschlusskommentar des Issues den Wert `CONTEXT_TOKENS` aus "
        f"`python3 {hooks}/workflow.py context` (Kontextgröße dieser Sitzung).",
    ])


def handoff_route() -> "tuple[str, int | None, dict | None]":
    """(Weg none|cloud|herdr|inline, naechstes Issue, Auftrag) nach #667. Wirft nie."""
    try:
        if not auftrag_settings()["enabled"]:
            return "none", None, None
        auftrag = read_auftrag()
        if not auftrag:
            return "none", None, None
        own = _handoff_own_issue()
        nxt = next((n for n in auftrag_open_issues(auftrag) if n != own), None)
        if nxt is None or not auftrag["autark"] or autonomy_mode() != "auto":
            return "none", nxt, auftrag
        if os.environ.get("CLAUDE_CODE_REMOTE", "").strip().lower() == "true":
            return "cloud", nxt, auftrag
        import shutil
        import herdr_bridge
        if herdr_bridge._pane() and shutil.which("claude"):
            return "herdr", nxt, auftrag
        return "inline", nxt, auftrag
    except Exception:
        return "none", None, None


def _handoff_mark(root: Path, number: int, mode: str) -> None:
    """Start-Vermerk unter Sperre setzen (#668): Auftrag neu lesen, Feld `handoff`, schreiben.

    Sperre wie die Plan-Pane-Datei (`herdr_bridge._pp_flock`); ohne Sperre (Timeout)
    fail-open weiter. Kein Auftrag mehr -> RuntimeError (zaehlt als Fehlschlag).
    """
    from datetime import timezone
    import herdr_bridge
    fd = herdr_bridge._pp_flock(auftrag_path(root, auftrag_owner_key()))
    try:
        data = read_auftrag(root)
        if data is None:
            raise RuntimeError("kein Auftrag")
        data["handoff"] = {"issue": number, "mode": mode,
                           "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        write_auftrag(root, data)
    finally:
        if fd is not None:
            os.close(fd)


def _worktree_toplevel() -> "str | None":
    """Wurzel des aktuellen Worktrees (`git rev-parse --show-toplevel` im cwd, #696),
    nicht `find_project_root()` (das loest Worktrees zum Haupt-Repo auf). Wirft nie."""
    try:
        import subprocess
        res = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, timeout=10, stdin=subprocess.DEVNULL)
        top = res.stdout.strip() if res.returncode == 0 else ""
        return top if top and os.path.isdir(top) else None
    except Exception:
        return None


def handoff_same_prompt(name: str, number: "int | None", next_cmd: str,
                        auftrag: "dict | None", hooks: str) -> str:
    """Startauftrag fuer `handoff --same` (#696): derselbe Workflow, frischer Kontext.

    `auftrag` nur, wenn `.claude/auftrag.json` offene Issues hat; dann dieselbe
    `queue add`-Zeile wie `handoff_prompt` (alle offenen Issues) und die autark-Zeile.
    """
    cmd, _sep, arg = next_cmd.lstrip("/").partition(" ")
    issue = f" für Issue #{number}" if number else ""
    call = f"Kurzbefehl `{cmd}`" + (f" mit Argument `{arg}`" if arg else "")
    lines = [f"Bitte den laufenden Workflow `{name}`{issue} in diesem Worktree fortsetzen.",
             ""]
    if auftrag:
        queue_add = _handoff_queue_add(auftrag_open_issues(auftrag), auftrag, hooks)
        lines += [f"Lege zuerst den Auftrag neu an: `{queue_add}`", ""]
    lines += [
        f"Hebe dann den Wartevermerk der Vorgängerin auf: `python3 {hooks}/workflow.py "
        "waiting --clear`",
        "",
        f"Führe danach den nächsten Schritt `{next_cmd}` aus ({call}; fehlt das Plugin, "
        f"liegt der Befehlstext unter skills/{cmd}/SKILL.md bzw. im Konsumenten-Projekt "
        "der Redirect-Alias) und folge dem Workflow weiter.",
        "",
        "Diese Sitzung setzt den Workflow mit frischem Kontext fort (#696).",
        "",
    ]
    if auftrag:
        lines += [HANDOFF_AUTARK_LINE, ""]
    lines.append("Nenne in deiner ersten Meldung in einem Satz den Stand des Workflows "
                 "(Phase und nächster Schritt).")
    return "\n".join(lines)


def _handoff_same_route() -> "tuple[str, str | None, dict | None, str | None]":
    """(Weg herdr|none, NEXT, State, Workflow-Name) fuer `handoff --same` (#696). Wirft nie."""
    try:
        found = read_active_workflow_fast()
        if not found or not isinstance(found[1], dict):
            return "none", None, None, None
        name, data = found
        nxt = expected_footer_command(data)
        if not (isinstance(nxt, str) and nxt.startswith("/")):
            return "none", None, None, None
        if not _same_handoff_possible():
            return "none", None, None, None
        return "herdr", nxt, data, name
    except Exception:
        return "none", None, None, None


def _handoff_same_auftrag() -> "dict | None":
    """Offener Auftrag fuer den Startauftrag (#696), sonst None. Wirft nie."""
    try:
        if not auftrag_settings()["enabled"]:
            return None
        auftrag = read_auftrag()
        return auftrag if auftrag and auftrag_open_issues(auftrag) else None
    except Exception:
        return None


def _handoff_same_start(name: str, data: dict, nxt: str, prompt: str) -> "tuple[str, str]":
    """Start fuer `handoff --same --start` (#696): (STARTED, REASON).

    Gleicher Vermerk `handoff_same` (Phase + NEXT) -> already ohne Start. Sonst
    Worktree-Wurzel als cwd, `herdr_bridge.start_session`; nur bei Erfolg Vermerk
    `handoff_same` und `waiting_on` (Endzustand ⏳) in den Workflow-State schreiben.
    """
    from datetime import timezone
    import herdr_bridge
    phase = data.get("current_phase")
    note = data.get("handoff_same")
    if isinstance(note, dict) and note.get("phase") == phase and note.get("next") == nxt:
        return "already", ""
    cwd = _worktree_toplevel()
    if cwd is None:
        return "no", "Worktree-Wurzel nicht ermittelbar (git rev-parse --show-toplevel)"
    number = workflow_issue_number(data)
    label = _handoff_label(int(number)) if number else name[:40]
    ok, reason = herdr_bridge.start_session(prompt, cwd, label)
    if not ok:
        return "no", reason
    path = _workflow_file(name)
    fresh = _read_workflow(path)
    fresh["handoff_same"] = {
        "phase": phase, "next": nxt,
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    fresh["waiting_on"] = _one_line(f"frische Sitzung setzt {nxt} fort")
    _atomic_write(path, fresh)
    return "yes", ""


def _cmd_handoff_same(start: bool) -> None:
    """`handoff --same [--start]` (#696): laufenden Workflow an eine frische Sitzung geben.

    Zeilen: `HANDOFF=herdr|none`, `NEXT=<Folgebefehl inkl. #N>|none`, bei `--start`
    `STARTED=yes|no|already` (+ `REASON=` bei no), bei herdr der Startauftrag
    zwischen `PROMPT_BEGIN`/`PROMPT_END`. Ohne `--start` keine Schreibung. Exit 0.
    """
    route, nxt, data, name = _handoff_same_route()
    prompt = None
    if route == "herdr":
        try:
            number = workflow_issue_number(data)
            prompt = handoff_same_prompt(name, int(number) if number else None, nxt,
                                         _handoff_same_auftrag(),
                                         _handoff_hooks_rel(find_project_root()))
        except Exception:
            route, nxt = "none", None
    print(f"HANDOFF={route}")
    print(f"NEXT={nxt or 'none'}")
    if start:
        started, reason = "no", f"Weg {route}"
        if route == "herdr":
            try:
                started, reason = _handoff_same_start(name, data, nxt, prompt)
            except Exception as exc:
                started, reason = "no", f"Fehler {type(exc).__name__}"
        print(f"STARTED={started}")
        if started == "no":
            print(f"REASON={' '.join(str(reason or 'unbekannt').split())}")
    if prompt:
        print("PROMPT_BEGIN")
        print(prompt)
        print("PROMPT_END")


def cmd_handoff(args: list[str]) -> None:
    """`handoff [--start] [--mark cloud|herdr]` (#667, #668): naechstes Auftrags-Issue frisch starten.

    Zeilen in dieser Reihenfolge: `HANDOFF=none|cloud|herdr|inline`, `NEXT=<M>|none`,
    bei cloud `REPO_URL=<https ohne .git>|none`, `HANDOFF_DONE=<weg>` wenn fuer
    NEXT schon ein Start vermerkt ist (#668), bei `--mark` `MARKED=yes|no`
    (+ `WARN=` bei Schreibfehler), bei `--start` `STARTED=yes|no|already`
    (+ `REASON=` bei no bzw. `WARN=` wenn der Start lief, der Vermerk aber
    scheiterte), bei HANDOFF != none der Startauftrag zwischen `PROMPT_BEGIN`
    und `PROMPT_END`. `--start` startet im Weg herdr eine neue Claude-Sitzung in
    einem neuen Tab (#694); `--mark` vermerkt einen Start (Cloud: nach `create_session`).
    Vermerk im Auftragsfeld `handoff` (unter Sperre neu gelesen); derselbe Vermerk
    macht `--start` zu `STARTED=already`. Exit immer 0 (fail-open), ausser
    ungueltigen Argumenten (Usage auf stderr, Exit 1, keine Schreibung).
    `--same` (#696) uebergibt stattdessen den laufenden Workflow, siehe `_cmd_handoff_same`.
    """
    start, mark, same = _handoff_parse(args)
    if same:
        _cmd_handoff_same(start)
        return
    route, nxt, auftrag, prompt = "none", None, None, None
    try:
        route, nxt, auftrag = handoff_route()
        root = find_project_root()
        if route != "none":
            own = _handoff_own_issue()
            rest = [n for n in auftrag_open_issues(auftrag) if n != own]
            prompt = handoff_prompt(nxt, rest, auftrag, _handoff_hooks_rel(root), own)
    except Exception:
        route, prompt = "none", None
    print(f"HANDOFF={route}")
    print(f"NEXT={nxt if nxt is not None else 'none'}")
    if route == "cloud":
        print(f"REPO_URL={_handoff_repo_url(root)}")
    done = {}
    if route != "none":
        done = (auftrag or {}).get("handoff") or {}
        if not isinstance(done, dict):
            done = {}
        if done.get("issue") == nxt:
            print(f"HANDOFF_DONE={done.get('mode') or 'unbekannt'}")
    if mark:
        marked, warn = "no", ""
        if route != "none":
            try:
                _handoff_mark(root, nxt, mark)
                marked = "yes"
            except Exception as exc:
                warn = f"Vermerk fehlgeschlagen ({type(exc).__name__})"
        print(f"MARKED={marked}")
        if warn:
            print(f"WARN={warn}")
    if start:
        started, reason, warn = "no", f"Weg {route}", ""
        try:
            if route != "none" and done.get("issue") == nxt:
                started, reason = "already", ""
            elif route == "herdr":
                import herdr_bridge
                ok, reason = herdr_bridge.start_session(prompt, root, _handoff_label(nxt))
                if ok:
                    started = "yes"
                    try:
                        _handoff_mark(root, nxt, "herdr")
                    except Exception as exc:
                        warn = f"Vermerk fehlgeschlagen ({type(exc).__name__})"
        except Exception as exc:
            started, reason = "no", f"Fehler {type(exc).__name__}"
        print(f"STARTED={started}")
        if started == "no":
            print(f"REASON={' '.join(str(reason or 'unbekannt').split())}")
        elif warn:
            print(f"WARN={warn}")
    if prompt:
        print("PROMPT_BEGIN")
        print(prompt)
        print("PROMPT_END")


def cmd_spur(args: list[str]) -> None:
    """`spur [<name> | --clear]` (#591): Spur des Auftrags setzen, leeren oder zeigen.

    Ausgabe genau `SPUR=<name>` bzw. `SPUR=none`. Setzen legt bei Bedarf einen
    Auftrag mit leerer Liste an; `--clear` leert nur das Feld. Ungueltiger Name:
    Usage auf stderr, Exit 1, keine Schreibung. Kill-Switch `auftrag.enabled:
    false`: genau `SPUR=disabled`, Exit 0, keine Schreibung.
    """
    if not auftrag_settings()["enabled"]:
        print("SPUR=disabled")
        return
    root = find_project_root()
    if len(args) > 1:
        print(SPUR_USAGE, file=sys.stderr)
        sys.exit(1)
    if not args:
        print(f"SPUR={(read_auftrag(root) or {}).get('spur') or 'none'}")
        return
    name = "" if args[0] == "--clear" else args[0]
    if not name and args[0] == "--clear" and read_auftrag(root) is None:
        print("SPUR=none")
        return
    if args[0] != "--clear" and normalize_spur(name) is None:
        print(f"spur: ungültiger Name {name!r}", file=sys.stderr)
        print(SPUR_USAGE, file=sys.stderr)
        sys.exit(1)
    auftrag = auftrag_set_spur(root, name)
    print(f"SPUR={(auftrag or {}).get('spur') or 'none'}")


def _split_batch(args: list[str]) -> list[list[str]]:
    groups: list[list[str]] = [[]]
    for arg in args:
        if arg == "--":
            groups.append([])
        else:
            groups[-1].append(arg)
    return [g for g in groups if g]


def cmd_batch(args: list[str]) -> None:
    """Mehrere Unterbefehle in EINEM Aufruf, getrennt durch `--` (Kontext-Haushalt).

        workflow.py batch add-artifact test_output logs/t.log "3 failed" phase5_tdd_red \
                          -- mark-red "3 failed" -- status

    Jeder Schritt laeuft wie ein eigener Aufruf (gleicher State, gleiche Gates), nur
    ohne den Tool-Roundtrip dazwischen. Vor jedem Schritt eine Kopfzeile
    `# batch i/n: <befehl>`. Der erste Schritt mit Exit != 0 beendet den Lauf mit
    genau diesem Exit-Code; die restlichen Schritte laufen nicht. `batch` in
    `batch` ist nicht erlaubt.
    """
    groups = _split_batch(args)
    if not groups:
        print("Usage: workflow.py batch <cmd> [args] -- <cmd> [args] ...", file=sys.stderr)
        sys.exit(1)
    total = len(groups)
    for index, group in enumerate(groups, 1):
        sub = group[0]
        if sub == "batch" or sub not in COMMANDS:
            print(f"BATCH: Schritt {index}/{total}: unbekannter Befehl {sub!r}", file=sys.stderr)
            sys.exit(1)
        print(f"# batch {index}/{total}: {' '.join(group)}")
        sys.stdout.flush()
        try:
            COMMANDS[sub](group[1:])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
            if code != 0:
                print(f"BATCH: Schritt {index}/{total} `{sub}` endete mit Exit {code}; "
                      f"{total - index} Schritt(e) nicht ausgefuehrt", file=sys.stderr)
                sys.exit(code)
        sys.stdout.flush()


def cmd_auto_approve(args: list[str]) -> None:
    """Automatische Spec-Freigabe im Auto-Modus (#470).

    stdout: `AUTO_APPROVE=done|human` und `REASON=<kurz>`. Exit immer 0,
    fail-closed: jede Ausnahme ergibt `human`. Bei "done" folgt ggf. die
    Budget-Rueckfrage (#341) wie bei `cmd_phase` (F006) — nach den beiden
    Zeilen, ohne eine weitere `AUTO_APPROVE=`/`REASON=`-Zeile.
    """
    exceeded: list = []
    try:
        verdict, reason, exceeded = _auto_approve_decision()
    except BaseException as exc:  # noqa: BLE001 — fail-closed, auch SystemExit
        verdict, reason = "human", f"Fehler ({type(exc).__name__})"
    try:
        print(f"AUTO_APPROVE={verdict}\nREASON={_flat_line(reason) or '-'}")
    except Exception:
        pass
    if verdict == "done":
        try:
            _print_budget_question(exceeded)
        except Exception:
            pass


def _green_artifact_file(rel: str) -> "Path | None":
    """Pfad des GREEN-Artefakts, nur wenn regulaere Datei innerhalb des Projekts (#471).

    Relative Pfade: Worktree vor Hauptrepo (#509, `_worktree_first_root`), Grenze
    nur gegen genau diese Wurzel. Absolute Pfade: innerhalb Worktree- oder
    Projekt-Root. Symlink, Verzeichnis, Geraet oder ausserhalb (nach
    `resolve()`) → None, ohne die Datei zu lesen.
    """
    import stat as _stat
    candidate = Path(rel)
    try:
        if candidate.is_absolute():
            roots = [r for r in (_worktree_root_if_any(), find_project_root()) if r is not None]
        else:
            root = _worktree_first_root(rel)
            candidate = root / candidate
            roots = [root]
        if not _stat.S_ISREG(os.lstat(candidate).st_mode):
            return None
        resolved = candidate.resolve(strict=True)
        if not any(resolved.is_relative_to(r.resolve()) for r in roots):
            return None
    except (OSError, ValueError, RuntimeError):
        return None
    return resolved


# Zusaetzliche Rot-Evidenz nur fuer auto-green (#471): eine Zeile, die mit
# FAILED/ERROR beginnt (pytest short summary), oder eine Testzeile mit
# pytest-Ergebnis FAILED/ERROR (`test_a.py::t FAILED`) — auch bei "0 failed".
_AUTO_GREEN_RED_LINE_RE = _re.compile(r"^[ \t]*(?:FAILED|ERROR)\b", _re.M)
_AUTO_GREEN_RED_RESULT_RE = _re.compile(
    r"^[ \t]*(?:\[[^\]\n]*\][ \t]*)*\S+[ \t]+(?:FAILED|ERROR)\b", _re.M)


def _auto_green_decision() -> "tuple[str, str]":
    """Pruefkette fuer `auto-green` (#471): (verdict, reason).

    Erste Verfehlung ergibt "human" OHNE State-Aenderung; nur bei "done"
    wird gespeichert. Kein Phasenwechsel, kein Marker, kein Lock.
    """
    if autonomy_mode() != "auto":
        return "human", "Modus manual"
    try:
        data, _name = _read_active()
    except SystemExit:
        return "human", "kein aktiver Workflow"
    if data.get("current_phase") != "phase6_implement":
        return "human", f"Phase {data.get('current_phase')} statt phase6_implement"
    if not data.get("red_test_done"):
        return "human", "RED nicht belegt (red_test_done fehlt)"
    artifacts = [a for a in (data.get("test_artifacts") or [])
                 if isinstance(a, dict) and a.get("type") == "test_output"
                 and a.get("phase") == "phase6_implement"]
    if not artifacts:
        return "human", "kein test_output-Artefakt der Phase phase6_implement"
    art_path = artifacts[-1].get("path")
    if not isinstance(art_path, str) or not art_path:
        return "human", "GREEN-Artefakt ohne Pfad"
    path = _green_artifact_file(art_path)
    if path is None:
        return "human", ("GREEN-Artefakt fehlt, ist keine regulaere Datei "
                         "oder liegt ausserhalb des Projekts")
    try:
        if path.stat().st_size == 0:
            return "human", "GREEN-Artefakt ist leer"
    except OSError:
        return "human", "GREEN-Artefakt nicht lesbar"
    import qa_gate
    # trusted=False: Altersgrenze (30 min) und Mindestgroesse (100 Byte) bleiben
    # aktiv — die Datei hat nicht das Gate selbst erzeugt.
    valid, message = qa_gate.validate_test_output(str(path), trusted=False)
    if not valid:
        return "human", f"GREEN-Artefakt nicht gruen: {message}"
    try:
        content = qa_gate.strip_ansi(path.read_text(errors="replace"))
    except OSError:
        return "human", "GREEN-Artefakt nicht lesbar"
    if _AUTO_GREEN_RED_LINE_RE.search(content) or _AUTO_GREEN_RED_RESULT_RE.search(content):
        return "human", "GREEN-Artefakt enthaelt FAILED/ERROR-Zeile"
    from hook_utils import is_stop_locked
    if is_stop_locked(find_project_root()):
        return "human", "Stop-Lock aktiv"
    if data.get("green_approved"):
        return "human", "GREEN bereits freigegeben"
    data["green_approved"] = True
    record_approval(data, "green", "auto", "GREEN-Artefakt vorhanden",
                    evidence={"artifact": art_path})
    _save_active(data)
    return "done", f"GREEN automatisch freigegeben ({art_path})"


def cmd_auto_green(args: list[str]) -> None:
    """Automatische GREEN-Freigabe im Auto-Modus (#471).

    stdout: `AUTO_GREEN=done|human` und `REASON=<kurz>`. Exit immer 0,
    fail-closed: jede Ausnahme (auch SystemExit) ergibt `human`.
    """
    try:
        verdict, reason = _auto_green_decision()
    except BaseException as exc:  # noqa: BLE001 — fail-closed, auch SystemExit
        verdict, reason = "human", f"Fehler ({type(exc).__name__})"
    try:
        print(f"AUTO_GREEN={verdict}\nREASON={_flat_line(reason) or '-'}")
    except Exception:
        pass


def cmd_sessions(args: list[str]) -> None:
    """List registered Claude sessions of this project (session-locks)."""
    entries = _read_session_entries()

    if "--json" in args:
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return

    if not entries:
        print("Keine registrierten Sessions in .claude/session-locks/.")
        return

    def col(entry, key):
        """Wert der Spalte, ungekuerzt — die Breiten unten fassen die
        Namenskonvention `typ-NNN[-MMM]-beschreibung` vollstaendig."""
        value = entry.get(key)
        if value is None or value == "":
            return SESSIONS_PLACEHOLDER
        return str(value)

    def issue_col(entry):
        """Einzige gekuerzte Spalte (B5): ein Claim kann mehrere Nummern halten
        (`120,121`), und ein kaputter oder manipulierter Wert darf die Tabelle
        nicht sprengen."""
        value = col(entry, "issue")
        return value if len(value) <= ISSUE_W else value[:ISSUE_W - 1] + "…"

    # Breiten aus den realen Werten dieses Projekts abgeleitet (laengste:
    # session_id 36 = UUID, agent_name 20, branch 23, workflow 28, phase 17).
    # worktree 21, weil branch = "worktree-" (9 Zeichen) + Worktree-Name ist:
    # was in branch passt, passt damit garantiert auch in worktree.
    ISSUE_W = 9
    SEP = "─" * 178
    print(SEP)
    print(
        f"  {'Session':<36} {'Agent':<20} {'Worktree':<21} {'Branch':<30} "
        f"{'Workflow':<30} {'Phase':<18} {'Issue':<{ISSUE_W}} {'Alter':>5}"
    )
    print(SEP)
    for entry in entries:
        print(
            f"  {col(entry, 'session_id'):<36} {col(entry, 'agent_name'):<20} "
            f"{col(entry, 'worktree'):<21} {col(entry, 'branch'):<30} "
            f"{col(entry, 'workflow'):<30} {col(entry, 'phase'):<18} "
            f"{issue_col(entry):<{ISSUE_W}} {_sessions_age(entry.get('last_seen')):>5}"
        )
    print(SEP)
    print(f"  {len(entries)} Session(s) registriert.")
    _print_claim_states(entries)


def _print_claim_states(entries: list) -> None:
    """#461: Registrierungsstand am Issue je Workflow (unter der Tabelle, Breiten fix)."""
    seen = set()
    for entry in entries:
        name = entry.get("workflow")
        if not isinstance(name, str) or name in seen or not _NAME_RE.match(name):
            continue
        seen.add(name)
        try:
            claim = _read_workflow(_workflow_file(name)).get("issue_claim")
        except Exception:
            continue
        if isinstance(claim, dict) and claim.get("status"):
            print(f"Registrierung {name}: {claim['status']} an Issue #{claim.get('issue', '?')}")


COMMANDS = {
    "start": cmd_start,
    "switch": cmd_switch,
    "status": cmd_status,
    "plan": cmd_plan,
    "issue-title": cmd_issue_title,
    "issue-brief": cmd_issue_brief,
    "phase": cmd_phase,
    "phase-log": cmd_phase_log,
    "set-field": cmd_set_field,
    "set-briefing": cmd_set_briefing,
    "set-affected-files": cmd_set_affected_files,
    "add-artifact": cmd_add_artifact,
    "remove-artifact": cmd_remove_artifact,
    "mark-red": cmd_mark_red,
    "mark-ui-red": cmd_mark_ui_red,
    "write-log": cmd_write_log,
    "override-ambiguous": cmd_override_ambiguous,
    "complete": cmd_complete,
    # Alias: der Worktree-Waechter des Harness liest "complete" als bash-Builtin
    # und blockiert die ganze Kommandozeile (gregor_zwanzig#1478).
    "finish": cmd_complete,
    "abandon": cmd_abandon,
    "no-build": cmd_no_build,
    "list": cmd_list,
    "find": cmd_find,
    "approvals": cmd_approvals,
    "deploy-config": cmd_deploy_config,
    "deploy-status": cmd_deploy_status,
    "ship-status": cmd_ship_status,
    "waiting": cmd_waiting,
    "endstate": cmd_endstate,
    "queue": cmd_queue,
    "spur": cmd_spur,
    "handoff": cmd_handoff,
    "retro-list": cmd_retro_list,
    "sessions": cmd_sessions,
    "claim": cmd_claim,
    "observable-surface": cmd_observable_surface,
    "autonomy": cmd_autonomy,
    "autoclear": cmd_autoclear,
    "auto-ship": cmd_auto_ship,
    "auto-approve": cmd_auto_approve,
    "auto-green": cmd_auto_green,
    "context": cmd_context,
    "estimate": cmd_estimate,
    "batch": cmd_batch,
    "retro": cmd_retro,
    "cleanup-stale-locks": cmd_cleanup_stale_locks,
}


def main():
    if len(sys.argv) < 2:
        print("Usage: workflow.py <command> [args...]", file=sys.stderr)
        print(f"Commands: {', '.join(COMMANDS.keys())}", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)

    try:
        COMMANDS[cmd](sys.argv[2:])
    except UnsafeStateError as exc:
        # #416: unsicherer State → Meldung statt Traceback, kein Weiterarbeiten
        print(f"BLOCKED: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
