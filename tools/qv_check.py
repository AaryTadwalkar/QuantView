#!/usr/bin/env python3
"""qv_check.py - preservation + consistency checker for the 4 QuantView spec files.
  python qv_check.py snapshot DOCS_DIR OUT.json
  python qv_check.py compare  BEFORE.json AFTER.json ALLOW.txt   (exit 1 if non-allowed removals)
  python qv_check.py lint     DOCS_DIR [STALE.txt]                (exit 1 on any failure)
  python qv_check.py report   [DOCS_DIR]                          (one paste-friendly status block; also writes ops/qv_report.txt)
ALLOW.txt: one substring per line; a removed line/token/id is tolerated only if it contains one.
STALE.txt: one regex per line; any match anywhere in the docs fails lint (old names after a rename).
"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

for _s in (sys.stdout, sys.stderr):          # Windows consoles/redirects default to cp1252; docs contain ₹ → ≤
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass

def read_list(path):
    """UTF-8 (BOM tolerated) list file, one entry per line, CRLF-safe, blank lines ignored."""
    p = Path(path)
    return [x.strip() for x in p.read_text(encoding="utf-8-sig").splitlines() if x.strip()] if p.exists() else []

FILES = {"MASTER": "QUANTVIEW_MASTER_SPEC.md", "DATA": "QUANTVIEW_DATA_SPEC.md",
         "ENGINE": "QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md", "AGENTS": "AGENTS.md"}
LONG = {"ENGINE_UI_RESEARCH": "ENGINE", "DATA": "DATA", "MASTER": "MASTER"}
TOKEN = re.compile(r"`([^`\n]{1,80})`")
IDRE = re.compile(r"\b(ADR-\d+|M\d+-\d+b?|V-\d+|G0a|G[0-6][ab]?)\b")
HEAD = re.compile(r"^(#{1,6})\s+(.*)$")
NUMHEAD = re.compile(r"^#{1,6}\s+(\d+(?:\.\d+)*)\.?\s")

def load(d):
    d = Path(d); out = {}
    for k, f in FILES.items():
        p = d / f
        if not p.exists(): sys.exit(f"MISSING FILE: {p}")
        out[k] = p.read_text(encoding="utf-8").split("\n")
    return out

def table_rows(lines):
    """list of (heading, row_count) per markdown table"""
    res, head, cur = [], "", 0
    for ln in lines + [""]:
        m = HEAD.match(ln)
        if m: head = m.group(2)
        if ln.startswith("|"): cur += 1
        else:
            if cur: res.append((head, cur)); cur = 0
    return res

def snapshot(d, out):
    snap = {}
    for k, lines in load(d).items():
        text = "\n".join(lines)
        snap[k] = {"lines_n": len(lines), "sha": hashlib.sha256(text.encode()).hexdigest(),
                   "headings": [l for l in lines if HEAD.match(l)],
                   "tokens": dict(Counter(TOKEN.findall(text))),
                   "ids": dict(Counter(IDRE.findall(text))),
                   "tables": table_rows(lines), "fences": text.count("```"),
                   "lines": [l.rstrip() for l in lines if l.strip()]}
    Path(out).write_text(json.dumps(snap)); print("snapshot written:", out)

def allowed(s, allow): return any(a and a in s for a in allow)

def compare(b, a, allow_file):
    B, A = json.loads(Path(b).read_text()), json.loads(Path(a).read_text())
    allow = read_list(allow_file)
    bad = 0
    for k in B:
        print(f"\n=== {k}: lines {B[k]['lines_n']} -> {A[k]['lines_n']}")
        hb, ha = Counter(B[k]["headings"]), Counter(A[k]["headings"])
        for h in (hb - ha):
            if not allowed(h, allow): print("  HEADING REMOVED/CHANGED:", h[:100]); bad += 1
        for key in ("ids", "tokens"):
            for t, n in B[k][key].items():
                if A[k][key].get(t, 0) < n and not allowed(t, allow):
                    print(f"  {key[:-1].upper()} LOST: {t}  ({n} -> {A[k][key].get(t,0)})"); bad += 1
        tb, ta = B[k]["tables"], A[k]["tables"]
        if len(ta) < len(tb): print("  TABLE COUNT DROPPED", len(tb), "->", len(ta)); bad += 1
        else:
            for (h1, n1), (h2, n2) in zip(tb, ta):
                if n2 < n1 and not allowed(h1, allow): print(f"  TABLE ROWS DROPPED under '{h1[:60]}': {n1} -> {n2}"); bad += 1
        if A[k]["fences"] < B[k]["fences"]: print("  CODE FENCES DROPPED"); bad += 1
        rem = Counter(B[k]["lines"]) - Counter(A[k]["lines"]); add = Counter(A[k]["lines"]) - Counter(B[k]["lines"])
        unexplained = [l for l in rem if not allowed(l, allow)]
        print(f"  lines removed/changed: {sum(rem.values())}  added: {sum(add.values())}  UNEXPLAINED removed: {len(unexplained)}")
        for l in unexplained[:40]: print("    -", l[:140])
        bad += len(unexplained)
    print("\nRESULT:", "FAIL" if bad else "PASS", f"({bad} unexplained)"); sys.exit(1 if bad else 0)

def sections(lines):
    return {m.group(1) for l in lines if (m := NUMHEAD.match(l))}

def lint_checks(d, stale_file=None):
    docs = load(d); fail = []; text = {k: "\n".join(v) for k, v in docs.items()}
    secs = {k: sections(v) for k, v in docs.items()}
    adrs = set(re.findall(r"^## (ADR-\d+)", text["MASTER"], re.M))
    # 1. cross references must resolve
    pats = [(re.compile(r"\b(ENGINE|DATA|MASTER|AGENTS)(?:\.md)?\s*§§?\s*(\d+(?:\.\d+)*)"), None),
            (re.compile(r"QUANTVIEW_(ENGINE_UI_RESEARCH|DATA|MASTER)_SPEC\.md\s*§§?\s*(\d+(?:\.\d+)*)"), LONG)]
    for k, t in text.items():
        for pat, mp in pats:
            for m in pat.finditer(t):
                tgt = mp[m.group(1)] if mp else m.group(1)
                if m.group(2) not in secs[tgt]: fail.append(f"{k}: reference to {tgt} §{m.group(2)} - no such numbered heading")
        for a in set(re.findall(r"\bADR-\d+\b", t)):
            if a not in adrs: fail.append(f"{k}: {a} is not defined as a '## ADR-xxx' heading in MASTER")
    # 2. task registry
    A = text["AGENTS"]; parts = re.split(r"\n#### ", A)
    tasks = {}
    for p in parts[1:]:
        m = re.match(r"(M\d+-\d+b?) ", p)
        if not m: continue
        size = re.search(r"\*\*Size:\*\* [SML][^\n]*?\(([\d.]+) person-day", p); dep = re.search(r"\*\*Depends on:\*\* ([^\n]*)", p)
        tasks[m.group(1)] = (float(size.group(1)) if size else None, dep.group(1) if dep else "", "RETIRED" in p.split("\n")[0].upper())
    gates = {}
    sec5 = A[A.index("## 5. Gates"):A.index("**Gate dependency rule")]
    for r in sec5.split("\n"):
        if re.match(r"\| G\w+ — ", r):
            c = [x.strip() for x in r.strip("|").split("|")]
            gates[c[0].split(" ")[0]] = re.findall(r"M\d+-\d+b?", c[2])
    allowed_dep = set(tasks) | set(gates)
    for t, (_, dep, _) in tasks.items():
        if re.search(r"M\d+-\d+b?|\bG\w+", dep) is None and dep.strip() not in ("—", "-", "", "None"): fail.append(f"task {t}: unparseable depends_on '{dep}'")
        for x in re.findall(r"M\d+-\d+b?|\bG0a\b|\bG[0-6][ab]?\b", dep):
            if x not in allowed_dep: fail.append(f"task {t}: depends on unknown {x}")
    dep = {t: [x for x in re.findall(r"M\d+-\d+b?", v[1]) if x in tasks] for t, v in tasks.items()}; state = {}
    def dfs(n, path):
        state[n] = 1
        for m in dep[n]:
            if state.get(m) == 1: fail.append("dependency cycle: " + " -> ".join(path + [n, m]))
            elif m not in state: dfs(m, path + [n])
        state[n] = 2
    for n in dep:
        if n not in state: dfs(n, [])
    inn = Counter(x for v in gates.values() for x in v)
    for t, v in tasks.items():
        if not v[2] and inn[t] != 1: fail.append(f"task {t}: appears in {inn[t]} gates (must be exactly 1; retired tasks exempt)")
    for x in inn:
        if x not in tasks: fail.append(f"gate lists unknown task {x}")
    total, active = len(tasks), sum(1 for v in tasks.values() if not v[2]); days = sum(v[0] or 0 for v in tasks.values())
    for n in re.findall(r"\b(\d+)[- ]tasks?\b", A):
        if int(n) not in (total, active): fail.append(f"AGENTS states {n} tasks; registry has {total} ({active} active)")
    for n in re.findall(r"(\d+) active", A):
        if int(n) != active: fail.append(f"AGENTS states {n} active; registry has {active}")
    for n in re.findall(r"(\d+(?:\.\d+)?) person-days", A):
        if abs(float(n) - days) > 1e-9 and float(n) not in (0.0, 0.5, 1.0, 2.0, 2.5, 3.0, 5.0): fail.append(f"AGENTS states {n} person-days total; registry sums to {days}")
    # 3. RunConfig field uniqueness and example keys
    E = docs["ENGINE"]; i0 = next(i for i, l in enumerate(E) if l.startswith("### 19.1")); i1 = next(i for i, l in enumerate(E) if l.startswith("### 19.2"))
    rows = [l for l in E[i0:i1] if re.match(r"\| `[a-z_]+`", l)]; names = [re.match(r"\| `([a-z_]+)`", l).group(1) for l in rows]
    for n, c in Counter(names).items():
        if c > 1: fail.append(f"RunConfig field '{n}' defined {c} times")
    rc = next((l for l in rows if l.startswith("| `risk_controls`")), "")
    ctl = set(re.findall(r"`([a-z_]+)`", rc.split("Controls:")[-1])) if "Controls:" in rc else set()
    for n in ctl & set(names): fail.append(f"name collision: '{n}' is both a top-level RunConfig field and a risk_controls control")
    ex = "\n".join(E[i1:i1 + 80]); js = re.search(r"```json\n(.*?)```", ex, re.S)
    if js:
        for k in json.loads(js.group(1)):
            if k not in names: fail.append(f"RunConfig example key '{k}' is not in the field table")
    # 4. stale names
    if stale_file:
        for pat in read_list(stale_file):
            for k, t in text.items():
                for m in re.finditer(pat, t): fail.append(f"{k}: stale name /{pat}/ at char {m.start()}")
    return f"tasks={total} active={active} days={days} gates={','.join(gates)}", fail

def lint(d, stale_file=None):
    info, fail = lint_checks(d, stale_file)
    print(info)
    for f in fail: print("FAIL:", f)
    print("LINT:", "FAIL" if fail else "PASS", f"({len(fail)})"); sys.exit(1 if fail else 0)

DEFAULT_STALE = ["final_eval=true", "MASTER §5 owner decisions", "single-use per strategy version",
                 r"UNIQUE\(strategy_id, strategy_version\)"]

def fix_status(docs):
    T = {k: "\n".join(v) for k, v in docs.items()}; E, D, A, M = T["ENGINE"], T["DATA"], T["AGENTS"], T["MASTER"]
    row = lambda txt, key: next((l for l in txt.split("\n") if l.startswith(f"| `{key}`")), "")
    rc = row(E, "risk_controls"); sm = row(E, "slippage_multiplier"); fe = row(D, "final_evaluation_uses"); sr = row(D, "strategies_registry")
    v = lambda key: next((l for l in A.split("\n") if l.startswith(f"| `{key}`")), "")
    res = [
     ("FIX-1 intrabar_stop_policy enum", "DONE" if "TARGET_FIRST_SENSITIVITY" in E else "NEEDED"),
     ("FIX-2 risk_controls min_dte rename", "DONE" if "risk_min_dte_entry" in rc else ("NEEDED" if "min_dte" in rc else "CHECK")),
     ("FIX-3 final_eval -> final_evaluation", f"NEEDED ({sum(t.count('final_eval=true') for t in T.values())} hits)" if any("final_eval=true" in t for t in T.values()) else "DONE"),
     ("FIX-4 slippage_multiplier Decimal string", "DONE" if "Decimal string" in sm and '"slippage_multiplier": "1"' in E else "NEEDED"),
     ("FIX-5 UtcEpochSec defined in DATA", "DONE" if re.search(r"^- `UtcEpochSec`", D, re.M) else "NEEDED"),
     ("FIX-6a V-05 cites ADR-007", "NEEDED" if "per ADR-007" in A else "DONE"),
     ("FIX-6b V-18 cites DATA 11.4", "NEEDED" if "§11.4" in v("V-18") else "DONE"),
     ("FIX-6c V-19 cites DATA 11.5", "NEEDED" if "§11.5" in v("V-19") else "DONE"),
     ("FIX-6d V-20 cites ADR-004", "NEEDED" if "ADR-004" in v("V-20") else "DONE"),
     ("FIX-7 'MASTER §5 owner decisions'", "NEEDED" if "MASTER §5 owner decisions" in E else "DONE"),
     ("FIX-8 hold-out per lineage (optional D3)", "DONE" if "lineage_id" in fe and "lineage_id" in sr else ("NEEDED" if "UNIQUE(strategy_id" in fe or "per strategy version" in (E + A + D) else "CHECK")),
    ]
    return res

def run(cmd, timeout=10):
    import subprocess
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return (r.stdout + r.stderr).strip()[:400] or "(no output)"
    except Exception as e:
        return f"(could not run: {type(e).__name__})"

def report(d, out="ops/qv_report.txt"):
    import os
    import platform
    import shutil
    L = []; add = L.append; d = Path(d)
    add("== QV REPORT =="); add(f"python={platform.python_version()} os={platform.platform()}")
    add("\n-- files in %s (bytes, lines, sha12) --" % d)
    for p in sorted(d.iterdir()):
        if p.is_file():
            b = p.read_bytes(); nl = b.count(b"\n") + 1; h = hashlib.sha256(b).hexdigest()[:12]
            note = "  <-- not one of the 4 spec files" if p.name not in FILES.values() else ""
            add(f"{p.name:48s} {len(b):8d} {nl:5d} {h}{note}")
    before = d.parent / (d.name + "_before")
    if before.exists():
        add("\n-- DOCS vs DOCS_before --")
        for f in FILES.values():
            a, b = d / f, before / f
            add(f"{f}: " + ("IDENTICAL" if a.exists() and b.exists() and a.read_bytes() == b.read_bytes() else "DIFFERENT/MISSING"))
    docs = load(d)
    add("\n-- fix status (what the correction prompt still needs to do) --")
    for name, st in fix_status(docs): add(f"{name:46s} {st}")
    import tempfile
    sf = Path(tempfile.gettempdir()) / "qv_default_stale.txt"; sf.write_text("\n".join(DEFAULT_STALE), encoding="utf-8")
    info, fail = lint_checks(d, str(sf)); add("\n-- lint (with default stale list) --"); add(info)
    for f in fail: add("FAIL: " + f)
    add(f"LINT: {'FAIL' if fail else 'PASS'} ({len(fail)})")
    add("\n-- environment / git safety --")
    for t in ("git", "docker", "node", "npm", "wsl", "psql"): add(f"{t}: {shutil.which(t) or 'NOT FOUND'}")
    add("docker daemon: " + (run(["docker", "info", "--format", "{{.ServerVersion}}"]) if shutil.which("docker") else "n/a"))
    add("git check-ignore .env Data: " + run(["git", "check-ignore", "-v", ".env", "Data"]))
    add("git tracks .env?: " + (run(["git", "ls-files", ".env"]) if True else ""))
    add("git history of .env: " + run(["git", "log", "--all", "--oneline", "--", ".env"]))
    add("git status DOCS: " + run(["git", "status", "--short", str(d)]))
    txt = "\n".join(L); print(txt)
    Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_text(txt, encoding="utf-8"); print(f"\n(written to {out})")

if __name__ == "__main__":
    c = sys.argv[1:2]
    if c == ["snapshot"]: snapshot(sys.argv[2], sys.argv[3])
    elif c == ["compare"]: compare(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    elif c == ["lint"]: lint(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif c == ["report"]: report(sys.argv[2] if len(sys.argv) > 2 else "DOCS")
    else: print(__doc__)
