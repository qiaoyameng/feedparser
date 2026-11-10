Features
--------

*   Add an optional ``hierarchical_media`` argument to ``feedparser.parse()``
    that preserves the structure of Media RSS ``media:group`` and
    ``media:content`` elements.  Entries expose ``media_groups`` and
    ``media_ungrouped_content`` while the existing flat ``media_content``
    fields keep their historical shape.  Group-level ``title``,
    ``description``, ``credit``, ``rating`` and ``thumbnail`` are inherited
    by nested contents, with content-level declarations taking precedence,
    and relative media URLs are resolved against the effective ``xml:base``.
