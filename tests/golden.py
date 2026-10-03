"""Regression comparison of two delivery run packages (golden vs candidate).

A behaviour-preserving change must reproduce every substantive output exactly. Only
execution metadata (``run_metadata.json``) and identity-bearing strings may differ:
the run ID, stage identity, derived validation ID, model-code hashes and the absolute
project root. Each is replaced by a placeholder before comparison; nothing is skipped
by file name except ``run_metadata.json``.

Usage: ``python tests/golden.py <golden_run_dir> <candidate_run_dir>``
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

EXECUTION_METADATA = {'run_metadata.json'}
# Root-level counters documented as execution diagnostics in the Phase 7 audit.
DIAGNOSTIC_KEYS = {'processed_tiles', 'resumed_tiles'}


def _root_of(meta):
    grid = Path(meta['configured_grid']['path'])
    relative = Path(meta['configuration']['grid_path'])
    if grid.parts[-len(relative.parts):] != relative.parts:
        raise ValueError('Cannot infer project root from run metadata')
    return str(Path(*grid.parts[:-len(relative.parts)]))


def identity_tokens(folder: Path) -> dict[str, str]:
    """Strings that legitimately differ between code revisions or project roots."""
    meta = json.loads((folder / 'run_metadata.json').read_text(encoding='utf-8'))
    tokens = {meta['stage_identity']: '<STAGE_IDENTITY>', meta['run_id']: '<RUN_ID>'}
    validation_id = meta.get('source_coverage_and_checks', {}).get('validation_report', {}).get('validation_id')
    if validation_id:
        tokens[validation_id] = '<VALIDATION_ID>'
    for name, sha in meta.get('actual_working_code_sha256', {}).items():
        tokens[sha] = f'<CODE:{Path(name).as_posix()}>'
    # Resumable tile cache keys hash the geography code revision and absolute source paths.
    core_manifest = folder / 'geography_core' / 'data_manifest.json'
    if core_manifest.is_file():
        for key in json.loads(core_manifest.read_text(encoding='utf-8')).get('tile_keys', []):
            tokens[key] = '<TILE_KEY>'
    # Digest of the validation input binding, which embeds the identities above.
    sensitivity = folder / 'sensitivity_results.parquet'
    texts = [p.read_text(encoding='utf-8') for p in folder.rglob('*.json') if p.name not in EXECUTION_METADATA]
    if sensitivity.is_file() and 'case_assumptions_json' in pq.read_schema(sensitivity).names:
        texts += [v for v in pq.read_table(sensitivity, columns=['case_assumptions_json']).column(0).to_pylist() if v]
    for text in texts:
        for value in re.findall(r'input_binding_sha256\\?"\s*:\s*\\?"([0-9a-f]{64})', text):
            tokens[value] = '<INPUT_BINDING>'
    root = _root_of(meta)
    for form in (root, root.replace('\\', '/'), root.replace('\\', '\\\\')):
        tokens[form] = '<ROOT>'
    return dict(sorted(tokens.items(), key=lambda item: -len(item[0])))


def _replace(text: str, tokens: dict[str, str]) -> str:
    for old, new in tokens.items():
        text = text.replace(old, new)
    return re.sub(r'<ROOT>[\\/]', '<ROOT>/', text)


def _normalize_json(value, tokens):
    if isinstance(value, dict):
        return {_replace(k, tokens): _normalize_json(v, tokens) for k, v in value.items() if k not in DIAGNOSTIC_KEYS}
    if isinstance(value, list):
        return [_normalize_json(v, tokens) for v in value]
    if isinstance(value, str):
        return _replace(value, tokens).replace('\\', '/')
    return value


def _parquet_frame(path: Path, tokens):
    table = pq.read_table(path)
    meta = {k.decode(): _replace(v.decode(), tokens) for k, v in (table.schema.metadata or {}).items()}
    frame = table.to_pandas()
    for column in frame.columns:
        if frame[column].dtype == object:
            frame[column] = frame[column].map(lambda v: _replace(v, tokens).replace('\\', '/') if isinstance(v, str) else v)
    return frame, meta, [str(f.type) for f in table.schema]


def compare_file(relative: str, golden: Path, candidate: Path, gt, ct) -> str | None:
    a, b = golden / relative, candidate / relative
    if a.read_bytes() == b.read_bytes():
        return None
    suffix = a.suffix.lower()
    if suffix == '.parquet':
        (fa, ma, ta), (fb, mb, tb) = _parquet_frame(a, gt), _parquet_frame(b, ct)
        if ta != tb:
            return f'column types differ: {ta} vs {tb}'
        if ma != mb:
            keys = sorted(k for k in set(ma) | set(mb) if ma.get(k) != mb.get(k))
            return f'schema metadata differs: {keys}'
        if list(fa.columns) != list(fb.columns) or len(fa) != len(fb):
            return f'shape/columns differ: {fa.shape} vs {fb.shape}'
        if not fa.equals(fb):
            bad = [c for c in fa.columns if not fa[c].equals(fb[c])]
            return f'values differ in columns {bad[:8]}'
        return None
    if suffix in {'.json', '.geojson'}:
        ja = _normalize_json(json.loads(a.read_text(encoding='utf-8')), gt)
        jb = _normalize_json(json.loads(b.read_text(encoding='utf-8')), ct)
        if relative.startswith('stage_manifests/'):
            # Output hashes are re-checked file by file below; keys must still match.
            ja['output_hashes'] = sorted(ja['output_hashes']); jb['output_hashes'] = sorted(jb['output_hashes'])
        return None if ja == jb else 'JSON content differs'
    ta, tb = _replace(a.read_text(encoding='utf-8'), gt), _replace(b.read_text(encoding='utf-8'), ct)
    if ta.replace('\\', '/') == tb.replace('\\', '/'):
        return None
    la, lb = ta.splitlines(), tb.splitlines()
    first = next((i for i, (x, y) in enumerate(zip(la, lb)) if x != y), min(len(la), len(lb)))
    return f'text differs at line {first + 1}'


def compare_runs(golden: Path, candidate: Path) -> dict:
    golden, candidate = Path(golden), Path(candidate)
    gt, ct = identity_tokens(golden), identity_tokens(candidate)
    files_a = {p.relative_to(golden).as_posix() for p in golden.rglob('*') if p.is_file()} - EXECUTION_METADATA
    files_b = {p.relative_to(candidate).as_posix() for p in candidate.rglob('*') if p.is_file()} - EXECUTION_METADATA
    differences = {name: compare_file(name, golden, candidate, gt, ct) for name in sorted(files_a & files_b)}
    differences = {k: v for k, v in differences.items() if v}
    return {'compared': len(files_a & files_b), 'missing_in_candidate': sorted(files_a - files_b),
            'extra_in_candidate': sorted(files_b - files_a), 'differences': differences,
            'identical': not differences and files_a == files_b}


if __name__ == '__main__':
    result = compare_runs(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['identical'] else 1)
