"""event_emitter.py — Shared auto-emission helper for Stream C retrofits (v1.58 C.1-C.7).

Thin wrapper around vault/tools/tropo-emit-event.py emit(). Each choke-point tool
imports auto_emit() and calls it after its substrate write. Non-blocking:
failures are logged to stderr and swallowed so the calling tool's exit code
is never affected by event emission failures.
"""
from __future__ import annotations
import sys
from pathlib import Path

_VAULT_ROOT = Path(__file__).resolve().parents[3]
_TOOLS_DIR = _VAULT_ROOT / "vault" / "tools"
_EMIT_TOOL = _TOOLS_DIR / "tropo-emit-event.py"

# Lazily loaded emit function from vault/tools/tropo-emit-event.py
_emit_fn = None


def _load_emit():
    global _emit_fn
    if _emit_fn is not None:
        return _emit_fn
    try:
        import importlib.util
        # tropo-emit-event.py does `from lib import event_identity`, resolved
        # against vault/tools/lib. Loading it by file path does not put its own
        # directory on sys.path, so that import fails unless we add it here —
        # and because this helper swallows failures by contract, the failure is
        # a silent no-op rather than a crash. Stream C emission was dead this
        # way, unnoticed, from the day the emit tool took that dependency.
        if str(_TOOLS_DIR) not in sys.path:
            sys.path.insert(0, str(_TOOLS_DIR))
        spec = importlib.util.spec_from_file_location("tropo_emit_event", str(_EMIT_TOOL))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _emit_fn = mod.emit
    except Exception as e:
        print(f"WARN: event_emitter could not load tropo-emit-event: {e}", file=sys.stderr)
        _emit_fn = None
    return _emit_fn


def auto_emit(
    event_type: str,
    source: str,
    source_uid: str,
    lifecycle: str = "evergreen",
    subject: str | None = None,
    data: dict | None = None,
    correlationid: str | None = None,
) -> None:
    """Emit one event non-blocking. Swallows all failures — never raises."""
    fn = _load_emit()
    if fn is None:
        return
    try:
        fn(event_type, source, source_uid, lifecycle,
           subject=subject, data=data, correlationid=correlationid)
    except Exception as e:
        print(f"WARN: auto_emit({event_type!r}) failed (non-blocking): {e}", file=sys.stderr)
