# Kontext + Analyse: fix-506-autoclear-ohne-herdr-status (Issue #506)

## Request Summary
Auto-/clear bricht beim PO an Phasengrenzen fast immer ab (24 Abbrueche, 3 Erfolge): `ABBRUCH: wait 1/2: agent wait Exit 1 timed out waiting for agent status`.
PO-Vorgabe: „Du hast es mit dem Plugin ja in der Hand. Also aendere doch das Plugin und versuche nicht, mit dem Plugin irgendwie zurecht zu kommen.“ → keine Konfig-Krücke, keine Abhaengigkeit von Herdrs Statusklassifikation.

## Ursache (belegt in #506)
- `core/hooks/herdr_bridge.py` `_Runner._wait_ready` (~Z. 656): `herdr agent wait <pane> --until idle --until done`.
- Herdr klassifiziert den Zustand per Erkennungs-Manifest; beim PO ergaenzt ein lokales Manifest `~/.config/herdr/agent-detection/claude.toml` Regeln (Prio 960): Antwort endet mit „❗ Du: …“ → `blocked`; „ℹ️ Nichts zu tun …“ → `working`. Genau an der Phasengrenze verlangt das Plugin „❗ Du: /<naechster> #N“ → Herdr nie `idle` → Timeout.
- Allgemein: Herdrs Zustand ist eine Heuristik ueber den Bildschirm; jede lokale/kuenftige Regel kann sie verschieben.

## Loesung: eigene Signale des Plugins statt Herdr-Status
- Der Runner wird vom Stop-Hook (footer_gate → maybe_auto_clear) gestartet — d. h. Claudes Antwort ist zu Ende. Nach Turn-Ende gibt es keine Berechtigungsdialoge mehr (die entstehen nur waehrend eines Turns).
- Signal A „Turn zu Ende, nichts Neues eingegeben“: UserPromptSubmit-Hook (`phase_listener.py`, laeuft bei JEDEM abgeschickten Prompt) vermerkt pro Herdr-Pane den Zeitpunkt der letzten Eingabe. Runner vor `/clear`: nach grace prüfen, dass seit dem Spawn keine neue Eingabe kam (sonst ABBRUCH „Nutzer hat weitergeschrieben“).
- Signal B „/clear ist angekommen“: SessionStart-Hook (`session_banner.py` bzw. `session_singleton_guard.py register`, laeuft bei source=clear) vermerkt pro Pane `{source, at}`. Runner nach `/clear`: warten (Timeout idle_timeout_s) bis ein SessionStart mit source=clear nach dem eigenen /clear vermerkt ist, dann settle, dann Folgebefehl. Ohne Signal → ABBRUCH.
- Herdr wird nur noch zum Tippen genutzt (`agent prompt`), nicht mehr zum Warten (`agent wait` entfaellt). Weitere Pruefungen bleiben: `_recheck` (Phase/Befehl), Once-Lock, /99-reset-Sperre, Pane muss existieren.
- Marker-Ablage: wie die uebrigen Auto-Clear-Zustaende unter `_ac_base()/.claude/` (Worktree), Datei je Pane, atomar, fail-open. Hooks schreiben nur, wenn `HERDR_PANE_ID` gesetzt ist.

## Related Files
- core/hooks/herdr_bridge.py — `_Runner` (`_wait_ready`, `run`), `maybe_auto_clear`, `_ac_base`, `AC_DEFAULTS`
- core/hooks/phase_listener.py — UserPromptSubmit
- core/hooks/session_banner.py — SessionStart (alle sources)
- tests/test_herdr_auto_clear_467.py (Stub erwartet `agent wait` — anpassen), tests/test_herdr_plan_deploy_sessionstart_478.py (`test_runner_reads_real_agent_status_field`), weitere Auto-Clear-Tests
- scripts/e2e_auto_clear.sh — echter E2E

## Abnahme (echt)
- E2E-Szenario G: Test-Herdr bekommt das PO-Manifest nachgebaut (`$XDG_CONFIG_HOME/herdr/agent-detection/claude.toml` mit den Regeln „❗ Du:“→blocked, „ℹ️ Nichts zu tun“→working, Prio 960; Format aus `herdr` Doku/`agent explain` am echten 0.9.5 belegen). Gegenprobe: alter Code (origin/main) scheitert mit Timeout, neuer Code tippt /clear + Folgebefehl.
- A'–D, F weiter gruen; neuer Fall: Nutzer tippt waehrend der grace-Zeit einen neuen Prompt → kein /clear.
