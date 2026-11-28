#!/usr/bin/env python3
"""
Skill Gate — PreToolUse (Matcher `Skill`), Issue #707

`/70-deploy` darf Claude nur selbst aufrufen, wenn das Projekt
`deploy.autonomous: true` gesetzt hat. Der Skill traegt dafuer
`disable-model-invocation: false`; die eigentliche Sperre ist dieser Hook.

Regeln:
- Nur ein Skill-Aufruf mit dem Namen `70-deploy` wird geprueft (auch
  `/70-deploy` und `agent-os-openspec:70-deploy`).
- Erlaubt nur, wenn `workflow.deploy_autonomous()` genau `True` liefert —
  dieselbe Funktion, die auch den Endzustand berechnet (#550). Jede Ausnahme
  blockiert (fail-closed).
- Alles andere (andere Skills, andere Tools, kaputter Payload) geht durch
  (fail-open): ein Hook, der bei eigenem Defekt jede Arbeit blockiert, schuetzt
  nichts mehr.

Der vom PO getippte `/70-deploy` laeuft nicht ueber das Skill-Tool (der Alias
bleibt Vollkopie, siehe alias_sync.FULL_COPY_SKILLS) und ist hiervon unberuehrt.

Exit-Codes: 0 = erlaubt, 2 = blockiert
"""

import json
import os
import sys
from pathlib import Path


def _setup():
    hooks_dir = str(Path(__file__).parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)


_setup()

DEPLOY_SKILL = "70-deploy"
_PLUGIN_PREFIX = "agent-os-openspec:"

BLOCK_MESSAGE = (
    "BLOCKED [skill_gate]: /70-deploy bleibt dem PO vorbehalten — "
    "deploy.autonomous ist nicht true (#707).\n"
    "  Der PO tippt `/70-deploy #N`; beende den Turn mit:\n"
    "  ❗ Du: `/70-deploy #N` — Deploy bleibt beim PO."
)


def _read_payload() -> "tuple[str, object]":
    """(tool_name, tool_input): Env-Variablen zuerst, sonst stdin-JSON (wie
    secret_egress_guard._read_payload). Fehler -> ("", {})."""
    ti_env = os.environ.get("CLAUDE_TOOL_INPUT", "")
    tn_env = os.environ.get("CLAUDE_TOOL_NAME", "")
    if ti_env and tn_env:
        try:
            return tn_env, json.loads(ti_env)
        except json.JSONDecodeError:
            return tn_env, {}
    try:
        data = json.load(sys.stdin)
    except Exception:
        return "", {}
    if not isinstance(data, dict):
        return "", {}
    return data.get("tool_name", ""), data.get("tool_input", {})


def skill_name(tool_name: str, tool_input: object) -> "str | None":
    """Normalisierter Skill-Name (ohne `/` und Plugin-Praefix), sonst None."""
    if tool_name != "Skill" or not isinstance(tool_input, dict):
        return None
    name = tool_input.get("skill")
    if not isinstance(name, str):
        return None
    name = name.strip().lstrip("/")
    if name.startswith(_PLUGIN_PREFIX):
        name = name[len(_PLUGIN_PREFIX):]
    return name


def deploy_autonomous() -> bool:
    """`workflow.deploy_autonomous()`; jede Ausnahme -> False (fail-closed)."""
    try:
        import workflow  # noqa: PLC0415
        return workflow.deploy_autonomous() is True
    except Exception:
        return False


def main() -> int:
    tool_name, tool_input = _read_payload()
    if skill_name(tool_name, tool_input) != DEPLOY_SKILL:
        return 0
    if deploy_autonomous():
        return 0
    try:
        from hook_utils import block  # noqa: PLC0415 - loggt das Gate-Event (#181)
    except Exception:
        print(BLOCK_MESSAGE, file=sys.stderr)
        return 2
    block(BLOCK_MESSAGE, hook="skill_gate", tool="Skill",
          command_excerpt=DEPLOY_SKILL)
    return 2


if __name__ == "__main__":
    try:
        code = main()
    except SystemExit:
        raise
    except Exception:
        code = 0
    sys.exit(code)
