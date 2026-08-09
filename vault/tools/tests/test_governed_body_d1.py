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


if __name__ == "__main__":
    unittest.main(verbosity=1)


def check_wildcard_mint_form_is_vocabulary_not_defect():
    """<<MINT:*>> is doc vocabulary (star is unrepresentable in the token grammar).

    Ruled by metis-g105 2026-08-08 after the in-box binary gate; soundness proven by
    talos-t40 (evt 9552). Mutation guard: real tokens and every other malformed
    form must still report."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from lib.template_leg import find_stray_mint_tokens
    assert find_stray_mint_tokens("prose about <<MINT:*>> tokens", "capsule-definition") == []
    assert find_stray_mint_tokens("real <<MINT:uid>> left", "note") == ["<<MINT:uid>>"]
    assert find_stray_mint_tokens("typo <<MINT:Uid>> here", "note")
    assert find_stray_mint_tokens("weird <<MINT:**>> here", "note")

if __name__ == "__main__" and "check_wildcard" in str(globals().get("__doc__","")) is False:
    pass
