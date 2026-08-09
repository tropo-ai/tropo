#!/usr/bin/env python3
"""G2 Stage 1 acceptance suite for dev-spec 1a04bf0e/test-spec 834a6b6e.

The live Cursor plant is intentional: the harness helper/key is the known
positive reachability fixture.  On a Cursor Cloud machine it must successfully
sign under the fabricated Forger identity; an "unreachable" result fails.
"""
from __future__ import annotations

import base64
import concurrent.futures
import importlib.util
import inspect
import itertools
import json
import os
import random
import re
import shutil
import stat
import subprocess
import struct
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
CLI = TOOLS / "tropo-verify-authority.py"
CANARY_COMMIT = "b1cee30e"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import authority_chain as ac  # noqa: E402


def _harness_signer_configured() -> bool:
    """Can this machine produce a harness signature at all?

    WHY THIS EXISTS (metis-g101, 2026-08-04, Mike-directed). Until today this
    whole suite was an ENVIRONMENTAL SKIP on macOS. Argus A145 fixed the real
    blockers -- descriptor inheritance and an authority path that loaded the full
    activation history -- and all 112 tests became runnable off Cursor Cloud,
    which is a genuine improvement and closed the one verification gap of the
    lifecycle cutover.

    Eight of them then failed on Mike's Mac, all with the same
    `HARNESS_SIGNER_UNAVAILABLE`, because a bare macOS checkout has no
    `user.signingkey` / `gpg.format` / `commit.gpgsign` and Cursor Cloud does.
    Not a defect: the tests need a signer and say so honestly. But the effect was
    EIGHT PERMANENTLY RED TESTS ON THE MACHINE THE HUMAN ACTUALLY WORKS ON, for
    something no code change can fix.

    That is the exact shape G100 split `test_cutover_readiness.py` apart to
    avoid, and this studio has already paid thirty days for it once: Po's record
    sat open while a correct check reported it where nobody was looking. A
    permanently-red instrument teaches a crew to discount it, and the crew is
    right to -- which is how the next real red gets missed.

    So the skip is scoped to the eight tests that genuinely need a signer, rather
    than to the suite. 104 tests run everywhere including a bare checkout; 8 skip
    with a reason a human can read. Strictly better than the all-or-nothing skip
    this suite had this morning, and better than today's silent red.
    """
    try:
        ac.discover_harness_signer(ROOT)
    except Exception:
        return False
    return True


_NEEDS_SIGNER = unittest.skipUnless(
    _harness_signer_configured(),
    "needs a configured git signing key (user.signingkey/gpg.format) — Cursor "
    "Cloud has one, a bare macOS checkout does not. Not a defect; see "
    "_harness_signer_configured.",
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ACTIVATION_TOOL = _load("g2_write_activation_entry", TOOLS / "40b2f455.py")


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed:\n{result.stderr or result.stdout}"
        )
    return result


def _synthetic_ed25519_public_key(seed: int) -> str:
    algorithm = b"ssh-ed25519"
    point = seed.to_bytes(4, "big") * 8
    blob = (
        struct.pack(">I", len(algorithm))
        + algorithm
        + struct.pack(">I", len(point))
        + point
    )
    return "ssh-ed25519 " + base64.b64encode(blob).decode("ascii")


def _write_activation(
    vault_files: Path,
    *,
    uid: str,
    agent: str,
    generation: str,
    status: str,
    public_key: str | None,
    activated_at: str,
    activated_by: str = "user",
    name: str | None = None,
    agent_class: str = "executive",
    agent_root: str = "",
    predecessor_activation_uid: str | None = None,
    declare_predecessor: bool = True,
) -> Path:
    name = name or f"{agent}-{generation.lower()}"
    key_line = (
        f'agent_public_key: "{public_key}"\n'
        if public_key is not None
        else ""
    )
    predecessor_line = (
        (
            "predecessor_activation_uid: "
            f"{predecessor_activation_uid or 'null'}\n"
        )
        if public_key is not None and declare_predecessor
        else ""
    )
    path = vault_files / f"{uid}.md"
    path.write_text(
        "---\n"
        f"uid: {uid}\n"
        "type: activation\n"
        f"name: {name}\n"
        f"agent: {agent}\n"
        + (f"agent_root: {agent_root}\n" if agent_root else "")
        + f"agent_class: {agent_class}\n"
        f"generation: {generation}\n"
        f"activated_at: {activated_at}\n"
        f"activated_by: {activated_by}\n"
        f"status: {status}\n"
        f"{predecessor_line}"
        f"{key_line}"
        "---\n\n"
        f"# {name}\n",
        encoding="utf-8",
    )
    return path


def _write_agent_root(
    vault_files: Path,
    *,
    uid: str,
    agent: str,
    generation_prefix: str = "",
    agent_class: str = "executive",
    current_generation: str = "",
) -> Path:
    path = vault_files / f"{uid}.md"
    path.write_text(
        "---\n"
        f"uid: {uid}\n"
        "type: project\n"
        f"agent_slug: {agent}\n"
        f"agent_class: {agent_class}\n"
        + (f"generation_prefix: {generation_prefix}\n" if generation_prefix else "")
        + (f"current_generation: {current_generation}\n" if current_generation else "")
        + "status: active\n"
        "---\n",
        encoding="utf-8",
    )
    return path


def _write_unified_agent(
    repo: Path,
    *,
    uid: str,
    agent: str,
    agent_class: str,
    generation: str = "",
    current_activation_uid: str = "",
) -> Path:
    agents = repo / "vault" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    path = agents / f"{uid}.md"
    path.write_text(
        "---\n"
        f"uid: {uid}\n"
        "type: agent\n"
        f"agent: {agent}\n"
        f"agent_class: {agent_class}\n"
        + (f"generation: {generation}\n" if generation else "")
        + (
            f"current_activation_uid: {current_activation_uid}\n"
            if current_activation_uid
            else ""
        )
        + "status: ACTIVE\n"
        "---\n",
        encoding="utf-8",
    )
    return path


def _write_principal(
    vault_files: Path,
    *,
    uid: str,
    slug: str,
    status: str = "active",
    state: str = "active",
    public_key: str | None = None,
    may_sign_authority: bool = False,
    key_custody: str | None = None,
    revoked_at: str | None = None,
    aliases: tuple[str, ...] = (),
) -> Path:
    path = vault_files / f"{uid}.md"
    lines = [
        "---",
        f"uid: {uid}",
        "type: principal",
        f"slug: {slug}",
        f"name: {slug}",
        f"status: {status}",
        f"state: {state}",
        f"may_sign_authority: {'true' if may_sign_authority else 'false'}",
    ]
    if public_key:
        lines.append(f'authority_public_key: "{public_key}"')
    if key_custody:
        lines.append(f"key_custody: {key_custody}")
    if revoked_at:
        lines.append(f"revoked_at: {revoked_at}")
    if aliases:
        lines.append("slug_aliases:")
        lines.extend(f"  - {alias}" for alias in aliases)
    lines.extend(["---", "", f"# {slug}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


class GitFixture:
    def __init__(self, parent: Path):
        self.repo = parent / "repo"
        self.repo.mkdir()
        template = parent / "empty-template"
        template.mkdir()
        _git(self.repo, "init", "--quiet", "--template", str(template))
        _git(
            self.repo,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@test.local",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--allow-empty",
            "--no-gpg-sign",
            "-m",
            "fixture baseline",
        )

    @property
    def config_path(self) -> Path:
        common = Path(_git(self.repo, "rev-parse", "--git-common-dir").stdout.strip())
        if not common.is_absolute():
            common = self.repo / common
        return common.resolve() / "config"


def _tamper_commit_author(repo: Path, commit: str) -> str:
    original = subprocess.run(
        ["git", "cat-file", "commit", commit],
        cwd=str(repo),
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout
    tampered, count = re.subn(
        rb"^author [^\n]+$",
        b"author Tampered <tampered@test.local> 0 +0000",
        original,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise AssertionError("fixture commit has no author header")
    result = subprocess.run(
        ["git", "hash-object", "-t", "commit", "-w", "--stdin"],
        cwd=str(repo),
        input=tampered,
        capture_output=True,
        check=True,
        timeout=30,
    )
    return result.stdout.decode().strip()


def _tamper_commit_message(repo: Path, commit: str) -> str:
    original = subprocess.run(
        ["git", "cat-file", "commit", commit],
        cwd=str(repo),
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout
    header, separator, _body = original.partition(b"\n\n")
    if not separator:
        raise AssertionError("fixture commit has no message body")
    tampered = header + separator + b"tampered after signing\n"
    result = subprocess.run(
        ["git", "hash-object", "-t", "commit", "-w", "--stdin"],
        cwd=str(repo),
        input=tampered,
        capture_output=True,
        check=True,
        timeout=30,
    )
    return result.stdout.decode().strip()


def _external_signed_commit(
    repo: Path,
    signing_key: Path | ac.MintedAgentKey,
    *,
    author_name: str,
    author_email: str,
    message: str,
) -> str:
    environment = dict(os.environ)
    if isinstance(signing_key, ac.MintedAgentKey):
        key_value = f"key::{signing_key.public_key}"
        environment.update(
            {
                "SSH_AUTH_SOCK": str(signing_key.broker_socket),
                "SSH_AGENT_PID": str(signing_key.broker_pid),
            }
        )
    else:
        key_value = str(signing_key)
    result = subprocess.run(
        [
            "git",
            "-c",
            f"user.name={author_name}",
            "-c",
            f"user.email={author_email}",
            "-c",
            f"user.signingkey={key_value}",
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.program={shutil.which('ssh-keygen')}",
            "commit",
            "--allow-empty",
            "-S",
            "-m",
            message,
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=120,
        env=environment,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _append_unsigned_commits(repo: Path, count: int) -> None:
    parent = _git(repo, "rev-parse", "HEAD").stdout.strip()
    expected_old = parent
    tree = _git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    for index in range(count):
        parent = _git(
            repo,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@test.local",
            "commit-tree",
            tree,
            "-p",
            parent,
            "-m",
            f"unsigned filler {index}",
        ).stdout.strip()
    _git(repo, "update-ref", "HEAD", parent, expected_old)


def _write_unsupported_pgp_commit(repo: Path) -> str:
    tree = _git(repo, "write-tree").stdout.strip()
    parent = _git(repo, "rev-parse", "HEAD").stdout.strip()
    payload = (
        f"tree {tree}\n"
        f"parent {parent}\n"
        "author PGP User <pgp@test.local> 0 +0000\n"
        "committer PGP User <pgp@test.local> 0 +0000\n"
        "gpgsig -----BEGIN PGP SIGNATURE-----\n"
        " fake-pgp-payload\n"
        " -----END PGP SIGNATURE-----\n"
        "\n"
        "unsupported PGP fixture\n"
    )
    result = subprocess.run(
        ["git", "hash-object", "-t", "commit", "-w", "--stdin"],
        cwd=str(repo),
        input=payload,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return result.stdout.strip()


class AuthorityFixture(unittest.TestCase):
    def setUp(self):
        session_root = ac.session_key_root()
        self.preexisting_session_dirs = (
            set(session_root.iterdir()) if session_root.is_dir() else set()
        )
        self.temporary = tempfile.TemporaryDirectory(prefix="g2-authority-tests-")
        self.root = Path(self.temporary.name)
        self.git = GitFixture(self.root)
        self.vault_files = self.git.repo / "vault" / "files"
        self.vault_files.mkdir(parents=True)
        self.minted_uids: set[str] = set()
        _write_principal(
            self.vault_files,
            uid="70000000",
            slug="user",
        )

    def tearDown(self):
        for uid in self.minted_uids:
            try:
                ac.remove_agent_keypair(uid)
            except ac.AuthorityChainError:
                pass
        session_root = ac.session_key_root()
        if session_root.is_dir():
            for broker_dir in set(session_root.iterdir()) - self.preexisting_session_dirs:
                # Broker directories are named <activation-uid>-<random>. Test
                # helpers that call op_open() do not flow through mint_record(),
                # so clean those session-scoped brokers explicitly.
                activation_uid = broker_dir.name.split("-", 1)[0]
                if re.fullmatch(r"[0-9a-f]{8}", activation_uid):
                    try:
                        ac.remove_agent_keypair(activation_uid)
                    except ac.AuthorityChainError:
                        pass
        self.temporary.cleanup()

    def mint_record(
        self,
        uid: str,
        agent: str,
        generation: str,
        *,
        status: str = "active",
        activated_at: str = "2026-07-26T12:00:00Z",
        activated_by: str = "user",
    ) -> tuple[ac.ActivationRecord, ac.MintedAgentKey]:
        minted = ac.mint_agent_keypair(
            uid,
            agent,
            generation,
        )
        self.minted_uids.add(uid)
        _write_activation(
            self.vault_files,
            uid=uid,
            agent=agent,
            generation=generation,
            status=status,
            public_key=minted.public_key,
            activated_at=activated_at,
            activated_by=activated_by,
        )
        records = ac.load_activation_entries(self.vault_files)
        return next(record for record in records if record.uid == uid), minted


class _ActivationMintFixture(AuthorityFixture):
    """Shared setup for the mint-path suites. Holds no tests of its own.

    Split out 2026-08-03 so TestProvisionalBirth can reuse the fixture without
    inheriting TestCriterion1ActivationMint's cases — which it did briefly, and
    re-ran the entire strict-mode suite in non-strict mode.
    """

    def _open_args(self, **overrides):
        values = {
            "agent": "demo",
            "generation": "D1",
            "model": "test-model",
            "platform": "test-platform",
            "agent_root": "11111111",
            "agent_class": "executive",
            "activated_by": "user",
            "member_of": "",
            "commissioned_purpose": "",
            "run_folder": "playbook-runs/demo-D1",
            "stale_threshold_hours": None,
            # strict=True because these cases exist to prove each identity check
            # DETECTS its violation, and refusal is how a detection is observable
            # in a test. As of 2026-08-03 refusal is no longer the DEFAULT
            # consequence of detection: Mike ruled that a failed identity check
            # marks a generation provisional and lets it work, never refuses
            # existence (three consecutive Metis generations were each blocked at
            # birth by a different check in one family). --strict preserves
            # refuse-on-first-finding for exactly this audience -- validators, CI
            # and these tests. The default path is covered separately by
            # TestProvisionalBirth below; do not "fix" a provisional-path test by
            # setting strict here.
            "strict": True,
        }
        values.update(overrides)
        return types.SimpleNamespace(**values)

    def _patch_tool(self, minted_uid: str = "feed0001"):
        fake_history = types.ModuleType("lib.tropo_git_history")
        fake_history.boot_reconcile_if_dirty = lambda *args, **kwargs: (True, "clean")
        fake_history.activation_close_commit = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("keyed G2 lifecycle commit used the plain commit fallback")
        )
        fake_history.signal_commit_failure = lambda *args, **kwargs: None
        fake_emitter = types.ModuleType("lib.event_emitter")
        fake_emitter.auto_emit = lambda *args, **kwargs: None
        return (
            patch.object(ACTIVATION_TOOL, "VAULT_ROOT", self.git.repo),
            patch.object(ACTIVATION_TOOL, "VAULT_FILES", self.vault_files),
            patch.object(
                ACTIVATION_TOOL,
                "VAULT_AGENTS",
                self.git.repo / "vault" / "agents",
            ),
            patch.object(
                ACTIVATION_TOOL,
                "LOCK_DIR",
                self.git.repo / ".tropo-studio" / "locks",
            ),
            patch.object(ACTIVATION_TOOL, "load_existing_uids", return_value=set()),
            patch.object(ACTIVATION_TOOL, "mint_uid", return_value=minted_uid),
            patch.dict(
                sys.modules,
                {
                    "lib.tropo_git_history": fake_history,
                    "lib.event_emitter": fake_emitter,
                },
            ),
        )

    def _run_patched(self, callable_, *, minted_uid="feed0001"):
        patches = self._patch_tool(minted_uid)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[
            5
        ], patches[6]:
            return callable_()


class TestCriterion1ActivationMint(_ActivationMintFixture):
    def test_open_mints_and_binds_public_half_without_private_vault_material(self):
        run_folder = self.root / "playbook-runs" / "demo-D1"
        run_folder.mkdir(parents=True)
        caller_key = ac.mint_agent_keypair("bad00001", "caller", "C1")
        self.minted_uids.add("bad00001")

        result = self._run_patched(
            lambda: ACTIVATION_TOOL.op_open(
                self._open_args(agent_public_key=caller_key.public_key)
            )
        )
        self.assertEqual(result, 0)

        entry = self.vault_files / "feed0001.md"
        text = entry.read_text(encoding="utf-8")
        self.assertIn("agent_public_key: \"ssh-ed25519 ", text)
        record = ac.load_activation_entries(self.vault_files)[0]
        self.minted_uids.add("feed0001")
        broker = ac.activation_signing_broker(
            "feed0001",
            expected_public_key=record.agent_public_key,
        )
        self.assertEqual(
            record.public_key.blob,
            ac.parse_openssh_public_key(broker.public_key).blob,
        )
        self.assertNotEqual(
            record.public_key.blob,
            ac.parse_openssh_public_key(caller_key.public_key).blob,
        )

        # The private material is session-local only.  Neither the Vault nor the
        # activation run folder contains an OpenSSH private-key block.
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            payload = path.read_bytes()
            self.assertNotIn(b"BEGIN OPENSSH PRIVATE KEY", payload, str(path))
        self.assertFalse(any(run_folder.rglob("id_ed25519")))
        regular_runtime_files = [
            path for path in broker.socket_path.parent.iterdir() if path.is_file()
        ]
        self.assertEqual(
            [path.name for path in regular_runtime_files],
            [ac.BROKER_METADATA_NAME],
        )
        self.assertNotIn(
            b"BEGIN OPENSSH PRIVATE KEY",
            regular_runtime_files[0].read_bytes(),
        )

    def test_open_cli_has_no_caller_held_public_key_option(self):
        result = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "40b2f455.py"),
                "open",
                "--agent",
                "demo",
                "--generation",
                "D1",
                "--model",
                "test-model",
                "--platform",
                "test-platform",
                "--agent-root",
                "11111111",
                "--agent-class",
                "executive",
                "--activated-by",
                "user",
                "--agent-public-key",
                "caller-held-key",
            ],
            cwd=str(self.git.repo),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments: --agent-public-key", result.stderr)

    def test_op_update_refuses_identity_key_lifecycle_fields_and_aliases(self):
        path = _write_activation(
            self.vault_files,
            uid="f00000a1",
            agent="demo",
            generation="D1",
            status="active",
            public_key=None,
            activated_at="2026-07-26T12:00:00Z",
        )
        original = path.read_bytes()
        fields = sorted(
            ACTIVATION_TOOL.LIFECYCLE_FIELDS
            | ACTIVATION_TOOL.LIFECYCLE_FIELD_ALIASES
            | {
                "agent-public-key",
                "agentPublicKey",
                "agent.public.key",
                "public_key",
                "signing-key",
                "activationUid",
            }
        )
        for field_name in fields:
            with self.subTest(field=field_name):
                args = types.SimpleNamespace(
                    activation_uid="f00000a1",
                    field=field_name,
                    value="attacker-controlled",
                )
                with self.assertRaises(SystemExit) as raised:
                    self._run_patched(lambda: ACTIVATION_TOOL.op_update(args))
                self.assertEqual(raised.exception.code, 1)
                self.assertEqual(path.read_bytes(), original)

    def test_canonical_class_binding_refuses_laundering_and_unregistered_opaque_slugs(self):
        _write_agent_root(
            self.vault_files,
            uid="11111111",
            agent="demo",
            generation_prefix="D",
            agent_class="executive",
        )
        _write_unified_agent(
            self.git.repo,
            uid="a1111111",
            agent="demo",
            agent_class="executive",
        )
        for index, laundering_class in enumerate(
            ("sa", "worker", "child-agent", "pipeline")
        ):
            uid = f"f20000{index:02x}"
            with self.subTest(laundering_class=laundering_class):
                with self.assertRaises(SystemExit) as raised:
                    self._run_patched(
                        lambda laundering_class=laundering_class: ACTIVATION_TOOL.op_open(
                            self._open_args(
                                generation="opaque",
                                agent_class=laundering_class,
                            )
                        ),
                        minted_uid=uid,
                    )
                self.assertEqual(raised.exception.code, 1)
                self.assertFalse((self.vault_files / f"{uid}.md").exists())
                with self.assertRaises(ac.AuthorityChainError):
                    ac.activation_signing_broker(uid)

        for index, opaque_class in enumerate(("sa", "pipeline")):
            agent = f"unregistered-{opaque_class}"
            uid = f"f20001{index:02x}"
            with self.subTest(unregistered=opaque_class):
                with self.assertRaises(SystemExit) as raised:
                    self._run_patched(
                        lambda agent=agent, opaque_class=opaque_class: ACTIVATION_TOOL.op_open(
                            self._open_args(
                                agent=agent,
                                generation="opaque",
                                agent_class=opaque_class,
                                agent_root="99999999",
                                run_folder="",
                            )
                        ),
                        minted_uid=uid,
                    )
                self.assertEqual(raised.exception.code, 1)
                self.assertFalse((self.vault_files / f"{uid}.md").exists())

    def test_every_registered_class_opens_only_under_its_canonical_class(self):
        cases = (
            ("executive", "E1", "E"),
            ("director", "D1", "D"),
            ("cosmo", "C1", "C"),
            ("tropo", "T1", "T"),
            ("sa", "sa.opaque/restart", ""),
            ("worker", "worker.opaque/restart", ""),
            ("child-agent", "child.opaque/restart", ""),
            ("pipeline", "pipeline.opaque/restart", ""),
        )
        for index, (agent_class, generation, prefix) in enumerate(cases):
            agent = f"class-{agent_class}"
            root_uid = f"e20000{index:02x}"
            activation_uid = f"d20000{index:02x}"
            _write_agent_root(
                self.vault_files,
                uid=root_uid,
                agent=agent,
                generation_prefix=prefix,
                agent_class=agent_class,
            )
            _write_unified_agent(
                self.git.repo,
                uid=f"c20000{index:02x}",
                agent=agent,
                agent_class=agent_class,
            )
            with self.subTest(agent_class=agent_class):
                result = self._run_patched(
                    lambda agent=agent, agent_class=agent_class, generation=generation, root_uid=root_uid: ACTIVATION_TOOL.op_open(
                        self._open_args(
                            agent=agent,
                            generation=generation,
                            agent_class=agent_class,
                            agent_root=root_uid,
                            run_folder="",
                        )
                    ),
                    minted_uid=activation_uid,
                )
                self.assertEqual(result, 0)
                record = next(
                    record
                    for record in ac.load_canonical_activation_entries(self.git.repo)
                    if record.uid == activation_uid
                )
                self.assertEqual(record.canonical_agent_class, agent_class)
                self.assertEqual(
                    bool(record.agent_public_key),
                    agent_class != "pipeline",
                )
                if record.agent_public_key:
                    self.minted_uids.add(activation_uid)
                    self.assertTrue(record.predecessor_link_declared)
                    self.assertIsNone(record.predecessor_activation_uid)
                else:
                    self.assertFalse(record.predecessor_link_declared)

    def test_open_derives_predecessor_uid_for_opaque_keyed_classes(self):
        cases = ("sa", "worker", "child-agent")
        for index, agent_class in enumerate(cases):
            agent = f"linked-{agent_class}"
            root_uid = f"e21000{index:02x}"
            predecessor_uid = f"d21000{index:02x}"
            successor_uid = f"d22000{index:02x}"
            _write_agent_root(
                self.vault_files,
                uid=root_uid,
                agent=agent,
                agent_class=agent_class,
            )
            _write_unified_agent(
                self.git.repo,
                uid=f"c21000{index:02x}",
                agent=agent,
                agent_class=agent_class,
            )
            predecessor_key = ac.mint_agent_keypair(
                predecessor_uid,
                agent,
                "opaque-previous",
            )
            self.minted_uids.add(predecessor_uid)
            _write_activation(
                self.vault_files,
                uid=predecessor_uid,
                agent=agent,
                generation="opaque-previous",
                status="retired",
                public_key=predecessor_key.public_key,
                activated_at="2026-07-25T12:00:00Z",
                agent_class=agent_class,
            )
            with self.subTest(agent_class=agent_class):
                result = self._run_patched(
                    lambda agent=agent, agent_class=agent_class, root_uid=root_uid: ACTIVATION_TOOL.op_open(
                        self._open_args(
                            agent=agent,
                            generation="opaque-next",
                            agent_class=agent_class,
                            agent_root=root_uid,
                            run_folder="",
                        )
                    ),
                    minted_uid=successor_uid,
                )
                self.assertEqual(result, 0)
                self.minted_uids.add(successor_uid)
                successor = next(
                    record
                    for record in ac.load_canonical_activation_entries(self.git.repo)
                    if record.uid == successor_uid
                )
                self.assertEqual(
                    successor.predecessor_activation_uid,
                    predecessor_uid,
                )
                self.assertTrue(successor.predecessor_link_declared)
                self.assertTrue(
                    ac.analyze_activations(
                        ac.load_canonical_activation_entries(self.git.repo)
                    ).is_gate_valid(successor_uid)
                )

        blocked_agent = "linked-unresolvable-sa"
        _write_agent_root(
            self.vault_files,
            uid="e21000ff",
            agent=blocked_agent,
            agent_class="sa",
        )
        blocked_key = ac.mint_agent_keypair(
            "d21000ff",
            blocked_agent,
            "opaque-previous",
        )
        self.minted_uids.add("d21000ff")
        _write_activation(
            self.vault_files,
            uid="d21000ff",
            agent=blocked_agent,
            generation="opaque-previous",
            status="retired",
            public_key=blocked_key.public_key,
            activated_at="2026-07-25T12:00:00Z",
            agent_class="sa",
            predecessor_activation_uid="deadbeef",
        )
        with self.assertRaises(SystemExit) as blocked:
            self._run_patched(
                lambda: ACTIVATION_TOOL.op_open(
                    self._open_args(
                        agent=blocked_agent,
                        generation="opaque-next",
                        agent_class="sa",
                        agent_root="e21000ff",
                        run_folder="",
                    )
                ),
                minted_uid="d22000ff",
            )
        self.assertEqual(blocked.exception.code, 1)
        self.assertFalse((self.vault_files / "d22000ff.md").exists())
        with self.assertRaises(ac.AuthorityChainError):
            ac.activation_signing_broker("d22000ff")

        missing_agent = "linked-hard-deleted-sa"
        _write_agent_root(
            self.vault_files,
            uid="e21000fe",
            agent=missing_agent,
            agent_class="sa",
        )
        _write_unified_agent(
            self.git.repo,
            uid="c21000fe",
            agent=missing_agent,
            agent_class="sa",
            current_activation_uid="deadbeef",
        )
        with self.assertRaises(SystemExit) as hard_deleted:
            self._run_patched(
                lambda: ACTIVATION_TOOL.op_open(
                    self._open_args(
                        agent=missing_agent,
                        generation="opaque-next",
                        agent_class="sa",
                        agent_root="e21000fe",
                        run_folder="",
                    )
                ),
                minted_uid="d22000fe",
            )
        self.assertEqual(hard_deleted.exception.code, 1)
        self.assertFalse((self.vault_files / "d22000fe.md").exists())
        with self.assertRaises(ac.AuthorityChainError):
            ac.activation_signing_broker("d22000fe")

    def test_production_sa_skeptic_hard_deleted_predecessor_refuses_before_mint(self):
        agent = "sa.skeptic"
        root_uid = "e2477000"
        predecessor_uid = "d2477001"
        successor_uid = "d2477002"
        _write_agent_root(
            self.vault_files,
            uid=root_uid,
            agent=agent,
            agent_class="sa",
        )
        _write_unified_agent(
            self.git.repo,
            uid="c2477000",
            agent=agent,
            agent_class="sa",
            current_activation_uid=predecessor_uid,
        )
        predecessor_key = ac.mint_agent_keypair(
            predecessor_uid,
            agent,
            "sa.skeptic-001",
        )
        self.minted_uids.add(predecessor_uid)
        predecessor_path = _write_activation(
            self.vault_files,
            uid=predecessor_uid,
            agent=agent,
            generation="sa.skeptic-001",
            status="retired",
            public_key=predecessor_key.public_key,
            activated_at="2026-07-25T12:00:00Z",
            agent_class="sa",
        )
        relative = predecessor_path.relative_to(self.git.repo)
        _git(self.git.repo, "add", str(relative))
        _git(
            self.git.repo,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@test.local",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--no-gpg-sign",
            "-m",
            "record skeptic predecessor",
        )
        predecessor_path.unlink()

        with self.assertRaises(SystemExit) as refusal:
            self._run_patched(
                lambda: ACTIVATION_TOOL.op_open(
                    self._open_args(
                        agent=agent,
                        generation="sa.skeptic-002",
                        agent_class="sa",
                        agent_root=root_uid,
                        run_folder="",
                    )
                ),
                minted_uid=successor_uid,
            )
        self.assertEqual(refusal.exception.code, 1)
        self.assertFalse((self.vault_files / f"{successor_uid}.md").exists())
        with self.assertRaises(ac.AuthorityChainError) as no_broker:
            ac.activation_signing_broker(successor_uid)
        self.assertEqual(
            no_broker.exception.code,
            ac.AuthorityErrorCode.KEY_BROKER_UNAVAILABLE,
        )

    def test_git_snapshot_identity_mutations_poison_open_signer_and_chain(self):
        mutations = (
            "agent",
            "agent_class",
            "generation",
            "agent_public_key",
            "predecessor_activation_uid",
            "key_presence",
        )

        def commit_path(path: Path, message: str) -> None:
            _git(self.git.repo, "add", str(path.relative_to(self.git.repo)))
            _git(
                self.git.repo,
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@test.local",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--no-gpg-sign",
                "-m",
                message,
            )

        for index, mutation in enumerate(mutations):
            agent = f"snapshot-{mutation.replace('_', '-')}"
            root_uid = f"e8{index:06x}"
            first_uid = f"a8{index:06x}"
            predecessor_uid = f"b8{index:06x}"
            live_uid = f"c8{index:06x}"
            attempted_uid = f"d8{index:06x}"
            _write_agent_root(
                self.vault_files,
                uid=root_uid,
                agent=agent,
                generation_prefix="A",
                agent_class="executive",
                current_generation="A2",
            )
            _write_unified_agent(
                self.git.repo,
                uid=f"f8{index:06x}",
                agent=agent,
                agent_class="executive",
                generation="A2",
                current_activation_uid=predecessor_uid,
            )
            _write_activation(
                self.vault_files,
                uid=first_uid,
                agent=agent,
                generation="A1",
                status="retired",
                public_key=_synthetic_ed25519_public_key(8000 + index * 10),
                activated_at="2026-07-24T12:00:00Z",
                agent_class="executive",
                agent_root=root_uid,
            )
            predecessor_key = _synthetic_ed25519_public_key(
                8001 + index * 10
            )
            replacement_key = _synthetic_ed25519_public_key(
                8002 + index * 10
            )
            predecessor_path = _write_activation(
                self.vault_files,
                uid=predecessor_uid,
                agent=agent,
                generation="A2",
                status="retired",
                public_key=predecessor_key,
                activated_at="2026-07-25T12:00:00Z",
                agent_class="executive",
                agent_root=root_uid,
                predecessor_activation_uid=first_uid,
            )
            original = predecessor_path.read_text(encoding="utf-8")
            if mutation == "key_presence":
                original = original.replace(
                    f'agent_public_key: "{predecessor_key}"\n',
                    "",
                )
                predecessor_path.write_text(original, encoding="utf-8")
            commit_path(predecessor_path, f"add {mutation} predecessor")

            changed = original
            if mutation == "agent":
                changed = changed.replace(f"agent: {agent}\n", "agent: intruder\n")
            elif mutation == "agent_class":
                changed = changed.replace(
                    "agent_class: executive\n",
                    "agent_class: sa\n",
                )
            elif mutation == "generation":
                changed = changed.replace("generation: A2\n", "generation: A9\n")
            elif mutation == "agent_public_key":
                changed = changed.replace(predecessor_key, replacement_key)
            elif mutation == "predecessor_activation_uid":
                changed = changed.replace(
                    f"predecessor_activation_uid: {first_uid}\n",
                    "predecessor_activation_uid: deadbeef\n",
                )
            elif mutation == "key_presence":
                changed = changed.replace(
                    "---\n\n",
                    f'agent_public_key: "{predecessor_key}"\n---\n\n',
                    1,
                )
            predecessor_path.write_text(changed, encoding="utf-8")
            commit_path(predecessor_path, f"mutate {mutation} predecessor")
            _git(self.git.repo, "rm", str(predecessor_path.relative_to(self.git.repo)))
            _git(
                self.git.repo,
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@test.local",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--no-gpg-sign",
                "-m",
                f"delete {mutation} predecessor",
            )

            with self.subTest(mutation=mutation, phase="durable-poison"):
                records = ac.load_canonical_activation_entries(self.git.repo)
                conflicts = [
                    record
                    for record in records
                    if record.history_invalid_code
                    == ac.AuthorityErrorCode.ACTIVATION_HISTORY_IDENTITY_CONFLICT
                    and predecessor_uid in record.history_affected_uids
                ]
                self.assertTrue(conflicts)
                with self.assertRaises(ac.AuthorityChainError) as derivation:
                    ac.derive_new_activation_predecessor(
                        records,
                        agent,
                        "executive",
                        "A3",
                        predecessor_uid,
                    )
                self.assertEqual(
                    derivation.exception.code,
                    ac.AuthorityErrorCode.ACTIVATION_HISTORY_IDENTITY_CONFLICT,
                )

            with self.subTest(mutation=mutation, phase="production-open"):
                with self.assertRaises(SystemExit) as refusal:
                    self._run_patched(
                        lambda agent=agent, root_uid=root_uid: ACTIVATION_TOOL.op_open(
                            self._open_args(
                                agent=agent,
                                generation="A3",
                                agent_class="executive",
                                agent_root=root_uid,
                                run_folder="",
                            )
                        ),
                        minted_uid=attempted_uid,
                    )
                self.assertEqual(refusal.exception.code, 1)
                self.assertFalse(
                    (self.vault_files / f"{attempted_uid}.md").exists()
                )

            live_key = ac.mint_agent_keypair(live_uid, agent, "A3")
            self.minted_uids.add(live_uid)
            _write_activation(
                self.vault_files,
                uid=live_uid,
                agent=agent,
                generation="A3",
                status="active",
                public_key=live_key.public_key,
                activated_at="2026-07-26T12:00:00Z",
                agent_class="executive",
                agent_root=root_uid,
                predecessor_activation_uid=first_uid,
            )
            records = ac.load_canonical_activation_entries(self.git.repo)
            analysis = ac.analyze_activations(records)
            with self.subTest(mutation=mutation, phase="signer"):
                self.assertFalse(analysis.is_gate_valid(live_uid))
                self.assertIn(
                    ac.AuthorityErrorCode.ACTIVATION_HISTORY_IDENTITY_CONFLICT,
                    {
                        finding.code
                        for finding in analysis.reasons_for(live_uid)
                    },
                )
                live_record = next(
                    record
                    for record in records
                    if record.uid == live_uid and not record.history_invalid
                )
                self.assertNotIn(
                    ac.canonical_git_identity(live_record)[1],
                    ac.derive_allowed_signers(records),
                )
            author_name, author_email = ac.canonical_git_identity(live_record)
            commit = _external_signed_commit(
                self.git.repo,
                live_key,
                author_name=author_name,
                author_email=author_email,
                message=f"{mutation} conflict claim",
            )
            with self.subTest(mutation=mutation, phase="chain"):
                with self.assertRaises(ac.AuthorityChainError) as chain:
                    ac.resolve_commit_chain(self.git.repo, commit)
                self.assertEqual(
                    chain.exception.code,
                    ac.AuthorityErrorCode.ACTIVATION_GATE_INVALID,
                )

    def test_status_modified_and_identical_recycle_snapshots_are_legal(self):
        agent = "snapshot-mutable"
        root_uid = "e8ff0000"
        first_uid = "a8ff0001"
        predecessor_uid = "b8ff0002"
        live_uid = "c8ff0003"
        _write_agent_root(
            self.vault_files,
            uid=root_uid,
            agent=agent,
            generation_prefix="A",
            agent_class="executive",
            current_generation="A2",
        )
        _write_unified_agent(
            self.git.repo,
            uid="f8ff0000",
            agent=agent,
            agent_class="executive",
            generation="A2",
            current_activation_uid=predecessor_uid,
        )
        _write_activation(
            self.vault_files,
            uid=first_uid,
            agent=agent,
            generation="A1",
            status="retired",
            public_key=_synthetic_ed25519_public_key(8990),
            activated_at="2026-07-24T12:00:00Z",
            agent_class="executive",
            agent_root=root_uid,
        )
        predecessor_key = _synthetic_ed25519_public_key(8991)
        predecessor_path = _write_activation(
            self.vault_files,
            uid=predecessor_uid,
            agent=agent,
            generation="A2",
            status="active",
            public_key=predecessor_key,
            activated_at="2026-07-25T12:00:00Z",
            agent_class="executive",
            agent_root=root_uid,
            predecessor_activation_uid=first_uid,
        )

        def commit_predecessor(message: str) -> None:
            _git(
                self.git.repo,
                "add",
                str(predecessor_path.relative_to(self.git.repo)),
            )
            _git(
                self.git.repo,
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@test.local",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--no-gpg-sign",
                "-m",
                message,
            )

        commit_predecessor("add mutable predecessor")
        mutable = predecessor_path.read_text(encoding="utf-8").replace(
            "status: active\n",
            "status: retired\n"
            "retired_at: 2026-07-26T09:00:00Z\n"
            "closure_reason: completed\n"
            "modified: 2026-07-26\n"
            "modified_by: closer\n",
        )
        predecessor_path.write_text(mutable, encoding="utf-8")
        commit_predecessor("retire mutable predecessor")
        _git(self.git.repo, "rm", str(predecessor_path.relative_to(self.git.repo)))
        _git(
            self.git.repo,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@test.local",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--no-gpg-sign",
            "-m",
            "delete mutable predecessor",
        )
        git_only_records = ac.load_canonical_activation_entries(self.git.repo)
        newest_git_snapshot = next(
            record
            for record in git_only_records
            if record.uid == predecessor_uid and not record.history_invalid
        )
        self.assertTrue(newest_git_snapshot.history_only)
        self.assertEqual(newest_git_snapshot.status, "retired")
        self.assertFalse(
            any(
                record.history_invalid_code
                == ac.AuthorityErrorCode.ACTIVATION_HISTORY_IDENTITY_CONFLICT
                and predecessor_uid in record.history_affected_uids
                for record in git_only_records
            )
        )

        for directory in (
            self.git.repo / "recycle" / "mutable-one",
            self.git.repo / "recycle" / "mutable-two",
        ):
            directory.mkdir(parents=True)
            _write_activation(
                directory,
                uid=predecessor_uid,
                agent=agent,
                generation="A2",
                status="retired",
                public_key=predecessor_key,
                activated_at="2026-07-25T12:00:00Z",
                agent_class="executive",
                agent_root=root_uid,
                predecessor_activation_uid=first_uid,
            )
        _write_activation(
            self.vault_files,
            uid=live_uid,
            agent=agent,
            generation="A3",
            status="active",
            public_key=_synthetic_ed25519_public_key(8992),
            activated_at="2026-07-26T12:00:00Z",
            agent_class="executive",
            agent_root=root_uid,
            predecessor_activation_uid=predecessor_uid,
        )
        records = ac.load_canonical_activation_entries(self.git.repo)
        self.assertFalse(
            any(
                record.history_invalid_code
                == ac.AuthorityErrorCode.ACTIVATION_HISTORY_IDENTITY_CONFLICT
                and predecessor_uid in record.history_affected_uids
                for record in records
            )
        )
        self.assertTrue(ac.analyze_activations(records).is_gate_valid(live_uid))
        self.assertIn(
            "snapshot-mutable-a3@agents.tropo.local",
            ac.derive_allowed_signers(records),
        )

    def test_key_required_classes_without_keys_are_never_gate_valid(self):
        records = []
        for index, agent_class in enumerate(sorted(ACTIVATION_TOOL.VALID_CLASSES)):
            agent = f"missing-key-{agent_class}"
            _write_agent_root(
                self.vault_files,
                uid=f"e30000{index:02x}",
                agent=agent,
                generation_prefix="M" if agent_class in ac.EXECUTIVE_GENERATION_CLASSES else "",
                agent_class=agent_class,
            )
            _write_unified_agent(
                self.git.repo,
                uid=f"c30000{index:02x}",
                agent=agent,
                agent_class=agent_class,
            )
            _write_activation(
                self.vault_files,
                uid=f"d30000{index:02x}",
                agent=agent,
                generation="M1" if agent_class in ac.EXECUTIVE_GENERATION_CLASSES else "opaque",
                status="active",
                public_key=None,
                activated_at="2026-07-26T12:00:00Z",
                agent_class=agent_class,
            )
        records = ac.load_canonical_activation_entries(self.git.repo)
        analysis = ac.analyze_activations(records)
        for record in records:
            if record.uid.startswith("d30000"):
                with self.subTest(agent_class=record.agent_class):
                    self.assertEqual(
                        analysis.is_gate_valid(record.uid),
                        record.agent_class == "pipeline",
                    )
                    if record.agent_class != "pipeline":
                        self.assertIn(
                            ac.AuthorityErrorCode.ACTIVATION_KEY_MISSING,
                            {
                                finding.code
                                for finding in analysis.reasons_for(record.uid)
                            },
                        )

    def test_established_canonical_generation_refuses_history_reset_before_mint(self):
        _write_agent_root(
            self.vault_files,
            uid="e4000001",
            agent="established",
            generation_prefix="E",
            current_generation="E9",
        )
        _write_unified_agent(
            self.git.repo,
            uid="c4000001",
            agent="established",
            agent_class="executive",
            generation="E9",
        )
        for index, attempted_generation in enumerate(("E1", "E10")):
            uid = f"d40000{index:02x}"
            with self.subTest(generation=attempted_generation):
                with self.assertRaises(SystemExit) as raised:
                    self._run_patched(
                        lambda attempted_generation=attempted_generation: ACTIVATION_TOOL.op_open(
                            self._open_args(
                                agent="established",
                                generation=attempted_generation,
                                agent_root="e4000001",
                            )
                        ),
                        minted_uid=uid,
                    )
                self.assertEqual(raised.exception.code, 1)
                self.assertFalse((self.vault_files / f"{uid}.md").exists())
                with self.assertRaises(ac.AuthorityChainError):
                    ac.activation_signing_broker(uid)

        for number in range(1, 10):
            uid = f"d400000{number}"
            _write_activation(
                self.vault_files,
                uid=uid,
                agent="established",
                generation=f"E{number}",
                status="retired",
                public_key=_synthetic_ed25519_public_key(400 + number),
                activated_at=f"2026-07-25T12:{number:02d}:00Z",
                predecessor_activation_uid=(
                    f"d400000{number - 1}" if number > 1 else None
                ),
            )
        result = self._run_patched(
            lambda: ACTIVATION_TOOL.op_open(
                self._open_args(
                    agent="established",
                    generation="E10",
                    agent_root="e4000001",
                )
            ),
            minted_uid="d4000010",
        )
        self.assertEqual(result, 0)
        self.minted_uids.add("d4000010")

    def test_executive_generation_matrix_refuses_before_key_mint(self):
        _write_agent_root(
            self.vault_files,
            uid="11111111",
            agent="demo",
            generation_prefix="D",
        )
        predecessor_key = ac.mint_agent_keypair("aa100001", "demo", "D1")
        self.minted_uids.add("aa100001")
        _write_activation(
            self.vault_files,
            uid="aa100001",
            agent="demo",
            generation="D1",
            status="retired",
            public_key=predecessor_key.public_key,
            activated_at="2026-07-25T12:00:00Z",
        )
        invalid_labels = (
            "",
            "D1",
            "D2-resume",
            "D02",
            "D" + ("9" * 128),
            "T2",
        )
        for index, label in enumerate(invalid_labels):
            uid = f"f100000{index}"
            with self.subTest(label=label):
                with self.assertRaises(SystemExit) as raised:
                    self._run_patched(
                        lambda label=label: ACTIVATION_TOOL.op_open(
                            self._open_args(generation=label)
                        ),
                        minted_uid=uid,
                    )
                self.assertEqual(raised.exception.code, 1)
                self.assertFalse((self.vault_files / f"{uid}.md").exists())
                with self.assertRaises(ac.AuthorityChainError):
                    ac.activation_signing_broker(uid)

        result = self._run_patched(
            lambda: ACTIVATION_TOOL.op_open(self._open_args(generation="D2")),
            minted_uid="f100000f",
        )
        self.assertEqual(result, 0)
        self.minted_uids.add("f100000f")
        self.assertTrue(ac.activation_signing_broker("f100000f").socket_path.exists())

    def test_opaque_pipeline_worker_and_sa_generations_keep_their_contract(self):
        cases = (
            ("pipeline", "pipeline/opaque@8428", "c1000001", False),
            ("worker", "worker-vNext/resume", "c1000002", True),
            ("sa", "sa.audit-special", "c1000003", True),
        )
        for agent_class, generation, uid, expects_key in cases:
            agent = f"demo-{agent_class}"
            with self.subTest(agent_class=agent_class):
                agent_root = f"{int(uid, 16) + 1:08x}"
                if agent_class in {"pipeline", "sa"}:
                    _write_agent_root(
                        self.vault_files,
                        uid=agent_root,
                        agent=agent,
                        agent_class=agent_class,
                    )
                result = self._run_patched(
                    lambda: ACTIVATION_TOOL.op_open(
                        self._open_args(
                            agent=agent,
                            generation=generation,
                            agent_class=agent_class,
                            agent_root=agent_root,
                            run_folder="",
                        )
                    ),
                    minted_uid=uid,
                )
                self.assertEqual(result, 0)
                record = next(
                    record
                    for record in ac.load_activation_entries(self.vault_files)
                    if record.uid == uid
                )
                self.assertEqual(record.generation, generation)
                self.assertEqual(bool(record.agent_public_key), expects_key)
                if expects_key:
                    self.minted_uids.add(uid)

    def test_paused_activation_blocks_resume_as_second_live_identity(self):
        _write_activation(
            self.vault_files,
            uid="aa100002",
            agent="demo",
            generation="D1",
            status="paused",
            public_key=None,
            activated_at="2026-07-25T12:00:00Z",
        )
        with self.assertRaises(SystemExit) as raised:
            self._run_patched(
                lambda: ACTIVATION_TOOL.op_open(self._open_args(generation="D2")),
                minted_uid="f1000010",
            )
        self.assertEqual(raised.exception.code, 1)
        self.assertFalse((self.vault_files / "f1000010.md").exists())
        with self.assertRaises(ac.AuthorityChainError):
            ac.activation_signing_broker("f1000010")

    def test_adr016_or_adr028_failure_writes_neither_entry_nor_key(self):
        _write_activation(
            self.vault_files,
            uid="aaaa0001",
            agent="demo",
            generation="D1",
            status="active",
            public_key=None,
            activated_at="2026-07-26T11:00:00Z",
        )
        with self.assertRaises(SystemExit) as raised:
            self._run_patched(
                lambda: ACTIVATION_TOOL.op_open(
                    self._open_args(generation="D2")
                )
            )
        self.assertEqual(raised.exception.code, 1)
        self.assertFalse((self.vault_files / "feed0001.md").exists())
        with self.assertRaises(ac.AuthorityChainError):
            ac.activation_signing_broker("feed0001")

        (self.vault_files / "aaaa0001.md").write_text(
            (self.vault_files / "aaaa0001.md")
            .read_text()
            .replace("status: active", "status: retired")
        )
        with self.assertRaises(SystemExit) as raised:
            self._run_patched(
                lambda: ACTIVATION_TOOL.op_open(
                    self._open_args(generation="D3")
                )
            )
        self.assertEqual(raised.exception.code, 1)
        self.assertFalse((self.vault_files / "feed0001.md").exists())
        with self.assertRaises(ac.AuthorityChainError):
            ac.activation_signing_broker("feed0001")

    def test_production_activation_close_publishes_activation_bound_signed_commit(self):
        _write_agent_root(
            self.vault_files,
            uid="22222222",
            agent="demo-sa",
            agent_class="sa",
        )
        open_args = self._open_args(
            agent="demo-sa",
            generation="demo-sa-001",
            agent_class="sa",
            agent_root="22222222",
            run_folder="",
        )
        self._run_patched(
            lambda: ACTIVATION_TOOL.op_open(open_args),
            minted_uid="feed0002",
        )
        self.minted_uids.add("feed0002")
        opened_broker = ac.activation_signing_broker("feed0002")
        broker_directory = opened_broker.socket_path.parent
        head_before = _git(self.git.repo, "rev-parse", "HEAD").stdout.strip()
        foreign = self.git.repo / "agents" / "other" / "concurrent.md"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("foreign concurrent work\n", encoding="utf-8")
        config_before = self.git.config_path.read_bytes()
        close_args = types.SimpleNamespace(
            activation_uid="feed0002",
            target_status="failed",
            closure_reason="dispatch-failure",
            transfer_uid="",
            retirement_run_folder="",
            retiring_flip_recorded_at="",
            reflection_path="",
            skip_retirement_invariants=False,
            dry_run=False,
            actor="demo-sa-001",
        )
        result = self._run_patched(
            lambda: ACTIVATION_TOOL.op_close(close_args),
            minted_uid="unused00",
        )
        self.assertEqual(result, 0)
        self.assertFalse(broker_directory.exists())
        stopped_state = ac._broker_process_state(opened_broker.pid)
        self.assertTrue(
            stopped_state is None or stopped_state.startswith("Z"),
            f"broker remained live in process state {stopped_state!r}",
        )
        unavailable = subprocess.run(
            ["ssh-add", "-L"],
            capture_output=True,
            env={
                **os.environ,
                "SSH_AUTH_SOCK": str(opened_broker.socket_path),
                "SSH_AGENT_PID": str(opened_broker.pid),
            },
            timeout=30,
        )
        self.assertNotEqual(unavailable.returncode, 0)
        self.assertEqual(self.git.config_path.read_bytes(), config_before)
        signature = ac.extract_commit_signature(self.git.repo, "HEAD")
        entry = ac.load_activation_entries(self.vault_files)[0]
        self.assertEqual(signature.key_blob, entry.public_key.blob)
        ac._verify_one_key(self.git.repo, signature, "production-close-integration")
        self.assertEqual(
            _git(self.git.repo, "rev-parse", "HEAD^").stdout.strip(),
            head_before,
        )
        self.assertEqual(
            _git(self.git.repo, "show", "-s", "--format=%s", "HEAD").stdout.strip(),
            "tropo: close activation demo-sa demo-sa-001 (feed0002) → failed",
        )
        committed = _git(
            self.git.repo,
            "show",
            "--pretty=",
            "--name-only",
            "HEAD",
        ).stdout.splitlines()
        self.assertEqual(committed, ["vault/files/feed0002.md"])
        self.assertIn(
            "agents/other/concurrent.md",
            _git(
                self.git.repo,
                "status",
                "--porcelain",
                "--untracked-files=all",
            ).stdout,
        )

    def test_close_signing_failure_rolls_back_and_retains_key(self):
        _write_agent_root(
            self.vault_files,
            uid="22222222",
            agent="demo-sa",
            agent_class="sa",
        )
        open_args = self._open_args(
            agent="demo-sa",
            generation="demo-sa-002",
            agent_class="sa",
            agent_root="22222222",
            run_folder="",
        )
        self._run_patched(
            lambda: ACTIVATION_TOOL.op_open(open_args),
            minted_uid="feed0003",
        )
        self.minted_uids.add("feed0003")
        entry = self.vault_files / "feed0003.md"
        original = entry.read_bytes()
        broker_socket = ac.activation_signing_broker("feed0003").socket_path
        close_args = types.SimpleNamespace(
            activation_uid="feed0003",
            target_status="failed",
            closure_reason="dispatch-failure",
            transfer_uid="cafebabe",
            retirement_run_folder="",
            retiring_flip_recorded_at="",
            reflection_path="",
            skip_retirement_invariants=False,
            dry_run=False,
            actor="demo-sa-002",
        )

        real_sign = ac.sign_commit

        def fail_after_explicit_staging(repo, activation, message, **kwargs):
            return real_sign(
                repo,
                activation,
                message,
                signing_program="/bin/false",
                **kwargs,
            )

        real_auto_create = ACTIVATION_TOOL.auto_create_transfer_stub
        created_stub_content: dict[str, bytes] = {}

        def create_and_capture(*args, **kwargs):
            created = real_auto_create(*args, **kwargs)
            if created:
                created_stub_content["payload"] = (
                    self.vault_files / "cafebabe.md"
                ).read_bytes()
            return created

        with patch.object(
            ACTIVATION_TOOL,
            "auto_create_transfer_stub",
            side_effect=create_and_capture,
        ), patch.object(
            ACTIVATION_TOOL,
            "sign_commit",
            side_effect=fail_after_explicit_staging,
        ):
            result = self._run_patched(
                lambda: ACTIVATION_TOOL.op_close(close_args),
                minted_uid="unused00",
            )

        self.assertEqual(result, 3)
        self.assertEqual(entry.read_bytes(), original)
        self.assertTrue(broker_socket.exists())
        self.assertFalse((self.vault_files / "cafebabe.md").exists())
        archive_dir = (
            self.git.repo
            / "recycle"
            / "activation-close-rollbacks"
            / ACTIVATION_TOOL.TODAY
        )
        archived_stubs = list(archive_dir.glob("cafebabe-*.md"))
        self.assertEqual(len(archived_stubs), 1)
        archived_stub = archived_stubs[0]
        self.assertEqual(archived_stub.read_bytes(), created_stub_content["payload"])
        sidecar = json.loads(
            Path(f"{archived_stub}.rollback.json").read_text(encoding="utf-8")
        )
        self.assertEqual(sidecar["activation_uid"], "feed0003")
        self.assertEqual(sidecar["original_transfer_uid"], "cafebabe")
        self.assertEqual(
            sidecar["original_intended_path"],
            "vault/files/cafebabe.md",
        )
        self.assertTrue(sidecar["reason"].startswith("signing-failure:"))
        self.assertEqual(
            _git(self.git.repo, "diff", "--cached", "--name-only").stdout,
            "",
        )
        self.assertEqual(
            _git(self.git.repo, "log", "-1", "--format=%s").stdout.strip(),
            "fixture baseline",
        )

    def test_close_signing_failure_never_moves_preexisting_transfer_stub(self):
        entry = _write_activation(
            self.vault_files,
            uid="feed0013",
            agent="demo-sa",
            generation="demo-sa-013",
            status="active",
            public_key=_synthetic_ed25519_public_key(13),
            activated_at="2026-07-26T12:00:00Z",
        )
        original_entry = entry.read_bytes()
        transfer_stub = self.vault_files / "decafbad.md"
        preexisting_content = b"pre-existing transfer stub\n\x00"
        transfer_stub.write_bytes(preexisting_content)
        parsed = ACTIVATION_TOOL.parse_frontmatter(entry)
        self.assertIsNotNone(parsed)
        fm, raw_fm, body = parsed
        close_args = types.SimpleNamespace(
            activation_uid="feed0013",
            target_status="failed",
            closure_reason="dispatch-failure",
            transfer_uid="decafbad",
            actor="demo-sa-013",
        )

        with patch.object(
            ACTIVATION_TOOL,
            "_commit_activation_close_with_provenance",
            return_value=(False, "planted signing failure"),
        ):
            result = self._run_patched(
                lambda: ACTIVATION_TOOL._apply_activation_close_transaction(
                    close_args,
                    entry,
                    fm,
                    raw_fm,
                    body,
                )
            )

        self.assertEqual(result, 3)
        self.assertEqual(entry.read_bytes(), original_entry)
        self.assertEqual(transfer_stub.read_bytes(), preexisting_content)
        archive_dir = (
            self.git.repo
            / "recycle"
            / "activation-close-rollbacks"
            / ACTIVATION_TOOL.TODAY
        )
        self.assertEqual(list(archive_dir.glob("decafbad-*.md")), [])

    def test_activation_close_rollback_archive_is_collision_safe(self):
        entry = self.vault_files / "feed0014.md"
        original_entry = b"original activation bytes\n\x00"
        entry.write_bytes(b"mutated activation")
        transfer_stub = self.vault_files / "facefeed.md"
        archive_dir = (
            self.git.repo
            / "recycle"
            / "activation-close-rollbacks"
            / ACTIVATION_TOOL.TODAY
        )
        archive_dir.mkdir(parents=True)
        colliding_destination = archive_dir / "facefeed.md"
        colliding_content = b"older rollback must survive\n"
        colliding_destination.write_bytes(colliding_content)

        payloads = (b"first uncommitted stub\n", b"second uncommitted stub\n")
        for index, payload in enumerate(payloads, start=1):
            transfer_stub.write_bytes(payload)
            entry.write_bytes(f"mutated activation {index}".encode())
            self._run_patched(
                lambda index=index: ACTIVATION_TOOL._rollback_activation_close(
                    entry,
                    original_entry,
                    created_stub=transfer_stub,
                    activation_uid="feed0014",
                    reason=f"transaction-failure: collision plant {index}",
                )
            )
            self.assertEqual(entry.read_bytes(), original_entry)
            self.assertFalse(transfer_stub.exists())

        archived_stubs = list(archive_dir.glob("facefeed-*.md"))
        self.assertEqual(len(archived_stubs), 2)
        self.assertEqual(
            {path.read_bytes() for path in archived_stubs},
            set(payloads),
        )
        self.assertEqual(
            len({path.name for path in archived_stubs}),
            2,
        )
        self.assertEqual(colliding_destination.read_bytes(), colliding_content)
        for archived_stub in archived_stubs:
            sidecar = Path(f"{archived_stub}.rollback.json")
            self.assertTrue(sidecar.is_file())

    def test_activation_close_rollback_move_failure_is_named_and_lossless(self):
        entry = self.vault_files / "feed0015.md"
        original_entry = b"byte-exact original activation\n\x00"
        entry.write_bytes(b"terminal mutation")
        transfer_stub = self.vault_files / "deadbeef.md"
        original_stub = b"uncommitted transfer stub\n\x00"
        transfer_stub.write_bytes(original_stub)

        with patch.object(
            ACTIVATION_TOOL.os,
            "replace",
            side_effect=OSError("planted atomic move failure"),
        ):
            with self.assertRaises(
                ACTIVATION_TOOL.ActivationCloseRollbackError
            ) as raised:
                self._run_patched(
                    lambda: ACTIVATION_TOOL._rollback_activation_close(
                        entry,
                        original_entry,
                        created_stub=transfer_stub,
                        activation_uid="feed0015",
                        reason="transaction-failure: planted move failure",
                    )
                )

        self.assertIn("ACTIVATION_CLOSE_ROLLBACK_FAILED", str(raised.exception))
        self.assertEqual(
            raised.exception.code,
            ac.AuthorityErrorCode.GIT_COMMAND_FAILED,
        )
        self.assertEqual(entry.read_bytes(), original_entry)
        self.assertEqual(transfer_stub.read_bytes(), original_stub)

    def test_activation_close_rollback_source_forbids_direct_stub_delete(self):
        source = inspect.getsource(ACTIVATION_TOOL._rollback_activation_close)
        self.assertNotIn(".unlink(", source)
        self.assertNotIn("os.remove(", source)

    def test_detached_signer_verification_mismatch_never_publishes_terminal_state(self):
        _write_agent_root(
            self.vault_files,
            uid="22222222",
            agent="demo-sa",
            agent_class="sa",
        )
        open_args = self._open_args(
            agent="demo-sa",
            generation="demo-sa-003",
            agent_class="sa",
            agent_root="22222222",
            run_folder="",
        )
        self._run_patched(
            lambda: ACTIVATION_TOOL.op_open(open_args),
            minted_uid="feed0004",
        )
        self.minted_uids.add("feed0004")
        entry = self.vault_files / "feed0004.md"
        _git(self.git.repo, "add", "--", "vault/files/feed0004.md")
        _git(
            self.git.repo,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@test.local",
            "commit",
            "--no-gpg-sign",
            "-m",
            "active activation baseline",
        )
        original_entry = entry.read_bytes()
        broker_socket = ac.activation_signing_broker("feed0004").socket_path
        head_before = _git(self.git.repo, "rev-parse", "HEAD").stdout.strip()
        index_path = Path(
            _git(self.git.repo, "rev-parse", "--git-path", "index").stdout.strip()
        )
        if not index_path.is_absolute():
            index_path = self.git.repo / index_path
        index_before = index_path.read_bytes()
        close_args = types.SimpleNamespace(
            activation_uid="feed0004",
            target_status="failed",
            closure_reason="dispatch-failure",
            transfer_uid="",
            retirement_run_folder="",
            retiring_flip_recorded_at="",
            reflection_path="",
            skip_retirement_invariants=False,
            dry_run=False,
            actor="demo-sa-003",
        )
        mismatch = ac.AuthorityChainError(
            ac.AuthorityErrorCode.SIGNATURE_INVALID,
            "independent signer verification mismatch plant",
        )
        verification_heads: list[str] = []

        def reject_signer(*_args, **_kwargs):
            verification_heads.append(
                _git(self.git.repo, "rev-parse", "HEAD").stdout.strip()
            )
            raise mismatch

        with patch.object(ac, "_verify_one_key", side_effect=reject_signer):
            result = self._run_patched(
                lambda: ACTIVATION_TOOL.op_close(close_args),
                minted_uid="unused00",
            )

        self.assertEqual(result, 3)
        self.assertEqual(verification_heads, [head_before])
        self.assertEqual(_git(self.git.repo, "rev-parse", "HEAD").stdout.strip(), head_before)
        self.assertEqual(index_path.read_bytes(), index_before)
        self.assertEqual(entry.read_bytes(), original_entry)
        self.assertTrue(broker_socket.exists())
        at_head = _git(
            self.git.repo,
            "show",
            "HEAD:vault/files/feed0004.md",
        )
        self.assertIn("status: active", at_head.stdout)
        self.assertNotIn("status: failed", at_head.stdout)

    def test_lifecycle_commit_excludes_and_preserves_foreign_prestaged_file(self):
        _write_agent_root(
            self.vault_files,
            uid="22222222",
            agent="demo-sa",
            agent_class="sa",
        )
        open_args = self._open_args(
            agent="demo-sa",
            generation="demo-sa-004",
            agent_class="sa",
            agent_root="22222222",
            run_folder="",
        )
        self._run_patched(
            lambda: ACTIVATION_TOOL.op_open(open_args),
            minted_uid="feed0005",
        )
        self.minted_uids.add("feed0005")
        foreign = self.git.repo / "foreign-prestaged.txt"
        foreign.write_text("belongs to another operation\n", encoding="utf-8")
        _git(self.git.repo, "add", "--", "foreign-prestaged.txt")
        close_args = types.SimpleNamespace(
            activation_uid="feed0005",
            target_status="failed",
            closure_reason="dispatch-failure",
            transfer_uid="",
            retirement_run_folder="",
            retiring_flip_recorded_at="",
            reflection_path="",
            skip_retirement_invariants=False,
            dry_run=False,
            actor="demo-sa-004",
        )
        result = self._run_patched(
            lambda: ACTIVATION_TOOL.op_close(close_args),
            minted_uid="unused00",
        )

        self.assertEqual(result, 0)
        committed = _git(
            self.git.repo,
            "show",
            "--pretty=",
            "--name-only",
            "HEAD",
        ).stdout.splitlines()
        self.assertEqual(committed, ["vault/files/feed0005.md"])
        self.assertEqual(
            _git(self.git.repo, "diff", "--cached", "--name-only").stdout.splitlines(),
            ["foreign-prestaged.txt"],
        )
        self.assertNotEqual(
            _git(
                self.git.repo,
                "cat-file",
                "-e",
                "HEAD:foreign-prestaged.txt",
                check=False,
            ).returncode,
            0,
        )


class TestProvisionalBirth(_ActivationMintFixture):
    """A failed identity check marks a generation provisional. It never refuses it.

    Mike's standing rule, 2026-08-02: "a failed identity check marks a generation
    provisional and lets it work — it never refuses existence." Verbatim bar:
    "I NEVER EVER want to see my agents telling me they are failing to boot.
    Denied because of ceremony that protects nothing."

    Three consecutive Metis generations were blocked at birth by three different
    checks in one family (G97 a pre-G2 key demand, G99 a governed broker-loss
    void, G100 the same void one link deeper). Each fix corrected the check it
    hit; none ended the class, because the class was never which check is wrong.
    It is refusal itself: a gate on the boot path fires at the one moment nobody
    is home, and the agent who could fix it is the agent who cannot start.

    Inherits TestCriterion1ActivationMint for its fixture, then overrides
    _open_args to drop strict — the parent's cases prove the checks DETECT,
    these prove what detection now COSTS.
    """

    def _open_args(self, **overrides):
        overrides.setdefault("strict", False)
        return super()._open_args(**overrides)

    def _plant_live_predecessor(self):
        """An open activation for the same agent — the ADR-016 violation."""
        (self.vault_files / "aaaa0016.md").write_text(
            "---\n"
            "uid: aaaa0016\n"
            "type: activation\n"
            "agent: demo\n"
            "agent_root: 11111111\n"
            "agent_class: executive\n"
            "generation: D1\n"
            "status: active\n"
            "activated_at: 2026-08-01\n"
            "activated_by: user\n"
            "stale_threshold_hours: 168\n"
            "---\n",
            encoding="utf-8",
        )

    def test_failed_check_still_produces_a_working_agent(self):
        run_folder = self.root / "playbook-runs" / "demo-D2"
        run_folder.mkdir(parents=True)
        self._plant_live_predecessor()

        result = self._run_patched(
            lambda: ACTIVATION_TOOL.op_open(
                self._open_args(generation="D2", run_folder="playbook-runs/demo-D2")
            )
        )

        self.assertEqual(
            result, 0, "a failed identity check must not refuse the birth"
        )
        entry = self.vault_files / "feed0001.md"
        self.assertTrue(
            entry.is_file(),
            "the agent must EXIST — an entry that was never written is exactly "
            "the deadlock this rule removes",
        )
        self.minted_uids.add("feed0001")

    def test_the_finding_is_recorded_in_the_entry_not_swallowed(self):
        run_folder = self.root / "playbook-runs" / "demo-D2"
        run_folder.mkdir(parents=True)
        self._plant_live_predecessor()

        self._run_patched(
            lambda: ACTIVATION_TOOL.op_open(
                self._open_args(generation="D2", run_folder="playbook-runs/demo-D2")
            )
        )
        text = (self.vault_files / "feed0001.md").read_text(encoding="utf-8")
        self.minted_uids.add("feed0001")

        self.assertIn(
            "provisional: true",
            text,
            "born-anyway must never mean born-silently: the entry itself carries "
            "the flag, so a later reader sees an unproven record as unproven",
        )
        self.assertIn("provisional_reasons:", text)
        self.assertIn(
            "ADR-016",
            text,
            "the reason must name the check that failed, or the record says "
            "something is wrong without saying what",
        )

    def test_strict_still_refuses_for_validators_and_ci(self):
        run_folder = self.root / "playbook-runs" / "demo-D2"
        run_folder.mkdir(parents=True)
        self._plant_live_predecessor()

        with self.assertRaises(SystemExit):
            self._run_patched(
                lambda: ACTIVATION_TOOL.op_open(
                    self._open_args(
                        generation="D2",
                        run_folder="playbook-runs/demo-D2",
                        strict=True,
                    )
                )
            )
        self.assertFalse(
            (self.vault_files / "feed0001.md").is_file(),
            "--strict must keep the old all-or-nothing contract intact",
        )


class TestCriterion1KeyContainment(AuthorityFixture):
    def test_random_session_directories_and_strict_permissions(self):
        _, first = self.mint_record("aa000001", "alpha", "A1")
        _, second = self.mint_record("bb000001", "beta", "B1")
        self.assertNotEqual(first.broker_socket.parent, second.broker_socket.parent)
        self.assertRegex(first.broker_socket.parent.name, r"^aa000001-[a-z0-9_-]+$")
        for minted in (first, second):
            directory = minted.broker_socket.parent
            self.assertEqual(
                stat.S_IMODE(directory.stat().st_mode),
                0o700,
            )
            metadata = directory / ac.BROKER_METADATA_NAME
            self.assertEqual(stat.S_IMODE(metadata.stat().st_mode), 0o600)
            self.assertTrue(stat.S_ISSOCK(minted.broker_socket.stat().st_mode))
            self.assertEqual(directory.parent, ac.session_key_root())
            self.assertEqual(
                {path.name for path in directory.iterdir()},
                {ac.BROKER_METADATA_NAME, ac.BROKER_SOCKET_NAME},
            )

    def test_arbitrary_and_symlink_key_roots_are_refused(self):
        with self.assertRaises(ac.AuthorityChainError) as arbitrary:
            ac.mint_agent_keypair(
                "aa000002",
                "alpha",
                "A1",
                key_root=self.root / "attacker-chosen",
            )
        self.assertEqual(arbitrary.exception.code, ac.AuthorityErrorCode.KEY_ROOT_UNSAFE)

        with patch.dict(
            os.environ,
            {ac.SESSION_KEY_ROOT_ENV: str(self.root / "legacy-root")},
        ):
            with self.assertRaises(ac.AuthorityChainError) as environment:
                ac.session_key_root()
        self.assertEqual(environment.exception.code, ac.AuthorityErrorCode.KEY_ROOT_UNSAFE)

        base = ac.session_key_root()
        target = self.root / "symlink-target"
        target.mkdir()
        spoof = base / "aa000003-spoof"
        spoof.symlink_to(target, target_is_directory=True)
        try:
            with self.assertRaises(ac.AuthorityChainError) as symlink:
                ac.activation_signing_broker("aa000003")
            self.assertEqual(symlink.exception.code, ac.AuthorityErrorCode.KEY_ROOT_UNSAFE)
        finally:
            spoof.unlink()

    def test_tmpdir_cannot_redirect_keys_and_terminal_boundary_cleans_them(self):
        redirected = self.root / "attacker-tmp"
        redirected.mkdir()
        with patch.dict(os.environ, {"TMPDIR": str(redirected)}):
            activation, minted = self.mint_record("aa000004", "alpha", "A1")
        broker_directory = minted.broker_socket.parent
        self.assertEqual(broker_directory.parent, ac.session_key_root())
        self.assertNotIn(redirected, broker_directory.parents)
        path = self.vault_files / f"{activation.uid}.md"
        path.write_text(path.read_text().replace("status: active", "status: retired"))
        removed = ac.cleanup_stale_agent_keypairs(
            ac.load_activation_entries(self.vault_files)
        )
        self.assertEqual(removed, (activation.uid,))
        self.assertFalse(broker_directory.exists())

    def test_key_survives_minting_process_exit_and_is_usable_by_parent(self):
        code = (
            "import json; from lib.authority_chain import mint_agent_keypair; "
            "m=mint_agent_keypair('aa000005','alpha','A1'); "
            "print(json.dumps({'public_key':m.public_key,'socket':str(m.broker_socket),'pid':m.broker_pid}))"
        )
        environment = dict(os.environ)
        environment["PYTHONPATH"] = (
            str(TOOLS)
            + os.pathsep
            + environment.get("PYTHONPATH", "")
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(self.git.repo),
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        created = json.loads(result.stdout)
        public_key = created["public_key"]
        broker = ac.activation_signing_broker(
            "aa000005",
            expected_public_key=public_key,
        )
        self.assertEqual(broker.pid, created["pid"])
        self.assertEqual(broker.socket_path, Path(created["socket"]))
        runtime_payload = b"\n".join(
            path.read_bytes()
            for path in broker.socket_path.parent.iterdir()
            if path.is_file()
        )
        process_output = subprocess.run(
            ["ps", "eww", "-p", str(broker.pid)],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.encode()
        same_user_view = subprocess.run(
            ["ssh-add", "-L"],
            capture_output=True,
            env={
                **os.environ,
                "SSH_AUTH_SOCK": str(broker.socket_path),
                "SSH_AGENT_PID": str(broker.pid),
            },
            check=True,
            timeout=30,
        ).stdout
        for exposed in (runtime_payload, process_output, same_user_view):
            self.assertNotIn(b"BEGIN OPENSSH PRIVATE KEY", exposed)
            self.assertNotIn(b"PRIVATE KEY", exposed)
        self.assertEqual(
            ac.parse_openssh_public_key(same_user_view.decode()).blob,
            ac.parse_openssh_public_key(public_key).blob,
        )
        _write_activation(
            self.vault_files,
            uid="aa000005",
            agent="alpha",
            generation="A1",
            status="active",
            public_key=public_key,
            activated_at="2026-07-26T12:00:00Z",
        )
        activation = ac.load_activation_entries(self.vault_files)[0]
        signed = ac.sign_commit(
            self.git.repo,
            activation,
            "cross-process runtime key",
        )
        self.assertEqual(
            signed.signature.key_blob,
            ac.parse_openssh_public_key(public_key).blob,
        )
        path = self.vault_files / "aa000005.md"
        path.write_text(path.read_text().replace("status: active", "status: retired"))
        removed = ac.cleanup_stale_agent_keypairs(
            ac.load_activation_entries(self.vault_files),
        )
        self.assertEqual(removed, ("aa000005",))
        self.assertFalse(broker.socket_path.parent.exists())

    def test_abnormal_partial_directory_cleanup_is_symlink_safe(self):
        root = ac.session_key_root()
        partial = root / "aa000006-partial"
        partial.mkdir(mode=0o700)
        old = time.time() - 7200
        os.utime(partial, (old, old))
        removed = ac.cleanup_stale_agent_keypairs(
            [],
            orphan_activation_uids=("aa000006",),
            orphan_grace_seconds=3600,
        )
        self.assertEqual(removed, ("aa000006",))
        self.assertFalse(partial.exists())

        target = self.root / "must-survive"
        target.write_text("do not follow\n", encoding="utf-8")
        hostile = root / "aa000007-hostile"
        hostile.mkdir(mode=0o700)
        (hostile / "id_ed25519").symlink_to(target)
        try:
            with self.assertRaises(ac.AuthorityChainError) as raised:
                ac.cleanup_stale_agent_keypairs(
                    [],
                    orphan_activation_uids=("aa000007",),
                    orphan_grace_seconds=0,
                )
            self.assertEqual(
                raised.exception.code,
                ac.AuthorityErrorCode.KEY_ROOT_UNSAFE,
            )
            self.assertEqual(target.read_text(), "do not follow\n")
        finally:
            (hostile / "id_ed25519").unlink(missing_ok=True)
            hostile.rmdir()


class TestCriteria2And3SigningChain(AuthorityFixture):
    def test_exact_sshsig_key_and_end_to_end_chain(self):
        activation, minted = self.mint_record("a1000001", "alpha", "A1")
        config_before = self.git.config_path.read_bytes()
        signed = ac.sign_commit(
            self.git.repo,
            activation,
            "alpha signed commit",
        )
        self.assertEqual(self.git.config_path.read_bytes(), config_before)
        self.assertEqual(
            signed.signature.key_blob,
            ac.parse_openssh_public_key(minted.public_key).blob,
        )

        result = ac.resolve_commit_chain(
            self.git.repo,
            signed.commit,
        )
        self.assertEqual(result.activation_uid, "a1000001")
        self.assertEqual(result.agent, "alpha")
        self.assertEqual(result.generation, "A1")
        self.assertEqual(result.activated_by, "user")
        self.assertFalse(result.authority)
        self.assertEqual(result.provenance, "agent-activation")

    def test_retired_activation_refuses_valid_signature(self):
        activation, minted = self.mint_record("a1000002", "alpha", "A1")
        signed = ac.sign_commit(
            self.git.repo,
            activation,
            "signed before retirement",
        )
        path = self.vault_files / "a1000002.md"
        path.write_text(path.read_text().replace("status: active", "status: retired"))
        with self.assertRaises(ac.AuthorityChainError) as raised:
            ac.resolve_commit_chain(
                self.git.repo,
                signed.commit,
            )
        self.assertEqual(raised.exception.code, ac.AuthorityErrorCode.ACTIVATION_RETIRED)

    def test_verifier_ignores_stale_snapshot_and_reads_retirement_from_disk(self):
        activation, minted = self.mint_record("a1000004", "alpha", "A1")
        signed = ac.sign_commit(
            self.git.repo,
            activation,
            "fresh canonical reads only",
        )
        stale_records = ac.load_activation_entries(self.vault_files)
        path = self.vault_files / activation.uid
        path = path.with_suffix(".md")
        path.write_text(path.read_text().replace("status: active", "status: retired"))
        self.assertEqual(stale_records[0].status, "active")
        with self.assertRaises(ac.AuthorityChainError) as raised:
            ac.resolve_commit_chain(self.git.repo, signed.commit)
        self.assertEqual(raised.exception.code, ac.AuthorityErrorCode.ACTIVATION_RETIRED)

    def test_verifier_waits_for_activation_retirement_lock_then_revalidates_snapshot(self):
        activation, minted = self.mint_record("a1000007", "alpha", "A1")
        signed = ac.sign_commit(
            self.git.repo,
            activation,
            "locked canonical retirement",
        )
        path = self.vault_files / f"{activation.uid}.md"
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            with ac.activation_state_lock(
                self.git.repo,
                activation.uid,
                exclusive=True,
            ):
                future = executor.submit(
                    ac.resolve_commit_chain,
                    self.git.repo,
                    signed.commit,
                )
                time.sleep(0.1)
                self.assertFalse(future.done())
                path.write_text(
                    path.read_text().replace("status: active", "status: retired")
                )
            with self.assertRaises(ac.AuthorityChainError) as raised:
                future.result(timeout=30)
        self.assertEqual(raised.exception.code, ac.AuthorityErrorCode.ACTIVATION_RETIRED)

    def test_nonexistent_activated_by_is_a_named_chain_failure(self):
        activation, minted = self.mint_record("a1000005", "alpha", "A1")
        path = self.vault_files / f"{activation.uid}.md"
        path.write_text(path.read_text().replace("activated_by: user", "activated_by: ghost"))
        signed = ac.sign_commit(
            self.git.repo,
            activation,
            "ghost activator",
        )
        with self.assertRaises(ac.AuthorityChainError) as raised:
            ac.resolve_commit_chain(self.git.repo, signed.commit)
        self.assertEqual(raised.exception.code, ac.AuthorityErrorCode.ACTIVATOR_UNRESOLVED)

    def test_real_mike_alias_resolves_to_canonical_principal(self):
        _write_principal(
            self.vault_files,
            uid="7b921d17",
            slug="mike-maziarz",
            aliases=("mike-maziarz", "mike", "maz"),
        )
        activation, minted = self.mint_record(
            "a1000006",
            "alpha",
            "A1",
            activated_by="mike",
        )
        signed = ac.sign_commit(
            self.git.repo,
            activation,
            "canonical Mike alias",
        )
        result = ac.resolve_commit_chain(self.git.repo, signed.commit)
        self.assertEqual(result.activator_type, "principal")
        self.assertEqual(result.activator_uid, "7b921d17")

    def test_yaml_flow_alias_with_quoted_colon_resolves_canonically(self):
        (self.vault_files / "7b921d18.md").write_text(
            "---\n"
            "uid: 7b921d18\n"
            "type: principal\n"
            "slug: mike-maziarz\n"
            "name: Mike Maziarz\n"
            "status: active\n"
            "state: active\n"
            "may_sign_authority: false\n"
            'slug_aliases: [mike, "Michael: Maziarz"]\n'
            "---\n",
            encoding="utf-8",
        )
        activation, minted = self.mint_record(
            "a1000008",
            "alpha",
            "A1",
            activated_by='"Michael: Maziarz"',
        )
        signed = ac.sign_commit(
            self.git.repo,
            activation,
            "canonical quoted YAML alias",
        )
        result = ac.resolve_commit_chain(self.git.repo, signed.commit)
        self.assertEqual(result.activator_type, "principal")
        self.assertEqual(result.activator_uid, "7b921d18")

    def test_agent_key_can_never_satisfy_authority_gate(self):
        activation, minted = self.mint_record("a1000003", "alpha", "A1")
        signed = ac.sign_commit(
            self.git.repo,
            activation,
            "provenance is not authority",
        )
        with self.assertRaises(ac.AuthorityChainError) as raised:
            ac.resolve_commit_chain(
                self.git.repo,
                signed.commit,
                require_authority=True,
            )
        self.assertEqual(
            raised.exception.code,
            ac.AuthorityErrorCode.AGENT_KEY_PROVENANCE_ONLY,
        )

    def test_concurrent_agent_commits_keep_identity_local_and_config_unchanged(self):
        first, first_key = self.mint_record(
            "a1000011", "alpha", "A1", activated_at="2026-07-26T12:00:00Z"
        )
        second, second_key = self.mint_record(
            "b1000011", "beta", "B1", activated_at="2026-07-26T12:00:00Z"
        )
        config_before = self.git.config_path.read_bytes()

        def make_commit(record, minted, label):
            return ac.sign_commit(
                self.git.repo,
                record,
                label,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(make_commit, first, first_key, "alpha concurrent"),
                executor.submit(make_commit, second, second_key, "beta concurrent"),
            ]
            signed = [future.result(timeout=30) for future in futures]

        self.assertEqual(self.git.config_path.read_bytes(), config_before)
        resolved = [
            ac.resolve_commit_chain(self.git.repo, item.commit) for item in signed
        ]
        self.assertEqual({item.agent for item in resolved}, {"alpha", "beta"})
        expected_blobs = {
            ac.parse_openssh_public_key(first_key.public_key).blob,
            ac.parse_openssh_public_key(second_key.public_key).blob,
        }
        self.assertEqual({item.signature.key_blob for item in signed}, expected_blobs)

    def test_explicit_staging_invocation_has_no_add_all_flag(self):
        activation, minted = self.mint_record("a1000012", "alpha", "A1")
        intended = self.git.repo / "intended.txt"
        intended.write_text("only this path\n", encoding="utf-8")
        git_calls: list[tuple[str, ...]] = []
        real_git = ac._git

        def record_git(repo, *args, **kwargs):
            git_calls.append(args)
            return real_git(repo, *args, **kwargs)

        with patch.object(ac, "_git", side_effect=record_git):
            ac.sign_commit(
                self.git.repo,
                activation,
                "explicit path only",
                allow_empty=False,
                stage_paths=(intended,),
            )
        add_calls = [call for call in git_calls if call[:1] == ("add",)]
        self.assertEqual(add_calls, [("add", "--", "intended.txt")])
        self.assertNotIn("-A", add_calls[0])

    def test_update_ref_race_restores_exact_index_and_leaves_head_unchanged(self):
        activation, minted = self.mint_record("a1000013", "alpha", "A1")
        intended = self.git.repo / "race-intended.txt"
        intended.write_text("detached content\n", encoding="utf-8")
        foreign = self.git.repo / "race-foreign.txt"
        foreign.write_text("pre-staged foreign content\n", encoding="utf-8")
        _git(self.git.repo, "add", "--", "race-foreign.txt")
        head_before = _git(self.git.repo, "rev-parse", "HEAD").stdout.strip()
        index_path = Path(
            _git(self.git.repo, "rev-parse", "--git-path", "index").stdout.strip()
        )
        if not index_path.is_absolute():
            index_path = self.git.repo / index_path
        index_before = index_path.read_bytes()
        worktree_before = intended.read_bytes()
        real_git = ac._git

        def reject_ref_update(repo, *args, **kwargs):
            if args[:2] == ("update-ref", "HEAD"):
                return subprocess.CompletedProcess(
                    ["git", *args],
                    1,
                    "",
                    "simulated compare-and-swap race",
                )
            return real_git(repo, *args, **kwargs)

        with patch.object(ac, "_git", side_effect=reject_ref_update):
            with self.assertRaises(ac.AuthorityChainError) as raised:
                ac.sign_commit(
                    self.git.repo,
                    activation,
                    "must remain detached",
                    allow_empty=False,
                    stage_paths=(intended,),
                )
        self.assertEqual(raised.exception.code, ac.AuthorityErrorCode.GIT_REF_RACE)
        self.assertEqual(_git(self.git.repo, "rev-parse", "HEAD").stdout.strip(), head_before)
        self.assertEqual(index_path.read_bytes(), index_before)
        self.assertEqual(intended.read_bytes(), worktree_before)
        self.assertTrue(minted.broker_socket.exists())


@_NEEDS_SIGNER
class TestCriteria4And5HarnessPositivePlant(unittest.TestCase):
    def test_harness_probe_positively_forges_then_refuses_anchor(self):
        harness_key, _ = ac.discover_harness_signer(ROOT)
        result = ac.probe_harness_anchor(ROOT)
        self.assertTrue(result.attempted)
        self.assertTrue(result.reachable)
        self.assertFalse(result.authority_accepted)
        self.assertTrue(result.positive_control_passed)
        self.assertEqual(result.finding, ac.AuthorityErrorCode.ANCHOR_REACHABLE)
        self.assertEqual(
            result.candidate_classification,
            ac.AnchorClassification.KNOWN_HARNESS_KEY_AND_PROGRAM,
        )
        self.assertIsNotNone(result.signature)
        self.assertEqual(
            result.signature.key_blob,
            ac.parse_openssh_public_key(harness_key).blob,
        )
        self.assertEqual(
            result.signature.author_identity,
            "Forger <forge@test.local>",
        )

    def test_mike_authored_harness_commit_is_provenance_only(self):
        canary = ac.extract_commit_signature(ROOT, CANARY_COMMIT)
        harness_key, _ = ac.discover_harness_signer(ROOT)
        self.assertEqual(
            canary.key_blob,
            ac.parse_openssh_public_key(harness_key).blob,
        )
        self.assertEqual(canary.author_name, "Mike Maziarz")

        with patch.object(
            ac,
            "load_canonical_activation_entries",
            side_effect=AssertionError(
                "known harness provenance must short-circuit activation history"
            ),
        ):
            result = ac.resolve_commit_chain(ROOT, CANARY_COMMIT)
            self.assertEqual(result.provenance, "harness-provenance-only")
            self.assertFalse(result.authority)
            self.assertEqual(
                result.findings[0].code,
                ac.AuthorityErrorCode.HARNESS_KEY_PROVENANCE_ONLY,
            )
            with self.assertRaises(ac.AuthorityChainError) as raised:
                ac.resolve_commit_chain(
                    ROOT,
                    CANARY_COMMIT,
                    require_authority=True,
                )
        self.assertEqual(
            raised.exception.code,
            ac.AuthorityErrorCode.HARNESS_KEY_PROVENANCE_ONLY,
        )

    def test_false_program_cannot_launder_known_harness_key_into_authority(self):
        harness_key, _ = ac.discover_harness_signer(ROOT)
        probe = ac.probe_anchor_with_positive_control(
            ROOT,
            harness_key,
            signing_program="/bin/false",
        )
        self.assertTrue(probe.positive_control_passed)
        self.assertTrue(probe.reachable)
        self.assertFalse(probe.authority_accepted)
        self.assertEqual(
            probe.candidate_classification,
            ac.AnchorClassification.KNOWN_HARNESS_KEY,
        )
        with patch.object(
            ac,
            "load_canonical_activation_entries",
            side_effect=AssertionError(
                "known harness authority refusal must short-circuit activation history"
            ),
        ):
            with self.assertRaises(ac.AuthorityChainError) as raised:
                ac.verify_authority_claim(ROOT, CANARY_COMMIT, probe)
        self.assertEqual(
            raised.exception.code,
            ac.AuthorityErrorCode.HARNESS_KEY_PROVENANCE_ONLY,
        )


class TestCriterion6DerivedAllowedSigners(AuthorityFixture):
    def test_retirement_drops_key_without_signer_artifact(self):
        activation, _ = self.mint_record("a2000001", "alpha", "A1")
        before_files = {path.relative_to(self.root) for path in self.root.rglob("*") if path.is_file()}
        rendered = ac.derive_allowed_signers(
            ac.load_activation_entries(self.vault_files)
        )
        self.assertIn(activation.public_key.canonical, rendered)
        after_files = {path.relative_to(self.root) for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(after_files, before_files)
        self.assertFalse(any("allowed_signers" in str(path) for path in after_files))

        path = self.vault_files / "a2000001.md"
        path.write_text(path.read_text().replace("status: active", "status: retired"))
        rerendered = ac.derive_allowed_signers(
            ac.load_activation_entries(self.vault_files)
        )
        self.assertNotIn(activation.public_key.canonical, rerendered)
        self.assertEqual(rerendered, "")


class TestCriterion7CustodySurface(AuthorityFixture):
    def test_authority_key_without_custody_is_named_failure(self):
        _, minted = self.mint_record("a3000001", "alpha", "A1")
        principal = {
            "uid": "70000001",
            "type": "principal",
            "slug": "mike",
            "status": "active",
            "state": "active",
            "may_sign_authority": True,
            "authority_public_key": minted.public_key,
        }
        with self.assertRaises(ac.AuthorityChainError) as raised:
            ac.validate_authority_principals([principal])
        self.assertEqual(raised.exception.code, ac.AuthorityErrorCode.KEY_CUSTODY_MISSING)

    @_NEEDS_SIGNER
    def test_activation_key_refuses_every_authority_custody_relabel(self):
        activation, minted = self.mint_record("a30000a0", "alpha", "A1")
        signed = ac.sign_commit(
            self.git.repo,
            activation,
            "activation key custody relabel plant",
        )
        stages = (
            ("stage-1", "ephemeral", "activation-bound-runtime-key"),
            ("stage-2", "file", "principal-file-key"),
            ("stage-3", "fido2", "user-presence-hardware-key"),
        )
        for stage, custody, proof in stages:
            with self.subTest(custody=custody):
                principal = {
                    "uid": "700000a0",
                    "slug": "mike",
                    "status": "active",
                    "state": "active",
                    "may_sign_authority": True,
                    "authority_public_key": minted.public_key,
                    "key_custody": custody,
                }
                _write_principal(
                    self.vault_files,
                    uid="700000a0",
                    slug="mike",
                    public_key=minted.public_key,
                    may_sign_authority=True,
                    key_custody=custody,
                )
                with self.assertRaises(ac.AuthorityChainError) as refused:
                    ac.verify_stage_authority_claim(
                        self.git.repo,
                        signed.commit,
                        principal,
                        stage=stage,
                        custody_evidence={"stage": stage, "proof": proof},
                    )
                self.assertEqual(
                    refused.exception.code,
                    ac.AuthorityErrorCode.AGENT_KEY_PROVENANCE_ONLY,
                )

        forged_probe = ac.ReachabilityProbeResult(
            attempted=True,
            reachable=False,
            authority_accepted=True,
            positive_control_passed=True,
            finding=ac.AuthorityErrorCode.ANCHOR_UNREACHABLE,
            candidate_public_key=minted.public_key,
            signing_program="/bin/false",
            fabricated_author="Forger <forge@test.local>",
        )
        with self.assertRaises(ac.AuthorityChainError) as authority_refusal:
            ac.verify_authority_claim(
                self.git.repo,
                signed.commit,
                forged_probe,
            )
        self.assertEqual(
            authority_refusal.exception.code,
            ac.AuthorityErrorCode.AGENT_KEY_PROVENANCE_ONLY,
        )

    @_NEEDS_SIGNER
    def test_custody_is_structural_but_negative_probe_never_grants_authority(self):
        minted = ac.mint_agent_keypair("a3000002", "principal", "P1")
        self.minted_uids.add("a3000002")
        commit = _external_signed_commit(
            self.git.repo,
            minted,
            author_name="Mike Authority",
            author_email="mike@test.local",
            message="authority fixture",
        )
        ssh_keygen = shutil.which("ssh-keygen")
        self.assertIsNotNone(ssh_keygen)
        # Deliberately supply only the public key to stock ssh-keygen.  The
        # attempt executes but cannot sign because this key is not in its agent.
        bare_unreachable = ac.probe_anchor_reachability(
            minted.public_key,
            signing_program=ssh_keygen,
        )
        self.assertFalse(bare_unreachable.reachable)
        self.assertFalse(bare_unreachable.positive_control_passed)
        self.assertFalse(bare_unreachable.authority_accepted)
        principal = {
            "uid": "70000002",
            "type": "principal",
            "slug": "mike",
            "status": "active",
            "state": "active",
            "may_sign_authority": True,
            "authority_public_key": minted.public_key,
            "key_custody": "file",
        }
        self.assertIn("key_custody", ac.authority_claim_shape(principal))
        _write_principal(
            self.vault_files,
            uid="70000002",
            slug="mike",
            public_key=minted.public_key,
            may_sign_authority=True,
            key_custody="file",
        )
        with self.assertRaises(ac.AuthorityChainError) as bare_refusal:
            ac.verify_authority_claim(
                self.git.repo,
                commit,
                bare_unreachable,
            )
        self.assertEqual(
            bare_refusal.exception.code,
            ac.AuthorityErrorCode.AUTHORITY_REACHABILITY_UNPROVEN,
        )

        unreachable = ac.probe_anchor_with_positive_control(
            ROOT,
            minted.public_key,
            signing_program=ssh_keygen,
        )
        self.assertTrue(unreachable.attempted)
        self.assertFalse(unreachable.reachable)
        self.assertTrue(unreachable.positive_control_passed)
        self.assertFalse(unreachable.authority_accepted)
        with self.assertRaises(ac.AuthorityChainError) as refused:
            ac.verify_authority_claim(
                self.git.repo,
                commit,
                unreachable,
            )
        self.assertEqual(
            refused.exception.code,
            ac.AuthorityErrorCode.AUTHORITY_REACHABILITY_UNPROVEN,
        )

        false_program = ac.probe_anchor_with_positive_control(
            ROOT,
            minted.public_key,
            signing_program="/bin/false",
        )
        self.assertFalse(false_program.reachable)
        self.assertFalse(false_program.authority_accepted)
        with self.assertRaises(ac.AuthorityChainError) as false_program_refusal:
            ac.verify_authority_claim(
                self.git.repo,
                commit,
                false_program,
            )
        self.assertEqual(
            false_program_refusal.exception.code,
            ac.AuthorityErrorCode.AUTHORITY_REACHABILITY_UNPROVEN,
        )

        forged_claim = ac.ReachabilityProbeResult(
            attempted=True,
            reachable=False,
            authority_accepted=True,
            positive_control_passed=True,
            finding=ac.AuthorityErrorCode.ANCHOR_UNREACHABLE,
            candidate_public_key=minted.public_key,
            signing_program="/bin/false",
            fabricated_author="Forger <forge@test.local>",
            positive_control_key=ac.discover_harness_signer(ROOT)[0],
            positive_control_commit="caller-forged-proof",
        )
        with self.assertRaises(ac.AuthorityChainError) as forged_refusal:
            ac.verify_authority_claim(
                self.git.repo,
                commit,
                forged_claim,
            )
        self.assertEqual(
            forged_refusal.exception.code,
            ac.AuthorityErrorCode.AUTHORITY_REACHABILITY_UNPROVEN,
        )

    @_NEEDS_SIGNER
    def test_exact_commit_signature_is_verified_and_tampered_payload_is_rejected(self):
        minted = ac.mint_agent_keypair("a3000003", "principal", "P1")
        self.minted_uids.add("a3000003")
        commit = _external_signed_commit(
            self.git.repo,
            minted,
            author_name="Mike Authority",
            author_email="mike@test.local",
            message="authority exact commit",
        )
        _write_principal(
            self.vault_files,
            uid="70000003",
            slug="mike",
            public_key=minted.public_key,
            may_sign_authority=True,
            key_custody="file",
        )
        probe = ac.probe_anchor_with_positive_control(
            ROOT,
            minted.public_key,
            signing_program=shutil.which("ssh-keygen"),
        )
        with self.assertRaises(ac.AuthorityChainError) as original:
            ac.verify_authority_claim(self.git.repo, commit, probe)
        self.assertEqual(
            original.exception.code,
            ac.AuthorityErrorCode.AUTHORITY_REACHABILITY_UNPROVEN,
        )

        tampered_commit = _tamper_commit_author(self.git.repo, commit)
        with self.assertRaises(ac.AuthorityChainError) as raised:
            ac.verify_authority_claim(self.git.repo, tampered_commit, probe)
        self.assertEqual(raised.exception.code, ac.AuthorityErrorCode.SIGNATURE_INVALID)

    @_NEEDS_SIGNER
    def test_authority_principal_must_be_active_unrevoked_and_explicitly_eligible(self):
        minted = ac.mint_agent_keypair("a3000004", "principal", "P1")
        self.minted_uids.add("a3000004")
        commit = _external_signed_commit(
            self.git.repo,
            minted,
            author_name="Mike Authority",
            author_email="mike@test.local",
            message="principal eligibility",
        )
        probe = ac.probe_anchor_with_positive_control(
            ROOT,
            minted.public_key,
            signing_program=shutil.which("ssh-keygen"),
        )
        cases = (
            {"may_sign_authority": False},
            {"status": "retired", "may_sign_authority": True},
            {"revoked_at": "2026-07-26", "may_sign_authority": True},
        )
        for index, overrides in enumerate(cases):
            with self.subTest(case=index):
                _write_principal(
                    self.vault_files,
                    uid="70000004",
                    slug="mike",
                    status=overrides.get("status", "active"),
                    public_key=minted.public_key,
                    may_sign_authority=overrides["may_sign_authority"],
                    key_custody="file",
                    revoked_at=overrides.get("revoked_at"),
                )
                with self.assertRaises(ac.AuthorityChainError) as raised:
                    ac.verify_authority_claim(self.git.repo, commit, probe)
                self.assertEqual(
                    raised.exception.code,
                    ac.AuthorityErrorCode.AUTHORITY_PRINCIPAL_INELIGIBLE,
                )

    def test_unrelated_retired_principal_does_not_block_active_principal(self):
        _, active_key = self.mint_record("a3000005", "alpha", "A1")
        _, retired_key = self.mint_record("b3000005", "beta", "B1")
        active = {
            "uid": "70000005",
            "type": "principal",
            "slug": "active",
            "status": "active",
            "may_sign_authority": True,
            "authority_public_key": active_key.public_key,
            "key_custody": "file",
        }
        retired = {
            "uid": "70000006",
            "type": "principal",
            "slug": "retired",
            "status": "retired",
            "may_sign_authority": True,
            "authority_public_key": retired_key.public_key,
            "key_custody": "file",
        }
        eligible = ac.validate_authority_principals([retired, active])
        self.assertEqual([principal["uid"] for principal in eligible], ["70000005"])


class TestMutationGuards(AuthorityFixture):
    def test_mutation_deleting_author_identity_guard_is_killed(self):
        activation, minted = self.mint_record("a7000001", "alpha", "A1")
        signed = ac.sign_commit(
            self.git.repo,
            activation,
            "wrong-author mutation plant",
            author_name="Impostor",
            author_email="impostor@test.local",
        )

        def refusal_oracle() -> None:
            with self.assertRaises(ac.AuthorityChainError) as raised:
                ac.resolve_commit_chain(self.git.repo, signed.commit)
            self.assertEqual(
                raised.exception.code,
                ac.AuthorityErrorCode.AUTHOR_IDENTITY_MISMATCH,
            )

        refusal_oracle()
        with patch.object(
            ac,
            "_require_activation_author_identity",
            return_value=None,
        ):
            with self.assertRaises(AssertionError):
                refusal_oracle()

    def test_mutation_deleting_chain_crypto_verification_is_killed(self):
        activation, minted = self.mint_record("a7000002", "alpha", "A1")
        signed = ac.sign_commit(
            self.git.repo,
            activation,
            "chain crypto mutation plant",
        )
        tampered = _tamper_commit_message(self.git.repo, signed.commit)

        def refusal_oracle() -> None:
            with self.assertRaises(ac.AuthorityChainError) as raised:
                ac.resolve_commit_chain(self.git.repo, tampered)
            self.assertEqual(
                raised.exception.code,
                ac.AuthorityErrorCode.SIGNATURE_INVALID,
            )

        refusal_oracle()
        with patch.object(ac, "_verify_commit_with_signers", return_value=None):
            with self.assertRaises(AssertionError):
                refusal_oracle()

    def test_mutation_deleting_detached_commit_crypto_verification_is_killed(self):
        activation, minted = self.mint_record("a7000003", "alpha", "A1")
        crypto_failure = ac.AuthorityChainError(
            ac.AuthorityErrorCode.SIGNATURE_INVALID,
            "injected detached verification refusal",
        )

        def publication_oracle() -> None:
            head_before = _git(self.git.repo, "rev-parse", "HEAD").stdout.strip()
            with patch.object(
                ac,
                "_verify_commit_with_signers",
                side_effect=crypto_failure,
            ):
                with self.assertRaises(ac.AuthorityChainError) as raised:
                    ac.sign_commit(
                        self.git.repo,
                        activation,
                        "detached crypto mutation plant",
                    )
            self.assertEqual(
                raised.exception.code,
                ac.AuthorityErrorCode.SIGNATURE_INVALID,
            )
            self.assertEqual(
                _git(self.git.repo, "rev-parse", "HEAD").stdout.strip(),
                head_before,
            )

        publication_oracle()
        pre_mutant_head = _git(self.git.repo, "rev-parse", "HEAD").stdout.strip()
        with patch.object(ac, "_verify_one_key", return_value=None):
            with self.assertRaises(AssertionError):
                publication_oracle()
        self.assertNotEqual(
            _git(self.git.repo, "rev-parse", "HEAD").stdout.strip(),
            pre_mutant_head,
        )

    def test_mutation_deleting_stage_claim_key_equality_is_killed(self):
        principal_key = ac.mint_agent_keypair("a7100001", "principal", "P1")
        wrong_key = ac.mint_agent_keypair("a7100002", "wrong", "W1")
        self.minted_uids.update({"a7100001", "a7100002"})
        principal = {
            "uid": "72000001",
            "slug": "mike",
            "status": "active",
            "state": "active",
            "may_sign_authority": True,
            "authority_public_key": principal_key.public_key,
            "key_custody": "file",
        }
        _write_principal(
            self.vault_files,
            uid=principal["uid"],
            slug=principal["slug"],
            public_key=principal["authority_public_key"],
            may_sign_authority=True,
            key_custody="file",
        )
        commit = _external_signed_commit(
            self.git.repo,
            wrong_key,
            author_name="Wrong Stage Signer",
            author_email="wrong@test.local",
            message="stage key-equality mutation plant",
        )

        def refusal_oracle() -> None:
            with patch.object(ac, "_verify_one_key", return_value=None):
                with self.assertRaises(ac.AuthorityChainError) as refusal:
                    ac.verify_stage_authority_claim(
                        self.git.repo,
                        commit,
                        principal,
                        stage="stage-2",
                        custody_evidence={
                            "stage": "stage-2",
                            "proof": "principal-file-key",
                        },
                    )
            self.assertEqual(
                refusal.exception.code,
                ac.AuthorityErrorCode.SIGNING_KEY_MISMATCH,
            )

        refusal_oracle()
        with patch.object(
            ac,
            "_require_stage_signature_key_match",
            return_value=None,
        ):
            with self.assertRaises(AssertionError):
                refusal_oracle()

    def test_mutation_deleting_stage_claim_crypto_verification_is_killed(self):
        principal_key = ac.mint_agent_keypair("a7200001", "principal", "P2")
        self.minted_uids.add("a7200001")
        principal = {
            "uid": "72000002",
            "slug": "mike",
            "status": "active",
            "state": "active",
            "may_sign_authority": True,
            "authority_public_key": principal_key.public_key,
            "key_custody": "file",
        }
        _write_principal(
            self.vault_files,
            uid=principal["uid"],
            slug=principal["slug"],
            public_key=principal["authority_public_key"],
            may_sign_authority=True,
            key_custody="file",
        )
        signed = _external_signed_commit(
            self.git.repo,
            principal_key,
            author_name="Mike Custody Fixture",
            author_email="mike@test.local",
            message="stage crypto mutation plant",
        )
        tampered = _tamper_commit_message(self.git.repo, signed)

        def refusal_oracle() -> None:
            with self.assertRaises(ac.AuthorityChainError) as refusal:
                ac.verify_stage_authority_claim(
                    self.git.repo,
                    tampered,
                    principal,
                    stage="stage-2",
                    custody_evidence={
                        "stage": "stage-2",
                        "proof": "principal-file-key",
                    },
                )
            self.assertEqual(
                refusal.exception.code,
                ac.AuthorityErrorCode.SIGNATURE_INVALID,
            )

        refusal_oracle()
        with patch.object(ac, "_verify_one_key", return_value=None):
            with self.assertRaises(AssertionError):
                refusal_oracle()


class TestCriterion8IdentityCollapse(AuthorityFixture):
    def test_retired_predecessor_key_cannot_be_reused_by_active_successor(self):
        predecessor, minted = self.mint_record(
            "a4000000",
            "alpha",
            "A1",
            status="retired",
            activated_at="2026-07-25T12:00:00Z",
        )
        _write_activation(
            self.vault_files,
            uid="a4000001",
            agent="alpha",
            generation="A2",
            status="active",
            public_key=minted.public_key,
            activated_at="2026-07-26T12:00:00Z",
        )
        records = ac.load_activation_entries(self.vault_files)
        successor = next(record for record in records if record.uid == "a4000001")
        analysis = ac.analyze_activations(records)
        self.assertTrue(analysis.is_gate_valid(predecessor.uid))
        self.assertFalse(analysis.is_gate_valid(successor.uid))
        self.assertIn(
            ac.AuthorityErrorCode.ACTIVATION_KEY_REUSE,
            {
                finding.code
                for finding in analysis.reasons_for(successor.uid)
            },
        )
        self.assertNotIn(
            ac.canonical_git_identity(successor)[1],
            ac.derive_allowed_signers(records),
        )
        self.assertNotIn(
            ac.canonical_git_identity(successor)[1],
            ac.derive_canonical_allowed_signers(self.git.repo),
        )
        with self.assertRaises(ac.AuthorityChainError) as signing_refusal:
            ac.sign_commit(
                self.git.repo,
                successor,
                "successor must not inherit predecessor key",
            )
        self.assertEqual(
            signing_refusal.exception.code,
            ac.AuthorityErrorCode.ACTIVATION_GATE_INVALID,
        )

        author_name, author_email = ac.canonical_git_identity(successor)
        commit = _external_signed_commit(
            self.git.repo,
            minted,
            author_name=author_name,
            author_email=author_email,
            message="external predecessor-key signature claiming A2",
        )
        signature = ac.extract_commit_signature(self.git.repo, commit)
        ac._verify_one_key(self.git.repo, signature, "external-validity-control")
        with self.assertRaises(ac.AuthorityChainError) as chain_refusal:
            ac.resolve_commit_chain(self.git.repo, commit)
        self.assertEqual(
            chain_refusal.exception.code,
            ac.AuthorityErrorCode.ACTIVATION_GATE_INVALID,
        )
        reason_codes = {
            reason["code"]
            for reason in chain_refusal.exception.details["reasons"]
        }
        self.assertIn(
            ac.AuthorityErrorCode.ACTIVATION_KEY_REUSE.value,
            reason_codes,
        )

    def test_two_keys_one_slug_invalidates_every_nonterminal_entry(self):
        first, _ = self.mint_record(
            "a4000001", "alpha", "A1", activated_at="2026-07-26T12:00:00Z"
        )
        second, _ = self.mint_record(
            "a4000002", "alpha", "A2", activated_at="2026-07-26T12:01:00Z"
        )
        analysis = ac.analyze_activations(
            ac.load_activation_entries(self.vault_files)
        )
        self.assertFalse(analysis.is_gate_valid(first.uid))
        self.assertFalse(analysis.is_gate_valid(second.uid))
        self.assertIn(
            ac.AuthorityErrorCode.TWO_KEYS_ONE_SLUG,
            {finding.code for finding in analysis.findings},
        )

    def test_one_key_many_slugs_is_named_failure_from_activation_entries(self):
        _, minted = self.mint_record("a4000011", "alpha", "A1")
        _write_activation(
            self.vault_files,
            uid="b4000011",
            agent="beta",
            generation="B1",
            status="active",
            public_key=minted.public_key,
            activated_at="2026-07-26T12:01:00Z",
        )
        analysis = ac.analyze_activations(
            ac.load_activation_entries(self.vault_files)
        )
        self.assertIn(
            ac.AuthorityErrorCode.ONE_KEY_MANY_SLUGS,
            {finding.code for finding in analysis.findings},
        )
        self.assertFalse(analysis.is_gate_valid("a4000011"))
        self.assertFalse(analysis.is_gate_valid("b4000011"))

    @_NEEDS_SIGNER
    def test_live_one_key_three_authors_is_detected(self):
        harness_key, _ = ac.discover_harness_signer(ROOT)
        harness_blob = ac.parse_openssh_public_key(harness_key).blob
        mike = ac.extract_commit_signature(ROOT, CANARY_COMMIT)
        self.assertEqual(mike.key_blob, harness_blob)

        commits = _git(ROOT, "rev-list", "--max-count=400", "HEAD").stdout.splitlines()
        cursor_signature = None
        for commit in commits:
            try:
                candidate = ac.extract_commit_signature(ROOT, commit)
            except ac.AuthorityChainError as error:
                if error.code == ac.AuthorityErrorCode.SIGNATURE_MISSING:
                    continue
                raise
            if candidate.key_blob == harness_blob and candidate.author_name == "Cursor Agent":
                cursor_signature = candidate
                break
        self.assertIsNotNone(cursor_signature, "live harness-key Cursor Agent commit missing")

        forged = ac.probe_harness_anchor(ROOT)
        self.assertEqual(forged.signature.author_name, "Forger")
        with self.assertRaises(ac.AuthorityChainError) as raised:
            ac.detect_key_author_collapse(
                [mike, cursor_signature, forged.signature]
            )
        self.assertEqual(
            raised.exception.code,
            ac.AuthorityErrorCode.ONE_KEY_MANY_AUTHORS,
        )
        self.assertEqual(len(raised.exception.details["authors"]), 3)

    def test_mixed_pgp_signature_is_classified_and_skipped(self):
        activation, minted = self.mint_record("a4000021", "alpha", "A1")
        signed = ac.sign_commit(
            self.git.repo,
            activation,
            "supported SSH signature",
        )
        pgp_commit = _write_unsupported_pgp_commit(self.git.repo)
        audited = ac.audit_commits_for_identity_collapse(
            self.git.repo,
            [pgp_commit, signed.commit],
        )
        self.assertEqual(len(audited), 1)
        self.assertEqual(len(audited.skipped), 1)
        self.assertEqual(
            audited.skipped[0].code,
            ac.AuthorityErrorCode.SIGNATURE_UNSUPPORTED,
        )

    def test_mixed_pgp_does_not_mask_one_key_many_authors(self):
        activation, minted = self.mint_record("a4000022", "alpha", "A1")
        first = ac.sign_commit(
            self.git.repo,
            activation,
            "first author",
        )
        second = ac.sign_commit(
            self.git.repo,
            activation,
            "second author",
            author_name="Other Author",
            author_email="other@test.local",
        )
        pgp_commit = _write_unsupported_pgp_commit(self.git.repo)
        with self.assertRaises(ac.AuthorityChainError) as raised:
            ac.audit_commits_for_identity_collapse(
                self.git.repo,
                [pgp_commit, first.commit, second.commit],
            )
        self.assertEqual(
            raised.exception.code,
            ac.AuthorityErrorCode.ONE_KEY_MANY_AUTHORS,
        )


class TestLifecycleReuseProperties(AuthorityFixture):
    @staticmethod
    def _record(
        uid: str,
        generation: str,
        status: str,
        public_key: str,
        *,
        agent: str = "alpha",
        activated_at: str = "2026-07-26T12:00:00Z",
        predecessor_activation_uid: str | None = None,
    ) -> ac.ActivationRecord:
        return ac.ActivationRecord(
            uid=uid,
            agent=agent,
            generation=generation,
            status=status,
            activated_by="user",
            activated_at=activated_at,
            agent_public_key=public_key,
            name=f"{agent}-{generation.lower()}",
            agent_class="executive",
            predecessor_activation_uid=predecessor_activation_uid,
            predecessor_link_declared=True,
        )

    def test_duplicate_key_lifecycle_matrix_is_order_invariant(self):
        shared = ac.mint_agent_keypair("b4000001", "alpha", "A1")
        distinct = ac.mint_agent_keypair("b4000002", "alpha", "A2")
        self.minted_uids.update({"b4000001", "b4000002"})
        for live_status, historical_status, labels in itertools.product(
            ("active", "paused"),
            ("retired", "stale"),
            (("A1", "A2"), ("A99", "A1")),
        ):
            live = self._record(
                "b4000010",
                labels[0],
                live_status,
                shared.public_key,
                activated_at="2026-07-25T12:00:00Z",
            )
            historical = self._record(
                "b4000011",
                labels[1],
                historical_status,
                shared.public_key,
                activated_at="2026-07-26T12:00:00Z",
            )
            for ordering in itertools.permutations((live, historical)):
                with self.subTest(
                    live=live_status,
                    historical=historical_status,
                    labels=labels,
                    order=[record.uid for record in ordering],
                ):
                    analysis = ac.analyze_activations(ordering)
                    self.assertFalse(analysis.is_gate_valid(live.uid))
                    self.assertIn(
                        ac.AuthorityErrorCode.ACTIVATION_KEY_REUSE,
                        {
                            finding.code
                            for finding in analysis.reasons_for(live.uid)
                        },
                    )
                    self.assertNotIn(
                        ac.canonical_git_identity(live)[1],
                        ac.derive_allowed_signers(ordering),
                    )

        retired_pair = (
            self._record("b4000020", "A1", "retired", shared.public_key),
            self._record("b4000021", "A2", "stale", shared.public_key),
        )
        analysis = ac.analyze_activations(retired_pair)
        self.assertTrue(all(analysis.is_gate_valid(record.uid) for record in retired_pair))
        self.assertIn(
            ac.AuthorityErrorCode.ACTIVATION_KEY_REUSE,
            {finding.code for finding in analysis.findings},
        )
        self.assertEqual(ac.derive_allowed_signers(retired_pair), "")

        legal = (
            self._record("b4000030", "A1", "retired", shared.public_key),
            self._record(
                "b4000031",
                "A2",
                "active",
                distinct.public_key,
                predecessor_activation_uid="b4000030",
            ),
        )
        for ordering in itertools.permutations(legal):
            analysis = ac.analyze_activations(ordering)
            self.assertTrue(analysis.is_gate_valid("b4000031"))
            self.assertIn("alpha-a2@agents.tropo.local", ac.derive_allowed_signers(ordering))

    def test_simultaneous_nonterminal_two_key_matrix_refuses_every_holder(self):
        first = ac.mint_agent_keypair("b4000040", "alpha", "A1")
        second = ac.mint_agent_keypair("b4000041", "alpha", "A2")
        self.minted_uids.update({"b4000040", "b4000041"})
        for statuses in itertools.product(("active", "paused"), repeat=2):
            records = (
                self._record("b4000040", "A1", statuses[0], first.public_key),
                self._record("b4000041", "A2", statuses[1], second.public_key),
            )
            for ordering in itertools.permutations(records):
                with self.subTest(statuses=statuses, order=[item.uid for item in ordering]):
                    analysis = ac.analyze_activations(ordering)
                    self.assertFalse(analysis.is_gate_valid("b4000040"))
                    self.assertFalse(analysis.is_gate_valid("b4000041"))
                    self.assertIn(
                        ac.AuthorityErrorCode.TWO_KEYS_ONE_SLUG,
                        {finding.code for finding in analysis.findings},
                    )

    def test_generation_label_fuzz_matrix_fails_closed_without_order_dependence(self):
        first = ac.mint_agent_keypair("b4000050", "alpha", "A1")
        second = ac.mint_agent_keypair("b4000051", "alpha", "A2")
        self.minted_uids.update({"b4000050", "b4000051"})
        malformed_labels = ("", "A1-resume", "A01", "A" + ("9" * 128))
        randomizer = random.Random(8428)
        for label in malformed_labels:
            records = [
                self._record("b4000050", label, "active", first.public_key),
                self._record("b4000051", "A1", "retired", second.public_key),
            ]
            for _ in range(6):
                randomizer.shuffle(records)
                with self.subTest(label=label, order=[item.uid for item in records]):
                    analysis = ac.analyze_activations(tuple(records))
                    self.assertFalse(analysis.is_gate_valid("b4000050"))
                    codes = {
                        finding.code
                        for finding in analysis.reasons_for("b4000050")
                    }
                    expected = (
                        ac.AuthorityErrorCode.ACTIVATION_LINEAGE_INCOMPLETE
                        if label.startswith("A9")
                        else ac.AuthorityErrorCode.ACTIVATION_GENERATION_INVALID
                    )
                    self.assertIn(expected, codes)

        duplicate_generation = (
            self._record("b4000060", "A1", "retired", first.public_key),
            self._record("b4000061", "A1", "active", second.public_key),
        )
        for ordering in itertools.permutations(duplicate_generation):
            analysis = ac.analyze_activations(ordering)
            self.assertFalse(analysis.is_gate_valid("b4000061"))
            self.assertIn(
                ac.AuthorityErrorCode.ACTIVATION_GENERATION_INVALID,
                {
                    finding.code
                    for finding in analysis.reasons_for("b4000061")
                },
            )

    def test_activation_class_equivalence_is_declared_once(self):
        """cosmo/tropo carry a role class on the root and boot as another.

        The pairing lived only inside load_canonical_agent_classes, so the
        resolver tolerated these agents while the predecessor gate refused them
        with a bare `!=` -- making cosmo and tropo the only two agents in the
        Studio that could never be born (vela-v71, 2026-07-31). Sibling drift:
        the knowledge existed in one function and not its neighbour.
        """
        self.assertEqual(
            ac._activation_compatible_classes("cosmo"), {"cosmo", "executive"}
        )
        self.assertEqual(
            ac._activation_compatible_classes("tropo"), {"tropo", "concierge"}
        )
        # Symmetric: the gate compares in both directions.
        self.assertTrue(ac._classes_activation_compatible("cosmo", "executive"))
        self.assertTrue(ac._classes_activation_compatible("executive", "cosmo"))
        # And it is not a free-for-all.
        self.assertFalse(ac._classes_activation_compatible("sa", "executive"))
        self.assertFalse(ac._classes_activation_compatible("cosmo", "tropo"))

    def test_unparseable_snapshot_that_AGREES_is_not_poison(self):
        """An unparseable file is not automatically an unaccountable one.

        A YAML break in a descriptive field left every identity field and the
        key readable and identical to the canonical entry, yet blocked the whole
        vela lineage. The cure reads the snapshot rather than excusing it: it
        clears only when everything comparable agrees, and retains the poison the
        moment anything disagrees or is unreadable.
        """
        from dataclasses import replace

        key = ac.mint_agent_keypair("b4000090", "alpha", "A1")
        self.minted_uids.add("b4000090")
        canonical = replace(
            self._record("b4000090", "A1", "retired", key.public_key),
            agent_root="a0000001",
        )
        broken = replace(
            canonical,
            status="history-invalid",
            history_invalid=True,
            history_invalid_code=(
                ac.AuthorityErrorCode.ACTIVATION_HISTORY_UNPARSEABLE
            ),
            history_invalid_reason="frontmatter is unparseable",
            history_only=True,
        )

        healed = ac._reconciled_unparseable(broken, canonical)
        self.assertFalse(healed.history_invalid, "agreeing snapshot still poisons")

        # Disagreement on any comparable field keeps the refusal.
        for field, value in (
            ("generation", "A2"),
            ("agent", "beta"),
            ("agent_public_key", ac.mint_agent_keypair(
                "b4000091", "alpha", "A9").public_key),
        ):
            self.minted_uids.add("b4000091")
            with self.subTest(field=field):
                self.assertTrue(
                    ac._reconciled_unparseable(
                        replace(broken, **{field: value}), canonical
                    ).history_invalid,
                    f"a snapshot disagreeing on {field} was waved through",
                )

        # An unreadable field is one we cannot vouch for: keep the poison.
        self.assertTrue(
            ac._reconciled_unparseable(
                replace(broken, agent_public_key=None), canonical
            ).history_invalid
        )

    def test_generation_letter_case_is_not_identity(self):
        """Historical lowercase labels normalize; real malformations still fail."""
        from dataclasses import replace

        self.assertEqual(ac.canonical_executive_generation("a67"), ("A", 67))
        self.assertEqual(ac.canonical_executive_generation("A67"), ("A", 67))
        self.assertEqual(ac.normalize_generation_label("a67"), "A67")
        self.assertIsNone(ac.canonical_executive_generation(""))
        self.assertIsNone(ac.canonical_executive_generation("A1-resume"))
        self.assertIsNone(ac.canonical_executive_generation("A01"))

        key = ac.mint_agent_keypair("b4000080", "alpha", "A1")
        live_key = ac.mint_agent_keypair("b4000081", "alpha", "A2")
        self.minted_uids.update({"b4000080", "b4000081"})

        # Same UID across snapshots with only letter-case drift must not poison.
        snapshots = [
            replace(self._record("b4000080", "A1", "retired", key.public_key)),
            replace(
                self._record("b4000080", "a1", "retired", key.public_key),
                history_only=True,
                generation=ac.normalize_generation_label("a1"),
            ),
        ]
        snapshots[0] = replace(
            snapshots[0],
            generation=ac.normalize_generation_label(snapshots[0].generation),
        )
        self.assertEqual(ac._snapshot_identity_conflicts(snapshots), ())

        # Lowercase historical predecessor must not block a live successor.
        records = (
            replace(
                self._record("b4000080", "a1", "retired", key.public_key),
                generation=ac.normalize_generation_label("a1"),
            ),
            replace(
                self._record("b4000081", "A2", "active", live_key.public_key),
                generation=ac.normalize_generation_label("A2"),
                predecessor_activation_uid="b4000080",
            ),
        )
        analysis = ac.analyze_activations(records)
        self.assertTrue(analysis.is_gate_valid("b4000081"))
        self.assertNotIn(
            ac.AuthorityErrorCode.ACTIVATION_GENERATION_INVALID,
            {finding.code for finding in analysis.findings},
        )

        # Loader normalizes bytes on the way in — file can stay lowercase on disk.
        _write_activation(
            self.vault_files,
            uid="b4000082",
            agent="alpha",
            generation="a3",
            status="retired",
            public_key=ac.mint_agent_keypair("b4000082", "alpha", "A3").public_key,
            activated_at="2026-07-25T12:00:00Z",
        )
        self.minted_uids.add("b4000082")
        loaded = {
            record.uid: record
            for record in ac.load_canonical_activation_entries(self.git.repo)
        }
        self.assertEqual(loaded["b4000082"].generation, "A3")
        self.assertFalse(loaded["b4000082"].history_invalid)

    def test_recycle_and_archive_history_poison_reused_live_keys(self):
        recycle_key = ac.mint_agent_keypair("b4000070", "alpha", "A1")
        archive_key = ac.mint_agent_keypair("b4000071", "beta", "B1")
        self.minted_uids.update({"b4000070", "b4000071"})
        preserved = (
            (
                self.git.repo / "recycle" / "agent-deletions" / "2026-07-27",
                "b4000070",
                "b400007a",
                "alpha",
                "A1",
                recycle_key.public_key,
            ),
            (
                self.git.repo / "archive" / "activation-history",
                "b4000071",
                "b400007b",
                "beta",
                "B1",
                archive_key.public_key,
            ),
        )
        for directory, uid, live_uid, agent, generation, key in preserved:
            directory.mkdir(parents=True)
            _write_activation(
                directory,
                uid=uid,
                agent=agent,
                generation=generation,
                status="retired",
                public_key=key,
                activated_at="2026-07-25T12:00:00Z",
            )
            _write_activation(
                self.vault_files,
                uid=live_uid,
                agent=agent,
                generation=f"{generation[0]}2",
                status="active",
                public_key=key,
                activated_at="2026-07-26T12:00:00Z",
            )

        records = ac.load_canonical_activation_entries(self.git.repo)
        analysis = ac.analyze_activations(records)
        for uid in ("b400007a", "b400007b"):
            self.assertFalse(analysis.is_gate_valid(uid))
        active_records = [record for record in records if record.status == "active"]
        self.assertEqual(ac.derive_canonical_allowed_signers(self.git.repo), "")
        self.assertEqual(len(active_records), 2)
        for ordering in itertools.permutations(records):
            permuted = ac.analyze_activations(ordering)
            self.assertTrue(
                all(not permuted.is_gate_valid(record.uid) for record in active_records)
            )

        alpha = next(record for record in active_records if record.agent == "alpha")
        author_name, author_email = ac.canonical_git_identity(alpha)
        commit = _external_signed_commit(
            self.git.repo,
            recycle_key,
            author_name=author_name,
            author_email=author_email,
            message="recycled predecessor key claiming live generation",
        )
        with self.assertRaises(ac.AuthorityChainError) as refusal:
            ac.resolve_commit_chain(self.git.repo, commit)
        self.assertEqual(
            refusal.exception.code,
            ac.AuthorityErrorCode.ACTIVATION_GATE_INVALID,
        )

    def test_all_keyed_classes_follow_predecessor_links_through_recycle(self):
        classes = (
            "executive",
            "director",
            "cosmo",
            "tropo",
            "sa",
            "worker",
            "child-agent",
            "pipeline",
        )
        prefixes = {
            "executive": "E",
            "director": "D",
            "cosmo": "C",
            "tropo": "T",
        }
        recycle = self.git.repo / "recycle" / "linked-class-history"
        recycle.mkdir(parents=True)
        fixtures = []
        for index, agent_class in enumerate(classes):
            agent = f"linked-history-{agent_class}"
            predecessor_uid = f"b6{index:06x}"
            live_uid = f"b7{index:06x}"
            root_uid = f"e6{index:06x}"
            prefix = prefixes.get(agent_class, "")
            predecessor_generation = f"{prefix}1" if prefix else "opaque-previous"
            live_generation = f"{prefix}2" if prefix else "opaque-current"
            _write_agent_root(
                self.vault_files,
                uid=root_uid,
                agent=agent,
                agent_class=agent_class,
                generation_prefix=prefix,
            )
            _write_unified_agent(
                self.git.repo,
                uid=f"c6{index:06x}",
                agent=agent,
                agent_class=agent_class,
            )
            predecessor_key = ac.mint_agent_keypair(
                predecessor_uid,
                agent,
                predecessor_generation,
            )
            live_key = ac.mint_agent_keypair(live_uid, agent, live_generation)
            self.minted_uids.update({predecessor_uid, live_uid})
            predecessor_path = _write_activation(
                recycle,
                uid=predecessor_uid,
                agent=agent,
                generation=predecessor_generation,
                status="retired",
                public_key=predecessor_key.public_key,
                activated_at="2026-07-25T12:00:00Z",
                agent_class=agent_class,
            )
            _write_activation(
                self.vault_files,
                uid=live_uid,
                agent=agent,
                generation=live_generation,
                status="active",
                public_key=live_key.public_key,
                activated_at="2026-07-26T12:00:00Z",
                agent_class=agent_class,
                predecessor_activation_uid=predecessor_uid,
            )
            fixtures.append((agent_class, predecessor_path, live_uid))

        records = ac.load_canonical_activation_entries(self.git.repo)
        analysis = ac.analyze_activations(records)
        for agent_class, _predecessor_path, live_uid in fixtures:
            with self.subTest(agent_class=agent_class, state="present"):
                self.assertTrue(analysis.is_gate_valid(live_uid))

        for agent_class, predecessor_path, live_uid in fixtures:
            predecessor_bytes = predecessor_path.read_bytes()
            predecessor_path.unlink()
            with self.subTest(agent_class=agent_class, state="missing"):
                missing = ac.analyze_activations(
                    ac.load_canonical_activation_entries(self.git.repo)
                )
                self.assertFalse(missing.is_gate_valid(live_uid))
                self.assertIn(
                    ac.AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
                    {
                        finding.code
                        for finding in missing.reasons_for(live_uid)
                    },
                )
            predecessor_path.write_bytes(predecessor_bytes)

    def test_universal_genesis_skip_and_durable_history_matrix(self):
        classes = (
            "executive",
            "director",
            "cosmo",
            "tropo",
            "sa",
            "worker",
            "child-agent",
            "pipeline",
        )
        prefixes = {
            "executive": "E",
            "director": "D",
            "cosmo": "C",
            "tropo": "T",
            "sa": "sa-",
            "worker": "worker-",
            "child-agent": "child-",
            "pipeline": "pipeline-",
        }
        recycle = self.git.repo / "recycle" / "universal-lineage"
        recycle.mkdir(parents=True)
        key_index = 0
        fixture_index = 0
        expected: list[tuple[str, str, bool, str]] = []

        def public_key() -> str:
            nonlocal key_index
            key_index += 1
            algorithm = b"ssh-ed25519"
            point = key_index.to_bytes(2, "big") * 16
            blob = (
                struct.pack(">I", len(algorithm))
                + algorithm
                + struct.pack(">I", len(point))
                + point
            )
            return "ssh-ed25519 " + base64.b64encode(blob).decode("ascii")

        def generation(agent_class: str, number: int) -> str:
            prefix = prefixes[agent_class]
            if agent_class in ac.EXECUTIVE_GENERATION_CLASSES:
                return f"{prefix}{number}"
            return f"{prefix}{number:03d}"

        def register(agent: str, agent_class: str) -> None:
            nonlocal fixture_index
            _write_agent_root(
                self.vault_files,
                uid=f"e0{fixture_index:06x}",
                agent=agent,
                agent_class=agent_class,
                generation_prefix=(
                    prefixes[agent_class]
                    if agent_class in ac.EXECUTIVE_GENERATION_CLASSES
                    else ""
                ),
            )
            _write_unified_agent(
                self.git.repo,
                uid=f"e1{fixture_index:06x}",
                agent=agent,
                agent_class=agent_class,
            )
            fixture_index += 1

        def hard_delete(path: Path, label: str) -> None:
            relative = path.relative_to(self.git.repo)
            _git(self.git.repo, "add", str(relative))
            _git(
                self.git.repo,
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@test.local",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--no-gpg-sign",
                "-m",
                f"add {label}",
            )
            _git(self.git.repo, "rm", str(relative))
            _git(
                self.git.repo,
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@test.local",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--no-gpg-sign",
                "-m",
                f"hard delete {label}",
            )

        for index, agent_class in enumerate(classes):
            genesis_agent = f"genesis-{agent_class}"
            register(genesis_agent, agent_class)
            genesis_uid = f"d0{index:06x}"
            _write_activation(
                self.vault_files,
                uid=genesis_uid,
                agent=genesis_agent,
                generation=generation(agent_class, 1),
                status="active",
                public_key=public_key(),
                activated_at="2026-07-26T10:00:00Z",
                agent_class=agent_class,
            )
            expected.append(("genesis", genesis_uid, True, agent_class))

            null_agent = f"null-prior-{agent_class}"
            register(null_agent, agent_class)
            prior_uid = f"d1{index:06x}"
            current_uid = f"d2{index:06x}"
            location = index % 3
            prior_directory = (
                self.vault_files if location != 1 else recycle
            )
            prior_path = _write_activation(
                prior_directory,
                uid=prior_uid,
                agent=null_agent,
                generation=generation(agent_class, 1),
                status="retired",
                public_key=public_key(),
                activated_at="2026-07-25T10:00:00Z",
                agent_class=agent_class,
            )
            if location == 2:
                hard_delete(prior_path, f"null-{agent_class}")
            _write_activation(
                self.vault_files,
                uid=current_uid,
                agent=null_agent,
                generation=generation(agent_class, 2),
                status="active",
                public_key=public_key(),
                activated_at="2026-07-26T10:00:00Z",
                agent_class=agent_class,
            )
            expected.append(
                (
                    ("git" if location == 2 else "recycle" if location == 1 else "canonical")
                    + "-null",
                    current_uid,
                    False,
                    agent_class,
                )
            )

            skip_agent = f"skip-prior-{agent_class}"
            register(skip_agent, agent_class)
            first_uid = f"d3{index:06x}"
            skipped_uid = f"d4{index:06x}"
            latest_uid = f"d5{index:06x}"
            skip_generations = (
                tuple(generation(agent_class, number) for number in (1, 2, 3))
                if (
                    agent_class in ac.EXECUTIVE_GENERATION_CLASSES
                    or index % 2 == 0
                )
                else ("phase-alpha", "phase-beta", "phase-gamma")
            )
            _write_activation(
                self.vault_files,
                uid=first_uid,
                agent=skip_agent,
                generation=skip_generations[0],
                status="retired",
                public_key=public_key(),
                activated_at="2026-07-24T10:00:00Z",
                agent_class=agent_class,
            )
            skipped_location = (index + 1) % 3
            skipped_directory = (
                recycle if skipped_location == 1 else self.vault_files
            )
            skipped_path = _write_activation(
                skipped_directory,
                uid=skipped_uid,
                agent=skip_agent,
                generation=skip_generations[1],
                status="retired",
                public_key=public_key(),
                activated_at="2026-07-25T10:00:00Z",
                agent_class=agent_class,
                predecessor_activation_uid=first_uid,
            )
            if skipped_location == 2:
                hard_delete(skipped_path, f"skip-{agent_class}")
            _write_activation(
                self.vault_files,
                uid=latest_uid,
                agent=skip_agent,
                generation=skip_generations[2],
                status="active",
                public_key=public_key(),
                activated_at="2026-07-26T10:00:00Z",
                agent_class=agent_class,
                predecessor_activation_uid=first_uid,
            )
            expected.append(
                (
                    ("git" if skipped_location == 2 else "recycle" if skipped_location == 1 else "canonical")
                    + "-skip",
                    latest_uid,
                    False,
                    agent_class,
                )
            )

        records = ac.load_canonical_activation_entries(self.git.repo)
        history_only = {record.uid for record in records if record.history_only}
        self.assertTrue(history_only)
        analysis = ac.analyze_activations(records)
        for case, uid, expected_valid, agent_class in expected:
            with self.subTest(
                case=case,
                agent_class=agent_class,
            ):
                self.assertEqual(analysis.is_gate_valid(uid), expected_valid)
                if not expected_valid:
                    self.assertIn(
                        ac.AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
                        {
                            finding.code
                            for finding in analysis.reasons_for(uid)
                        },
                    )

    def test_predecessor_anchor_validity_matrix_canonical_and_recycled(self):
        recycle = self.git.repo / "recycle" / "anchor-validity"
        recycle.mkdir(parents=True)
        cases = (
            ("retired", self.vault_files, {}, True),
            ("stale", recycle, {}, True),
            ("failed", self.vault_files, {}, True),
            ("wrong-class", recycle, {"agent_class": "worker"}, False),
            ("missing-class", self.vault_files, {"remove": "agent_class"}, False),
            ("missing-status", recycle, {"remove": "status"}, False),
            ("invalid-status", self.vault_files, {"status": "archived"}, False),
            ("active", recycle, {}, False),
            ("paused", self.vault_files, {}, False),
            ("agent-mismatch", recycle, {"agent": "other"}, False),
            ("missing-uid", self.vault_files, {"remove": "uid"}, False),
            ("missing-type", recycle, {"remove": "type"}, False),
            ("wrong-type", self.vault_files, {"type": "memory"}, False),
            ("missing-generation", recycle, {"remove": "generation"}, False),
        )
        fixtures = []
        for index, (label, directory, mutations, expected_valid) in enumerate(cases):
            agent = f"anchor-{index}"
            predecessor_uid = f"c1{index:06x}"
            live_uid = f"c2{index:06x}"
            _write_agent_root(
                self.vault_files,
                uid=f"d1{index:06x}",
                agent=agent,
                agent_class="sa",
            )
            _write_unified_agent(
                self.git.repo,
                uid=f"e1{index:06x}",
                agent=agent,
                agent_class="sa",
                current_activation_uid=predecessor_uid,
            )
            predecessor_key = ac.mint_agent_keypair(
                predecessor_uid,
                agent,
                "previous",
            )
            live_key = ac.mint_agent_keypair(live_uid, agent, "current")
            ac.remove_agent_keypair(predecessor_uid)
            ac.remove_agent_keypair(live_uid)
            predecessor_status = (
                str(mutations["status"])
                if "status" in mutations
                else (
                    label
                    if label in ac.VALID_ACTIVATION_STATUSES
                    else "retired"
                )
            )
            predecessor_path = _write_activation(
                directory,
                uid=predecessor_uid,
                agent=(
                    f"other-{agent}"
                    if mutations.get("agent") == "other"
                    else agent
                ),
                generation="previous",
                status=predecessor_status,
                public_key=predecessor_key.public_key,
                activated_at="2026-07-25T12:00:00Z",
                agent_class=str(mutations.get("agent_class", "sa")),
            )
            text = predecessor_path.read_text(encoding="utf-8")
            if mutations.get("remove") == "agent_class":
                text = text.replace("agent_class: sa\n", "")
            elif mutations.get("remove") == "status":
                text = text.replace(f"status: {predecessor_status}\n", "")
            elif mutations.get("remove") == "uid":
                text = text.replace(f"uid: {predecessor_uid}\n", "")
            elif mutations.get("remove") == "type":
                text = text.replace("type: activation\n", "")
            elif mutations.get("remove") == "generation":
                text = text.replace("generation: previous\n", "")
            if "type" in mutations:
                text = text.replace(
                    "type: activation\n",
                    f"type: {mutations['type']}\n",
                )
            predecessor_path.write_text(text, encoding="utf-8")
            with self.subTest(case=label, phase="open-predecessor-derivation"):
                if expected_valid:
                    self.assertEqual(
                        ac.derive_new_activation_predecessor(
                            ac.load_canonical_activation_entries(self.git.repo),
                            agent,
                            "sa",
                            "current",
                            predecessor_uid,
                        ),
                        predecessor_uid,
                    )
                else:
                    with self.assertRaises(ac.AuthorityChainError) as refusal:
                        ac.derive_new_activation_predecessor(
                            ac.load_canonical_activation_entries(self.git.repo),
                            agent,
                            "sa",
                            "current",
                            predecessor_uid,
                        )
                    self.assertEqual(
                        refusal.exception.code,
                        ac.AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
                    )
            _write_activation(
                self.vault_files,
                uid=live_uid,
                agent=agent,
                generation="current",
                status="active",
                public_key=live_key.public_key,
                activated_at="2026-07-26T12:00:00Z",
                agent_class="sa",
                predecessor_activation_uid=predecessor_uid,
            )
            fixtures.append((label, live_uid, expected_valid, directory))

        analysis = ac.analyze_activations(
            ac.load_canonical_activation_entries(self.git.repo)
        )
        for label, live_uid, expected_valid, directory in fixtures:
            with self.subTest(
                case=label,
                location="recycle" if directory == recycle else "canonical",
            ):
                self.assertEqual(analysis.is_gate_valid(live_uid), expected_valid)
                codes = {
                    finding.code for finding in analysis.reasons_for(live_uid)
                }
                if expected_valid:
                    self.assertNotIn(
                        ac.AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
                        codes,
                    )
                else:
                    self.assertIn(
                        ac.AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
                        codes,
                    )

    def test_prelink_compatibility_is_exact_uid_only(self):
        legacy_key = ac.mint_agent_keypair("b8000000", "frozen", "T37")
        claimed_key = ac.mint_agent_keypair("b8000001", "claimed", "A1")
        self.minted_uids.update({"b8000000", "b8000001"})
        _write_activation(
            self.vault_files,
            uid="d37aeeb3",
            agent="frozen",
            generation="T36",
            status="retired",
            public_key=None,
            activated_at="2026-07-25T12:00:00Z",
        )
        _write_activation(
            self.vault_files,
            uid="d37aeeb4",
            agent="frozen",
            generation="T37",
            status="active",
            public_key=legacy_key.public_key,
            activated_at="2026-07-26T12:00:00Z",
            declare_predecessor=False,
        )
        claimed = _write_activation(
            self.vault_files,
            uid="b8000001",
            agent="claimed",
            generation="A1",
            status="active",
            public_key=claimed_key.public_key,
            activated_at="2026-07-26T12:00:00Z",
            declare_predecessor=False,
        )
        claimed.write_text(
            claimed.read_text(encoding="utf-8").replace(
                "agent_public_key:",
                "predecessor_compatibility: true\nagent_public_key:",
            ),
            encoding="utf-8",
        )
        analysis = ac.analyze_activations(
            ac.load_activation_entries(self.vault_files)
        )
        self.assertTrue(analysis.is_gate_valid("d37aeeb4"))
        self.assertFalse(analysis.is_gate_valid("b8000001"))
        self.assertIn(
            ac.AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
            {
                finding.code
                for finding in analysis.reasons_for("b8000001")
            },
        )

    def test_strict_public_key_wire_and_terminal_predecessor_poison(self):
        valid = ac.mint_agent_keypair("b8100000", "wire", "valid")
        self.minted_uids.add("b8100000")
        parsed = ac.parse_openssh_public_key(valid.public_key)

        def ssh_string(value: bytes) -> bytes:
            return struct.pack(">I", len(value)) + value

        algorithm = b"ssh-ed25519"
        valid_encoded = parsed.canonical.split()[1]
        malformed_keys = (
            f"ssh-ed25519 {valid_encoded[:-4]}",
            "ssh-ed25519 "
            + base64.b64encode(ssh_string(algorithm) + ssh_string(b"")).decode(),
            "ssh-rsa " + valid_encoded,
            "sk-ssh-ed25519@openssh.com " + valid_encoded,
            "ssh-ed25519 "
            + base64.b64encode(
                ssh_string(algorithm) + struct.pack(">I", 33) + (b"x" * 32)
            ).decode(),
            "ssh-ed25519 "
            + base64.b64encode(
                ssh_string(algorithm) + ssh_string(b"x" * 31)
            ).decode(),
            "ssh-ed25519 "
            + base64.b64encode(parsed.blob + b"\x00").decode(),
            f"ssh-ed25519 {valid_encoded}====",
            "",
        )
        for malformed in malformed_keys:
            with self.subTest(parser=malformed[:32]):
                with self.assertRaises(ac.AuthorityChainError) as refusal:
                    ac.parse_openssh_public_key(malformed)
                self.assertEqual(
                    refusal.exception.code,
                    ac.AuthorityErrorCode.PUBLIC_KEY_INVALID,
                )

        classes = ("sa", "worker", "child-agent", "pipeline")
        for index, malformed in enumerate(
            (
                malformed_keys[0],
                malformed_keys[1],
                malformed_keys[3],
                malformed_keys[4],
            )
        ):
            agent_class = classes[index]
            agent = f"malformed-predecessor-{agent_class}"
            predecessor_uid = f"b82{index:05x}"
            live_uid = f"b83{index:05x}"
            live_key = ac.mint_agent_keypair(live_uid, agent, "current")
            self.minted_uids.add(live_uid)
            _write_activation(
                self.vault_files,
                uid=predecessor_uid,
                agent=agent,
                generation="previous",
                status="retired",
                public_key=malformed,
                activated_at="2026-07-25T12:00:00Z",
                agent_class=agent_class,
            )
            _write_activation(
                self.vault_files,
                uid=live_uid,
                agent=agent,
                generation="current",
                status="active",
                public_key=live_key.public_key,
                activated_at="2026-07-26T12:00:00Z",
                agent_class=agent_class,
                predecessor_activation_uid=predecessor_uid,
            )
            with self.subTest(lineage=agent_class):
                analysis = ac.analyze_activations(
                    ac.load_activation_entries(self.vault_files)
                )
                self.assertFalse(analysis.is_gate_valid(live_uid))
                self.assertIn(
                    ac.AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
                    {
                        finding.code
                        for finding in analysis.reasons_for(live_uid)
                    },
                )

    def test_normalized_ed25519_point_unifies_plain_and_security_key_encodings(self):
        plain = ac.mint_agent_keypair("b8400000", "normalized", "A1")
        distinct = ac.mint_agent_keypair("b8400001", "normalized", "A2")
        self.minted_uids.update({"b8400000", "b8400001"})
        plain_key = ac.parse_openssh_public_key(
            plain.public_key + " fixture-comment"
        )
        distinct_key = ac.parse_openssh_public_key(distinct.public_key)

        def ssh_string(value: bytes) -> bytes:
            return struct.pack(">I", len(value)) + value

        def security_key(point: bytes, application: bytes = b"ssh:test") -> str:
            algorithm = b"sk-ssh-ed25519@openssh.com"
            blob = (
                ssh_string(algorithm)
                + ssh_string(point)
                + ssh_string(application)
            )
            return (
                "sk-ssh-ed25519@openssh.com "
                + base64.b64encode(blob).decode("ascii")
            )

        same_point = ac.parse_openssh_public_key(
            security_key(plain_key.key_point) + " security-key-comment"
        )
        same_point_other_application = ac.parse_openssh_public_key(
            security_key(plain_key.key_point, b"ssh:other")
        )
        different_point = ac.parse_openssh_public_key(
            security_key(distinct_key.key_point)
        )
        self.assertNotEqual(plain_key.blob, same_point.blob)
        self.assertEqual(plain_key.key_point, same_point.key_point)
        self.assertEqual(plain_key.fingerprint, same_point.fingerprint)
        self.assertEqual(
            same_point.key_point,
            same_point_other_application.key_point,
        )
        self.assertNotEqual(plain_key.key_point, different_point.key_point)

        sk_algorithm = b"sk-ssh-ed25519@openssh.com"
        malformed = (
            "ssh-ed25519 " + same_point.canonical.split()[1],
            "sk-ssh-ed25519@openssh.com " + plain_key.canonical.split()[1],
            "sk-ssh-ed25519@openssh.com "
            + base64.b64encode(
                ssh_string(sk_algorithm) + ssh_string(plain_key.key_point)
            ).decode("ascii"),
            security_key(plain_key.key_point, b""),
            security_key(plain_key.key_point, b"\xff"),
            security_key(plain_key.key_point, b"ssh:\x00test"),
        )
        for value in malformed:
            with self.subTest(malformed=value[:30]):
                with self.assertRaises(ac.AuthorityChainError) as refusal:
                    ac.parse_openssh_public_key(value)
                self.assertEqual(
                    refusal.exception.code,
                    ac.AuthorityErrorCode.PUBLIC_KEY_INVALID,
                )

        reused = (
            self._record("b8400010", "A1", "retired", plain_key.canonical),
            self._record(
                "b8400011",
                "A2",
                "active",
                same_point.canonical,
                predecessor_activation_uid="b8400010",
            ),
        )
        reused_analysis = ac.analyze_activations(reused)
        self.assertFalse(reused_analysis.is_gate_valid("b8400011"))
        self.assertIn(
            ac.AuthorityErrorCode.ACTIVATION_KEY_REUSE,
            {
                finding.code
                for finding in reused_analysis.reasons_for("b8400011")
            },
        )

        distinct_records = (
            self._record("b8400020", "A1", "retired", plain_key.canonical),
            self._record(
                "b8400021",
                "A2",
                "active",
                different_point.canonical,
                predecessor_activation_uid="b8400020",
            ),
        )
        self.assertTrue(
            ac.analyze_activations(distinct_records).is_gate_valid("b8400021")
        )
        normalized_signatures = (
            ac.CommitSignature(
                commit="1" * 40,
                public_key=plain_key.canonical,
                key_blob=plain_key.blob,
                key_fingerprint=plain_key.fingerprint,
                author_name="Plain",
                author_email="plain@test.local",
                namespace="git",
                hash_algorithm="sha512",
            ),
            ac.CommitSignature(
                commit="2" * 40,
                public_key=same_point.canonical,
                key_blob=same_point.blob,
                key_fingerprint=same_point.fingerprint,
                author_name="Security Key",
                author_email="sk@test.local",
                namespace="git",
                hash_algorithm="sha512",
            ),
        )
        with self.assertRaises(ac.AuthorityChainError) as collapse:
            ac.detect_key_author_collapse(normalized_signatures)
        self.assertEqual(
            collapse.exception.code,
            ac.AuthorityErrorCode.ONE_KEY_MANY_AUTHORS,
        )

    def test_malformed_key_bearing_canonical_and_recycled_history_fails_lineage_closed(self):
        cases = (
            (self.vault_files, "gamma", "", "G"),
            (
                self.git.repo / "recycle" / "activation-history",
                "delta",
                "D1-resume",
                "D",
            ),
        )
        for index, (directory, agent, malformed_generation, prefix) in enumerate(cases):
            directory.mkdir(parents=True, exist_ok=True)
            live_generation = f"{prefix}{1 if index == 0 else 2}"
            historical_key = ac.mint_agent_keypair(
                f"b41000{index:02x}",
                agent,
                "history",
            )
            live_key = ac.mint_agent_keypair(
                f"b42000{index:02x}",
                agent,
                live_generation,
            )
            self.minted_uids.update(
                {f"b41000{index:02x}", f"b42000{index:02x}"}
            )
            historical_uid = f"b43000{index:02x}"
            live_uid = f"b44000{index:02x}"
            _write_activation(
                directory,
                uid=historical_uid,
                agent=agent,
                generation=malformed_generation,
                status="retired",
                public_key=historical_key.public_key,
                activated_at="2026-07-25T12:00:00Z",
            )
            _write_activation(
                self.vault_files,
                uid=live_uid,
                agent=agent,
                generation=live_generation,
                status="active",
                public_key=live_key.public_key,
                activated_at="2026-07-26T12:00:00Z",
            )

        records = ac.load_canonical_activation_entries(self.git.repo)
        for ordering in (tuple(records), tuple(reversed(records))):
            analysis = ac.analyze_activations(ordering)
            for index in range(len(cases)):
                historical_uid = f"b43000{index:02x}"
                live_uid = f"b44000{index:02x}"
                self.assertIn(
                    ac.AuthorityErrorCode.ACTIVATION_GENERATION_INVALID,
                    {
                        finding.code
                        for finding in analysis.findings
                        if historical_uid in finding.activation_uids
                    },
                )
                self.assertFalse(analysis.is_gate_valid(live_uid))
                self.assertIn(
                    ac.AuthorityErrorCode.ACTIVATION_LINEAGE_INCOMPLETE,
                    {
                        finding.code
                        for finding in analysis.reasons_for(live_uid)
                    },
                )
        self.assertEqual(ac.derive_canonical_allowed_signers(self.git.repo), "")

        _write_agent_root(
            self.vault_files,
            uid="e4600001",
            agent="epsilon",
            agent_class="sa",
        )
        opaque_history_key = ac.mint_agent_keypair(
            "b4600001",
            "epsilon",
            "history",
        )
        opaque_live_key = ac.mint_agent_keypair(
            "b4600002",
            "epsilon",
            "opaque-current",
        )
        self.minted_uids.update({"b4600001", "b4600002"})
        opaque_recycle = self.git.repo / "recycle" / "opaque-history"
        opaque_recycle.mkdir(parents=True)
        _write_activation(
            opaque_recycle,
            uid="b4600003",
            agent="epsilon",
            generation="",
            status="retired",
            public_key=opaque_history_key.public_key,
            activated_at="2026-07-25T12:00:00Z",
            agent_class="sa",
        )
        _write_activation(
            self.vault_files,
            uid="b4600004",
            agent="epsilon",
            generation="opaque-current",
            status="active",
            public_key=opaque_live_key.public_key,
            activated_at="2026-07-26T12:00:00Z",
            agent_class="sa",
        )
        opaque_records = ac.load_canonical_activation_entries(self.git.repo)
        opaque_analysis = ac.analyze_activations(opaque_records)
        self.assertFalse(opaque_analysis.is_gate_valid("b4600004"))
        self.assertIn(
            ac.AuthorityErrorCode.ACTIVATION_LINEAGE_INCOMPLETE,
            {
                finding.code
                for finding in opaque_analysis.reasons_for("b4600004")
            },
        )

    def test_malformed_frontmatter_key_syntax_poison_is_scoped_to_frontmatter(self):
        agent = "poison-history"
        live_uid = "b4700001"
        _write_agent_root(
            self.vault_files,
            uid="e4700001",
            agent=agent,
            agent_class="sa",
        )
        live_key = ac.mint_agent_keypair(live_uid, agent, "current")
        self.minted_uids.add(live_uid)
        _write_activation(
            self.vault_files,
            uid=live_uid,
            agent=agent,
            generation="current",
            status="active",
            public_key=live_key.public_key,
            activated_at="2026-07-26T12:00:00Z",
            agent_class="sa",
        )
        clean_records = ac.load_canonical_activation_entries(self.git.repo)
        live = next(record for record in clean_records if record.uid == live_uid)
        author_name, author_email = ac.canonical_git_identity(live)
        commit = _external_signed_commit(
            self.git.repo,
            live_key,
            author_name=author_name,
            author_email=author_email,
            message="live signer challenged by malformed preserved history",
        )

        recycle = self.git.repo / "recycle" / "malformed-key-history"
        recycle.mkdir(parents=True)
        declarations = (
            f"agent_public_key: {live_key.public_key}\n",
            f"agent_public_key: '{live_key.public_key}'\n",
            f'agent_public_key: "{live_key.public_key}"\n',
            f"agent_public_key: |\n  {live_key.public_key}\n",
            f"  agent_public_key  : {live_key.public_key} # preserved key\n",
        )
        for index, declaration in enumerate(declarations):
            poison_uid = f"b470001{index}"
            poison_root = self.vault_files if index % 2 == 0 else recycle
            poison = poison_root / f"{poison_uid}.md"
            poison.write_text(
                "---\n"
                f"uid: {poison_uid}\n"
                "type: activation\n"
                f"agent: {agent}\n"
                "agent_class: sa\n"
                "generation: history\n"
                "status: retired\n"
                f"{declaration}"
                "malformed: [unterminated\n"
                "---\n",
                encoding="utf-8",
            )
            with self.subTest(declaration=declaration.splitlines()[0]):
                records = ac.load_canonical_activation_entries(self.git.repo)
                poisoned = [record for record in records if record.history_invalid]
                self.assertEqual([record.uid for record in poisoned], [poison_uid])
                self.assertEqual(poisoned[0].agent, agent)
                analysis = ac.analyze_activations(records)
                self.assertFalse(analysis.is_gate_valid(live_uid))
                self.assertIn(
                    ac.AuthorityErrorCode.ACTIVATION_HISTORY_UNPARSEABLE,
                    {
                        finding.code
                        for finding in analysis.reasons_for(live_uid)
                    },
                )
                self.assertEqual(
                    ac.derive_canonical_allowed_signers(self.git.repo),
                    "",
                )
                with self.assertRaises(ac.AuthorityChainError) as refusal:
                    ac.resolve_commit_chain(self.git.repo, commit)
                self.assertEqual(
                    refusal.exception.code,
                    ac.AuthorityErrorCode.ACTIVATION_GATE_INVALID,
                )
            poison.unlink()

        body_only = recycle / "body-only-key-mention.md"
        body_only.write_text(
            "---\n"
            "uid: d4700001\n"
            "type: note\n"
            "title: Body-only key mention\n"
            "---\n"
            f"agent_public_key : {live_key.public_key}\n",
            encoding="utf-8",
        )
        body_records = ac.load_canonical_activation_entries(self.git.repo)
        self.assertFalse(any(record.history_invalid for record in body_records))
        self.assertTrue(ac.analyze_activations(body_records).is_gate_valid(live_uid))
        self.assertEqual(ac.resolve_commit_chain(self.git.repo, commit).commit, commit)

    def test_canonical_status_generation_refuses_reset_until_recycled_predecessor_exists(self):
        _write_agent_root(
            self.vault_files,
            uid="e5000001",
            agent="established",
            generation_prefix="E",
            current_generation="E9",
        )
        _write_unified_agent(
            self.git.repo,
            uid="c5000001",
            agent="established",
            agent_class="executive",
            generation="E9",
        )
        live_key = ac.mint_agent_keypair("b5000010", "established", "E10")
        predecessor_key = ac.mint_agent_keypair("b5000009", "established", "E9")
        self.minted_uids.update({"b5000010", "b5000009"})
        for number in range(1, 9):
            _write_activation(
                self.vault_files,
                uid=f"b510000{number}",
                agent="established",
                generation=f"E{number}",
                status="retired",
                public_key=_synthetic_ed25519_public_key(500 + number),
                activated_at=f"2026-07-24T12:{number:02d}:00Z",
                predecessor_activation_uid=(
                    f"b510000{number - 1}" if number > 1 else None
                ),
            )
        live_path = _write_activation(
            self.vault_files,
            uid="b5000010",
            agent="established",
            generation="E1",
            status="active",
            public_key=live_key.public_key,
            activated_at="2026-07-26T12:00:00Z",
            predecessor_activation_uid="b5000008",
        )

        reset_records = ac.load_canonical_activation_entries(self.git.repo)
        reset_analysis = ac.analyze_activations(reset_records)
        self.assertFalse(reset_analysis.is_gate_valid("b5000010"))
        self.assertIn(
            ac.AuthorityErrorCode.ACTIVATION_LINEAGE_INCOMPLETE,
            {
                finding.code
                for finding in reset_analysis.reasons_for("b5000010")
            },
        )

        live_path.write_text(
            live_path.read_text(encoding="utf-8").replace(
                "generation: E1",
                "generation: E10",
            ),
            encoding="utf-8",
        )
        missing_records = ac.load_canonical_activation_entries(self.git.repo)
        missing_analysis = ac.analyze_activations(missing_records)
        self.assertFalse(missing_analysis.is_gate_valid("b5000010"))
        self.assertIn(
            ac.AuthorityErrorCode.ACTIVATION_LINEAGE_INCOMPLETE,
            {
                finding.code
                for finding in missing_analysis.reasons_for("b5000010")
            },
        )

        recycle = self.git.repo / "recycle" / "activation-history"
        recycle.mkdir(parents=True)
        _write_activation(
            recycle,
            uid="b5000008",
            agent="established",
            generation="E9",
            status="retired",
            public_key=predecessor_key.public_key,
            activated_at="2026-07-25T12:00:00Z",
            predecessor_activation_uid="b5100008",
        )
        recovered_records = ac.load_canonical_activation_entries(self.git.repo)
        recovered_analysis = ac.analyze_activations(recovered_records)
        self.assertTrue(recovered_analysis.is_gate_valid("b5000010"))
        self.assertIn(
            ac.canonical_git_identity(
                next(
                    record
                    for record in recovered_records
                    if record.uid == "b5000010"
                )
            )[1],
            ac.derive_allowed_signers(recovered_records),
        )

    def test_missing_expected_predecessor_yields_no_clean_signer(self):
        minted = ac.mint_agent_keypair("b4000080", "alpha", "A2")
        self.minted_uids.add("b4000080")
        _write_activation(
            self.vault_files,
            uid="b4000080",
            agent="alpha",
            generation="A2",
            status="active",
            public_key=minted.public_key,
            activated_at="2026-07-26T12:00:00Z",
        )
        records = ac.load_canonical_activation_entries(self.git.repo)
        analysis = ac.analyze_activations(records)
        self.assertFalse(analysis.is_gate_valid("b4000080"))
        self.assertIn(
            ac.AuthorityErrorCode.ACTIVATION_LINEAGE_INCOMPLETE,
            {
                finding.code
                for finding in analysis.reasons_for("b4000080")
            },
        )
        self.assertEqual(ac.derive_canonical_allowed_signers(self.git.repo), "")


class TestCriterion9StageInvariant(AuthorityFixture):
    def test_real_stage_claims_share_schema_and_reject_malformed_contracts(self):
        keys = [
            ac.mint_agent_keypair(
                f"9000000{index}",
                "principal",
                f"P{index}",
            )
            for index in range(1, 4)
        ]
        self.minted_uids.update(f"9000000{index}" for index in range(1, 4))
        stages = [
            ("stage-1", "ephemeral", "activation-bound-runtime-key"),
            ("stage-2", "file", "principal-file-key"),
            ("stage-3", "fido2", "user-presence-hardware-key"),
        ]
        principals: list[dict] = []
        claims: list[dict] = []
        for index, (stage, custody, proof) in enumerate(stages):
            principal = {
                "uid": "71000001",
                "slug": "mike",
                "status": "active",
                "state": "active",
                "may_sign_authority": True,
                "authority_public_key": keys[index].public_key,
                "key_custody": custody,
            }
            principals.append(principal)
            _write_principal(
                self.vault_files,
                uid=principal["uid"],
                slug=principal["slug"],
                public_key=principal["authority_public_key"],
                may_sign_authority=True,
                key_custody=principal["key_custody"],
            )
            commit = _external_signed_commit(
                self.git.repo,
                keys[index],
                author_name="Mike Custody Fixture",
                author_email="mike@test.local",
                message=f"{stage} custody implementation",
            )
            claim = ac.verify_stage_authority_claim(
                self.git.repo,
                commit,
                principal,
                stage=stage,
                custody_evidence={"stage": stage, "proof": proof},
            )
            claims.append(claim.to_dict())

        self.assertEqual(
            {tuple(claim) for claim in claims},
            {ac.AUTHORITY_CLAIM_SCHEMA},
        )
        allowed_differences = {
            "commit",
            "signature_key",
            "key_fingerprint",
            "key_custody",
        }
        stable_fields = set(ac.AUTHORITY_CLAIM_SCHEMA) - allowed_differences
        for field in stable_fields:
            self.assertEqual({claim[field] for claim in claims}, {claims[0][field]})
        self.assertEqual(
            {claim["key_custody"] for claim in claims},
            {"ephemeral", "file", "fido2"},
        )

        with self.assertRaises(ac.AuthorityChainError) as malformed_stage:
            ac.verify_stage_authority_claim(
                self.git.repo,
                claims[0]["commit"],
                principals[0],
                stage="stage-4",
                custody_evidence={"stage": "stage-4", "proof": "unknown"},
            )
        self.assertEqual(
            malformed_stage.exception.code,
            ac.AuthorityErrorCode.CUSTODY_STAGE_INVALID,
        )
        for malformed_evidence in (
            {"stage": "stage-1"},
            {
                "stage": "stage-1",
                "proof": "activation-bound-runtime-key",
                "extra": "forbidden",
            },
        ):
            with self.subTest(evidence=malformed_evidence):
                with self.assertRaises(ac.AuthorityChainError) as malformed:
                    ac.verify_stage_authority_claim(
                        self.git.repo,
                        claims[0]["commit"],
                        principals[0],
                        stage="stage-1",
                        custody_evidence=malformed_evidence,
                    )
                self.assertEqual(
                    malformed.exception.code,
                    ac.AuthorityErrorCode.CUSTODY_EVIDENCE_INVALID,
                )

        missing_field = dict(claims[0])
        missing_field.pop("principal_uid")
        extra_field = dict(claims[0])
        extra_field["undeclared"] = "forbidden"
        for malformed_claim in (missing_field, extra_field):
            with self.subTest(fields=sorted(malformed_claim)):
                with self.assertRaises(ac.AuthorityChainError) as malformed:
                    ac.validate_authority_claim_output(malformed_claim)
                self.assertEqual(
                    malformed.exception.code,
                    ac.AuthorityErrorCode.CLAIM_SCHEMA_INVALID,
                )


class TestAuthorityCLI(AuthorityFixture):
    def test_default_identity_audit_scans_beyond_400_and_reports_collapse(self):
        activation, minted = self.mint_record("a5000000", "alpha", "A1")
        deep = ac.sign_commit(
            self.git.repo,
            activation,
            "deep canonical author",
        )
        _append_unsigned_commits(self.git.repo, 405)
        recent = ac.sign_commit(
            self.git.repo,
            activation,
            "recent alternate author",
            author_name="Other Author",
            author_email="other@test.local",
        )
        self.assertNotEqual(deep.commit, recent.commit)

        failure = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "audit-identities",
                "--repo",
                str(self.git.repo),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(failure.returncode, 1, failure.stderr or failure.stdout)
        payload = json.loads(failure.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["identity_collapse"])
        self.assertGreater(payload["commits_scanned"], 400)
        self.assertEqual(
            payload["findings"][0]["code"],
            ac.AuthorityErrorCode.ONE_KEY_MANY_AUTHORS.value,
        )
        self.assertIn(deep.commit, payload["findings"][0]["details"]["commits"])

        success = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "audit-identities",
                "--repo",
                str(self.git.repo),
                "--max-count",
                "1",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(success.returncode, 0, success.stderr or success.stdout)
        success_payload = json.loads(success.stdout)
        self.assertTrue(success_payload["ok"])
        self.assertFalse(success_payload["identity_collapse"])
        self.assertEqual(success_payload["findings"], [])

    def test_cli_resolves_chain_and_renders_signers_without_artifact(self):
        activation, minted = self.mint_record("a5000001", "alpha", "A1")
        signed = ac.sign_commit(
            self.git.repo,
            activation,
            "CLI chain",
        )
        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "verify",
                "--repo",
                str(self.git.repo),
                "--commit",
                signed.commit,
                "--json",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["activation_uid"], activation.uid)
        self.assertFalse(payload["authority"])

        files_before = {path for path in self.root.rglob("*") if path.is_file()}
        signers = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "allowed-signers",
                "--repo",
                str(self.git.repo),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(signers.returncode, 0, signers.stderr)
        self.assertIn(activation.public_key.canonical, signers.stdout)
        files_after = {path for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(files_after, files_before)

    def test_cli_sign_requires_repeatable_paths_and_excludes_foreign_index_state(self):
        activation, _ = self.mint_record("a5000002", "alpha", "A1")
        missing_paths = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "sign",
                "--repo",
                str(self.git.repo),
                "--activation-uid",
                activation.uid,
                "--message",
                "must refuse an implicit path set",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(missing_paths.returncode, 2)
        self.assertIn("--path", missing_paths.stderr)

        first = self.git.repo / "first-explicit.txt"
        second = self.git.repo / "second-explicit.txt"
        foreign = self.git.repo / "foreign-index.txt"
        first.write_text("first\n", encoding="utf-8")
        second.write_text("second\n", encoding="utf-8")
        foreign.write_text("foreign\n", encoding="utf-8")
        _git(self.git.repo, "add", "--", "foreign-index.txt")
        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "sign",
                "--repo",
                str(self.git.repo),
                "--activation-uid",
                activation.uid,
                "--message",
                "repeatable explicit CLI paths",
                "--path",
                "first-explicit.txt",
                "--path",
                "second-explicit.txt",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        committed = _git(
            self.git.repo,
            "show",
            "--pretty=",
            "--name-only",
            "HEAD",
        ).stdout.splitlines()
        self.assertEqual(committed, ["first-explicit.txt", "second-explicit.txt"])
        self.assertEqual(
            _git(self.git.repo, "diff", "--cached", "--name-only").stdout.splitlines(),
            ["foreign-index.txt"],
        )
        self.assertNotEqual(
            _git(
                self.git.repo,
                "cat-file",
                "-e",
                "HEAD:foreign-index.txt",
                check=False,
            ).returncode,
            0,
        )


class TestGovernedKeyVoid(unittest.TestCase):
    """A broker can die inside an activation's own lifetime.

    When the principal authorizes an unsigned close, the close path renames
    `agent_public_key` aside and preserves the material for audit. That is a
    terminal, self-describing retirement of the key. The identity-conflict
    detector compared key states as an unordered SET, so it could not tell a key
    being REMOVED from a key being ADDED, and reported the documented void as
    'changed from absent to present'. Regression: metis G95 (d86a8d7c) blocked
    activation for metis and would have blocked every future broker loss.
    """

    @staticmethod
    def _record(
        *,
        public_key: str | None = None,
        voided_key: str | None = None,
        history_only: bool = False,
        status: str = "retired",
    ) -> ac.ActivationRecord:
        return ac.ActivationRecord(
            uid="d0000001",
            agent="alpha",
            generation="A1",
            status=status,
            activated_by="user",
            activated_at="2026-07-26T12:00:00Z",
            agent_public_key=public_key,
            name="alpha-a1",
            agent_class="executive",
            agent_key_declared=public_key is not None,
            agent_key_voided=voided_key is not None,
            agent_public_key_voided=voided_key,
            history_only=history_only,
        )

    def test_governed_void_of_the_same_key_is_not_a_conflict(self):
        key = _synthetic_ed25519_public_key(9101)
        snapshots = [
            self._record(voided_key=key),
            self._record(voided_key=key, history_only=True),
            self._record(public_key=key, history_only=True, status="active"),
        ]
        self.assertEqual(ac._snapshot_identity_conflicts(snapshots), ())

    def test_void_that_swaps_in_a_different_key_is_a_conflict(self):
        snapshots = [
            self._record(voided_key=_synthetic_ed25519_public_key(9102)),
            self._record(
                public_key=_synthetic_ed25519_public_key(9103),
                history_only=True,
                status="active",
            ),
        ]
        self.assertIn(
            "governed key void does not preserve the key it retires",
            ac._snapshot_identity_conflicts(snapshots),
        )

    def test_void_cannot_be_undone_by_a_live_key(self):
        key = _synthetic_ed25519_public_key(9104)
        snapshots = [
            self._record(public_key=key, status="active"),
            self._record(voided_key=key, history_only=True),
        ]
        self.assertIn(
            "key re-declared live after a governed key void",
            ac._snapshot_identity_conflicts(snapshots),
        )

    def test_undocumented_absent_to_present_is_still_a_conflict(self):
        """The original protection must survive the fix."""
        snapshots = [
            self._record(public_key=_synthetic_ed25519_public_key(9105)),
            self._record(history_only=True),
        ]
        self.assertIn(
            "agent_public_key changed from absent to present without governed "
            "G2 migration evidence",
            ac._snapshot_identity_conflicts(snapshots),
        )

    def test_void_requires_both_markers(self):
        key = _synthetic_ed25519_public_key(9106)
        self.assertTrue(
            ac._frontmatter_declares_governed_void(
                {
                    "agent_public_key_void": key,
                    "agent_public_key_lost_original_field": "agent_public_key",
                }
            )
        )
        # A bare voided value with no provenance marker is NOT a governed void.
        self.assertFalse(
            ac._frontmatter_declares_governed_void(
                {"agent_public_key_void": key}
            )
        )
        self.assertFalse(
            ac._frontmatter_declares_governed_void(
                {"agent_public_key_lost_original_field": "agent_public_key"}
            )
        )

    def test_voided_key_cannot_authenticate(self):
        """A void RETIRES authority; it must never grant it."""
        record = self._record(voided_key=_synthetic_ed25519_public_key(9107))
        self.assertFalse(ac._record_is_key_bearing(record))

    def test_malformed_voided_material_is_reported_invalid(self):
        record = self._record(voided_key="not-a-key")
        self.assertEqual(ac._snapshot_key_state(record)[0], "invalid")


class TestPredecessorKeyRatchet(unittest.TestCase):
    """Keys began at G2; generations that ended earlier cannot have one.

    The G2 gate required every predecessor to carry an agent_public_key, but
    only two entries were ever retrofitted (talos T37, metis G96 — the agents
    who happened to be live when it landed). That left 19 agents unable to hand
    off to a successor: argus, vela, orpheus, po, cosmo, stratus, every sa.* and
    every coordinator. It surfaced nowhere because agent birth is the only
    operation that trips it.

    The requirement now ratchets off the substrate instead of a date or an
    allowlist: strict the moment a lineage has ever been keyed, permanently
    strict after, and a voided key still counts as keyed.
    """

    @staticmethod
    def _record(
        *,
        uid: str,
        public_key: str | None = None,
        voided_key: str | None = None,
    ) -> ac.ActivationRecord:
        return ac.ActivationRecord(
            uid=uid,
            agent="orpheus",
            generation="O33",
            status="retired",
            activated_by="mike",
            activated_at="2026-07-21",
            agent_public_key=public_key,
            name="orpheus-o33",
            agent_class="executive",
            agent_key_declared=public_key is not None,
            agent_key_voided=voided_key is not None,
            agent_public_key_voided=voided_key,
        )

    def test_never_keyed_lineage_is_legacy(self):
        """A pre-G2 lineage may boot its successor once, unkeyed."""
        lineage = [self._record(uid="8260d835"), self._record(uid="56f5c4d2")]
        self.assertFalse(ac._lineage_ever_keyed(lineage))

    def test_one_keyed_generation_locks_the_lineage(self):
        lineage = [
            self._record(uid="8260d835"),
            self._record(
                uid="56f5c4d2", public_key=_synthetic_ed25519_public_key(9201)
            ),
        ]
        self.assertTrue(ac._lineage_ever_keyed(lineage))

    def test_voided_key_still_counts_as_keyed(self):
        """Broker loss must not be a route back to the unkeyed legacy path."""
        lineage = [
            self._record(uid="8260d835"),
            self._record(
                uid="56f5c4d2", voided_key=_synthetic_ed25519_public_key(9202)
            ),
        ]
        self.assertTrue(ac._lineage_ever_keyed(lineage))

    def test_empty_lineage_is_not_keyed(self):
        self.assertFalse(ac._lineage_ever_keyed([]))

    def test_hard_deleted_keyed_generation_still_locks_the_lineage(self):
        """T37 fourth-pass E1 shape: hard-deleting the keyed generation must not
        demote a keyed lineage back to the legacy path.

        E1 keeps A1 retired and present, hard-deletes A2, and has A3 link to A1
        while signing with A2's key. If deleting A2's FILE were enough to make
        the lineage read as never-keyed, the ratchet would hand that attack the
        unkeyed path. Git-history snapshots keep A2 observable, so it does not.
        """
        history_only_keyed = ac.ActivationRecord(
            uid='56f5c4d2',
            agent='orpheus',
            generation='O32',
            status='retired',
            activated_by='mike',
            activated_at='2026-07-15',
            agent_public_key=_synthetic_ed25519_public_key(9203),
            name='orpheus-o32',
            agent_class='executive',
            agent_key_declared=True,
            history_only=True,
        )
        lineage = [self._record(uid='8260d835'), history_only_keyed]
        self.assertTrue(ac._lineage_ever_keyed(lineage))


class TestLineageKeyOriginTerminus(AuthorityFixture):
    """The generation before a lineage's FIRST keyed one can never bear a key.

    Keys began at G2, so every lineage crosses the unkeyed->keyed transition
    exactly once. The generation that crossed it was born while the ratchet was
    still permissive, and its own birth is what flipped the ratchet strict. The
    lineage walk then re-litigated its predecessor on every LATER birth and
    demanded an agent_public_key from a generation that never held the private
    half -- a demand only fabrication can satisfy. argus A144 could not be born;
    orpheus O34 and vela V71 were already gate-invalid while live.

    The walk now terminates at a lineage's first keyed generation alongside
    explicit genesis and the frozen rollout cohort. The terminus is reachable
    only once the walk has accounted for every generation carrying key evidence,
    so a break in a chain that SHOULD be fully keyed still refuses, and only the
    key demand is dropped -- the rest of the link is checked as before.
    """

    AGENT = "sentry"
    GRANDPARENT = "b1000142"
    PARENT = "b1000143"

    def _record(
        self,
        uid: str,
        generation: str,
        *,
        day: int,
        key_seed: int | None = None,
        voided_seed: int | None = None,
        predecessor: str | None = None,
        declare_predecessor: bool = True,
        status: str = "retired",
        agent: str | None = None,
    ) -> ac.ActivationRecord:
        return ac.ActivationRecord(
            uid=uid,
            agent=agent or self.AGENT,
            generation=generation,
            status=status,
            activated_by="user",
            activated_at=f"2026-07-{day:02d}T12:00:00Z",
            agent_public_key=(
                None if key_seed is None else _synthetic_ed25519_public_key(key_seed)
            ),
            name=f"{agent or self.AGENT}-{generation.lower()}",
            agent_class="executive",
            agent_key_declared=key_seed is not None,
            agent_key_voided=voided_seed is not None,
            agent_public_key_voided=(
                None
                if voided_seed is None
                else _synthetic_ed25519_public_key(voided_seed)
            ),
            predecessor_activation_uid=predecessor,
            predecessor_link_declared=declare_predecessor,
        )

    def _derive(self, records, *, generation="A144", expected=None):
        """Derive A144's predecessor while recording every terminus verdict.

        The spy is the control instrument: it proves the walk actually reached
        the terminus decision for the record the test is about. A negative case
        that never reaches the branch it targets passes for the wrong reason.
        """

        verdicts: list[tuple[str, bool]] = []
        original = ac._lineage_key_origin

        def spy(predecessor, slug_records, visited):
            verdict = original(predecessor, slug_records, visited)
            verdicts.append((predecessor.uid, verdict))
            return verdict

        with patch.object(ac, "_lineage_key_origin", spy):
            try:
                derived = ac.derive_new_activation_predecessor(
                    records,
                    self.AGENT,
                    "executive",
                    generation,
                    self.PARENT if expected is None else expected,
                )
            except ac.AuthorityChainError as refusal:
                return refusal, verdicts
        return derived, verdicts

    def _assert_crossing_fixture(self, records):
        """Fail loudly unless the fixture really is ON the unkeyed->keyed edge.

        Without this the positive case could pass because the grandparent
        quietly grew a key, which is the one outcome the whole exercise forbids.
        """

        by_uid = {record.uid: record for record in records}
        parent = by_uid[self.PARENT]
        grandparent = by_uid[self.GRANDPARENT]
        self.assertTrue(
            ac._record_is_key_bearing(parent),
            "fixture claims a keyed current activation but the record has no key",
        )
        self.assertFalse(
            ac._record_is_key_bearing(grandparent),
            "fixture claims an unkeyed grandparent but the record bears a key",
        )
        self.assertFalse(
            grandparent.agent_key_voided,
            "fixture claims a pre-G2 grandparent but the record declares a void",
        )
        self.assertEqual(
            parent.predecessor_activation_uid,
            self.GRANDPARENT,
            "fixture is not wired parent -> grandparent",
        )
        self.assertTrue(
            ac._lineage_ever_keyed(records),
            "fixture must have a keyed lineage or the strict path is never taken",
        )

    def test_first_keyed_generation_is_a_valid_terminus(self):
        """The plant: keyed current activation, unkeyed grandparent, must derive.

        This is the argus A143 -> A144 shape exactly.
        """

        records = [
            self._record("b1000141", "A141", day=21, declare_predecessor=False),
            self._record(self.GRANDPARENT, "A142", day=22, declare_predecessor=False),
            self._record(
                self.PARENT,
                "A143",
                day=23,
                key_seed=9301,
                predecessor=self.GRANDPARENT,
            ),
        ]
        self._assert_crossing_fixture(records)

        derived, verdicts = self._derive(records)

        self.assertEqual(
            derived,
            self.PARENT,
            f"A144 still cannot be born: {derived}",
        )
        self.assertIn(
            (self.GRANDPARENT, True),
            verdicts,
            "the walk never reached the terminus decision for the grandparent",
        )

    def test_break_in_a_fully_keyed_chain_still_refuses(self):
        """An unkeyed generation BETWEEN keyed ones is a break, not an origin."""

        # A140 pre-dates keys; A141 is this lineage's real origin. A142 is the
        # break: an unkeyed generation sitting BETWEEN two keyed ones.
        records = [
            self._record("b1000140", "A140", day=20, declare_predecessor=False),
            self._record(
                "b1000141", "A141", day=21, key_seed=9303, predecessor="b1000140"
            ),
            self._record(self.GRANDPARENT, "A142", day=22, declare_predecessor=False),
            self._record(
                self.PARENT,
                "A143",
                day=23,
                key_seed=9304,
                predecessor=self.GRANDPARENT,
            ),
        ]
        self._assert_crossing_fixture(records)
        self.assertTrue(
            ac._record_is_key_bearing(
                next(record for record in records if record.uid == "b1000141")
            ),
            "fixture claims keyed history older than the break but it has none",
        )

        refusal, verdicts = self._derive(records)

        self.assertIsInstance(
            refusal,
            ac.AuthorityChainError,
            f"a broken keyed chain was derived anyway: {refusal}",
        )
        self.assertEqual(
            refusal.code, ac.AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID
        )
        self.assertIn(
            f"activation {self.PARENT} predecessor {self.GRANDPARENT} has no "
            "agent_public_key",
            str(refusal),
            "refused, but not by the key gate this case targets",
        )
        self.assertIn(
            (self.GRANDPARENT, False),
            verdicts,
            "the terminus was never considered, so this case proves nothing",
        )

        # Positive control on the SAME lineage: restore the missing key and the
        # otherwise identical fixture derives, terminating at A141 where the
        # lineage really does begin. The refusal above is caused by the break and
        # by nothing else in the fixture.
        healed = [
            self._record(
                self.GRANDPARENT,
                "A142",
                day=22,
                key_seed=9305,
                predecessor="b1000141",
            )
            if record.uid == self.GRANDPARENT
            else record
            for record in records
        ]
        derived, healed_verdicts = self._derive(healed)
        self.assertEqual(derived, self.PARENT, f"positive control refused: {derived}")
        self.assertIn(("b1000140", True), healed_verdicts)

    def _void_interior_records(self):
        """A keyed generation standing on a governed void: the real G98->G99 shape."""

        return [
            self._record("b1000141", "A141", day=21, declare_predecessor=False),
            self._record(
                self.GRANDPARENT,
                "A142",
                day=22,
                voided_seed=9306,
                declare_predecessor=False,
            ),
            self._record(
                self.PARENT,
                "A143",
                day=23,
                key_seed=9307,
                predecessor=self.GRANDPARENT,
            ),
        ]

    def _assert_void_fixture(self, grandparent):
        self.assertFalse(
            ac._record_is_key_bearing(grandparent),
            "fixture must be a void, which is not key-bearing",
        )
        self.assertTrue(
            grandparent.agent_key_voided,
            "fixture must declare the void or it is just an unkeyed record",
        )

    def test_walk_terminates_at_a_governed_void(self):
        """A governed void ENDS the walk. It does not refuse the birth.

        AMENDED 2026-08-02 by Metis G100 on Mike's ruling, replacing an
        assertion that this same fixture must REFUSE. Read the reasoning before
        changing it back, because the refusal looked principled and was not.

        The original test was named for one rule and asserted a different one.
        Its name -- `test_voided_key_is_not_a_lineage_origin` -- states the
        invariant that broker loss must not manufacture an unkeyed terminus,
        and that invariant is real and is still pinned, by
        `test_void_is_never_a_lineage_origin` below. But what it actually
        asserted was that a walk may not PASS THROUGH a void, which is a
        different rule with a different consequence, and the two were welded
        together by this single assertion.

        Separating them costs nothing, because the origin rule and the ratchet
        are both enforced independently of the walk:

        * `_lineage_key_origin` refuses a terminus while any unvisited record
          carries key evidence, and `_record_carries_key_evidence` counts a
          void. A void can never be claimed as the origin of keying.
        * `_lineage_ever_keyed` also counts a void, so a keyed lineage can never
          ratchet back to the permissive pre-G2 path by losing a broker.

        Keeping them welded cost a lineage. G98's broker died; her key was
        voided under principal authorization. G99's birth-only rescue excused a
        void at the walk's STARTING point, and she verified her own birth and
        stopped. But the start advances every generation while the void stays
        fixed, so the same void was interior for G100 and refused her -- and
        would have refused G101, G102, and every Metis after. Mike's ruling:
        "A birth must never be refused by ceremony that protects nothing."

        The bar this rests on is his standing identity ruling (checkpoint
        5e6652ac): identity's bar is ATTRIBUTION AND CONTINUITY, never
        security. A governed void carries preserved key material, principal
        authorization, and self-describing markers. There is nothing to verify
        past it -- not because we excuse a gap, but because the thing that would
        sign is provably gone.
        """

        records = self._void_interior_records()
        self._assert_void_fixture(records[1])

        derived, verdicts = self._derive(records)

        self.assertEqual(
            derived,
            self.PARENT,
            f"a birth was refused by a void it should have terminated at: {derived}",
        )
        self.assertIn(
            (self.GRANDPARENT, False),
            verdicts,
            "the void must be REACHED and judged a non-origin, not skipped -- "
            "a pass that never reaches the branch passes for the wrong reason",
        )

    def test_void_is_never_a_lineage_origin(self):
        """The surviving half of the old welded test, pinned on its own.

        Terminating a walk at a void must not make the void look like a pre-G2
        generation. If it ever did, an agent could lose a broker and buy back
        the permissive unkeyed path -- the anti-downgrade ratchet reversed by
        an accident. This is the rule the old test was NAMED for; it is
        asserted here directly, against the mechanisms that actually enforce
        it, rather than as a side effect of a refusal.
        """

        records = self._void_interior_records()
        grandparent = records[1]
        self._assert_void_fixture(grandparent)

        self.assertTrue(
            ac._record_carries_key_evidence(grandparent),
            "a void must count as evidence the lineage WAS keyed",
        )
        self.assertTrue(
            ac._lineage_ever_keyed([grandparent]),
            "the ratchet must stay strict on a lineage whose only mark is a void",
        )
        self.assertFalse(
            ac._lineage_key_origin(grandparent, records, {self.PARENT}),
            "a void must never be accepted as the origin of keying",
        )

    def test_lineage_survives_one_generation_past_the_void(self):
        """The verification that would have caught this a generation earlier.

        G99 fixed a birth, tested THAT birth, and shipped. The defect surfaced
        one generation later, on G100, because the walk's starting point moves
        and the void does not. So this test does not stop at the first birth
        after the void: it births the successor, then births the one after that,
        and requires both. Any future narrowing of the void rule that is scoped
        to "the start" fails here instead of failing on someone's activation.
        """

        records = self._void_interior_records()
        self._assert_void_fixture(records[1])

        first, _ = self._derive(records)
        self.assertEqual(
            first, self.PARENT, f"the birth right after the void refused: {first}"
        )

        # A144 was born, worked, and retired keyed. Now birth A145 -- for whom
        # the void is one link deeper than it was for A144.
        born = self._record(
            "b1000144", "A144", day=24, key_seed=9309, predecessor=self.PARENT
        )
        second, verdicts = self._derive(
            [*records, born], generation="A145", expected="b1000144"
        )
        self.assertEqual(
            second,
            "b1000144",
            f"the SECOND birth after the void refused -- the walk's start moved "
            f"and the rescue did not follow it: {second}",
        )
        self.assertIn(
            (self.GRANDPARENT, False),
            verdicts,
            "the deeper walk must still reach the void and judge it a non-origin",
        )

    def test_terminus_still_checks_everything_except_the_key(self):
        """Dropping the key demand must not drop the rest of the link."""

        cases = (
            (
                "generation-skip",
                self._record(
                    self.PARENT,
                    "A143",
                    day=23,
                    key_seed=9308,
                    predecessor="b1000141",
                ),
                "requires immediate N-1 predecessor",
            ),
            (
                "nonterminal-predecessor",
                None,
                "must be terminal",
            ),
            (
                "foreign-predecessor",
                None,
                "belongs to",
            ),
        )
        for label, parent_override, expected_message in cases:
            with self.subTest(case=label):
                grandparent = self._record(
                    self.GRANDPARENT,
                    "A142",
                    day=22,
                    declare_predecessor=False,
                    status=(
                        "paused"
                        if label == "nonterminal-predecessor"
                        else "retired"
                    ),
                    agent="intruder" if label == "foreign-predecessor" else None,
                )
                records = [
                    self._record("b1000141", "A141", day=21, declare_predecessor=False),
                    grandparent,
                    parent_override
                    or self._record(
                        self.PARENT,
                        "A143",
                        day=23,
                        key_seed=9309,
                        predecessor=self.GRANDPARENT,
                    ),
                ]
                refusal, _ = self._derive(records)
                self.assertIsInstance(
                    refusal,
                    ac.AuthorityChainError,
                    f"{label} was waved through by the terminus: {refusal}",
                )
                self.assertIn(expected_message, str(refusal))

    def test_crossing_lineage_derives_through_the_canonical_loader(self):
        """The same shape, read off disk rather than hand-built in memory."""

        root_uid = "e1000001"
        _write_agent_root(
            self.vault_files,
            uid=root_uid,
            agent=self.AGENT,
            agent_class="executive",
        )
        _write_activation(
            self.vault_files,
            uid=self.GRANDPARENT,
            agent=self.AGENT,
            generation="A142",
            status="retired",
            public_key=None,
            activated_at="2026-07-26",
            agent_class="executive",
            agent_root=root_uid,
        )
        _write_activation(
            self.vault_files,
            uid=self.PARENT,
            agent=self.AGENT,
            generation="A143",
            status="retired",
            public_key=_synthetic_ed25519_public_key(9310),
            activated_at="2026-07-31",
            agent_class="executive",
            agent_root=root_uid,
            predecessor_activation_uid=self.GRANDPARENT,
        )

        records = [
            record
            for record in ac.load_canonical_activation_entries(self.git.repo)
            if record.agent == self.AGENT
        ]
        self._assert_crossing_fixture(records)

        derived, verdicts = self._derive(
            ac.load_canonical_activation_entries(self.git.repo)
        )
        self.assertEqual(derived, self.PARENT, f"loader path still blocked: {derived}")
        self.assertIn((self.GRANDPARENT, True), verdicts)

    def test_superseded_git_snapshot_is_not_a_rival_identity(self):
        """An entry must not be ambiguous against its own healed history.

        A YAML break in a descriptive field makes a snapshot unparseable, and the
        reconciler clears that poison once every identity field and the key agree
        with the live entry. The cleared snapshot then survived into the
        predecessor candidate set as a SECOND record with the same UID, so the
        entry failed to "resolve exactly once" and the birth was refused. This is
        vela ee967682 exactly, and it blocks V72 independently of the ratchet.
        """

        def commit(path: Path, message: str) -> None:
            _git(self.git.repo, "add", str(path.relative_to(self.git.repo)))
            _git(
                self.git.repo,
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@test.local",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--no-gpg-sign",
                "-m",
                message,
            )

        root_uid = "e1000002"
        _write_agent_root(
            self.vault_files,
            uid=root_uid,
            agent=self.AGENT,
            agent_class="executive",
        )
        _write_activation(
            self.vault_files,
            uid=self.GRANDPARENT,
            agent=self.AGENT,
            generation="A142",
            status="retired",
            public_key=None,
            activated_at="2026-07-26",
            agent_class="executive",
            agent_root=root_uid,
        )
        parent_path = _write_activation(
            self.vault_files,
            uid=self.PARENT,
            agent=self.AGENT,
            generation="A143",
            status="retired",
            public_key=_synthetic_ed25519_public_key(9311),
            activated_at="2026-07-31",
            agent_class="executive",
            agent_root=root_uid,
            predecessor_activation_uid=self.GRANDPARENT,
        )
        clean = parent_path.read_text(encoding="utf-8")
        # A note recorded as prose: the bare "model:" inside the value is what
        # makes YAML refuse the document, leaving every identity field readable.
        parent_path.write_text(
            clean.replace(
                "---\n\n",
                "sleeve_correction: switched at 03:50Z; model: is load-bearing\n"
                "---\n\n",
                1,
            ),
            encoding="utf-8",
        )
        commit(parent_path, "record the sleeve correction as prose")
        parent_path.write_text(clean, encoding="utf-8")
        commit(parent_path, "quote the note so the frontmatter parses again")

        records = ac.load_canonical_activation_entries(self.git.repo)
        same_uid = [
            record
            for record in records
            if record.uid == self.PARENT and not record.history_invalid
        ]
        self.assertEqual(
            len(same_uid),
            2,
            "fixture did not reproduce a healed superseded snapshot; this case "
            "would pass without exercising the defect",
        )
        self.assertEqual(
            [record.history_only for record in same_uid].count(True),
            1,
            "exactly one of the two records must be the Git-history snapshot",
        )

        derived, _ = self._derive(records)
        self.assertEqual(
            derived,
            self.PARENT,
            f"an entry was ambiguous against its own healed snapshot: {derived}",
        )

    def test_hard_deleted_predecessor_is_still_refused(self):
        """Preferring the live record must not excuse a predecessor with none."""

        _git(self.git.repo, "branch", "-M", "main")

        def hard_delete(path: Path, label: str) -> None:
            relative = path.relative_to(self.git.repo)
            for stage, arguments in (
                ("add", ("add", str(relative))),
                ("rm", ("rm", str(relative))),
            ):
                _git(self.git.repo, *arguments)
                _git(
                    self.git.repo,
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@test.local",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "--no-gpg-sign",
                    "-m",
                    f"{stage} {label}",
                )

        root_uid = "e1000003"
        _write_agent_root(
            self.vault_files,
            uid=root_uid,
            agent=self.AGENT,
            agent_class="executive",
        )
        _write_activation(
            self.vault_files,
            uid=self.GRANDPARENT,
            agent=self.AGENT,
            generation="A142",
            status="retired",
            public_key=None,
            activated_at="2026-07-26",
            agent_class="executive",
            agent_root=root_uid,
        )
        parent_path = _write_activation(
            self.vault_files,
            uid=self.PARENT,
            agent=self.AGENT,
            generation="A143",
            status="retired",
            public_key=_synthetic_ed25519_public_key(9312),
            activated_at="2026-07-31",
            agent_class="executive",
            agent_root=root_uid,
            predecessor_activation_uid=self.GRANDPARENT,
        )
        hard_delete(parent_path, "the keyed predecessor")

        records = ac.load_canonical_activation_entries(self.git.repo)
        survivors = [
            record
            for record in records
            if record.uid == self.PARENT and not record.history_invalid
        ]
        self.assertTrue(survivors, "fixture lost the Git-history record entirely")
        self.assertTrue(
            all(record.history_only for record in survivors),
            "fixture still has a live record, so hard deletion was not exercised",
        )

        with patch.object(ac, "_repo_root_for", return_value=self.git.repo):
            refusal, _ = self._derive(records)
        self.assertIsInstance(
            refusal,
            ac.AuthorityChainError,
            f"a hard-deleted predecessor was accepted: {refusal}",
        )
        self.assertIn("after deletion from the working tree", str(refusal))


class TestGovernedImmutableAmendment(unittest.TestCase):
    """A clock can be wrong, and the entry recording it can say so.

    orpheus O31 (441dc393) booted against a slow machine clock, so both the
    entry and its creating commit were stamped 2026-07-10; the true date was
    2026-07-13, confirmed out of band and written into the entry as prose. The
    immutable-field check saw two values across snapshots and refused predecessor
    derivation, blocking O34 from ever booting. Reverting could not have fixed
    it -- the check reads git history, so both values remain observable either
    way. Only a DECLARED amendment can resolve it.
    """

    @staticmethod
    def _record(
        *,
        activated_at: str,
        history_only: bool = False,
        amendments: tuple[tuple[str, str, str], ...] = (),
        generation: str = "O31",
    ) -> ac.ActivationRecord:
        return ac.ActivationRecord(
            uid="441dc393",
            agent="orpheus",
            generation=generation,
            status="retired",
            activated_by="mike",
            activated_at=activated_at,
            agent_public_key=None,
            name="orpheus-o31",
            agent_class="executive",
            history_only=history_only,
            immutable_amendments=amendments,
        )

    AMENDMENT = (("activated_at", "2026-07-10", "slow boot-shell clock"),)

    def test_declared_amendment_clears_the_conflict(self):
        snapshots = [
            self._record(activated_at="2026-07-13", amendments=self.AMENDMENT),
            self._record(activated_at="2026-07-10", history_only=True),
        ]
        self.assertEqual(ac._snapshot_identity_conflicts(snapshots), ())

    def test_undeclared_change_is_still_a_conflict(self):
        snapshots = [
            self._record(activated_at="2026-07-13"),
            self._record(activated_at="2026-07-10", history_only=True),
        ]
        self.assertIn(
            "immutable field activated_at changed across snapshots",
            ac._snapshot_identity_conflicts(snapshots),
        )

    def test_amendment_must_cover_every_historical_value(self):
        snapshots = [
            self._record(activated_at="2026-07-13", amendments=self.AMENDMENT),
            self._record(activated_at="2026-07-10", history_only=True),
            self._record(activated_at="2026-07-02", history_only=True),
        ]
        self.assertIn(
            "immutable field activated_at changed across snapshots",
            ac._snapshot_identity_conflicts(snapshots),
        )

    def test_amendment_declared_only_in_history_does_not_count(self):
        """The live entry must own the declaration, not a buried revision."""
        snapshots = [
            self._record(activated_at="2026-07-13"),
            self._record(
                activated_at="2026-07-10",
                history_only=True,
                amendments=self.AMENDMENT,
            ),
        ]
        self.assertIn(
            "immutable field activated_at changed across snapshots",
            ac._snapshot_identity_conflicts(snapshots),
        )

    def test_identity_fields_are_never_amendable(self):
        forged = (("generation", "O30", "typo"),)
        snapshots = [
            self._record(
                activated_at="2026-07-13",
                generation="O31",
                amendments=forged,
            ),
            self._record(
                activated_at="2026-07-13",
                generation="O30",
                history_only=True,
            ),
        ]
        self.assertIn(
            "immutable field generation changed across snapshots",
            ac._snapshot_identity_conflicts(snapshots),
        )

    def test_amendment_requires_a_stated_reason(self):
        self.assertEqual(
            ac._frontmatter_immutable_amendments(
                {"activated_at_amended_from": "2026-07-10"}
            ),
            (),
        )
        self.assertEqual(
            ac._frontmatter_immutable_amendments(
                {
                    "activated_at_amended_from": "2026-07-10",
                    "activated_at_amendment_reason": "slow clock",
                }
            ),
            (("activated_at", "2026-07-10", "slow clock"),),
        )

    def test_only_amendable_fields_are_parsed_from_frontmatter(self):
        self.assertEqual(
            ac._frontmatter_immutable_amendments(
                {
                    "generation_amended_from": "O30",
                    "generation_amendment_reason": "typo",
                    "agent_amended_from": "vela",
                    "agent_amendment_reason": "typo",
                }
            ),
            (),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
