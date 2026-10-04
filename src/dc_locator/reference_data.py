"""Public Cleanview listing samples for external comparison, never model features.

Only rendered listing headings, summary cards, and ``largest-operating`` cards
are read. Script payloads, map APIs, paid detail fields, and coordinates are not
used. These capacity-selected samples are incomplete commercial observations.

React's server-streamed public listing initially has a hidden ``S:n`` wrapper
paired with a visible ``B:n`` template placeholder. Browser inspection confirms
the public listings become visible after hydration. Only these paired markup
wrappers are admitted; their scripts and every other hidden node are excluded.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
from threading import Lock
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import pandas as pd

from .geography.sources.ingestion import PROJECT_MAX_BYTES, USER_AGENT, file_digest


NATIONAL_URL = "https://cleanview.co/data-centers/us"
SOURCE_ID = "cleanview_reference"
LICENSE_NOTE = (
    "Commercial copyrighted public listing; comparison-only reference. "
    "No open-data license established; public visibility is not a reuse license."
)
SELECTION_BIAS = "top_capacity_sample"
CONUS_STATE_NAMES = frozenset({
    "Alabama", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "District of Columbia", "Florida", "Georgia", "Idaho", "Illinois",
    "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland",
    "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana",
    "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
    "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah",
    "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
})
_DETAIL_PATH = re.compile(r"^/data-centers/[^/]+/(\d+)/[^/]+/?$")
_STATE_PATH = re.compile(r"^/data-centers/[^/]+/?$")
_UNKNOWN = frozenset({"", "n/a", "na", "unknown", "tbd", "not available", "—", "-"})
_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input",
                   "link", "meta", "param", "source", "track", "wbr"})


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    content: list[Any] = field(default_factory=list)
    excluded: bool = False

    def text(self) -> str:
        return " ".join(" ".join(
            item if isinstance(item, str) else item.text() for item in self.content
        ).split())

    def descendants(self, tag: str | None = None):
        for item in self.content:
            if isinstance(item, _Node):
                if tag is None or item.tag == tag:
                    yield item
                yield from item.descendants(tag)


class _PublicHTML(HTMLParser):
    """Discard payloads and hidden nodes, retaining paired streamed public markup."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack = [self.root]
        self.public_stream_ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        style = re.sub(r"\s+", "", attributes.get("style") or "").lower()
        placeholder = re.fullmatch(r"B:(\d+)", attributes.get("id") or "")
        if tag == "template" and placeholder and not self.stack[-1].excluded:
            self.public_stream_ids.add(placeholder.group(1))
        streamed = re.fullmatch(r"S:(\d+)", attributes.get("id") or "")
        public_stream = tag == "div" and streamed and streamed.group(1) in self.public_stream_ids
        excluded = (
            self.stack[-1].excluded or tag in {"head", "script", "style", "template"}
            or ("hidden" in attributes and not public_stream) or attributes.get("aria-hidden") == "true"
            or "display:none" in style or "visibility:hidden" in style
        )
        node = _Node(tag, attributes, excluded=excluded)
        if not excluded:
            self.stack[-1].content.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if not self.stack[-1].excluded:
            self.stack[-1].content.append(data)


def _public_url(href: str, page_url: str) -> str | None:
    parsed = urlparse(urljoin(page_url, href))
    if parsed.scheme != "https" or parsed.netloc != "cleanview.co":
        return None
    if parsed.query or parsed.fragment:
        return None
    return parsed.geturl().rstrip("/")


def _null_text(text: Any) -> str | None:
    if text is None or pd.isna(text):
        return None
    value = " ".join(str(text).split())
    return None if value.casefold() in _UNKNOWN else value


def _count(text: str) -> int | None:
    compact = text.replace(",", "").strip()
    return int(compact) if re.fullmatch(r"\d+", compact) else None


def _summary(root: _Node) -> dict[str, Any]:
    names = {
        "Total Data Centers": "total_data_centers",
        "Operating Data Centers": "operating_data_centers",
        "Planned Data Centers": "planned_data_centers",
    }
    result: dict[str, Any] = {name: None for name in names.values()}
    for div in root.descendants("div"):
        paragraphs = [node for node in div.content if isinstance(node, _Node) and node.tag == "p"]
        if len(paragraphs) == 2 and paragraphs[0].text() in names:
            result[names[paragraphs[0].text()]] = _count(paragraphs[1].text())
    values = [result[name] for name in names.values()]
    result["other_or_unreconciled_data_centers"] = (
        values[0] - values[1] - values[2] if all(value is not None for value in values) else None
    )
    result["reconciliation_status"] = (
        "unknown" if result["other_or_unreconciled_data_centers"] is None else
        "reconciled" if result["other_or_unreconciled_data_centers"] == 0 else "unreconciled"
    )
    public_text = root.text()
    month = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b",
        public_text,
    )
    result["version"] = month.group(0) if month else "public listing snapshot; no visible version"
    result["selection_bias"] = SELECTION_BIAS
    result["source_status"] = "PARTIAL"
    result["missing_reason"] = (
        "Public summary counts do not identify every facility; only largest-operating cards are sampled."
    )
    return result


def parse_reference_html(html: str, *, page_url: str, retrieved_at: str) -> dict[str, Any]:
    """Parse visible operating cards and linked state pages without hidden payloads.

    No latitude/longitude is inferred. Unknown text and missing displayed values
    remain null. Operating means the listing section's classification, which is
    not independent verification of either commissioning or AI workload.
    """
    parser = _PublicHTML()
    parser.feed(html)
    root = parser.root
    sections = [node for node in root.descendants("section")
                if node.attrs.get("id") == "largest-operating"]
    rows = []
    for section in sections:
        for card in section.descendants("a"):
            source_url = _public_url(card.attrs.get("href") or "", page_url)
            if source_url is None:
                continue
            detail = _DETAIL_PATH.fullmatch(urlparse(source_url).path)
            headings = list(card.descendants("h3"))
            if detail is None or len(headings) != 1:
                continue
            fields = {}
            paragraphs = list(card.descendants("p"))
            for paragraph in paragraphs:
                text = paragraph.text()
                label, separator, value = text.partition(":")
                if separator:
                    fields[label.strip()] = value.strip()
            capacity_text = next((node.text() for node in paragraphs
                                  if re.fullmatch(r"[\d,.]+\s+MW", node.text())), None)
            capacity_mw = float(capacity_text.split()[0].replace(",", "")) if capacity_text else None
            year_text = _null_text(fields.get("Year Operational"))
            year = int(year_text) if year_text and re.fullmatch(r"\d{4}", year_text) else None
            location = _null_text(fields.get("Location"))
            county, comma, state = (location or "").rpartition(",")
            county_text = _null_text(county) if comma else None
            state_text = _null_text(state) if comma else None
            if state_text and state_text not in CONUS_STATE_NAMES:
                continue
            rows.append({
                "facility_id": f"cleanview:{detail.group(1)}",
                "name": headings[0].text(),
                "operating_status": "operating",
                "operating_status_basis": "public largest-operating section; not independently verified",
                "operational_year": year,
                "operational_year_text": year_text,
                "operational_year_status": "observed" if year is not None else "unknown",
                "operational_year_missing_reason": None if year is not None else "Year Operational missing, TBD, or nonnumeric",
                "county_text": county_text,
                "state_text": state_text,
                "location_text": location,
                "location_status": "observed" if county_text and state_text else "unknown",
                "location_missing_reason": None if county_text and state_text else "Public county and state location not provided",
                "capacity_mw": capacity_mw,
                "capacity_status": "observed" if capacity_mw is not None else "unknown",
                "capacity_missing_reason": None if capacity_mw is not None else "Public operating card has no numeric MW capacity",
                "developer_text": _null_text(fields.get("Developer")),
                "status": "observed",
                "confidence": "low",
                "source_id": SOURCE_ID,
                "source_url": source_url,
                "listing_page_url": page_url,
                "listing_page_urls": [page_url],
                "retrieved_at": retrieved_at,
                "data_mode": "real",
                "selection_bias": SELECTION_BIAS,
                "workload_type": "unknown",
                "workload_missing_reason": "Listing card does not independently establish an AI workload; mining names and developer labels are preserved",
            })
    state_links = []
    for section in root.descendants("section"):
        headings = [node.text() for node in section.descendants("h2")]
        if "Explore Data Centers by State" not in headings:
            continue
        for anchor in section.descendants("a"):
            name = anchor.text()
            url = _public_url(anchor.attrs.get("href") or "", page_url)
            if name in CONUS_STATE_NAMES and url and _STATE_PATH.fullmatch(urlparse(url).path):
                state_links.append({"state_text": name, "url": url})
    summary = _summary(root)
    return {"rows": deduplicate_reference_rows(rows), "summary": summary,
            "state_links": sorted({item["url"]: item for item in state_links}.values(), key=lambda item: item["url"]),
            "has_operating_section": bool(sections)}


def deduplicate_reference_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeat cards deterministically; expose conflicts instead of choosing."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["facility_id"], []).append(row)
    result = []
    checked = ("name", "county_text", "state_text", "capacity_mw", "operational_year", "developer_text")
    for facility_id, records in sorted(grouped.items()):
        records = sorted(records, key=lambda row: (row["listing_page_url"], row["source_url"], json.dumps(row, sort_keys=True)))
        chosen = dict(records[0])
        chosen["listing_page_urls"] = sorted({url for row in records for url in row["listing_page_urls"]})
        conflicts = []
        for key in checked:
            values = {row[key] for row in records}
            if len(values) > 1:
                chosen[key] = None
                conflicts.append(key)
        if "capacity_mw" in conflicts:
            chosen.update(capacity_status="unknown", capacity_missing_reason="Conflicting public card capacities across listing pages")
        if "operational_year" in conflicts:
            chosen.update(operational_year_status="unknown", operational_year_missing_reason="Conflicting public operational years across listing pages")
        if "county_text" in conflicts or "state_text" in conflicts:
            chosen.update(location_status="unknown", location_missing_reason="Conflicting public locations across listing pages")
        chosen["duplicate_conflicts"] = conflicts
        result.append(chosen)
    return result


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


class _PageCache:
    def __init__(self, raw_dir: Path, max_page_bytes: int):
        self.raw_dir = raw_dir
        self.root = raw_dir / SOURCE_ID / "public_listing_v1"
        self.root.mkdir(parents=True, exist_ok=True)
        self.log = self.root / "download_log.json"
        self.records = json.loads(self.log.read_text(encoding="utf-8")) if self.log.exists() else []
        self.lock = Lock()
        self.remaining = PROJECT_MAX_BYTES - sum(path.stat().st_size for path in raw_dir.rglob("*") if path.is_file())
        self.max_page_bytes = max_page_bytes

    def read(self, url: str) -> tuple[str, dict[str, Any]]:
        public_url = _public_url(url, NATIONAL_URL)
        if public_url != url or not _STATE_PATH.fullmatch(urlparse(url).path):
            raise ValueError("Only public listing pages discovered in Cleanview state links are permitted")
        path = self.root / (urlparse(url).path.rsplit("/", 1)[-1] + ".html")
        cached = next((record for record in self.records if record.get("url") == url), None)
        if path.exists():
            if not cached or cached.get("bytes") != path.stat().st_size or cached.get("sha256") != file_digest(path):
                raise ValueError("Existing Cleanview page is unverified or has a cache checksum mismatch")
            return path.read_text(encoding="utf-8"), dict(cached)
        if cached:
            raise ValueError("Cleanview manifest references a missing cached page; no silent redownload")
        request = Request(url, headers={"User-Agent": USER_AGENT})
        pieces = []
        with urlopen(request, timeout=45) as response:
            if response.geturl() != url:
                raise ValueError("Unexpected listing redirect; manual review required")
            if "text/html" not in (response.headers.get("Content-Type") or "").lower():
                raise ValueError("Cleanview listing did not return public HTML")
            length = response.headers.get("Content-Length")
            if length and int(length) > self.max_page_bytes:
                raise ValueError("Public page exceeds bounded HTML acquisition size")
            with self.lock:
                if length and int(length) > self.remaining:
                    raise ValueError("Download would exceed authorized project 60 GB raw-data budget")
            count = 0
            while chunk := response.read(64 * 1024):
                count += len(chunk)
                if count > self.max_page_bytes:
                    raise ValueError("Public page exceeds bounded HTML acquisition size")
                with self.lock:
                    if len(chunk) > self.remaining:
                        raise ValueError("Download would exceed authorized project 60 GB raw-data budget")
                    self.remaining -= len(chunk)
                pieces.append(chunk)
        content = b"".join(pieces)
        html = content.decode("utf-8")
        retrieved_at = datetime.now(timezone.utc).isoformat()
        parsed = parse_reference_html(html, page_url=url, retrieved_at=retrieved_at)
        if parsed["summary"]["total_data_centers"] is None:
            raise ValueError("Expected public summary absent; access block or page change requires manual review")
        partial = path.with_suffix(".html.part")
        partial.write_bytes(content)
        partial.replace(path)
        entry = {"url": url, "path": str(path), "retrieved_at_utc": retrieved_at,
                 "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                 "source_id": SOURCE_ID, "version": parsed["summary"]["version"],
                 "license": LICENSE_NOTE, "license_terms_note": LICENSE_NOTE}
        with self.lock:
            self.records.append(entry)
            self.records.sort(key=lambda record: record["url"])
            _atomic_json(self.log, self.records)
        return html, entry


def acquire_reference(raw_dir: str | Path, *, include_states: bool = True,
                      max_workers: int = 4, max_page_bytes: int = 5_000_000) -> dict[str, Any]:
    """Acquire immutable verified public pages and return incomplete operating samples.

    ``raw_dir`` is the project's ``data/raw`` directory. State requests follow
    only visible national links. The operational bounds (4 requests, 5 MB/page)
    limit acquisition resources and are not model parameters. The sampled public
    pages inspected for this adapter were 0.83 MB nationally and 0.21 MB for
    Tennessee; up to 50 national/state requests are estimated below 50 MB.
    """
    if max_workers < 1 or max_workers > 4 or max_page_bytes < 1:
        raise ValueError("Public listing acquisition requires 1–4 workers and a positive page byte limit")
    cache = _PageCache(Path(raw_dir), max_page_bytes)
    html, national_entry = cache.read(NATIONAL_URL)
    national = parse_reference_html(html, page_url=NATIONAL_URL, retrieved_at=national_entry["retrieved_at_utc"])
    rows = list(national["rows"])
    pages = [{"url": NATIONAL_URL, "state_text": None, "status": "PARTIAL", "acquired": True,
              "analyzed": True, "sample_count": len(rows), "summary": national["summary"],
              "missing_reason": "Public largest-operating sample is not a complete inventory"}]
    links = national["state_links"] if include_states else []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        pending = {executor.submit(cache.read, link["url"]): link for link in links}
        for future in as_completed(pending):
            link = pending[future]
            try:
                text, entry = future.result()
                parsed = parse_reference_html(text, page_url=link["url"], retrieved_at=entry["retrieved_at_utc"])
                rows.extend(parsed["rows"])
                pages.append({"url": link["url"], "state_text": link["state_text"], "status": "PARTIAL",
                              "acquired": True, "analyzed": True, "sample_count": len(parsed["rows"]),
                              "summary": parsed["summary"],
                              "missing_reason": "Public largest-operating sample is not a complete inventory"})
            except (OSError, ValueError) as error:
                pages.append({"url": link["url"], "state_text": link["state_text"], "status": "BLOCKED",
                              "acquired": False, "analyzed": False, "sample_count": 0,
                              "missing_reason": str(error)})
    rows = deduplicate_reference_rows(rows)
    pages.sort(key=lambda page: page["url"])
    discovered_states = {link["state_text"] for link in national["state_links"]}
    manifest = {
        "source_id": SOURCE_ID, "schema_version": "1.0.0", "source_status": "PARTIAL", "implemented": True,
        "acquired_pages": sum(page["acquired"] for page in pages),
        "analyzed_pages": sum(page["analyzed"] for page in pages),
        "unique_operating_sample_count": len(rows), "selection_bias": SELECTION_BIAS,
        "download_bytes_total": sum(entry["bytes"] for entry in cache.records),
        "estimated_acquisition_bytes": 50_000_000,
        "missing_conus_state_links": sorted(CONUS_STATE_NAMES - discovered_states),
        "version": national["summary"]["version"], "data_mode": "real",
        "license_terms_note": LICENSE_NOTE, "summary": national["summary"], "pages": pages,
        "limitations": ["Capacity-selected operating samples are not the complete operating inventory",
                        "Operating classification and engineering capacity are not independently verified",
                        "No facility coordinates or AI workload inferred; planned projects excluded",
                        "Summary status counts may contain other or unreconciled facilities"],
    }
    _atomic_json(cache.root / "source_manifest.json", manifest)
    return {"schema_version": "1.0.0", "data_mode": "real", "rows": rows, "pages": pages,
            "summary": national["summary"], "manifest": manifest}


def _normalized_county(value: str | None) -> str | None:
    value = _null_text(value)
    if value is None:
        return None
    return re.sub(r"\s+(?:county|parish|borough|census[ -]area)$", "", value.casefold()).strip()


def _state_code(value: Any) -> str:
    text = _null_text(value)
    return text.removesuffix(".0").zfill(2) if text else ""


def match_counties(rows: list[dict[str, Any]] | pd.DataFrame, counties: pd.DataFrame,
                   states: pd.DataFrame) -> list[dict[str, Any]]:
    """Match literal county/state labels to Census IDs; never geocode or fuzzy-match.

    County inputs require GEOID and NAME, plus STATEFP or a five-digit GEOID.
    State inputs require STATEFP or two-digit GEOID plus NAME and/or STUSPS.
    Repeated identical county records are harmless; distinct matching IDs are
    ambiguous. A county match says nothing about the parcel location.
    """
    if not {"GEOID", "NAME"}.issubset(counties.columns):
        raise ValueError("Census county matching requires GEOID and NAME")
    state_id = "STATEFP" if "STATEFP" in states else "GEOID" if "GEOID" in states else None
    if state_id is None or not {"NAME", "STUSPS"}.intersection(states.columns):
        raise ValueError("Census state matching requires STATEFP/GEOID and NAME/STUSPS")
    state_lookup: dict[str, set[str]] = {}
    for record in states.to_dict("records"):
        code = _state_code(record[state_id])
        if not re.fullmatch(r"\d{2}", code):
            continue
        for column in ("NAME", "STUSPS"):
            label = _null_text(record.get(column))
            if label:
                state_lookup.setdefault(label.casefold(), set()).add(code)
        state_lookup.setdefault(code, set()).add(code)
    county_lookup: dict[tuple[str, str], set[str]] = {}
    for record in counties.to_dict("records"):
        identifier = _null_text(record["GEOID"])
        geoid = identifier.removesuffix(".0").zfill(5) if identifier else ""
        code = _state_code(record.get("STATEFP", geoid[:2]))
        label = _normalized_county(record["NAME"])
        if label and re.fullmatch(r"\d{5}", geoid):
            county_lookup.setdefault((code, label), set()).add(geoid)
    input_rows = rows.to_dict("records") if isinstance(rows, pd.DataFrame) else rows
    result = []
    for original in sorted(input_rows, key=lambda row: row["facility_id"]):
        record = dict(original)
        label = _normalized_county(record.get("county_text"))
        state = _null_text(record.get("state_text"))
        state_codes = state_lookup.get(state.casefold(), set()) if state else set()
        matches = set()
        if len(state_codes) == 1 and label:
            matches = county_lookup.get((next(iter(state_codes)), label), set())
        if not label or not state:
            reason = "Public listing has no county/state label"
        elif len(state_codes) != 1:
            reason = "State label is unmatched or ambiguous in Census state reference"
        elif not matches:
            reason = "County label does not exactly match Census county reference; no fuzzy correction applied"
        elif len(matches) > 1:
            reason = "County label matches multiple Census GEOIDs; no arbitrary assignment applied"
        else:
            reason = None
        record.update(county_geoid=next(iter(matches)) if len(matches) == 1 else None,
                      county_match_status="calculated" if reason is None else "unknown",
                      county_match_confidence="low" if reason is None else "unknown",
                      county_match_method="exact normalized county and state label against Census county/state reference",
                      county_match_missing_reason=reason)
        result.append(record)
    return result
