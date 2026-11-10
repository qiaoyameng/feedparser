from __future__ import annotations

import io

import pytest
import responses

import feedparser
import feedparser.api


# The same relative reference is placed under two nested xml:base scopes and
# repeated in a sibling entry, so the three results must differ only through
# their effective base while sharing the same original text.
NESTED_FEED = """
<feed xmlns="http://www.w3.org/2005/Atom" xml:base="http://outer.example/root/">
  <link rel="self" href="feed.xml"/>
  <entry xml:base="nested/one/">
    <link href="page.html"/>
    <link rel="enclosure" href="feed.xml"/>
    <content type="html">&lt;img src="pic.png"/&gt;</content>
  </entry>
  <entry>
    <link href="page.html"/>
  </entry>
</feed>
"""


@pytest.fixture(params=["strict", "loose"])
def parsed(request, monkeypatch):
    if request.param == "loose":
        monkeypatch.setattr(feedparser.api, "_XML_AVAILABLE", False)
    return feedparser.parse(
        io.StringIO(NESTED_FEED), track_uri_sources=True
    )


def test_feature_is_opt_in():
    result = feedparser.parse(io.StringIO(NESTED_FEED))
    assert "uri_sources" not in result
    assert "base_sources" not in result


def test_three_references_keep_position_and_scope(parsed):
    records = parsed.uri_sources
    page_records = [r for r in records if r["source"] == "page.html"]
    assert len(page_records) == 2

    nested, sibling = page_records
    assert nested["entry_index"] == 0
    assert nested["base"] == "http://outer.example/root/nested/one/"
    assert (
        nested["resolved"]
        == "http://outer.example/root/nested/one/page.html"
    )
    assert sibling["entry_index"] == 1
    assert sibling["base"] == "http://outer.example/root/"
    assert sibling["resolved"] == "http://outer.example/root/page.html"

    # Each record preserves the original text alongside the resolution.
    assert all(r["source"] == "page.html" for r in page_records)
    assert all(r["reason"] == "" for r in records)


def test_repeated_field_uses_occurrence_not_name_overwrite(parsed):
    entry_links = [
        r
        for r in parsed.uri_sources
        if r["scope"] == "entry"
        and r["entry_index"] == 0
        and r["field"] == "links"
    ]
    assert [r["source"] for r in entry_links] == [
        "page.html",
        "feed.xml",
    ]
    assert [r["occurrence"] for r in entry_links] == [0, 1]


def test_nested_xml_base_is_scoped_and_restored(parsed):
    # base_sources keeps the declaration order and the scope exit.
    element_bases = [
        b for b in parsed.base_sources if b["scope"] == "element"
    ]
    assert [b["raw"] for b in element_bases] == [
        "http://outer.example/root/",
        "nested/one/",
    ]

    nested = next(
        r
        for r in parsed.uri_sources
        if r["source"] == "page.html" and r["entry_index"] == 0
    )
    assert [c["value"] for c in nested["base_chain"]] == [
        "http://outer.example/root/",
        "http://outer.example/root/nested/one/",
    ]

    sibling = next(
        r
        for r in parsed.uri_sources
        if r["source"] == "page.html" and r["entry_index"] == 1
    )
    # The nested xml:base left scope before the sibling entry opened.
    assert [c["value"] for c in sibling["base_chain"]] == [
        "http://outer.example/root/",
    ]


def test_xhtml_href_and_src_are_tracked(parsed):
    img = next(
        r
        for r in parsed.uri_sources
        if r["field"] == "content" and r["tag"] == "img"
    )
    assert img["attribute"] == "src"
    assert img["source"] == "pic.png"
    assert (
        img["resolved"]
        == "http://outer.example/root/nested/one/pic.png"
    )

    # The stored markup itself is still rewritten as before.
    assert (
        parsed.entries[0]["content"][0]["value"]
        == '<img src="http://outer.example/root/nested/one/pic.png" />'
    )


def test_existing_fields_are_unchanged(parsed):
    assert parsed.feed["links"][0]["href"] == (
        "http://outer.example/root/feed.xml"
    )
    assert parsed.entries[0]["link"] == (
        "http://outer.example/root/nested/one/page.html"
    )


def test_strict_and_loose_agree(monkeypatch):
    strict = feedparser.parse(
        io.StringIO(NESTED_FEED), track_uri_sources=True
    )
    monkeypatch.setattr(feedparser.api, "_XML_AVAILABLE", False)
    loose = feedparser.parse(
        io.StringIO(NESTED_FEED), track_uri_sources=True
    )
    assert loose["bozo"] is False
    assert [dict(r) for r in loose.uri_sources] == [
        dict(r) for r in strict.uri_sources
    ]


def test_unsafe_xml_base_is_recorded_but_not_applied():
    xml = """
    <feed xmlns="http://www.w3.org/2005/Atom"
          xml:base="http://safe.example/root/">
      <entry xml:base="javascript:alert(1)">
        <link href="inside.html"/>
      </entry>
      <entry>
        <link href="outside.html"/>
      </entry>
    </feed>
    """
    result = feedparser.parse(io.StringIO(xml), track_uri_sources=True)
    unsafe = next(
        b
        for b in result.base_sources
        if b["raw"] == "javascript:alert(1)"
    )
    assert unsafe["effective"] is False
    assert unsafe["reason"] == "the URI scheme is not allowed"

    inside, outside = (
        r for r in result.uri_sources if r["source"].endswith(".html")
    )
    assert inside["base"] == "http://safe.example/root/"
    assert inside["resolved"] == "http://safe.example/root/inside.html"
    assert outside["base"] == "http://safe.example/root/"


def test_malformed_uri_keeps_original_and_reason():
    xml = """
    <rss version="2.0" xml:base="http://safe.example/">
      <channel>
        <item><link>http://bad]test/x</link></item>
      </channel>
    </rss>
    """
    result = feedparser.parse(io.StringIO(xml), track_uri_sources=True)
    record = result.uri_sources[0]
    assert record["source"] == "http://bad]test/x"
    assert record["resolved"] == ""
    assert record["reason"] == "the URI is malformed"
    # No fabricated absolute URI leaks into the parsed field either.
    assert result.entries[0]["link"] == ""


def test_missing_base_keeps_relative_text():
    xml = (
        '<rss version="2.0"><channel>'
        "<item><link>rel/page.html</link></item>"
        "</channel></rss>"
    )
    result = feedparser.parse(io.StringIO(xml), track_uri_sources=True)
    record = result.uri_sources[0]
    assert record["base"] == ""
    assert record["resolved"] == "rel/page.html"
    missing = result.base_sources[0]
    assert missing["effective"] is False
    assert missing["reason"] == "no base URI is available"


def test_disabling_html_resolution_skips_markup_records_only():
    xml = """
    <rss version="2.0" xml:base="http://x.example/">
      <channel>
        <item>
          <description><![CDATA[<a href="rel.html">x</a>]]></description>
          <link>feed-link.html</link>
        </item>
      </channel>
    </rss>
    """
    result = feedparser.parse(
        io.StringIO(xml),
        track_uri_sources=True,
        resolve_relative_uris=False,
    )
    # The markup is untouched, so no markup-level record exists.
    assert not [
        r for r in result.uri_sources if r["field"] == "description"
    ]
    assert result.entries[0]["summary"] == '<a href="rel.html">x</a>'
    # Feed-level references are still tracked.
    link = result.uri_sources[0]
    assert link["field"] == "link"
    assert link["resolved"] == "http://x.example/feed-link.html"


def test_content_location_takes_precedence_over_final_url():
    url = "http://127.0.0.1:8097/feed.xml"
    body = (
        b'<rss version="2.0"><channel>'
        b"<item><link>a.html</link></item>"
        b"</channel></rss>"
    )
    responses.get(
        url,
        body=body,
        content_type="text/xml",
        headers={"Content-Location": "http://cl.example/feed/"},
    )
    result = feedparser.parse(url, track_uri_sources=True)

    origins = {b["origin"]: b for b in result.base_sources}
    assert origins["HTTP final URL"]["effective"] is False
    assert origins["Content-Location header"]["effective"] is True
    record = result.uri_sources[0]
    assert record["base"] == "http://cl.example/feed/"
    assert record["resolved"] == "http://cl.example/feed/a.html"


def test_final_url_used_without_content_location():
    url = "http://127.0.0.1:8097/feed2.xml"
    body = (
        b'<rss version="2.0"><channel>'
        b"<item><link>b.html</link></item>"
        b"</channel></rss>"
    )
    responses.get(url, body=body, content_type="text/xml")
    result = feedparser.parse(url, track_uri_sources=True)

    document_base = next(
        b for b in result.base_sources if b["scope"] == "document"
    )
    assert document_base["origin"] == "HTTP final URL"
    assert document_base["effective"] is True
    assert result.uri_sources[0]["resolved"] == (
        "http://127.0.0.1:8097/b.html"
    )


def test_relative_content_location_uses_final_url_as_its_base():
    url = "http://127.0.0.1:8097/feed3.xml"
    body = (
        b'<rss version="2.0"><channel>'
        b"<item><link>c.html</link></item>"
        b"</channel></rss>"
    )
    responses.get(
        url,
        body=body,
        content_type="text/xml",
        headers={"Content-Location": "relative/feed/"},
    )
    result = feedparser.parse(url, track_uri_sources=True)
    # The relative Content-Location is resolved against the final HTTP URL.
    assert result.uri_sources[0]["base"] == (
        "http://127.0.0.1:8097/relative/feed/"
    )
    assert result.uri_sources[0]["resolved"] == (
        "http://127.0.0.1:8097/relative/feed/c.html"
    )
    effective = next(b for b in result.base_sources if b["effective"])
    assert effective["origin"] == "Content-Location header"


def test_rss_enclosure_and_atom_content_src_are_tracked():
    xml = """
    <rss version="2.0" xml:base="http://media.example/root/">
      <channel>
        <item>
          <enclosure url="song.mp3" length="10" type="audio/mpeg"/>
        </item>
      </channel>
    </rss>
    """
    result = feedparser.parse(io.StringIO(xml), track_uri_sources=True)
    enclosure = next(
        r for r in result.uri_sources if r["field"] == "links"
    )
    assert enclosure["source"] == "song.mp3"
    assert enclosure["resolved"] == "http://media.example/root/song.mp3"
    assert result.entries[0]["enclosures"][0]["href"] == (
        "http://media.example/root/song.mp3"
    )

    atom = (
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xml:base="http://media.example/root/">'
        '<entry><content src="movie.mp4"/></entry></feed>'
    )
    atom_result = feedparser.parse(
        io.StringIO(atom), track_uri_sources=True
    )
    src_record = atom_result.uri_sources[0]
    assert src_record["field"] == "content"
    assert src_record["attribute"] == "src"
    assert src_record["resolved"] == (
        "http://media.example/root/movie.mp4"
    )


def test_feed_level_fields_are_tracked_with_feed_scope():
    xml = """
    <feed xmlns="http://www.w3.org/2005/Atom"
          xml:base="http://f.example/root/">
      <generator uri="gen/">Gen</generator>
      <author><uri>author.html</uri></author>
      <id>feed-id</id>
      <entry><id>entry-id</id></entry>
    </feed>
    """
    result = feedparser.parse(io.StringIO(xml), track_uri_sources=True)
    fields = {
        (r["scope"], r["field"], r["source"]): r for r in result.uri_sources
    }
    generator = fields[("feed", "generator_detail", "gen/")]
    assert generator["resolved"] == "http://f.example/root/gen/"
    author = fields[("feed", "href", "author.html")]
    assert author["resolved"] == "http://f.example/root/author.html"
    entry_id = fields[("entry", "id", "entry-id")]
    assert entry_id["entry_index"] == 0


def test_multiple_enclosures_keep_distinct_positions():
    xml = """
    <rss version="2.0" xml:base="http://media.example/root/">
      <channel>
        <item>
          <enclosure url="one.mp3" length="1" type="audio/mpeg"/>
          <enclosure url="two.mp3" length="2" type="audio/mpeg"/>
        </item>
      </channel>
    </rss>
    """
    result = feedparser.parse(io.StringIO(xml), track_uri_sources=True)
    enclosures = [
        r for r in result.uri_sources if r["field"] == "links"
    ]
    assert [r["source"] for r in enclosures] == ["one.mp3", "two.mp3"]
    assert [r["occurrence"] for r in enclosures] == [0, 1]
    assert [r["resolved"] for r in enclosures] == [
        "http://media.example/root/one.mp3",
        "http://media.example/root/two.mp3",
    ]
