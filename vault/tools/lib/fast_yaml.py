"""One YAML entry point that uses libyaml's C scanner when the box has it.

WHY THIS EXISTS (talos-t40, 2026-08-09, velocity item 1 of the v1.86
retrospective).

A profiled full run of `tropo-validate.py` over this vault spent 701.7s of 794s
inside `yaml/composer.py::compose_node` — **88% of the validator is YAML
parsing**, and the validator is in turn 245s of the 278s full vault rebuild.
The top eleven entries by self-time were all `yaml/scanner.py` and
`yaml/reader.py`: `scan_plain`, `need_more_tokens`, `forward`, `peek`,
`check_token`. That is the PURE-PYTHON scanner, character by character.

PyYAML ships a C scanner built on libyaml and exposes it as `CSafeLoader`. It
was already installed here and nothing was using it. Measured on 600 real vault
frontmatter blocks: 0.758s pure-Python against 0.096s in C, **7.9x**.

EQUIVALENCE IS VERIFIED, NOT ASSUMED. Swapping a parser on the strength of a
benchmark would be the same move as trusting an instrument without reading it.
Every frontmatter block in the live vault was parsed both ways and compared:
**4,717 blocks, 4,717 identical results, zero value mismatches, and zero cases
where one loader raised and the other did not.** The check is kept as a test so
it runs against tomorrow's corpus too, not just the one I measured.

THE FALLBACK IS THE POINT, NOT A COURTESY. `CSafeLoader` exists only when PyYAML
was built against libyaml, and a customer studio is a zip on a machine we have
never seen. A hard import here would turn a performance improvement into a boot
failure for anyone without the C extension. So the import is guarded once, at
module load, and every caller gets a working loader either way. `USING_C_LOADER`
is exported so a diagnostic can report which one this machine got rather than
leaving it to be guessed.

What this module deliberately does NOT do is monkeypatch `yaml.safe_load`.
A global patch would make every call site lie about what it runs, and the next
agent reading `yaml.safe_load(...)` would have no way to know it had been
replaced. Call sites name this module explicitly.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any

import yaml

try:  # pragma: no cover - exercised by both branches in test_fast_yaml.py
    from yaml import CSafeLoader as _Loader

    USING_C_LOADER = True
except ImportError:  # pragma: no cover - the no-libyaml box
    from yaml import SafeLoader as _Loader  # type: ignore[assignment]

    USING_C_LOADER = False

#: The loader class in use, exported for callers that must pass a Loader= to a
#: PyYAML API this module does not wrap (e.g. `yaml.load_all`).
Loader = _Loader

__all__ = ["safe_load", "Loader", "USING_C_LOADER", "loader_name"]


#: Parsed documents, keyed on the SHA-256 of the source BYTES.
#:
#: MEASURED 2026-08-09 (talos-t40, velocity item 1 after Mike's ruling to follow
#: the measurement into the validator): one `tropo-validate` run called
#: `yaml.load` **159,087 times over 14,408 distinct documents**. 144,679 of those
#: — **90.9% of all parsing in a single run** — were byte-identical repeats,
#: because roughly thirty checks each independently re-read and re-parse the same
#: frontmatter. The worst single document was parsed 46 times; the median 4.
#:
#: This is a different lever from the incremental/registered validation brief
#: (5d192c3c) and a safer one. Skipping requires classifying every check as
#: per-entry or relational, and the brief is explicit that getting that wrong
#: reproduces the instrument-blindness it exists to kill. Memoizing a PURE parse
#: of IDENTICAL BYTES cannot change any finding at all: nothing is skipped, every
#: check still runs against every file, and the two runs are the same run.
#:
#: It is also immune to the brief's §4 rule-version hazard. That rule exists
#: because a cached VERDICT goes stale when a new rule is added. A parse is not a
#: verdict — the same bytes yield the same object under any rule set — so there
#: is no version to key on and no silent-blindness to ship.
#: THE MEMO IS ANCHORED TO THE `yaml` MODULE, not to this one, and that is the
#: only reliable place to put it. This studio has two `lib` packages, so
#: `fast_yaml` can legitimately be loaded more than once in a process — as
#: `lib.fast_yaml` from the vault tree, and through the kernel-tree pointer. Two
#: module objects mean two half-empty caches and most of the saving lost, which
#: is exactly what happened on the first attempt: both copies reported one entry
#: after being handed the same document.
#:
#: `yaml` is imported once per process by definition, so hanging the dict there
#: makes "one cache per process" true by construction rather than by an import
#: convention every future caller has to honour.
_MEMO_ATTR = "_tropo_fast_yaml_parse_memo"
_PARSE_MEMO: "dict[str, Any]" = getattr(yaml, _MEMO_ATTR, None)
if _PARSE_MEMO is None:
    _PARSE_MEMO = {}
    setattr(yaml, _MEMO_ATTR, _PARSE_MEMO)

#: Sized above the observed corpus (14,408) on purpose. The surface-meta memo in
#: index_surfaces clears WHOLESALE on overflow, and a cache that clears wholesale
#: thrashes hard the moment the corpus exceeds it — that is what made Python's
#: own 512-entry regex cache the largest line item in the rebuild profile.
_PARSE_MEMO_MAX = 32768


def safe_load(stream: Any) -> Any:
    """Drop-in for `yaml.safe_load`, on the fastest safe loader available.

    Same inputs, same outputs, same exceptions — see the equivalence evidence in
    the module docstring. Safety is unchanged: `CSafeLoader` is the C build of
    `SafeLoader`, not of the unsafe full loader, so no Python object
    construction is reachable from the document.

    Identical documents are parsed once and thereafter DEEP-COPIED out of the
    memo. The copy is the whole safety argument and is not an optimisation to be
    removed later: parsed frontmatter is a mutable dict, callers across ~30
    checks do mutate what they are handed, and returning a shared object would
    let one check's edit become another check's input. Measured, the copy costs
    ~10% of a parse and the hash ~1%, so a repeat costs about an eighth of the
    work it replaces — while `index_surfaces._load_surface_meta` had to hand back
    a shared reference and PROVE no caller mutates it, which is a proof that
    quietly expires the next time someone adds a caller.

    Failures are not cached: a document that raises must raise on every call, for
    the same reason a refusal must never be memoized.
    """
    try:
        raw = stream.encode("utf-8") if isinstance(stream, str) else bytes(stream)
    except (AttributeError, TypeError):
        # A file object or other stream: not hashable without consuming it, so
        # parse it directly rather than getting clever about rewinding.
        return yaml.load(stream, Loader=_Loader)

    key = hashlib.sha256(raw).hexdigest()
    cached = _PARSE_MEMO.get(key)
    if cached is not None:
        return copy.deepcopy(cached)

    parsed = yaml.load(stream, Loader=_Loader)
    if parsed is not None:
        if len(_PARSE_MEMO) >= _PARSE_MEMO_MAX:
            _PARSE_MEMO.clear()
        _PARSE_MEMO[key] = copy.deepcopy(parsed)
    return parsed


def loader_name() -> str:
    """Which scanner this machine actually got — for diagnostics, not control flow."""
    return "libyaml (C)" if USING_C_LOADER else "pure-Python"
