# Fast Track: 'halt' als Stop-Wort entfernen (#146, Epic #199, 3.29.1)

## Problem

`STOP_PHRASES` in `core/hooks/phase_listener.py` enthielt `"halt"` ohne `leading_only`-
Einschränkung — Stop-Lock-Phrasen matchen bewusst überall im Text (Not-Aus soll großzügig
greifen). Im Deutschen ist „halt" jedoch ein extrem häufiges Füllwort („das ist halt so",
„ich wollte halt fragen"), das mit jeder solchen normalen Nachricht ungewollt einen echten
Stop-Lock auslöste — genau das Fehlalarm-Muster, das Epic #199 systematisch abstellen soll.

Derselbe Drift wie #145: `config.yaml` (`stop_lock.stop_keywords`) führt eine eigene Kopie der
Liste, die `phase_listener._load_phrases()` gegenüber dem Python-Default bevorzugt. `config.yaml`
listete „halt" ebenfalls explizit — und fehlte dabei zusätzlich „anhalten" komplett (eigener,
unabhängiger Drift-Befund, durch denselben Fix miterledigt).

Herkunft: Nebenfund bei der Analyse zu #141 (2026-09-19), eigene Tech-Lead-Entscheidung auf
Kommentar #146 vom 22.09.2026 („raus aus der Standard-Liste").

## Scope

- `core/hooks/phase_listener.py::STOP_PHRASES` — `"halt"` entfernt, `["stop", "stopp",
  "anhalten"]` bleibt.
- `config.yaml::stop_lock.stop_keywords` — `"halt"` entfernt, `"anhalten"` ergänzt (Drift-Fix,
  bringt die Vorlage mit dem Code-Default in Deckung — dieselbe Datei ist auch die Vorlage, die
  `setup.py::generate_config_yaml()` in jedes Konsumenten-Projekt kopiert).
- **Nicht enthalten:** Kontext-sensitive Erkennung von „halt" als eigenständiges Kommando-Wort
  (im Issue selbst als Alternative skizziert). Verworfen, weil deutsches Füllwort-„halt" fast
  immer bereits an Wortgrenzen steht („das ist halt so") — eine Wortgrenzen-Verschärfung hätte
  das Füllwort nicht von einem echten Stop-Kommando unterschieden.

## Definition of Done

Eine Nachricht, die „halt" nur als Füllwort enthält, löst keinen Stop-Lock mehr aus. „stop"/
„stopp"/„anhalten" lösen ihn weiterhin aus — unverändert großzügig, überall im Text. Config-
Vorlage und Code-Default sind identisch.

## Acceptance Criteria

- **AC-1:** Given eine Nachricht mit „halt" ausschließlich als Füllwort („das ist halt so, kein
  Problem damit"), When `phase_listener.py` sie verarbeitet, Then wird `.claude/stop_lock.json`
  nicht angelegt.
- **AC-2:** Given eine Nachricht mit „stopp" (oder „stop"/„anhalten"), When `phase_listener.py`
  sie verarbeitet, Then wird der Stop-Lock weiterhin aktiviert (`enabled: true`) — unverändert
  gegenüber vorher.
- **AC-3:** Given `core/hooks/phase_listener.py::STOP_PHRASES` und `config.yaml::stop_lock.
  stop_keywords`, When sie verglichen werden, Then sind sie identisch (keine zweite Quelle der
  Wahrheit, die auseinanderlaufen kann).

## Test Plan

`tests/test_stop_word_halt_146.py`, 6 Tests in zwei Klassen:

- `TestNoFillerWordInDefaults` — „halt" fehlt in Code-Default und Config-Vorlage, „stop"/
  „stopp"/„anhalten" bleiben in beiden, beide Listen sind identisch (AC-3)
- `TestIntegrationRealConfigNoLongerTriggersOnFillerWord` — hermetischer Subprozess-Test gegen
  die echte `config.yaml` dieses Repos (Stilvorlage: `test_config_yaml_secrets_pattern_
  drift_145.py`): Füllwort löst keinen Lock aus (AC-1), echtes Stop-Wort weiterhin (AC-2)

Nachweis:

- Ausgangsstand (main nach #181): 1068 passed, 4 skipped
- GREEN: 1074 passed, 4 skipped (6 neue, keine bestehenden verändert)

**Gegenprobe (Mutation).** Zwei unabhängige Rückbauten, beide wurden rot: `config.yaml` zurück
auf „halt" (4 von 6 Tests rot — inkl. des Integrationstests, der Config-Drift ist damit
nachweislich der scharfe Teil des Bugs) · `STOP_PHRASES`-Code-Default zurück auf „halt" (2 von 6
Tests rot — die verbleibenden Config-Tests, weil `config.yaml` zur Laufzeit gegenüber dem
Python-Default gewinnt und den Fehler allein schon abfängt). Beide Mutationen einzeln bestätigen:
beide Stellen sind unabhängig notwendig. Arbeitsbaum danach nachweislich sauber wiederhergestellt
(`diff` gegen vorherigen Stand).
