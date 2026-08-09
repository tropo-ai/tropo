"""Shared trust decision for mounted external-artifact projections.

Index derivation and template/body-shape exemption must agree on whether an
available projection is bound to exactly one authoritative sidecar.  This
module owns both the no-follow sidecar catalog and the pure binding decision so
neither caller can silently adopt a weaker interpretation.
"""
from __future__ import annotations

import hashlib
import os
import posixpath
import re
import stat
from pathlib import Path
from typing import Any, Optional

import yaml


UID_RE = re.compile(r'^[0-9a-f]{8}$')


def safe_mount_relative(value: Any) -> Optional[Path]:
    if not isinstance(value, str) or not value.strip():
        return None
    relative = Path(value.strip().replace('\\', '/'))
    if relative.is_absolute() or '..' in relative.parts:
        return None
    return relative


def mounted_relative_text(value: Any) -> Optional[str]:
    relative = safe_mount_relative(value)
    if relative is None or not relative.parts:
        return None
    return relative.as_posix()


def path_has_suffix(path: Path, suffix: Path) -> bool:
    return (
        len(path.parts) >= len(suffix.parts)
        and path.parts[-len(suffix.parts):] == suffix.parts
    )


def read_mounted_regular_bytes(
    mount_root: Path,
    relpath: str,
    *,
    max_bytes: int,
) -> tuple[str, Optional[bytes], Optional[int]]:
    """Read one contained regular file from stable no-follow descriptors."""
    relative = safe_mount_relative(relpath)
    if relative is None or not relative.parts:
        return 'unavailable', None, None
    nofollow = getattr(os, 'O_NOFOLLOW', 0)
    cloexec = getattr(os, 'O_CLOEXEC', 0)
    directory = getattr(os, 'O_DIRECTORY', 0)
    nonblock = getattr(os, 'O_NONBLOCK', 0)
    opened: list[int] = []
    try:
        root_fd = os.open(
            os.fspath(mount_root),
            os.O_RDONLY | directory | nofollow | cloexec,
        )
        opened.append(root_fd)
        if not stat.S_ISDIR(os.fstat(root_fd).st_mode):
            return 'unavailable', None, None
        parent_fd = root_fd
        for component in relative.parts[:-1]:
            child_fd = os.open(
                component,
                os.O_RDONLY | directory | nofollow | cloexec,
                dir_fd=parent_fd,
            )
            opened.append(child_fd)
            if not stat.S_ISDIR(os.fstat(child_fd).st_mode):
                return 'unavailable', None, None
            parent_fd = child_fd

        leaf = relative.parts[-1]
        named_before = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        source_fd = os.open(
            leaf,
            os.O_RDONLY | nofollow | cloexec | nonblock,
            dir_fd=parent_fd,
        )
        opened.append(source_fd)
        before = os.fstat(source_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(named_before.st_mode)
            or (before.st_dev, before.st_ino)
            != (named_before.st_dev, named_before.st_ino)
        ):
            return 'unavailable', None, None
        if before.st_size > max_bytes:
            return 'bounded', None, before.st_size

        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining > 0:
            chunk = os.read(source_fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b''.join(chunks)
        after = os.fstat(source_fd)
        named_after = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        identity_fields = (
            'st_dev',
            'st_ino',
            'st_mode',
            'st_size',
            'st_mtime_ns',
            'st_ctime_ns',
        )
        if (
            len(raw) != before.st_size
            or any(
                getattr(before, field) != getattr(after, field)
                for field in identity_fields
            )
            or any(
                getattr(before, field) != getattr(named_after, field)
                for field in ('st_dev', 'st_ino', 'st_mode', 'st_size')
            )
        ):
            return 'unavailable', None, None
        return 'ok', raw, before.st_size
    except (OSError, ValueError):
        return 'unavailable', None, None
    finally:
        for fd in reversed(opened):
            try:
                os.close(fd)
            except OSError:
                pass


def load_sidecar_catalog(
    mount_root: Path,
    *,
    max_bytes: int,
) -> tuple[
    dict[str, list[tuple[str, dict[str, Any], str]]],
    dict[str, tuple[dict[str, Any], str]],
]:
    """Load every readable sidecar while retaining duplicate UID candidates."""
    by_uid: dict[str, list[tuple[str, dict[str, Any], str]]] = {}
    by_path: dict[str, tuple[dict[str, Any], str]] = {}
    try:
        candidates = sorted(mount_root.rglob('.tropo-studio/*.tropo.md'))
    except OSError:
        candidates = []
    for sidecar in candidates:
        try:
            sidecar_relpath = sidecar.relative_to(mount_root).as_posix()
        except ValueError:
            continue
        status, raw, _size = read_mounted_regular_bytes(
            mount_root,
            sidecar_relpath,
            max_bytes=max_bytes,
        )
        if status != 'ok' or raw is None:
            continue
        try:
            text = raw.decode('utf-8')
        except UnicodeError:
            continue
        if not text.startswith('---'):
            continue
        end = text.find('\n---', 3)
        if end < 0:
            continue
        try:
            parsed = yaml.safe_load(text[3:end])
        except Exception:
            continue
        metadata = parsed if isinstance(parsed, dict) else {}
        sidecar_sha256 = hashlib.sha256(raw).hexdigest()
        by_path[sidecar_relpath] = (metadata, sidecar_sha256)
        uid = str(metadata.get('uid') or '')
        if UID_RE.fullmatch(uid):
            by_uid.setdefault(uid, []).append(
                (sidecar_relpath, metadata, sidecar_sha256)
            )
    return by_uid, by_path


def _sidecar_bound_source_relpath(sidecar_relpath: str) -> Optional[str]:
    sidecar = Path(sidecar_relpath)
    suffix = '.tropo.md'
    if (
        sidecar.parent.name != '.tropo-studio'
        or not sidecar.name.endswith(suffix)
    ):
        return None
    source_name = sidecar.name[:-len(suffix)]
    return mounted_relative_text(
        (sidecar.parent.parent / source_name).as_posix()
    )


def verify_available_projection_binding(
    record: dict,
    *,
    mount_uid: str,
    mount: Optional[dict],
    mount_root: Path,
    sidecars: dict[str, list[tuple[str, dict[str, Any], str]]],
    sidecars_by_path: dict[str, tuple[dict[str, Any], str]],
) -> dict[str, Any]:
    """Return the canonical available-projection sidecar trust decision."""
    uid = str(record.get('uid') or '')

    def invalid(
        reason: str,
        *,
        sidecar_input: Optional[tuple[str, str]] = None,
    ) -> dict[str, Any]:
        return {
            'status': 'untrusted',
            'reason': reason,
            'relpath': None,
            'sidecar_input': sidecar_input,
        }

    if record.get('type') != 'external-artifact':
        return invalid('projection-type-not-external-artifact')
    # `projection_authority: derived-only` is stamped by the post-migration
    # writer. A LEGACY projection predates the field entirely, and refusing it
    # here does not make anything safer -- it silently strips the content of a
    # file that is sitting readable on disk. On the studio's first real folder
    # mount that meant every one of Mike's notes disappeared from search and
    # from the crown with no signal.
    #
    # Trust here is about whether this projection genuinely belongs to this
    # mount. That is proven below by mount registration, adopted state, the
    # relpath, and the sidecar binding -- all of which still run unchanged. The
    # authority stamp is a FORMAT marker, and a missing format marker is a
    # migration state, not a trust failure. An entry that declares a DIFFERENT
    # authority is still refused. (metis-g99 2026-08-02; third of three gates
    # with this same predicate, the others in tropo-folder.py.)
    declared_authority = record.get('projection_authority')
    if declared_authority is not None and declared_authority != 'derived-only':
        return invalid('projection-authority-not-derived-only')
    if record.get('path') != f'vault/files/{uid}.md':
        return invalid('projection-path-mismatch')
    if not isinstance(mount, dict):
        return invalid('mount-unregistered')
    if mount.get('state') != 'adopted':
        return invalid('mount-not-adopted')

    record_relpath = mounted_relative_text(record.get('mount_relpath'))
    expected_sidecar: Optional[str] = None
    if record.get('mount_relpath') is not None and record_relpath is None:
        return invalid('mount-relpath-unsafe')
    if record_relpath is not None:
        relative = Path(record_relpath)
        expected_sidecar = (
            relative.parent
            / '.tropo-studio'
            / f'{relative.name}.tropo.md'
        ).as_posix()
        expected_entry = sidecars_by_path.get(expected_sidecar)
        if expected_entry is not None:
            expected_metadata, expected_sha256 = expected_entry
            if str(expected_metadata.get('uid') or '') != uid:
                return invalid(
                    'sidecar-uid-mismatch',
                    sidecar_input=(expected_sidecar, expected_sha256),
                )

    uid_candidates = sidecars.get(uid, [])
    if not uid_candidates:
        return invalid('sidecar-binding-missing')
    if len(uid_candidates) != 1:
        return invalid('sidecar-binding-ambiguous')
    sidecar_relpath, metadata, sidecar_sha256 = uid_candidates[0]
    sidecar_input = (sidecar_relpath, sidecar_sha256)
    if expected_sidecar is not None and sidecar_relpath != expected_sidecar:
        return invalid('sidecar-path-mismatch', sidecar_input=sidecar_input)
    if metadata.get('type') != 'external-artifact':
        return invalid('sidecar-type-mismatch', sidecar_input=sidecar_input)
    relpath = _sidecar_bound_source_relpath(sidecar_relpath)
    if relpath is None:
        return invalid('sidecar-location-invalid', sidecar_input=sidecar_input)
    if record_relpath is not None and record_relpath != relpath:
        return invalid(
            'mount-relpath-sidecar-mismatch',
            sidecar_input=sidecar_input,
        )

    raw_source_path = metadata.get('source_path')
    if not isinstance(raw_source_path, str) or not raw_source_path.strip():
        return invalid(
            'sidecar-source-path-missing',
            sidecar_input=sidecar_input,
        )
    source_path = Path(raw_source_path.strip().replace('\\', '/'))
    if source_path.is_absolute():
        absolute = Path(os.path.abspath(source_path))
        try:
            metadata_relpath = absolute.relative_to(mount_root).as_posix()
        except ValueError:
            metadata_relpath = (
                relpath
                if path_has_suffix(absolute, Path(relpath))
                else None
            )
    else:
        metadata_relpath = mounted_relative_text(
            posixpath.normpath(
                (Path(sidecar_relpath).parent / source_path).as_posix()
            )
        )
    if metadata_relpath != relpath:
        return invalid(
            'sidecar-source-path-mismatch',
            sidecar_input=sidecar_input,
        )

    source_sidecar = record.get('source_sidecar')
    if isinstance(source_sidecar, str) and source_sidecar.strip():
        recorded_sidecar = Path(source_sidecar.strip().replace('\\', '/'))
        if not path_has_suffix(recorded_sidecar, Path(sidecar_relpath)):
            return invalid(
                'projection-sidecar-path-mismatch',
                sidecar_input=sidecar_input,
            )

    return {
        'status': 'verified',
        'reason': '',
        'relpath': relpath,
        'sidecar_input': sidecar_input,
    }
