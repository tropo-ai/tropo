"""One temp Studio that every global points at (argus-a147, AC2 isolation NO-GO).

WHY A WHOLE STUDIO AND NOT A PATCHED GLOBAL
-------------------------------------------
`tropo-lock-dev-spec.py` takes `files_dir` and `vault_root` arguments, so it
LOOKS redirectable. It is not, because the gesture it performs reaches tools that
resolve their own root from their own location:

    e337f1dd.py (pipeline-activate)  VAULT_ROOT = Path(__file__).resolve().parents[2]
    tropo-emit-event.py              VAULT_ROOT = Path(__file__).resolve().parents[2]

Those are computed at import from the script's position on disk. No argument,
environment variable or `cwd` moves them. Passing `files_dir=<tmp>` therefore
redirects the part of the gesture written in Python and leaves the subprocess
half writing into the production Studio — which is exactly what happened: the
AC2 suite wrote fourteen governed entries, seven run folders and six event
streams into the live vault across seven runs, while its assertions all passed.

So the only honest isolation is to give the tools a different `__file__`: build a
Studio-shaped temp tree, copy the tools into it, and run THOSE. Then
`parents[2]` resolves to the temp root for every tool, including ones nobody
remembered to think about.

WHAT THIS ALSO BUYS
-------------------
`production_fingerprint()` makes the claim checkable rather than assumed. A test
asserts the production Studio is byte-identical before and after, so a tool that
starts writing somewhere new is caught by the invariant instead of by a reviewer
reading a diff weeks later.
"""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
from pathlib import Path
from types import ModuleType

REAL_ROOT = Path(__file__).resolve().parents[3]
REAL_TOOLS = REAL_ROOT / "vault" / "tools"

#: Tools the lock gesture reaches, directly or as a subprocess. Copied so their
#: own `__file__` lands inside the temp Studio.
TOOL_SCRIPTS = (
    "tropo-lock-dev-spec.py",
    "tropo-lock-release-plan.py",
    "e337f1dd.py",                # pipeline-activate
    "write-activation-entry.py",
    "tropo-mint-id.py",
    "tropo-emit-event.py",
    "tropo-recycle.py",
    "9e7003b1.py",                # pipeline runtime
)

#: Every surface a gesture can write to. Enumerating SURFACES rather than
#: artifacts is deliberate: a new artifact lands in one of these and is caught,
#: where a new artifact never appears in a hand-kept list.
PRODUCTION_SURFACES = (
    ("governed entries", Path("vault/files"), "*.md"),
    ("run folders", Path("vault/pipeline-runs"), "*"),
    ("event streams", Path("vault/events/streams"), "*.jsonl"),
    ("event receipts", Path("vault/events/receipts"), "*.jsonl"),
    ("activate manifests", Path("playbook-runs"), "*"),
    ("lock journals", Path(".tropo-studio/lock-transactions"), "*.json"),
)


class TempStudio:
    """A Studio-shaped tree with its own copy of the tools."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.files = self.root / "vault" / "files"
        self.runs = self.root / "vault" / "pipeline-runs"
        self.events = self.root / "vault" / "events"
        self.tools = self.root / "vault" / "tools"
        self.journals = self.root / ".tropo-studio" / "lock-transactions"
        self._modules: dict = {}

    def build(self) -> "TempStudio":
        for path in (self.files, self.runs, self.tools,
                     self.events / "streams", self.events / "receipts",
                     self.journals, self.root / "playbook-runs",
                     self.root / ".tropo" / "scripts"):
            path.mkdir(parents=True, exist_ok=True)

        # The tools, and the whole lib package they import from.
        shutil.copytree(REAL_TOOLS / "lib", self.tools / "lib", dirs_exist_ok=True)
        for name in TOOL_SCRIPTS:
            source = REAL_TOOLS / name
            if source.is_file():
                shutil.copy2(source, self.tools / name)

        # .tropo/scripts/lib exists in the real Studio and some tools resolve it.
        real_scripts_lib = REAL_ROOT / ".tropo" / "scripts" / "lib"
        if real_scripts_lib.is_dir():
            shutil.copytree(real_scripts_lib, self.root / ".tropo" / "scripts" / "lib",
                            dirs_exist_ok=True)
        return self

    def load(self, script_name: str, alias: str) -> ModuleType:
        """Import the COPY, so its `__file__`-derived root is this Studio.

        Importing the real module and patching its globals is what fails: it
        cannot reach the subprocess tools at all, and it silently leaves any
        global nobody thought of pointing at production.
        """
        if alias in self._modules:
            return self._modules[alias]
        path = self.tools / script_name
        spec = importlib.util.spec_from_file_location(alias, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._modules[alias] = module
        return module

    def assert_tools_are_rooted_here(self, module: ModuleType) -> None:
        """Confirm the copy actually re-rooted, rather than trusting that it did."""
        root = getattr(module, "VAULT_ROOT", None)
        if root is None:
            return
        assert Path(root).resolve() == self.root, (
            f"{module.__name__} resolved VAULT_ROOT to {root}, not the temp Studio "
            f"{self.root}. The copy did not re-root and this test would write to "
            "production."
        )

    def write_entry(self, uid: str, lines: list) -> Path:
        path = self.files / f"{uid}.md"
        path.write_text(
            "---\n" + f"uid: {uid}\n" + "\n".join(lines) + "\n---\n\n# " + uid + "\n",
            encoding="utf-8")
        return path


def production_fingerprint() -> dict:
    """Content hashes of every production surface a gesture could touch.

    Content, not names: a test that overwrote an existing entry in place would
    leave the name list identical and the Studio changed.
    """
    fingerprint: dict = {}
    for label, relative, pattern in PRODUCTION_SURFACES:
        directory = REAL_ROOT / relative
        entries: dict = {}
        if directory.is_dir():
            for path in sorted(directory.glob(pattern)):
                if path.is_file():
                    entries[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
                elif path.is_dir():
                    entries[path.name + "/"] = _directory_digest(path)
        fingerprint[label] = entries
    return fingerprint


def _directory_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for child in sorted(path.rglob("*")):
        if child.is_file():
            digest.update(str(child.relative_to(path)).encode("utf-8"))
            digest.update(hashlib.sha256(child.read_bytes()).digest())
    return digest.hexdigest()


def diff_fingerprints(before: dict, after: dict) -> dict:
    """What changed, per surface, as {surface: {added, removed, modified}}."""
    changes: dict = {}
    for label in before:
        was, now = before[label], after.get(label, {})
        added = sorted(set(now) - set(was))
        removed = sorted(set(was) - set(now))
        modified = sorted(k for k in set(was) & set(now) if was[k] != now[k])
        if added or removed or modified:
            changes[label] = {"added": added, "removed": removed, "modified": modified}
    return changes
