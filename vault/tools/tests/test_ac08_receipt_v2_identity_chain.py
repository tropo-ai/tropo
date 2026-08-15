"""AC8 receipt schema: the public receipt binds bytes and identity.

Preflight §5 and A148's Q4. A v1 receipt proves a release happened and says
where; it cannot say which artefact, which run authorised it, or which
membership shipped, so nothing about it can be checked after the fact. v2 makes
the receipt self-verifying, and the v1 shape stays readable forever without
ever becoming authority for a v2 release.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import release_receipt as rr  # noqa: E402

DIGEST = "c" * 64
FAN_IN = "d" * 64
TAG_PAGE = "https://github.com/tropo-ai/tropo/releases/tag/v1.87.0"
ASSET = "https://github.com/tropo-ai/tropo/releases/download/v1.87.0/tropo-os-v1.87.0.zip"


def v1(**over):
    base = {
        "schema_version": rr.SCHEMA_VERSION,
        "receipt_kind": rr.RECEIPT_KIND,
        "publisher_tool_uid": rr.PUBLISHER_TOOL_UID,
        "publisher_tool_source": rr.PUBLISHER_TOOL_SOURCE,
        "repository": rr.REPOSITORY,
        "version": "1.87.0",
        "tag": "v1.87.0",
        "public_url": TAG_PAGE,
        "published_at": "2026-08-11T15:00:00Z",
        "remote_main_sha": "a" * 40,
        "remote_tag_sha": "a" * 40,
        "release_object_tag": "v1.87.0",
        "release_object_url": TAG_PAGE,
        "release_object_published_at": "2026-08-11T15:00:00Z",
        "release_object_is_draft": False,
        "verify_live_at": "2026-08-11T15:01:00Z",
    }
    base.update(over)
    return base


def v2(**over):
    base = v1(schema_version=rr.SCHEMA_VERSION_V2)
    base.update({
        "release_plan_uid": "11111111",
        "release_entry_uid": "22222222",
        "release_activation_uid": "33333333",
        "release_pipeline_run_uid": "44444444",
        "activation_root_uid": "55555555",
        "fan_in_digest": FAN_IN,
        "package_sha256": DIGEST,
        "public_asset_observations": [{"url": ASSET, "observed_sha256": DIGEST}],
        "transaction_id": "tx-01",
    })
    base.update(over)
    return base


class TheV2ReceiptBindsBytesAndIdentity(unittest.TestCase):

    def test_a_complete_v2_receipt_validates(self):
        self.assertEqual(rr.validate_release_receipt_v2(v2())["package_sha256"], DIGEST)

    def test_every_added_binding_is_required(self):
        """P4: drop each binding one at a time."""
        for field in sorted(rr.V2_ADDED_FIELDS):
            with self.subTest(dropped=field):
                raw = v2()
                del raw[field]
                with self.assertRaises(rr.ReleaseReceiptError):
                    rr.validate_release_receipt_v2(raw)

    def test_the_v1_core_is_still_enforced(self):
        with self.assertRaises(rr.ReleaseReceiptError):
            rr.validate_release_receipt_v2(v2(tag="1.87.0"))

    def test_an_observed_digest_that_differs_from_the_package_refuses(self):
        """P16/P3: what is downloadable must be what shipped."""
        with self.assertRaises(rr.ReleaseReceiptError) as caught:
            rr.validate_release_receipt_v2(v2(
                public_asset_observations=[{"url": ASSET, "observed_sha256": "e" * 64}]))
        self.assertIn("Silent divergence", str(caught.exception))

    def test_a_receipt_with_no_observation_refuses(self):
        """Recording an upload is not verifying a download."""
        with self.assertRaises(rr.ReleaseReceiptError) as caught:
            rr.validate_release_receipt_v2(v2(public_asset_observations=[]))
        self.assertIn("recording an upload", str(caught.exception))

    def test_a_mirror_must_match_too(self):
        mirror = ASSET.replace("github.com", "supabase.example.com")
        with self.assertRaises(rr.ReleaseReceiptError):
            rr.validate_release_receipt_v2(v2(public_asset_observations=[
                {"url": ASSET, "observed_sha256": DIGEST},
                {"url": mirror, "observed_sha256": "f" * 64},
            ]))

    def test_malformed_uids_and_digests_refuse(self):
        with self.assertRaises(rr.ReleaseReceiptError):
            rr.validate_release_receipt_v2(v2(release_plan_uid="nothex01"))
        with self.assertRaises(rr.ReleaseReceiptError):
            rr.validate_release_receipt_v2(v2(package_sha256="short"))


class V1IsHistoryNeverAuthority(unittest.TestCase):

    def test_a_v1_receipt_still_validates_as_v1(self):
        """Read compatibility is real: old receipts stay interpretable."""
        self.assertEqual(rr.validate_release_receipt(v1())["version"], "1.87.0")

    def test_a_v1_receipt_cannot_authorise_a_v2_release(self):
        with self.assertRaises(rr.ReleaseReceiptError) as caught:
            rr.assert_v2_authority(v1(), purpose="release closure")
        message = str(caught.exception)
        self.assertIn("v1 receipt", message)
        self.assertIn("package_sha256", message,
                      "the refusal must name the missing digest rather than "
                      "just declining")
        self.assertIn("remains valid evidence", message,
                      "the refusal should not imply the v1 receipt is invalid")

    def test_a_v2_receipt_is_accepted_as_authority(self):
        self.assertEqual(
            rr.assert_v2_authority(v2(), purpose="release closure")["transaction_id"],
            "tx-01")

    def test_an_unknown_schema_is_refused_rather_than_assumed(self):
        with self.assertRaises(rr.ReleaseReceiptError) as caught:
            rr.assert_v2_authority(v1(schema_version="3.0.0"), purpose="closure")
        self.assertIn("unrecognised", str(caught.exception))

    def test_authority_refusal_names_what_it_was_asked_to_authorise(self):
        for purpose in ("the package gate", "release closure"):
            with self.subTest(purpose=purpose):
                with self.assertRaises(rr.ReleaseReceiptError) as caught:
                    rr.assert_v2_authority(v1(), purpose=purpose)
                self.assertIn(purpose, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
