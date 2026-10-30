#!/usr/bin/env bash
# End-to-End-Test des Plan-Pane-Lebenszyklus (#496) mit echtem Herdr 0.9.5 (headless),
# echtem Claude-Code-TUI und diesem Repo als Plugin (--plugin-dir).
#
# Szenarien (Exit 0 nur, wenn alle PASS):
#   a  START         aktiver Workflow, Claude startet -> genau 1 Plan-Pane mit Tokens
#                    owner=<Claude-Pane>, workflow=<Name>, version=<plugin.json>
#   b  EXIT          wie a, dann `/exit` -> 0 Plan-Panes (SessionEnd plan-pane-close)
#   b2 KILL -9       wie a, dann `kill -9` auf Claude -> 0 Plan-Panes nach hoechstens 6 s
#                    (kein SessionEnd; der Watcher bemerkt den toten Owner)
#   c  NEUSTART      wie b, dann Claude erneut im selben Pane -> genau 1 Plan-Pane
#   d  ALTLASTEN     vor dem Start: Plan-Pane mit geloeschtem cwd, eines mit totem
#                    fremdem Owner, eines ohne Tokens (+ normales Kontroll-Pane)
#                    -> nur das eigene neue Plan-Pane bleibt, Kontroll-Pane bleibt
#   e  OHNE WF       kein aktiver Workflow, vorher ein eigenes Plan-Pane -> 0 Plan-Panes
#   f  /clear        wie a, dann `/clear` -> dasselbe Pane, derselbe Watcher-Prozess
#   g  VERSION       vorher ein eigenes Plan-Pane mit altem version-Token -> geschlossen,
#                    neues Pane mit aktueller Version
#   h  ZWEI SESSIONS Claude A und B im selben Workspace, C in einem zweiten Workspace,
#                    je mit eigenem Workflow -> /exit und Neustart von A lassen die
#                    Plan-Panes von B und C unberuehrt (gleiche pane_id vorher/nachher)
#   i  WERKZEUGLAUF  B startet, waehrend A ein Werkzeug ausfuehrt -> A behaelt sein Pane
#   j  GLEICHZEITIG  A und B im selben Workspace starten GLEICHZEITIG, J_REPS-mal
#                    (Default 10) -> jedes Mal hat jede Session genau 1 eigenes Plan-Pane
#                    und kein Runner schliesst ein Pane der anderen (#496 R1 F002)
#   k  AGENT-LABEL   lebendes Claude-Pane B heisst „Workflow“ (pane rename) -> der Sweep
#                    von A laesst B am Leben (#496 R1 F001)
#   l  KIND-CLAUDE   Eltern-Claude mit Workflow + Plan-Pane startet per Bash-Werkzeug zwei
#                    `claude -p` (geerbte HERDR-Env; Worktree mit und ohne Workflow) ->
#                    Plan-Pane der Eltern bleibt: gleiche ID, gleicher Watcher, gleiche Tokens
#                    (#496 R2 F001)
#
# Aufruf:
#   HERDR_E2E_BIN=/pfad/zu/herdr bash scripts/e2e_plan_pane.sh   # vorhandenes Binary
#   bash scripts/e2e_plan_pane.sh                                # laedt v0.9.5, prueft SHA256
#   KEEP=1 ...       laesst die Arbeitsordner stehen
#   ONLY="a h" ...   nur ausgewaehlte Szenarien (Default "a b b2 c d e f g h i j k l")
#   J_REPS=20 ...    Wiederholungen fuer Szenario j (Default 10)
#   E2E_MODEL=...    Modell (Default haiku)
#
# Voraussetzungen: claude (eingeloggt bzw. Auth per Umgebung), git, python3, curl.
# Claude laeuft in Git-Worktrees unter .claude/worktrees/, weil session_singleton_guard
# im Haupt-Ordner Schreib-Tools blockt. Es wird keine Rechtepruefung abgeschaltet:
# freigegeben werden nur einzelne, exakte Bash-Befehle (Szenarien i und l).

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
HERDR_URL="https://github.com/herdrdev/herdr/releases/download/v0.9.5/herdr-linux-x86_64"
HERDR_SHA256="14d9e8bc8b4a9e0118d77c32266f76d461f09b40342eb23752960bd89f59929d"
MODEL="${E2E_MODEL:-haiku}"
KEEP="${KEEP:-0}"
ONLY="${ONLY:-a b b2 c d e f g h i j k l}"
J_REPS="${J_REPS:-10}"
WF="feat-998-plan-e2e"
VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$REPO/.claude-plugin/plugin.json")"

log() { printf '[e2e %s] %s\n' "$(date +%H:%M:%S)" "$*"; }

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
log "Claude Code: $(claude --version 2>&1), Plugin-Version $VERSION, Modell $MODEL"

# --- Isolierte Claude-Konfiguration (einmal je Lauf) -----------------------
CFG="$GLOBAL_TMP/cfg"
mkdir -p "$CFG"
log "Auth fuer isolierte CLAUDE_CONFIG_DIR (claude -p)"
AUTH_OUT="$(cd "$GLOBAL_TMP" && CLAUDE_CONFIG_DIR="$CFG" timeout 120 claude -p "Antworte nur mit: ok" --model haiku 2>&1)"
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

# --- Bausteine ----------------------------------------------------------------
H() { "$HB" --session e2epp "$@"; }

add_worktree() {  # $1 = Name, $2 = Workflow-Name oder leer; gibt den Pfad aus
    local wt="$P/.claude/worktrees/$1"
    git -C "$P" worktree add -q "$wt" -b "$1" >/dev/null 2>&1 || return 1
    if [ -n "$2" ]; then
        (cd "$wt" && python3 "$REPO/core/hooks/workflow.py" start "$2" >/dev/null 2>&1) || return 1
    fi
    trust_project "$wt"
    echo "$wt"
}

setup_case() {  # $1 = Workflow-Name fuer T oder leer; setzt W, P, T, WS1, PANE
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
    enabled: false
YAML
    mkdir -p "$P/.claude"
    trust_project "$P"
    T="$(add_worktree e2e "${1:-}")" || { echo "setup: Worktree/Workflow fehlgeschlagen"; return 1; }

    "$HB" --session e2epp server >"$W/server.log" 2>&1 &
    SERVER_PID=$!
    local i
    for i in $(seq 1 50); do H workspace list >/dev/null 2>&1 && break; sleep 0.2; done
    H workspace list >/dev/null 2>&1 || { echo "setup: Herdr-Server antwortet nicht"; cat "$W/server.log"; return 1; }
    new_workspace "$T" || return 1
    WS1="$NEW_WS"; PANE="$NEW_PANE"
    log "Workspace $WS1, Claude-Pane $PANE (Worktree $T)"
}

new_workspace() {  # $1 = cwd; setzt NEW_WS, NEW_PANE
    local out
    out="$(H workspace create --cwd "$1" --no-focus --env "CLAUDE_CONFIG_DIR=$CFG")" \
        || { echo "setup: workspace create fehlgeschlagen: $out"; return 1; }
    NEW_WS="$(echo "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["workspace"]["workspace_id"])')"
    NEW_PANE="$(echo "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["root_pane"]["pane_id"])')"
    sleep 1
}

split_pane() {  # $1 = Quell-Pane, $2 = cwd, $3 = Richtung; gibt neue pane_id aus
    H pane split "$1" --direction "${3:-down}" --cwd "$2" --no-focus \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])'
}

teardown_case() {
    [ -n "${W:-}" ] || return 0
    H server stop >/dev/null 2>&1 || true
    if [ -n "${SERVER_PID:-}" ]; then
        local i
        for i in $(seq 1 25); do kill -0 "$SERVER_PID" 2>/dev/null || break; sleep 0.2; done
        kill "$SERVER_PID" 2>/dev/null || true
    fi
    pkill -f -- "--session e2epp" 2>/dev/null || true
    if [ "$KEEP" = "1" ]; then log "KEEP=1: $W bleibt stehen"; else rm -rf "$W"; fi
}

panes_json() {  # $1 = Workspace (IMMER mit --workspace)
    H pane list --workspace "$1" 2>/dev/null
}

plans() {  # $1 = Workspace -> Zeilen "pane_id owner workflow version cwd" (nur Label Workflow)
    panes_json "$1" | python3 -c '
import json, sys
try:
    panes = json.load(sys.stdin)["result"]["panes"]
except Exception:
    panes = []
for p in panes:
    if p.get("label") == "Workflow":
        t = p.get("tokens") or {}
        print(p["pane_id"], t.get("owner", "-"), t.get("workflow", "-"), t.get("version", "-"), p.get("cwd"))
'
}
plan_ids() { plans "$1" | awk -v o="${2:-}" 'o=="" || $2==o {print $1}' | sort | tr '\n' ' ' | sed 's/ $//'; }
plan_count() { plans "$1" | awk -v o="${2:-}" 'o=="" || $2==o' | wc -l | tr -d ' '; }
pane_exists() { panes_json "$1" | grep -Fq "\"pane_id\":\"$2\""; }

pane_field() {  # $1 = Pane, $2 = Feld
    H pane get "$1" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["pane"].get(sys.argv[1]))' "$2" 2>/dev/null
}

start_claude() {  # $1 = Pane; wartet, bis das TUI als claude erkannt und bereit ist
    H pane run "$1" "CLAUDE_CONFIG_DIR=$CFG claude --plugin-dir $REPO --model $MODEL" >/dev/null
    local i st
    for i in $(seq 1 120); do
        if [ "$(pane_field "$1" agent)" = "claude" ]; then
            st="$(pane_field "$1" agent_status)"
            [ "$st" = "idle" ] || [ "$st" = "done" ] && return 0
        fi
        sleep 0.5
    done
    echo "  FAIL Claude in $1 nicht bereit (agent=$(pane_field "$1" agent), Status=$(pane_field "$1" agent_status))"
    H pane read "$1" --source visible 2>&1 | tail -20 | sed 's/^/    pane | /'
    CASE_FAIL=1; return 1
}

exit_claude() {  # $1 = Pane; `/exit` tippen, warten bis Claude weg ist
    H pane run "$1" "/exit" >/dev/null
    local i
    for i in $(seq 1 40); do
        [ "$(pane_field "$1" agent)" != "claude" ] && break
        sleep 0.25
    done
}

wait_count() {  # $1 Workspace, $2 Owner oder "", $3 erwartete Zahl, $4 Sekunden
    local i n
    for i in $(seq 1 $(( $4 * 4 ))); do
        n="$(plan_count "$1" "$2")"
        [ "$n" = "$3" ] && return 0
        sleep 0.25
    done
    return 1
}

runner_log() {  # Runner-Log (worktree-lokal), immer Exit 0
    local f
    for f in "$@"; do [ -f "$f/.claude/herdr_plan_pane.log" ] && sed "s|^|$(basename "$f"): |" "$f/.claude/herdr_plan_pane.log"; done
    return 0
}

fake_plan() {  # $1 Quell-Pane, $2 cwd, $3.. Tokens (k=v); gibt pane_id aus
    local src="$1" cwd="$2"; shift 2
    local id
    id="$(split_pane "$src" "$cwd" right)" || return 1
    H pane rename "$id" Workflow >/dev/null
    if [ $# -gt 0 ]; then
        local args=() t
        for t in "$@"; do args+=(--token "$t"); done
        H pane report-metadata "$id" --source user:openspec "${args[@]}" >/dev/null
    fi
    echo "$id"
}

show() {  # Beleg: pane list des Workspace
    echo "    pane list --workspace $1:"
    panes_json "$1" | python3 -c '
import json, sys
for p in json.load(sys.stdin)["result"]["panes"]:
    print("      ", p["pane_id"], "label=%s" % p.get("label"), "agent=%s" % p.get("agent"),
          "tokens=%s" % json.dumps(p.get("tokens") or {}, sort_keys=True), "cwd=%s" % p.get("cwd"))
' 2>/dev/null
}

FAILS=0
check() {  # $1 Beschreibung, $2 Ergebnis (0 = ok)
    if [ "$2" -eq 0 ]; then echo "  ok   $1"; else echo "  FAIL $1"; CASE_FAIL=1; fi
}

tokens_ok() {  # $1 Workspace, $2 Owner, $3 Workflow
    [ "$(plans "$1" | awk -v o="$2" '$2==o {print $3, $4}')" = "$3 $VERSION" ]
}

# --- Szenarien ----------------------------------------------------------------
scenario_a() {
    setup_case "$WF" || { CASE_FAIL=1; return; }
    start_claude "$PANE" || return
    wait_count "$WS1" "$PANE" 1 20; check "genau 1 Plan-Pane fuer Owner $PANE" $?
    [ "$(plan_count "$WS1")" = 1 ]; check "genau 1 Plan-Pane im Workspace" $?
    tokens_ok "$WS1" "$PANE" "$WF"; check "Tokens owner=$PANE workflow=$WF version=$VERSION" $?
    local pp; pp="$(plan_ids "$WS1" "$PANE")"
    local cmd; cmd="$(H pane process-info --pane "$pp" 2>/dev/null | grep -o "plan --watch --target [^\"]*" | head -1)"
    [ "$cmd" = "plan --watch --target $PANE" ]; check "Watcher laeuft: '$cmd'" $?
    show "$WS1"; runner_log "$T" | sed 's/^/    log  | /'
}

scenario_b() {
    setup_case "$WF" || { CASE_FAIL=1; return; }
    start_claude "$PANE" || return
    wait_count "$WS1" "$PANE" 1 20; check "Vorstufe: 1 Plan-Pane" $?
    local pp; pp="$(plan_ids "$WS1" "$PANE")"
    local t0; t0="$(date +%s.%N)"
    exit_claude "$PANE"
    wait_count "$WS1" "" 0 6; check "/exit -> 0 Plan-Panes" $?
    log "Plan-Pane $pp weg nach $(python3 -c "import time; print(round(time.time()-$t0,2))") s"
    pane_exists "$WS1" "$PANE"; check "Claude-Pane $PANE selbst bleibt" $?
    show "$WS1"
}

claude_pid() {  # $1 = Pane
    H pane process-info --pane "$1" 2>/dev/null | python3 -c '
import json, sys
fp = json.load(sys.stdin)["result"]["process_info"]["foreground_processes"]
print([p["pid"] for p in fp if "claude" in " ".join(p.get("cmdline") or []) or "claude" in str(p.get("cmdline"))][0])' 2>/dev/null
}

scenario_b2() {
    setup_case "$WF" || { CASE_FAIL=1; return; }
    start_claude "$PANE" || return
    wait_count "$WS1" "$PANE" 1 20; check "Vorstufe: 1 Plan-Pane" $?
    local pid; pid="$(claude_pid "$PANE")"
    [ -n "$pid" ]; check "Claude-PID ermittelt ($pid)" $?
    [ -n "$pid" ] || return
    kill -9 "$pid"
    local t0=$SECONDS
    wait_count "$WS1" "" 0 6; check "kill -9 -> 0 Plan-Panes nach <= 6 s ($((SECONDS - t0)) s)" $?
    show "$WS1"
}

scenario_c() {
    setup_case "$WF" || { CASE_FAIL=1; return; }
    start_claude "$PANE" || return
    wait_count "$WS1" "$PANE" 1 20; check "Vorstufe: 1 Plan-Pane" $?
    local first; first="$(plan_ids "$WS1" "$PANE")"
    exit_claude "$PANE"
    wait_count "$WS1" "" 0 6; check "/exit -> 0 Plan-Panes" $?
    sleep 4
    start_claude "$PANE" || return
    wait_count "$WS1" "$PANE" 1 20; check "Neustart im selben Pane -> genau 1 Plan-Pane" $?
    sleep 3
    [ "$(plan_count "$WS1")" = 1 ]; check "weiter genau 1 Plan-Pane im Workspace" $?
    local second; second="$(plan_ids "$WS1" "$PANE")"
    [ -n "$second" ] && [ "$second" != "$first" ]; check "neues Pane ($first -> $second)" $?
    tokens_ok "$WS1" "$PANE" "$WF"; check "Tokens aktuell" $?
    show "$WS1"; runner_log "$T" | sed 's/^/    log  | /'
}

scenario_d() {
    setup_case "$WF" || { CASE_FAIL=1; return; }
    local gone="$W/gone"; mkdir -p "$gone"
    local del dead raw ctl
    del="$(fake_plan "$PANE" "$gone" "owner=w9:p9" "workflow=alt" "version=$VERSION")"
    dead="$(fake_plan "$PANE" "$T" "owner=w1:p99" "workflow=alt" "version=$VERSION")"
    raw="$(fake_plan "$PANE" "$T")"
    ctl="$(split_pane "$PANE" "$T" down)"
    rm -rf "$gone"
    sleep 1
    echo "  Altlasten: deleted=$del toter-owner=$dead ohne-tokens=$raw, Kontrolle=$ctl"
    show "$WS1"
    plans "$WS1" | grep -F "$del" | grep -Fq "(deleted)"; check "Vorbedingung: cwd von $del endet auf (deleted)" $?
    start_claude "$PANE" || return
    wait_count "$WS1" "" 1 20; check "nur noch 1 Plan-Pane im Workspace" $?
    [ "$(plan_count "$WS1" "$PANE")" = 1 ]; check "das verbliebene gehoert $PANE" $?
    local id
    for id in "$del" "$dead" "$raw"; do
        ! pane_exists "$WS1" "$id"; check "Altlast $id geschlossen" $?
    done
    pane_exists "$WS1" "$ctl"; check "Kontroll-Pane $ctl (kein Plan-Pane) bleibt" $?
    show "$WS1"; runner_log "$T" | sed 's/^/    log  | /'
}

scenario_e() {
    setup_case "" || { CASE_FAIL=1; return; }
    local own; own="$(fake_plan "$PANE" "$T" "owner=$PANE" "workflow=$WF" "version=$VERSION")"
    echo "  eigenes Plan-Pane ohne aktiven Workflow: $own"
    start_claude "$PANE" || return
    wait_count "$WS1" "" 0 15; check "ohne aktiven Workflow -> 0 Plan-Panes" $?
    sleep 3
    [ "$(plan_count "$WS1")" = 0 ]; check "es wird auch nichts nachtraeglich geoeffnet" $?
    show "$WS1"; runner_log "$T" | sed 's/^/    log  | /'
}

watcher_pid() {  # $1 = Plan-Pane
    H pane process-info --pane "$1" 2>/dev/null | python3 -c '
import json, sys
fp = json.load(sys.stdin)["result"]["process_info"]["foreground_processes"]
print(" ".join(str(p["pid"]) for p in fp if "--watch" in str(p.get("cmdline"))))' 2>/dev/null
}

scenario_f() {
    setup_case "$WF" || { CASE_FAIL=1; return; }
    start_claude "$PANE" || return
    wait_count "$WS1" "$PANE" 1 20; check "Vorstufe: 1 Plan-Pane" $?
    local pp wp; pp="$(plan_ids "$WS1" "$PANE")"; wp="$(watcher_pid "$pp")"
    local before; before="$(runner_log "$T" | grep -c "plan-pane:")"
    H pane run "$PANE" "/clear" >/dev/null
    local i
    for i in $(seq 1 60); do
        [ "$(runner_log "$T" | grep -c "behalten")" -ge 1 ] && break
        sleep 0.5
    done
    runner_log "$T" | grep -Fq "$pp behalten"; check "SessionStart(clear): Runner behielt $pp" $?
    sleep 2
    [ "$(plan_ids "$WS1")" = "$pp" ]; check "dasselbe Pane, kein zweites ($(plan_ids "$WS1"))" $?
    local wp2; wp2="$(watcher_pid "$pp")"
    [ -n "$wp" ] && [ "$wp" = "$wp2" ]; check "derselbe Watcher-Prozess ($wp -> $wp2)" $?
    H pane read "$PANE" --source recent --lines 60 2>/dev/null | grep -F "/clear" | head -3 | sed 's/^/    pane | /'
    show "$WS1"; runner_log "$T" | sed 's/^/    log  | /'
}

scenario_g() {
    setup_case "$WF" || { CASE_FAIL=1; return; }
    local old; old="$(fake_plan "$PANE" "$T" "owner=$PANE" "workflow=$WF" "version=0.0.0-alt")"
    echo "  eigenes Plan-Pane mit altem version-Token: $old"
    start_claude "$PANE" || return
    wait_count "$WS1" "$PANE" 1 20; check "genau 1 Plan-Pane" $?
    ! pane_exists "$WS1" "$old"; check "altes Pane $old geschlossen" $?
    tokens_ok "$WS1" "$PANE" "$WF"; check "neues Pane $(plan_ids "$WS1") mit version=$VERSION" $?
    show "$WS1"; runner_log "$T" | sed 's/^/    log  | /'
}

scenario_h() {
    setup_case "$WF" || { CASE_FAIL=1; return; }
    local tb tc
    tb="$(add_worktree e2e-b "${WF}-b")" || { echo "  FAIL Worktree B"; CASE_FAIL=1; return; }
    tc="$(add_worktree e2e-c "${WF}-c")" || { echo "  FAIL Worktree C"; CASE_FAIL=1; return; }
    local pb; pb="$(split_pane "$PANE" "$tb" down)"
    new_workspace "$tc" || { CASE_FAIL=1; return; }
    local ws2="$NEW_WS" pc="$NEW_PANE"
    echo "  A=$PANE (Workspace $WS1), B=$pb (Workspace $WS1), C=$pc (Workspace $ws2)"
    start_claude "$pb" || return
    start_claude "$pc" || return
    wait_count "$WS1" "$pb" 1 20; check "B hat 1 Plan-Pane" $? || true
    if [ "$CASE_FAIL" -ne 0 ]; then
        H pane read "$pb" --source visible 2>&1 | tail -30 | sed 's/^/    B    | /'
    fi
    wait_count "$ws2" "$pc" 1 20; check "C hat 1 Plan-Pane" $?
    local ppb ppc; ppb="$(plan_ids "$WS1" "$pb")"; ppc="$(plan_ids "$ws2" "$pc")"
    start_claude "$PANE" || return
    wait_count "$WS1" "$PANE" 1 20; check "A hat 1 Plan-Pane" $?
    sleep 3
    [ "$(plan_ids "$WS1" "$pb")" = "$ppb" ]; check "Start A: Plan-Pane von B unveraendert ($ppb)" $?
    [ "$(plan_ids "$ws2" "$pc")" = "$ppc" ]; check "Start A: Plan-Pane von C unveraendert ($ppc)" $?
    exit_claude "$PANE"
    wait_count "$WS1" "$PANE" 0 6; check "/exit A: Plan-Pane von A weg" $?
    sleep 2
    [ "$(plan_ids "$WS1" "$pb")" = "$ppb" ]; check "/exit A: Plan-Pane von B unveraendert ($ppb)" $?
    [ "$(plan_ids "$ws2" "$pc")" = "$ppc" ]; check "/exit A: Plan-Pane von C unveraendert ($ppc)" $?
    sleep 4
    start_claude "$PANE" || return
    wait_count "$WS1" "$PANE" 1 20; check "Neustart A: wieder 1 Plan-Pane fuer A" $?
    sleep 3
    [ "$(plan_ids "$WS1" "$pb")" = "$ppb" ]; check "Neustart A: Plan-Pane von B unveraendert ($ppb)" $?
    [ "$(plan_ids "$ws2" "$pc")" = "$ppc" ]; check "Neustart A: Plan-Pane von C unveraendert ($ppc)" $?
    tokens_ok "$WS1" "$pb" "${WF}-b"; check "B: Tokens workflow=${WF}-b" $?
    tokens_ok "$ws2" "$pc" "${WF}-c"; check "C: Tokens workflow=${WF}-c" $?
    [ "$(plan_count "$WS1")" = 2 ] && [ "$(plan_count "$ws2")" = 1 ]; check "Workspace $WS1: 2 Plan-Panes, $ws2: 1" $?
    show "$WS1"; show "$ws2"; runner_log "$T" "$tb" "$tc" | sed 's/^/    log  | /'
}

probe_owner() {  # $1 Pane, $2 Datei: alle 0,5 s `pane get` + process-info protokollieren
    while :; do
        {
            printf '%s ' "$(date +%s.%N | cut -c1-14)"
            H pane get "$1" 2>&1 | python3 -c '
import json, sys
try:
    p = json.load(sys.stdin)["result"]["pane"]
    print("rc=0 agent=%s agent_status=%s" % (p.get("agent"), p.get("agent_status")), end=" ")
except Exception as e:
    print("rc=? fehler=%s" % type(e).__name__, end=" ")'
            H pane process-info --pane "$1" 2>/dev/null | python3 -c '
import json, sys
try:
    fp = json.load(sys.stdin)["result"]["process_info"]["foreground_processes"]
    cmd = lambda c: (c if isinstance(c, str) else " ".join(c or []))[:30].replace(" ", "_")
    print("fg=" + ",".join(cmd(p.get("cmdline")) for p in fp))
except Exception:
    print("fg=?")'
        } >>"$2"
        sleep 0.5
    done
}

scenario_i() {
    setup_case "$WF" || { CASE_FAIL=1; return; }
    # Genau EIN Werkzeugaufruf ist freigegeben: Bash `sleep 20` (keine abgeschaltete Pruefung)
    python3 - "$T/.claude/settings.json" <<'PY'
import json, sys
json.dump({"permissions": {"allow": ["Bash(sleep 20)"]}}, open(sys.argv[1], "w"), indent=2)
PY
    local tb; tb="$(add_worktree e2e-b "${WF}-b")" || { echo "  FAIL Worktree B"; CASE_FAIL=1; return; }
    start_claude "$PANE" || return
    wait_count "$WS1" "$PANE" 1 20; check "Vorstufe: A hat 1 Plan-Pane" $?
    local ppa wpa; ppa="$(plan_ids "$WS1" "$PANE")"; wpa="$(watcher_pid "$ppa")"
    local probe="$W/probe.log"
    probe_owner "$PANE" "$probe" &
    local probe_pid=$!
    H pane run "$PANE" "Automatisierter Test. Fuehre mit dem Bash-Werkzeug genau den Befehl sleep 20 aus, unveraendert, ohne Zusatz. Danach antworte nur: fertig" >/dev/null
    local i t_sleep=""
    for i in $(seq 1 60); do
        pgrep -f "^(/bin/)?(ba|z)?sh .*sleep 20|^sleep 20$" >/dev/null 2>&1 && { t_sleep=$SECONDS; break; }
        sleep 0.5
    done
    [ -n "$t_sleep" ]; check "A fuehrt sleep 20 per Bash aus" $?
    local pb; pb="$(split_pane "$PANE" "$tb" down)"
    echo "  B=$pb startet waehrend A's Werkzeuglauf"
    start_claude "$pb" || { kill "$probe_pid" 2>/dev/null; return; }
    wait_count "$WS1" "$pb" 1 20; check "B hat 1 Plan-Pane" $?
    pgrep -f "^sleep 20$" >/dev/null 2>&1; check "B fertig gestartet, waehrend sleep 20 noch laeuft" $?
    [ "$(plan_ids "$WS1" "$PANE")" = "$ppa" ]; check "nach Start von B: Plan-Pane von A unveraendert ($ppa)" $?
    for i in $(seq 1 60); do pgrep -f "^sleep 20$" >/dev/null 2>&1 || break; sleep 0.5; done
    sleep 3
    kill "$probe_pid" 2>/dev/null; wait "$probe_pid" 2>/dev/null
    [ "$(plan_ids "$WS1" "$PANE")" = "$ppa" ]; check "nach sleep 20: Plan-Pane von A unveraendert ($ppa)" $?
    local wpa2; wpa2="$(watcher_pid "$ppa")"
    [ -n "$wpa" ] && [ "$wpa" = "$wpa2" ]; check "Watcher von A lief durch ($wpa -> $wpa2)" $?
    local n bad
    n="$(wc -l <"$probe")"; bad="$(grep -vc "agent=claude " "$probe")"
    [ "$n" -ge 20 ] && [ "$bad" -eq 0 ]; check "pane get A: $n Proben, davon $bad ohne agent=claude" $?
    echo "    Statuswerte: $(grep -o 'agent_status=[a-z_]*' "$probe" | sort | uniq -c | tr -s ' ' | tr '\n' ';')"
    echo "    Proben (Auszug):"; sed -n '1,4p;$p' "$probe" | sed 's/^/      /'
    grep -F "sleep" "$probe" | head -2 | sed 's/^/      sleep| /'
    H pane read "$PANE" --source recent --lines 40 2>/dev/null | grep -E "sleep 20|fertig" | head -4 | sed 's/^/    pane | /'
    show "$WS1"; runner_log "$T" "$tb" | sed 's/^/    log  | /'
}

wait_ready() {  # $1 = Pane; wie start_claude, nur ohne `pane run`
    local i st
    for i in $(seq 1 120); do
        if [ "$(pane_field "$1" agent)" = "claude" ]; then
            st="$(pane_field "$1" agent_status)"
            [ "$st" = "idle" ] || [ "$st" = "done" ] && return 0
        fi
        sleep 0.5
    done
    echo "  FAIL Claude in $1 nicht bereit (agent=$(pane_field "$1" agent))"
    CASE_FAIL=1; return 1
}

scenario_j() {
    setup_case "$WF" || { CASE_FAIL=1; return; }
    local tb; tb="$(add_worktree e2e-b "${WF}-b")" || { echo "  FAIL Worktree B"; CASE_FAIL=1; return; }
    local pb; pb="$(split_pane "$PANE" "$tb" down)"
    echo "  A=$PANE, B=$pb (beide Workspace $WS1), $J_REPS gleichzeitige Starts"
    local cmd="CLAUDE_CONFIG_DIR=$CFG claude --plugin-dir $REPO --model $MODEL"
    local rep ok_reps=0 na nb n
    for rep in $(seq 1 "$J_REPS"); do
        # explizite PIDs: ein blankes `wait` wartete auch auf den Herdr-Server
        local ja jb
        H pane run "$PANE" "$cmd" >/dev/null & ja=$!
        H pane run "$pb" "$cmd" >/dev/null & jb=$!
        wait "$ja" "$jb"
        wait_ready "$PANE" || return
        wait_ready "$pb" || return
        wait_count "$WS1" "$PANE" 1 20; wait_count "$WS1" "$pb" 1 20
        sleep 3  # > PP_ORPHAN_GRACE_S: ein spaeter Close der anderen Session waere jetzt sichtbar
        na="$(plan_count "$WS1" "$PANE")"; nb="$(plan_count "$WS1" "$pb")"; n="$(plan_count "$WS1")"
        if [ "$na" = 1 ] && [ "$nb" = 1 ] && [ "$n" = 2 ]; then
            ok_reps=$((ok_reps + 1)); echo "  rep $rep: ok (A=$(plan_ids "$WS1" "$PANE") B=$(plan_ids "$WS1" "$pb"))"
        else
            echo "  rep $rep: FAIL A=$na B=$nb gesamt=$n"; show "$WS1"
        fi
        exit_claude "$PANE" & ja=$!
        exit_claude "$pb" & jb=$!
        wait "$ja" "$jb"
        wait_count "$WS1" "" 0 8 || { echo "  rep $rep: nach /exit noch $(plan_count "$WS1") Plan-Panes"; }
        sleep 2
    done
    [ "$ok_reps" = "$J_REPS" ]; check "gleichzeitiger Start: $ok_reps/$J_REPS mit je genau 1 eigenem Plan-Pane" $?
    local foreign
    foreign="$(runner_log "$T" "$tb" | grep -c "Altlast")"
    [ "$foreign" = 0 ]; check "kein Runner schloss ein Pane als ownerlose Altlast ($foreign)" $?
    runner_log "$T" "$tb" | grep -E "close|uebersprungen" | sed 's/^/    log  | /'
}

scenario_k() {
    setup_case "$WF" || { CASE_FAIL=1; return; }
    local tb; tb="$(add_worktree e2e-b "")" || { echo "  FAIL Worktree B"; CASE_FAIL=1; return; }
    local pb; pb="$(split_pane "$PANE" "$tb" down)"
    start_claude "$pb" || return
    H pane rename "$pb" Workflow >/dev/null
    sleep 1
    [ "$(pane_field "$pb" label)" = "Workflow" ] && [ "$(pane_field "$pb" agent)" = "claude" ]
    check "Vorbedingung: Claude-Pane B=$pb heisst Workflow (agent=claude)" $?
    show "$WS1"
    start_claude "$PANE" || return
    wait_count "$WS1" "$PANE" 1 20; check "A hat 1 Plan-Pane" $?
    sleep 3
    pane_exists "$WS1" "$pb"; check "Claude-Pane B=$pb lebt nach dem Sweep von A" $?
    [ "$(pane_field "$pb" agent)" = "claude" ]; check "B ist weiter eine Claude-Session" $?
    ! runner_log "$T" | grep -Fq "close $pb"; check "Runner von A hat $pb nicht angefasst" $?
    show "$WS1"; runner_log "$T" "$tb" | sed 's/^/    log  | /'
}

scenario_l() {
    setup_case "$WF" || { CASE_FAIL=1; return; }
    local tb; tb="$(add_worktree e2e-b "")" || { echo "  FAIL Worktree B"; CASE_FAIL=1; return; }
    # Kind-Claude wie aus dem Bash-Werkzeug bzw. einem Skript der Eltern-Session: erbt die
    # HERDR-Env, laeuft einmal im Worktree MIT aktivem Workflow, einmal in einem OHNE.
    local kid="$W/kind.sh" done="$W/kind.done" klog="$W/kind.log"
    cat >"$kid" <<KID
#!/usr/bin/env bash
exec >"$klog" 2>&1
for d in "$T" "$tb"; do
    echo "== Kind in \$d: HERDR_PANE_ID=\$HERDR_PANE_ID eltern-CLAUDE_PID=\$CLAUDE_PID"
    (cd "\$d" && timeout 180 claude -p "Antworte nur OK" --plugin-dir "$REPO" --model "$MODEL" </dev/null 2>&1)
    echo "kind-rc=\$?"
done
touch "$done"
KID
    chmod +x "$kid"
    python3 - "$T/.claude/settings.json" "$kid" <<'PY'
import json, sys
json.dump({"permissions": {"allow": [f"Bash(bash {sys.argv[2]})"]}}, open(sys.argv[1], "w"), indent=2)
PY
    start_claude "$PANE" || return
    wait_count "$WS1" "$PANE" 1 20; check "Vorstufe: Eltern-Claude $PANE hat 1 Plan-Pane" $?
    local pp wp tk; pp="$(plan_ids "$WS1" "$PANE")"; wp="$(watcher_pid "$pp")"
    tk="$(plans "$WS1" | awk -v o="$PANE" '$2==o')"
    H pane run "$PANE" "Automatisierter Test. Fuehre mit dem Bash-Werkzeug genau den Befehl bash $kid aus, unveraendert, ohne Zusatz. Danach antworte nur: fertig" >/dev/null
    local i
    for i in $(seq 1 480); do [ -f "$done" ] && break; sleep 0.5; done
    [ -f "$done" ]; check "Eltern-Claude startete beide Kind-Sessions (claude -p)" $?
    [ -f "$done" ] || H pane read "$PANE" --source visible 2>&1 | tail -25 | sed 's/^/    pane | /'
    sed 's/^/    kind | /' "$klog" 2>/dev/null
    [ "$(grep -c '^kind-rc=0$' "$klog" 2>/dev/null)" = 2 ]; check "beide Kind-Sessions liefen durch (Exit 0)" $?
    sleep 3  # > PP_ORPHAN_GRACE_S
    [ "$(pane_field "$PANE" agent)" = "claude" ]; check "Eltern-Claude $PANE lebt weiter" $?
    [ "$(plan_ids "$WS1" "$PANE")" = "$pp" ]; check "Plan-Pane der Eltern unveraendert ($pp)" $?
    [ "$(plan_count "$WS1")" = 1 ]; check "genau 1 Plan-Pane im Workspace" $?
    [ -n "$wp" ] && [ "$(watcher_pid "$pp")" = "$wp" ]; check "Watcher der Eltern lief durch ($wp -> $(watcher_pid "$pp"))" $?
    [ "$(plans "$WS1" | awk -v o="$PANE" '$2==o')" = "$tk" ]; check "Tokens/cwd unveraendert ($tk)" $?
    local skipped; skipped="$(runner_log "$T" "$tb" | grep -c 'nichts angefasst')"
    [ "$skipped" = 2 ]; check "SessionStart beider Kinder lief und fasste nichts an ($skipped/2)" $?
    show "$WS1"; runner_log "$T" "$tb" | sed 's/^/    log  | /'
    exit_claude "$PANE"
    wait_count "$WS1" "" 0 6; check "Kontrolle: /exit der Eltern -> 0 Plan-Panes" $?
}

run_case() {
    local name="$1"; CASE_FAIL=0; W=""; SERVER_PID=""
    local t0=$SECONDS
    log "=== Szenario $name ==="
    trap 'teardown_case; cleanup_global' EXIT
    "scenario_$name"
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
