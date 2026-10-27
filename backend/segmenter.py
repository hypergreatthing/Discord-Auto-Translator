import re
from typing import List

# Common abbreviations to avoid false sentence splits
ABBREVIATIONS = (
    r"(?:etc|e\.g|i\.e|vs|mr|mrs|ms|dr|prof|st|ave|rd|gen|col|approx|dept)\."
)

class SentenceSegmenter:
    """
    Splits text into complete grammatical sentences and thoughts across
    Western and Asian scripts, preventing sentence fragmentation.
    """

    @classmethod
    def split_sentences(cls, text: str) -> List[str]:
        if not text or not text.strip():
            return []

        clean_text = text.strip()

        # Step 1: Normalize common multi-character punctuations
        normalized = re.sub(r"\.{3,}", "…", clean_text)

        # Step 2: Protect common abbreviations
        def abbrev_protect(m):
            return m.group(0).replace(".", "___DOT___")

        protected = re.sub(ABBREVIATIONS, abbrev_protect, normalized, flags=re.IGNORECASE)

        # Step 3: Protect decimal numbers (e.g., 3.14, 1.5k)
        protected = re.sub(r"(\d)\.(\d)", r"\1___DOT___\2", protected)

        # Step 4: Split along punctuation boundaries
        # Supports Latin (. ! ? …), CJK (。！？…), Arabic (؟)
        # Using lookbehind to keep delimiters attached to the sentence
        pattern = r"(?<=[.!?。！？…؟])\s+(?=[^\d\s])|(?<=[。！？])"
        parts = re.split(pattern, protected)

        # Step 5: Restore protected dots and filter empty strings
        sentences = []
        for part in parts:
            restored = part.replace("___DOT___", ".").strip()
            if restored:
                sentences.append(restored)

        # Fallback if no delimiter was found
        if not sentences and clean_text:
            sentences = [clean_text]

        return sentences
