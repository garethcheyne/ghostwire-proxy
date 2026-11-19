"""Lets the tests import the `updater` package from updater/ (run with: cd updater && python -m pytest tests)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A checkout and a Docker socket for start_upgrade_container to stat."""
    from updater import main

    (tmp_path / ".git").mkdir()
    (tmp_path / "upgradeGhostwireProxy.sh").write_text("#!/usr/bin/env bash\n")
    socket = tmp_path / "docker.sock"
    socket.write_text("")
    monkeypatch.setattr(main, "COMPOSE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(main, "DOCKER_SOCKET", str(socket))
    monkeypatch.setattr(main, "UPGRADE_POLL_SECONDS", 0)
    return tmp_path
