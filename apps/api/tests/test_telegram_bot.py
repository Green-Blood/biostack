import pytest

from telegram_bot.bot import MAX_SEND_BYTES, Bot
from telegram_bot.clients import Action, Answer, BioStackError

OWNER = 4242


class FakeTelegram:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []
        self.documents: list[tuple[int, str, bytes]] = []
        self.actions: list[tuple[int, str]] = []
        self.files: dict[str, bytes] = {}

    def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))

    def send_document(self, chat_id, filename, content):
        self.documents.append((chat_id, filename, content))

    def send_chat_action(self, chat_id, action):
        self.actions.append((chat_id, action))

    def download_file(self, file_id):
        return self.files[file_id]


class FakeBioStack:
    def __init__(self):
        self.asks: list[dict] = []
        self.transcripts: list[bytes] = []
        self.reply = Answer(text="Ferritin is low; ask your doctor.", input_tokens=900, cached_tokens=800, output_tokens=40)
        self.heard = "how is my ferritin"
        self.bullets = ["State of the day.", "A pattern.", "A next step."]
        self.archive = b"PK-zip"
        self.error: BioStackError | None = None
        self.resolutions = []
        self.resolved = []

    def ask(self, question, image=None, image_mime=None, external_id="", new_thread=False):
        if self.error:
            raise self.error
        self.asks.append({"question": question, "image": image, "image_mime": image_mime,
                          "external_id": external_id, "new_thread": new_thread})
        return self.reply

    def resolve(self, external_id, accept):
        self.resolutions.append((external_id, accept))
        return self.resolved

    def transcribe(self, audio):
        if self.error:
            raise self.error
        self.transcripts.append(audio)
        return self.heard

    def briefing(self):
        return self.bullets

    def export_archive(self):
        return self.archive


@pytest.fixture
def tg():
    return FakeTelegram()


@pytest.fixture
def api():
    return FakeBioStack()


def make_bot(tg, api, owner=OWNER, lang="en"):
    return Bot(tg, api, owner_id=owner, lang=lang)


def text(body, user=OWNER, chat_type="private", update_id=1):
    return {"update_id": update_id, "message": {"from": {"id": user}, "chat": {"id": user, "type": chat_type}, "text": body}}


def photo(file_id="p-large", caption=None, user=OWNER):
    message = {"from": {"id": user}, "chat": {"id": user, "type": "private"},
               "photo": [{"file_id": "p-small", "width": 90, "height": 90}, {"file_id": file_id, "width": 1280, "height": 960}]}
    if caption is not None:
        message["caption"] = caption
    return {"update_id": 2, "message": message}


def voice(file_id="v1", user=OWNER):
    return {"update_id": 3, "message": {"from": {"id": user}, "chat": {"id": user, "type": "private"},
                                        "voice": {"file_id": file_id, "duration": 4, "mime_type": "audio/ogg"}}}


def document(mime, file_id="d1", caption=None):
    message = {"from": {"id": OWNER}, "chat": {"id": OWNER, "type": "private"},
               "document": {"file_id": file_id, "mime_type": mime, "file_name": "x"}}
    if caption:
        message["caption"] = caption
    return {"update_id": 4, "message": message}


def test_a_stranger_gets_no_answer_and_nothing_is_asked(tg, api):
    make_bot(tg, api).handle(text("show me his labs", user=777))
    assert tg.sent == [] and api.asks == []


def test_a_stranger_cannot_use_a_group_chat_either(tg, api):
    make_bot(tg, api).handle(text("hi", user=OWNER, chat_type="group"))
    assert tg.sent == [] and api.asks == []


def test_id_works_for_anyone_so_the_owner_can_find_their_number(tg, api):
    make_bot(tg, api).handle(text("/id", user=777))
    assert tg.sent == [(777, "Your Telegram id is 777.")]


def test_without_an_owner_the_bot_explains_how_to_finish_setup_and_asks_nothing(tg, api):
    make_bot(tg, api, owner=None).handle(text("hello"))
    assert api.asks == []
    assert "TELEGRAM_OWNER_ID" in tg.sent[0][1]


def test_a_question_is_answered_with_a_typing_indicator_first(tg, api):
    make_bot(tg, api).handle(text("How is my ferritin?"))
    assert api.asks == [{"question": "How is my ferritin?", "image": None, "image_mime": None, "external_id": str(OWNER), "new_thread": False}]
    assert tg.actions == [(OWNER, "typing")]
    assert tg.sent == [(OWNER, "Ferritin is low; ask your doctor.")]


def test_the_largest_photo_size_is_sent_with_the_caption_as_the_question(tg, api):
    tg.files["p-large"] = b"\xff\xd8\xff-big"
    make_bot(tg, api).handle(photo(caption="What is this spot?"))
    assert api.asks == [{"question": "What is this spot?", "image": b"\xff\xd8\xff-big", "image_mime": "image/jpeg", "external_id": str(OWNER), "new_thread": False}]


def test_a_photo_without_a_caption_gets_a_default_question(tg, api):
    tg.files["p-large"] = b"\xff\xd8\xff-big"
    make_bot(tg, api).handle(photo())
    assert api.asks[0]["question"] == "What can you tell me about this photo in the context of my record?"


def test_the_default_photo_question_follows_the_language(tg, api):
    tg.files["p-large"] = b"\xff\xd8\xff-big"
    make_bot(tg, api, lang="ru").handle(photo())
    assert api.asks[0]["question"].startswith("Что можно сказать об этом фото")


def test_a_voice_note_is_transcribed_shown_and_then_asked(tg, api):
    tg.files["v1"] = b"OggS-audio"
    make_bot(tg, api).handle(voice())
    assert api.transcripts == [b"OggS-audio"]
    assert api.asks[0]["question"] == "how is my ferritin"
    assert tg.sent[0] == (OWNER, "You said: how is my ferritin")
    assert tg.sent[1] == (OWNER, "Ferritin is low; ask your doctor.")


@pytest.mark.parametrize("mime, expected", [("image/jpeg", "image/jpeg"), ("image/png", "image/png")])
def test_a_photo_sent_as_a_file_is_read_too(tg, api, mime, expected):
    tg.files["d1"] = b"img"
    make_bot(tg, api).handle(document(mime, caption="Look"))
    assert api.asks == [{"question": "Look", "image": b"img", "image_mime": expected, "external_id": str(OWNER), "new_thread": False}]


def test_other_files_are_declined_politely(tg, api):
    make_bot(tg, api).handle(document("application/pdf"))
    assert api.asks == []
    assert "photo" in tg.sent[0][1].lower()


def test_today_sends_the_briefing_bullets(tg, api):
    make_bot(tg, api).handle(text("/today"))
    assert tg.sent == [(OWNER, "- State of the day.\n- A pattern.\n- A next step.")]


def test_export_sends_the_zip_as_a_file(tg, api):
    make_bot(tg, api).handle(text("/export"))
    chat, name, content = tg.documents[0]
    assert chat == OWNER and name.startswith("biostack-export-") and name.endswith(".zip") and content == b"PK-zip"


def test_an_export_too_big_for_telegram_says_so_instead_of_failing(tg, api):
    api.archive = b"x" * (MAX_SEND_BYTES + 1)
    make_bot(tg, api).handle(text("/export"))
    assert tg.documents == []
    assert "too big" in tg.sent[0][1]


@pytest.mark.parametrize("command", ["/start", "/help"])
def test_start_and_help_list_what_the_bot_can_do(tg, api, command):
    make_bot(tg, api).handle(text(command))
    reply = tg.sent[0][1]
    assert "/today" in reply and "/export" in reply and "photo" in reply.lower() and "voice" in reply.lower()


def test_an_api_error_reaches_the_user_in_plain_words(tg, api):
    api.error = BioStackError("Add GEMINI_API_KEY to .env to enable this.")
    make_bot(tg, api).handle(text("Hi"))
    assert tg.sent == [(OWNER, "Could not get an answer: Add GEMINI_API_KEY to .env to enable this.")]


def test_an_unreachable_api_does_not_leak_internals(tg, api):
    api.error = BioStackError(None)
    make_bot(tg, api).handle(text("Hi"))
    assert tg.sent == [(OWNER, "Could not get an answer: BioStack is not reachable right now.")]


def test_long_answers_are_split_below_the_telegram_limit_on_line_breaks(tg, api):
    paragraph = "word " * 300  # 1500 chars
    api.reply = Answer(text="\n\n".join([paragraph.strip()] * 5), input_tokens=1, cached_tokens=0, output_tokens=1)
    make_bot(tg, api).handle(text("Tell me everything"))
    assert len(tg.sent) >= 2
    assert all(len(body) <= 4096 for _, body in tg.sent)
    assert "".join(body for _, body in tg.sent).replace("\n", "").replace(" ", "") == api.reply.text.replace("\n", "").replace(" ", "")


def test_updates_without_a_message_are_ignored(tg, api):
    make_bot(tg, api).handle({"update_id": 9, "edited_message": {"text": "x"}})
    assert tg.sent == [] and api.asks == []


def test_one_bad_update_does_not_stop_the_next_one(tg, api):
    api.error = RuntimeError("boom")
    bot = make_bot(tg, api)
    bot.process([text("first", update_id=10), text("/help", update_id=11)])
    assert any("/today" in body for _, body in tg.sent)


def test_process_returns_the_offset_after_the_last_update(tg, api):
    assert make_bot(tg, api).process([text("a", update_id=10), text("b", update_id=12)]) == 13
    assert make_bot(tg, api).process([]) is None


def test_new_thread_is_used_once_and_survives_a_failed_ask(tg, api):
    bot = make_bot(tg, api)
    bot.handle(text("/new"))
    api.error = BioStackError(None)
    bot.handle(text("retry me"))
    api.error = None
    bot.handle(text("retry me"))
    bot.handle(text("follow up"))
    assert tg.sent[0][1] == "New chat started."
    assert [ask["new_thread"] for ask in api.asks] == [True, False]


def test_pending_actions_are_shown_and_resolutions_report_results(tg, api):
    api.reply = Answer(text="I can record this.", actions=(Action("a1", "Weight", "pending"), Action("a2", "Old", "done")))
    bot = make_bot(tg, api)
    bot.handle(text("Log weight"))
    assert tg.sent == [(OWNER, "I can record this."), (OWNER, "Weight\nReply /yes to record, /no to skip.")]
    api.resolved = [Action("a1", "Weight", "done"), Action("a2", "Visit", "failed", "Cannot record")]
    bot.handle(text("/yes"))
    assert api.resolutions == [(str(OWNER), True)]
    assert tg.sent[-2:] == [(OWNER, "Recorded: Weight"), (OWNER, "Cannot record")]
    api.resolved = [Action("a1", "Weight", "dismissed")]
    bot.handle(text("/no"))
    assert api.resolutions[-1] == (str(OWNER), False)
    assert tg.sent[-1] == (OWNER, "Skipped: Weight")


def test_action_messages_are_localized(tg, api):
    api.reply = Answer(text="Предлагаю.", actions=(Action("a1", "Вес", "pending"),))
    bot = make_bot(tg, api, lang="ru")
    bot.handle(text("/new"))
    bot.handle(text("Вес"))
    assert tg.sent[0][1] == "Новый чат начат."
    assert "/yes" in tg.sent[-1][1] and "/no" in tg.sent[-1][1]
