import datetime as dt

import pytest
from sqlmodel import select

from config import settings
from db.models import BodyMeasurement, ChatMessage, ChatThread, HealthJournal, MedicalRecord, SupplementLog
from main import app
from routers.chat import get_chat_client_factory
from services.gemini_client import AiRequestError, ChatReply, ToolCall

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32


@pytest.fixture
def ai(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    class Fake:
        calls = ()
        history = []
        fail = False
        def generate_text(self, system, context, question, image=None, image_mime=None, history=None, tools=None):
            self.history = history
            if self.fail:
                raise AiRequestError("down")
            return ChatReply(text="", calls=self.calls) if self.calls else ChatReply(text="answer")
    fake = Fake()
    app.dependency_overrides[get_chat_client_factory] = lambda: lambda: fake
    return fake


def ask(client, **data):
    return client.post("/api/v1/chat/ask", data={"question": "hello", **data})


def test_threads_failure_and_history(client, session, ai):
    assert ask(client, thread_id=999).status_code == 404
    ai.fail = True
    assert ask(client).status_code == 502
    assert session.exec(select(ChatThread)).all() == []
    ai.fail = False
    first = ask(client).json()
    assert ask(client, thread_id=first["thread_id"]).status_code == 200
    assert [t.role for t in ai.history] == ["user", "model"]
    detail = client.get(f"/api/v1/chat/threads/{first['thread_id']}").json()
    assert len(detail["messages"]) == 4
    assert client.get("/api/v1/chat/threads").json()[0]["message_count"] == 4


def test_photos_and_delete(client, ai, tmp_path):
    thread = None
    for i in range(5):
        data = {"question": "photo"}
        if thread:
            data["thread_id"] = thread
        result = client.post("/api/v1/chat/ask", data=data, files={"image": ("a.jpg", JPEG + bytes([i]), "image/jpeg")}).json()
        thread = result["thread_id"]
    ask(client, thread_id=thread)
    assert sum(t.image is not None for t in ai.history) == 4
    detail = client.get(f"/api/v1/chat/threads/{thread}").json()
    assert client.get(detail["messages"][0]["image_url"]).status_code == 200
    assert client.delete(f"/api/v1/chat/threads/{thread}").status_code == 204
    assert not list((tmp_path / "chat").glob("*"))


def test_telegram_idle_and_new(client, session, ai):
    first = ask(client, channel="telegram", external_id="12").json()["thread_id"]
    assert ask(client, channel="telegram", external_id="12").json()["thread_id"] == first
    thread = session.get(ChatThread, first)
    thread.updated_at -= dt.timedelta(hours=7)
    session.add(thread)
    session.commit()
    second = ask(client, channel="telegram", external_id="12").json()["thread_id"]
    assert second != first
    assert ask(client, channel="telegram", external_id="12", new_thread="true").json()["thread_id"] != second


@pytest.mark.parametrize("name,args,model", [
    ("add_body_measurement", {"kind": "weight", "value": 70}, BodyMeasurement),
    ("log_visit", {"title": "Doctor"}, MedicalRecord),
    ("add_journal_entry", {"title": "Headache"}, HealthJournal),
    ("log_supplement", {"item_name": "Vitamin D"}, SupplementLog),
])
def test_confirm_actions(client, session, ai, name, args, model):
    ai.calls = (ToolCall(name, args),)
    result = ask(client).json()
    assert "args" not in result["actions"][0]
    url = f"/api/v1/chat/messages/{result['message_id']}/actions/a1/confirm"
    assert client.post(url).json()["status"] == "done"
    assert session.exec(select(model)).first() is not None
    assert client.post(url).status_code == 409


def test_invalid_dismiss_failed_and_resolve(client, session, ai):
    ai.calls = (ToolCall("add_body_measurement", {"kind": "weight", "value": 5000}),)
    assert ask(client).json()["actions"] == []
    ai.calls = (ToolCall("add_body_measurement", {"kind": "weight", "value": 70, "date": "2999-01-01"}),)
    result = ask(client).json()
    url = f"/api/v1/chat/messages/{result['message_id']}/actions/a1/confirm"
    assert client.post(url).json()["status"] == "failed"
    ai.calls = (ToolCall("add_body_measurement", {"kind": "weight", "value": 70}),)
    ask(client, channel="telegram", external_id="12")
    assert client.post("/api/v1/chat/resolve", data={"external_id": "12", "accept": "false"}).json()["actions"][0]["status"] == "dismissed"
    assert session.exec(select(BodyMeasurement)).all() == []
