#!/usr/bin/env bash
# End-to-End-Test der Auto-/clear-Kette (#467/#495) mit echtem Claude-Code-TUI,
# diesem Repo als Plugin (--plugin-dir) und echtem Herdr 0.9.5 (headless).
#
# Szenarien (Exit 0 nur, wenn alle PASS):
#   A  REALISTISCH   Claude fuehrt `workflow.py autoclear` per Bash aus und gibt nur
#                    die ❗Du-Zeile aus (ohne Positiv-Satz) -> /clear + Folgebefehl.
#   B  NEGATIV       wie A, aber mit "`/clear` jetzt NICHT" -> skip: Negativmarker.
#   C  OHNE VERMERK  nur die ❗Du-Zeile, kein autoclear -> skip: keine Grenze vermerkt.
#   D  VERBRAUCHT    A, danach (Once-Lock geloescht) ein weiterer Turn mit derselben
#                    ❗Du-Zeile ohne autoclear -> skip: keine Grenze vermerkt, kein
#                    zweites /clear (Vermerk ist Einmal-Signal, #495 F001).
#
# Aufruf:
#   HERDR_E2E_BIN=/pfad/zu/herdr bash scripts/e2e_auto_clear.sh   # vorhandenes Binary
#   bash scripts/e2e_auto_clear.sh                                # laedt v0.9.5, prueft SHA256
#   KEEP=1 ...      laesst die Arbeitsordner stehen
#   ONLY="A C" ...  nur ausgewaehlte Szenarien
#
# Voraussetzungen: claude (eingeloggt bzw. Auth per Umgebung), git, python3, curl.
# Die Session laeuft in einem Git-Worktree unter .claude/worktrees/e2e, weil
# session_singleton_guard im Haupt-Ordner jeden Bash-Aufruf blockt.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
HERDR_URL="https://github.com/herdrdev/herdr/releases/download/v0.9.5/herdr-linux-x86_64"
HERDR_SHA256="14d9e8bc8b4a9e0118d77c32266f76d461f09b40342eb23752960bd89f59929d"
WF="feat-999-e2e"
CMD="/10-context #999"
MODEL="${E2E_MODEL:-haiku}"
KEEP="${KEEP:-0}"
ONLY="${ONLY:-A B C D}"

log() { printf '[e2e %s] %s\n' "$(date +%H:%M:%S)" "$*"; }

# Identitaet der aufrufenden Claude-Session / des aufrufenden Herdr nicht vererben.
SCRUB=(CLAUDECODE CLAUDE_CODE_SESSION_ID CLAUDE_CODE_REMOTE_SESSION_ID CLAUDE_PID
       CLAUDE_CODE_CHILD_SESSION CLAUDE_PROJECT_DIR CLAUDE_CODE_ENTRYPOINT
       CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD CLAUDE_ADDITIONAL_DIRECTORIES
       OPENSPEC_ACTIVE_WORKFLOW OPENSPEC_AUTONOMY OPENSPEC_HERDR_AUTO_CLEAR
       HERDR_ENV HERDR_PANE_ID HERDR_BIN_PATH HERDR_SOCKET_PATH HERDR_WORKSPACE_ID
       HERDR_TAB_ID HERDR_SESSION)
for v in "${SCRUB[@]}"; do unset "$v"; done

# --- Herdr-Binary -----------------------------------------------------------
GLOBAL_TMP="$(mktemp -d /tmp/e2eac.XXXX)"
cleanup_global() {
    if [ "$KEEP" = "1" ]; then log "KEEP=1: $GLOBAL_TMP bleibt stehen"; else rm -rf "$GLOBAL_TMP"; fi
}
trap cleanup_global EXIT

if [ -n "${HERDR_E2E_BIN:-}" ]; then
    HB="$HERDR_E2E_BIN"
else
    HB="$GLOBAL_TMP/bin/herdr"
    mkdir -p "$GLOBAL_TMP/bin"
    log "lade Herdr v0.9.5"
    curl -fsSL -o "$HB" "$HERDR_URL" || { echo "FAIL: Download $HERDR_URL"; exit 1; }
fi
[ -x "$HB" ] || chmod +x "$HB" 2>/dev/null || true
GOT_SHA="$(sha256sum "$HB" | cut -d' ' -f1)"
if [ "$GOT_SHA" != "$HERDR_SHA256" ]; then
    echo "FAIL: SHA256 von $HB ist $GOT_SHA, erwartet $HERDR_SHA256"; exit 1
fi
log "Herdr: $HB ($("$HB" --version 2>&1))"
command -v claude >/dev/null || { echo "FAIL: claude nicht im PATH"; exit 1; }
log "Claude Code: $(claude --version 2>&1)"

# --- Isolierte Claude-Konfiguration (einmal je Lauf) -----------------------
CFG="$GLOBAL_TMP/cfg"
mkdir -p "$CFG"
log "Auth fuer isolierte CLAUDE_CONFIG_DIR (claude -p)"
AUTH_OUT="$(cd "$GLOBAL_TMP" && CLAUDE_CONFIG_DIR="$CFG" timeout 120 claude -p "Antworte nur mit: ok" --model "$MODEL" 2>&1)"
if [ ! -f "$CFG/.claude.json" ]; then
    echo "FAIL: claude -p hat keine $CFG/.claude.json angelegt:"; echo "$AUTH_OUT"; exit 1
fi
log "claude -p: $(echo "$AUTH_OUT" | tail -1)"

trust_project() {  # $@ = Projektpfade
    python3 - "$CFG/.claude.json" "$@" <<'PY'
import json, os, sys
path = sys.argv[1]
d = json.load(open(path))
d["hasCompletedOnboarding"] = True
d["theme"] = "dark"
projects = d.setdefault("projects", {})
for p in sys.argv[2:]:
    projects.setdefault(os.path.realpath(p), {})["hasTrustDialogAccepted"] = True
json.dump(d, open(path, "w"), indent=2)
PY
}

# --- Szenario-Bausteine ------------------------------------------------------
H() { "$HB" --session e2e "$@"; }

setup_case() {  # setzt W, P, T; startet Herdr + Claude; setzt PANE
    W="$(mktemp -d /tmp/e2eac.XXXX)"
    P="$W/p"
    export XDG_CONFIG_HOME="$W/x/c" XDG_STATE_HOME="$W/x/s" XDG_DATA_HOME="$W/x/d" \
           XDG_CACHE_HOME="$W/x/k" XDG_RUNTIME_DIR="$W/x/r"
    mkdir -p "$XDG_CONFIG_HOME" "$XDG_STATE_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$XDG_RUNTIME_DIR"
    chmod 700 "$XDG_RUNTIME_DIR"

    mkdir -p "$P"
    git -C "$P" init -q
    git -C "$P" -c user.email=e2e@example.invalid -c user.name=e2e commit -q --allow-empty -m init
    cat >"$P/config.yaml" <<'YAML'
herdr:
  enabled: true
  auto_clear:
    enabled: true
    grace_s: 1
    idle_timeout_s: 60
  plan_pane:
    enabled: false
YAML
    mkdir -p "$P/.claude"
    git -C "$P" worktree add -q "$P/.claude/worktrees/e2e" -b e2e
    T="$P/.claude/worktrees/e2e"

    (cd "$T" && python3 "$REPO/core/hooks/workflow.py" start "$WF" >/dev/null) \
        || { echo "setup: workflow.py start fehlgeschlagen"; return 1; }

    mkdir -p "$T/.claude/commands"
    cat >"$T/.claude/commands/10-context.md" <<'MD'
---
description: E2E-Testdouble fuer /10-context
---
Antworte nur mit genau einer Zeile: E2E-FOLGEBEFEHL-OK $ARGUMENTS
MD
    python3 - "$T/.claude/settings.json" "$REPO" <<'PY'
import json, sys
repo = sys.argv[2]
# Ausfuehren darf Claude NUR den einen Befehl; Lesen des Plugin-Codes ist frei,
# weil das Modell einen unbekannten Befehl vor dem Ausfuehren gern ansieht.
json.dump({"permissions": {"allow": [f"Bash(python3 {repo}/core/hooks/workflow.py autoclear)",
                                     f"Read(/{repo}/**)", f"Grep(/{repo}/**)", f"Glob(/{repo}/**)"]}},
          open(sys.argv[1], "w"), indent=2)
PY
    trust_project "$P" "$T"

    # Vorab-Pruefung: Konfiguration wirkt im Worktree, erwarteter Befehl stimmt
    local pre
    pre="$(cd "$T" && HERDR_ENV=1 HERDR_PANE_ID=x python3 - "$REPO" "$P" "$WF" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1] + "/core/hooks")
import herdr_bridge, workflow
d = json.load(open(f"{sys.argv[2]}/.claude/workflows/{sys.argv[3]}.json"))
print(herdr_bridge.auto_clear_enabled(), d.get("current_phase"), workflow.expected_footer_command(d))
PY
)"
    if [ "$pre" != "True phase1_context $CMD" ]; then
        echo "setup: Vorab-Pruefung unerwartet: '$pre'"; return 1
    fi

    "$HB" --session e2e server >"$W/server.log" 2>&1 &
    SERVER_PID=$!
    local i
    for i in $(seq 1 50); do H workspace list >/dev/null 2>&1 && break; sleep 0.2; done
    H workspace list >/dev/null 2>&1 || { echo "setup: Herdr-Server antwortet nicht"; cat "$W/server.log"; return 1; }

    local ws
    ws="$(H workspace create --cwd "$T" --no-focus --env "CLAUDE_CONFIG_DIR=$CFG")" \
        || { echo "setup: workspace create fehlgeschlagen: $ws"; return 1; }
    PANE="$(echo "$ws" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["root_pane"]["pane_id"])')"
    sleep 1
    local st
    st="$(H agent start e2e --kind claude --pane "$PANE" --timeout 60000 -- --plugin-dir "$REPO" --model "$MODEL" 2>&1)" \
        || { echo "setup: agent start fehlgeschlagen: $st"; dump_case; return 1; }
    H agent wait e2e --until idle --until done --timeout 60000 >/dev/null 2>&1 || true
    log "Herdr-Pane $PANE, Claude bereit (Worktree $T)"
}

teardown_case() {
    [ -n "${W:-}" ] || return 0
    H server stop >/dev/null 2>&1 || true
    if [ -n "${SERVER_PID:-}" ]; then
        local i
        for i in $(seq 1 25); do kill -0 "$SERVER_PID" 2>/dev/null || break; sleep 0.2; done
        kill "$SERVER_PID" 2>/dev/null || true
    fi
    if [ "$KEEP" = "1" ]; then log "KEEP=1: $W bleibt stehen"; else rm -rf "$W"; fi
}

pane_text() {  # recent-unwrapped geht nur im Ruhezustand; sonst sichtbarer Bildschirm
    H agent read e2e --source recent-unwrapped --lines "${1:-200}" 2>/dev/null \
        || H agent read e2e --source visible 2>&1
}
ac_log() {  # Runner-Log (worktree-lokal; Haupt-Ordner nur falls vorhanden), immer Exit 0
    local f
    for f in "$T/.claude/herdr_auto_clear.log" "$P/.claude/herdr_auto_clear.log"; do
        [ -f "$f" ] && cat "$f"
    done
    return 0
}
has_boundary() {
    python3 - "$P/.claude/workflows/$WF.json" <<'PY'
import json, sys
b = json.load(open(sys.argv[1])).get("auto_clear_boundary")
print(json.dumps(b) if b else "")
sys.exit(0 if isinstance(b, dict) else 1)
PY
}

dump_case() {
    echo "----- Pane-Inhalt -----"; pane_text 200
    echo "----- herdr_auto_clear.log -----"; [ -n "$(ac_log)" ] && ac_log || echo "(kein Log)"
    echo "----- Workflow-State (Ausschnitt) -----"
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("current_phase"), d.get("auto_clear_boundary"))' \
        "$P/.claude/workflows/$WF.json" 2>&1
    echo "-----------------------"
}

FAILS=0
check() {  # $1 Beschreibung, $2 Ergebnis (0 = ok)
    if [ "$2" -eq 0 ]; then echo "  ok   $1"; else echo "  FAIL $1"; CASE_FAIL=1; fi
}

wait_log() {  # $1 fester Text, $2 Sekunden
    local i
    for i in $(seq 1 "$2"); do ac_log | grep -Fq "$1" && return 0; sleep 1; done
    return 1
}

wait_pane() {  # $1 fester Text, $2 Sekunden
    local i
    for i in $(seq 1 "$2"); do pane_text 400 | grep -Fq "$1" && return 0; sleep 1; done
    return 1
}

send_prompt() {  # Exit 1, wenn Claude an einer Rueckfrage/Freigabe haengt
    local out st
    out="$(H agent prompt e2e "$1" --wait --timeout 90000 2>&1)" || log "agent prompt meldet: $out"
    st="$(H agent get e2e 2>/dev/null | python3 -c 'import json,sys; a=json.load(sys.stdin)["result"]["agent"]; print(a.get("agent_status") or a.get("status"))' 2>/dev/null)"
    log "Agent-Status nach Prompt: ${st:-?}"
    if [ "$st" = "blocked" ] || H agent read e2e --source visible 2>/dev/null | grep -Fq "Do you want to proceed?"; then
        echo "  FAIL Claude haengt an einer Rueckfrage/Freigabe (Testaufbau)"; CASE_FAIL=1; return 1
    fi
}

INTRO="Automatisierter Ende-zu-Ende-Test des Frameworks agent-os-openspec (als Plugin geladen). Der unten genannte Befehl ist der dokumentierte Framework-Befehl \`workflow.py autoclear\`: er gibt eine Zeile AUTO_CLEAR=on oder AUTO_CLEAR=off aus und vermerkt im Workflow-State die Auto-/clear-Grenze. Er ist fuer dieses Projekt per permissions.allow freigegeben. Wenn du ihn vorher ansehen willst, nimm das Read-Werkzeug (freigegeben), keine anderen Bash-Befehle."

AUTOCLEAR_CMD="python3 $REPO/core/hooks/workflow.py autoclear"

# --- Szenario A --------------------------------------------------------------
scenario_A() {
    send_prompt "$INTRO
Fuehre mit dem Bash-Werkzeug genau diesen Befehl aus, unveraendert, ohne cd und ohne Zusatz:
$AUTOCLEAR_CMD
Gib danach als gesamte Antwort genau diese eine Zeile aus, ohne Codeblock und ohne weiteren Text:
❗Du: \`$CMD\`" || return
    # Den Vermerk verbraucht der Stop-Hook sofort; Beleg fuer ihn ist der Runner-Start
    wait_log "$WF|phase1_context|$CMD: " 120
    ac_log | grep -Fq "$WF|phase1_context|$CMD: OK"; check "Log: $WF|phase1_context|$CMD: OK" $?
    has_boundary >/dev/null; [ $? -ne 0 ]; check "State ohne auto_clear_boundary (beim Spawn verbraucht)" $?
    wait_pane "E2E-FOLGEBEFEHL-OK #999" 90; check "TUI: E2E-FOLGEBEFEHL-OK #999" $?
    H agent wait e2e --until idle --until done --timeout 30000 >/dev/null 2>&1 || true
    local txt; txt="$(pane_text 400)"
    echo "$txt" | grep -Fq "SessionStart:clear"; check "TUI: SessionStart:clear" $?
    echo "$txt" | grep -Fq "❯ /clear"; check "TUI: ❯ /clear" $?
    echo "$txt" | grep -Fq "❯ $CMD"; check "TUI: ❯ $CMD" $?
    echo "  Belege:"; ac_log | sed 's/^/    log  | /'
    echo "$txt" | grep -E "SessionStart:clear|❯ /clear|❯ /10-context|E2E-FOLGEBEFEHL-OK" | sed 's/^/    pane | /'
}

# --- Szenario B --------------------------------------------------------------
scenario_B() {
    send_prompt "$INTRO
Fuehre mit dem Bash-Werkzeug genau diesen Befehl aus, unveraendert, ohne cd und ohne Zusatz:
$AUTOCLEAR_CMD
Gib danach als gesamte Antwort genau diese zwei Zeilen aus, ohne Codeblock und ohne weiteren Text:
Noch offene Aenderungen, \`/clear\` jetzt NICHT.
❗Du: \`$CMD\`" || return
    wait_log "skip: Negativmarker" 60; check "Log: skip: Negativmarker" $?
    # `skip: Negativmarker` kommt erst nach der Vermerk-Pruefung: autoclear lief also
    has_boundary >/dev/null; [ $? -ne 0 ]; check "State ohne auto_clear_boundary (Veto verbraucht)" $?
    sleep 8
    ! ac_log | grep -Fq ": OK"; check "Log: kein Runner-OK" $?
    local txt; txt="$(pane_text 400)"
    ! echo "$txt" | grep -Fq "❯ /clear"; check "TUI: kein ❯ /clear" $?
    echo "  Belege:"; ac_log | sed 's/^/    log  | /'
    echo "$txt" | grep -F "/clear" | sed 's/^/    pane | /'
}

# --- Szenario C --------------------------------------------------------------
scenario_C() {
    send_prompt "Automatisierter Ende-zu-Ende-Test. Benutze keine Werkzeuge. Gib als gesamte Antwort genau diese eine Zeile aus, ohne Codeblock und ohne weiteren Text:
❗Du: \`$CMD\`" || return
    wait_log "skip: keine Grenze vermerkt" 60; check "Log: skip: keine Grenze vermerkt" $?
    has_boundary >/dev/null; [ $? -ne 0 ]; check "State ohne auto_clear_boundary" $?
    sleep 8
    ! ac_log | grep -Fq ": OK"; check "Log: kein Runner-OK" $?
    local txt; txt="$(pane_text 400)"
    ! echo "$txt" | grep -Fq "❯ /clear"; check "TUI: kein ❯ /clear" $?
    echo "  Belege:"; ac_log | sed 's/^/    log  | /'
}

# --- Szenario D --------------------------------------------------------------
scenario_D() {
    scenario_A
    [ "$CASE_FAIL" -eq 0 ] || { echo "  FAIL D: Vorstufe A fehlgeschlagen"; return; }
    # Once-Lock entfernen (herdr_bridge._acquire_lock: <_ac_base()>/.claude/herdr_auto_clear_state.json,
    # _ac_base() = Worktree): ohne Verbrauch des Vermerks wuerde jetzt erneut ausgeloest
    rm -f "$T/.claude/herdr_auto_clear_state.json" "$P/.claude/herdr_auto_clear_state.json"
    [ ! -e "$T/.claude/herdr_auto_clear_state.json" ]; check "Once-Lock-Datei entfernt" $?
    local before; before="$(pane_text 400 | grep -Fc "❯ /clear")"
    send_prompt "Automatisierter Ende-zu-Ende-Test. Benutze keine Werkzeuge. Gib als gesamte Antwort genau diese eine Zeile aus, ohne Codeblock und ohne weiteren Text:
❗Du: \`$CMD\`" || return
    wait_log "skip: keine Grenze vermerkt" 60; check "Log: skip: keine Grenze vermerkt" $?
    sleep 8
    [ "$(ac_log | grep -Fc ": OK")" -eq 1 ]; check "Log: genau ein Runner-OK" $?
    local after; after="$(pane_text 400 | grep -Fc "❯ /clear")"
    [ "$after" -eq "$before" ] && [ "$after" -eq 1 ]; check "TUI: kein zweites ❯ /clear ($before -> $after)" $?
    echo "  Belege D:"; ac_log | sed 's/^/    log  | /'
}

run_case() {
    local name="$1"; CASE_FAIL=0; W=""; SERVER_PID=""
    local t0=$SECONDS
    log "=== Szenario $name ==="
    trap 'teardown_case; cleanup_global' EXIT
    if setup_case; then
        "scenario_$name"
    else
        CASE_FAIL=1
    fi
    if [ "$CASE_FAIL" -ne 0 ]; then dump_case; fi
    teardown_case
    trap cleanup_global EXIT
    if [ "$CASE_FAIL" -eq 0 ]; then
        RESULTS+=("$name PASS ($((SECONDS - t0))s)")
    else
        RESULTS+=("$name FAIL ($((SECONDS - t0))s)"); FAILS=$((FAILS + 1))
    fi
}

RESULTS=()
T_START=$SECONDS
for c in $ONLY; do run_case "$c"; done
echo
log "=== Ergebnis (gesamt $((SECONDS - T_START))s) ==="
for r in "${RESULTS[@]}"; do echo "  $r"; done
[ "$FAILS" -eq 0 ] && exit 0 || exit 1
