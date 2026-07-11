# Release Test-Report — mechanical layer (PASS)

- release_dir: `/Users/mike/git/tropo-releases/v1.84.1/builds/tropo-os-v1.84.1`
- mode: mechanical (deterministic regression; the guided stranger-walk is the playbook's other half)
- result: **10/10 checks passed**
- stats: {'index_rows': 517, 'uids': 517, 'version': 'v1.84.1', 'capsule_defs': 1}

| Check | Verdict | Detail |
|---|---|---|
| required files/dirs present | ✓ PASS | all present |
| index parses (every row valid JSON + uid/type) | ✓ PASS | 517 rows, 0 malformed |
| version stamped | ✓ PASS | version = v1.84.1 |
| capsule definitions ship | ✓ PASS | 1 capsule-definition entries in vault/files |
| MANIFEST present | ✓ PASS | MANIFEST.md |
| no private/reference-only content leaked | ✓ PASS | clean |
| .tropo/playbooks has at least one .md playbook | ✓ PASS | 18 playbooks |
| START-TROPO.md non-empty | ✓ PASS | 27 non-blank lines |
| tropo-validate.py present and non-empty | ✓ PASS | present (544095 bytes) |
| golden-output snapshot (not seeded — skip) | ✓ PASS | no expected-checks.json; seed with check names to activate |

