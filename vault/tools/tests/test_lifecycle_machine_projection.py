"""Focused plants for capsule-declared lifecycle-machine SQLite projection."""
from __future__ import annotations

import importlib.util
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import lifecycle_machine  # noqa: E402


def _load_rebuild():
    spec = importlib.util.spec_from_file_location(
        "lifecycle_projection_rebuild",
        TOOLS / "tropo-rebuild-index.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rebuild = _load_rebuild()

CAPSULE_NAMES = (
    "tropo-task.capsule.md",
    "tropo-note.capsule.md",
    "tropo-project.capsule.md",
    "tropo-decision.capsule.md",
)
EXPECTED_STATES = {
    "task": ("new", "accepted", "active", "closed"),
    "note": ("new", "accepted", "active", "closed"),
    "project": ("active", "evergreen", "done", "cancelled"),
    "decision": ("design", "done"),
}
EXPECTED_EDGES = {
    "task": (
        ("new", "accepted"),
        ("new", "closed"),
        ("accepted", "active"),
        ("accepted", "new"),
        ("accepted", "closed"),
        ("active", "closed"),
        ("active", "closed"),
        ("closed", "active"),
    ),
    "note": (
        ("new", "accepted"),
        ("accepted", "active"),
        ("accepted", "new"),
        ("active", "closed"),
    ),
    "project": (("active", "done"), ("active", "cancelled")),
    "decision": (("design", "done"),),
}
EXPECTED_ALIASES = {
    "task": (),
    "note": (("done", "closed"),),
    "project": (
        ("build", "active"),
        ("dormant", "evergreen"),
        ("ideate", "active"),
        ("specify", "active"),
    ),
    "decision": (),
}

BASE_CAPSULE = """---
uid: abcdef01
name: fixture
type: capsule-definition
enforced_enums:
  status:
    - new
    - active
meta_status_rollup:
  to-do:
    - new
  in-progress:
    - active
lifecycle_machine:
  field: status
  optional: false
  states:
    - {value: new, label: New, terminal: false}
    - {value: active, label: Active, terminal: true}
  moves:
    - move_id: start
      from: new
      to: active
      label: Start
      direction: forward
      confirm: false
      resolution: null
      gate: null
      warning: null
      principal_only: false
      legacy_default: false
---

# fixture
"""


class LifecycleMachineProjectionTests(unittest.TestCase):
    def _live_machines(self) -> dict[str, lifecycle_machine.LifecycleMachine]:
        return {
            machine.type_name: machine
            for machine in lifecycle_machine.load_lifecycle_machines(ROOT)
        }

    def _fixture_root(self) -> tempfile.TemporaryDirectory:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / ".tropo").mkdir()
        (root / "vault" / "files").mkdir(parents=True)
        capsules = root / "vault" / "capsules"
        capsules.mkdir()
        for name in CAPSULE_NAMES:
            shutil.copy2(ROOT / "vault" / "capsules" / name, capsules / name)
        return temporary

    def _malformed_root(self, text: str) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        capsules = root / "vault" / "capsules"
        capsules.mkdir(parents=True)
        (capsules / "tropo-fixture.capsule.md").write_text(
            text,
            encoding="utf-8",
        )
        return root

    @staticmethod
    def _projection_rows(
        sqlite_path: Path,
    ) -> tuple[list[tuple], list[tuple], list[tuple]]:
        with sqlite3.connect(sqlite_path) as conn:
            machines = conn.execute(
                """
                SELECT type,field,optional,state,state_label,state_ord,terminal
                FROM lifecycle_machines
                ORDER BY type,state_ord
                """
            ).fetchall()
            transitions = conn.execute(
                """
                SELECT type,move_id,from_state,to_state,move_ord,label,direction,
                       confirm,resolution,gate,warning,principal_only,legacy_default
                FROM lifecycle_transitions
                ORDER BY type,move_ord
                """
            ).fetchall()
            aliases = conn.execute(
                """
                SELECT type,alias,canonical_state
                FROM lifecycle_aliases
                ORDER BY type,alias
                """
            ).fetchall()
        return machines, transitions, aliases

    def test_four_live_declarations_match_locked_machine_semantics(self) -> None:
        machines = self._live_machines()
        self.assertEqual(set(machines), set(EXPECTED_STATES))

        for type_name, expected_states in EXPECTED_STATES.items():
            machine = machines[type_name]
            self.assertEqual(machine.field, "status")
            self.assertEqual(
                tuple(state.value for state in machine.states),
                expected_states,
            )
            self.assertEqual(
                tuple((move.from_state, move.to_state) for move in machine.moves),
                EXPECTED_EDGES[type_name],
            )
            self.assertEqual(
                [state.state_ord for state in machine.states],
                list(range(len(machine.states))),
            )
            self.assertEqual(
                [move.move_ord for move in machine.moves],
                list(range(len(machine.moves))),
            )
            self.assertTrue(
                all(
                    move.direction in {"forward", "back"}
                    for move in machine.moves
                )
            )
            self.assertEqual(
                tuple(
                    (alias.alias, alias.canonical_state)
                    for alias in machine.aliases
                ),
                EXPECTED_ALIASES[type_name],
            )

        self.assertTrue(machines["note"].optional)
        self.assertFalse(machines["task"].optional)
        self.assertTrue(
            next(state for state in machines["note"].states if state.value == "closed").terminal
        )
        self.assertTrue(
            next(state for state in machines["decision"].states if state.value == "done").terminal
        )
        self.assertFalse(
            any(move.from_state == "closed" for move in machines["note"].moves)
        )
        self.assertFalse(
            any(move.from_state == "done" for move in machines["decision"].moves)
        )
        self.assertFalse(
            {"retired", "ideate", "build"}
            & {state.value for state in machines["project"].states}
        )

    def test_move_ids_disambiguate_task_closure_and_metadata_round_trips(self) -> None:
        task = self._live_machines()["task"]
        by_id = {move.move_id: move for move in task.moves}
        closures = {
            move_id: by_id[move_id]
            for move_id in ("close-done", "close-rejected", "close-cancelled")
        }
        self.assertEqual(
            {move.to_state for move in closures.values()},
            {"closed"},
        )
        self.assertEqual(
            {move.resolution for move in closures.values()},
            {"done", "rejected", "cancelled"},
        )
        self.assertEqual(len({move.move_id for move in task.moves}), len(task.moves))
        self.assertEqual(by_id["cancel-before-start"].from_state, "accepted")
        self.assertEqual(by_id["cancel-before-start"].resolution, "cancelled")
        self.assertEqual(
            by_id["close-done"].gate,
            "verifier-and-conditional-approver",
        )
        self.assertTrue(by_id["close-done"].legacy_default)
        self.assertFalse(by_id["close-cancelled"].legacy_default)
        self.assertEqual(
            [
                move.move_id
                for move in task.moves
                if move.from_state == "active"
                and move.to_state == "closed"
                and move.legacy_default
            ],
            ["close-done"],
        )
        self.assertEqual(
            [
                (type_name, move.move_id)
                for type_name, machine in self._live_machines().items()
                for move in machine.moves
                if move.legacy_default
            ],
            [("task", "close-done")],
        )
        self.assertEqual(
            by_id["reopen-regression"].gate,
            "closed-done-regression-audit",
        )
        self.assertEqual(by_id["reroute"].direction, "back")
        self.assertEqual(by_id["reopen-regression"].direction, "back")
        self.assertEqual(
            next(
                move
                for move in self._live_machines()["note"].moves
                if move.move_id == "reroute"
            ).direction,
            "back",
        )

        decision = self._live_machines()["decision"].moves[0]
        self.assertTrue(decision.principal_only)
        self.assertTrue(decision.confirm)
        self.assertEqual(decision.gate, "vault-principal")
        self.assertIsNotNone(decision.warning)

    def test_malformed_declarations_fail_loud(self) -> None:
        duplicate_move = BASE_CAPSULE.replace(
            "      legacy_default: false\n---",
            """      legacy_default: false
    - move_id: start
      from: new
      to: active
      label: Start again
      direction: forward
      confirm: false
      resolution: null
      gate: null
      warning: null
      principal_only: false
      legacy_default: false
---""",
        )
        ambiguous_no_default = BASE_CAPSULE.replace(
            "      legacy_default: false\n---",
            """      legacy_default: false
    - move_id: start-alternative
      from: new
      to: active
      label: Start another way
      direction: forward
      confirm: false
      resolution: null
      gate: null
      warning: null
      principal_only: false
      legacy_default: false
---""",
        )
        ambiguous_multiple_defaults = ambiguous_no_default.replace(
            "legacy_default: false",
            "legacy_default: true",
        )
        unambiguous_default = BASE_CAPSULE.replace(
            "legacy_default: false",
            "legacy_default: true",
        )
        unordered_moves = BASE_CAPSULE.replace(
            """  moves:
    - move_id: start
      from: new
      to: active
      label: Start
      direction: forward
      confirm: false
      resolution: null
      gate: null
      warning: null
      principal_only: false
      legacy_default: false""",
            """  moves:
    0:
      move_id: start""",
        )
        alias_dangle = BASE_CAPSULE.replace(
            """  status:
    - new
    - active""",
            """  status:
    canonical:
      - new
      - active
    aliases:
      legacy: missing""",
        )
        plants = {
            "field": BASE_CAPSULE.replace("field: status", "field: stage"),
            "duplicate-state": BASE_CAPSULE.replace(
                "{value: active, label: Active",
                "{value: new, label: Active",
            ),
            "state-order": BASE_CAPSULE.replace(
                """    - {value: new, label: New, terminal: false}
    - {value: active, label: Active, terminal: true}""",
                """    - {value: active, label: Active, terminal: true}
    - {value: new, label: New, terminal: false}""",
            ),
            "dangling-endpoint": BASE_CAPSULE.replace("to: active", "to: missing"),
            "duplicate-move-id": duplicate_move,
            "missing-legacy-default": BASE_CAPSULE.replace(
                "      legacy_default: false\n",
                "",
            ),
            "ambiguous-no-default": ambiguous_no_default,
            "ambiguous-multiple-defaults": ambiguous_multiple_defaults,
            "unambiguous-default": unambiguous_default,
            "invalid-direction": BASE_CAPSULE.replace(
                "direction: forward",
                "direction: sideways",
            ),
            "unordered-move-shape": unordered_moves,
            "duplicate-metadata": BASE_CAPSULE.replace(
                "      label: Start\n",
                "      label: Start\n      label: Duplicate\n",
            ),
            "alias-dangle": alias_dangle,
            "rollup-not-total": BASE_CAPSULE.replace(
                "  in-progress:\n    - active\n",
                "",
            ),
        }

        for name, text in plants.items():
            with self.subTest(name=name):
                root = self._malformed_root(text)
                with self.assertRaises(lifecycle_machine.LifecycleMachineError):
                    lifecycle_machine.load_lifecycle_machines(root)

    def test_rebuild_rejects_malformed_machine_before_sqlite_write(self) -> None:
        root = self._malformed_root(
            BASE_CAPSULE.replace("to: active", "to: missing")
        )
        (root / ".tropo").mkdir()
        (root / "vault" / "files").mkdir()

        self.assertEqual(rebuild.rebuild_index(root, True), 1)
        self.assertFalse((root / "vault" / "00-index.sqlite").exists())
        self.assertFalse((root / "vault" / "00-index.jsonl").exists())

    def test_repeated_fixture_rebuild_is_deterministic_and_preserves_sources(
        self,
    ) -> None:
        temporary = self._fixture_root()
        root = Path(temporary.name)
        capsules = root / "vault" / "capsules"
        before = {
            name: (capsules / name).read_bytes()
            for name in CAPSULE_NAMES
        }

        self.assertEqual(rebuild.rebuild_index(root, True), 0)
        first = self._projection_rows(root / "vault" / "00-index.sqlite")
        self.assertEqual(rebuild.rebuild_index(root, True), 0)
        second = self._projection_rows(root / "vault" / "00-index.sqlite")

        self.assertEqual(first, second)
        self.assertEqual(
            before,
            {name: (capsules / name).read_bytes() for name in CAPSULE_NAMES},
        )

        parsed = lifecycle_machine.load_lifecycle_machines(root)
        expected_machine_rows, expected_transition_rows, expected_alias_rows = (
            lifecycle_machine.normalized_rows(parsed)
        )
        self.assertEqual(first[0], list(expected_machine_rows))
        self.assertEqual(first[1], list(expected_transition_rows))
        self.assertEqual(first[2], list(expected_alias_rows))

    def test_sqlite_keys_foreign_keys_and_move_order_constraints(self) -> None:
        temporary = self._fixture_root()
        root = Path(temporary.name)
        self.assertEqual(rebuild.rebuild_index(root, True), 0)
        sqlite_path = root / "vault" / "00-index.sqlite"

        with sqlite3.connect(sqlite_path) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            machine_columns = [
                row[1]
                for row in conn.execute("PRAGMA table_info(lifecycle_machines)")
            ]
            transition_columns = [
                row[1]
                for row in conn.execute("PRAGMA table_info(lifecycle_transitions)")
            ]
            alias_columns = [
                row[1]
                for row in conn.execute("PRAGMA table_info(lifecycle_aliases)")
            ]
            self.assertEqual(
                machine_columns,
                [
                    "type",
                    "field",
                    "optional",
                    "state",
                    "state_label",
                    "state_ord",
                    "terminal",
                ],
            )
            self.assertEqual(
                transition_columns,
                [
                    "type",
                    "move_id",
                    "from_state",
                    "to_state",
                    "move_ord",
                    "label",
                    "direction",
                    "confirm",
                    "resolution",
                    "gate",
                    "warning",
                    "principal_only",
                    "legacy_default",
                ],
            )
            self.assertEqual(
                alias_columns,
                ["type", "alias", "canonical_state"],
            )
            self.assertEqual(
                len(
                    conn.execute(
                        "PRAGMA foreign_key_list(lifecycle_transitions)"
                    ).fetchall()
                ),
                4,
            )

            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO lifecycle_machines
                    VALUES ('task','status',0,'duplicate-order','Duplicate',0,0)
                    """
                )
            conn.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO lifecycle_transitions
                    VALUES ('task','accept','new','accepted',99,'Duplicate',
                            'forward',0,NULL,NULL,NULL,0,0)
                    """
                )
            conn.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO lifecycle_transitions
                    VALUES ('task','dangling','missing','closed',99,'Dangling',
                            'forward',0,NULL,NULL,NULL,0,0)
                    """
                )
            conn.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO lifecycle_transitions
                    VALUES ('task','duplicate-order','new','accepted',0,'Duplicate',
                            'forward',0,NULL,NULL,NULL,0,0)
                    """
                )
            conn.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO lifecycle_aliases
                    VALUES ('task','legacy-state','missing')
                    """
                )

    def test_meta_status_queries_are_total_and_reversible(self) -> None:
        temporary = self._fixture_root()
        root = Path(temporary.name)
        self.assertEqual(rebuild.rebuild_index(root, True), 0)

        with sqlite3.connect(root / "vault" / "00-index.sqlite") as conn:
            for type_name, expected_states in EXPECTED_STATES.items():
                forward = conn.execute(
                    """
                    SELECT lm.state, lm.state_ord, msm.bucket
                    FROM lifecycle_machines AS lm
                    JOIN meta_status_map AS msm
                      ON msm.type=lm.type AND msm.value=lm.state
                    WHERE lm.type=?
                    ORDER BY lm.state_ord
                    """,
                    (type_name,),
                ).fetchall()
                self.assertEqual(
                    tuple(row[0] for row in forward),
                    expected_states,
                )
                self.assertEqual(len(forward), len(set(expected_states)))

                reverse_states: set[str] = set()
                for bucket in sorted({row[2] for row in forward}):
                    reverse_states.update(
                        row[0]
                        for row in conn.execute(
                            """
                            SELECT lm.state, lm.state_label, lm.state_ord, lm.terminal
                            FROM lifecycle_machines AS lm
                            JOIN meta_status_map AS msm
                              ON msm.type=lm.type AND msm.value=lm.state
                            WHERE lm.type=? AND msm.bucket=?
                            ORDER BY lm.state_ord
                            """,
                            (type_name, bucket),
                        )
                    )
                self.assertEqual(reverse_states, set(expected_states))

                destinations = {
                    row[0]
                    for row in conn.execute(
                        """
                        SELECT DISTINCT to_state
                        FROM lifecycle_transitions
                        WHERE type=?
                        """,
                        (type_name,),
                    )
                }
                self.assertTrue(destinations <= reverse_states)


if __name__ == "__main__":
    unittest.main()
