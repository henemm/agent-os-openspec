#!/bin/bash
# Installiert den Prozess-Waechter (#462) als launchd-Dienst (macOS), Lauf einmal pro Minute.
# Aufruf: scripts/install_watchdog_service.sh [Pfad/zu/process_watchdog.py]
# Ohne Argument: Plugin-Pfad aus installed_plugins.json, sonst dieses Repo.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
wd="${1:-}"
if [ -z "$wd" ]; then
  p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [v[0]]),""))' 2>/dev/null || true)"
  if [ -n "$p" ]; then wd="$p/core/hooks/process_watchdog.py"; else wd="$here/core/hooks/process_watchdog.py"; fi
fi
[ -f "$wd" ] || { echo "Nicht gefunden: $wd" >&2; exit 1; }
target="$HOME/Library/LaunchAgents/com.henemm.process-watchdog.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
sed -e "s|__WATCHDOG__|$wd|" -e "s|__HOME__|$HOME|g" \
  "$here/scripts/launchd/com.henemm.process-watchdog.plist" > "$target"
launchctl bootout "gui/$(id -u)/com.henemm.process-watchdog" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$target"
echo "Waechter installiert: $target -> $wd (Log: ~/Library/Logs/process-watchdog.log)"
