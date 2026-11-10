.. _advanced.hierarchical_media:

Hierarchical Media RSS
======================

Media RSS feeds may group several ``media:content`` elements inside a
``media:group``, for example one video per language.  By default,
:program:`Universal Feed Parser` flattens every ``media:content`` element into
a single ``media_content`` list on the entry, so the relationship between a
group, its contents, and the metadata declared on each of them is lost.

Pass ``hierarchical_media=True`` to :func:`feedparser.parse` to keep that
structure.  The flat ``media_content``, ``media_thumbnail``, ``media_credit``,
``media_rating`` and related fields keep their historical shape and are always
populated.

..  code-block:: pycon

    >>> import feedparser
    >>> d = feedparser.parse(url, hierarchical_media=True)
    >>> entry = d.entries[0]


Group and content structure
---------------------------

Each entry exposes two additional fields:

*   ``media_groups`` is a list with one dictionary per ``media:group``.
    Every group dictionary contains:

    *   ``attrs`` -- the attributes declared on the ``media:group`` element;
    *   ``content`` -- one dictionary per nested ``media:content`` element;
    *   ``title``, ``description``, ``credit``, ``rating`` and
        ``thumbnail`` -- the metadata declared on the group, when present.

*   ``media_ungrouped_content`` lists the ``media:content`` elements that
    appear outside every ``media:group``.  Ungrouped thumbnails are collected
    in ``media_ungrouped_thumbnail``.

``title`` and ``description`` are dictionaries carrying the element text in
their ``value`` key together with the element's attributes (such as
``type``).  ``credit`` and ``thumbnail`` are always lists because the Media
RSS specification allows them to repeat; every occurrence is preserved, in
document order.  ``rating`` is a single dictionary.


Inheritance and precedence
--------------------------

Group-level ``title``, ``description``, ``credit``, ``rating`` and
``thumbnail`` act as defaults for the ``media:content`` elements in that
group.  A value declared on the content itself takes precedence:

*   a content-level single-valued element (``title``, ``description`` or
    ``rating``) replaces the inherited value;
*   a content-level repeatable element (``credit`` or ``thumbnail``) replaces
    the inherited list rather than being merged with it; when the content
    declares nothing, the group default is inherited unchanged.

Inherited values are deep copies.  Modifying the lists returned for one
content never affects sibling contents or the group itself.


URL resolution
--------------

The flat fields keep the raw ``url`` attribute.  Hierarchical nodes keep that
raw ``url`` and, when it is relative, additionally expose the absolute URI in
``href``, resolved against the effective ``xml:base`` in scope for the
element.  Absolute URLs are stored unchanged.  The namespace prefix used in
the feed is irrelevant; matching is done on the Media RSS namespace URI.

A ``media:title`` element never overrides the entry's regular ``title``.
