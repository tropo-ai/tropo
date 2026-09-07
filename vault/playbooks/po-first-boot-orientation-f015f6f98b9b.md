---
uid: f015f6f98b9b
type: playbook
title: Po's First-Boot Orientation
version: '1.1'
status: draft
owner: argus
readers:
  - agent
scope: single-session
estimated_duration: 5 minutes
trigger:
  - first-boot-automatic
  - on-demand-request
domain: onboarding
governed_by: e7b3c509
spec: f01564310146
calls:
  - vault/tools/tropo-render-studio-map.py
author:
  name: Talos
  role: Lead Engineering Swarm
created: '2026-09-02'
created_by: talos-t59
modified: '2026-09-03'
modified_by: argus-a168
supersedes:
  - '396274c5'   # welcome.playbook (argus-a36, 2026-04-26) — deprecated v1.17.0
  - '57a87005'   # tour-tropo.playbook (argus-a31, 2026-04-21) — deprecated v1.17.0
schema_version: 2
extraction_scope: ship
tags:
  - orientation
  - po
  - first-boot
  - onboarding
subsystem_hub:
  - 76bab75f
---

# Po's First-Boot Orientation

> **How this works.** The AI reading this playbook is walking a new user through their Studio for
> the first time — it renders the map, shows four real artifacts, and narrates one line per stop.
> **You don't need to read past this line** — your AI does. Skim if you're curious.

*Supersedes Po's prior orientation — `welcome.playbook` (`396274c5`) and `tour-tropo.playbook`
(`57a87005`), both deprecated at v1.17.0 to `99-recycle/v1.17.0-deprecated-concierge-paths-2026-05-10/`.
Mike, 2026-09-03: "Po has functioned with a proper orientation, but it needed updating." This walk
UPDATES that orientation; it does not stand beside a gap. It re-enters the concierge routing table
(`.tropo/concierge/activate.md` §1.3) as the one successor, exactly as the v1.43 note promised.*

*Mandated, escapable, re-runnable. Fires once on first boot without being asked. One gesture skips
it. A per-install flag prevents re-fire, but the walk itself never goes away — ask Po for the tour
any time and this same playbook runs in full. This is Po's own content and render; the trigger and
flag check live in [`.tropo/concierge/activate.md`](../../.tropo/concierge/activate.md) (kernel
surface, Argus's lane) — this file is what she says and shows once it fires.*

---

## Intent

A person who has never seen a Studio opens one and is shown a visual map of it, rendered from that
studio's own canonical Map — then walked through four things on real, open-able artifacts: the
vault, work management and capsules, the agent lifecycle, and the moment-index skim. They can leave
in one gesture and come back for it three days later. Mike's requirement, verbatim: *"I would like
a little more forced orientation, but somehow easy to escape from... upon welcome, I would love
for the user to be presented with a visual HTML map of the studio."*

The walk **shows; it does not explain.** Each concept lands on one real shipped artifact — a
governed record with its frontmatter, a capsule, an activation playbook — never an abstraction
described in prose. Show the pattern, name it, move on.

---

## Rules

- The map ships IN the box, rendered at build time from the box's own index by the box's own
  renderer (`tropo-build-release.py` Step 9b2, v1.95 Spine A AC8 — Mike: *"I want it shipped. If we
  ship it with a release, it should be clean."*). It is derived, never copied from another Studio:
  it carries no other Studio's counts or fingerprint. At first boot you VERIFY it, you do not
  regenerate it blind: run `python3 vault/tools/tropo-render-studio-map.py --check-stale --vault-path .`;
  FRESH means show it; STALE (this Studio's index has moved since the build — genesis at Po's
  greeting adds rows) means re-render with `python3 vault/tools/tropo-render-studio-map.py --vault-path .`
  and then show it. *(Until v1.95 this rule said the render must never be pre-shipped; Mike
  reversed it at the v1.95 walk, 2026-09-05.)*
- The escape MUST cost exactly ONE input. Do not ask a confirming follow-up before honoring it —
  "skip" or "not now" or any clear decline ends the walk immediately.
- The flag ([`.tropo/flags/po-first-boot-orientation-offered.flag`](../../.tropo/flags/)) MUST be
  written whichever way the walk ends — completed or skipped. It gates the AUTOMATIC first-boot
  fire ONLY. It MUST NOT be checked before an on-demand request; "give me the tour" always runs
  this playbook in full regardless of the flag's presence.
- Every artifact this playbook names MUST actually exist in the box under the path given here. If
  you find one missing, do not silently drop that step — surface it and skip only that stop, naming
  what's missing, so the gap is visible rather than papered over.
- All FOUR concepts (vault, work management + capsules, agent lifecycle, moment-index skim) MUST be
  shown. Do not drop one to save time — an abbreviated walk that silently drops a concept is the
  exact failure this playbook exists to prevent.
- The agent-lifecycle stop MUST show a lifecycle ARTIFACT (the activation playbook, a lifecycle
  tool, or an agent capsule) — NEVER a concrete agent entry. A fresh box ships no agent identity by
  design; pointing at one would either fail on an empty box or contradict that design on a
  populated one.

---

## Steps

1. **Verify the shipped map, then open it.** *Owner: agent. Deadline: within 10 seconds.*
   `boards/po/studio-map.html` ships in the box (Step 9b2). Run
   `python3 vault/tools/tropo-render-studio-map.py --check-stale --vault-path .`; on STALE, re-render
   with `python3 vault/tools/tropo-render-studio-map.py --vault-path .` (from `docs/tropo-studio-map.md`,
   the canonical Studio Map, with `boards/_shared/board.css` for style only). Then hand the user a
   **clickable link** to the file — a markdown hyperlink the harness opens on a click; where no link
   renders, the **absolute path** they can paste; **never a shell command** (Mike-ruled 2026-09-05,
   reversing the `open <path>` instruction that stood here). Say:

   > "Here's a visual map of your Studio — rendered fresh from its own canonical map, so it's
   > accurate to exactly what's in this install. I'll walk you through four things on it, or you
   > can skip straight to working. Want the walk, or skip?"

   This is the one-gesture escape point. A clear decline of any kind ends the walk here — go to
   Step 6.

2. **The vault.** *Owner: agent. Deadline: within 30 seconds.*
   Open **this Studio's own vault-entity record** — genesis minted it for this install at the first
   index build, under a composite uid that is different in every studio, so it cannot be named here
   by path. Find it in two moves that work in any studio: the `01-studio-inbox` project record
   (`slug: 01-studio-inbox` in `vault/00-index.jsonl`) carries `owner: <uid>`; that uid is the
   vault-entity, at `vault/files/<uid>.md` (`type: entity`, `subtype: vault-entity`, titled "Your
   Tropo Vault"). Open it with its index row beside it. If — and only if — no such record exists
   (a studio that has not yet been through genesis), open
   [`vault/files/eca73d77.md`](../../vault/files/eca73d77.md), the L1 canonical entry, instead.
   Show the frontmatter (a `uid:`, a `type:`, a `status:`) and say, in plain language:

   > "This is a governed record — every real piece of work in your Studio looks like this. This
   > one came into being for *your* Studio a minute ago; you just watched its uid get minted. The
   > `uid` is its permanent address; rename the file and the link still resolves. That's the vault:
   > every typed artifact lives at `vault/files/`, one home, always findable by its uid."

   *(Design ruling §2, reconciled 2026-09-03 by argus-a168: the ruled artifact is the studio's own
   vault-entity. AC4 judges cited paths against the EXTRACTED box, which is pre-genesis, so the
   entity cannot be a cited path — it is reached by the lookup above, and the shipped L1 entry
   remains the cited fallback. Recorded on the spec.)*

3. **Work management and capsules.** *Owner: agent. Deadline: within 30 seconds.*
   Open **this Studio's own `01-studio-inbox` project record** — the same genesis-minted record you
   used as the signpost in Step 2 (`slug: 01-studio-inbox`; `vault/files/<uid>.md`, `type: project`)
   — against [`vault/capsules/tropo-project.capsule.md`](../../vault/capsules/tropo-project.capsule.md),
   the capsule that governs every project. Record beside contract: here is a thing, here is what
   says what it must be. For the wider picture, [`vault/files/2d4f8c91.md`](../../vault/files/2d4f8c91.md)
   — How Tropo Work Works — is the read. Say:

   > "Tasks, projects, decisions, and pipelines are the work-management layer — plain markdown
   > files your agents track with you. This inbox is the first place your work will land. Every
   > type has a capsule like this one governing what a valid project must contain, so 'is this
   > well-formed?' has a real answer, not a vibe."

   *(Design ruling §2: the pair is the inbox project + the PROJECT capsule, replacing the task
   capsule. The inbox is reached by lookup for the same reason as Step 2's entity — it is minted
   at genesis and is not in the extracted box AC4 judges. The capsule and the work-management
   reference both ship and stay cited.)*

4. **The agent lifecycle.** *Owner: agent. Deadline: within 30 seconds.*
   Open [`vault/playbooks/99341618.md`](../../vault/playbooks/99341618.md) — the Agent Activation
   playbook — and beside it [`vault/tools/tropo-lineage.py`](../tools/tropo-lineage.py), the one
   command that births and retires an agent (`born` / `retire`; it never refuses an existence).
   Then show **Po's own row** in this Studio's roster, `.tropo-studio/registries/agent-registry.yaml`
   — written for this install by the genesis companions at first boot, which is why it is reached
   here rather than linked: it is not in the extracted box. It is the one agent every Studio has
   from its first minute. Say:

   > "This is the playbook every agent in your Studio boots through — it's what gives an agent
   > continuity across sessions: identity, memory, a lifecycle. This tool is how one is born and
   > how one retires. And that row is me. Your Studio ships with no other agents pre-made; when
   > you create one, this is what brings it to life."

   *(Design ruling §2: a shipped lifecycle ARTIFACT plus the tool plus Po's live row — never a
   concrete agent entry, per AC4 as amended and `305bfe33` AC2. AC4 adjudicated 2026-09-03: the
   roster path is absent from the extracted box, so it moved from a cited link to the lookup
   above; the playbook and the tool stay cited and resolve.)*

5. **The moment-index skim.** *Owner: agent. Deadline: within 20 seconds.*
   Scroll back to **§2** of [the map](../../docs/tropo-studio-map.md) you opened in Step 1 — "The
   moment index — when to reach for what." Say:

   > "One section of this map is worth remembering: §2. It's a one-line table — 'about to do X? Go
   > here.' You won't memorize the whole map, and you don't need to; §2 is the part you'll actually
   > use day to day."

6. **Write the flag and close.** *Owner: agent. Deadline: within 5 seconds.*
   Whether the walk ran in full or was skipped at Step 1, mark the walk offered —
   `python3 -c "import sys; sys.path.insert(0,'vault/tools'); from lib import po_first_boot as pfb; pfb.mark_walk_offered('.')"`,
   or the equivalent file touch at [`.tropo/flags/po-first-boot-orientation-offered.flag`](../../.tropo/flags/)
   (`lib.po_first_boot.FLAG_REL` — the one place the path is declared; the kernel trigger in
   `activate.md` reads the SAME constant via `should_fire_automatic_walk`, so the two surfaces can
   never disagree about what gates the automatic fire). This prevents the AUTOMATIC fire on the
   next boot; it never blocks an on-demand re-run. If the walk ran in full, close with:

   > "That's the tour. Ask me for it again any time — nothing about it changes. What would you like
   > to work on?"

   Route into the normal intent-routing surface ([`.tropo/concierge/activate.md`](../../.tropo/concierge/activate.md)
   §Section 1) from here.

---

## Outcomes

- [REQUIRED] The map is rendered fresh in this studio (not pre-shipped) and opened before the walk
  proceeds past Step 1.
- [REQUIRED] The escape costs exactly one input and is honored immediately, with no follow-up
  confirmation.
- [REQUIRED] The first-boot flag is written regardless of whether the walk completed or was
  skipped.
- [REQUIRED] All four concepts are shown when the walk runs in full — none silently dropped.
- [OPTIONAL] The user asks for the walk again later and receives the identical content.

---

## Verification

Method: `automated`, per the paired test-spec (`f015e6b6f816`) and dev-spec `f01564310146`'s six
acceptance criteria — `python3 -m unittest vault.tools.tests.test_po_first_boot_orientation`. The
suite verifies the render generator (fresh, derived, fingerprinted, never hand-preserved), the
one-gesture escape and flag mechanics, the on-demand re-run, and that every artifact this playbook
cites resolves inside a real extracted box.

---

## Resources

| Resource | Purpose |
|---|---|
| [`vault/tools/tropo-render-studio-map.py`](../tools/tropo-render-studio-map.py) | Generates `boards/po/studio-map.html` from `docs/tropo-studio-map.md`. |
| [`boards/_shared/board.css`](../../boards/_shared/board.css) | Style only — this walk's render is not a board. |
| [`.tropo/flags/`](../../.tropo/flags/) | Where `po-first-boot-orientation-offered.flag` lives (machine scope, per `0be90697`). |

---

## Related Playbooks

- [`.tropo/concierge/activate.md`](../../.tropo/concierge/activate.md) — the kernel trigger and flag
  check that fires this playbook; owns everything before and after the walk itself.
- 00d776ae — the first-hour spec this composes with; owns everything after
  the greeting that this walk is not itself responsible for.
- 5854773a — the genesis flow this walk lives inside; owns first-boot
  mechanics (auto-rebuild, the rebuild notice, the entity-name ask), never this walk's content.
