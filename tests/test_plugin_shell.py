from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = ("resume", "search", "explore", "projects")


def test_skills_have_frontmatter_and_name_the_mcp_tool():
    for s in SKILLS:
        text = (REPO / "skills" / s / "SKILL.md").read_text()
        assert text.startswith("---\n")
        frontmatter = text.split("---", 2)[1]
        assert f"name: codex8-{s}" in frontmatter
        assert "description:" in frontmatter
        assert f"codex8_{s}" in text  # each skill names its MCP tool


def _install(codex_home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(REPO / "install.sh")],
        env={**os.environ, "CODEX_HOME": str(codex_home)},
        capture_output=True,
        text=True,
        check=True,
    )


def test_installer_registers_server_and_links_skills(tmp_path):
    out = _install(tmp_path)
    assert "registered [mcp_servers.codex8]" in out.stdout
    config = (tmp_path / "config.toml").read_text()
    assert config.count("[mcp_servers.codex8]") == 1
    assert f'command = "{REPO}/.venv/bin/python"' in config
    assert '"codex8.mcp.server"' in config
    for s in SKILLS:
        link = tmp_path / "skills" / f"codex8-{s}"
        assert link.is_symlink()
        assert link.resolve() == (REPO / "skills" / s).resolve()


def test_installer_is_idempotent(tmp_path):
    _install(tmp_path)
    second = _install(tmp_path)
    assert "leaving it untouched" in second.stdout
    config = (tmp_path / "config.toml").read_text()
    assert config.count("[mcp_servers.codex8]") == 1
