"""Thin, injectable wrapper around the google-genai SDK. Everything else depends on the protocol only."""
import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from google import genai
from google.genai import errors, types

PDF = "application/pdf"


class AiRequestError(Exception):
    """The AI service failed or returned something that is not JSON."""


class GeminiClient(Protocol):
    def generate_json(self, prompt: str, document: bytes, schema: dict, mime_type: str = PDF) -> dict: ...

    def generate_grounded(self, prompt: str, document: bytes, mime_type: str = "application/json") -> str: ...


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict


@dataclass(frozen=True)
class ChatReply:
    text: str
    input_tokens: int = 0
    cached_tokens: int = 0  # part of the input the provider served from its cache, billed at a discount
    output_tokens: int = 0
    calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class ChatTurn:
    role: str  # "user" or "model"
    text: str
    image: bytes | None = None
    image_mime: str | None = None


class ChatClient(Protocol):
    def generate_text(self, system: str, context: str, question: str, image: bytes | None = None,
                      image_mime: str | None = None, history: list[ChatTurn] | None = None,
                      tools: list[dict] | None = None) -> ChatReply: ...


class Transcriber(Protocol):
    def transcribe(self, audio: bytes, mime_type: str) -> str: ...


TRANSCRIBE_PROMPT = ("Transcribe this voice note word for word in the language spoken. "
                     "Reply with the transcript only; if there is no speech, reply with nothing.")
MAX_CHAT_OUTPUT_TOKENS = 2048  # a ceiling for cost; includes the model's own thinking on some models


class GoogleGenAIClient:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate_json(self, prompt: str, document: bytes, schema: dict, mime_type: str = PDF) -> dict:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[types.Part.from_bytes(data=document, mime_type=mime_type), prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_json_schema=schema, temperature=0,
                ),
            )
            return json.loads(response.text or "")
        except errors.APIError as exc:
            raise AiRequestError(f"The AI service refused the request ({exc.code}).") from exc
        except (json.JSONDecodeError, TypeError) as exc:
            raise AiRequestError("The AI service returned an answer that is not valid JSON.") from exc

    def generate_grounded(self, prompt: str, document: bytes, mime_type: str = "application/json") -> str:
        """Free text from a call that may search Google. JSON mode cannot be combined with search, so the caller parses."""
        def call(tools):
            return self._client.models.generate_content(
                model=self._model, contents=[types.Part.from_bytes(data=document, mime_type=mime_type), prompt],
                config=types.GenerateContentConfig(tools=tools, temperature=0.3))
        try:
            try:
                response = call([types.Tool(google_search=types.GoogleSearch())])
            except errors.APIError as exc:
                if exc.code not in (400, 403, 429):
                    raise
                response = call(None)  # ponytail: search may have its own quota or be unsupported; an answer from the model alone beats none
        except errors.APIError as exc:
            hint = " The AI quota is used up for now; try again later or choose another GEMINI_MODEL." if exc.code == 429 else ""
            raise AiRequestError(f"The AI service refused the request ({exc.code}).{hint}") from exc
        text = (response.text or "").strip()
        if not text:
            raise AiRequestError("The AI service returned an empty answer.")
        return text

    def _chat_request(self, system, context, question, image, image_mime, history, tools):
        turns = list(history or []) + [ChatTurn("user", question, image, image_mime)]
        contents = []
        for index, turn in enumerate(turns):
            parts = [types.Part.from_text(text=turn.text)]
            if turn.image is not None and turn.image_mime:
                parts.insert(0, types.Part.from_bytes(data=turn.image, mime_type=turn.image_mime))
            if index == 0:
                parts.insert(0, types.Part.from_text(text=context))
            contents.append(types.Content(role=turn.role, parts=parts))
        declarations = [types.FunctionDeclaration(name=t["name"], description=t["description"],
                                                   parameters_json_schema=t["parameters"]) for t in tools or []]
        config = types.GenerateContentConfig(system_instruction=system, temperature=0.3,
            max_output_tokens=MAX_CHAT_OUTPUT_TOKENS,
            tools=[types.Tool(function_declarations=declarations)] if declarations else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        return contents, config

    @staticmethod
    def _visible(response) -> list:
        parts = response.candidates[0].content.parts if response.candidates and response.candidates[0].content else []
        return [p for p in parts or [] if not p.thought]

    @staticmethod
    def _reply(text: str, calls: list, usage) -> ChatReply:
        if not text and not calls:
            raise AiRequestError("The AI service returned an empty answer.")
        return ChatReply(text=text, input_tokens=(usage.prompt_token_count or 0) if usage else 0,
                         cached_tokens=(usage.cached_content_token_count or 0) if usage else 0,
                         output_tokens=(usage.candidates_token_count or 0) if usage else 0, calls=tuple(calls))

    def generate_text(self, system: str, context: str, question: str, image: bytes | None = None,
                      image_mime: str | None = None, history: list[ChatTurn] | None = None,
                      tools: list[dict] | None = None) -> ChatReply:
        contents, config = self._chat_request(system, context, question, image, image_mime, history, tools)
        try:
            response = self._client.models.generate_content(model=self._model, contents=contents, config=config)
        except errors.APIError as exc:
            raise AiRequestError(f"The AI service refused the request ({exc.code}).") from exc
        visible = self._visible(response)
        calls = [ToolCall(p.function_call.name, dict(p.function_call.args or {}))
                 for p in visible if p.function_call and p.function_call.name]
        return self._reply("".join(p.text for p in visible if p.text).strip(), calls, response.usage_metadata)

    def stream_text(self, system: str, context: str, question: str, image: bytes | None = None,
                    image_mime: str | None = None, history: list[ChatTurn] | None = None,
                    tools: list[dict] | None = None) -> Iterator[str | ChatReply]:
        """Yields text deltas as they arrive, then the finished ChatReply (with tool calls and usage) last."""
        contents, config = self._chat_request(system, context, question, image, image_mime, history, tools)
        text, calls, usage = "", [], None
        try:
            for chunk in self._client.models.generate_content_stream(model=self._model, contents=contents, config=config):
                usage = chunk.usage_metadata or usage
                for p in self._visible(chunk):
                    if p.function_call and p.function_call.name:
                        calls.append(ToolCall(p.function_call.name, dict(p.function_call.args or {})))
                    elif p.text:
                        text += p.text
                        yield p.text
        except errors.APIError as exc:
            raise AiRequestError(f"The AI service refused the request ({exc.code}).") from exc
        yield self._reply(text.strip(), calls, usage)

    def transcribe(self, audio: bytes, mime_type: str) -> str: ...


TRANSCRIBE_PROMPT = ("Transcribe this voice note word for word in the language spoken. "
                     "Reply with the transcript only; if there is no speech, reply with nothing.")
MAX_CHAT_OUTPUT_TOKENS = 2048  # a ceiling for cost; includes the model's own thinking on some models


class GoogleGenAIClient:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate_json(self, prompt: str, document: bytes, schema: dict, mime_type: str = PDF) -> dict:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[types.Part.from_bytes(data=document, mime_type=mime_type), prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_json_schema=schema, temperature=0,
                ),
            )
            return json.loads(response.text or "")
        except errors.APIError as exc:
            raise AiRequestError(f"The AI service refused the request ({exc.code}).") from exc
        except (json.JSONDecodeError, TypeError) as exc:
            raise AiRequestError("The AI service returned an answer that is not valid JSON.") from exc

    def generate_grounded(self, prompt: str, document: bytes, mime_type: str = "application/json") -> str:
        """Free text from a call that may search Google. JSON mode cannot be combined with search, so the caller parses."""
        def call(tools):
            return self._client.models.generate_content(
                model=self._model, contents=[types.Part.from_bytes(data=document, mime_type=mime_type), prompt],
                config=types.GenerateContentConfig(tools=tools, temperature=0.3))
        try:
            try:
                response = call([types.Tool(google_search=types.GoogleSearch())])
            except errors.APIError as exc:
                if exc.code not in (400, 403, 429):
                    raise
                response = call(None)  # ponytail: search may have its own quota or be unsupported; an answer from the model alone beats none
        except errors.APIError as exc:
            hint = " The AI quota is used up for now; try again later or choose another GEMINI_MODEL." if exc.code == 429 else ""
            raise AiRequestError(f"The AI service refused the request ({exc.code}).{hint}") from exc
        text = (response.text or "").strip()
        if not text:
            raise AiRequestError("The AI service returned an empty answer.")
        return text

    def generate_text(self, system: str, context: str, question: str, image: bytes | None = None,
                      image_mime: str | None = None, history: list[ChatTurn] | None = None,
                      tools: list[dict] | None = None) -> ChatReply:
        turns = list(history or []) + [ChatTurn("user", question, image, image_mime)]
        contents = []
        for index, turn in enumerate(turns):
            parts = [types.Part.from_text(text=turn.text)]
            if turn.image is not None and turn.image_mime:
                parts.insert(0, types.Part.from_bytes(data=turn.image, mime_type=turn.image_mime))
            if index == 0:
                parts.insert(0, types.Part.from_text(text=context))
            contents.append(types.Content(role=turn.role, parts=parts))
        declarations = [types.FunctionDeclaration(name=t["name"], description=t["description"],
                                                   parameters_json_schema=t["parameters"]) for t in tools or []]
        try:
            response = self._client.models.generate_content(
                model=self._model, contents=contents,
                config=types.GenerateContentConfig(system_instruction=system, temperature=0.3,
                    max_output_tokens=MAX_CHAT_OUTPUT_TOKENS,
                    tools=[types.Tool(function_declarations=declarations)] if declarations else None,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)),
            )
        except errors.APIError as exc:
            raise AiRequestError(f"The AI service refused the request ({exc.code}).") from exc
        parts = response.candidates[0].content.parts if response.candidates and response.candidates[0].content else []
        visible = [p for p in parts or [] if not p.thought]
        text = "".join(p.text for p in visible if p.text).strip()
        calls = tuple(ToolCall(p.function_call.name, dict(p.function_call.args or {}))
                      for p in visible if p.function_call and p.function_call.name)
        if not text and not calls:
            raise AiRequestError("The AI service returned an empty answer.")
        usage = response.usage_metadata
        return ChatReply(text=text, input_tokens=(usage.prompt_token_count or 0) if usage else 0,
                         cached_tokens=(usage.cached_content_token_count or 0) if usage else 0,
                         output_tokens=(usage.candidates_token_count or 0) if usage else 0, calls=calls)

    def transcribe(self, audio: bytes, mime_type: str) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._model, contents=[types.Part.from_bytes(data=audio, mime_type=mime_type), TRANSCRIBE_PROMPT],
                config=types.GenerateContentConfig(temperature=0),
            )
        except errors.APIError as exc:
            raise AiRequestError(f"The AI service refused the request ({exc.code}).") from exc
        return (response.text or "").strip()
