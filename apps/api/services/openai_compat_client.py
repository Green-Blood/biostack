"""OpenAI-compatible AI client (Ollama, LM Studio, OpenAI, OpenRouter) using httpx."""
import base64
import io
import json
import re
from collections.abc import Iterator

import httpx
from pypdf import PdfReader

from services.gemini_client import (
    MAX_CHAT_OUTPUT_TOKENS,
    PDF,
    TRANSCRIBE_PROMPT,
    AiRequestError,
    ChatReply,
    ChatTurn,
    ToolCall,
)

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.S)


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    match = _FENCE_RE.match(text)
    return match.group(1).strip() if match else text


def _pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()


def _document_parts(prompt: str, document: bytes, mime_type: str) -> list[dict]:
    if mime_type.startswith("image/"):
        b64 = base64.b64encode(document).decode("ascii")
        return [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
        ]
    if mime_type == PDF:
        extracted = _pdf_text(document)
        body = extracted if extracted else "[Empty or image-only PDF]"
        return [{"type": "text", "text": f"{prompt}\n\nDocument text:\n{body}"}]
    text = document.decode("utf-8", errors="replace")
    return [{"type": "text", "text": f"{prompt}\n\nDocument:\n{text}"}]


class OpenAICompatClient:
    """Client for OpenAI-compatible /v1/chat/completions endpoints."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _client(self, timeout: float = 120.0) -> httpx.Client:
        return httpx.Client(base_url=self._base_url, headers=self._headers(), timeout=timeout, transport=self._transport)

    def _post_chat(self, payload: dict) -> dict:
        try:
            with self._client() as client:
                res = client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise AiRequestError(f"Could not reach AI provider: {exc}") from exc
        if res.status_code >= 400:
            raise AiRequestError(f"The AI service refused the request ({res.status_code}).")
        try:
            return res.json()
        except ValueError as exc:
            raise AiRequestError("The AI service returned invalid JSON.") from exc

    def ping(self) -> dict:
        """Verify the provider endpoint responds on GET /models."""
        try:
            with self._client(timeout=10.0) as client:
                res = client.get("/models")
        except httpx.HTTPError as exc:
            raise AiRequestError(f"Could not reach AI provider: {exc}") from exc
        if res.status_code >= 400:
            raise AiRequestError(f"The AI service refused the request ({res.status_code}).")
        return {"ok": True, "provider": "openai_compat", "model": self._model}

    def generate_json(self, prompt: str, document: bytes, schema: dict, mime_type: str = PDF) -> dict:
        system = (
            "Respond with a single valid JSON object matching this JSON schema and nothing else:\n"
            + json.dumps(schema, ensure_ascii=False)
        )
        payload = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": _document_parts(prompt, document, mime_type)},
            ],
        }
        data = self._post_chat(payload)
        try:
            content = data["choices"][0]["message"]["content"] or ""
            return json.loads(_strip_fences(content))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise AiRequestError("The AI service returned an answer that is not valid JSON.") from exc

    def generate_grounded(self, prompt: str, document: bytes, mime_type: str = "application/json") -> str:
        payload = {
            "model": self._model,
            "temperature": 0.3,
            "messages": [
                {"role": "user", "content": _document_parts(prompt, document, mime_type)},
            ],
        }
        data = self._post_chat(payload)
        try:
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise AiRequestError("The AI service returned an empty answer.") from exc
        if not text:
            raise AiRequestError("The AI service returned an empty answer.")
        return text

    @staticmethod
    def _chat_messages(
        system: str,
        context: str,
        question: str,
        image: bytes | None,
        image_mime: str | None,
        history: list[ChatTurn] | None,
    ) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": system}]
        turns = list(history or []) + [ChatTurn("user", question, image, image_mime)]
        for idx, turn in enumerate(turns):
            role = "assistant" if turn.role == "model" else "user"
            text = f"{context}\n\n{turn.text}" if idx == 0 else turn.text
            if turn.image is not None and turn.image_mime:
                b64 = base64.b64encode(turn.image).decode("ascii")
                content: str | list[dict] = [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": f"data:{turn.image_mime};base64,{b64}"}},
                ]
            else:
                content = text
            messages.append({"role": role, "content": content})
        return messages

    @staticmethod
    def _openai_tools(tools: list[dict] | None) -> list[dict] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]

    @staticmethod
    def _parse_tool_calls(raw_calls: list[dict] | None) -> list[ToolCall]:
        parsed: list[ToolCall] = []
        for item in raw_calls or []:
            fn = item.get("function") or {}
            name = fn.get("name")
            if not name:
                continue
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except (json.JSONDecodeError, TypeError):
                args = {}
            parsed.append(ToolCall(name=name, args=args if isinstance(args, dict) else {}))
        return parsed

    def generate_text(
        self,
        system: str,
        context: str,
        question: str,
        image: bytes | None = None,
        image_mime: str | None = None,
        history: list[ChatTurn] | None = None,
        tools: list[dict] | None = None,
    ) -> ChatReply:
        payload: dict = {
            "model": self._model,
            "temperature": 0.3,
            "max_tokens": MAX_CHAT_OUTPUT_TOKENS,
            "messages": self._chat_messages(system, context, question, image, image_mime, history),
        }
        oa_tools = self._openai_tools(tools)
        if oa_tools:
            payload["tools"] = oa_tools
        data = self._post_chat(payload)
        choice = (data.get("choices") or [{}])[0]
        msg_obj = choice.get("message") or {}
        text = (msg_obj.get("content") or "").strip()
        calls = self._parse_tool_calls(msg_obj.get("tool_calls"))
        if not text and not calls:
            raise AiRequestError("The AI service returned an empty answer.")
        usage = data.get("usage") or {}
        return ChatReply(
            text=text,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            cached_tokens=int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            calls=tuple(calls),
        )

    def stream_text(
        self,
        system: str,
        context: str,
        question: str,
        image: bytes | None = None,
        image_mime: str | None = None,
        history: list[ChatTurn] | None = None,
        tools: list[dict] | None = None,
    ) -> Iterator[str | ChatReply]:
        payload: dict = {
            "model": self._model,
            "temperature": 0.3,
            "max_tokens": MAX_CHAT_OUTPUT_TOKENS,
            "stream": True,
            "messages": self._chat_messages(system, context, question, image, image_mime, history),
        }
        oa_tools = self._openai_tools(tools)
        if oa_tools:
            payload["tools"] = oa_tools

        text = ""
        tool_buf: dict[int, dict[str, str]] = {}
        input_tokens = output_tokens = cached_tokens = 0

        try:
            with self._client() as client:
                with client.stream("POST", "/chat/completions", json=payload) as res:
                    if res.status_code >= 400:
                        raise AiRequestError(f"The AI service refused the request ({res.status_code}).")
                    for line in res.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        chunk_str = line[5:].strip()
                        if chunk_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(chunk_str)
                        except json.JSONDecodeError:
                            continue
                        if usage := chunk.get("usage"):
                            input_tokens = int(usage.get("prompt_tokens") or input_tokens)
                            output_tokens = int(usage.get("completion_tokens") or output_tokens)
                            cached_tokens = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or cached_tokens)
                        delta = ((chunk.get("choices") or [{}])[0]).get("delta") or {}
                        if piece := delta.get("content"):
                            text += piece
                            yield piece
                        for tc in delta.get("tool_calls") or []:
                            idx = int(tc.get("index", 0))
                            entry = tool_buf.setdefault(idx, {"name": "", "arguments": ""})
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                entry["name"] += fn["name"]
                            if fn.get("arguments"):
                                entry["arguments"] += fn["arguments"]
        except httpx.HTTPError as exc:
            raise AiRequestError(f"Could not reach AI provider: {exc}") from exc

        calls = self._parse_tool_calls([{"function": tool_buf[k]} for k in sorted(tool_buf)])
        if not text.strip() and not calls:
            raise AiRequestError("The AI service returned an empty answer.")
        yield ChatReply(
            text=text.strip(),
            input_tokens=input_tokens,
            cached_tokens=cached_tokens,
            output_tokens=output_tokens,
            calls=tuple(calls),
        )

    def transcribe(self, audio: bytes, mime_type: str) -> str:
        ext = mime_type.split("/")[-1].split(";")[0] or "ogg"
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            with httpx.Client(base_url=self._base_url, headers=headers, timeout=60.0, transport=self._transport) as client:
                res = client.post(
                    "/audio/transcriptions",
                    data={"model": "whisper-1", "prompt": TRANSCRIBE_PROMPT},
                    files={"file": (f"voice.{ext}", audio, mime_type)},
                )
        except httpx.HTTPError as exc:
            raise AiRequestError(f"Could not reach AI provider: {exc}") from exc
        if res.status_code >= 400:
            raise AiRequestError(f"The AI service refused the request ({res.status_code}).")
        try:
            return (res.json().get("text") or "").strip()
        except ValueError as exc:
            raise AiRequestError("The AI service returned an answer that is not valid JSON.") from exc
