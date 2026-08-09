"""Contract-C0 structural portability plants (dev-spec ``372ffdda``).

Covers the structural path/tree/ZIP portion of ``portable_tree.py``:

- canonical path validation at the locked limit triples and every illegal shape;
- the injected-normalizer seam (the module carries NO Unicode 15.1 table);
- ``lstat`` special-file/hardlink/symlink/FIFO refusal;
- the exact human-tree hash (determinism + empty-directory inclusion);
- deterministic canonical STORED packing; and
- the hostile-ZIP preflight matrix, each asserting a nonzero refusal, an
  absent-or-byte-identical destination, and no leftover staging directory.

The normalizer here is a small, fully deterministic TEST FIXTURE.  It is NOT a
Unicode 15.1 table and does not touch ``unicodedata``/``unicodedata2``; it maps
just enough segments to exercise ``NFKC(seg).casefold().rstrip(" .")`` behaviour
(ligatures, compatibility forms, casefold, trailing-dot/space folding, and a
normalization that yields a separator) that the collision key demands.
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "vault" / "tools" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import folder_sidecar as fs  # noqa: E402
import portable_tree as pt  # noqa: E402


# ---------------------------------------------------------------------------
# Deterministic injected fixture normalizer (NOT a Unicode 15.1 table).
# ---------------------------------------------------------------------------
# Each mapping is the intended NFKC-then-casefold image of that single scalar,
# hand-pinned so the suite is reproducible on any runtime regardless of the
# ambient Unicode database version.  A real host injects the hash-pinned 15.1
# table instead; this module deliberately provides no such data.
_FIXTURE_FOLD = {
    "\uFB01": "fi",   # ﬁ LATIN SMALL LIGATURE FI -> NFKC 'fi'
    "\u212A": "k",    # K KELVIN SIGN -> NFKC 'K' -> casefold 'k'
    "\uFF21": "a",    # Ａ FULLWIDTH LATIN CAPITAL A -> NFKC 'A' -> casefold 'a'
    "\u00DF": "ss",   # ß -> casefold 'ss'
    "\uFF0F": "/",    # ／ FULLWIDTH SOLIDUS -> NFKC '/'  (exercises rule 5)
}


def fixture_normalizer(segment: str) -> str:
    out: list[str] = []
    for ch in segment:
        if ch in _FIXTURE_FOLD:
            out.append(_FIXTURE_FOLD[ch])
        elif "A" <= ch <= "Z":
            out.append(ch.lower())
        else:
            out.append(ch)
    return "".join(out).rstrip(" .")


class _NormalizerObject:
    """A NormalizationTable protocol object (method form, not a bare callable)."""

    def normalize_segment(self, segment: str, /) -> str:
        return fixture_normalizer(segment)


def _path_with_total_bytes(total: int, *, components: int = 8) -> str:
    """Build an ASCII path of exactly ``total`` UTF-8 bytes, depth ``components``."""

    sum_comps = total - (components - 1)
    base = sum_comps // components
    sizes = [base] * (components - 1) + [sum_comps - base * (components - 1)]
    assert all(1 <= size <= pt.MAX_COMPONENT_BYTES for size in sizes), sizes
    path = "/".join("a" * size for size in sizes)
    assert len(path.encode("utf-8")) == total, (len(path), total)
    return path


# ---------------------------------------------------------------------------
# Configurable ZIP builder used to craft benign and hostile fixtures.
# ---------------------------------------------------------------------------
def build_zip(
    entries,
    *,
    disk: int = 0,
    cd_start_disk: int = 0,
    this_disk_count=None,
    total_count=None,
) -> bytes:
    """Assemble a ZIP with full control over every header field.

    Each entry is a dict with ``name`` and optional ``data``, ``method``,
    ``flag``, ``made_by``, ``external_attr``, ``crc``, ``comp``, ``uncomp``.
    """

    local_chunks: list[bytes] = []
    central_chunks: list[bytes] = []
    offset = 0
    for entry in entries:
        name = entry["name"].encode("utf-8")
        data = entry.get("data", b"")
        method = entry.get("method", 0)
        flag = entry.get("flag", 0)
        made_by = entry.get("made_by", (3 << 8) | 20)
        external_attr = entry.get("external_attr", 0o100644 << 16)
        if method == 8:
            comp = zlib.compressobj(9, zlib.DEFLATED, -15)
            raw = comp.compress(data) + comp.flush()
        else:
            raw = data
        crc = entry.get("crc", zlib.crc32(data) & 0xFFFFFFFF)
        comp_size = entry.get("comp", len(raw))
        uncomp_size = entry.get("uncomp", len(data))
        local = (
            struct.pack(
                "<4sHHHHHIIIHH",
                b"PK\x03\x04",
                20,
                flag,
                method,
                0,
                0x21,
                crc,
                comp_size,
                uncomp_size,
                len(name),
                0,
            )
            + name
            + raw
        )
        central = (
            struct.pack(
                "<4sHHHHHHIIIHHHHHII",
                b"PK\x01\x02",
                made_by,
                20,
                flag,
                method,
                0,
                0x21,
                crc,
                comp_size,
                uncomp_size,
                len(name),
                0,
                0,
                0,
                0,
                external_attr,
                offset,
            )
            + name
        )
        local_chunks.append(local)
        central_chunks.append(central)
        offset += len(local)

    central_bytes = b"".join(central_chunks)
    local_bytes = b"".join(local_chunks)
    count = len(entries)
    eocd = struct.pack(
        "<4sHHHHIIH",
        b"PK\x05\x06",
        disk,
        cd_start_disk,
        count if this_disk_count is None else this_disk_count,
        count if total_count is None else total_count,
        len(central_bytes),
        len(local_bytes),
        0,
    )
    return local_bytes + central_bytes + eocd


class _UnpackHarness(unittest.TestCase):
    """Base class giving each test an isolated scratch parent directory."""

    def setUp(self) -> None:
        self.scratch = tempfile.mkdtemp(prefix="c0-portability-")
        self.addCleanup(shutil.rmtree, self.scratch, ignore_errors=True)

    def fresh_dest(self, name: str = "dest") -> str:
        return os.path.join(self.scratch, name)

    def assert_unpack_refuses(self, archive: bytes, expected_code: str) -> None:
        """Unpack into an ABSENT destination; assert refusal + no residue."""

        dest = self.fresh_dest()
        with self.assertRaises(pt.C0Refusal) as ctx:
            pt.safe_unpack(archive, dest, normalizer=fixture_normalizer)
        self.assertEqual(ctx.exception.code, expected_code)
        self.assertFalse(os.path.exists(dest), "destination must remain absent")
        leftovers = [
            name
            for name in os.listdir(self.scratch)
            if name.startswith(pt.STAGING_PREFIX)
        ]
        self.assertEqual(leftovers, [], f"staging leftovers: {leftovers}")


# ---------------------------------------------------------------------------
# Path limit triples (component bytes, path bytes, depth).
# ---------------------------------------------------------------------------
class PathLimitTripleTests(unittest.TestCase):
    def test_component_bytes_triple(self) -> None:
        self.assertTrue(
            pt.derive_portability_key("a" * (pt.MAX_COMPONENT_BYTES - 1), fixture_normalizer)
        )
        self.assertTrue(
            pt.derive_portability_key("a" * pt.MAX_COMPONENT_BYTES, fixture_normalizer)
        )
        with self.assertRaises(pt.C0Refusal) as ctx:
            pt.derive_portability_key("a" * (pt.MAX_COMPONENT_BYTES + 1), fixture_normalizer)
        self.assertEqual(ctx.exception.code, pt.C0_PATH_TOO_LONG)

    def test_path_bytes_triple(self) -> None:
        for total in (pt.MAX_PATH_BYTES - 1, pt.MAX_PATH_BYTES):
            path = _path_with_total_bytes(total)
            self.assertTrue(pt.derive_portability_key(path, fixture_normalizer))
        over = _path_with_total_bytes(pt.MAX_PATH_BYTES + 1)
        with self.assertRaises(pt.C0Refusal) as ctx:
            pt.derive_portability_key(over, fixture_normalizer)
        self.assertEqual(ctx.exception.code, pt.C0_PATH_TOO_LONG)

    def test_depth_triple(self) -> None:
        for depth in (pt.MAX_COMPONENTS - 1, pt.MAX_COMPONENTS):
            path = "/".join(["a"] * depth)
            self.assertTrue(pt.derive_portability_key(path, fixture_normalizer))
        over = "/".join(["a"] * (pt.MAX_COMPONENTS + 1))
        with self.assertRaises(pt.C0Refusal) as ctx:
            pt.derive_portability_key(over, fixture_normalizer)
        self.assertEqual(ctx.exception.code, pt.C0_PATH_TOO_LONG)


# ---------------------------------------------------------------------------
# Every illegal path shape refuses with the right code.
# ---------------------------------------------------------------------------
class IllegalPathShapeTests(unittest.TestCase):
    CASES = {
        "../escape": pt.C0_PATH_INVALID,
        "a/../b": pt.C0_PATH_INVALID,
        "/etc/passwd": pt.C0_PATH_INVALID,
        "a//b": pt.C0_PATH_INVALID,
        "a/./b": pt.C0_PATH_INVALID,
        "a/": pt.C0_PATH_INVALID,
        "a\\b": pt.C0_PATH_INVALID,
        "C:/win": pt.C0_PATH_INVALID,
        "a\x00b": pt.C0_PATH_INVALID,
        "\x1fctrl": pt.C0_PATH_INVALID,
        "a<b": pt.C0_PATH_INVALID,
        "a>b": pt.C0_PATH_INVALID,
        'a"b': pt.C0_PATH_INVALID,
        "a|b": pt.C0_PATH_INVALID,
        "a?b": pt.C0_PATH_INVALID,
        "a*b": pt.C0_PATH_INVALID,
        "a:b": pt.C0_PATH_INVALID,
        "...": pt.C0_PATH_INVALID,            # normalization -> empty (rule 5)
        "a\uFF0Fb": pt.C0_PATH_INVALID,       # normalization -> separator (rule 5)
        ".git/config": pt.C0_RESERVED_NAMESPACE,
        ".tropo/x": pt.C0_RESERVED_NAMESPACE,
        ".tropo-studio/x": pt.C0_RESERVED_NAMESPACE,
        "con": pt.C0_RESERVED_NAMESPACE,
        "PRN": pt.C0_RESERVED_NAMESPACE,
        "com1.txt": pt.C0_RESERVED_NAMESPACE,
        "lpt9.log": pt.C0_RESERVED_NAMESPACE,
        "nul": pt.C0_RESERVED_NAMESPACE,
    }

    def test_illegal_shapes(self) -> None:
        for path, expected in self.CASES.items():
            with self.subTest(path=path):
                with self.assertRaises(pt.C0Refusal) as ctx:
                    pt.derive_portability_key(path, fixture_normalizer)
                self.assertEqual(ctx.exception.code, expected)

    def test_empty_nonroot_path_refuses(self) -> None:
        with self.assertRaises(pt.C0Refusal) as ctx:
            pt.derive_portability_key("", fixture_normalizer)
        self.assertEqual(ctx.exception.code, pt.C0_PATH_INVALID)


# ---------------------------------------------------------------------------
# Injected-normalizer seam (the module carries no Unicode table).
# ---------------------------------------------------------------------------
class InjectedNormalizerSeamTests(unittest.TestCase):
    def test_normalizer_is_required(self) -> None:
        with self.assertRaises(pt.C0Refusal) as ctx:
            pt.derive_portability_key("docs/report.md", None)
        self.assertEqual(ctx.exception.code, pt.C0_SCHEMA_INVALID)

    def test_root_key_is_empty(self) -> None:
        self.assertEqual(
            pt.derive_portability_key("", fixture_normalizer, is_root=True), ""
        )

    def test_key_is_nfkc_casefold_rstrip_joined(self) -> None:
        self.assertEqual(
            pt.derive_portability_key("DOCS/Report.MD", fixture_normalizer),
            "docs/report.md",
        )
        # Trailing space/dot fold (rstrip) and ligature/compat folds collide.
        self.assertEqual(
            pt.derive_portability_key("Report ", fixture_normalizer), "report"
        )
        self.assertEqual(
            pt.derive_portability_key("\uFB01le", fixture_normalizer), "file"
        )
        self.assertEqual(
            pt.derive_portability_key("\uFF21bc", fixture_normalizer), "abc"
        )

    def test_protocol_object_and_callable_agree(self) -> None:
        obj = _NormalizerObject()
        self.assertEqual(
            pt.derive_portability_key("Docs/File.md", obj),
            pt.derive_portability_key("Docs/File.md", fixture_normalizer),
        )

    def test_distinct_spellings_collide_on_key(self) -> None:
        # NFKC/casefold/rstrip makes these different raw paths share one key —
        # exactly the collision the profile must catch.
        a = pt.derive_portability_key("Report.md", fixture_normalizer)
        b = pt.derive_portability_key("report.md ", fixture_normalizer)
        c = pt.derive_portability_key("\uFF21/x", fixture_normalizer)
        d = pt.derive_portability_key("a/x", fixture_normalizer)
        self.assertEqual(a, b)
        self.assertEqual(c, d)

    def test_make_portability_key_adapter(self) -> None:
        key = pt.make_portability_key(fixture_normalizer)
        self.assertEqual(key("Docs/A.md", False), "docs/a.md")
        self.assertEqual(key("", True), "")


# ---------------------------------------------------------------------------
# lstat special-file / hardlink / symlink / FIFO refusal.
# ---------------------------------------------------------------------------
class SpecialFileScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tempfile.mkdtemp(prefix="c0-scan-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_symlink_refuses(self) -> None:
        os.symlink("/etc/hostname", os.path.join(self.root, "link"))
        with self.assertRaises(pt.C0Refusal) as ctx:
            pt.scan_tree(self.root, normalizer=fixture_normalizer)
        self.assertEqual(ctx.exception.code, pt.C0_SPECIAL_FILE)

    def test_hardlink_refuses(self) -> None:
        first = os.path.join(self.root, "a.txt")
        with open(first, "w") as handle:
            handle.write("payload")
        os.link(first, os.path.join(self.root, "b.txt"))
        with self.assertRaises(pt.C0Refusal) as ctx:
            pt.scan_tree(self.root, normalizer=fixture_normalizer)
        self.assertEqual(ctx.exception.code, pt.C0_HARDLINK)

    def test_fifo_refuses(self) -> None:
        os.mkfifo(os.path.join(self.root, "pipe"))
        with self.assertRaises(pt.C0Refusal) as ctx:
            pt.scan_tree(self.root, normalizer=fixture_normalizer)
        self.assertEqual(ctx.exception.code, pt.C0_SPECIAL_FILE)

    def test_reserved_component_in_tree_refuses(self) -> None:
        os.mkdir(os.path.join(self.root, ".git"))
        with self.assertRaises(pt.C0Refusal) as ctx:
            pt.scan_tree(self.root, normalizer=fixture_normalizer)
        self.assertEqual(ctx.exception.code, pt.C0_RESERVED_NAMESPACE)

    def test_clean_tree_scans(self) -> None:
        os.makedirs(os.path.join(self.root, "docs"))
        os.mkdir(os.path.join(self.root, "empty"))
        with open(os.path.join(self.root, "docs", "r.md"), "w") as handle:
            handle.write("hello")
        result = pt.scan_tree(self.root, normalizer=fixture_normalizer)
        self.assertEqual(result.file_count, 1)
        self.assertEqual(result.directory_count, 2)
        paths = {entry.payload_path for entry in result.entries}
        self.assertEqual(paths, {"", "docs", "empty", "docs/r.md"})


# ---------------------------------------------------------------------------
# Exact human-tree hash: determinism + empty-directory inclusion.
# ---------------------------------------------------------------------------
class HumanTreeHashTests(unittest.TestCase):
    def _entries(self):
        return [
            fs.PayloadEntry.directory("", ""),
            fs.PayloadEntry.directory("docs", "docs"),
            fs.PayloadEntry.file("docs/r.md", b"hello", "docs/r.md"),
        ]

    def test_deterministic_regardless_of_input_order(self) -> None:
        entries = self._entries()
        forward = pt.human_tree_hash(entries)
        backward = pt.human_tree_hash(list(reversed(entries)))
        self.assertEqual(forward, backward)

    def test_empty_directory_is_included(self) -> None:
        base = self._entries()
        with_empty = base + [fs.PayloadEntry.directory("empty", "empty")]
        self.assertNotEqual(pt.human_tree_hash(base), pt.human_tree_hash(with_empty))

    def test_exact_line_format_and_sort(self) -> None:
        entries = self._entries()
        # Reconstruct the specified bytes independently: raw-path-byte sorted,
        # "F NUL b64 NUL sha LF" for files and "D NUL b64 LF" for directories.
        import base64

        def line(entry):
            raw = entry.payload_path_bytes
            b64 = base64.b64encode(raw)
            if entry.record_kind == "file":
                return b"F\x00" + b64 + b"\x00" + entry.payload_sha256.encode() + b"\n"
            return b"D\x00" + b64 + b"\n"

        ordered = sorted(entries, key=lambda e: e.payload_path_bytes)
        expected = hashlib.sha256(b"".join(line(e) for e in ordered)).hexdigest()
        self.assertEqual(pt.human_tree_hash(entries), expected)

    def test_tropo_and_git_excluded_but_private_siblings_kept(self) -> None:
        base = self._entries()
        with_meta = base + [
            fs.PayloadEntry.file(".git/config", b"x", ".git/config"),
            fs.PayloadEntry.directory(".tropo", ".tropo"),
        ]
        self.assertEqual(pt.human_tree_hash(base), pt.human_tree_hash(with_meta))
        # A private-but-legal human sibling (dotfile) IS part of the hash.
        with_private = base + [fs.PayloadEntry.file(".secret", b"s", ".secret")]
        self.assertNotEqual(pt.human_tree_hash(base), pt.human_tree_hash(with_private))


# ---------------------------------------------------------------------------
# Deterministic canonical STORED pack.
# ---------------------------------------------------------------------------
class CanonicalPackTests(unittest.TestCase):
    def _members(self):
        return [
            pt.PackMember("b/", True),
            pt.PackMember("a/", True),
            pt.PackMember("a/f.txt", False, b"hello"),
            pt.PackMember("empty/", True),
        ]

    def test_repeated_pack_is_byte_identical(self) -> None:
        members = self._members()
        self.assertEqual(pt.canonical_pack(members), pt.canonical_pack(members))

    def test_pack_is_order_independent(self) -> None:
        members = self._members()
        shuffled = [members[2], members[0], members[3], members[1]]
        self.assertEqual(pt.canonical_pack(members), pt.canonical_pack(shuffled))

    def test_pack_metadata_is_canonical(self) -> None:
        archive = pt.canonical_pack(self._members())
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            self.assertIsNone(zf.testzip())
            names = [zi.filename for zi in zf.infolist()]
            self.assertEqual(names, sorted(names))  # sorted names
            for zi in zf.infolist():
                self.assertEqual(zi.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(zi.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(zi.extra, b"")
                self.assertEqual(zi.comment, b"")
                mode = zi.external_attr >> 16
                if zi.filename.endswith("/"):
                    self.assertEqual(mode & 0o777, 0o755)
                else:
                    self.assertEqual(mode & 0o777, 0o644)

    def test_pack_preserves_empty_directory(self) -> None:
        with zipfile.ZipFile(io.BytesIO(pt.canonical_pack(self._members()))) as zf:
            self.assertIn("empty/", zf.namelist())

    def test_pack_rejects_git(self) -> None:
        with self.assertRaises(pt.C0Refusal) as ctx:
            pt.canonical_pack([pt.PackMember(".git/config", False, b"x")])
        self.assertEqual(ctx.exception.code, pt.C0_RESERVED_NAMESPACE)

    def test_pack_rejects_duplicate(self) -> None:
        with self.assertRaises(pt.C0Refusal) as ctx:
            pt.canonical_pack(
                [pt.PackMember("a.txt", False, b"1"), pt.PackMember("a.txt", False, b"2")]
            )
        self.assertEqual(ctx.exception.code, pt.C0_ZIP_DUPLICATE)


# ---------------------------------------------------------------------------
# Positive round trip through pack -> safe_unpack.
# ---------------------------------------------------------------------------
class RoundTripTests(_UnpackHarness):
    def test_pack_then_unpack_reproduces_tree(self) -> None:
        src = os.path.join(self.scratch, "src")
        os.makedirs(os.path.join(src, "docs"))
        os.mkdir(os.path.join(src, "empty"))
        with open(os.path.join(src, "docs", "r.md"), "wb") as handle:
            handle.write("héllo".encode("utf-8"))
        scan = pt.scan_tree(src, normalizer=fixture_normalizer)

        members = []
        for entry in scan.entries:
            if entry.payload_path == "":
                continue
            if entry.record_kind == "directory":
                members.append(pt.PackMember(entry.payload_path, True))
            else:
                with open(os.path.join(src, *entry.payload_path.split("/")), "rb") as fh:
                    members.append(pt.PackMember(entry.payload_path, False, fh.read()))
        archive = pt.canonical_pack(members)

        dest = self.fresh_dest("out")
        result = pt.safe_unpack(archive, dest, normalizer=fixture_normalizer)
        self.assertEqual(result.tree_sha256, scan.tree_sha256)
        self.assertTrue(os.path.isdir(os.path.join(dest, "empty")))
        with open(os.path.join(dest, "docs", "r.md"), "rb") as handle:
            self.assertEqual(handle.read(), "héllo".encode("utf-8"))
        rescan = pt.scan_tree(dest, normalizer=fixture_normalizer)
        self.assertEqual(rescan.tree_sha256, scan.tree_sha256)

    def test_deflate_entry_round_trips(self) -> None:
        payload = b"The quick brown fox jumps over the lazy dog.\n" * 16
        archive = build_zip([{"name": "notes.txt", "data": payload, "method": 8}])
        dest = self.fresh_dest("out")
        pt.safe_unpack(archive, dest, normalizer=fixture_normalizer)
        with open(os.path.join(dest, "notes.txt"), "rb") as handle:
            self.assertEqual(handle.read(), payload)

    def test_c0_shaped_archive_keeps_tropo_metadata_but_excludes_it_from_hash(self) -> None:
        # A real C0 archive carries .tropo metadata alongside the payload; it
        # must unpack (never refused as a reserved payload component) while the
        # human-tree hash covers only the payload, per the spec exclusion.
        members = [
            pt.PackMember(".tropo/vault-manifest.md", False, b"manifest"),
            pt.PackMember(".tropo/folder-sidecars/v1/records/aaaaaaaa.json", False, b"{}\n"),
            pt.PackMember("payload/", True),
            pt.PackMember("payload/doc.md", False, b"body"),
        ]
        archive = pt.canonical_pack(members)
        dest = self.fresh_dest("out")
        result = pt.safe_unpack(archive, dest, normalizer=fixture_normalizer)
        self.assertTrue(os.path.isfile(os.path.join(dest, ".tropo", "vault-manifest.md")))
        self.assertTrue(os.path.isfile(os.path.join(dest, "payload", "doc.md")))
        payload_only = pt.human_tree_hash(
            [
                fs.PayloadEntry.directory("", ""),
                fs.PayloadEntry.directory("payload", "payload"),
                fs.PayloadEntry.file("payload/doc.md", b"body", "payload/doc.md"),
            ]
        )
        self.assertEqual(result.tree_sha256, payload_only)


# ---------------------------------------------------------------------------
# Hostile-ZIP preflight matrix.
# ---------------------------------------------------------------------------
class HostileZipMatrixTests(_UnpackHarness):
    def test_traversal(self) -> None:
        self.assert_unpack_refuses(
            build_zip([{"name": "../evil.txt", "data": b"x"}]), pt.C0_ZIP_TRAVERSAL
        )

    def test_absolute(self) -> None:
        self.assert_unpack_refuses(
            build_zip([{"name": "/etc/passwd", "data": b"x"}]), pt.C0_ZIP_ABSOLUTE
        )

    def test_drive_prefix(self) -> None:
        self.assert_unpack_refuses(
            build_zip([{"name": "C:/evil.txt", "data": b"x"}]), pt.C0_ZIP_DRIVE_PREFIX
        )

    def test_raw_duplicate(self) -> None:
        self.assert_unpack_refuses(
            build_zip(
                [{"name": "a.txt", "data": b"1"}, {"name": "a.txt", "data": b"2"}]
            ),
            pt.C0_ZIP_DUPLICATE,
        )

    def test_normalized_duplicate(self) -> None:
        self.assert_unpack_refuses(
            build_zip(
                [{"name": "Report.md", "data": b"1"}, {"name": "report.md", "data": b"2"}]
            ),
            pt.C0_PORTABILITY_COLLISION,
        )

    def test_file_directory_conflict(self) -> None:
        self.assert_unpack_refuses(
            build_zip([{"name": "a", "data": b"1"}, {"name": "a/b", "data": b"2"}]),
            pt.C0_ZIP_DUPLICATE,
        )

    def test_encrypted(self) -> None:
        self.assert_unpack_refuses(
            build_zip([{"name": "a.txt", "data": b"x", "flag": 0x0001}]),
            pt.C0_ZIP_ENCRYPTED,
        )

    def test_multi_disk(self) -> None:
        self.assert_unpack_refuses(
            build_zip([{"name": "a.txt", "data": b"x"}], disk=1),
            pt.C0_ZIP_UNSUPPORTED,
        )

    def test_unsupported_method(self) -> None:
        self.assert_unpack_refuses(
            build_zip([{"name": "a.txt", "data": b"x", "method": 12}]),
            pt.C0_ZIP_UNSUPPORTED,
        )

    def test_special_mode(self) -> None:
        # A symlink smuggled in via Unix external attributes.
        self.assert_unpack_refuses(
            build_zip([{"name": "lnk", "data": b"/etc", "external_attr": 0o120777 << 16}]),
            pt.C0_ZIP_SPECIAL_FILE,
        )

    def test_non_utf8_name(self) -> None:
        archive = build_zip([{"name": "a.txt", "data": b"x"}])
        # Corrupt the stored name bytes to invalid UTF-8 in both headers.
        archive = archive.replace(b"a.txt", b"a\xff.tx")
        self.assert_unpack_refuses(archive, pt.C0_PATH_INVALID)

    # --- each limit at limit+1 -------------------------------------------
    def test_over_count(self) -> None:
        # Declares one past the entry ceiling; refused from the EOCD count
        # before the (absent) records are ever materialized.
        over = pt.MAX_ZIP_ENTRIES + 1
        archive = build_zip(
            [{"name": "a.txt", "data": b"x"}],
            this_disk_count=over,
            total_count=over,
        )
        self.assert_unpack_refuses(archive, pt.C0_ZIP_LIMIT_COUNT)

    def test_over_size_per_entry(self) -> None:
        size = pt.MAX_ENTRY_EXPANDED_BYTES + 1
        archive = build_zip(
            [{"name": "big.bin", "uncomp": size, "comp": size, "crc": 0}]
        )
        self.assert_unpack_refuses(archive, pt.C0_ZIP_LIMIT_SIZE)

    def test_over_size_total(self) -> None:
        entry_size = pt.MAX_ENTRY_EXPANDED_BYTES  # exactly at the per-entry cap
        count = (pt.MAX_TOTAL_EXPANDED_BYTES // entry_size) + 1
        entries = [
            {"name": f"f{i}.bin", "uncomp": entry_size, "comp": entry_size, "crc": 0}
            for i in range(count)
        ]
        self.assert_unpack_refuses(build_zip(entries), pt.C0_ZIP_LIMIT_SIZE)

    def test_over_ratio(self) -> None:
        # Declares a 100+:1 expansion (zip bomb) — refused before streaming.
        uncomp = 100 * 1024 * 1024
        comp = uncomp // (pt.MAX_COMPRESSION_RATIO + 1)
        archive = build_zip(
            [{"name": "bomb.bin", "method": 8, "uncomp": uncomp, "comp": comp, "crc": 0}]
        )
        self.assert_unpack_refuses(archive, pt.C0_ZIP_LIMIT_RATIO)

    def test_over_depth(self) -> None:
        deep = "/".join(f"d{i}" for i in range(pt.MAX_COMPONENTS + 1)) + "/f.txt"
        self.assert_unpack_refuses(
            build_zip([{"name": deep, "data": b"x"}]), pt.C0_PATH_TOO_LONG
        )


# ---------------------------------------------------------------------------
# Destination + staging guarantees.
# ---------------------------------------------------------------------------
class DestinationAndStagingTests(_UnpackHarness):
    def test_existing_destination_is_left_byte_identical(self) -> None:
        dest = self.fresh_dest("out")
        os.mkdir(dest)
        with open(os.path.join(dest, "keep.txt"), "wb") as handle:
            handle.write(b"original")
        archive = pt.canonical_pack([pt.PackMember("new.txt", False, b"payload")])
        with self.assertRaises(pt.C0Refusal) as ctx:
            pt.safe_unpack(archive, dest, normalizer=fixture_normalizer)
        self.assertEqual(ctx.exception.code, pt.C0_DESTINATION_NOT_EMPTY)
        with open(os.path.join(dest, "keep.txt"), "rb") as handle:
            self.assertEqual(handle.read(), b"original")
        self.assertFalse(os.path.exists(os.path.join(dest, "new.txt")))

    def test_streaming_failure_cleans_staging_and_leaves_dest_absent(self) -> None:
        # Passes the whole preflight (local/central agree on a wrong CRC) but the
        # actual streamed bytes fail CRC, exercising post-preflight cleanup.
        archive = build_zip([{"name": "a.txt", "data": b"real-bytes", "crc": 0}])
        self.assert_unpack_refuses(archive, pt.C0_HASH_MISMATCH)

    def test_local_central_disagreement_refuses(self) -> None:
        archive = build_zip([{"name": "a.txt", "data": b"x"}])
        # Flip the local-header method to 8 while central stays 0.
        idx = archive.index(b"PK\x03\x04")
        mutable = bytearray(archive)
        mutable[idx + 8] = 8
        self.assert_unpack_refuses(bytes(mutable), pt.C0_ZIP_UNSUPPORTED)


if __name__ == "__main__":
    unittest.main()
