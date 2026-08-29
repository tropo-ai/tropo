"""The executor binding: which pipeline step a runnable thing executes.

Stream 1 of v1.92 (dev-spec 5b608d28), AC2 — and the CONTRACT between AC2 and
AC6, declared first because two builders now work against it in parallel
(metis-g112's condition on the build split, 2026-08-24).

THE PROBLEM THIS EXISTS FOR. The release-pipeline 634913c2 declares twelve leaf
steps and is Mike-activated governed substrate. The tools that actually perform
a release reference it ZERO times: tropo-build-release.py carries 28 step
functions of its own naming, tropo-publish-release.py none, and of the twelve
declared steps the FIRST (validate-release-plan-fan-in) and the TERMINAL
(publish-official-release) are named in no tool at all. A human stands in that
gap telling the runtime what happened.

WHY "EXECUTOR" AND NOT "TOOL". The first draft of AC2 required every leaf to
bind exactly one TOOL. That is unsatisfiable, and measuring it is what proved
it: five of the twelve leaves are agent- or human-executed BY DESIGN — the
cold-boot walk runs three personas through a playbook, external-test and
notify-triggered-pipeline-owners are human legs, and the two trigger legs fire
other pipelines — while two leaves legitimately share one tool. Requiring a tool
entry point for each would have forced fake entry points onto human work, which
is worse than the gap it closes.

So a leaf binds exactly one EXECUTOR, and the binding declares its KIND.

    KIND_TOOL      a runnable entry point. Deterministic: the machine does it.
    KIND_PLAYBOOK  a governed procedure. Judgment: a named executor does it.

THE ONE HARD RULE. A playbook-kind binding MUST name an executor class. A
procedure with no named executor is precisely the defect the retirement stream
exists to cure — "a procedure with no executor is an event with no emitter" —
and it is refused here at load rather than discovered at 2am.

HOW THE PIECES USE THIS
  * each tool declares its own bindings as module-level data (`PIPELINE_BINDINGS`)
  * `collect()` gathers them and validates the whole set
  * the AC6 runner asks `for_step()` what comes next and how to run it
  * the AC5 release profile binds its slots with the SAME vocabulary, so a
    profile and a tool cannot disagree about what "deterministic" means

One shape, several declarers, one collector. The alternative — each reader
keeping its own idea of a binding — is the defect this whole stream is about.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "KIND_TOOL",
    "KIND_PLAYBOOK",
    "KINDS",
    "BindingError",
    "StepRefusal",
    "ExecutorBinding",
    "binding_from_declaration",
    "collect",
    "for_step",
    "EXAMPLE_DECLARATION",
    "OPERATOR_TOOLING",
    "JUDGMENT_LEG_BINDINGS",
    "PIPELINE_ROOT_UID",
    "DECLARATION_ATTR",
    "declared_leaves",
    "leaf_names",
    "declarations_in_source",
    "declaring_tools",
    "collect_from_tools",
]

#: The release-pipeline root. Its leaves are what a binding may address.
PIPELINE_ROOT_UID = "634913c2"

#: The module-level name a tool uses to declare its own bindings.
DECLARATION_ATTR = "PIPELINE_BINDINGS"

#: Deterministic slot: a runnable entry point. The machine performs it.
KIND_TOOL = "tool"

#: Judgment slot: a governed procedure performed by a NAMED executor class.
KIND_PLAYBOOK = "playbook"

KINDS: Tuple[str, ...] = (KIND_TOOL, KIND_PLAYBOOK)


class BindingError(RuntimeError):
    """A malformed or unsatisfiable binding. Never a release verdict."""


class StepRefusal(RuntimeError):
    """A refusal that knows which pipeline leaf it belongs to.

    THE HALF OF AC2 THAT IS NOT ABOUT COVERAGE. A release refuses today with
    the name of the script that raised — `tropo-build-release.py: no plan
    record` — which tells the operator where the traceback came from and not
    where they are in the release. The pipeline step is the coordinate that
    means something to a person standing there at 2am: it says which leaf of
    634913c2 is unsatisfied, therefore what has already succeeded, and
    therefore what re-running will and will not repeat.

    `step_uid` is REQUIRED and validated. A refusal that cannot name its step
    is the defect, so this class refuses to construct one — the same
    fail-at-declaration posture `ExecutorBinding` takes, for the same reason:
    2am is the wrong time to discover a message is uninformative.

    `harm` is optional HERE and required by AC3 for the priced class. This
    class deliberately does not enforce that: AC3 enumerates refusal sites and
    asserts each carries exactly one disposition, and a library that refuses to
    construct an unpriced refusal cannot be used to report how many are
    unpriced. Same reasoning as `collect()` not requiring total coverage.
    """

    def __init__(
        self,
        step_uid: str,
        message: str,
        harm: Optional[str] = None,
        step_name: Optional[str] = None,
    ) -> None:
        if not step_uid or len(step_uid) != 8:
            raise BindingError(
                "a step refusal must name the pipeline leaf it belongs to; got "
                "step_uid %r. A refusal that cannot say where in the release it "
                "happened is the defect AC2 exists to close." % (step_uid,)
            )
        if not message:
            raise BindingError(
                "step refusal for %s carries no message" % step_uid
            )
        self.step_uid = step_uid
        self.step_name = step_name
        self.harm = harm
        self.message = message
        super().__init__(self.rendered())

    def rendered(self) -> str:
        """What the operator reads. The step uid is always present."""
        where = self.step_uid
        if self.step_name:
            where = "%s (%s)" % (self.step_name, self.step_uid)
        text = "release step %s: %s" % (where, self.message)
        if self.harm:
            text += " — refusing prevents: %s" % self.harm
        return text

    @property
    def priced(self) -> bool:
        """True when this refusal names the irreversible harm it prevents."""
        return bool(self.harm)


@dataclass(frozen=True)
class ExecutorBinding:
    """One leaf of the release pipeline, and the thing that executes it.

    `step_uid`   the 8-hex uid of a leaf in 634913c2. Never a stage, never a
                 name — the uid is the address, so a rename cannot orphan it.
    `kind`       KIND_TOOL or KIND_PLAYBOOK.
    `entry`      tool: the runnable entry point, as `<script>:<callable>` or a
                 command string. playbook: the governed procedure's uid.
    `executor`   REQUIRED for KIND_PLAYBOOK — the executor CLASS that performs
                 it (an agent role such as "argus", "talos", or "human"). Must
                 be absent for KIND_TOOL, because a deterministic step that
                 names a human executor is a judgment step wearing the wrong
                 label.
    `description` one line, for the runner to print to whoever is standing there.
    """

    step_uid: str
    kind: str
    entry: str
    description: str
    executor: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.step_uid or len(self.step_uid) != 8:
            raise BindingError(
                "binding declares step_uid %r, which is not an 8-hex leaf uid"
                % (self.step_uid,)
            )
        if self.kind not in KINDS:
            raise BindingError(
                "binding for %s declares kind %r; expected one of %s"
                % (self.step_uid, self.kind, ", ".join(KINDS))
            )
        if not self.entry:
            raise BindingError("binding for %s names no entry" % self.step_uid)
        if self.kind == KIND_PLAYBOOK and not self.executor:
            raise BindingError(
                "playbook binding for %s names no executor class. A procedure "
                "with no executor is an event with no emitter — the runner "
                "would stop here and be unable to say who acts."
                % self.step_uid
            )
        if self.kind == KIND_TOOL and self.executor:
            raise BindingError(
                "tool binding for %s names executor %r. A deterministic step "
                "that names a human executor is a judgment step wearing the "
                "wrong label; declare it as %r instead."
                % (self.step_uid, self.executor, KIND_PLAYBOOK)
            )

    @property
    def deterministic(self) -> bool:
        """True when the machine performs it without stopping to ask."""
        return self.kind == KIND_TOOL

    def as_dict(self) -> Dict[str, Any]:
        return {
            "step_uid": self.step_uid,
            "kind": self.kind,
            "entry": self.entry,
            "executor": self.executor,
            "description": self.description,
        }


def binding_from_declaration(row: Any) -> ExecutorBinding:
    """One declared row -> one validated binding.

    Accepts the mapping form a tool writes in its own module. A tuple is NOT
    accepted: positional bindings are how a field gets silently reordered, and
    this contract has two readers who would not notice.
    """
    if not isinstance(row, dict):
        raise BindingError(
            "binding declarations are mappings, not %s — a positional form "
            "can be silently reordered and this contract has two readers"
            % type(row).__name__
        )
    unknown = set(row) - {"step_uid", "kind", "entry", "executor", "description"}
    if unknown:
        raise BindingError(
            "binding for %s declares unknown key(s): %s"
            % (row.get("step_uid", "?"), ", ".join(sorted(unknown)))
        )
    return ExecutorBinding(
        step_uid=str(row.get("step_uid") or ""),
        kind=str(row.get("kind") or ""),
        entry=str(row.get("entry") or ""),
        description=str(row.get("description") or ""),
        executor=(str(row["executor"]) if row.get("executor") else None),
    )


def collect(
    declarations: Iterable[Any], declared_leaves: Optional[Sequence[str]] = None
) -> List[ExecutorBinding]:
    """Validate a whole set of declarations together.

    Set-level rules a single binding cannot enforce:

      * ONE executor per leaf. Two bindings for one step means the runner
        cannot say what comes next, which is the gap this closes.
      * every binding names a leaf that EXISTS, when the caller supplies the
        declared leaves. A binding pointing at an archived or invented uid
        resolves to nothing and reads, from the outside, exactly like coverage.

    Deliberately NOT enforced here: that every leaf has a binding. Partial
    coverage is the honest state during the build, and AC2's test is what
    requires completeness — a library that refuses to load an incomplete set
    cannot be used to report how incomplete it is.
    """
    bindings = [binding_from_declaration(row) for row in declarations]

    seen: Dict[str, ExecutorBinding] = {}
    for binding in bindings:
        prior = seen.get(binding.step_uid)
        if prior is not None:
            raise BindingError(
                "step %s is bound twice (%s and %s); one leaf, one executor"
                % (binding.step_uid, prior.entry, binding.entry)
            )
        seen[binding.step_uid] = binding

    if declared_leaves is not None:
        known = set(declared_leaves)
        stray = sorted(b.step_uid for b in bindings if b.step_uid not in known)
        if stray:
            raise BindingError(
                "binding(s) name step uid(s) that are not live leaves of the "
                "release pipeline: %s" % ", ".join(stray)
            )
    return bindings


def for_step(
    bindings: Iterable[ExecutorBinding], step_uid: str
) -> Optional[ExecutorBinding]:
    """The executor for one leaf, or None. The runner's read path."""
    for binding in bindings:
        if binding.step_uid == step_uid:
            return binding
    return None


# --------------------------------------------------------------------------
# Resolving the leaves. AC5 and AC6 both accept `declared_leaves` as a
# caller-supplied tuple and NOTHING produced one — each reader was on course to
# grow its own idea of what the twelve leaves are, which is the defect this
# module exists to prevent, one level up.
# --------------------------------------------------------------------------

def _studio_root() -> Path:
    """vault/tools/lib/release_bindings.py -> the studio root."""
    return Path(__file__).resolve().parents[3]


def _frontmatter(path: Path) -> str:
    text = path.read_text(errors="replace")
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end != -1 else ""


def _children(fm_text: str) -> List[str]:
    block = re.search(r"^children:\s*\n((?:[ \t]+-[ \t]+\S+\n)*)", fm_text, re.M)
    if not block:
        return []
    return re.findall(r"-[ \t]+(\S+)", block.group(1))


def _scalar(fm_text: str, key: str) -> Optional[str]:
    m = re.search(rf"^{key}:[ \t]*(.*)$", fm_text, re.M)
    if not m:
        return None
    return m.group(1).strip().strip("'\"") or None


def _walk(uid: str, root: Path, seen: set) -> List[Tuple[str, Optional[str]]]:
    if uid in seen:  # a cycle would otherwise hang the collector
        raise BindingError(
            "pipeline node %s appears twice on one path; the tree is cyclic" % uid
        )
    seen = seen | {uid}
    path = root / "vault" / "files" / f"{uid}.md"
    if not path.exists():
        raise BindingError(
            "pipeline node %s is declared as a child but has no entry at %s"
            % (uid, path.relative_to(root))
        )
    fm_text = _frontmatter(path)
    kids = _children(fm_text)
    if not kids:
        return [(uid, _scalar(fm_text, "name") or _scalar(fm_text, "title"))]
    out: List[Tuple[str, Optional[str]]] = []
    for kid in kids:
        out.extend(_walk(kid, root, seen))
    return out


def _leaf_rows(studio_root: Optional[Path] = None) -> List[Tuple[str, Optional[str]]]:
    root = Path(studio_root) if studio_root is not None else _studio_root()
    return _walk(PIPELINE_ROOT_UID, root, set())


def declared_leaves(studio_root: Optional[Path] = None) -> Tuple[str, ...]:
    """The live leaf uids of the release pipeline, read from the vault.

    Computed by walking `634913c2`'s children to the nodes that have none —
    NOT a pinned list. A pinned list is a second copy of the pipeline that
    goes stale the first time a stage gains a step, and the two readers would
    disagree about the release in exactly the way this module forbids for
    bindings. The pipeline entry is the world; this reads it.
    """
    return tuple(uid for uid, _name in _leaf_rows(studio_root))


def leaf_names(studio_root: Optional[Path] = None) -> Dict[str, Optional[str]]:
    """uid -> readable leaf name, for refusal text a person can act on."""
    return {uid: name for uid, name in _leaf_rows(studio_root)}


# --------------------------------------------------------------------------
# Reading a tool's declaration WITHOUT importing it.
# --------------------------------------------------------------------------

_KIND_NAMES = {"KIND_TOOL": KIND_TOOL, "KIND_PLAYBOOK": KIND_PLAYBOOK}


def _module_constants(tree: ast.Module) -> Dict[str, Any]:
    """Module-level `NAME = <literal>` bindings, for static reference.

    A tool naming its own step constant — `"step_uid": FREEZE_STEP` — is the
    normal way to keep one uid in one place, and refusing it would push every
    declarer into duplicating a uid it already defines. Resolved statically
    from the same file, so nothing is executed to read it.
    """
    consts: Dict[str, Any] = dict(_KIND_NAMES)
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            consts[target.id] = ast.literal_eval(node.value)
        except Exception:  # noqa: BLE001 - non-literal constants simply don't qualify
            continue
    return consts


def _literal(node: ast.AST, where: str, consts: Dict[str, Any]) -> Any:
    """Resolve a declaration node: literals, plus module-level constants.

    Recurses through mappings and sequences so a constant may appear at any
    depth. Anything that is neither — a call, an f-string, a comprehension —
    is refused: bindings are data, and a computed value cannot be read without
    running the tool, which is precisely what this reader must not do.
    """
    if isinstance(node, ast.Name):
        if node.id in consts:
            return consts[node.id]
        raise BindingError(
            "%s references %s, which is not a module-level literal constant in "
            "the declaring file. A binding may name a constant defined beside "
            "it, not one computed or imported at runtime."
            % (where, node.id)
        )
    if isinstance(node, ast.Attribute) and node.attr in _KIND_NAMES:
        return _KIND_NAMES[node.attr]
    if isinstance(node, ast.Dict):
        out: Dict[Any, Any] = {}
        for key_node, val_node in zip(node.keys, node.values):
            if key_node is None:
                raise BindingError(
                    "%s uses dict unpacking in a binding; declare the keys"
                    % where
                )
            out[_literal(key_node, where, consts)] = _literal(
                val_node, where, consts
            )
        return out
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_literal(el, where, consts) for el in node.elts]
    try:
        return ast.literal_eval(node)
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        raise BindingError(
            "%s declares a binding value that is not a literal (%s). Bindings "
            "are data: a computed value cannot be read without running the "
            "tool, and this contract is read by things that must not run it."
            % (where, exc)
        ) from exc


def declarations_in_source(path: Path) -> List[Dict[str, Any]]:
    """A tool's `PIPELINE_BINDINGS`, read statically. No import, no execution.

    Deliberately not `import_module`. These tools build and publish releases;
    importing one to ask what it declares would run its module body, and the
    collector is called from tests and from a cold runner that has no business
    executing a release tool as a side effect of reading it.
    """
    path = Path(path)
    try:
        tree = ast.parse(path.read_text(errors="replace"), filename=str(path))
    except SyntaxError as exc:
        raise BindingError("%s does not parse: %s" % (path.name, exc)) from exc

    for node in tree.body:  # module level only: a binding is not conditional
        targets = (
            node.targets if isinstance(node, ast.Assign)
            else [node.target] if isinstance(node, ast.AnnAssign)
            else []
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id == DECLARATION_ATTR:
                value = node.value
                if value is None:
                    return []
                if not isinstance(value, (ast.Tuple, ast.List)):
                    raise BindingError(
                        "%s declares %s as %s; expected a tuple or list of "
                        "mappings" % (path.name, DECLARATION_ATTR,
                                      type(value).__name__)
                    )
                consts = _module_constants(tree)
                return [
                    _literal(el, f"{path.name}:{DECLARATION_ATTR}", consts)
                    for el in value.elts
                ]
    return []


def declaring_tools(studio_root: Optional[Path] = None) -> List[Path]:
    """Every release tool that declares bindings, in a stable order."""
    root = Path(studio_root) if studio_root is not None else _studio_root()
    tools = root / "vault" / "tools"
    if not tools.is_dir():
        raise BindingError("no vault/tools directory under %s" % root)
    found = [
        p for p in sorted(tools.glob("*.py"))
        if DECLARATION_ATTR in p.read_text(errors="replace")
    ]
    return found


def collect_from_tools(
    studio_root: Optional[Path] = None,
) -> Tuple[List[ExecutorBinding], Dict[str, Path]]:
    """Gather every tool's declaration and validate the whole set.

    Returns the bindings and a step_uid -> declaring-file map, so a duplicate
    or a stray can be reported by the file that caused it rather than as an
    anonymous set-level complaint.
    """
    root = Path(studio_root) if studio_root is not None else _studio_root()
    rows: List[Dict[str, Any]] = list(JUDGMENT_LEG_BINDINGS)
    here = Path(__file__)
    source_of: Dict[str, Path] = {
        str(row["step_uid"]): here for row in JUDGMENT_LEG_BINDINGS
    }
    for tool in declaring_tools(root):
        for row in declarations_in_source(tool):
            if not isinstance(row, dict):
                raise BindingError(
                    "%s declares a non-mapping binding row" % tool.name
                )
            uid = str(row.get("step_uid") or "?")
            prior = source_of.get(uid)
            if prior is not None:
                raise BindingError(
                    "step %s is declared by both %s and %s; one leaf, one "
                    "executor" % (uid, prior.name, tool.name)
                )
            source_of[uid] = tool
            rows.append(row)
    bindings = collect(rows, declared_leaves(root))
    return bindings, source_of


# --------------------------------------------------------------------------
# The legs no tool declares, because no tool executes them.
#
# A156's design has each tool declare the leaves it performs, and that instinct
# is right: the tool is the authority on its own work. It does not reach five of
# the twelve. The judgment legs are performed by a person or an agent and have
# no module to hold a declaration, so declaring them "in the tool" would mean
# inventing a tool to hold the sentence — the fake entry point AC2's own
# behavior text refuses.
#
# So they are declared here, in the contract itself, and `collect_from_tools`
# folds both sources. This ADDS a declaration site; it does not change the
# shape. `ExecutorBinding`, `collect` and `for_step` are untouched, which is why
# T51's AC6 read path is unaffected.
#
# ON `entry` FOR FOUR OF THESE FIVE. A playbook binding's `entry` is the
# governed procedure's uid. Only the cold-boot walk has a separate playbook
# (6f3d2a18). For the other four the governed procedure IS the leaf entry's own
# body — 0cf86ea5 and 4f64ec3c carry numbered execution steps, 37996741 carries
# the five-step notify sequence, bc6b17ec carries the hand-off text and the exit
# criteria. Binding a leaf to itself looks circular and is not: `entry` answers
# "what does the executor read to perform this", and for these four the honest
# answer is that entry. The alternative was to bind them to the pipeline
# definitions they trigger (5a4337ff, da3f50dc), which name what gets SPAWNED
# and not what the executor DOES.
#
# ONE OF THESE IS A KNOWN HOLE AND IS NOT PAPERED OVER. bc6b17ec's own §Gaps
# records that the external-test protocol was never specified — who executes it,
# what pass/fail means, how results are recorded — and that its previous
# cross-reference pointed at a playbook section that does not exist. Its body
# does carry an actionable hand-off ("Mike unpacks the zip and runs the vault
# through its activation sequence") plus machine-checkable exit criteria, so the
# binding is real rather than decorative. The missing spec is filed separately,
# not hidden behind a green test.
JUDGMENT_LEG_BINDINGS: Tuple[Dict[str, Any], ...] = (
    {
        "step_uid": "0cf86ea5",
        "kind": KIND_PLAYBOOK,
        "entry": "0cf86ea5",
        "executor": "argus",
        "description": "author the doc-spec and fire the doc-pipeline trigger",
    },
    {
        "step_uid": "4f64ec3c",
        "kind": KIND_PLAYBOOK,
        "entry": "4f64ec3c",
        "executor": "argus",
        "description": "author the test-spec and fire the test-pipeline trigger",
    },
    {
        "step_uid": "37996741",
        "kind": KIND_PLAYBOOK,
        "entry": "37996741",
        "executor": "argus",
        "description": "notify the doc- and test-pipeline owners on their channels",
    },
    {
        "step_uid": "bc6b17ec",
        "kind": KIND_PLAYBOOK,
        "entry": "bc6b17ec",
        "executor": "mike",
        "description": "external test: unpack the zip and run the vault cold",
    },
    {
        "step_uid": "c6b61fb9",
        "kind": KIND_PLAYBOOK,
        "entry": "6f3d2a18",
        "executor": "vela",
        "description": "cold-boot walk: three personas walk the artifact cold",
    },
    # Tool-kind, but its executor lives OUTSIDE vault/tools, so no tool in the
    # collector's glob can declare it. The leaf names no tool at all — its exit
    # criterion says release history, last_release_reflected, registry rows and
    # subsystems_touched must be written, and nothing in the entry says by what.
    # This script writes exactly those four, which is why it is the binding.
    {
        "step_uid": "2e9b1db7",
        "kind": KIND_TOOL,
        "entry": "python3 .tropo/scripts/dev-pipeline/update-subsystem-canonical-docs.py",
        "description": "write release history, registry rows and subsystems_touched",
    },
)


#: The worked example the split's two builders share. Deliberately real: this
#: is the release-pipeline's own terminal step, which today is named in no tool
#: at all. `entry` is the callable a runner would invoke; `description` is what
#: it prints to whoever is standing there.
#: THE PRODUCT'S OPERATOR TOOLING, declared here because this module is the
#: bindings declaration and is allowed to know what is being shipped.
#:
#: The cold runner is not. `test_release_profile_seam_v192` asserts that
#: tropo-release-run.py names no product literal at all — "the machine does not
#: know what it is shipping" — and argus-a159 broke that guard by hardcoding
#: eleven tool names and commands into the runner while building the v1.93
#: release driver (05de711d). The runner carried ZERO such literals before that
#: work and the guard was green; it was reported to him as a pre-existing red
#: and it was not.
#:
#: The names live here and the runner reads them, which also removes the second
#: source of truth: the runner had its own idea of what the release tools are
#: called, alongside the profile that declares them.
OPERATOR_TOOLING: Dict[str, str] = {
    # module the runner loads to read a run's recorded moments + identity
    "orchestrator_module": "tropo-release.py",
    # what an operator runs to perform the orchestrator step
    "orchestrator_command": "python3 vault/tools/tropo-release.py --release-plan-uid %s",
    # what an operator runs for the one irreversible outward act
    "publish_command": "python3 vault/tools/tropo-publish-release.py fire",
    # argv[0] the build step's main() expects to see
    "build_argv0": "tropo-build-release.py",
    # the enforced path for recording that a human gate was satisfied
    "signoff_command": ("python3 vault/tools/9e7003b1.py --activation-uid %s "
                        "resume --confirmation-granted-by <principal>"),
    # THE AUTHORITATIVE subsystem registry. Declared here, and read by the
    # runner's release-history adapter, because this module is allowed to know
    # what is being shipped and tropo-release-run.py is not
    # (test_release_profile_seam_v192).
    #
    # It is declared at all because the step's own script DEFAULTS to
    # `<studio-root>/subsystem-registry.jsonl` — a path that has never been
    # authoritative. That default has already fired once: the repo-root file
    # holds exactly ONE orphaned row, v1.54.0, written 2026-05-26 by
    # argus-a84, while the real store carries 146. One release's registry row
    # went to the wrong file and nobody noticed for three months. The build
    # reads the authoritative store, so a row written to the stub is simply
    # absent from the box with nothing failing loudly.
    # (argus-a160, 2026-08-27, found by driving v1.93's release-history step.)
    "subsystem_registry_path": ".tropo-studio/registries/subsystem-registry.jsonl",
}


EXAMPLE_DECLARATION: Tuple[Dict[str, Any], ...] = (
    {
        "step_uid": "3dd817cb",
        "kind": KIND_TOOL,
        "entry": "tropo-publish-release.py:cmd_fire",
        "description": "publish the official release (the one outward act)",
    },
    {
        "step_uid": "c6b61fb9",
        "kind": KIND_PLAYBOOK,
        "entry": "6f3d2a18",
        "executor": "vela",
        "description": "cold-boot walk: three personas walk the artifact cold",
    },
)

# CORRECTION, argus-a157 2026-08-25, before either reader consumed this.
# The playbook-kind row above named `e2c7d185` — the AGENT RETIREMENT playbook —
# as the procedure governing the release cold-boot walk. The leaf itself names
# `6f3d2a18` ("Release Cold-Boot Walk") in its own Flow Rules, and `e2c7d185`
# governs nothing in the release path.
#
# It matters more than an example usually would. AC6's runner prints
# `entry` and `executor` to whoever is standing at a judgment slot, so the
# uncorrected row would have sent a release operator to the retirement
# procedure — and this row is the shape the AC5 profile copies. Grepped before
# fixing: no reader had consumed EXAMPLE_DECLARATION yet, so the correction is
# a value change, not a shape change, and T51's in-flight AC6 is unaffected.
#
# `executor` moved "human" -> "vela" on the same evidence: the leaf's Flow Rules
# put the walk in the orchestrator's hands with Vela ratifying the verdict, and
# Vela authored the playbook at v1.41. The walk is not unowned.
#
# The defect class is the one A156 catalogued seven times on 2026-08-24: a
# reader pointed at a shape the writer never emits. Here it reached the worked
# example of the contract written to stop it. That is not irony worth a comment
# — it is the reason the AC2 test below asserts every playbook entry resolves
# to a live procedure rather than merely being non-empty.
