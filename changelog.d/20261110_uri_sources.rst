Added
-----

*   Add an opt-in ``track_uri_sources`` parameter to ``feedparser.parse()``.
    When enabled, the result gains a ``uri_sources`` list with one record per
    URI reference (the original value, the effective base, the resolved
    value and the base resolution chain) and a ``base_sources`` list
    describing the HTTP-derived and ``xml:base`` declarations in scope.
    References that cannot be resolved safely keep their original text with
    a machine-readable ``reason`` instead of a fabricated absolute URI.
    The feature is off by default and does not change the result object
    when disabled.
