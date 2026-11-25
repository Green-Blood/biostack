"""Run the bot: `python -m telegram_bot`. It long-polls Telegram, so it needs no public address."""
import logging
import sys
import time

from config import settings
from telegram_bot.bot import Bot
from telegram_bot.clients import BioStackApi, TelegramApi, TelegramError

POLL_SECONDS = 30
RETRY_SECONDS = 5

log = logging.getLogger("telegram_bot")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its request lines contain the bot token
    if not settings.telegram_bot_token:
        log.warning("TELEGRAM_BOT_TOKEN is not set; the bot stays off. Create a bot with @BotFather and add the token to .env.")
        return 0
    owner = int(settings.telegram_owner_id) if settings.telegram_owner_id.strip() else None
    if owner is None:
        log.warning("TELEGRAM_OWNER_ID is not set; the bot only answers /id until you add it.")
    telegram = TelegramApi(settings.telegram_bot_token)
    api = BioStackApi(settings.biostack_api_url, settings.api_secret_key, settings.bot_lang)
    bot = Bot(telegram, api, owner, settings.bot_lang)
    log.info("Bot is listening.")
    offset: int | None = None
    while True:
        try:
            updates = telegram.get_updates(offset, POLL_SECONDS)
        except TelegramError as exc:
            log.warning("%s; retrying in %s s", exc, RETRY_SECONDS)
            time.sleep(RETRY_SECONDS)
            continue
        offset = bot.process(updates) or offset


if __name__ == "__main__":
    sys.exit(main())
