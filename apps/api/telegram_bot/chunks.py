"""Splitting long answers to fit Telegram's message limit."""

MAX_MESSAGE_CHARS = 4096


def split_message(text: str, limit: int = MAX_MESSAGE_CHARS) -> list[str]:
    """Pieces of at most `limit` characters, cut at a blank line, a line break or a space when one is near the end."""
    pieces: list[str] = []
    rest = text.strip()
    while len(rest) > limit:
        cut = next((at for sep in ("\n\n", "\n", " ") if (at := rest.rfind(sep, 0, limit)) >= limit // 2), limit)
        pieces.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        pieces.append(rest)
    return pieces
