"""Character counting shared by the duration tool and the scripted model."""

import re

NUMBER_TOKEN = re.compile(r"\d+(?:\.\d+)?%|\d+(?:\.\d+)?倍")
GENERIC_THEME_WORDS = ("短视频", "视频", "脚本", "做一个", "做一条", "生成", "一个")


def is_spoken(char: str) -> bool:
    if char.isascii() and char.isalnum():
        return True
    code = ord(char)
    return 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF


def spoken_text(text: str) -> str:
    return "".join(char for char in text if is_spoken(char))


def spoken_count(text: str) -> int:
    return len(spoken_text(text))


def duration_ms(char_count: int, chars_per_second: float) -> int:
    return int(round(char_count * 1000 / chars_per_second))


def chars_per_second(style: str) -> float:
    if style == "纯字幕":
        return 3.5
    return 4.0


def seconds_of(milliseconds: int) -> float:
    return round(milliseconds / 1000, 3)


def target_ms(duration_sec: float) -> int:
    return int(round(duration_sec * 1000))


def number_tokens(text: str) -> list[str]:
    return NUMBER_TOKEN.findall(text)


def content_theme(theme: str) -> str:
    text = theme.strip()
    for word in GENERIC_THEME_WORDS:
        text = text.replace(word, "")
    return text.strip()


def pad_to_spoken_length(length: int, fact: str) -> str:
    if spoken_count(fact) > length:
        raise ValueError(f"fact is longer than {length}")
    filler = "今天继续往下看"
    text = fact
    while spoken_count(text) < length:
        text += filler
    while spoken_count(text) > length:
        text = text[:-1]
    if fact not in text:
        raise ValueError("padding removed the cited fact")
    return text
