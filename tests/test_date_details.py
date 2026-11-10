"""Tests for the date detail mode.

The detail records distinguish information explicitly present in the source
string from values the parsers assume. Nothing is ever reverse-engineered
from the zero-valued fields of the resulting ``time.struct_time``.
"""

from __future__ import annotations

import time

import responses

import feedparser
from feedparser.datetimes import (
    _date_handlers,
    _parse_date_with_details,
    registerDateHandler,
)
from feedparser.datetimes.types import (
    UNKNOWN,
    DateDetail,
    DateParseResult,
)


def test_missing_timezone_is_not_claimed():
    """An RFC 822 date with no timezone is normalized to UTC silently."""

    result = _parse_date_with_details("01 Jan 2004 19:48:21")
    assert result is not None
    detail = result.detail
    assert detail.value == "01 Jan 2004 19:48:21"
    assert detail.handler == "rfc822"
    assert detail.precision == "second"
    assert detail.timezone_explicit is False
    assert detail.timezone_offset == UNKNOWN
    # The parsed tuple is still UTC for backwards compatibility.
    assert result.parsed[:6] == (2004, 1, 1, 19, 48, 21)


def test_date_only_has_day_precision_and_no_timezone():
    """A date without any time component is day precision."""

    result = _parse_date_with_details("01 Jan 2004")
    assert result is not None
    detail = result.detail
    assert detail.precision == "day"
    assert detail.timezone_explicit is False
    assert detail.timezone_offset == UNKNOWN
    # Midnight UTC appears in the tuple but was assumed, not sourced.
    assert result.parsed[3:6] == (0, 0, 0)

    w3c = _parse_date_with_details("2003-12-31")
    assert w3c is not None
    assert w3c.detail.handler == "w3dtf"
    assert w3c.detail.precision == "day"
    assert w3c.detail.timezone_explicit is False
    assert w3c.detail.timezone_offset == UNKNOWN


def test_non_integer_hour_offset_is_preserved():
    """Offsets with minutes survive in the detail record."""

    result = _parse_date_with_details(
        "2003-12-31T10:14:55+05:30"
    )
    assert result is not None
    detail = result.detail
    assert detail.handler == "w3dtf"
    assert detail.precision == "second"
    assert detail.timezone_explicit is True
    assert detail.timezone_offset == 5 * 60 + 30

    rfc822 = _parse_date_with_details(
        "Thu, 01 Jan 2004 19:48:21 -0430"
    )
    assert rfc822 is not None
    assert rfc822.detail.timezone_explicit is True
    assert rfc822.detail.timezone_offset == -(4 * 60 + 30)


def test_invalid_date_keeps_source_and_marks_unknowns():
    """Unparseable values still produce a detail record in feed output."""

    result = _parse_date_with_details("not a date at all")
    assert result is None

    feed = feedparser.parse(
        _rss_feed("not a date at all"),
        date_details=True,
    )
    entry = feed.entries[0]
    assert entry["published_parsed"] is None
    detail = entry["published_date_detail"]
    assert detail == {
        "value": "not a date at all",
        "handler": UNKNOWN,
        "precision": UNKNOWN,
        "timezone_explicit": UNKNOWN,
        "timezone_offset": UNKNOWN,
    }


def test_minute_precision_distinguished_from_seconds():
    minute = _parse_date_with_details("01 Jan 2004 19:48")
    assert minute is not None
    assert minute.detail.precision == "minute"

    w3c_minute = _parse_date_with_details("2003-12-31T10:14")
    assert w3c_minute is not None
    assert w3c_minute.detail.precision == "minute"


def test_explicit_utc_is_distinct_from_assumed_utc():
    explicit = _parse_date_with_details(
        "Thu, 01 Jan 2004 19:48:21 GMT"
    )
    assert explicit is not None
    assert explicit.detail.timezone_explicit is True
    assert explicit.detail.timezone_offset == 0

    assumed = _parse_date_with_details("01 Jan 2004 19:48:21")
    assert assumed is not None
    assert assumed.detail.timezone_explicit is False
    assert assumed.detail.timezone_offset == UNKNOWN
    # Both normalize to the same UTC tuple for backwards compatibility.
    assert explicit.parsed == assumed.parsed


def test_legacy_nine_tuple_handler_still_works_with_incomplete_details():
    calls = {"count": 0}

    def legacy_handler(value):
        calls["count"] += 1
        if value != "legacy-marker":
            return None
        return (2010, 5, 6, 7, 8, 9, 3, 126, 0)

    registerDateHandler(legacy_handler)
    try:
        feed = feedparser.parse(
            _rss_feed("legacy-marker"),
            date_details=True,
        )
        entry = feed.entries[0]
        assert tuple(entry["published_parsed"]) == (
            2010,
            5,
            6,
            7,
            8,
            9,
            3,
            126,
            0,
        )
        detail = entry["published_date_detail"]
        assert detail["handler"] == "legacy_handler"
        assert detail["value"] == "legacy-marker"
        # A 9-tuple carries no provenance, so these must stay unknown.
        assert detail["precision"] == UNKNOWN
        assert detail["timezone_explicit"] == UNKNOWN
        assert detail["timezone_offset"] == UNKNOWN
        # Parsing the value once must suffice for the tuple and the details.
        assert calls["count"] == 1
    finally:
        _date_handlers.remove(legacy_handler)


def test_modern_handler_is_invoked_exactly_once():
    calls = {"count": 0}

    def modern_handler(value):
        calls["count"] += 1
        if value != "modern-marker":
            return None
        return DateParseResult(
            parsed=time.struct_time((2011, 6, 7, 8, 9, 10, 1, 158, 0)),
            detail=DateDetail(
                value=value,
                handler="modern",
                precision="minute",
                timezone_explicit=True,
                timezone_offset=-300,
            ),
        )

    registerDateHandler(modern_handler)
    try:
        feed = feedparser.parse(
            _rss_feed("modern-marker"),
            date_details=True,
        )
        entry = feed.entries[0]
        assert entry["published_date_detail"]["handler"] == "modern"
        assert entry["published_date_detail"]["timezone_offset"] == -300
        assert calls["count"] == 1
    finally:
        _date_handlers.remove(modern_handler)


def test_xml_and_json_feeds_expose_identical_details():
    value = "2003-12-31T10:14:55+05:30"

    atom = feedparser.parse(
        f"""<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>t</title>
          <entry><title>a</title><updated>{value}</updated></entry>
        </feed>""",
        date_details=True,
    )
    json_feed = feedparser.parse(
        f"""{{
          "version": "https://jsonfeed.org/version/1.1",
          "title": "t",
          "items": [{{"id": "1", "date_published": "{value}"}}]
        }}""",
        date_details=True,
    )

    assert (
        atom.entries[0]["updated_date_detail"]
        == json_feed.entries[0]["published_date_detail"]
    )
    assert (
        atom.entries[0]["updated_parsed"]
        == json_feed.entries[0]["published_parsed"]
    )


def test_detail_mode_defaults_off():
    feed = feedparser.parse(_rss_feed("Thu, 01 Jan 2004 19:48:21 GMT"))
    entry = feed.entries[0]
    assert "published_date_detail" not in entry
    assert entry["published_parsed"] is not None


def test_http_last_modified_detail(mock_responses):
    url = "http://example.com/feed.xml"
    responses.add(
        responses.GET,
        url,
        body=_rss_feed("Thu, 01 Jan 2004 19:48:21 GMT"),
        content_type="application/rss+xml",
        headers={"Last-Modified": "Mon, 03 Apr 2023 01:02:03 GMT"},
        status=200,
    )

    feed = feedparser.parse(url, date_details=True)
    assert feed["modified_date_detail"] == {
        "value": "Mon, 03 Apr 2023 01:02:03 GMT",
        "handler": "rfc822",
        "precision": "second",
        "timezone_explicit": True,
        "timezone_offset": 0,
    }
    assert feed["modified_parsed"] is not None

    plain = feedparser.parse(url)
    assert "modified_date_detail" not in plain
def _rss_feed(pub_date: str) -> str:
    return f"""<?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <title>t</title>
        <item>
          <title>a</title>
          <pubDate>{pub_date}</pubDate>
          <description>d</description>
        </item>
      </channel>
    </rss>"""
