# Release Test-Report — mechanical layer (PASS)

- release_dir: `tropo-os-v1.93.0` (basename only — this file ships)
- mode: mechanical (deterministic regression; the guided stranger-walk is the playbook's other half)
- result: **12/12 checks passed**
- stats: {'index_rows': 496, 'uids': 496, 'version': 'v1.93.0', 'capsule_defs': 1}

| Check | Verdict | Detail |
|---|---|---|
| required files/dirs present | ✓ PASS | all present |
| index parses (every row valid JSON + uid/type) | ✓ PASS | 496 rows, 0 malformed |
| version stamped | ✓ PASS | version = v1.93.0 |
| capsule definitions ship | ✓ PASS | 1 capsule-definition entries in vault/files |
| MANIFEST present | ✓ PASS | MANIFEST.md |
| no private/reference-only scope leaked into vault/files | ✓ PASS | clean |
| no maintainer machine paths in the box | ✓ PASS | clean |
| .tropo/playbooks has at least one .md playbook | ✓ PASS | 18 playbooks |
| START-TROPO.md non-empty | ✓ PASS | 66 non-blank lines |
| tropo-validate.py present and non-empty | ✓ PASS | present (747528 bytes) |
| shipped Python lib import closure | ✓ PASS | 109 tools, 91 lib modules resolved |
| golden-output snapshot (not seeded — skip) | ✓ PASS | no expected-checks.json; seed with check names to activate |

