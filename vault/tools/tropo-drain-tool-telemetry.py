#!/usr/bin/env python3
"""tropo-drain-tool-telemetry — sealed local shards for tool telemetry (3f38521a AC7).

The durability lane for black-box recorder records. This tool NEVER touches
canonical events: telemetry shards live under the gitignored
``.tropo-studio/telemetry/`` tree, partitioned by segment, sealed with
content-hash manifests, and rotated only after every registered consumer
has checkpointed them. Active shards are never pruned; the canonical event
plane is never edited; crash recovery preserves the valid prefix of a torn
active shard.

Two gestures on purpose (the extractor's pattern): observed tools enqueue
in memory through ``lib/tool_telemetry.py`` and keep moving; sealing,
retention, and recovery happen here, off the observed thread. The pilot
choke points hand their drained records to this module at safe boundaries.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

_STUDIO_DEFAULT = Path(__file__).resolve().parents[2]
TELEMETRY_REL = Path(".tropo-studio") / "telemetry"
CANONICAL_EVENTS_REL = Path("vault") / "events"
DEFAULT_MAX_SEALED_BYTES = 64 * 1024 * 1024

EVENT_TYPE = "tropo.tool.telemetry.recorded"


class ShardIntegrityError(RuntimeError):
    """A sealed shard no longer matches its hash-bound manifest."""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _envelope(record: dict) -> dict:
    """CloudEvents-compatible envelope; the record itself rides in `data`."""
    return {
        "specversion": "1.0",
        "type": EVENT_TYPE,
        "source": f"/tools/{record['tool_uid']}",
        "id": f"{record['invocation_uid']}:{record['outcome']}:{record['attempt']}",
        "time": record["event_time_utc"],
        "data": record,
    }


class TelemetryDrainer:
    """Disk state machine for the telemetry lane.

    Layout (all gitignored):
      .tropo-studio/telemetry/active/active.<segment>.jsonl   — mutable
      .tropo-studio/telemetry/shards/<name>.jsonl             — sealed
      .tropo-studio/telemetry/shards/<name>.manifest.json     — hash-bound
      .tropo-studio/telemetry/checkpoints/<consumer>.json     — vectors
    """

    def __init__(self, studio_root: Path, *,
                 max_sealed_bytes: int = DEFAULT_MAX_SEALED_BYTES) -> None:
        self.studio_root = Path(studio_root)
        self.base = self.studio_root / TELEMETRY_REL
        self.active_dir = self.base / "active"
        self.shards_dir = self.base / "shards"
        self.checkpoints_dir = self.base / "checkpoints"
        self.max_sealed_bytes = max_sealed_bytes

    # -- ingest -----------------------------------------------------------

    def ingest(self, records: list[dict]) -> int:
        """Append drained records to per-segment active shards."""
        if not records:
            return 0
        self.active_dir.mkdir(parents=True, exist_ok=True)
        written = 0
        by_segment: dict[str, list[dict]] = {}
        for record in records:
            by_segment.setdefault(record["segment"], []).append(record)
        for segment, group in sorted(by_segment.items()):
            active = self.active_dir / f"active.{segment}.jsonl"
            with active.open("a", encoding="utf-8") as handle:
                for record in group:
                    handle.write(json.dumps(_envelope(record)) + "\n")
                    written += 1
        return written

    # -- sealing ----------------------------------------------------------

    def seal_all(self) -> list[dict]:
        """Seal every non-empty active shard under a content-hash manifest."""
        if not self.active_dir.is_dir():
            return []
        self.shards_dir.mkdir(parents=True, exist_ok=True)
        manifests: list[dict] = []
        for active in sorted(self.active_dir.glob("active.*.jsonl")):
            raw = active.read_bytes()
            if not raw.strip():
                active.unlink()
                continue
            segment = active.stem.split(".", 1)[1]
            digest = sha256_hex(raw)
            shard_name = f"telemetry-{segment}-{digest[:12]}.jsonl"
            shard_path = self.shards_dir / shard_name
            shard_path.write_bytes(raw)
            manifest = {
                "shard": shard_name,
                "segment": segment,
                "record_count": len(raw.decode("utf-8").strip().splitlines()),
                "bytes": len(raw),
                "sha256": digest,
                "sealed_utc": _now_utc(),
                "event_type": EVENT_TYPE,
            }
            (self.shards_dir / f"{shard_name}.manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            manifests.append(manifest)
            active.unlink()  # rotation: the sealed copy replaces the active one
        return manifests

    def verify_sealed(self, manifest: dict) -> None:
        shard_path = self.shards_dir / manifest["shard"]
        digest = sha256_hex(shard_path.read_bytes())
        if digest != manifest["sha256"]:
            raise ShardIntegrityError(
                f"{manifest['shard']} content hash {digest} != manifest "
                f"{manifest['sha256']}: sealed shards are immutable")

    # -- consumers + retention --------------------------------------------

    def register_consumer(self, name: str) -> None:
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        path = self.checkpoints_dir / f"{name}.json"
        if not path.exists():
            path.write_text(json.dumps({"shards": []}) + "\n",
                            encoding="utf-8")

    def _consumers(self) -> dict[str, set[str]]:
        consumers: dict[str, set[str]] = {}
        if not self.checkpoints_dir.is_dir():
            return consumers
        for path in sorted(self.checkpoints_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            consumers[path.stem] = set(payload.get("shards") or [])
        return consumers

    def checkpoint_consumer(self, name: str, shard_hashes: list[str]) -> None:
        """Record a consumer's sealed-shard coverage. ['*'] = all current."""
        hashes = set(shard_hashes)
        if "*" in hashes:
            hashes.discard("*")
            hashes.update(
                json.loads(m.read_text(encoding="utf-8"))["sha256"]
                for m in self._manifests()
            )
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        (self.checkpoints_dir / f"{name}.json").write_text(
            json.dumps({"shards": sorted(hashes)}) + "\n", encoding="utf-8")

    def _manifests(self) -> list[Path]:
        if not self.shards_dir.is_dir():
            return []
        return sorted(self.shards_dir.glob("*.manifest.json"))

    def apply_retention(self) -> list[str]:
        """Rotate sealed shards that EVERY registered consumer checkpointed.

        Never touches active shards; never edits canonical events. Bounds
        total sealed bytes by rotating oldest-first within the eligible set.
        """
        consumers = self._consumers()
        removed: list[str] = []
        candidates: list[tuple[str, int, Path, Path]] = []
        for manifest_path in self._manifests():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            shard_path = self.shards_dir / manifest["shard"]
            if not shard_path.is_file():
                manifest_path.unlink()  # orphan manifest from an interrupted rotation
                continue
            if not consumers or not all(
                    manifest["sha256"] in covered for covered in consumers.values()
            ):
                # No registered consumers, or one has not checkpointed: the
                # shard is unmined evidence and stays. Rotation requires
                # positive coverage from every registered consumer — an empty
                # consumer set is not "all clear", it is "nobody has read
                # this yet".
                continue
            candidates.append(
                (manifest["shard"], manifest["bytes"], shard_path, manifest_path))
        total = sum(size for _, size, _, _ in candidates)
        for shard_name, size, shard_path, manifest_path in sorted(candidates):
            shard_path.unlink()
            manifest_path.unlink()
            removed.append(shard_name)
            total -= size
            if total <= self.max_sealed_bytes:
                break
        return removed



    # -- viewer-safe query composition (AC4) -------------------------------

    def read_records(self, *, viewer_segments: list[str]) -> dict:
        """Snapshot-safe read of SEALED telemetry through a viewer filter.

        Safety properties, each load-bearing:
          - only sealed shards with verifiable manifests are read (mining
            never observes a mutable active shard);
          - the segment filter applies BEFORE anything is counted, ordered,
            or returned — a viewer sees no existence/count/timing signal of
            segments outside its own;
          - the projection carries no global sequence and no cross-segment
            ordering: records arrive in per-shard file order, unsequenced;
          - an unknown-segment shard answers no query, under any filter,
            including one that names it.
        """
        order = ["public", "argo-reference", "argo-private"]
        allowed = {s for s in viewer_segments if s in order}
        records: list[dict] = []
        shards_read = 0
        windows: list[str] = []
        if not self.shards_dir.is_dir():
            return {"records": records,
                    "coverage": {"shards_read": 0, "windows": windows}}
        for manifest_path in sorted(self.shards_dir.glob("*.manifest.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            segment = manifest.get("segment")
            # Unknown segments and segments outside the viewer's allowlist
            # are excluded by the SAME derivation in `allowed` — one guard,
            # not two (a redundant twin survived its own mutation probe).
            if segment not in allowed:
                continue  # filtered BEFORE counting: no side channel
            shard_path = self.shards_dir / manifest["shard"]
            if not shard_path.is_file():
                continue
            raw = shard_path.read_bytes()
            if sha256_hex(raw) != manifest["sha256"]:
                continue  # integrity failure: skip, never serve
            shards_read += 1
            if manifest.get("sealed_utc"):
                windows.append(manifest["sealed_utc"][:10])
            for line in raw.decode("utf-8").strip().splitlines():
                envelope = json.loads(line)
                records.append({
                    "type": envelope.get("type"),
                    "source": envelope.get("source"),
                    "time": envelope.get("time"),
                    "data": envelope.get("data"),
                    "durability": "telemetry-local",
                })
        return {"records": records,
                "coverage": {"shards_read": shards_read, "windows": windows}}

    # -- crash recovery -----------------------------------------------------

    def recover(self) -> int:
        """Truncate torn trailing writes on active shards; drop orphan
        manifests whose shard never landed. Returns torn lines dropped."""
        dropped = 0
        if self.active_dir.is_dir():
            for active in sorted(self.active_dir.glob("*.jsonl")):
                text = active.read_text(encoding="utf-8")
                lines = text.split("\n")
                # A clean shard ends with a newline; anything after the last
                # parseable line is a torn write.
                good_end = 0
                for index, line in enumerate(lines):
                    if not line:
                        if index == len(lines) - 1:
                            good_end = index
                        continue
                    try:
                        json.loads(line)
                        good_end = index + 1
                    except json.JSONDecodeError:
                        break
                prefix = "\n".join(lines[:good_end])
                if prefix and not prefix.endswith("\n"):
                    prefix += "\n"
                if prefix != text:
                    before = len([l for l in text.strip().splitlines() if l])
                    after = len([l for l in prefix.strip().splitlines() if l])
                    dropped += before - after
                    active.write_text(prefix, encoding="utf-8")
        if self.shards_dir.is_dir():
            for manifest_path in self._manifests():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if not (self.shards_dir / manifest["shard"]).is_file():
                    manifest_path.unlink()
        return dropped


def read_records(studio_root: Path, *, viewer_segments: list[str]) -> dict:
    """Viewer-safe sealed-shard read for the query surface (AC4)."""
    return TelemetryDrainer(Path(studio_root)).read_records(
        viewer_segments=viewer_segments)



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seal, verify, and retain local tool-telemetry shards.")
    parser.add_argument("--studio-root", default=str(_STUDIO_DEFAULT))
    parser.add_argument("--recover", action="store_true",
                        help="repair torn active shards and orphan manifests")
    parser.add_argument("--seal", action="store_true",
                        help="seal all active shards under hash manifests")
    parser.add_argument("--checkpoint", metavar="CONSUMER",
                        help="checkpoint CONSUMER against every sealed shard")
    parser.add_argument("--retention", action="store_true",
                        help="rotate fully-checkpointed sealed shards")
    args = parser.parse_args(argv)

    drainer = TelemetryDrainer(Path(args.studio_root))
    if args.recover:
        print(f"recovery: dropped {drainer.recover()} torn line(s)")
    if args.seal:
        for manifest in drainer.seal_all():
            print(f"sealed {manifest['shard']} "
                  f"({manifest['record_count']} records, {manifest['bytes']} B)")
    if args.checkpoint:
        drainer.checkpoint_consumer(args.checkpoint, ["*"])
        print(f"checkpointed {args.checkpoint} against all sealed shards")
    if args.retention:
        removed = drainer.apply_retention()
        print(f"retention rotated {len(removed)} shard(s)"
              + (f": {', '.join(removed)}" if removed else ""))
    if not (args.recover or args.seal or args.checkpoint or args.retention):
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
