"""The two HTTP clients the bot needs: Telegram's Bot API and BioStack's own API."""
from dataclasses import dataclass

import httpx

TELEGRAM_URL = "https://api.telegram.org"
LONG_POLL_MARGIN_SECONDS = 15
BIOSTACK_TIMEOUT_SECONDS = 120.0  # a question can wait for the AI


class TelegramError(Exception):
    """Telegram refused a call or could not be reached. The message never contains the bot token."""


class BioStackError(Exception):
    """BioStack refused a call or could not be reached; `detail` is its explanation for the user, when it gave one."""

    def __init__(self, detail: str | None) -> None:
        super().__init__(detail or "BioStack is not reachable")
        self.detail = detail


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    status: str
    result: str = ""


@dataclass(frozen=True)
class Answer:
    text: str
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    actions: tuple[Action, ...] = ()


class TelegramApi:
    def __init__(self, token: str, transport: httpx.BaseTransport | None = None) -> None:
        self._token = token
        self._http = httpx.Client(base_url=TELEGRAM_URL, transport=transport, timeout=30.0)

    def get_updates(self, offset: int | None, timeout: int) -> list[dict]:
        body: dict = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            body["offset"] = offset
        return self._call("getUpdates", json=body, timeout=timeout + LONG_POLL_MARGIN_SECONDS)

    def send_message(self, chat_id: int, text: str) -> None:
        self._call("sendMessage", json={"chat_id": chat_id, "text": text})

    def send_chat_action(self, chat_id: int, action: str) -> None:
        self._call("sendChatAction", json={"chat_id": chat_id, "action": action})

    def send_document(self, chat_id: int, filename: str, content: bytes) -> None:
        self._call("sendDocument", data={"chat_id": str(chat_id)}, files={"document": (filename, content)}, timeout=300.0)

    def download_file(self, file_id: str) -> bytes:
        path = self._call("getFile", json={"file_id": file_id})["file_path"]
        try:
            response = self._http.get(f"/file/bot{self._token}/{path}")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TelegramError(f"Could not download a file from Telegram ({type(exc).__name__})") from None
        return response.content

    def _call(self, method: str, timeout: float | None = None, **kwargs):
        try:
            response = self._http.post(f"/bot{self._token}/{method}", timeout=timeout or self._http.timeout, **kwargs)
        except httpx.HTTPError as exc:  # the exception text holds the URL, which holds the token
            raise TelegramError(f"Telegram {method} failed ({type(exc).__name__})") from None
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if not payload.get("ok"):
            raise TelegramError(f"Telegram {method} refused: {payload.get('description', response.status_code)}")
        return payload["result"]


class BioStackApi:
    def __init__(self, base_url: str, secret: str, lang: str, transport: httpx.BaseTransport | None = None) -> None:
        self._http = httpx.Client(base_url=base_url, transport=transport, timeout=BIOSTACK_TIMEOUT_SECONDS,
                                  headers={"Authorization": f"Bearer {secret}", "Accept-Language": lang})

    def ask(self, question: str, image: bytes | None = None, image_mime: str | None = None,
            external_id: str = "", new_thread: bool = False) -> Answer:
        files = {"image": ("photo", image, image_mime)} if image is not None else None
        data = {"question": question, "channel": "telegram", "external_id": str(external_id),
                "new_thread": str(new_thread).lower()}
        body = self._request("POST", "/api/v1/chat/ask", data=data, files=files).json()
        usage = body["usage"]
        return Answer(text=body["answer"], input_tokens=usage["input_tokens"], cached_tokens=usage["cached_tokens"],
                      output_tokens=usage["output_tokens"], actions=tuple(self._action(a) for a in body.get("actions", [])))

    def resolve(self, external_id: str, accept: bool) -> list[Action]:
        body = self._request("POST", "/api/v1/chat/resolve",
                             data={"external_id": str(external_id), "accept": str(accept).lower()}).json()
        return [self._action(a) for a in body["actions"]]

    @staticmethod
    def _action(action: dict) -> Action:
        return Action(id=action["id"], label=action["label"], status=action["status"], result=action.get("result", ""))

    def transcribe(self, audio: bytes) -> str:
        return self._request("POST", "/api/v1/chat/transcribe", files={"audio": ("voice", audio)}).json()["text"]

    def briefing(self) -> list[str]:
        return self._request("GET", "/api/v1/analytics/briefing").json()["bullets"]

    def export_archive(self) -> bytes:
        return self._request("GET", "/api/v1/settings/export/archive").content

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise BioStackError(None) from None
        if response.is_success:
            return response
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        raise BioStackError(detail if isinstance(detail, str) else None)
