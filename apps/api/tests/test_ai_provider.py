import pytest
from pydantic import ValidationError

from config import Settings
from services.ai_provider import AiNotConfigured, build_chat_client, build_lab_parser, build_report_reader
from services.fake_ai import FakeGeminiClient


def test_missing_key_says_how_to_enable():
    with pytest.raises(AiNotConfigured, match="Add GEMINI_API_KEY to .env to enable this"):
        build_lab_parser(Settings(_env_file=None, gemini_api_key="", gemini_model="m"))


def test_missing_model_is_a_clear_configuration_error():
    with pytest.raises(AiNotConfigured, match="GEMINI_MODEL"):
        build_lab_parser(Settings(_env_file=None, gemini_api_key="k", gemini_model=""))


def test_fake_ai_requires_test_environment():
    with pytest.raises(ValidationError, match="APP_ENV=test"):
        Settings(_env_file=None, biostack_fake_ai=True, app_env="")


def test_fake_ai_used_only_when_enabled_in_test_env():
    parser = build_lab_parser(Settings(_env_file=None, biostack_fake_ai=True, app_env="test"))
    assert isinstance(parser.client, FakeGeminiClient)
    assert parser.parse(b"%PDF").rows


def test_report_reader_needs_the_same_configuration_and_says_how_to_continue():
    with pytest.raises(AiNotConfigured, match="Add GEMINI_API_KEY to .env to enable this. You can still type the report in"):
        build_report_reader(Settings(_env_file=None, gemini_api_key="", gemini_model="m"))
    with pytest.raises(AiNotConfigured, match="GEMINI_MODEL"):
        build_report_reader(Settings(_env_file=None, gemini_api_key="k", gemini_model=""))


def test_fake_report_reader_answers_without_network_in_test_env():
    reader = build_report_reader(Settings(_env_file=None, biostack_fake_ai=True, app_env="test"))
    text = reader.read(b"%PDF", "application/pdf")
    assert text.summary_text and "Lungs are clear." in text.findings_text


def test_briefing_writer_uses_the_fake_client_in_test_env_and_needs_configuration_otherwise():
    from services.ai_provider import build_briefing_writer

    writer = build_briefing_writer(Settings(_env_file=None, biostack_fake_ai=True, app_env="test"))
    assert len(writer.write({})) == 3
    with pytest.raises(AiNotConfigured, match="Add GEMINI_API_KEY to .env to enable this"):
        build_briefing_writer(Settings(_env_file=None, gemini_api_key="", gemini_model="m"))


def test_chat_client_needs_the_same_configuration():
    with pytest.raises(AiNotConfigured, match="GEMINI_MODEL"):
        build_chat_client(Settings(_env_file=None, gemini_api_key="k", gemini_model=""))


def test_fake_chat_client_answers_with_usage():
    reply = build_chat_client(Settings(_env_file=None, biostack_fake_ai=True, app_env="test")).generate_text("s", "c", "q")
    assert reply.text and reply.input_tokens > 0
