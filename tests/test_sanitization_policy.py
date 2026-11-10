from __future__ import annotations

import dataclasses
import io
import json
import threading

import pytest

import feedparser
from feedparser.sanitizer import HTMLSanitizer, SanitizationPolicy


MARKUP = (
    "<custom-a>a</custom-a>"
    "<custom-b>b</custom-b>"
    "<p style=\"color: red; position: absolute;\">hi</p>"
    '<a href="javascript:alert(1)">x</a>'
)

RSS_TEMPLATE = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>tenant</title>
    <item>
      <guid>1</guid>
      <description type="text/html"><![CDATA[{markup}]]></description>
    </item>
  </channel>
</rss>
"""

ATOM_TEMPLATE = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>tenant</title>
  <id>urn:tenant</id>
  <updated>2026-01-01T00:00:00Z</updated>
  <entry>
    <id>1</id>
    <title>entry</title>
    <updated>2026-01-01T00:00:00Z</updated>
    <content type="html">{markup}</content>
  </entry>
</feed>
"""


def _rss_feed(markup: str = MARKUP) -> bytes:
    return RSS_TEMPLATE.format(markup=markup).encode("utf-8")


def _atom_feed(markup: str = MARKUP) -> bytes:
    import xml.sax.saxutils

    escaped = xml.sax.saxutils.escape(markup)
    return ATOM_TEMPLATE.format(markup=escaped).encode("utf-8")


def _json_feed(markup: str = MARKUP) -> io.StringIO:
    payload = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "tenant",
        "items": [
            {
                "id": "1",
                "content_html": markup,
            }
        ],
    }
    return io.StringIO(json.dumps(payload))


def _parse(content, policy=None, *, json_feed=False, sanitize_html=None):
    headers = (
        {"content-type": "application/feed+json"} if json_feed else None
    )
    kwargs = {}
    if policy is not None:
        kwargs["sanitization_policy"] = policy
    if sanitize_html is not None:
        kwargs["sanitize_html"] = sanitize_html
    return feedparser.parse(content, response_headers=headers, **kwargs)


def _html(result) -> str:
    """Return the sanitized HTML body of the first parsed entry."""

    entry = result.entries[0]
    if "content" in entry:
        content = entry.content
        if isinstance(content, list):
            return content[0].value
        return content.value
    return entry.summary_detail.value


@pytest.fixture
def tenant_policies():
    default = SanitizationPolicy.default()
    policy_a = default.expanded(elements={"custom-a"})
    policy_b = default.expanded(elements={"custom-b"})
    return policy_a, policy_b


def test_default_policy_matches_builtin_sanitizer_output():
    result = _parse(_rss_feed())
    value = _html(result)
    # Unknown custom elements are dropped, disallowed CSS properties are
    # stripped, and javascript: hrefs are neutralized.
    assert "<custom-a>" not in value
    assert "<custom-b>" not in value
    assert "position" not in value
    assert "color: red" in value
    assert 'href=""' in value
    assert "javascript" not in value


def test_default_policy_is_immutable_and_shares_no_mutable_state():
    policy = SanitizationPolicy.default()
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.elements = frozenset()  # type: ignore[misc]
    assert isinstance(policy.elements, frozenset)
    assert isinstance(policy.attributes, frozenset)
    assert isinstance(policy.css_properties, frozenset)
    assert isinstance(policy.uri_schemes, tuple)


def test_restricted_only_tightens_and_rejects_unknown_names():
    default = SanitizationPolicy.default()
    tight = default.restricted(
        elements={"p"},
        attributes=set(),
        css_properties={"color"},
        uri_schemes=("https",),
    )
    result = _parse(_rss_feed(), tight)
    value = _html(result)
    assert "<p>" in value
    assert "<a " not in value

    with pytest.raises(ValueError):
        default.restricted(elements={"custom-a"})
    with pytest.raises(ValueError):
        default.restricted(attributes={"onclick"})
    with pytest.raises(ValueError):
        default.restricted(css_properties={"position"})
    with pytest.raises(ValueError):
        default.restricted(uri_schemes=("javascript",))


def test_expanded_requires_explicit_additions():
    default = SanitizationPolicy.default()
    # Nothing changes unless additions are explicitly named.
    assert default.expanded() == default

    policy = default.expanded(
        elements={"custom-a"},
        uri_schemes=("mailto",),
    )
    assert "custom-a" in policy.elements
    assert "custom-b" not in policy.elements
    assert "mailto" in policy.uri_schemes
    # The source policy is never mutated.
    assert "custom-a" not in default.elements


def test_restricted_rejects_empty_uri_scheme_tuple_widening():
    default = SanitizationPolicy.default()
    with pytest.raises(ValueError):
        default.restricted(uri_schemes=())

    # A genuinely allow-all policy (constructed explicitly) stays
    # permissive when expanded rather than collapsing into a whitelist.
    open_policy = dataclasses.replace(default, uri_schemes=())
    assert open_policy.expanded(uri_schemes=("foo",)).uri_schemes == ()
    # And restricting it back down selects a concrete whitelist.
    tightened = open_policy.restricted(uri_schemes=("https",))
    assert tightened.uri_schemes == ("https",)


def test_restricted_policy_strips_css_properties_and_uri_schemes():
    tight = SanitizationPolicy.default().restricted(
        css_properties=set(),
        uri_schemes=("https",),
    )
    result = _parse(_rss_feed(), tight)
    value = _html(result)
    assert "style" not in value or 'style=""' in value
    assert 'href=""' in value


def test_expanded_uri_scheme_is_explicitly_allowed():
    policy = SanitizationPolicy.default().expanded(uri_schemes=("javascript",))
    result = _parse(_rss_feed(), policy)
    value = _html(result)
    assert 'href="javascript:alert(1)"' in value

    # The default policy used by another call must not have been widened.
    default_result = _parse(_rss_feed())
    assert "javascript" not in _html(default_result)


@pytest.mark.parametrize("feed_factory", (_rss_feed, _atom_feed))
def test_custom_tags_isolated_per_policy_in_xml_feeds(
    feed_factory, tenant_policies
):
    policy_a, policy_b = tenant_policies

    result_a = _parse(feed_factory(), policy_a)
    result_b = _parse(feed_factory(), policy_b)
    result_default = _parse(feed_factory())

    value_a = _html(result_a)
    value_b = _html(result_b)
    value_default = _html(result_default)

    assert "<custom-a>a</custom-a>" in value_a
    assert "<custom-b>" not in value_a
    assert "<custom-b>b</custom-b>" in value_b
    assert "<custom-a>" not in value_b
    assert "<custom-a>" not in value_default
    assert "<custom-b>" not in value_default


def test_same_policy_used_for_json_feed_content_html(tenant_policies):
    policy_a, policy_b = tenant_policies

    value_a = _html(_parse(_json_feed(), policy_a, json_feed=True))
    value_b = _html(_parse(_json_feed(), policy_b, json_feed=True))
    value_default = _html(_parse(_json_feed(), json_feed=True))

    assert "<custom-a>a</custom-a>" in value_a
    assert "<custom-b>" not in value_a
    assert "<custom-b>b</custom-b>" in value_b
    assert "<custom-a>" not in value_b
    assert "<custom-a>" not in value_default
    assert "<custom-b>" not in value_default


def test_sanitize_html_false_keeps_explicit_opt_out_semantics(tenant_policies):
    policy_a, _ = tenant_policies
    result = _parse(_rss_feed(), policy_a, sanitize_html=False)
    value = _html(result)
    assert "<script>" not in value  # this feed has no script, but check raw
    assert "<custom-b>b</custom-b>" in value
    assert "javascript:alert(1)" in value


def test_interleaved_parses_keep_tenant_policies_separated(tenant_policies):
    policy_a, policy_b = tenant_policies
    seen_a: list[str] = []
    seen_b: list[str] = []

    for index in range(20):
        if index % 2 == 0:
            value = _html(_parse(_rss_feed(), policy_a))
            seen_a.append(value)
        else:
            value = _html(_parse(_rss_feed(), policy_b))
            seen_b.append(value)

    assert all("<custom-a>a</custom-a>" in value for value in seen_a)
    assert all("<custom-b>" not in value for value in seen_a)
    assert all("<custom-b>b</custom-b>" in value for value in seen_b)
    assert all("<custom-a>" not in value for value in seen_b)


def test_multithreaded_parses_keep_tenant_policies_separated(tenant_policies):
    policy_a, policy_b = tenant_policies
    errors: list[BaseException] = []

    def worker(policy: SanitizationPolicy, expected: str, forbidden: str):
        try:
            for _ in range(50):
                value = _html(_parse(_rss_feed(), policy))
                assert expected in value
                assert forbidden not in value
                # The shared policy object must remain intact for other
                # threads.
                assert policy == SanitizationPolicy.default().expanded(
                    elements={expected.split(">")[0].lstrip("<")}
                )
        except BaseException as exc:  # pragma: no cover - failure reporting
            errors.append(exc)

    threads = [
        threading.Thread(
            target=worker,
            args=(policy_a, "<custom-a>a</custom-a>", "<custom-b>"),
        ),
        threading.Thread(
            target=worker,
            args=(policy_b, "<custom-b>b</custom-b>", "<custom-a>"),
        ),
        threading.Thread(
            target=worker,
            args=(
                SanitizationPolicy.default(),
                "<p",
                "<custom-a>",
            ),
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []


def test_nested_parse_inside_a_policy_parse_is_unaffected(tenant_policies):
    policy_a, _ = tenant_policies
    nested_values: list[str] = []

    original_feed = HTMLSanitizer.feed
    nested_done = False

    def spying_feed(self, data):
        nonlocal nested_done
        if not nested_done and self.policy.elements == policy_a.elements:
            nested_done = True
            # Re-enter parse() with the default policy while the outer
            # sanitizer is about to process its document.
            nested_values.append(_html(_parse(_rss_feed())))
        return original_feed(self, data)

    HTMLSanitizer.feed = spying_feed
    try:
        outer = _parse(_rss_feed(), policy_a)
    finally:
        HTMLSanitizer.feed = original_feed

    outer_value = _html(outer)
    assert "<custom-a>a</custom-a>" in outer_value
    assert len(nested_values) == 1
    assert "<custom-a>" not in nested_values[0]
    assert "<custom-b>" not in nested_values[0]
    # A later default parse must still behave like the default.
    later_default = _parse(_rss_feed())
    assert "<custom-a>" not in _html(later_default)


def test_exception_during_parse_does_not_change_other_calls(tenant_policies):
    policy_a, _ = tenant_policies

    original_feed = HTMLSanitizer.feed

    def boom(self, data):
        if self.policy.elements == policy_a.elements:
            raise RuntimeError("tenant A parse failure")
        return original_feed(self, data)

    HTMLSanitizer.feed = boom
    try:
        with pytest.raises(RuntimeError):
            _parse(_rss_feed(), policy_a)
    finally:
        HTMLSanitizer.feed = original_feed

    value = _html(_parse(_rss_feed()))
    assert "<custom-a>" not in value
    assert "<custom-b>" not in value

    policy_b_value = _html(_parse(_rss_feed(), tenant_policies[1]))
    assert "<custom-b>b</custom-b>" in policy_b_value


def test_policy_does_not_mutate_class_attributes():
    default_elements = set(HTMLSanitizer.acceptable_elements)
    policy = SanitizationPolicy.default().expanded(elements={"custom-a"})
    _parse(_rss_feed(), policy)
    assert set(HTMLSanitizer.acceptable_elements) == default_elements
    assert "custom-a" not in HTMLSanitizer.acceptable_elements
