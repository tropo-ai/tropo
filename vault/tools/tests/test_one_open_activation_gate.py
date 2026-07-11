#!/usr/bin/env python3
"""Gauntlet for the one-open-activation engine gate (board item 3b433691).

Proves: pipeline-activate.py refuses to open a second activation for a
(pipeline_uid, dev_spec_uid) pair that already has one OPEN — the exact
proof-case from the 2026-07-01 collision (dev-spec ba454e56: Argus's
ad02f944 canonical vs Talos's 9edee670 duplicate, opened four minutes apart
on crossed messages). Retired/superseded priors must NOT block a legitimate
re-run. Self-running (python3 test_one_open_activation_gate.py) and
pytest-compatible.
"""
import sys, tempfile, shutil
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_TOOLS))
import importlib.util
_spec = importlib.util.spec_from_file_location("pipeline_activate", _TOOLS / "e337f1dd.py")
pa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pa)


def _write_activation(root: Path, uid: str, pipeline_uid: str, dev_spec_uid: str,
                       status: str, activated_by: str = "talos"):
    (root / f"{uid}.md").write_text(
        "---\n"
        "type: activation\n"
        f"uid: {uid}\n"
        "activation_class: pipeline\n"
        f"pipeline_uid: {pipeline_uid}\n"
        f"dev_spec_uid: {dev_spec_uid}\n"
        f"status: {status}\n"
        f"activated_by: {activated_by}\n"
        "activated_at: '2026-07-01'\n"
        "---\n\n# test fixture\n"
    )


def main() -> int:
    results = []

    def check(name, ok):
        results.append((name, bool(ok)))

    tmp = Path(tempfile.mkdtemp(prefix="one-open-act-gauntlet-"))
    orig_vault_files = pa.VAULT_FILES
    try:
        pa.VAULT_FILES = tmp

        # 1. Empty sandbox — no collision, fresh activation proceeds.
        check("no prior activation -> no collision",
              pa.find_open_activation("cd1fcd25", "ba454e56") is None)

        # 2. The exact plant: reproduce the 2026-07-01 collision sequence.
        #    Argus opens ad02f944 (OPEN) for (cd1fcd25, ba454e56) first.
        _write_activation(tmp, "ad02f944", "cd1fcd25", "ba454e56", "active", "argus")
        collision = pa.find_open_activation("cd1fcd25", "ba454e56")
        check("plant: Talos's second activation attempt -> REFUSED (collision detected)",
              collision is not None and collision.get("uid") == "ad02f944")
        check("plant: refusal names the holder",
              collision is not None and collision.get("activated_by") == "argus")

        # 3. Retire the open run (supersession path) — a NEW activation must
        #    now be allowed; retired priors do not block legitimate re-runs.
        _write_activation(tmp, "ad02f944", "cd1fcd25", "ba454e56", "retired", "argus")
        check("retired prior -> does NOT block re-activation",
              pa.find_open_activation("cd1fcd25", "ba454e56") is None)

        # 4. Specificity: same pipeline, DIFFERENT dev-spec -> no collision.
        _write_activation(tmp, "aaaaaaaa", "cd1fcd25", "ba454e56", "active", "argus")
        check("same pipeline, different dev-spec -> no collision",
              pa.find_open_activation("cd1fcd25", "other-spec") is None)

        # 5. Specificity: DIFFERENT pipeline, same dev-spec -> no collision.
        check("different pipeline, same dev-spec -> no collision",
              pa.find_open_activation("other-pipeline", "ba454e56") is None)

    finally:
        pa.VAULT_FILES = orig_vault_files
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"  {'✓' if ok else '✗ FAIL'}  {name}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


def test_one_open_activation_gate():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
