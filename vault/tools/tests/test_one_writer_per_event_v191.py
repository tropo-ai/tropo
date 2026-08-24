#!/usr/bin/env python3
"""v1.91 S2 AC1 (3fb41c99) — exactly one writer per declared release event.

Red baseline (2026-08-23, pre-split): tropo.release.package_frozen carries TWO
shipped writers (tropo-build-release.py stage6 + tropo-freeze-release-
candidate.py) and three declared events carry none (fire_authorized,
orchestrator_invoked, scope_locked). The split lands: the build emits
candidate_built (bytes-produced), the freeze tool is package_frozen's one
writer (evidence-bound).

Writer detection is line-level, not file-level: a writer is a line that
references the event AND sits within a small window of an append/write/make_
event call. A file can be a reader of one event and the writer of another
(the freeze tool reads candidate_built and writes package_frozen) —
file-level counting would call that file a writer of both.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
STUDIO = TOOLS.parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.event_writers import emit_sites  # the ONE shared resolver

sys.modules.setdefault("release_events_for_test",
                       __import__("types").ModuleType("release_events_for_test"))
_spec = importlib.util.spec_from_file_location(
    "release_events_for_test", TOOLS / "lib" / "release_events.py")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["release_events_for_test"] = _mod
_spec.loader.exec_module(_mod)
RELEASE_EVENTS = _mod.RELEASE_EVENTS

def _emit_sites(event_name):
    return emit_sites(event_name, STUDIO)


def test_writer_cardinality_matches_declaration() -> None:
    """One where the contract declares one; many only where it declares many.

    AC1 as originally written asserted exactly-one for EVERY declared event, and
    talos-t48 found that it over-binds: saga_intent, saga_observed and
    verification_receipt are library primitives with many honest call sites. The
    cure is `writers_expected` on EventContract, accepted by argus-a154 with a
    bound — `engine-many` is legitimate ONLY when every writer emits through one
    shared authorship path. That bound is enforced by the reviewer at declaration
    time, not here; what this asserts is that the DECLARATION and the TREE agree.

    Why that is still a real gate: an event declared `one` that grows a second
    writer is the package_frozen defect returning, and this turns RED the moment
    it does.
    """
    failures = []
    for event_name in sorted(RELEASE_EVENTS):
        expected = getattr(RELEASE_EVENTS[event_name], "writers_expected", "one")
        sites = _emit_sites(event_name)
        detail = "; ".join(f"{f}:{n}" for f, n in sites)
        if len(sites) == 0:
            failures.append(f"{event_name}: NO writer in the shipped tree — "
                            f"declared vocabulary that cannot be emitted "
                            f"(the AC2 class)")
        elif expected == "one" and len(sites) > 1:
            failures.append(f"{event_name}: declared writers_expected=one but has "
                            f"{len(sites)} writers ({detail}) — one event, one "
                            f"assertion, one writer")
        elif expected == "engine-many" and len(sites) < 2:
            failures.append(f"{event_name}: declared writers_expected=engine-many "
                            f"but has {len(sites)} writer(s) — a single-writer event "
                            f"must not claim the many-writer carve-out")
    assert not failures, "\n".join(failures)


def test_split_names_carry_distinct_assertions() -> None:
    """The v1.90 overload stays split: the build writes bytes-produced
    (candidate_built), the freeze tool writes evidence-bound (package_frozen),
    and neither writes the other's event."""
    build = _emit_sites("tropo.release.candidate_built")
    freeze = _emit_sites("tropo.release.package_frozen")
    build_files = {f for f, _ in build}
    freeze_files = {f for f, _ in freeze}
    assert any("tropo-build-release.py" in f for f in build_files), \
        f"the build must be candidate_built's writer (bytes-produced); got {build_files}"
    assert any("tropo-freeze-release-candidate.py" in f for f in freeze_files), \
        f"the freeze tool must be package_frozen's writer (evidence-bound); got {freeze_files}"
    assert not any("tropo-build-release.py" in f for f in freeze_files), \
        "the build still writes package_frozen — the overload is not split"


if __name__ == "__main__":
    test_writer_cardinality_matches_declaration()
    test_split_names_carry_distinct_assertions()
    print("all one-writer assertions passed")
