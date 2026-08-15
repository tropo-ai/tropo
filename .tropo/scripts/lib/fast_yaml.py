"""The kernel-tree spelling of `fast_yaml`. One implementation, one memo.

This studio has two `lib` packages — `vault/tools/lib/` and `.tropo/scripts/lib/`
— and which one `from lib import x` resolves to depends on who imported first.
`tropo-validate.py` says so in its own comments and loads several helpers by path
to dodge it.

That ambiguity is fine for stateless helpers and fatal for this one. `fast_yaml`
carries a PARSE MEMO, and the entire value of the memo is that every caller in a
process shares it: a validator run parses 108,000+ documents of which ~91% are
byte-identical repeats, and two copies of this module would mean two half-empty
caches and most of the saving lost.

So this file is a pointer, not a copy. It loads the canonical implementation at
`vault/tools/lib/fast_yaml.py` under a FIXED name in `sys.modules`, so importing
it by either spelling yields the same module object and therefore the same memo.
A duplicated implementation would also be a second place for the equivalence
argument to drift, and that argument is the reason the C loader is trusted at
all.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

#: One name, so both import spellings resolve to one module object.
_CANONICAL_MODULE_NAME = "tropo_fast_yaml_canonical"

_existing = sys.modules.get(_CANONICAL_MODULE_NAME)
if _existing is None:
    _canonical_path = (
        Path(__file__).resolve().parents[3] / "vault" / "tools" / "lib" / "fast_yaml.py"
    )
    if not _canonical_path.is_file():
        raise ImportError(
            f"canonical fast_yaml not found at {_canonical_path}; this module is a "
            "pointer and must not grow its own implementation"
        )
    _spec = importlib.util.spec_from_file_location(
        _CANONICAL_MODULE_NAME, _canonical_path
    )
    if _spec is None or _spec.loader is None:
        raise ImportError(f"could not load canonical fast_yaml at {_canonical_path}")
    _existing = importlib.util.module_from_spec(_spec)
    sys.modules[_CANONICAL_MODULE_NAME] = _existing
    _spec.loader.exec_module(_existing)

safe_load = _existing.safe_load
Loader = _existing.Loader
USING_C_LOADER = _existing.USING_C_LOADER
loader_name = _existing.loader_name

__all__ = ["safe_load", "Loader", "USING_C_LOADER", "loader_name"]
