#!/usr/bin/env python3
"""W5 acceptance: cockpit ask -> orient -> mounted cache -> real citation."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


orient = _load("w5_orient", TOOLS / "tropo-orient.py")
gardener = _load("w5_gardener", TOOLS / "tropo-gardener-verdict.py")
validator = _load("w5_validator", TOOLS / "tropo-validate.py")
walker = _load("w5_import_walker", TOOLS / "tropo-import-walker.py")
stage_tests = _load(
    "w5_stage_tests", TOOLS / "tests" / "test_orient_stage_c.py"
)

from lib import (  # noqa: E402
    distiller,
    metered_model,
    orient_stage_c,
    span_guard,
    viewer_projection,
)


ROUTE = ROOT / "tropo-app" / "app" / "api" / "orient" / "route.ts"
COCKPIT = ROOT / "tropo-app" / "components" / "work" / "OrientAsk.tsx"


class MountedFixture:
    ANSWER = "W5CACHEONLY says the launch window is forty two days."

    def __init__(self, suffix: str = ".docx", uid: str = "abcd1234"):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.uid = uid
        self.files = self.root / "vault" / "files"
        self.files.mkdir(parents=True)
        self.source = self.root / "mounted" / f"real-source{suffix}"
        self.source.parent.mkdir()
        self.source.write_bytes(f"binary fixture {suffix}".encode())
        self.pointer = self.files / f"{uid}.md"
        self.pointer.write_text(
            "---\n"
            f"uid: {uid}\n"
            "type: external-artifact\n"
            "title: Mike's real mounted fixture\n"
            "content_class: imported-external\n"
            f"source_path: {self.source}\n"
            "source_hash: outside\n"
            "---\n"
            "# Pointer only\n\nThe answer is deliberately absent here.\n"
        )
        cache = self.root / ".tropo-studio" / "extract-cache"
        cache.mkdir(parents=True)
        self.cache = cache / f"{uid}.json"
        self.cache.write_text(
            json.dumps(
                {
                    "uid": uid,
                    "content_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
                    "source_filename": self.source.name,
                    "status": "ok",
                    "chars": len(self.ANSWER),
                    "text": self.ANSWER,
                }
            )
        )
        self.record = {
            "uid": uid,
            "type": "external-artifact",
            "title": "Mike's real mounted fixture",
            "content_class": "imported-external",
            "source_path": str(self.source),
            "source_hash": "outside",
            "path": f"vault/files/{uid}.md",
        }

    def close(self):
        self.tmp.cleanup()


def _fts(path: Path, rows: list[tuple[str, str, str]]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE VIRTUAL TABLE entries_fts USING fts5(uid UNINDEXED, title, body)"
        )
        connection.executemany("INSERT INTO entries_fts VALUES (?,?,?)", rows)


class CockpitFreePathTests(unittest.TestCase):
    def test_asks_without_uid_and_keeps_cost_arithmetic_untouched(self):
        route = ROUTE.read_text()
        cockpit = COCKPIT.read_text()
        self.assertIn('runArgoTool("tropo-orient"', route)
        self.assertNotIn("vault/tools/tropo-orient.py", route)
        self.assertIn('if (read) args.push("--read")', route)
        self.assertIn('read: mode !== "free"', cockpit)
        self.assertIn('approve: mode === "approved"', cockpit)

        answer = {
            "ok": True,
            "task": "abcd1234",
            "task_title": "Resolved without a UID",
            "items": [{"uid": "abcd1234", "title": "Citation", "where": "real.md"}],
        }
        out = io.StringIO()
        argv = ["tropo-orient.py", "--question", "Where is W5?", "--json"]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(
                orient,
                "resolve_question_anchor",
                return_value={
                    "uid": "abcd1234",
                    "terms": ("where",),
                    "method": "entries_fts",
                },
            ),
            mock.patch.object(orient, "orient", return_value=answer) as run,
            mock.patch.object(
                orient,
                "_admission_quote",
                side_effect=AssertionError("free path priced a provider call"),
            ),
            mock.patch.object(
                orient,
                "MeteredEdge",
                side_effect=AssertionError("free path constructed a metered edge"),
            ),
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(orient.main(), 0)

        payload = json.loads(out.getvalue())
        self.assertEqual(payload["items"][0]["where"], "real.md")
        self.assertIsNone(run.call_args.args[3] if len(run.call_args.args) > 3 else None)


class ExtractedBodyTests(unittest.TestCase):
    def test_reads_extracted_bodies_for_all_locked_formats_and_fails_loudly(self):
        formats = (
            (".docx", "abcd1200"),
            (".pptx", "abcd1201"),
            (".xlsx", "abcd1202"),
            (".pdf", "f015abcd1203"),
        )
        for suffix, uid in formats:
            fixture = MountedFixture(suffix, uid)
            self.addCleanup(fixture.close)
            reader = orient_stage_c.studio_body_reader(
                fixture.root, fixture.files, {uid: fixture.record}
            )
            source = reader.source(uid)
            self.assertIn(fixture.ANSWER, source.body.decode())
            self.assertEqual(source.citation_path, str(fixture.source))
            self.assertTrue(Path(source.citation_path).is_file())

            # Negative control: without cache wiring the governed pointer does
            # not contain the answer.
            governed = span_guard.match_domain_bytes(fixture.pointer).decode()
            self.assertNotIn(fixture.ANSWER, governed)

        stale = MountedFixture()
        self.addCleanup(stale.close)
        stale.cache.write_text(
            json.dumps(
                {
                    "uid": stale.uid,
                    "content_sha256": "0" * 64,
                    "status": "ok",
                    "text": stale.ANSWER,
                }
            )
        )
        with self.assertRaises(orient_stage_c.BodySourceError) as caught:
            orient_stage_c.studio_body_reader(
                stale.root, stale.files, {stale.uid: stale.record}
            )(stale.uid)
        self.assertEqual(caught.exception.code, "EXTRACT_CACHE_UNSYNCED")

        dataless = MountedFixture()
        self.addCleanup(dataless.close)
        original_lstat = Path.lstat

        def planted_lstat(path: Path):
            value = original_lstat(path)
            if path == dataless.source:
                return types.SimpleNamespace(
                    st_flags=orient_stage_c._extractor_module().SF_DATALESS,
                    st_mode=stat.S_IFREG | 0o644,
                )
            return value

        with mock.patch.object(Path, "lstat", planted_lstat):
            with self.assertRaises(orient_stage_c.BodySourceError) as caught:
                orient_stage_c.studio_body_reader(
                    dataless.root, dataless.files, {dataless.uid: dataless.record}
                )(dataless.uid)
        self.assertEqual(caught.exception.code, "MOUNTED_SOURCE_DATALESS")


class _Result:
    def __init__(self, value):
        self.ok = True
        self.value = value
        self.error = None


class _LiveProjection:
    def __init__(self):
        self.membership = {
            "11111111": ("a0000001",),
            "22222222": ("a0000001",),
        }
        self.stored_count = 999

    def filter_visible_uids(self, _candidates, viewer):
        return _Result(self.membership[viewer.principal_uid])


class VisibilityTests(unittest.TestCase):
    def test_visibility_is_derived_live_uid_keyed_and_class_counted(self):
        records = {
            "a0000001": {"uid": "a0000001", "content_class": "studio-work"},
            "a0000002": {"uid": "a0000002", "content_class": "imported-external"},
        }
        projection = _LiveProjection()
        first = orient.visibility_report(
            records=records,
            projection=projection,
            principal_uids=("11111111", "22222222"),
            principal_names={"11111111": "Mike", "22222222": "Talos"},
        )
        self.assertEqual(first["scope_mode"], "undifferentiated")
        self.assertEqual(first["principals"]["11111111"]["visible_records"], 1)
        self.assertEqual(
            first["principals"]["11111111"]["content_classes"], {"studio-work": 1}
        )
        self.assertNotIn("Mike", first["principals"])

        projection.membership["11111111"] = ("a0000001", "a0000002")
        second = orient.visibility_report(
            records=records,
            projection=projection,
            principal_uids=("11111111", "22222222"),
            principal_names={"11111111": "Mike", "22222222": "Talos"},
        )
        self.assertEqual(second["scope_mode"], "per-principal")
        self.assertEqual(second["principals"]["11111111"]["visible_records"], 2)
        self.assertNotEqual(
            second["principals"]["11111111"]["visible_records"],
            projection.stored_count,
        )


class ComposedPathTests(unittest.TestCase):
    def _route_call(self, fixture: MountedFixture, database: Path) -> subprocess.CompletedProcess:
        # The TS harness below does `import "next/server"`, a bare specifier tsx/node
        # resolves by walking up from the harness FILE's own directory looking for
        # node_modules -- cwd (set to tropo-app on the subprocess.run below) is not
        # part of that walk. A harness written under the OS temp dir (fixture.root)
        # never reaches tropo-app/node_modules regardless of cwd; anchoring the temp
        # dir under tropo-app itself puts node_modules one hop up. (v1.94 W5 AC4.)
        harness_dir = tempfile.TemporaryDirectory(dir=ROOT / "tropo-app")
        self.addCleanup(harness_dir.cleanup)
        work = Path(harness_dir.name)
        python_harness = work / "orient_harness.py"
        python_harness.write_text(
            """
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

root = Path(os.environ["W5_REPO_ROOT"])
tools = root / "vault" / "tools"
sys.path.insert(0, str(root))
sys.path.insert(0, str(tools))
spec = importlib.util.spec_from_file_location("w5_composed_orient", tools / "tropo-orient.py")
orient = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = orient
spec.loader.exec_module(orient)
from lib import orient_stage_c
from vault.tools.tests import test_orient_stage_c as stage_tests

fixture_root = Path(os.environ["W5_FIXTURE_ROOT"])
uid = os.environ["W5_UID"]
answer = os.environ["W5_ANSWER"]
record = json.loads(os.environ["W5_RECORD"])
try:
    anchored = orient.resolve_question_anchor(
        "What does W5CACHEONLY say?",
        index_path=Path(os.environ["W5_INDEX"]),
        studio_root=fixture_root,
        files_root=fixture_root / "vault" / "files",
        records={uid: record},
    )
    reader = orient_stage_c.studio_body_reader(
        fixture_root, fixture_root / "vault" / "files", {uid: record}
    )
    case = stage_tests.StageCCase("runTest")
    case.setUp()
    try:
        provider = case.provider(spans=[{"uid": uid, "span_text": answer}])
        ranking = stage_tests.FakeRanking(
            viewer=case.viewer,
            index_as_of=stage_tests.SNAPSHOT,
            uids=(uid,),
            authority={uid: 3},
        )
        block = case.run_stage_c(
            provider=provider,
            task_uid=uid,
            task_source=types.SimpleNamespace(
                uid=uid, title="Mounted fixture question", body=answer, links=()
            ),
            ranking=ranking,
            circle=(uid,),
            seed_candidates=(uid,),
            body_reader=reader,
        )
        spans = [
            {
                "uid": span.uid,
                "title": record["title"],
                "text": span.span_text,
                "where": reader.citation_path(span.uid),
                "content_class": record["content_class"],
            }
            for span in block.spans
        ]
        print(json.dumps({
            "ok": True,
            "task": anchored["uid"],
            "task_title": record["title"],
            "items": spans,
            "read": {"status": "read", "spans": spans},
        }))
    finally:
        case.doCleanups()
except Exception as error:
    print(json.dumps({"ok": False, "error": str(error)}))
    raise SystemExit(1)
""".strip()
            + "\n"
        )
        ts_harness = work / "route_harness.ts"
        ts_harness.write_text(
            f"""
import childProcess from "node:child_process";
import {{ syncBuiltinESMExports }} from "node:module";
import {{ NextRequest }} from "next/server";

async function main() {{
const original = childProcess.spawnSync;
childProcess.spawnSync = ((command: string, args: string[], options: object) => {{
  if (command !== "python3" || !args[0]?.endsWith(".tropo/scripts/tropo.py")
      || args[1] !== "tropo-orient") {{
    throw new Error(`unexpected dispatch: ${{command}} ${{args.join(" ")}}`);
  }}
  if (!args.includes("--question") || !args.includes("--read") || !args.includes("--yes")) {{
    throw new Error(`route omitted required orient arguments: ${{args.join(" ")}}`);
  }}
  if (!args.includes("--quote-token") || !args.includes("a".repeat(64))) {{
    throw new Error(`route omitted the bound quote token: ${{args.join(" ")}}`);
  }}
  return original("python3", [{json.dumps(str(python_harness))}], options);
}}) as typeof childProcess.spawnSync;
syncBuiltinESMExports();

const {{ POST }} = await import({json.dumps(ROUTE.as_uri())});
const response = await POST(new NextRequest("http://localhost/api/orient", {{
  method: "POST",
  headers: {{ "content-type": "application/json" }},
  body: JSON.stringify({{
    question: "What does W5CACHEONLY say?",
    read: true,
    approve: true,
    quoteToken: "a".repeat(64),
  }}),
}}));
console.log(JSON.stringify({{ status: response.status, body: await response.json() }}));
}}

main().catch((error) => {{
  console.error(error);
  process.exitCode = 1;
}});
""".strip()
            + "\n"
        )
        environment = os.environ.copy()
        environment.update(
            {
                "W5_REPO_ROOT": str(ROOT),
                "W5_FIXTURE_ROOT": str(fixture.root),
                "W5_INDEX": str(database),
                "W5_UID": fixture.uid,
                "W5_ANSWER": fixture.ANSWER,
                "W5_RECORD": json.dumps(fixture.record),
            }
        )
        return subprocess.run(
            ["node", "--import", "tsx", str(ts_harness)],
            cwd=ROOT / "tropo-app",
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_composed_ask_to_citation_crosses_dispatch_anchor_cache_and_guard(self):
        fixture = MountedFixture(".docx", "abcd1234")
        self.addCleanup(fixture.close)
        database = fixture.root / "vault" / "00-index.sqlite"
        _fts(
            database,
            [
                (
                    fixture.uid,
                    fixture.record["title"],
                    "The extracted-only answer is absent from this index.",
                )
            ],
        )

        result = self._route_call(fixture, database)
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(response["status"], 200, response)
        payload = response["body"]
        self.assertEqual(payload["task"], fixture.uid)
        self.assertEqual(payload["read"]["status"], "read")
        self.assertEqual(payload["read"]["spans"][0]["text"], fixture.ANSWER)
        citation = payload["read"]["spans"][0]["where"]
        self.assertTrue(Path(citation).is_file(), citation)

        # Mutation tooth: disconnect the extracted cache from the same anchor
        # route call. The index and pointer still exist, but the composed call
        # must fail because neither contains W5CACHEONLY.
        fixture.cache.unlink()
        failed = self._route_call(fixture, database)
        self.assertEqual(failed.returncode, 0, failed.stderr)
        refusal = json.loads(failed.stdout)
        self.assertEqual(refusal["status"], 422)
        self.assertFalse(refusal["body"]["ok"])


class RuledPairTests(unittest.TestCase):
    def test_ruled_pair_survives_labels_previews_then_gates_from_one_quote(self):
        fixture = MountedFixture()
        self.addCleanup(fixture.close)
        records = {fixture.uid: fixture.record}
        with (
            mock.patch.object(orient, "ROOT", fixture.root),
            mock.patch.object(orient, "FILES", fixture.files),
        ):
            items = [{"uid": fixture.uid, "title": "Outside"}]

            def assert_outside_survives():
                kept, dropped = orient._read_set(items, records)
                self.assertEqual(kept, [fixture.uid])
                self.assertEqual(dropped, [])

            assert_outside_survives()

            # The ruling's named mutation tooth: put the old outside-origin
            # refusal back and the same positive assertion must fail.
            def old_refusal(_items, _records):
                return [], [
                    {
                        **orient._named(items[0], records),
                        "reason": "imported-refusal-mutation",
                    }
                ]

            with mock.patch.object(orient, "_read_set", side_effect=old_refusal):
                with self.assertRaises(AssertionError):
                    assert_outside_survives()

            named = orient._named({"uid": fixture.uid}, records)
            self.assertTrue(named["outside_origin"])
            self.assertEqual(named["content_class"], "imported-external")
            self.assertEqual(orient.egress_class(fixture.uid, records), "os")
            records[fixture.uid]["audience"] = ["nobody"]
            self.assertEqual(orient.egress_class(fixture.uid, records), "os")
        self.assertNotIn("DROP_IMPORTED", (TOOLS / "tropo-orient.py").read_text())

        request = types.SimpleNamespace(task_source=types.SimpleNamespace(uid="abcd1234"))
        missing = distiller._stage_c_block(
            request,
            task_uid="abcd1234",
            viewer=viewer_projection.Viewer("11111111"),
            index_as_of="w5",
            deterministic=types.SimpleNamespace(),
            query_seeds=types.SimpleNamespace(),
            run_binding=object(),
            policy_resolver=object(),
            segment_resolver=None,
        )
        self.assertFalse(missing.ok)
        self.assertIn("segment_resolver", missing.error.message)
        disclosure = orient_stage_c.EgressDisclosure(
            uid="abcd1234", segment_class="os"
        )
        stage_block = orient_stage_c.StageCBlock(
            (),
            (),
            None,
            "",
            False,
            orient_stage_c.CaptureLog((), "os"),
            (),
            (),
            None,
            (disclosure,),
        )
        carried = distiller.SpanOrientation(None, None, None, stage_block)
        self.assertEqual(carried.egress_report, (disclosure,))

        payload = {"task_uid": "abcd1234", "title": "W5", "body": "", "links": []}
        quote = orient._admission_quote(
            orient.stage_c.C1_TASK_CLASS,
            payload,
            system=orient.stage_c.C1_SYSTEM_PROMPT,
            max_tokens=orient.stage_c.C1_MAX_OUTPUT_TOKENS,
        )
        self.assertEqual(
            orient._admits(
                orient.stage_c.C1_TASK_CLASS,
                payload,
                system=orient.stage_c.C1_SYSTEM_PROMPT,
                max_tokens=orient.stage_c.C1_MAX_OUTPUT_TOKENS,
            ),
            quote.admitted,
        )

        events: list[str] = []
        preview = {
            "status": "ready",
            "count": 1,
            "documents": [
                {
                    "uid": "abcd1234",
                    "title": "Outside",
                    "where": str(fixture.source),
                    "content_class": "imported-external",
                }
            ],
            "token_estimate": quote.token_estimate,
            "dollar_estimate": quote.worst_case_nano_usd / 1_000_000_000,
            "worst_case_nano_usd": quote.worst_case_nano_usd,
            "admitted": True,
            "approval_required": True,
            "quotes": [{"worst_case_nano_usd": quote.worst_case_nano_usd}],
            "quote_token": "a" * 64,
        }
        preparation = types.SimpleNamespace(preview=preview)
        answer = {
            "ok": True,
            "task": "abcd1234",
            "task_title": "W5",
            "items": [{"uid": "abcd1234", "title": "Outside"}],
        }

        def fake_orient(*args, **_kwargs):
            if len(args) > 3 and args[3] is not None:
                events.append("provider")
            return dict(answer)

        def edge():
            events.append("edge")
            return object()

        argv = [
            "tropo-orient.py",
            "--question",
            "Where is W5?",
            "--read",
            "--yes",
            "--quote-token",
            "a" * 64,
            "--json",
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(
                orient,
                "resolve_question_anchor",
                return_value={"uid": "abcd1234", "terms": ("where",)},
            ),
            mock.patch.object(orient, "orient", side_effect=fake_orient),
            mock.patch.object(orient, "prepare_read", return_value=preparation),
            mock.patch.object(
                orient,
                "_preview_lines",
                side_effect=lambda value: events.append("preview") or ["PREVIEW"],
            ),
            mock.patch.object(orient, "MeteredEdge", side_effect=edge),
            mock.patch(
                "socket.create_connection",
                return_value=types.SimpleNamespace(close=lambda: None),
            ),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(orient.main(), 0)
        self.assertEqual(events, ["preview", "edge", "provider"])

        tampered_argv = [
            "tropo-orient.py",
            "--question",
            "Where is W5?",
            "--read",
            "--yes",
            "--quote-token",
            "b" * 64,
            "--json",
        ]
        with (
            mock.patch.object(sys, "argv", tampered_argv),
            mock.patch.object(
                orient,
                "resolve_question_anchor",
                return_value={"uid": "abcd1234", "terms": ("where",)},
            ),
            mock.patch.object(orient, "orient", return_value=dict(answer)),
            mock.patch.object(orient, "prepare_read", return_value=preparation),
            mock.patch.object(
                orient,
                "MeteredEdge",
                side_effect=AssertionError("tampered quote reached the edge"),
            ),
            mock.patch(
                "socket.create_connection",
                side_effect=AssertionError("tampered quote reached gateway preflight"),
            ),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(orient.main(), 0)

        stage_case = stage_tests.StageCCase("runTest")
        stage_case.setUp()
        self.addCleanup(stage_case.doCleanups)
        provider = stage_case.provider()
        denied_quote = metered_model.RequestAdmissionQuote(
            task=orient_stage_c.C1_TASK_CLASS,
            model=quote.model,
            request_bytes=quote.request_bytes,
            request_sha256=quote.request_sha256,
            max_tokens=quote.max_tokens,
            worst_case_nano_usd=quote.ceiling_nano_usd + 1,
            ceiling_nano_usd=quote.ceiling_nano_usd,
            admitted=False,
        )
        with mock.patch.object(
            metered_model, "quote_request_admission", return_value=denied_quote
        ):
            with self.assertRaises(orient_stage_c.StageCRefusal) as caught:
                stage_case.run_stage_c(provider=provider)
        self.assertEqual(caught.exception.reason, orient_stage_c.REASON_SPEND_CEILING)
        self.assertEqual(provider.calls, [])

        preview_body = span_guard.match_domain_bytes(
            stage_case.fx.files["aaaa0001"]
        )
        preview_c2 = orient._admission_quote(
            orient_stage_c.C2_TASK_CLASS,
            orient._c2_preview_payload(
                stage_tests.TASK_UID, ["aaaa0001"], {"aaaa0001": preview_body}
            ),
            system=orient_stage_c.C2_SYSTEM_PROMPT,
            max_tokens=orient_stage_c.C2_MAX_OUTPUT_TOKENS,
        )
        production_quotes: list[metered_model.RequestAdmissionQuote] = []
        quote_request = metered_model.quote_request_admission

        def record_production_quote(*args, **kwargs):
            result = quote_request(*args, **kwargs)
            production_quotes.append(result)
            return result

        # W5 AC5 (Argus A166 ruling evt_b51c083be28ac6fe_00000350): a bounded
        # preview figure and a realized production request can never be
        # byte-identical — Stage C injects C1's provider-produced brief after
        # the preview is shown. The contract is not sha equality; it is that
        # the exact figure the human approved becomes the ceiling the real
        # edge admits on.
        approved_ceiling_nano_usd = preview_c2.worst_case_nano_usd
        with mock.patch.object(
            metered_model,
            "quote_request_admission",
            side_effect=record_production_quote,
        ):
            stage_case.run_stage_c(
                provider=stage_case.provider(),
                c2_approved_ceiling_nano_usd=approved_ceiling_nano_usd,
            )
        edge_c2 = next(
            item
            for item in production_quotes
            if item.task == orient_stage_c.C2_TASK_CLASS
        )
        self.assertEqual(
            edge_c2.ceiling_nano_usd,
            approved_ceiling_nano_usd,
            "the real C2 call must admit against the exact figure the human "
            "approved, not a re-realized bounded preview figure",
        )
        self.assertTrue(
            edge_c2.admitted,
            "an honestly worst-case-priced preview must never under-quote "
            "the real call it approved",
        )


class ContentClassTests(unittest.TestCase):
    def _write(self, root: Path, uid: str, extra: str) -> Path:
        path = root / "vault" / "files" / f"{uid}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\n"
            f"uid: {uid}\n"
            "type: note\n"
            "title: W5 fixture\n"
            "status: active\n"
            "state: active\n"
            "owner: test\n"
            "created: '2026-08-31'\n"
            f"{extra}"
            "---\n"
            "# Body\n\nBody bytes stay fixed.\n"
        )
        return path

    def test_content_class_is_stamped_backfilled_and_warn_safe(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        (root / "vault" / "files").mkdir(parents=True)
        (root / "STUDIO.md").write_text(
            "---\nuid: 11111111\ntier: vault\n---\n# Fixture\n"
        )
        external = self._write(
            root,
            "aaaabbbb",
            "source_hash: outside\nextraction_scope: external\n",
        )
        unknown = self._write(root, "ccccdddd", "")
        current = root / "vault" / "00-index.jsonl"
        archive = root / "vault" / "00-archive-index.jsonl"
        archive.write_text("")
        database = root / "vault" / "00-index.sqlite"
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE entries(uid TEXT PRIMARY KEY, fm_json TEXT)")

        def freshen(_uid: str, fixture_root: Path) -> int:
            rows = []
            for path in sorted((fixture_root / "vault" / "files").glob("*.md")):
                raw = path.read_text()
                front = raw.split("---", 2)[1]
                record = yaml.safe_load(front)
                record["path"] = f"vault/files/{path.name}"
                rows.append(record)
            current.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with sqlite3.connect(database) as connection:
                for row in rows:
                    connection.execute(
                        "INSERT OR REPLACE INTO entries(uid, fm_json) VALUES (?,?)",
                        (row["uid"], json.dumps(row)),
                    )
            return 0

        freshen("", root)
        findings, checked, missing = validator.check_origin_marked_content_class(root)
        self.assertEqual((checked, missing), (1, 1))
        self.assertTrue(any("[WARN]" in finding for finding in findings))

        before_bodies = {
            path.name: path.read_bytes().split(b"---\n", 2)[-1]
            for path in (external, unknown)
        }
        dry = gardener.backfill_content_classes(
            vault_root=root, apply=False, freshen=freshen
        )
        self.assertEqual(dry["counts"]["imported-external"], 1)
        self.assertEqual(dry["counts"]["unclassified"], 1)
        self.assertEqual(dry["changed"], 2)
        self.assertNotIn("content_class:", external.read_text())

        applied = gardener.backfill_content_classes(
            vault_root=root, apply=True, freshen=freshen
        )
        self.assertTrue(applied["complete"], applied["errors"])
        self.assertEqual(applied["changed"], 2)
        self.assertIn("content_class: imported-external", external.read_text())
        self.assertIn("content_class: unclassified", unknown.read_text())
        after_bodies = {
            path.name: path.read_bytes().split(b"---\n", 2)[-1]
            for path in (external, unknown)
        }
        self.assertEqual(after_bodies, before_bodies)

        findings, checked, missing = validator.check_origin_marked_content_class(root)
        self.assertEqual((checked, missing), (1, 0))
        self.assertEqual(findings, [])

    def test_content_class_is_stamped_on_import_admission(self):
        def admission_verdict() -> str:
            rendered = walker.render_vault_projection(
                "aaaabbbb",
                "mounted/.tropo-sidecar.md",
                "mounted/source.docx",
                "Imported fixture",
                "11111111",
                "source.docx",
                42,
                "2026-09-01T00:00:00Z",
                "a" * 64,
                "sha256",
                "/outside/source.docx",
            )
            return str(yaml.safe_load(rendered.split("---", 2)[1])["content_class"])

        self.assertEqual(admission_verdict(), "imported-external")
        with mock.patch.object(
            walker, "_external_content_class", return_value="unclassified"
        ):
            self.assertEqual(admission_verdict(), "unclassified")


if __name__ == "__main__":
    unittest.main()
