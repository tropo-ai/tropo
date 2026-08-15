#!/usr/bin/env python3
"""D1 — the covenant hash must be blind to every renderer-owned byte range.

Since the 2026-07-23 File Anatomy v2 retool the renderer strips un-sentineled
Relations/Members tables; `canonicalize_for_content_hash()` stripped only the
sentinel span. Measured in the live customer studio: 78 files carry legacy
Relations renders, so a CLEAN apply would have produced 78 content_hash
mismatches, quarantined the run, and read the customer a covenant-violation
banner for a defect that was entirely ours.

The fix is one shared primitive with two importers, not a second regex.
(Task d220d43b item 1; Argus A145 concurrence, evt 9429.)
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import governed_body as gb  # noqa: E402
from lib import tropo_update_receipt as receipt  # noqa: E402

LEGACY_RELATIONS = """# Title

Owner prose that must survive.

**Relations**

| Relation | Target |
|---|---|
| refs | aaaa1111 |

**Members**

| Type | Children |
|---|---|
| note | bbbb2222 |

Closing owner prose.
"""

AUTHORED_PROSE_CONTROL = """# Title

Owner prose discussing **Relations** in a sentence, and a table the owner
wrote themselves:

| Relation | Target |
|---|---|
| this is | the owner's own table |

Closing owner prose.
"""


def _housekeep(body: str) -> str:
    """What the renderer does: strip retired renders, insert its breadcrumb."""
    out = gb.strip_legacy_renders(body)
    return out.replace(
        "\n\n",
        "\n\n<!-- nav-block:start -->\nVault-Path: x / y\n<!-- nav-block:end -->\n\n",
        1,
    )


class CovenantHashIsBlindToRendererOwnedSpans(unittest.TestCase):
    def test_control_the_fixture_actually_carries_a_legacy_render(self) -> None:
        """Without this the whole suite passes vacuously.

        My first attempt at this test used `| Kind | Target |` and the finder
        never matched, so the hashes agreed because nothing was stripped. A
        plant that does not reach the branch measures nothing.
        """
        self.assertIsNotNone(
            gb.find_relations_block(LEGACY_RELATIONS),
            "fixture does not match the real legacy shape the renderer strips")

    def test_housekeeping_a_legacy_render_leaves_the_content_hash_identical(self) -> None:
        before = LEGACY_RELATIONS
        after = _housekeep(before)
        self.assertNotEqual(before, after, "control: housekeeping must change the bytes")
        self.assertEqual(
            receipt.content_hash(before), receipt.content_hash(after),
            "a clean apply reported a covenant violation for the studio's own "
            "renderer housekeeping — this is the 78-file customer defect")

    def test_the_byte_hash_still_discloses_the_renderer_write(self) -> None:
        """Blind is not silent. The owner must still see that we wrote."""
        before = LEGACY_RELATIONS
        after = _housekeep(before)
        self.assertNotEqual(
            receipt.byte_hash(before), receipt.byte_hash(after),
            "the renderer's write must remain honestly disclosed")

    def test_owner_words_survive_canonicalization(self) -> None:
        canonical = receipt.canonicalize_for_content_hash(LEGACY_RELATIONS)
        self.assertIn("Owner prose that must survive.", canonical)
        self.assertIn("Closing owner prose.", canonical)

    def test_an_authored_table_is_not_treated_as_renderer_chrome(self) -> None:
        """The other direction, and the one that would be a real violation.

        If canonicalization ate the owner's own table, a genuine edit to it
        would hash identical and the covenant would go quiet exactly when it
        should speak.
        """
        canonical = receipt.canonicalize_for_content_hash(AUTHORED_PROSE_CONTROL)
        self.assertIn("the owner's own table", canonical)
        edited = AUTHORED_PROSE_CONTROL.replace("the owner's own table", "EDITED BY US")
        self.assertNotEqual(
            receipt.content_hash(AUTHORED_PROSE_CONTROL), receipt.content_hash(edited),
            "an edit to the owner's own words must still change the content hash")

    def test_one_definition_not_two(self) -> None:
        """The structural half: the receipt module must not carry its own regex.

        A copy would pass every test above on the day it was written and drift
        the first time the renderer learned a new shape — which is exactly how
        this defect was born.
        """
        source = (TOOLS / "lib" / "tropo_update_receipt.py").read_text(encoding="utf-8")
        self.assertIn("governed_body.strip_legacy_renders", source)
        self.assertNotIn(
            "find_relations_block(", source.split("import")[-1],
            "the receipt module re-implements the finder instead of importing it")

    def test_mutation_sentinel_only_canonicalization_reproduces_the_defect(self) -> None:
        """The governing proof: revert the fix and the customer defect returns."""
        before = LEGACY_RELATIONS
        after = _housekeep(before)
        sentinel_only = lambda t: hashlib.sha256(
            gb._NAV_BLOCK_RE.sub("", t).encode("utf-8")).hexdigest()
        self.assertNotEqual(
            sentinel_only(before), sentinel_only(after),
            "sentinel-only canonicalization no longer reproduces the false "
            "violation — this test has stopped discriminating the fix")


class WildcardMintFormIsVocabularyNotDefect(unittest.TestCase):
    """`<<MINT:*>>` is documentation convention and can never be a real token.

    Ruled by metis-g105 2026-08-08 after the in-box binary gate left the two
    wildcard mentions (38c63381, de5181b0) as the sole remaining reds; the
    grammar proof is talos-t40's (evt 9552) — `MINT_TOKEN_RE` admits only
    `[a-z_]+`, so a star can never name a substitution the minter would fill.

    REWRITTEN AS A REAL TEST BY talos-t40, 2026-08-09. These four assertions
    shipped as a module-level `check_wildcard_...()` function that nothing ever
    called, guarded by
    `if __name__ == "__main__" and "check_wildcard" in str(...) is False:` whose
    body was `pass`. Three independent reasons it could not fire: Python chains
    that comparison into `(x in s) and (s is False)`, and a str is never False,
    so the condition is a constant False; the body called nothing even if it
    ran; and `unittest.main()` sits above it and exits the process, so the
    function was never even defined during a script run.

    The suppression itself was correct — all four claims verified by hand before
    this rewrite, so nothing shipped broken. What was missing is the only thing
    that keeps it correct tomorrow. Guards that cannot fire are the shape this
    file already exists to fight: its own
    `test_mutation_sentinel_only_canonicalization_reproduces_the_defect` is
    there because a green test that never reaches its branch measures nothing.
    """

    def setUp(self) -> None:
        from lib.template_leg import find_stray_mint_tokens

        self.scan = find_stray_mint_tokens

    def test_the_wildcard_form_is_not_reported(self) -> None:
        self.assertEqual(
            self.scan("prose about <<MINT:*>> tokens", "capsule-definition"), []
        )

    def test_a_real_token_still_reports(self) -> None:
        self.assertEqual(self.scan("real <<MINT:uid>> left", "note"), ["<<MINT:uid>>"])

    def test_a_typo_form_still_reports(self) -> None:
        """Uppercase is outside the grammar, so it is a malformed token, not vocabulary."""
        self.assertTrue(self.scan("typo <<MINT:Uid>> here", "note"))

    def test_a_double_star_still_reports(self) -> None:
        """The suppression is the exact form and nothing adjacent to it."""
        self.assertTrue(self.scan("weird <<MINT:**>> here", "note"))

    def test_the_suppression_is_type_independent_and_that_is_deliberate(self) -> None:
        """Not scoped to capsule-definition, unlike the template-leg exclusion.

        Recorded because the two behaviours sit in the same function and the
        difference is easy to read as an oversight. It is not: the template-leg
        exclusion suppresses tokens that ARE well-formed, so it must be scoped
        to the type entitled to carry them. A star is unrepresentable in the
        grammar for every type, so no scope buys anything.
        """
        for entry_type in ("note", "task", "capsule-definition", None):
            with self.subTest(entry_type=entry_type):
                self.assertEqual(self.scan("about <<MINT:*>> tokens", entry_type), [])

    def test_mutation_removing_the_suppression_reddens_the_first_test(self) -> None:
        """Teeth, run rather than asserted.

        Re-implements the scan with the one `if form != "<<MINT:*>>"` guard
        removed and asserts the wildcard comes back. If this ever passes, the
        suppression is no longer what makes the first test green.
        """
        from lib import template_leg as tl

        text = "prose about <<MINT:*>> tokens"
        scannable = tl.scannable_instance_text(text, "capsule-definition")
        unsuppressed: list[str] = []
        cursor = 0
        while True:
            start = scannable.find(tl.MINT_TOKEN_OPEN, cursor)
            if start == -1:
                break
            match = tl.MINT_TOKEN_RE.match(scannable, start)
            if match is not None:
                unsuppressed.append(match.group(0))
                cursor = match.end()
                continue
            end = scannable.find(">>", start)
            end = end + 2 if end != -1 else len(scannable)
            unsuppressed.append(scannable[start:end])
            cursor = max(end, start + len(tl.MINT_TOKEN_OPEN))
        self.assertEqual(unsuppressed, ["<<MINT:*>>"])
        self.assertEqual(self.scan(text, "capsule-definition"), [])

    def test_the_grammar_claim_the_suppression_rests_on(self) -> None:
        """The whole argument is that a star cannot name a substitution."""
        from lib import template_leg as tl

        self.assertIsNone(tl.MINT_TOKEN_RE.fullmatch("<<MINT:*>>"))
        self.assertIsNotNone(tl.MINT_TOKEN_RE.fullmatch("<<MINT:uid>>"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
