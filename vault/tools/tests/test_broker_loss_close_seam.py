"""End-to-end coverage across the broker-loss seam (eda86636 / 163b3923).

This test exists because it did not. Two identical incidents five days apart —
Metis G95 on 2026-07-27 and Metis G98 on 2026-08-01 — hit the same failure: an
activation outlives the session-scoped ssh-agent holding its signing key, so its
retirement can never be signed, by anyone, ever. Each cost a principal decision
and roughly forty minutes of hand-editing governed YAML on a lifecycle-critical
record, during a failed boot. Nothing crossed the seam between "the broker is
gone" and "the close still has to happen", so nothing caught the recurrence.

The properties pinned here are the ones whose absence caused real damage:

  1. A close is always possible. The signature is a claim about what was
     provable at close time, not a precondition for closing.
  2. An unsignable close NEVER voids the key. The old remedy renamed the key
     aside, which left the record non-key-bearing while the lineage still
     counted as keyed — complementary on exactly the voided case, so the
     remedy for an unsignable close deterministically bricked the successor's
     birth. It is also irreversible, so a wrong remedy is permanent.
  3. Attested closes are attributable, and fail closed without a principal.
  4. The attested grade cannot be claimed when a signature was available.
  5. Broker health is answerable at step 0, cheaply, before the work is done —
     G98 completed an entire retirement before learning it could not close.
  6. A voided record is never reported as a benign unkeyed one.

Sandboxing follows the established close-tool pattern: patch the module-level
VAULT_ROOT/VAULT_FILES so nothing touches the real vault.

Run: python3 vault/tools/tests/test_broker_loss_close_seam.py
(unittest, not pytest — matches the rest of the authority suite.)
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

_VAULT_TOOLS = Path(__file__).resolve().parent.parent
if str(_VAULT_TOOLS) not in sys.path:
    sys.path.insert(0, str(_VAULT_TOOLS))

_spec = importlib.util.spec_from_file_location(
    "closetool_seam", str(_VAULT_TOOLS / "40b2f455.py")
)
closetool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(closetool)


KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIP7o79JZ82v1GH45The5lUpqJE3UUeZuMA/VMkTqUH+i"
)


def _args(**overrides):
    base = dict(
        activation_uid="",
        target_status="retired",
        closure_reason="",
        transfer_uid="",
        retirement_run_folder="",
        reflection_path="",
        retiring_flip_recorded_at="",
        skip_retirement_invariants=True,
        dry_run=False,
        broker_lost=False,
        authorized_by="",
        check_broker=False,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


def _activation_text(uid: str, *, keyed: bool = True, status: str = "active") -> str:
    key_line = f"agent_public_key: {KEY}\n" if keyed else ""
    return (
        "---\n"
        f"uid: {uid}\n"
        "type: activation\n"
        'title: "seam-agent — Activation"\n'
        "agent: seam-agent\n"
        "agent_class: executive\n"
        "generation: S1\n"
        f"status: {status}\n"
        "activated_at: 2026-08-01\n"
        "activated_by: mike\n"
        f"{key_line}"
        "schema_version: 2\n"
        "---\n\n# Seam activation\n"
    )


class BrokerLossCloseSeamTests(unittest.TestCase):
    """Every property here maps to damage that actually happened."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="broker-seam-")).resolve()
        self.files = self.tmp / "vault" / "files"
        self.files.mkdir(parents=True)
        self.agents_dir = self.tmp / "vault" / "agents"
        self.agents_dir.mkdir(parents=True)
        # The close path takes an authority lock, which is git-backed. A real
        # repo keeps the sandbox faithful to production rather than stubbing
        # out the very locking the lifecycle write depends on.
        subprocess.run(
            ["git", "init", "-q", str(self.tmp)],
            check=True, capture_output=True,
        )
        self._orig = (
            closetool.VAULT_ROOT, closetool.VAULT_FILES, closetool.VAULT_AGENTS
        )
        closetool.VAULT_ROOT = self.tmp
        closetool.VAULT_FILES = self.files
        closetool.VAULT_AGENTS = self.agents_dir

    def tearDown(self):
        (closetool.VAULT_ROOT, closetool.VAULT_FILES,
         closetool.VAULT_AGENTS) = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, uid: str, **kw) -> Path:
        path = self.files / f"{uid}.md"
        path.write_text(_activation_text(uid, **kw), encoding="utf-8")
        return path

    def _close(self, uid: str, **kw):
        """Run the real op_close with commit + side effects neutralised.

        The seam under test is the lifecycle/frontmatter contract, not git.
        """
        args = _args(activation_uid=uid, **kw)
        with patch.object(
            closetool, "_commit_activation_close_with_provenance",
            return_value=(True, "signed-stub"),
        ), patch.object(
            closetool, "_commit_attested_close",
            return_value=(True, "attested-stub"),
        ), patch.object(
            closetool, "_run_post_close_side_effects", return_value=None
        ), patch.object(
            closetool, "remove_agent_keypair", return_value=None
        ):
            return closetool.op_close(args)

    # ---- item 5: the question is answerable at step 0 --------------------

    def test_probe_never_raises_and_distinguishes_all_three_states(self):
        """A probe that can throw is a probe nobody runs at step 0."""
        alive, detail = closetool.probe_signing_broker("00000000", {"uid": "0"})
        self.assertTrue(alive)
        self.assertIn("unkeyed", detail)

        alive, detail = closetool.probe_signing_broker(
            "deadbeef", {"uid": "deadbeef", "agent_public_key": KEY}
        )
        self.assertFalse(alive)
        self.assertTrue(detail.strip(), "a failed probe must say why")

        # item 6 — a VOIDED record must never read as a benign pre-G2 one.
        # That ambiguity is precisely what bricked a birth.
        alive, detail = closetool.probe_signing_broker(
            "cafebabe",
            {
                "uid": "cafebabe",
                "agent_public_key_void": KEY,
                "agent_public_key_lost_original_field": "agent_public_key",
            },
        )
        self.assertFalse(alive)
        self.assertIn("VOIDED", detail)
        self.assertNotIn("pre-G2 history path", detail)

    # ---- item 3: attribution, and failing closed -------------------------

    def test_attested_close_fails_closed_without_a_principal(self):
        uid = "a1a1a1a1"
        path = self._write(uid)
        with self.assertRaises(SystemExit) as raised:
            self._close(uid, broker_lost=True)
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("status: active", path.read_text(encoding="utf-8"))

    def test_attested_grade_refused_when_signing_was_actually_available(self):
        """`attested` must mean impossible, never merely inconvenient.

        Without this the escape hatch becomes the default path and the
        guarantee is quietly erased.
        """
        uid = "b2b2b2b2"
        path = self._write(uid, keyed=False)  # unkeyed => probe says signable
        with self.assertRaises(SystemExit) as raised:
            self._close(uid, broker_lost=True, authorized_by="mike")
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("status: active", path.read_text(encoding="utf-8"))

    # ---- items 1 + 2: the close lands, and the key survives --------------

    def test_unsignable_close_succeeds_and_never_voids_the_key(self):
        """The property whose absence bricked a birth, twice in five days."""
        uid = "c3c3c3c3"
        path = self._write(uid)
        with patch.object(
            closetool, "probe_signing_broker",
            return_value=(False, "signing broker is not running"),
        ):
            rc = self._close(
                uid, broker_lost=True, authorized_by="mike",
                closure_reason="session ended without ceremony",
            )
        self.assertEqual(rc, 0, "an unsignable retirement must still close")

        text = path.read_text(encoding="utf-8")
        self.assertIn("status: retired", text)
        self.assertIn("close_evidence: attested", text)
        self.assertIn("mike", text)

        # THE CRUX. Same field name, same value, nothing renamed, nothing
        # retired, nothing irreversible. The key was never invalid — only the
        # broker was gone.
        self.assertIn(f"agent_public_key: {KEY}", text)
        self.assertNotIn("agent_public_key_void", text)
        self.assertNotIn("agent_public_key_lost_original_field", text)

        # A lifecycle record no loader can read is durable history poison.
        import yaml
        fm = yaml.safe_load(text.split("---")[1])
        self.assertEqual(fm["status"], "retired")
        self.assertEqual(fm["close_evidence"], "attested")
        self.assertEqual(fm["agent_public_key"], KEY)
        self.assertEqual(fm["close_attested_by"], "mike")
        self.assertTrue(str(fm["close_attested_reason"]).strip())

    def test_successor_birth_is_not_bricked_by_an_attested_close(self):
        """The property the old remedy destroyed, stated directly.

        A voided key left the record non-key-bearing while the lineage still
        counted as keyed. After an attested close the record must remain
        key-bearing, so no rescue in the authority chain is required for the
        successor to be born.
        """
        uid = "f6f6f6f6"
        path = self._write(uid)
        with patch.object(
            closetool, "probe_signing_broker",
            return_value=(False, "signing broker is not running"),
        ):
            self._close(uid, broker_lost=True, authorized_by="mike")

        import yaml
        fm = yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])
        self.assertTrue(
            fm.get("agent_public_key"),
            "record must still be key-bearing after an attested close",
        )
        voided = [k for k in fm if str(k).startswith("agent_public_key_")]
        self.assertEqual(voided, [], f"no void artifacts may be created: {voided}")

    # ---- item 1: never a silent third state ------------------------------

    def test_signed_close_records_its_grade_too(self):
        """A reader can always tell which grade it got."""
        uid = "d4d4d4d4"
        path = self._write(uid, keyed=False)
        rc = self._close(uid, closure_reason="clean-retirement")
        self.assertEqual(rc, 0)
        self.assertIn("close_evidence: signed", path.read_text(encoding="utf-8"))

    def test_grade_is_never_duplicated_or_contradictory(self):
        """Re-closing must not stack two grades in one record."""
        uid = "e5e5e5e5"
        path = self._write(uid, keyed=False)
        self._close(uid, closure_reason="clean-retirement")
        self._close(uid, closure_reason="clean-retirement")
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count("close_evidence:"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
