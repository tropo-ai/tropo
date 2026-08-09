#!/usr/bin/env python3
"""test_appship_scope_gate_498e88fc.py — conformance + hostile gauntlet for the
declaration-grounded app-ship scope gate.

Pairs dev-spec f47da329 (App-Ship Publish Boundary — scope-gate F1–F5) and its
test-spec 498e88fc (assertions G1–G7). Grounding declaration: ed10a8be
(.tropo/app-ship.manifest.md).

Every fixture builds a THROWAWAY git repo under tempfile.mkdtemp() — a real
`git init`, real commits, a real `tropo-app/` prefix, and a copy of the real
app-ship declaration — then runs the real gate end-to-end (real
`git subtree split`, real `git ls-tree`). Assertions check exact exit codes +
refusal reasons, never narrative (test-spec §Scope). NOTHING ever points at the
real studio repo.

Coverage map (test-spec §Coverage map):
  G1  F1 manifest grounding      — missing/corrupt manifest → fail closed
                                    (exit != 0, "no app-ship declaration").
  G2  F2 deny-holes              — planted deny-hole path refused; app source passes.
  G3  F3 pinned commit           — split + cross-check the PINNED commit, not the
                                    advanced HEAD.
  G4  F4 gitlink refusal         — mode-160000 gitlink refused; 120000 symlink still.
  G5  F5 .jsonl scan             — planted private-marker .jsonl caught; the prior
                                    extension list would have missed it.
  G6  fail-closed + banner       — clean split exits 0 + UNSIGNED banner; any
                                    violation → exit != 0.
  G7  boundary separation        — the gate does NOT import lib/segment.py's
                                    federation two-gate filter.
Plus the regression guards (test-spec §Coverage classes): anchored root dirs,
.env.example allowlist, serialized-record vs code content match, legitimate
Next.js agents/ routes not flagged.
"""
import contextlib
import importlib.util
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GATE_PATH = ROOT / "vault" / "tools" / "tropo-publish-scope-gate.py"
REAL_MANIFEST = ROOT / ".tropo" / "app-ship.manifest.md"

# The gate filename carries dashes, so load it via importlib. Register it in
# sys.modules BEFORE exec so its (evaluated) dataclass annotations resolve.
_spec = importlib.util.spec_from_file_location("appship_scope_gate_under_test", str(GATE_PATH))
gate = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gate
_spec.loader.exec_module(gate)

# The pre-F5 content-scan extension list the gate USED to hardcode. Kept here
# only to prove F5 closes the .jsonl gap (G5) — it is NOT used by the gate.
OLD_HARDCODED_EXTENSIONS = (".md", ".txt", ".json", ".ts", ".tsx", ".js", ".py", ".yml", ".yaml")

# A syntactically valid but fake 40-hex sha for planting a gitlink pointer.
FAKE_SUBMODULE_SHA = "1234567890abcdef1234567890abcdef12345678"


def _git(*args, cwd):
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, f"git {args} failed: {r.stderr}"
    return r.stdout.strip()


class GateFixture:
    """A throwaway repo with a tropo-app/ prefix + the app-ship declaration."""

    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="appship-gate-"))
        _git("init", cwd=self.dir)
        _git("config", "user.email", "talos@argo.test", cwd=self.dir)
        _git("config", "user.name", "Talos T34", cwd=self.dir)
        _git("config", "commit.gpgsign", "false", cwd=self.dir)
        self._gitlinks: list[tuple[str, str]] = []

    def write_manifest(self, text=None):
        d = self.dir / ".tropo"
        d.mkdir(parents=True, exist_ok=True)
        (d / "app-ship.manifest.md").write_text(
            REAL_MANIFEST.read_text(encoding="utf-8") if text is None else text,
            encoding="utf-8",
        )

    def add_file(self, relpath, content):
        p = self.dir / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def add_symlink(self, relpath, target):
        p = self.dir / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.symlink_to(target)

    def add_gitlink(self, relpath, sha=FAKE_SUBMODULE_SHA):
        self._gitlinks.append((relpath, sha))

    def commit(self, msg="c"):
        _git("add", "-A", cwd=self.dir)
        for relpath, sha in self._gitlinks:
            _git("update-index", "--add", "--cacheinfo", f"160000,{sha},{relpath}", cwd=self.dir)
        self._gitlinks = []
        _git("commit", "-m", msg, cwd=self.dir)
        return _git("rev-parse", "HEAD", cwd=self.dir)

    def run(self, source_commit):
        """Run the gate's core logic; returns a GateResult."""
        return gate.run_gate(self.dir, source_commit)

    def run_cli(self, source_commit=None):
        """Run the gate's CLI entrypoint; returns (exit_code, stdout)."""
        argv = ["--root", str(self.dir)]
        if source_commit is not None:
            argv += ["--source-commit", source_commit]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = gate.main(argv)
        return code, buf.getvalue()

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class AppShipScopeGateTest(unittest.TestCase):
    def setUp(self):
        self.fx = GateFixture()
        self.addCleanup(self.fx.cleanup)

    def _clean_app(self):
        """A minimal, clean tropo-app/ that passes every check."""
        self.fx.write_manifest()
        self.fx.add_file("tropo-app/app/page.tsx", "export default function P(){return null}\n")

    # ---- G1: F1 manifest grounding — fail closed ----------------------------

    def test_g1_missing_manifest_fails_closed(self):
        # No manifest at all — the gate must refuse, never fall back to allow.
        self.fx.add_file("tropo-app/app/page.tsx", "ok\n")
        commit = self.fx.commit()
        result = self.fx.run(commit)
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(result.exit_code, gate.EXIT_NO_DECLARATION)
        self.assertTrue(any("no app-ship declaration" in v for v in result.violations),
                        result.violations)

    def test_g1_corrupt_manifest_fails_closed(self):
        # A manifest with no parseable frontmatter is corrupt → fail closed.
        self.fx.write_manifest(text="not a manifest, just garbage bytes\n")
        self.fx.add_file("tropo-app/app/page.tsx", "ok\n")
        commit = self.fx.commit()
        result = self.fx.run(commit)
        self.assertEqual(result.exit_code, gate.EXIT_NO_DECLARATION)
        self.assertTrue(any("no app-ship declaration" in v for v in result.violations),
                        result.violations)

    def test_g1_non_deny_default_fails_closed(self):
        # A well-formed manifest that is NOT default-deny cannot authorize.
        bad = REAL_MANIFEST.read_text(encoding="utf-8").replace("default: deny", "default: allow")
        self.fx.write_manifest(text=bad)
        self.fx.add_file("tropo-app/app/page.tsx", "ok\n")
        commit = self.fx.commit()
        result = self.fx.run(commit)
        self.assertEqual(result.exit_code, gate.EXIT_NO_DECLARATION)

    # ---- G2: F2 deny-holes ---------------------------------------------------

    def test_g2_denyhole_playbook_runs_refused(self):
        self._clean_app()
        self.fx.add_file("tropo-app/playbook-runs/x/run.jsonl", '{"note":"benign"}\n')
        commit = self.fx.commit()
        result = self.fx.run(commit)
        self.assertEqual(result.exit_code, gate.EXIT_VIOLATION)
        self.assertTrue(any("DENY-HOLE 'playbook-runs/**'" in v and "run.jsonl" in v
                            for v in result.violations), result.violations)

    def test_g2_denyhole_tropo_studio_refused(self):
        self._clean_app()
        self.fx.add_file("tropo-app/config/.tropo-studio/dirty-counter.json", "{}\n")
        commit = self.fx.commit()
        result = self.fx.run(commit)
        self.assertEqual(result.exit_code, gate.EXIT_VIOLATION)
        self.assertTrue(any("**/.tropo-studio/**" in v for v in result.violations),
                        result.violations)

    def test_g2_clean_app_source_passes(self):
        self._clean_app()
        commit = self.fx.commit()
        result = self.fx.run(commit)
        self.assertEqual(result.exit_code, gate.EXIT_CLEAN, result.violations)

    def test_g2_denyhole_matcher_is_pure_and_anchored(self):
        # The deny-hole matcher (helper) is unit-checkable straight off the
        # loaded manifest: anchored dir globs match at the root, marker globs
        # match at any depth, and the historical Next.js false positive stays
        # clean.
        m = gate.load_manifest(ROOT)
        self.assertIsNotNone(m.deny_hole_hit("playbook-runs/x/run.jsonl"))
        self.assertIsNotNone(m.deny_hole_hit("vault/files/x.md"))
        self.assertIsNotNone(m.deny_hole_hit("a/b/agent-memory.md"))
        self.assertIsNone(m.deny_hole_hit("app/api/agents/roster/route.ts"))
        self.assertIsNone(m.deny_hole_hit("app/page.tsx"))

    # ---- G3: F3 pinned commit vs advanced HEAD -------------------------------

    def test_g3_pins_commit_ignores_denyhole_added_at_head(self):
        # C1 is clean. HEAD advances to C2, which introduces a deny-hole file.
        # Pinning to C1 must produce a CLEAN split (the C2 violation is invisible
        # to the pin); pinning to C2 must REFUSE. A floating-HEAD-only gate could
        # not tell these apart.
        self._clean_app()
        c1 = self.fx.commit("c1-clean")
        self.fx.add_file("tropo-app/playbook-runs/leak/run.jsonl", '{"event":"run_created"}\n')
        c2 = self.fx.commit("c2-adds-denyhole")

        pinned_c1 = self.fx.run(c1)
        self.assertEqual(pinned_c1.exit_code, gate.EXIT_CLEAN, pinned_c1.violations)
        self.assertEqual(pinned_c1.file_count, 1)  # only C1's page.tsx, not C2's leak
        self.assertEqual(pinned_c1.source_commit, c1)

        pinned_c2 = self.fx.run(c2)
        self.assertEqual(pinned_c2.exit_code, gate.EXIT_VIOLATION)
        self.assertTrue(any("playbook-runs/**" in v for v in pinned_c2.violations))

    def test_g3_missing_pin_fails_closed(self):
        # pinned_commit_required: true + no --source-commit → fail closed.
        self._clean_app()
        self.fx.commit()
        code, out = self.fx.run_cli(source_commit=None)
        self.assertEqual(code, gate.EXIT_NO_DECLARATION)
        self.assertIn("pinned source commit required", out)

    # ---- G4: F4 gitlink refusal ----------------------------------------------

    def test_g4_gitlink_mode_160000_refused(self):
        self._clean_app()
        self.fx.add_gitlink("tropo-app/vendor/submod")
        commit = self.fx.commit()
        result = self.fx.run(commit)
        self.assertEqual(result.exit_code, gate.EXIT_VIOLATION)
        self.assertTrue(any("160000" in v and "GITLINK" in v.upper() for v in result.violations),
                        result.violations)

    def test_g4_symlink_mode_120000_still_refused(self):
        self._clean_app()
        self.fx.add_symlink("tropo-app/app/escape.txt", "../../../etc/passwd")
        commit = self.fx.commit()
        result = self.fx.run(commit)
        self.assertEqual(result.exit_code, gate.EXIT_VIOLATION)
        self.assertTrue(any("120000" in v and "SYMLINK" in v.upper() for v in result.violations),
                        result.violations)

    def test_g4_refused_modes_come_from_declaration(self):
        m = gate.load_manifest(ROOT)
        self.assertIn("120000", m.refused_modes)
        self.assertIn("160000", m.refused_modes)

    # ---- G5: F5 .jsonl content scan ------------------------------------------

    def test_g5_jsonl_private_marker_refused(self):
        self._clean_app()
        self.fx.add_file(
            "tropo-app/data/feed.jsonl",
            '{"type": "tropo.broadcast.crew", "party_uid": "34cf0f1c"}\n',
        )
        commit = self.fx.commit()
        result = self.fx.run(commit)
        self.assertEqual(result.exit_code, gate.EXIT_VIOLATION)
        self.assertTrue(any("feed.jsonl" in v and "PRIVATE CREW DATA" in v
                            for v in result.violations), result.violations)

    def test_g5_prior_extension_list_would_have_missed_jsonl(self):
        # The whole point of F5: the OLD hardcoded extension list did not scan
        # .jsonl, so the marker would have slipped through. The declaration now
        # scans it.
        m = gate.load_manifest(ROOT)
        self.assertTrue(m.scanned_extension("tropo-app/data/feed.jsonl"))
        self.assertTrue(m.scanned_extension("tropo-app/data/feed.ndjson"))
        self.assertFalse(any("feed.jsonl".endswith(e) for e in OLD_HARDCODED_EXTENSIONS),
                         "guard: .jsonl must be absent from the pre-F5 list")

    # ---- G6: fail-closed + RATIFIED banner -----------------------------------
    # Ratified 2026-07-19 (Mike GO; signed Argus A135): the clean-result banner
    # now asserts RATIFIED, not UNSIGNED — a clean gate result authorizes publish.

    def test_g6_clean_split_exits_zero_with_ratified_banner(self):
        self._clean_app()
        commit = self.fx.commit()
        code, out = self.fx.run_cli(commit)
        self.assertEqual(code, gate.EXIT_CLEAN)
        self.assertIn("RATIFIED", out)
        self.assertIn("no violation found", out)

    def test_g6_single_violation_fails_closed(self):
        self._clean_app()
        self.fx.add_file("tropo-app/vault/secret.md", "leak\n")  # deny-hole
        commit = self.fx.commit()
        code, out = self.fx.run_cli(commit)
        self.assertNotEqual(code, 0)
        self.assertIn("DO NOT PUBLISH", out)
        # a refusal must NOT print the clean-result UNSIGNED banner
        self.assertNotIn("no violation found", out)

    # ---- G7: boundary separation (no federation import) ----------------------

    def test_g7_no_federation_path_import(self):
        src = GATE_PATH.read_text(encoding="utf-8")
        for forbidden in ("import segment", "from lib.segment", "from lib import segment",
                          "lib.segment", "import lib.segment"):
            self.assertNotIn(forbidden, src,
                             f"app-ship gate must not share the federation code path (G7): {forbidden!r}")

    # ---- G8: F6 secret-shaped basenames, allowlist-exempt --------------------

    def test_g8_env_and_credential_basenames_refused(self):
        # The exact leak F6 closes: env/credential files that no deny-hole,
        # extension scan, or mode check would have caught before F6 — they would
        # have SHIPPED. Each must now be refused.
        for i, name in enumerate((".env.local", ".env.production", "credentials", "credentials.json")):
            with self.subTest(name=name):
                fx = GateFixture()
                self.addCleanup(fx.cleanup)
                fx.write_manifest()
                fx.add_file("tropo-app/app/page.tsx", "ok\n")
                fx.add_file(f"tropo-app/{name}", "SECRET=real-value\n")
                commit = fx.commit()
                result = fx.run(commit)
                self.assertEqual(result.exit_code, gate.EXIT_VIOLATION, result.violations)
                self.assertTrue(
                    any("SECRET-SHAPED FILENAME" in v and name in v for v in result.violations),
                    result.violations,
                )

    def test_g8_env_templates_still_ship(self):
        # The allowlist-exempt half: .env.example/.sample/.template match the
        # .env.* pattern but their exact basenames are in secret_allowlist, so
        # they still pass (this is what makes F6 different from a deny-hole).
        self._clean_app()
        self.fx.add_file("tropo-app/.env.example", "KEY=your-key-here\n")
        self.fx.add_file("tropo-app/.env.sample", "KEY=sample\n")
        self.fx.add_file("tropo-app/.env.template", "KEY=template\n")
        commit = self.fx.commit()
        result = self.fx.run(commit)
        self.assertEqual(result.exit_code, gate.EXIT_CLEAN, result.violations)

    def test_g8_matcher_is_allowlist_exempt_and_precise(self):
        # Unit check of the F6 helper straight off the real declaration: the
        # env/credential shapes hit, the templates are exempt, and a legit
        # `credentials-helper.ts` is NOT a false positive.
        m = gate.load_manifest(ROOT)
        self.assertIsNotNone(m.secret_filename_hit("tropo-app/.env.local"))
        self.assertIsNotNone(m.secret_filename_hit("tropo-app/config/credentials"))
        self.assertIsNone(m.secret_filename_hit("tropo-app/.env.example"))
        self.assertIsNone(m.secret_filename_hit("tropo-app/.env.template"))
        self.assertIsNone(m.secret_filename_hit("tropo-app/lib/credentials-helper.ts"))

    def test_g8_field_absent_fails_closed(self):
        # F1-consistent: a manifest missing secret_filename_patterns fails closed.
        stripped = "\n".join(
            line for line in REAL_MANIFEST.read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith(("secret_filename_patterns", '- ".env"', '- ".env.*"',
                                            '- "credentials"', '- "credentials.*"'))
        )
        self.fx.write_manifest(text=stripped)
        self.fx.add_file("tropo-app/app/page.tsx", "ok\n")
        commit = self.fx.commit()
        result = self.fx.run(commit)
        self.assertEqual(result.exit_code, gate.EXIT_NO_DECLARATION)
        self.assertTrue(any("secret_filename_patterns" in v for v in result.violations),
                        result.violations)

    # ---- Regression guards (test-spec §Coverage classes) ---------------------

    def test_reg_anchored_agents_route_not_flagged(self):
        # app/api/agents/... is a legitimate Next.js route; the anchored
        # `agents/**` deny-hole must not match it (historical false positive).
        self._clean_app()
        self.fx.add_file("tropo-app/app/api/agents/roster/route.ts", "export const GET = () => {}\n")
        self.fx.add_file("tropo-app/app/(boards)/boards/agents/page.tsx", "export default () => null\n")
        commit = self.fx.commit()
        result = self.fx.run(commit)
        self.assertEqual(result.exit_code, gate.EXIT_CLEAN, result.violations)

    def test_reg_env_example_allowlist_passes(self):
        self._clean_app()
        self.fx.add_file("tropo-app/.env.example", "ANTHROPIC_API_KEY=your-key-here\n")
        commit = self.fx.commit()
        result = self.fx.run(commit)
        self.assertEqual(result.exit_code, gate.EXIT_CLEAN, result.violations)

    def test_reg_code_type_reference_not_flagged_but_json_row_is(self):
        # A TS equality check naming an event type is app code, not a leaked
        # event row — it must NOT match (requires the JSON key-value shape).
        self._clean_app()
        self.fx.add_file(
            "tropo-app/lib/studio-events.ts",
            'if (e.type === "tropo.broadcast.crew") render(e);\n',
        )
        commit = self.fx.commit()
        clean = self.fx.run(commit)
        self.assertEqual(clean.exit_code, gate.EXIT_CLEAN, clean.violations)

        # The serialized-record shape (a real event row) MUST be caught.
        self.fx.add_file(
            "tropo-app/lib/leaked.json",
            '{"type": "tropo.broadcast.crew", "agent_root_uid": "123e12e7"}\n',
        )
        commit2 = self.fx.commit("adds-json-row")
        leaked = self.fx.run(commit2)
        self.assertEqual(leaked.exit_code, gate.EXIT_VIOLATION)
        self.assertTrue(any("leaked.json" in v for v in leaked.violations), leaked.violations)


if __name__ == "__main__":
    unittest.main(verbosity=2)
