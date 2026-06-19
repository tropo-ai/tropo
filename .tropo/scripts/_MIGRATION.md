# .tropo/scripts/ → vault/tools/ Migration (v1.56.0)

All governed tool scripts have moved to `vault/tools/<uid>.py` per tool.capsule v1.6 §2.5
single-file-truth pattern. This folder now contains:

- **Compatibility forwarders** (`tropo-validate.py`, `rebuild-vault.py`, etc.) — thin shims
  that forward to `vault/tools/<uid>.py`. These keep old invocation paths working during
  the v1.56 → v1.57 transition.
- **Library modules** (`_yaml_dup_lib.py`, `docx_styles_bundle.py`, `publish_types.py`) — shared
  modules imported by vault/tools/ scripts. These stay here.
- **Publish targets** (`publish_targets/`) — target-specific implementation modules. Stays here.
- **Lib validators** (`lib/`) — validator library modules. Stays here.
- **Test fixtures** (`test_*.py`) — regression tests. Stays here.

## Canonical invocation after v1.56

| Old path | New path | UID |
|---|---|---|
| `.tropo/scripts/tropo-validate.py` | `vault/tools/d2b9c8e6.py` | d2b9c8e6 |
| `.tropo/scripts/rebuild-vault.py` | `vault/tools/e8d4c1b9.py` | e8d4c1b9 |
| `.tropo/scripts/rebuild-index.py` | `vault/tools/f4b8a6e2.py` | f4b8a6e2 |
| `.tropo/scripts/pipeline-activate.py` | `vault/tools/e337f1dd.py` | e337f1dd |
| `.tropo/scripts/pipeline-runtime.py` | `vault/tools/9e7003b1.py` | 9e7003b1 |
| `.tropo/scripts/publish.py` | `vault/tools/2e642578.py` | 2e642578 |
| `.tropo/scripts/tropo-recycle.py` | `vault/tools/2573f6dd.py` | 2573f6dd |
| `.tropo/scripts/write-activation-entry.py` | `vault/tools/40b2f455.py` | 40b2f455 |
| `.tropo/scripts/vault-search.py` | `vault/tools/943149d4.py` | 943149d4 |
| `.tropo/scripts/build-web-content.py` | `vault/tools/11f3ebd4.py` | 11f3ebd4 |

v1.57+ text sweep (capsules + playbooks + how-tos) to replace `.tropo/scripts/<name>.py`
references with `vault/tools/<uid>.py` canonical paths per R5 deferral pattern.

Authored: 2026-05-27 by talos-t10 (v1.56 Lane S)
