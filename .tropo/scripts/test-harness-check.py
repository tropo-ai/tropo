#!/usr/bin/env python3
"""test-harness-check.py — the mechanical-regression layer of the Release Test-Harness.

Design-brief f13cc214 (Mike-A115). Deterministic, zero-judgment PASS/FAIL checks a cold agent
(or a human) runs against a release build to answer "does this release still work?" — the
automated-regression half. The guided stranger-walk (agent judgment) is the playbook's other half.

SELF-CONTAINED BY DESIGN: no studio imports, stdlib only — it must run inside a stranger's
downloaded release with nothing but Python. Run it from the release root, or pass --release-dir.
Writes a machine + human readable verdict; exit 0 = all PASS, nonzero = at least one FAIL.

PROTOTYPE (Argus A115, 2026-06-17) — lock-ready for the v1.72 cycle, which wires it into
Build-Release Phase 3 + the canonical playbook. Golden-output snapshots (diff actual-vs-expected
per release) are the planned v1.1 hardening; this v0 checks structural + integrity invariants.
"""
import sys, os, json, re, argparse
from pathlib import Path

# Files/dirs every Tropo release must contain for a stranger to cold-boot.
# H1 (258f5aa6): CLAUDE.md + .tropo/concierge/activate.md added per gate-4 gauntlet finding.
REQUIRED = [
    "AGENTS.md", "README.md", "START-TROPO.md", "CAPSULE.md", "CLAUDE.md",
    ".tropo/version.md", ".tropo/orientation.md", ".tropo/playbooks",
    ".tropo/concierge/activate.md",
    "vault/00-index.jsonl",
]
PRIVATE_SCOPES = ("argo-private", "reference-only")  # must NEVER ship


def _check(name, ok, detail=""):
    return {"check": name, "ok": bool(ok), "detail": detail}


def run_checks(root: Path):
    results = []

    # 1. Required structure
    missing = [f for f in REQUIRED if not (root / f).exists()]
    results.append(_check("required files/dirs present", not missing,
                          "all present" if not missing else f"MISSING: {missing}"))

    # 2. Index integrity — every line valid JSON with uid+type
    idx = root / "vault" / "00-index.jsonl"
    rows, bad = 0, 0
    uids = set()
    if idx.is_file():
        for line in idx.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rows += 1
            try:
                d = json.loads(line)
                if not d.get("uid") or not d.get("type"):
                    bad += 1
                else:
                    uids.add(d["uid"])
            except Exception:
                bad += 1
        # (E) v0.1 fix: rows>0 guard — empty file gives rows=0,bad=0 which was PASS before
        ok = bad == 0 and rows > 0
        results.append(_check("index parses (every row valid JSON + uid/type)", ok,
                              f"{rows} rows, {bad} malformed" if rows > 0 else "EMPTY — index has 0 rows"))
    else:
        results.append(_check("index parses", False, "00-index.jsonl absent"))

    # 3. Version stamped — accept either bare "v1.71.0" or frontmatter `version: "1.71.0"`
    # (the build stamps version.md as a formatted markdown doc; source is bare — handle both)
    vf = root / ".tropo" / "version.md"
    raw = vf.read_text() if vf.is_file() else ""
    ver = ""
    m = re.search(r'(?m)^\s*version:\s*["\']?v?(\d+\.\d+\.\d+)', raw)
    if m:
        ver = "v" + m.group(1)
    else:
        m2 = re.search(r'v?(\d+\.\d+\.\d+)', raw)
        if m2:
            ver = "v" + m2.group(1)
    # (F) v0.1 fix: value floor — v0.0.0 matches the shape regex but is not a real release version
    ver_ok = bool(ver) and ver != "v0.0.0"
    results.append(_check("version stamped", ver_ok, f"version = {ver or '(unparseable)'}"))

    # 4. Capsules present — the type system ships (v1.60+ path: vault/files/ as type:capsule-definition)
    # Pre-v1.60: capsules lived at .tropo/capsules/*.capsule.md (kernel copy).
    # Post-v1.60 migration: capsules are vault entries (extraction_scope:ship) landing in vault/files/<uid>.md.
    vfiles_dir = root / "vault" / "files"
    caps = []
    if vfiles_dir.is_dir():
        for p in vfiles_dir.glob("*.md"):
            if p.stat().st_size == 0:
                continue
            head = p.read_bytes()[:500].decode("utf-8", errors="replace")
            if "type: capsule-definition" in head:
                caps.append(p)
    results.append(_check("capsule definitions ship", len(caps) > 0,
                          f"{len(caps)} capsule-definition entries in vault/files"))

    # 5. Manifest present
    results.append(_check("MANIFEST present", (root / "MANIFEST.md").is_file(),
                          "MANIFEST.md" if (root / "MANIFEST.md").is_file() else "absent (non-fatal warn upstream)"))

    # 6. No private content leaked into shipped vault entries
    leaks = []
    vfiles = root / "vault" / "files"
    if vfiles.is_dir():
        for p in vfiles.glob("*.md"):
            head = p.read_text()[:1500]
            for scope in PRIVATE_SCOPES:
                if f"extraction_scope: {scope}" in head or f'extraction_scope: "{scope}"' in head:
                    leaks.append(p.name)
                    break
    results.append(_check("no private/reference-only content leaked", not leaks,
                          "clean" if not leaks else f"LEAKED: {leaks[:5]}{'…' if len(leaks) > 5 else ''}"))

    # 7. (G) v0.1 fix: .tropo/playbooks/*.md count>0 — dir-exists was PASS even with 0 playbooks
    playbooks_dir = root / ".tropo" / "playbooks"
    playbooks = list(playbooks_dir.glob("*.md")) if playbooks_dir.is_dir() else []
    results.append(_check(".tropo/playbooks has at least one .md playbook", len(playbooks) > 0,
                          f"{len(playbooks)} playbooks" if playbooks else "EMPTY — no .md files in .tropo/playbooks/"))

    # 8. H2 (258f5aa6) — START-TROPO.md is non-empty (has ≥ 1 non-blank line)
    st = root / "START-TROPO.md"
    st_lines = [ln for ln in st.read_text().splitlines() if ln.strip()] if st.is_file() else []
    results.append(_check("START-TROPO.md non-empty", len(st_lines) > 0,
                          f"{len(st_lines)} non-blank lines" if st_lines else "empty or absent"))

    # 8. H3 (258f5aa6) + (H3) v0.1 fix: size>0 — a 0-byte validator placeholder was presence-PASS before
    validator = root / "vault" / "tools" / "tropo-validate.py"
    val_ok = validator.is_file() and validator.stat().st_size > 0
    val_detail = (f"present ({validator.stat().st_size} bytes)" if val_ok
                  else ("ABSENT" if not validator.is_file() else "EMPTY (0 bytes) — not a real validator"))
    results.append(_check("tropo-validate.py present and non-empty", val_ok, val_detail))

    # 9. H4 (258f5aa6) — golden-output snapshot (compare if expected-checks.json exists, else skip)
    snapshot_f = root / "expected-checks.json"
    if snapshot_f.is_file():
        try:
            expected = json.loads(snapshot_f.read_text())
            actual_names = [r["check"] for r in results]
            missing = [n for n in expected if n not in actual_names]
            extra = [n for n in actual_names if n not in expected]
            ok = not missing and not extra
            detail = "matches snapshot" if ok else f"missing={missing[:3]} extra={extra[:3]}"
            results.append(_check("golden-output snapshot match", ok, detail))
        except Exception as e:
            results.append(_check("golden-output snapshot match", False, f"snapshot parse error: {e}"))
    else:
        results.append(_check("golden-output snapshot (not seeded — skip)", True,
                              "no expected-checks.json; seed with check names to activate"))

    return results, {"index_rows": rows, "uids": len(uids), "version": ver, "capsule_defs": len(caps)}


def write_report(root: Path, results, stats, mode="mechanical"):
    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    verdict = "PASS" if passed == total else "FAIL"
    lines = [
        f"# Release Test-Report — mechanical layer ({verdict})",
        "",
        f"- release_dir: `{root}`",
        f"- mode: {mode} (deterministic regression; the guided stranger-walk is the playbook's other half)",
        f"- result: **{passed}/{total} checks passed**",
        f"- stats: {stats}",
        "",
        "| Check | Verdict | Detail |",
        "|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['check']} | {'✓ PASS' if r['ok'] else '✗ FAIL'} | {r['detail']} |")
    lines.append("")
    report = root / "test-report.md"
    report.write_text("\n".join(lines) + "\n")
    return report, verdict, passed, total


def main(argv=None):
    ap = argparse.ArgumentParser(description="Release Test-Harness — mechanical regression checks")
    ap.add_argument("--release-dir", default=".", help="release build root (default: cwd)")
    ap.add_argument("--no-report", action="store_true", help="print only; don't write test-report.md")
    args = ap.parse_args(argv)
    root = Path(args.release_dir).resolve()
    results, stats = run_checks(root)
    for r in results:
        print(f"  {'✓' if r['ok'] else '✗ FAIL'}  {r['check']} — {r['detail']}")
    passed = sum(1 for r in results if r["ok"])
    print(f"\n{passed}/{len(results)} mechanical checks passed")
    if not args.no_report:
        report, verdict, p, t = write_report(root, results, stats)
        print(f"report → {report} ({verdict} {p}/{t})")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
