---
change_id: feat-94-loc-limit-risk
status: proposed
created: 2026-08-09
github_issue: 94
---

# LoC-Limit misst Risiko statt Aenderungs-Churn

Closes #94

## Modus

AENDERUNG — bestehendes Gate `core/hooks/edit_gate.py::_check_loc_delta()` wird
in seiner Zaehl- und Bewertungslogik korrigiert. Kein neues System, kein neuer
Hook. Der bestehende Schwellwert (`scope_guard.max_loc_delta`, Default 250)
und die bestehenden Exclude-Patterns bleiben unveraendert.

## Warum

`_check_loc_delta()` zaehlt aktuell `added + deleted` ueber ALLE per
`git diff HEAD --numstat` erfassten Dateien, ohne Unterscheidung zwischen
Produktiv- und Testcode. Das fuehrt zu zwei konkreten Fehlanreizen, belegt an
einer echten Session (henemm/gregor_zwanzig#1633):

1. **Umbenennungen werden doppelt bestraft.** `git diff` stellt eine
   Zeilenaenderung als Loeschen der alten + Hinzufuegen der neuen Zeile dar.
   `added + deleted` zaehlt eine reine Umbenennung an 40 Aufrufstellen daher
   doppelt so hoch wie eine aequivalente Neuanlage. Das Gate bestraft damit
   die sauberere Loesung (konsistente Umbenennung) staerker als die
   schlechtere (alten, inkonsistenten Namen belassen).
2. **Testcode zaehlt 1:1 wie Produktivcode.** Die einzigen Exclude-Patterns
   sind Lokalisierungsdateien (`.xcstrings`, `.strings`, `.po`,
   `Localizable.`). Mechanische Testanpassungen (z.B. 40 gleichfoermige
   `monkeypatch`-Aufrufstellen nach einer Umbenennung) verbrauchen das
   Produktiv-Budget, obwohl sie kein Produktiv-Scope-Risiko darstellen.

Beleg-Session: ein Commit mit 98 Zeilen echter Produktivaenderung + 286
Zeilen mechanischer Testanpassung wurde in Summe als 384 Zeilen gezaehlt und
blockierte gegen das Limit von 250 — obwohl beide Anteile fuer sich genommen
unauffaellig sind.

Da `edit_gate.py` Teil des Core-Frameworks ist, wirkt jede Aenderung hier
projektweit auf alle Konsumenten-Projekte (Verteilung ueber Plugin-Update).
Entsprechend sorgfaeltig ist auf Rueckwaertskompatibilitaet zu bestehenden
Statusfeldern und Override-Mechanismen zu achten (siehe Abschnitt
"Kompatibilitaet" unten).

## Aktueller Zustand

`core/hooks/edit_gate.py::_check_loc_delta()` (Zeilen 241-268):

- Liest `git diff HEAD --numstat` fuer den gesamten Workdir.
- Pro Datei: matched sie ein Exclude-Pattern → ignorieren. Sonst
  `total += added + deleted`.
- Blockiert, wenn `total > max_loc` (`workflow.loc_limit_override` >
  `config.scope_guard.max_loc_delta` > Default 250).
- Schreibt bei Erfolg `loc_delta_current` als `"+<total>"` in die aktive
  Workflow-JSON (fuer `workflow.py status` und den Retro-Log unter
  `scope_loc_delta`).
- Blockade-Meldung zeigt nur die Gesamtzahl (`"LoC delta 384 exceeds limit
  250"`) plus `gate_diagnostics(workflow, delta="+384", limit=250)`.

Nebenfund: `core/hooks/config_loader.py::get_scope_loc_config()` (Zeilen
264-273) kapselt bereits `(max_loc_delta, loc_exclude_patterns)` aus der
Config, wird aber nirgends aufgerufen — `edit_gate.py` dupliziert die
Lookup-Logik stattdessen inline. Toter Code, der durch diese Aenderung
erstmals genutzt wird.

## Delta

1. **Zaehlweise: nur `added` statt `added + deleted`.** Eine 1:1-Umbenennung
   an einer Zeile zaehlt danach 1 statt 2 — der Doppelbestrafungs-Effekt bei
   Refactorings entfaellt. Siehe "Entscheidung: added vs. added-deleted"
   unten fuer die Begruendung gegen die Netto-Wachstum-Alternative.
2. **Zwei getrennte Buckets: Produktiv und Test**, mit eigenen Limits:
   - Produktiv: `scope_guard.max_loc_delta` (unveraendert, Default 250)
   - Test: neues `scope_guard.max_test_loc_delta` (Default 500)
   - Klassifikation ueber neues `scope_guard.test_path_patterns`
     (Default deckt `tests/`, `__tests__/`, `Tests/`, `UITests/`,
     `test_*.py`, `*_test.py`, `*.test.ts`/`.tsx`/`.js`/`.jsx`,
     `*.spec.ts`/`.tsx`/`.js`/`.jsx` ab — abgeleitet aus den Konventionen
     dieses Repos und von henemm/gregor_zwanzig).
   - Reiner Ausschluss von Tests ist explizit NICHT das Ziel (Test-Wildwuchs
     soll sichtbar bleiben) — daher ein eigener, grosszuegigerer Schwellwert
     statt eines Excludes.
3. **Aufgeschluesselte Blockade-Meldung**: `"Produktiv 98/250, Tests
   286/500"` statt einer einzelnen Gesamtzahl. Beide Teilwerte werden immer
   gezeigt, sobald einer der beiden Buckets sein Limit ueberschreitet.
4. **Aktivierung des toten Codes**: `edit_gate.py` ruft ab jetzt
   `config_loader.get_scope_loc_config()` fuer den Produktiv-Teil auf statt
   die Lookup-Logik zu duplizieren; ein neues, analog gebautes
   `get_scope_test_loc_config()` liefert den Test-Teil.

**Explizit NICHT Teil dieses Scopes** (Punkt 4 aus Issue #94): ein
projektweiter Override-Zaehler/-Audit-Trail. Das bleibt ein eigenstaendiges
Anliegen fuer ein separates Issue.

## Entscheidung: `added` statt `added - deleted` (Netto-Wachstum)

Empfehlung: **nur `added` zaehlen**, nicht `added - deleted`.

Begruendung:
- `added` behebt das im Issue beschriebene Problem direkt: eine
  1:1-Umbenennung (1 Zeile geloescht, 1 Zeile neu) zaehlt 1 statt 2 —
  die doppelte Bestrafung entfaellt vollstaendig, ohne dass reine
  Loeschungen "gratis" grossflaechige, unkontrollierte Netto-Aenderungen
  kaschieren koennten.
- `added - deleted` (Netto-Wachstum) ist leicht zu umgehen: 500 Zeilen
  loeschen und 500 Zeilen woanders neu schreiben ergibt netto 0 — ein
  Aenderungsumfang, der real ein hohes Review-/Risiko-Volumen darstellt,
  würde vollstaendig unsichtbar. Umgekehrt kann bei ueberwiegenden
  Loeschungen der Wert negativ werden, was fuer eine "Zeilen bis zum
  Limit"-Anzeige (`98/250`) semantisch unklar ist (negative Zahl gegen ein
  positives Limit?).
- `added` ist monoton nicht-negativ, einfach zu kommunizieren ("wie viel
  neuer/veraenderter Code wurde eingefuehrt, der noch nicht durch den
  TDD-/Review-Zyklus lief") und deckt sich mit gaengiger Praxis anderer
  Code-Review-/Churn-Tools, die Loeschungen bewusst geringer gewichten als
  Neuanlagen.

Bekannter Trade-off (akzeptiert, kein offener Punkt): reine Loeschungen
(added=0) loesen das Gate nicht mehr aus. Das ist beabsichtigt — das Gate
soll unreviewten NEUEN Code begrenzen, nicht Aufraeumarbeiten verhindern.

## Kompatibilitaet — Seiteneffekte-Check

- **`loc_limit_override`** (bestehendes Workflow-Feld): bleibt unveraendert
  und wirkt weiterhin ausschliesslich auf den Produktiv-Bucket. Neu
  symmetrisch ergaenzt: `test_loc_limit_override` fuer den Test-Bucket
  (gleiches Muster: `workflow.py set-field test_loc_limit_override <N>`).
- **`loc_delta_current`** (Statusfeld, gelesen von `workflow.py status` und
  vom Retro-Log unter `scope_loc_delta`): bleibt als Feldname UND Semantik
  erhalten — reprae­sentiert weiterhin den Produktiv-Anteil (jetzt
  `added`-only statt `added+deleted`). Kein Breaking Change fuer bestehende
  Konsumenten von `workflow.py status`. Neu ergaenzt: `loc_delta_test_current`
  fuer den Test-Anteil, analog gespiegelt im Retro-Log als
  `scope_loc_delta_test`.
- **`get_scope_loc_config()`**: Signatur (`tuple[int, list]`) bleibt
  unveraendert — wird jetzt erstmals von `edit_gate.py` aufgerufen statt nur
  von Tests. Bestehende Tests (`tests/test_gate_coverage.py::TestScopeConfig`)
  bleiben ohne Anpassung gueltig. Neu ergaenzt: `get_scope_test_loc_config()`
  mit gleichem Rueckgabetyp fuer den Test-Bucket.
- **Bestehende Config** (z.B. `henemm/gregor_zwanzig/openspec.yaml`
  `scope_guard:` Sektion): definiert nur `max_loc_delta` und
  `loc_exclude_patterns`. `max_test_loc_delta` und `test_path_patterns`
  fehlen dort — beide fallen automatisch auf die neuen Defaults (500 bzw.
  die Standard-Testpfad-Patterns) zurueck. Keine Config-Migration noetig.

## Betroffene Systeme

- `core/hooks/edit_gate.py` — `_check_loc_delta()` (Kernaenderung)
- `core/hooks/config_loader.py` — `get_scope_loc_config()` aktivieren, neues
  `get_scope_test_loc_config()`
- `core/hooks/workflow.py` — Status-/Retro-Ausgabe um Test-Bucket ergaenzen
- `core/commands/80-workflow.md` — Doku fuer `test_loc_limit_override`
- `tests/test_gate_coverage.py` — bestehende `_check_loc_delta`-Tests an
  `added`-only-Semantik anpassen, neue Tests fuer Test-Bucket/Breakdown
- Alle Konsumenten-Projekte via Plugin-Update (keine Aktion noetig dank
  Default-Fallback, siehe Kompatibilitaet)
