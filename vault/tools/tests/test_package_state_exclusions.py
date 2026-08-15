#!/usr/bin/env python3
"""State must not travel in a box. Proven against the package that shipped it.

talos-t40, 2026-08-09, velocity item 8 of the v1.86 retrospective, grounded in
cold-walk findings ae5e743c.

State that travels does not merely leak — it OPERATES. A flag is read by the
machinery that wrote it and means the same thing in the customer's studio as it
did in ours. The v1.86.0 package is used as the fixture on purpose: it is the
artifact that actually carries the defect, so these tests cannot pass on a
tidier hypothetical.
"""

from __future__ import annotations

import importlib.util
import unittest
import unittest.mock
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
SHIPPED_PACKAGE = ROOT / "updates" / "tropo-update-v1.86.0" / "files"

_spec = importlib.util.spec_from_file_location(
    "package_state_exclusions_under_test",
    TOOLS / "lib" / "package_state_exclusions.py",
)
assert _spec and _spec.loader
psx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(psx)


class TheRuleClassifiesStateCorrectly(unittest.TestCase):
    def test_a_leading_dot_slash_does_not_break_matching(self) -> None:
        """`lstrip("./")` strips CHARACTERS, not a prefix.

        The first version of the normaliser used it, so `.tropo/flags/x.flag`
        became `tropo/flags/x.flag` and every rule missed. It was caught on the
        first run of the table below, which is the only reason this is a test
        and not a shipped hole.
        """
        for form in (
            ".tropo/flags/attendant-mode-offered.flag",
            "./.tropo/flags/attendant-mode-offered.flag",
            ".//.tropo/flags/attendant-mode-offered.flag",
        ):
            with self.subTest(form=form):
                self.assertTrue(psx.is_studio_state(form))

    def test_os_content_is_never_state(self) -> None:
        for path in (
            ".tropo/boot-config.md",
            ".tropo/TROPO-CONTROL.md",
            "vault/files/abc12345.md",
            "vault/tools/tropo-validate.py",
            "vault/updates/pending/.gitkeep",
        ):
            with self.subTest(path=path):
                self.assertFalse(psx.is_studio_state(path))

    def test_the_prefix_match_does_not_swallow_a_neighbour(self) -> None:
        """`.tropo/flagship/` is not `.tropo/flags/`.

        The rule is a string prefix, so the trailing slash is load-bearing.
        """
        self.assertFalse(psx.is_studio_state(".tropo/flagship/notaflag.md"))
        self.assertTrue(psx.is_studio_state(".tropo/flags/x.flag"))

    def test_every_exclusion_can_explain_itself(self) -> None:
        """A build that drops a file silently is how state got in unnoticed."""
        for path in sorted(psx.STATE_FILES) + [".tropo/flags/anything.flag"]:
            with self.subTest(path=path):
                reason = psx.why_excluded(path)
                self.assertGreater(len(reason), 30, "a reason must be actionable")
                self.assertNotEqual(reason, "per-studio state", path)


class TheShippedPackageIsTheEvidence(unittest.TestCase):
    """Reads the real v1.86.0 package — the artifact that carries the defect."""

    def setUp(self) -> None:
        if not SHIPPED_PACKAGE.is_dir():
            self.skipTest("v1.86.0 package not present in this tree")

    def _shipped(self) -> list[str]:
        return [
            p.relative_to(SHIPPED_PACKAGE).as_posix()
            for p in SHIPPED_PACKAGE.rglob("*")
            if p.is_file()
        ]

    def test_the_rule_catches_what_v1_86_actually_shipped(self) -> None:
        """The control AND the claim: the defect is real and the rule sees it.

        If this ever finds zero, either the package was fixed (good, and this
        test should then be re-pointed at the new one) or the rule stopped
        working (bad). Asserting a positive count keeps those distinguishable.
        """
        caught = [p for p in self._shipped() if psx.is_studio_state(p)]
        self.assertGreater(
            len(caught),
            20,
            "v1.86.0 shipped 24 flags plus the dev discovery manifest; finding "
            "none means the rule has stopped matching, not that the box is clean",
        )
        self.assertIn(".tropo/flags/attendant-mode-offered.flag", caught)
        self.assertIn(".tropo/flags/attendant-mode-enabled.flag", caught)
        self.assertIn("vault/updates/updates-manifest.json", caught)

    def test_the_consent_flags_are_the_sharp_end(self) -> None:
        """Named separately because these two are not merely untidy.

        `attendant-mode-offered.flag` documents (e9c2a7b3) as "the offer was
        made; do NOT repeat it" — so shipping ours tells a brand-new studio its
        owner already went through onboarding and Po never offers.
        `attendant-mode-enabled.flag` says Attendant Mode is active, which
        transplants a consent decision the customer never made.
        """
        for flag in ("attendant-mode-offered.flag", "attendant-mode-enabled.flag"):
            path = SHIPPED_PACKAGE / ".tropo" / "flags" / flag
            with self.subTest(flag=flag):
                self.assertTrue(path.is_file(), "fixture assumption changed")
                self.assertTrue(psx.is_studio_state(f".tropo/flags/{flag}"))

    def test_the_rule_does_not_condemn_the_os_the_package_carries(self) -> None:
        """A rule that excluded everything would pass the test above trivially."""
        shipped = self._shipped()
        kept = [p for p in shipped if not psx.is_studio_state(p)]
        self.assertGreater(len(kept), 400, "the rule is eating the OS, not the state")
        self.assertIn(".tropo/TROPO-CONTROL.md", kept)


class TheBuildActuallyAppliesTheRule(unittest.TestCase):
    def test_the_kernel_copy_consults_the_exclusion(self) -> None:
        """Wiring check: the rule existing is not the rule running.

        A helper nobody calls is the shape this studio keeps finding — a guard
        that could not fire, a check that stopped checking. Asserts the build's
        kernel walk actually consults it.
        """
        source = (TOOLS / "tropo-build-release.py").read_text(encoding="utf-8")
        self.assertIn("package_state_exclusions.is_studio_state", source)
        self.assertIn("package_state_exclusions", source)

class TheBoxGetsAConcreteUpdateAddress(unittest.TestCase):
    """ae5e743c finding 4: the box shipped no update-source address at all.

    Found on the FIRST customer discovery. The concierge names "the stable
    manifest URL" and no such URL existed in the shipped tree, so the check was
    never testable — and because the surrounding contract is "offline = skip, no
    error state", a MISSING address looked exactly like a down network and the
    gap was swallowed forever.
    """

    def _build_module(self):
        spec = importlib.util.spec_from_file_location(
            "tropo_build_release_under_test", TOOLS / "tropo-build-release.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except SystemExit:
            self.skipTest("build-release refuses to import outside a build context")
        return module

    def test_an_unresolvable_address_refuses_the_build(self) -> None:
        """A refusal, not a warning, and at OUR end rather than the customer's.

        Only we can supply this address, and only at build time. Surfacing it to
        a customer as a configuration gap would move the report away from the
        one person who can act on it.
        """
        build = self._build_module()
        with unittest.mock.patch.object(
            build, "_resolve_update_manifest_url", return_value=None
        ):
            with self.assertRaises(SystemExit) as caught:
                build.step_3g_write_update_source("/tmp/does-not-matter")
        message = str(caught.exception)
        self.assertIn("no update address", message)
        self.assertIn("ae5e743c", message)
        self.assertIn("Do not hand-write a URL", message)

    def test_a_resolved_address_is_written_into_the_box(self) -> None:
        import json
        import tempfile

        build = self._build_module()
        url = "https://example.supabase.co/storage/v1/object/public/releases/updates-manifest.json"
        with tempfile.TemporaryDirectory() as tmp:
            with unittest.mock.patch.object(
                build, "_resolve_update_manifest_url", return_value=url
            ), unittest.mock.patch.object(build, "DRY_RUN", False):
                build.step_3g_write_update_source(tmp)
            written = json.loads(
                (Path(tmp) / ".tropo" / "update-source.json").read_text()
            )
        self.assertEqual(written["manifest_url"], url)
        self.assertIn("CONFIGURATION GAP", written["note"])

    def test_no_fictional_host_is_used_as_an_address(self) -> None:
        """The host that never resolved must not be a VALUE anywhere.

        Checked against string constants that are not docstrings, rather than
        against the raw text. A grep-style check fails on the comment above
        explaining the incident — which is prose a future reader needs, not an
        address anything could dial. The first version of this test did exactly
        that and flagged my own docstring.
        """
        import ast

        tree = ast.parse((TOOLS / "tropo-build-release.py").read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    docstrings.add(doc)
        offenders = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "api.tropo-ai.com" in node.value
            and node.value not in docstrings
        ]
        self.assertEqual(offenders, [], "a fictional host is reachable as a value")

if __name__ == "__main__":
    unittest.main(verbosity=2)
