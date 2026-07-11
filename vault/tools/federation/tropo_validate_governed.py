#!/usr/bin/env python3
"""tropo_validate_governed.py — the governance-validator GATE for federated governed markdown (Phase D3).

Reference impl reconstructed + re-verified by Metis G86 (2026-07-03), hardened after an adversarial break
pass (fixes shipped + regression-tested):
  - CRITICAL shared bug: fence detection used `.strip()`, so an indented `---` inside a block scalar was
    mistaken for the closing fence and fields below it silently vanished — and because the driver shared
    the flaw, the corrupt file was blessed VALID. Fixed: exact-line fence (`line.rstrip() == '---'`), the
    SAME rule the driver uses, so the two never disagree; body is extracted via the real fence.
  - false-HOLD: the conflict-annotation check was a raw substring scan (a legitimate value containing the
    string forced HOLD). Fixed: line-based detection of the annotation FORM.

THE LOAD-BEARING PIECE. The merge driver is necessary but NOT sufficient (it honors a delete of a required
field as a clean merge). This validator is the mandatory backstop. Wire it as a pre-commit / pre-receive
hook (or required CI check) — never a manual step. exit 0=VALID · 1=BROKEN · 2=NEEDS-RESOLUTION.
"""
import sys
import re
import os

REQUIRED_KEYS = ("uid", "type", "title", "owner")  # owner catches the delete/change field-drop the driver honors
MARKERS = ("<<<<<<<", "=======", ">>>>>>>")
KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):")
ANNOT_RE = re.compile(r"^[A-Za-z_][\w-]*:.*#\s*TROPO-FIELD-CONFLICT")  # the annotation FORM, on a key line


def split_doc(text):
    """(frontmatter, body) via EXACT-line fences (never .strip()); (None, text) if malformed."""
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return None, text


def _yaml_load_no_dupes(fm_text):
    try:
        import yaml
    except ImportError:
        return _hand_parse(fm_text)

    class NoDup(yaml.SafeLoader):
        pass

    def _nd(loader, node, deep=False):
        m = {}
        for kn, vn in node.value:
            k = loader.construct_object(kn, deep=deep)
            if k in m:
                raise yaml.constructor.ConstructorError(None, None, "duplicate key %r" % k, kn.start_mark)
            m[k] = loader.construct_object(vn, deep=deep)
        return m

    NoDup.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _nd)
    try:
        data = yaml.load(fm_text, Loader=NoDup)
        if not isinstance(data, dict):
            return None, "frontmatter is not a single YAML mapping"
        return data, None
    except Exception as e:
        return None, "YAML parse error: %s" % e


def _hand_parse(fm_text):
    keys = {}
    for line in fm_text.split("\n"):
        if line[:1].isspace():
            continue
        m = KEY_RE.match(line)
        if m:
            k = m.group(1)
            if k in keys:
                return None, "duplicate top-level key %r" % k
            keys[k] = line.split(":", 1)[1].strip()
    return keys, None


def validate(path):
    text = open(path).read()
    problems = []
    if any(mk in text for mk in MARKERS):
        problems.append("git conflict markers present (a raw line-merge corrupted this file)")
    fm, body = split_doc(text)
    if fm is None:
        problems.append("no well-formed YAML frontmatter (exact '---' fences missing)")
        return "BROKEN", problems
    # a SECOND exact fence inside the frontmatter region would mean a truncated/injected header
    if any(ln.rstrip() == "---" for ln in fm.split("\n")):
        problems.append("stray '---' fence line inside frontmatter (possible field amputation)")
    needs_resolution = any(ANNOT_RE.match(ln) for ln in fm.split("\n"))
    data, err = _yaml_load_no_dupes(fm)
    if err:
        problems.append(err); return "BROKEN", problems
    for k in REQUIRED_KEYS:
        if k not in data or data.get(k) in (None, ""):
            problems.append("missing/empty required key: %r" % k)
    if not (body or "").strip():
        problems.append("empty body")
    fname = os.path.basename(path); stem = fname[:-3] if fname.endswith(".md") else fname
    uid = str(data.get("uid", "")).strip()
    if uid and stem and uid != stem and not stem.endswith(uid):
        problems.append("filename/uid mismatch: file %r vs uid %r" % (stem, uid))
    if problems:
        return "BROKEN", problems
    if needs_resolution:
        return "NEEDS-RESOLUTION", ["an unresolved TROPO-FIELD-CONFLICT annotation (pick a value)"]
    return "VALID", []


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: tropo_validate_governed.py <file.md> [...]\n"); return 2
    worst = 0
    for path in sys.argv[1:]:
        status, problems = validate(path)
        worst = max(worst, {"VALID": 0, "BROKEN": 1, "NEEDS-RESOLUTION": 2}[status])
        print("[%s] %s — %s" % ({"VALID": "OK ", "BROKEN": "FAIL", "NEEDS-RESOLUTION": "HOLD"}[status], path, status))
        for p in problems:
            print("        - %s" % p)
    return worst


if __name__ == "__main__":
    sys.exit(main())
