"""Everything the bot says, in the two languages the app speaks."""
TEXTS = {
    "en": {
        "help": ("I answer questions about your health record.\n\n"
                 "- Write a question, or send a voice note.\n"
                 "- Send a photo (the caption is your question).\n"
                 "/new - start a new chat\n"
                 "/yes or /no - confirm or skip proposed actions\n"
                 "/today - today's summary\n"
                 "/export - everything as one ZIP\n"
                 "/id - your Telegram id"),
        "your_id": "Your Telegram id is {id}.",
        "new_chat": "New chat started.",
        "action_hint": "Reply /yes to record, /no to skip.",
        "recorded": "Recorded: {label}",
        "dismissed": "Skipped: {label}",
        "setup": "Almost ready. Put your id ({id}) into TELEGRAM_OWNER_ID in .env and restart the bot. Send /id any time to see it again.",
        "photo_question": "What can you tell me about this photo in the context of my record?",
        "you_said": "You said: {text}",
        "other_file": "I can only read photos. Send a photo, or use the web app for PDFs and scans.",
        "export_too_big": "The export is too big to send through Telegram ({mb} MB, the limit is 50 MB). Download it in the web app instead.",
        "failed": "Could not get an answer: {reason}",
        "unreachable": "BioStack is not reachable right now.",
        "crashed": "Something went wrong on my side. Try again in a minute.",
    },
    "ru": {
        "help": ("Я отвечаю на вопросы о вашей медицинской карте.\n\n"
                 "- Напишите вопрос или отправьте голосовое сообщение.\n"
                 "- Отправьте фото (подпись к нему станет вопросом).\n"
                 "/new - начать новый чат\n"
                 "/yes или /no - подтвердить или пропустить предложенные действия\n"
                 "/today - сводка на сегодня\n"
                 "/export - всё одним ZIP-файлом\n"
                 "/id - ваш Telegram id"),
        "your_id": "Ваш Telegram id: {id}.",
        "new_chat": "Новый чат начат.",
        "action_hint": "Ответьте /yes, чтобы записать, или /no, чтобы пропустить.",
        "recorded": "Записано: {label}",
        "dismissed": "Пропущено: {label}",
        "setup": "Почти готово. Впишите ваш id ({id}) в TELEGRAM_OWNER_ID в .env и перезапустите бота. Отправьте /id, чтобы увидеть его снова.",
        "photo_question": "Что можно сказать об этом фото с учётом моей медицинской карты?",
        "you_said": "Вы сказали: {text}",
        "other_file": "Я читаю только фото. Отправьте фото или загрузите PDF и снимки в веб-приложении.",
        "export_too_big": "Экспорт слишком большой для Telegram ({mb} МБ, лимит 50 МБ). Скачайте его в веб-приложении.",
        "failed": "Не удалось получить ответ: {reason}",
        "unreachable": "BioStack сейчас недоступен.",
        "crashed": "У меня что-то пошло не так. Повторите через минуту.",
    },
}
