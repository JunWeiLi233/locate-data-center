"""Synthetic public-listing HTML tests; no fabricated geographic observations."""
import io
import json

import pandas as pd
import pytest

from dc_locator import reference_data as reference


RETRIEVED = "2026-10-03T12:00:00+00:00"


def card(facility_id="1", *, capacity="100 MW", year="2020", county="Example County",
         state="Tennessee", name="Example Mining", developer="Example Mining Developer"):
    return (
        f'<a href="/data-centers/tennessee/{facility_id}/example-{facility_id}">'
        f"<h3>{name}</h3><p>{capacity}</p>"
        f"<div><p><span>Year Operational<!-- -->:</span> <!-- -->{year}</p>"
        f"<p><span>Location:</span> {county}, {state}</p>"
        f"<p><span>Developer:</span> {developer}</p></div></a>"
    )


def public_page(*cards, total="3,659", operating="1,316", planned="2,296", links=""):
    summary = "".join(
        f"<div><p>{label}</p><p>{value}</p></div>"
        for label, value in (("Total Data Centers", total), ("Operating Data Centers", operating),
                             ("Planned Data Centers", planned))
    )
    return (f"<html><head><script>unavailable hidden payload</script></head><body>"
            f"<h1>US Data Centers October 2026</h1>{summary}"
            f'<section id="largest-operating"><h2>Largest Operating Data Centers</h2>{"".join(cards)}</section>'
            f'<section><h2>Explore Data Centers by State</h2>{links}</section>'
            "</body></html>")


def parse(html, url=reference.NATIONAL_URL):
    return reference.parse_reference_html(html, page_url=url, retrieved_at=RETRIEVED)


def test_public_summary_reconciliation_and_observed_card():
    parsed = parse(public_page(card(capacity="1,085 MW")))
    summary = parsed["summary"]
    assert summary["total_data_centers"] == 3659
    assert summary["operating_data_centers"] == 1316
    assert summary["planned_data_centers"] == 2296
    assert summary["other_or_unreconciled_data_centers"] == 47
    assert summary["reconciliation_status"] == "unreconciled"
    assert summary["version"] == "October 2026"
    row, = parsed["rows"]
    assert row["facility_id"] == "cleanview:1"
    assert row["capacity_mw"] == 1085
    assert row["capacity_status"] == "observed"
    assert row["operational_year"] == 2020
    assert row["county_text"] == "Example County"
    assert row["state_text"] == "Tennessee"
    assert row["selection_bias"] == "top_capacity_sample"
    assert row["source_url"] == "https://cleanview.co/data-centers/tennessee/1/example-1"
    assert row["name"] == "Example Mining"
    assert row["developer_text"] == "Example Mining Developer"
    assert row["workload_type"] == "unknown"
    assert not any(key in row for key in ("latitude", "longitude", "geometry"))


def test_missing_capacity_year_and_county_remain_null():
    row, = parse(public_page(card(capacity="N/A", year="TBD", county="N/A")))["rows"]
    assert row["capacity_mw"] is None
    assert row["capacity_status"] == "unknown"
    assert row["capacity_missing_reason"]
    assert row["operational_year"] is None
    assert row["operational_year_status"] == "unknown"
    assert row["operational_year_missing_reason"]
    assert row["county_text"] is None
    assert row["location_status"] == "unknown"
    assert row["location_missing_reason"]


def test_planned_hidden_and_script_cards_are_never_sampled():
    html = public_page(card())
    html = html.replace("</body>",
                        f'<section id="largest-planned">{card("2")}</section>'
                        f'<div hidden><section id="largest-operating">{card("3")}</section></div>'
                        f'<script type="application/json">{card("4")}</script>'
                        f'<section id="largest-operating" style="display: none">{card("5")}</section></body>')
    assert [row["facility_id"] for row in parse(html)["rows"]] == ["cleanview:1"]


def test_paired_react_streamed_public_markup_matches_browser_visible_listing():
    content = public_page(card()).split("<body>", 1)[1].rsplit("</body>", 1)[0]
    html = ('<html><body><main><!--$?--><template id="B:0"></template><!--/$--></main>'
            f'<div hidden id="S:0">{content}'
            f'<div hidden><section id="largest-operating">{card("2")}</section></div></div>'
            f'<div hidden id="S:9"><section id="largest-operating">{card("3")}</section></div>'
            '<script>stream rendering instructions and inaccessible payload are ignored</script></body></html>')
    parsed = parse(html)
    assert parsed["summary"]["total_data_centers"] == 3659
    assert [row["facility_id"] for row in parsed["rows"]] == ["cleanview:1"]


def test_state_discovery_uses_only_visible_conus_explore_links():
    links = ('<a href="/data-centers/tennessee">Tennessee</a>'
             '<a href="/data-centers/alaska">Alaska</a>'
             '<a href="/data-centers/hawaii">Hawaii</a>'
             '<a href="https://other.example/data-centers/texas">Texas</a>'
             '<a href="/data-centers/tennessee">Tennessee</a>')
    html = public_page(card(), links=links).replace("</body>", '<a href="/data-centers/ohio">Ohio</a></body>')
    assert parse(html)["state_links"] == [{"state_text": "Tennessee", "url": "https://cleanview.co/data-centers/tennessee"}]


def test_deduplication_is_deterministic_and_exposes_conflicting_capacity():
    first = parse(public_page(card("2"), card("1")))["rows"]
    second = parse(public_page(card("1", capacity="101 MW")), "https://cleanview.co/data-centers/tennessee")["rows"]
    combined = reference.deduplicate_reference_rows(first + second)
    assert combined == reference.deduplicate_reference_rows(list(reversed(first + second)))
    assert [row["facility_id"] for row in combined] == ["cleanview:1", "cleanview:2"]
    assert combined[0]["capacity_mw"] is None
    assert combined[0]["capacity_status"] == "unknown"
    assert combined[0]["duplicate_conflicts"] == ["capacity_mw"]
    assert len(combined[0]["listing_page_urls"]) == 2


def test_unknown_summary_is_not_reconciled_or_zero():
    summary = parse(public_page(card(), operating="N/A"))["summary"]
    assert summary["operating_data_centers"] is None
    assert summary["other_or_unreconciled_data_centers"] is None
    assert summary["reconciliation_status"] == "unknown"


@pytest.fixture
def census():
    states = pd.DataFrame([{"STATEFP": "47", "NAME": "Tennessee", "STUSPS": "TN"},
                           {"STATEFP": "22", "NAME": "Louisiana", "STUSPS": "LA"}])
    counties = pd.DataFrame([{"GEOID": "47001", "STATEFP": "47", "NAME": "Example"},
                             {"GEOID": "47165", "STATEFP": "47", "NAME": "Sumner"},
                             {"GEOID": "22001", "STATEFP": "22", "NAME": "Other Parish"}])
    return counties, states


def test_county_matching_exact_suffix_and_state_abbreviation(census):
    counties, states = census
    records = [{"facility_id": "a", "county_text": "Example County", "state_text": "TN"},
               {"facility_id": "b", "county_text": "Other", "state_text": "Louisiana"}]
    matched = reference.match_counties(records, counties, states)
    assert [row["county_geoid"] for row in matched] == ["47001", "22001"]
    assert all(row["county_match_status"] == "calculated" for row in matched)
    assert all(row["county_match_missing_reason"] is None for row in matched)
    assert all(row["county_match_confidence"] == "low" for row in matched)


def test_county_matching_never_fuzzy_corrects_and_keeps_unknowns(census):
    counties, states = census
    records = [{"facility_id": "a", "county_text": "Summer", "state_text": "Tennessee"},
               {"facility_id": "b", "county_text": None, "state_text": "Tennessee"}]
    matched = reference.match_counties(records, counties, states)
    assert all(row["county_geoid"] is None for row in matched)
    assert all(row["county_match_status"] == "unknown" for row in matched)
    assert "no fuzzy correction" in matched[0]["county_match_missing_reason"]
    assert matched[1]["county_match_missing_reason"]


def test_ambiguous_county_does_not_get_arbitrary_id(census):
    counties, states = census
    extra = pd.DataFrame([{"GEOID": "47003", "STATEFP": "47", "NAME": "Example"}])
    counties = pd.concat([counties, extra], ignore_index=True)
    row, = reference.match_counties([{"facility_id": "a", "county_text": "Example", "state_text": "Tennessee"}], counties, states)
    assert row["county_geoid"] is None
    assert "multiple Census GEOIDs" in row["county_match_missing_reason"]


class FakeResponse(io.BytesIO):
    def __init__(self, url, html):
        self.url = url
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        super().__init__(html.encode("utf-8"))

    def geturl(self):
        return self.url


def test_acquisition_verified_cache_and_manifest(monkeypatch, tmp_path):
    requested = []
    html = public_page(card())

    def fake_open(request, timeout):
        requested.append(request.full_url)
        return FakeResponse(request.full_url, html)

    monkeypatch.setattr(reference, "urlopen", fake_open)
    acquired = reference.acquire_reference(tmp_path / "raw", include_states=False)
    assert acquired["schema_version"] == "1.0.0"
    assert acquired["data_mode"] == "real"
    assert acquired["manifest"]["source_status"] == "PARTIAL"
    assert acquired["manifest"]["unique_operating_sample_count"] == 1
    assert acquired["manifest"]["acquired_pages"] == 1
    assert acquired["manifest"]["analyzed_pages"] == 1
    assert acquired["manifest"]["download_bytes_total"] == len(html.encode("utf-8"))
    log = json.loads((tmp_path / "raw/cleanview_reference/public_listing_v1/download_log.json").read_text())
    assert log[0]["url"] == reference.NATIONAL_URL
    assert log[0]["bytes"] == len(html.encode("utf-8"))
    assert len(log[0]["sha256"]) == 64
    assert log[0]["retrieved_at_utc"]
    assert "No open-data license" in log[0]["license_terms_note"]
    again = reference.acquire_reference(tmp_path / "raw", include_states=False)
    assert requested == [reference.NATIONAL_URL]
    assert acquired["rows"] == again["rows"]


def test_modified_cached_page_is_not_redownloaded(monkeypatch, tmp_path):
    monkeypatch.setattr(reference, "urlopen", lambda request, timeout: FakeResponse(request.full_url, public_page(card())))
    reference.acquire_reference(tmp_path / "raw", include_states=False)
    cached = tmp_path / "raw/cleanview_reference/public_listing_v1/us.html"
    cached.write_text("modified", encoding="utf-8")
    monkeypatch.setattr(reference, "urlopen", lambda *_args, **_kwargs: pytest.fail("must not redownload corrupt cache"))
    with pytest.raises(ValueError, match="cache checksum mismatch"):
        reference.acquire_reference(tmp_path / "raw", include_states=False)


def test_blocked_state_is_reported_separately(monkeypatch, tmp_path):
    html = public_page(card(), links='<a href="/data-centers/tennessee">Tennessee</a>')

    def fake_open(request, timeout):
        if request.full_url != reference.NATIONAL_URL:
            raise OSError("Source denies public access")
        return FakeResponse(request.full_url, html)

    monkeypatch.setattr(reference, "urlopen", fake_open)
    acquired = reference.acquire_reference(tmp_path / "raw")
    state, = [page for page in acquired["pages"] if page["state_text"] == "Tennessee"]
    assert state["status"] == "BLOCKED"
    assert not state["acquired"]
    assert not state["analyzed"]
    assert state["missing_reason"] == "Source denies public access"
    assert acquired["manifest"]["unique_operating_sample_count"] == 1
