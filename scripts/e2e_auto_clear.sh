#!/usr/bin/env bash
# End-to-End-Test der Auto-/clear-Kette (#467/#495/#497) mit echtem Claude-Code-TUI,
# diesem Repo als Plugin (--plugin-dir) und echtem Herdr 0.9.5 (headless).
#
# Szenarien (Exit 0 nur, wenn alle PASS):
#   A  REALISTISCH   (A', #497) Claude fuehrt per Bash NUR `workflow.py phase
#                    phase2_analyse` aus (kein `autoclear`) und gibt die ❗Du-Zeile
#                    `/20-analyse #999` aus -> der Phasenwechsel vermerkt die Grenze,
#                    Herdr tippt /clear + Folgebefehl (Testdouble 20-analyse).
#   B  NEGATIV       wie A, aber mit "`/clear` jetzt NICHT" -> skip: Negativmarker.
#   C  OHNE VERMERK  kein Grenz-Phasenwechsel, nur die ❗Du-Zeile `/10-context #999`
#                    -> skip: keine Grenze vermerkt.
#   D  VERBRAUCHT    A, danach (Once-Lock geloescht) ein weiterer Turn mit derselben
#                    ❗Du-Zeile ohne Phasenwechsel -> skip: keine Grenze vermerkt, kein
#                    zweites /clear (Vermerk ist Einmal-Signal, #495 F001).
#   E  ECHT          (nur explizit per ONLY=E) echter Plugin-Befehl
#                    `/agent-os-openspec:10-context #999` in einem Wegwerf-Projekt mit
#                    grossem Modell (E2E_MODEL, Default opus) -> phase2_analyse, Herdr
#                    tippt /clear + /agent-os-openspec:20-analyse #999 (keine Aliase,
#                    #499), der echte 20-analyse startet. /10-context setzt context_file
#                    selbst (#500), keine Hilfsregel dafuer.
#                    Rechte: eng gefasste permissions.allow, keine abgeschaltete Pruefung.
#   F  PLUGIN-FORM   (#499) wie A, aber ohne Testdouble und ohne Aliase (nur
#                    --plugin-dir) -> Herdr tippt /agent-os-openspec:20-analyse #999,
#                    der Plugin-Befehl startet, kein "Unknown command".
#
# Aufruf:
#   HERDR_E2E_BIN=/pfad/zu/herdr bash scripts/e2e_auto_clear.sh   # vorhandenes Binary
#   bash scripts/e2e_auto_clear.sh                                # laedt v0.9.5, prueft SHA256
#   KEEP=1 ...      laesst die Arbeitsordner stehen
#   ONLY="A C" ...  nur ausgewaehlte Szenarien (Default "A B C D F"; E nur explizit)
#   E2E_MODEL=...   Modell (Default haiku fuer A-D, opus fuer E)
#
# Voraussetzungen: claude (eingeloggt bzw. Auth per Umgebung), git, python3, curl.
# Die Session laeuft in einem Git-Worktree unter .claude/worktrees/e2e, weil
# session_singleton_guard im Haupt-Ordner jeden Bash-Aufruf blockt.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
HERDR_URL="https://github.com/herdrdev/herdr/releases/download/v0.9.5/herdr-linux-x86_64"
HERDR_SHA256="14d9e8bc8b4a9e0118d77c32266f76d461f09b40342eb23752960bd89f59929d"
WF="feat-999-e2e"
CMD10="/10-context #999"
CMD="/20-analyse #999"
PCMD="/agent-os-openspec:20-analyse #999"   # getippte Form ohne Aliase (#499)
MODEL_AD="${E2E_MODEL:-haiku}"
MODEL_E="${E2E_MODEL:-opus}"
MODEL="$MODEL_AD"
E_TIMEOUT_S="${E_TIMEOUT_S:-900}"
KEEP="${KEEP:-0}"
ONLY="${ONLY:-A B C D F}"

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

# --- Szenario-Bausteine ------------------------------------------------------
H() { "$HB" --session e2e "$@"; }

setup_case() {  # $1 = stub|plugin|real; setzt W, P, T; startet Herdr + Claude; setzt PANE
    local mode="${1:-stub}"
    W="$(mktemp -d /tmp/e2eac.XXXX)"
    P="$W/p"
    export XDG_CONFIG_HOME="$W/x/c" XDG_STATE_HOME="$W/x/s" XDG_DATA_HOME="$W/x/d" \
           XDG_CACHE_HOME="$W/x/k" XDG_RUNTIME_DIR="$W/x/r"
    mkdir -p "$XDG_CONFIG_HOME" "$XDG_STATE_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$XDG_RUNTIME_DIR"
    chmod 700 "$XDG_RUNTIME_DIR"

    mkdir -p "$P"
    git -C "$P" init -q
    if [ "$mode" = "real" ]; then write_demo_project "$P"; fi
    git -C "$P" add -A
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

    mkdir -p "$T/.claude"
    if [ "$mode" = "real" ]; then
        # Keine Aliase (#499): Herdr tippt die Plugin-Form, die mit --plugin-dir existiert
        write_real_settings "$T/.claude/settings.json"
    else
        # Vorbedingung des Grenz-Phasenwechsels 1->2 (sonst blockt workflow.py phase)
        (cd "$T" && python3 "$REPO/core/hooks/workflow.py" set-field context_file \
            "docs/context/$WF.md" >/dev/null) || { echo "setup: set-field fehlgeschlagen"; return 1; }
        mkdir -p "$T/.claude/commands"
        # F (plugin): kein Testdouble, kein Alias -> Plugin-Form (#499)
        [ "$mode" = "plugin" ] || cat >"$T/.claude/commands/20-analyse.md" <<'MD'
---
description: E2E-Testdouble fuer /20-analyse
---
Antworte nur mit genau einer Zeile: E2E-FOLGEBEFEHL-OK $ARGUMENTS
MD
        python3 - "$T/.claude/settings.json" "$REPO" <<'PY'
import json, sys
repo = sys.argv[2]
# Ausfuehren darf Claude NUR den einen Phasenwechsel; Lesen des Plugin-Codes ist frei,
# weil das Modell einen unbekannten Befehl vor dem Ausfuehren gern ansieht.
json.dump({"permissions": {"allow": [
    f"Bash(python3 {repo}/core/hooks/workflow.py phase phase2_analyse)",
    f"Read(/{repo}/**)", f"Grep(/{repo}/**)", f"Glob(/{repo}/**)"]}},
          open(sys.argv[1], "w"), indent=2)
PY
    fi
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
    if [ "$pre" != "True phase1_context $CMD10" ]; then
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
    local extra=()
    if [ "$mode" = "real" ]; then extra=(--permission-mode acceptEdits); fi
    st="$(H agent start e2e --kind claude --pane "$PANE" --timeout 60000 -- --plugin-dir "$REPO" --model "$MODEL" "${extra[@]}" 2>&1)" \
        || { echo "setup: agent start fehlgeschlagen: $st"; dump_case; return 1; }
    H agent wait e2e --until idle --until done --timeout 60000 >/dev/null 2>&1 || true
    log "Herdr-Pane $PANE, Claude bereit (Worktree $T)"
}

write_demo_project() {  # $1 = Projektordner; 3 kleine Dateien fuer Szenario E
    mkdir -p "$1/src" "$1/tests"
    cat >"$1/README.md" <<'MD'
# Gruss-Demo

Kleines Wegwerf-Projekt fuer den E2E-Test. `src/greeting.py` erzeugt Grussformeln.
Issue #999: `greet()` soll den Namen optional machen ("Hallo!" ohne Namen).
MD
    cat >"$1/src/greeting.py" <<'PY'
def greet(name):
    """Grussformel fuer einen Namen."""
    return f"Hallo, {name}!"
PY
    cat >"$1/tests/test_greeting.py" <<'PY'
from src.greeting import greet


def test_greet_name():
    assert greet("Ada") == "Hallo, Ada!"
PY
}

write_real_settings() {  # $1 = settings.json; eng gefasste Allow-Liste fuer Szenario E
    python3 - "$1" "$REPO" "$W" <<'PY'
import json, sys
path, repo, w = sys.argv[1:4]
hooks = f"{repo}/core/hooks"
allow = ["Read", "Grep", "Glob", f"Read(/{repo}/**)",
         f"Edit(/{w}/**)", f"Write(/{w}/**)", "Edit(docs/context/**)", "Write(docs/context/**)",
         f"Bash(python3 {hooks}/workflow.py:*)", f"Bash(python3 {hooks}/session_singleton_guard.py:*)",
         "Bash(git status:*)", "Bash(git log:*)", "Bash(git ls-files:*)", "Bash(ls:*)", "Bash(grep:*)", "Skill(agent-os-openspec:*)"]
json.dump({"permissions": {"allow": allow}}, open(path, "w"), indent=2)
PY
    # Die Befehlstexte nutzen `_H=...; WF=...; $WF ...` — Shell-Variablen kann die
    # Rechtepruefung nicht vorab pruefen (Freigabe-Dialog trotz Allow-Liste). Daher
    # die Projektregel: Hook-Aufrufe einzeln und mit ausgeschriebenem Pfad.
    cat >"$(dirname "$(dirname "$1")")/CLAUDE.md" <<MD
# E2E-Wegwerfprojekt

Bash-Regel fuer dieses Projekt (Rechtepruefung per Allow-Liste):
- Framework-Skripte immer mit ausgeschriebenem Pfad aufrufen, ohne Shell-Variablen,
  z. B. \`python3 $REPO/core/hooks/workflow.py status\` statt \`\$WF status\`.
- Genau ein Befehl pro Bash-Aufruf: keine \`;\`, \`&&\`, \`|\`, kein \`cd\`.
- Dateien mit Read/Grep/Glob lesen, nicht mit cat/head/find/grep — auch im Framework-Code
  unter $REPO (dafuer ist Lesen freigegeben).
MD
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

INTRO="Automatisierter Ende-zu-Ende-Test des Frameworks agent-os-openspec (als Plugin geladen). Der unten genannte Befehl ist der dokumentierte Framework-Befehl \`workflow.py phase\`: er setzt den aktiven Workflow von phase1_context auf phase2_analyse und gibt eine Zeile 'Set phase to: phase2_analyse' aus. Der Sprung von Phase 1 nach Phase 2 ohne /10-context ist in diesem Test ausdruecklich vom User gewollt und bestaetigt (die Kontext-Datei ist bereits gesetzt); der Hook-Hinweis auf /10-context gilt hier nicht. Er ist fuer dieses Projekt per permissions.allow freigegeben. Wenn du ihn vorher ansehen willst, nimm das Read-Werkzeug (freigegeben), keine anderen Bash-Befehle."

PHASE_CMD="python3 $REPO/core/hooks/workflow.py phase phase2_analyse"

# --- Szenario A --------------------------------------------------------------
scenario_A() {
    send_prompt "$INTRO
Fuehre mit dem Bash-Werkzeug genau diesen Befehl aus, unveraendert, ohne cd und ohne Zusatz:
$PHASE_CMD
Gib danach als gesamte Antwort genau diese eine Zeile aus, ohne Codeblock und ohne weiteren Text:
❗Du: \`$CMD\`" || return
    # Den Vermerk verbraucht der Stop-Hook sofort; Beleg fuer ihn ist der Runner-Start
    wait_log "$WF|phase2_analyse|$CMD: " 120
    ac_log | grep -Fq "$WF|phase2_analyse|$CMD: OK"; check "Log: $WF|phase2_analyse|$CMD: OK" $?
    has_boundary >/dev/null; [ $? -ne 0 ]; check "State ohne auto_clear_boundary (beim Spawn verbraucht)" $?
    wait_pane "E2E-FOLGEBEFEHL-OK #999" 90; check "TUI: E2E-FOLGEBEFEHL-OK #999" $?
    H agent wait e2e --until idle --until done --timeout 30000 >/dev/null 2>&1 || true
    local txt; txt="$(pane_text 400)"
    echo "$txt" | grep -Fq "SessionStart:clear"; check "TUI: SessionStart:clear" $?
    echo "$txt" | grep -Fq "❯ /clear"; check "TUI: ❯ /clear" $?
    echo "$txt" | grep -Fq "❯ $CMD"; check "TUI: ❯ $CMD" $?
    echo "  Belege:"; ac_log | sed 's/^/    log  | /'
    echo "$txt" | grep -E "SessionStart:clear|❯ /clear|❯ /20-analyse|E2E-FOLGEBEFEHL-OK" | sed 's/^/    pane | /'
}

# --- Szenario B --------------------------------------------------------------
scenario_B() {
    send_prompt "$INTRO
Fuehre mit dem Bash-Werkzeug genau diesen Befehl aus, unveraendert, ohne cd und ohne Zusatz:
$PHASE_CMD
Gib danach als gesamte Antwort genau diese zwei Zeilen aus, ohne Codeblock und ohne weiteren Text:
Noch offene Aenderungen, \`/clear\` jetzt NICHT.
❗Du: \`$CMD\`" || return
    wait_log "skip: Negativmarker" 60; check "Log: skip: Negativmarker" $?
    # `skip: Negativmarker` kommt erst nach der Vermerk-Pruefung: der Phasenwechsel lief also
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
❗Du: \`$CMD10\`" || return
    wait_log "skip: keine Grenze vermerkt" 60; check "Log: skip: keine Grenze vermerkt" $?
    has_boundary >/dev/null; [ $? -ne 0 ]; check "State ohne auto_clear_boundary" $?
    [ "$(cur_phase)" = "phase1_context" ]; check "State: weiter phase1_context (kein Phasenwechsel)" $?
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

# --- Szenario E --------------------------------------------------------------
cur_phase() {
    python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("current_phase"))' \
        "$P/.claude/workflows/$WF.json" 2>/dev/null
}

agent_status() {
    H agent get e2e 2>/dev/null | python3 -c 'import json,sys; a=json.load(sys.stdin)["result"]["agent"]; print(a.get("agent_status") or a.get("status"))' 2>/dev/null
}

wait_real() {  # bis Runner-Log-Zeile oder Timeout; Exit 1 bei haengender Freigabe
    local i st
    for i in $(seq 1 "$E_TIMEOUT_S"); do
        ac_log | grep -Fq "$WF|" && return 0
        if [ $((i % 5)) -eq 0 ]; then
            st="$(agent_status)"
            if [ "$st" = "blocked" ] || H agent read e2e --source visible 2>/dev/null \
                    | grep -Eq "Do you want to (proceed|make this edit|create)"; then
                echo "  FAIL Claude haengt an einer Freigabe/Rueckfrage nach ${i}s (Allow-Liste ergaenzen):"
                H agent read e2e --source visible 2>&1 | sed 's/^/    pane | /'
                CASE_FAIL=1; return 1
            fi
        fi
        [ $((i % 60)) -eq 0 ] && log "E: ${i}s, Phase $(cur_phase), Agent $(agent_status)"
        sleep 1
    done
    echo "  FAIL keine Runner-Log-Zeile nach ${E_TIMEOUT_S}s"; CASE_FAIL=1; return 1
}

scenario_E() {
    local real="/agent-os-openspec:10-context #999 Feature aus README.md: greet() soll den Namen optional machen."
    log "E: sende $real (Modell $MODEL)"
    H agent prompt e2e "$real" >/dev/null 2>&1 || { echo "  FAIL agent prompt"; CASE_FAIL=1; return; }
    wait_real || return
    [ "$(cur_phase)" = "phase2_analyse" ]; check "State: current_phase=phase2_analyse ($(cur_phase))" $?
    ac_log | grep -Fq "$WF|phase2_analyse|$CMD: OK"; check "Log: $WF|phase2_analyse|$CMD: OK" $?
    check_plugin_followup E
    usage_report
}

check_plugin_followup() {  # $1 Szenario; Herdr tippte die Plugin-Form, der Befehl startet
    wait_pane "❯ $PCMD" 120; check "TUI: ❯ $PCMD" $?
    # Aktivitaet des echten 20-analyse: nach der letzten Eingabe-Zeile mindestens eine
    # Antwort-/Werkzeug-Zeile (● bzw. ⏺) des neuen Kontexts
    local i ok=1 txt
    for i in $(seq 1 180); do
        txt="$(pane_text 400)"
        echo "$txt" | awk -v c="❯ $PCMD" 'index($0,c){f=1;next} f&&/●|⏺/{found=1} END{exit found?0:1}' \
            && { ok=0; break; }
        sleep 1
    done
    check "TUI: echter 20-analyse antwortet nach ❯ $PCMD" $ok
    txt="$(pane_text 400)"
    echo "$txt" | grep -Fq "❯ /clear"; check "TUI: ❯ /clear" $?
    ! echo "$txt" | grep -Fqi "Unknown command"; check "TUI: kein \"Unknown command\"" $?
    ! echo "$txt" | grep -Fq "❯ $CMD"; check "TUI: Kurzform $CMD nicht getippt" $?
    echo "  Belege $1:"; ac_log | sed 's/^/    log  | /'
    echo "$txt" | grep -nE "SessionStart:clear|❯ /clear|❯ /20-analyse|❯ /agent-os-openspec|❗Du|Set phase to|Unknown command" \
        | sed 's/^/    pane | /'
    echo "$txt" | awk -v c="❯ $PCMD" 'index($0,c){f=1} f' | head -25 | sed 's/^/    nach | /'
}

# --- Szenario F --------------------------------------------------------------
scenario_F() {
    send_prompt "$INTRO
Fuehre mit dem Bash-Werkzeug genau diesen Befehl aus, unveraendert, ohne cd und ohne Zusatz:
$PHASE_CMD
Gib danach als gesamte Antwort genau diese eine Zeile aus, ohne Codeblock und ohne weiteren Text:
❗Du: \`$CMD\`" || return
    wait_log "$WF|phase2_analyse|$CMD: " 120
    ac_log | grep -Fq "$WF|phase2_analyse|$CMD: OK"; check "Log: $WF|phase2_analyse|$CMD: OK" $?
    [ ! -e "$T/.claude/commands/20-analyse.md" ] && [ ! -e "$P/.claude/commands/20-analyse.md" ]
    check "kein Alias/Testdouble 20-analyse im Projekt" $?
    check_plugin_followup F
}

usage_report() {  # Token-Summe je Modell aus den Transkripten der isolierten Konfiguration
    python3 - "$CFG/projects" <<'PY'
import glob, json, os, sys
tot = {}
for f in glob.glob(os.path.join(sys.argv[1], "**", "*.jsonl"), recursive=True):
    seen = set()
    for line in open(f, errors="replace"):
        try:
            m = json.loads(line).get("message") or {}
        except Exception:
            continue
        u, mid = m.get("usage"), m.get("id")
        if not isinstance(u, dict) or mid in seen:
            continue
        seen.add(mid)
        t = tot.setdefault(m.get("model", "?"), [0, 0, 0, 0])
        for i, k in enumerate(("input_tokens", "output_tokens",
                               "cache_creation_input_tokens", "cache_read_input_tokens")):
            t[i] += int(u.get(k) or 0)
for model, (i, o, cw, cr) in tot.items():
    print(f"  Tokens {model}: input={i} output={o} cache_write={cw} cache_read={cr}")
PY
}

run_case() {
    local name="$1"; CASE_FAIL=0; W=""; SERVER_PID=""
    local t0=$SECONDS mode=stub
    MODEL="$MODEL_AD"
    if [ "$name" = "E" ]; then mode=real; MODEL="$MODEL_E"; fi
    if [ "$name" = "F" ]; then mode=plugin; fi
    log "=== Szenario $name ==="
    trap 'teardown_case; cleanup_global' EXIT
    if setup_case "$mode"; then
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
