"""Test fixture for check_mint_id_chokepoint (796d9330) — planted UID bypass.
Deleted immediately after the adversarial test runs; should never survive on disk.
"""
import secrets

def bogus_mint():
    return secrets.token_hex(4)
