"""Saved conversations with the AI: finding the thread a question belongs to, storing photos, and rebuilding
what the model should see of the earlier turns."""
import datetime as dt
import hashlib

from sqlmodel import Session, select

from config import settings
from db.models import ChatMessage, ChatThread
from services.gemini_client import ChatTurn

IDLE_WINDOW = dt.timedelta(hours=6)  # a Telegram chat quiet this long starts a fresh thread
MAX_HISTORY_MESSAGES = 40  # twenty exchanges
MAX_HISTORY_PHOTOS = 4  # older photos stay on screen but are not sent again
TITLE_CHARS = 60
_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/heic": ".heic"}


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def find_thread(session: Session, thread_id: int | None, channel: str, external_id: str, new_thread: bool) -> ChatThread | None:
    """The thread to continue, or None when this question opens a new one. A Telegram chat continues its latest
    thread unless the person said /new or it has been quiet for the idle window."""
    if thread_id is not None:
        return session.get(ChatThread, thread_id)
    if channel != "telegram" or not external_id or new_thread:
        return None
    latest = session.exec(select(ChatThread).where(ChatThread.channel == "telegram", ChatThread.external_id == external_id)
                          .order_by(ChatThread.updated_at.desc())).first()
    return latest if latest is not None and utcnow() - latest.updated_at <= IDLE_WINDOW else None


def store_image(content: bytes, mime: str) -> str:
    relative = f"chat/{hashlib.sha256(content).hexdigest()}{_EXTENSIONS[mime]}"
    target = settings.data_dir / relative
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return relative


def _model_text(message: ChatMessage) -> str:
    """What the model said, plus what became of anything it offered to record."""
    notes = {"pending": "Proposed, not yet confirmed by the person", "done": "Recorded", "dismissed": "Declined by the person",
             "failed": "Could not be saved"}
    lines = [f"[{notes[a['status']]}: {a['label']}]" for a in message.actions]
    return "\n".join([message.text, *lines]) if lines else message.text


def messages_of(session: Session, thread_id: int) -> list[ChatMessage]:
    return list(session.exec(select(ChatMessage).where(ChatMessage.thread_id == thread_id).order_by(ChatMessage.id)).all())


def history_turns(session: Session, thread: ChatThread | None) -> list[ChatTurn]:
    """Earlier turns, oldest first, opening with the person's question. Messages are always saved in
    question-and-answer pairs, so the turns alternate."""
    if thread is None:
        return []
    messages = messages_of(session, thread.id)[-MAX_HISTORY_MESSAGES:]
    if messages and messages[0].role != "user":
        messages = messages[1:]
    with_photo = [m.id for m in messages if m.image_path][-MAX_HISTORY_PHOTOS:]
    turns = []
    for m in messages:
        image = (settings.data_dir / m.image_path).read_bytes() if m.id in with_photo and (settings.data_dir / m.image_path).exists() else None
        turns.append(ChatTurn(role=m.role, text=_model_text(m) if m.role == "model" else m.text,
                              image=image, image_mime=m.image_mime if image else None))
    return turns


def save_exchange(session: Session, thread: ChatThread | None, channel: str, external_id: str, question: str,
                  image_path: str | None, image_mime: str | None, reply, actions: list[dict]) -> tuple[ChatThread, ChatMessage]:
    """Stores the question and its answer together (a failed answer stores nothing) and returns the thread and answer."""
    now = utcnow()
    if thread is None:
        thread = ChatThread(title=question.strip().replace("\n", " ")[:TITLE_CHARS], channel=channel,
                            external_id=external_id or None, created_at=now, updated_at=now)
        session.add(thread)
        session.flush()
    thread.updated_at = now
    session.add(thread)
    session.add(ChatMessage(thread_id=thread.id, role="user", text=question, image_path=image_path, image_mime=image_mime, created_at=now))
    answer = ChatMessage(thread_id=thread.id, role="model", text=reply.text, input_tokens=reply.input_tokens,
                         cached_tokens=reply.cached_tokens, output_tokens=reply.output_tokens, actions=actions,
                         created_at=now + dt.timedelta(microseconds=1))
    session.add(answer)
    session.commit()
    session.refresh(answer)
    return thread, answer


def delete_thread(session: Session, thread: ChatThread) -> None:
    messages = messages_of(session, thread.id)
    paths = {m.image_path for m in messages if m.image_path}
    for m in messages:
        session.delete(m)
    session.delete(thread)
    session.commit()
    for path in paths:  # a photo file is shared by identical content, so keep it while any message still uses it
        if session.exec(select(ChatMessage).where(ChatMessage.image_path == path)).first() is None:
            (settings.data_dir / path).unlink(missing_ok=True)
