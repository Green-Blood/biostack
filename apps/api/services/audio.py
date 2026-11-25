"""Recognising the voice-note formats BioStack accepts (Telegram OGG/Opus, MP3, WAV, M4A) from their first bytes."""


def sniff_audio(content: bytes) -> str | None:
    """The MIME type Gemini expects, or None when the bytes are not a supported recording."""
    if content.startswith(b"OggS"):
        return "audio/ogg"
    if content.startswith(b"ID3") or content[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mp3"
    if content[:4] == b"RIFF" and content[8:12] == b"WAVE":
        return "audio/wav"
    if content[4:8] == b"ftyp":
        return "audio/mp4"
    return None
