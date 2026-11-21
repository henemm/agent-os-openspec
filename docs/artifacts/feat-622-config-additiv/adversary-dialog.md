# Adversary Dialog — feat-622-config-additiv
Spec: docs/specs/feat-622-config-additiv.md
Datum: 2026-11-21 14:47

## Checkliste
- [x] **Input:** Write, Edit oder MultiEdit auf die wirksame `config.yaml` im Projekt.
- [x] **Output:** Nur Anzeige-Abschnitte betroffen: erlaubt ohne Token. Sonst: blockiert wie bisher, Ausweg „override“.
- [x] **Side effects:** keine; die Funktion `display_only_change` ist pur. Befehlstexte und Generate tragen den Planungshinweis.
- [x] **AC-1:** Given die wirksame `config.yaml` mit Plugin-Block und ohne Override-Token / When ein Write einen neuen Abschnitt `time_estimate` hinzufügt und alle anderen Schlüssel gleich lässt / Then lässt `edit_gate.py` den Schreibzugriff ohne Token zu
- [x] **AC-2:** Given die wirksame `config.yaml` mit Abschnitten `time_estimate` und `next_suggestion` / When ein Edit den Wert in einem dieser Abschnitte ändert oder ein MultiEdit einen davon entfernt / Then wird der Zugriff ohne Token zugelassen
- [x] **AC-3:** Given die wirksame `config.yaml` / When ein Edit einen bestehenden Gate-Schlüssel ändert (etwa `adversary_coverage_gate.enabled` von true auf false) / Then blockiert `edit_gate.py` weiterhin und nennt „override“ als Ausweg
- [x] **AC-4:** Given die wirksame `config.yaml` / When ein Write einen bestehenden Gate-Abschnitt entfernt oder einen neuen Abschnitt außerhalb der Anzeige-Liste einfügt (etwa `adversary_coverage_gate: {enabled: false}`) / Then wird weiterhin blockiert
- [x] **AC-5:** Given die wirksame `config.yaml` / When die neue Fassung Anzeige-Abschnitte ändert, aber einen Schlüssel doppelt enthält oder als YAML unlesbar ist / Then wird weiterhin blockiert (fail-closed)
- [x] **AC-6:** Given eine App-`config.yaml` ohne Plugin-Block, die nicht die wirksame Config ist, oder keine vorhandene wirksame Config / When ein Write einen Anzeige-Abschnitt dort hinzufügt oder eine vorrangige Config neu anlegt / Then wird weiterhin blockiert
- [x] **AC-7:** Given die wirksame `config.yaml` / When ein Bash-Aufruf einen Anzeige-Abschnitt per Schreibumleitung hinzufügt / Then blockiert `bash_gate.py` unverändert ohne Token
- [x] **AC-8:** Given ein gültiger Override-Token und die wirksame `config.yaml` / When ein Gate-Schlüssel geändert wird / Then wird der Zugriff wie bisher zugelassen
- [x] **AC-9:** Given die Befehlstexte `00-intake` und `30-write-spec` samt den erzeugten `skills/` / When ein autarker Auftrag geplant wird / Then enthalten beide Texte den Hinweis, keine Schritte einzuplanen, die einen Override brauchen, und die Skills stimmen mit den Quellen überein (kein Sync-Drift)

## Dialog

### Runde 1
**Adversary:** Tests (5 Dateien) 75 passed (adversary-test-output.txt). Probeläufe: `probe-unit.py` (32 YAML-Fälle gegen `display_only_change`: doppelte Schlüssel top/nested, `<<` top-level und in Anzeige-Abschnitt, Alias, `!!python`-Tag, 1/true/"true", Groß-/Kleinschreibung, Zero-Width-Zeichen im Schlüssel, BOM, `---`-Mehrdokument, Tab, JSON-Flow, Listenreihenfolge, leere Datei, Rekursionsbombe) und `probe-gate.py`/`probe-gate2.py` (50 Gate-Subprozessläufe: replace_all, MultiEdit hin-und-zurück, Entfernen von Überschriften, Plugin-Block verlieren, vorrangige Config anlegen (openspec.yaml, .claude/openspec.yaml), Schatten-Config (App-config.yaml vor .claude/config.yaml), `..`-Pfad, Symlink, Hardlink, Symlink auf Datei außerhalb, 300-KiB-Write, 21 Edits, fehlender Inhalt, CRLF, U+2028, %YAML-Direktive, Dokumentende+zweites Dokument, Override-Token). Ergebnis: keine Umgehung; jede Gate-Änderung blockt, jede reine Anzeige-Änderung läuft. Bash und ~/.claude/settings* nicht angefasst (unverändert, Tests #418/#481 grün). Mutations-Gegenprobe auf einer Kopie des Arbeitsbaums (Scratchpad; Original unberührt, per diff bestätigt): 21 Mutationen, 10 gefangen, 11 überlebt.
**Implementierer:** (nicht beteiligt, Kontext-Isolation)

### Runde 2
**Adversary:** Nachgefasst an der Stelle, die der Nutzer erreicht (edit_gate-Subprozess statt nur Unit): überlebt haben M3 Alias erlaubt, M4/M5/M8 Typ-Strenge (1/true/0/false, Schlüsseltyp), M10 `must_stay_plugin`, M12 nur erste Variante geprüft, M13 Dateideckel, M14 Edit-Deckel, M15 Inhaltsdeckel, M16 Zeitbudget, M17 Ausnahme→True, M18/M21 (äquivalente Mutanten, kein Befund). Beleg M4 auf der Kopie: `display_only_change("a:\n  enabled: 0\n","a:\n  enabled: false\n")` ist mit Mutation True (Gate würde per 0→false abschaltbar), im echten Code False. Laufzeit: 240-KiB-Flow-Liste im Anzeige-Abschnitt = ca. 2,2 s je Parse, Gate-Lauf 5 s von 10 s Hook-Limit (hooks.json) bei Gate-Änderung; ein Timeout wäre für Claude Code nicht blockierend, Spielraum auf langsamer Hardware klein (kein Beleg für Umgehung).
**Implementierer:** (nicht beteiligt)

## Findings
F001 MEDIUM edit_case: Typ-Strenge (CHANGELOG und Spec-Punkt 2 behaupten sie) hat keinen Test; Mutation `_strict_equal` ohne Typvergleich, `_typed_items` ohne Typ und Anzeige-Schlüssel ohne `type(k) is str` bleiben grün.
Code reference: core/hooks/config_loader.py:151-160
Code reference: core/hooks/config_loader.py:146
Code reference: core/hooks/config_loader.py:183
F002 MEDIUM edge_case: nur die erste Edit-Variante geprüft (`contents[:1]`) bleibt grün; Test mit Variante 2 (leerer new_string, gefressener Zeilenumbruch) fehlt.
Code reference: core/hooks/edit_gate.py:667
F003 MEDIUM edge_case: Datei-, Inhalts-, Edit-Zahl- und Zeitdeckel sowie Ausnahme→erlauben im 0a-Ausnahmepfad ungetestet (die CHANGELOG nennt sie als gesperrt).
Code reference: core/hooks/edit_gate.py:660-676
F004 LOW edge_case: `must_stay_plugin` (Root-config.yaml verliert Plugin-Block) ungetestet; im echten Code wirksam, Mutation überlebt.
Code reference: core/hooks/edit_gate.py:666
Code reference: core/hooks/edit_gate.py:673
F005 LOW edge_case: Alias-Verbot ungetestet (Wirkung gering, Rekursionsfehler fängt ohnehin).
Code reference: core/hooks/config_loader.py:129-132
F006 LOW anti_pattern: `display_only_change(old, ...)` parst die alte Fassung je Variante neu; bei 240-KiB-Anzeige-Abschnitt 5 s von 10 s Hook-Limit.
Code reference: core/hooks/edit_gate.py:671

## Bestätigungen
Code reference: core/hooks/config_loader.py:163
Code reference: core/hooks/edit_gate.py:643
Code reference: core/hooks/edit_gate.py:698

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict
VERDICT: VERIFIED
(keine Umgehung gefunden; Findings F001-F006 sind Testlücken, keine Codefehler)

## Geprüfte Dateien

- sha256:12b36f8038277caaf84d41ea53b448d99ed46e8cc34f6b2e5ef681bc688f49e2  core/hooks/config_loader.py
- sha256:bf5b43a08caeb5b8e269f099718b5df80098a577868de90e7398a74db1526109  core/hooks/edit_gate.py

## Prüfbasis

- base: ea7999172166debcba77455a49e1913c7d80b421
- blob:c882111d4aa2b215b1ad7ff20700bd63168f2d48  core/hooks/config_loader.py
- blob:5c2ce5ebcb7f94bc7d33ae692f823edfacb0b156  core/hooks/edit_gate.py
