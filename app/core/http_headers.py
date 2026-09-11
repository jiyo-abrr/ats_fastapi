"""HTTP header helpers.

`content_disposition_attachment` builds a `Content-Disposition` value that is
safe for any filename. A raw non-Latin-1 filename interpolated into the header
raises `UnicodeEncodeError` when the response is serialised (HTTP header values
are Latin-1); a filename containing `"` or control characters breaks quoting.
RFC 6266 handles both: an ASCII `filename` fallback plus a percent-encoded
UTF-8 `filename*`.
"""

from urllib.parse import quote

_ASCII_FALLBACK_MAX = 120


def _ascii_fallback(filename: str) -> str:
    out = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in filename)
    out = out.strip() or "download"
    return out[:_ASCII_FALLBACK_MAX]


def content_disposition_attachment(filename: str) -> str:
    fallback = _ascii_fallback(filename)
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"
