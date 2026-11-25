import pytest

from main import app
from routers.chat import get_transcriber_factory
from services.ai_provider import AiNotConfigured
from services.gemini_client import AiRequestError

OGG = b"OggS\x00\x02" + b"0" * 32
MP3 = b"ID3\x04\x00" + b"0" * 32
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"0" * 32
M4A = b"\x00\x00\x00\x20ftypM4A " + b"0" * 32


class RecordingTranscriber:
    def __init__(self, text: str = "how is my ferritin"):
        self.text = text
        self.calls: list[tuple[bytes, str]] = []

    def transcribe(self, audio: bytes, mime_type: str) -> str:
        self.calls.append((audio, mime_type))
        return self.text


@pytest.fixture
def transcriber():
    ai = RecordingTranscriber()
    app.dependency_overrides[get_transcriber_factory] = lambda: (lambda: ai)
    return ai


@pytest.mark.parametrize("audio, mime", [(OGG, "audio/ogg"), (MP3, "audio/mp3"), (WAV, "audio/wav"), (M4A, "audio/mp4")])
def test_voice_note_comes_back_as_text(client, transcriber, audio, mime):
    r = client.post("/api/v1/chat/transcribe", files={"audio": ("voice.bin", audio, "application/octet-stream")})
    assert r.status_code == 200
    assert r.json() == {"text": "how is my ferritin"}
    assert transcriber.calls == [(audio, mime)]


def test_the_type_comes_from_the_bytes_not_the_filename(client, transcriber):
    client.post("/api/v1/chat/transcribe", files={"audio": ("voice.mp3", OGG, "audio/mpeg")})
    assert transcriber.calls[0][1] == "audio/ogg"


def test_something_that_is_not_audio_is_refused(client, transcriber):
    r = client.post("/api/v1/chat/transcribe", files={"audio": ("x.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert r.status_code == 415 and not transcriber.calls


def test_a_huge_recording_is_refused(client, transcriber):
    r = client.post("/api/v1/chat/transcribe", files={"audio": ("v.ogg", OGG + b"0" * (10 * 1024 * 1024), "audio/ogg")})
    assert r.status_code == 413 and not transcriber.calls


def test_silence_is_a_readable_422(client):
    ai = RecordingTranscriber(text="   ")
    app.dependency_overrides[get_transcriber_factory] = lambda: (lambda: ai)
    r = client.post("/api/v1/chat/transcribe", files={"audio": ("v.ogg", OGG, "audio/ogg")})
    assert r.status_code == 422 and "words" in r.json()["detail"]


def test_missing_key_says_what_to_add(client):
    def boom():
        raise AiNotConfigured("Add GEMINI_API_KEY to .env to enable this. x")
    app.dependency_overrides[get_transcriber_factory] = lambda: boom
    r = client.post("/api/v1/chat/transcribe", files={"audio": ("v.ogg", OGG, "audio/ogg")})
    assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"]


def test_ai_failure_is_a_readable_502(client):
    class Failing:
        def transcribe(self, audio, mime_type):
            raise AiRequestError("The AI service refused the request (500).")
    app.dependency_overrides[get_transcriber_factory] = lambda: (lambda: Failing())
    r = client.post("/api/v1/chat/transcribe", files={"audio": ("v.ogg", OGG, "audio/ogg")})
    assert r.status_code == 502 and "Try again" in r.json()["detail"]


def test_russian_error_for_a_bad_file(client, transcriber):
    r = client.post("/api/v1/chat/transcribe", headers={"Accept-Language": "ru"},
                    files={"audio": ("x.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert r.status_code == 415 and "Голосовое" in r.json()["detail"]
