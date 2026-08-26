"""Build a release fixture the way the PRODUCERS build one.

Stream 1 AC4 / item 3 of the locked-records batch (Mike-approved 2026-08-24,
routed by metis-g112).

WHY THIS MODULE EXISTS. Three suites each hand-built a "finished release" by
writing two files:

    run_dir/publication-receipt.json
    run_dir/scorecard.json

Neither filename has ever been written by any producer in this Studio. The
completion verifier read those same two names, so reader and fixture agreed
with each other and disagreed with the world — and stayed green through four
releases while the verifier could not pass a single real one.

Repairing the reader alone would have left three suites asserting the fiction.
Repairing each suite separately would have created three new copies of "what a
finished release looks like", which is the defect one layer up. So the shape
lives HERE, once, derived from the producers:

  * the publication receipt is CONTENT-ADDRESSED — `release_receipt` names the
    file by the sha256 of its own bytes, under vault/events/release-receipts/.
    This builder hashes what it writes and names the file that, so a fixture
    cannot drift from the addressing rule it is meant to exercise.
  * the published event carries `receipt_sha256` (what `_published_event_data`
    emits), not `publication_receipt_sha256` (what nothing emits).
  * the closure names its five real records, not a `closed_uids` list.
  * the scorecard sits at the producer's own mode-specific filename, taken from
    `release_metrics` rather than restated here.

Metis's condition on this repair, honoured by every suite that uses it: each
repaired test carries a mutation guard that goes RED when the mechanism it
covers is removed. A fixture that only ever passes is how this started.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "PUBLISHED_EVENT",
    "CLOSED_EVENT",
    "write_publication_receipt",
    "real_fire_scorecard_path",
    "write_scorecard",
    "published_event_row",
    "closure_event_row",
    "bus_published_row",
    "build_finished_release",
]

PUBLISHED_EVENT = "tropo.release.published"
CLOSED_EVENT = "tropo.release.closed"


def write_publication_receipt(
    studio_root: Path, version: str = "9.9.9", extra: Optional[Dict[str, Any]] = None
) -> str:
    """Write a content-addressed receipt and return the sha that names it.

    The sha is computed from the bytes actually written. A caller cannot pass
    one in, because a receipt whose name disagrees with its content is exactly
    what the verifier is supposed to catch.
    """
    body: Dict[str, Any] = {"version": version, "kind": "verify-live-public-release"}
    body.update(extra or {})
    payload = json.dumps(body, sort_keys=True).encode("utf-8")
    sha = hashlib.sha256(payload).hexdigest()
    # A Studio is recognised by its .tropo/ directory — tools that resolve a
    # studio root check for it. A fixture "studio" without one is not a studio,
    # and the resolver correctly falls back to the real installation.
    (Path(studio_root) / ".tropo").mkdir(parents=True, exist_ok=True)
    store = Path(studio_root) / "vault" / "events" / "release-receipts"
    store.mkdir(parents=True, exist_ok=True)
    (store / ("%s.json" % sha)).write_bytes(payload)
    return sha


def real_fire_scorecard_path(run_dir: Path) -> Path:
    """The producer's filename, from the producer's module when importable."""
    try:
        from lib import release_metrics  # noqa: WPS433 — optional lib

        return Path(release_metrics.scorecard_path(run_dir, release_metrics.REAL_FIRE))
    except Exception:  # noqa: BLE001 — a missing lib narrows the fixture, never widens it
        return Path(run_dir) / "one-prompt-real-fire-scorecard.json"


def write_scorecard(run_dir: Path, verdict: str = "pass") -> Path:
    """A scorecard in the producer's shape: mode and verdict, no self-hash.

    Deliberately carries NO `scorecard_sha256`. A card cannot contain the hash
    of itself, and the old fixtures supplied one because the old reader asked
    for one — the pair of them inventing a field no producer writes.
    """
    path = real_fire_scorecard_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "real-fire",
                "verdict": verdict,
                "release_version": "9.9.9",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def published_event_row(receipt_sha: str, version: str = "9.9.9") -> Dict[str, Any]:
    """The run-journal mirror, in the shape the publisher actually appends.

    Key is `type`, not `event` — the mirror copies the bus CloudEvent verbatim.
    """
    return {
        "type": PUBLISHED_EVENT,
        "ts": "2026-08-24T09:40:11Z",
        "source": "/tools/publish-release",
        "data": {
            "version": version,
            "tag": "v%s" % version,
            "public_url": "https://example.invalid/releases/v%s" % version,
            "published_at": "2026-08-24T09:36:51Z",
            "receipt_sha256": receipt_sha,
        },
    }


def closure_event_row(receipt_sha: str) -> Dict[str, Any]:
    """A closure that names its five real records, as the closer writes them."""
    return {
        "event": CLOSED_EVENT,
        "ts": "2026-08-24T09:40:27Z",
        "actor": "tropo-publish-release.py",
        "data": {
            "receipt_sha256": receipt_sha,
            "transaction_id": "fire-9.9.9-fixture",
            "release_pipeline_run_uid": "aaaaaaaa",
            "release_plan_uid": "bbbbbbbb",
            "release_entry_uid": "cccccccc",
            "activation_root_uid": "dddddddd",
            "release_activation_uid": "eeeeeeee",
        },
    }


def bus_published_row(receipt_sha: str, version: str = "9.9.9") -> Dict[str, Any]:
    """The bus event, carrying the version that binds it to ONE release."""
    row = published_event_row(receipt_sha, version)
    return {"type": row["type"], "data": row["data"]}


def build_finished_release(
    run_dir: Path,
    studio_root: Path,
    extra_rows: Optional[List[Dict[str, Any]]] = None,
    version: str = "9.9.9",
    with_scorecard: bool = True,
) -> str:
    """Everything a genuinely finished release leaves behind. Returns the sha."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    sha = write_publication_receipt(studio_root, version=version)

    rows: List[Dict[str, Any]] = list(extra_rows or [])
    rows.append(published_event_row(sha, version))
    rows.append(closure_event_row(sha))
    (run_dir / "run.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    if with_scorecard:
        write_scorecard(run_dir)
    return sha


#: The five keys a closure names its records under. Exported so a suite that
#: wants a genuinely EMPTY closure can strip them all, rather than each suite
#: keeping its own copy of the list — which is the defect one layer up.
CLOSED_RECORD_KEYS = (
    "release_pipeline_run_uid",
    "release_plan_uid",
    "release_entry_uid",
    "activation_root_uid",
    "release_activation_uid",
)


def write_the_old_fiction(run_dir: Path, sha: str = "ab" * 32) -> None:
    """The shape these suites used to build, which no producer ever wrote.

    Kept ONLY so every repaired suite can assert it no longer satisfies the
    verifier. That assertion is the mutation guard metis-g112 required as the
    condition of this repair: if someone reverts the reader to the old names,
    or "helpfully" makes it tolerate both, these tests go red instead of
    quietly agreeing with the fiction again.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "publication-receipt.json").write_text(
        json.dumps({"publication_receipt_sha256": sha, "version": "9.9.9"}),
        encoding="utf-8",
    )
    (run_dir / "scorecard.json").write_text(
        json.dumps({"scorecard_sha256": "cd" * 32}), encoding="utf-8"
    )
