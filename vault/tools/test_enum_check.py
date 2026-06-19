import sys
from pathlib import Path

vault_root = Path(".").resolve()
sys.path.append(str(vault_root / "vault" / "tools"))

from d2b9c8e6 import check_enforced_enum_compliance

findings, checked, warns, norms = check_enforced_enum_compliance(vault_root)

print(f"Checked: {checked}, Warns: {warns}, Norms: {norms}")
for f in findings:
    if "WARN" in f:
        print(f)
