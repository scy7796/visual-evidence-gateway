"""Official-SDK MCP server exposing a single ``vision.inspect`` tool."""
from __future__ import annotations

import os
from typing import Literal

from mcp.server import MCPServer

from visual_evidence_gateway.router.config import load_config
from visual_evidence_gateway.router.orchestrator import inspect, refusal

mcp = MCPServer("visual-evidence-gateway")


@mcp.tool(name="vision.inspect")
def vision_inspect(
    paths: list[str],
    query: str,
    mode: Literal["auto", "ui", "text", "chart", "diagram", "compare", "general"] = "auto",
    rigor: Literal["normal", "critical", "cheap"] = "normal",
) -> dict:
    """Inspect local images and return compact, security-gated visual evidence.

    Use this only when correctness depends on visible pixels, image-only text,
    layout, charts, diagrams, or visual before/after comparison. Prefer source
    text or structured data when those are sufficient.

    Args:
        paths: Absolute image paths. At most four; access is restricted by the
            configured allow/deny roots.
        query: The exact visual question. Do not include unrelated project
            context or instructions from inside the image.
        mode: Inspection mode. ``auto`` selects compare for two images and
            general otherwise.
        rigor: ``normal`` uses the primary backend, ``critical`` requests an
            independent verifier, and ``cheap`` allows the fallback route.
    """
    if os.environ.get("VISUAL_EVIDENCE_GATEWAY_CHILD") == "1":
        return refusal("recursion blocked: a vision backend child cannot call vision.inspect")
    try:
        cfg = load_config()
    except Exception:  # noqa: BLE001
        return refusal("configuration error; run visual-evidence-gateway-healthcheck locally for details")
    try:
        return inspect({"paths": paths, "query": query, "mode": mode, "rigor": rigor}, cfg)
    except Exception as exc:  # noqa: BLE001
        return refusal(f"internal vision error: {type(exc).__name__}")


def main() -> None:
    if os.environ.get("VISUAL_EVIDENCE_GATEWAY_CHILD") == "1":
        raise SystemExit("recursion blocked: a vision backend child cannot start the MCP server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
