"""The project must not store data on the local machine unless told to."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph import config  # noqa: E402
from pitchgraph.data.statsbomb import StatsBomb  # noqa: E402


class _FakeResponse:
    status_code = 200
    content = '[{"name": "Atlético Madrid"}]'.encode("utf-8")

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self):
        self.calls = 0

    def get(self, url, timeout):
        self.calls += 1
        return _FakeResponse()


def test_default_loader_writes_nothing_to_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sb = StatsBomb()
    sb._session = _FakeSession()
    assert sb.competitions()[0]["name"] == "Atlético Madrid"
    assert list(tmp_path.rglob("*")) == [], "default loader must not create files"


def test_repeat_reads_are_served_from_memory():
    sb = StatsBomb()
    sb._session = fake = _FakeSession()
    sb.competitions(); sb.competitions()
    assert fake.calls == 1


def test_memory_cache_is_bounded():
    sb = StatsBomb(memory_items=2)
    sb._session = _FakeSession()
    for mid in range(5):
        sb.events(mid)
    assert len(sb._memory) == 2


def test_explicit_cache_dir_is_the_only_way_to_persist(tmp_path):
    sb = StatsBomb(cache_dir=tmp_path / "raw")
    sb._session = _FakeSession()
    sb.competitions()
    assert (tmp_path / "raw" / "competitions.json").exists()


def test_lake_refuses_to_run_without_a_configured_root(monkeypatch):
    monkeypatch.delenv(config.DATA_ENV, raising=False)
    assert config.data_root() is None
    with pytest.raises(RuntimeError):
        config.lake_dir()


def test_lake_lives_under_the_configured_root(monkeypatch, tmp_path):
    monkeypatch.setenv(config.DATA_ENV, str(tmp_path))
    assert config.lake_dir() == tmp_path / "lake"
