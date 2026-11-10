from __future__ import annotations

import pathlib

import pytest

import feedparser
import feedparser.api

FIXTURE_DIR = pathlib.Path(__file__).parent / "rss1_sequence"


def _load(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


@pytest.fixture(params=["strict", "loose"], ids=["strict", "loose"])
def parse(request, monkeypatch):
    mode = request.param
    if request.param == "loose":
        monkeypatch.setattr(feedparser.api, "_XML_AVAILABLE", False)

    def _parse(text: str, **kwargs):
        return feedparser.parse(text, **kwargs)

    return mode, _parse


def test_sequence_overrides_document_order(parse):
    mode, do_parse = parse
    result = do_parse(_load("forward_reference.xml"), rss1_sequence=True)

    assert result.bozo is False
    assert [entry.title for entry in result.entries] == [
        "Third",
        "First",
        "Second",
    ]
    channel = result.feed.rss1_channels[0]
    assert [entry.title for entry in channel.entries] == [
        "Third",
        "First",
        "Second",
    ]
    assert result.feed.rss1_unsequenced_entries == []
    assert result.feed.rss1_diagnostics == []


def test_shared_item_keeps_per_channel_order(parse):
    _, do_parse = parse
    result = do_parse(_load("shared_channels.xml"), rss1_sequence=True)

    assert result.bozo is False
    channel_a, channel_b = result.feed.rss1_channels
    assert channel_a.resource == "http://example.org/channel-a"
    assert channel_b.resource == "http://example.org/channel-b"
    assert [entry.title for entry in channel_a.entries] == [
        "Gamma",
        "Alpha",
        "Shared",
    ]
    assert [entry.title for entry in channel_b.entries] == ["Shared", "Beta"]
    # The shared entry is the same object in both channels.
    assert channel_a.entries[2] is channel_b.entries[0]


def test_resource_identity_uses_each_xml_base(parse):
    _, do_parse = parse
    result = do_parse(_load("shared_channels.xml"), rss1_sequence=True)

    by_title = {entry.title: entry for entry in result.entries}
    # A relative rdf:about under a nested xml:base matches a resource
    # referenced from the root-level xml:base.
    assert by_title["Beta"].id == "beta"
    channel_b = result.feed.rss1_channels[1]
    assert channel_b.entries[1].title == "Beta"
    assert by_title["Shared"].id == "shared"
    assert result.feed.rss1_diagnostics == []


def test_unsequenced_items_are_not_attached_to_a_channel(parse):
    _, do_parse = parse
    result = do_parse(_load("shared_channels.xml"), rss1_sequence=True)

    unsequenced = result.feed.rss1_unsequenced_entries
    assert [entry.title for entry in unsequenced] == ["Orphan"]
    for channel in result.feed.rss1_channels:
        assert all(entry.title != "Orphan" for entry in channel.entries)
    # Orphan still appears in the flat entries list, after sequenced items.
    assert result.entries[-1].title == "Orphan"


def test_foreign_namespace_li_is_ignored(parse):
    _, do_parse = parse
    result = do_parse(_load("unknown_namespace_li.xml"), rss1_sequence=True)

    assert result.bozo is False
    members = result.feed.rss1_channels[0].members
    assert members == [
        "http://example.org/feed/items/one",
        "http://example.org/feed/items/three",
    ]
    assert [entry.title for entry in result.entries] == ["One", "Three", "Two"]
    assert [entry.title for entry in result.feed.rss1_unsequenced_entries] == [
        "Two"
    ]
    assert result.feed.rss1_diagnostics == []


def test_diagnostics_are_localizable(parse):
    mode, do_parse = parse
    result = do_parse(_load("diagnostics.xml"), rss1_sequence=True)

    diagnostic_types = {d.type for d in result.feed.rss1_diagnostics}
    assert diagnostic_types == {
        "missing_reference",
        "duplicate_member",
        "missing_resource",
        "conflicting_definition",
    }
    by_type = {d.type: d for d in result.feed.rss1_diagnostics}
    assert by_type["missing_reference"].uri == (
        "http://example.org/feed/items/missing"
    )
    assert by_type["duplicate_member"].uri == (
        "http://example.org/feed/items/one"
    )
    # The repeated member is kept in sequence order with a diagnostic;
    # the unresolvable reference is skipped.
    channel_entries = result.feed.rss1_channels[0].entries
    assert [entry.title for entry in channel_entries] == ["One", "One"]
    # The conflicting re-definition is not another sequence member; it is
    # retained and reported rather than silently merged or dropped.
    assert [
        entry.title for entry in result.feed.rss1_unsequenced_entries
    ] == ["One, redefined differently"]
    # Every diagnostic carries a human-readable message; strict parsing
    # also reports the source line, while the loose parser cannot.
    assert all(diagnostic.message for diagnostic in result.feed.rss1_diagnostics)
    for diagnostic in result.feed.rss1_diagnostics:
        assert diagnostic.line is None or isinstance(diagnostic.line, int)
    if mode == "strict":
        assert all(
            isinstance(diagnostic.line, int)
            for diagnostic in result.feed.rss1_diagnostics
        )
    else:
        assert all(
            diagnostic.line is None
            for diagnostic in result.feed.rss1_diagnostics
        )


def test_strict_and_loose_associations_match(monkeypatch):
    text = _load("shared_channels.xml")

    monkeypatch.setattr(feedparser.api, "_XML_AVAILABLE", True)
    strict = feedparser.parse(text, rss1_sequence=True)
    monkeypatch.setattr(feedparser.api, "_XML_AVAILABLE", False)
    loose = feedparser.parse(text, rss1_sequence=True)

    def signature(result):
        return (
            [entry.title for entry in result.entries],
            [
                [entry.title for entry in channel.entries]
                for channel in result.feed.rss1_channels
            ],
            [entry.title for entry in result.feed.rss1_unsequenced_entries],
            [
                (diagnostic.type, diagnostic.uri)
                for diagnostic in result.feed.rss1_diagnostics
            ],
        )

    assert signature(strict) == signature(loose)


def test_default_behavior_keeps_flat_document_order(parse):
    _, do_parse = parse
    text = _load("forward_reference.xml")

    result = do_parse(text)

    assert [entry.title for entry in result.entries] == [
        "First",
        "Second",
        "Third",
    ]
    assert "rss1_channels" not in result.feed
    assert "rss1_unsequenced_entries" not in result.feed
    assert "rss1_diagnostics" not in result.feed


def test_sequence_mode_is_rss1_only(parse):
    _, do_parse = parse
    rss20 = """
    <rss version="2.0">
      <channel>
        <item><title>RSS 2.0 item</title></item>
      </channel>
    </rss>
    """
    result = do_parse(rss20, rss1_sequence=True)

    assert result.version == "rss20"
    assert [entry.title for entry in result.entries] == ["RSS 2.0 item"]
    assert "rss1_channels" not in result.feed


def test_module_constant_enables_sequence_mode(parse, monkeypatch):
    _, do_parse = parse
    text = _load("forward_reference.xml")
    monkeypatch.setattr(feedparser, "RSS1_SEQUENCE", 1)

    result = do_parse(text)

    assert [entry.title for entry in result.entries] == [
        "Third",
        "First",
        "Second",
    ]
    assert "rss1_channels" in result.feed
