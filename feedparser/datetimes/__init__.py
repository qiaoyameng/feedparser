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

from collections.abc import Callable
from time import struct_time

from .asctime import _parse_date_asctime, _parse_date_asctime_detail
from .greek import _parse_date_greek, _parse_date_greek_detail
from .hungarian import _parse_date_hungarian, _parse_date_hungarian_detail
from .iso8601 import _parse_date_iso8601
from .korean import (
    _parse_date_nate,
    _parse_date_nate_detail,
    _parse_date_onblog,
    _parse_date_onblog_detail,
)
from .perforce import _parse_date_perforce, _parse_date_perforce_detail
from .rfc822 import _parse_date_rfc822, _parse_date_rfc822_detail
from .types import UNKNOWN, DateDetail, DateParseResult, make_failure_detail
from .w3dtf import _parse_date_w3dtf, _parse_date_w3dtf_detail

_date_handlers: list[Callable[[str], DateParseResult | tuple | None]] = []


def registerDateHandler(func):
    """Register a date handler.

    Handlers may either return a :class:`~feedparser.datetimes.types.DateParseResult`
    (the detail-aware protocol) or a plain 9-tuple date in GMT, which remains
    supported for backwards compatibility. A 9-tuple handler is still used to
    parse values, but its provenance information is necessarily incomplete:
    precision, timezone presence, and offset are reported as ``unknown``.
    """

    _date_handlers.insert(0, func)


def _parse_date(date_string):
    """Parse a variety of date formats into a UTC 9-tuple.

    Each registered handler is invoked at most once for ``date_string``.
    """

    result = _parse_date_with_details(date_string)
    if result is None:
        return None
    return result.parsed


def _parse_date_with_details(
    date_string: str,
) -> DateParseResult | None:
    """Parse a date and return both the UTC tuple and provenance details.

    The handler chain is walked exactly once. The first handler that returns
    a usable value wins, so handlers with side effects are never invoked a
    second time merely to populate the detail record.
    """

    if not date_string:
        return None
    for handler in _date_handlers:
        try:
            handler_result = handler(date_string)
        except (KeyError, OverflowError, ValueError, AttributeError):
            continue
        if not handler_result:
            continue
        if isinstance(handler_result, DateParseResult):
            return handler_result
        if len(handler_result) != 9:
            continue
        # Legacy handler protocol: a plain 9-tuple with no provenance.
        # The handler name is still known, but nothing about precision or
        # timezone can be inferred without inspecting the tuple's zero
        # values, which must not be reverse-engineered into source claims.
        detail = DateDetail(
            value=date_string,
            handler=getattr(handler, "__name__", UNKNOWN),
            precision=UNKNOWN,
            timezone_explicit=UNKNOWN,
            timezone_offset=UNKNOWN,
        )
        return DateParseResult(parsed=struct_time(handler_result), detail=detail)
    return None


def _date_detail(date_string: str) -> DateDetail:
    """Return provenance details, including a failure record for bad dates."""

    result = _parse_date_with_details(date_string)
    if result is None:
        return make_failure_detail(date_string)
    return result.detail


registerDateHandler(_parse_date_onblog_detail)
registerDateHandler(_parse_date_nate_detail)
registerDateHandler(_parse_date_greek_detail)
registerDateHandler(_parse_date_hungarian_detail)
registerDateHandler(_parse_date_perforce_detail)
registerDateHandler(_parse_date_asctime_detail)
registerDateHandler(_parse_date_iso8601)
registerDateHandler(_parse_date_rfc822_detail)
registerDateHandler(_parse_date_w3dtf_detail)
