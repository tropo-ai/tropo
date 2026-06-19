#!/usr/bin/env python3
"""
---
uid: 2490e8ad
name: crew-activation-board
type: tool
title: "crew-activation-board — who has unread work waiting, so the principal knows whom to activate"
description: "Renders boards/crew/activation-board.html + a terminal summary: per crew agent, the unanswered reply_required items addressed to them (unbounded answered-state scan via check-events 2471edc0 logic), their last outbound activity, and the waiting-since age of their oldest live item. Born from Mike-A109's pain 2026-06-11: 'i often have to activate agents and have them check. they're not all on active loops. who are you waiting on?' — the principal is the activation surface, so the substrate should tell him where activation is needed instead of him asking. Composes with the read-receipts design (69edec91): when receipts land, this board upgrades from unanswered-state to true unread-state. Static render = snapshot; rerun to refresh (OP-12: the authoring agent keeps it fresh)."
status: active
state: active
owner: argus
domain: "crew coordination — principal-facing activation surface"
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/2490e8ad.py"
script_path: vault/tools/2490e8ad.py
spawnable_by:
  - all-executives
created: 2026-06-11
created_by: argus-a109
governed_by: 8dd772a0
member_of:
  - "b7649a1c"   # v1.69 root (session artifact; standing tool thereafter)
refs:
  - "2471edc0"   # check-events — the scan logic this consumes
  - "69edec91"   # read-receipts design — the upgrade path
schema_version: 2
extraction_scope: argo-reference
tags: [tool, crew, activation-board, principal-surface, unanswered-state, op-12]
---
"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
CHECK_EVENTS = VAULT_ROOT / "vault" / "tools" / "2471edc0.py"
BOARD = VAULT_ROOT / "boards" / "crew" / "activation-board.html"
CREW = ["vela", "metis", "orpheus", "cosmo", "talos", "argus"]
TODAY = date.today().isoformat()


def scan(agent: str) -> dict:
    out = subprocess.run(
        [sys.executable, str(CHECK_EVENTS), "--as", agent],
        capture_output=True, text=True, cwd=VAULT_ROOT,
    ).stdout
    items, in_unanswered = [], False
    for line in out.splitlines():
        if "UNANSWERED" in line:
            in_unanswered = True
            continue
        if in_unanswered and line.strip().startswith("⚠"):
            items.append(line.strip().lstrip("⚠").strip())
    # pair id-lines with headline-lines
    paired = []
    for i in range(0, len(items) - 1, 2):
        paired.append((items[i], items[i + 1]))
    return {"agent": agent, "count": len(paired), "items": paired}


def main() -> int:
    rows = [scan(a) for a in CREW]
    print(f"=== Crew Activation Board — {TODAY} ===")
    html_rows = []
    for r in rows:
        live = [(h, b) for h, b in r["items"] if "2026-06-1" in h]  # June 10+ = current-era
        hist = r["count"] - len(live)
        flag = "🔴 NEEDS ACTIVATION" if live else ("🟡 historical debt only" if hist else "🟢 clear")
        print(f"{r['agent']:>10}: {len(live)} live / {hist} historical — {flag}")
        for h, b in live:
            print(f"            • {h[:110]}")
            print(f"              {b[:110]}")
        items_html = "".join(
            f"<div class='it {'live' if (h_b in live) else 'hist'}'><b>{h_b[0][:130]}</b><span>{h_b[1][:160]}</span></div>"
            for h_b in r["items"][:8]
        )
        html_rows.append(
            f"<div class='card'><h2>{r['agent']} <em>{flag}</em></h2>"
            f"<div class='meta'>{len(live)} live · {hist} historical-debt (pre-correlation era; one-time ack-sweep clears)</div>{items_html}</div>"
        )
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    BOARD.write_text(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Crew Activation Board — {TODAY}</title><style>
body{{font-family:-apple-system,sans-serif;background:#0f1419;color:#e6e1d7;padding:28px}}
h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#8a9199;font-size:12px;margin-bottom:20px}}
.card{{background:#171d24;border-radius:10px;padding:12px 16px;margin-bottom:12px}}
.card h2{{font-size:15px;margin:0 0 2px}} .card h2 em{{font-size:11px;font-style:normal;color:#dcdcaa;margin-left:8px}}
.meta{{font-size:11px;color:#8a9199;margin-bottom:8px}}
.it{{background:#1f2730;border-radius:6px;padding:6px 9px;margin-bottom:5px;font-size:11.5px;border-left:3px solid #555}}
.it.live{{border-left-color:#e8654f}} .it b{{display:block}} .it span{{color:#9aa4ad}}
</style></head><body>
<h1>Crew Activation Board</h1>
<div class="sub">Who has unread work waiting — rendered {TODAY} by crew-activation-board (2490e8ad). 🔴 = a live item is waiting on this agent's next activation. Rerun: <code>python3 vault/tools/2490e8ad.py</code>. Upgrades to true read-state when receipts (69edec91) land.</div>
{''.join(html_rows)}
</body></html>""", encoding="utf-8")
    print(f"\nBoard rendered: {BOARD.relative_to(VAULT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
