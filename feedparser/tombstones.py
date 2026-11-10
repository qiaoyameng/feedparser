"""Incremental merge support for Atom tombstone deletion events.

This module provides a pure, standalone helper that merges parsed feeds
(normal entries plus ``at:deleted-entry`` tombstones) into a caller-owned
state mapping. It performs no network I/O, maintains no database, and never
mutates its inputs; applying the same batch twice yields the same state.

Merge semantics:

*   Entry ID (``id`` for entries, ``ref`` for tombstones) is the identity.
*   ``updated`` (entries) and ``when`` (tombstones) are the event times.
*   A newer event wins; an older event is ignored.
*   Same-time events with conflicting content are reported as conflicts.
*   A normal entry that is newer than a deletion reappears in the state.
"""

import copy
import typing

__all__ = (
    "MergeConflict",
    "apply_batch",
)


class MergeConflict(typing.NamedTuple):
    """Two events for the same ID at the same time with different content."""

    id: str
    existing: dict
    incoming: dict


def _time_key(value):
    """Sort key for event times; missing/unparseable times sort oldest."""

    if value is None:
        return (0, ())
    return (1, tuple(value))


def _records_from(parsed):
    """Build merge records from a parse result without mutating it."""

    for entry in parsed.get("entries") or ():
        entry_id = entry.get("id")
        if not entry_id:
            continue
        yield {
            "kind": "entry",
            "id": entry_id,
            "time": entry.get("updated_parsed"),
            "time_raw": entry.get("updated"),
            "payload": copy.deepcopy(dict(entry)),
        }
    for tombstone in parsed.get("tombstones") or ():
        ref = tombstone.get("ref")
        if not ref:
            continue
        yield {
            "kind": "deleted",
            "id": ref,
            "time": tombstone.get("when_parsed"),
            "time_raw": tombstone.get("when"),
            "payload": copy.deepcopy(dict(tombstone)),
        }


def apply_batch(state, parsed):
    """Merge one parsed batch into *state* and return the new state.

    :param state:
        A mapping of entry ID to record, as returned by a previous call to
        this function (or ``None``/an empty mapping for a fresh state).
        It is not modified.
    :param parsed:
        A parse result (or any mapping) with ``entries`` and ``tombstones``
        lists, such as the value returned by :func:`feedparser.parse`.
        It is not modified.
    :returns:
        A ``(new_state, conflicts)`` tuple. ``new_state`` maps entry IDs to
        records with ``kind`` (``"entry"`` or ``"deleted"``), ``time``,
        ``time_raw`` (the original timestamp text), and ``payload`` keys.
        ``conflicts`` is a list of :class:`MergeConflict` for same-time
        events whose content disagrees.
    """

    new_state = dict(state) if state else {}
    conflicts = []
    for record in _records_from(parsed):
        existing = new_state.get(record["id"])
        if existing is None:
            new_state[record["id"]] = record
            continue
        existing_key = _time_key(existing["time"])
        record_key = _time_key(record["time"])
        if record_key > existing_key:
            new_state[record["id"]] = record
        elif record_key == existing_key:
            if (
                existing["kind"] != record["kind"]
                or existing["payload"] != record["payload"]
            ):
                conflicts.append(MergeConflict(record["id"], existing, record))
        # Older events are ignored.
    return new_state, conflicts
