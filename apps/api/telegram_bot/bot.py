"""The bot's behaviour: who may talk to it and what each kind of message does. Network access is injected."""
import datetime as dt
import logging
from typing import Protocol

from telegram_bot.chunks import split_message
from telegram_bot.clients import Action, Answer, BioStackError
from telegram_bot.texts import TEXTS

MAX_SEND_BYTES = 50 * 1024 * 1024  # Telegram's limit for files a bot uploads
IMAGE_MIMES = ("image/jpeg", "image/png")

log = logging.getLogger("telegram_bot")


class Telegram(Protocol):
    def send_message(self, chat_id: int, text: str) -> None: ...
    def send_document(self, chat_id: int, filename: str, content: bytes) -> None: ...
    def send_chat_action(self, chat_id: int, action: str) -> None: ...
    def download_file(self, file_id: str) -> bytes: ...


class BioStack(Protocol):
    def ask(self, question: str, image: bytes | None = None, image_mime: str | None = None,
            external_id: str = "", new_thread: bool = False) -> Answer: ...
    def resolve(self, external_id: str, accept: bool) -> list[Action]: ...
    def transcribe(self, audio: bytes) -> str: ...
    def briefing(self) -> list[str]: ...
    def export_archive(self) -> bytes: ...


class Bot:
    """Answers only the owner, in a private chat. Anyone may ask for /id, which is how the owner finds their number."""

    def __init__(self, telegram: Telegram, biostack: BioStack, owner_id: int | None, lang: str = "ru") -> None:
        self._tg = telegram
        self._api = biostack
        self._owner = owner_id
        self._t = TEXTS["ru" if lang == "ru" else "en"]
        self._new_threads: set[int] = set()

    def process(self, updates: list[dict]) -> int | None:
        """Handles each update (one failure never blocks the next) and returns the offset to ask Telegram for next."""
        for update in updates:
            try:
                self.handle(update)
            except Exception:
                log.exception("Could not handle update %s", update.get("update_id"))
                self._tell_after_failure(update)
        return updates[-1]["update_id"] + 1 if updates else None

    def handle(self, update: dict) -> None:
        message = update.get("message")
        if not message:
            return
        chat_id, sender = message["chat"]["id"], message.get("from", {}).get("id")
        command = self._command(message)
        if command == "/id":
            self._tg.send_message(chat_id, self._t["your_id"].format(id=sender))
            return
        if self._owner is None:
            self._tg.send_message(chat_id, self._t["setup"].format(id=sender))
            return
        if sender != self._owner or message["chat"].get("type") != "private":
            log.info("Ignored a message from user %s", sender)
            return
        try:
            self._route(chat_id, message, command)
        except BioStackError as exc:
            self._tg.send_message(chat_id, self._t["failed"].format(reason=exc.detail or self._t["unreachable"]))

    def _route(self, chat_id: int, message: dict, command: str | None) -> None:
        if command in ("/start", "/help"):
            self._tg.send_message(chat_id, self._t["help"])
        elif command == "/new":
            self._new_threads.add(chat_id)
            self._tg.send_message(chat_id, self._t["new_chat"])
        elif command in ("/yes", "/no"):
            for action in self._api.resolve(str(chat_id), command == "/yes"):
                if action.status == "done":
                    self._tg.send_message(chat_id, self._t["recorded"].format(label=action.label))
                elif action.status == "failed":
                    self._tg.send_message(chat_id, action.result)
                elif action.status == "dismissed":
                    self._tg.send_message(chat_id, self._t["dismissed"].format(label=action.label))
        elif command == "/today":
            self._tg.send_message(chat_id, "\n".join(f"- {bullet}" for bullet in self._api.briefing()))
        elif command == "/export":
            self._export(chat_id)
        elif "photo" in message:
            largest = max(message["photo"], key=lambda size: size["width"] * size["height"])
            self._ask_with_photo(chat_id, largest["file_id"], "image/jpeg", message.get("caption"))
        elif "voice" in message:
            self._ask_by_voice(chat_id, message["voice"]["file_id"])
        elif "document" in message:
            document = message["document"]
            if document.get("mime_type") in IMAGE_MIMES:
                self._ask_with_photo(chat_id, document["file_id"], document["mime_type"], message.get("caption"))
            else:
                self._tg.send_message(chat_id, self._t["other_file"])
        elif message.get("text"):
            self._answer(chat_id, message["text"])

    def _command(self, message: dict) -> str | None:
        words = (message.get("text") or "").split()
        if words and words[0].startswith("/"):
            return words[0].split("@")[0].lower()
        return None

    def _answer(self, chat_id: int, question: str, image: bytes | None = None, image_mime: str | None = None) -> None:
        self._tg.send_chat_action(chat_id, "typing")
        reply = self._api.ask(question, image, image_mime, str(chat_id), chat_id in self._new_threads)
        self._new_threads.discard(chat_id)
        for piece in split_message(reply.text):
            self._tg.send_message(chat_id, piece)
        pending = [action.label for action in reply.actions if action.status == "pending"]
        if pending:
            for piece in split_message("\n".join([*pending, self._t["action_hint"]])):
                self._tg.send_message(chat_id, piece)

    def _ask_with_photo(self, chat_id: int, file_id: str, mime: str, caption: str | None) -> None:
        image = self._tg.download_file(file_id)
        self._answer(chat_id, (caption or "").strip() or self._t["photo_question"], image, mime)

    def _ask_by_voice(self, chat_id: int, file_id: str) -> None:
        self._tg.send_chat_action(chat_id, "typing")
        heard = self._api.transcribe(self._tg.download_file(file_id))
        self._tg.send_message(chat_id, self._t["you_said"].format(text=heard))
        self._answer(chat_id, heard)

    def _export(self, chat_id: int) -> None:
        self._tg.send_chat_action(chat_id, "upload_document")
        archive = self._api.export_archive()
        if len(archive) > MAX_SEND_BYTES:
            self._tg.send_message(chat_id, self._t["export_too_big"].format(mb=len(archive) // (1024 * 1024)))
            return
        self._tg.send_document(chat_id, f"biostack-export-{dt.date.today()}.zip", archive)

    def _tell_after_failure(self, update: dict) -> None:
        message = update.get("message") or {}
        if message.get("from", {}).get("id") != self._owner or self._owner is None:
            return
        try:
            self._tg.send_message(message["chat"]["id"], self._t["crashed"])
        except Exception:
            log.exception("Could not report the failure to the owner")
