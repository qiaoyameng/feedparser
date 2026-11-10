# Explicit RSS 1.0 (RDF) channel sequence support
# Copyright 2010-2025 Kurt McKee <contactme@kurtmckee.org>
# Copyright 2002-2008 Mark Pilgrim
# All rights reserved.
#
# This file is a part of feedparser.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
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

from ..urls import make_safe_absolute_uri
from ..util import FeedParserDict

# Diagnostic ``type`` values emitted while reconstructing RSS 1.0 sequences.
DIAG_MISSING_REFERENCE = "missing_reference"
DIAG_DUPLICATE_MEMBER = "duplicate_member"
DIAG_CONFLICTING_DEFINITION = "conflicting_definition"
DIAG_MISSING_RESOURCE = "missing_resource"


class Namespace:
    """Reassemble RSS 1.0 entries from each channel's ``rdf:Seq``.

    RSS 1.0 is an RDF/XML format: ``item`` elements may appear anywhere in
    the document (including after the channel that references them), and
    the authoritative member order of a channel is the ``rdf:li`` list
    inside ``channel/items/rdf:Seq`` -- not the document order of the
    ``item`` elements.

    This namespace deliberately understands only the RSS 1.0 vocabulary.
    It is not a general-purpose RDF reasoner.  Every handler is a no-op
    unless sequence mode was explicitly requested with
    ``feedparser.parse(..., rss1_sequence=True)`` and the document was
    detected as RSS 1.0.
    """

    def _rss1_active(self):
        return self.rss1_sequence and self.version == "rss10"

    @staticmethod
    def _rss1_attr(attrs_d, localname):
        # The strict SAX handler reports RDF attributes with their prefix
        # when one is used (``rdf:resource``) but with a bare local name
        # (``resource``) when the RDF namespace is applied without one.
        return attrs_d.get("rdf:" + localname, attrs_d.get(localname))

    def _rss1_diagnostic(self, type, message, uri=None):
        line = None
        locator = getattr(self, "locator", None)
        if locator is not None:
            try:
                line = locator.getLineNumber()
            except AttributeError:
                line = None
        self.rss1_diagnostics.append(
            FeedParserDict(type=type, message=message, uri=uri, line=line)
        )

    def _rss1_resolve(self, uri):
        # Mirror how element text such as an item's rdf:about-derived id is
        # made absolute in pop(): the in-scope base URI (itself an absolute,
        # scheme-whitelisted URI) is combined with the raw attribute value.
        return make_safe_absolute_uri(self.baseuri or "", uri)

    def _start_channel(self, attrs_d):
        # Delegate to the base feed-format handler first.
        super()._start_channel(attrs_d)
        if not self._rss1_active():
            return
        resource = self._rss1_attr(attrs_d, "about")
        if resource:
            resource = self._rss1_resolve(resource)
        channel = FeedParserDict(
            resource=resource,
            members=[],
            entries=[],
        )
        self.rss1_channels.append(channel)
        self.rss1_current_channel = channel

    def _end_channel(self):
        super()._end_channel()
        if not self._rss1_active():
            return
        self.rss1_current_channel = None

    def _start_rdf_seq(self, attrs_d):
        if not self._rss1_active():
            return
        self.rss1_seq_depth += 1

    def _end_rdf_seq(self):
        if not self._rss1_active():
            return
        self.rss1_seq_depth -= 1

    def _start_rdf_li(self, attrs_d):
        if not self._rss1_active():
            return
        # ``rdf:li`` elements outside a channel's sequence cannot be
        # associated with a channel and are ignored.
        if not self.rss1_seq_depth or self.rss1_current_channel is None:
            return
        resource = self._rss1_attr(attrs_d, "resource")
        if not resource:
            self._rss1_diagnostic(
                DIAG_MISSING_RESOURCE,
                "rdf:li without an rdf:resource was ignored",
            )
            return
        resource = self._rss1_resolve(resource)
        members = self.rss1_current_channel["members"]
        if resource in members:
            self._rss1_diagnostic(
                DIAG_DUPLICATE_MEMBER,
                "resource is listed more than once in this channel's sequence",
                uri=resource,
            )
        members.append(resource)

    def _end_rdf_li(self):
        # All work happens in the start handler.
        return

    def _start_item(self, attrs_d):
        # Keep the historical flat-entry behavior intact.
        super()._start_item(attrs_d)
        if not self._rss1_active():
            return
        raw_resource = self._rss1_attr(attrs_d, "about")
        if not raw_resource:
            # An item with no rdf:about cannot be referenced by an
            # rdf:li resource, so it can never belong to a sequence.
            self.rss1_unsequenced.append(self.entries[-1])
            return
        # Index by the absolute resource identity (resolved against the
        # in-scope xml:base) so it matches rdf:li resources even though
        # the entry itself keeps its original rdf:about value as its id.
        resource = self._rss1_resolve(raw_resource)
        definitions = self.rss1_items_by_uri.setdefault(resource, [])
        if definitions:
            previous = definitions[0]
            if previous != self.entries[-1]:
                self._rss1_diagnostic(
                    DIAG_CONFLICTING_DEFINITION,
                    "multiple item definitions share this rdf:about "
                    "but their contents differ",
                    uri=resource,
                )
        definitions.append(self.entries[-1])

    _start_entry = _start_item

    def _end_item(self):
        super()._end_item()

    _end_entry = _end_item

    def finalize_rss1_sequence(self):
        """Rebuild ``entries`` from the channel sequences.

        Called once after the document has been parsed.  Each channel keeps
        its own member order (a single item may be referenced by several
        channels), references that cannot be resolved are diagnosed and
        skipped, and items that no sequence references are reported
        separately instead of being attached to the first channel.
        """
        if not self.rss1_sequence or self.version != "rss10":
            return

        sequenced = []
        sequenced_ids = set()
        for channel in self.rss1_channels:
            for resource in channel["members"]:
                definitions = self.rss1_items_by_uri.get(resource)
                if not definitions:
                    self._rss1_diagnostic(
                        DIAG_MISSING_REFERENCE,
                        "channel sequence references an item that is "
                        "not defined in the document",
                        uri=resource,
                    )
                    continue
                entry = definitions[0]
                channel["entries"].append(entry)
                if id(entry) not in sequenced_ids:
                    sequenced_ids.add(id(entry))
                    sequenced.append(entry)

        unsequenced = [
            entry
            for definitions in self.rss1_items_by_uri.values()
            for entry in definitions
            if id(entry) not in sequenced_ids
        ]
        unsequenced.extend(
            entry
            for entry in self.rss1_unsequenced
            if id(entry) not in sequenced_ids
        )

        self.entries = sequenced + unsequenced
        self.feeddata["rss1_channels"] = self.rss1_channels
        self.feeddata["rss1_unsequenced_entries"] = unsequenced
        self.feeddata["rss1_diagnostics"] = self.rss1_diagnostics
