"""VisionSieve image-probe entry point."""
from __future__ import annotations

from typing import Optional

from visionsieve_mcp._compat import bridge_config_env


def main(argv: Optional[list[str]] = None) -> int:
    bridge_config_env()
    from visual_evidence_gateway.probe import main as core_main

    return int(core_main(argv) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
