.. _advanced.uri_sources:

Tracking URI Sources
====================

When relative :abbr:`URI (Uniform Resource Identifier)`\s are resolved, the
original relative text is normally replaced by the resolved absolute
:abbr:`URI`, so it is no longer possible to tell which ``xml:base`` was in
effect or why a resolved :abbr:`URI` looks wrong.  Pass
``track_uri_sources=True`` to :func:`feedparser.parse` to keep this
provenance alongside the existing data:

..  code-block:: pycon

    >>> import feedparser
    >>> d = feedparser.parse(feed_text, track_uri_sources=True)
    >>> d.uri_sources
    [FeedParserDict({'field': 'links', ...})]

The feature is strictly opt-in.  When it is disabled (the default) the
parsed object is unchanged, and no extra keys or :class:`list` entries are
created.


The ``uri_sources`` list
------------------------

One record is appended for every tracked :abbr:`URI` reference, in document
order.  Repeated references to the same field are kept separate with an
``occurrence`` counter; they are never collapsed by field name.  Each record
contains:

* ``source``: the original value exactly as written in the feed;
* ``base``: the base :abbr:`URI` that was effective at the reference's
  location after every in-scope ``xml:base`` was applied;
* ``resolved``: the value actually stored on the parsed object;
* ``reason``: an empty string when resolution succeeded, otherwise a
  machine-readable explanation;
* ``base_chain``: the ordered document base and ``xml:base`` declarations
  that produced ``base``;
* ``field``, ``scope`` (``feed``, ``entry`` or ``source``) and, for entry
  data, ``entry_index``;
* ``occurrence``: the zero-based position of the reference within its field
  location;
* ``attribute`` and ``tag`` for references found on feed elements (such as
  ``link`` ``href``) or on elements inside embedded
  :abbr:`HTML (HyperText Markup Language)` /
  :abbr:`XHTML (Extensible HyperText Markup Language)` markup (such as an
  ``img`` ``src``).

Tracked feed fields include ``link``/``links``, ``enclosure`` (stored on
``links`` and exposed through ``enclosures``), ``id``, ``comments``,
``docs``, author and contributor ``href`` values, ``generator_detail`` and
Atom ``content`` ``src``.  Within embedded markup every ``href``/``src``
attribute that :ref:`relative link resolution <advanced.base>` rewrites is
tracked as well.

References inside embedded markup are only rewritten when
``resolve_relative_uris`` is enabled (the default).  Passing
``resolve_relative_uris=False`` leaves the markup untouched, so no
markup-level records are produced; feed-level references such as ``link``
continue to be tracked because their resolution is not governed by that
option.


The ``base_sources`` list
-------------------------

``base_sources`` records how the working base :abbr:`URI` was derived, in
encounter order:

* document-level candidates from the :abbr:`HTTP (HyperText Transfer
  Protocol)` response, each flagged with ``effective`` when it is the
  candidate that became the working base;
* every ``xml:base`` declaration, including declarations that could not be
  applied.  An ineffective declaration keeps its raw text and a ``reason``
  and leaves the previous base in effect.

Nested ``xml:base`` declarations follow
`XML:Base <http://www.w3.org/TR/xmlbase/>`_ scoping: a declaration applies to
the element carrying it and its descendants, and the previous base is
restored when the element closes.  A relative ``xml:base`` is resolved
against the base in effect at that point.


HTTP base precedence
--------------------

When a feed is retrieved over :abbr:`HTTP`, the initial base is calculated
using the same precedence as ordinary resolution:

#. the ``Content-Location`` response header resolved against the final
   response :abbr:`URL` (the value also exposed as ``d.href``, which already
   follows redirects);
#. the ``Content-Location`` header on its own;
#. the final response :abbr:`URL`.

In other words, ``Content-Location`` wins whenever it yields a safe
absolute :abbr:`URI`; the final :abbr:`URL` is only used when no usable
``Content-Location`` is available.  When feeds are parsed from strings or
files, pass the location explicitly through the ``response_headers``
parameter's ``content-location`` key.


Unresolvable references
-----------------------

The same rules are shared by the strict and loose parsers.  A reference is
never invented:

* with no usable base, a relative reference keeps its original text and the
  record carries ``reason = "no base URI is available"``;
* a malformed :abbr:`URI` keeps its original text and the record carries
  ``reason = "the URI is malformed"`` while the stored value follows the
  normal (empty-string) behavior;
* an unacceptable :abbr:`URI` scheme keeps its original text and the record
  carries ``reason = "the URI scheme is not allowed"`` (or
  ``"the base URI scheme is not allowed"`` when the base itself is unsafe).
