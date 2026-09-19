# Mini-Spec: fix-137-dotenv-pattern-swiftui-environment

PR: #137 · Workflow: `fix-dotenv-pattern-swiftui-environment` · Track: Fast

## Problem (live reproduziert am 2026-09-16 in henemm/loose-ends)

`SECRETS_SENSITIVE_PATTERNS` in `core/hooks/hook_utils.py` fuehrt das
unverankerte Muster `\.env`. Es trifft jedes Token, das mit `.env` beginnt,
also auch die SwiftUI-Modifier `.environment(...)` und
`.environmentObject(...)`, die in praktisch jeder SwiftUI-Datei stehen.
Beide Guards (`secrets_guard.py` fuer Read/Edit/Write, der Secrets-Check in
`bash_gate.py` fuer Bash) nutzen dieselbe Liste. Live geblockt wurden u.a.:

1. `grep -n ".environment(" LooseEnds/App/LooseEndsApp.swift`
2. `sed -n '10,40p' LooseEnds/App/ContentView.swift` (enthaelt den Modifier)
3. Read-Tool auf eine Swift-Datei mit `Environment` im Namen

Der Hinweis „touch .claude/staging" im Block-Text verleitet dazu, den Schutz
gleich ganz abzuschalten — das Gegenteil dessen, was der Guard erreichen soll.

## Was aendert sich

**Betroffen: 1 Code-Datei** — `core/hooks/hook_utils.py`, eine Zeile in
`SECRETS_SENSITIVE_PATTERNS`.

- Muster ist jetzt `\.env(rc)?\b`: Wortgrenze nach `env`. `.env`, `.env.local`,
  `.env.production`, `.envrc` und `config/.env` bleiben geschuetzt;
  `.environment` hat zwischen `v` und `i` keine Wortgrenze und faellt heraus.
- Beide Guards profitieren automatisch, weil sie die Liste aus `hook_utils`
  importieren — kein Guard-Drift.
- README-Vorlage fuer `secrets_guard.sensitive_patterns` zeigt das neue Muster.
- `CHANGELOG.md`-Eintrag unter `[Unreleased]`, keine Versionsnummer vergeben.

## Was darf sich nicht aendern (Sicherheits-Invarianten, je als Gegenprobe)

- `cat .env`, `cat .env.local`, `cat .env.production`, `cat .envrc`,
  `cat config/.env` → weiterhin BLOCK (Bash-Guard).
- Read-Tool auf `.env` → weiterhin BLOCK (secrets_guard).
- Alle uebrigen Eintraege in `SECRETS_SENSITIVE_PATTERNS` unveraendert.
- Staging-Modus-Verhalten unveraendert.

## Test Plan

`tests/test_swiftui_environment_not_dotenv.py`, hermetisch fuer beide Guards
(12 Tests, vor dem Fix rot, danach gruen):

- [x] `grep` auf `.environmentObject(` in einer Swift-Datei → kein Block.
- [x] `sed -n` auf eine Swift-Datei mit `.environment(` → kein Block.
- [x] `cat` einer Swift-Datei mit `Environment` im Dateinamen → kein Block.
- [x] Read-Tool auf dieselbe Datei → kein Block.
- [x] Alle fuenf .env-Varianten oben per `cat` → Block bleibt.
- [x] Read-Tool auf `.env` → Block bleibt.

## Manuelle Test-Schritte

1. In einem SwiftUI-Projekt mit installierten Hooks
   `grep -rn ".environment(" Sources/` ausfuehren → laeuft durch.
2. `cat .env` im selben Projekt → wird weiterhin geblockt.
