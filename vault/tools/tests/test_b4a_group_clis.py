#!/usr/bin/env python3
"""Focused executable contract for the two governed B4a group CLIs.

Both tools are driven **as subprocesses** (never imported), exactly as an
operator or the pipeline would invoke them, inside throwaway
``tempfile.TemporaryDirectory()`` corpora.  The only in-process import is the
pure ``lib.group_contract.semantic_hash`` helper, used solely to author valid
group *source* fixtures (the authored source carries a ``semantic_hash`` the
library re-derives; it is stripped from the canonical ``groups.jsonl`` output).

What this suite proves (dev-spec ``vault/files/0bfa771d.md`` -- ``## Authority
and trust``, ``## Registry, resolver, and contextual audience``, ``##
Finalization and recovery``):

``tropo-group-authority.py``
    * ``build`` reproduces the locked authority vector AV1 byte-for-byte
      (public key, out-of-band fingerprint, signature, corpus + envelope
      digests) from the RFC 8032 test seed supplied only as an external key.
    * ``build`` -> ``accept-fingerprint`` (exact fingerprint) -> ``install`` is
      the positive path, and the registry it publishes passes the *other*
      tool's parity ``verify``.
    * A wrong out-of-band fingerprint refuses ``AUTHORITY_FINGERPRINT_MISMATCH``
      and records no trust (no trust-on-first-use).
    * ``verify`` against an unaccepted key refuses ``AUTHORITY_UNTRUSTED``.
    * ``install`` enforces the high-water rule: a genuine successor advances,
      while both a same-generation-different-digest replay and an older
      generation refuse ``AUTHORITY_ROLLBACK``.

``tropo-rebuild-group-registry.py``
    * ``rebuild`` is deterministic: two runs over one corpus emit byte-identical
      JSONL (and wrapper), and dropping a group leaves no stale row.
    * ``verify`` catches a mutated SQLite mirror as ``PROJECTION_MISMATCH``.
    * ``recover`` on a settled tree is a clean no-op.

The AV1 Ed25519 seed
``9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60`` is used
**only** as a test-supplied signing key.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.group_contract import semantic_hash  # noqa: E402

AUTHORITY_TOOL = TOOLS / "tropo-group-authority.py"
REGISTRY_TOOL = TOOLS / "tropo-rebuild-group-registry.py"


# --------------------------------------------------------------------------- #
# Locked authority vector AV1 literals (dev-spec "Locked authority vector AV1").#
# These are contract, not captured output: build must reproduce them exactly.  #
# --------------------------------------------------------------------------- #

AV1_SEED_HEX = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
MIKE_UID = "7b921d17"
MIKE_GROUP_UID = "11111111"
AV1_AUTHORITY_UID = "a1b2c3d4"
AV1_SIGNING_KEY_UID = "e5f6a7b8"

AV1_PUBLIC_KEY_B64 = "11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo="
AV1_FINGERPRINT = "21fe31dfa154a261626bf854046fd2271b7bed4b6abe45aa58877ef47f9721b9"
AV1_CORPUS_SHA256 = "8fac9a9ce622c9b265ee91c1f9176bb9ac6054ea3ee49763bf36b37a4516002f"
AV1_ENVELOPE_SHA256 = "14a2885fed3d99f671af09f2a1845f8e8fb65c6d1083a896582f2a64d6f62a8d"
AV1_PRINCIPAL_DIRECTORY_REVISION = (
    "sha256:9af1ee55eafdc2261db97211ab959c9ca9fdab66d5e70f5c24d178e58fa84d83"
)
AV1_SIGNATURE_B64 = (
    "zHzZdBPKO6Qaeq4bzLe0lBSiiwV5/bLsWdTMMSa15Eh1EMgVW479ps6UlBJIjZ/QrZnbXzao1MMD8JWnfrb3AA=="
)

# The exact canonical groups.jsonl line AV1 pins (semantic_hash is *not* present
# in the canonical output even though the authored source carries it).
AV1_GROUPS_JSONL_LINE = (
    b'{"uid":"11111111","type":"group","slug":"mike","title":"Mike",'
    b'"description":"Personal work visible to Mike.","owner":"7b921d17",'
    b'"members":["7b921d17"],"includes_groups":[],"status":"active","version":1}\n'
)

# Published, resolver-visible registry surfaces (corpus-root-relative POSIX).
PUBLISHED_REGISTRY = "vault/00-group-registry.jsonl"
PUBLISHED_SQLITE = "vault/00-group-registry.sqlite"
PUBLISHED_WRAPPER = "vault/00-group-registry-wrapper.json"
INSTALLED_PIN = ".tropo-studio/authorities/group-authority/installed.json"
TRUST_FILE = ".tropo-studio/trust/group-authorities.json"
SIGNED_ENVELOPE = "signed-envelope.json"


# --------------------------------------------------------------------------- #
# Fixture + subprocess helpers.                                                #
# --------------------------------------------------------------------------- #


def _authored_group(
    uid: str,
    slug: str,
    title: str,
    description: str,
    *,
    owner: str = MIKE_UID,
    members=None,
    includes=None,
    status: str = "active",
    version: int = 1,
) -> dict:
    """Author a valid group *source* object with a library-derived semantic hash."""

    obj = {
        "uid": uid,
        "type": "group",
        "slug": slug,
        "title": title,
        "description": description,
        "owner": owner,
        "members": [owner] if members is None else list(members),
        "includes_groups": list(includes or []),
        "status": status,
        "version": version,
    }
    obj["semantic_hash"] = semantic_hash(obj)
    return obj


def _av1_group() -> dict:
    return _authored_group("11111111", "mike", "Mike", "Personal work visible to Mike.")


AV1_PRINCIPAL_CLAIM = {
    "principal_uid": MIKE_UID,
    "principal_class": "human",
    "status": "active",
    "source_authority_uid": AV1_AUTHORITY_UID,
    "source_revision": "1",
}


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _seed_corpus(root: Path, groups) -> None:
    """Write group sources, the principal directory, and the external seed file."""

    for group in groups:
        _write_json(root / "groups" / f"{group['uid']}.json", group)
    _write_json(root / "principals.json", [AV1_PRINCIPAL_CLAIM])
    (root / "seed.hex").write_text(AV1_SEED_HEX, encoding="utf-8")


class _Result:
    """A subprocess outcome with lazily-parsed stdout (ok) / stderr (refusal)."""

    def __init__(self, completed: subprocess.CompletedProcess):
        self.returncode = completed.returncode
        self.stdout = completed.stdout
        self.stderr = completed.stderr

    def ok(self) -> dict:
        return json.loads(self.stdout)

    def error(self) -> dict:
        return json.loads(self.stderr)


def _run(tool: Path, *args: str) -> _Result:
    completed = subprocess.run(
        [sys.executable, str(tool), *args],
        capture_output=True,
        text=True,
    )
    return _Result(completed)


def _authority(*args: str) -> _Result:
    return _run(AUTHORITY_TOOL, *args)


def _registry(*args: str) -> _Result:
    return _run(REGISTRY_TOOL, *args)


def _build_argv(
    root: Path,
    *,
    generation: int = 1,
    out_dir: str | None = None,
    previous_envelope: Path | None = None,
) -> list[str]:
    argv = [
        "build",
        "--corpus-root",
        str(root),
        "--authority-uid",
        AV1_AUTHORITY_UID,
        "--signing-key-uid",
        AV1_SIGNING_KEY_UID,
        "--authority-generation",
        str(generation),
        "--private-group-uid",
        MIKE_GROUP_UID,
        "--signing-key-file",
        str(root / "seed.hex"),
        "--principals-file",
        str(root / "principals.json"),
    ]
    if out_dir is not None:
        argv += ["--out-dir", out_dir]
    if previous_envelope is not None:
        argv += ["--previous-envelope-file", str(previous_envelope)]
    return argv


def _accept_argv(root: Path, *, fingerprint: str) -> list[str]:
    return [
        "accept-fingerprint",
        "--corpus-root",
        str(root),
        "--authority-uid",
        AV1_AUTHORITY_UID,
        "--key-uid",
        AV1_SIGNING_KEY_UID,
        "--public-key",
        AV1_PUBLIC_KEY_B64,
        "--expected-fingerprint",
        fingerprint,
        "--accepted-by",
        MIKE_UID,
        "--accepted-at",
        "2026-01-01T00:00:00Z",
    ]


def _registry_argv(root: Path, command: str = "rebuild") -> list[str]:
    argv = [command, "--corpus-root", str(root)]
    if command == "rebuild":
        argv += [
            "--principals-file",
            str(root / "principals.json"),
            "--authority-uid",
            AV1_AUTHORITY_UID,
            "--principal-directory-revision",
            AV1_PRINCIPAL_DIRECTORY_REVISION,
            "--derive-revision",
        ]
    return argv


# --------------------------------------------------------------------------- #
# tropo-group-authority.py                                                     #
# --------------------------------------------------------------------------- #


class GroupAuthorityCliTests(unittest.TestCase):
    def test_build_reproduces_locked_av1_vector(self):
        """build derives + signs AV1 byte-for-byte from the external seed."""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_corpus(root, [_av1_group()])

            result = _authority(*_build_argv(root))
            self.assertEqual(result.returncode, 0, result.stderr)
            built = result.ok()

            self.assertEqual(built["status"], "built")
            self.assertEqual(built["authority_uid"], AV1_AUTHORITY_UID)
            self.assertEqual(built["authority_generation"], 1)
            self.assertEqual(built["signing_key_uid"], AV1_SIGNING_KEY_UID)
            self.assertEqual(built["public_key"], AV1_PUBLIC_KEY_B64)
            self.assertEqual(built["sha256_fingerprint"], AV1_FINGERPRINT)
            self.assertEqual(built["corpus_sha256"], AV1_CORPUS_SHA256)
            self.assertEqual(built["envelope_sha256"], AV1_ENVELOPE_SHA256)
            self.assertEqual(built["signature"], AV1_SIGNATURE_B64)
            self.assertIsNone(built["previous_envelope_sha256"])

            # The signed corpus artifact is the exact AV1 canonical line.
            bundle = root / built["bundle_dir"]
            self.assertEqual((bundle / "groups.jsonl").read_bytes(), AV1_GROUPS_JSONL_LINE)
            # The private seed is never copied into the Studio bundle.
            for artifact in bundle.iterdir():
                self.assertNotIn(AV1_SEED_HEX, artifact.read_text(encoding="utf-8", errors="ignore"))

    def test_build_accept_install_positive_path(self):
        """build -> accept-fingerprint(exact) -> install publishes a verifiable registry."""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_corpus(root, [_av1_group()])

            built = _authority(*_build_argv(root))
            self.assertEqual(built.returncode, 0, built.stderr)
            fingerprint = built.ok()["sha256_fingerprint"]
            self.assertEqual(fingerprint, AV1_FINGERPRINT)

            accepted = _authority(*_accept_argv(root, fingerprint=fingerprint))
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(accepted.ok()["status"], "accepted")

            verified = _authority(
                "verify", "--corpus-root", str(root), "--expected-fingerprint", fingerprint
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(verified.ok()["authority_uid"], AV1_AUTHORITY_UID)

            installed = _authority(
                "install", "--corpus-root", str(root), "--expected-fingerprint", fingerprint
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            pin = installed.ok()
            self.assertEqual(pin["status"], "installed")
            self.assertEqual(pin["authority_generation"], 1)
            self.assertEqual(pin["envelope_sha256"], AV1_ENVELOPE_SHA256)
            self.assertEqual(pin["registry_row_count"], 1)

            # Publisher surfaces exist and the machine-local pin was written.
            self.assertTrue((root / PUBLISHED_REGISTRY).exists())
            self.assertTrue((root / PUBLISHED_SQLITE).exists())
            self.assertTrue((root / PUBLISHED_WRAPPER).exists())
            self.assertTrue((root / INSTALLED_PIN).exists())

            # Cross-tool: the registry the authority published passes the
            # registry tool's independent parity verification.
            reg_verify = _registry("verify", "--corpus-root", str(root))
            self.assertEqual(reg_verify.returncode, 0, reg_verify.stderr)
            self.assertEqual(reg_verify.ok()["status"], "verified")

            # Re-installing the identical envelope is idempotent, not a rollback.
            again = _authority(
                "install", "--corpus-root", str(root), "--expected-fingerprint", fingerprint
            )
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(again.ok()["status"], "idempotent")

    def test_accept_fingerprint_wrong_value_refuses(self):
        """A mismatched out-of-band fingerprint refuses and records no trust."""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_corpus(root, [_av1_group()])
            self.assertEqual(_authority(*_build_argv(root)).returncode, 0)

            wrong_fingerprint = "0" * 64
            self.assertNotEqual(wrong_fingerprint, AV1_FINGERPRINT)
            refused = _authority(*_accept_argv(root, fingerprint=wrong_fingerprint))

            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(refused.error()["error"], "AUTHORITY_FINGERPRINT_MISMATCH")
            # No trust-on-first-use: the trust record must not have been created.
            self.assertFalse((root / TRUST_FILE).exists())

    def test_verify_untrusted_key_refuses(self):
        """verify never manufactures trust: an unaccepted key refuses."""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_corpus(root, [_av1_group()])
            self.assertEqual(_authority(*_build_argv(root)).returncode, 0)

            refused = _authority(
                "verify", "--corpus-root", str(root), "--expected-fingerprint", AV1_FINGERPRINT
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(refused.error()["error"], "AUTHORITY_UNTRUSTED")

    def test_install_same_generation_different_digest_rolls_back(self):
        """A same-generation replay with a different digest refuses AUTHORITY_ROLLBACK."""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_corpus(root, [_av1_group()])

            self.assertEqual(_authority(*_build_argv(root)).returncode, 0)
            self.assertEqual(
                _authority(*_accept_argv(root, fingerprint=AV1_FINGERPRINT)).returncode, 0
            )
            self.assertEqual(
                _authority(
                    "install",
                    "--corpus-root",
                    str(root),
                    "--expected-fingerprint",
                    AV1_FINGERPRINT,
                ).returncode,
                0,
            )

            # Re-author generation 1 with different semantics -> different digest.
            rogue = _authored_group(
                "11111111", "mike", "Mike", "A tampered description that shifts the digest."
            )
            _write_json(root / "groups" / "11111111.json", rogue)
            rogue_bundle = ".tropo-studio/authorities/group-authority/rogue-build"
            self.assertEqual(
                _authority(*_build_argv(root, generation=1, out_dir=rogue_bundle)).returncode, 0
            )

            refused = _authority(
                "install",
                "--corpus-root",
                str(root),
                "--bundle-dir",
                rogue_bundle,
                "--expected-fingerprint",
                AV1_FINGERPRINT,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(refused.error()["error"], "AUTHORITY_ROLLBACK")

    def test_install_high_water_advance_then_older_generation_rolls_back(self):
        """A genuine successor advances the high-water; a later older gen rolls back."""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_corpus(root, [_av1_group()])

            gen1_bundle = ".tropo-studio/authorities/group-authority/build-gen1"
            self.assertEqual(
                _authority(*_build_argv(root, generation=1, out_dir=gen1_bundle)).returncode, 0
            )
            self.assertEqual(
                _authority(*_accept_argv(root, fingerprint=AV1_FINGERPRINT)).returncode, 0
            )
            self.assertEqual(
                _authority(
                    "install",
                    "--corpus-root",
                    str(root),
                    "--bundle-dir",
                    gen1_bundle,
                    "--expected-fingerprint",
                    AV1_FINGERPRINT,
                ).returncode,
                0,
            )

            # Generation 2 chains onto gen1's envelope and genuinely advances the
            # corpus (a second active group), so it must install.
            _write_json(
                root / "groups" / "22222222.json",
                _authored_group("22222222", "mike-notes", "Mike Notes", "Second active group."),
            )
            gen2_bundle = ".tropo-studio/authorities/group-authority/build-gen2"
            gen1_envelope = root / gen1_bundle / SIGNED_ENVELOPE
            self.assertTrue(gen1_envelope.exists())
            self.assertEqual(
                _authority(
                    *_build_argv(
                        root,
                        generation=2,
                        out_dir=gen2_bundle,
                        previous_envelope=gen1_envelope,
                    )
                ).returncode,
                0,
            )
            advance = _authority(
                "install",
                "--corpus-root",
                str(root),
                "--bundle-dir",
                gen2_bundle,
                "--expected-fingerprint",
                AV1_FINGERPRINT,
            )
            self.assertEqual(advance.returncode, 0, advance.stderr)
            advanced = advance.ok()
            self.assertEqual(advanced["status"], "installed")
            self.assertEqual(advanced["authority_generation"], 2)
            self.assertEqual(advanced["registry_row_count"], 2)

            # Re-presenting the older generation-1 bundle now rolls back.
            refused = _authority(
                "install",
                "--corpus-root",
                str(root),
                "--bundle-dir",
                gen1_bundle,
                "--expected-fingerprint",
                AV1_FINGERPRINT,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(refused.error()["error"], "AUTHORITY_ROLLBACK")


# --------------------------------------------------------------------------- #
# tropo-rebuild-group-registry.py                                             #
# --------------------------------------------------------------------------- #


class RebuildGroupRegistryCliTests(unittest.TestCase):
    def _seed_registry_corpus(self, root: Path, groups) -> None:
        _seed_corpus(root, groups)

    def test_rebuild_is_byte_identical_twice(self):
        """Two deterministic rebuilds over one corpus emit identical bytes."""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_registry_corpus(
                root,
                [
                    _av1_group(),
                    _authored_group("22222222", "mike-notes", "Mike Notes", "Second active group."),
                ],
            )

            first = _registry(*_registry_argv(root))
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.ok()["row_count"], 2)
            jsonl_first = (root / PUBLISHED_REGISTRY).read_bytes()
            wrapper_first = (root / PUBLISHED_WRAPPER).read_bytes()

            second = _registry(*_registry_argv(root))
            self.assertEqual(second.returncode, 0, second.stderr)
            jsonl_second = (root / PUBLISHED_REGISTRY).read_bytes()
            wrapper_second = (root / PUBLISHED_WRAPPER).read_bytes()

            self.assertEqual(jsonl_first, jsonl_second)
            self.assertEqual(wrapper_first, wrapper_second)
            self.assertEqual(first.ok()["registry_jsonl_sha256"], second.ok()["registry_jsonl_sha256"])

            verified = _registry("verify", "--corpus-root", str(root))
            self.assertEqual(verified.returncode, 0, verified.stderr)

    def test_tampered_sqlite_refuses_projection_mismatch(self):
        """A mutated SQLite mirror is caught by verify as PROJECTION_MISMATCH."""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_registry_corpus(root, [_av1_group()])

            self.assertEqual(_registry(*_registry_argv(root)).returncode, 0)
            self.assertEqual(_registry("verify", "--corpus-root", str(root)).returncode, 0)

            connection = sqlite3.connect(str(root / PUBLISHED_SQLITE))
            try:
                connection.execute(
                    "UPDATE group_registry SET title = 'HACKED' WHERE group_uid = ?",
                    (MIKE_GROUP_UID,),
                )
                connection.commit()
            finally:
                connection.close()

            refused = _registry("verify", "--corpus-root", str(root))
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(refused.error()["error"], "PROJECTION_MISMATCH")

    def test_rebuild_drops_stale_rows(self):
        """Re-projection drops and rebuilds the table; a removed group leaves no row."""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_registry_corpus(
                root,
                [
                    _av1_group(),
                    _authored_group("22222222", "mike-notes", "Mike Notes", "Second active group."),
                ],
            )

            self.assertEqual(_registry(*_registry_argv(root)).ok()["row_count"], 2)

            (root / "groups" / "22222222.json").unlink()
            rebuilt = _registry(*_registry_argv(root))
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
            self.assertEqual(rebuilt.ok()["row_count"], 1)

            jsonl = (root / PUBLISHED_REGISTRY).read_text(encoding="utf-8")
            self.assertNotIn("22222222", jsonl)
            self.assertIn("11111111", jsonl)

            # The dropped row is gone from the SQLite mirror too, and parity holds.
            connection = sqlite3.connect(str(root / PUBLISHED_SQLITE))
            try:
                rows = connection.execute("SELECT group_uid FROM group_registry").fetchall()
            finally:
                connection.close()
            self.assertEqual(sorted(uid for (uid,) in rows), ["11111111"])
            self.assertEqual(_registry("verify", "--corpus-root", str(root)).returncode, 0)

    def test_recover_without_transaction_is_noop(self):
        """recover on a settled tree reports no outstanding transaction."""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_registry_corpus(root, [_av1_group()])
            self.assertEqual(_registry(*_registry_argv(root)).returncode, 0)

            recovered = _registry("recover", "--corpus-root", str(root))
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            outcome = recovered.ok()
            self.assertEqual(outcome["status"], "recovered")
            self.assertEqual(outcome["state"], "none")


if __name__ == "__main__":
    unittest.main()
