"""Git environment containment for test fixtures — the shared seam.

THE INCIDENT, 2026-09-02 ~22:20 local. A fixture ran `git init` with `cwd=<temp>`
and `env=None`, so it inherited the caller's environment. A sub-agent shell had
`GIT_DIR` set. **cwd does not win over GIT_DIR**: git re-initialised the REAL
argo-os repository as BARE, and the `config` calls that followed landed in
argo-os/.git/config — core.bare=true, core.hooksPath pointed at a temp directory
that was about to be deleted. Three agents lost their working tree at once.

talos-t61 cured exactly one fixture (test_distiller_orient.py) and left the
mechanics as a template with the instruction not to hand-patch the rest. This
module is that template, extracted once so every fixture can share it.

Two rules, and the second is the one that makes this containment rather than
hygiene:

1. Every inherited `GIT_*` variable is stripped. A fixture's git must be told
   where it operates, never inherit it.
2. The REDIRECT variables are refused **even when a caller passes them
   explicitly**. Identity and date variables may be set deliberately; the nine
   below point git at a different repository, and no fixture has a legitimate
   reason to set one. This is strictly stronger than scrubbing inheritance,
   because the incident's shape is "something upstream set GIT_DIR" and an
   explicit pass-through would reopen it.

Use `git_run` rather than calling subprocess directly — it also pins the
repository with `-C`, which is belt to the scrubbed environment's braces.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

#: The GIT_* variables that REDIRECT git at another repository. Refused whether
#: inherited OR passed explicitly. Every other GIT_* variable (dates, identity)
#: is inherited-scrubbed but may be set deliberately by a caller.
GIT_REDIRECT_VARS = frozenset({
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
})


def scrubbed_env(env: dict | None = None) -> dict:
    """The caller's environment with every GIT_* removed, `env` applied as an OVERLAY.

    A caller's `env` is a set of additions, not a replacement: the process
    environment minus GIT_* is the base, so a fixture does not have to rebuild
    PATH to set GIT_AUTHOR_DATE. Redirect variables in `env` are dropped, not
    honoured — see this module's docstring.
    """
    source = os.environ
    scrubbed = {k: v for k, v in source.items() if not k.startswith("GIT_")}
    scrubbed["GIT_OPTIONAL_LOCKS"] = "0"
    for key, value in (env or {}).items():
        if key in GIT_REDIRECT_VARS:
            continue  # never, not even explicitly — this is the incident
        if key.startswith("GIT_") or key not in source:
            scrubbed[key] = value
    return scrubbed


def git_run(
    *args: str,
    cwd: str | os.PathLike,
    env: dict | None = None,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    timeout: int = 60,
    **kwargs,
) -> subprocess.CompletedProcess:
    """Run git contained: `-C cwd` for the repository, a scrubbed environment.

    `-C` is deliberate redundancy. The scrubbed environment already removes the
    variables that beat cwd; pinning the repository on the command line means a
    future edit that weakens the scrub still cannot silently retarget the call.
    """
    root = Path(cwd)
    return subprocess.run(
        ["git", "-C", str(root), *args],
        env=scrubbed_env(env),
        check=check,
        capture_output=capture_output,
        text=text,
        timeout=timeout,
        **kwargs,
    )


def init_repo(root: str | os.PathLike, *, name: str = "Fixture",
              email: str = "fixture@example.invalid") -> Path:
    """A fresh repository at `root`, contained, with signing and hooks disabled.

    Hooks are pointed at a directory inside the fixture so a developer's global
    core.hooksPath cannot run against fixture commits.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    git_run("init", cwd=root)
    git_run("config", "user.name", name, cwd=root)
    git_run("config", "user.email", email, cwd=root)
    git_run("config", "commit.gpgSign", "false", cwd=root)
    hooks = root / ".fixture-hooks"
    hooks.mkdir(exist_ok=True)
    git_run("config", "core.hooksPath", str(hooks), cwd=root)
    git_run("branch", "-M", "main", cwd=root)
    return root
