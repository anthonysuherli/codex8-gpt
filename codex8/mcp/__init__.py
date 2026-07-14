"""MCP surface for the local Codex8 engine.

An in-process FastMCP stdio server resolves project and KB names locally and
drains the same engine through the Store seam. It exposes four tools: resume,
search, explore, and projects.
"""

from __future__ import annotations
