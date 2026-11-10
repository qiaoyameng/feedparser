import io

import pytest

import feedparser
import feedparser.api


def _rss(items: int, description: str = "description") -> bytes:
    body = b"".join(
        b"<item><title>item %d</title><link>http://example.com/%d</link>"
        b"<guid isPermaLink='false'>id-%d</guid>"
        b"<description>%s</description></item>" % (i, i, i, description.encode())
        for i in range(items)
    )
    return (
        b"<?xml version='1.0' encoding='utf-8'?>"
        b"<rss version='2.0'><channel><title>example</title>"
        b"<link>http://example.com/</link>" + body + b"</channel></rss>"
    )


def _atom(entries: int) -> bytes:
    body = b"".join(
        b"<entry><title>entry %d</title><id>tag:example.com,%d</id>"
        b"<link href='/rel-%d'/></entry>" % (i, i, i)
        for i in range(entries)
    )
    return (
        b"<?xml version='1.0' encoding='utf-8'?>"
        b"<feed xmlns='http://www.w3.org/2005/Atom'>"
        b"<title>atom</title><id>tag:example.com,feed</id>"
        b"<link href='http://example.com/feed'/>" + body + b"</feed>"
    )


RSS = _rss(3)
ATOM = _atom(3)
# Declared ISO-8859-1, with non-ASCII bytes late in the document.
LATIN1 = _rss(2, "café").replace(
    b"encoding='utf-8'", b"encoding='ISO-8859-1'"
).replace("café".encode(), "café".encode("latin-1"))
# Ill-formed (bare '&'): the strict parser fails and the loose parser
# has to re-read the staged content.
ILL_FORMED = _rss(200).replace(b"<description>description", b"<description>a & b", 1)


class DribbleStream:
    """A non-seekable binary stream that yields a few bytes per read."""

    def __init__(self, data: bytes, chunk: int = 5):
        self.data = data
        self.chunk = chunk
        self.offset = 0
        self.read_sizes = []
        self.closed = False

    def read(self, size=-1):
        self.read_sizes.append(size)
        if self.offset >= len(self.data):
            return b""
        if size is None or size < 0:
            size = len(self.data)
        # Deliberately return fewer bytes than requested:
        # a short read must not be treated as EOF.
        piece = self.data[self.offset : self.offset + min(size, self.chunk)]
        self.offset += len(piece)
        return piece

    def seekable(self):
        return False

    def close(self):
        self.closed = True


def _assert_same_result(expected, actual):
    assert actual.bozo == expected.bozo
    assert type(actual.get("bozo_exception")) is type(expected.get("bozo_exception"))
    assert actual.version == expected.version
    assert actual.encoding == expected.encoding
    assert actual.feed == expected.feed
    assert actual.entries == expected.entries


@pytest.mark.parametrize("data", (RSS, ATOM, LATIN1), ids=("rss", "atom", "latin1"))
@pytest.mark.parametrize(
    "kwargs",
    (
        {},
        {"optimistic_encoding_detection": True},
        {"optimistic_encoding_detection": False},
    ),
)
def test_non_seekable_stream_matches_bytesio(data, kwargs):
    expected = feedparser.parse(io.BytesIO(data), **kwargs)

    stream = DribbleStream(data)
    actual = feedparser.parse(stream, **kwargs)

    assert len(actual.entries) == len(expected.entries) != 0
    _assert_same_result(expected, actual)
    # The caller's stream is never closed.
    assert not stream.closed
    # The original stream is only read with bounded read() calls
    # (read(0) is the binary/text probe and consumes nothing).
    assert stream.read_sizes
    assert all(size is not None and size >= 0 for size in stream.read_sizes)


def test_relative_links_match_bytesio():
    headers = {"content-location": "http://example.com/feeds/atom"}
    expected = feedparser.parse(io.BytesIO(ATOM), response_headers=headers)
    actual = feedparser.parse(DribbleStream(ATOM), response_headers=headers)
    _assert_same_result(expected, actual)
    assert actual.entries[0].link == "http://example.com/rel-0"


# Declared utf-8, but with a byte that is invalid utf-8 late in the
# document: the optimistic full-decode check fails and the encoding
# must be re-detected from the same staged raw bytes.
LATE_DECODE_ERROR = _rss(1).replace(
    b"<description>description",
    b"<description>" + b"x" * 200000 + b"\xe9",
    1,
)


@pytest.mark.parametrize("staging_memory_threshold", (2**20, 512))
def test_decode_error_fallback_uses_staged_bytes(staging_memory_threshold):
    expected = feedparser.parse(io.BytesIO(LATE_DECODE_ERROR))
    assert expected.encoding == "windows-1252"

    actual = feedparser.parse(
        DribbleStream(LATE_DECODE_ERROR),
        staging_memory_threshold=staging_memory_threshold,
    )
    _assert_same_result(expected, actual)


@pytest.fixture
def spool_spy(monkeypatch):
    original = feedparser.api.tempfile.SpooledTemporaryFile

    class SpoolSpy:
        instances = []

        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs
            self.file = original(*args, **kwargs)
            type(self).instances.append(self)

        def __getattr__(self, name):
            return getattr(self.file, name)

    monkeypatch.setattr(
        feedparser.api.tempfile, "SpooledTemporaryFile", SpoolSpy
    )
    return SpoolSpy


def test_staging_rolls_over_to_disk_and_survives_loose_fallback(tmp_path, spool_spy):
    expected = feedparser.parse(io.BytesIO(ILL_FORMED))
    assert expected.bozo
    assert expected.entries

    result = feedparser.parse(
        DribbleStream(ILL_FORMED),
        staging_memory_threshold=512,
        staging_dir=str(tmp_path),
    )

    (spool,) = spool_spy.instances
    # The content exceeded the in-memory threshold and rolled over to disk,
    # in the requested directory.
    assert spool.file._rolled
    assert spool.kwargs["dir"] == str(tmp_path)
    # The strict parser failed and the loose parser re-read the staged
    # content from disk, with the same result as a seekable input.
    _assert_same_result(expected, result)
    # The staging file was cleaned up afterwards.
    assert spool.file.closed


def test_staging_not_rolled_over_below_threshold(tmp_path, spool_spy):
    result = feedparser.parse(
        DribbleStream(RSS),
        staging_memory_threshold=2**20,
        staging_dir=str(tmp_path),
    )
    (spool,) = spool_spy.instances
    assert not spool.file._rolled
    assert spool.file.closed
    assert result.entries


def test_staging_cleaned_up_on_parse_error(tmp_path, spool_spy, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(feedparser.api, "_parse_file_inplace", boom)

    stream = DribbleStream(_rss(200))
    with pytest.raises(RuntimeError, match="parser exploded"):
        feedparser.parse(
            stream,
            staging_memory_threshold=1,
            staging_dir=str(tmp_path),
        )

    (spool,) = spool_spy.instances
    assert spool.file._rolled
    assert spool.file.closed
    assert not stream.closed


def test_seekable_stream_is_not_staged(spool_spy):
    stream = io.BytesIO(RSS)
    result = feedparser.parse(stream, staging_memory_threshold=1)
    assert not spool_spy.instances
    assert not stream.closed
    assert result.entries
