# Support for the Media RSS format
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

import copy

from ..util import FeedParserDict

# Element-stack marker names used to capture text inside media elements.
# They must not collide with marker names used elsewhere in the parser.
_TITLE_MARKER = "_media_title_capture"
_DESCRIPTION_MARKER = "_media_description_capture"
_THUMBNAIL_MARKER = "_media_thumbnail_capture"

# Metadata inherited from a media:group by its media:content children.
# The boolean marks elements that may repeat and therefore stay lists.
_GROUP_DEFAULTS = (
    ("title", False),
    ("description", False),
    ("credit", True),
    ("rating", False),
    ("thumbnail", True),
)

# Private bookkeeping keys kept on open content nodes.
_OWN_KEY = "_media_own"
_INHERITED_KEY = "_media_inherited"


class Namespace:
    supported_namespaces = {
        # Canonical namespace
        "http://search.yahoo.com/mrss/": "media",
        # Old namespace (no trailing slash)
        "http://search.yahoo.com/mrss": "media",
    }

    # ------------------------------------------------------------------
    # Hierarchical Media RSS tracking
    #
    # The flat ``media_content``/``media_thumbnail``/... fields keep their
    # original shape.  When ``hierarchical_media`` is enabled on the parser
    # the following extra state tracks which media:group (if any) each
    # element belongs to:
    #
    #   ``_media_stack`` -- open group/content nodes, innermost last.
    #   ``_media_*_map`` -- maps flat dictionaries to the hierarchical
    #       dictionary so data filled in by the legacy end-tag handlers can
    #       be mirrored onto the correct node.
    # ------------------------------------------------------------------

    def _media_tracking_enabled(self):
        return getattr(self, "hierarchical_media", False)

    def _media_init_tracking(self, context):
        context.setdefault("media_groups", [])
        context.setdefault("media_ungrouped_content", [])
        if not hasattr(self, "_media_stack"):
            self._media_stack = []
            self._media_thumbnail_map = {}
            self._media_credit_map = {}
            self._media_rating_map = {}

    def _media_current_node(self):
        """Return the innermost open media node (group or content)."""
        if self._media_tracking_enabled():
            stack = getattr(self, "_media_stack", None)
            if stack:
                return stack[-1]
        return None

    def _media_own_node(self, key):
        """Return the node that metadata named ``key`` should be written to.

        For an open media:content node, group-inherited defaults live on the
        content node itself while the content's own declarations go into a
        private bucket.  The bucket wins when the content closes, so a
        content-level declaration is not merged with the group default.
        """
        node = self._media_current_node()
        if node is not None and _OWN_KEY in node:
            default = [] if key in ("credit", "thumbnail") else None
            node[_OWN_KEY].setdefault(key, default)
            return node[_OWN_KEY]
        return node

    def _media_resolve(self, value):
        """Resolve a URI against the currently effective xml:base."""
        if not value:
            return value
        return self.resolve_uri(value)

    def _media_apply_url(self, target, attrs_d):
        """Copy media URL attributes and resolve a relative ``url``.

        The flat fields keep the raw ``url`` attribute.  Hierarchical nodes
        additionally expose the xml:base-resolved URI as ``href``; when the
        attribute is already absolute both keys hold the same value.
        """
        target.update(attrs_d)
        url = target.get("url")
        if url:
            resolved = self._media_resolve(url)
            if resolved and resolved != url:
                target["href"] = resolved

    @staticmethod
    def _media_copy_attrs(attrs_d):
        # ``attrs_d`` is reused by the flat-field handlers, so the
        # hierarchical copy must not share mutable state with it.
        # Plain dicts are used deliberately: FeedParserDict.__setitem__()
        # remaps the MRSS ``description`` key to ``summary``.
        return dict(attrs_d)

    def _start_media_category(self, attrs_d):
        attrs_d.setdefault("scheme", "http://search.yahoo.com/mrss/category_schema")
        self._start_category(attrs_d)

    def _end_media_category(self):
        self._end_category()

    def _end_media_keywords(self):
        for term in self.pop("media_keywords").split(","):
            if term.strip():
                self._add_tag(term.strip(), None, None)

    def _start_media_title(self, attrs_d):
        if self._media_tracking_enabled():
            node = self._media_own_node("title")
            if node is not None:
                self._media_title_attrs = self._media_copy_attrs(attrs_d)
                self.push(_TITLE_MARKER, 1)
                return
        self._start_title(attrs_d)

    def _end_media_title(self):
        if self._media_tracking_enabled():
            node = self._media_own_node("title")
            if (
                node is not None
                and self.elementstack
                and self.elementstack[-1][0] == _TITLE_MARKER
            ):
                _element, _expecting_text, pieces = self.elementstack.pop()
                value = "".join(pieces).strip()
                title = self._media_title_attrs
                if value is not None and value.strip():
                    title["value"] = value
                    node["title"] = title
                del self._media_title_attrs
                return
        title_depth = self.title_depth
        self._end_title()
        self.title_depth = title_depth

    def _start_media_group(self, attrs_d):
        if not self._media_tracking_enabled():
            # don't do anything, but don't break the enclosed tags either
            return
        context = self._get_context()
        self._media_init_tracking(context)
        group = dict(
            attrs=self._media_copy_attrs(attrs_d),
            content=[],
        )
        context["media_groups"].append(group)
        self._media_stack.append(group)

    def _end_media_group(self):
        if not self._media_tracking_enabled():
            return
        if self._media_stack:
            self._media_stack.pop()

    def _start_media_rating(self, attrs_d):
        context = self._get_context()
        if self._media_tracking_enabled():
            node = self._media_own_node("rating")
            if node is not None:
                rating = self._media_copy_attrs(attrs_d)
                self._media_rating_map[id(attrs_d)] = rating
                self.push("rating", 1)
                # The flat handler still owns ``attrs_d`` so the legacy
                # ``media_rating`` field keeps its original shape.
                context.setdefault("media_rating", attrs_d)
                return
        context.setdefault("media_rating", attrs_d)
        self.push("rating", 1)

    def _end_media_rating(self):
        rating = self.pop("rating")
        if rating is not None and rating.strip():
            if self._media_tracking_enabled():
                flat = self._get_context().get("media_rating")
                hierarchical = (
                    self._media_rating_map.pop(id(flat), None)
                    if flat is not None
                    else None
                )
                if hierarchical is not None:
                    hierarchical["content"] = rating
                    node = self._media_own_node("rating")
                    if node is not None:
                        node["rating"] = hierarchical
            context = self._get_context()
            context["media_rating"]["content"] = rating

    def _start_media_credit(self, attrs_d):
        context = self._get_context()
        if self._media_tracking_enabled():
            node = self._media_own_node("credit")
            if node is not None:
                credit = self._media_copy_attrs(attrs_d)
                node.setdefault("credit", [])
                node["credit"].append(credit)
                self._media_credit_map[id(attrs_d)] = credit
                context.setdefault("media_credit", [])
                context["media_credit"].append(attrs_d)
                self.push("credit", 1)
                return
        context.setdefault("media_credit", [])
        context["media_credit"].append(attrs_d)
        self.push("credit", 1)

    def _end_media_credit(self):
        credit = self.pop("credit")
        if credit is not None and credit.strip():
            if self._media_tracking_enabled():
                flat_credits = self._get_context().get("media_credit")
                flat = flat_credits[-1] if flat_credits else None
                hierarchical = (
                    self._media_credit_map.pop(id(flat), None)
                    if flat is not None
                    else None
                )
                if hierarchical is not None:
                    hierarchical["content"] = credit
            context = self._get_context()
            context["media_credit"][-1]["content"] = credit

    def _start_media_description(self, attrs_d):
        if self._media_tracking_enabled():
            node = self._media_own_node("description")
            if node is not None:
                self._media_description_attrs = self._media_copy_attrs(attrs_d)
                self.push(_DESCRIPTION_MARKER, 1)
                return
        self._start_description(attrs_d)

    def _end_media_description(self):
        if self._media_tracking_enabled():
            node = self._media_own_node("description")
            if (
                node is not None
                and self.elementstack
                and self.elementstack[-1][0] == _DESCRIPTION_MARKER
            ):
                _element, _expecting_text, pieces = self.elementstack.pop()
                value = "".join(pieces).strip()
                description = self._media_description_attrs
                if value is not None and value.strip():
                    description["value"] = value
                    node["description"] = description
                del self._media_description_attrs
                return
        self._end_description()

    def _start_media_restriction(self, attrs_d):
        context = self._get_context()
        context.setdefault("media_restriction", attrs_d)
        self.push("restriction", 1)

    def _end_media_restriction(self):
        restriction = self.pop("restriction")
        if restriction is not None and restriction.strip():
            context = self._get_context()
            context["media_restriction"]["content"] = [
                cc.strip().lower() for cc in restriction.split(" ")
            ]

    def _start_media_license(self, attrs_d):
        context = self._get_context()
        context.setdefault("media_license", attrs_d)
        self.push("license", 1)

    def _end_media_license(self):
        license_ = self.pop("license")
        if license_ is not None and license_.strip():
            context = self._get_context()
            context["media_license"]["content"] = license_

    def _start_media_content(self, attrs_d):
        context = self._get_context()
        context.setdefault("media_content", [])
        context["media_content"].append(attrs_d)
        if not self._media_tracking_enabled():
            return

        self._media_init_tracking(context)
        content = self._media_copy_attrs(attrs_d)
        self._media_apply_url(content, attrs_d)
        content[_OWN_KEY] = {}
        content[_INHERITED_KEY] = set()
        if self._media_stack:
            # Inherit group-level defaults up front.  Content-level
            # declarations are collected in the private own-value bucket and
            # replace the inherited value when the content closes, so the two
            # are never merged.
            group = self._media_stack[-1]
            for key, _repeats in _GROUP_DEFAULTS:
                if key in group:
                    content[key] = copy.deepcopy(group[key])
                    content[_INHERITED_KEY].add(key)
            group["content"].append(content)
        else:
            context["media_ungrouped_content"].append(content)
        self._media_stack.append(content)

    def _end_media_content(self):
        if not self._media_tracking_enabled():
            return
        if not self._media_stack:
            return
        content = self._media_stack.pop()
        own = content.pop(_OWN_KEY, {})
        inherited = content.pop(_INHERITED_KEY, set())
        for key, repeats in _GROUP_DEFAULTS:
            if key not in own:
                continue
            if repeats:
                # A declared repeatable element fully replaces the inherited
                # list; otherwise the group default stays in place.
                if own[key]:
                    content[key] = own[key]
            else:
                if own[key] is not None:
                    content[key] = own[key]

    def _start_media_thumbnail(self, attrs_d):
        context = self._get_context()
        if self._media_tracking_enabled():
            node = self._media_own_node("thumbnail")
            thumbnail = self._media_copy_attrs(attrs_d)
            self._media_apply_url(thumbnail, attrs_d)
            if node is not None:
                node.setdefault("thumbnail", [])
                node["thumbnail"].append(thumbnail)
            else:
                # A thumbnail outside of every group is collected separately
                # so it is never mistaken for group/content metadata.
                self._media_init_tracking(context)
                context.setdefault("media_ungrouped_thumbnail", [])
                context["media_ungrouped_thumbnail"].append(thumbnail)
            self._media_thumbnail_map[id(attrs_d)] = thumbnail
            # A dedicated marker frame captures the raw text content without
            # triggering XMLParserMixin.pop()'s relative-URI handling for
            # elements named "url".
            self.push(_THUMBNAIL_MARKER, 1)
        else:
            self.push("url", 1)  # new
        # Use dict.setdefault() explicitly: FeedParserDict.setdefault() goes
        # through __getitem__(), whose keymap redirects "media_thumbnail".
        if "media_thumbnail" not in context:
            dict.__setitem__(context, "media_thumbnail", [])
        context["media_thumbnail"].append(attrs_d)

    def _end_media_thumbnail(self):
        if self._media_tracking_enabled():
            raw_url = ""
            if (
                self.elementstack
                and self.elementstack[-1][0] == _THUMBNAIL_MARKER
            ):
                _element, _expecting_text, pieces = self.elementstack.pop()
                raw_url = "".join(pieces).strip()
            flat = self._get_context().get("media_thumbnail")
            flat_thumbnail = (
                flat[-1] if isinstance(flat, list) and flat else None
            )
            hierarchical = (
                self._media_thumbnail_map.pop(id(flat_thumbnail), None)
                if flat_thumbnail is not None
                else None
            )
            if (
                hierarchical is not None
                and raw_url
                and "url" not in hierarchical
            ):
                hierarchical["url"] = raw_url
                resolved = self._media_resolve(raw_url)
                if resolved and resolved != raw_url:
                    hierarchical["href"] = resolved
                # Mirror the historical flat-field behavior, which resolves
                # text-content thumbnail URLs against the current base.
                flat_thumbnail["url"] = resolved or raw_url
            url = raw_url
        else:
            url = self.pop("url")
        context = self._get_context()
        flat_thumbnails = context.get("media_thumbnail")
        if (
            url is not None
            and url.strip()
            and isinstance(flat_thumbnails, list)
            and flat_thumbnails
            and "url" not in flat_thumbnails[-1]
        ):
            flat_thumbnails[-1]["url"] = url

    def _start_media_player(self, attrs_d):
        self.push("media_player", 0)
        self._get_context()["media_player"] = FeedParserDict(attrs_d)

    def _end_media_player(self):
        value = self.pop("media_player")
        context = self._get_context()
        context["media_player"]["content"] = value
