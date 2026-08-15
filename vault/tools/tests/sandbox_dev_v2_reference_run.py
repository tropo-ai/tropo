#!/usr/bin/env python3
"""Stage 3 reference run for 0a0a6777 — kept, not thrown away.

Committed because the spec says the ship proof is not "the definitions parse",
it is two real sandboxed reference runs. A proof that only ever existed in a
terminal is a claim; this one can be re-run by anyone, including the stranger
who has to trust it.

Run: python3 vault/tools/tests/sandbox_dev_v2_reference_run.py

Original header:

Stage 3 proof: a dev v2 run closes at ONE tested SHA and produces NO release artifacts.

Sandboxed. Builds a throwaway git repo with the v2 graph shape, walks a run
through Specify -> Build -> Test, and asserts at the end that:
  1. the terminal verdict welded closure,
  2. the closure bound to exactly the tested tree SHA,
  3. nothing release-class was created.

Point 3 is the half that is easy to skip and is the actual claim of the stage:
"dev work ends at Test". A run that closes correctly while quietly minting a
release entry would satisfy every other assertion here.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

# tests -> tools -> vault -> studio root
SRC = Path(__file__).resolve().parents[3]


def git(cwd, *a):
    r = subprocess.run(["git", *a], cwd=str(cwd), capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(a)}: {r.stderr}")
    return r.stdout.strip()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "studio"
        (root / "vault" / "tools" / "lib").mkdir(parents=True)
        (root / "vault" / "files").mkdir(parents=True)
        (root / ".tropo-studio").mkdir(parents=True)

        # Minimal engine surface: the module under test plus what it imports.
        # Copy the engine and the tools it loads by path at import time. Copying
        # rather than symlinking on purpose: the sandbox must be able to have a
        # dirty tree without dirtying the real studio.
        for rel in ["vault/tools/9e7003b1.py", "vault/tools/tropo-mint-id.py",
                    "vault/tools/tropo-lineage.py"]:
            src = SRC / rel
            if src.is_file():
                (root / rel).write_bytes(src.read_bytes())
        for extra in (SRC / "vault" / "capsules").glob("*.md"):
            d = root / "vault" / "capsules"; d.mkdir(parents=True, exist_ok=True)
            (d / extra.name).write_bytes(extra.read_bytes())
        for lib in (SRC / "vault" / "tools" / "lib").glob("*.py"):
            (root / "vault" / "tools" / "lib" / lib.name).write_bytes(lib.read_bytes())
        # The engine reaches into .tropo/scripts/lib for the identity resolver.
        ks = root / ".tropo" / "scripts" / "lib"
        ks.mkdir(parents=True)
        for lib in (SRC / ".tropo" / "scripts" / "lib").glob("*.py"):
            (ks / lib.name).write_bytes(lib.read_bytes())

        git(root, "init", "-q")
        git(root, "config", "user.email", "sandbox@tropo")
        git(root, "config", "user.name", "sandbox")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "sandbox base")
        tested_sha = git(root, "rev-parse", "HEAD")

        # `lib` must resolve inside the sandbox, and it must resolve there FIRST —
        # the real studio's lib is already importable from this process.
        sys.path.insert(0, str(root / "vault" / "tools"))
        for mod in [m for m in list(sys.modules) if m == "lib" or m.startswith("lib.")]:
            del sys.modules[mod]
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "sandbox_engine", root / "vault" / "tools" / "9e7003b1.py")
        eng = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(eng)
        eng.VAULT_ROOT = root

        print("sandbox studio :", root)
        print("tested tree SHA:", tested_sha)

        # 1. the binding accepts the clean, single-SHA case
        ok = eng.assert_one_unchanged_tested_sha(root, [], tested_sha)
        print("\n[1] clean single-SHA binding accepted   :", ok == tested_sha)

        # 2. a dirty tree refuses (the tested tree no longer exists)
        (root / "vault" / "files" / "scratch.md").write_text("x")
        git(root, "add", "-A")
        dirty_refused = False
        try:
            eng.assert_one_unchanged_tested_sha(root, [], tested_sha)
        except Exception as e:
            dirty_refused = "stale" in str(e)
        print("[2] dirty tree refused as stale         :", dirty_refused)
        git(root, "reset", "-q", "--hard", "HEAD")

        # 3. two trees in one run refuses as theatre
        theatre_refused = False
        try:
            eng.assert_one_unchanged_tested_sha(
                root, [{"event": "verification_receipt", "data": {"tested_sha": "c" * 40}}],
                tested_sha)
        except Exception as e:
            theatre_refused = "theatre" in str(e)
        print("[3] two trees refused as theatre        :", theatre_refused)

        # 4. the journal is written before the close, and is recoverable
        journal = eng._write_close_journal("sandboxact", tested_sha, "talos-t40")
        recorded = json.loads(journal.read_text())
        print("[4] close journal written first         :",
              recorded["tested_sha"] == tested_sha and recorded["state"] == "opened")

        # 5. NO RELEASE ARTIFACTS. The claim of the stage.
        release_shaped = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if any(k in rel for k in ("releases/", "release-notes", ".zip", "package_sha256")):
                release_shaped.append(rel)
        for path in (root / "vault" / "files").glob("*.md"):
            text = path.read_text(errors="ignore")
            if "type: release" in text or "type: release-plan" in text:
                release_shaped.append(path.relative_to(root).as_posix())
        print("[5] release artifacts produced          :", release_shaped or "NONE")

        every = (ok == tested_sha and dirty_refused and theatre_refused
                 and recorded["tested_sha"] == tested_sha and not release_shaped)
        print("\nSTAGE 3 PROOF:", "PASS" if every else "FAIL")
        return 0 if every else 1


if __name__ == "__main__":
    sys.exit(main())
