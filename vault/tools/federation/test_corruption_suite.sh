#!/usr/bin/env bash
# test_corruption_suite.sh — the re-runnable red-test corpus for the Federation Phase-D enforcement.
# Reconstructed + re-verified by Metis G86 (2026-07-03). Proves the merge driver + validator TOGETHER
# make concurrent same-file editing of governed markdown safe. Run: bash test_corruption_suite.sh
#
# Each row is a real git merge (the driver is invoked by git), then the validator is run on the result.
# Expected outcomes encode the honest design: the driver auto-composes independent fields, annotates
# true clashes (never raw markers), and the VALIDATOR GATE is the mandatory backstop that blocks any
# broken artifact — including the delete-of-a-required-field the driver honors as a clean merge.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
DRIVER="$HERE/tropo_merge.py"
VALIDATE="$HERE/tropo_validate_governed.py"
PASS=0; FAIL=0
GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; NC=$'\033[0m'

base_file() { cat <<'EOF'
---
uid: studio-a-0001
type: doctrine
title: The Shared Doctrine
status: draft
owner: studio-a
refs:
  - eca73d77
  - d61ce0a7
---

Paragraph one, the opening.

Paragraph two, the middle.

Paragraph three, the close.
EOF
}

# newrepo: fresh git repo with the driver wired + base committed on main
newrepo() {
  local d; d="$(mktemp -d)"; cd "$d" || exit 1
  git init -q; git config user.email t@t; git config user.name t
  git config merge.tropo.driver "python3 $DRIVER %O %A %B %P"
  echo 'files/*.md merge=tropo' > .gitattributes
  mkdir files; base_file > files/studio-a-0001.md
  git add -A; git commit -qm base
  echo "$d"
}

# run_case NAME  EXPECT_MERGE(clean|conflict)  EXPECT_VALID(VALID|BROKEN|HOLD)  edit_a_fn  edit_b_fn
run_case() {
  local name="$1" exp_merge="$2" exp_valid="$3" ea="$4" eb="$5"
  local d; d="$(newrepo)"; ( cd "$d" || exit 1
    git checkout -q -b a; "$ea" files/studio-a-0001.md; git commit -qam a
    git checkout -q main; git checkout -q -b b; "$eb" files/studio-a-0001.md; git commit -qam b
    git checkout -q a
    if git merge -q b >/dev/null 2>&1; then merge=clean; else merge=conflict; fi
    python3 "$VALIDATE" files/studio-a-0001.md >/tmp/val.out 2>&1; vc=$?
    case $vc in 0) v=VALID;; 1) v=BROKEN;; 2) v=HOLD;; *) v=ERR;; esac
    ok=1
    [ "$merge" = "$exp_merge" ] || ok=0
    [ "$v" = "$exp_valid" ] || ok=0
    if [ $ok -eq 1 ]; then echo "${GREEN}PASS${NC} $name (merge=$merge validator=$v)"; else
      echo "${RED}FAIL${NC} $name (merge=$merge want $exp_merge; validator=$v want $exp_valid)"; sed 's/^/      /' files/studio-a-0001.md | head -12; fi
    echo "$ok" > /tmp/case_ok
  )
  if [ "$(cat /tmp/case_ok)" = "1" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); fi
  rm -rf "$d"
}

# --- edit helpers (each rewrites files/studio-a-0001.md) ---
set_status_done() { sed -i.bak 's/^status: draft/status: done/' "$1"; rm -f "$1.bak"; }
set_status_review(){ sed -i.bak 's/^status: draft/status: review/' "$1"; rm -f "$1.bak"; }
set_owner_b()     { sed -i.bak 's/^owner: studio-a/owner: studio-b/' "$1"; rm -f "$1.bak"; }
del_owner()       { sed -i.bak '/^owner: studio-a/d' "$1"; rm -f "$1.bak"; }
retitle_x()       { sed -i.bak 's/^title: .*/title: Title X/' "$1"; rm -f "$1.bak"; }
retitle_y()       { sed -i.bak 's/^title: .*/title: Title Y/' "$1"; rm -f "$1.bak"; }
edit_para1()      { sed -i.bak 's/^Paragraph one.*/Paragraph one, edited by A./' "$1"; rm -f "$1.bak"; }
edit_para3()      { sed -i.bak 's/^Paragraph three.*/Paragraph three, edited by B./' "$1"; rm -f "$1.bak"; }
edit_para1_b()    { sed -i.bak 's/^Paragraph one.*/Paragraph one, edited by B differently./' "$1"; rm -f "$1.bak"; }

echo "=== Federation Phase-D enforcement — corruption suite ==="
# 1. Adjacent independent fields (status vs owner) — the false-conflict killer. Driver auto-composes; VALID.
run_case "adjacent-fields (status|owner)"        clean    VALID  set_status_done   set_owner_b
# 2. Same field, both changed (status vs status) — true clash → annotated, parseable, driver conflicts → HOLD.
run_case "same-field clash (status|status)"      conflict HOLD   set_status_done   set_status_review
# 3. Delete a REQUIRED field vs change another — driver honors delete (clean), GATE catches missing owner → BROKEN.
run_case "delete-required vs change (owner|status)" clean  BROKEN del_owner         set_status_done
# 4. Both retitle differently — true clash on title → HOLD (annotated, no raw markers).
run_case "same-field clash (title|title)"        conflict HOLD   retitle_x         retitle_y
# 5. Disjoint body paragraphs — clean line-merge, header untouched → VALID.
run_case "disjoint body paragraphs"              clean    VALID  edit_para1        edit_para3
# 6. Same body paragraph — real body conflict → driver conflicts, markers in body → GATE BROKEN.
run_case "same body paragraph"                   conflict BROKEN edit_para1        edit_para1_b

# ---- adversarial-break regression cases (found + fixed 2026-07-03) ----
run_custom() { # name  basefn  edit_a  edit_b  exp_merge  exp_valid
  local name="$1" basefn="$2" ea="$3" eb="$4" em="$5" ev="$6"
  local d; d="$(mktemp -d)"; ( cd "$d" || exit 1
    git init -q; git config user.email t@t; git config user.name t
    git config merge.tropo.driver "python3 $DRIVER %O %A %B %P"
    echo 'files/*.md merge=tropo' > .gitattributes
    mkdir files; "$basefn" > files/studio-a-0001.md
    git add -A; git commit -qm base
    git checkout -q -b a; "$ea" files/studio-a-0001.md; git commit -qam a
    git checkout -q main; git checkout -q -b b; "$eb" files/studio-a-0001.md; git commit -qam b
    git checkout -q a
    if git merge -q b >/dev/null 2>&1; then merge=clean; else merge=conflict; fi
    python3 "$VALIDATE" files/studio-a-0001.md >/dev/null 2>&1; vc=$?
    case $vc in 0) v=VALID;; 1) v=BROKEN;; 2) v=HOLD;; *) v=ERR;; esac
    ok=1; [ "$merge" = "$em" ] || ok=0; [ "$v" = "$ev" ] || ok=0
    if [ $ok -eq 1 ]; then echo "${GREEN}PASS${NC} $name (merge=$merge validator=$v)"; else
      echo "${RED}FAIL${NC} $name (merge=$merge want $em; validator=$v want $ev)"; sed 's/^/      /' files/studio-a-0001.md; fi
    echo "$ok" > /tmp/case_ok )
  if [ "$(cat /tmp/case_ok)" = "1" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); fi
  rm -rf "$d"
}
base_ml() { cat <<'EOF'
---
uid: studio-a-0001
type: doctrine
title: The Shared Doctrine
owner: studio-a
status: draft
summary: |
  This doctrine supersedes the prior one.
  ---
  See the references below.
refs:
  - eca73d77
  - d61ce0a7
approvals: 7
---

Body paragraph.
EOF
}
base_note() { cat <<'EOF'
---
uid: studio-a-0001
type: doctrine
title: The Shared Doctrine
owner: studio-a
status: draft
note: "the string TROPO-FIELD-CONFLICT appears in this legit value"
---

Body paragraph.
EOF
}
append_ref_a() { sed -i.bak 's/^  - d61ce0a7/  - d61ce0a7\n  - aaaaaaaa/' "$1"; rm -f "$1.bak"; }
append_ref_b() { sed -i.bak 's/^  - d61ce0a7/  - d61ce0a7\n  - bbbbbbbb/' "$1"; rm -f "$1.bak"; }

# BREAK-1 CRITICAL: `---` inside a block scalar must NOT amputate fields → clean + VALID (refs/approvals survive)
run_custom "break1: --- inside block scalar" base_ml   set_status_done  retitle_x    clean VALID
# BREAK-2 HIGH: both append a different ref → element-wise list merge → clean + VALID (all items survive)
run_custom "break2: list append both sides"  base_ml   append_ref_a     append_ref_b clean VALID
# BREAK-3 LOW: a value containing the marker string must NOT false-HOLD → clean + VALID
run_custom "break3: value contains marker"   base_note set_status_done  set_owner_b  clean VALID

# ---- nav-divergence row (dev-spec 6ec30708 AC3: "extends test_corruption_suite.sh
# with a nav-divergence row, green") ----
# Proves Option A's actual claim: the derived Navigation block never reaches the
# object store the merge driver operates on, so two studios that each render their
# OWN (viewer-relative, necessarily-different) nav-block from their own composed
# index — the exact scenario that would otherwise be a merge-storm — see ZERO
# conflict on the nav region, because the shared bytes never carry it. This is a
# STRIPPED-COMMIT simulation of the clean filter (base/A/B are each committed with the
# region ALREADY absent, mirroring what `git add` under `.gitattributes filter=
# navblockstrip` produces) — the corruption suite itself has no `.gitattributes`
# filter-driver wiring to exercise (that machinery is Phase D2's merge driver, a
# DIFFERENT git mechanism from the clean filter this row proves against). If a nav
# region ever DID leak into the shared canonical (the Option-C failure this spec
# rejected), this same suite shape would show a real conflict — left as a documented,
# not run, negative case: re-adding a `nav-block:start`/`nav-block:end` pair with
# DIFFERING Siblings/Cited-by content on each side to `base_navdiverge` below
# reproduces exactly the false-conflict-on-derived-bytes failure Option A closes.
base_navdiverge() { cat <<'EOF'
---
uid: studio-a-0001
type: doctrine
title: The Shared Doctrine
status: draft
owner: studio-a
refs:
  - eca73d77
  - d61ce0a7
---

Paragraph one, the opening.

Paragraph two, the middle.

Paragraph three, the close.
EOF
}
# Each side's edit is what a LOCAL rebuild-vault render pass would do to ITS OWN
# working tree before the clean filter strips the region back out at `git add` time —
# i.e. each side independently regenerates a viewer-relative nav-block, then stages
# through the filter, so the STAGED/committed bytes this suite operates on never carry
# it (mirrors the already-proven git-boundary strip in
# vault/tools/tests/test_nav_blocks_out_6ec30708.py, not re-proven here).
edit_a_unrelated_body() { sed -i.bak 's/^Paragraph one.*/Paragraph one, edited by A (nav-divergence row)./' "$1"; rm -f "$1.bak"; }
edit_b_unrelated_body() { sed -i.bak 's/^Paragraph three.*/Paragraph three, edited by B (nav-divergence row)./' "$1"; rm -f "$1.bak"; }
run_custom "nav-divergence: viewer-relative renders never reach shared bytes" \
  base_navdiverge edit_a_unrelated_body edit_b_unrelated_body clean VALID

echo "=== $PASS passed, $FAIL failed ==="
[ $FAIL -eq 0 ]
