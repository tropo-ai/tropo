# Release Test-Report — mechanical layer (PASS)

- release_dir: `/Users/mike/dev/tropo-releases/v1.73.0/builds/tropo-os-v1.73.0`
- mode: mechanical (deterministic regression; the guided stranger-walk is the playbook's other half)
- result: **6/6 checks passed**
- stats: {'index_rows': 413, 'uids': 400, 'version': 'v1.73.0', 'capsules': 63}

| Check | Verdict | Detail |
|---|---|---|
| required files/dirs present | ✓ PASS | all present |
| index parses (every row valid JSON + uid/type) | ✓ PASS | 413 rows, 0 malformed |
| version stamped | ✓ PASS | version = v1.73.0 |
| capsule definitions ship | ✓ PASS | 63 capsules |
| MANIFEST present | ✓ PASS | MANIFEST.md |
| no private/reference-only content leaked | ✓ PASS | clean |

