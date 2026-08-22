"""The separate site target: pinned identity, bounded diff, observed endpoint.

Dev-spec 2fae6312 (locked), implementation step 7.

WHY THE SITE IS ITS OWN PROBLEM. Everything else a release publishes lives in
one repository. The badge lives in another, `tropo-app`, and cross-repository
publication cannot be atomic. So the site gets its own pinned identity, its own
bounded diff, its own compare-and-swap push, and its own observed verification —
and when it fails, the release stays honestly open at
`release-live-site-pending` rather than reporting complete with a stale badge.

THREE REFUSALS THIS MODULE EXISTS FOR:

  * **The wrong repository.** The target is pinned. A redirected remote is
    refused rather than followed, because a redirect is the remote telling you
    the identity you pinned is not the identity you reached.
  * **A credential in the record.** Push URLs can carry tokens. Journals are
    committed substrate, so a URL is sanitised before it is recorded and a
    credential-bearing URL is refused outright — a leaked token is not
    something a later commit can take back.
  * **An unrelated path.** The prepared commit may touch the badge and, on
    first rollout only, the route. Anything else refuses. A release that can
    quietly carry an arbitrary site change is a release that can ship one.

WHAT IS AND IS NOT PROVEN AT THE END. When the provider cannot expose the
commit it deployed, endpoint equality is what can be observed and is all this
module claims. It does not manufacture a causal link between the pushed commit
and the bytes served.

The git and HTTP edges are injected, as in `release_saga` and
`release_completion`: this module decides, the caller acts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit

__all__ = [
    "SITE_REPO",
    "SITE_BRANCH",
    "SITE_REMOTE",
    "SITE_ENDPOINT",
    "SOURCE_MAP",
    "ENDPOINT_FIELDS",
    "ReleaseSiteError",
    "sanitize_remote_url",
    "assert_pinned_identity",
    "classify_diff",
    "decide_site_push",
    "verify_endpoint",
    "SiteVerdict",
]


class ReleaseSiteError(RuntimeError):
    """Misuse of this module. Never a publication verdict."""


#: Pinned target identity. Credentials never live here; the machine-local
#: remote supplies them and this is what gets compared and recorded.
SITE_REPO = "https://github.com/tropo-ai/tropo-app.git"
SITE_BRANCH = "main"
SITE_REMOTE = "app-deploy"
SITE_ENDPOINT = "https://tropo-ai.com/api/os-release"

#: Studio source -> site-repo target. The complete allowed surface.
SOURCE_MAP: Dict[str, str] = {
    "tropo-app/os-release.json": "os-release.json",
    "tropo-app/app/api/os-release/route.ts": "app/api/os-release/route.ts",
}

BADGE_TARGET = SOURCE_MAP["tropo-app/os-release.json"]
ROUTE_TARGET = SOURCE_MAP["tropo-app/app/api/os-release/route.ts"]

#: Exactly these, in the response. Not a subset, not a superset.
ENDPOINT_FIELDS: Tuple[str, ...] = ("version", "fileSize", "sizeBytes", "releasedAt")

REFUSAL_IDENTITY = "site-identity"
REFUSAL_CREDENTIAL = "credential-in-url"
REFUSAL_DIFF = "unrelated-path"
REFUSAL_CONFLICT = "site-ref-conflict"
REFUSAL_ENDPOINT = "site-endpoint"

PENDING_STATE = "release-live-site-pending"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class SiteVerdict:
    ok: bool
    action: str = ""
    refusal_class: Optional[str] = None
    detail: str = ""
    evidence: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.evidence is None:
            object.__setattr__(self, "evidence", {})

    @property
    def pending_state(self) -> Optional[str]:
        return None if self.ok else PENDING_STATE


def sanitize_remote_url(url: str) -> str:
    """A URL safe to write into committed substrate.

    Strips any userinfo component. Journals are committed, and a token written
    into one cannot be recalled by a later commit.
    """
    if not isinstance(url, str) or not url:
        raise ReleaseSiteError("a remote URL is required")
    parts = urlsplit(url)
    if not parts.hostname:
        # Not a URL we can reason about (an SSH shorthand, a local path). Return
        # it unchanged rather than pretending to have sanitised it.
        return url
    netloc = parts.hostname
    if parts.port:
        netloc = "%s:%d" % (netloc, parts.port)
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _carries_credential(url: str) -> bool:
    parts = urlsplit(url)
    return bool(parts.username or parts.password)


def assert_pinned_identity(
    observed_url: str,
    *,
    observed_branch: str = SITE_BRANCH,
    redirected_to: Optional[str] = None,
) -> SiteVerdict:
    """The remote must be the repository we pinned, reached without redirect."""
    if _carries_credential(observed_url):
        return SiteVerdict(
            False,
            refusal_class=REFUSAL_CREDENTIAL,
            detail=(
                "the observed remote URL carries a credential; it is refused "
                "rather than recorded, because a journal is committed substrate"
            ),
            evidence={"observed_url": sanitize_remote_url(observed_url)},
        )
    if redirected_to:
        return SiteVerdict(
            False,
            refusal_class=REFUSAL_IDENTITY,
            detail=(
                "the pinned repository redirected to %s; a redirect is the remote "
                "saying the identity reached is not the identity pinned"
                % sanitize_remote_url(redirected_to)
            ),
            evidence={"expected": SITE_REPO, "redirected_to": sanitize_remote_url(redirected_to)},
        )
    if sanitize_remote_url(observed_url) != SITE_REPO:
        return SiteVerdict(
            False,
            refusal_class=REFUSAL_IDENTITY,
            detail="observed remote %s is not the pinned %s"
            % (sanitize_remote_url(observed_url), SITE_REPO),
            evidence={"expected": SITE_REPO, "observed": sanitize_remote_url(observed_url)},
        )
    if observed_branch != SITE_BRANCH:
        return SiteVerdict(
            False,
            refusal_class=REFUSAL_IDENTITY,
            detail="branch %r is not the pinned %r" % (observed_branch, SITE_BRANCH),
        )
    return SiteVerdict(True, action="identity-verified",
                       evidence={"repo": SITE_REPO, "branch": SITE_BRANCH})


def classify_diff(
    changed_paths: Sequence[str], *, route_exists: bool
) -> SiteVerdict:
    """The prepared commit may touch the badge, and the route once.

    `route_exists` is observed in the fetched site checkout, not asserted by
    the caller's intent. After first rollout the route is unchanged, so a
    commit that touches it again is carrying something the release did not
    declare.
    """
    paths = list(changed_paths)
    if not paths:
        return SiteVerdict(
            False,
            refusal_class=REFUSAL_DIFF,
            detail="the prepared commit changes nothing; there is no badge to publish",
        )

    allowed = {BADGE_TARGET} if route_exists else {BADGE_TARGET, ROUTE_TARGET}
    unrelated = sorted(set(paths) - allowed)
    if unrelated:
        return SiteVerdict(
            False,
            refusal_class=REFUSAL_DIFF,
            detail=(
                "the prepared commit touches %s, which the release did not "
                "declare%s"
                % (
                    ", ".join(unrelated),
                    " (the route is unchanged after first rollout)"
                    if route_exists and ROUTE_TARGET in unrelated
                    else "",
                )
            ),
            evidence={"unrelated": unrelated, "allowed": sorted(allowed)},
        )
    if BADGE_TARGET not in paths:
        return SiteVerdict(
            False,
            refusal_class=REFUSAL_DIFF,
            detail="the prepared commit does not update %s" % BADGE_TARGET,
        )
    return SiteVerdict(
        True,
        action="first-rollout" if not route_exists else "badge-only",
        evidence={"changed": sorted(paths)},
    )


def decide_site_push(
    *, remote_sha: str, expected_parent: str, prepared_commit: str
) -> SiteVerdict:
    """Fast-forward compare-and-swap, or refuse. Never force.

    Three outcomes and no fourth: the remote is where we left it and the push
    goes; the remote is already the prepared commit and the push is a no-op
    (a lost acknowledgement, not a problem); or the remote is somewhere else
    entirely, which is a conflict. Forcing would make the third case look like
    the first by destroying whatever the remote had.
    """
    for name, value in (
        ("remote_sha", remote_sha),
        ("expected_parent", expected_parent),
        ("prepared_commit", prepared_commit),
    ):
        if not _SHA_RE.match(str(value or "")):
            raise ReleaseSiteError("%s must be a 40-hex commit id, got %r" % (name, value))

    if remote_sha == prepared_commit:
        return SiteVerdict(
            True, action="no-op",
            detail="the remote already carries the prepared commit",
            evidence={"site_commit": prepared_commit},
        )
    if remote_sha == expected_parent:
        return SiteVerdict(
            True, action="fast-forward-cas",
            detail="the remote is at the expected parent; CAS push is safe",
            evidence={"expected_parent": expected_parent, "site_commit": prepared_commit},
        )
    return SiteVerdict(
        False,
        refusal_class=REFUSAL_CONFLICT,
        detail=(
            "the site remote moved to %s, which is neither the expected parent "
            "%s nor the prepared commit. Someone else pushed; forcing would "
            "delete their work" % (remote_sha[:12], expected_parent[:12])
        ),
        evidence={"remote_sha": remote_sha, "expected_parent": expected_parent},
    )


def verify_endpoint(
    response: Mapping[str, Any],
    *,
    expected_version: str,
    expected_size_bytes: int,
) -> SiteVerdict:
    """The served badge must be this release's badge, freshly served.

    `response` is an observation: status, final URL, content type, headers and
    parsed body as the client actually received them.
    """
    status = response.get("status")
    if status != 200:
        return SiteVerdict(False, refusal_class=REFUSAL_ENDPOINT,
                           detail="endpoint returned HTTP %r" % (status,))

    final_url = str(response.get("final_url") or "")
    if final_url and final_url.split("?")[0] != SITE_ENDPOINT:
        return SiteVerdict(
            False, refusal_class=REFUSAL_ENDPOINT,
            detail="endpoint redirected to %s; a redirected badge is not the "
                   "badge whose freshness was verified" % final_url,
        )

    content_type = str(response.get("content_type") or "")
    if "application/json" not in content_type:
        return SiteVerdict(False, refusal_class=REFUSAL_ENDPOINT,
                           detail="content type %r is not JSON" % content_type)

    cache_control = str(
        (response.get("headers") or {}).get("cache-control", "")
    ).lower()
    if cache_control and not ("no-store" in cache_control or "no-cache" in cache_control):
        return SiteVerdict(
            False, refusal_class=REFUSAL_ENDPOINT,
            detail="cache-control %r permits a stale badge to be served" % cache_control,
        )

    body = response.get("body")
    if not isinstance(body, dict):
        return SiteVerdict(False, refusal_class=REFUSAL_ENDPOINT,
                           detail="response body is not a JSON object")

    observed_fields = set(body)
    expected_fields = set(ENDPOINT_FIELDS)
    if observed_fields != expected_fields:
        missing = sorted(expected_fields - observed_fields)
        extra = sorted(observed_fields - expected_fields)
        return SiteVerdict(
            False, refusal_class=REFUSAL_ENDPOINT,
            detail="schema mismatch — missing %s, unexpected %s" % (missing, extra),
            evidence={"missing": missing, "extra": extra},
        )

    if str(body.get("version")) != str(expected_version):
        return SiteVerdict(
            False, refusal_class=REFUSAL_ENDPOINT,
            detail="served version %r is not this release's %r; the badge is stale"
                   % (body.get("version"), expected_version),
        )
    if int(body.get("sizeBytes", -1)) != int(expected_size_bytes):
        return SiteVerdict(
            False, refusal_class=REFUSAL_ENDPOINT,
            detail="served sizeBytes %r does not match the published package %r"
                   % (body.get("sizeBytes"), expected_size_bytes),
        )

    return SiteVerdict(
        True, action="endpoint-verified",
        detail="observed endpoint equality",
        evidence={
            "endpoint": SITE_ENDPOINT,
            "version": body.get("version"),
            "sizeBytes": body.get("sizeBytes"),
            "response_sha256": response.get("body_sha256"),
            "observed_at": response.get("observed_at"),
        },
    )
