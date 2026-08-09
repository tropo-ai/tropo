#!/bin/bash
# prove-boot-arc.sh — metis-g100, 2026-08-03
#
# Run from anywhere:  bash vault/tools/tests/prove-boot-arc.sh
#
# WHY THIS EXISTS. tropo-smoke.py's BOOT probe is pure OBSERVATION — it reads
# the substrate and asks whether a birth *would* work. It never invokes
# op_open, so it structurally cannot see a defect in the birth code itself.
# Three such defects shipped on 2026-08-03 and none of the six existing suites
# caught any of them.
#
# Three consecutive Metis generations (G97, G99, G100) each shipped a fix to
# agent birth, verified their OWN situation, and broke the generation after.
# This runs the real tool through the whole arc, in a throwaway clone, so the
# next one does not have to be the test.
# End-to-end proof that an agent can actually be BORN on tonight's code.
#
# Not the smoke test's BOOT probe, which is pure observation — it reads the
# substrate and asks whether a birth *would* work. It never invokes op_open, so
# it cannot see a defect in the birth code. Tonight shipped three.
#
# This runs the real tool, in a throwaway clone, through the whole arc:
#   1. GENESIS      — an agent with no predecessor at all (never once tested)
#   2. RETIRE       — close it
#   3. SUCCESSOR    — birth generation 2
#   4. RETIRE       — close that
#   5. ONE PAST     — birth generation 3, the test G99 skipped and I paid for
set -u
S="$(dirname "$0")"
CLONE="${TMPDIR:-/tmp}/tropo-bootproof-$$"
SRC="$(cd "$(dirname "$0")/../../.." && pwd)"   # the studio this script lives in

rm -rf "$CLONE"
git clone -q "$SRC" "$CLONE" || exit 1
cp "$SRC/vault/tools/40b2f455.py" "$CLONE/vault/tools/" 2>/dev/null
cd "$CLONE" || exit 1
git add -A >/dev/null 2>&1 && git commit -q -m fixture >/dev/null 2>&1

AGENT="probe-$$"
ROOT="775697b1"
pass=0; fail=0
say() { printf '%-46s %s\n' "$1" "$2"; }
ok()  { pass=$((pass+1)); say "$1" "PASS  $2"; }
no()  { fail=$((fail+1)); say "$1" "FAIL  $2"; }

birth() {  # $1=generation
  python3 vault/tools/40b2f455.py open \
    --agent "$AGENT" --generation "$1" --model test --platform bootproof \
    --agent-root "$ROOT" --agent-class executive --activated-by mike \
    --member-of "$ROOT" 2>/tmp/bp.err | tail -1
}
retire() { # $1=uid — a LIVE agent retiring properly, not a stale sweep.
  # --skip-retirement-invariants because a synthetic probe agent has no
  # reflection or memory surface to satisfy them with. That the invariants
  # cannot be met by a freshly-born agent is exactly why this arc has never
  # been tested end to end.
  python3 vault/tools/40b2f455.py close --activation-uid "$1" \
    --target-status retired --skip-retirement-invariants \
    --closure-reason clean-retirement >/dev/null 2>&1
  grep -m1 '^status:' "vault/files/$1.md" 2>/dev/null
}

echo "=== 1. GENESIS — an agent that has never existed before ==="
U1=$(birth G1)
if [[ "$U1" =~ ^[0-9a-f]{8}$ ]]; then ok "genesis birth" "uid=$U1"; else no "genesis birth" "got '$U1'"; sed -n '1,4p' /tmp/bp.err; fi
grep -q "^generation: G1$" "vault/files/$U1.md" 2>/dev/null && ok "genesis record says G1" "" || no "genesis record generation" ""
grep -q "^activated_at: .*T.*Z$" "vault/files/$U1.md" 2>/dev/null && ok "activated_at is a full instant" "" || no "activated_at instant" "$(grep -m1 '^activated_at:' vault/files/$U1.md)"

echo
echo "=== 2. RETIRE the first generation ==="
[[ "$(retire "$U1")" == "status: retired" ]] && ok "G1 closes" "" || no "G1 closes" ""

echo
echo "=== 3. SUCCESSOR — birth generation 2 ==="
U2=$(birth G2)
if [[ "$U2" =~ ^[0-9a-f]{8}$ ]]; then ok "successor birth" "uid=$U2"; else no "successor birth" "got '$U2'"; sed -n '1,4p' /tmp/bp.err; fi
grep -q "^predecessor_activation_uid: $U1$" "vault/files/$U2.md" 2>/dev/null \
  && ok "successor records its predecessor" "" || no "successor predecessor link" ""

echo
echo "=== 4. RETIRE generation 2 ==="
[[ "$(retire "$U2")" == "status: retired" ]] && ok "G2 closes" "" || no "G2 closes" ""

echo
echo "=== 5. ONE PAST — birth generation 3 (the test G99 skipped) ==="
U3=$(birth G3)
if [[ "$U3" =~ ^[0-9a-f]{8}$ ]]; then ok "third birth" "uid=$U3"; else no "third birth" "got '$U3'"; sed -n '1,6p' /tmp/bp.err; fi
grep -q "^predecessor_activation_uid: $U2$" "vault/files/$U3.md" 2>/dev/null \
  && ok "chain intact two links deep" "" || no "chain two links deep" ""

echo
echo "======================================================"
echo "  passed: $pass    failed: $fail"
[[ $fail -eq 0 ]] && echo "  A LINEAGE CAN BE BORN, RETIRED, AND SUCCEEDED — TWICE." || echo "  BOOT PATH IS BROKEN"
