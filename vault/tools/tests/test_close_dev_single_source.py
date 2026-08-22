"""9a640a8a AC1/AC2 — the one-command close: receipt for the fan-in, never refuses.

Causal over live substrate: the three closes this tool performed today ARE the
fixtures. Discriminating per the studio rule: each test names what turns it red.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[3]
RUNS = STUDIO / "vault" / "pipeline-runs"
CLOSES = {  # spec -> (activation, run, run_folder_glob)
    "d317f532": ("084dfef7", "92a485c8"),
    "dd570ea4": ("87aa63ad", "5cee5fea"),
    "4883fa94": ("921d4694", "9143dad0"),
}


def _receipts(run_glob):
    out = []
    for d in RUNS.glob(f"*{run_glob}*"):
        j = d / "run.jsonl"
        if not j.is_file():
            continue
        for line in j.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"dev_closed"' not in line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") == "dev_closed" and (ev.get("data") or {}).get(
                    "receipt_kind") == "canonical-dev-close":
                out.append(ev)
    return out


class ReceiptContractTests(unittest.TestCase):
    """AC1: exactly one canonical receipt, identity-bound, one 40-hex sha.

    RED if: the receipt write is removed (no receipts), the close double-stamps
    (receipt count > 1 breaks the fan-in's exactly-one), or identity fields drop.
    """

    def test_exactly_one_canonical_receipt_per_close(self):
        for spec, (_act, run) in CLOSES.items():
            with self.subTest(spec=spec):
                rs = _receipts(run)
                self.assertEqual(len(rs), 1, f"{spec}: fan-in requires exactly one, found {len(rs)}")

    def test_receipt_binds_identity_and_one_sha(self):
        import re
        sha_re = re.compile(r"^[0-9a-f]{40}$")
        for spec, (act, run) in CLOSES.items():
            with self.subTest(spec=spec):
                d = _receipts(run)[0]["data"]
                self.assertEqual(d["dev_spec_uid"], spec)
                self.assertEqual(d["activation_uid"], act)
                self.assertTrue(sha_re.match(d["tested_commit_sha"]))

    def test_fan_in_reads_every_receipt(self):
        import importlib.util
        spec_l = importlib.util.spec_from_file_location(
            "lrp", STUDIO / "vault/tools/tropo-lock-release-plan.py")
        lrp = importlib.util.module_from_spec(spec_l)
        try:
            spec_l.loader.exec_module(lrp)
        except SystemExit:
            pass
        for spec, (act, run) in CLOSES.items():
            with self.subTest(spec=spec):
                r = lrp.read_canonical_close_receipt(spec, act, run, STUDIO / "vault/files")
                self.assertEqual(r.get("receipt_kind"), "canonical-dev-close")


class NeverRefusesTests(unittest.TestCase):
    """AC2: idempotent no-op on a receipted run; hard stop only on unresolvable ids.

    RED if: a second close writes a second receipt, or a bogus uid exits 0.
    """

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(STUDIO / "vault/tools/tropo-close-dev.py"), *args],
            capture_output=True, text=True, timeout=120)

    def test_second_close_is_a_reported_noop(self):
        before = len(_receipts("92a485c8"))
        p = self._run("--dev-spec-uid", "d317f532", "--actor", "test-suite")
        self.assertEqual(p.returncode, 0)
        self.assertIn("already-receipted", p.stdout)
        self.assertEqual(len(_receipts("92a485c8")), before, "a second receipt was written")

    def test_unresolvable_spec_stops_by_name(self):
        p = self._run("--dev-spec-uid", "00000000", "--actor", "test-suite")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("does not resolve", p.stderr)


if __name__ == "__main__":
    unittest.main()
