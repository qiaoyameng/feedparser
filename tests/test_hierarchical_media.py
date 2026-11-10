from __future__ import annotations

import pathlib

import pytest

import feedparser


FIXTURE = (
    pathlib.Path(__file__).parent
    / "wellformed"
    / "media-rss"
    / "hierarchical_media.xml"
)


@pytest.fixture
def strict_entry():
    result = feedparser.parse(
        FIXTURE.read_text(encoding="utf-8"), hierarchical_media=True
    )
    assert result["bozo"] is False
    return result.entries[0]


@pytest.fixture
def loose_entry(monkeypatch):
    monkeypatch.setattr(feedparser.api, "_XML_AVAILABLE", False)
    result = feedparser.parse(
        FIXTURE.read_text(encoding="utf-8"), hierarchical_media=True
    )
    assert result["bozo"] is False
    return result.entries[0]


@pytest.fixture(params=["strict_entry", "loose_entry"])
def entry(request):
    return request.getfixturevalue(request.param)


def test_flat_fields_keep_their_original_shape(entry):
    # Four media:content elements: two in the first group, one in the second,
    # plus one outside the groups.
    assert len(entry["media_content"]) == 4
    # The flat field keeps raw (xml:base-unresolved) URLs.
    assert entry["media_content"][-1] == {
        "url": "outside.mp4",
        "type": "video/mp4",
    }
    assert entry["media_thumbnail"][0]["url"] == "group-thumb.jpg"
    assert entry["media_rating"]["content"] == "adult"
    assert entry["media_credit"][0] == {
        "role": "creator",
        "content": "Group credit",
    }


def test_media_title_does_not_override_the_entry_title(entry):
    assert entry["title"] == "Entry title"


def test_groups_and_ungrouped_content_are_separated(entry):
    assert len(entry["media_groups"]) == 2
    assert len(entry["media_groups"][0]["content"]) == 2
    assert len(entry["media_groups"][1]["content"]) == 1
    assert entry["media_ungrouped_content"] == [
        {
            "url": "outside.mp4",
            "type": "video/mp4",
            "href": "http://example.com/feed/outside.mp4",
        }
    ]


def test_group_level_metadata_is_the_default(entry):
    group = entry["media_groups"][0]
    assert group["title"] == {"type": "plain", "value": "English group"}
    assert group["description"] == {
        "type": "plain",
        "value": "English description",
    }
    assert group["credit"] == [{"role": "creator", "content": "Group credit"}]
    assert group["rating"] == {"scheme": "urn:simple", "content": "adult"}
    assert group["thumbnail"] == [
        {
            "url": "group-thumb.jpg",
            "width": "100",
            "height": "80",
            "href": "http://example.com/feed/group-thumb.jpg",
        }
    ]
    # A group with only a title and a thumbnail does not gain empty metadata.
    second_group = entry["media_groups"][1]
    assert set(second_group) == {"attrs", "content", "title", "thumbnail"}


def test_content_declarations_take_precedence_over_group_defaults(entry):
    high, low = entry["media_groups"][0]["content"]

    # Content-level title replaces the group title.
    assert high["title"] == {"value": "English high bitrate"}
    assert low["title"] == {"value": "English low bitrate"}

    # Repeatable elements declared on the content are not merged with the
    # group's list; the group's list remains the default.
    assert high["credit"] == [
        {"role": "publisher", "content": "Content publisher"}
    ]
    assert high["thumbnail"] == [
        {
            "url": "en-high-thumb.jpg",
            "href": "http://example.com/feed/en-high-thumb.jpg",
        }
    ]
    assert low["credit"] == [{"role": "creator", "content": "Group credit"}]
    assert low["thumbnail"] == [
        {
            "url": "group-thumb.jpg",
            "width": "100", "height": "80",
            "href": "http://example.com/feed/group-thumb.jpg",
        }
    ]

    # Single-valued defaults are inherited unchanged.
    assert high["description"] == {
        "type": "plain",
        "value": "English description",
    }
    assert high["rating"] == {"scheme": "urn:simple", "content": "adult"}


def test_repeatable_elements_keep_every_item_in_order(entry):
    group = entry["media_groups"][0]
    assert [credit["role"] for credit in group["credit"]] == ["creator"]
    assert [thumb["url"] for thumb in group["thumbnail"]] == ["group-thumb.jpg"]

    high = group["content"][0]
    assert [thumb["url"] for thumb in high["thumbnail"]] == [
        "en-high-thumb.jpg"
    ]
    assert [credit["role"] for credit in high["credit"]] == ["publisher"]


def test_repeated_group_metadata_is_not_reduced_to_the_last_item(monkeypatch):
    text = """
    <rss xmlns:media="http://search.yahoo.com/mrss">
      <channel>
        <item>
          <media:group>
            <media:credit role="creator">First</media:credit>
            <media:credit role="writer">Second</media:credit>
            <media:thumbnail url="one.jpg" />
            <media:thumbnail url="two.jpg" />
            <media:content url="video.mp4" type="video/mp4" />
          </media:group>
        </item>
      </channel>
    </rss>
    """
    for xml_available in (True, False):
        monkeypatch.setattr(feedparser.api, "_XML_AVAILABLE", xml_available)
        result = feedparser.parse(text, hierarchical_media=True)
        group = result.entries[0]["media_groups"][0]
        assert [credit["role"] for credit in group["credit"]] == [
            "creator",
            "writer",
        ]
        assert [thumb["url"] for thumb in group["thumbnail"]] == [
            "one.jpg",
            "two.jpg",
        ]
        # The flat fields keep every occurrence as well.
        assert len(result.entries[0]["media_credit"]) == 2
        assert len(result.entries[0]["media_thumbnail"]) == 2


def test_urls_follow_the_effective_xml_base(entry):
    first_group = entry["media_groups"][0]
    assert first_group["thumbnail"][0]["href"] == (
        "http://example.com/feed/group-thumb.jpg"
    )
    high = first_group["content"][0]
    assert high["url"] == "en-high.mp4"
    assert high["href"] == "http://example.com/feed/en-high.mp4"
    assert high["thumbnail"][0]["href"] == (
        "http://example.com/feed/en-high-thumb.jpg"
    )

    # The second group overrides xml:base for itself and its content.
    second_group = entry["media_groups"][1]
    assert second_group["thumbnail"][0]["href"] == (
        "http://example.com/feed/fr/fr-thumb.jpg"
    )
    french = second_group["content"][0]
    assert french["href"] == "http://example.com/feed/fr/fr-high.mp4"

    # The group-relative base does not leak outside the group: ungrouped
    # content only follows the feed-level xml:base.
    assert entry["media_ungrouped_content"][0]["href"] == (
        "http://example.com/feed/outside.mp4"
    )


def test_mutating_one_content_does_not_affect_sibling_or_group(entry):
    group = entry["media_groups"][0]
    high, low = group["content"]

    high["thumbnail"].append({"url": "mutation"})
    high["credit"].append({"role": "mutation"})

    assert [thumb["url"] for thumb in low["thumbnail"]] == ["group-thumb.jpg"]
    assert [credit["role"] for credit in low["credit"]] == ["creator"]
    assert [thumb["url"] for thumb in group["thumbnail"]] == ["group-thumb.jpg"]
    assert [credit["role"] for credit in group["credit"]] == ["creator"]


def test_namespace_prefix_is_arbitrary(entry):
    # The fixture binds the media namespace to the ``mvideo`` prefix and the
    # hierarchy is still recognized via the namespace URI.
    assert entry["media_groups"][0]["title"]["value"] == "English group"


def test_hierarchical_output_is_opt_in():
    result = feedparser.parse(FIXTURE.read_text(encoding="utf-8"))
    entry = result.entries[0]
    assert "media_groups" not in entry
    assert "media_ungrouped_content" not in entry
    # Flat fields remain available with their historical shape.
    assert len(entry["media_content"]) == 4


def test_module_level_constant_enables_the_feature(monkeypatch):
    monkeypatch.setattr(feedparser, "HIERARCHICAL_MEDIA", 1)
    result = feedparser.parse(FIXTURE.read_text(encoding="utf-8"))
    assert len(result.entries[0]["media_groups"]) == 2

    monkeypatch.setattr(feedparser, "HIERARCHICAL_MEDIA", 0)
    result = feedparser.parse(FIXTURE.read_text(encoding="utf-8"))
    assert "media_groups" not in result.entries[0]
