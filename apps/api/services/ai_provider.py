"""Chooses the AI client from settings; reports a missing configuration instead of failing obscurely."""
from config import Settings
from services.briefing_writer import BriefingWriter
from services.fake_ai import FakeGeminiClient
from services.gemini_client import AiRequestError, ChatClient, GeminiClient, GoogleGenAIClient, Transcriber
from services.gemini_parser import LabParser
from services.openai_compat_client import OpenAICompatClient
from services.report_reader import ReportReader
from services.scan_extractor import ScanExtractor


class AiNotConfigured(Exception):
    """AI features need a key and a model name in .env."""


def _build_client(settings: Settings, fallback: str) -> GeminiClient:
    if settings.biostack_fake_ai:  # Settings guarantees APP_ENV=test here
        return FakeGeminiClient()
    if settings.ai_provider == "openai_compat":
        if not settings.openai_base_url:
            raise AiNotConfigured(f"Set AI_PROVIDER=openai_compat and OPENAI_BASE_URL in .env to enable this. {fallback}")
        if not settings.openai_model:
            raise AiNotConfigured(f"Add OPENAI_MODEL to .env to enable this. {fallback}")
        return OpenAICompatClient(settings.openai_base_url, settings.openai_model, settings.openai_api_key)
    if not settings.gemini_api_key:
        raise AiNotConfigured(f"Add GEMINI_API_KEY to .env to enable this. {fallback}")
    if not settings.gemini_model:
        raise AiNotConfigured(f"Add GEMINI_MODEL to .env to enable this. {fallback}")
    return GoogleGenAIClient(settings.gemini_api_key, settings.gemini_model)


def ai_status(settings: Settings) -> dict:
    """Safe summary of active AI configuration (never exposes API keys)."""
    if settings.biostack_fake_ai:
        return {"provider": "fake", "model": "fake", "configured": True, "base_url": None}
    if settings.ai_provider == "openai_compat":
        return {
            "provider": "openai_compat",
            "model": settings.openai_model or None,
            "configured": bool(settings.openai_base_url and settings.openai_model),
            "base_url": settings.openai_base_url or None,
        }
    return {
        "provider": "gemini",
        "model": settings.gemini_model or None,
        "configured": bool(settings.gemini_api_key and settings.gemini_model),
        "base_url": None,
    }


def check_ai_connection(settings: Settings) -> dict:
    """Run a lightweight connectivity & model check against the configured AI provider."""
    if settings.biostack_fake_ai:
        return {"ok": True, "provider": "fake", "model": "fake"}
    client = _build_client(settings, "Check your .env configuration.")
    if isinstance(client, OpenAICompatClient):
        return client.ping()
    if isinstance(client, GoogleGenAIClient):
        try:
            client._client.models.get(model=settings.gemini_model)
        except Exception as exc:  # noqa: BLE001
            raise AiRequestError(f"Gemini model check failed: {exc}") from exc
        return {"ok": True, "provider": "gemini", "model": settings.gemini_model}
    return {"ok": True, "provider": settings.ai_provider, "model": settings.gemini_model}


def build_lab_parser(settings: Settings) -> LabParser:
    return LabParser(_build_client(settings, "You can still enter results by hand."))


def build_report_reader(settings: Settings) -> ReportReader:
    return ReportReader(_build_client(settings, "You can still type the report in."))


def build_scan_extractor(settings: Settings) -> ScanExtractor:
    return ScanExtractor(_build_client(settings, "You can still enter the measurements by hand."))


def build_briefing_writer(settings: Settings) -> BriefingWriter:
    return BriefingWriter(_build_client(settings, "A summary from your data is shown instead."))


def build_insight_client(settings: Settings) -> GeminiClient:
    return _build_client(settings, "Your results are still here to read yourself.")


def build_chat_client(settings: Settings) -> ChatClient:
    return _build_client(settings, "Your records are still here to read yourself.")  # type: ignore[return-value]


def build_transcriber(settings: Settings) -> Transcriber:
    return _build_client(settings, "Type your question instead.")  # type: ignore[return-value]
