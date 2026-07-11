#!/usr/bin/env python3
"""tropo_merge.py — field-aware 3-way merge driver for governed markdown (Federation Phase D2).

Reference implementation reconstructed + re-verified by Metis G86 (2026-07-03), then hardened after an
adversarial break pass found two integrity bugs the first cut missed (both now fixed + regression-tested):
  - a `---` INSIDE a multi-line value was mistaken for the closing fence (fields silently amputated);
    fixed by exact-line fence detection (`line.rstrip() == '---'`, never `.strip()`), in lockstep with
    the validator so the two never disagree.
  - two studios appending different items to a list (`refs:`) destroyed the whole list; fixed by
    element-wise list merge (union of additions, deletions honored) so the canonical case AUTO-merges.
Requirements + proven behavior: the same-file spike result (vault/files/39df3124.md); build spec Phase D
(vault/files/304badf7.md). Corruption corpus: test_corruption_suite.sh (all green incl. the break cases).

WHY: git's line-merge falsely conflicts INDEPENDENT frontmatter fields on adjacent lines and wraps
`<<<<<<<` markers INSIDE the YAML — a broken governed file. This driver merges frontmatter FIELD-by-FIELD
(adjacency irrelevant), merges LIST fields element-wise, and delegates the prose body to git merge-file.
A TRUE scalar clash → a PARSEABLE single-key `# TROPO-FIELD-CONFLICT` annotation carrying BOTH real
values, and the driver exits non-zero. The validator (tropo_validate_governed.py) is the mandatory gate.

Wire it (BOTH parts — `.gitattributes` alone does not carry the command):
    files/*.md merge=tropo                 # in the team repo's .gitattributes
    git config merge.tropo.driver "python3 vault/tools/federation/tropo_merge.py %O %A %B %P"   # per clone
"""
import sys
import re

FM_DELIM = "---"
KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):(.*)$")
LIST_ITEM_RE = re.compile(r"^\s*-\s?(.*)$")


def is_fence(line):
    # exact fence: a line that is '---' with only trailing whitespace/CR. An indented '  ---' inside a
    # block/folded scalar is NOT a fence (the break-pass CRITICAL bug lived in using .strip()).
    return line.rstrip() == FM_DELIM


def split_doc(text):
    """Return (frontmatter_text, body_text) or (None, whole_text) if no well-formed frontmatter."""
    lines = text.split("\n")
    if not lines or not is_fence(lines[0]):
        return None, text
    for i in range(1, len(lines)):
        if is_fence(lines[i]):
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return None, text


def parse_fields(fm_text):
    """Ordered [(key, block)]. A block is the key line + following indented/list continuation lines,
    so nested lists like `refs:` stay attached. Returns (order, {key: block})."""
    if fm_text is None:
        return [], {}
    order, blocks, cur = [], {}, None
    for line in fm_text.split("\n"):
        m = KEY_RE.match(line)
        starts_field = m and not line[:1].isspace()  # a column-0 key line
        if starts_field:
            cur = m.group(1)
            if cur not in blocks:
                order.append(cur); blocks[cur] = line
            else:
                blocks[cur] += "\n" + line  # duplicate source key — keep so the validator flags it
        elif cur is not None:
            blocks[cur] += "\n" + line
        else:
            key = "__pre__%d" % len(order)
            order.append(key); blocks[key] = line
    return order, blocks


def block_as_list(block):
    """If a field block is a YAML list (`key:` then `- item` lines), return (header, [items]); else None."""
    lines = block.split("\n")
    head = lines[0]
    hm = KEY_RE.match(head)
    if not hm or hm.group(2).strip() not in ("", None):
        return None  # inline value on the key line — not a block list
    items, saw = [], False
    for ln in lines[1:]:
        im = LIST_ITEM_RE.match(ln)
        if im:
            saw = True; items.append(im.group(1).strip())
        elif ln.strip() == "":
            continue
        else:
            return None  # a non-list continuation (nested map, block scalar) — treat as opaque
    return (head, items) if saw else None


def merge_list(base_b, our_b, their_b):
    """3-way set-merge of a list field: honor deletions, union additions. Returns merged block text."""
    def items(b):
        p = block_as_list(b) if b is not None else None
        return p[1] if p else None
    bi = items(base_b) or []
    oi = items(our_b); ti = items(their_b)
    header = (block_as_list(our_b) or block_as_list(their_b) or (KEY_RE.match((our_b or their_b).split("\n")[0]).group(0),))[0]
    added = [x for x in (oi or []) if x not in bi] + [x for x in (ti or []) if x not in bi and x not in (oi or [])]
    deleted = set(x for x in bi if (oi is not None and x not in oi)) | set(x for x in bi if (ti is not None and x not in ti))
    merged = [x for x in bi if x not in deleted] + added
    lines = [header] + ["  - " + x for x in merged]
    return "\n".join(lines)


def merge_fields(base, ours, theirs):
    bb, ob, tb = base[1], ours[1], theirs[1]
    all_keys = list(dict.fromkeys(list(bb.keys()) + ours[0] + theirs[0]))
    merged, order, conflicts = {}, [], []
    for k in all_keys:
        in_b, in_o, in_t = k in bb, k in ob, k in tb
        bv, ov, tv = bb.get(k), ob.get(k), tb.get(k)
        if in_b and not in_o and not in_t:
            continue                                                  # both deleted
        if in_b and not in_o and in_t:
            if tv == bv:
                continue                                              # ours deleted, theirs unchanged → delete
            conflicts.append(k); order.append(k); merged[k] = _annotate(k, "<deleted>", tv); continue
        if in_b and in_o and not in_t:
            if ov == bv:
                continue
            conflicts.append(k); order.append(k); merged[k] = _annotate(k, ov, "<deleted>"); continue
        if in_o and in_t and ov == tv:
            order.append(k); merged[k] = ov; continue                 # identical both sides
        # both/one present and differ → try list merge first
        both_present = in_o and in_t
        list_shaped = any(block_as_list(x) for x in (bv, ov, tv) if x is not None)
        if list_shaped:
            order.append(k); merged[k] = merge_list(bv, ov, tv); continue
        if in_b and in_o and in_t:
            if ov == bv:
                order.append(k); merged[k] = tv; continue             # only theirs changed
            if tv == bv:
                order.append(k); merged[k] = ov; continue             # only ours changed
            conflicts.append(k); order.append(k); merged[k] = _annotate(k, ov, tv); continue
        if in_o and not in_t:
            order.append(k); merged[k] = ov; continue
        if in_t and not in_o:
            order.append(k); merged[k] = tv; continue
        if both_present:
            conflicts.append(k); order.append(k); merged[k] = _annotate(k, ov, tv); continue
    return order, merged, conflicts


def _scalar(block):
    if block is None or block.startswith("<"):
        return block
    first = block.split("\n", 1)[0]
    m = KEY_RE.match(first)
    v = m.group(2).strip() if m else first.strip()
    # a multi-line/list value: summarise so the annotation carries something real, never ''
    if v in ("", None) and "\n" in block:
        rest = " ".join(x.strip() for x in block.split("\n")[1:] if x.strip())
        return "[" + rest + "]"
    return v


def _annotate(key, ours_val, theirs_val):
    o, t = _scalar(ours_val), _scalar(theirs_val)
    shown = o if o not in (None, "") else '""'
    return "{k}: {v}  # TROPO-FIELD-CONFLICT ours={o!r} theirs={t!r} — resolve".format(k=key, v=shown, o=o, t=t)


def git_merge_file(base_body, ours_body, theirs_body):
    import subprocess, tempfile, os
    d = tempfile.mkdtemp()
    po, pb, pt = (os.path.join(d, n) for n in ("o", "b", "t"))
    open(po, "w").write(ours_body); open(pb, "w").write(base_body); open(pt, "w").write(theirs_body)
    r = subprocess.run(["git", "merge-file", "-p", "-L", "ours", "-L", "base", "-L", "theirs", po, pb, pt],
                       capture_output=True, text=True)
    return r.stdout, (r.returncode != 0)


def render(order, blocks):
    seen, out = set(), []
    for k in order:
        if k in seen:
            continue
        seen.add(k); out.append(blocks[k])
    return "\n".join(out)


def main():
    if len(sys.argv) < 4:
        sys.stderr.write("usage: tropo_merge.py <base> <ours> <theirs> [pathname]\n"); return 2
    base_t, ours_t, theirs_t = (open(sys.argv[i]).read() for i in (1, 2, 3))
    b_fm, b_body = split_doc(base_t); o_fm, o_body = split_doc(ours_t); t_fm, t_body = split_doc(theirs_t)
    if o_fm is None or t_fm is None:
        merged_body, conflicted = git_merge_file(base_t, ours_t, theirs_t)
        open(sys.argv[2], "w").write(merged_body); return 1 if conflicted else 0
    order, blocks, conflicts = merge_fields(parse_fields(b_fm), parse_fields(o_fm), parse_fields(t_fm))
    merged_body, body_conflict = git_merge_file(b_body or "", o_body or "", t_body or "")
    open(sys.argv[2], "w").write("{d}\n{fm}\n{d}\n{body}".format(d=FM_DELIM, fm=render(order, blocks), body=merged_body))
    if conflicts:
        sys.stderr.write("tropo_merge: field conflict(s): %s\n" % ", ".join(map(str, conflicts)))
    if body_conflict:
        sys.stderr.write("tropo_merge: body conflict\n")
    return 1 if (conflicts or body_conflict) else 0


if __name__ == "__main__":
    sys.exit(main())
