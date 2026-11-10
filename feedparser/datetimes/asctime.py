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

from dataclasses import replace

from .rfc822 import _parse_date_rfc822_detail
from .types import UNKNOWN, DateParseResult

_months = [
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
]


def _parse_date_asctime_detail(dt):
    """Parse asctime-style dates.

    Converts asctime to RFC822-compatible dates and uses the RFC822 parser
    to do the actual parsing.

    Supported formats (format is standardized to the first one listed):

    * {weekday name} {month name} dd hh:mm:ss {+-tz} yyyy
    * {weekday name} {month name} dd hh:mm:ss yyyy
    """

    parts = dt.split()

    # Insert a GMT timezone, if needed.
    timezone_was_inserted = len(parts) == 5
    if len(parts) == 5:
        parts.insert(4, "+0000")

    # Exit if there are not six parts.
    if len(parts) != 6:
        return None

    # Reassemble the parts in an RFC822-compatible order and parse them.
    result = _parse_date_rfc822_detail(
        " ".join(
            [
                parts[0],
                parts[2],
                parts[1],
                parts[5],
                parts[3],
                parts[4],
            ]
        )
    )
    if result is None:
        return None
    if timezone_was_inserted:
        # The ``+0000`` offset was synthesized; the source carried no
        # timezone, so none must be reported as explicit.
        detail = replace(
            result.detail,
            value=dt,
            handler="asctime",
            timezone_explicit=False,
            timezone_offset=UNKNOWN,
        )
    else:
        detail = replace(result.detail, value=dt, handler="asctime")
    return DateParseResult(parsed=result.parsed, detail=detail)


def _parse_date_asctime(dt):
    """Parse asctime-style dates into a UTC 9-tuple."""

    result = _parse_date_asctime_detail(dt)
    if result is None:
        return None
    return result.parsed
