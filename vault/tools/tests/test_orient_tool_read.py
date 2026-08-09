#!/usr/bin/env python3
"""The reading stage of ``vault/tools/tropo-orient.py`` — the surface, not the
engine.

WHAT IS UNDER TEST HERE, AND WHAT IS NOT
----------------------------------------
Stage C's own contract lives in ``test_orient_stage_c``. This file covers the
three things the TOOL is responsible for, all of which are about what a person
sees and what a person is charged:

  1. **Degraded is the normal shape.** Most runs read some of the circle and
     not the rest, and every survivor that was not read is a FIELD in the
     block with a named reason — never a number the renderer computes and
     never a sentence a reader can skim past. A run that can read nothing must
     say so in those words, and must never let the citation list stand under a
     heading that implies it was read: a list of documents under a confident
     heading is indistinguishable from a distilled answer.
  2. **Egress is its own classification.** ``extraction_scope`` answers "may
     this go on the website". Whether a document may cross to a model provider
     is a different question, and the tool must not answer one with the other
     in either direction — agent-authored governed content is eligible
     whatever its publishing label, and an imported artifact is not, whatever
     its publishing label.
  3. **Spending is opt-in and stated.** Without ``--read`` there is no edge,
     no reservation and no read block at all. With it, the block says what the
     run cost even when the answer is that it cost nothing.

THE FIXTURE IS A WHOLE STUDIO
-----------------------------
Governed files on disk, both index projections, and a spend ledger — because
the classifier reads frontmatter off disk, the naming reads the archive
projection, and "nothing was spent" is only a claim worth making if there is a
ledger that could have changed.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import socket
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent.parent
ROOT = TOOLS.parent.parent
for candidate in (str(TOOLS), str(TOOLS / "lib"), str(ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from lib import index_surfaces, span_guard  # noqa: E402
from lib import viewer_projection as vp  # noqa: E402

_SOCKET_PATCHERS = (
    mock.patch.object(
        socket, "create_connection",
        side_effect=AssertionError("network forbidden by test guard"),
    ),
    mock.patch.object(
        socket.socket, "connect",
        side_effect=AssertionError("network forbidden by test guard"),
    ),
)


def setUpModule() -> None:
    for patcher in _SOCKET_PATCHERS:
        patcher.start()


def tearDownModule() -> None:
    for patcher in _SOCKET_PATCHERS:
        patcher.stop()


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "orient_tool_under_test", TOOLS / "tropo-orient.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = load_tool()


# --------------------------------------------------------------------------- #
# Fixture                                                                       #
# --------------------------------------------------------------------------- #

#: Four documents, one per origin story the classifier has to tell apart.
#: ``ours`` carries the publishing label that used to make it ineligible; the
#: three imports each carry ONE of the marks and nothing else, so no test can
#: pass because a sibling mark happened to be there too.
FIXTURE = {
    "aa000001": {
        "frontmatter": (
            "uid: aa000001\ntitle: What the studio wrote\ntype: note\n"
            "status: active\nextraction_scope: argo-reference\n"
        ),
        "body": "The studio wrote this sentence. It is ours to send.\n",
    },
    "bb000002": {
        "frontmatter": (
            "uid: bb000002\ntitle: A deck that came from outside\n"
            "type: external-artifact\nstatus: active\n"
            "extraction_scope: argo-reference\n"
        ),
        "body": "Somebody outside the studio wrote this deck.\n",
    },
    "cc000003": {
        "frontmatter": (
            "uid: cc000003\ntitle: A file with an outside publishing label\n"
            "type: note\nstatus: active\nextraction_scope: external\n"
        ),
        "body": "This one is labelled external for publishing.\n",
    },
    "dd000004": {
        "frontmatter": (
            "uid: dd000004\ntitle: A file the walker carried in\ntype: note\n"
            "status: active\nextraction_scope: argo-reference\n"
            "source_hash: 9f2c1b7ae4d0\n"
        ),
        "body": "The import walker stamped a provenance digest on this.\n",
    },
    "ee000005": {
        "frontmatter": (
            "uid: ee000005\ntitle: A finished piece of work\ntype: note\n"
            "status: closed\nstate: archived\n"
            "extraction_scope: argo-reference\n"
        ),
        "body": "This one is archived and still perfectly readable.\n",
    },
}


class StudioFixture:
    """A vault the tool can be pointed at: files, both projections, a ledger."""

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="orient-tool-")).resolve()
        (self.root / ".tropo").mkdir()
        (self.root / "vault" / "files").mkdir(parents=True)
        (self.root / "vault" / "loop-runs" / ".model-spend").mkdir(parents=True)
        current, archive = [], []
        for uid, spec in FIXTURE.items():
            (self.root / "vault" / "files" / f"{uid}.md").write_text(
                f"---\n{spec['frontmatter']}---\n{spec['body']}"
            )
            record = {
                "uid": uid,
                "path": f"vault/files/{uid}.md",
                **{
                    key.strip(): value.strip()
                    for key, value in (
                        line.split(":", 1)
                        for line in spec["frontmatter"].strip().splitlines()
                    )
                },
            }
            (archive if index_surfaces.is_archive_record(record)
             else current).append(record)
        self._write("00-index.jsonl", current)
        self._write("00-archive-index.jsonl", archive)

    def _write(self, name: str, rows: list) -> None:
        (self.root / "vault" / name).write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
        )

    def add(self, uid: str, frontmatter: str, body: str = "A body.\n") -> str:
        """One more governed file on disk and in no index projection."""
        (self.root / "vault" / "files" / f"{uid}.md").write_text(
            f"---\nuid: {uid}\ntitle: An extra file\ntype: note\n"
            f"{frontmatter}---\n{body}"
        )
        return uid

    def files(self) -> dict:
        return {
            path.name: path.read_bytes()
            for path in sorted((self.root / "vault" / "files").glob("*.md"))
        }

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def item(uid: str, title: str = "") -> dict:
    """One ranked survivor in the shape ``orient`` builds them."""
    return {"uid": uid, "title": title or f"{uid} — not in the index"}


@dataclass(frozen=True)
class _Member:
    uid: str


@dataclass(frozen=True)
class _Circle:
    members: tuple


@dataclass(frozen=True)
class _Deterministic:
    """Stage A+B's output in the only shape the tool reads off it.

    ``read_block`` takes the deterministic orientation whole and uses exactly
    one thing from it — the circle's member uids, which Stage C carries into
    the block. Standing that in is not a shortcut around the composition: the
    real ``DeterministicOrientation`` is built from a SQLite index over the
    real vault and is exercised where it belongs, in the live run and in
    ``test_distiller_orient``. What is under test here is the surface.
    """

    circle: _Circle


def circle_of(*uids: str) -> _Deterministic:
    return _Deterministic(circle=_Circle(members=tuple(_Member(u) for u in uids)))


class ToolCase(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = StudioFixture()
        self.addCleanup(self.fx.close)
        patchers = [
            mock.patch.object(tool, "ROOT", self.fx.root),
            mock.patch.object(tool, "FILES", self.fx.root / "vault" / "files"),
            mock.patch.object(
                tool, "INDEX_JSONL", self.fx.root / "vault" / "00-index.jsonl"
            ),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.records = tool._all_records()


# --------------------------------------------------------------------------- #
# Ruling 2 — egress is its own classification                                   #
# --------------------------------------------------------------------------- #


class EgressClassificationTests(ToolCase):
    def test_agent_authored_governed_content_is_eligible(self):
        """Including the publishing label that used to make it ineligible.

        ``argo-reference`` means "not for the website". It says nothing about
        a model, and every word of the file was written by one.
        """
        self.assertEqual(
            self.records["aa000001"]["extraction_scope"], "argo-reference"
        )
        self.assertEqual(
            tool.egress_class("aa000001", self.records), vp.OS_SEGMENT
        )

    def test_each_mark_of_an_outside_origin_carves_out_on_its_own(self):
        """Three marks, one per fixture, and none of the fixtures carries two.

        Any one of them can be edited away, so the carve-out cannot rest on
        their conjunction — and a test where every import carried every mark
        would pass with two of the three checks deleted.
        """
        marks = {
            "bb000002": ("type", "external-artifact"),
            "cc000003": ("extraction_scope", "external"),
            "dd000004": ("source_hash", "9f2c1b7ae4d0"),
        }
        for uid, (field, value) in marks.items():
            with self.subTest(mark=field):
                record = self.records[uid]
                # CONTROL: this uid must carry THIS mark and no other.
                self.assertEqual(record.get(field), value)
                others = [
                    other for other, (name, _) in marks.items() if name != field
                ]
                for other in others:
                    name = marks[other][0]
                    self.assertNotEqual(
                        record.get(name), marks[other][1],
                        f"{uid} also carries {name}, so this subtest does not "
                        f"isolate {field}",
                    )
                self.assertEqual(tool.egress_class(uid, self.records), "private")

    def test_the_provenance_stamp_is_read_off_disk_without_an_index_row(self):
        """A governed file with no index row still has an origin.

        This is the case the old rule got wrong in the other direction: it
        refused everything unindexed. The file is on disk and so is its
        frontmatter, so the question is answerable.
        """
        self.assertEqual(tool.egress_class("dd000004", {}), "private")
        self.assertEqual(tool.egress_class("aa000001", {}), vp.OS_SEGMENT)

    def test_the_publishing_answer_does_not_move_the_egress_answer(self):
        """Every publishing label in use, and one answer across all of them.

        ``argo-reference`` is the label that made 2,400 agent-authored records
        ineligible, and it is only one of the values the vault uses. If egress
        were still reading the publishing question, the answer would move as
        these move. It must not — the sole value that changes anything is
        ``external``, which is not a publishing judgement at all but the
        importer's record of where the bytes came from.
        """
        for n, scope in enumerate(
            ("argo-reference", "public", "internal", "tropo-os", "")
        ):
            with self.subTest(scope=scope or "(absent)"):
                uid = self.fx.add(
                    f"1000000{n}",
                    f"extraction_scope: {scope}\n" if scope else "",
                )
                # CONTROL: the label really is on the file being classified,
                # so a fixture that silently wrote the same file five times
                # fails here rather than passing five times.
                self.assertEqual(self._scope_of(uid), scope)
                self.assertEqual(tool.egress_class(uid, {}), vp.OS_SEGMENT)
        moved = self.fx.add("20000000", "extraction_scope: external\n")
        self.assertEqual(tool.egress_class(moved, {}), "private")

    def _scope_of(self, uid: str) -> str:
        for line in (
            self.fx.root / "vault" / "files" / f"{uid}.md"
        ).read_text().splitlines():
            if line.startswith("extraction_scope:"):
                return line.split(":", 1)[1].strip()
        return ""

    def test_a_uid_with_no_governed_body_is_not_offered_to_the_edge(self):
        self.assertEqual(tool.egress_class("ffffffff", self.records), "private")


# --------------------------------------------------------------------------- #
# Ruling 1 — the dropped are structure, and nothing is dressed up as an answer  #
# --------------------------------------------------------------------------- #


class DegradedBlockTests(ToolCase):
    def test_every_drop_carries_a_named_reason_and_a_name(self):
        items = [item(uid) for uid in
                 ("aa000001", "bb000002", "cc000003", "dd000004", "ffffffff")]
        uids, dropped = tool._read_set(items, self.records)

        self.assertEqual(uids, ["aa000001"])
        self.assertEqual(
            {entry["uid"]: entry["reason"] for entry in dropped},
            {
                "bb000002": tool.DROP_IMPORTED,
                "cc000003": tool.DROP_IMPORTED,
                "dd000004": tool.DROP_IMPORTED,
                "ffffffff": tool.DROP_UNGOVERNED,
            },
        )
        for entry in dropped:
            with self.subTest(uid=entry["uid"]):
                self.assertIn(entry["reason"], tool._DROP_SENTENCE)
                # The register rule: name the thing, then cite it. A title
                # that is the uid is the habit this tool exists to break.
                self.assertNotIn(entry["uid"], entry["title"])

        # Every entry that HAS a path cites it, and the one that does not is
        # not given an invented one — "vault/files/ffffffff.md — this is not
        # a governed body" names a file in order to say the file is absent.
        cited = {entry["uid"]: entry["where"] for entry in dropped}
        self.assertEqual(cited["bb000002"], "vault/files/bb000002.md")
        self.assertEqual(cited["ffffffff"], "")
        rendered = "\n".join(tool._read_lines(
            {**self._block(dropped=dropped), "considered": 5}
        ))
        self.assertNotIn("vault/files/ffffffff.md", rendered)
        self.assertIn(tool._DROP_SENTENCE[tool.DROP_UNGOVERNED], rendered)
        self.assertNotIn("vault/files/ffffffff.md", tool._board_read(
            {**self._block(dropped=dropped), "considered": 5}
        ))

    def test_the_batch_bound_is_stage_cs_k_and_is_not_tuned_up(self):
        self.assertEqual(tool.K_READ, tool.stage_c.K_SURVIVORS)
        many = [item("aa000001") for _ in range(tool.K_READ + 3)]
        uids, dropped = tool._read_set(many, self.records)
        self.assertEqual(len(uids), tool.K_READ)
        self.assertEqual(
            [entry["reason"] for entry in dropped],
            [tool.DROP_BATCH] * 3,
        )

    def test_a_zero_eligible_run_says_so_and_reaches_no_edge(self):
        edge = tool.MeteredEdge(
            studio_root=self.fx.root,
            provider_call=mock.Mock(side_effect=AssertionError("edge reached")),
        )
        block = tool.read_block(
            "aa000001", "A task", [item("bb000002"), item("ffffffff")],
            vp.Viewer(principal_uid="7b921d17"), None, tool.INDEX_AS_OF, edge,
        )
        self.assertEqual(block["status"], "nothing-eligible")
        self.assertEqual(block["read"], [])
        self.assertEqual(block["dropped_count"], 2)
        self.assertEqual(block["spend"]["calls"], [])

        text = "\n".join(tool._read_lines(block))
        self.assertIn("NOTHING HERE WAS READ", text)
        self.assertIn("No survivor was eligible to be read", text)
        self.assertIn("it is not an answer", text)
        board = tool._board_read(block)
        self.assertIn("nothing here was read", board)
        self.assertIn("No survivor was eligible to be read", board)

    def test_the_renderers_are_driven_by_the_list_and_not_by_a_count(self):
        """A dropped document that vanishes from the roster while the number
        still looks right is the failure this guards against."""
        block = self._block(dropped=[
            {"uid": "bb000002", "title": "A deck that came from outside",
             "where": "vault/files/bb000002.md", "archived": False,
             "reason": tool.DROP_IMPORTED},
            {"uid": "cc000003", "title": "An outside publishing label",
             "where": "vault/files/cc000003.md", "archived": False,
             "reason": tool.DROP_UNGOVERNED},
        ])
        block["dropped_count"] = 99          # a count that disagrees
        for surface, rendered in (
            ("text", "\n".join(tool._read_lines(block))),
            ("board", tool._board_read(block)),
        ):
            with self.subTest(surface=surface):
                self.assertIn("A deck that came from outside", rendered)
                self.assertIn("An outside publishing label", rendered)
                self.assertIn(
                    tool._DROP_SENTENCE[tool.DROP_IMPORTED], rendered
                )
                self.assertIn(
                    tool._DROP_SENTENCE[tool.DROP_UNGOVERNED], rendered
                )
                # The renderer counted the list, not the field.
                self.assertNotIn("99", rendered)
                self.assertIn("2 of the 5 were not read", rendered)

    def test_a_refused_run_never_renders_as_an_answer(self):
        block = self._block(status="refused", refusal="STAGE_C_MODEL_EDGE",
                            detail="the model edge refused with PROVIDER_FAILED")
        text = "\n".join(tool._read_lines(block))
        self.assertIn("THE READ DID NOT HAPPEN", text)
        self.assertIn("STAGE_C_MODEL_EDGE", text)
        self.assertIn("Nothing below has been read", text)
        self.assertNotIn("WHAT THEY SAY — read from", text)

    def test_a_refusal_says_whether_the_bodies_actually_crossed(self):
        """The brief goes over the wire alone; the bodies wait for C2.

        A run that stopped at C1 opened its documents from disk and sent none
        of them, and "had sent" there would overstate the only fact in a
        refused block a reader might act on.
        """
        opened = [{"uid": "aa000001", "title": "What the studio wrote",
                   "where": "vault/files/aa000001.md", "archived": False}]
        brief_only = self._block(
            status="refused", refusal="STAGE_C_MODEL_EDGE", detail="no answer",
            read=opened,
            spend={"spent_nano_usd": 0, "reserved_nano_usd": 10_000_000,
                   "calls": [{"task": tool.stage_c.C1_TASK_CLASS,
                              "model": "haiku", "status": "reserved",
                              "reserved_nano_usd": 10_000_000,
                              "spent_nano_usd": 0}]},
        )
        after_c2 = self._block(
            status="refused", refusal="STAGE_C_SPAN_GUARD", detail="unplaceable",
            read=opened,
            spend={"spent_nano_usd": 1_000_000, "reserved_nano_usd": 0,
                   "calls": [{"task": tool.stage_c.C2_TASK_CLASS,
                              "model": "sonnet", "status": "reconciled",
                              "reserved_nano_usd": 0,
                              "spent_nano_usd": 1_000_000}]},
        )
        # CONTROL: the two blocks differ only in which call was made, so a
        # renderer that ignored the calls would give them the same phrase.
        self.assertEqual(brief_only["read"], after_c2["read"])
        self.assertFalse(tool._crossed(brief_only))
        self.assertTrue(tool._crossed(after_c2))
        for surface, render in (("text", lambda b: "\n".join(tool._read_lines(b))),
                                ("board", tool._board_read)):
            with self.subTest(surface=surface):
                self.assertIn("1 document this had opened, and had not sent",
                              render(brief_only).casefold())
                self.assertIn("had sent when it stopped", render(after_c2))
                self.assertNotIn("had opened, and had not sent",
                                 render(after_c2))
                # "The 1 documents" is a template talking, and a reader hears
                # the template instead of the number.
                self.assertNotIn("1 documents", render(brief_only))

    def test_every_drop_reason_in_the_vocabulary_can_be_rendered(self):
        """A reason with no sentence is a KeyError in front of Mike."""
        for reason in (tool.DROP_UNGOVERNED, tool.DROP_IMPORTED,
                       tool.DROP_BATCH, tool.DROP_SPEND):
            with self.subTest(reason=reason):
                block = self._block(dropped=[{
                    "uid": "aa000001", "title": "What the studio wrote",
                    "where": "vault/files/aa000001.md", "archived": False,
                    "reason": reason,
                }])
                self.assertIn(
                    tool._DROP_SENTENCE[reason],
                    "\n".join(tool._read_lines(block)),
                )
                self.assertIn(tool._DROP_SENTENCE[reason],
                              tool._board_read(block))

    def _block(self, **overrides) -> dict:
        block = {
            "status": "nothing-eligible", "considered": 5, "read": [],
            "dropped": [], "dropped_count": 0, "brief": "", "spans": [],
            "spend": {"spent_nano_usd": 0, "reserved_nano_usd": 0, "calls": []},
            "refusal": None, "detail": None,
            "task_body_bytes": 0, "task_body_bytes_total": 0,
        }
        block.update(overrides)
        block.setdefault("dropped_count", len(block["dropped"]))
        return block


# --------------------------------------------------------------------------- #
# Naming — the register rule                                                    #
# --------------------------------------------------------------------------- #


class NamingTests(ToolCase):
    def test_an_archived_document_is_named_and_the_discrepancy_explained(self):
        """The citation list reads the current projection and shows an
        archived entry as bare hex. The read block reads the union, so it has
        the name — and says why the two halves disagree."""
        # CONTROL: the current projection genuinely does not carry it.
        self.assertNotIn("ee000005", tool._records())
        self.assertIn("ee000005", self.records)

        named = tool._named(item("ee000005"), self.records)
        self.assertEqual(named["title"], "A finished piece of work")
        self.assertTrue(named["archived"])
        self.assertIn(tool._ARCHIVED_NOTE, tool._cite(named))

        plain = tool._named(item("aa000001"), self.records)
        self.assertFalse(plain["archived"])
        self.assertNotIn(tool._ARCHIVED_NOTE, tool._cite(plain))

    def test_an_entry_nothing_carries_is_described_rather_than_spelled(self):
        named = tool._named(item("ffffffff"), self.records)
        self.assertNotIn("ffffffff", named["title"])
        self.assertEqual(named["title"], "an entry no index carries")
        self.assertEqual(named["where"], "")
        # CONTROL: the same call on an entry that HAS a path gives the path,
        # so the empty string above is a fact about this uid and not about
        # the function.
        self.assertEqual(
            tool._named(item("aa000001"), self.records)["where"],
            "vault/files/aa000001.md",
        )

    def test_a_type_that_keeps_its_name_elsewhere_is_still_named(self):
        """A memory entry's name is its ``context``; ``title`` is empty.

        Seven of the eight survivors of one real circle are memory entries,
        and reading only ``title`` renders all seven as the same sentence —
        which is the UID habit with the hex taken out.
        """
        self.records["40000000"] = {
            "uid": "40000000", "type": "memory", "title": "",
            "path": ".tropo-studio/memory/entries/40000000.md",
            "context": "Patient Honing Doctrine — Mike's bedrock framing",
        }
        self.records["40000001"] = {
            "uid": "40000001", "type": "memory", "title": "",
            "path": ".tropo-studio/memory/entries/40000001.md",
            "description": "A record that carries a description instead",
        }
        # CONTROL: neither record has a title, so a fallback that never fired
        # would leave both of these named after the placeholder.
        for uid in ("40000000", "40000001"):
            self.assertEqual(self.records[uid]["title"], "")
        self.assertEqual(
            tool._named(item("40000000"), self.records)["title"],
            "Patient Honing Doctrine — Mike's bedrock framing",
        )
        self.assertEqual(
            tool._named(item("40000001"), self.records)["title"],
            "A record that carries a description instead",
        )

    def test_a_complete_index_title_is_used_without_rereading_source(self):
        """The composed index is the lossless title authority.

        Orient must use the exact current/archive union value rather than
        reopening a source file. Source rereads bypass the stamped composition
        and can make the read block disagree with the ranked citation list.
        """
        whole = (
            "A complete indexed title that remains readable well beyond the "
            "old one-hundred-character projection boundary"
        )
        uid = "50000000"
        (self.fx.root / "vault" / "files" / f"{uid}.md").write_text(
            f"---\nuid: {uid}\ntitle: stale source title\ntype: note\n---\nA body.\n"
        )
        self.assertGreater(len(whole), 100)
        self.records[uid] = {"uid": uid, "title": whole,
                             "path": f"vault/files/{uid}.md"}
        self.assertEqual(tool._named(item(uid), self.records)["title"], whole)

    def test_a_record_with_no_name_anywhere_is_not_confused_with_no_record(self):
        self.records["40000002"] = {
            "uid": "40000002", "type": "memory",
            "path": ".tropo-studio/memory/entries/40000002.md",
            # A list where a name would be: index rows are JSON, and a field
            # that is text in one row is not text in the next.
            "context": ["not", "a", "name"],
        }
        self.assertEqual(
            tool._named(item("40000002"), self.records)["title"],
            "an entry the index carries under no name",
        )
        self.assertEqual(
            tool._named(item("ffffffff"), self.records)["title"],
            "an entry no index carries",
        )

    def test_a_path_the_index_carries_is_cited_even_off_vault_files(self):
        """The reason a document was dropped is often visible in its path.

        ``vault/tools/tropo-preflight.py`` explains "not a governed body" by
        itself. Taking the index's path rather than assuming vault/files is
        what makes that line informative instead of wrong.
        """
        self.records["30000000"] = {
            "uid": "30000000", "title": "preflight — Tool",
            "path": "vault/tools/tropo-preflight.py", "type": "tool",
        }
        named = tool._named(item("30000000"), self.records)
        self.assertEqual(named["where"], "vault/tools/tropo-preflight.py")
        self.assertEqual(
            tool._read_set([item("30000000")], self.records)[1][0]["reason"],
            tool.DROP_UNGOVERNED,
        )


# --------------------------------------------------------------------------- #
# Ruling 3 — spending is opt-in and stated                                      #
# --------------------------------------------------------------------------- #


class SpendVisibilityTests(ToolCase):
    def test_without_the_flag_there_is_no_read_block(self):
        parser_default = tool.main.__doc__  # placeholder-free: check the flag
        source = (TOOLS / "tropo-orient.py").read_text()
        self.assertIn('"--read", action="store_true"', source)
        self.assertIn("MeteredEdge() if args.read else None", source)
        self.assertIsNone(parser_default)

    #: Wording only a read block can produce. Deliberately not the bare
    #: phrase "what they say", which the free footer uses to say it is NOT
    #: saying it — an assertion against that passes on the wrong sentence.
    READ_ONLY_WORDING = (
        "read from", "were not read:", "nothing here was read",
        "the read did not happen", "no model was reached",
    )

    def test_the_free_renderers_carry_no_read_section(self):
        answer = {"ok": True, "task": "aa000001", "task_title": "A task",
                  "items": [{"uid": "aa000001", "title": "What the studio wrote",
                             "type": "note", "status": "active",
                             "why": "sits beside it", "score": 1.0,
                             "stale": False, "indexed": True}]}
        for surface, rendered in (("text", tool.render_text(answer)),
                                  ("board", tool.render_board(answer))):
            with self.subTest(surface=surface):
                for phrase in self.READ_ONLY_WORDING:
                    self.assertNotIn(phrase, rendered.casefold())
        # CONTROL: the same renderers on the same answer with a block DO say
        # it — so a match rule that could never fire fails here.
        answer["read"] = DegradedBlockTests._block(
            DegradedBlockTests, status="read", brief="A brief.",
            read=[{"uid": "aa000001", "title": "What the studio wrote",
                   "where": "vault/files/aa000001.md", "archived": False}],
        )
        for surface, rendered in (("text", tool.render_text(answer)),
                                  ("board", tool.render_board(answer))):
            with self.subTest(surface=surface, present=True):
                self.assertIn("read from", rendered.casefold())

    def test_the_cost_is_stated_even_when_it_is_zero(self):
        self.assertIn(
            "Nothing was spent",
            "\n".join(tool._spend_lines(
                {"spent_nano_usd": 0, "reserved_nano_usd": 0, "calls": []}
            )),
        )

    def test_a_retained_reservation_is_reported_as_held_not_as_free(self):
        """The dangerous middle state: the call was made, no answer came back,
        and the money is still held against today's budget."""
        lines = "\n".join(tool._spend_lines({
            "spent_nano_usd": 0, "reserved_nano_usd": 10_000_000,
            "calls": [{"task": tool.stage_c.C1_TASK_CLASS,
                       "model": "claude-haiku-4-5-20251001", "status": "reserved",
                       "reserved_nano_usd": 10_000_000, "spent_nano_usd": 0}],
        }))
        self.assertIn("$0.0100 was held", lines)
        self.assertIn("stays held", lines)
        # Named in the reader's words, not the spend policy's route key.
        self.assertIn("reading the task and writing the brief", lines)
        self.assertNotIn("parse-query", lines)

    def test_a_real_cost_is_broken_down_by_what_it_bought(self):
        lines = "\n".join(tool._spend_lines({
            "spent_nano_usd": 41_000_000, "reserved_nano_usd": 187_500_000,
            "calls": [
                {"task": tool.stage_c.C1_TASK_CLASS, "model": "haiku",
                 "status": "reconciled", "reserved_nano_usd": 10_000_000,
                 "spent_nano_usd": 1_400_000},
                {"task": tool.stage_c.C2_TASK_CLASS, "model": "sonnet",
                 "status": "reconciled", "reserved_nano_usd": 177_500_000,
                 "spent_nano_usd": 39_600_000},
            ],
        }))
        self.assertIn("This read cost $0.0410", lines)
        self.assertIn("$0.1875 was held", lines)
        self.assertIn("choosing which sentences answer it", lines)


# --------------------------------------------------------------------------- #
# End to end, against the fixture Studio                                        #
# --------------------------------------------------------------------------- #


class ReadEndToEndTests(ToolCase):
    """One whole read, with the provider round trip scripted.

    The scripted provider points at a span by RETYPING it, which is what a
    model does. The emitted text must therefore be the file's bytes and not
    the pointer, or the guard is not doing its job in this composition.
    """

    def _provider(self, spans):
        from lib import llm

        def call(task, messages, **kwargs):
            payload = json.loads(messages[0]["content"])
            self.sent.append((task, payload))
            body = (
                {"brief": "What did the studio write down about this?"}
                if task == tool.stage_c.C1_TASK_CLASS else {"spans": spans}
            )
            return llm.LockedLLMResponse(
                text=json.dumps(body, ensure_ascii=False),
                model=llm.LOCKED_TASK_MODELS[task],
                usage={
                    "input_tokens": 120, "output_tokens": 30,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "service_tier": "standard", "inference_geo": "not_available",
                },
            )

        return call

    def setUp(self) -> None:
        super().setUp()
        self.sent = []

    def test_a_degraded_read_names_what_it_read_and_what_it_did_not(self):
        pointer = "The studio wrote this sentence."
        retyped = pointer.replace("this", "this")  # same bytes; see below
        edge = tool.MeteredEdge(
            studio_root=self.fx.root,
            run_uid="0a1b2c3d",
            provider_call=self._provider(
                [{"uid": "aa000001", "span_text": retyped}]
            ),
        )
        block = tool.read_block(
            "aa000001", "A task",
            [item("aa000001"), item("bb000002"), item("ffffffff")],
            vp.Viewer(principal_uid="7b921d17"),
            circle_of("aa000001", "bb000002", "ffffffff"),
            tool.INDEX_AS_OF, edge,
        )
        self.assertEqual(block["status"], "read", block["detail"])
        self.assertEqual([entry["uid"] for entry in block["read"]], ["aa000001"])
        self.assertEqual(
            sorted(entry["reason"] for entry in block["dropped"]),
            [tool.DROP_IMPORTED, tool.DROP_UNGOVERNED],
        )

        # CONTROL: the survivors that were dropped never reached the wire.
        for task, payload in self.sent:
            if task != tool.stage_c.C2_TASK_CLASS:
                continue
            crossed = {entry["uid"] for entry in payload["survivors"]}
            self.assertEqual(crossed, {"aa000001"})

        # The emitted span is the file's bytes at the locator, not the model's.
        span = block["spans"][0]
        raw = span_guard.match_domain_bytes(
            self.fx.root / "vault" / "files" / "aa000001.md"
        )
        self.assertEqual(
            raw.decode()[span["char_start"]:span["char_end"]], span["text"]
        )
        self.assertEqual(span["title"], "What the studio wrote")

        text = "\n".join(tool._read_lines(block))
        self.assertIn("WHAT THEY SAY — read from 1 of 3 documents", text)
        self.assertIn("2 of the 3 were not read", text)
        self.assertIn("A deck that came from outside", text)
        self.assertIn("This read cost", text)

    def test_a_retyped_pointer_still_emits_the_sources_own_bytes(self):
        on_disk = "The studio wrote this sentence."
        pointer = "The studio wrote this sentence\u2026".replace(
            "sentence\u2026", "sentence."
        )
        # CONTROL: build a pointer that genuinely differs from the source.
        pointer = "The  studio\nwrote this sentence."
        self.assertNotEqual(pointer, on_disk)
        edge = tool.MeteredEdge(
            studio_root=self.fx.root, run_uid="0a1b2c3e",
            provider_call=self._provider(
                [{"uid": "aa000001", "span_text": pointer}]
            ),
        )
        block = tool.read_block(
            "aa000001", "A task", [item("aa000001")],
            vp.Viewer(principal_uid="7b921d17"), circle_of("aa000001"),
            tool.INDEX_AS_OF, edge,
        )
        self.assertEqual(block["status"], "read", block["detail"])
        self.assertEqual(block["spans"][0]["text"], on_disk)

    def test_an_imported_task_refuses_before_anything_crosses(self):
        """The task's own words go over the wire in the brief, so the task
        itself has to clear the same gate its survivors do."""
        edge = tool.MeteredEdge(
            studio_root=self.fx.root,
            provider_call=mock.Mock(side_effect=AssertionError("edge reached")),
        )
        block = tool.read_block(
            "bb000002", "A deck", [item("aa000001")],
            vp.Viewer(principal_uid="7b921d17"), circle_of("aa000001"),
            tool.INDEX_AS_OF, edge,
        )
        self.assertEqual(block["status"], "refused")
        self.assertEqual(block["refusal"], "TASK_NOT_OURS_TO_SEND")
        self.assertEqual(block["spend"]["calls"], [])
        # CONTROL: the same call with an eligible task does reach the edge.
        self.assertEqual(
            tool.read_block(
                "aa000001", "A task", [item("aa000001")],
                vp.Viewer(principal_uid="7b921d17"), circle_of("aa000001"),
                tool.INDEX_AS_OF,
                tool.MeteredEdge(
                    studio_root=self.fx.root, run_uid="0a1b2c3f",
                    provider_call=self._provider(
                        [{"uid": "aa000001",
                          "span_text": "The studio wrote this sentence."}]
                    ),
                ),
            )["status"],
            "read",
        )

    def test_a_whole_read_rewrites_no_governed_file(self):
        """The other way to widen the publishing boundary is to move it.

        Relabelling 2,400 records ``public`` would make them eligible under
        the OLD rule and would corrupt the label the website depends on. A
        read is a pure read: every governed file is byte-identical after it.
        """
        before = self.fx.files()
        block = tool.read_block(
            "aa000001", "A task", [item("aa000001"), item("cc000003")],
            vp.Viewer(principal_uid="7b921d17"),
            circle_of("aa000001", "cc000003"), tool.INDEX_AS_OF,
            tool.MeteredEdge(
                studio_root=self.fx.root, run_uid="0a1b2c40",
                provider_call=self._provider(
                    [{"uid": "aa000001",
                      "span_text": "The studio wrote this sentence."}]
                ),
            ),
        )
        # CONTROL: a run that refused early would leave the files untouched
        # for a reason that has nothing to do with the claim.
        self.assertEqual(block["status"], "read", block["detail"])
        self.assertEqual(
            [entry["reason"] for entry in block["dropped"]], [tool.DROP_IMPORTED]
        )
        self.assertEqual(self.fx.files(), before)


if __name__ == "__main__":
    unittest.main()
