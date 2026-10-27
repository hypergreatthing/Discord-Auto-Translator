import re
from typing import Tuple, Dict

# Regex patterns for Discord-specific markdown elements and URLs
DISCORD_PATTERNS = [
    (r"<@!?\d+>", "USER_MENTION"),       # User mentions <@12345>
    (r"<@&\d+>", "ROLE_MENTION"),        # Role mentions <@&12345>
    (r"<#\d+>", "CHANNEL_LINK"),         # Channel mentions <#12345>
    (r"<a?:\w+:\d+>", "CUSTOM_EMOJI"),   # Custom emojis <:name:12345>
    (r"https?://[^\s<>]+", "URL"),       # URLs
    (r"```[\s\S]*?```", "CODE_BLOCK"),   # Multi-line code blocks
    (r"`[^`]+`", "INLINE_CODE"),         # Inline code
]

class DiscordMasker:
    """
    Masks Discord tokens, mentions, emojis, and code blocks before sending text
    to the Neural MT engine so IDs, links, and code are never translated or corrupted.
    """

    @staticmethod
    def mask(text: str) -> Tuple[str, Dict[str, str]]:
        placeholders: Dict[str, str] = {}
        masked_text = text
        token_counter = 0

        for pattern, tag in DISCORD_PATTERNS:
            def repl(match):
                nonlocal token_counter
                key = f"__DCTOK_{tag}_{token_counter}__"
                placeholders[key] = match.group(0)
                token_counter += 1
                return key

            masked_text = re.sub(pattern, repl, masked_text)

        return masked_text, placeholders

    @staticmethod
    def unmask(text: str, placeholders: Dict[str, str]) -> str:
        restored = text
        for placeholder, original in placeholders.items():
            # Handle cases where model might introduce extra whitespace around underscores
            clean_key = placeholder
            restored = restored.replace(clean_key, original)
            # Fuzzy match in case tokenizer broke token
            tag_name = clean_key.strip("_")
            restored = re.sub(rf"__\s*{re.escape(tag_name)}\s*__", original, restored)
        return restored
