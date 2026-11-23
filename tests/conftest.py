import pytest


@pytest.fixture(autouse=True)
def isolate_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
