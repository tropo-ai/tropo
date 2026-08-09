#!/usr/bin/env python3
"""Focused executable contract for the B4a group-registry projector + resolver.

Covers the acceptance criteria this slice owns:

* AC2 DETERMINISTIC PROJECTION - byte-identical JSONL across repeated and
  build-order-independent projections, full SQLite field-for-field parity, the
  wrapper digest + row count binding, and stale-row removal after re-projection.
* AC4 DECLARATION DEFINES ORDER - a three-level DAG proving containment
  direction and transitivity, and equal-member groups without an ``includes``
  edge staying incomparable.
* AC8 IDEMPOTENT READ MODEL - repeated projection/resolution byte-stability and
  a mutated SQLite database being caught as ``PROJECTION_MISMATCH`` (SQLite is
  never writable truth).
* Resolver refusals - unknown UID, invisible drafts, and stale/unavailable
  corpora each returning the correct typed error, never empty membership.

Modules under test are loaded by file path with ``importlib`` (see
``test_event_ledger_distributed_identity.py``); the pure group_contract
dependency is imported normally so both share one class identity.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sqlite3
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


group_registry = _load(
    "b4a_group_registry_under_test",
    TOOLS / "lib" / "group_registry.py",
)

from lib.group_contract import (  # noqa: E402
    GroupContractError,
    GroupErrorCode,
    build_group_corpus,
    semantic_hash,
)

AuthorityRevisionContext = group_registry.AuthorityRevisionContext
GroupResolver = group_registry.GroupResolver
RegistryProjection = group_registry.RegistryProjection
RegistryWrapper = group_registry.RegistryWrapper
Result = group_registry.Result
build_parity_database = group_registry.build_parity_database
check_sqlite_parity = group_registry.check_sqlite_parity
parse_registry_jsonl = group_registry.parse_registry_jsonl
project_registry = group_registry.project_registry
CANONICALIZATION_VERSION = group_registry.CANONICALIZATION_VERSION
DEFAULT_CONSUMERS = group_registry.DEFAULT_CONSUMERS
DEFAULT_PRODUCERS = group_registry.DEFAULT_PRODUCERS
PARITY_TABLE = group_registry.PARITY_TABLE
REGISTRY_ROW_KEYS = group_registry.REGISTRY_ROW_KEYS
WRAPPER_SCHEMA_ID = group_registry.WRAPPER_SCHEMA_ID


MIKE_UID = "7b921d17"
MIKE_GROUP_UID = "11111111"

# AV1 authority-revision literals (dev-spec 0bfa771d, locked vector AV1).
AV1_AUTHORITY_UID = "a1b2c3d4"
AV1_CORPUS_REVISION = (
    "sha256:8fac9a9ce622c9b265ee91c1f9176bb9ac6054ea3ee49763bf36b37a4516002f"
)
AV1_PRINCIPAL_DIRECTORY_REVISION = (
    "sha256:9af1ee55eafdc2261db97211ab959c9ca9fdab66d5e70f5c24d178e58fa84d83"
)
AV1_GROUP_SHA256 = (
    "8fac9a9ce622c9b265ee91c1f9176bb9ac6054ea3ee49763bf36b37a4516002f"
)

EXPECTED_ROW_KEYS = (
    "group_uid",
    "slug",
    "title",
    "status",
    "version",
    "owner_uid",
    "direct_member_uids",
    "direct_included_group_uids",
    "effective_member_uids",
    "wider_group_uids",
    "source_authority_uid",
    "source_revision",
    "source_path",
    "source_hash",
    "principal_directory_revision",
)


def principal(uid: str, *, status: str = "active") -> dict:
    return {
        "principal_uid": uid,
        "principal_class": "human",
        "status": status,
        "source_authority_uid": AV1_AUTHORITY_UID,
        "source_revision": "1",
        "source_hash": "0" * 64,
    }


def active_group(
    uid: str,
    slug: str,
    *,
    owner: str = MIKE_UID,
    members: list[str] | None = None,
    includes_groups: list[str] | None = None,
    title: str | None = None,
    description: str | None = None,
) -> dict:
    group = {
        "uid": uid,
        "type": "group",
        "slug": slug,
        "title": title or slug.replace("-", " ").title(),
        "description": description or f"Purpose of {slug}.",
        "owner": owner,
        "members": list(members if members is not None else [owner]),
        "includes_groups": list(includes_groups or []),
        "status": "active",
        "version": 1,
    }
    group["semantic_hash"] = semantic_hash(group)
    return group


def draft_group(uid: str, slug: str) -> dict:
    return {
        "uid": uid,
        "type": "group",
        "slug": slug,
        "title": slug.replace("-", " ").title(),
        "description": f"Draft purpose of {slug}.",
        "owner": MIKE_UID,
        "members": [MIKE_UID],
        "includes_groups": [],
        "status": "draft",
        "version": 1,
        "semantic_hash": None,
    }


def source_paths_for(*group_uids: str) -> dict:
    return {uid: f"vault/groups/{uid}.md" for uid in group_uids}


def make_context(
    *group_uids: str,
    authority: str = AV1_AUTHORITY_UID,
    revision: str = AV1_CORPUS_REVISION,
    principal_directory_revision: str = AV1_PRINCIPAL_DIRECTORY_REVISION,
) -> AuthorityRevisionContext:
    return AuthorityRevisionContext(
        source_authority_uid=authority,
        source_revision=revision,
        principal_directory_revision=principal_directory_revision,
        source_paths=source_paths_for(*group_uids),
    )


def mike_principals() -> dict:
    return {MIKE_UID: principal(MIKE_UID)}


def three_level_principals() -> dict:
    return {
        MIKE_UID: principal(MIKE_UID),
        "22222222": principal("22222222"),
        "33333333": principal("33333333"),
    }


def three_level_groups() -> dict:
    narrow = active_group("aa000001", "narrow", members=["33333333"])
    middle = active_group(
        "aa000004",
        "middle",
        members=["22222222"],
        includes_groups=["aa000001"],
    )
    wide = active_group(
        "aa000005",
        "wide",
        members=[MIKE_UID],
        includes_groups=["aa000004"],
    )
    return {"aa000005": wide, "aa000001": narrow, "aa000004": middle}


class B4aGroupRegistryTests(unittest.TestCase):
    def assert_code(self, expected: GroupErrorCode, operation) -> GroupContractError:
        with self.assertRaises(GroupContractError) as raised:
            operation()
        self.assertEqual(raised.exception.code, expected)
        self.assertTrue(str(raised.exception).startswith(expected.value + ":"))
        return raised.exception

    def assert_result_error(
        self,
        result: Result,
        expected: GroupErrorCode,
    ) -> GroupContractError:
        self.assertIsInstance(result, Result)
        self.assertFalse(result.ok)
        self.assertIsNone(result.value)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, expected)
        # The typed error must be raiseable, not silently a bare False/empty.
        with self.assertRaises(GroupContractError) as raised:
            result.unwrap()
        self.assertEqual(raised.exception.code, expected)
        return result.error

    def assert_result_value(self, result: Result, expected) -> None:
        self.assertIsInstance(result, Result)
        self.assertTrue(result.ok, msg=result.error)
        self.assertIsNone(result.error)
        self.assertEqual(result.value, expected)
        self.assertEqual(result.unwrap(), expected)

    # ------------------------------------------------------------------ AC2

    def test_ac2_projection_key_order_is_the_locked_row_order(self) -> None:
        self.assertEqual(REGISTRY_ROW_KEYS, EXPECTED_ROW_KEYS)
        corpus = build_group_corpus(three_level_groups(), three_level_principals())
        projection = project_registry(
            corpus,
            make_context("aa000001", "aa000004", "aa000005"),
        )
        lines = projection.jsonl_bytes.decode("utf-8").split("\n")
        self.assertEqual(lines[-1], "")
        for line in lines[:-1]:
            row = json.loads(line)
            self.assertEqual(tuple(row.keys()), EXPECTED_ROW_KEYS)
        self.assertEqual(
            projection.group_uids,
            ("aa000001", "aa000004", "aa000005"),
        )

    def test_ac2_projection_is_byte_identical_and_independent_of_build_order(
        self,
    ) -> None:
        raw_groups = three_level_groups()
        principals = three_level_principals()

        corpus_a = build_group_corpus(copy.deepcopy(raw_groups), copy.deepcopy(principals))
        reversed_groups = dict(reversed(list(copy.deepcopy(raw_groups).items())))
        corpus_b = build_group_corpus(reversed_groups, copy.deepcopy(principals))

        context_a = make_context("aa000001", "aa000004", "aa000005")
        context_b = make_context("aa000005", "aa000004", "aa000001")

        projection_a1 = project_registry(corpus_a, context_a)
        projection_a2 = project_registry(corpus_a, context_a)
        projection_b = project_registry(corpus_b, context_b)

        # Repeated projection of one corpus is byte-identical.
        self.assertEqual(projection_a1.jsonl_bytes, projection_a2.jsonl_bytes)
        # Independent corpus + independent context + shuffled build order agree.
        self.assertEqual(projection_a1.jsonl_bytes, projection_b.jsonl_bytes)
        self.assertEqual(projection_a1.jsonl_sha256, projection_b.jsonl_sha256)
        self.assertEqual(
            projection_a1.wrapper.canonical_bytes(),
            projection_b.wrapper.canonical_bytes(),
        )

    def test_ac2_full_sqlite_parity_reconstructs_every_field(self) -> None:
        corpus = build_group_corpus(three_level_groups(), three_level_principals())
        projection = project_registry(
            corpus,
            make_context("aa000001", "aa000004", "aa000005"),
        )
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        build_parity_database(projection, connection)

        # Parity passes for a faithful database.
        self.assertIsNone(check_sqlite_parity(projection, connection))

        # Every logical field is actually present in SQLite and equals JSONL.
        cursor = connection.cursor()
        cursor.execute(
            "SELECT " + ",".join(REGISTRY_ROW_KEYS) + f" FROM {PARITY_TABLE} ORDER BY group_uid"
        )
        db_rows = cursor.fetchall()
        expected_rows = parse_registry_jsonl(projection.jsonl_bytes)
        self.assertEqual(len(db_rows), len(expected_rows))
        for db_row, expected in zip(db_rows, expected_rows):
            record = dict(zip(REGISTRY_ROW_KEYS, db_row))
            for key in REGISTRY_ROW_KEYS:
                if key in (
                    "direct_member_uids",
                    "direct_included_group_uids",
                    "effective_member_uids",
                    "wider_group_uids",
                ):
                    self.assertEqual(json.loads(record[key]), expected[key])
                else:
                    self.assertEqual(record[key], expected[key])

    def test_ac2_wrapper_binds_digest_row_count_version_and_authority(self) -> None:
        corpus = build_group_corpus(three_level_groups(), three_level_principals())
        projection = project_registry(
            corpus,
            make_context("aa000001", "aa000004", "aa000005"),
        )
        wrapper = projection.wrapper
        self.assertEqual(wrapper.jsonl_sha256, projection.jsonl_sha256)
        self.assertEqual(wrapper.row_count, 3)
        self.assertEqual(wrapper.row_count, projection.row_count)
        self.assertEqual(wrapper.canonicalization_version, CANONICALIZATION_VERSION)
        self.assertEqual(wrapper.canonicalization_version, 1)
        self.assertEqual(wrapper.source_authority_uid, AV1_AUTHORITY_UID)
        self.assertEqual(wrapper.source_revision, AV1_CORPUS_REVISION)
        self.assertEqual(
            wrapper.principal_directory_revision,
            AV1_PRINCIPAL_DIRECTORY_REVISION,
        )
        self.assertEqual(wrapper.producers, DEFAULT_PRODUCERS)
        self.assertEqual(wrapper.consumers, DEFAULT_CONSUMERS)

        obj = wrapper.canonical_object()
        self.assertEqual(obj["schema_id"], WRAPPER_SCHEMA_ID)
        self.assertEqual(obj["jsonl_sha256"], projection.jsonl_sha256)
        self.assertEqual(obj["row_count"], 3)
        # The wrapper's own digest is stable across independent projections.
        again = project_registry(
            build_group_corpus(three_level_groups(), three_level_principals()),
            make_context("aa000001", "aa000004", "aa000005"),
        )
        self.assertEqual(wrapper.wrapper_sha256, again.wrapper.wrapper_sha256)

    def test_ac2_reprojection_removes_stale_rows(self) -> None:
        principals = mike_principals()
        principals["22222222"] = principal("22222222")
        mike = active_group(MIKE_GROUP_UID, "mike")
        other = active_group("22222222", "other-group", members=["22222222"])

        corpus_two = build_group_corpus(
            {MIKE_GROUP_UID: mike, "22222222": other},
            principals,
        )
        projection_two = project_registry(
            corpus_two,
            make_context(MIKE_GROUP_UID, "22222222"),
        )
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        build_parity_database(projection_two, connection)
        self.assertIsNone(check_sqlite_parity(projection_two, connection))

        # Remove one group and re-project the smaller corpus.
        corpus_one = build_group_corpus({MIKE_GROUP_UID: mike}, principals)
        projection_one = project_registry(corpus_one, make_context(MIKE_GROUP_UID))
        self.assertEqual(projection_one.group_uids, (MIKE_GROUP_UID,))
        self.assertNotIn("22222222", projection_one.group_uids)
        self.assertNotEqual(projection_one.jsonl_bytes, projection_two.jsonl_bytes)

        # A stale database (still holding the removed row) is caught...
        self.assert_code(
            GroupErrorCode.PROJECTION_MISMATCH,
            lambda: check_sqlite_parity(projection_one, connection),
        )
        # ...and rebuilding drops the stale row so parity is clean again.
        build_parity_database(projection_one, connection)
        self.assertIsNone(check_sqlite_parity(projection_one, connection))
        cursor = connection.cursor()
        cursor.execute(f"SELECT group_uid FROM {PARITY_TABLE}")
        self.assertEqual([row[0] for row in cursor.fetchall()], [MIKE_GROUP_UID])

    def test_ac2_mike_row_source_hash_equals_group_semantic_hash(self) -> None:
        mike = active_group(
            MIKE_GROUP_UID,
            "mike",
            title="Mike",
            description="Personal work visible to Mike.",
        )
        corpus = build_group_corpus({MIKE_GROUP_UID: mike}, mike_principals())
        projection = project_registry(corpus, make_context(MIKE_GROUP_UID))
        row = parse_registry_jsonl(projection.jsonl_bytes)[0]
        self.assertEqual(row["group_uid"], MIKE_GROUP_UID)
        self.assertEqual(row["source_hash"], AV1_GROUP_SHA256)
        self.assertEqual(row["source_hash"], semantic_hash(mike))
        self.assertEqual(row["effective_member_uids"], [MIKE_UID])
        self.assertEqual(row["wider_group_uids"], [])
        self.assertEqual(row["source_path"], f"vault/groups/{MIKE_GROUP_UID}.md")

    # ------------------------------------------------------------------ AC4

    def test_ac4_three_level_dag_controls_direction_and_transitivity(self) -> None:
        corpus = build_group_corpus(three_level_groups(), three_level_principals())
        projection = project_registry(
            corpus,
            make_context("aa000001", "aa000004", "aa000005"),
        )
        resolver = GroupResolver.from_projection(projection)

        # Transitive effective membership flows down declared inclusion.
        self.assert_result_value(resolver.resolve_members("aa000001"), ("33333333",))
        self.assert_result_value(
            resolver.resolve_members("aa000004"),
            ("22222222", "33333333"),
        )
        self.assert_result_value(
            resolver.resolve_members("aa000005"),
            ("22222222", "33333333", MIKE_UID),
        )

        # Direction: wider-is-equal-or-wider than narrower, never the reverse.
        self.assert_result_value(
            resolver.is_equal_or_wider("aa000005", "aa000001"), True
        )
        self.assert_result_value(
            resolver.is_equal_or_wider("aa000004", "aa000001"), True
        )
        self.assert_result_value(
            resolver.is_equal_or_wider("aa000005", "aa000004"), True
        )
        self.assert_result_value(
            resolver.is_equal_or_wider("aa000001", "aa000005"), False
        )
        self.assert_result_value(
            resolver.is_equal_or_wider("aa000005", "aa000005"), True
        )

        # can_reference(A, B) true exactly when B == A or B wider than A.
        self.assert_result_value(resolver.can_reference("aa000001", "aa000005"), True)
        self.assert_result_value(resolver.can_reference("aa000001", "aa000004"), True)
        self.assert_result_value(resolver.can_reference("aa000005", "aa000001"), False)
        self.assert_result_value(resolver.can_reference("aa000001", "aa000001"), True)

        row = resolver.resolve_group("aa000001").unwrap()
        self.assertEqual(row["wider_group_uids"], ["aa000004", "aa000005"])
        self.assertEqual(row["direct_included_group_uids"], [])

    def test_ac4_equal_members_without_includes_remain_incomparable(self) -> None:
        first = active_group("aa000001", "first")
        second = active_group("aa000002", "second")
        corpus = build_group_corpus(
            {"aa000002": second, "aa000001": first},
            mike_principals(),
        )
        projection = project_registry(corpus, make_context("aa000001", "aa000002"))
        resolver = GroupResolver.from_projection(projection)

        # Identical member snapshots...
        self.assert_result_value(resolver.resolve_members("aa000001"), (MIKE_UID,))
        self.assert_result_value(resolver.resolve_members("aa000002"), (MIKE_UID,))
        # ...but no declared inclusion, so neither contains the other.
        self.assert_result_value(
            resolver.is_equal_or_wider("aa000001", "aa000002"), False
        )
        self.assert_result_value(
            resolver.is_equal_or_wider("aa000002", "aa000001"), False
        )
        self.assert_result_value(resolver.can_reference("aa000001", "aa000002"), False)
        self.assert_result_value(resolver.can_reference("aa000002", "aa000001"), False)

    def test_ac4_resolver_matches_corpus_oracle_for_all_pairs(self) -> None:
        corpus = build_group_corpus(three_level_groups(), three_level_principals())
        projection = project_registry(
            corpus,
            make_context("aa000001", "aa000004", "aa000005"),
        )
        resolver = GroupResolver.from_projection(projection)
        uids = ("aa000001", "aa000004", "aa000005")
        for wider in uids:
            for narrower in uids:
                self.assertEqual(
                    resolver.is_equal_or_wider(wider, narrower).unwrap(),
                    corpus.is_equal_or_wider(wider, narrower),
                    msg=f"is_equal_or_wider({wider},{narrower})",
                )
        for from_uid in uids:
            for to_uid in uids:
                self.assertEqual(
                    resolver.can_reference(from_uid, to_uid).unwrap(),
                    corpus.can_reference(from_uid, to_uid),
                    msg=f"can_reference({from_uid},{to_uid})",
                )
            self.assertEqual(
                resolver.resolve_members(from_uid).unwrap(),
                corpus.resolve_members(from_uid),
            )

    # ------------------------------------------------------------------ AC8

    def test_ac8_repeated_projection_and_resolution_are_byte_stable(self) -> None:
        corpus = build_group_corpus(three_level_groups(), three_level_principals())
        context = make_context("aa000001", "aa000004", "aa000005")
        first = project_registry(corpus, context)
        second = project_registry(corpus, context)
        self.assertEqual(first.jsonl_bytes, second.jsonl_bytes)

        resolver = GroupResolver.from_projection(first)
        # Resolution is byte-stable and returns detached copies each time.
        group_first = resolver.resolve_group("aa000005").unwrap()
        group_second = resolver.resolve_group("aa000005").unwrap()
        self.assertEqual(group_first, group_second)
        group_first["title"] = "mutated copy"
        self.assertNotEqual(
            resolver.resolve_group("aa000005").unwrap()["title"],
            "mutated copy",
        )
        self.assertEqual(
            resolver.resolve_members("aa000005").unwrap(),
            resolver.resolve_members("aa000005").unwrap(),
        )
        # Re-parsing the JSONL reproduces exactly the projected rows.
        self.assertEqual(
            parse_registry_jsonl(first.jsonl_bytes),
            [dict(row) for row in first.rows],
        )

    def test_ac8_mutated_sqlite_is_detected_as_projection_mismatch(self) -> None:
        corpus = build_group_corpus(three_level_groups(), three_level_principals())
        projection = project_registry(
            corpus,
            make_context("aa000001", "aa000004", "aa000005"),
        )

        def fresh_db() -> sqlite3.Connection:
            connection = sqlite3.connect(":memory:")
            self.addCleanup(connection.close)
            build_parity_database(projection, connection)
            return connection

        # Baseline is clean.
        self.assertIsNone(check_sqlite_parity(projection, fresh_db()))

        mutations = (
            "UPDATE group_registry SET title='tampered' WHERE group_uid='aa000001'",
            "UPDATE group_registry SET effective_member_uids='[\"deadbeef\"]' "
            "WHERE group_uid='aa000005'",
            "UPDATE group_registry SET wider_group_uids='[]' WHERE group_uid='aa000001'",
            "DELETE FROM group_registry WHERE group_uid='aa000004'",
            "INSERT INTO group_registry VALUES "
            "('bb000009','ghost','Ghost','active',1,'7b921d17','[]','[]','[]','[]',"
            "'a1b2c3d4','r','vault/groups/bb000009.md','" + ("0" * 64) + "','p')",
        )
        for statement in mutations:
            with self.subTest(mutation=statement.split()[0] + "-" + statement[:24]):
                connection = fresh_db()
                connection.execute(statement)
                connection.commit()
                self.assert_code(
                    GroupErrorCode.PROJECTION_MISMATCH,
                    lambda connection=connection: check_sqlite_parity(
                        projection, connection
                    ),
                )

    # ---------------------------------------------------- resolver refusals

    def test_resolver_unknown_uid_refuses_and_never_returns_empty_membership(
        self,
    ) -> None:
        corpus = build_group_corpus(
            {MIKE_GROUP_UID: active_group(MIKE_GROUP_UID, "mike")},
            mike_principals(),
        )
        resolver = GroupResolver.from_projection(
            project_registry(corpus, make_context(MIKE_GROUP_UID))
        )
        self.assert_result_error(
            resolver.resolve_group("deadbeef"), GroupErrorCode.GROUP_NOT_FOUND
        )
        members = resolver.resolve_members("deadbeef")
        self.assert_result_error(members, GroupErrorCode.GROUP_NOT_FOUND)
        # Critically, a refusal is not an empty membership snapshot.
        self.assertIsNot(members.value, ())
        self.assertIsNone(members.value)
        self.assert_result_error(
            resolver.is_equal_or_wider("deadbeef", MIKE_GROUP_UID),
            GroupErrorCode.GROUP_NOT_FOUND,
        )
        self.assert_result_error(
            resolver.is_equal_or_wider(MIKE_GROUP_UID, "deadbeef"),
            GroupErrorCode.GROUP_NOT_FOUND,
        )
        self.assert_result_error(
            resolver.can_reference(MIKE_GROUP_UID, "deadbeef"),
            GroupErrorCode.GROUP_NOT_FOUND,
        )
        # Hostile non-string inputs refuse rather than crash.
        self.assert_result_error(
            resolver.resolve_group(None), GroupErrorCode.GROUP_NOT_FOUND
        )
        self.assert_result_error(
            resolver.resolve_members(["not", "hashable"]),
            GroupErrorCode.GROUP_NOT_FOUND,
        )

    def test_resolver_never_exposes_drafts_or_unsigned_candidates(self) -> None:
        mike = active_group(MIKE_GROUP_UID, "mike")
        draft = draft_group("22222222", "draft-only")
        corpus = build_group_corpus(
            {"22222222": draft, MIKE_GROUP_UID: mike},
            mike_principals(),
        )
        projection = project_registry(corpus, make_context(MIKE_GROUP_UID))

        # The draft is absent from the projected JSONL entirely.
        self.assertEqual(projection.group_uids, (MIKE_GROUP_UID,))
        self.assertNotIn(b"22222222", projection.jsonl_bytes)

        resolver = GroupResolver.from_projection(projection)
        self.assertEqual(resolver.active_uids, (MIKE_GROUP_UID,))
        self.assert_result_error(
            resolver.resolve_group("22222222"), GroupErrorCode.GROUP_NOT_FOUND
        )
        self.assert_result_error(
            resolver.resolve_members("22222222"), GroupErrorCode.GROUP_NOT_FOUND
        )
        self.assert_result_error(
            resolver.can_reference("22222222", MIKE_GROUP_UID),
            GroupErrorCode.GROUP_NOT_FOUND,
        )

    def test_resolver_stale_corpus_returns_group_corpus_stale(self) -> None:
        corpus = build_group_corpus(
            {MIKE_GROUP_UID: active_group(MIKE_GROUP_UID, "mike")},
            mike_principals(),
        )
        projection = project_registry(corpus, make_context(MIKE_GROUP_UID))
        # A resolver pinned to a different revision than the JSONL is stale.
        self.assert_code(
            GroupErrorCode.GROUP_CORPUS_STALE,
            lambda: GroupResolver.from_jsonl(
                projection.jsonl_bytes,
                expected_revision="sha256:" + ("f" * 64),
            ),
        )
        # The matching revision constructs cleanly.
        resolver = GroupResolver.from_jsonl(
            projection.jsonl_bytes,
            wrapper=projection.wrapper,
            expected_revision=AV1_CORPUS_REVISION,
        )
        self.assertEqual(resolver.revision, AV1_CORPUS_REVISION)

    def test_resolver_unavailable_corpus_returns_group_corpus_unavailable(self) -> None:
        for bad in (None, 123, "not-bytes"):
            with self.subTest(bad=type(bad).__name__):
                self.assert_code(
                    GroupErrorCode.GROUP_CORPUS_UNAVAILABLE,
                    lambda bad=bad: GroupResolver.from_jsonl(bad),
                )
        self.assert_code(
            GroupErrorCode.GROUP_CORPUS_UNAVAILABLE,
            lambda: project_registry(None, make_context()),
        )
        self.assert_code(
            GroupErrorCode.GROUP_CORPUS_UNAVAILABLE,
            lambda: GroupResolver.from_projection(None),
        )

    def test_resolver_malformed_jsonl_and_wrapper_mismatch_typed_errors(self) -> None:
        corpus = build_group_corpus(
            {MIKE_GROUP_UID: active_group(MIKE_GROUP_UID, "mike")},
            mike_principals(),
        )
        projection = project_registry(corpus, make_context(MIKE_GROUP_UID))

        # Malformed / non-canonical JSONL refuses as unavailable resolution.
        self.assert_code(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            lambda: parse_registry_jsonl(b"{not json}\n"),
        )
        self.assert_code(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            lambda: parse_registry_jsonl(b'{"group_uid":"11111111"}\n'),
        )
        self.assert_code(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            lambda: parse_registry_jsonl(projection.jsonl_bytes.rstrip(b"\n")),
        )

        # A wrapper whose digest disagrees with the JSONL is a projection
        # mismatch, not a silent acceptance.
        tampered = projection.jsonl_bytes.replace(b'"mike"', b'"myke"')
        self.assertNotEqual(tampered, projection.jsonl_bytes)
        self.assert_code(
            GroupErrorCode.PROJECTION_MISMATCH,
            lambda: GroupResolver.from_jsonl(
                tampered, wrapper=projection.wrapper
            ),
        )

    def test_projection_missing_source_path_refuses(self) -> None:
        corpus = build_group_corpus(
            {MIKE_GROUP_UID: active_group(MIKE_GROUP_UID, "mike")},
            mike_principals(),
        )
        empty_context = AuthorityRevisionContext(
            source_authority_uid=AV1_AUTHORITY_UID,
            source_revision=AV1_CORPUS_REVISION,
            principal_directory_revision=AV1_PRINCIPAL_DIRECTORY_REVISION,
            source_paths={},
        )
        self.assert_code(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            lambda: project_registry(corpus, empty_context),
        )
        absolute_context = AuthorityRevisionContext(
            source_authority_uid=AV1_AUTHORITY_UID,
            source_revision=AV1_CORPUS_REVISION,
            principal_directory_revision=AV1_PRINCIPAL_DIRECTORY_REVISION,
            source_paths={MIKE_GROUP_UID: "/etc/groups/mike.md"},
        )
        self.assert_code(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            lambda: project_registry(corpus, absolute_context),
        )

    def test_result_distinguishes_false_value_from_refusal(self) -> None:
        success_false = Result.success(False)
        self.assertTrue(success_false.ok)
        self.assertIs(success_false.value, False)
        self.assertIsNone(success_false.error)
        self.assertIs(success_false.unwrap(), False)

        error = GroupContractError(GroupErrorCode.GROUP_NOT_FOUND, "missing")
        failure = Result.failure(error)
        self.assertFalse(failure.ok)
        self.assertIsNone(failure.value)
        with self.assertRaises(GroupContractError):
            failure.unwrap()

    def test_empty_corpus_projects_to_zero_rows_and_resolves_not_found(self) -> None:
        # A corpus whose only group is a draft has no active rows.
        corpus = build_group_corpus(
            {"22222222": draft_group("22222222", "draft-only")},
            mike_principals(),
        )
        projection = project_registry(corpus, make_context())
        self.assertEqual(projection.jsonl_bytes, b"")
        self.assertEqual(projection.row_count, 0)
        self.assertEqual(projection.wrapper.row_count, 0)

        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        build_parity_database(projection, connection)
        self.assertIsNone(check_sqlite_parity(projection, connection))

        resolver = GroupResolver.from_projection(projection)
        self.assertEqual(resolver.active_uids, ())
        self.assert_result_error(
            resolver.resolve_members("22222222"), GroupErrorCode.GROUP_NOT_FOUND
        )


if __name__ == "__main__":
    unittest.main()
