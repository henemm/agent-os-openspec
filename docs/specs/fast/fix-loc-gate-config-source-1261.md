# Fast Track: LoC-Gate nennt die Quelle seiner Grenzen (3.26.1)

## Problem

`edit_gate._check_loc_delta` misst das Delta mit `_measurement_root()` im **Worktree** (Issue #96),
lädt `scope_guard` aber über `config_loader.find_project_root()`, das einen Worktree bewusst auf das
**Hauptrepo** auflöst. Neue `loc_exclude_patterns` im Worktree greifen deshalb erst nach dem Merge.

Gemeldet aus einer Worktree-Sitzung (#153): Das Gate blockte mit `Produktiv 1015/250`, obwohl 890
der Zeilen abgeholte Messdaten waren und die passenden Patterns in der `openspec.yaml` des
Worktrees bereits standen. Die Meldung nannte die Quelle nicht — der wirkungslose Eintrag sah aus
wie ein Tippfehler in der eigenen Config. Die Umgehung in jener Sitzung (Messdaten auf HEAD
zurücksetzen, editieren, wiederherstellen) war Handarbeit am Messobjekt.

## Scope

- `core/hooks/config_loader.py`: ungecachtes `_find_config_file(root)`; `load_config()` nutzt es
  statt der eigenen Suchschleife (Verhalten unverändert). Neu: `config_source_note()`
- `core/hooks/edit_gate.py`: die Sperrmeldung von `_check_loc_delta` hängt diese Notiz an
- Nicht enthalten: die Config wird **nicht** worktree-first gelesen — siehe ADR
- Nicht enthalten: andere Aufrufer von `load_config()` (`secrets_guard`, `claude_md_protection`,
  `bash_gate`). Die Notiz erscheint nur dort, wo der Fall gemeldet wurde; sonst wird sie Rauschen

## Definition of Done

Blockt das LoC-Gate, nennt die Meldung die Datei, aus der die Grenzen stammen. Weicht die Config
des Arbeitsbaums davon ab, sagt die Meldung ausdrücklich, dass diese Fassung nicht wirksam ist und
warum. Sind beide gleich, erscheint kein Hinweis.

## Acceptance Criteria

- **AC-1:** Given das Gate blockt, When die Meldung entsteht, Then nennt sie den Pfad der
  tatsächlich benutzten Config-Datei.
- **AC-2:** Given die `openspec.yaml` des Worktrees weicht von der wirksamen ab, When das Gate
  blockt, Then nennt die Meldung beide Pfade und sagt, dass die Worktree-Fassung nicht wirksam ist.
- **AC-3:** Given die Worktree-Config ist inhaltlich gleich, When das Gate blockt, Then erscheint
  **kein** Abweichungs-Hinweis.
- **AC-4:** Given die Sitzung läuft im Hauptrepo, When das Gate blockt, Then nennt die Meldung
  dessen Config und keinen Abweichungs-Hinweis.
- **AC-5:** Given der Worktree hat gar keine Config-Datei, When das Gate blockt, Then blockt es
  sauber ohne Traceback.
- **AC-6:** Given eine im Worktree hochgesetzte `max_loc_delta`, When das Gate läuft, Then bleibt
  die Grenze des Hauptrepos wirksam und das Gate blockt weiterhin.

## Test Plan

- `tests/test_loc_gate_config_source_153.py`: 6 Tests (AC-1 bis AC-6), echtes `git worktree add`,
  `edit_gate.py` als Subprozess mit `cwd=worktree`.
- Warum Subprozess: `config_loader.load_config()` und `find_project_root()` sind `lru_cache`-behaftet.
  Ein In-Process-Test läse die Wurzel, die ein früher gelaufener Test zwischengespeichert hat.
- RED vor dem Fix: 3 von 6 rot (die drei Meldungs-Erwartungen). Grün blieben die Gegenproben —
  darunter AC-6, der die Sicherheitseigenschaft prüft, die schon heute gilt und nicht brechen darf.

## ADR

**Entscheidung:** Die Config wird **weiterhin aus dem Hauptrepo** gelesen. Behoben wird die
Diagnose, nicht die Fundstelle.

**Verworfene Alternative — Config worktree-first lesen** (die naheliegende Lesart von #153):
`edit_gate` erlaubt in phase6 das Editieren von `openspec.yaml`. Läse das Gate seine Grenzen aus
dem Worktree, könnte eine Sitzung `max_loc_delta` im eigenen Branch hochsetzen und weiterarbeiten —
ohne Merge, ohne Review. Das ist genau das Muster, das die Sperrmeldung des Gates selbst verbietet:
den Prüfpunkt manipulieren statt die Bedingung zu erfüllen. Der Komfortgewinn wiegt den Verlust der
Selbstzertifizierungs-Sperre nicht auf.

**Verworfene Alternative — Trennung „Messparameter worktree-first, Grenzen am Hauptrepo":**
klingt sauber, hält aber nicht. Auch `loc_exclude_patterns` schwächt das Gate: was ausgeschlossen
wird, zählt nicht. Die Linie zwischen „Messung" und „Autorität" lässt sich hier nicht ziehen.

**Sanktionierter Ausweg bleibt:** `override` (vom Menschen getippt) oder
`workflow.py set-field loc_limit_override <N>`. Beides ist sichtbar und bewusst.

**Folge für #153:** Das Issue bleibt in seiner ersten Lesart („Gate liest Config aus dem
Worktree") ausdrücklich unerfüllt. Die zweite, vom Melder gleichwertig genannte Erwartung
(„die Meldung nennt die Quelle") wird erfüllt.
