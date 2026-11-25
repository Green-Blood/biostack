import json

import httpx
import pytest

from telegram_bot.clients import Action, Answer, BioStackApi, BioStackError, TelegramApi, TelegramError

TOKEN = "123456:SECRET-TOKEN"


def telegram(handler) -> TelegramApi:
    return TelegramApi(TOKEN, transport=httpx.MockTransport(handler))


def biostack(handler, lang="ru") -> BioStackApi:
    return BioStackApi("http://api:8000", "api-secret", lang, transport=httpx.MockTransport(handler))


def ok(result) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, "result": result})


def test_get_updates_asks_for_the_next_offset_with_long_polling():
    seen = {}

    def handler(request):
        seen["path"], seen["body"] = request.url.path, json.loads(request.content)
        return ok([{"update_id": 5}])

    assert telegram(handler).get_updates(offset=5, timeout=30) == [{"update_id": 5}]
    assert seen["path"] == f"/bot{TOKEN}/getUpdates"
    assert seen["body"] == {"offset": 5, "timeout": 30, "allowed_updates": ["message"]}


def test_send_message_posts_chat_and_text():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return ok({})

    telegram(handler).send_message(42, "hello")
    assert seen["body"] == {"chat_id": 42, "text": "hello"}


def test_send_document_uploads_the_bytes_as_a_file():
    seen = {}

    def handler(request):
        seen["path"], seen["body"] = request.url.path, request.content
        return ok({})

    telegram(handler).send_document(42, "a.zip", b"PK-bytes")
    assert seen["path"].endswith("/sendDocument")
    assert b'filename="a.zip"' in seen["body"] and b"PK-bytes" in seen["body"]


def test_download_file_resolves_the_path_then_fetches_the_bytes():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/getFile"):
            return ok({"file_path": "voice/file_1.oga"})
        return httpx.Response(200, content=b"audio-bytes")

    assert telegram(handler).download_file("abc") == b"audio-bytes"
    assert paths == [f"/bot{TOKEN}/getFile", f"/file/bot{TOKEN}/voice/file_1.oga"]


def test_a_telegram_refusal_is_an_error_without_the_token():
    def handler(request):
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    with pytest.raises(TelegramError) as caught:
        telegram(handler).send_message(1, "x")
    assert "Unauthorized" in str(caught.value) and TOKEN not in str(caught.value)


def test_a_network_failure_is_an_error_without_the_token():
    def handler(request):
        raise httpx.ConnectError("cannot connect to " + str(request.url))

    with pytest.raises(TelegramError) as caught:
        telegram(handler).get_updates(offset=None, timeout=1)
    assert TOKEN not in str(caught.value) and TOKEN not in repr(caught.value.__cause__ or "")


def test_ask_sends_the_token_language_question_and_photo_and_reads_the_answer():
    seen = {}

    def handler(request):
        seen.update(path=request.url.path, auth=request.headers["authorization"], lang=request.headers["accept-language"], body=request.content)
        return httpx.Response(200, json={"answer": "Fine.", "usage": {"input_tokens": 10, "cached_tokens": 4, "output_tokens": 2}})

    reply = biostack(handler).ask("Spot?", b"\xff\xd8\xff-img", "image/jpeg")
    assert reply == Answer(text="Fine.", input_tokens=10, cached_tokens=4, output_tokens=2)
    assert seen["path"] == "/api/v1/chat/ask" and seen["auth"] == "Bearer api-secret" and seen["lang"] == "ru"
    assert b"Spot?" in seen["body"] and b"-img" in seen["body"] and b"image/jpeg" in seen["body"]


def test_ask_without_a_photo_sends_no_file_part():
    seen = {}

    def handler(request):
        seen["body"] = request.content
        return httpx.Response(200, json={"answer": "x", "usage": {"input_tokens": 1, "cached_tokens": 0, "output_tokens": 1}})

    biostack(handler).ask("Hi")
    assert b'name="image"' not in seen["body"]


def test_api_errors_carry_the_servers_explanation():
    def handler(request):
        return httpx.Response(503, json={"detail": "Add GEMINI_API_KEY to .env to enable this."})

    with pytest.raises(BioStackError) as caught:
        biostack(handler).ask("Hi")
    assert caught.value.detail == "Add GEMINI_API_KEY to .env to enable this."


def test_an_unreachable_api_has_no_detail():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(BioStackError) as caught:
        biostack(handler).ask("Hi")
    assert caught.value.detail is None


def test_validation_errors_do_not_dump_the_raw_payload():
    def handler(request):
        return httpx.Response(422, json={"detail": [{"loc": ["body"], "msg": "bad"}]})

    with pytest.raises(BioStackError) as caught:
        biostack(handler).ask("Hi")
    assert caught.value.detail is None


def test_transcribe_posts_the_recording_and_returns_the_text():
    seen = {}

    def handler(request):
        seen.update(path=request.url.path, body=request.content)
        return httpx.Response(200, json={"text": "how is my ferritin"})

    assert biostack(handler).transcribe(b"OggS-audio") == "how is my ferritin"
    assert seen["path"] == "/api/v1/chat/transcribe" and b"OggS-audio" in seen["body"]


def test_briefing_returns_the_bullets():
    def handler(request):
        assert request.url.path == "/api/v1/analytics/briefing"
        return httpx.Response(200, json={"bullets": ["a", "b"], "date": "2026-11-12", "source": "ai", "label": "", "ai_enabled": True, "can_retry": False})

    assert biostack(handler).briefing() == ["a", "b"]


def test_export_archive_returns_the_zip_bytes():
    def handler(request):
        assert request.url.path == "/api/v1/settings/export/archive"
        return httpx.Response(200, content=b"PK-zip")

    assert biostack(handler).export_archive() == b"PK-zip"


def test_chat_thread_fields_and_actions():
    def handler(request):
        assert b'name="channel"\r\n\r\ntelegram' in request.content
        assert b'name="external_id"\r\n\r\n4242' in request.content
        assert b'name="new_thread"\r\n\r\ntrue' in request.content
        return httpx.Response(200, json={"answer": "Proposed", "usage": {"input_tokens": 1, "cached_tokens": 0, "output_tokens": 2},
                                        "actions": [{"id": "a1", "label": "Weight", "status": "pending"}]})

    answer = biostack(handler).ask("Log", b"photo", "image/jpeg", "4242", True)
    assert answer.actions == (Action("a1", "Weight", "pending"),)


def test_resolve_posts_the_chat_and_decision():
    def handler(request):
        assert request.url.path == "/api/v1/chat/resolve"
        assert request.content == b"external_id=4242&accept=false"
        return httpx.Response(200, json={"actions": [{"id": "a1", "label": "Weight", "status": "dismissed", "result": ""}]})

    assert biostack(handler).resolve("4242", False) == [Action("a1", "Weight", "dismissed")]
