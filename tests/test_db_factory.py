import builtins
import os
import types
from unittest import mock

import pytest
import sys

from kinetiqo.db import factory


class DummyConfig:
    def __init__(self, database_type):
        self.database_type = database_type


def test_get_version_returns_dev_when_no_file(monkeypatch):
    # Ensure os.path.exists returns False for both candidates
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    assert factory.get_version() == "dev"


def test_get_version_reads_version_file(monkeypatch):
    # Simulate a version.txt existing in base dir and containing text
    sample_version = "1.2.3\n"

    def fake_exists(path):
        # Pretend the version.txt path exists
        if path.endswith("version.txt"):
            return True
        return False

    monkeypatch.setattr(os.path, "exists", fake_exists)

    mock_open = mock.mock_open(read_data=sample_version)
    monkeypatch.setattr(builtins, "open", mock_open)

    assert factory.get_version() == "1.2.3"


def _make_dummy_module(cls_name):
    mod = types.SimpleNamespace()
    # Create a simple class with the expected name that accepts (config)
    def __init__(self, config=None):
        self.config = config
    cls = type(cls_name, (), {"__init__": __init__})
    setattr(mod, cls_name, cls)
    return mod


@pytest.mark.parametrize(
    "db_type, mod_name, cls_name",
    [
        ("mysql", "kinetiqo.db.mysql", "MySQLRepository"),
        ("postgresql", "kinetiqo.db.postgresql", "PostgresqlRepository"),
        ("firebird", "kinetiqo.db.firebird", "FirebirdRepository"),
    ],
)
def test_create_repository_supported(monkeypatch, db_type, mod_name, cls_name):
    config = DummyConfig(db_type)

    # Inject a fake module into sys.modules so the factory's import succeeds
    dummy_mod = _make_dummy_module(cls_name)
    monkeypatch.setitem(sys.modules, mod_name, dummy_mod)

    repo = factory.create_repository(config)
    assert isinstance(repo, getattr(dummy_mod, cls_name))


def test_create_repository_unsupported_raises():
    config = DummyConfig("sqlite")
    with pytest.raises(ValueError):
        factory.create_repository(config)
