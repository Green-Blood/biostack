import json
from collections.abc import Callable
from functools import partial
from dataclasses import replace
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from config import settings
from db.database import get_session
from db.models import ChatMessage, ChatThread
from services import chat as chat_service, chat_threads, chat_actions, chat_tools
from services.ai_provider import AiNotConfigured, build_chat_client, build_transcriber
from services.audio import sniff_audio
from services.documents import JPEG_KIND, PNG_KIND, HEIC_KIND, sniff_document
from services.gemini_client import AiRequestError, ChatClient, Transcriber
from services.heic import HEIC_MIME, to_jpeg
from services.i18n import Lang, get_lang, msg, translate_text

router = APIRouter(prefix="/chat", tags=["chat"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BYTES = 10 * 1024 * 1024
IMAGE_KINDS = (JPEG_KIND, PNG_KIND, HEIC_KIND)
NL = chr(10)
class Usage(BaseModel):
    input_tokens: int
    cached_tokens: int
    output_tokens: int


class Answer(BaseModel):
    answer: str
    usage: Usage
    thread_id: int
    message_id: int
    actions: list[dict]


def get_chat_client_factory() -> Callable[[], ChatClient]:
    return partial(build_chat_client, settings)


class Transcript(BaseModel):
    text: str


def get_transcriber_factory() -> Callable[[], Transcriber]:
    return partial(build_transcriber, settings)


def _public(action: dict) -> dict:
    return {k: action[k] for k in ("id", "name", "label", "status", "result")}


def _thread(session: Session, thread_id: int, lang: Lang) -> ChatThread:
    thread = session.get(ChatThread, thread_id)
    if thread is None:
        raise HTTPException(404, msg(lang, "http.chat_thread_missing"))
    return thread


async def _prepare(question: str, image: UploadFile | None, thread_id: int | None, channel: str, external_id: str,
                   new_thread: bool, session: Session, lang: Lang):
    question = question.strip()
    if not question or len(question) > chat_service.MAX_QUESTION_CHARS:
        raise HTTPException(422, msg(lang, "http.chat_question", max=chat_service.MAX_QUESTION_CHARS))
    thread = chat_threads.find_thread(session, thread_id, channel, external_id, new_thread)
    if thread_id is not None and thread is None:
        raise HTTPException(404, msg(lang, "http.chat_thread_missing"))
    photo, mime = None, None
    if image is not None and image.filename:
        photo = await image.read(MAX_IMAGE_BYTES + 1)
        if len(photo) > MAX_IMAGE_BYTES:
            raise HTTPException(413, msg(lang, "http.lab_too_large", mb=MAX_IMAGE_BYTES // (1024 * 1024)))
        kind = sniff_document(photo)
        if kind not in IMAGE_KINDS:
            raise HTTPException(415, msg(lang, "http.chat_bad_image"))
        mime = kind.mime_type
    args = (chat_service.SYSTEM + chat_service.LANGUAGE_NOTES.get(lang, ""), chat_service.record_context(session),
            question, photo, mime, chat_threads.history_turns(session, thread))
    return question, thread, photo, mime, args


def _ai_error(exc: Exception, lang: Lang) -> HTTPException:
    if isinstance(exc, AiNotConfigured):
        return HTTPException(503, translate_text(lang, str(exc)))
    return HTTPException(502, msg(lang, "http.ai_retry_plain", error=translate_text(lang, str(exc))))


def _finish(session: Session, thread, channel: str, external_id: str, question: str, photo, mime, reply, lang: Lang) -> Answer:
    actions = chat_actions.propose(session, reply.calls, lang)
    if not reply.text:
        reply = replace(reply, text=msg(lang, "chat.proposed_lead"))
    path = chat_threads.store_image(photo, mime) if photo is not None else None
    thread, answer = chat_threads.save_exchange(session, thread, channel, external_id, question, path, mime, reply, actions)
    return Answer(answer=reply.text, usage=Usage(input_tokens=reply.input_tokens, cached_tokens=reply.cached_tokens,
                  output_tokens=reply.output_tokens), thread_id=thread.id, message_id=answer.id,
                  actions=[_public(a) for a in actions])


@router.post("/ask")
async def ask(question: str = Form(...), image: UploadFile | None = File(default=None),
              thread_id: int | None = Form(default=None), channel: Literal["web", "telegram"] = Form(default="web"),
              external_id: str = Form(default=""), new_thread: bool = Form(default=False),
              session: Session = Depends(get_session),
              client_factory: Callable[[], ChatClient] = Depends(get_chat_client_factory),
              lang: Lang = Depends(get_lang)) -> Answer:
    question, thread, photo, mime, args = await _prepare(question, image, thread_id, channel, external_id, new_thread, session, lang)
    try:
        reply = client_factory().generate_text(*args, tools=chat_tools.DECLARATIONS)
    except (AiNotConfigured, AiRequestError) as exc:
        raise _ai_error(exc, lang) from exc
    return _finish(session, thread, channel, external_id, question, photo, mime, reply, lang)


@router.post("/ask-stream")
async def ask_stream(question: str = Form(...), image: UploadFile | None = File(default=None),
                     thread_id: int | None = Form(default=None), channel: Literal["web", "telegram"] = Form(default="web"),
                     external_id: str = Form(default=""), new_thread: bool = Form(default=False),
                     session: Session = Depends(get_session),
                     client_factory: Callable[[], ChatClient] = Depends(get_chat_client_factory),
                     lang: Lang = Depends(get_lang)) -> StreamingResponse:
    """Same as /ask, but answers as newline-delimited JSON: {"delta": text} lines, then {"done": Answer} or {"error": ..}."""
    question, thread, photo, mime, args = await _prepare(question, image, thread_id, channel, external_id, new_thread, session, lang)

    def lines():
        try:
            client = client_factory()
            stream = client.stream_text(*args, tools=chat_tools.DECLARATIONS) if hasattr(client, "stream_text") else iter(
                [client.generate_text(*args, tools=chat_tools.DECLARATIONS)])
            reply, streamed = None, False
            for part in stream:
                if isinstance(part, str):
                    streamed = True
                    yield json.dumps({"delta": part}) + NL
                else:
                    reply = part
            if not streamed and reply.text:  # a client without streaming: one delta with the whole text
                yield json.dumps({"delta": reply.text}) + NL
            answer = _finish(session, thread, channel, external_id, question, photo, mime, reply, lang)
            yield json.dumps({"done": answer.model_dump()}) + NL
        except (AiNotConfigured, AiRequestError) as exc:
            yield json.dumps({"error": _ai_error(exc, lang).detail}) + NL

    return StreamingResponse(lines(), media_type="application/x-ndjson")


@router.get("/threads")
def list_threads(channel: Literal["web", "telegram"] | None = None, session: Session = Depends(get_session)) -> list[dict]:
    query = select(ChatThread)
    if channel:
        query = query.where(ChatThread.channel == channel)
    threads = session.exec(query.order_by(ChatThread.updated_at.desc(), ChatThread.id.desc()).limit(50)).all()
    return [{"id": t.id, "title": t.title, "channel": t.channel, "updated_at": t.updated_at.isoformat(),
             "message_count": len(chat_threads.messages_of(session, t.id))} for t in threads]


@router.get("/threads/{thread_id}")
def get_thread(thread_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    t = _thread(session, thread_id, lang)
    return {"id": t.id, "title": t.title, "channel": t.channel, "messages": [
        {"id": m.id, "role": m.role, "text": m.text, "image_url": f"/api/v1/chat/messages/{m.id}/image" if m.image_path else None,
         "actions": [_public(a) for a in m.actions], "created_at": m.created_at.isoformat()}
        for m in chat_threads.messages_of(session, t.id)]}


@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> Response:
    chat_threads.delete_thread(session, _thread(session, thread_id, lang))
    return Response(status_code=204)


@router.get("/messages/{message_id}/image")
def message_image(message_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    m = session.get(ChatMessage, message_id)
    path = settings.data_dir / m.image_path if m and m.image_path else None
    if path is None or not path.is_file():
        raise HTTPException(404, msg(lang, "http.chat_thread_missing"))
    if m.image_mime == HEIC_MIME:
        return Response(to_jpeg(path.read_bytes()), media_type="image/jpeg")
    return FileResponse(path, media_type=m.image_mime)


def _resolve_action(session: Session, message: ChatMessage, action_id: str, accept: bool, lang: Lang) -> dict:
    actions = list(message.actions)
    index = next ( (i for i, a in enumerate(actions) if a["id"] == action_id), None)
    if index is None:
        raise HTTPException(404, msg(lang, "http.chat_action_missing"))
    action = actions[index]
    if action["status"] != chat_actions.PENDING:
        raise HTTPException(409, msg(lang, "http.chat_action_not_pending"))
    actions[index] = chat_actions.execute(session, action, lang) if accept else {**action, "status": chat_actions.DISMISSED}
    message.actions = actions
    session.add(message)
    session.commit()
    return _public(actions[index])


@router.post("/messages/{message_id}/actions/{action_id}/{operation}")
def action(message_id: int, action_id: str, operation: Literal["confirm", "dismiss"],
           session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    message = session.get(ChatMessage, message_id)
    if message is None:
        raise HTTPException(404, msg(lang, "http.chat_action_missing"))
    return _resolve_action(session, message, action_id, operation == "confirm", lang)


@router.post("/resolve")
def resolve(external_id: str = Form(...), accept: bool = Form(...), session: Session = Depends(get_session),
            lang: Lang = Depends(get_lang)) -> dict:
    thread = chat_threads.find_thread(session, None, "telegram", external_id, False)
    messages = chat_threads.messages_of(session, thread.id) if thread else []
    message = messages[-1] if messages else None
    if not message:
        return {"actions": []}
    ids = [a["id"] for a in message.actions if a["status"] == chat_actions.PENDING]
    return {"actions": [_resolve_action(session, message, action_id, accept, lang) for action_id in ids]}


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), transcriber_factory: Callable[[], Transcriber] = Depends(get_transcriber_factory),
                     lang: Lang = Depends(get_lang)) -> Transcript:
    """Voice note to text, so the Telegram bot can ask a spoken question the same way as a typed one."""
    content = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(413, msg(lang, "http.lab_too_large", mb=MAX_AUDIO_BYTES // (1024 * 1024)))
    mime = sniff_audio(content)
    if mime is None:
        raise HTTPException(415, msg(lang, "http.voice_bad_audio"))
    try:
        text = transcriber_factory().transcribe(content, mime).strip()
    except AiNotConfigured as exc:
        raise HTTPException(503, translate_text(lang, str(exc))) from exc
    except AiRequestError as exc:
        raise HTTPException(502, msg(lang, "http.ai_retry_plain", error=translate_text(lang, str(exc)))) from exc
    if not text:
        raise HTTPException(422, msg(lang, "http.voice_no_words"))
    return Transcript(text=text)
