"""Codex8 wordmark — the banner that leads the resume surface.

Keeping it here (not inside ``select_preamble``) keeps the public preamble XML
clean — the banner is a conversation-surface concern only.
"""

from __future__ import annotations

CODEX8_BANNER = """\\
        ╱──
──────◌
        ╲──
   c o d e x 8
   knowledge, tapped"""
