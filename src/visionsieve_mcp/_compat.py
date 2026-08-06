"""Compatibility helpers for the v1 public rename.

The hardened core remains in ``visual_evidence_gateway`` for the 1.0 release so
existing imports and installations keep working. New public entry points use
``VISIONSIEVE_CONFIG`` and mirror it into the legacy runtime variable before
loading the core.
"""
from __future__ import annotations

import os

CONFIG_ENV = "VISIONSIEVE_CONFIG"
LEGACY_CONFIG_ENV = "VISUAL_EVIDENCE_GATEWAY_CONFIG"


def bridge_config_env() -> None:
    new_value = os.environ.get(CONFIG_ENV)
    old_value = os.environ.get(LEGACY_CONFIG_ENV)
    if new_value and not old_value:
        os.environ[LEGACY_CONFIG_ENV] = new_value
    elif old_value and not new_value:
        os.environ[CONFIG_ENV] = old_value
