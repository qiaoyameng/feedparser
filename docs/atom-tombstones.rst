.. _advanced.tombstones:

Atom Tombstones and Incremental Merging
#######################################

Some Atom feeds advertise deletions with ``at:deleted-entry`` elements
(`RFC 6721 <https://www.rfc-editor.org/rfc/rfc6721>`_). These elements are
not entries, so they never appear in ``entries``; they are exposed separately
as :ref:`reference.tombstones`, with rejected elements reported in
:ref:`reference.tombstone_diagnostics`.

:func:`feedparser.apply_batch` merges one parsed batch into a caller-owned
state mapping. It performs no network I/O, keeps no database, and never
modifies its inputs; applying the same batch twice produces the same state.

..  code-block:: python

    import feedparser

    state = {}
    for url in urls:
        parsed = feedparser.parse(url)
        state, conflicts = feedparser.apply_batch(state, parsed)

The merge rules are:

*   The entry ID (``id`` for entries, ``ref`` for tombstones) is the identity.
*   ``updated`` (entries) and ``when`` (tombstones) are the event times.
*   A newer event replaces an older one; older events are ignored.
*   Events at the same time with conflicting content are returned as
    :class:`feedparser.MergeConflict` tuples.
*   An entry that is newer than a deletion reappears in the state.

``apply_batch`` returns a ``(new_state, conflicts)`` tuple. ``new_state``
maps entry IDs to records with ``kind`` (``"entry"`` or ``"deleted"``),
``time``, ``time_raw`` (the original timestamp text), and ``payload`` keys.
