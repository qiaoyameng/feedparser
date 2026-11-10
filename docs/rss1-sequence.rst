.. _rss1.sequence:

RSS 1.0 Channel Sequences
#########################

:abbr:`RSS (Rich Site Summary)` 1.0 is an :abbr:`RDF (Resource Description
Framework)`/XML format.  The ``item`` elements are top-level RDF resources
and may appear anywhere in the document, including after the channel that
references them.  The authoritative member order of a channel is therefore
not the document order of the ``item`` elements; it is the ``rdf:li`` list
nested in ``channel/items/rdf:Seq``.

By default feedparser keeps its historical behavior and returns every
``item`` in a flat, document-order :py:attr:`FeedParserDict.entries` list.
Pass ``rss1_sequence=True`` to :func:`feedparser.parse` to opt into explicit
RSS 1.0 sequence handling instead.

..  code-block:: pycon

    >>> import feedparser
    >>> result = feedparser.parse(feed_text, rss1_sequence=True)

Sequence mode understands only the RSS 1.0 vocabulary; it is not a
general-purpose RDF reasoner and never follows triples outside the
``rdf:RDF``/``channel``/``items``/``rdf:Seq``/``rdf:li``/``item`` elements.
It has no effect on RSS 2.0, Atom, JSON or other feed types.

Resource identity
=================

Each ``item`` is identified by its ``rdf:about`` and each sequence member by
its ``rdf:resource``.  Both attributes are resolved to absolute URIs against
the ``xml:base`` in scope at that element before they are compared, so a
relative reference in a sequence matches an item declared under a different
parent ``xml:base`` as long as both resolve to the same absolute URI.  The
entry itself keeps its original ``rdf:about`` value as its ``id``; the
absolute URI is only used internally to match references.

Forward references (an ``rdf:li`` that points to an ``item`` defined later in
the document) are resolved, and a single item may be referenced by more than
one channel.  Each channel keeps its own member order and refers to the same
parsed entry object.

Sequence results
================

When sequence mode is active on an RSS 1.0 feed, ``result.feed`` gains three
extra keys:

``rss1_channels``
    A list with one dictionary per channel.  Each dictionary contains
    ``resource`` (the resolved channel ``rdf:about``, or ``None``),
    ``members`` (the ordered list of resolved member URIs, including any
    repeats) and ``entries`` (the entries resolved from those members in the
    same order).
``rss1_unsequenced_entries``
    Entries that no channel sequence references.  They are never attached to
    the first channel automatically.
``rss1_diagnostics``
    Locatable problems encountered while assembling the sequences.  Each
    diagnostic has ``type``, ``message``, ``uri`` (when applicable) and
    ``line`` (populated by the strict XML parser, ``None`` otherwise).

The flat ``result.entries`` list is rebuilt as the sequenced entries (in
first-reference order across the channels) followed by the unsequenced
entries, so existing entry-oriented code keeps working.

Diagnostic types
================

``missing_reference``
    An ``rdf:li`` references an item URI that is never defined by an
    ``rdf:about`` in the document.  The reference is skipped.
``duplicate_member``
    The same resource appears more than once in one channel's sequence.  The
    repeat is retained in ``members``/``entries`` and reported.
``conflicting_definition``
    More than one ``item`` shares an ``rdf:about`` but their parsed contents
    differ.  The first definition is used for sequence assembly and the
    others are retained and reported.
``missing_resource``
    An ``rdf:li`` inside a sequence has no ``rdf:resource`` and cannot be
    matched to an item, so it is ignored.

``rdf:li`` elements from any namespace other than the RDF namespace are not
sequence members and never enter ``members``.
