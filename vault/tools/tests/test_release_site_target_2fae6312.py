#!/usr/bin/env python3
"""The site is a second repository, and it is treated like one.

Dev-spec 2fae6312 step 7. Nothing here touches a network or a real remote —
the git and HTTP edges are injected, so these cases exercise the decisions
rather than the plumbing. The decisions are where the release can go wrong
quietly: the wrong repository, a token in a committed journal, an unrelated
path riding along, a force push over someone else's work, or a stale badge
reported as live.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = STUDIO_ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.release_site import (  # noqa: E402
    BADGE_TARGET,
    ENDPOINT_FIELDS,
    PENDING_STATE,
    REFUSAL_CONFLICT,
    REFUSAL_CREDENTIAL,
    REFUSAL_DIFF,
    REFUSAL_ENDPOINT,
    REFUSAL_IDENTITY,
    ROUTE_TARGET,
    SITE_BRANCH,
    SITE_ENDPOINT,
    SITE_REMOTE,
    SITE_REPO,
    SOURCE_MAP,
    ReleaseSiteError,
    assert_pinned_identity,
    classify_diff,
    decide_site_push,
    sanitize_remote_url,
    verify_endpoint,
)

PARENT = "a" * 40
PREPARED = "b" * 40
STRANGER = "c" * 40


class PinnedIdentityTests(unittest.TestCase):
    def test_the_target_is_pinned_to_the_spec(self):
        self.assertEqual(SITE_REPO, "https://github.com/tropo-ai/tropo-app.git")
        self.assertEqual(SITE_BRANCH, "main")
        self.assertEqual(SITE_REMOTE, "app-deploy")
        self.assertEqual(SITE_ENDPOINT, "https://tropo-ai.com/api/os-release")

    def test_the_pinned_remote_verifies(self):
        self.assertTrue(assert_pinned_identity(SITE_REPO).ok)

    def test_another_repository_refuses(self):
        verdict = assert_pinned_identity("https://github.com/someone/else.git")
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.refusal_class, REFUSAL_IDENTITY)

    def test_a_redirect_refuses_rather_than_being_followed(self):
        verdict = assert_pinned_identity(
            SITE_REPO, redirected_to="https://github.com/tropo-ai/tropo-app-old.git"
        )
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.refusal_class, REFUSAL_IDENTITY)
        self.assertIn("redirect", verdict.detail)

    def test_another_branch_refuses(self):
        verdict = assert_pinned_identity(SITE_REPO, observed_branch="staging")
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.refusal_class, REFUSAL_IDENTITY)

    def test_a_failed_identity_names_the_pending_state(self):
        self.assertEqual(
            assert_pinned_identity("https://github.com/x/y.git").pending_state,
            PENDING_STATE,
        )


class CredentialTests(unittest.TestCase):
    """A journal is committed substrate; a token in one cannot be recalled."""

    def test_userinfo_is_stripped(self):
        self.assertEqual(
            sanitize_remote_url("https://user:ghp_secret@github.com/tropo-ai/tropo-app.git"),
            SITE_REPO,
        )

    def test_a_credential_bearing_url_refuses(self):
        verdict = assert_pinned_identity(
            "https://user:ghp_secret@github.com/tropo-ai/tropo-app.git"
        )
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.refusal_class, REFUSAL_CREDENTIAL)

    def test_the_refusal_evidence_carries_no_secret(self):
        verdict = assert_pinned_identity(
            "https://user:ghp_secret@github.com/tropo-ai/tropo-app.git"
        )
        blob = repr(verdict.evidence) + verdict.detail
        self.assertNotIn("ghp_secret", blob)
        self.assertNotIn("user:", blob)

    def test_a_token_only_url_is_also_sanitised(self):
        self.assertEqual(
            sanitize_remote_url("https://ghp_tokenonly@github.com/tropo-ai/tropo-app.git"),
            SITE_REPO,
        )

    def test_a_port_survives_sanitisation(self):
        self.assertEqual(
            sanitize_remote_url("https://u:p@example.com:8443/a/b.git"),
            "https://example.com:8443/a/b.git",
        )

    def test_an_ssh_shorthand_is_returned_unchanged_not_pretend_sanitised(self):
        shorthand = "git@github.com:tropo-ai/tropo-app.git"
        self.assertEqual(sanitize_remote_url(shorthand), shorthand)

    def test_an_empty_url_is_misuse(self):
        with self.assertRaises(ReleaseSiteError):
            sanitize_remote_url("")


class DiffBoundaryTests(unittest.TestCase):
    def test_the_source_map_is_the_two_declared_paths(self):
        self.assertEqual(
            SOURCE_MAP,
            {
                "tropo-app/os-release.json": "os-release.json",
                "tropo-app/app/api/os-release/route.ts": "app/api/os-release/route.ts",
            },
        )

    def test_badge_only_is_allowed_once_the_route_exists(self):
        verdict = classify_diff([BADGE_TARGET], route_exists=True)
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.action, "badge-only")

    def test_first_rollout_may_add_the_route(self):
        verdict = classify_diff([BADGE_TARGET, ROUTE_TARGET], route_exists=False)
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.action, "first-rollout")

    def test_the_route_may_not_change_again_after_rollout(self):
        verdict = classify_diff([BADGE_TARGET, ROUTE_TARGET], route_exists=True)
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.refusal_class, REFUSAL_DIFF)
        self.assertIn("first rollout", verdict.detail)

    def test_an_unrelated_path_refuses(self):
        verdict = classify_diff([BADGE_TARGET, "app/page.tsx"], route_exists=True)
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.refusal_class, REFUSAL_DIFF)
        self.assertIn("app/page.tsx", verdict.detail)

    def test_a_commit_that_skips_the_badge_refuses(self):
        verdict = classify_diff([ROUTE_TARGET], route_exists=False)
        self.assertFalse(verdict.ok)
        self.assertIn("does not update", verdict.detail)

    def test_an_empty_diff_refuses(self):
        self.assertFalse(classify_diff([], route_exists=True).ok)


class CompareAndSwapTests(unittest.TestCase):
    """Three outcomes and no fourth. Force is not one of them."""

    def test_the_expected_parent_fast_forwards(self):
        verdict = decide_site_push(
            remote_sha=PARENT, expected_parent=PARENT, prepared_commit=PREPARED
        )
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.action, "fast-forward-cas")

    def test_an_already_pushed_commit_is_a_no_op(self):
        verdict = decide_site_push(
            remote_sha=PREPARED, expected_parent=PARENT, prepared_commit=PREPARED
        )
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.action, "no-op")

    def test_a_moved_remote_conflicts_and_is_never_forced(self):
        verdict = decide_site_push(
            remote_sha=STRANGER, expected_parent=PARENT, prepared_commit=PREPARED
        )
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.refusal_class, REFUSAL_CONFLICT)
        self.assertIn("would delete their work", verdict.detail)

    def test_no_outcome_offers_a_force(self):
        for remote in (PARENT, PREPARED, STRANGER):
            verdict = decide_site_push(
                remote_sha=remote, expected_parent=PARENT, prepared_commit=PREPARED
            )
            with self.subTest(remote=remote[:4]):
                self.assertNotIn("force", verdict.action)

    def test_a_malformed_sha_is_misuse(self):
        with self.assertRaises(ReleaseSiteError):
            decide_site_push(
                remote_sha="not-a-sha", expected_parent=PARENT, prepared_commit=PREPARED
            )


class EndpointVerificationTests(unittest.TestCase):
    def response(self, **overrides):
        payload = {
            "status": 200,
            "final_url": SITE_ENDPOINT + "?cb=12345",
            "content_type": "application/json; charset=utf-8",
            "headers": {"cache-control": "no-store, max-age=0"},
            "body": {
                "version": "v1.89.0",
                "fileSize": "6.3 MB",
                "sizeBytes": 6580452,
                "releasedAt": "2026-08-16",
            },
            "body_sha256": "d" * 64,
            "observed_at": "2026-08-16T22:40:00Z",
        }
        payload.update(overrides)
        return payload

    def verify(self, **overrides):
        return verify_endpoint(
            self.response(**overrides),
            expected_version="v1.89.0",
            expected_size_bytes=6580452,
        )

    def test_a_correct_badge_verifies(self):
        verdict = self.verify()
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.action, "endpoint-verified")
        self.assertIn("observed endpoint equality", verdict.detail)

    def test_a_non_200_refuses(self):
        self.assertEqual(self.verify(status=503).refusal_class, REFUSAL_ENDPOINT)

    def test_a_redirect_refuses(self):
        verdict = self.verify(final_url="https://www.tropo-ai.com/api/os-release")
        self.assertFalse(verdict.ok)
        self.assertIn("redirected", verdict.detail)

    def test_a_non_json_content_type_refuses(self):
        self.assertFalse(self.verify(content_type="text/html").ok)

    def test_a_cacheable_response_refuses(self):
        verdict = self.verify(headers={"cache-control": "public, max-age=3600"})
        self.assertFalse(verdict.ok)
        self.assertIn("stale", verdict.detail)

    def test_an_extra_field_refuses(self):
        body = self.response()["body"]
        body["schema"] = "tropo.os-release/v1"
        verdict = self.verify(body=body)
        self.assertFalse(verdict.ok)
        self.assertIn("schema", verdict.detail)

    def test_a_missing_field_refuses(self):
        body = self.response()["body"]
        del body["releasedAt"]
        self.assertFalse(self.verify(body=body).ok)

    def test_a_stale_version_refuses(self):
        body = self.response()["body"]
        body["version"] = "v1.88.0"
        verdict = self.verify(body=body)
        self.assertFalse(verdict.ok)
        self.assertIn("stale", verdict.detail)

    def test_a_size_mismatch_refuses(self):
        body = self.response()["body"]
        body["sizeBytes"] = 999
        self.assertFalse(self.verify(body=body).ok)

    def test_every_failure_names_the_pending_state(self):
        self.assertEqual(self.verify(status=500).pending_state, PENDING_STATE)


class RouteContractTests(unittest.TestCase):
    """The served route must agree with what the verifier requires."""

    ROUTE = STUDIO_ROOT / "tropo-app" / "app" / "api" / "os-release" / "route.ts"

    def test_the_route_exists_where_the_spec_maps_it(self):
        self.assertTrue(self.ROUTE.is_file(), str(self.ROUTE))
        self.assertEqual(
            SOURCE_MAP["tropo-app/app/api/os-release/route.ts"],
            "app/api/os-release/route.ts",
        )

    def test_the_route_serves_exactly_the_four_fields(self):
        text = self.ROUTE.read_text(encoding="utf-8")
        declared = re.search(r"SERVED_FIELDS\s*=\s*\[(.*?)\]", text, re.S)
        self.assertIsNotNone(declared, "the route declares no served field list")
        fields = re.findall(r'"(\w+)"', declared.group(1))
        self.assertEqual(sorted(fields), sorted(ENDPOINT_FIELDS))

    def test_the_route_does_not_serve_the_files_schema_key(self):
        """os-release.json has a fifth key; serving it would fail the verifier."""
        badge = STUDIO_ROOT / "tropo-app" / "os-release.json"
        import json

        self.assertIn("schema", json.loads(badge.read_text(encoding="utf-8")))
        text = self.ROUTE.read_text(encoding="utf-8")
        self.assertNotIn("...parsed", text, "a spread would leak new keys into the response")

    def test_the_route_declares_a_no_store_policy(self):
        text = self.ROUTE.read_text(encoding="utf-8")
        self.assertIn("no-store", text)
        self.assertIn("revalidate = 0", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
