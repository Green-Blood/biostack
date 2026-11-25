"""Text the API produces for people comes back in the language the web app asks for.

The web proxy sends `Accept-Language: ru` or `en`. Anything that is not Russian is English, so tests and curl, which
send no header, keep the English wording. English messages are the source of truth (see i18n_messages).
"""
import re
from functools import lru_cache
from typing import Literal

from fastapi import Request

from services.i18n_messages import EN, RU

Lang = Literal["ru", "en"]
_CATALOGS = {"en": EN, "ru": RU}


def parse_lang(header: str | None) -> Lang:
    first = (header or "").split(",")[0].split(";")[0].strip().lower()
    return "ru" if first == "ru" or first.startswith("ru-") else "en"


def get_lang(request: Request) -> Lang:
    """FastAPI dependency: the language of the first tag in Accept-Language."""
    return parse_lang(request.headers.get("accept-language"))


def msg(lang: str, key: str, **params: object) -> str:
    template = _CATALOGS["ru" if lang == "ru" else "en"][key]
    return template.format(**params)


def plural_category(lang: str, n: int) -> str:
    """"one" | "few" | "many". English has only one/many; Russian follows 1 / 2-4 / 5+ (11-14 are "many")."""
    if lang != "ru":
        return "one" if n == 1 else "many"
    if n % 10 == 1 and n % 100 != 11:
        return "one"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "few"
    return "many"


def msg_plural(lang: str, key: str, n: int, **params: object) -> str:
    """The catalog entry `<key>.one|few|many` for a count, with {n} filled in."""
    return msg(lang, f"{key}.{plural_category(lang, n)}", n=n, **params)


@lru_cache(maxsize=1)
def _patterns() -> list[tuple[re.Pattern[str], str]]:
    found = []
    for key, template in EN.items():
        pieces = re.split(r"{(\w+)}", template)
        body = "".join(re.escape(p) if i % 2 == 0 else f"(?P<{p}>.+?)" for i, p in enumerate(pieces))
        found.append((re.compile(f"^{body}$", re.S), key))
    return found


def translate_text(lang: str, text: str) -> str:
    """Translates an English message raised by a service (an exception's text) when it is in the catalog."""
    if lang != "ru":
        return text
    for pattern, key in _patterns():
        match = pattern.match(text)
        if match:
            return msg(lang, key, **{name: translate_text(lang, value) for name, value in match.groupdict().items()})
    return text
