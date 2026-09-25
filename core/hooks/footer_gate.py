#!/usr/bin/env python3
"""Footer-Gate (Stop-Hook): prueft die ❗Du-Fusszeile gegen next_step() (#234).

Die ❗Du-Zeile ist die einzige Zeile, die der PO als „das tippe ich jetzt"
liest. `workflow.next_step()` kennt den korrekten Schritt deterministisch aus
dem State — dieser Hook gleicht die Fusszeile mechanisch dagegen ab und
erzwingt bei Abweichung per Exit 2 eine Korrektur, statt (wie #174/#209/#213/
#221) erneut nur Prompt-Text zu verschaerfen.

TRAGENDE ANFORDERUNG IST FAIL-OPEN, NICHT DIE ERKENNUNGSRATE: der Hook laeuft
im Plugin-Modus bei jedem Turn-Ende in jedem Konsumenten-Projekt. Jeder
unklare Fall endet mit Exit 0; keine Ausnahme darf nach aussen dringen.
"""

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from hook_utils import setup_path
setup_path()

from hook_utils import block, find_project_root, framework_disabled, resolve_active_workflow  # noqa: E402
from workflow import expected_footer_command  # noqa: E402

# Marker-Zeile: „❗ Du: ..." bzw. „‼️ Du: ..." (Variation Selector optional).
DU_LINE_RE = re.compile(r"^\s*(?:❗|‼)️?\s*Du\s*:")

# Slash-Befehl. Zwei Feinheiten, beide belegt:
# 1. Die Befehle dieses Frameworks beginnen mit Ziffern (/40-tdd-red,
#    /50-implement) — ein Muster wie `/[a-zA-Z][\w-]*` wuerde ausgerechnet
#    sie nicht finden.
# 2. Der Lookbehind verwirft jeden Slash, dem ein Wortzeichen oder ein
#    weiterer Slash vorausgeht. Ohne ihn gewann ein relativer Pfad oder eine
#    URL VOR dem Befehl ("siehe docs/specs/x.md, dann `/50-implement`" ->
#    `/specs`, "https://example.com/foo" -> `/example`).
# Gegen alles, was der Lookbehind nicht erwischt (absoluter Pfad, zweiter
# gueltiger Befehl, Markdown-Link), hilft nicht das Muster, sondern die
# Auswertung: siehe _footer_commands().
SLASH_CMD_RE = re.compile(r"(?<![\w/])/[A-Za-z0-9][\w-]*")

STATE_FILE = "footer_gate_state.json"

# Ohne `prompt_id` ist die Turn-Kennung ein Hash der Antwort. Korrigiert
# Claude die Fusszeile, aendert sich der Text und damit die Kennung — der
# Kennungsvergleich allein kann eine Schleife dann nicht beenden. In diesem
# Fall zieht zusaetzlich eine Zeitgrenze: hoechstens eine Blockade je Fenster.
# Mit vorhandenem `prompt_id` bleibt es beim exakten Vergleich.
_LOOP_WINDOW_SECONDS = 120


def _state_path() -> Path:
    """Worktree-lokale Zustandsdatei (Vorbild: phase_listener._stop_lock_path)."""
    try:
        from hook_utils import _find_worktree_root
        wt = _find_worktree_root()
        if wt is not None:
            return wt / ".claude" / STATE_FILE
    except Exception:
        pass
    return find_project_root() / ".claude" / STATE_FILE


def _prompt_id(payload: dict) -> "str | None":
    """`prompt_id` aus der Payload, oder None (Claude Code < v2.1.196)."""
    pid = payload.get("prompt_id")
    if isinstance(pid, str) and pid.strip():
        return pid.strip()
    return None


def _turn_id(payload: dict, message: str) -> str:
    """Kennung des laufenden Turns fuer den Schleifenschutz.

    Ohne `prompt_id` traegt ein Hash der Antwort die Kennung — allein aber
    nicht ausreichend, siehe _LOOP_WINDOW_SECONDS.
    """
    pid = _prompt_id(payload)
    if pid:
        return pid
    return "sha256:" + hashlib.sha256(message.encode("utf-8", "replace")).hexdigest()


def _read_state() -> dict:
    try:
        data = json.loads(_state_path().read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _blocked_within_window(state: dict) -> bool:
    """True, wenn die letzte Blockade weniger als das Fenster zurueckliegt.

    Ein fehlender, kaputter oder nicht vergleichbarer Zeitstempel bedeutet
    ausschliesslich „keine Grenze aktiv" — nie einen Absturz.

    Die Differenz muss in der Vergangenheit liegen (>= 0). Ohne diese
    Untergrenze haette ein Zeitstempel aus der ZUKUNFT (kaputte
    Zustandsdatei, Uhr-Drift) das Fenster dauerhaft wahr gemacht und das Gate
    still abgeschaltet — die eine Richtung, in der Fail-open kippt: nicht ein
    Fehlalarm, sondern gar keine Pruefung mehr.
    """
    try:
        last = datetime.fromisoformat(state.get("last_block_at"))
        elapsed = (datetime.now() - last).total_seconds()
        return 0 <= elapsed < _LOOP_WINDOW_SECONDS
    except Exception:
        return False


def _remember(turn_id: str) -> None:
    try:
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "last_turn_id": turn_id,
            "last_block_at": datetime.now().isoformat(),
        }))
    except Exception:
        pass


def _footer_commands(message: str) -> list:
    """ALLE Slash-Befehle der LETZTEN ❗Du-Zeile, in Reihenfolge der Zeile.

    Bewusst eine Liste statt eines einzelnen Treffers: weder der erste noch
    der letzte Treffer ist zuverlaessig der gemeinte. Der erste verliert gegen
    alles, was davor steht ("nicht mehr `/40-tdd-red`, sondern
    `/50-implement`", "[veraltet](/40-tdd-red) — jetzt `/50-implement`",
    "/root/x.txt lesen, dann `/50-implement`"); der letzte verliert gegen die
    Normalform ("`/60-validate` — danach siehe docs/...").

    Blockiert wird deshalb nur, wenn der erwartete Befehl unter KEINEM Treffer
    ist. Preis dieser Regel, vom PO ausdruecklich so entschieden: eine Zeile,
    die den erwarteten Befehl irgendwo nennt, aber auf einen anderen zeigt,
    kommt durch. Fail-open ist die tragende Anforderung.
    """
    marker = None
    for line in message.splitlines():
        if DU_LINE_RE.match(line):
            marker = line
    if marker is None:
        return []
    return SLASH_CMD_RE.findall(marker)


def _expected_command(name: str) -> "str | None":
    """Erwarteter Slash-Befehl aus dem Workflow-State, oder None (fail-open)."""
    try:
        path = find_project_root() / ".claude" / "workflows" / f"{name}.json"
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            return None
        data.setdefault("name", name)
        expected = expected_footer_command(data)
    except Exception:
        return None
    if not isinstance(expected, str) or not expected.startswith("/"):
        return None
    return expected.split()[0]


def main() -> None:
    if framework_disabled():
        sys.exit(0)

    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)

    message = payload.get("last_assistant_message")
    if not isinstance(message, str) or not message:
        sys.exit(0)

    actuals = _footer_commands(message)
    if not actuals:
        sys.exit(0)

    try:
        name, source = resolve_active_workflow()
    except Exception:
        sys.exit(0)
    if not name or source == "none":
        sys.exit(0)

    expected = _expected_command(name)
    if not expected or expected in actuals:
        sys.exit(0)

    # Schleifenschutz: Exit 2 setzt den Turn fort — ohne ihn entstuende eine
    # Endlosschleife. Der eigene Zaehler traegt die Garantie allein;
    # `stop_hook_active` ist ein undokumentierter, rein defensiver Zusatz.
    if payload.get("stop_hook_active") is True:
        sys.exit(0)
    state = _read_state()
    turn_id = _turn_id(payload, message)
    if state.get("last_turn_id") == turn_id:
        sys.exit(0)
    if _prompt_id(payload) is None and _blocked_within_window(state):
        sys.exit(0)
    _remember(turn_id)

    # Genannt wird der ERSTE Treffer — die Meldung bleibt damit wortgleich zum
    # bisherigen Verhalten.
    block(
        f"FUSSZEILE FALSCH: Fußzeile nennt `{actuals[0]}`, korrekt ist `{expected}`.\n"
        "Gib die Fußzeile erneut mit dem korrekten Befehl aus."
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Fail-open: ein Absturz hier wuerde jedes Turn-Ende stoeren.
        sys.exit(0)
