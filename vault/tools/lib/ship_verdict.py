"""Ship verdict resolution — the single home for the algebra.

v1.94 Stream 5 (B-1, dev-spec 91d951f4), built by talos-t60 2026-09-02 against the
Mike-locked spec whose seven AC6 rows were ratified at the 2026-09-02 walk.

WHAT THIS IS FOR. Shipping used to be a NEGATIVE census: everything goes in the box
except a growing exclusion list. Every cure grew the list, and the list kept losing --
the v1.90 apply destroyed 13 customer files, 46 private-marked files sat in the public
box, and an internal locked spec shipped publicly twice. This module inverts it. Every
path resolves to exactly ONE ruled verdict; the default is DENY; the box becomes
provably exactly-what-was-ruled.

Mike's frame at the lock walk, which governs how this gets used:

    "The twin is meant to help future tropo-studio owners. I want to have a bias
     towards helping them... PII, privacy are not my concern. It is super hard to
     get people to adopt what we are doing, we are enablers not preventers."

DENY-by-default is what makes everything else a yes without a stripping pass. This is
not a redaction engine.

THE ALGEBRA LIVES IN ONE PLACE AND THIS IS NOT IT. The canonical statement is
`vault/capsules/tropo-ship-artifact.capsule.md` §Verdict Algebra (v1.5). This module
IMPLEMENTS it; the capsule RULES it. If the two disagree, the capsule is right and this
file is a defect. Do not restate the rule anywhere else -- one fact, two writers is the
defect family this whole release exists to end.
"""

import json
import os
import posixpath

# The three ruled verdicts, plus the two reported non-verdicts.
DENY = 'DENY'
SHIP_AS_IS = 'SHIP-AS-IS'
SHADOW = 'SHADOW'
RULED_VERDICTS = (DENY, SHIP_AS_IS, SHADOW)

# GENERATED is not a ruled verdict -- it is what the build says about a path it WROTE
# rather than copied, so no source-side verdict could exist for it. Named, never silent.
GENERATED = 'GENERATED'

# The ratified posture for a path no channel covers (AC6 row 6, Mike 2026-09-02:
# "I go with your lean"). It does not ship, AND it is named in the census. Both halves
# are the rule: nothing ships unseen, nothing drops unseen.
UNRULED_VERDICT = DENY

# Where a decision came from. Reported so a census row can be audited back to its rule.
CH_ARTIFACT = 'ship-artifact'      # a ship_verdict: field on a ship-artifact entry
CH_ROOT_MANIFEST = 'root-manifest'  # a path->verdict row in b2e7d4a9's ROOT MANIFEST block
CH_SCOPE = 'record-scope'          # extraction_scope: ship on a vault record (fallback)
CH_GENERATED = 'generated'         # declared by the build at the write site
CH_UNRULED = 'unruled'             # nothing covered it


class Decision:
    """One path's effective verdict, and the receipt for how it was reached."""

    __slots__ = ('path', 'verdict', 'channel', 'grain', 'ruled_by', 'shadow_of', 'note')

    def __init__(self, path, verdict, channel, grain=None, ruled_by=None,
                 shadow_of=None, note=None):
        self.path = path
        self.verdict = verdict
        self.channel = channel
        self.grain = grain          # 'file' | 'folder' | None
        self.ruled_by = ruled_by    # uid or manifest row key that decided it
        self.shadow_of = shadow_of  # source designation, when verdict is SHADOW
        self.note = note

    @property
    def ships(self):
        """Does the SOURCE at this path go into the box verbatim?

        SHADOW is deliberately False: the source does NOT ship -- its twin ships in its
        place, which the caller emits separately. Reading SHADOW as 'ships' is the bug
        that makes a shadow pair put both bodies in the box.
        """
        return self.verdict in (SHIP_AS_IS, GENERATED)

    @property
    def is_unruled(self):
        return self.channel == CH_UNRULED

    def __repr__(self):
        return (f'<Decision {self.path} {self.verdict} '
                f'via {self.channel}'
                + (f' ({self.grain})' if self.grain else '')
                + (f' ruled_by={self.ruled_by}' if self.ruled_by else '') + '>')


def normalize(path):
    """Vault-root-relative, forward-slashed, no leading './' or '/'.

    Every path this module compares passes through here. Two spellings of one path
    resolving to two verdicts is the failure this function exists to make impossible.
    """
    if not path:
        return ''
    p = str(path).replace(os.sep, '/')
    if p.startswith('argo-os/'):
        p = p[len('argo-os/'):]
    p = posixpath.normpath(p)
    if p in ('.', '/'):
        return ''
    return p.lstrip('./').lstrip('/')


def _is_folder_key(key):
    return key.endswith('/')


class ShipVerdictResolver:
    """Resolves a source path to exactly one effective verdict.

    Precedence, per the capsule's §Verdict Algebra:
      1. manifest grain (ship-artifact ship_verdict, or a ROOT MANIFEST row)
         -- these BEAT record scope, which is what lets DENY beat extraction_scope: ship
      2. within manifest grain: file beats folder; longest matching prefix wins
      3. record scope (extraction_scope: ship) -> SHIP-AS-IS
      4. unruled -> DENY, named

    GENERATED is not resolved here; the build declares it at the write site, because
    only the writer knows it wrote rather than copied.
    """

    def __init__(self, file_rules=None, folder_rules=None, scope_paths=None,
                 withheld_paths=None):
        # path -> (verdict, channel, ruled_by, shadow_of)
        self._file_rules = dict(file_rules or {})
        self._folder_rules = dict(folder_rules or {})
        self._scope_paths = set(scope_paths or ())
        # Paths whose OWN record explicitly declares a non-ship scope. These are the
        # asymmetry's subject -- see _apply_withholding.
        self._withheld_paths = set(withheld_paths or ())
        # Longest-first so the first prefix hit is the winner; computed once, not per
        # lookup, because this runs once per file in a ~4000-file box.
        self._folder_keys = sorted(self._folder_rules, key=len, reverse=True)

    # ── construction ────────────────────────────────────────────────────────

    @classmethod
    def from_sources(cls, artifact_rows=(), manifest_rows=(), scope_rows=()):
        """Build from the two manifest channels plus the scope channel.

        artifact_rows: index rows with type == 'ship-artifact'
        manifest_rows: (path, verdict, shadow_of) triples from the ROOT MANIFEST block
        scope_rows:    index rows carrying extraction_scope == 'ship'
        """
        file_rules, folder_rules = {}, {}

        for row in artifact_rows:
            verdict = (row.get('ship_verdict') or '').strip().upper()
            if verdict not in RULED_VERDICTS:
                # Missing or unrecognized: this artifact rules nothing. It is NOT an
                # implicit ship. The path falls through to scope or to unruled, and the
                # field-keyed census counts it as unruled -- which is exactly how the
                # backfill's progress stays measurable (0 of 92 -> 92 of 92).
                continue
            src = normalize(row.get('canonical_source'))
            if not src:
                continue
            rule = (verdict, CH_ARTIFACT, row.get('uid'), row.get('shadow_of'))
            if row.get('kind') == 'folder':
                folder_rules[src.rstrip('/') + '/'] = rule
            else:
                file_rules[src] = rule

        for entry in manifest_rows:
            path, verdict, shadow_of = entry
            verdict = (verdict or '').strip().upper()
            if verdict not in RULED_VERDICTS:
                continue
            key = str(path).replace(os.sep, '/')
            rule = (verdict, CH_ROOT_MANIFEST, key, shadow_of)
            if _is_folder_key(key):
                folder_rules[normalize(key).rstrip('/') + '/'] = rule
            else:
                file_rules[normalize(key)] = rule

        scope_paths, withheld = set(), set()
        for row in scope_rows:
            p = normalize(row.get('path') or row.get('canonical_source'))
            if not p:
                continue
            if row.get('extraction_scope') == 'ship':
                scope_paths.add(p)
            else:
                withheld.add(p)

        return cls(file_rules, folder_rules, scope_paths, withheld)

    # ── resolution ──────────────────────────────────────────────────────────

    def _apply_withholding(self, decision):
        """THE ASYMMETRY. A manifest DENY beats record scope; a manifest SHIP does not.

        Precedence is not symmetric, and the reason is which direction each mistake
        fails in. DENY-beats-scope is the D3 mechanism the spec asks for by name: it is
        how a ruled denial overrides `extraction_scope: ship`. The opposite direction
        has no ruled purpose and one very sharp edge -- a broad folder row like
        `agents/tropo/: SHIP-AS-IS` silently overrides the explicit `argo-private` on a
        file inside it, and private substrate crosses into a public box because someone
        wrote a convenient folder rule.

        Measured, not hypothesised: the first draft of this module was symmetric, and
        the first census run against the real vault shipped
        `agents/tropo/tropo-status.md` -- an argo-private status card -- through exactly
        that path. Rather than add a file-grain DENY exception and call it fixed (a
        guard that has to be correct), the class is made unrepresentable: a SHIP verdict
        can never override a record that declares itself non-ship. The conflict is
        NAMED rather than silently resolved, because a folder rule colliding with an
        explicit withholding is a thing a human should see.
        """
        if decision.verdict != SHIP_AS_IS:
            return decision
        if decision.grain != 'folder':
            # FILE GRAIN MAY OVERRIDE A WITHHOLDING; FOLDER GRAIN MAY NOT. Specificity
            # carries intent. A file row is a human naming one exact path -- a
            # deliberate statement stronger than a scope value, which is very often the
            # Gardener's PATH-BASED BACKFILL rather than anyone's decision (38f706de
            # documents exactly that: five crew souls shipped for years because a
            # backfill rule, not a person, set their scope). A folder row is broad and
            # over-reaches by construction.
            #
            # Both halves are measured. Without the folder restriction,
            # `agents/tropo/: SHIP-AS-IS` leaked an argo-private status card. Without
            # the file exemption, six vault/tools files stopped shipping -- silently
            # reversing Argus A92's atomic-infrastructure ruling (fdef56ea: the
            # scripting layer ships WHOLESALE, per-tool tagging re-opens the omission
            # bug) and leaving the scripting layer part-dead in a customer box.
            return decision
        if decision.path not in self._withheld_paths:
            return decision
        return Decision(
            decision.path, DENY, decision.channel, decision.grain, decision.ruled_by,
            None,
            note=(f'manifest ruled SHIP-AS-IS via {decision.ruled_by or decision.channel} '
                  'but the record declares a non-ship extraction_scope; a SHIP verdict '
                  'never overrides an explicit withholding (asymmetric precedence)'),
        )

    def resolve(self, path):
        p = normalize(path)

        # 1+2. Manifest grain, file first (file beats folder unconditionally).
        rule = self._file_rules.get(p)
        if rule:
            verdict, channel, ruled_by, shadow_of = rule
            return self._apply_withholding(
                Decision(p, verdict, channel, 'file', ruled_by, shadow_of))

        # Folder grain, longest matching prefix wins.
        for key in self._folder_keys:
            if p.startswith(key):
                verdict, channel, ruled_by, shadow_of = self._folder_rules[key]
                return self._apply_withholding(
                    Decision(p, verdict, channel, 'folder', ruled_by, shadow_of))

        # 3. Record scope -- a RESOLUTION, not a ruling. The census keys on the field,
        #    so a path arriving here still counts as carrying no verdict.
        if p in self._scope_paths:
            return Decision(p, SHIP_AS_IS, CH_SCOPE, None, None, None,
                            note='resolved by extraction_scope: ship; carries no ship_verdict field')

        # 4. Unruled: DENY, and named.
        return Decision(p, UNRULED_VERDICT, CH_UNRULED, None, None, None,
                        note='no ship-artifact, no manifest row, no ship scope')

    def generated(self, path, reason):
        """Declare a path as build-GENERATED. Named class, never silent."""
        return Decision(normalize(path), GENERATED, CH_GENERATED, None, None, None,
                        note=reason)

    # ── introspection, for the census and the tests ─────────────────────────

    @property
    def file_rule_count(self):
        return len(self._file_rules)

    @property
    def folder_rule_count(self):
        return len(self._folder_rules)

    def rules_with_verdict(self, verdict):
        """Every path ruled to `verdict`, both grains. Used to assert the D3 row count."""
        v = verdict.strip().upper()
        out = [k for k, r in self._file_rules.items() if r[0] == v]
        out += [k for k, r in self._folder_rules.items() if r[0] == v]
        return sorted(out)

    def folder_ship_collisions(self, candidate_paths):
        """Paths where a broad folder SHIP row collides with a record's withholding.

        Each one is a question only a human can answer: does the folder's ruling
        govern, or does the record's? While unsettled the safe direction wins (DENY,
        never leak), and this list is what stops that being silent. Settle one with an
        explicit file-grain row, which is a deliberate statement about that exact path.
        """
        out = []
        for path in candidate_paths:
            p = normalize(path)
            if p in self._file_rules or p not in self._withheld_paths:
                continue
            for key in self._folder_keys:
                if p.startswith(key) and self._folder_rules[key][0] == SHIP_AS_IS:
                    out.append((p, key))
                    break
        return sorted(out)

    def shadow_pairs(self):
        """(source_path, twin_designation) for every SHADOW rule."""
        pairs = []
        for k, r in list(self._file_rules.items()) + list(self._folder_rules.items()):
            if r[0] == SHADOW:
                pairs.append((k, r[3]))
        return sorted(pairs)


# ─── The ROOT MANIFEST block ────────────────────────────────────────────────
#
# Paths that no ship-artifact owns are ruled by rows in ONE fenced yaml block in the
# release manifest root's body (b2e7d4a9). Format per spec F11.

ROOT_MANIFEST_FENCE = 'ship-manifest'


def parse_root_manifest(body_text):
    """Extract (path, verdict, shadow_of) triples from the ROOT MANIFEST fenced block.

    The block is ```yaml ship-manifest ... ``` in b2e7d4a9's body. Rows are either
    `path: VERDICT` or `path: {verdict: SHADOW, ships_as: <uid>}`.

    Returns [] when no block is present -- an absent block is legal (it means no
    path-designated rules), and is NOT the same as a malformed one, which raises.
    """
    import yaml

    lines = body_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('```') and ROOT_MANIFEST_FENCE in stripped:
            start = i + 1
            break
    if start is None:
        return []

    end = None
    for j in range(start, len(lines)):
        if lines[j].strip().startswith('```'):
            end = j
            break
    if end is None:
        raise ValueError(
            'ROOT MANIFEST block opened with a ```'
            f'{ROOT_MANIFEST_FENCE} fence and never closed -- refusing to guess where '
            'the rules end, because a truncated rule set silently under-rules the box.'
        )

    block = '\n'.join(lines[start:end])
    if not block.strip():
        return []

    data = yaml.safe_load(block)
    if data is None:
        return []
    if not isinstance(data, dict):
        raise ValueError(
            f'ROOT MANIFEST block must be a mapping of path -> verdict; got '
            f'{type(data).__name__}'
        )

    rows = []
    for path, value in data.items():
        if isinstance(value, dict):
            verdict = value.get('verdict')
            shadow_of = value.get('ships_as') or value.get('shadow_of')
        else:
            verdict, shadow_of = value, None
        rows.append((str(path), verdict, shadow_of))
    return rows


def load_root_manifest(vault_root, manifest_root_uid='b2e7d4a9'):
    """Read the ROOT MANIFEST rows from the manifest-root entry's body on disk."""
    from pathlib import Path

    root = Path(vault_root)
    candidates = list((root / 'vault' / 'files').glob(f'*{manifest_root_uid}*.md'))
    exact = root / 'vault' / 'files' / f'{manifest_root_uid}.md'
    if exact.exists():
        candidates = [exact]
    if not candidates:
        return []
    return parse_root_manifest(candidates[0].read_text(encoding='utf-8'))


def load_index_rows(index_path):
    """Split an index into (ship_artifact_rows, scope_declaring_rows) in one pass.

    The second list is EVERY row that declares an extraction_scope, not just the
    shipping ones. The withheld rows are load-bearing: they are what a manifest
    SHIP verdict is forbidden to override (see _apply_withholding). Returning only
    the ship-scoped rows is what made the first cut of this module leak
    agents/tropo/tropo-status.md.
    """
    artifacts, scoped = [], []
    with open(index_path, 'r', encoding='utf-8') as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get('type') == 'ship-artifact':
                artifacts.append(row)
            if row.get('extraction_scope'):
                scoped.append(row)
    return artifacts, scoped


def build_resolver(vault_root, index_path=None, manifest_root_uid='b2e7d4a9'):
    """The one constructor callers should use: build + validator + tests share it."""
    from pathlib import Path

    root = Path(vault_root)
    index_path = index_path or (root / 'vault' / '00-index.jsonl')
    artifacts, scoped = ([], [])
    if os.path.exists(index_path):
        artifacts, scoped = load_index_rows(index_path)
    # The ARCHIVE index counts too. An archived record's withholding is still a
    # withholding -- archiving a private entry must not become a way to make a folder
    # rule ship it.
    archive_path = Path(index_path).with_name('00-archive-index.jsonl')
    if archive_path.exists():
        a_artifacts, a_scoped = load_index_rows(archive_path)
        artifacts += a_artifacts
        scoped += a_scoped
    manifest_rows = load_root_manifest(root, manifest_root_uid)
    return ShipVerdictResolver.from_sources(artifacts, manifest_rows, scoped)


# ─── Census ─────────────────────────────────────────────────────────────────

class Census:
    """What shipped, under which verdict, through which channel.

    Keyed on the FIELD, not the resolution. The difference is the whole point: an
    artifact missing `ship_verdict` whose path carries `extraction_scope: ship`
    RESOLVES to SHIP-AS-IS, so a resolution-keyed census reads 100% ruled while the
    backfill is half-finished. Field-keyed, it reads 0 of 92 before the sweep and can
    actually fail.
    """

    def __init__(self):
        self.decisions = []

    def record(self, decision):
        self.decisions.append(decision)
        return decision

    # -- counts -----------------------------------------------------------

    def by_verdict(self):
        out = {}
        for d in self.decisions:
            out[d.verdict] = out.get(d.verdict, 0) + 1
        return out

    def by_channel(self):
        out = {}
        for d in self.decisions:
            out[d.channel] = out.get(d.channel, 0) + 1
        return out

    def unruled(self):
        return [d for d in self.decisions if d.is_unruled]

    def denied(self):
        return [d for d in self.decisions if d.verdict == DENY]

    def shipped(self):
        return [d for d in self.decisions if d.ships]

    def shadowed(self):
        return [d for d in self.decisions if d.verdict == SHADOW]

    # -- report -----------------------------------------------------------

    def render(self, stream=None):
        """The loud census. Silence is not a report."""
        import sys
        out = stream or sys.stdout
        by_v = self.by_verdict()
        total = len(self.decisions)

        print('', file=out)
        print('  ─── Ship census ───────────────────────────────────────────', file=out)
        print(f'  {total} paths resolved', file=out)
        for verdict in (SHIP_AS_IS, SHADOW, DENY, GENERATED):
            if verdict in by_v:
                print(f'    {verdict:<12} {by_v[verdict]}', file=out)
        print('  by channel:', file=out)
        for channel, n in sorted(self.by_channel().items()):
            print(f'    {channel:<16} {n}', file=out)

        unruled = self.unruled()
        if unruled:
            print(f'  UNRULED -> DENY, named ({len(unruled)}) — nothing ships unruled, '
                  'and nothing drops unseen:', file=out)
            for d in unruled:
                print(f'    unruled-pruned: {d.path}', file=out)
        else:
            print('  UNRULED: none — every path resolved through a ruled channel.', file=out)

        pruned = [d for d in self.denied() if not d.is_unruled]
        if pruned:
            print(f'  DENY prunes by rule ({len(pruned)}):', file=out)
            for d in pruned:
                print(f'    deny-pruned: {d.path}  (by {d.ruled_by or d.channel})', file=out)

        shadows = self.shadowed()
        if shadows:
            print(f'  SHADOW substitutions ({len(shadows)}):', file=out)
            for d in shadows:
                print(f'    {d.path} -> twin {d.shadow_of}', file=out)
        print('  ───────────────────────────────────────────────────────────', file=out)
