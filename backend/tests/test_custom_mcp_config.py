from pathlib import Path

from deerflow.config.custom_mcp_config import (
    get_custom_mcp_container_path,
    get_custom_mcp_host_path,
    get_custom_mcp_install_path,
)


def test_custom_mcp_host_path_prefers_environment_variable(monkeypatch):
    monkeypatch.setenv("DEER_FLOW_CUSTOM_MCP_SERVERS_HOST_PATH", "/tmp/runtime-mcp")

    assert get_custom_mcp_host_path() == Path("/tmp/runtime-mcp")


def test_custom_mcp_container_path_prefers_environment_variable(monkeypatch):
    monkeypatch.setenv("DEER_FLOW_CUSTOM_MCP_SERVERS_PATH", "/runtime/custom-mcp")

    assert get_custom_mcp_container_path() == "/runtime/custom-mcp"


def test_custom_mcp_container_path_defaults_to_app_directory(monkeypatch):
    monkeypatch.delenv("DEER_FLOW_CUSTOM_MCP_SERVERS_PATH", raising=False)

    assert get_custom_mcp_container_path() == "/app/custom-mcp-servers"


def test_custom_mcp_install_path_prefers_container_visible_path(monkeypatch):
    monkeypatch.setenv("DEER_FLOW_CUSTOM_MCP_SERVERS_PATH", "/app/custom-mcp-servers")

    assert get_custom_mcp_install_path() == Path("/app/custom-mcp-servers")


def test_custom_mcp_host_path_defaults_to_repo_relative_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("DEER_FLOW_CUSTOM_MCP_SERVERS_HOST_PATH", raising=False)
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    monkeypatch.chdir(backend_dir)

    assert get_custom_mcp_host_path() == tmp_path / "custom-mcp-servers"


def test_custom_mcp_install_path_falls_back_to_host_path_when_container_path_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("DEER_FLOW_CUSTOM_MCP_SERVERS_PATH", raising=False)
    monkeypatch.delenv("DEER_FLOW_CUSTOM_MCP_SERVERS_HOST_PATH", raising=False)
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    monkeypatch.chdir(backend_dir)

    assert get_custom_mcp_install_path() == tmp_path / "custom-mcp-servers"
