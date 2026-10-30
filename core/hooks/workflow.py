#!/usr/bin/env python3
"""
Workflow v3 — Isolated State Manager

Each workflow gets its own JSON file in .claude/workflows/.
Active workflow tracked ONLY via OPENSPEC_ACTIVE_WORKFLOW env var.
The .active symlink fallback is intentionally disabled — using it causes
cross-session drift. Always set: export OPENSPEC_ACTIVE_WORKFLOW=<name>
Atomic writes via tempfile + rename (no file locks).

Usage:
    python3 workflow.py start <name> [--type feature|bug]
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
    python3 workflow.py sessions [--json]
    python3 workflow.py observable-surface
"""

from hook_utils import setup_path, find_project_root
from hook_utils import UnsafeStateError, atomic_write_json, read_state_json
setup_path()

import hashlib as _hashlib
import json
import os
import re as _re
import sys
import tempfile
import time
from datetime import datetime
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
    """
    if not isinstance(data, dict):
        return None
    phase = data.get("current_phase")
    if not isinstance(phase, str) or phase not in NEXT_STEP:
        return None
    if phase in _NO_BUILD_PHASES and data.get("no_build_reason"):
        return "/99-reset"  # PO-Entscheidung "nichts bauen" (#424)
    if phase == "phase3_spec" and data.get("spec_file"):
        if _auto_approval_pending(data):
            return AUTO_APPROVAL_STEP  # Ampel gruen im Auto-Modus (#470)
        return "Freigabe der Spec (Stichwort: approved)"
    if phase == "phase5_tdd_red" and (
        data.get("red_test_done") or data.get("ui_test_red_done")
    ):
        return "/50-implement"
    return NEXT_STEP[phase]


def issue_number(workflow_name: str) -> "str | None":
    """Erste Ziffernfolge im Workflow-Namen (fix-1761-xyz -> '1761')."""
    match = _re.search(r"\d+", workflow_name or "")
    return match.group(0) if match else None


def expected_footer_command(data: dict) -> "str | None":
    """Erwarteter Fusszeilen-Befehl — dieselbe Quelle wie status_note() (#234).

    Duenne Huelle um next_step() + issue_number(), damit footer_gate.py die
    Fusszeile gegen genau den Wert prueft, den status_note() ansagt. Keine
    eigene Logik: None und Freitext-Schritte werden unveraendert
    durchgereicht.
    """
    step = next_step(data)
    if not step or not step.startswith("/"):
        return step  # None oder Freitext-Schritt (z.B. "Freigabe der Spec ...")
    issue = issue_number((data or {}).get("name", ""))
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


def render_plan(data, archived: bool = False, width: "int | None" = None,
                deploy: bool = False) -> str:
    """Workflow-Plan als Text (#476): ✔ erledigt, ▶ laeuft, ○ offen. Pure.

    `deploy` (#478): nach "8 Fertig" ein Schritt Deploy; in Phase 8 offen bis
    zur Archivierung, naechster Befehl dann `/70-deploy #N`.
    """
    if not isinstance(data, dict):
        lines = ["Kein aktiver Workflow"]
    else:
        fast = data.get("workflow_type") == "feature-fast"
        steps = PLAN_STEPS_FAST if fast else PLAN_STEPS
        phase = data.get("current_phase")
        done_all = archived or phase == "phase8_complete"
        running = None
        if not done_all and phase in PHASES and phase != "phase0_idle":
            # Phase nicht in der Liste (Fast Track): letzter Schritt davor laeuft
            pos = PHASES.index(phase)
            for i, (_, _, step_phase) in enumerate(steps):
                if PHASES.index(step_phase) <= pos:
                    running = i
        name = str(data.get("name") or "")
        issue = issue_number(name)
        lines = [f"Workflow #{issue}" if issue else "Workflow", name]
        title = data.get("issue_title")
        if isinstance(title, str) and title.strip():
            lines.append(title)  # #490: Kurztitel des Issues unter dem Namen
        lines.append("")
        for i, (nr, label, _) in enumerate(steps):
            if done_all or (running is not None and i < running):
                lines.append(f"✔ {nr} {label}")
            elif i == running:
                lines.append(f"▶ {nr} {label}  (läuft)")
            else:
                lines.append(f"○ {nr} {label}")
        deploy_open = bool(deploy) and not archived and phase == "phase8_complete"
        if deploy:
            if archived:
                lines.append("✔ Deploy")
            elif deploy_open:
                lines.append("▶ Deploy  (offen)")
            else:
                lines.append("○ Deploy")
        if deploy_open:
            lines += ["", f"Nächster: /70-deploy #{issue}" if issue else "Nächster: /70-deploy"]
        elif done_all:
            lines += ["", "abgeschlossen"]
        else:
            try:
                nxt = expected_footer_command(data)
            except Exception:
                nxt = None
            if nxt:
                lines += ["", f"Nächster: {nxt}"]
    if isinstance(width, int) and width > 0:
        lines = [line[:width] for line in lines]
    return "\n".join(lines)


def status_note(data: dict) -> "str | None":
    """Statusvermerk fuer den UserPromptSubmit-Hook, oder None.

    None heisst: nichts anhaengen — kein Workflow, Phase 8, oder State
    unbrauchbar. Der Vermerk ist die einzige Stelle, die Claude auch in frei
    formulierten Nachrichten NACH dem Ende einer Phase (Loop-Aufwachen,
    Zwischenfragen) daran erinnert, dass ein Pflicht-Schritt offen ist.
    """
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
        issue = issue_number(name)
        if issue:
            step = f"{step} #{issue}"
    if step == AUTO_APPROVAL_STEP:
        # Auto-Fall (#470): der PO muss nichts tippen — keine Du-Pflicht.
        return (
            f"{STATUS_NOTE_PREFIX} AKTIVER WORKFLOW {name} · "
            f"Phase {PHASE_NUMBERS[phase]} von {TOTAL_PHASES} ({phase}) · "
            f"Nächster Pflicht-Schritt: {step}\n"
            "Diesen Schritt führst du selbst aus (Auto-Modus, Ampel im PO-Briefing "
            "grün) — der PO muss dafür nichts tippen, es gibt dafür KEINE Du-Zeile. "
            "Meldet `workflow.py auto-approve` AUTO_APPROVE=human, entscheidet der PO "
            "wie bisher per Freigabe-Stichwort.\n"
            "„fertig“/„abgeschlossen“/„erledigt“ gilt für den Workflow erst ab "
            "phase8_complete."
        )
    return (
        f"{STATUS_NOTE_PREFIX} AKTIVER WORKFLOW {name} · "
        f"Phase {PHASE_NUMBERS[phase]} von {TOTAL_PHASES} ({phase}) · "
        f"Nächster Pflicht-Schritt: {step}\n"
        "Nenne diesen Schritt in jeder Arbeitsstandsmeldung als Pflicht — nie als "
        "„bei Bedarf“ oder „optional“; Empfehlungen zu /clear oder Token-Kosten "
        "stehen nie darüber.\n"
        "Kennzeichne für den PO, wer am Zug ist, mit GENAU EINER Zeile ganz am Ende "
        "der Nachricht — nie zusätzlich mitten im Fließtext: „❗ Du: <Schritt>“, "
        "wenn der PO ihn tippen oder entscheiden muss. Das gilt AUCH, wenn du "
        "selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl "
        "des PO wartest — das ist niemals „nichts zu tun“. „ℹ️ Nichts zu tun: "
        "<du arbeitest gerade selbst / wartest auf ein Ergebnis, z. B. einen "
        "Hintergrund-Agenten> — danach: <Schritt>“ gilt ausschließlich, wenn du "
        "auf etwas ANDERES als den PO wartest.\n"
        "Hast DU SELBST in dieser Nachricht per `workflow.py phase <x>` (oder "
        "`complete`) die Phase gewechselt, ist dieser Hinweis hier noch der ALTE "
        "Stand von Turn-Beginn — nutze für Schritt und Phase in der Fußzeile "
        "trotzdem den NEUEN, von dir selbst herbeigeführten Stand. Die "
        "Marker-Zeilen entfallen NIE aus diesem Grund.\n"
        "❗/ℹ️/⚙ erscheinen AUSSCHLIESSLICH in den hier und in den "
        "Command-Vorlagen fest vorgeschriebenen Zeilen. Erfinde keine "
        "weiteren Zeilen mit diesen oder anderen Emojis (z. B. eine eigene "
        "„ℹ️ Status: ...“-Zusammenfassung) — Statusrekaps im Fließtext bleiben "
        "Emoji-frei.\n"
        "„fertig“/„abgeschlossen“/„erledigt“ gilt für den Workflow erst ab "
        "phase8_complete."
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


def short_title(title, max_words: int = 6) -> str:
    """Issue-Titel auf die ersten `max_words` Woerter kuerzen (#490). Pure."""
    if not isinstance(title, str):
        return ""
    words = title.split()
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


def fetch_issue_title(issue, timeout: float = 8) -> "str | None":
    """Titel per `gh` holen, kuerzen, cachen (#490). Fail-open: None, wirft nie."""
    try:
        import shutil
        import subprocess
        gh = shutil.which("gh")
        if not gh or not str(issue).isdigit():
            return None
        res = subprocess.run(
            [gh, "issue", "view", str(issue), "--json", "title", "-q", ".title"],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(find_project_root()), stdin=subprocess.DEVNULL,
        )
        title = short_title(res.stdout) if res.returncode == 0 else ""
        if not title:
            return None
        cache = _read_issue_titles()
        cache[str(issue)] = title
        atomic_write_json(_issue_titles_file(), cache)
        return title
    except Exception:
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
    events = _record_budget_events(data)
    _note_transition_boundary(data, target)
    return events


# Phasengrenzen fuer Auto-/clear (#497): Ende eines Phasenbefehls, danach startet
# der Folgebefehl im neuen Kontext. Alle anderen Wechsel setzen keinen Vermerk.
AUTO_CLEAR_BOUNDARIES = frozenset({
    ("phase1_context", "phase2_analyse"),
    ("phase2_analyse", "phase3_spec"),
    ("phase3_spec", "phase4_approved"),
    ("phase5_tdd_red", "phase6_implement"),
    ("phase6b_adversary", "phase7_validate"),
})


def _boundary_timestamp() -> str:
    """Zeitstempel fuer `auto_clear_boundary.at`, mit Zeitzone (#497b)."""
    return datetime.now().astimezone().isoformat()


def _note_transition_boundary(data: dict, target: str) -> None:
    """Grenz-Vermerk beim Phasenwechsel in `data` setzen (#497); fail-open, still.

    Nur fuer Grenzen aus AUTO_CLEAR_BOUNDARIES bei aktivem Auto-/clear. Speichern
    uebernimmt der Aufrufer; `current_phase` ist hier noch die alte Phase.
    """
    try:
        if (data.get("current_phase"), target) not in AUTO_CLEAR_BOUNDARIES:
            return
        import herdr_bridge
        if not (herdr_bridge._pane() and herdr_bridge.auto_clear_enabled()):
            return
        command = expected_footer_command(dict(data, current_phase=target))
        if isinstance(command, str) and command.startswith("/"):
            data["auto_clear_boundary"] = {
                "phase": target, "command": command, "at": _boundary_timestamp(),
            }
    except Exception:
        pass


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

_PO_BRIEFING_PLACEHOLDERS = ("[todo", "[tbd", "todo:", "fixme:", "xxx:", "<platzhalter")

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
    lowered = content.lower()
    for marker in _PO_BRIEFING_PLACEHOLDERS:
        if marker in lowered:
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
        # #447: sonst waere das Evidence-Gate per `start --type feature-fast` umgehbar.
        if target == "phase8_complete":
            return _evidence_reason(target, data)
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

    if tgt_idx >= PHASES.index("phase6_implement"):
        red_artifacts = [a for a in data.get("test_artifacts", [])
                        if a.get("phase") == "phase5_tdd_red"]
        if (not red_artifacts and not data.get("red_test_done")
                and not data.get("ui_test_red_done")):
            return "No RED test artifacts — run /tdd-red first"

    if tgt_idx >= PHASES.index("phase8_complete"):
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
        # #447: Evidence-Gate (opt-in) erst nach bestandenem Dialog-Check.
        return _evidence_reason(target, data)

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

def cmd_start(args: list[str]) -> None:
    workflow_type = "feature"
    name_args = []
    i = 0
    while i < len(args):
        if args[i] == "--type" and i + 1 < len(args):
            workflow_type = args[i + 1]
            i += 2
        else:
            name_args.append(args[i])
            i += 1
    if not name_args:
        print("Usage: workflow.py start <name> [--type feature|feature-fast]", file=sys.stderr)
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
    data["base_commit"] = _start_base_commit()  # #259: Basis-Kandidat fuer Phase 8
    if workflow_type == "feature-fast":
        # Fast-track for small features: skip context/analyse, start at spec
        data["current_phase"] = "phase3_spec"
        data["red_test_done"] = True  # inline TDD during implementation
        _log_phase_transition(data, "phase3_spec")
    else:
        _log_phase_transition(data, "phase1_context")
    _atomic_write(wf_file, data)
    _set_active(name)
    _herdr("report", data)
    issue = issue_number(name)
    if issue and cached_issue_title(issue) is None:
        _spawn_issue_title_fetch(issue)  # #490: abgekoppelt, wartet nicht
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
    """`issue_title` aus dem Cache setzen, falls vorhanden (#490). Wirft nie."""
    try:
        issue = issue_number(str(data.get("name") or ""))
        title = cached_issue_title(issue) if issue else None
        if title:
            data["issue_title"] = title
    except Exception:
        pass
    return data


def _plan_fetch_missing(data, tried: set) -> None:
    """Fehlenden Titel hoechstens einmal je Issue und Prozess holen (#490)."""
    try:
        if not isinstance(data, dict) or data.get("issue_title"):
            return
        issue = issue_number(str(data.get("name") or ""))
        if not issue or issue in tried:
            return
        tried.add(issue)
        if cached_issue_title(issue) is None:
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
    pane_file = _plan_pane_file() if target else None
    try:
        while True:
            data = None
            if _plan_watch_should_end(target, own_file, misses):
                break  # Herdr schliesst das Pane, wenn der exec-Prozess endet
            _plan_follow_target(target, pane_file)  # #493: vor dem Aufloesen
            try:
                width = shutil.get_terminal_size().columns
                deploy = deploy_configured()  # je Runde neu (#478)
                found = _plan_active()
                if found:
                    last_name, data = found
                    out = render_plan(data, width=width, deploy=deploy)
                elif last_name and _archive_file(last_name).exists():
                    data = dict(_read_workflow(_archive_file(last_name)))
                    data.setdefault("name", last_name)
                    _with_issue_title(data)
                    out = render_plan(data, archived=True, width=width, deploy=deploy)
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
    print(render_plan(found[1] if found else None, deploy=deploy_configured()))


def cmd_issue_title(args: list[str]) -> None:
    """`issue-title <N>` (#490): Kurztitel holen und cachen; Exit immer 0."""
    title = fetch_issue_title(args[0]) if args else None
    if title:
        print(title)


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
    """
    if current not in PHASES or target not in PHASES:
        return
    cur_idx, tgt_idx = PHASES.index(current), PHASES.index(target)
    if tgt_idx >= cur_idx:
        return
    if tgt_idx < PHASES.index("phase4_approved"):
        data["spec_approved"] = False
    if tgt_idx < PHASES.index("phase6_implement"):
        data["green_approved"] = False


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
    _save_active(data)
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
    outcome = args[0] if args else "success"
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
    print(f"Execution log written: {log_file}")


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
    try:  # #250 B: Messung blockiert den Abschluss nie
        final = _final_loc(data)
        if final is not None:
            data["loc_delta_final"], data["loc_delta_test_final"] = final
    except Exception:
        pass
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
    print(f"Workflow {name} completed and archived.")


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
        if not pat.search(f.stem):
            continue
        d = _read_workflow(f)
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


def cmd_approvals(args: list[str]) -> None:
    """Freigabe-Protokoll des aktiven Workflows anzeigen (#472). Nur Anzeige.

    stdout: `APPROVALS=<n>`, danach je Eintrag `- <gate> | <by> | <at> | <reason>`.
    `--auto` zeigt nur automatische Freigaben (`by == "auto"`). Exit immer 0 —
    ohne aktiven Workflow oder bei unlesbarem State `APPROVALS=0`.
    """
    try:
        data, _name = _read_active()
        entries = data.get("approvals") or []
    except (SystemExit, Exception):
        entries = []
    if not isinstance(entries, list):
        entries = []
    rows = [e for e in entries if isinstance(e, dict)
            and ("--auto" not in args or e.get("by") == "auto")]
    print(f"APPROVALS={len(rows)}")
    for e in rows:
        print("- " + " | ".join(_one_line(e.get(k) or "-")
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


def _one_line(value) -> str:
    """Zeilenumbrueche platt machen — die Auskunft hat genau fuenf Zeilen."""
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
        reason = _one_line(report.get("reason") or "") or "unbekannt"
        files = int(report.get("files") or 0)
        root = _one_line(report.get("root") or "")
    except Exception as exc:
        # Ein Absturz darf keine Rueckfrage unterdruecken: yes + sprechender Grund.
        surface, reason, files, root = "yes", f"internal-error {type(exc).__name__}", 0, ""
    try:
        from config_loader import config_source_note
        note = _one_line(config_source_note() or "")
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


def cmd_autoclear(args: list[str]) -> None:
    """Auskunft, kein Gate: genau eine Zeile `AUTO_CLEAR=on|off`, Exit immer 0 (#489).

    `on` nur in einem Herdr-Pane (`_pane()`) bei aktivem Auto-/clear. Bewusst ohne
    aktiven Workflow, Vorbild `cmd_autonomy`. Bei `on` zusaetzlich Grenz-Vermerk
    im aktiven Workflow (#495), ohne Einfluss auf Ausgabe/Exit.
    """
    state = "off"
    try:
        import herdr_bridge
        if herdr_bridge._pane() and herdr_bridge.auto_clear_enabled():
            state = "on"
    except Exception:
        state = "off"
    if state == "on":
        _record_auto_clear_boundary()
    try:
        print(f"AUTO_CLEAR={state}")
    except Exception:
        pass


def _record_auto_clear_boundary() -> None:
    """Grenz-Vermerk `auto_clear_boundary` im aktiven Workflow speichern (#495).

    Der Stop-Hook (`herdr_bridge.maybe_auto_clear`) loest nur aus, wenn der
    Vermerk zu Phase und erwartetem Befehl passt. Fail-open: kein Workflow,
    kein bestimmbarer Befehl oder jeder Fehler = nichts speichern, still.
    """
    try:
        found = read_active_workflow_fast()
        if found is None:
            return
        name, data = found
        command = expected_footer_command(data)
        if not isinstance(command, str):
            return
        data.setdefault("name", name)
        data["auto_clear_boundary"] = {
            "phase": data.get("current_phase"),
            "command": command,
            "at": _boundary_timestamp(),
        }
        # Bewusst ohne _save_active: kein Herdr-Report, Stand unveraendert
        _atomic_write(_workflow_file(name), data)
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
        print(f"AUTO_APPROVE={verdict}\nREASON={_one_line(reason) or '-'}")
    except Exception:
        pass
    if verdict == "done":
        try:
            _print_budget_question(exceeded)
        except Exception:
            pass


def _green_artifact_file(rel: str) -> "Path | None":
    """Pfad des GREEN-Artefakts, nur wenn regulaere Datei innerhalb des Projekts (#471).

    Relative Pfade gegen den Projekt-Root; Symlink, Verzeichnis, Geraet oder
    ausserhalb (nach `resolve()`) → None, ohne die Datei zu lesen.
    """
    import stat as _stat
    root = find_project_root()
    candidate = Path(rel)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        if not _stat.S_ISREG(os.lstat(candidate).st_mode):
            return None
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
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
        print(f"AUTO_GREEN={verdict}\nREASON={_one_line(reason) or '-'}")
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


COMMANDS = {
    "start": cmd_start,
    "switch": cmd_switch,
    "status": cmd_status,
    "plan": cmd_plan,
    "issue-title": cmd_issue_title,
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
    "retro-list": cmd_retro_list,
    "sessions": cmd_sessions,
    "observable-surface": cmd_observable_surface,
    "autonomy": cmd_autonomy,
    "autoclear": cmd_autoclear,
    "auto-approve": cmd_auto_approve,
    "auto-green": cmd_auto_green,
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
