import datetime as dt

import pytest

from db.models import Biomarker, BodyMeasurement, LabReport, Profile
from main import app
from routers.chat import get_chat_client_factory
from services.ai_provider import AiNotConfigured
from services.gemini_client import AiRequestError, ChatReply

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32


class RecordingChat:
    def __init__(self):
        self.calls = []

    def generate_text(self, system, context, question, image=None, image_mime=None, history=None, tools=None):
        self.calls.append({"system": system, "context": context, "question": question, "image": image, "image_mime": image_mime,
                           "history": history})
        return ChatReply(text="Looks benign; show a doctor.", input_tokens=900, cached_tokens=0, output_tokens=40)


@pytest.fixture(autouse=True)
def chat_data(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)


@pytest.fixture
def chat():
    ai = RecordingChat()
    app.dependency_overrides[get_chat_client_factory] = lambda: (lambda: ai)
    return ai


@pytest.fixture
def filled(session):
    session.add(Profile(id=1, sex="male", height_cm=170.0))
    session.add(BodyMeasurement(measured_on=dt.date(2026, 7, 30), kind="weight", value=70.75))
    report = LabReport(test_date=dt.date(2026, 1, 5), lab_name="Demo Lab", source="manual")
    session.add(report)
    session.commit()
    session.add(Biomarker(report_id=report.id, marker_key="ferritin", display_name="Ferritin", value=9.0, unit="ng/mL", ref_min=30, ref_max=400, is_out_of_range=True))
    session.commit()


def test_answer_comes_back_with_token_usage(client, chat, filled):
    r = client.post("/api/v1/chat/ask", data={"question": "What is this spot on my leg?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Looks benign; show a doctor."
    assert body["usage"] == {"input_tokens": 900, "cached_tokens": 0, "output_tokens": 40}


def test_the_whole_record_goes_as_text_and_the_question_stays_separate(client, chat, filled):
    client.post("/api/v1/chat/ask", data={"question": "What is this spot?"})
    call = chat.calls[0]
    assert call["question"] == "What is this spot?"
    assert "Ferritin" in call["context"] and "out of range" in call["context"]  # lab result with its flag
    assert "70.75" in call["context"] and "170" in call["context"]  # weight and height
    assert "What is this spot?" not in call["context"]  # keeps the cacheable prefix identical across questions
    assert "diagnos" in call["system"].lower()  # told not to diagnose


def test_context_is_identical_between_questions_so_the_provider_can_cache_it(client, chat, filled):
    client.post("/api/v1/chat/ask", data={"question": "one"})
    client.post("/api/v1/chat/ask", data={"question": "two"})
    assert chat.calls[0]["context"] == chat.calls[1]["context"]


def test_a_photo_is_passed_along(client, chat, filled):
    r = client.post("/api/v1/chat/ask", data={"question": "Spot?"}, files={"image": ("spot.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 200
    assert chat.calls[0]["image"] == JPEG and chat.calls[0]["image_mime"] == "image/jpeg"


def test_a_pdf_is_not_accepted_as_a_photo(client, chat, filled):
    r = client.post("/api/v1/chat/ask", data={"question": "Spot?"}, files={"image": ("x.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert r.status_code == 415 and not chat.calls


@pytest.mark.parametrize("question", ["", "   ", "x" * 4001])
def test_empty_or_huge_questions_are_refused(client, chat, filled, question):
    assert client.post("/api/v1/chat/ask", data={"question": question}).status_code == 422
    assert not chat.calls


def test_missing_key_says_what_to_add(client, filled):
    def boom():
        raise AiNotConfigured("Add GEMINI_API_KEY to .env to enable this. x")
    app.dependency_overrides[get_chat_client_factory] = lambda: boom
    r = client.post("/api/v1/chat/ask", data={"question": "Hi"})
    assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"]


def test_ai_failure_is_a_readable_502(client, filled):
    class Down:
        def generate_text(self, *a, **k):
            raise AiRequestError("The AI service refused the request (429).")
    app.dependency_overrides[get_chat_client_factory] = lambda: (lambda: Down())
    r = client.post("/api/v1/chat/ask", data={"question": "Hi"})
    assert r.status_code == 502 and "429" in r.json()["detail"]


def test_earlier_turns_reach_the_model_so_a_follow_up_has_context(client, chat, filled):
    first = client.post("/api/v1/chat/ask", data={"question": "Why is my ferritin low?"}).json()
    r = client.post("/api/v1/chat/ask", data={"question": "Elaborate on that", "thread_id": first["thread_id"]})
    assert r.status_code == 200
    assert [(t.role, t.text) for t in chat.calls[1]["history"]] == [
        ("user", "Why is my ferritin low?"), ("model", "Looks benign; show a doctor.")]


def test_stream_sends_deltas_then_the_saved_answer(client, chat, filled):
    import json
    res = client.post("/api/v1/chat/ask-stream", data={"question": "How am I?"})
    assert res.status_code == 200
    events = [json.loads(line) for line in res.text.splitlines()]
    assert "".join(e["delta"] for e in events if "delta" in e).strip() == "Looks benign; show a doctor."
    done = events[-1]["done"]
    assert done["answer"] == "Looks benign; show a doctor." and done["usage"]["input_tokens"] == 900
    assert len(client.get(f"/api/v1/chat/threads/{done['thread_id']}").json()["messages"]) == 2


def test_stream_reports_an_ai_failure_as_an_error_line(client, chat, filled):
    import json

    def boom():
        raise AiRequestError("nope")
    app.dependency_overrides[get_chat_client_factory] = lambda: boom
    res = client.post("/api/v1/chat/ask-stream", data={"question": "How am I?"})
    assert "error" in json.loads(res.text.splitlines()[-1])
