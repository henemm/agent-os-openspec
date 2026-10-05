#!/usr/bin/env python3
"""Differenztest: hook_utils.strip_heredoc_bodies gegen bash als Orakel (#357).

Uebernommen aus der unabhaengigen Pruefrunde zu PR #362; tests/test_heredoc_bash_oracle_357.py
fuehrt eine kleine, feste Stichprobe aus. Manuell: python3 tests/heredoc_bash_oracle.py 1000 <seed>

Differential test: hook_utils.strip_heredoc_bodies vs. bash (oracle).

Every line gets a probe `: >exec_<n>` (as its own command or appended as
`; : >exec_<n>`). After running the snippet with bash in a temp dir, the set
of exec_<n> files = probes bash EXECUTED. Each executed probe's source line
must still be a line of strip_heredoc_bodies(snippet).
"""
import json, os, random, subprocess, sys, tempfile, shutil

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core", "hooks"))
from hook_utils import strip_heredoc_bodies  # noqa: E402

OUT = tempfile.gettempdir()  # Laufordner; main() setzt einen eigenen


class Gen:
    def __init__(self, rng):
        self.rng = rng
        self.lines = []      # (text, probe_id or None, role)
        self.n = 0
        self.tags = set()

    def pid(self):
        self.n += 1
        return self.n

    def probe_line(self, role="cmd"):
        p = self.pid()
        self.lines.append((f": >exec_{p}", p, role))

    def add(self, text, probe=True, role="code"):
        if probe:
            p = self.pid()
            self.lines.append((f"{text}; : >exec_{p}", p, role))
        else:
            self.lines.append((text, None, role))

    def body(self, marker, k, paren_p=0.10):
        r = self.rng
        for _ in range(k):
            c = r.random()
            if c < paren_p:
                # #365: unmaskierte `)` vor ungerader `"`-Zahl — bash 3.2 beendet
                # daran ein umschliessendes "$( ... )" vor dem Heredoc-Ende.
                self.lines.append((r.choice(['y)"', 'a) b"', '1) x"']), None, "body"))
                self.probe_line("body")  # die Folgezeile, die bash 3.2 dann ausfuehrt
                continue
            c = (c - paren_p) / (1 - paren_p)  # bestehende Zweige behalten ihre Anteile
            if c < 0.55:
                self.probe_line("body")
            elif c < 0.95:
                p = self.pid()
                extra = r.choice([
                    "", " <<X", " <<'Y'", " # c", " )", " (", " '", ' "', " $HOME",
                    " `true`", " $(true)", " ;", " && true", " <<<w", " \\",
                    f" {marker}", " }", " fi", " esac", " ;;",
                ])
                # keep the probe executable if the line ever runs as code:
                # put the probe FIRST, then a harmless comment-ish tail
                tail = extra
                if extra in (" '", ' "', " )", " (", " }", " fi", " esac", " ;;", " \\"):
                    tail = " #" + extra
                self.lines.append((f": >exec_{p}{tail}", p, "body"))
            else:
                self.lines.append((r.choice([marker + " ", " " + marker, "\t" + marker,
                                             marker + "x", "x" + marker, "EOF", "E"]),
                                   None, "body"))

    def terminator(self, marker, dash):
        r = self.rng
        v = r.random()
        if v < 0.80:
            self.lines.append((marker, None, "term"))
        elif v < 0.88:
            self.lines.append((("\t" if dash else "") + marker, None, "term"))
        elif v < 0.93:
            self.lines.append((marker + " ", None, "fake-term"))  # not a terminator
            self.probe_line("body?")
            self.lines.append((marker, None, "term"))
        elif v < 0.97:
            self.lines.append(("\t" + marker, None, "maybe-term"))
            self.probe_line("after")
            if not dash:
                self.lines.append((marker, None, "term"))
        else:
            self.tags.add("missing-term")  # EOF terminates


CONSUMERS = [
    ("", "none"), (" | cat", "data"), (" | tr a b", "data"), (" >/dev/null", "data"),
    (" | bash", "interp"), (" | b\\ash", "interp"), (' | "bash"', "interp"),
    (" | $SHELL", "interp"), (' | "$SHELL"', "interp"), (" | env bash", "interp"),
    (" | command bash", "interp"), (" | /bin/sh", "interp"), (" > >(bash)", "interp"),
    (" | $I", "interp"), (" | awk '{system($0)}'", "interp"), (" | sed e", "interp"),
    (" | $BASH", "interp"), (" | xargs -I{} sh -c {}", "interp"),
]


def opener_forms(m, m2):
    # (prefix_lines, opener_line, closer_lines, markers[(m,dash)], is_real_heredoc)
    return [
        ([], f"cat <<'{m}'", [], [(m, False)], True),
        ([], f"cat <<{m}", [], [(m, False)], True),
        ([], f'cat <<"{m}"', [], [(m, False)], True),
        ([], f"cat <<\\{m}", [], [(m, False)], True),
        ([], f"cat <<-{m}", [], [(m, True)], True),
        ([], f"cat <<- '{m}'", [], [(m, True)], True),
        ([], f'cat > f.txt <<"{m}"', [], [(m, False)], True),
        ([], f"true | cat <<{m}", [], [(m, False)], True),
        ([], f"cat <<'{m}' <<{m2}", [], [(m, False), (m2, False)], True),
        ([], f"cat <<{m}; cat <<'{m2}'", [], [(m, False), (m2, False)], True),
        ([], f"echo \"$(cat <<'{m}'", [')"'], [(m, False)], True),
        ([], f"git() {{ :; }}; git commit -m \"$(cat <<'{m}'", [')"'], [(m, False)], True),
        ([], f"x=$(cat <<'{m}'", [")"], [(m, False)], True),
        ([], f"true && cat <<{m}", [], [(m, False)], True),
        ([], f"true; cat <<{m}", [], [(m, False)], True),
        ([], f"{{ cat <<{m}", ["}"], [(m, False)], True),
        ([], f"( cat <<{m}", [")"], [(m, False)], True),
        ([], f"f() {{ cat <<{m}", ["}; f"], [(m, False)], True),
        ([], f"case x in x) cat <<{m}", [";; esac"], [(m, False)], True),
        ([], f"if true; then cat <<{m}", ["fi"], [(m, False)], True),
        (["# a comment <<Z"], f"cat <<{m}", [], [(m, False)], True),
        ([], f"cat <(echo) <<{m}", [], [(m, False)], True),
        ([], f"cat <<{m} |", ["cat"], [(m, False)], True),
        ([], f"cat <<{m} |", ["bash"], [(m, False)], True),
        ([], f"cat <<{m} &&", ["true"], [(m, False)], True),
        ([], f"I=bash; cat <<{m}", [], [(m, False)], True),
        # non-heredoc lookalikes
        ([], f"echo 'a <<{m}'", [], [], False),
        ([], f"echo \"a <<{m}\"", [], [], False),
        ([], f"cat <<<{m}", [], [], False),
        ([], f"echo x # <<{m}", [], [], False),
        ([], f"(true)#<<{m}", [], [], False),
        ([], f"echo \\ #<<{m}", [], [(m, False)], True),   # real heredoc in bash!
        ([], f"echo a\\#<<{m}", [], [(m, False)], True),
        ([], f"echo $#<<{m}", [], [(m, False)], True),
        ([], f"echo x;#<<{m}", [], [], False),
        ([], f"echo x&#<<{m}", [], [], False),
        ([], f"echo x|#<<{m}", [], [], False),
        ([], f"echo x>#<<{m}", [], [], False),
        ([], f"echo x}}#<<{m}", [], [(m, False)], True),
        ([], f"echo \"$(true)\"#<<{m}", [], [(m, False)], True),
        ([], f"echo '#'<<{m}", [], [(m, False)], True),
    ]


def make_snippet(rng):
    g = Gen(rng)
    same = rng.random() < 0.4
    for _ in range(rng.randint(1, 3)):
        if rng.random() < 0.5:
            g.probe_line("top")
        m = "E" if same else rng.choice(["E", "EOF", "END", "M1", "_x"])
        m2 = "F" if same else rng.choice(["F", "EOF2", "E"])
        if m2 == m:
            m2 = m + "2"
        forms = opener_forms(m, m2)
        pre, op, closers, markers, real = rng.choice(forms)
        cons, ckind = rng.choice(CONSUMERS)
        g.tags.add("consumer:" + ckind)
        for p in pre:
            g.add(p, probe=False, role="comment")
        line = op
        if not op.endswith("|") and not op.endswith("&&") and "$(" not in op[-12:] \
                and not op.endswith("x=$(cat <<'" + m + "'"):
            if cons and "<<" in op and real:
                line = op + cons
        # probe on opener line (where valid)
        if op.endswith("|") or op.endswith("&&") or op.endswith("'" + m + "'") and "$(" in op:
            g.add(line, probe=False, role="opener")
        elif op.startswith("echo x;#") or op.startswith("echo x&#") or op.startswith("echo x|#") \
                or "#" in op and op.startswith("(true)"):
            g.add(line, probe=False, role="opener")
        else:
            g.add(line, probe=True, role="opener")
        for mk, dash in markers:
            g.body(mk, rng.randint(0, 3), 0.5 if '"$(' in op else 0.10)  # #365
            g.terminator(mk, dash)
        for c in closers:
            if c in ("cat", "bash", "true"):
                g.add(c, probe=False, role="closer")
            else:
                g.add(c, probe=rng.random() < 0.6 and c not in (")", ')"'), role="closer")
        if not real:
            for _ in range(rng.randint(0, 2)):
                g.probe_line("after-fake")
            if rng.random() < 0.5:
                g.lines.append((m, None, "fake-term"))
        if rng.random() < 0.6:
            g.probe_line("top")
        if "missing-term" in g.tags:
            break
    return g


def run_bash(snippet):
    d = tempfile.mkdtemp(prefix="dt_", dir=OUT + "/runs")
    try:
        with open(os.path.join(d, "s.sh"), "w") as f:
            f.write(snippet)
        env = {"PATH": "/usr/bin:/bin", "SHELL": "/bin/bash", "HOME": d, "LC_ALL": "C"}
        try:
            subprocess.run(["bash", "s.sh"], cwd=d, env=env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except subprocess.TimeoutExpired:
            return None
        return {int(x[5:]) for x in os.listdir(d) if x.startswith("exec_")}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check(snippet, lines):
    executed = run_bash(snippet)
    out = strip_heredoc_bodies(snippet)
    out_lines = out.split("\n")
    missing = []
    if executed is None:
        return out, None, []
    for text, p, role in lines:
        if p is not None and p in executed and text not in out_lines:
            missing.append((p, text, role))
    return out, executed, missing


def run(n: int, seed: int) -> "tuple[dict, list]":
    """n zufaellige Snippets; liefert (Statistik, Befunde)."""
    global OUT
    OUT = tempfile.mkdtemp(prefix="heredoc_oracle_")
    os.makedirs(OUT + "/runs", exist_ok=True)
    rng = random.Random(seed)
    stats = {"total": 0, "findings": 0, "timeouts": 0}
    findings = []
    try:
        for _ in range(n):
            g = make_snippet(rng)
            snippet = "\n".join(t for t, _, _ in g.lines) + "\n"
            out, executed, missing = check(snippet, g.lines)
            stats["total"] += 1
            if executed is None:
                stats["timeouts"] += 1
            elif missing:
                stats["findings"] += 1
                findings.append({"snippet": snippet, "output": out, "missing": missing})
    finally:
        shutil.rmtree(OUT, ignore_errors=True)
    return stats, findings


def main():
    os.makedirs(OUT + "/runs", exist_ok=True)
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 357
    rng = random.Random(seed)
    stats = {"total": 0, "stripped": 0, "unchanged": 0, "timeouts": 0, "findings": 0,
             "unchanged_pure_data": 0, "with_real_heredoc": 0}
    findings = []
    for _ in range(N):
        g = make_snippet(rng)
        snippet = "\n".join(t for t, _, _ in g.lines) + "\n"
        out, executed, missing = check(snippet, g.lines)
        stats["total"] += 1
        if executed is None:
            stats["timeouts"] += 1
            continue
        changed = out != snippet
        stats["stripped" if changed else "unchanged"] += 1
        body_probes = [p for _, p, r in g.lines if r == "body" and p is not None]
        has_real = any(r == "term" for _, _, r in g.lines)
        if has_real:
            stats["with_real_heredoc"] += 1
            if not changed and body_probes and not any(p in executed for p in body_probes):
                stats["unchanged_pure_data"] += 1
        if missing:
            stats["findings"] += 1
            findings.append({"snippet": snippet, "output": out, "missing": missing,
                             "tags": sorted(g.tags)})
    with open(OUT + f"/findings_{seed}.json", "w") as f:
        json.dump(findings, f, indent=1)
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
