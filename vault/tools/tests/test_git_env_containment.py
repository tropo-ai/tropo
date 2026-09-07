"""The git-env containment seam: semantics, the incident itself, and a corpus ratchet.

The 2026-09-02 incident is in git_env.py's docstring. This suite proves three
separate claims, and the middle one is the only one that proves the mechanism:

1. `scrubbed_env` has the semantics it claims (unit level).
2. The seam CONTAINS the incident — with GIT_DIR pointed at a decoy repository,
   `git_run("init")` initialises the target and leaves the decoy alone — and the
   control shows raw subprocess in the same conditions does NOT (the decoy wins
   and the target gets nothing). A containment test without that control proves
   only that git works.
3. No NEW fixture joins the uncontained population (ratchet).

The ratchet is fail-closed, and under deb77758 that needs its named harm: a
write-class git call with an inherited environment re-initialised the real
argo-os repository as bare and cost three agents their working tree at once.
The harm is irreversible and it has already happened, so new sites are refused
rather than warned. The 122 existing sites are recorded, not forgiven — the
counts below only move down.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import git_env  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent

# Files exempt from the scan: the seam itself and this gate both name git
# write verbs as data, not as calls against a repository.
EXEMPT = {"git_env.py", Path(__file__).name}

SUB_FUNCS = {"run", "check_call", "check_output", "Popen", "call"}
GLOBAL_FLAGS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
WRITE_VERBS = frozenset({
    "init", "clone", "commit", "add", "config", "checkout", "reset", "clean",
    "branch", "worktree", "remote", "push", "fetch", "pull", "gc", "repack",
    "merge", "rebase", "stash", "rm", "mv", "tag", "apply", "am", "cherry-pick",
    "switch", "restore", "submodule", "update-ref", "symbolic-ref",
    "update-index", "write-tree", "commit-tree", "hash-object", "prune",
    "fsck", "filter-branch", "notes", "replace", "bisect",
})

#: Recorded 2026-09-04 by talos-t62 (AST scan, this file's own scanner). These
#: are files carrying write-class git subprocess calls that inherit the caller's
#: environment. THIS SET ONLY SHRINKS. Migrating a file to git_env.git_run
#: removes it from the scan; delete its line here in the same commit — and
#: test_the_baseline_names_no_file_that_is_already_clean makes that mandatory
#: rather than polite, so the baseline cannot outlive its subject.
#: Opened at 16 files / 122 sites; test_broker_loss_close_seam.py and
#: test_tropo_folder.py migrated the same day as the worked example.
UNCONTAINED_BASELINE = frozenset({
    "sandbox_release_v1_reference_run.py",
    "test_authority_chain.py",
    "test_boundary3_receipt_sha_pushdown.py",
    "test_event_ledger_distributed_identity.py",
    "test_governed_skips_d9ca03fd.py",
    "test_lineage.py",
    "test_merge_seam_wired.py",
    "test_mounted_content_phase2.py",
    "test_provenance_before_close_0caad12b.py",
    "test_public_snapshot_export.py",
    "test_release_adapters_v190.py",
    "test_release_coupling_fbe50871.py",
    "test_tropo_smoke.py",
    "test_v188_weld_batch_cb194126.py",
})
UNCONTAINED_SITE_CEILING = 115


def _arg_tokens(node):
    if isinstance(node, (ast.List, ast.Tuple)):
        return [e.value if isinstance(e, ast.Constant) and isinstance(e.value, str) else None
                for e in node.elts]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.split()
    return []


def _verb(tokens):
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t is None:
            return None
        if t in GLOBAL_FLAGS_WITH_VALUE:
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        return t
    return None


def _env_is_controlled(call):
    keywords = {k.arg: k.value for k in call.keywords}
    if "env" not in keywords:
        return False
    value = keywords["env"]
    if isinstance(value, ast.Constant) and value.value is None:
        return False
    dumped = ast.dump(value)
    if "environ" in dumped and "scrub" not in dumped.lower():
        return False
    return True


def scan_uncontained():
    """Every write-class git subprocess site in the corpus that inherits the env."""
    found = {}
    for path in sorted(TESTS_DIR.glob("*.py")):
        if path.name in EXEMPT:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name not in SUB_FUNCS:
                continue
            tokens = _arg_tokens(node.args[0])
            if not tokens or tokens[0] != "git":
                continue
            if _verb(tokens) not in WRITE_VERBS:
                continue
            if _env_is_controlled(node):
                continue
            found.setdefault(path.name, []).append(node.lineno)
    return found


class ScrubbedEnvSemantics(unittest.TestCase):
    def test_inherited_git_variables_are_stripped(self):
        with mock.patch.dict(os.environ, {"GIT_DIR": "/decoy/.git", "GIT_AUTHOR_NAME": "x"}):
            env = git_env.scrubbed_env()
        self.assertNotIn("GIT_DIR", env)
        self.assertNotIn("GIT_AUTHOR_NAME", env)

    def test_redirect_variables_are_refused_even_when_passed_explicitly(self):
        env = git_env.scrubbed_env({"GIT_DIR": "/decoy/.git",
                                    "GIT_WORK_TREE": "/decoy"})
        for name in ("GIT_DIR", "GIT_WORK_TREE"):
            self.assertNotIn(name, env, f"{name} survived an explicit pass — this is the incident")

    def test_every_declared_redirect_variable_is_refused(self):
        env = git_env.scrubbed_env({name: "/decoy" for name in git_env.GIT_REDIRECT_VARS})
        self.assertEqual(set(env) & git_env.GIT_REDIRECT_VARS, set())

    def test_non_redirect_git_variables_may_be_set_deliberately(self):
        env = git_env.scrubbed_env({"GIT_AUTHOR_DATE": "2026-09-04T00:00:00Z"})
        self.assertEqual(env["GIT_AUTHOR_DATE"], "2026-09-04T00:00:00Z")

    def test_caller_env_is_an_overlay_not_a_replacement(self):
        with mock.patch.dict(os.environ, {"PATH": "/sentinel/bin"}):
            env = git_env.scrubbed_env({"SOME_FIXTURE_FLAG": "1"})
        self.assertEqual(env["PATH"], "/sentinel/bin")
        self.assertEqual(env["SOME_FIXTURE_FLAG"], "1")

    def test_optional_locks_disabled(self):
        self.assertEqual(git_env.scrubbed_env()["GIT_OPTIONAL_LOCKS"], "0")


class TheIncidentIsContained(unittest.TestCase):
    """GIT_DIR beats cwd. These two tests are the same conditions, two mechanisms."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.decoy = base / "decoy"
        self.target = base / "target"
        self.target.mkdir()
        git_env.init_repo(self.decoy)
        self.addCleanup(self._tmp.cleanup)

    def test_seam_initialises_the_target_and_leaves_the_decoy_alone(self):
        before = (self.decoy / ".git" / "config").read_text(encoding="utf-8")
        with mock.patch.dict(os.environ, {"GIT_DIR": str(self.decoy / ".git")}):
            self.target.mkdir(exist_ok=True)
            git_env.git_run("init", cwd=self.target)
        self.assertTrue((self.target / ".git").exists(),
                        "the target did not get a repository — containment failed open")
        self.assertEqual((self.decoy / ".git" / "config").read_text(encoding="utf-8"), before,
                         "the decoy's config changed — GIT_DIR reached git through the seam")

    def test_control_raw_subprocess_in_the_same_conditions_hits_the_decoy(self):
        """The mutation control. Without the seam the incident reproduces.

        If this test ever passes trivially — the target getting its own repo
        despite GIT_DIR — then GIT_DIR no longer beats cwd on this platform and
        the suite above is proving nothing. That is the failure this asserts.
        """
        raw_target = Path(self._tmp.name) / "raw-target"
        raw_target.mkdir()
        env = dict(os.environ)
        env["GIT_DIR"] = str(self.decoy / ".git")
        subprocess.run(["git", "init"], cwd=raw_target, env=env,
                       capture_output=True, text=True, timeout=60, check=True)
        self.assertFalse(
            (raw_target / ".git").exists(),
            "raw subprocess gave the target its own repo — GIT_DIR no longer beats cwd, "
            "so the containment test above has nothing left to prove",
        )


class UncontainedPopulationRatchet(unittest.TestCase):
    def test_no_new_file_joins_the_uncontained_population(self):
        found = scan_uncontained()
        new = sorted(set(found) - UNCONTAINED_BASELINE)
        self.assertEqual(
            new, [],
            "NEW uncontained write-class git call(s). Route them through "
            "vault/tools/tests/git_env.py (git_run / init_repo). A fixture that inherits "
            "GIT_* re-initialised the real argo-os repository as bare on 2026-09-02 and "
            f"cost three agents their working tree. Offending file(s): {new}",
        )

    def test_the_population_only_shrinks(self):
        found = scan_uncontained()
        sites = sum(len(v) for v in found.values())
        self.assertLessEqual(
            sites, UNCONTAINED_SITE_CEILING,
            f"uncontained write-class git sites rose to {sites} (ceiling "
            f"{UNCONTAINED_SITE_CEILING}). This number only moves down.",
        )

    def test_the_baseline_names_no_file_that_is_already_clean(self):
        """A baseline that outlives its subject is a gate that cannot change verdict."""
        found = scan_uncontained()
        stale = sorted(UNCONTAINED_BASELINE - set(found))
        self.assertEqual(
            stale, [],
            f"baseline names file(s) with no uncontained sites left — delete them "
            f"from UNCONTAINED_BASELINE: {stale}",
        )


if __name__ == "__main__":
    unittest.main()
