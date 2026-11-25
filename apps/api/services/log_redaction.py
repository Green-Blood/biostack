"""Keep what the owner types into search out of the access log."""
import logging

_SEARCH_PATH = "/search"


class RedactSearchQuery(logging.Filter):
    """uvicorn's access log shows the full request path; for /search the query string is replaced by q=<redacted>."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            path, sep, _query = args[2].partition("?")
            if sep and path.rstrip("/").endswith(_SEARCH_PATH):
                record.args = (*args[:2], f"{path}?q=<redacted>", *args[3:])
        return True
