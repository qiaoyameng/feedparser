# Copyright 2010-2025 Kurt McKee <contactme@kurtmckee.org>
# Copyright 2002-2008 Mark Pilgrim
# All rights reserved.
#
# This file is a part of feedparser.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice
#   in this list of conditions and the following disclaimer in the
#   documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS 'AS IS'
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""Opt-in tracking of how every string-based URI reference is resolved.

The tracking implemented in this module is intentionally separate from the
normal parsing flow.  It is only activated when ``track_uri_sources=True`` is
passed to :func:`feedparser.parse`, so the shape and size of the result
object do not change when the feature is not requested.

Each tracked reference keeps three pieces of information:

* the original value as written in the feed (``source``);
* the base URI that was in effect at the reference's location (``base``),
  including the full chain of bases that produced it (``base_chain``);
* the value that was actually stored on the parsed object (``resolved``).

References that cannot be resolved safely keep their original text and carry
a machine-readable ``reason`` instead of a fabricated absolute URI.
"""

from __future__ import annotations

import urllib.parse

from .urls import ACCEPTABLE_URI_SCHEMES, _urljoin
from .util import FeedParserDict

# Machine-readable reasons stored on records whose URI could not be resolved.
REASON_NO_BASE = "no base URI is available"
REASON_MALFORMED = "the URI is malformed"
REASON_UNACCEPTABLE_SCHEME = "the URI scheme is not allowed"
REASON_UNACCEPTABLE_BASE_SCHEME = "the base URI scheme is not allowed"

ORIGIN_XML_BASE = "xml:base"


def _scheme_of(uri: str) -> str:
    try:
        return urllib.parse.urlparse(uri)[0]
    except ValueError:
        return ""


def explain_join(base: str, uri: str) -> tuple[str, str]:
    """Mirror the loose ``_urljoin()`` resolution used by element text.

    :return: ``(resolved, reason)`` where ``reason`` is an empty string when
        the reference could be resolved.
    """

    try:
        resolved = _urljoin(base, uri)
    except ValueError:
        return "", REASON_MALFORMED
    if not resolved:
        return "", REASON_MALFORMED
    return resolved, ""


def explain_safe(base: str, uri: str) -> tuple[str, str]:
    """Mirror :func:`feedparser.urls.make_safe_absolute_uri`.

    :return: ``(resolved, reason)`` where ``reason`` is an empty string when
        the reference could be resolved to an acceptable absolute URI.
    """

    if not ACCEPTABLE_URI_SCHEMES:
        return explain_join(base, uri)
    if not base:
        if not uri:
            return "", REASON_MALFORMED
        scheme = _scheme_of(uri)
        if not scheme or scheme in ACCEPTABLE_URI_SCHEMES:
            return uri, ""
        return "", REASON_UNACCEPTABLE_SCHEME
    try:
        resolved = _urljoin(base, uri)
    except ValueError:
        return "", REASON_MALFORMED
    if not resolved:
        return "", REASON_MALFORMED
    if _scheme_of(base) not in ACCEPTABLE_URI_SCHEMES:
        return "", REASON_UNACCEPTABLE_BASE_SCHEME
    scheme = resolved.strip().split(":", 1)[0]
    if scheme not in ACCEPTABLE_URI_SCHEMES:
        return "", REASON_UNACCEPTABLE_SCHEME
    return resolved, ""


class URISourceTracker:
    """Track base URI scope changes and individual references.

    The strict and loose feed parsers share this class.  ``enter_element()``
    and ``exit_element()`` mirror the push/pop handling of ``xml:base`` in
    :class:`feedparser.mixin.XMLParserMixin`, while the ``record_*`` methods
    are called at every place the parsers turn a reference into a stored
    value.

    Base information is kept in two ordered lists:

    * ``base_sources`` holds every base declaration encountered, including
      HTTP-derived candidates that did not win the precedence decision and
      ``xml:base`` declarations that could not be applied safely;
    * the active scope is a stack of frames, one per element that declared
      ``xml:base``, resting on the document-level working base.
    """

    def __init__(self, initial_base: str = ""):
        self.current_base = initial_base or ""
        # Active xml:base frames; ``None`` marks an element without xml:base.
        self._frame_stack: list[FeedParserDict | None] = []
        self._occurrence_counts: dict[tuple, int] = {}
        self.base_sources: list[FeedParserDict] = []
        self.uri_sources: list[FeedParserDict] = []
        self._document_base = FeedParserDict(
            raw="",
            value="",
            origin=REASON_NO_BASE,
            scope="document",
            effective=False,
            reason=REASON_NO_BASE,
        )

    # -- document-level (HTTP) bases ---------------------------------------

    def add_document_base(
        self,
        raw_base: str,
        origin: str,
        *,
        effective: bool,
    ) -> None:
        """Record an HTTP-derived base candidate.

        Document-level bases never push a scope frame.  Only the candidate
        marked ``effective`` becomes the working base; the others are kept
        for diagnostics so the precedence decision is auditable.
        """

        if effective:
            # The caller already computed the working base using the full
            # precedence rules (including resolving a relative
            # Content-Location against the final HTTP URL), so adopt it
            # verbatim instead of re-deriving the candidate in isolation.
            resolved, reason = self.current_base, ""
        else:
            resolved, reason = raw_base, ""
        record = FeedParserDict(
            raw=raw_base,
            value=resolved,
            origin=origin,
            scope="document",
            effective=effective,
            reason=reason,
        )
        self.base_sources.append(record)
        if effective:
            self._document_base = record

    def note_missing_base(self) -> None:
        """Record that no HTTP-derived base URI was available."""

        record = FeedParserDict(
            raw="",
            value="",
            origin=REASON_NO_BASE,
            scope="document",
            effective=False,
            reason=REASON_NO_BASE,
        )
        self.base_sources.append(record)

    # -- xml:base scope handling -------------------------------------------

    def enter_element(self, raw_base: str | None) -> None:
        """Record an ``xml:base`` declaration, if the element carries one."""

        if raw_base is None:
            self._frame_stack.append(None)
            return
        previous_base = self.current_base
        effective_value, reason = explain_safe(previous_base, raw_base)
        if reason and not previous_base:
            # A relative xml:base with no absolute base to resolve against
            # cannot produce an absolute URI.
            reason = REASON_NO_BASE
        if reason:
            effective_value = previous_base
        else:
            self.current_base = effective_value
        frame = FeedParserDict(
            raw=raw_base,
            value=effective_value,
            origin=ORIGIN_XML_BASE,
            scope="element",
            effective=not reason,
            reason=reason,
        )
        self.base_sources.append(frame)
        self._frame_stack.append(frame)

    def exit_element(self) -> None:
        """Pop the element's base frame and restore the previous base.

        The frame stays in ``base_sources`` so every ``xml:base``
        declaration, including ones that failed to apply, remains auditable
        after parsing completes.  Only the active-scope stack is popped.
        """

        frame = self._frame_stack.pop()
        if frame is None:
            return
        for active in reversed(self._frame_stack):
            if active is not None:
                self.current_base = active["value"]
                return
        self.current_base = self._document_base["value"]

    def _active_chain(self) -> list[FeedParserDict]:
        chain = []
        if self._document_base["effective"]:
            chain.append(
                FeedParserDict(
                    raw=self._document_base["raw"],
                    value=self._document_base["value"],
                    origin=self._document_base["origin"],
                    reason=self._document_base["reason"],
                )
            )
        chain.extend(
            FeedParserDict(
                raw=frame["raw"],
                value=frame["value"],
                origin=frame["origin"],
                reason=frame["reason"],
            )
            for frame in self._frame_stack
            if frame is not None
        )
        return chain

    # -- reference recording -----------------------------------------------

    def record_join(
        self,
        source: str,
        *,
        field: str,
        scope: str,
        entry_index: int | None = None,
        attribute: str | None = None,
        tag: str | None = None,
        occurrence: int | None = None,
    ) -> str:
        """Record a reference resolved with the loose ``_urljoin()`` rules."""

        resolved, reason = explain_join(self.current_base, source)
        self._append(
            source=source,
            resolved=resolved,
            reason=reason,
            field=field,
            scope=scope,
            entry_index=entry_index,
            attribute=attribute,
            tag=tag,
            occurrence=occurrence,
        )
        return resolved

    def record_html(
        self,
        source: str,
        resolved: str,
        *,
        field: str,
        scope: str,
        tag: str,
        attribute: str,
        entry_index: int | None = None,
    ) -> str:
        """Record an ``href``/``src`` reference inside embedded markup.

        The resolver already computed the value written into the markup, so
        that exact value is recorded instead of being re-derived.
        """

        _, reason = explain_safe(self.current_base, source.strip())
        self._append(
            source=source,
            resolved=resolved,
            reason=reason,
            field=field,
            scope=scope,
            entry_index=entry_index,
            attribute=attribute,
            tag=tag,
        )
        return resolved

    def _append(
        self,
        *,
        source: str,
        resolved: str,
        reason: str,
        field: str,
        scope: str,
        entry_index: int | None,
        attribute: str | None,
        tag: str | None,
        occurrence: int | None = None,
    ) -> None:
        # Occurrences are counted per field location, not per attribute name:
        # repeated references on the same field keep distinct positions even
        # when they use different attributes (for example, <img src> next to
        # <a href> inside one content element).
        key = (scope, entry_index, field)
        if occurrence is None:
            occurrence = self._occurrence_counts.get(key, 0)
        self._occurrence_counts[key] = occurrence + 1
        record = FeedParserDict(
            field=field,
            scope=scope,
            occurrence=occurrence,
            source=source,
            base=self.current_base,
            resolved=resolved,
            reason=reason,
            base_chain=self._active_chain(),
        )
        if entry_index is not None:
            record["entry_index"] = entry_index
        if attribute is not None:
            record["attribute"] = attribute
        if tag is not None:
            record["tag"] = tag
        self.uri_sources.append(record)
