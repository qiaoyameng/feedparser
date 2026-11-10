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

import email.utils
import re
import time

from .types import UNKNOWN, DateDetail, DateParseResult


def _parse_date_perforce_detail(date_string):
    """parse a date in yyyy/mm/dd hh:mm:ss TTT format"""
    # Fri, 2006/09/15 08:19:53 EDT
    _my_date_pattern = re.compile(
        r"(\w{,3}), (\d{,4})/(\d{,2})/(\d{2}) (\d{,2}):(\d{2}):(\d{2}) (\w{,3})"
    )

    m = _my_date_pattern.search(date_string)
    if m is None:
        return None
    dow, year, month, day, hour, minute, second, tz = m.groups()
    months = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    new_date_string = (
        f"{dow}, {day} {months[int(month) - 1]} {year} {hour}:{minute}:{second} {tz}"
    )
    tm = email.utils.parsedate_tz(new_date_string)
    if tm:
        parsed = time.gmtime(email.utils.mktime_tz(tm))
        # ``parsedate_tz`` returns the offset as a tenth element when the
        # source carries a recognizable timezone; an unrecognized name
        # carries no reliable offset.
        offset = tm[9] if len(tm) > 9 else None
        if offset is not None:
            timezone_explicit = True
            timezone_offset = offset
        else:
            timezone_explicit = False
            timezone_offset = UNKNOWN
        detail = DateDetail(
            value=date_string,
            handler="perforce",
            precision="second",
            timezone_explicit=timezone_explicit,
            timezone_offset=timezone_offset,
        )
        return DateParseResult(parsed=parsed, detail=detail)
    return None


def _parse_date_perforce(date_string):
    """parse a date in yyyy/mm/dd hh:mm:ss TTT format"""

    result = _parse_date_perforce_detail(date_string)
    if result is None:
        return None
    return result.parsed
