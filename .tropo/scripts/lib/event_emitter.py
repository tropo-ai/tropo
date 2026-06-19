"""event_emitter.py — Shared auto-emission helper for Stream C retrofits (v1.58 C.1-C.7).

Thin wrapper around vault/tools/ca90f098.py emit(). Each choke-point tool
imports auto_emit() and calls it after its substrate write. Non-blocking:
failures are logged to stderr and swallowed so the calling tool's exit code
is never affected by event emission failures.
"""
from __future__ import annotations
import sys
from pathlib import Path

_VAULT_ROOT = Path(__file__).resolve().parents[3]
_EMIT_TOOL = _VAULT_ROOT / "vault" / "tools" / "ca90f098.py"

# Lazily loaded emit function from vault/tools/ca90f098.py
_emit_fn = None


def _load_emit():
    global _emit_fn
    if _emit_fn is not None:
        return _emit_fn
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("ca90f098", str(_EMIT_TOOL))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _emit_fn = mod.emit
    except Exception as e:
        print(f"WARN: event_emitter could not load ca90f098: {e}", file=sys.stderr)
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
