import os
import re
import threading
from typing import Dict, Any, List, Optional, Tuple
import langdetect
import regex

# langdetect is non-deterministic by default (same text can yield different languages run-to-run).
langdetect.DetectorFactory.seed = 0

try:
    import ctranslate2
    from transformers import NllbTokenizerFast, AutoTokenizer
    from huggingface_hub import snapshot_download
    CT2_AVAILABLE = True
except ImportError:
    CT2_AVAILABLE = False

from .segmenter import SentenceSegmenter
from .masker import DiscordMasker
from .ru_slang import normalize_ru
from .config import load_config

# Map common ISO-639-1 language codes to NLLB-200 language tokens
NLLB_LANG_MAP = {
    "en": "eng_Latn",
    "ja": "jpn_Jpan",
    "zh": "zho_Hans",
    "zh-cn": "zho_Hans",  # langdetect's code for Simplified Chinese
    "zh-tw": "zho_Hant",
    "es": "spa_Latn",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "ru": "rus_Cyrl",
    "ko": "kor_Hang",
    "it": "ita_Latn",
    "pt": "por_Latn",
    "ar": "arb_Arab",
    "hi": "hin_Deva",
    "vi": "vie_Latn",
    "th": "tha_Thai",
    "id": "ind_Latn",
    "pl": "pol_Latn",
    "nl": "nld_Latn",
    "tr": "tur_Latn",
    "uk": "ukr_Cyrl",
    "sv": "swe_Latn",
    "cs": "ces_Latn",
    "el": "ell_Grek",
    "he": "heb_Hebr",
}

DEFAULT_MODEL_REPO = "Tushe/nllb-200-600M-ct2-int8"
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

class TranslationEngine:
    """
    Offline Neural Machine Translation engine powered by CTranslate2 and Meta NLLB-200.
    Engineered for complete sentence context, semantic correctness, and zero gaming impact.
    """

    def __init__(self):
        self.config = load_config()
        self.lock = threading.Lock()
        self.translator: Optional[Any] = None
        self.tokenizer: Optional[Any] = None
        self.model_path = os.path.join(MODELS_DIR, "nllb-200-600m-int8")
        self.is_loading = False
        self.load_error: Optional[str] = None
        self.is_ready = False

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_ready": self.is_ready,
            "is_loading": self.is_loading,
            "model_downloaded": os.path.exists(self.model_path),
            "load_error": self.load_error,
            "device": self.config.get("device", "cpu"),
            "accuracy_mode": self.config.get("accuracy_mode", "deep_thought"),
        }

    def ensure_model_downloaded(self, progress_callback=None) -> str:
        """Downloads the int8 quantized NLLB model (~620MB) if not already present."""
        os.makedirs(MODELS_DIR, exist_ok=True)
        if not os.path.exists(os.path.join(self.model_path, "model.bin")):
            print(f"[Engine] Downloading offline model from {DEFAULT_MODEL_REPO} to {self.model_path}...")
            snapshot_download(
                repo_id=DEFAULT_MODEL_REPO,
                local_dir=self.model_path,
                local_dir_use_symlinks=False
            )
            print("[Engine] Offline model download complete.")
        return self.model_path

    def load_model(self) -> bool:
        if self.is_ready:
            return True

        with self.lock:
            if self.is_ready:
                return True
            self.is_loading = True
            self.load_error = None

            try:
                if not CT2_AVAILABLE:
                    raise RuntimeError("ctranslate2 or transformers package not available")

                self.ensure_model_downloaded()

                device = self.config.get("device", "cpu")
                compute_type = self.config.get("compute_type", "int8")
                threads = self.config.get("max_cpu_threads", 2)

                print(f"[Engine] Loading CTranslate2 model on device: {device} ({compute_type}) with {threads} threads...")

                # Intra-threads in Translator handles CPU thread capping for inference


                self.translator = ctranslate2.Translator(
                    self.model_path,
                    device=device,
                    compute_type=compute_type,
                    inter_threads=1,
                    intra_threads=threads
                )

                # NLLB tokenizer loaded via HuggingFace transformers
                try:
                    self.tokenizer = NllbTokenizerFast.from_pretrained(
                        "facebook/nllb-200-distilled-600M"
                    )
                except Exception:
                    self.tokenizer = AutoTokenizer.from_pretrained(
                        self.model_path,
                        src_lang="eng_Latn"
                    )

                self.is_ready = True
                self.is_loading = False
                print("[Engine] Translation engine loaded and ready!")
                return True

            except Exception as e:
                self.is_loading = False
                self.load_error = str(e)
                print(f"[Engine] Failed to load model: {e}")
                return False

    # Characters from scripts that are never English. If any appear, the text is definitely foreign
    # and langdetect is reliable for these scripts.
    _NON_LATIN_SCRIPT = re.compile(
        r"[\u0370-\u03FF\u0400-\u04FF\u0500-\u052F\u0590-\u05FF\u0600-\u06FF\u0900-\u097F"
        r"\u0E00-\u0E7F\u1100-\u11FF\u3040-\u30FF\u3130-\u318F\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF]"
    )
    # Accented Latin letters (é, ñ, ü, ß, ą, ç, ...) are a strong hint of a non-English Latin language.
    _ACCENTED_LATIN = re.compile(r"[\u00C0-\u00FF\u0100-\u024F]")

    # Common English words + gaming/chat slang. Short Discord messages ("gg wp", "lol ok", "idk tbh")
    # are mostly made of these, and langdetect misclassifies them as Tagalog/Slovak/Swedish/etc.
    # Deliberately EXCLUDES short words that are also common in Spanish/Portuguese/French/Italian/German/Dutch
    # (a, am, an, come, die, in, man, me, no, on, or, so, was, will, ...) so foreign text isn't mistaken for English.
    _ENGLISH_WORDS = frozenset("""
        about after again all also always any anyone are around as at away back be because been
        before being best better big both but by came can cant could day did didnt do does doesnt doing
        done dont down each even ever every first for from get gets getting give go goes going gone good got
        great had has have he her here him his how i if im into is isnt it its ive just know last later let
        lets like little long look lot made make many may more most much must my need never new next not
        nothing now of off ok okay once one only other our out over people please put really right said
        same say see she should since some someone something soon still such sure take than thank thanks that
        thats the their them then there these they thing things think this those though time to today tomorrow
        tonight too try two up us use very want way we well went were what when where which while who why
        with without wont work would yeah yes yet you your youre yours
        hi hello hey bye yo sup thx ty tysm pls plz np nvm idk idc imo imho tbh btw brb afk gg wp ggwp glhf gl hf
        lol lmao lmfao rofl omg omfg wtf wth smh fr ngl irl dm dms rn ikr jk lmk wyd hbu ez op nerf buff
        noob nub pog poggers kek xd haha hahaha hehe lul k kk yep yup nope nah cool nice dude bro
        guys guy true false mood raid boss server channel online offline game play playing join ready
    """.split())

    def detect_language(self, text: str) -> str:
        """
        Detects the ISO 639-1 language code of the text.

        Returns "und" (undetermined) when the text is too short/ambiguous to classify confidently.
        Callers should treat "und" as "don't translate" rather than guessing.
        """
        # Strip things that carry no language signal: links, Discord tokens (<@id>, <:emoji:id>),
        # :shortcodes:, @mentions/[TAGS], digits and punctuation.
        clean = re.sub(r"https?://\S+|<[^>]+>|:[\w\-~]+:|@\S+|\[[^\]]*\]", " ", text)
        clean = re.sub(r"[\d\W_]+", " ", clean).strip()
        if len(clean) < 2:
            return "und"

        # 1) Non-Latin scripts (Cyrillic, CJK, Kana, Hangul, Arabic, Hebrew, Greek, Thai, Devanagari):
        #    langdetect is accurate here.
        if self._NON_LATIN_SCRIPT.search(clean):
            try:
                return langdetect.detect(clean)
            except Exception:
                return "und"

        words = clean.lower().split()
        has_accents = bool(self._ACCENTED_LATIN.search(clean))

        # 2) Plain-ASCII text made mostly of English words/slang -> English.
        if not has_accents and words:
            english_hits = sum(1 for w in words if w in self._ENGLISH_WORDS)
            if english_hits / len(words) >= 0.6:
                return "en"

        # 3) Otherwise ask langdetect, but only trust a confident answer on enough text.
        try:
            candidates = langdetect.detect_langs(clean)
        except Exception:
            return "und"
        if not candidates:
            return "und"
        best = candidates[0]

        # Accented text is very likely foreign, so accept a lower bar; plain ASCII needs more evidence.
        min_prob = 0.80 if has_accents else 0.95
        min_words = 2 if has_accents else 3
        if best.prob >= min_prob and len(words) >= min_words:
            return best.lang
        return "und"

    def to_nllb_lang(self, lang_code: str) -> str:
        code_clean = lang_code.lower().strip()
        return NLLB_LANG_MAP.get(code_clean, "eng_Latn")

    def translate_text(
        self,
        text: str,
        source_lang: Optional[str] = None,
        target_lang: str = "en",
        mode: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Translates text with full sentence preservation, context awareness,
        and Discord token protection.
        """
        if not text or not text.strip():
            return {"translated_text": text, "source_lang": source_lang or "en", "target_lang": target_lang}

        # Convert emoji shortcodes (e.g. :white_check_mark:, :globe_with_meridians:) to actual graphical Unicode emojis
        try:
            import emoji
            text = emoji.emojize(text, language="alias")
        except Exception:
            pass

        # Auto-detect language if not provided
        if not source_lang or source_lang == "auto":
            source_lang = self.detect_language(text)

        def skip(reason: str) -> Dict[str, Any]:
            return {
                "translated_text": text,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "skipped": True,
                "skip_reason": reason,
            }

        # Undetermined (too short / ambiguous) -> don't guess, leave the message alone
        if source_lang == "und":
            return skip("language undetermined")

        # If source is already target language, skip translation
        if source_lang == target_lang:
            return skip("already in target language")

        # Unsupported source language: previously this silently mapped to English, which produced
        # English -> English "translations". Skip instead.
        if source_lang.lower().strip() not in NLLB_LANG_MAP:
            return skip(f"unsupported source language '{source_lang}'")
        if self.to_nllb_lang(source_lang) == self.to_nllb_lang(target_lang):
            return skip("source and target map to the same model language")

        # Lazy load model if not yet loaded
        if not self.is_ready:
            success = self.load_model()
            if not success:
                return {
                    "error": f"Model failed to load: {self.load_error}",
                    "translated_text": text,
                    "source_lang": source_lang,
                    "target_lang": target_lang
                }

        accuracy_mode = mode or self.config.get("accuracy_mode", "deep_thought")
        beam_size = self.config.get("beam_size", 4) if accuracy_mode == "deep_thought" else 1

        src_nllb = self.to_nllb_lang(source_lang)
        tgt_nllb = self.to_nllb_lang(target_lang)

        # Regex recognizing Unicode emojis, Discord custom emojis, mentions, links, and code blocks
        icon_pattern = regex.compile(
            r"(\p{Extended_Pictographic}(?:[\ufe0e\ufe0f]|\p{Emoji_Modifier}|\u200d\p{Extended_Pictographic})*|"
            r"<a?:[\w\-]+:\d+>|"
            r":[\w\-]+:|"
            r"<@!?\d+>|"
            r"<@&\d+>|"
            r"<#\d+>|"
            r"https?://\S+|"
            r"```[\s\S]*?```|"
            r"`[^`]+`)"
        )

        lines = text.split("\n")
        line_structures = []
        batch_tasks = []

        # Step 1: Parse lines and isolate translatable text from icons and bullets
        for line_idx, line in enumerate(lines):
            if not line.strip():
                line_structures.append([])
                continue

            parts = icon_pattern.split(line)
            current_line_tokens = []

            for part in parts:
                if not part:
                    continue

                # If this part is an icon, mention, link, or code block: keep as-is
                if icon_pattern.fullmatch(part.strip()):
                    current_line_tokens.append({"type": "verbatim", "content": part})
                elif part.strip():
                    # Preserve indentation and bullet formatting (e.g., "- ", "• ", "> ", "1. ")
                    leading_ws = part[:len(part) - len(part.lstrip())]
                    trailing_ws = part[len(part.rstrip()):]
                    trimmed = part.strip()

                    bullet_prefix = ""
                    for b in ["- ", "* ", "• ", "> ", "1. ", "2. ", "3. ", "4. ", "5. "]:
                        if trimmed.startswith(b):
                            bullet_prefix = b
                            trimmed = trimmed[len(b):]
                            break

                    if trimmed:
                        token_entry = {
                            "type": "translatable",
                            "leading": leading_ws,
                            "bullet": bullet_prefix,
                            "content": trimmed,
                            "trailing": trailing_ws,
                            "translated": trimmed
                        }
                        current_line_tokens.append(token_entry)
                        batch_tasks.append(token_entry)
                    else:
                        current_line_tokens.append({"type": "verbatim", "content": part})
                else:
                    current_line_tokens.append({"type": "verbatim", "content": part})

            line_structures.append(current_line_tokens)

        # Step 2: Batch translate all pure text chunks in a single vectorized pass
        if batch_tasks:
            with self.lock:
                self.tokenizer.src_lang = src_nllb
                target_prefix = [[tgt_nllb]] * len(batch_tasks)

                use_ru_slang = (
                    source_lang.lower().strip().split("-")[0] == "ru"
                    and self.config.get("ru_slang_normalize", True)
                )
                tokenized_batch = [
                    self.tokenizer.convert_ids_to_tokens(
                        self.tokenizer.encode(normalize_ru(task["content"]) if use_ru_slang else task["content"])
                    )
                    for task in batch_tasks
                ]

                results = self.translator.translate_batch(
                    tokenized_batch,
                    target_prefix=target_prefix,
                    beam_size=beam_size,
                    max_decoding_length=256,
                    repetition_penalty=1.2,
                    length_penalty=1.0 if accuracy_mode == "deep_thought" else 0.6
                )

                for task, res in zip(batch_tasks, results):
                    hyp = res.hypotheses[0]
                    if hyp and hyp[0] == tgt_nllb:
                        hyp = hyp[1:]
                    decoded = self.tokenizer.decode(
                        self.tokenizer.convert_tokens_to_ids(hyp),
                        skip_special_tokens=True
                    ).strip()
                    task["translated"] = decoded

        # Step 3: Reconstruct lines with exact newlines, bullets, and emojis preserved
        reconstructed_lines = []
        for line_tokens in line_structures:
            if not line_tokens:
                reconstructed_lines.append("")
                continue

            assembled_line = []
            for entry in line_tokens:
                if entry["type"] == "verbatim":
                    assembled_line.append(entry["content"])
                else:
                    assembled_line.append(f"{entry['leading']}{entry['bullet']}{entry['translated']}{entry['trailing']}")
            reconstructed_lines.append("".join(assembled_line))

        final_text = "\n".join(reconstructed_lines)

        # If the model just echoed the input back (ignoring case/whitespace/punctuation), it's not a translation.
        def _norm(s: str) -> str:
            return re.sub(r"[\W_]+", "", s).lower()
        if _norm(final_text) == _norm(text):
            return skip("translation identical to original")

        return {
            "original_text": text,
            "translated_text": final_text,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "accuracy_mode": accuracy_mode,
            "sentences_count": len(batch_tasks)
        }

engine_instance = TranslationEngine()
