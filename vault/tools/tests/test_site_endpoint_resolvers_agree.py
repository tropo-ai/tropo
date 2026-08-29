#!/usr/bin/env python3
"""The two site-endpoint resolvers must name the same URL, and it must be the
declared one.

THE DEFECT THIS GUARDS. Every release fire probed
`https://tropo-ai.com/os-release.json` and got a 404, so `site_endpoint` went
unobserved and the completion saga could not close. The badge was never broken:
tropo-app is a Next.js app serving it from `app/api/os-release/route.ts`, which
reads `os-release.json` from the repo root at request time. Next serves static
files only out of `public/`, and the badge is not there — so no URL ever exposed
that filename, and one was being probed anyway.

The URL was DERIVED (`f"https://tropo-ai.com/{Path(OS_RELEASE_REL).name}"`) in
tropo-publish-release.py while `lib/release_site.SITE_ENDPOINT` carried the
correct value in a module that file already imports, and while
tropo-verify-release-live.py already fell back to that constant. One fact, two
resolvers, and the deriving one ran during the fire.

Verified live 2026-08-26: /api/os-release -> 200 {"version":"v1.92.0",…};
/os-release.json -> 404.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = STUDIO_ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.release_site import SITE_ENDPOINT  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "tropo_publish_release_under_test", TOOLS / "tropo-publish-release.py")
publisher = importlib.util.module_from_spec(_spec)
sys.modules["tropo_publish_release_under_test"] = publisher
_spec.loader.exec_module(publisher)

_vspec = importlib.util.spec_from_file_location(
    "tropo_verify_release_live_under_test", TOOLS / "tropo-verify-release-live.py")
verifier = importlib.util.module_from_spec(_vspec)
sys.modules["tropo_verify_release_live_under_test"] = verifier
_vspec.loader.exec_module(verifier)


class SiteEndpointResolvers(unittest.TestCase):

    def setUp(self):
        self._saved = os.environ.pop("TROPO_SITE_ENDPOINT_URL", None)
        if self._saved is not None:
            self.addCleanup(os.environ.__setitem__,
                            "TROPO_SITE_ENDPOINT_URL", self._saved)

    def test_publisher_default_is_the_declared_endpoint(self):
        self.assertEqual(publisher._site_endpoint_url({}), SITE_ENDPOINT)

    def test_publisher_default_is_not_derived_from_the_badge_filename(self):
        """The specific defect, named. `os-release.json` is a file on disk that
        the route reads; it is not a path the site serves."""
        self.assertNotIn("os-release.json", publisher._site_endpoint_url({}))

    def test_both_tools_name_the_same_url(self):
        """One fact, one source. The verifier's fallback and the publisher's
        default disagreeing is what made the fire probe a URL that never was."""
        self.assertEqual(publisher._site_endpoint_url({}),
                         verifier._site_route_fallback())

    def test_the_declared_endpoint_is_the_api_route_the_site_source_serves(self):
        self.assertTrue(SITE_ENDPOINT.endswith("/api/os-release"), SITE_ENDPOINT)

    # --- the inputs that must still win over the default ---

    def test_staged_state_wins(self):
        self.assertEqual(
            publisher._site_endpoint_url({"site_endpoint_url": "https://example.test/x"}),
            "https://example.test/x")

    def test_environment_wins_over_the_default(self):
        os.environ["TROPO_SITE_ENDPOINT_URL"] = "https://example.test/env"
        self.addCleanup(os.environ.pop, "TROPO_SITE_ENDPOINT_URL", None)
        self.assertEqual(publisher._site_endpoint_url({}), "https://example.test/env")


if __name__ == "__main__":
    unittest.main()
