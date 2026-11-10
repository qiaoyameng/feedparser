import copy
import itertools

import feedparser
from feedparser import MergeConflict, apply_batch

ADD_FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>urn:test:feed</id>
  <title>Test feed</title>
  <updated>2026-01-02T00:00:00Z</updated>
  <entry>
    <id>urn:test:1</id>
    <title>One</title>
    <updated>2026-01-02T00:00:00Z</updated>
  </entry>
</feed>
"""

DELETE_FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:at="http://purl.org/atompub/tombstones/1.0">
  <id>urn:test:feed</id>
  <title>Test feed</title>
  <updated>2026-01-03T00:00:00Z</updated>
  <at:deleted-entry ref="urn:test:1" when="2026-01-03T00:00:00Z">
    <at:by>
      <name>Admin</name>
      <email>admin@example.com</email>
    </at:by>
    <at:comment>spam</at:comment>
  </at:deleted-entry>
</feed>
"""

REAPPEAR_FEED = ADD_FEED.replace("2026-01-02", "2026-01-04").replace(
    "<title>One</title>", "<title>One v2</title>"
)


def test_strict_parse_exposes_tombstones():
    result = feedparser.parse(DELETE_FEED)
    assert not result.bozo
    assert result.entries == []
    assert result.tombstone_diagnostics == []
    assert len(result.tombstones) == 1
    tombstone = result.tombstones[0]
    assert tombstone["ref"] == "urn:test:1"
    # The original timestamp text is preserved alongside the parsed value.
    assert tombstone["when"] == "2026-01-03T00:00:00Z"
    assert tombstone["when_parsed"] is not None
    assert tombstone["when_parsed"].tm_year == 2026
    assert tombstone["by"]["name"] == "Admin"
    assert tombstone["by"]["email"] == "admin@example.com"
    assert tombstone["comment"] == "spam"


def test_loose_parse_exposes_tombstones():
    # An undefined entity forces the strict parser to fail so that the
    # loose parser handles the document.
    data = DELETE_FEED.replace(
        "<at:comment>spam</at:comment>", "<at:comment>spam &nbsp; eggs</at:comment>"
    )
    result = feedparser.parse(data)
    assert result.bozo
    assert len(result.tombstones) == 1
    tombstone = result.tombstones[0]
    assert tombstone["ref"] == "urn:test:1"
    assert tombstone["when"] == "2026-01-03T00:00:00Z"
    assert tombstone["by"]["name"] == "Admin"
    assert "spam" in tombstone["comment"]


def test_tombstones_matched_by_namespace_uri_not_prefix():
    data = DELETE_FEED.replace("at:", "tomb:").replace("xmlns:at=", "xmlns:tomb=")
    result = feedparser.parse(data)
    assert len(result.tombstones) == 1
    assert result.tombstones[0]["ref"] == "urn:test:1"


def test_missing_ref_leaves_diagnostic():
    data = DELETE_FEED.replace(' ref="urn:test:1"', "")
    result = feedparser.parse(data)
    assert result.tombstones == []
    assert len(result.tombstone_diagnostics) == 1
    diagnostic = result.tombstone_diagnostics[0]
    assert "missing ref" in diagnostic["problems"]
    assert diagnostic["when"] == "2026-01-03T00:00:00Z"


def test_invalid_when_leaves_diagnostic():
    data = DELETE_FEED.replace('when="2026-01-03T00:00:00Z"', 'when="not-a-date"')
    result = feedparser.parse(data)
    assert result.tombstones == []
    assert len(result.tombstone_diagnostics) == 1
    diagnostic = result.tombstone_diagnostics[0]
    assert diagnostic["ref"] == "urn:test:1"
    assert "invalid when" in diagnostic["problems"]
    # The original timestamp text is preserved in the diagnostic.
    assert diagnostic["when"] == "not-a-date"
    assert diagnostic["when_parsed"] is None


def test_entries_behavior_unchanged():
    result = feedparser.parse(ADD_FEED)
    assert len(result.entries) == 1
    assert result.entries[0]["id"] == "urn:test:1"
    assert result.entries[0]["title"] == "One"
    assert result.tombstones == []
    assert result.tombstone_diagnostics == []


def _apply_in_order(names, batches):
    state = {}
    for name in names:
        state, _ = apply_batch(state, batches[name])
    return state


def test_merge_is_order_independent():
    batches = {
        "add": feedparser.parse(ADD_FEED),
        "delete": feedparser.parse(DELETE_FEED),
        "reappear": feedparser.parse(REAPPEAR_FEED),
    }
    final_states = [
        _apply_in_order(order, batches) for order in itertools.permutations(batches)
    ]
    for state in final_states:
        assert state == final_states[0]
    record = final_states[0]["urn:test:1"]
    assert record["kind"] == "entry"
    assert record["time_raw"] == "2026-01-04T00:00:00Z"
    assert record["payload"]["title"] == "One v2"


def test_merge_deletion_wins_over_older_entry():
    state, _ = apply_batch({}, feedparser.parse(DELETE_FEED))
    state, conflicts = apply_batch(state, feedparser.parse(ADD_FEED))
    assert conflicts == []
    record = state["urn:test:1"]
    assert record["kind"] == "deleted"
    assert record["time_raw"] == "2026-01-03T00:00:00Z"


def test_merge_reappearing_entry_wins_over_older_deletion():
    state, _ = apply_batch({}, feedparser.parse(DELETE_FEED))
    state, conflicts = apply_batch(state, feedparser.parse(REAPPEAR_FEED))
    assert conflicts == []
    assert state["urn:test:1"]["kind"] == "entry"


def test_merge_is_idempotent_for_repeated_batches():
    parsed = feedparser.parse(DELETE_FEED)
    state, _ = apply_batch({}, parsed)
    again, conflicts = apply_batch(state, parsed)
    assert again == state
    assert conflicts == []


def test_merge_same_time_content_conflict_is_reported():
    other = ADD_FEED.replace("<title>One</title>", "<title>Different</title>")
    state, _ = apply_batch({}, feedparser.parse(ADD_FEED))
    state, conflicts = apply_batch(state, feedparser.parse(other))
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert isinstance(conflict, MergeConflict)
    assert conflict.id == "urn:test:1"
    assert conflict.existing["payload"]["title"] == "One"
    assert conflict.incoming["payload"]["title"] == "Different"
    # The first event at a given time is kept.
    assert state["urn:test:1"]["payload"]["title"] == "One"


def test_merge_same_time_entry_versus_deletion_conflict_is_reported():
    deletion = DELETE_FEED.replace("2026-01-03", "2026-01-02")
    state, _ = apply_batch({}, feedparser.parse(ADD_FEED))
    state, conflicts = apply_batch(state, feedparser.parse(deletion))
    assert len(conflicts) == 1
    assert conflicts[0].existing["kind"] == "entry"
    assert conflicts[0].incoming["kind"] == "deleted"
    assert state["urn:test:1"]["kind"] == "entry"


def test_merge_does_not_mutate_inputs():
    parsed = feedparser.parse(ADD_FEED)
    parsed_snapshot = copy.deepcopy(parsed)
    state, _ = apply_batch({}, parsed)
    state_snapshot = copy.deepcopy(state)
    apply_batch(state, parsed)
    assert parsed == parsed_snapshot
    assert state == state_snapshot
