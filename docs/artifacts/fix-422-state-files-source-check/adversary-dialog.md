# Adversary Dialog — fix-422-state-files-source-check
Spec: docs/specs/fix-422-state-files-source-check.md
Datum: 2026-10-11

## Checkliste
- [x] **Input:** Jeder Lese- oder Schreibzugriff auf Override-Token, Freigabevermerk, Stop-Lock, Pending-Lock, Footer-State, Session-Locks und `active_workflow` durch die genannten Hooks.
- [x] **Output:** Normale eigene Datei: Verhalten wie heute. Verweis hart oder weich (Datei, ein Ordner der Kette oder `.claude`): Der Zugriff verhält sich gemäß Tabelle in Implementation Details Punkt 2, mit Meldung bzw. Log, die Pfad und Grund nennen. Kein Gate gewährt dadurch eine Freigabe, keine Sperre wird dadurch aufgehoben, und kein Schreiber verändert ein Verweisziel.
- [x] **Side effects:** Keine neuen Subprozesse, keine neuen Abhängigkeiten, keine geänderten Config-Keys, kein neues State-Format, keine geänderten Dateipfade. Beim Fund wird nichts zurückgeschrieben und nichts kopiert.
- [x] **AC-1:** Given jede der vier Richtungen für eine Zustandsdatei / When `read_state_text` bzw. der Leserkern sie liest / Then wirft er `UnsafeStateError` mit Pfad und Grund; `read_state_json` aus #416 verhält sich unverändert
- [x] **AC-2:** Given eine normale eigene Datei, eine fehlende Datei, kaputter Inhalt und eine Wurzel hinter einem Symlink-Elternordner / When der Kern bzw. jeder umgestellte Leser sie liest / Then liefern sie den Inhalt, `FileNotFoundError` bzw. das heutige Verhalten wie vor der Änderung, ohne `UnsafeStateError` und ohne Fehlalarm
- [x] **AC-3:** Given `user_override_token.json` mit gültigem Token als Verweis (alle vier Richtungen) / When `override_token.has_valid_token`, `edit_gate` und `bash_gate` (als Subprozess), die Worktree-Prüfung und der Import-Fallback in `phase_listener` den Token auswerten / Then liefert `has_valid_token` `False`, und kein Gate gewährt dadurch eine Freigabe (Code-Edit bleibt blockiert, Exit 2); der Fund wird im Leser abgefangen und nie propagiert
- [x] **AC-4:** Given `user_approved_validation_<wf>` (Freigabevermerk) als Verweis mit zum Pending-Lock passendem Inhalt (alle vier Richtungen) / When `post_implementation_gate` läuft / Then gilt der Vermerk als nicht vorhanden: der Lock wird nicht gelöscht, der Edit nicht erlaubt (Exit 2)
- [x] **AC-5:** Given `stop_lock.json` als Verweis, auch hängend und auch mit `enabled: false` im Ziel (alle vier Richtungen) / When `edit_gate` und `bash_gate` als Subprozess laufen / Then sind sie gesperrt (Exit 2), die Meldung nennt den Verweis und dass Entfernen ihn löst; beide nutzen dieselbe Funktion `hook_utils.is_stop_locked`, und die Kopien in den Gates sind entfernt
- [x] **AC-6:** Given `pending_validation_<wf>.json` als Verweis, auch mit `created` in der Zukunft (alle vier Richtungen) / When `post_implementation_gate` und `phase_listener` laufen / Then blockt `post_implementation_gate` ausdrücklich per `block()` (Exit 2, nie Exit 1 durch unbehandelte Ausnahme), das Batch-Fenster bleibt nicht offen, und `phase_listener` schreibt keinen Freigabevermerk
- [x] **AC-7:** Given `footer_gate_state.json` als Verweis mit Inhalt, der das Gate abschalten würde (`last_turn_id` des aktuellen Turns bzw. frisches `last_block_at`) (alle vier Richtungen) / When `footer_gate` als Subprozess läuft / Then wird der Verweis wie ein leerer State behandelt (das Gate prüft die Fußzeile), ein Log nennt den Fund, und der Hook endet nie mit einer Ausnahme nach außen (fail-open)
- [x] **AC-8:** Given Session-Locks (`session-locks/*.json`), von denen ein Eintrag ein Verweis ist (alle vier Richtungen) / When `session_singleton_guard._read_entries` und `workflow.py sessions` lesen / Then wird der Eintrag übersprungen (taucht nicht in der Anzeige auf), die übrigen Einträge werden normal gelesen, und es entsteht keine Ausnahme nach außen
- [x] **AC-9:** Given der eigene Session-Lock oder `active_workflow` ist ein Verweis auf eine fremde Datei (alle vier Richtungen) / When `session_singleton_guard` Heartbeat, Register oder Claim schreibt / Then bleibt die fremde Zieldatei byte-gleich, nichts wird durchgeschrieben, und der Hook endet unverändert fail-open ohne neue Ausnahme
- [x] **AC-10:** Given `active_workflow` als Verweis (alle vier Richtungen), und `settings.local.json` mit anderem Namen / When `resolve_active_workflow` den Namen bestimmt / Then gilt der Marker als nicht vorhanden, der Fallback `settings.local.json` greift, ein Log nennt den Fund, und der Name aus dem Verweis wird nie übernommen
- [x] **AC-11:** Given Override-Token, Stop-Lock, Pending-Lock, Freigabevermerk und Footer-State als Verweis auf eine fremde Datei (alle vier Richtungen) / When `override_token._save_tokens`, `phase_listener._set_stop_lock`, der Schreiber des Freigabevermerks, der Token-Fallback, `post_implementation_gate._write_lock` und `footer_gate._remember` schreiben / Then ändert sich das Verweisziel nie (byte-gleich); am Ziel entsteht eine neue normale Datei bzw. bei Fund in der Ordnerkette wird gar nicht geschrieben, mit Warnung
- [x] **AC-12:** Given `.claude` oder ein Ordner der Kette (z. B. `session-locks`) ist ein Symlink / When ein atomarer Schreiber mit `root` schreibt / Then wird kein tempfile am Verweisziel angelegt, nichts geschrieben und `UnsafeStateError` gemeldet; die Ordnerkette wird also wie beim Lesen geprüft, nicht nur das letzte Glied
- [x] **AC-13:** Given Schreiber ohne `root` (Fremdaufrufer von `atomic_write_json`) / When sie aufgerufen werden / Then behalten sie das bisherige Verhalten (tempfile im Elternordner, `os.replace`, kein Walk)
- [x] **AC-14:** Given Verweise auf die Zustandsdateien und die Unlink-Pfade `post_implementation_gate._clear_lock`, `session_singleton_guard._reap_dead` und `override_token.remove_all_tokens` / When sie laufen / Then wird nur der Verweis entfernt und das Verweisziel bleibt unverändert; je Pfad ein Test
- [x] **AC-15:** Given jeder Fund-Pfad in `footer_gate` und `session_singleton_guard` / When die Hooks als Subprozess laufen / Then endet keiner mit einer unbehandelten Ausnahme (kein Exit 1, kein Traceback nach außen); fail-open bleibt wie vor der Änderung
- [x] **AC-16:** Given normale eigene Zustandsdateien in allen sieben Fällen / When die Hooks lesen und schreiben / Then bleibt das Verhalten unverändert (Token gewährt Freigabe, Stop-Lock sperrt bei `enabled: true`, Pending-Lock und passender Vermerk lösen die Sperre, Footer-State schaltet das Gate ab, Session-Locks erscheinen in der Anzeige, `active_workflow` wählt den Namen), und die geschriebene Datei ist wieder eine normale Datei mit `st_nlink == 1`
- [x] **AC-17:** Given der bestehende Testbestand / When die Vollsuite einschließlich `tests/test_state_reader_source_416.py` und `tests/test_bash_gate*` läuft / Then bleibt sie grün
- [x] **AC-18:** Given `CHANGELOG.md` und `CLAUDE.md` / When sie gelesen werden / Then nennt der `[Unreleased]`-Eintrag die Known Limitations aus #416 (Link anlegen, schreiben, löschen; direktes Schreiben ohne Link) und `settings.local.json` als ungeprüft, `CLAUDE.md` nennt die neuen `hook_utils`-Funktionen, und es gibt keinen Versions-Bump

## Dialog

### Runde 1
**Adversary:** Vollsuite gestartet (`pytest -q --tb=short`, Ausgabe in docs/artifacts/fix-422-state-files-source-check/adversary-test-output.txt): 2552 bestanden, 0 fehlgeschlagen, 23 übersprungen. Die Testdatei tests/test_state_files_source_422.py läuft allein mit 75 bestanden und deckt alle in den ACs genannten Testnamen ab. Danach habe ich den gesamten Diff gegen ce348be gelesen und jeden AC gegen den Codepfad geprüft.
**Implementierer:** (Diff und Tests liegen vor; kein Gesprächsverlauf.)

Belege je Punkt:

Input (alle sieben Dateien): Grep über core/hooks und scripts findet keinen verbliebenen Rohleser für Token, Stop-Lock, Footer-State, Freigabevermerk, Pending-Lock und Session-Locks außerhalb der umgestellten Funktionen. Bewusst ungeprüft und dokumentiert: `settings.local.json`, `migrate_state.py`, Harness-Register unter ~/.claude/sessions.
Code reference: core/hooks/hook_utils.py:1500
Status: CONFIRMED

Output (Tabelle Punkt 2): Token gibt nichts frei, Freigabevermerk gilt als nicht vorhanden, Stop-Lock gilt als gesperrt, Pending-Lock blockt, Footer-State gilt als leer, Session-Lock-Eintrag wird übersprungen, `active_workflow` fällt auf `settings.local.json` zurück. Die Meldung nennt Pfad, Grund und "Entfernen des Verweises löst".
Code reference: core/hooks/hook_utils.py:1610
Status: CONFIRMED

Side effects: keine neuen Subprozesse, Abhängigkeiten, Config-Keys, Formate oder Pfade im Diff. Kein Versions-Bump (plugin.json und setup.py nicht im Diff). Beim Fund wird nichts zurückgeschrieben oder kopiert.
Code reference: core/hooks/hook_utils.py:1557
Status: CONFIRMED

AC-1: `_read_state_bytes` wirft `UnsafeStateError` mit Pfad und Grund (Linkzahl, Verweis in der Pfadkette). `read_state_json` parst nur die Bytes des Kerns und ist sonst unverändert. Test test_kern_wirft_unsafe_state_error_je_richtung grün.
Code reference: core/hooks/hook_utils.py:1507
Status: CONFIRMED

AC-2: Normalfall, fehlende Datei, kaputtes JSON und Wurzel hinter Symlink-Elternordner (Probelauf p7.py, Fall A9) verhalten sich wie vorher. `read_state_text` ist ein dünner Wrapper.
Code reference: core/hooks/hook_utils.py:1533
Status: CONFIRMED

AC-3: `_load_tokens` fängt `UnsafeStateError` selbst ab und liefert `{}`. `has_valid_token` ist damit `False`, der Fund wird nie propagiert. Der Import-Fallback in phase_listener liest über `read_state_json` und fängt den Fund.
Code reference: core/hooks/override_token.py:33
Status: CONFIRMED

AC-4: Der Vermerk wird mit `_read_marker` gelesen; Verweis ergibt `_ABSENT`, der Lock bleibt, der Edit wird nicht über den Vermerk erlaubt.
Code reference: core/hooks/post_implementation_gate.py:71
Status: CONFIRMED

AC-5: `edit_gate` und `bash_gate` rufen beide `hook_utils.is_stop_locked` und `stop_lock_state` auf. Die Kopien `_is_stop_locked` sind in beiden Dateien entfernt (Grep). Probelauf p7.py: Verweis auf `.claude` mit Lock, Verweis mit `enabled: false` im Ziel, hängender Datei-Link, Verzeichnis und FIFO ergeben alle "gesperrt".
Code reference: core/hooks/edit_gate.py:639
Status: CONFIRMED
Code reference: core/hooks/bash_gate.py:1135
Status: CONFIRMED

AC-6: `_read_lock` fängt `UnsafeStateError` und ruft `block(...)`. Das ist Exit 2, nie Exit 1. `phase_listener` fängt den Fund in demselben try und schreibt keinen Vermerk.
Code reference: core/hooks/post_implementation_gate.py:55
Status: CONFIRMED
Code reference: core/hooks/phase_listener.py:621
Status: CONFIRMED

AC-7: `_read_state` gibt bei Fund `{}` zurück und loggt auf stderr. `_remember` schreibt atomar mit `root` und schluckt jede Ausnahme (fail-open). Die Hauptfunktion bleibt von der alten Ausnahmebehandlung umschlossen.
Code reference: core/hooks/footer_gate.py:87
Status: CONFIRMED

AC-8: `_read_entries` überspringt Einträge, deren `_read_lock` `None` liefert, und `workflow._read_session_entries` liest über den Kern in einem try.
Code reference: core/hooks/session_singleton_guard.py:182
Status: CONFIRMED
Code reference: core/hooks/workflow.py:2117
Status: CONFIRMED

AC-9: Heartbeat, Register, Re-Register und Claim schreiben über `_write_lock` (atomar mit `root`) und fangen jede Ausnahme. Ein Verweis wird ersetzt, das Ziel nie verändert.
Code reference: core/hooks/session_singleton_guard.py:87
Status: CONFIRMED

AC-10: `_read_active_file` liefert bei Fund `""` mit Log, der Fallback `settings.local.json` greift in beiden Zweigen (Worktree und Hauptrepo).
Code reference: core/hooks/hook_utils.py:1661
Status: CONFIRMED

AC-11: Alle Schreiber (`_save_tokens`, `_set_stop_lock`, Vermerk, Token-Fallback, `_write_lock`, `_remember`) laufen über `atomic_write_*` mit `root`. Der Fund in der Kette wird gefangen, es wird nicht geschrieben und gewarnt.
Code reference: core/hooks/override_token.py:64
Status: CONFIRMED
Code reference: core/hooks/phase_listener.py:434
Status: CONFIRMED
Code reference: core/hooks/post_implementation_gate.py:108
Status: CONFIRMED

AC-12: Probelauf p3.py, Fall G: Ein Symlink `session-locks` in der Kette führt zu `UnsafeStateError`, das Zielverzeichnis bleibt leer. Der Schreiber legt das tempfile nur über den geprüften Ordner-Deskriptor an.
Code reference: core/hooks/hook_utils.py:1471
Status: CONFIRMED

AC-13: Ohne `root` läuft `_atomic_write_legacy` mit tempfile im Elternordner und `os.replace`, ohne Walk.
Code reference: core/hooks/hook_utils.py:1540
Status: CONFIRMED

AC-14: Die drei Unlink-Pfade sind unverändert, `unlink` entfernt nur den Verweis. Je ein Test ist vorhanden und grün.
Code reference: core/hooks/override_token.py:128
Status: CONFIRMED
Code reference: core/hooks/post_implementation_gate.py:132
Status: CONFIRMED

AC-15: Kein Fund-Pfad in footer_gate oder session_singleton_guard lässt eine Ausnahme nach außen. Test test_footer_gate_und_session_guard_werfen_nie_nach_aussen grün.
Code reference: core/hooks/session_singleton_guard.py:616
Status: CONFIRMED

AC-16: Der Normalfall bleibt unverändert, die geschriebene Datei ist eine neue normale Datei mit `st_nlink == 1`. Test test_normale_dateien_verhalten_unveraendert grün.
Code reference: core/hooks/hook_utils.py:1589
Status: CONFIRMED

AC-17: Vollsuite 2552 bestanden, 0 fehlgeschlagen, 23 übersprungen, darunter test_state_reader_source_416 und test_bash_gate*.
Code reference: core/hooks/hook_utils.py:1521
Status: CONFIRMED

AC-18: Der [Unreleased]-Eintrag nennt "Link anlegen, schreiben, Link löschen", "direktes Schreiben ohne Link" und `settings.local.json` samt `migrate_state.py` als ungeprüft. CLAUDE.md nennt `read_state_text`, `atomic_write_text`, `is_stop_locked`. Kein Versions-Bump im Diff.
Code reference: CHANGELOG.md:12
Status: CONFIRMED

Early-Agreement-Skepsis: Alle Punkte sind in Runde 1 grün. Deshalb wurde in Runde 2 gezielt nach Brüchen gesucht, nicht nur wiederholt bestätigt.

### Runde 2
**Adversary:** Eigene Angriffe, Probeskripte p2.py, p3.py, p7.py im Scratchpad (Sandboxen nur dort, nie im Worktree-`.claude/`).
**Implementierer:** (kein Gesprächsverlauf vorhanden.)

a) Stop-Lock-Ausnahme "`.claude` hängt ins Leere und die Datei fehlt gilt als frei". Probelauf p7.py: Hängender Ordner-Link ergibt frei (wie vorher). Ein Ordner-Link auf ein Verzeichnis mit Lock, auch mit `enabled: false`, ergibt gesperrt. Ein hängender Datei-Link ergibt gesperrt mit Meldung. Verzeichnis oder FIFO als Lock-Datei ergibt gesperrt. JSON-Liste ergibt frei, vorher ein Absturz mit Exit 1. Ungültiges UTF-8 ergibt frei wie bisher. Eine bestehende echte Sperre lässt sich damit nicht aufheben: Dafür müsste ein Angreifer `.claude` ersetzen oder die Datei löschen, was auch vor #422 möglich war. `lexists` folgt dem Ordner-Link nur dann ins Leere, wenn der Verweis wirklich hängt. Kein neuer Weg, die Sperre zu verlieren. Grenze: `os.path.lexists` meldet bei einem Rechtefehler in der Kette ebenfalls False, nur mit Verrenkung ausnutzbar und schlechter als der Status quo ist es nicht.
Code reference: core/hooks/hook_utils.py:1625
Status: CONFIRMED

b) TOCTOU: Der Kern öffnet mit `dir_fd` und `O_NOFOLLOW`, prüft `fstat` und liest über denselben Deskriptor. Ein nach dem Öffnen ersetzter Verweis wirkt nicht mehr. In `_read_marker` ist das vorgeschaltete `lexists` nur eine Abkürzung, die Entscheidung trifft der Kern. Die Aufrufer re-lesen den Wert nicht.
Code reference: core/hooks/post_implementation_gate.py:71
Status: CONFIRMED

c) Atomarer Schreiber: Ziel ist ein Verzeichnis: `IsADirectoryError`, tempfile aufgeräumt (Rest-Liste leer, p3.py B). Ein Text, der nicht UTF-8-kodierbar ist: `UnicodeEncodeError` vor dem tempfile, nichts bleibt liegen. Fehlende Zwischenordner werden angelegt, Symlink-Ordner nie. `os.replace` mit `dir_fd` läuft auf macOS. Vier parallele Schreiber hinterlassen keine Reste. Dateimodus wird 0600, vorher bei `write_text` der Modus der Altdatei; belanglos.
Code reference: core/hooks/hook_utils.py:1557
Status: CONFIRMED

d) Breite `except Exception` (bash_gate, hook_utils-Aufrufer, session_singleton_guard, workflow): `UnsafeStateError` wird in `_load_tokens`, `stop_lock_state`, `_read_active_file`, `_read_lock` und den Footer-Funktionen innen gefangen, bevor ein breites `except` ins Spiel kommt. Es gibt keinen Weg, auf dem er zu "frei" oder "Freigabe" kippt. Die breiten except-Zweige bedeuten dort ohnehin nur "kein Token" oder "übersprungen".
Code reference: core/hooks/override_token.py:33
Status: CONFIRMED

e) Exit 1 durch unbehandelte Ausnahme in edit_gate, bash_gate, post_implementation_gate: `stop_lock_state` fängt `UnsafeStateError`, `OSError` und `ValueError`. `_read_lock` blockt explizit. `_read_marker` fängt Fund, Dateifehler und Dekodierfehler. Neue Ausnahmewege sind nicht erkennbar. Reine `OSError` beim Schreiben (schreibgeschützter Ordner) wirken wie vor der Änderung.
Code reference: core/hooks/post_implementation_gate.py:108
Status: CONFIRMED
Code reference: core/hooks/edit_gate.py:639
Status: CONFIRMED
Code reference: core/hooks/bash_gate.py:1135
Status: CONFIRMED

f) Claim bei schreibgeschützter Einzeldatei (Testanpassung in tests/test_session_singleton_guard.py): Der atomare Schreiber ersetzt per `os.replace`, ein Schreibfehler entsteht jetzt am Ordner statt an der Datei. Der angepasste Test setzt den Ordner auf 0500 und prüft weiter, dass ein Schreibfehler nicht still bleibt. Das Dateibit allein verhindert den Claim nicht mehr. Das ist die logische Folge von "nie durch den Verweis schreiben" und vertretbar. Kein Test prüfte ein Sicherheitsmerkmal des Dateibits.
Code reference: core/hooks/session_singleton_guard.py:774
Status: CONFIRMED

Nebenbefunde:

Finding:
  ID: F001
  Severity: MEDIUM
  Category: edge_case
  Code reference: core/hooks/hook_utils.py:1507
  Description: Der Leserkern meldet `st_nlink != 1` als harten Verweis. Öffnet ein Leser eine Datei und ersetzt ein Schreiber sie danach per `os.replace` (oder löscht `_clear_lock` sie), ist der geöffnete Inode ohne Namen, `nlink` ist 0, und der Leser wirft `UnsafeStateError` ("harter Verweis, Linkzahl 0") bei einer ganz normalen Datei.
  Spec requirement: AC-2 / AC-16 — normale eigene Datei: Verhalten wie heute, ohne Fehlalarm
  Conflict: Probelauf p3.py Fall E: vier Schreiber in Dauerschleife, 92 von 500 Lesezugriffen lieferten diesen Fehlalarm. Die Folge ist immer fail-closed (keine Freigabe, Stop-Lock, Pending-Lock-Block, Session-Eintrag kurz übersprungen), nie eine falsche Freigabe. Der Race stammt aus #416, trifft durch #422 aber mehr Dateien (Heartbeat jeder Session, parallele Edits mit Lock-Löschung). Reale Eintrittswahrscheinlichkeit gering (Mikrosekundenfenster).
  Remediation: Nur `st_nlink > 1` als Verweis werten, oder bei `st_nlink == 0` einmal neu öffnen. Als Folgeticket, nicht blockierend.

Finding:
  ID: F002
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/hook_utils.py:1557
  Description: Der tempfile-Name ist Zielname plus 22 Zeichen. Zielnamen ab etwa 233 Zeichen scheitern mit ENAMETOOLONG (Probelauf p3.py Fall F).
  Spec requirement: AC-13 — altes Verhalten nur ohne `root`; mit `root` neu
  Conflict: Der Altpfad (mkstemp) kannte die Grenze nicht. In der Praxis sind Workflow- und Session-Namen deutlich kürzer.
  Remediation: Kurzen festen tempfile-Namen verwenden (zum Beispiel `.tmp.<hex>`).

Finding:
  ID: F003
  Severity: LOW
  Category: anti_pattern
  Code reference: core/hooks/override_token.py:64
  Description: Findet `_save_tokens` einen Verweis in der Ordnerkette, meldet es das nur auf stderr; der Nutzer, der "override" tippt, sieht in der UserPromptSubmit-Antwort nichts.
  Spec requirement: AC-11 — bei Fund in der Kette nicht schreiben, mit Warnung
  Conflict: Die Warnung ist vorhanden, aber schwach sichtbar. Sicherheitsrichtung stimmt.
  Remediation: Über `_notify` in phase_listener an den Nutzer geben.

Weitere Dateien der Änderungsmenge:
Code reference: core/hooks/footer_gate.py:120
Status: CONFIRMED
Code reference: core/hooks/phase_listener.py:377
Status: CONFIRMED
Code reference: core/hooks/session_singleton_guard.py:555
Status: CONFIRMED
Code reference: core/hooks/workflow.py:2117
Status: CONFIRMED

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`).

## Verdict

Tests: 2552 passed, 0 failed, 23 übersprungen
Edge cases: Angriffe a) bis f) geprüft, keine Freigabe und keine aufgehobene Sperre; F001 (MEDIUM, fail-closed Fehlalarm bei gleichzeitigem Ersetzen) als Folgeticket empfohlen
Regressions: keine
Checklist: 21/21 Punkte belegt

## Verdict: VERIFIED
VERDICT: VERIFIED

## Geprüfte Dateien

- sha256:597a2e74e44d325bd8897e636e037b77b2ead11c36d97a3c1ef304c29ece2e18  CHANGELOG.md
- sha256:9e2eb27372ae37ef9725db77dad8e78e39d3da89240efa5bc35995b9d35d9936  core/hooks/bash_gate.py
- sha256:48712677c167ab78d1f4dc0062114e7efec0e57443db4517540043c3b2d0b850  core/hooks/edit_gate.py
- sha256:6d98c88e18d0b33b1047300363baa2f2a9ca10a6614e0d78d878a034e1730c79  core/hooks/footer_gate.py
- sha256:01def667a149b73776fe43c8eacb610454304ed45ad6f0200739acd8886cd494  core/hooks/hook_utils.py
- sha256:758d17ecad0bd7f47fcca681bbb5c1fd82e47bef4e10d6a629049aacbff195fe  core/hooks/override_token.py
- sha256:91d3d83d99f64bd4ca5808c8d56789875ed3a290152b6aef25d84a7818ab87e3  core/hooks/phase_listener.py
- sha256:f54a94d292f93fcafe73879032267df7d0ddf7d3d8cca0bf1a155e973a0c652e  core/hooks/post_implementation_gate.py
- sha256:e012c6adc46e53e56ff93cf87bff9ae860a618f329f7017ed435ccd8a251470f  core/hooks/session_singleton_guard.py
- sha256:79d7f1715f6800fd5a30b46c21c27786d9f7d9697296ce6086a1c84bbb5933f6  core/hooks/workflow.py

## Prüfbasis

- base: ce348bea4c40b6ce6358ccef388608cd8d739260
- blob:d580b60c4f4789587a638de39c46f5266e020740  CHANGELOG.md
- blob:fa58525943fab54f53e2254ac26dd4c960dadc8f  core/hooks/bash_gate.py
- blob:1558e5d57cec04a2cb2f3da166770e109c088799  core/hooks/edit_gate.py
- blob:831a702c7aff8ff85502600493be09bfb81a9755  core/hooks/footer_gate.py
- blob:97c7280fc6720af38d1645c7f41304be3d0d9efc  core/hooks/hook_utils.py
- blob:d07dd0d295c0ec18e695cfbe3be8e5b5dc3ba120  core/hooks/override_token.py
- blob:20501944fe0e3db76b055c68124881867ee6229a  core/hooks/phase_listener.py
- blob:1744ce2d6834e49b394a946f44a33e02a1d0d125  core/hooks/post_implementation_gate.py
- blob:77cd3928e7ebd58c76ded2a3121ee2241f001264  core/hooks/session_singleton_guard.py
- blob:e8f8310a3d3243d860f92a51b99e06b7305fcda0  core/hooks/workflow.py
