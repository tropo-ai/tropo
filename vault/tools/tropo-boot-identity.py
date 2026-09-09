#!/usr/bin/env python3
"""tropo-boot-identity.py -- resolve an agent's soul at Step 2.0, and let a
reader who is NOT that agent check afterwards whether the step actually ran.

Two defects, one disease (v1.95 external test, f015ab052267):

  1. A customer's own agent never loads its soul. The shipped
     `create-executive-agent` skill writes a THREE-FILE agent whose activation
     pointer declares `charter_file:`. The canonical playbook resolved identity
     two ways, neither of which reads a charter, so Step 2.0 was never entered
     and the Group 2 milestone fired green over the hole.

  2. The first-boot orientation walk has never fired for a human being. The
     wiring is correct and reads one fact; the last inch was a sentence in
     prose addressed to the one agent who could skip it unobserved.

Both are the same shape: an obligation carried as a sentence to an agent, with
no witness but that agent. Darin, from the same test, verbatim:

    "I did not experience skipping five of six reads as a failure -- I
     experienced it as a competent, efficient boot... Do not build any part of
     this system on an agent's self-report of its own compliance."

So nothing here asks an agent what it did. `soul` computes the disposition from
files on disk and records it. `orientation` reads one flag and hands back the
line to fold. `audit` reads the run journal as a third party and says whether
the milestone fired over an unaccounted step.

WARN-SAFE, and this is a hard contract, not a preference:

  * every verb exits 0 on every outcome including "not resolved", so this tool
    can never stop a boot, a build, or the founder;
  * a soul that will not resolve is a LOUD NAMED finding the agent relays and
    then CONTINUES past -- a missing soul is better than a halted activation;
  * an uncommissioned placeholder agent gets one neutral line and no alarm,
    because a red marker that fires on healthy states teaches a founder to stop
    reading red markers;
  * `orientation` fires at most once per install and never repeats.

The only nonzero exit is argparse's own usage error, which an agent can hit and
a human cannot.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Optional

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import boot_identity as bi  # noqa: E402
from lib import po_first_boot as pfb  # noqa: E402
from lib import run_journal as rj  # noqa: E402

SOUL_STEP = "2.0"

# Fixed strings. Fixed so they are greppable across sessions and legible to a
# founder who has never opened the playbook, and so the two boot surfaces can
# never word the same event two ways.
BANNER_LOADED = "soul: LOADED — shape {shape} from {source} ({section})"
BANNER_PLACEHOLDER = (
    "soul: LOADED WITH UNFILLED TEMPLATE VALUES — shape {shape} from {source} ({section})"
)
BANNER_NOT_RESOLVED = (
    "⛔ SOUL NOT LOADED — Step 2.0 cannot resolve an identity for agent `{agent}`."
)
BANNER_NOT_COMMISSIONED = (
    "soul: not applicable — `{agent}` is an uncommissioned placeholder "
    "(its activation file says so); no identity substrate exists yet, by design."
)
BANNER_NO_ACTIVATION = (
    "⛔ SOUL NOT LOADED — no activation file for agent `{agent}`."
)

RELAY = (
    "I am booting WITHOUT my identity. Put this line in your startup signal FIRST, above the\n"
    "identity confirmation, say it to the person who launched you, and CONTINUE the boot.\n"
    "A missing soul is a loud finding, never a halt."
)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_root(raw: Optional[str]) -> Path:
    return Path(raw or ".").resolve()


# ---------------------------------------------------------------------------
# soul
# ---------------------------------------------------------------------------


def cmd_soul(args: argparse.Namespace) -> int:
    root = _resolve_root(args.vault_root)
    res = bi.resolve_soul(root, args.agent)

    if args.json:
        payload = res.to_dict()
        payload["soul_text"] = res.text
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _print_soul_human(res, args)

    # Record the disposition. The row is what makes a skipped Step 2.0 sayable
    # later by somebody other than the agent; a journal that cannot be written
    # is a note, never a stop.
    if not args.no_journal:
        journal = (
            Path(args.run_journal).resolve()
            if args.run_journal
            else rj.find_latest_run_journal(root, args.agent)
        )
        if journal is None:
            if not args.json:
                print(
                    "\n[note] no run journal found under playbook-runs/agent-activation-{}-* — "
                    "disposition not recorded. Pass --run-journal to name one.".format(
                        args.agent
                    )
                )
        else:
            # `tried` rides along even on a clean resolve: the row has to be
            # able to say WHY a shape did not match, or the audit can only
            # report that something went wrong, never what.
            detail = res.to_dict()
            problem = rj.append_step_disposition(
                journal, SOUL_STEP, res.status, detail, _now()
            )
            if problem and not args.json:
                print(
                    "\n[note] could not append the Step 2.0 disposition to {} ({}). "
                    "Boot continues; say so in your startup signal.".format(
                        journal, problem
                    )
                )
            elif not args.json:
                print("\n[recorded] Step 2.0 disposition `{}` → {}".format(res.status, journal))

    # Warn-safe by contract: always 0.
    return 0


def _print_soul_human(res: bi.Resolution, args: argparse.Namespace) -> None:
    if res.status == bi.STATUS_NOT_COMMISSIONED:
        print(BANNER_NOT_COMMISSIONED.format(agent=res.agent))
        return

    if res.status in (bi.STATUS_NOT_RESOLVED, bi.STATUS_NO_ACTIVATION):
        banner = (
            BANNER_NO_ACTIVATION
            if res.status == bi.STATUS_NO_ACTIVATION
            else BANNER_NOT_RESOLVED
        )
        print(banner.format(agent=res.agent))
        print("   Shapes tried, in order, and why each failed:")
        for shape, why in res.tried:
            print("     {}: {}".format(shape, why))
        print(
            "   A soul resolves through any ONE of: `agent_uid:` (Shape A), `charter_file:` "
            "(Shape C),\n   `charter_uid:` (Shape D), or a Tier-3 `soul_letter:` (Shape B), "
            "declared in\n   {}.".format(res.activation_file or "the agent's activation file")
        )
        print(RELAY)
        return

    banner = (
        BANNER_PLACEHOLDER if res.status == bi.STATUS_PLACEHOLDER else BANNER_LOADED
    )
    print(
        banner.format(
            shape=res.shape, source=res.source, section=res.section or "—"
        )
    )
    if res.placeholders:
        print(
            "[warn] unfilled template values still in this identity: {}\n"
            "       You are booting with a template where your identity belongs. Name it in your\n"
            "       startup signal and ask the founder to fill it. This is a warning; continue.".format(
                ", ".join(res.placeholders)
            )
        )
    if not args.terse:
        print("")
        print(res.text)


# ---------------------------------------------------------------------------
# orientation
# ---------------------------------------------------------------------------


def cmd_orientation(args: argparse.Namespace) -> int:
    root = _resolve_root(args.vault_root)
    state = pfb.orientation_state(root)

    if args.json:
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return 0

    if not state["agent_fold_armed"]:
        # Silence when clean. A tour already offered, by either surface, says
        # nothing at all -- ever.
        return 0

    print(pfb.AGENT_OFFER_LINE)
    if not args.record:
        print(
            "[note] not recorded (pass --record to mark this surfaced; without it the "
            "offer stays armed)."
        )
        return 0
    try:
        flag = pfb.mark_agent_offer_surfaced(root)
        n = pfb.agent_offer_handoffs(root)
        # Says what this tool actually knows: it printed a line. Whether the
        # line reached a human is not observable from here (F1, 2026-09-07).
        print(
            "[recorded] tour offer HANDED to an agent ({} of {} for this install) → {}\n"
            "[note] handed is not seen. Fold the line above into your startup signal; "
            "if you drop it, the offer stays armed rather than being lost.".format(
                n, pfb.AGENT_OFFER_HANDOFF_CEILING, flag
            )
        )
    except OSError as exc:
        print(
            "[note] could not write {} ({}). Fold the line anyway; it may be offered "
            "again on a later boot.".format(pfb.AGENT_OFFER_FLAG_REL, exc)
        )
    return 0


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


def cmd_audit(args: argparse.Namespace) -> int:
    root = _resolve_root(args.vault_root)
    journal = (
        Path(args.run_journal).resolve()
        if args.run_journal
        else (rj.find_latest_run_journal(root, args.agent) if args.agent else None)
    )

    out = {"orientation": pfb.orientation_state(root)}
    if journal is not None:
        result = rj.audit(journal)
        out["run_journal"] = {
            "journal": result.journal,
            "milestones": result.milestones,
            "accounted": result.accounted,
            "unaccounted": result.unaccounted,
            "findings": result.findings,
            "clean": result.clean,
        }

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    print("orientation: {}".format(out["orientation"]["summary"]))
    if out["orientation"]["agent_offer_surfaced"] and not out["orientation"]["walk_offered"]:
        print(
            "  ↳ a concierge boot's first-boot offer did not reach the walk on this "
            "install; the line was handed to an agent {} time(s) instead. Handed is not "
            "seen -- no record here proves a human read it.".format(
                out["orientation"].get("agent_offer_handoffs", 0)
            )
        )
    if journal is None:
        print("run journal: none named and none discovered — nothing to audit.")
        return 0
    rjr = out["run_journal"]
    print("run journal: {}".format(rjr["journal"]))
    for line in rjr["accounted"]:
        print("  ok        {}".format(line))
    for line in rjr["findings"]:
        print("  UNACCOUNTED  {}".format(line))
    if rjr["clean"] and not rjr["findings"]:
        print("  every milestone that is accountable for a step has that step's disposition.")
    return 0


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tropo-boot-identity.py",
        description=(
            "Resolve an agent's soul from files on disk (Step 2.0), surface the "
            "first-boot orientation offer, and audit a run journal for steps that "
            "left no evidence. Never exits nonzero on a finding."
        ),
    )
    p.add_argument("--vault-root", default=".", help="Studio root (default: .)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("soul", help="resolve and print an agent's soul")
    s.add_argument("--agent", required=True, help="agent slug")
    s.add_argument("--json", action="store_true")
    s.add_argument(
        "--terse", action="store_true", help="disposition line only, no soul payload"
    )
    s.add_argument("--run-journal", help="run.jsonl to record the disposition into")
    s.add_argument(
        "--no-journal", action="store_true", help="resolve only; record nothing"
    )
    s.set_defaults(func=cmd_soul)

    o = sub.add_parser(
        "orientation", help="the one-line first-boot tour offer, or silence"
    )
    o.add_argument("--json", action="store_true")
    o.add_argument(
        "--record",
        action="store_true",
        help="mark the offer surfaced so it fires at most once per install",
    )
    o.set_defaults(func=cmd_orientation)

    a = sub.add_parser(
        "audit", help="read the boot record as somebody who did not write it"
    )
    a.add_argument("--agent", help="agent slug, to discover its newest run journal")
    a.add_argument("--run-journal", help="explicit run.jsonl to audit")
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_audit)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # pragma: no cover - warn-safe floor
        # Even an unexpected crash must not become a refusal. Name it and exit 0.
        print(
            "[warn] tropo-boot-identity.py hit an unexpected error and is reporting "
            "nothing rather than blocking you: {}: {}".format(type(exc).__name__, exc)
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
