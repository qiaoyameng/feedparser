.. _reference.date_detail:

``*_date_detail``
=================

When ``date_details=True`` is passed to :func:`feedparser.parse`, every parsed
date is accompanied by a detail dictionary that records where the parsed value
came from. The key mirrors the parsed-tuple key: ``published_parsed`` is paired
with ``published_date_detail``, ``updated_parsed`` with
``updated_date_detail``, and likewise for ``created``, ``expired``,
``validity_start``, ``validity_end`` and (for HTTP ``Last-Modified`` headers)
``modified``.

The dictionary always contains these keys:

* ``value``: the original date string from the feed, unchanged.
* ``handler``: the name of the date handler that parsed the value, or
  ``"unknown"`` if every registered handler failed.
* ``precision``: ``"day"``, ``"minute"`` or ``"second"``, based solely on the
  components present in the source string.
* ``timezone_explicit``: ``True`` or ``False`` when the handler can determine
  whether a timezone was given, and ``"unknown"`` for legacy handlers that
  only return a 9-tuple.
* ``timezone_offset``: the source offset from UTC in minutes, or
  ``"unknown"`` when no timezone was given or it cannot be determined.

The ``"unknown"`` string means the information has no basis in the source
data. feedparser does not infer timezone presence, offsets, or precision from
the zero-valued fields of the normalized UTC 9-tuple.

See :ref:`advanced.date.date_details` for examples and the custom handler
protocol.


.. seealso::

    * :ref:`advanced.date`
    * :ref:`reference.entry.published_parsed`
    * :ref:`reference.feed.updated_parsed`
