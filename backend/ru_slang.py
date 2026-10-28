"""
Russian slang / chat-shorthand normalizer.

NLLB is trained mostly on formal parallel text, so internet slang, gaming jargon and chat
abbreviations are often translated literally or left untouched (e.g. "блин" -> "pancake",
"гг" -> "gg" with no meaning). This module rewrites known slang into plain, standard Russian
that the model translates reliably. It runs on the *source* text only, before tokenization.

The glossary is intentionally conservative: ambiguous words whose slang sense is not clearly
dominant in chat (e.g. "душно", "короче" on its own) are left alone.
"""
from typing import Dict, List, Tuple

import regex

# (slang pattern, plain-Russian replacement). Patterns are matched case-insensitively as whole
# words. Longer / multi-word entries are listed first so they win over their sub-words.
_RAW_GLOSSARY: List[Tuple[str, str]] = [
    # --- multi-word phrases ---
    (r"ржу\s+не\s*могу", "умираю со смеху"),
    (r"короче\s+говоря", "в общем"),
    (r"хрен\s+знает", "кто его знает"),
    (r"хз", "не знаю"),
    (r"го\s+в\s+дс", "давай в дискорд"),

    # --- gaming / chat ---
    (r"гг(?:шка)?", "хорошая игра"),
    (r"изи", "легко"),
    (r"лол", "ха-ха"),
    (r"кринж(?:ово|овый|овая|овое|а)?", "очень неловко и стыдно"),
    (r"рофл(?:ить|ю)?", "шутка"),
    (r"ору", "я смеюсь до слёз"),
    (r"ржу|ржач|ржака", "очень смешно"),
    (r"имба(?:а)?", "невероятно сильный"),
    (r"нуб(?:ас|ы|ик)?", "новичок"),
    (r"афк", "отошёл от компьютера"),
    (r"го", "давай"),
    (r"дс", "дискорд"),
    (r"кд", "время перезарядки"),
    (r"тильт(?:ую|ит)?", "злюсь"),
    (r"пати", "группа"),
    (r"фарм(?:ить|лю)", "добывать ресурсы"),
    (r"найс", "отлично"),
    (r"красав(?:а|чик)", "молодец"),
    (r"жиза", "это очень жизненно, со мной так же"),
    (r"годнот(?:а|ы)", "отличная вещь"),
    (r"годн(?:о|ый|ая|ое)", "хороший"),
    (r"рили", "правда"),
    (r"душнил(?:а|ы)", "зануда"),
    (r"зашкв?ар(?:ный|но)?", "позор"),
    (r"вайб", "атмосфера"),
    (r"хайп", "ажиотаж"),
    (r"чилить", "отдыхать"),

    # --- people / address ---
    (r"бро|братан|братишка", "друг"),
    (r"чел(?:ик)?", "парень"),
    (r"лошара|лох", "неудачник"),
    (r"сорян|сорри", "извини"),
    (r"здарова|дарова|прив|хай", "привет"),
    (r"споки", "спокойной ночи"),
    (r"спс|спасибки", "спасибо"),
    (r"пожалуйста|пож|плз|пжлст", "пожалуйста"),

    # --- common shorthand / fillers ---
    (r"норм", "нормально"),
    (r"мб", "может быть"),
    (r"чё|че", "что"),
    (r"щас|ща", "сейчас"),
    (r"кст", "кстати"),
    (r"имхо", "по моему мнению"),
    (r"типа", "как бы"),
    (r"угу", "да"),
    (r"ничоси", "ничего себе"),
    (r"пофиг(?:у)?", "всё равно"),
    (r"прикольно", "здорово"),
    (r"прикол", "забавная вещь"),

    # --- mild intensifiers & euphemisms ("pancake" fixes) ---
    (r"блин|бляха|бля", "чёрт"),
    (r"капец|пипец|писец|ппц", "ужас"),
    (r"жесть", "что-то невероятное"),
    (r"офигеть|ахренеть|охренеть", "ничего себе"),
    (r"офигенно|охренительно", "потрясающе"),
    (r"зашибись|заебись", "отлично"),
    (r"фигня|хрень|херня", "ерунда"),
    (r"нафига|нахрена", "зачем"),
    (r"пиздец", "полный кошмар"),
    (r"пиздато|охуенно", "потрясающе"),
    (r"нихуя|нихрена", "ничего"),
]

_WORD = r"(?<![\p{L}\p{N}_])(?:%PATTERN%)(?![\p{L}\p{N}_])"

_COMPILED = [
    (regex.compile(_WORD.replace("%PATTERN%", pat), regex.IGNORECASE | regex.UNICODE), repl)
    for pat, repl in _RAW_GLOSSARY
]


def _match_case(original: str, replacement: str) -> str:
    """Preserve leading capital / ALL-CAPS of the matched slang word."""
    letters = [c for c in original if c.isalpha()]
    if len(letters) > 2 and all(c.isupper() for c in letters):
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def normalize_ru(text: str) -> str:
    """Rewrite Russian slang / chat shorthand in `text` into plain Russian."""
    if not text or not regex.search(r"\p{Cyrillic}", text):
        return text
    for pattern, repl in _COMPILED:
        text = pattern.sub(lambda m, r=repl: _match_case(m.group(0), r), text)
    return text
