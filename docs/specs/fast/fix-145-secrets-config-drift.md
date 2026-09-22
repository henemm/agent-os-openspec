# Fast Track: config.yaml fuehrte die #75-Haertung nie nach (#145, 3.28.4)

## Problem

`secrets_guard.py` blockierte den Lesezugriff auf `tests/test_phase_listener_keyword_guard.py`
vollstaendig — eine normale pytest-Datei ohne jedes Geheimnis. Meldung: „enthaelt
Credentials/Keys. Diese Datei ist immer geschuetzt.", kein Override moeglich (laut CLAUDE.md
bewusst so, fuer echte Secrets).

Der im Issue vermutete Grund („keyword" matcht Substring „key" in einem im Code verbliebenen
Breitmuster) traf nicht zu: `core/hooks/hook_utils.py::SECRETS_SENSITIVE_PATTERNS` traegt seit
Issue #75 bereits die geharteten, verankerten Formen (`private[_.]key`, `[_.]secret\.`) — keine
davon matcht „keyword" (nachgeprueft: `re.search` gegen den Pfad liefert fuer keines der sieben
Code-Default-Muster einen Treffer).

Der tatsaechliche Fehler liegt in `config.yaml`. `secrets_guard.py::_get_config()`:

    cfg.get("sensitive_patterns", _DEFAULT_SENSITIVE)

nutzt den Code-Default nur als Fallback — wenn die geladene Projekt-Config das Feld setzt,
gewinnt die Config. `config.yaml` setzte `secrets_guard.sensitive_patterns` und `always_blocked`
mit den ALTEN, unverankerten Mustern `_key`/`_secret`, die #75 im Code laengst ersetzt hat. Die
#75-Haertung war dadurch fuer jedes Projekt, das eine generierte `config.yaml` nutzt, wirkungslos.

Radius: `config.yaml` ist nicht nur die Config dieses Repos selbst, sondern auch die Vorlage,
die `setup.py::generate_config_yaml()` in jedes Konsumenten-Projekt kopiert (Copy- und
Plugin-Modus, Aufrufstellen `install_plugin_mode` und `main()`). Jedes neu installierte Projekt
erbte die ungehaerteten Muster.

## Scope

- `config.yaml`: `secrets_guard.sensitive_patterns` und `secrets_guard.always_blocked` auf
  dieselben Muster wie `hook_utils.SECRETS_SENSITIVE_PATTERNS`/`SECRETS_ALWAYS_BLOCKED`
  gebracht; Kommentar ergaenzt, der die Kopplung und den Regressionstest benennt
- Version 3.28.4, `skills/` unveraendert (kein Skill-Inhalt betroffen), CHANGELOG, README
- **Nicht enthalten:** Ein automatischer Abgleich, der `config.yaml` bei jedem Testlauf oder
  Release generiert statt von Hand zu pflegen. Der neue Test schuetzt gegen erneuten Drift;
  ob ein Generator lohnt, haengt davon ab, ob `config.yaml` noch an weiteren Stellen von den
  Code-Defaults abweicht — dafuer fehlt aktuell der Beleg.
- **Nicht enthalten:** `setup.py --update` automatisch auf bestehende Projekte anwenden. Ein
  `--update` ohne `--force` ueberschreibt eine vom Nutzer ggf. angepasste `config.yaml` nicht
  (gewolltes Verhalten); die Verteilung an Bestandsprojekte ist damit ein manueller Schritt und
  im CHANGELOG benannt.

## Definition of Done

`tests/test_phase_listener_keyword_guard.py` und `tests/test_secret_egress_guard.py` sind lesbar.
Eine echte `.env`-Datei und eine `private.key`-Datei bleiben blockiert. `config.yaml`s
Secrets-Muster stimmen mit den Code-Defaults in `hook_utils.py` exakt überein, geprüft durch
einen Test statt durch Konvention.

## Acceptance Criteria

- **AC-1:** Given `config.yaml`s `secrets_guard.sensitive_patterns`, When sie mit `hook_utils.SECRETS_SENSITIVE_PATTERNS` verglichen werden, Then sind sie identisch (Reihenfolge und Inhalt).
- **AC-2:** Given `config.yaml`s `secrets_guard.always_blocked`, When sie mit `hook_utils.SECRETS_ALWAYS_BLOCKED` verglichen werden, Then sind sie identisch.
- **AC-3:** Given `secrets_guard.py` laeuft mit der echten `config.yaml` dieses Repos gegen `tests/test_phase_listener_keyword_guard.py` (Read-Tool), Then ist der Zugriff erlaubt (Exit 0).
- **AC-4:** Given dieselbe Konfiguration gegen `tests/test_secret_egress_guard.py`, Then ist der Zugriff erlaubt — derselbe Fehlertyp wie #75, diesmal ueber die Config statt den Code.
- **AC-5:** Given dieselbe Konfiguration gegen eine echte `.env`-Datei und eine `private.key`-Datei, Then bleiben beide blockiert (Gegenprobe: der Fix darf den Schutz nicht abschwaechen).

## Test Plan

`tests/test_config_yaml_secrets_pattern_drift_145.py`, 7 Tests:

- `TestConfigYamlMatchesCodeDefaults` — direkter Listenvergleich `config.yaml` vs. `hook_utils.py`, plus eine explizite Prüfung, dass `_key`/`_secret` nirgends mehr als eigenständiges Muster vorkommen (AC-1, AC-2)
- `TestRealFilesNoLongerBlocked` — hermetischer Subprozess-Lauf von `secrets_guard.py` mit der echten `config.yaml` dieses Repos in eine `tmp_path`-Projektwurzel kopiert (Stilvorlage: `tests/test_bash_gate_freetext_fixes_64_75.py`), vier Fälle: die beiden vormals blockierten Testdateien lesbar, `.env` und `private.key` weiterhin blockiert (AC-3, AC-4, AC-5)

Nachweis:

- Ausgangsstand (nach #137 auf `main`): 1037 passed, 4 skipped
- RED vor dem Fix: 5 der 7 neuen Tests rot; die 2 grünen (Gegenproben) sichern unverändertes Verhalten ab
- Realer Vorfall direkt reproduziert: `python3 core/hooks/secrets_guard.py` gegen `tests/test_phase_listener_keyword_guard.py` im echten Repo → BLOCKED (exit 2), Meldung wortgleich mit dem Issue
- GREEN: 1044 passed, 4 skipped
- Realer Vorfall nach dem Fix direkt im echten Repo erneut geprüft: exit 0; `.env` weiterhin exit 2

**Gegenprobe (Mutation).** `config.yaml` zurück auf die alten Muster (`_key`/`_secret`) gesetzt —
4 der 7 Tests sofort rot, darunter der reale Vorfall. Arbeitsbaum danach nachweislich sauber
wiederhergestellt.
