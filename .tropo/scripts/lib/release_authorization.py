#!/usr/bin/env python3
from __future__ import annotations
"""release_authorization.py — the Pipeline Activation Key gate (dev-spec 2ffdd9d6, brief f8cda3dd).

Fingerprint-as-key. The pipeline runtime mints a key when a run legitimately reaches the
produce-release-folder gate (all prior gates green + the doc/test cascade fired). The build and
ship tools REFUSE without it. The key is a fingerprint of the run's work record — you cannot
mint it without the run having done the work.

THREAT MODEL (honest, per the brief's "later, not now"):
  NOW (private studio, trusted agents): this defeats the ACCIDENTAL shortcut — running
  build/ship with no activation, no pipeline-run, or a run that never reached the gate. The
  fingerprint binds the key to the run's actual event record.
  S9 round-2 (v1.80 addendum, f417a577): it ALSO now defeats a LEAKED key replayed into a
  foreign run folder, even one whose metadata the attacker fully controls/edits — see the
  run_nonce binding below. What it still does NOT do: defend against an attacker who
  exfiltrates the entire ORIGIN run folder (nonce included). That attacker already holds the
  origin's own authorized release; replaying its key into a copy of its own folder gains them
  nothing new. Closing that (and any malicious-agent forgery of the nonce itself) is the same
  deferred graduation as below.
  LATER (marketplace, untrusted agents): true anti-forgery against a malicious agent who
  replays the hash needs cryptographic signing (HMAC/PKI) with a runtime-held key. The
  fingerprint is chosen so a signature wraps the SAME primitive later — no redesign. Until
  then: plain SHA-256 + run-folder-local entropy.

RUN_NONCE BINDING (S9 round-2, f417a577): round-1 salted the fingerprint with run_uid +
minted_at, both read from the KEY at verify time (or the target folder's self-reported
identity). An attacker replaying a stolen key into a same-work-shape folder could edit that
folder's run.state.json (pipeline_run_uid) to match the key's claim — the check passed, and
two independently-built same-shape runs collapsed to the SAME fingerprint anyway, because the
canonical hash strips to `event|step|verdict` and drops everything that would differ between
runs. The fix: every run folder gets a `run_nonce` (os.urandom(16) hex), minted once at
bootstrap (the first write to run.state.json) and never rewritten. The nonce is folded into
compute_fingerprint's canonical input — but the nonce itself NEVER travels in the minted key.
At verify time the fingerprint is recomputed by reading the run_nonce fresh from the run
folder actually being verified, not from anything the key claims. A key minted for run B,
copied into run C, recomputes over C's own (different) nonce and cannot match — the attacker
cannot forge C's nonce to B's because B's nonce never left B's folder.

Importable (require_release_authorization / mint_key) and a CLI (mint / verify).
"""
import sys, json, hashlib, argparse, re, time, os
from pathlib import Path

# This file lives at .tropo/scripts/lib/release_authorization.py, i.e. already inside the
# same lib/ namespace package as _identity.py. When imported normally (e.g. via
# `from lib.release_authorization import ...`, as tropo-build-release.py and the test suite
# do), the caller has already put .tropo/scripts on sys.path, so `from lib._identity import
# ...` below resolves cleanly with no extra work. But this module is ALSO directly
# executable as a CLI (`if __name__ == "__main__"`), and run that way .tropo/scripts is not
# on sys.path — so we defensively insert it ourselves, same pattern vault/tools/9e7003b1.py
# uses for the identical import (d996b941 L0c shared identity resolver).
_TROPO_SCRIPTS = Path(__file__).resolve().parent.parent  # .tropo/scripts
if str(_TROPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_TROPO_SCRIPTS))
from lib._identity import _resolve_principal_uid, _load_fm  # noqa: E402

VAULT_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_RUNS = VAULT_ROOT / "vault" / "pipeline-runs"
VAULT_FILES = VAULT_ROOT / "vault" / "files"
GATE_PRODUCE = "produce-release-folder"
KEY_FILENAME = "release-authorization.json"
CHANGELOG_PATH = VAULT_ROOT / "CHANGELOG.md"
ATTESTED_BUILD_SOURCE_UID = "2ffdd9d6"  # this module's governing dev-spec — stable identity for audit emits

# Events that constitute the "work record" the fingerprint is computed over.
# NOTE: human_signoff is DELIBERATELY excluded — the fingerprint attests the PIPELINE ran (and
# is minted at the produce gate, before any ship signoff). The human signoff is a SEPARATE ship
# gate (checked by _has_human_signoff), so recording it later does not invalidate the key.
_WORK_EVENTS = ("step_completed", "verification_receipt")
# dev-pipeline cascade trigger steps (4.5 doc / 4.6 test). The cascade "fired" = both of these
# trigger-step UIDs have a step_completed event in the run (verified against real run.jsonl,
# not assumed — the structural proof the protocol was followed).
DOC_TRIGGER_STEP = "0cf86ea5"
TEST_TRIGGER_STEP = "4f64ec3c"


def _verdict(e):
    return e.get("verdict") or (e.get("data") or {}).get("verdict") or ""


def _step(e):
    return e.get("step") or e.get("step_name") or ""


class ReleaseAuthorizationError(Exception):
    """Raised on any authorization failure. Callers treat as fail-closed (refuse)."""


def _read_run_events(run_folder: Path):
    """Read all run.jsonl segment events in order. Empty list if none."""
    events = []
    idx = run_folder / "run-index.json"
    segments = ["run.jsonl"]
    if idx.is_file():
        try:
            segments = json.loads(idx.read_text()).get("segments", ["run.jsonl"])
        except Exception:
            segments = ["run.jsonl"]
    for seg in segments:
        p = run_folder / seg
        if not p.is_file():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue  # a malformed line is not a valid work event; fail-closed downstream
    return events


def find_run_folder(activation_uid: str) -> Path:
    """Locate the pipeline-run folder whose run records this activation. Fail-closed (raise)."""
    if not PIPELINE_RUNS.is_dir():
        raise ReleaseAuthorizationError("no pipeline-runs directory")
    matches = []
    for folder in PIPELINE_RUNS.iterdir():
        if not folder.is_dir():
            continue
        for ev in _read_run_events(folder):
            # Real runtime links the run to its activation via the event trace_id; keep the
            # activation_uid/activation fields as fallback for other shapes.
            if (ev.get("trace_id") == activation_uid
                    or ev.get("activation_uid") == activation_uid
                    or ev.get("activation") == activation_uid):
                matches.append(folder)
                break
    if not matches:
        raise ReleaseAuthorizationError(
            f"no pipeline-run found for activation {activation_uid!r} — "
            f"the release did not go through the pipeline (no key can exist)")
    # newest by mtime if more than one (re-runs/supersession)
    return max(matches, key=lambda f: f.stat().st_mtime)


def _read_run_state(run_folder: Path) -> dict:
    """Read run.state.json for run metadata. Returns {} if absent or malformed."""
    p = run_folder / "run.state.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _extract_run_uid(run_folder: Path) -> str:
    """Extract the pipeline_run_uid for this run.

    Primary source: run.state.json (pipeline_run_uid field).
    Fallback: parse the folder name — pattern dev-pipeline-<run_uid>-<date>.
    Returns empty string if neither resolves (key is still minted; fingerprint
    salt falls back to folder-name hash so it remains run-unique).
    """
    state = _read_run_state(run_folder)
    if state.get("pipeline_run_uid"):
        return str(state["pipeline_run_uid"])
    # Folder-name fallback: <type>-<run_uid>-<YYYY-MM-DD>
    parts = run_folder.name.split("-")
    # The folder format: e.g. dev-pipeline-bd21c40c-2026-07-04
    # run_uid is a 8-hex value — find it among parts
    for p in parts:
        if re.fullmatch(r"[0-9a-f]{8}", p):
            return p
    # Last resort: hash the folder name for uniqueness
    return hashlib.sha256(run_folder.name.encode()).hexdigest()[:8]


def _get_or_create_run_nonce(run_folder: Path) -> str:
    """Read this run folder's bootstrap secret nonce, minting it if this is the first touch.

    S9 round-2 fix (f417a577). The nonce is os.urandom(16)-derived hex — not derivable from
    run_uid, work-shape, or any timestamp. It is stored in run.state.json's `run_nonce` field,
    written once (whichever call — pipeline-runtime bootstrap or this fallback — touches the
    folder first) and preserved verbatim thereafter (existing value is always returned as-is,
    never regenerated or rewritten). This function only ever ADDS the field if run.state.json
    exists without one, or creates a minimal run.state.json if the folder predates state
    tracking entirely (e.g. a lightweight test scratch run) — it never touches any other key
    in that file.
    """
    state_path = run_folder / "run.state.json"
    state = {}
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text())
        except Exception:
            state = {}
        nonce = state.get("run_nonce")
        if nonce:
            return str(nonce)
    nonce = os.urandom(16).hex()
    state["run_nonce"] = nonce
    run_folder.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2))
    return nonce


def _trigger_step_satisfied(step_id: str, events: list) -> bool:
    """True if step_id fired (step_completed) OR was legitimately skipped with authorization.

    d2f8a91c-class fix (Talos T28, 2026-07-10): a dev-spec with no doc-pipeline-class
    deliverable (e.g. mount-gate/409ef1cc and its 3 federation siblings, all test-only)
    legitimately skips DOC_TRIGGER_STEP via the engine's own skip_request -> skip_authorization
    -> step_skipped lifecycle (pipeline-runtime.py action_apply_skip/action_authorize_skip).
    The original cascade check only recognized step_completed, so a doc-less dev-spec could
    NEVER mint a key — caught live trying to close mount-gate's v1.84.1 ceremony.

    This does not weaken the gate: a step_skipped is only accepted if it carries
    disposition:'skip_with_authorization' AND its skip_authorization_span_id resolves to a
    real skip_authorization event with a non-empty authorized_by IN THIS RUN'S OWN EVENT
    RECORD. The authorizer's identity was already validated against a registered
    type:principal at write time by action_authorize_skip — this re-checks that the chain
    exists and is linked, not the authorizer's identity again (that trust boundary lives in
    the engine, not here). A step_skipped event with no matching skip_authorization (forged
    or absent) does not satisfy this and the gate still refuses.
    """
    if any(_step(e) == step_id and e.get("event") == "step_completed" for e in events):
        return True
    for sk in events:
        if _step(sk) != step_id or sk.get("event") != "step_skipped":
            continue
        data = sk.get("data") or {}
        if data.get("disposition") != "skip_with_authorization":
            continue
        auth_span = data.get("skip_authorization_span_id")
        if not auth_span:
            continue
        if any(e.get("event") == "skip_authorization" and e.get("span_id") == auth_span
               and (e.get("data") or {}).get("authorized_by")
               for e in events):
            return True
    return False


def compute_fingerprint(run_folder: Path, gate: str = GATE_PRODUCE,
                        event_limit: int = None) -> str:
    """SHA-256 over the run's ordered work record, salted with the run folder's OWN run_nonce.

    S9 round-2 (v1.80 addendum, f417a577): the nonce is ALWAYS read fresh from the run_folder
    argument's own run.state.json (via _get_or_create_run_nonce) — never accepted as a
    parameter, never trusted from a key being verified. This is the load-bearing property: a
    key minted for run B carries a fingerprint salted with B's nonce; verifying that key
    against run C recomputes the salt from C's own (independent) nonce, which the attacker
    cannot have forged into C because B's nonce never traveled anywhere outside B's folder
    (not in the key, not derivable from run_uid/work-shape/timestamps). Two independently
    built runs with byte-identical work records therefore produce DIFFERENT fingerprints.

    event_limit: if set, consider only the first N events (used by require_release_authorization
    to recompute the fingerprint at mint-time — events added after minting must not shift it).

    Requires the gate step to have completed AND the doc/test cascade to have fired — else
    the run never legitimately reached the gate and NO fingerprint is mintable (raise)."""
    events = _read_run_events(run_folder)
    if event_limit is not None:
        events = events[:event_limit]
    work = [e for e in events if e.get("event") in _WORK_EVENTS]

    # The run must have actually progressed (not an empty/bootstrap-only run). Minting
    # happens AT the produce gate, so we require progress + the cascade, not produce-already-
    # completed (which would be a chicken-and-egg at mint time).
    if not any(e.get("event") == "step_completed" for e in events):
        raise ReleaseAuthorizationError(
            "run has completed no steps — not eligible for a key (empty/bootstrap-only run)")

    # The doc/test pipeline cascade (dev-pipeline steps 4.5/4.6) MUST have fired — proven by a
    # step_completed for BOTH trigger-step UIDs, OR a legitimately-authorized skip for a
    # dev-spec that genuinely has no doc-class deliverable (see _trigger_step_satisfied). This
    # is the structural proof the release protocol was followed, not shortcut. (Verified
    # against real run.jsonl event shapes.)
    if not _trigger_step_satisfied(DOC_TRIGGER_STEP, events) or not _trigger_step_satisfied(TEST_TRIGGER_STEP, events):
        raise ReleaseAuthorizationError(
            "doc/test pipeline cascade (steps 4.5/4.6) did not fire (nor was legitimately "
            "skipped with authorization) in the run — the protocol was not followed; no key")

    canonical = "\n".join(f"{e.get('event')}|{_step(e)}|{_verdict(e)}" for e in work)
    # S9 round-2 salt: the run folder's own secret nonce, read fresh — see docstring.
    nonce = _get_or_create_run_nonce(run_folder)
    salt = f"run_nonce:{nonce}"
    return hashlib.sha256((salt + "\n" + canonical).encode("utf-8")).hexdigest()


def mint_key(activation_uid: str, gate: str = GATE_PRODUCE) -> dict:
    """Mint the key for a run that legitimately reached the gate. Runtime-only caller.

    S9 round-2 (f417a577): the fingerprint is bound to the run folder's own run_nonce
    (established here if this run predates state tracking / bootstrap hasn't run yet).
    The nonce itself is deliberately NOT stored in the key — see module docstring.
    run_uid/minted_at are still recorded in the key as metadata (round-1's identity check
    at verify time), but no longer participate in the fingerprint salt themselves.
    """
    run_folder = find_run_folder(activation_uid)
    run_uid = _extract_run_uid(run_folder)
    _get_or_create_run_nonce(run_folder)  # ensure bootstrap has happened before minting
    minted_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    fp = compute_fingerprint(run_folder, gate)
    events = _read_run_events(run_folder)
    key = {
        "activation_uid": activation_uid,
        "run_uid": run_uid,
        "gate": gate,
        "fingerprint": fp,
        "minted_at": minted_at,
        "minted_at_event": len(events),
        "minted_by": "pipeline-runtime",
    }
    (run_folder / KEY_FILENAME).write_text(json.dumps(key, indent=2))
    return key


def _has_human_signoff(run_folder: Path) -> bool:
    """Public-ship gate (5864c0b6, v1.80 post-S9): require an INDEPENDENT, REGISTERED signer.

    Round-3 adversarial re-verify (Argus, forge-proven) found this check accepted ANY
    well-shaped human_signoff event, with no check on who authored it — an executing agent
    could append a self-authored `{"event": "human_signoff", "data": {"verdict": "accepted"}}`
    line to its own run.jsonl and flip this gate. The runtime's `human:` criterion path
    (vault/tools/9e7003b1.py evaluate_criterion, lines ~694-731) already had the correct
    checks; this ports that same logic verbatim rather than inventing a new design:

      1. Trust ONLY the engine-stamped `ev.actor` as the signer — never a self-reported
         `data.signer_principal_uid` / `data.signed_by` field (that field is agent-writable;
         it is the forged-stamp exploit Vela V60 closed, 2026-06-07).
      2. Resolve the signer to a canonical principal via `_resolve_principal_uid` and require
         it be REGISTERED (non-None). A bare/unregistered actor label is rejected.
      3. Require the signer principal differ from every principal that executed a step in
         this run (resolved the same way) — an agent cannot sign off on its own run. Unlike
         the runtime's per-step `human:` criterion, this check is not scoped to one step (the
         release module has no single "subject" step), so "the run's executor" is the set of
         all step_completed actors across the whole run.
    """
    events = _read_run_events(run_folder)
    executor_principal_uids = set()
    for e in events:
        if e.get("event") == "step_completed":
            actor = e.get("actor")
            if not actor:
                continue
            puid = _resolve_principal_uid(actor, VAULT_ROOT)
            if puid:
                executor_principal_uids.add(puid)
    for e in events:
        if e.get("event") == "human_signoff" and _verdict(e) in ("accepted", "accepted_with_exceptions"):
            # (1) Trust ONLY ev.actor — never any self-reported field in data.
            signed_by = e.get("actor") or ""
            signer_principal_uid = _resolve_principal_uid(signed_by, VAULT_ROOT)
            # (2) Unregistered/bare signer — rejected (closes unregistered-label bypass).
            if signer_principal_uid is None:
                continue
            # (3) Signer must be independent of every executor of this run — same identity
            # as an executor is a self-signoff (two-label spoof) — rejected.
            if signer_principal_uid in executor_principal_uids:
                continue
            return True
    return False


def require_release_authorization(activation_uid: str, gate: str = GATE_PRODUCE,
                                  *, require_human_signoff: bool = False,
                                  version: str = None) -> dict:
    """The gate. Returns the key dict on success; raises ReleaseAuthorizationError otherwise.

    version: when supplied alongside require_human_signoff, also verifies CHANGELOG.md has
    a [version] entry and an [Unreleased] section above it (Metis G83 anti-drift gate, v1.74).

    Fail-closed: ANY failure (no activation, no run, no key, fingerprint mismatch, missing
    signoff, CHANGELOG drift, unexpected error) refuses. There is no override flag (dev-spec AC-5)."""
    try:
        if not activation_uid:
            raise ReleaseAuthorizationError("no --activation-uid supplied (no key, no run)")
        run_folder = find_run_folder(activation_uid)
        key_path = run_folder / KEY_FILENAME
        if not key_path.is_file():
            raise ReleaseAuthorizationError(
                f"no release-authorization key in {run_folder.name} — "
                f"the run never reached the produce-release-folder gate")
        try:
            key = json.loads(key_path.read_text())
        except Exception as e:
            raise ReleaseAuthorizationError(f"key file unreadable/malformed: {e}")
        stored = key.get("fingerprint")
        # Recompute at the event-count snapshot recorded when the key was minted. Events added
        # AFTER minting (e.g. the produce-release-folder step_completed appended by the
        # pipeline-runtime after the verification_command runs) must not shift the fingerprint.
        mint_event_count = key.get("minted_at_event")
        stored_run_uid = key.get("run_uid") or ""

        # Round-1 win (v1.80 re-build): the salt must be verified against the RUN FOLDER's
        # OWN identity, not the key's self-reported `run_uid` field. `run_folder` here was
        # already resolved from THIS call's activation_uid (i.e. the run actually being
        # verified) — its independently-derived identity is the source of truth the key's
        # claim must be checked against, not trusted at face value.
        expected_run_uid = _extract_run_uid(run_folder)
        if stored_run_uid != expected_run_uid:
            raise ReleaseAuthorizationError(
                f"key run_uid ({stored_run_uid!r}) does not match this run folder's own "
                f"identity ({expected_run_uid!r}) — key was minted for a different run "
                f"(copied or replayed key; refused)")

        # S9 round-2 fix (f417a577): recompute the fingerprint over THIS run folder's own
        # run_nonce, read fresh from its run.state.json — never over anything read from the
        # key. compute_fingerprint does this internally (it never accepts a nonce argument),
        # so there is no code path here that could accidentally trust the key's claim.
        live = compute_fingerprint(run_folder, gate, event_limit=mint_event_count)
        if not stored or stored != live:
            raise ReleaseAuthorizationError(
                "key fingerprint does not match the run's work record "
                "(forged, stale, tampered key, or a key minted for a different run's nonce)")
        if require_human_signoff and not _has_human_signoff(run_folder):
            raise ReleaseAuthorizationError(
                "public ship requires a human_signoff event in the run — none found "
                "(the human key was not turned)")
        if require_human_signoff and version:
            check_changelog(version)
        return key
    except ReleaseAuthorizationError:
        raise
    except Exception as e:  # fail-closed on anything unexpected
        raise ReleaseAuthorizationError(f"authorization check failed (fail-closed): {e}")


def _find_activation_for_dev_spec(dev_spec_uid: str, vault_files: Path) -> dict | None:
    """Reverse-lookup: the type:activation entry whose dev_spec_uid matches. None if absent."""
    for f in vault_files.glob("*.md"):
        fm = _load_fm(f)
        if fm and fm.get("type") == "activation" and fm.get("dev_spec_uid") == dev_spec_uid:
            return fm
    return None


def attested_build_authorization(target_version: str, vault_root: Path = None) -> dict:
    """A SEPARATE, narrower authorization source for the PRODUCE gate only (argus-a129
    attested-build-gate spec, Mike-approved 2026-07-11).

    An attested-close release (8c8ca68c-class: dev-pipeline activations closed by documented
    human attestation rather than the engine's own complete-workflow ceremony, because that
    ceremony was proven defective — see the 6 pipeline-runtime.py bugs found/fixed 2026-07-09/10)
    has NO pipeline-run to key against. require_release_authorization / mint_key will ALWAYS
    refuse it — correctly, since no run reached the produce gate. Without this function, an
    attested-close release can never be built, which is the root of the 11-version GitHub
    drift this was built to close (see design-brief cf84697d).

    Authorizes iff ALL hold (fail-closed, same posture as the pipeline-key path):
      1. a type:release entry exists with release_version == target_version, status=='shipped',
         signed_by=='mike-maziarz', released_by non-empty;
      2. EVERY dev-spec in that release's derived_from has a corresponding type:activation
         entry with close_method=='attested-manual' — this path is ONLY for genuine
         attested-closes; a normal release that merely lost its key must still be refused here
         (it should go through the pipeline-key path instead, or fail);
      3. each such activation's closure_reason cites a decision UID ("decision <uid>") that
         resolves to a vault entry with status=='accepted' and signed_by=='mike-maziarz'.

    SCOPE (the safety property that makes this sound — do not weaken): this authorizes ONLY
    the local produce-release-folder gate (extracting already-shipped, already-verified content
    into a build folder — harmless on its own). It must NEVER satisfy the outward SHIP/upload
    gate — require_release_authorization(require_human_signoff=True) is a completely separate
    function, untouched by this one, and stays the sole path to a public push. Even under the
    known L1 posture ceiling that signed_by is agent-writable (5864c0b6 posture A — disclosed,
    not pretended to be cryptographic), the worst case of a forged attestation is a LOCAL build
    folder; nothing reaches the public repo without a real human_signoff event plus Mike's own
    live push. The un-forgeable control remains the outward action, unchanged by this function.

    Returns {method, release_uid, version, authorized_by, attestation_uid} on success.
    """
    vroot = vault_root or VAULT_ROOT
    vfiles = vroot / "vault" / "files"
    target_norm = str(target_version).lstrip("vV")

    release_fm, release_uid = None, None
    for f in vfiles.glob("*.md"):
        fm = _load_fm(f)
        if not fm or fm.get("type") != "release":
            continue
        if str(fm.get("release_version") or "").lstrip("vV") == target_norm:
            release_fm, release_uid = fm, (fm.get("uid") or f.stem)
            break
    if release_fm is None:
        raise ReleaseAuthorizationError(
            f"no type:release entry found for version {target_version!r} — "
            f"attested-build requires a shipped release entry to authorize against")
    if release_fm.get("status") != "shipped":
        raise ReleaseAuthorizationError(
            f"release {release_uid} status={release_fm.get('status')!r}, expected 'shipped'")
    signed_by = release_fm.get("signed_by")
    if signed_by != "mike-maziarz":
        raise ReleaseAuthorizationError(
            f"release {release_uid} signed_by={signed_by!r}, expected 'mike-maziarz'")
    if not release_fm.get("released_by"):
        raise ReleaseAuthorizationError(f"release {release_uid} has no released_by")

    derived = release_fm.get("derived_from") or []
    if not derived:
        raise ReleaseAuthorizationError(
            f"release {release_uid} has no derived_from — nothing to attest against")

    attestation_uids = set()
    for dev_spec_uid in derived:
        act_fm = _find_activation_for_dev_spec(dev_spec_uid, vfiles)
        if act_fm is None:
            raise ReleaseAuthorizationError(
                f"no activation found for dev-spec {dev_spec_uid!r} — "
                f"cannot verify attested-close basis")
        if act_fm.get("close_method") != "attested-manual":
            raise ReleaseAuthorizationError(
                f"activation for dev-spec {dev_spec_uid!r} has close_method="
                f"{act_fm.get('close_method')!r}, not 'attested-manual' — attested-build only "
                f"authorizes genuine attested-closes; a normal release must use the pipeline-key path")
        closure_reason = str(act_fm.get("closure_reason") or "")
        m = re.search(r"decision\s+([0-9a-f]{8})", closure_reason, re.IGNORECASE)
        if not m:
            raise ReleaseAuthorizationError(
                f"activation for dev-spec {dev_spec_uid!r} closure_reason does not cite "
                f"a decision UID — cannot verify attestation basis")
        attestation_uids.add(m.group(1))

    for dec_uid in attestation_uids:
        dec_fm = _load_fm(vfiles / f"{dec_uid}.md")
        if dec_fm is None:
            raise ReleaseAuthorizationError(f"cited attestation decision {dec_uid!r} does not resolve")
        if dec_fm.get("status") != "accepted":
            raise ReleaseAuthorizationError(
                f"attestation decision {dec_uid} status={dec_fm.get('status')!r}, expected 'accepted'")
        if dec_fm.get("signed_by") != "mike-maziarz":
            raise ReleaseAuthorizationError(
                f"attestation decision {dec_uid} signed_by={dec_fm.get('signed_by')!r}, "
                f"expected 'mike-maziarz'")

    result = {
        "method": "attested-build",
        "release_uid": release_uid,
        "version": target_version,
        "authorized_by": signed_by,
        "attestation_uid": sorted(attestation_uids)[0] if len(attestation_uids) == 1 else sorted(attestation_uids),
    }

    try:
        from lib.event_emitter import auto_emit  # noqa: E402 (lazy: _TROPO_SCRIPTS already on sys.path)
        auto_emit(
            "tropo.release.attested_build_authorized",
            source="/tools/release-authorization",
            source_uid=ATTESTED_BUILD_SOURCE_UID,
            lifecycle="evergreen",
            data={
                **result,
                "scope_note": "authorizes the local produce gate only; never the outward ship gate",
            },
        )
    except Exception:
        pass  # audit emission is best-effort; never blocks authorization (auto_emit already swallows too)

    return result


def check_changelog(version: str, changelog_path: Path = None) -> None:
    """Verify CHANGELOG.md is up to date for the shipping version.

    Requires:
      1. ## [X.Y.Z] header (exact version match) — the entry was written.
      2. ## [Unreleased] header still present AND above the version entry — drift guard.

    Raises ReleaseAuthorizationError on any failure. This is the Metis G83 anti-drift gate
    (v1.74): a plain file-header promise failed twice; only a hard gate stops drift #3.
    """
    path = changelog_path or CHANGELOG_PATH
    if not path.is_file():
        raise ReleaseAuthorizationError(
            f"CHANGELOG.md not found at {path} — "
            f"create it (Keep a Changelog format) with a [Unreleased] section + "
            f"[{version}] entry before shipping"
        )
    content = path.read_text(encoding="utf-8")

    version_re = re.compile(rf"^##\s+\[{re.escape(version)}\]", re.MULTILINE | re.IGNORECASE)
    unreleased_re = re.compile(r"^##\s+\[Unreleased\]", re.MULTILINE | re.IGNORECASE)

    version_match = version_re.search(content)
    if not version_match:
        raise ReleaseAuthorizationError(
            f"CHANGELOG.md has no ## [{version}] entry — "
            f"promote [Unreleased] to [{version}] (with date + changes) and add a fresh "
            f"empty [Unreleased] section before shipping"
        )

    unreleased_match = unreleased_re.search(content)
    if not unreleased_match:
        raise ReleaseAuthorizationError(
            "CHANGELOG.md is missing [Unreleased] section — "
            "after promoting [Unreleased] → [version], add a fresh empty [Unreleased] "
            "header above it so the next cycle has somewhere to accumulate"
        )

    if unreleased_match.start() > version_match.start():
        raise ReleaseAuthorizationError(
            f"CHANGELOG.md structure wrong: [Unreleased] appears after [{version}] — "
            "it must be at the top of the version list"
        )


def _main(argv=None):
    ap = argparse.ArgumentParser(description="Pipeline Activation Key — mint/verify release authorization")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mint", help="mint the key (runtime use, at the produce-release-folder gate)")
    m.add_argument("--activation-uid", required=True)
    m.add_argument("--gate", default=GATE_PRODUCE)
    v = sub.add_parser("verify", help="check authorization (exit 0 = authorized, nonzero = refused)")
    v.add_argument("--activation-uid", required=True)
    v.add_argument("--gate", default=GATE_PRODUCE)
    v.add_argument("--require-human-signoff", action="store_true")
    v.add_argument("--version", default=None, help="shipping version; enables CHANGELOG check")
    cc = sub.add_parser("check-changelog", help="verify CHANGELOG.md has entry for version (exit 0 = ok)")
    cc.add_argument("--version", required=True)
    cc.add_argument("--changelog", default=None, help="path to CHANGELOG.md (default: studio root)")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "mint":
            key = mint_key(args.activation_uid, args.gate)
            print(json.dumps(key, indent=2)); return 0
        elif args.cmd == "check-changelog":
            cp = Path(args.changelog) if args.changelog else None
            check_changelog(args.version, cp)
            print(f"CHANGELOG OK — [{args.version}] entry found + [Unreleased] section present"); return 0
        else:
            require_release_authorization(args.activation_uid, args.gate,
                                          require_human_signoff=args.require_human_signoff,
                                          version=args.version)
            print("AUTHORIZED"); return 0
    except ReleaseAuthorizationError as e:
        print(f"REFUSED: {e}", file=sys.stderr); return 2


if __name__ == "__main__":
    sys.exit(_main())
