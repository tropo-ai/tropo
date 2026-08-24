#!/usr/bin/env python3
"""v1.91 S2 AC3 (3fb41c99) — ONE reader per question, the keystone.

Two questions, answered from one journal: "is this run frozen" and "which
candidate is live." `lib/release_package.active_frozen_payload()` /
`active_candidate()` are the shared resolver. AC3 requires every OTHER reader
of the same journal to resolve through them rather than re-deriving the
answer with its own loop.

Argus A154's ruling (2026-08-23, correcting his own earlier framing): the
scope is TWO readers, not three.

  1. `tropo-freeze-release-candidate.py:decide()` — instance #4 in the spec's
     measured table. Its own comment (lines ~113-122) already admits the
     disagreement: "lib/release_package.active_frozen_payload() returned NONE
     for this same run while this loop said 'already frozen'."
  2. `lib/release_events.AuthorizationContext.observe()` — a second,
     independent re-derivation. Unwired (no production caller today), but
     ruled in scope anyway: "ONE READER PER QUESTION" does not say "among
     readers with callers," and this one does not merely duplicate the
     shared resolver -- it DISAGREES. It never handles `package_superseded`
     for `frozen_package_sha256` at all, so the day something wires it, it
     inherits a wrong answer silently. Same shape as `package_frozen`
     acquiring two meanings.

The publisher (`tropo-publish-release.py:1598,2919`) was in Argus's original
list and is struck: it already calls `active_frozen_payload` at both sites.
Asserted here as staying that way, not fixed.

THE PROOF CASE (Argus's own ask): a journal containing a `package_superseded`
row must yield the SAME answer -- "not frozen" -- from every reader. That is
exactly the case `AuthorizationContext.observe()` gets wrong today (RED
baseline), and the case the freeze tool's own comment names as the v1.90
defect it already lived through.
"""
from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[3]
TOOLS = STUDIO / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _code_only(source: str) -> str:
    """Strip whole-line comments so a structural check cannot be satisfied by
    a comment merely NAMING the function it should be calling. The freeze
    tool's own decide() has exactly this trap: its comment already quotes
    'lib/release_package.active_frozen_payload()' while describing the bug,
    three lines above code that never calls it.
    """
    return "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )

from lib import release_package as pkg  # noqa: E402
from lib import release_verify as rv  # noqa: E402

_freeze_spec = importlib.util.spec_from_file_location(
    "tropo_freeze_release_candidate_ac3", TOOLS / "tropo-freeze-release-candidate.py")
freeze = importlib.util.module_from_spec(_freeze_spec)
sys.modules[_freeze_spec.name] = freeze
_freeze_spec.loader.exec_module(freeze)

_events_spec = importlib.util.spec_from_file_location(
    "release_events_for_ac3", TOOLS / "lib" / "release_events.py")
release_events = importlib.util.module_from_spec(_events_spec)
sys.modules[_events_spec.name] = release_events
_events_spec.loader.exec_module(release_events)

RUN = "934436ca"


class SharedResolverAgreementTests(unittest.TestCase):
    """Every reader answers 'is this run frozen' the same way the shared
    resolver does, on the exact journal shape v1.90 measured live."""

    def _superseded_journal(self):
        """build -> freeze -> supersede. Ground truth: NOT frozen."""
        return [
            {"event": "tropo.release.candidate_built",
             "data": {"pipeline_run_uid": RUN, "candidate_sha256": "aaa111"}},
            {"event": "tropo.release.package_frozen",
             "data": {"pipeline_run_uid": RUN, "package_sha256": "aaa111"}},
            {"event": "tropo.release.package_superseded",
             "data": {"release_run_uid": RUN, "old_package_sha256": "aaa111",
                      "reason": "changelog promoted after freeze"}},
        ]

    def test_the_shared_resolver_itself_says_not_frozen(self):
        """Ground truth, asserted first so a fixture bug cannot masquerade as
        agreement between two readers that are both wrong the same way."""
        self.assertIsNone(pkg.active_frozen_payload(self._superseded_journal(), RUN))

    def test_the_freeze_tool_agrees_the_run_is_not_frozen(self):
        """decide() must not refuse with 'already frozen' once superseded.

        Isolated from the freeze tool's OTHER three criteria (byte match,
        four receipts, no invalidation) by using its own `decide()` on a
        journal built to pass all of them -- so a failure here can only be
        the frozen-question disagreement, not some other refusal.
        """
        import hashlib
        import json
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="ac3-freeze-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        candidate = tmp / "tropo-1.91.0.zip"
        candidate.write_bytes(b"ac3 proof bytes")
        sha = hashlib.sha256(candidate.read_bytes()).hexdigest()

        rows = [
            {"event": "tropo.release.candidate_built",
             "data": {"pipeline_run_uid": RUN, "candidate_sha256": sha}},
            {"event": "tropo.release.package_frozen",
             "data": {"pipeline_run_uid": RUN, "package_sha256": sha}},
            {"event": "tropo.release.package_superseded",
             "data": {"release_run_uid": RUN, "old_package_sha256": sha,
                      "reason": "changelog promoted after freeze"}},
        ]
        # v1.91 S2 (3fb41c99): the real release-verification-receipt shape,
        # not the generic dev-pipeline verification_receipt name it collided
        # with (Argus A155's ruling).
        for step in freeze.INSTRUMENTS:
            rows.append({
                "event": rv.RECEIPT_KIND,
                "data": {"receipt_kind": rv.RECEIPT_KIND,
                         "instrument": freeze.INSTRUMENTS[step],
                         "release_run_uid": RUN, "candidate_sha256": sha,
                         "verdict": "pass", "executor_or_attester": "test",
                         "execution_mode": "machine", "evidence_ref": step,
                         "started_at": "2026-08-23T00:00:00Z",
                         "completed_at": "2026-08-23T00:00:00Z"},
            })
        (tmp / "run.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

        payload, refusal = freeze.decide(tmp, candidate)
        self.assertIsNone(
            refusal,
            f"the freeze tool refused a superseded (not active-frozen) run: {refusal!r} "
            "-- it disagrees with lib/release_package.active_frozen_payload, the exact "
            "v1.90 defect ('already frozen' vs NONE)",
        )
        self.assertEqual(payload["verdict"], "pass")

    def test_authorization_context_agrees_the_run_is_not_frozen(self):
        """observe().frozen_package_sha256 must be None once superseded.

        RED baseline (2026-08-23): observe() never handles
        package_superseded, so it reports the superseded sha as still frozen
        -- the same disagreement the freeze tool already lived through,
        latent in a second, unwired reader.
        """
        import json
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="ac3-authctx-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "run.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in self._superseded_journal()),
            encoding="utf-8")

        observed = release_events.AuthorizationContext.observe(tmp)
        self.assertIsNone(
            observed.frozen_package_sha256,
            "AuthorizationContext.observe() reports a package_superseded run as still "
            "frozen -- disagrees with lib/release_package.active_frozen_payload",
        )


class DelegatesToTheSharedResolverTests(unittest.TestCase):
    """Behavioral agreement is not enough: instances 1-3 in the spec's own
    table were 'cured in-flight during v1.90' by ad-hoc patches that produced
    the right OUTPUT while still duplicating the LOGIC, and the spec names
    those cures as symptom patches, not the fix. The freeze tool's own
    already-frozen/package_superseded handling is exactly that shape today
    (see decide()'s comment) -- it agrees with the ground truth on the proof
    case above for the wrong reason: a second hand-patched loop, not a call
    to the shared resolver. Assert the delegation structurally so a future
    scenario cannot silently diverge again the way #3/#4/#5/#6 already did.
    """

    def test_the_freeze_tool_calls_the_shared_resolver(self):
        source = _code_only((TOOLS / "tropo-freeze-release-candidate.py").read_text(encoding="utf-8"))
        self.assertIn(
            "release_package", source,
            "tropo-freeze-release-candidate.py does not import lib.release_package "
            "in actual code -- decide() is answering 'is this run frozen' with its "
            "own loop (a COMMENT naming the function does not count)",
        )
        self.assertTrue(
            re.search(r'active_frozen_payload\s*\(', source),
            "decide() does not CALL release_package.active_frozen_payload() -- it "
            "still re-derives 'already frozen' from its own loop over raw events, "
            "which is the AC3 defect even where the two happen to agree today",
        )

    def test_authorization_context_calls_the_shared_resolver(self):
        source = _code_only((TOOLS / "lib" / "release_events.py").read_text(encoding="utf-8"))
        self.assertTrue(
            re.search(r'active_frozen_payload\s*\(', source)
            and re.search(r'active_candidate\s*\(', source),
            "AuthorizationContext.observe() does not CALL "
            "release_package.active_candidate()/active_frozen_payload() -- it "
            "re-derives both facts with its own loop",
        )


class CandidateLivenessAgreementTests(unittest.TestCase):
    """The second question -- 'which candidate is live' -- agrees too."""

    def _invalidated_journal(self):
        return [
            {"event": "tropo.release.candidate_built",
             "data": {"pipeline_run_uid": RUN, "candidate_sha256": "bbb222"}},
            {"event": "tropo.release.candidate_invalidated",
             "data": {"pipeline_run_uid": RUN, "candidate_sha256": "bbb222",
                      "reason": "prose fix"}},
        ]

    def test_authorization_context_agrees_no_candidate_is_live(self):
        import json
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="ac3-cand-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "run.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in self._invalidated_journal()),
            encoding="utf-8")

        ground_truth = pkg.active_candidate(self._invalidated_journal(), RUN)
        observed = release_events.AuthorizationContext.observe(tmp)
        self.assertIsNone(ground_truth)
        self.assertEqual(
            observed.active_candidate_sha256, ground_truth,
            "AuthorizationContext.observe() disagrees with "
            "lib/release_package.active_candidate() on candidate liveness",
        )


class PublisherStaysCompliantTests(unittest.TestCase):
    """The publisher was already routing through the shared resolver at both
    call sites before this AC; prove it stays that way rather than silently
    regressing while AC3's fix lands elsewhere."""

    def test_the_publisher_reads_frozen_state_through_the_shared_resolver(self):
        source = (TOOLS / "tropo-publish-release.py").read_text(encoding="utf-8")
        calls = re.findall(r'release_package\.active_frozen_payload\(', source)
        self.assertGreaterEqual(
            len(calls), 2,
            "tropo-publish-release.py no longer calls "
            "release_package.active_frozen_payload at (at least) its two known "
            "sites -- the publisher regressed off the shared resolver",
        )
        self.assertNotIn(
            "already_frozen = True", source,
            "tropo-publish-release.py grew its own local frozen-tracking loop",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
