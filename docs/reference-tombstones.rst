.. _reference.tombstones:

``tombstones``
==============

A list of Atom tombstones (``at:deleted-entry`` elements, identified by the
``http://purl.org/atompub/tombstones/1.0`` namespace URI regardless of the
prefix used in the document) found in the feed.

Each tombstone is a dictionary with these keys:

*   ``ref``: the ID of the deleted entry.
*   ``when``: the deletion time, exactly as it appeared in the feed.
*   ``when_parsed``: the deletion time as a parsed time tuple.
*   ``by``: optional dictionary with ``name``, ``email``, and/or ``href``
    of the person or entity that removed the entry.
*   ``comment``: optional text explaining why the entry was removed.

Tombstones with a missing ``ref`` or a missing/unparseable ``when`` cannot
act as deletions; they are reported in :ref:`reference.tombstone_diagnostics`
instead.

.. tip::

    This element always exists, although it may be an empty list.
    See :ref:`advanced.tombstones` for how to merge tombstones with entries.


.. _reference.tombstone_diagnostics:

``tombstone_diagnostics``
=========================

A list of ``at:deleted-entry`` elements that could not be turned into
deletions. Each diagnostic preserves whatever was captured (including the
original ``when`` text) and adds a ``problems`` list describing why the
tombstone was rejected (``"missing ref"``, ``"missing when"``, and/or
``"invalid when"``).

.. tip::

    This element always exists, although it may be an empty list.
