"""Cross-implementation vectors for the public release receipt projection.

These are the shared positive/negative vectors from design brief ``459a3070``
that BOTH the publisher and the website consumer must pass identically: the
normative golden bytes/hash, Unicode, key ordering, compact separators, final
LF, schema rejection, fact-ID/index consistency, single-byte tampering, and the
``public_fact_id`` vs ``projection_sha256`` substitution + equality negatives.

Destination-agnostic (Argus A134 G1.2 PARTIAL GO). No transport is exercised.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "vault" / "tools" / "lib"
sys.path.insert(0, str(LIB))


def _load_projection():
    spec = importlib.util.spec_from_file_location(
        "public_receipt_projection_under_test",
        LIB / "public_receipt_projection.py",
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not load public_receipt_projection")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = _load_projection()

# The normative cross-implementation vector from 459a3070.
GOLDEN = {
    "occurred_at": "2026-07-18T00:00:00Z",
    "public_fact_id": "rf_63bd173c61a8cc92071cd4f055e59f90edce537a963ad9582005a0301325c259",
    "public_url": "https://github.com/tropo-ai/tropo/releases/tag/v1.2.3",
    "tag": "v1.2.3",
    "type": "tropo.release.published",
    "version": "1.2.3",
}
GOLDEN_BYTES_LEN = 261
GOLDEN_SHA256 = "824690db5f495e5faa3c5a0d4b413b2e06afa808673235acdc890e9da1270356"


def _mutate(**overrides):
    fact = dict(GOLDEN)
    fact.update(overrides)
    return fact


class GoldenVectorTests(unittest.TestCase):
    def test_golden_bytes_and_hash(self):
        payload = P.canonical_projection_bytes(GOLDEN)
        self.assertEqual(len(payload), GOLDEN_BYTES_LEN)
        self.assertEqual(P.sha256_bytes(payload), GOLDEN_SHA256)
        self.assertEqual(P.projection_sha256(GOLDEN), GOLDEN_SHA256)
        # exactly one trailing LF, no CR, sorted keys, compact separators
        self.assertTrue(payload.endswith(b"\n"))
        self.assertFalse(payload.endswith(b"\n\n"))
        self.assertNotIn(b"\r", payload)
        self.assertNotIn(b", ", payload)
        self.assertNotIn(b": ", payload)
        text = payload.decode("utf-8")
        self.assertEqual(list(json.loads(text).keys()), sorted(GOLDEN.keys()))

    def test_round_trip_parse(self):
        payload = P.canonical_projection_bytes(GOLDEN)
        parsed = P.parse_projection_bytes(payload)
        self.assertEqual(parsed, GOLDEN)


class IdentityDistinctionTests(unittest.TestCase):
    def test_public_fact_id_differs_from_projection_hash(self):
        # The two identifiers are deliberately different.
        self.assertNotEqual(GOLDEN["public_fact_id"], P.projection_sha256(GOLDEN))
        # public_fact_id carries the rf_ prefix; projection_sha256 is bare 64-hex.
        self.assertTrue(GOLDEN["public_fact_id"].startswith("rf_"))
        self.assertFalse(P.projection_sha256(GOLDEN).startswith("rf_"))

    def test_substituting_hash_for_fact_id_fails(self):
        # Substituting the projection hash as public_fact_id must fail the rf_ rule.
        bad = _mutate(public_fact_id=P.projection_sha256(GOLDEN))
        with self.assertRaises(P.ProjectionError):
            P.validate_projection(bad)
        # ...and prefixing it does not make it the same identifier either.
        bad2 = _mutate(public_fact_id="rf_" + P.projection_sha256(GOLDEN))
        # rf_ + 64hex is a syntactically valid fact id, but it is NOT required to
        # equal the projection hash; validation must accept it without demanding
        # equality (proving the validator does not conflate the two).
        validated = P.validate_projection(bad2)
        self.assertNotEqual(validated["public_fact_id"][3:], P.projection_sha256(bad2))

    def test_no_equality_requirement(self):
        # A validator that REQUIRED pfid == sha would reject the golden vector.
        self.assertNotEqual(
            GOLDEN["public_fact_id"], "rf_" + P.projection_sha256(GOLDEN)
        )
        # The real validator accepts the golden vector precisely because it does
        # not require equality.
        self.assertEqual(P.validate_projection(GOLDEN), GOLDEN)


class CanonicalizationTests(unittest.TestCase):
    def test_unicode_emitted_as_utf8_not_escaped(self):
        # The six projection fields are ASCII, so this exercises the shared
        # canonicalizer contract directly: non-ASCII is UTF-8, never \uXXXX.
        payload = P.canonical_json_bytes({"k": "caf\u00e9-\u2713"})
        self.assertEqual(payload, "{\"k\":\"caf\u00e9-\u2713\"}\n".encode("utf-8"))
        self.assertNotIn(b"\\u", payload)

    def test_reordered_keys_are_noncanonical(self):
        reordered = (
            b'{"type":"tropo.release.published","occurred_at":"2026-07-18T00:00:00Z",'
            b'"public_fact_id":"rf_63bd173c61a8cc92071cd4f055e59f90edce537a963ad9582005a0301325c259",'
            b'"public_url":"https://github.com/tropo-ai/tropo/releases/tag/v1.2.3",'
            b'"tag":"v1.2.3","version":"1.2.3"}\n'
        )
        with self.assertRaises(Exception):
            P.parse_projection_bytes(reordered)

    def test_zero_and_double_trailing_lf_rejected(self):
        base = P.canonical_projection_bytes(GOLDEN)
        with self.assertRaises(Exception):
            P.parse_projection_bytes(base.rstrip(b"\n"))
        with self.assertRaises(Exception):
            P.parse_projection_bytes(base + b"\n")

    def test_whitespace_and_crlf_rejected(self):
        base = P.canonical_projection_bytes(GOLDEN)
        with self.assertRaises(Exception):
            P.parse_projection_bytes(b" " + base)
        with self.assertRaises(Exception):
            P.parse_projection_bytes(base.replace(b"\n", b"\r\n"))

    def test_duplicate_key_rejected(self):
        dup = (
            b'{"occurred_at":"2026-07-18T00:00:00Z","occurred_at":"2026-07-18T00:00:00Z",'
            b'"public_fact_id":"rf_63bd173c61a8cc92071cd4f055e59f90edce537a963ad9582005a0301325c259",'
            b'"public_url":"https://github.com/tropo-ai/tropo/releases/tag/v1.2.3",'
            b'"tag":"v1.2.3","type":"tropo.release.published","version":"1.2.3"}\n'
        )
        with self.assertRaises(Exception):
            P.parse_projection_bytes(dup)


class SchemaRejectionTests(unittest.TestCase):
    def test_valid_golden_accepted(self):
        self.assertEqual(P.validate_projection(GOLDEN), GOLDEN)

    def test_unknown_field_rejected(self):
        bad = dict(GOLDEN)
        bad["extra"] = "x"
        with self.assertRaises(P.ProjectionError):
            P.validate_projection(bad)

    def test_missing_field_rejected(self):
        for field in P.PROJECTION_FIELDS:
            bad = dict(GOLDEN)
            bad.pop(field)
            with self.assertRaises(P.ProjectionError):
                P.validate_projection(bad)

    def test_null_or_nonstring_rejected(self):
        for bad_value in (None, 123, ["v"], {"a": 1}, True):
            bad = dict(GOLDEN)
            bad["version"] = bad_value
            with self.assertRaises(P.ProjectionError):
                P.validate_projection(bad)

    def test_bad_public_fact_id_rejected(self):
        for pfid in (
            "63bd173c61a8cc92071cd4f055e59f90edce537a963ad9582005a0301325c259",  # no rf_
            "rf_XYZ",
            "rf_" + "0" * 63,
            "rf_" + "0" * 65,
            "rf_" + "0" * 63 + "G",
        ):
            with self.assertRaises(P.ProjectionError):
                P.validate_projection(_mutate(public_fact_id=pfid))

    def test_wrong_type_value_rejected(self):
        with self.assertRaises(P.ProjectionError):
            P.validate_projection(_mutate(type="tropo.release.drafted"))

    def test_leading_v_and_build_metadata_version_rejected(self):
        for version in ("v1.2.3", "1.2.3+build.5", "1.2", "1.2.3.4", "01.2.3", ""):
            with self.assertRaises(P.ProjectionError):
                P.validate_projection(_mutate(version=version, tag=f"v{version}"))

    def test_tag_must_equal_v_version(self):
        with self.assertRaises(P.ProjectionError):
            P.validate_projection(_mutate(tag="v1.2.4"))
        with self.assertRaises(P.ProjectionError):
            P.validate_projection(_mutate(tag="1.2.3"))

    def test_public_url_rules(self):
        for url in (
            "https://github.com/tropo-ai/tropo/releases/tag/v1.2.3?x=1",  # query
            "https://github.com/tropo-ai/tropo/releases/tag/v1.2.3#frag",  # fragment
            "http://github.com/tropo-ai/tropo/releases/tag/v1.2.3",  # http
            "https://github.com/tropo-ai/other/releases/tag/v1.2.3",  # wrong repo
            "https://github.com/tropo-ai/tropo/releases/tag/v9.9.9",  # tag mismatch
        ):
            with self.assertRaises(P.ProjectionError):
                P.validate_projection(_mutate(public_url=url))

    def test_occurred_at_must_be_canonical_utc(self):
        for ts in ("2026-07-18", "2026-07-18T00:00:00", "2026-07-18T00:00:00+00:00", "2026-13-01T00:00:00Z"):
            with self.assertRaises(Exception):
                P.validate_projection(_mutate(occurred_at=ts))


class ProjectFromFactTests(unittest.TestCase):
    def test_drops_excluded_fields(self):
        fact = dict(GOLDEN)
        fact.update(
            {
                "remote_main_sha": "a" * 40,
                "verify_live_at": "2026-07-18T00:00:01Z",
                "repository": "tropo-ai/tropo",
                "event_uid": "evt_x",
            }
        )
        projection = P.project_release_fact(fact)
        self.assertEqual(set(projection), P.PROJECTION_FIELDS)
        self.assertEqual(projection, GOLDEN)

    def test_ineligible_fact_missing_tag(self):
        fact = dict(GOLDEN)
        fact.pop("tag")
        with self.assertRaises(P.ProjectionError):
            P.project_release_fact(fact)


class ReceiptIndexTests(unittest.TestCase):
    def _second_projection(self):
        return {
            "occurred_at": "2026-07-01T12:30:00Z",
            "public_fact_id": "rf_" + "a" * 64,
            "public_url": "https://github.com/tropo-ai/tropo/releases/tag/v2.0.0-rc.1",
            "tag": "v2.0.0-rc.1",
            "type": "tropo.release.published",
            "version": "2.0.0-rc.1",
        }
    def test_build_and_validate_index(self):
        index = P.build_receipt_index([GOLDEN, self._second_projection()])
        P.validate_receipt_index(index)
        self.assertEqual(index["schema_version"], "1.0.0")
        entry = index["facts"][GOLDEN["public_fact_id"]]
        self.assertEqual(entry["projection_sha256"], GOLDEN_SHA256)
        self.assertEqual(entry["path"], f"receipts/releases/{GOLDEN_SHA256}.json")
        self.assertEqual(entry["projection_schema"], P.PROJECTION_SCHEMA)

    def test_index_consistency_passes_for_good_tree(self):
        projections = [GOLDEN, self._second_projection()]
        index = P.build_receipt_index(projections)
        tree = {
            P.index_path_for(P.projection_sha256(pr)): P.canonical_projection_bytes(pr)
            for pr in projections
        }
        P.verify_index_against_projections(index, tree)  # no raise

    def test_single_byte_tamper_detected(self):
        index = P.build_receipt_index([GOLDEN])
        good = P.canonical_projection_bytes(GOLDEN)
        tampered = bytearray(good)
        # flip a byte inside the version value (2 -> 3) without changing length
        idx = good.index(b'"version":"1.2.3"') + len('"version":"1.2.')
        tampered[idx] = ord("4")
        tree = {P.index_path_for(P.projection_sha256(GOLDEN)): bytes(tampered)}
        with self.assertRaises(P.ProjectionError):
            P.verify_index_against_projections(index, tree)

    def test_index_unknown_field_rejected(self):
        index = P.build_receipt_index([GOLDEN])
        index["unexpected"] = True
        with self.assertRaises(P.ProjectionError):
            P.validate_receipt_index(index)

    def test_index_entry_path_must_content_address(self):
        index = P.build_receipt_index([GOLDEN])
        entry = index["facts"][GOLDEN["public_fact_id"]]
        entry["path"] = "receipts/releases/deadbeef.json"
        with self.assertRaises(P.ProjectionError):
            P.validate_receipt_index(index)


class SemverNormalizationTests(unittest.TestCase):
    def test_strips_single_leading_v(self):
        self.assertEqual(P.normalize_version("v1.2.3"), "1.2.3")
        self.assertEqual(P.normalize_version("1.2.3"), "1.2.3")

    def test_accepts_prerelease(self):
        self.assertEqual(P.normalize_version("v2.0.0-rc.1"), "2.0.0-rc.1")

    def test_rejects_build_metadata_and_malformed(self):
        for raw in ("1.2.3+build.5", "vv1.2.3", "1.2", "1.2.3.4", "01.2.3", "", "latest"):
            with self.assertRaises(P.ProjectionError):
                P.normalize_version(raw)


if __name__ == "__main__":
    unittest.main()
