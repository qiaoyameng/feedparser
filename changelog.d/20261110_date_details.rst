Added
-----

*   Add a date detail mode, enabled with ``feedparser.parse(..., date_details=True)``
    or the ``feedparser.DATE_DETAILS`` flag. Each parsed date gains a
    ``*_date_detail`` record with the original value, the handler name, the
    precision expressed in the source (day/minute/second), whether a timezone
    was explicit, and the raw UTC offset in minutes. Values without a reliable
    basis in the source are reported as ``"unknown"`` instead of being inferred
    from the normalized UTC tuple. Legacy custom handlers returning a 9-tuple
    remain supported, with incomplete provenance; detail-aware handlers may
    return a ``DateParseResult``. The handler chain is still invoked exactly
    once per date, and XML and JSON feeds expose identical records.
