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

from __future__ import annotations

from dataclasses import dataclass
from time import struct_time
from typing import Literal

from ..util import FeedParserDict

#: Used when a piece of metadata cannot be reliably determined from the
#: source string. It is deliberately a string so that, for example,
#: ``timezone_offset == 0`` always means an explicit zero-minute offset
#: was present in the source; it is never inferred from a zero-valued
#: field of the parsed :class:`time.struct_time`.
UNKNOWN = "unknown"

Precision = Literal["day", "minute", "second", "unknown"]
Unknown = Literal["unknown"]


@dataclass(frozen=True)
class DateParseResult:
    """The result of a successful date handler invocation.

    ``parsed`` is a UTC :class:`time.struct_time`, identical in meaning to
    the values historically returned by the date handlers. ``detail``
    carries only information that can be attributed to the source string
    or to the handler that parsed it; anything that cannot be determined
    reliably is set to :data:`UNKNOWN` instead of being reconstructed from
    the zero-valued fields of ``parsed``.
    """

    parsed: struct_time
    detail: "DateDetail"


@dataclass(frozen=True)
class DateDetail:
    """Provenance information for a single date value found in a feed.

    :param value: The original, unmodified date string from the feed.
    :param handler: The name of the date handler that parsed the value,
        or :data:`UNKNOWN` if no registered handler could parse it.
    :param precision: The granularity actually expressed in the source
        string: ``"day"``, ``"minute"``, or ``"second"``. Defaulted
        hours, minutes, or seconds are not taken into account.
    :param timezone_explicit: ``True`` if the source string explicitly
        carries timezone information, ``False`` if it does not, and
        :data:`UNKNOWN` for handlers that only return a 9-tuple and
        therefore cannot report this information.
    :param timezone_offset: The offset of the source timezone from UTC,
        expressed in minutes, or :data:`UNKNOWN` when no timezone was
        given or the information is unavailable.
    """

    value: str
    handler: str | Unknown
    precision: Precision
    timezone_explicit: bool | Unknown
    timezone_offset: int | Unknown

    def as_dict(self) -> FeedParserDict:
        return FeedParserDict(
            value=self.value,
            handler=self.handler,
            precision=self.precision,
            timezone_explicit=self.timezone_explicit,
            timezone_offset=self.timezone_offset,
        )


def make_failure_detail(date_string: str) -> DateDetail:
    """Build the detail record stored when no handler can parse a value."""

    return DateDetail(
        value=date_string,
        handler=UNKNOWN,
        precision=UNKNOWN,
        timezone_explicit=UNKNOWN,
        timezone_offset=UNKNOWN,
    )
