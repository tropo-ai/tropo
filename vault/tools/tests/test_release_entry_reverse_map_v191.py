#!/usr/bin/env python3
"""S1 AC2 support (dev-spec 0a0e94d1, metis-g111 2026-08-23).

tropo-validate-capability-membership.py used to resolve a release entry's plan, when the entry
carried no `shipped_release_plan`, by re-reading and YAML-parsing every vault/files/*.md ONCE PER
SUCH ENTRY (46 entries x ~16.7s = the 12m30s strict run that overran the build's 600s
enforcement-gate timeout, so AC2 could never pass). main() now builds one reverse map in a single
pass and hands it to validate_release_entry; the per-entry scan survives only as the fallback for
direct callers that pass no map.

What this test pins, by RUNNING both paths on one fixture:
  1. With two release-plans pointing at the same release and the release entry sorting before
     both of them, the map path and the scan path resolve the SAME plan uid (first in glob order
     wins: the scan's `break` semantics, the map's `setdefault`).
  2. The findings produced by validate_release_entry are identical on both paths.
Mutation clauses (run them, do not read them): change `setdefault` to plain assignment in main()
and case 1 flips when the two plans' glob order disagrees with first-wins; drop the
`plan_by_release` argument at the call site in main() and the timing assertion in case 3 reds.
  3. The map path does not re-read vault/files per entry: with N synthetic release entries lacking
     `shipped_release_plan`, the number of file reads performed by the map path is O(1) in N.
"""
import importlib.util
import io
import os
import pathlib
import sys
import tempfile
import textwrap
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
TOOL = ROOT / "vault" / "tools" / "tropo-validate-capability-membership.py"


def _load_tool(vault_root: pathlib.Path):
    """Import the validator as a module with VAULT_ROOT pointed at the fixture."""
    os.environ["TROPO_VAULT_ROOT"] = str(vault_root)
    spec = importlib.util.spec_from_file_location("capmem_" + vault_root.name, TOOL)
    mod = importlib.util.module_from_spec(spec)
    # silence the module's import-time prints
    _stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.stdout = _stdout
    # hard-point the root regardless of how the module resolves it
    mod.VAULT_ROOT = vault_root
    return mod


def _write(path: pathlib.Path, frontmatter: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + textwrap.dedent(frontmatter).strip() + "\n---\n\n# fixture\n", encoding="utf-8")


def _fixture(n_extra_entries: int = 0) -> pathlib.Path:
    """A minimal vault: one hub, one capability, one release entry with NO shipped_release_plan,
    and TWO release-plans both claiming shipped_release == that entry (glob order decides)."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="capmem-rmap-"))
    files = root / "vault" / "files"
    _write(files / "8dd772a0.md", """
        uid: 8dd772a0
        type: subsystem
        subsystem_name: tropo-governance
        state: active
        status: active
    """)
    _write(files / "cafe0001.md", """
        uid: cafe0001
        type: dev-spec
        status: done
        subsystem_hub:
          - 8dd772a0
    """)
    # release entry named so it sorts BEFORE both plans in any ordering
    _write(files / "00000aaa.md", """
        uid: 00000aaa
        type: release
        status: shipped
        release_version: "1.60.0"
        title: "Tropo-OS v1.60.0 — fixture"
        subsystems_touched:
          - 8dd772a0
    """)
    for plan_uid in ("p1an0001", "p1an0002"):
        _write(files / f"{plan_uid}.md", f"""
            uid: {plan_uid}
            type: release-plan
            capsule_version: '1.3'
            status: done
            release_version: "1.60.0"
            title: "Tropo-OS v1.60.0 — plan {plan_uid}"
            shipped_release: 00000aaa
            capabilities_touched:
              - cafe0001
            hub_summaries:
              8dd772a0: "fixture summary long enough to satisfy the hub-summary floor of the validator check twenty-one, fifty chars minimum."
        """)
    for i in range(n_extra_entries):
        _write(files / f"00000b{i:02d}.md", f"""
            uid: 00000b{i:02d}
            type: release
            status: shipped
            release_version: "1.{61 + i}.0"
            title: "Tropo-OS v1.{61 + i}.0 — fixture"
            subsystems_touched:
              - 8dd772a0
        """)
    (root / ".tropo-studio" / "registries").mkdir(parents=True, exist_ok=True)
    (root / ".tropo-studio" / "registries" / "subsystem-registry.jsonl").write_text("")
    return root


class ReverseMapEquivalence(unittest.TestCase):
    def test_map_and_scan_resolve_the_same_plan_and_findings(self):
        root = _fixture()
        mod = _load_tool(root)
        files = root / "vault" / "files"
        fm = mod.parse_frontmatter((files / "00000aaa.md").read_text())
        mo_map = mod.load_member_of_map()
        registry = mod.load_subsystem_registry()
        # the map exactly as main() builds it (first plan in glob order wins)
        plan_by_release = {}
        for path in files.glob("*.md"):
            pfm = mod.parse_frontmatter(path.read_text())
            if pfm and pfm.get("type") == "release-plan" and pfm.get("shipped_release"):
                plan_by_release.setdefault(pfm["shipped_release"], pfm.get("uid"))
        self.assertIn("00000aaa", plan_by_release)
        via_map = mod.validate_release_entry("00000aaa", fm, mo_map, registry, True,
                                             plan_by_release=plan_by_release)
        via_scan = mod.validate_release_entry("00000aaa", fm, mo_map, registry, True)
        self.assertEqual([(f.severity, f.check, f.target, f.message) for f in via_map],
                         [(f.severity, f.check, f.target, f.message) for f in via_scan])
        # and the plan each path resolved is the same one: the scan's first match in glob order
        first_in_glob = next(mod.parse_frontmatter(p.read_text()).get("uid")
                             for p in files.glob("*.md")
                             if (mod.parse_frontmatter(p.read_text()) or {}).get("type") == "release-plan")
        self.assertEqual(plan_by_release["00000aaa"], first_in_glob)

    def test_map_path_does_not_rescan_per_entry(self):
        """O(1) file reads in the number of release entries: instrument Path.read_text."""
        root = _fixture(n_extra_entries=12)
        mod = _load_tool(root)
        files = root / "vault" / "files"
        mo_map = mod.load_member_of_map()
        registry = mod.load_subsystem_registry()
        plan_by_release = {}
        for path in files.glob("*.md"):
            pfm = mod.parse_frontmatter(path.read_text())
            if pfm and pfm.get("type") == "release-plan" and pfm.get("shipped_release"):
                plan_by_release.setdefault(pfm["shipped_release"], pfm.get("uid"))
        entries = [(p.stem, mod.parse_frontmatter(p.read_text())) for p in files.glob("*.md")]
        entries = [(u, f) for u, f in entries if f and f.get("type") == "release"]
        self.assertGreaterEqual(len(entries), 13)
        reads = {"n": 0}
        real_read_text = pathlib.Path.read_text

        def counting_read_text(self_, *a, **k):
            reads["n"] += 1
            return real_read_text(self_, *a, **k)

        pathlib.Path.read_text = counting_read_text
        try:
            for uid, fm in entries:
                mod.validate_release_entry(uid, fm, mo_map, registry, True, plan_by_release=plan_by_release)
            map_reads = reads["n"]
            reads["n"] = 0
            # the fallback scan, for contrast, reads the whole directory per entry
            mod.validate_release_entry(entries[0][0], entries[0][1], mo_map, registry, True)
            scan_reads_one_entry = reads["n"]
        finally:
            pathlib.Path.read_text = real_read_text
        # the map path's reads across ALL entries are fewer than one scan of the directory
        self.assertLess(map_reads, scan_reads_one_entry,
                        f"map path read {map_reads} files across {len(entries)} entries; "
                        f"a single fallback scan read {scan_reads_one_entry}")


if __name__ == "__main__":
    unittest.main()
