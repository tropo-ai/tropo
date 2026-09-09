"""One fact, two readers, and a gate that notices (A165 Finding 4, 2026-08-31).

The kernel's spec_substrate_refs.UID_RE and the vault authority's
governed_path.UID_SHAPES both encode the governed uid shape — deliberately
NOT one import, because the kernel (.tropo/scripts) must not take a runtime
dependency on the vault tree (a location-contract call, not style). The
proportionate cure for the two-readers family is this drift gate: assert the
two agree, the boot-derivation-fingerprint shape. If either side's shape set
changes without the other, this goes red and names both files.
"""

from __future__ import annotations

import importlib.util as _ilu
import re
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
STUDIO_ROOT = Path(__file__).resolve().parents[3]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import governed_path as gp  # noqa: E402

KERNEL_RE_PATH = STUDIO_ROOT / ".tropo" / "scripts" / "lib" / "spec_substrate_refs.py"


class ShapeAuthorityDrift(unittest.TestCase):
    def test_the_kernels_uid_re_agrees_with_the_vaults_uid_shapes(self) -> None:
        source = KERNEL_RE_PATH.read_text(encoding="utf-8")
        m = re.search(r'UID_RE = re\.compile\(r"([^"]+)"\)', source)
        self.assertIsNotNone(
            m, f"{KERNEL_RE_PATH} no longer declares UID_RE — update this gate's "
            "extraction to the new declaration shape")
        pattern = re.compile(m.group(1))

        spec = _ilu.spec_from_file_location("kernel_shape", KERNEL_RE_PATH)
        kernel = _ilu.module_from_spec(spec)
        sys.modules[spec.name] = kernel  # dataclasses resolves __module__ through sys.modules
        spec.loader.exec_module(kernel)

        # Every length the vault authority declares first-class must fullmatch
        # the kernel's pattern, and nothing else may.
        for length in sorted(gp.UID_SHAPES):
            sample = "a" * length
            self.assertTrue(
                bool(kernel.UID_RE.fullmatch(sample)),
                f"kernel UID_RE refuses the {length}-hex shape the vault authority "
                f"declares first-class — one fact, two readers, one drifted: "
                f"{KERNEL_RE_PATH} vs vault/tools/lib/governed_path.py")
        for wrong in sorted(set(range(max(gp.UID_SHAPES) + 5)) - gp.UID_SHAPES):
            self.assertFalse(
                bool(kernel.UID_RE.fullmatch("a" * wrong)),
                f"kernel UID_RE accepts a non-authority length ({wrong})")


if __name__ == "__main__":
    unittest.main()
