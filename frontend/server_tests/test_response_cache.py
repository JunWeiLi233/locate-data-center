"""Operational response-cache bounds; padded transport fixtures are not model evidence."""
from pathlib import Path

import pytest

from frontend.server.serialization import ArtifactReader, SCHEMA_VERSION, json_bytes

ROOT = Path(__file__).resolve().parents[2]
ACCEPTED = ROOT / "runs/phase7/root_v2_exploratory"
MIB = 1024 * 1024


def padded_response(byte_count):
    payload = {"schema_version": SCHEMA_VERSION, "transport_fixture_padding": "", "unknown": None}
    payload["transport_fixture_padding"] = "x" * (byte_count - len(json_bytes(payload)))
    return payload


@pytest.mark.parametrize("byte_count", [17 * MIB, 64 * MIB])
def test_large_bounded_response_is_reused_by_a_distinct_reader(tmp_path, monkeypatch, byte_count):
    reader = ArtifactReader(tmp_path / "responses")
    payload = padded_response(byte_count)
    calls = []
    def serialize(*args):
        calls.append(args)
        return payload
    monkeypatch.setattr(reader, "_serialize_run", serialize)
    first = reader.run(ACCEPTED)
    cached_files = list(reader.cache_root.glob("*.json"))
    assert len(cached_files) == 1, "Bounded regional-size responses must survive a new reader"
    assert cached_files[0].stat().st_size == byte_count
    assert cached_files[0].read_bytes() == json_bytes(first)

    other = ArtifactReader(reader.cache_root)
    def must_reuse(*args):
        pytest.fail("A new reader must reuse the checksum-bound durable response")
    monkeypatch.setattr(other, "_serialize_run", must_reuse)
    second = other.run(ACCEPTED)
    assert json_bytes(second) == cached_files[0].read_bytes()
    assert second["unknown"] is None and second["schema_version"] == SCHEMA_VERSION
    assert len(calls) == 1


def test_response_over_64_mib_is_not_written_to_durable_cache(tmp_path, monkeypatch):
    reader = ArtifactReader(tmp_path / "responses")
    payload = padded_response(64 * MIB + 1)
    calls = []
    def serialize(*args):
        calls.append(args)
        return payload
    monkeypatch.setattr(ArtifactReader, "_serialize_run", lambda self, *args: serialize(*args))
    first = reader.run(ACCEPTED)
    assert reader.run(ACCEPTED) is first, "Existing bounded memory caching remains available"
    assert not list(reader.cache_root.glob("*.json"))
    second = ArtifactReader(reader.cache_root).run(ACCEPTED)
    assert second == first and len(calls) == 2
    assert not list(reader.cache_root.glob("*.json"))
