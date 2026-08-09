#!/usr/bin/env python3
"""Focused executable contract for the pure B4a group-semantics slice."""
from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.group_contract import (  # noqa: E402
    GroupContractError,
    GroupErrorCode,
    assert_active_immutable,
    assert_group_transition,
    build_group_corpus,
    canonical_semantic_bytes,
    canonical_semantic_object,
    immutable_changed_fields,
    semantic_hash,
    validate_group,
    verify_active_semantic_hash,
)


MIKE_UID = "7b921d17"
MIKE_GROUP_UID = "11111111"

AV1_GROUP = {
    "uid": MIKE_GROUP_UID,
    "type": "group",
    "slug": "mike",
    "title": "Mike",
    "description": "Personal work visible to Mike.",
    "owner": MIKE_UID,
    "members": [MIKE_UID],
    "includes_groups": [],
    "status": "active",
    "version": 1,
}
AV1_GROUP_BYTES = (
    b'{"uid":"11111111","type":"group","slug":"mike","title":"Mike",'
    b'"description":"Personal work visible to Mike.","owner":"7b921d17",'
    b'"members":["7b921d17"],"includes_groups":[],"status":"active",'
    b'"version":1}\n'
)
AV1_GROUP_SHA256 = "8fac9a9ce622c9b265ee91c1f9176bb9ac6054ea3ee49763bf36b37a4516002f"


def principal(
    uid: str,
    *,
    status: str = "active",
    principal_class: str = "human",
) -> dict:
    return {
        "principal_uid": uid,
        "principal_class": principal_class,
        "status": status,
        "source_authority_uid": "a1b2c3d4",
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


class B4aGroupContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.principals = {MIKE_UID: principal(MIKE_UID)}

    def assert_code(
        self,
        expected: GroupErrorCode,
        operation,
    ) -> GroupContractError:
        with self.assertRaises(GroupContractError) as raised:
            operation()
        self.assertEqual(raised.exception.code, expected)
        self.assertTrue(str(raised.exception).startswith(expected.value + ":"))
        return raised.exception

    def test_av1_canonical_semantic_vector_is_literal_and_exact(self) -> None:
        actual = canonical_semantic_bytes(AV1_GROUP)
        self.assertEqual(actual, AV1_GROUP_BYTES)
        self.assertEqual(len(actual), 203)
        self.assertEqual(hashlib.sha256(actual).hexdigest(), AV1_GROUP_SHA256)
        self.assertEqual(semantic_hash(AV1_GROUP), AV1_GROUP_SHA256)
        self.assertEqual(
            tuple(canonical_semantic_object(AV1_GROUP)),
            (
                "uid",
                "type",
                "slug",
                "title",
                "description",
                "owner",
                "members",
                "includes_groups",
                "status",
                "version",
            ),
        )

    def test_valid_mike_group_validates_and_resolves_exactly(self) -> None:
        mike = active_group(
            MIKE_GROUP_UID,
            "mike",
            title="Mike",
            description="Personal work visible to Mike.",
        )
        validated = validate_group(mike, self.principals)
        self.assertEqual(validated, AV1_GROUP)
        self.assertEqual(verify_active_semantic_hash(mike), AV1_GROUP_SHA256)

        corpus = build_group_corpus({MIKE_GROUP_UID: mike}, self.principals)
        self.assertEqual(corpus.active_uids, (MIKE_GROUP_UID,))
        self.assertEqual(corpus.resolve_group(MIKE_GROUP_UID), AV1_GROUP)
        self.assertEqual(corpus.resolve_members(MIKE_GROUP_UID), (MIKE_UID,))
        self.assertEqual(corpus.strict_wider_ancestors(MIKE_GROUP_UID), ())
        self.assertTrue(corpus.is_equal_or_wider(MIKE_GROUP_UID, MIKE_GROUP_UID))
        self.assertTrue(corpus.can_reference(MIKE_GROUP_UID, MIKE_GROUP_UID))

    def test_founder_bootstrap_is_a_distinct_non_role_audience(self) -> None:
        mike = active_group(MIKE_GROUP_UID, "mike")
        founder = active_group(
            "22222222",
            "mindbridge-founder-bootstrap",
            title="MindBridge Founder Bootstrap",
            description="Temporary founder audience pending separate approval.",
        )
        corpus = build_group_corpus(
            {MIKE_GROUP_UID: mike, "22222222": founder},
            self.principals,
        )
        self.assertEqual(corpus.resolve_members("22222222"), (MIKE_UID,))
        self.assertNotIn("role", corpus.resolve_group("22222222"))
        self.assertFalse(corpus.is_equal_or_wider(MIKE_GROUP_UID, "22222222"))
        self.assertFalse(corpus.is_equal_or_wider("22222222", MIKE_GROUP_UID))

    def test_draft_and_active_hash_lifecycle_is_closed(self) -> None:
        draft = draft_group("22222222", "draft-group")
        self.assertEqual(validate_group(draft, self.principals)["status"], "draft")

        finalized = copy.deepcopy(draft)
        finalized["status"] = "active"
        finalized["semantic_hash"] = semantic_hash(finalized)
        self.assertIsNone(assert_group_transition(draft, finalized, self.principals))

        changed_during_finalize = copy.deepcopy(finalized)
        changed_during_finalize["slug"] = "changed-during-finalize"
        changed_during_finalize["semantic_hash"] = semantic_hash(changed_during_finalize)
        self.assert_code(
            GroupErrorCode.GROUP_IMMUTABLE,
            lambda: assert_group_transition(
                draft,
                changed_during_finalize,
                self.principals,
            ),
        )

        self.assert_code(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            lambda: assert_group_transition(draft, copy.deepcopy(draft), self.principals),
        )

        draft_with_hash = copy.deepcopy(draft)
        draft_with_hash["semantic_hash"] = "0" * 64
        self.assert_code(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            lambda: validate_group(draft_with_hash, self.principals),
        )

        active_without_hash = copy.deepcopy(draft)
        active_without_hash["status"] = "active"
        self.assert_code(
            GroupErrorCode.GROUP_SEMANTIC_HASH_MISMATCH,
            lambda: validate_group(active_without_hash, self.principals),
        )

        bad_version = copy.deepcopy(draft)
        bad_version["version"] = 2
        self.assert_code(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            lambda: validate_group(bad_version, self.principals),
        )

    def test_every_required_placeholder_class_refuses(self) -> None:
        plants = {
            "uid": "<<MINT:uid>>",
            "slug": "required-lowercase-kebab-case",
            "title": "<!-- REQUIRED: human title -->",
            "description": "required-purpose",
            "owner": "required-active-principal-uid",
            "members": ["required-active-principal-uid"],
            "includes_groups": ["required-active-principal-uid"],
        }
        baseline = draft_group("22222222", "draft-group")
        for field, planted_value in plants.items():
            with self.subTest(field=field):
                candidate = copy.deepcopy(baseline)
                candidate[field] = planted_value
                self.assert_code(
                    GroupErrorCode.GROUP_PLACEHOLDER,
                    lambda candidate=candidate: validate_group(candidate, self.principals),
                )

    def test_duplicate_member_include_and_slug_refuse_with_distinct_codes(self) -> None:
        duplicate_member = draft_group("22222222", "duplicate-member")
        duplicate_member["members"] = [MIKE_UID, MIKE_UID]
        self.assert_code(
            GroupErrorCode.GROUP_MEMBER_DUPLICATE,
            lambda: validate_group(duplicate_member, self.principals),
        )

        duplicate_include = draft_group("22222222", "duplicate-include")
        duplicate_include["includes_groups"] = ["33333333", "33333333"]
        self.assert_code(
            GroupErrorCode.GROUP_INCLUDE_DUPLICATE,
            lambda: validate_group(duplicate_include, self.principals),
        )

        first = active_group("22222222", "same-slug")
        second = active_group("33333333", "same-slug")
        self.assert_code(
            GroupErrorCode.GROUP_SLUG_DUPLICATE,
            lambda: build_group_corpus(
                {"33333333": second, "22222222": first},
                self.principals,
            ),
        )

    def test_owner_and_member_resolution_refuses_missing_inactive_and_nonprincipal(self) -> None:
        other_uid = "22222222"
        cases = (
            ("missing-owner", "owner", {}, MIKE_UID),
            (
                "inactive-owner",
                "owner",
                {MIKE_UID: principal(MIKE_UID, status="archived")},
                MIKE_UID,
            ),
            (
                "nonprincipal-owner",
                "owner",
                {
                    MIKE_UID: {
                        "principal_uid": MIKE_UID,
                        "principal_class": "task",
                        "status": "active",
                    }
                },
                MIKE_UID,
            ),
            (
                "missing-member",
                "members",
                {MIKE_UID: principal(MIKE_UID)},
                other_uid,
            ),
            (
                "inactive-member",
                "members",
                {
                    MIKE_UID: principal(MIKE_UID),
                    other_uid: principal(other_uid, status="archived"),
                },
                other_uid,
            ),
            (
                "nonprincipal-member",
                "members",
                {
                    MIKE_UID: principal(MIKE_UID),
                    other_uid: {
                        "principal_uid": other_uid,
                        "principal_class": "project",
                        "status": "active",
                    },
                },
                other_uid,
            ),
        )
        for name, field, principal_map, target_uid in cases:
            with self.subTest(name=name):
                candidate = draft_group("33333333", name)
                if field == "owner":
                    candidate["owner"] = target_uid
                    candidate["members"] = [target_uid]
                else:
                    candidate["members"] = [target_uid]
                error = self.assert_code(
                    GroupErrorCode.PRINCIPAL_UNRESOLVED,
                    lambda candidate=candidate, principal_map=principal_map: validate_group(
                        candidate,
                        principal_map,
                    ),
                )
                self.assertEqual(error.reference_uid, target_uid)

    def test_unknown_inactive_and_self_inclusions_refuse(self) -> None:
        unknown = active_group(
            "22222222",
            "unknown-include",
            includes_groups=["99999999"],
        )
        self.assert_code(
            GroupErrorCode.GROUP_NOT_FOUND,
            lambda: build_group_corpus({"22222222": unknown}, self.principals),
        )

        draft = draft_group("33333333", "narrow-draft")
        wider = active_group(
            "22222222",
            "wider",
            includes_groups=["33333333"],
        )
        self.assert_code(
            GroupErrorCode.GROUP_INACTIVE,
            lambda: build_group_corpus(
                {"22222222": wider, "33333333": draft},
                self.principals,
            ),
        )

        self_include = draft_group("44444444", "self-include")
        self_include["includes_groups"] = ["44444444"]
        error = self.assert_code(
            GroupErrorCode.GROUP_CYCLE,
            lambda: validate_group(self_include, self.principals),
        )
        self.assertEqual(error.cycle, ("44444444", "44444444"))

    def test_whole_corpus_two_and_three_group_cycles_are_deterministic(self) -> None:
        two_a = active_group("11111111", "two-a", includes_groups=["22222222"])
        two_b = active_group("22222222", "two-b", includes_groups=["11111111"])
        error = self.assert_code(
            GroupErrorCode.GROUP_CYCLE,
            lambda: build_group_corpus(
                {"22222222": two_b, "11111111": two_a},
                self.principals,
            ),
        )
        self.assertEqual(error.cycle, ("11111111", "22222222", "11111111"))

        three_a = active_group("11111111", "three-a", includes_groups=["22222222"])
        three_b = active_group("22222222", "three-b", includes_groups=["33333333"])
        three_c = active_group("33333333", "three-c", includes_groups=["11111111"])
        error = self.assert_code(
            GroupErrorCode.GROUP_CYCLE,
            lambda: build_group_corpus(
                {
                    "33333333": three_c,
                    "11111111": three_a,
                    "22222222": three_b,
                },
                self.principals,
            ),
        )
        self.assertEqual(
            error.cycle,
            ("11111111", "22222222", "33333333", "11111111"),
        )

    def test_thirty_two_deterministic_cycle_and_self_edge_plants(self) -> None:
        for plant in range(32):
            with self.subTest(plant=plant):
                if plant % 2 == 0:
                    uid = f"{0x40000000 + plant:08x}"
                    candidate = draft_group(uid, f"self-plant-{plant}")
                    candidate["includes_groups"] = [uid]
                    error = self.assert_code(
                        GroupErrorCode.GROUP_CYCLE,
                        lambda candidate=candidate: validate_group(
                            candidate,
                            self.principals,
                        ),
                    )
                    self.assertEqual(error.cycle, (uid, uid))
                    continue

                node_count = 2 + (plant % 7)
                uids = [f"{0x50000000 + index:08x}" for index in range(node_count)]
                groups = {
                    uid: active_group(
                        uid,
                        f"cycle-{plant}-node-{index}",
                        includes_groups=[uids[(index + 1) % node_count]],
                    )
                    for index, uid in enumerate(uids)
                }
                error = self.assert_code(
                    GroupErrorCode.GROUP_CYCLE,
                    lambda groups=groups: build_group_corpus(groups, self.principals),
                )
                self.assertEqual(error.cycle[0], error.cycle[-1])
                self.assertEqual(len(error.cycle), node_count + 1)

    def test_equal_member_snapshots_without_declaration_remain_incomparable(self) -> None:
        first = active_group("11111111", "first")
        second = active_group("22222222", "second")
        corpus = build_group_corpus(
            {"22222222": second, "11111111": first},
            self.principals,
        )
        self.assertEqual(corpus.resolve_members("11111111"), (MIKE_UID,))
        self.assertEqual(corpus.resolve_members("22222222"), (MIKE_UID,))
        self.assertFalse(corpus.is_equal_or_wider("11111111", "22222222"))
        self.assertFalse(corpus.is_equal_or_wider("22222222", "11111111"))
        self.assertFalse(corpus.can_reference("11111111", "22222222"))
        self.assertFalse(corpus.can_reference("22222222", "11111111"))

    def test_declared_transitivity_controls_members_ancestors_and_reference_direction(self) -> None:
        second_principal = "22222222"
        third_principal = "33333333"
        principals = {
            MIKE_UID: principal(MIKE_UID),
            second_principal: principal(second_principal),
            third_principal: principal(third_principal),
        }
        narrow = active_group(
            "11111111",
            "narrow",
            members=[third_principal],
        )
        middle = active_group(
            "44444444",
            "middle",
            members=[second_principal],
            includes_groups=["11111111"],
        )
        wide = active_group(
            "55555555",
            "wide",
            members=[MIKE_UID],
            includes_groups=["44444444"],
        )
        corpus = build_group_corpus(
            {
                "55555555": wide,
                "11111111": narrow,
                "44444444": middle,
            },
            principals,
        )

        self.assertEqual(corpus.resolve_members("11111111"), (third_principal,))
        self.assertEqual(
            corpus.resolve_members("44444444"),
            tuple(sorted((second_principal, third_principal))),
        )
        self.assertEqual(
            corpus.resolve_members("55555555"),
            tuple(sorted((MIKE_UID, second_principal, third_principal))),
        )
        self.assertEqual(
            corpus.strict_wider_ancestors("11111111"),
            ("44444444", "55555555"),
        )
        self.assertEqual(corpus.strict_wider_ancestors("44444444"), ("55555555",))
        self.assertTrue(corpus.is_equal_or_wider("55555555", "11111111"))
        self.assertTrue(corpus.can_reference("11111111", "55555555"))
        self.assertFalse(corpus.can_reference("55555555", "11111111"))

    def test_one_hundred_twenty_eight_deterministic_containment_dags(self) -> None:
        group_uids = [f"{0x10000000 + index:08x}" for index in range(8)]
        principal_uids = [f"{0x20000000 + index:08x}" for index in range(8)]
        principals = {MIKE_UID: principal(MIKE_UID)}
        principals.update({uid: principal(uid) for uid in principal_uids})
        optional_edges = (
            (2, 0),
            (3, 0),
            (4, 1),
            (5, 2),
            (6, 3),
            (7, 4),
            (7, 0),
        )

        for case in range(128):
            with self.subTest(case=case):
                includes_by_index = {
                    index: [group_uids[index - 1]] if index else []
                    for index in range(8)
                }
                for bit, (wider_index, narrower_index) in enumerate(optional_edges):
                    if case & (1 << bit):
                        includes_by_index[wider_index].append(group_uids[narrower_index])

                groups = {
                    uid: active_group(
                        uid,
                        f"dag-{case}-node-{index}",
                        members=[principal_uids[index]],
                        includes_groups=includes_by_index[index],
                    )
                    for index, uid in enumerate(group_uids)
                }
                corpus = build_group_corpus(groups, principals)

                self.assertEqual(
                    corpus.resolve_group(group_uids[-1])["includes_groups"],
                    sorted(includes_by_index[7]),
                )
                for narrower_index, narrower_uid in enumerate(group_uids):
                    self.assertEqual(
                        corpus.resolve_members(narrower_uid),
                        tuple(sorted(principal_uids[: narrower_index + 1])),
                    )
                    self.assertEqual(
                        corpus.strict_wider_ancestors(narrower_uid),
                        tuple(group_uids[narrower_index + 1 :]),
                    )
                    for wider_index, wider_uid in enumerate(group_uids):
                        expected = wider_index >= narrower_index
                        self.assertEqual(
                            corpus.is_equal_or_wider(wider_uid, narrower_uid),
                            expected,
                        )
                        self.assertEqual(
                            corpus.can_reference(narrower_uid, wider_uid),
                            expected,
                        )

    def test_drafts_are_validated_but_excluded_from_every_resolver_operation(self) -> None:
        draft = draft_group("22222222", "draft-only")
        active = active_group(MIKE_GROUP_UID, "mike")
        corpus = build_group_corpus(
            {"22222222": draft, MIKE_GROUP_UID: active},
            self.principals,
        )
        self.assertEqual(corpus.active_uids, (MIKE_GROUP_UID,))
        for operation in (
            lambda: corpus.resolve_group("22222222"),
            lambda: corpus.resolve_members("22222222"),
            lambda: corpus.strict_wider_ancestors("22222222"),
            lambda: corpus.is_equal_or_wider("22222222", MIKE_GROUP_UID),
            lambda: corpus.can_reference(MIKE_GROUP_UID, "22222222"),
        ):
            self.assert_code(GroupErrorCode.GROUP_INACTIVE, operation)

    def test_active_hash_mismatch_and_even_freshly_hashed_mutation_refuse(self) -> None:
        before = active_group(MIKE_GROUP_UID, "mike")

        stale = copy.deepcopy(before)
        stale["description"] = "Mutated without a fresh hash."
        self.assert_code(
            GroupErrorCode.GROUP_SEMANTIC_HASH_MISMATCH,
            lambda: verify_active_semantic_hash(stale),
        )

        freshly_hashed_mutation = copy.deepcopy(before)
        freshly_hashed_mutation["title"] = "Changed Mike"
        freshly_hashed_mutation["semantic_hash"] = semantic_hash(freshly_hashed_mutation)
        self.assertEqual(immutable_changed_fields(before, freshly_hashed_mutation), ("title",))
        self.assert_code(
            GroupErrorCode.GROUP_IMMUTABLE,
            lambda: assert_active_immutable(before, freshly_hashed_mutation),
        )

        unchanged = copy.deepcopy(before)
        self.assertIsNone(assert_active_immutable(before, unchanged))

    def test_all_public_operations_leave_input_mappings_unchanged(self) -> None:
        second_principal = "22222222"
        principals = {
            second_principal: principal(second_principal),
            MIKE_UID: principal(MIKE_UID),
        }
        narrow = active_group(
            "11111111",
            "narrow",
            members=[second_principal, MIKE_UID],
        )
        wide = active_group(
            "33333333",
            "wide",
            members=[second_principal, MIKE_UID],
            includes_groups=["11111111"],
        )
        groups = {"33333333": wide, "11111111": narrow}
        groups_before = copy.deepcopy(groups)
        principals_before = copy.deepcopy(principals)

        canonical_semantic_object(wide)
        canonical_semantic_bytes(wide)
        semantic_hash(wide)
        verify_active_semantic_hash(wide)
        validate_group(wide, principals)
        corpus = build_group_corpus(groups, principals)
        corpus.resolve_group("33333333")["members"].append("ffffffff")
        corpus.resolve_members("33333333")
        corpus.strict_wider_ancestors("11111111")
        corpus.is_equal_or_wider("33333333", "11111111")
        corpus.can_reference("11111111", "33333333")
        assert_active_immutable(wide, copy.deepcopy(wide))

        self.assertEqual(groups, groups_before)
        self.assertEqual(principals, principals_before)
        self.assertEqual(corpus.resolve_members("33333333"), (second_principal, MIKE_UID))

    def test_hostile_mapping_values_fail_with_typed_errors_not_builtin_exceptions(self) -> None:
        invalid_groups = (None, [], "group", 7, True)
        for invalid in invalid_groups:
            with self.subTest(entrypoint="canonical", value=type(invalid).__name__):
                self.assert_code(
                    GroupErrorCode.GROUP_SCHEMA_INVALID,
                    lambda invalid=invalid: canonical_semantic_object(invalid),
                )

        baseline = draft_group("22222222", "hostile-values")
        field_plants = {
            "uid": [],
            "type": {"group": True},
            "slug": 1,
            "title": "\ud800",
            "description": None,
            "owner": False,
            "members": {"uid": MIKE_UID},
            "includes_groups": [None],
            "status": ["active"],
            "version": True,
        }
        for field, value in field_plants.items():
            with self.subTest(entrypoint="field", field=field):
                candidate = copy.deepcopy(baseline)
                candidate[field] = value
                with self.assertRaises(GroupContractError):
                    validate_group(candidate, self.principals)

        mixed_key_group = copy.deepcopy(baseline)
        mixed_key_group[1] = "not-a-string-key"
        self.assert_code(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            lambda: validate_group(mixed_key_group, self.principals),
        )
        self.assert_code(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            lambda: validate_group(baseline, []),
        )
        self.assert_code(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            lambda: build_group_corpus([], self.principals),
        )
        self.assert_code(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            lambda: build_group_corpus({1: baseline}, self.principals),
        )
        self.assert_code(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            lambda: build_group_corpus({"22222222": None}, self.principals),
        )

        corpus = build_group_corpus(
            {MIKE_GROUP_UID: active_group(MIKE_GROUP_UID, "mike")},
            self.principals,
        )
        self.assert_code(
            GroupErrorCode.GROUP_NOT_FOUND,
            lambda: corpus.resolve_group(None),
        )


if __name__ == "__main__":
    unittest.main()
