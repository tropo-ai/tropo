# Release Test-Report — mechanical layer (PASS)

- release_dir: `/Users/maz/git/tropo-releases/v1.88.0/builds/tropo-os-v1.88.0`
- mode: mechanical (deterministic regression; the guided stranger-walk is the playbook's other half)
- result: **11/11 checks passed**
- stats: {'index_rows': 487, 'uids': 487, 'version': 'v1.88.0', 'capsule_defs': 1}

| Check | Verdict | Detail |
|---|---|---|
| required files/dirs present | ✓ PASS | all present |
| index parses (every row valid JSON + uid/type) | ✓ PASS | 487 rows, 0 malformed |
| version stamped | ✓ PASS | version = v1.88.0 |
| capsule definitions ship | ✓ PASS | 1 capsule-definition entries in vault/files |
| MANIFEST present | ✓ PASS | MANIFEST.md |
| no private/reference-only content leaked | ✓ PASS | clean |
| .tropo/playbooks has at least one .md playbook | ✓ PASS | 18 playbooks |
| START-TROPO.md non-empty | ✓ PASS | 39 non-blank lines |
| tropo-validate.py present and non-empty | ✓ PASS | present (671874 bytes) |
| shipped Python lib import closure | ✓ PASS | 94 tools, 77 lib modules resolved |
| golden-output snapshot (not seeded — skip) | ✓ PASS | no expected-checks.json; seed with check names to activate |

