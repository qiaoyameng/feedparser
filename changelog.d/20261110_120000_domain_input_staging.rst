Changed
-------

*   Stage non-seekable binary input streams in a bounded, rewindable
    temporary file instead of reading them fully into memory.
    ``parse()`` gained ``staging_memory_threshold`` and ``staging_dir``
    options to control how much staged content is kept in memory and
    where larger content is rolled over to disk.

*   Detect encodings from the full content (``optimistic_encoding_detection=False``
    and the decode-error fallback) without materializing the raw or
    converted document in memory; the content is decoded on the fly.
