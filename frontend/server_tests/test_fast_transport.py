"""Exact-byte cached transport and HTTP compression negotiation."""
import copy
import gzip
import io
import json
import shutil
from pathlib import Path

import pytest

from frontend.server.app import make_handler
from frontend.server.serialization import ApiError, ArtifactReader, json_bytes

ROOT = Path(__file__).resolve().parents[2]
ACCEPTED = ROOT/'runs/phase7/root_v2_exploratory'


def test_cached_wire_bytes_skip_json_decoding_and_serialization(tmp_path, monkeypatch):
    reader=ArtifactReader(tmp_path/'responses')
    payload={'schema_version':'1.4.0','transport_fixture':'x'*2048,'unknown':None}
    monkeypatch.setattr(reader,'_serialize_run',lambda *args:copy.deepcopy(payload))
    reader.run(ACCEPTED)
    other=ArtifactReader(reader.cache_root)
    monkeypatch.setattr(other,'_serialize_run',lambda *args:pytest.fail('Cached response serialized again'))
    import frontend.server.serialization as module
    original=module.read_json
    def no_cached_decode(path, fallback=None):
        if path.parent==other.cache_root:
            pytest.fail('Cached wire bytes decoded into a second object tree')
        return original(path,fallback)
    monkeypatch.setattr(module,'read_json',no_cached_decode)
    assert other.run_bytes(ACCEPTED)==json_bytes(payload)


def test_cold_wire_bytes_are_canonical_with_nulls(tmp_path,monkeypatch):
    reader=ArtifactReader(tmp_path/'responses')
    payload={'schema_version':'1.4.0','unknown':float('nan')}
    calls=[]
    monkeypatch.setattr(reader,'_serialize_run',lambda *args:calls.append(args) or payload)
    result=reader.run_bytes(ACCEPTED)
    assert result==json_bytes(payload)
    assert json.loads(result)['unknown'] is None
    assert reader.run_bytes(ACCEPTED)==result and len(calls)==1


def test_wire_cache_rejects_removed_required_artifact(tmp_path,monkeypatch):
    run=tmp_path/'run'
    shutil.copytree(ACCEPTED,run)
    reader=ArtifactReader(tmp_path/'responses')
    monkeypatch.setattr(reader,'_serialize_run',lambda *args:{'unknown':None})
    reader.run_bytes(run)
    (run/'candidate_regions.geojson').unlink()
    with pytest.raises(ApiError,match='missing required result artifacts'):
        reader.run_bytes(run)


def test_wire_cache_rechecks_content_identity(tmp_path,monkeypatch):
    run=tmp_path/'run'
    shutil.copytree(ACCEPTED,run)
    reader=ArtifactReader(tmp_path/'responses')
    calls=[]
    monkeypatch.setattr(reader,'_serialize_run',lambda *args:calls.append(args) or {'revision':len(calls),'unknown':None})
    first=reader.run_bytes(run)
    artifact=run/'screening_summary.json'
    old=artifact.read_bytes()
    # Preserve size and timestamps: content hashing must still invalidate the response.
    stat=artifact.stat()
    changed=old.replace(b'PASS',b'PAss',1)
    assert changed!=old and len(changed)==len(old)
    artifact.write_bytes(changed)
    import os
    os.utime(artifact,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    assert reader.run_bytes(run)!=first and len(calls)==2


def captured_response(body,accept_encoding,content_type='application/json; charset=utf-8'):
    Handler=make_handler(None)
    handler=object.__new__(Handler)
    handler.headers={'Accept-Encoding':accept_encoding,'Origin':'http://localhost:5173'}
    handler.wfile=io.BytesIO()
    headers={}
    handler.send_response=lambda status:None
    handler.send_header=lambda name,value:headers.__setitem__(name,value)
    handler.end_headers=lambda:None
    handler._send(body,content_type=content_type)
    return headers,handler.wfile.getvalue()


@pytest.mark.parametrize('encoding',['gzip','br, gzip, deflate','gzip;q=0.5','*;q=1'])
def test_large_json_compression_preserves_exact_bytes(encoding):
    body=json_bytes({'transport_fixture':'repeat '*500,'unknown':None})
    headers,compressed=captured_response(body,encoding)
    assert headers.get('Content-Encoding')=='gzip'
    assert gzip.decompress(compressed)==body and len(compressed)<len(body)
    assert int(headers['Content-Length'])==len(compressed)
    assert 'Accept-Encoding' in headers['Vary'] and 'Origin' in headers['Vary']


@pytest.mark.parametrize('encoding',['','br','gzip;q=0','gzip;q=0, *;q=1','gzip;q=invalid'])
def test_encoding_without_accepted_gzip_retains_exact_bytes(encoding):
    body=json_bytes({'transport_fixture':'repeat '*500,'unknown':None})
    headers,sent=captured_response(body,encoding)
    assert 'Content-Encoding' not in headers and sent==body


def test_small_json_and_binary_downloads_skip_compression():
    for body,kind in [(b'{"unknown":null}','application/json'),(b'x'*4096,'application/octet-stream')]:
        headers,sent=captured_response(body,'gzip',kind)
        assert 'Content-Encoding' not in headers and sent==body


def test_region_evidence_lookup_does_not_rescan_grid_columns(tmp_path,monkeypatch):
    import pandas as pd
    reader=ArtifactReader(tmp_path/'responses')
    expected=reader._serialize_run(ACCEPTED,ACCEPTED,'current')
    original=pd.Series.__eq__
    comparisons=[]
    def recorded(series,other):
        import inspect
        caller=inspect.currentframe().f_back
        if series.name=='grid_id' and caller.f_code.co_name=='_serialize_run':
            comparisons.append(len(series))
        return original(series,other)
    monkeypatch.setattr(pd.Series,'__eq__',recorded)
    actual=reader._serialize_run(ACCEPTED,ACCEPTED,'current')
    assert json_bytes(actual)==json_bytes(expected)
    assert not comparisons,'Region evidence must use keyed lookups, without repeated full-column scans'
